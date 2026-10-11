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
