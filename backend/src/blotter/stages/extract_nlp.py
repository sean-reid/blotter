import re

import httpx

from blotter.config import GoogleNLPConfig
from blotter.log import get_logger
from blotter.models import ExtractedLocation
from blotter.stages.extract import strip_ads

log = get_logger(__name__)

LOCATION_TYPES = {"LOCATION", "ADDRESS"}
INTERSECTION_ENTITY_TYPES = {"LOCATION", "ADDRESS", "PERSON"}

JUNCTION_RE = re.compile(r"\band\b|\bat\b|&|/|,", re.IGNORECASE)

SKIP_NAMES = {
    "location", "area", "block", "scene", "route", "unit", "dispatch",
    "suspect", "victim", "male", "female", "supervisor", "officer",
    "ambulance", "backup", "custody", "place", "number one",
    "south", "north", "east", "west", "people", "president",
    "minorities", "corner", "letter location", "island", "street",
    "stop", "roger", "roger that",
    "southwest", "southeast", "northeast", "northwest",
    "central", "pacific", "rampart", "hollenbeck", "harbor",
    "hollywood", "wilshire", "devonshire", "foothill", "topanga",
    "newton", "olympic", "mission", "van nuys",
    "division", "bureau", "station", "frequency",
    "charles", "adam", "lincoln", "mary", "boy", "king", "tom",
    "front desk", "front", "desk", "system", "radio", "channel",
    "cash back", "insurance", "commercial", "campus",
    "wood", "james", "beach", "garden", "park", "hill",
    "freeway", "highway", "interstate", "onramp", "offramp", "off-ramp", "on-ramp",
}

STREET_SUFFIX_RE = re.compile(
    r"\b(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|way|"
    r"lane|ln|place|pl|court|ct|highway|hwy|freeway|fwy)\b",
    re.IGNORECASE,
)

CODE_PATTERN_RE = re.compile(
    r"^(?:RD|rd|incident|code|unit)\s*[-#]?\s*\d+$",
    re.IGNORECASE,
)

FREEWAY_RE = re.compile(
    r"^(?:the\s+)?\d+\s*(?:freeway|fwy)?\s*(?:north|south|east|west|northbound|southbound|eastbound|westbound|nb|sb|eb|wb)$"
    r"|^(?:the\s+)?\d+\s+(?:freeway|fwy)$"
    r"|^(?:i-?\d+|us-?\d+|sr-?\d+|ca-?\d+|hwy\s*\d+)\s*(?:north|south|east|west|northbound|southbound|eastbound|westbound|nb|sb|eb|wb)?$"
    r"|^freeway\s+(?:north|south|east|west)$",
    re.IGNORECASE,
)


def _is_plausible_location(name: str) -> bool:
    if CODE_PATTERN_RE.match(name):
        return False
    if name.isdigit():
        return False
    if FREEWAY_RE.match(name):
        return False
    words = name.split()
    if len(words) == 1 and not STREET_SUFFIX_RE.search(name):
        return False
    return True


def _get_context(text: str, mention: str, window: int = 120) -> str:
    idx = text.find(mention)
    if idx == -1:
        return mention[:250]
    start = max(0, idx - window)
    end = min(len(text), idx + len(mention) + window)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def _call_nlp(text: str, api_key: str) -> list[dict]:
    resp = httpx.post(
        "https://language.googleapis.com/v1/documents:analyzeEntities",
        params={"key": api_key},
        json={
            "document": {"type": "PLAIN_TEXT", "content": text},
            "encodingType": "UTF8",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("entities", [])


def _mention_offset(entity: dict) -> int | None:
    mentions = entity.get("mentions", [])
    if not mentions:
        return None
    return mentions[0].get("text", {}).get("beginOffset")


def _ordinal_at(text: str, offset: int, num_len: int) -> str | None:
    end = offset + num_len
    suffix = text[end:end + 2].lower()
    if suffix[:2] in ("th", "st", "nd", "rd"):
        return text[offset:end + 2]
    return None


def _find_intersections(text: str, entities: list[dict]) -> list[tuple[str, int]]:
    located = []
    for e in entities:
        etype = e.get("type")
        offset = _mention_offset(e)
        if offset is None:
            continue
        name = e.get("name", "").strip()
        mention = e.get("mentions", [{}])[0].get("text", {}).get("content", name)

        if etype in INTERSECTION_ENTITY_TYPES:
            if name.lower() in SKIP_NAMES or len(name) < 3 or not _is_plausible_location(name):
                continue
            located.append((name, offset, len(mention)))
        elif etype == "NUMBER":
            ordinal = _ordinal_at(text, offset, len(mention))
            if ordinal:
                located.append((ordinal, offset, len(ordinal)))

    located.sort(key=lambda x: x[1])

    intersections: list[tuple[str, int]] = []
    for i in range(len(located) - 1):
        name_a, off_a, len_a = located[i]
        name_b, off_b, _ = located[i + 1]
        gap_start = off_a + len_a
        gap_end = off_b
        if gap_end - gap_start > 15:
            continue
        between = text[gap_start:gap_end]
        if JUNCTION_RE.search(between):
            combined = f"{name_a} and {name_b}"
            intersections.append((combined, off_a))

    return intersections


def _dedup_locations(locations: list[ExtractedLocation]) -> list[ExtractedLocation]:
    """Remove locations that are substrings of other resolved locations."""
    result = []
    names = {loc.normalized.lower() for loc in locations}
    for loc in locations:
        name_lower = loc.normalized.lower()
        is_substring = any(
            name_lower != other and name_lower in other
            for other in names
        )
        if not is_substring:
            result.append(loc)
        else:
            log.debug("dedup substring", name=loc.normalized)
    return result


def extract_entities(text: str, config: GoogleNLPConfig) -> list[ExtractedLocation]:
    cleaned = strip_ads(text)
    if not cleaned or not config.api_key:
        return []

    try:
        entities = _call_nlp(cleaned, config.api_key)
    except Exception:
        log.warning("nlp entity extraction failed", exc_info=True)
        return []

    intersections = _find_intersections(cleaned, entities)
    intersection_names = {name for name, _ in intersections}

    seen: set[str] = set()
    locations: list[ExtractedLocation] = []

    for name, offset in intersections:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        locations.append(ExtractedLocation(
            raw_text=name,
            normalized=name,
            confidence=0.8,
            source="nlp_intersection",
            context=_get_context(text, name.split(" and ")[0]),
        ))

    for entity in entities:
        etype = entity.get("type")
        if etype not in LOCATION_TYPES:
            continue
        name = entity.get("name", "").strip()
        if name.lower() in SKIP_NAMES or len(name) < 3:
            continue
        if not _is_plausible_location(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        already_in_intersection = any(key in iname.lower() for iname in intersection_names)
        if already_in_intersection:
            continue
        seen.add(key)

        mentions = entity.get("mentions", [])
        mention_text = mentions[0]["text"]["content"] if mentions else name

        locations.append(ExtractedLocation(
            raw_text=mention_text,
            normalized=name,
            confidence=entity.get("salience", 0.0),
            source="nlp",
            context=_get_context(text, mention_text),
        ))

    locations = _dedup_locations(locations)
    log.info("nlp entities extracted", count=len(locations), intersections=len(intersections))
    return locations
