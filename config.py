"""Alle Einstellungen an einer Stelle."""

# Märkte: CFTC-Code (nie über den Namen filtern, Namen haben sich 2022 geändert),
# Yahoo-Symbol, FRED-Kassakurs, BIS-Ländercode
MAERKTE = {
    "DX": {"name": "US-Dollar-Index", "cftc": "098662", "yahoo": "DX-Y.NYB", "fred": None,      "bis": "US"},
    "6A": {"name": "AUD",             "cftc": "232741", "yahoo": "6A=F",     "fred": "DEXUSAL",  "bis": "AU"},
    "6B": {"name": "GBP",             "cftc": "096742", "yahoo": "6B=F",     "fred": "DEXUSUK",  "bis": "GB"},
    "6S": {"name": "CHF",             "cftc": "092741", "yahoo": "6S=F",     "fred": "DEXSZUS",  "bis": "CH"},
    "6N": {"name": "NZD",             "cftc": "112741", "yahoo": "6N=F",     "fred": "DEXUSNZ",  "bis": "NZ"},
    "6J": {"name": "JPY",             "cftc": "097741", "yahoo": "6J=F",     "fred": "DEXJPUS",  "bis": "JP"},
    "6E": {"name": "EUR",             "cftc": "099741", "yahoo": "6E=F",     "fred": "DEXUSEU",  "bis": "XM"},
    "6C": {"name": "CAD",             "cftc": "090741", "yahoo": "6C=F",     "fred": "DEXCAUS",  "bis": "CA"},
}

CFTC_URL = "https://publicreporting.cftc.gov/resource/"
CFTC_DATASETS = {"legacy": "6dca-aqww", "tff": "gpe5-46if"}

# Frische-Ampel für die Prüfung: (grün bis, gelb bis) in Tagen, danach rot
FRISCHE = {
    "COT":        (10, 17),
    "Yahoo":      (3, 6),
    "FRED Kurse": (11, 20),
    "BIS Zinsen": (20, 40),  # BIS liefert einzelne Länder (z. B. AU) mit ca. 2 Wochen Verzug
}
