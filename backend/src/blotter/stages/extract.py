import re

from blotter.log import get_logger
from blotter.models import ExtractedLocation

log = get_logger(__name__)

AD_KEYWORDS = [
    "progressive", "geico", "state farm", "allstate", "liberty mutual",
    "insurance", "insurer", "coverage", "quote", "policy",
    "get a quote", "save on", "switch and save", "as america's",
    "roadside assistance", "we just do insurance",
    "motorcycle insurer", "for insurance only",
    "lumberjack special", "lumberjack", "riding hoodies",
    "cousin canceled", "beat me there", "we can share",
    "scanner", "premium", "listeners",
    "personal injury", "injury lawyer", "injury attorney",
    "attorney", "lawyer", "law firm", "law office",
    "building evidence", "client's pain", "settling low",
    "free consultation", "call now", "visit us",
    "cash back", "credit card", "loan", "mortgage",
    "commercial free", "sponsor", "brought to you by",
    "jesse crisp",
    "wells fargo", "wellsfargo",
    "overdraft", "banking account", "clear access",
    "heavy metal tea",
]

AD_KEYWORD_RE = re.compile("|".join(re.escape(k) for k in AD_KEYWORDS), re.IGNORECASE)

DISPATCH_ANCHOR_RE = re.compile(
    r"(?:unit\s+\d|dispatch|we've got|respond|suspect|victim|"
    r"code\s+\d|10-\d{1,2}\b|adam\s+\d|boy\s+\d|lincoln\s+\d|mary\s+\d|"
    r"copy\s+that|en\s+route|on\s+scene|requesting|"
    r"\d{2,5}\s+\w+\s+(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|way)\b|"
    r"\b(?:north|south|east|west)bound\b|\d{1,2}[A-Z]\d{1,2}\b)",
    re.IGNORECASE,
)


def strip_ads(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    in_ad = False

    for sentence in sentences:
        ad_hits = len(AD_KEYWORD_RE.findall(sentence))
        has_dispatch = bool(DISPATCH_ANCHOR_RE.search(sentence))

        if ad_hits >= 1:
            in_ad = True
            continue

        if in_ad and not has_dispatch:
            continue

        in_ad = False
        cleaned.append(sentence)

    result = " ".join(cleaned).strip()
    if result and not DISPATCH_ANCHOR_RE.search(result):
        return ""
    return result


def split_clauses(text: str) -> list[str]:
    clauses = re.split(r"[.,;!?]+", text)
    return [c.strip() for c in clauses if len(c.strip()) > 12]


def _get_context(text: str, clause: str, window: int = 120) -> str:
    idx = text.find(clause)
    if idx == -1:
        return clause[:250]
    start = max(0, idx - window)
    end = min(len(text), idx + len(clause) + window)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


LOCATION_HINT_RE = re.compile(
    r"\b(?:"
    r"\d{1,5}\s+\w+\s+(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd|way|lane|ln|place|pl|court|ct)"
    r"|(?:north|south|east|west)bound"
    r"|\band\b.+\b(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd)\b"
    r"|\bat\b.+\b(?:street|st|avenue|ave|boulevard|blvd|drive|dr|road|rd)\b"
    r"|(?:block|hundred)\s+(?:of\s+)?\w+"
    r"|\d+(?:th|st|nd|rd)\s+(?:and|&|at)\s+\w+"
    r")\b",
    re.IGNORECASE,
)


def extract_clauses(text: str) -> list[ExtractedLocation]:
    cleaned = strip_ads(text)
    clauses = split_clauses(cleaned)
    locations = []
    for clause in clauses:
        if not LOCATION_HINT_RE.search(clause):
            continue
        locations.append(ExtractedLocation(
            raw_text=clause,
            normalized=clause,
            confidence=0.5,
            source="clause",
            context=_get_context(text, clause),
        ))
    log.info("clauses extracted", count=len(locations))
    return locations
