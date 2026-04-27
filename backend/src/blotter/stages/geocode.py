import re
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
    def places_bias(self) -> str:
        return f"rectangle:{self.bias_south},{self.bias_west}|{self.bias_north},{self.bias_east}"

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


def _match_division(feed_name: str) -> DivisionGeo | None:
    lower = feed_name.lower()
    for key, div in DIVISIONS.items():
        if key in lower:
            return div
    return None


class PlaceResult:
    __slots__ = ("name", "lat", "lon", "types")

    def __init__(self, name: str, lat: float, lon: float, types: list[str]) -> None:
        self.name = name
        self.lat = lat
        self.lon = lon
        self.types = types

    @property
    def is_road(self) -> bool:
        if set(self.types) & ROAD_TYPES:
            return True
        if "/" in self.name and "transit_station" in self.types:
            return True
        return False


class Geocoder:
    def __init__(self, config: GoogleGeocodingConfig, region: RegionConfig) -> None:
        self.api_key = config.api_key
        self.region = region
        self._bbox = box(region.bbox_west, region.bbox_south, region.bbox_east, region.bbox_north)

    def _in_bounds(self, lat: float, lon: float) -> bool:
        return self._bbox.contains(Point(lon, lat))

    @lru_cache(maxsize=4096)
    def _places_lookup(self, query: str, bias: str | None = None) -> PlaceResult | None:
        try:
            resp = httpx.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={
                    "input": query,
                    "inputtype": "textquery",
                    "fields": "geometry,name,types",
                    "locationbias": bias or self.region.places_bias,
                    "key": self.api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.warning("places lookup failed", query=query)
            return None

        candidates = data.get("candidates", [])
        if not candidates:
            return None

        c = candidates[0]
        loc = c["geometry"]["location"]
        return PlaceResult(
            name=c.get("name", ""),
            lat=loc["lat"],
            lon=loc["lng"],
            types=c.get("types", []),
        )

    def _resolve(
        self, query: str, label: str,
        division: DivisionGeo | None = None,
    ) -> tuple[float, float, str] | None:
        bias = division.places_bias if division else None
        result = self._places_lookup(query, bias)
        if result is None:
            return None
        if not result.is_road:
            log.debug("not a road", clause=label[:60], name=result.name, types=result.types[:3])
            return None
        if not _name_relevant(label, result.name):
            log.info("name mismatch", query=label[:60], result=result.name)
            return None
        if not self._in_bounds(result.lat, result.lon):
            log.debug("outside bounds", clause=label[:60], lat=result.lat, lon=result.lon)
            return None
        if division and not division.contains(result.lat, result.lon):
            log.info("outside division", clause=label[:60], name=result.name,
                     lat=result.lat, lon=result.lon)
            return None
        log.info("resolved", clause=label[:60], name=result.name, lat=result.lat, lon=result.lon)
        return (result.lat, result.lon, result.name)

    def geocode(self, location: ExtractedLocation, feed_name: str = "") -> tuple[float, float, str] | None:
        clause = location.normalized
        division = _match_division(feed_name) if feed_name else None
        suffix = division.suffix if division else self.region.location_suffix

        if location.source == "nlp_intersection" and " and " in clause:
            parts = clause.split(" and ", 1)
            queries = [
                f"intersection of {parts[0]} and {parts[1]}, {suffix}",
                f"{parts[0]} & {parts[1]}, {suffix}",
                f"intersection of {parts[1]} and {parts[0]}, {suffix}",
            ]
            for q in queries:
                result = self._resolve(q, clause, division)
                if result:
                    return result
            return None

        result = self._resolve(f"{clause}, {suffix}", clause, division)
        if result:
            lat, lon, name = result
            return (lat, lon, _prefer_original_name(clause, name))
        return None
