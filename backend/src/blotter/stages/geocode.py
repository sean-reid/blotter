import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

import httpx
from shapely.geometry import Point, box

from blotter.config import GoogleGeocodingConfig, RegionConfig
from blotter.log import get_logger
from blotter.models import ExtractedLocation

log = get_logger(__name__)

ROAD_TYPES = {"route", "intersection", "street_address"}

_STREET_SUFFIXES = {
    "street", "st", "avenue", "ave", "boulevard", "blvd",
    "drive", "dr", "road", "rd", "way", "lane", "ln",
    "place", "pl", "court", "ct",
}
_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(_STREET_SUFFIXES, key=len, reverse=True)) + r")\.?$",
    re.IGNORECASE,
)


_DIRECTION_RE = re.compile(r"^(?:north|south|east|west|n|s|e|w)\.?\s+", re.IGNORECASE)
_NOISE_WORDS = {"the", "of", "and", "at", "in", "on", "to", "a", "an", "intersection"}


def _base_street_name(name: str) -> str:
    return _SUFFIX_RE.sub("", name).strip().rstrip(".")


def _significant_words(name: str) -> set[str]:
    name = _DIRECTION_RE.sub("", name)
    name = _SUFFIX_RE.sub("", name).strip()
    words = {w.lower().rstrip(".") for w in name.split()}
    return words - _NOISE_WORDS - _STREET_SUFFIXES


def _name_relevant(query: str, result_name: str) -> bool:
    q_words = _significant_words(query)
    r_words = _significant_words(result_name)
    if not q_words or not r_words:
        return True
    return bool(q_words & r_words)


def _prefer_original_name(original: str, geocoded: str) -> str:
    orig_base = _base_street_name(original).lower()
    geo_base = _base_street_name(geocoded).lower()
    if orig_base and orig_base == geo_base and _SUFFIX_RE.search(original):
        return original
    return geocoded


@dataclass(frozen=True)
class DivisionGeo:
    suffix: str
    bias_south: float
    bias_west: float
    bias_north: float
    bias_east: float
    bound_south: float
    bound_west: float
    bound_north: float
    bound_east: float

    @property
    def viewbox(self) -> str:
        return f"{self.bias_west},{self.bias_north},{self.bias_east},{self.bias_south}"

    def contains(self, lat: float, lon: float) -> bool:
        return (self.bound_south <= lat <= self.bound_north
                and self.bound_west <= lon <= self.bound_east)


DIVISIONS: dict[str, DivisionGeo] = {
    "south bureau": DivisionGeo(
        suffix="South Los Angeles, CA",
        bias_south=33.72, bias_west=-118.36, bias_north=34.02, bias_east=-118.19,
        bound_south=33.62, bound_west=-118.46, bound_north=34.12, bound_east=-118.09,
    ),
    "west bureau": DivisionGeo(
        suffix="West Los Angeles, CA",
        bias_south=33.93, bias_west=-118.52, bias_north=34.13, bias_east=-118.27,
        bound_south=33.83, bound_west=-118.62, bound_north=34.23, bound_east=-118.17,
    ),
    "valley bureau": DivisionGeo(
        suffix="San Fernando Valley, CA",
        bias_south=34.12, bias_west=-118.67, bias_north=34.35, bias_east=-118.35,
        bound_south=34.02, bound_west=-118.77, bound_north=34.45, bound_east=-118.25,
    ),
    "central bureau": DivisionGeo(
        suffix="Downtown Los Angeles, CA",
        bias_south=33.98, bias_west=-118.30, bias_north=34.10, bias_east=-118.19,
        bound_south=33.88, bound_west=-118.40, bound_north=34.20, bound_east=-118.09,
    ),
    "long beach": DivisionGeo(
        suffix="Long Beach, CA",
        bias_south=33.72, bias_west=-118.25, bias_north=33.88, bias_east=-118.06,
        bound_south=33.62, bound_west=-118.35, bound_north=33.98, bound_east=-117.96,
    ),
}


@dataclass(frozen=True)
class SystemRegion:
    suffix: str
    bias_south: float
    bias_west: float
    bias_north: float
    bias_east: float

    @property
    def viewbox(self) -> str:
        return f"{self.bias_west},{self.bias_north},{self.bias_east},{self.bias_south}"

    def contains(self, lat: float, lon: float) -> bool:
        return (self.bias_south - 0.15 <= lat <= self.bias_north + 0.15
                and self.bias_west - 0.15 <= lon <= self.bias_east + 0.15)


SYSTEM_REGIONS: dict[str, SystemRegion] = {
    "lapdvalley": SystemRegion(
        suffix="San Fernando Valley, CA",
        bias_south=34.02, bias_west=-118.77, bias_north=34.45, bias_east=-118.25,
    ),
    "lapdwest": SystemRegion(
        suffix="West Los Angeles, CA",
        bias_south=33.83, bias_west=-118.62, bias_north=34.23, bias_east=-118.17,
    ),
    "chi_cpd": SystemRegion(
        suffix="Chicago, IL",
        bias_south=41.64, bias_west=-87.84, bias_north=42.02, bias_east=-87.52,
    ),
    "cltp25": SystemRegion(
        suffix="Charlotte, NC",
        bias_south=35.05, bias_west=-81.01, bias_north=35.39, bias_east=-80.66,
    ),
    "philly": SystemRegion(
        suffix="Philadelphia, PA",
        bias_south=39.87, bias_west=-75.28, bias_north=40.14, bias_east=-74.96,
    ),
    "psern1": SystemRegion(
        suffix="Seattle, WA",
        bias_south=47.40, bias_west=-122.46, bias_north=47.78, bias_east=-122.10,
    ),
    "sfp25": SystemRegion(
        suffix="San Francisco, CA",
        bias_south=37.70, bias_west=-122.52, bias_north=37.83, bias_east=-122.35,
    ),
    "pgcomd": SystemRegion(
        suffix="Prince George's County, MD",
        bias_south=38.55, bias_west=-77.05, bias_north=39.00, bias_east=-76.65,
    ),
    "pdx2": SystemRegion(
        suffix="Portland, OR",
        bias_south=45.43, bias_west=-122.84, bias_north=45.65, bias_east=-122.47,
    ),
    "ntirnd1": SystemRegion(
        suffix="Dallas, TX",
        bias_south=32.62, bias_west=-97.00, bias_north=33.02, bias_east=-96.56,
    ),
    "nwhc": SystemRegion(
        suffix="Harris County, TX",
        bias_south=29.55, bias_west=-95.80, bias_north=30.15, bias_east=-95.20,
    ),
    "dane_com": SystemRegion(
        suffix="Madison, WI",
        bias_south=42.95, bias_west=-89.58, bias_north=43.20, bias_east=-89.20,
    ),
    "monroecony": SystemRegion(
        suffix="Rochester, NY",
        bias_south=43.05, bias_west=-77.75, bias_north=43.35, bias_east=-77.40,
    ),
    "dcfd": SystemRegion(
        suffix="Washington, DC",
        bias_south=38.80, bias_west=-77.12, bias_north=38.99, bias_east=-76.91,
    ),
    "mnhennco": SystemRegion(
        suffix="Minneapolis, MN",
        bias_south=44.85, bias_west=-93.50, bias_north=45.10, bias_east=-93.17,
    ),
    "njicsunion": SystemRegion(
        suffix="Union County, NJ",
        bias_south=40.55, bias_west=-74.45, bias_north=40.72, bias_east=-74.18,
    ),
    "gcrn": SystemRegion(
        suffix="Cleveland, OH",
        bias_south=41.37, bias_west=-81.88, bias_north=41.60, bias_east=-81.53,
    ),
    "mcbsimcast": SystemRegion(
        suffix="Macomb County, MI",
        bias_south=42.42, bias_west=-83.15, bias_north=42.72, bias_east=-82.80,
    ),
    "sc21102": SystemRegion(
        suffix="St. Clair County, IL",
        bias_south=38.40, bias_west=-90.20, bias_north=38.75, bias_east=-89.70,
    ),
    "scpd": SystemRegion(
        suffix="Suffolk County, NY",
        bias_south=40.60, bias_west=-73.40, bias_north=41.10, bias_east=-72.00,
    ),
    "snacc": SystemRegion(
        suffix="Las Vegas, NV",
        bias_south=35.90, bias_west=-115.40, bias_north=36.35, bias_east=-114.90,
    ),
    "apsp25": SystemRegion(
        suffix="Atlanta, GA",
        bias_south=33.65, bias_west=-84.55, bias_north=33.89, bias_east=-84.28,
    ),
    "bacop25": SystemRegion(
        suffix="Baltimore County, MD",
        bias_south=39.15, bias_west=-76.85, bias_north=39.50, bias_east=-76.45,
    ),
    "indydps": SystemRegion(
        suffix="Indianapolis, IN",
        bias_south=39.63, bias_west=-86.33, bias_north=39.93, bias_east=-85.95,
    ),
}


def _match_system(feed_id: str) -> SystemRegion | None:
    system = feed_id.rsplit("-", 1)[0] if "-" in feed_id else feed_id
    return SYSTEM_REGIONS.get(system)


def _match_division(feed_name: str) -> DivisionGeo | None:
    lower = feed_name.lower()
    for key, div in DIVISIONS.items():
        if key in lower:
            return div
    return None


_NOMINATIM_ROAD_CLASSES = {"highway", "junction"}
_NOMINATIM_ROAD_TYPES = {
    "residential", "primary", "secondary", "tertiary", "trunk",
    "motorway", "unclassified", "service", "living_street",
    "pedestrian", "track", "road", "path",
    "primary_link", "secondary_link", "tertiary_link", "trunk_link", "motorway_link",
    "intersection",
}


class PlaceResult:
    __slots__ = ("name", "lat", "lon", "osm_class", "osm_type")

    def __init__(self, name: str, lat: float, lon: float, osm_class: str, osm_type: str) -> None:
        self.name = name
        self.lat = lat
        self.lon = lon
        self.osm_class = osm_class
        self.osm_type = osm_type

    @property
    def is_road(self) -> bool:
        return self.osm_class in _NOMINATIM_ROAD_CLASSES or self.osm_type in _NOMINATIM_ROAD_TYPES


class Geocoder:
    def __init__(self, config: GoogleGeocodingConfig, region: RegionConfig) -> None:
        self.region = region
        self._default_bbox = box(region.bbox_west, region.bbox_south, region.bbox_east, region.bbox_north)
        self._default_viewbox = f"{region.bbox_west},{region.bbox_north},{region.bbox_east},{region.bbox_south}"
        self._client = httpx.Client(
            timeout=10,
            headers={"User-Agent": "blotter/1.0 (police-scanner-map)"},
        )
        self._rate_lock = threading.Lock()
        self._last_request = 0.0

    def _rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self._last_request = time.monotonic()

    def _in_bounds(self, lat: float, lon: float, system_region: SystemRegion | None = None) -> bool:
        if system_region:
            return system_region.contains(lat, lon)
        return self._default_bbox.contains(Point(lon, lat))

    @lru_cache(maxsize=4096)
    def _nominatim_lookup(self, query: str, viewbox: str | None = None) -> PlaceResult | None:
        self._rate_limit()
        try:
            params: dict[str, str] = {
                "q": query,
                "format": "json",
                "limit": "1",
                "addressdetails": "0",
            }
            vb = viewbox or self._default_viewbox
            if vb:
                params["viewbox"] = vb
                params["bounded"] = "0"

            resp = self._client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
            )
            resp.raise_for_status()
            results = resp.json()
        except Exception:
            log.warning("nominatim lookup failed", query=query)
            return None

        if not results:
            return None

        r = results[0]
        return PlaceResult(
            name=r.get("display_name", "").split(",")[0].strip(),
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            osm_class=r.get("class", ""),
            osm_type=r.get("type", ""),
        )

    def _resolve(
        self, query: str, label: str,
        division: DivisionGeo | None = None,
        system_region: SystemRegion | None = None,
    ) -> tuple[float, float, str] | None:
        viewbox = division.viewbox if division else (system_region.viewbox if system_region else None)
        result = self._nominatim_lookup(query, viewbox)
        if result is None:
            return None
        if not result.is_road:
            log.debug("not a road", clause=label[:60], name=result.name,
                      osm_class=result.osm_class, osm_type=result.osm_type)
            return None
        if not _name_relevant(label, result.name):
            log.info("name mismatch", query=label[:60], result=result.name)
            return None
        if not self._in_bounds(result.lat, result.lon, system_region):
            log.debug("outside bounds", clause=label[:60], lat=result.lat, lon=result.lon)
            return None
        if division and not division.contains(result.lat, result.lon):
            log.info("outside division", clause=label[:60], name=result.name,
                     lat=result.lat, lon=result.lon)
            return None
        log.info("resolved", clause=label[:60], name=result.name, lat=result.lat, lon=result.lon)
        return (result.lat, result.lon, result.name)

    def geocode(self, location: ExtractedLocation, feed_name: str = "", feed_id: str = "") -> tuple[float, float, str] | None:
        clause = location.normalized
        division = _match_division(feed_name) if feed_name else None
        system_region = _match_system(feed_id) if feed_id else None
        suffix = division.suffix if division else (system_region.suffix if system_region else self.region.location_suffix)

        if location.source == "nlp_intersection" and " and " in clause:
            parts = clause.split(" and ", 1)
            queries = [
                f"{parts[0]} and {parts[1]}, {suffix}",
                f"{parts[0]} & {parts[1]}, {suffix}",
            ]
            for q in queries:
                result = self._resolve(q, clause, division, system_region)
                if result:
                    return result
            return None

        result = self._resolve(f"{clause}, {suffix}", clause, division, system_region)
        if result:
            lat, lon, name = result
            return (lat, lon, _prefer_original_name(clause, name))
        return None
