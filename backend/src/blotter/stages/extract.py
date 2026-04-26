import re
from functools import lru_cache

from blotter.log import get_logger
from blotter.models import ExtractedLocation
from blotter.scc_data import ALL_LOCATIONS, SCC_ABBREVIATIONS, SCC_CITIES

log = get_logger(__name__)

STREET_SUFFIXES = (
    r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Dr(?:ive)?|Ct|Court|"
    r"Ln|Lane|Way|Rd|Road|Pl(?:ace)?|Cir(?:cle)?|Ter(?:race)?|"
    r"Pkwy|Parkway|Hwy|Highway|Expy|Expressway)"
)

STREET_WORD = r"[A-Z][a-zA-Z']+"
STREET_NAME = rf"(?:{STREET_WORD}(?:\s+{STREET_WORD}){{0,3}})"

ADDRESS_RE = re.compile(
    rf"\b(\d{{1,5}}\s+{STREET_NAME}\s+{STREET_SUFFIXES})\b",
    re.IGNORECASE,
)

BLOCK_RE = re.compile(
    rf"\b(\d{{1,4}}00?\s+block\s+(?:of\s+)?{STREET_NAME}(?:\s+{STREET_SUFFIXES})?)\b",
    re.IGNORECASE,
)

INTERSECTION_CONNECTORS = r"(?:and|&|at|/|cross(?:ing)?\s+of|x)"
INTERSECTION_RE = re.compile(
    rf"\b({STREET_NAME}(?:\s+{STREET_SUFFIXES})?\s+{INTERSECTION_CONNECTORS}\s+"
    rf"{STREET_NAME}(?:\s+{STREET_SUFFIXES})?)\b",
    re.IGNORECASE,
)

PROXIMITY_RE = re.compile(
    r"\b(?:near|vicinity\s+of|in\s+the\s+area\s+of|area\s+of|behind|"
    r"in\s+front\s+of|adjacent\s+to|across\s+from|next\s+to)\s+"
    rf"({STREET_NAME}(?:\s+{STREET_SUFFIXES})?(?:\s+{INTERSECTION_CONNECTORS}\s+"
    rf"{STREET_NAME}(?:\s+{STREET_SUFFIXES})?)?)",
    re.IGNORECASE,
)

HWY_RE = re.compile(
    r"\b((?:northbound|southbound|eastbound|westbound|NB|SB|EB|WB)\s+"
    r"(?:(?:Highway|Hwy|Interstate|I|Route|SR|US)\s*-?\s*)?\d{1,3}"
    r"(?:\s+(?:at|near|and|/)\s+[A-Z][a-zA-Z' ]{2,30})?)\b",
    re.IGNORECASE,
)

HWY_EXIT_RE = re.compile(
    r"\b((?:Highway|Hwy|Interstate|I|Route|SR|US)\s*-?\s*\d{1,3}"
    r"\s+(?:at|near|and|/|exit)\s+[A-Z][a-zA-Z' ]{2,30})\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _abbreviation_patterns() -> list[tuple[re.Pattern[str], str]]:
    return [
        (re.compile(rf"\b{re.escape(abbrev)}\b", re.IGNORECASE), expansion)
        for abbrev, expansion in SCC_ABBREVIATIONS.items()
    ]


def normalize_text(text: str) -> str:
    normalized = text
    for pattern, expansion in _abbreviation_patterns():
        normalized = pattern.sub(expansion, normalized)
    return normalized


def extract_landmarks(text: str) -> list[ExtractedLocation]:
    locations: list[ExtractedLocation] = []
    text_lower = text.lower()
    for pattern, canonical in ALL_LOCATIONS.items():
        if pattern in text_lower:
            locations.append(ExtractedLocation(
                raw_text=pattern,
                normalized=canonical,
                confidence=0.9,
                source="lookup",
            ))
    return locations


def extract_addresses(text: str) -> list[ExtractedLocation]:
    locations: list[ExtractedLocation] = []

    for match in ADDRESS_RE.finditer(text):
        locations.append(ExtractedLocation(
            raw_text=match.group(1).strip(),
            normalized=match.group(1).strip(),
            confidence=0.85,
            source="regex_address",
        ))

    for match in BLOCK_RE.finditer(text):
        raw = match.group(1).strip()
        normalized = re.sub(r"(\d+)00?\s+block\s+(?:of\s+)?", r"\g<1>50 ", raw, flags=re.IGNORECASE)
        locations.append(ExtractedLocation(
            raw_text=raw,
            normalized=normalized,
            confidence=0.7,
            source="regex_block",
        ))

    for match in INTERSECTION_RE.finditer(text):
        locations.append(ExtractedLocation(
            raw_text=match.group(1).strip(),
            normalized=match.group(1).strip().replace(" x ", " and ").replace("/", " and "),
            confidence=0.75,
            source="regex_intersection",
        ))

    for match in PROXIMITY_RE.finditer(text):
        locations.append(ExtractedLocation(
            raw_text=match.group(0).strip(),
            normalized=match.group(1).strip(),
            confidence=0.6,
            source="regex_proximity",
        ))

    for match in HWY_RE.finditer(text):
        locations.append(ExtractedLocation(
            raw_text=match.group(1).strip(),
            normalized=match.group(1).strip(),
            confidence=0.7,
            source="regex_highway",
        ))

    for match in HWY_EXIT_RE.finditer(text):
        locations.append(ExtractedLocation(
            raw_text=match.group(1).strip(),
            normalized=match.group(1).strip(),
            confidence=0.7,
            source="regex_highway_exit",
        ))

    log.info("regex extraction", count=len(locations))
    return locations


def split_dispatch_segments(text: str) -> list[str]:
    segments = re.split(
        r'(?:(?:^|\.\s+|\.\.\.\s*|,\s+)'
        r'(?:(?:unit|adam|boy|charlie|david|edward|frank|george|henry|ida|'
        r'john|king|lincoln|mary|nora|ocean|paul|queen|robert|sam|tom|'
        r'union|victor|william|x-ray|young|zebra)\s*\d+|'
        r'(?:dispatch|copy|roger|10-4|affirmative|negative|clear|code\s*\d+))'
        r'[\s,]*)',
        text,
        flags=re.IGNORECASE,
    )
    result = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) > 10:
            result.append(seg)
    if not result:
        result = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    return result


def extract_with_usaddress(text: str) -> list[ExtractedLocation]:
    try:
        import usaddress
    except ImportError:
        log.warning("usaddress not installed, skipping")
        return []

    locations: list[ExtractedLocation] = []
    segments = split_dispatch_segments(text)

    for segment in segments:
        try:
            tagged, addr_type = usaddress.tag(segment)
            if addr_type in ("Street Address", "Intersection"):
                if addr_type == "Street Address" and "AddressNumber" in tagged:
                    parts = []
                    for label in [
                        "AddressNumber", "StreetNamePreDirectional",
                        "StreetNamePreModifier", "StreetNamePreType",
                        "StreetName", "StreetNamePostType",
                        "StreetNamePostDirectional",
                    ]:
                        if label in tagged:
                            parts.append(tagged[label])
                    if len(parts) >= 2:
                        normalized = " ".join(parts)
                        city = tagged.get("PlaceName", "")
                        state = tagged.get("StateName", "")
                        if city:
                            normalized += f", {city}"
                        if state:
                            normalized += f", {state}"
                        locations.append(ExtractedLocation(
                            raw_text=segment.strip(),
                            normalized=normalized,
                            confidence=0.8,
                            source="usaddress",
                        ))
                elif addr_type == "Intersection":
                    street_names = []
                    for label in ["StreetName", "SecondStreetName"]:
                        if label in tagged:
                            street_names.append(tagged[label])
                    if len(street_names) == 2:
                        normalized = f"{street_names[0]} and {street_names[1]}"
                        locations.append(ExtractedLocation(
                            raw_text=segment.strip(),
                            normalized=normalized,
                            confidence=0.75,
                            source="usaddress_intersection",
                        ))
        except usaddress.RepeatedLabelError:
            continue

    log.info("usaddress extraction", count=len(locations))
    return locations


@lru_cache(maxsize=1)
def _load_spacy():
    import spacy
    return spacy.load("en_core_web_trf")


def extract_with_ner(text: str) -> list[ExtractedLocation]:
    try:
        nlp = _load_spacy()
    except (ImportError, OSError):
        log.warning("spacy model not available, skipping NER")
        return []

    doc = nlp(text)
    locations: list[ExtractedLocation] = []

    for ent in doc.ents:
        if ent.label_ not in ("LOC", "GPE", "FAC"):
            continue
        ent_text = ent.text.strip()
        if len(ent_text) < 3:
            continue
        skip_tokens = {"dispatch", "copy", "roger", "clear", "unit", "code"}
        if ent_text.lower() in skip_tokens:
            continue

        confidence = 0.6
        for city in SCC_CITIES:
            if city.lower() in ent_text.lower():
                confidence = 0.5
                break
        if any(suffix in ent_text.lower() for suffix in ["street", "ave", "blvd", "road", "drive", "way"]):
            confidence = 0.7

        locations.append(ExtractedLocation(
            raw_text=ent_text,
            normalized=ent_text,
            confidence=confidence,
            source="ner",
        ))

    log.info("NER extraction", count=len(locations))
    return locations


def append_scc_context(location: ExtractedLocation) -> ExtractedLocation:
    normalized = location.normalized
    has_city = any(city.lower() in normalized.lower() for city in SCC_CITIES)
    has_state = "ca" in normalized.lower() or "california" in normalized.lower()
    if not has_city and not has_state:
        if location.source.startswith("regex") or location.source == "usaddress":
            normalized = f"{normalized}, Santa Clara County, CA"
    return ExtractedLocation(
        raw_text=location.raw_text,
        normalized=normalized,
        confidence=location.confidence,
        source=location.source,
    )


def extract_locations(text: str) -> list[ExtractedLocation]:
    normalized_text = normalize_text(text)

    extractors = [
        extract_landmarks,
        extract_addresses,
        extract_with_usaddress,
        extract_with_ner,
    ]

    all_locations: list[ExtractedLocation] = []
    seen_normalized: set[str] = set()

    for extractor in extractors:
        for loc in extractor(normalized_text):
            key = loc.normalized.lower().strip()
            if key in seen_normalized:
                continue
            if len(key) < 4:
                continue
            seen_normalized.add(key)
            all_locations.append(append_scc_context(loc))

    all_locations.sort(key=lambda x: x.confidence, reverse=True)
    log.info("total locations extracted", count=len(all_locations))
    return all_locations
