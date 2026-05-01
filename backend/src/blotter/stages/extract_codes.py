import re

POLICE_CODES: dict[str, str] = {
    # Universal codes / 10-codes
    "code 1": "No lights/sirens",
    "code 2": "Urgent, no sirens",
    "code 3": "Lights & sirens",
    "code 4": "No further assist",
    "code 5": "Stakeout",
    "code 6": "Out for investigation",
    "code 7": "Meal break",
    "code 37": "Stolen vehicle",
    "10-1": "Poor reception",
    "10-2": "Good reception",
    "10-3": "Stop transmitting",
    "10-4": "Acknowledged",
    "10-5": "Relay",
    "10-6": "Busy",
    "10-7": "Out of service",
    "10-8": "In service",
    "10-9": "Repeat",
    "10-10": "Off duty",
    "10-14": "Escort",
    "10-15": "Prisoner in custody",
    "10-19": "Return to station",
    "10-20": "Location",
    "10-22": "Disregard",
    "10-23": "Stand by",
    "10-29": "Check for wants",
    "10-33": "Emergency traffic",
    "10-35": "Confidential info",
    "10-36": "Correct time",
    "10-54": "Possible dead body",
    "10-71": "Shooting",
    "10-77": "ETA",
    "10-97": "Arrived at scene",
    "10-98": "Available",
    "10-99": "Wanted person",

    # California penal codes
    "187": "Homicide",
    "207": "Kidnapping",
    "211": "Robbery",
    "242": "Battery",
    "245": "Assault w/ deadly weapon",
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
    "11-80": "Major accident",
    "11-81": "Minor accident",
    "11-82": "Property damage accident",
    "11-83": "Accident / no details",
    "11-85": "Tow truck needed",
    "11-99": "Officer needs help",

    # Charlotte (CMPD) signal codes
    "signal 5": "Robbery",
    "signal 7": "Assault",
    "signal 8": "Burglary in progress",
    "signal 9": "Larceny in progress",
    "signal 10": "Shooting",
    "signal 40": "Accident w/ injuries",
    "signal 42": "Hit and run",
    "signal 50": "Domestic",

    # Dallas (DPD) signal codes
    "signal 25": "Burglary",
    "signal 63": "Shooting",

    # Philadelphia signal codes
    "signal 32": "Gun involved",
    "signal 33": "Robbery",

    # PG County / Maryland
    "signal 13": "Officer needs help",

    # Rochester (Monroe County) signal codes
    "signal 30": "Robbery",
    "signal 31": "Burglary",

    # San Francisco codes
    "914": "Dead body",
    "917": "Suspicious person",
    "918": "Mental case",
    "919": "Keep the peace",
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

_SIGNAL_PATTERN = re.compile(
    r'\bsignal\s+(\d{1,3})\b',
    re.IGNORECASE,
)

_SF_CODE_PATTERN = re.compile(
    r'\b(914|917|918|919)\b'
)


def extract_codes(text: str) -> list[str]:
    found: dict[str, None] = {}

    for m in _CODE_PATTERN.finditer(text):
        if m.group(1):
            code = f"code {m.group(1)}"
        else:
            code = m.group(2)
        if code and code.lower() in POLICE_CODES:
            found[code.lower()] = None

    for m in _PENAL_PATTERN.finditer(text):
        found[m.group(1)] = None

    for m in _SIGNAL_PATTERN.finditer(text):
        code = f"signal {m.group(1)}"
        if code.lower() in POLICE_CODES:
            found[code.lower()] = None

    for m in _SF_CODE_PATTERN.finditer(text):
        found[m.group(1)] = None

    return list(found.keys())


def code_label(code: str) -> str:
    return POLICE_CODES.get(code.lower(), "")
