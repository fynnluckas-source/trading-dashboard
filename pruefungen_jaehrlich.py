r"""Jährliche Wiederholung der vorab festgelegten Prüfungen mit den neuen Daten. Die Regeln bleiben UNVERÄNDERT, nur der Zeitraum wächst.

Was passiert:
  1. Jede Prüfung (COT Etappe 1d, Saisonalität Etappe 2c, später Makro Etappe 3c) wird mit den heutigen Daten neu gerechnet.
  2. Das Ergebnis wird als Archiv-Datei mit Datum gespeichert (daten/pruefungen_archiv/), nichts wird überschrieben oder gelöscht.
  3. Eine Zeile je Prüfung kommt in daten/pruefungen_verlauf.csv (Jahresvergleich auf der Seite).
Läuft einmal im Jahr bei GitHub (.github/workflows/pruefungen.yml, 1. Februar), auf Wunsch auch von Hand.

Start:  .venv/Scripts/python.exe pruefungen_jaehrlich.py                 (alle Prüfungen neu rechnen)
        .venv/Scripts/python.exe pruefungen_jaehrlich.py --nur-erfassen  (vorhandene Ergebnisse nur ins Protokoll eintragen, ohne Neuberechnung)
"""
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

DATEN = Path(__file__).parent / "daten"
VERLAUF_SPALTEN = ["lauf_datum", "test", "daten_bis", "anzahl_tests", "anzahl_bestanden", "erwartet_zufall", "kennzahl"]


def _komma(x, stellen=3):
    return f"{x:+.{stellen}f}".replace(".", ",").replace("-", "−")


def beschreibung_cot(d):
    return f"{d['anzahl_bestanden']} von {d['anzahl_tests']} bestanden, Zeitraum {d['zeitraum_von']} bis {d['zeitraum_bis']}"


def beschreibung_saison(d):
    h = next((e for e in d["ergebnisse"] if e["quelle"] == "kassa" and e["auswahl"] == "A" and e["laenge"] == d.get("haupt_laenge", 28)), None)
    if not h or not h.get("n_trades"):
        return "Hauptfall ohne Trades"
    p = f"{h['p']:.2f}".replace(".", ",")
    return f"Hauptfall (Kassa, 4 Wochen): Ø {_komma(h['mean'])} %, {h['trefferquote']:.0f} % Treffer, p {p}"


def beschreibung_makro(d):
    namen = {"F1": "Zinsabstand", "F2": "Zinsabstand-Veränderung", "F3": "Inflationsabstand", "F4": "Inflationstrend", "F5": "Realzinsabstand", "F6": "Arbeitslosen-Trend"}
    treffer = [f"{namen[e['faktor']]} {e['wochen']} Wo. ({e['richtung']})" for e in d["ergebnisse"] if e["bestanden"]]
    return f"{d['anzahl_bestanden']} von {d['anzahl_tests']} bestanden" + (": " + ", ".join(treffer) if treffer else "")


def daten_bis_cot(d):
    return d["zeitraum_bis"]


def daten_bis_saison(d):
    return f"Testjahre {d['testjahre'][0]} bis {d['testjahre'][1]}"


def tests():
    """Alle Prüfungen, die wiederholt werden. Neue Prüfungen (z. B. Makro) hier eintragen."""
    import pruefung_cot
    import pruefung_makro
    import walkforward
    return [
        {"name": "COT (Etappe 1d)", "runner": pruefung_cot.main, "datei": "pruefung_cot.json", "bis": daten_bis_cot, "text": beschreibung_cot},
        {"name": "Saisonalität (Etappe 2c)", "runner": walkforward.main, "datei": "pruefung_saison.json", "bis": daten_bis_saison, "text": beschreibung_saison},
        {"name": "Makro (Etappe 3c)", "runner": pruefung_makro.main, "datei": "pruefung_makro.json", "bis": daten_bis_cot, "text": beschreibung_makro},
    ]


def lade_verlauf(daten=DATEN):
    pfad = Path(daten) / "pruefungen_verlauf.csv"
    if not pfad.exists():
        return []
    with open(pfad, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def schreibe_verlauf(zeilen, daten=DATEN):
    with open(Path(daten) / "pruefungen_verlauf.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=VERLAUF_SPALTEN)
        w.writeheader()
        w.writerows(zeilen)


def iso(datum_text):
    """'11.10.2026' -> '2026-10-11'."""
    return datetime.strptime(datum_text, "%d.%m.%Y").strftime("%Y-%m-%d")


def erfasse(test, ergebnis, daten=DATEN):
    """Archiviert das Ergebnis mit Datum und trägt eine Zeile in den Jahresvergleich ein (nie doppelt für denselben Lauf)."""
    daten = Path(daten)
    archiv = daten / "pruefungen_archiv"
    archiv.mkdir(exist_ok=True)
    lauf = iso(ergebnis["berechnet"])
    ziel = archiv / f"{Path(test['datei']).stem}_{lauf}.json"
    if not ziel.exists():
        ziel.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    zeilen = lade_verlauf(daten)
    if any(z["lauf_datum"] == lauf and z["test"] == test["name"] for z in zeilen):
        return False
    zeilen.append({"lauf_datum": lauf, "test": test["name"], "daten_bis": test["bis"](ergebnis), "anzahl_tests": ergebnis["anzahl_tests"],
                   "anzahl_bestanden": ergebnis["anzahl_bestanden"], "erwartet_zufall": ergebnis["erwartet_zufall"], "kennzahl": test["text"](ergebnis)})
    schreibe_verlauf(zeilen, daten)
    return True


def lauf(tests_liste=None, daten=DATEN, nur_erfassen=False):
    """Rechnet alle Prüfungen neu (oder liest bei nur_erfassen die vorhandenen Dateien) und protokolliert sie. Gibt die Zahl neuer Zeilen zurück."""
    neu = 0
    for t in (tests_liste if tests_liste is not None else tests()):
        if nur_erfassen:
            ergebnis = json.loads((Path(daten) / t["datei"]).read_text(encoding="utf-8"))
        else:
            ergebnis = t["runner"]()
        neu += int(erfasse(t, ergebnis, daten))
        print(f"{t['name']}: {ergebnis['anzahl_bestanden']} von {ergebnis['anzahl_tests']} bestanden ({t['text'](ergebnis)})")
    return neu


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n = lauf(nur_erfassen="--nur-erfassen" in sys.argv)
    print(f"Neue Zeilen im Jahresvergleich: {n}")
