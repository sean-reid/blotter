import re

POLICE_CODES: dict[str, str] = {
    "code 1": "Respond, no lights/sirens",
    "code 2": "Respond urgently",
    "code 3": "Emergency, lights & sirens",
    "code 4": "No further assistance",
    "code 5": "Stakeout",
    "code 6": "Out for investigation",
    "code 7": "Meal break",
    "code 37": "Stolen vehicle",
    "10-4": "Acknowledged",
    "10-7": "Out of service",
    "10-8": "In service",
    "10-15": "Prisoner in custody",
    "10-20": "Location",
    "10-29": "Check for wants",
    "10-33": "Emergency traffic",
    "10-77": "ETA",
    "10-97": "Arrived at scene",
    "10-98": "Available for assignment",
    "10-99": "Wanted person",
    "187": "Homicide",
    "207": "Kidnapping",
    "211": "Robbery",
    "242": "Battery",
    "245": "Assault with deadly weapon",
    "261": "Rape",
    "288": "Lewd conduct",
    "311": "Indecent exposure",
    "390": "Drunk",
    "415": "Disturbing the peace",
    "459": "Burglary",
    "484": "Theft",
    "487": "Grand theft",
    "502": "DUI",
    "586": "Illegal parking",
    "594": "Malicious mischief",
    "647": "Disorderly conduct",
    "10851": "Stolen vehicle",
    "11-44": "Deceased person",
    "11-80": "Traffic accident, major",
    "11-81": "Traffic accident, minor",
    "11-82": "Traffic accident, property damage",
    "11-83": "Traffic accident, no details",
    "11-85": "Tow truck needed",
    "11-99": "Officer needs help",
}

_CODE_PATTERN = re.compile(
    r'\b(?:'
    r'code\s+(\d{1,3})'
    r'|(1[01]-\d{1,3})'
    r')\b',
    re.IGNORECASE,
)

_PENAL_PATTERN = re.compile(
    r'\b(187|207|211|242|245|261|288|311|390|415|459|484|487|502|586|594|647|10851)\b'
)


def extract_codes(text: str) -> list[str]:
    found: dict[str, None] = {}

    for m in _CODE_PATTERN.finditer(text):
        if m.group(1):
            code = f"code {m.group(1)}"
        else:
            code = m.group(2)
        if code:
            found[code.lower()] = None

    for m in _PENAL_PATTERN.finditer(text):
        found[m.group(1)] = None

    return list(found.keys())


def code_label(code: str) -> str:
    return POLICE_CODES.get(code.lower(), "")
