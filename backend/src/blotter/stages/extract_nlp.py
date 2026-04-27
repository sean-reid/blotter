import re

import httpx

from blotter.config import GoogleNLPConfig
from blotter.log import get_logger
from blotter.models import ExtractedLocation
from blotter.stages.extract import strip_ads

log = get_logger(__name__)

LOCATION_TYPES = {"LOCATION", "ADDRESS"}
INTERSECTION_ENTITY_TYPES = {"LOCATION", "ADDRESS", "PERSON"}
MIN_SALIENCE = 0.03

JUNCTION_RE = re.compile(r"\band\b|\bat\b|&|/|,", re.IGNORECASE)

_CALLSIGN_NAMES = (
    "adam", "boy", "charles", "david", "edward", "frank", "george",
    "henry", "ida", "john", "king", "lincoln", "mary", "nora",
    "ocean", "paul", "queen", "robert", "sam", "tom", "union",
    "victor", "william", "x-ray", "xray", "young", "zebra",
)
_callsign_alt = "|".join(re.escape(n) for n in _CALLSIGN_NAMES)
UNIT_CALLSIGN_RE = re.compile(
    rf"\b\d{{1,3}}\s*-?\s*(?:{_callsign_alt})\s*-?\s*\d{{1,3}}\b"
    rf"|\b\d{{1,3}}\s*-?\s*(?:{_callsign_alt})\b"
    rf"|\b(?:{_callsign_alt})\s+\d{{1,3}}\b",
    re.IGNORECASE,
)

DISPATCH_REF_RE = re.compile(
    r"\bincident\s+[\w-]+"
    r"|\bcode\s+\d[\d-]+"
    r"|\bRD-?\d{3,}\b"
    r"|\b\d{3,}-[A-Z]{1,4}-[\w-]+\b",
    re.IGNORECASE,
)

_SUSPECT_STARTS = (
    "male", "female", "black", "white", "hispanic", "asian",
    "wearing", "approximately", "about", "described", "last seen",
    "fled", "running", "driving", "in custody", "armed", "unarmed",
    "thin", "heavy", "medium", "tall", "short", "unknown", "a ",
)
_suspect_alt = "|".join(re.escape(s) for s in _SUSPECT_STARTS)
SUSPECT_DESC_RE = re.compile(
    rf"\bsuspect\s+(?:is\s+)?(?:{_suspect_alt})[\w\s,''-]{{0,120}}"
    rf"(?=[.]|\b(?:code|incident|unit|respond|copy|roger)\b|$)"
    rf"|\b(?:male|female)\s+(?:black|white|hispanic|asian)\s*,?\s*\d{{1,2}}\s+years[\w\s,''-]{{0,80}}",
    re.IGNORECASE,
)

# Standalone words that NLP extracts as entities but are never dispatch locations.
SKIP_NAMES = {
    # dispatch roles / people
    "suspect", "victim", "male", "female", "supervisor", "officer",
    "informant", "complainant", "witness", "caller", "reporting party",
    "p.o.", "po", "pr", "rp",

    # generic place words
    "location", "area", "block", "scene", "route", "place",
    "corner", "island", "campus", "intersection",

    # standalone street type words (NLP sometimes returns just "Avenue")
    "street", "avenue", "boulevard", "road", "drive", "way",
    "lane", "place", "court", "alley",
    "freeway", "highway", "interstate",
    "onramp", "offramp", "off-ramp", "on-ramp",

    # cardinal directions
    "south", "north", "east", "west",
    "southwest", "southeast", "northeast", "northwest",

    # LAPD divisions / bureaus (not street addresses)
    "central", "pacific", "rampart", "hollenbeck", "harbor",
    "hollywood", "wilshire", "devonshire", "foothill", "topanga",
    "newton", "olympic", "mission", "van nuys",
    "west valley", "north hollywood", "west la",
    "77th street", "south bureau", "west bureau", "valley bureau",
    "central bureau",
    "division", "bureau", "station", "frequency",

    # LAPD station names (NLP extracts these as locations)
    "hollywood station", "wilshire station", "pacific station",
    "rampart station", "hollenbeck station", "harbor station",
    "newton station", "olympic station", "devonshire station",
    "foothill station", "topanga station", "mission station",
    "van nuys station", "west valley station", "north hollywood station",
    "west la station", "77th street station", "southeast station",
    "southwest station", "central station",

    # LAPD phonetic alphabet (standalone)
    "charles", "adam", "lincoln", "mary", "boy", "king", "tom",

    # dispatch vocabulary
    "unit", "dispatch", "ambulance", "backup", "custody",
    "stop", "roger", "roger that", "number one",
    "front desk", "front", "desk", "system", "radio", "channel",
    "team", "team family", "family",

    # common NLP false positives
    "people", "president", "minorities",
    "cash back", "insurance", "commercial",
    "wood", "james", "beach", "garden", "park", "hill",
}

STREET_SUFFIX_RE = re.compile(
    r"\b(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|way|"
    r"lane|ln|place|pl|court|ct|highway|hwy|freeway|fwy)\b",
    re.IGNORECASE,
)

STREET_ADDRESS_RE = re.compile(
    r"\b(\d{1,5}\s+"
    r"(?:north|south|east|west|n\.?|s\.?|e\.?|w\.?)?\s*"
    r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?\s+"
    r"(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|way|lane|ln|place|pl|court|ct))"
    r"\b\.?",
    re.IGNORECASE,
)

CODE_PATTERN_RE = re.compile(
    r"^(?:RD|rd|incident|code|unit)\s*[-#]?\s*[\d][\d-]*$",
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
        if not JUNCTION_RE.search(between):
            continue
        if not _is_plausible_location(name_a) or not _is_plausible_location(name_b):
            continue
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


def _extract_addresses(text: str) -> list[ExtractedLocation]:
    """Extract explicit street addresses (e.g. '115 South Conway Street') from text."""
    locations = []
    seen: set[str] = set()
    for m in STREET_ADDRESS_RE.finditer(text):
        addr = m.group(1).strip()
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        locations.append(ExtractedLocation(
            raw_text=addr,
            normalized=addr,
            confidence=0.9,
            source="address",
            context=_get_context(text, addr),
        ))
    return locations


def extract_entities(text: str, config: GoogleNLPConfig) -> list[ExtractedLocation]:
    cleaned = strip_ads(text)
    if not cleaned or not config.api_key:
        return []

    addresses = _extract_addresses(cleaned)

    cleaned = UNIT_CALLSIGN_RE.sub("", cleaned)
    cleaned = DISPATCH_REF_RE.sub("", cleaned)
    cleaned = SUSPECT_DESC_RE.sub("", cleaned)

    try:
        entities = _call_nlp(cleaned, config.api_key)
    except Exception:
        log.warning("nlp entity extraction failed", exc_info=True)
        return addresses

    intersections = _find_intersections(cleaned, entities)
    intersection_names = {name for name, _ in intersections}

    seen: set[str] = {loc.normalized.lower() for loc in addresses}
    locations: list[ExtractedLocation] = list(addresses)

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
        salience = entity.get("salience", 0.0)
        if salience < MIN_SALIENCE:
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
            confidence=salience,
            source="nlp",
            context=_get_context(text, mention_text),
        ))

    locations = _dedup_locations(locations)
    log.info("nlp entities extracted", count=len(locations),
             addresses=len(addresses), intersections=len(intersections))
    return locations
