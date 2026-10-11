r"""Etappe 4: Punktesystem. Fest vorgegebene Regel, nach der ein Faktor Punkte bekommen darf (so von Fynn am 11.10.2026 entschieden):

  nicht_bestanden  Der Rückwärtstest (Etappe 1d, 2c oder 3c) hat keine Variante bestanden. 0 Punkte, der Faktor bleibt Information.
  hinweis          Der Rückwärtstest wurde bestanden, der Vorwärtstest hat aber noch kein Urteil (oder es steht aus). 0 Punkte,
                   der Faktor läuft als "Beobachtung" getrennt mit.
  bestaetigt       Rückwärtstest UND Vorwärtstest bestanden. Erst dann gibt es Punkte, nach einer vorher festgelegten Regel je Faktor.

Punkte (nur bei "bestaetigt"): jeder bestätigte Faktor gibt -1, 0 oder +1 je Markt (Richtung laut Prüfung). Summe aller bestätigten Faktoren = Gesamtpunkte.
Einstufung: ab +3 stark bullisch, +1 bis +2 leicht bullisch, 0 neutral, -1 bis -2 leicht bärisch, ab -3 stark bärisch.
Gibt es noch gar keinen bestätigten Faktor, wird NICHT "neutral" gezeigt, sondern "ohne Bewertung".

Derzeit hat nur der Realzinsabstand (Etappe 3c, Hinweis) eine Punkte-Regel: Gruppe mit dem niedrigsten Realzinsabstand +1, höchste Gruppe -1 (Kontra),
die Mitte 0. Für alle anderen Faktoren wird eine Regel erst festgelegt, wenn sie eine Prüfung bestanden haben.
"""
import json
from pathlib import Path

import pandas as pd

import config

DATEN = Path(__file__).parent / "daten"

FAKTOREN = [
    {"key": "cot", "name": "COT (Positionierung)", "etappe": "1d", "pruefung": "pruefung_cot.json", "vorwaerts": None, "ids": None},
    {"key": "saison", "name": "Saisonalität", "etappe": "2c", "pruefung": "pruefung_saison.json", "vorwaerts": "vorwaertstest_ergebnis.json", "ids": None},
    {"key": "zinsen", "name": "Zinsen (Abstand und Richtung)", "etappe": "3c", "pruefung": "pruefung_makro.json", "vorwaerts": None, "ids": ["F1", "F2"]},
    {"key": "inflation", "name": "Inflation (Abstand und Trend)", "etappe": "3c", "pruefung": "pruefung_makro.json", "vorwaerts": None, "ids": ["F3", "F4"]},
    {"key": "arbeit", "name": "Arbeitsmarkt (Trend)", "etappe": "3c", "pruefung": "pruefung_makro.json", "vorwaerts": None, "ids": ["F6"]},
    {"key": "realzins", "name": "Realzinsabstand", "etappe": "3c", "pruefung": "pruefung_makro.json", "vorwaerts": "vorwaertstest_realzins_ergebnis.json", "ids": ["F5"]},
]


def _lade(datei, daten=DATEN):
    pfad = Path(daten) / datei
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else None


def rueckwaerts_bestanden(f, daten=DATEN):
    """(bestanden?, Zusammenfassung) des Rückwärtstests eines Faktors."""
    p = _lade(f["pruefung"], daten)
    if p is None:
        return False, "Prüfung fehlt"
    erg = p["ergebnisse"]
    if f["ids"] is not None:
        erg = [e for e in erg if e["faktor"] in f["ids"]]
    treffer = [e for e in erg if e.get("bestanden")]
    return bool(treffer), f"{len(treffer)} von {len(erg)} Tests bestanden"


def vorwaerts_bestaetigt(f, daten=DATEN):
    """True nur, wenn der Vorwärtstest ein Urteil hat UND bestanden ist."""
    if not f["vorwaerts"]:
        return False, "kein Vorwärtstest"
    v = _lade(f["vorwaerts"], daten)
    if v is None:
        return False, "Vorwärtstest fehlt"
    if not v.get("urteil_moeglich"):
        return False, "noch kein Urteil möglich"
    if "bestanden" in v:
        return bool(v["bestanden"]), "Urteil: " + ("bestanden" if v["bestanden"] else "nicht bestanden")
    treffer = [e for e in v.get("ergebnisse", []) if e.get("bestanden")]
    return bool(treffer), f"Urteil: {len(treffer)} Varianten bestanden"


def status(f, daten=DATEN):
    rb, rtext = rueckwaerts_bestanden(f, daten)
    if not rb:
        return {"status": "nicht_bestanden", "text": rtext}
    vb, vtext = vorwaerts_bestaetigt(f, daten)
    if vb:
        return {"status": "bestaetigt", "text": f"{rtext}; Vorwärtstest {vtext}"}
    return {"status": "hinweis", "text": f"{rtext}; Vorwärtstest: {vtext}"}


def stufe(gesamt, anzahl_bestaetigt):
    if anzahl_bestaetigt == 0:
        return "ohne Bewertung"
    return ("stark bullisch" if gesamt >= 3 else "leicht bullisch" if gesamt >= 1 else "neutral" if gesamt == 0
            else "leicht bärisch" if gesamt > -3 else "stark bärisch")


def realzins_gruppe(werte):
    """Gruppe je Markt aus den Realzinsabständen: 'lang' (niedrigste 3), 'kurz' (höchste 3), 'mitte', None (kein Wert, z. B. DX).
    Weniger als 6 gültige Währungen: überall None."""
    s = pd.Series(werte, dtype=float).dropna()
    if len(s) < 6:
        return {m: None for m in werte}
    rang = s.sort_values()
    aus = {m: None for m in werte}
    for m in rang.index:
        aus[m] = "mitte"
    for m in rang.index[:3]:
        aus[m] = "lang"
    for m in rang.index[-3:]:
        aus[m] = "kurz"
    return aus


def punkte_realzins(gruppe):
    """Kontra: niedrigster Realzinsabstand +1, höchster -1."""
    return {"lang": 1, "kurz": -1}.get(gruppe, 0)


def berechne(realzins_werte, daten=DATEN, stand_signal=None):
    """Alles für die Seite. realzins_werte: Realzinsabstand je Währung (z. B. {'6A': -0.1, ...}) für das aktuellste Signal."""
    fakt = []
    for f in FAKTOREN:
        s = status(f, daten)
        fakt.append({"key": f["key"], "name": f["name"], "etappe": f["etappe"], **s})
    stat = {f["key"]: f["status"] for f in fakt}
    anzahl = sum(1 for v in stat.values() if v == "bestaetigt")
    gruppen = realzins_gruppe(realzins_werte)
    maerkte = {}
    for m in config.MAERKTE:
        punkte = {k: 0 for k in stat}
        if stat["realzins"] == "bestaetigt":
            punkte["realzins"] = punkte_realzins(gruppen.get(m))
        gesamt = sum(punkte.values())
        maerkte[m] = {"punkte": punkte, "gesamt": gesamt, "stufe": stufe(gesamt, anzahl), "realzins_gruppe": gruppen.get(m),
                      "realzins_wert": None if m not in realzins_werte or pd.isna(realzins_werte[m]) else round(float(realzins_werte[m]), 3)}
    return {"faktoren": fakt, "bestaetigt": anzahl, "maerkte": maerkte, "stand_signal": stand_signal}
