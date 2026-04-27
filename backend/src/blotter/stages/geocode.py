from functools import lru_cache

import httpx
from shapely.geometry import Point, box

from blotter.config import GoogleGeocodingConfig, RegionConfig
from blotter.log import get_logger
from blotter.models import ExtractedLocation

log = get_logger(__name__)

ROAD_TYPES = {"route", "intersection", "street_address"}

DIVISION_BIAS: dict[str, tuple[str, str]] = {
    "south bureau": (
        "rectangle:33.72,-118.36|34.02,-118.19",
        "South Los Angeles, CA",
    ),
    "west bureau": (
        "rectangle:33.93,-118.52|34.13,-118.27",
        "West Los Angeles, CA",
    ),
    "valley bureau": (
        "rectangle:34.12,-118.67|34.35,-118.35",
        "San Fernando Valley, CA",
    ),
    "central bureau": (
        "rectangle:33.98,-118.30|34.10,-118.19",
        "Downtown Los Angeles, CA",
    ),
    "long beach": (
        "rectangle:33.72,-118.25|33.88,-118.06",
        "Long Beach, CA",
    ),
}


def _get_feed_bias(feed_name: str) -> tuple[str, str] | None:
    lower = feed_name.lower()
    for key, bias in DIVISION_BIAS.items():
        if key in lower:
            return bias
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

    def _resolve(self, query: str, label: str, bias: str | None = None) -> tuple[float, float, str] | None:
        result = self._places_lookup(query, bias)
        if result is None:
            return None
        if not result.is_road:
            log.debug("not a road", clause=label[:60], name=result.name, types=result.types[:3])
            return None
        if not self._in_bounds(result.lat, result.lon):
            log.debug("outside bounds", clause=label[:60], lat=result.lat, lon=result.lon)
            return None
        log.info("resolved", clause=label[:60], name=result.name, lat=result.lat, lon=result.lon)
        return (result.lat, result.lon, result.name)

    def geocode(self, location: ExtractedLocation, feed_name: str = "") -> tuple[float, float, str] | None:
        clause = location.normalized
        suffix = self.region.location_suffix
        bias: str | None = None

        feed_bias = _get_feed_bias(feed_name) if feed_name else None
        if feed_bias:
            bias, suffix = feed_bias

        if location.source == "nlp_intersection" and " and " in clause:
            parts = clause.split(" and ", 1)
            queries = [
                f"intersection of {parts[0]} and {parts[1]}, {suffix}",
                f"{parts[0]} & {parts[1]}, {suffix}",
            ]
            for q in queries:
                result = self._resolve(q, clause, bias)
                if result:
                    return result
            return None

        return self._resolve(f"{clause}, {suffix}", clause, bias)
