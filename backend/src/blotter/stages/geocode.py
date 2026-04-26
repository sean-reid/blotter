from functools import lru_cache

from geopy.geocoders import Nominatim
from shapely.geometry import Point, box

from blotter.config import NominatimConfig
from blotter.log import get_logger
from blotter.models import ExtractedLocation

log = get_logger(__name__)

SCC_BBOX = box(-122.2, 36.9, -121.2, 37.5)


class Geocoder:
    def __init__(self, config: NominatimConfig) -> None:
        self.config = config
        viewbox_parts = config.viewbox.split(",")
        self.viewbox = (
            (float(viewbox_parts[0]), float(viewbox_parts[1])),
            (float(viewbox_parts[2]), float(viewbox_parts[3])),
        )
        self.nominatim = Nominatim(
            domain=config.url.replace("http://", "").replace("https://", ""),
            scheme="http",
            user_agent="blotter/0.1",
        )

    @lru_cache(maxsize=2048)
    def _geocode_string(self, query: str) -> tuple[float, float] | None:
        try:
            result = self.nominatim.geocode(
                query,
                viewbox=self.viewbox,
                bounded=self.config.bounded,
                country_codes=self.config.country_codes,
                exactly_one=True,
                timeout=10,
            )
        except Exception:
            log.warning("geocoding failed", query=query)
            return None

        if result is None:
            return None

        point = Point(result.longitude, result.latitude)
        if not SCC_BBOX.contains(point):
            log.debug("geocode result outside SCC bounds", query=query, lat=result.latitude, lon=result.longitude)
            return None

        return (result.latitude, result.longitude)

    def geocode(self, location: ExtractedLocation) -> tuple[float, float] | None:
        result = self._geocode_string(location.normalized)
        if result is None:
            result = self._geocode_string(f"{location.normalized}, Santa Clara County, CA")
        return result
