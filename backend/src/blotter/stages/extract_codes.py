"""Scanner code extraction with per-feed code system mapping.

Each feed maps to a set of code dictionaries (state + agency). Regex
patterns are auto-compiled from dict keys and cached per feed prefix.
Adding a new city = one entry in _FEEDS plus any new code dicts.
"""

from __future__ import annotations

import re
from functools import lru_cache

# ── 10-codes (APCO, universally recognized) ─────────────────────────

_TEN: dict[str, str] = {
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
    "10-27": "License check",
    "10-28": "Registration check",
    "10-29": "Check for wants",
    "10-32": "Person with gun",
    "10-33": "Emergency traffic",
    "10-35": "Confidential info",
    "10-36": "Correct time",
    "10-40": "No lights/sirens",
    "10-50": "Traffic accident",
    "10-51": "Wrecker needed",
    "10-52": "Ambulance needed",
    "10-53": "Road blocked",
    "10-54": "Possible dead body",
    "10-56": "Intoxicated driver",
    "10-57": "Hit and run",
    "10-61": "Personnel in area",
    "10-62": "Unable to copy",
    "10-70": "Fire alarm",
    "10-71": "Shooting",
    "10-76": "En route",
    "10-77": "ETA",
    "10-78": "Need assistance",
    "10-80": "Pursuit",
    "10-97": "Arrived at scene",
    "10-98": "Available",
    "10-99": "Wanted person",
}

# ── State penal / criminal code sections ─────────────────────────────
# Only sections routinely cited on radio for dispatching or reporting.

_CA: dict[str, str] = {
    # California Penal Code
    "148": "Resisting arrest",
    "187": "Homicide",
    "207": "Kidnapping",
    "211": "Robbery",
    "215": "Carjacking",
    "242": "Battery",
    "243": "Battery on officer",
    "245": "Assault w/ deadly weapon",
    "246": "Shooting at dwelling",
    "261": "Rape",
    "273": "Child abuse",
    "288": "Lewd conduct",
    "290": "Sex offender",
    "311": "Indecent exposure",
    "390": "Drunk",
    "415": "Disturbing the peace",
    "417": "Brandishing weapon",
    "459": "Burglary",
    "470": "Forgery",
    "484": "Theft",
    "487": "Grand theft",
    "488": "Petty theft",
    "496": "Receiving stolen property",
    "502": "DUI",
    "586": "Illegal parking",
    "594": "Vandalism",
    "602": "Trespassing",
    "647": "Disorderly conduct",
    "653": "Threatening",
    "5150": "Psychiatric hold",
    "10851": "Stolen vehicle",
    # California 11-series (CHP / statewide)
    "11-44": "Deceased person",
    "11-80": "Major accident",
    "11-81": "Minor accident",
    "11-82": "Property damage accident",
    "11-83": "Accident, no details",
    "11-85": "Tow truck needed",
    "11-99": "Officer needs help",
    # California response codes
    "code 1": "Acknowledge",
    "code 2": "Urgent, no sirens",
    "code 3": "Lights & sirens",
    "code 4": "No further help needed",
    "code 5": "Stakeout",
    "code 6": "Out for investigation",
    "code 7": "Meal break",
    "code 20": "Notify media",
    "code 30": "Burglar alarm",
    "code 37": "Stolen vehicle",
    # San Francisco-specific
    "914": "Dead body",
    "917": "Suspicious person",
    "918": "Mental case",
    "919": "Keep the peace",
}

_TX: dict[str, str] = {
    # Texas Penal Code sections commonly cited on radio
    "20.03": "Kidnapping",
    "20.04": "Aggravated kidnapping",
    "21.11": "Indecency with child",
    "22.01": "Assault",
    "22.02": "Aggravated assault",
    "22.04": "Injury to child/elderly",
    "22.07": "Terroristic threat",
    "28.03": "Criminal mischief",
    "29.02": "Robbery",
    "29.03": "Aggravated robbery",
    "30.02": "Burglary",
    "31.03": "Theft",
    "38.04": "Evading arrest",
    "42.01": "Disorderly conduct",
    "46.02": "Unlawful carry weapon",
    "49.04": "DWI",
    "49.045": "DWI with child",
}

_IL: dict[str, str] = {
    # Illinois Compiled Statutes — commonly cited on Chicago radio
    "720-5/9-1": "First degree murder",
    "720-5/9-3": "Involuntary manslaughter",
    "720-5/11-1.20": "Criminal sexual assault",
    "720-5/12-1": "Assault",
    "720-5/12-2": "Aggravated assault",
    "720-5/12-3.05": "Aggravated battery",
    "720-5/18-1": "Robbery",
    "720-5/18-2": "Armed robbery",
    "720-5/19-1": "Burglary",
    "720-5/24-1.1": "UUW",
}

_NY: dict[str, str] = {
    # New York Penal Law sections commonly cited on radio
    "120.00": "Assault 3rd",
    "120.05": "Assault 2nd",
    "120.10": "Assault 1st",
    "140.20": "Burglary 3rd",
    "140.25": "Burglary 2nd",
    "140.30": "Burglary 1st",
    "155.25": "Petit larceny",
    "155.30": "Grand larceny 4th",
    "155.35": "Grand larceny 3rd",
    "160.05": "Robbery 3rd",
    "160.10": "Robbery 2nd",
    "160.15": "Robbery 1st",
    "165.40": "Criminal possession stolen property",
    "195.05": "Obstruction",
    "205.30": "Resisting arrest",
    "220.03": "Criminal possession controlled substance",
    "265.01": "Criminal possession weapon",
    "265.03": "Criminal possession weapon 2nd",
}

_GA: dict[str, str] = {
    "16-5-1": "Murder",
    "16-5-20": "Simple assault",
    "16-5-21": "Aggravated assault",
    "16-5-40": "Kidnapping",
    "16-7-1": "Burglary",
    "16-8-2": "Theft by shoplifting",
    "16-8-12": "Robbery",
    "16-8-40": "Armed robbery",
    "16-11-37": "Terroristic threat",
    "16-11-106": "DUI",
}

_OH: dict[str, str] = {
    "2903.01": "Aggravated murder",
    "2903.02": "Murder",
    "2903.11": "Felonious assault",
    "2903.13": "Assault",
    "2905.01": "Kidnapping",
    "2911.01": "Aggravated robbery",
    "2911.02": "Robbery",
    "2911.11": "Aggravated burglary",
    "2911.12": "Burglary",
    "2913.02": "Theft",
    "2917.11": "Disorderly conduct",
    "2919.25": "Domestic violence",
    "2921.33": "Resisting arrest",
    "4511.19": "OVI/DUI",
}

_NV: dict[str, str] = {
    "200.010": "Murder",
    "200.380": "Robbery",
    "200.400": "Battery",
    "200.471": "Assault",
    "205.060": "Burglary",
}

_PA: dict[str, str] = {
    "2501": "Homicide",
    "2702": "Aggravated assault",
    "2701": "Simple assault",
    "3502": "Burglary",
    "3701": "Robbery",
    "3921": "Theft",
    "3925": "Receiving stolen property",
    "3929": "Retail theft",
    "5503": "Disorderly conduct",
    "3802": "DUI",
}

_MD: dict[str, str] = {
    # Maryland Criminal Law sections
    "2-201": "Murder 1st",
    "3-202": "Assault 1st",
    "3-203": "Assault 2nd",
    "6-202": "Burglary 1st",
    "7-104": "Theft",
}

_NJ: dict[str, str] = {
    "2c:11-3": "Murder",
    "2c:12-1": "Assault",
    "2c:15-1": "Robbery",
    "2c:18-2": "Burglary",
    "2c:20-3": "Theft",
    "2c:33-2": "Disorderly conduct",
    "2c:35-10": "Drug possession",
    "2c:39-5": "Weapons offense",
}

_IN: dict[str, str] = {
    "35-42-1-1": "Murder",
    "35-42-2-1": "Battery",
    "35-42-5-1": "Robbery",
    "35-43-2-1": "Burglary",
    "35-43-4-2": "Theft",
}

_MI: dict[str, str] = {
    "750.316": "Murder 1st",
    "750.317": "Murder 2nd",
    "750.81": "Assault & battery",
    "750.82": "Felonious assault",
    "750.110a": "Home invasion",
    "750.529": "Armed robbery",
    "750.530": "Unarmed robbery",
    "750.356": "Larceny",
    "257.625": "OWI/DUI",
}

_WA: dict[str, str] = {
    "9a.32.030": "Murder 1st",
    "9a.36.011": "Assault 1st",
    "9a.36.021": "Assault 2nd",
    "9a.36.031": "Assault 3rd",
    "9a.52.025": "Burglary 1st",
    "9a.52.030": "Burglary 2nd",
    "9a.56.200": "Robbery 1st",
    "9a.56.210": "Robbery 2nd",
    "46.61.502": "DUI",
}

_OR: dict[str, str] = {
    "163.115": "Murder",
    "163.160": "Assault 4th",
    "163.165": "Assault 3rd",
    "163.175": "Assault 2nd",
    "164.215": "Burglary 1st",
    "164.225": "Burglary 2nd",
    "164.395": "Robbery 1st",
    "164.405": "Robbery 2nd",
    "813.010": "DUI",
}

_WI: dict[str, str] = {
    "940.01": "Murder 1st",
    "940.02": "Murder 2nd",
    "940.19": "Battery",
    "940.20": "Battery to officer",
    "943.10": "Burglary",
    "943.20": "Theft",
    "943.32": "Robbery",
    "946.41": "Resisting",
    "346.63": "OWI/DUI",
}

_MN: dict[str, str] = {
    "609.185": "Murder 1st",
    "609.19": "Murder 2nd",
    "609.221": "Assault 1st",
    "609.222": "Assault 2nd",
    "609.2231": "Assault 3rd",
    "609.224": "Assault 5th",
    "609.245": "Robbery 1st",
    "609.24": "Simple robbery",
    "609.582": "Burglary",
    "609.52": "Theft",
    "169a.20": "DWI",
}

_SC: dict[str, str] = {
    "16-3-10": "Homicide",
    "16-3-600": "Assault & battery",
    "16-11-310": "Burglary 1st",
    "16-11-312": "Burglary 2nd",
    "16-11-330": "Robbery",
    "16-13-30": "Theft",
    "56-5-2930": "DUI",
}

_NC: dict[str, str] = {
    "14-17": "Murder 1st",
    "14-17.1": "Murder 2nd",
    "14-33": "Assault",
    "14-51": "Burglary 1st",
    "14-54": "Burglary 2nd",
    "14-87": "Robbery w/ firearm",
    "14-87.1": "Common law robbery",
    "14-72": "Larceny",
    "20-138.1": "DWI",
}

# ── Agency-specific codes ────────────────────────────────────────────

_LAPD: dict[str, str] = {}  # LAPD uses CA codes above

_SFPD: dict[str, str] = {}  # SF-specific 900 codes are in _CA

_CPD: dict[str, str] = {
    # CPD 10-code overrides (most use plain language)
    "10-1": "Officer needs help",
    # CPD disposition codes (old Chicago phonetic alphabet)
    "19 adam": "Not bona fide",
    "19 boy": "No person found",
    "19 david": "Perpetrator gone",
    "19 frank": "Peace restored",
    "19 henry": "Advised re-contact",
    "19 ida": "Removed to hospital",
    "19 paul": "Police service rendered",
    "19 radio": "Arrest made",
    "19 x-ray": "Report taken",
    # CPD priority
    "priority 1": "Life-threatening emergency",
    "priority 2": "Rapid dispatch",
    "priority 3": "Routine",
}

_CMPD: dict[str, str] = {
    "signal 5": "Robbery",
    "signal 7": "Assault",
    "signal 8": "Burglary in progress",
    "signal 9": "Larceny in progress",
    "signal 10": "Shooting",
    "signal 40": "Accident w/ injuries",
    "signal 42": "Hit and run",
    "signal 50": "Domestic",
}

_DPD: dict[str, str] = {
    # Dallas PD signal codes
    "signal 5": "Meet complainant",
    "signal 15": "Disturbance",
    "signal 19": "Prowler",
    "signal 25": "Burglary",
    "signal 35": "Accident, major",
    "signal 36": "Accident, minor",
    "signal 63": "Shooting",
    "code 1": "Routine response",
    "code 3": "Lights & sirens",
    "code 5": "En route",
    "code 6": "On scene",
}

_PHILLY: dict[str, str] = {
    "signal 32": "Gun involved",
    "signal 33": "Robbery",
    "code 1": "Officer down",
    "priority 1": "In progress / emergency",
    "priority 2": "Just occurred",
    "priority 3": "Routine",
}

_PGPD: dict[str, str] = {
    "signal 13": "Officer needs help",
    "signal 7": "Shooting",
    "signal 9": "Stabbing",
    "signal 10": "Robbery",
    "signal 12": "Domestic",
}

_BCPD: dict[str, str] = {
    "signal 13": "Officer needs help",
    # Baltimore County 10-code overrides
    "10-10": "Fight in progress",
    "10-16": "Domestic problem",
    "10-31": "Crime in progress",
    "10-32": "Person with gun",
    "10-34": "Riot",
    "10-39": "Lights & sirens",
    "10-40": "No lights/sirens",
    "10-55": "Intoxicated driver",
    "10-80": "Pursuit",
    "10-89": "Bomb threat",
    "10-90": "Bank alarm",
    "10-96": "Mentally ill",
}

_MONROE: dict[str, str] = {
    "signal 30": "Robbery",
    "signal 31": "Burglary",
}

_DCFD: dict[str, str] = {
    "box alarm": "Structure fire",
    "working fire": "Active fire",
    "all hands": "Full assignment working",
    "task force": "Multi-unit response",
    "code 1": "Dead on arrival",
    "code 2": "Return to service",
    "code 3": "Lights & sirens",
    "code 4": "No further help needed",
    "priority 1": "Life-threatening",
    "priority 2": "Serious but stable",
    "priority 3": "Non-emergency",
}

_LVMPD: dict[str, str] = {
    "code 3": "Lights & sirens",
    "code 4": "No further help needed",
    # LVMPD IDF 400-series dispatch codes
    "401": "Traffic accident",
    "401b": "Accident w/ injury",
    "403": "Prowler",
    "404": "Unknown trouble",
    "405": "Suicide attempt",
    "406": "Burglary",
    "406a": "Burglary alarm",
    "407": "Robbery",
    "407a": "Robbery alarm",
    "409": "Drunk driver",
    "410": "Reckless driver",
    "411": "Stolen vehicle",
    "413": "Person with gun",
    "413a": "Person with knife",
    "414": "Grand larceny",
    "415": "Assault",
    "415a": "Assault w/ gun",
    "415b": "Assault w/ knife",
    "416": "Fight",
    "417": "Domestic",
    "419": "Dead body",
    "420": "Homicide",
    "421": "Sick/injured person",
    "421a": "Mentally ill person",
    "425": "Suspicious situation",
    "425a": "Suspicious person",
    "426": "Sexual assault",
    "427": "Kidnapping",
    "434": "Shots fired",
    "440": "Wanted suspect",
    "443": "Assist officer",
    "444": "Officer needs help",
    "445": "Bomb threat",
    "446": "Narcotics",
}

_HPD: dict[str, str] = {
    # Houston PD / Harris County signal codes
    "signal 4": "Assault",
    "signal 5": "Sexual assault",
    "signal 9": "Burglary in progress",
    "signal 11": "Stabbing",
    "signal 12": "Deceased person",
    "signal 13": "Mental case",
    "signal 14": "Disturbance",
    "signal 15": "Domestic disturbance",
    "signal 22": "Intoxicated driver",
    "signal 23": "Fight",
    "signal 25": "Fire",
    "signal 27": "Injured person",
    "signal 32": "Person with gun",
    "signal 34": "Prowler",
    "signal 36": "Robbery",
    "signal 37": "Shooting",
    "signal 38": "Suspicious person",
    "signal 40": "Theft",
    "signal 55": "Missing person",
    "signal 58": "Robbery alarm",
    "signal 60": "Stolen car",
    "signal 63": "Back up officer",
    "priority 1": "Urgent, threat to life",
    "priority 2": "Crime in progress",
    "priority 3": "Handle quickly",
}

_APD: dict[str, str] = {
    # Atlanta PD signal codes (SOP 3088)
    "signal 15": "Welfare check",
    "signal 21": "Kidnapping",
    "signal 24": "Demented person",
    "signal 25": "Shots fired",
    "signal 29": "Fight in progress",
    "signal 36b": "Business robbery in progress",
    "signal 36p": "Pedestrian robbery",
    "signal 36v": "Carjacking",
    "signal 42b": "Commercial burglary",
    "signal 42r": "Residential burglary",
    "signal 44p": "Pedestrian robbery",
    "signal 44v": "Carjacking",
    "signal 45v": "Vehicle theft",
    "signal 46": "Pedestrian struck",
    "signal 48": "Person dead",
    "signal 49": "Rape",
    "signal 50": "Person shot",
    "signal 51": "Person stabbed",
    "signal 53": "Suicide",
    "signal 54": "Suspicious person",
    "signal 56": "Missing person",
    "signal 58": "Domestic disturbance",
    "signal 63": "Officer needs help",
    "signal 69": "Person armed",
    "signal 70": "Prowler",
    "signal 79": "Stolen vehicle in progress",
    "signal 86": "Vandalism",
}

_INDYPD: dict[str, str] = {
    # Indiana signal codes (used by IMPD)
    "signal 7": "Emergency, serious",
    "signal 10": "Rush, lights & sirens",
    "signal 11": "Confidential info",
    "signal 27": "Traffic stop",
    "signal 46": "Pursuit",
    "signal 60": "Drugs",
    "signal 61": "Homicide",
    "signal 63": "Firearm",
    "signal 100": "Emergency, hold traffic",
    # Indiana 10-code overrides
    "10-0": "Fatality",
    "10-10": "Fight in progress",
    "10-16": "Domestic trouble",
    "10-31": "Crime in progress",
    "10-32": "Man with gun",
    "10-39": "Urgent, lights & sirens",
    "10-40": "Silent run",
    "10-55": "Intoxicated driver",
    "10-78": "Need assistance",
    "10-80": "Pursuit",
    "10-89": "Bomb threat",
    "10-90": "Bank alarm",
    "10-95": "Subject in custody",
    "10-96": "Mental subject",
    "code 3": "Lights & sirens",
    "code 4": "No further help needed",
}

_SEATTLE: dict[str, str] = {
    "priority 1": "In progress, life safety",
    "priority 2": "In progress",
    "priority 3": "Just occurred",
    "priority 4": "Routine",
    "code 3": "Lights & sirens",
    "code 4": "No further help needed",
}

_PORTLAND: dict[str, str] = {
    "code 0": "Officer in peril, all units",
    "code 1": "Routine, no lights/sirens",
    "code 2": "Medium priority, lights only",
    "code 3": "High priority, lights & sirens",
    "code 4": "Situation under control",
    "code 5": "Stakeout",
    "12-34": "Mentally unstable person",
    "priority 1": "In progress, threat to life",
    "priority 2": "In progress",
    "priority 3": "Cold / delayed",
}

_CLEVELAND: dict[str, str] = {
    "code 1": "Emergency",
    "code 2": "Urgent",
    "code 3": "Routine",
    # BSSA codes (Buckeye State Sheriffs Association)
    "bssa 4": "Accident, injury",
    "bssa 8": "Assault",
    "bssa 12": "Burglary",
    "bssa 12a": "Burglary in progress",
    "bssa 16": "DOA",
    "bssa 20": "Domestic trouble",
    "bssa 26": "Fight",
    "bssa 27": "Emergency run",
    "bssa 32": "Homicide",
    "bssa 36": "Larceny",
    "bssa 40": "Man with gun",
    "bssa 44": "Officer in trouble",
    "bssa 48": "Rape",
    "bssa 50": "Robbery",
    "bssa 50a": "Robbery in progress",
    "bssa 52": "Shooting",
    "bssa 54": "Stabbing",
    "bssa 56": "Stolen car",
    "bssa 58": "Suicide",
    "bssa 60": "Suspicious person",
    "bssa 69": "Narcotics",
    "bssa 76": "Mental",
    "bssa 88": "Bomb threat",
    "bssa 99": "Emergency, all stand by",
}

_SCPD: dict[str, str] = {
    # Suffolk County PD code signals
    "code 1": "Stolen vehicle",
    "code 5": "Wanted/escaped person",
    "code 6": "Missing person",
    "code 7": "Wanted for burglary",
    "code 8": "Wanted for armed robbery",
    "code 11": "Wanted for assault",
    "code 12": "Wanted for homicide",
    # Suffolk County 10-code overrides
    "10-1": "Officer needs assistance",
    "10-2": "Report of crime",
    "10-3": "Burglary",
    "10-5": "Homicide",
    "10-10": "Vehicle accident",
    "10-15": "Armed robbery",
    "10-16": "Fight",
    "10-17": "Disturbance",
    "10-20": "Drunk driver",
    "10-25": "Prowler",
    "10-41": "Bank robbery",
    "10-42": "Bomb threat",
    "10-47": "Armed person",
    "10-85": "Domestic in progress",
}

_DANE: dict[str, str] = {
    # Wisconsin C-code dispositions (distinctive, heard on radio)
    "c-1": "Adult arrest",
    "c-2": "Juvenile arrest",
    "c-7": "Mental observation",
    "c-8": "Report filed",
    "c-9": "Unfounded",
    "c-10": "Advised",
    "c-19": "False alarm",
    "c-20": "DV-related battery",
    "priority 1": "Lights & sirens",
    "priority 2": "Respond ASAP",
    "priority 3": "Normal response",
}

_MPLSPD: dict[str, str] = {
    # Minnesota-specific 10-codes (differ from APCO)
    "10-39": "Assist officer",
    "10-56": "Investigate DUI",
    "10-69": "Drug call",
    "10-72": "Dead person",
    "10-74": "Theft",
    "10-77": "Prowler",
    "10-79": "Domestic disturbance",
    "10-80": "Sex crime",
    "10-81": "ADT/bank alarm",
    "10-82": "Burglary",
    "10-83": "Disturbance",
    "10-84": "Fight",
    "10-85": "Stabbing",
    "10-86": "Armed robbery",
    "10-87": "Shooting",
    "10-88": "Officer needs help",
    "10-89": "Homicide",
}

_NJUNION: dict[str, str] = {
    "10-10": "Shots fired",
    "10-13": "Officer in trouble",
    "10-49": "Injuries/aided",
    "10-50": "Vehicle collision",
    "10-82": "Mental health emergency",
    "signal 400": "Mayday",
    "signal 401": "Working fire",
    "signal 402": "2nd alarm",
    "signal 403": "3rd alarm",
    "signal 500": "Arson investigation",
}

_SUMTER: dict[str, str] = {
    # Sumter County SC signal codes
    "signal 1": "DOA",
    "signal 2": "Gunshots",
    "signal 3": "Sexual assault",
    "signal 5": "Arson",
    "signal 7": "Murder",
    "signal 8": "Suicide",
    "signal 10": "Drugs",
    "signal 17": "Injury",
    "signal 18": "Hostage",
    "signal 25": "Canine",
    "signal 26": "Loud noise",
    "signal 27": "Stalking",
    "signal 35": "Welfare check",
    # SC 10-code overrides (differ from APCO)
    "10-43": "Lights & sirens",
    "10-44": "Silent run",
    "10-55": "DUI",
    "10-59": "Man with gun",
    "10-64": "Bomb threat",
    "10-67": "Subject arrested",
    "10-68": "Mental subject",
    "10-74": "Armed robbery",
    "10-75": "Shooting",
    "10-76": "Assault",
    "10-78": "Request assistance",
    "10-82": "Domestic disturbance",
    "10-83": "Fight in progress",
    "10-84": "Crime in progress",
    "10-85": "Alarm activation",
}

# ── Feed → code system mapping ──────────────────────────────────────
# Key = OpenMHz system name (the prefix of feed_id before the talkgroup
# number, e.g. "chi_cpd" from "chi_cpd-11").
# Value = tuple of code dicts applied for that system.
# _TEN codes are prepended automatically to every feed.

_FEEDS: dict[str, tuple[dict[str, str], ...]] = {
    # California
    "lapdvalley": (_CA,),
    "lapdwest":   (_CA,),
    "sfp25":      (_CA,),
    "scpd":       (_NY, _SCPD),     # Suffolk County PD (Long Island)
    # Texas
    "ntirnd1":    (_TX, _DPD),     # Dallas
    "nwhc":       (_TX, _HPD),     # NW Harris County (Houston)
    # Illinois
    "chi_cpd":    (_IL, _CPD),
    # North Carolina
    "cltp25":     (_NC, _CMPD),    # Charlotte-Mecklenburg
    # Pennsylvania
    "philly":     (_PA, _PHILLY),
    # Washington
    "psern1":     (_WA, _SEATTLE),
    "snacc":      (_NV, _LVMPD),   # Las Vegas Metro
    # Oregon
    "pdx2":       (_OR, _PORTLAND),
    # Maryland
    "pgcomd":     (_MD, _PGPD),    # Prince George's County
    "bacop25":    (_MD, _BCPD),    # Baltimore County
    # Wisconsin
    "dane_com":   (_WI, _DANE),
    # New York
    "monroecony": (_NY, _MONROE),  # Rochester / Monroe County
    # DC
    "dcfd":       (_DCFD,),
    # Minnesota
    "mnhennco":   (_MN, _MPLSPD),  # Hennepin County / Minneapolis
    # New Jersey
    "njicsunion": (_NJ, _NJUNION),
    # Ohio
    "gcrn":       (_OH, _CLEVELAND),
    # Michigan
    "mcbsimcast": (_MI,),          # Macomb County
    "sc21102":    (_SC, _SUMTER),   # Sumter County SC
    # Georgia
    "apsp25":     (_GA, _APD),     # Atlanta
    # Indiana
    "indydps":    (_IN, _INDYPD),
}


# ── Pattern compilation (cached) ─────────────────────────────────────

_ALL_CODES: dict[str, str] = {}
for _d in [_TEN, _CA, _TX, _IL, _NY, _GA, _OH, _NV, _PA, _MD, _NJ,
           _IN, _MI, _WA, _OR, _WI, _MN, _SC, _NC,
           _CPD, _CMPD, _DPD, _HPD, _PHILLY, _PGPD, _BCPD, _MONROE,
           _SCPD, _DCFD, _LVMPD, _APD, _INDYPD, _SEATTLE, _PORTLAND,
           _CLEVELAND, _DANE, _MPLSPD, _NJUNION, _SUMTER]:
    _ALL_CODES.update(_d)


def _make_pattern(codes: dict[str, str]) -> re.Pattern[str]:
    """Compile a single regex matching any key, longest first."""
    if not codes:
        return re.compile(r"(?!x)x")  # never matches
    keys = sorted(codes, key=len, reverse=True)
    alt = "|".join(re.escape(k) for k in keys)
    return re.compile(rf"\b(?:{alt})\b", re.IGNORECASE)


@lru_cache(maxsize=None)
def _for_feed(system: str) -> tuple[re.Pattern[str], dict[str, str]]:
    """Return compiled (pattern, lookup) for a feed's system prefix."""
    parts = (_TEN,) + _FEEDS.get(system, ())
    merged: dict[str, str] = {}
    for d in parts:
        merged.update(d)
    return _make_pattern(merged), {k.lower(): v for k, v in merged.items()}


# ── Public API ───────────────────────────────────────────────────────

def extract_codes(text: str, feed_id: str = "") -> list[str]:
    """Extract recognized scanner codes from transcript text.

    When feed_id is provided (e.g. "chi_cpd-11"), only codes relevant
    to that feed's jurisdiction are matched. Without feed_id, only
    universal 10-codes are checked.
    """
    system = feed_id.rsplit("-", 1)[0] if "-" in feed_id else feed_id
    pattern, lookup = _for_feed(system)
    found: dict[str, None] = {}
    for m in pattern.finditer(text):
        key = m.group().lower()
        if key in lookup:
            found[key] = None
    return list(found)


def code_label(code: str, feed_id: str = "") -> str:
    """Return human-readable label for a code, or empty string."""
    key = code.lower()
    if feed_id:
        system = feed_id.rsplit("-", 1)[0] if "-" in feed_id else feed_id
        _, lookup = _for_feed(system)
        if key in lookup:
            return lookup[key]
    return _ALL_CODES.get(key, "")
