"""Etappe 5: Termine der Zinsentscheide der 8 Notenbanken (nur Anzeige, kein Teil des Punktesystems).

Die Termine stehen fest in dieser Datei, weil die Notenbanken sie ein Jahr im Voraus veröffentlichen.
Abgelesen am 11.10.2026 von den Webseiten der Notenbanken (Fed, EZB, BoE, BoJ, SNB, RBA, RBNZ, BoC).
Aufgenommen sind nur Termine bis 31.03.2027, die ich bestätigt gefunden habe. Spätere Termine fehlen bewusst
(SNB und RBNZ hatten sie noch nicht vollständig veröffentlicht). Wird die Liste knapp, zeigt die Seite einen Hinweis.
Zeiten sind je Notenbank unterschiedlich (Ortszeit), deshalb steht hier nur der Tag der Entscheidung.
"""
import pandas as pd

STAND = "2026-10-11"
WARN_TAGE = 45        # läuft der letzte Termin in weniger als so vielen Tagen aus, gibt es einen Hinweis

NOTENBANKEN = {
    "DX": ("Fed", "US-Notenbank"),
    "6E": ("EZB", "Europäische Zentralbank"),
    "6B": ("BoE", "Bank of England"),
    "6J": ("BoJ", "Bank of Japan"),
    "6S": ("SNB", "Schweizerische Nationalbank"),
    "6A": ("RBA", "Reserve Bank of Australia"),
    "6N": ("RBNZ", "Reserve Bank of New Zealand"),
    "6C": ("BoC", "Bank of Canada"),
}

TERMINE = {
    "DX": ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17"],
    "6E": ["2026-10-29", "2026-12-17", "2027-02-04", "2027-03-18"],
    "6B": ["2026-11-05", "2026-12-17", "2027-02-04", "2027-03-18"],
    "6J": ["2026-10-30", "2026-12-18", "2027-01-22", "2027-03-18"],
    "6S": ["2026-12-10", "2027-03-18"],
    "6A": ["2026-11-03", "2026-12-08", "2027-02-09", "2027-03-23"],
    "6N": ["2026-10-28", "2026-12-09"],
    "6C": ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-03"],
}
# Die SNB hat im Oktober 2026 keinen Termin (nur März, Juni, September, Dezember).
ANMERKUNG = {
    "DX": "Fed-Termine 2027 sind laut Fed noch vorläufig.",
    "6N": "Termine 2027 noch nicht bestätigt, deshalb nicht aufgeführt.",
    "6S": "Die SNB entscheidet nur viermal im Jahr (März, Juni, September, Dezember).",
}


def naechste(heute, termine=None):
    """Nächster Termin je Markt ab heute (heute zählt mit). {markt: {"datum", "tage", "danach"}}; datum None, wenn die Liste leer ist."""
    termine = TERMINE if termine is None else termine
    h = pd.Timestamp(heute).normalize()
    aus = {}
    for m in NOTENBANKEN:
        liste = sorted(pd.Timestamp(t) for t in termine.get(m, []))
        kommend = [t for t in liste if t >= h]
        if not kommend:
            aus[m] = {"datum": None, "tage": None, "danach": None}
            continue
        aus[m] = {"datum": kommend[0].strftime("%Y-%m-%d"), "tage": int((kommend[0] - h).days),
                  "danach": kommend[1].strftime("%Y-%m-%d") if len(kommend) > 1 else None}
    return aus


def liste_ab(heute, tage=120, termine=None):
    """Alle Termine der nächsten `tage` Tage, nach Datum sortiert."""
    termine = TERMINE if termine is None else termine
    h = pd.Timestamp(heute).normalize()
    z = []
    for m, ts in termine.items():
        for t in ts:
            d = pd.Timestamp(t)
            if h <= d <= h + pd.Timedelta(days=tage):
                z.append({"datum": d.strftime("%Y-%m-%d"), "tage": int((d - h).days), "markt": m, "bank": NOTENBANKEN[m][0]})
    return sorted(z, key=lambda x: (x["datum"], x["markt"]))


def letzter_termin(termine=None):
    termine = TERMINE if termine is None else termine
    return max(pd.Timestamp(t) for ts in termine.values() for t in ts)


def berechne(heute, termine=None):
    """Alles für die Seite, inklusive Warnung, wenn die Terminliste bald ausläuft."""
    termine = TERMINE if termine is None else termine
    h = pd.Timestamp(heute).normalize()
    rest = int((letzter_termin(termine) - h).days)
    n = naechste(h, termine)
    fehlend = [m for m in NOTENBANKEN if n[m]["datum"] is None]
    warnung = None
    if fehlend:
        warnung = f"Für {', '.join(fehlend)} gibt es keinen kommenden Termin mehr in der Liste."
    elif rest < WARN_TAGE:
        warnung = f"Die Terminliste endet in {rest} Tagen. Neue Termine müssen eingetragen werden."
    return {"stand_liste": STAND, "letzter_termin": letzter_termin(termine).strftime("%Y-%m-%d"), "warnung": warnung,
            "naechste": n, "liste": liste_ab(h, 120, termine),
            "banken": {m: {"kurz": NOTENBANKEN[m][0], "name": NOTENBANKEN[m][1], "anmerkung": ANMERKUNG.get(m)} for m in NOTENBANKEN}}


# ---------------------------------------------------------------------------------------------------------------
# Datenveröffentlichungen (Inflation, Arbeitsmarkt): nur Termine, die ich auf den offiziellen Seiten sicher lesen konnte.
# USA: US-Arbeitsmarktbehörde BLS (Termine bis April 2027). Australien (ABS) und Kanada (StatCan) zeigen auf ihren Seiten
# nur die nächsten Wochen, deshalb stehen dort nur einzelne Termine. Für EU, GB, Japan, Schweiz, Neuseeland fehlen sie noch.
# Format: (Datum, Markt, Typ, Kurztext). Typ: "inflation" oder "arbeit".
DATEN_STAND = "2026-10-11"
DATEN_TERMINE = [
    ("2026-11-06", "DX", "arbeit", "US-Arbeitsmarktbericht Oktober (Arbeitslosenquote, neue Stellen)"),
    ("2026-12-04", "DX", "arbeit", "US-Arbeitsmarktbericht November"),
    ("2027-01-08", "DX", "arbeit", "US-Arbeitsmarktbericht Dezember"),
    ("2027-02-05", "DX", "arbeit", "US-Arbeitsmarktbericht Januar"),
    ("2027-03-05", "DX", "arbeit", "US-Arbeitsmarktbericht Februar"),
    ("2026-11-10", "DX", "inflation", "US-Inflationsrate Oktober"),
    ("2026-12-10", "DX", "inflation", "US-Inflationsrate November"),
    ("2027-01-13", "DX", "inflation", "US-Inflationsrate Dezember"),
    ("2027-02-11", "DX", "inflation", "US-Inflationsrate Januar"),
    ("2027-03-10", "DX", "inflation", "US-Inflationsrate Februar"),
    ("2026-10-15", "6A", "arbeit", "Australien Arbeitsmarkt September (Arbeitslosenquote)"),
    ("2026-10-28", "6A", "inflation", "Australien Inflationsrate September"),
    ("2026-10-19", "6C", "inflation", "Kanada Inflationsrate September"),
]

TYPEN = {
    "zins": ("Zinsentscheid", "Die Notenbank gibt den neuen Leitzins bekannt."),
    "inflation": ("Inflation", "Veröffentlichung der Inflationsrate des Vormonats."),
    "arbeit": ("Arbeitsmarkt", "Veröffentlichung der Arbeitsmarktzahlen (Arbeitslosenquote, Beschäftigung)."),
}
ABDECKUNG = {
    "DX": "Zinsen, Inflation und Arbeitsmarkt bis März 2027",
    "6A": "Zinsen bis März 2027, Inflation und Arbeitsmarkt nur der nächste Termin",
    "6C": "Zinsen bis März 2027, Inflation nur der nächste Termin, Arbeitsmarkt fehlt",
}


def ereignisse(heute, tage=60, termine=None, daten=None):
    """Alle Ereignisse (Zinsentscheide und Datenveröffentlichungen) der nächsten `tage` Tage, nach Datum sortiert."""
    termine = TERMINE if termine is None else termine
    daten = DATEN_TERMINE if daten is None else daten
    h = pd.Timestamp(heute).normalize()
    z = []
    for m, ts in termine.items():
        for t in ts:
            z.append((t, m, "zins", f"Zinsentscheid {NOTENBANKEN[m][0]}"))
    z += list(daten)
    aus = []
    for t, m, typ, text in z:
        d = pd.Timestamp(t)
        if h <= d <= h + pd.Timedelta(days=tage):
            aus.append({"datum": d.strftime("%Y-%m-%d"), "tage": int((d - h).days), "markt": m, "typ": typ, "text": text})
    return sorted(aus, key=lambda x: (x["datum"], {"zins": 0, "arbeit": 1, "inflation": 2}[x["typ"]], x["markt"]))


_berechne_alt = berechne


def berechne(heute, termine=None, daten=None):
    r = _berechne_alt(heute, termine)
    r["ereignisse"] = ereignisse(heute, 60, termine, daten)
    r["typen"] = {k: {"name": v[0], "text": v[1]} for k, v in TYPEN.items()}
    r["daten_stand"] = DATEN_STAND
    r["abdeckung"] = ABDECKUNG
    return r
