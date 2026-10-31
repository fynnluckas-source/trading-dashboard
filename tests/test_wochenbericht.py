import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wochenbericht as wb


def test_bericht_enthaelt_alle_abschnitte_und_keine_signale():
    t = wb.bericht("2026-10-11")
    for abschnitt in ["## Termine der nächsten 10 Tage", "## COT-Positionierung", "## Zinsen, Inflation, Arbeitsmarkt", "## Status der Prüfungen", "## Vorwärtstests"]:
        assert abschnitt in t
    assert t.startswith("---\ntags:") and "date: 2026-10-11" in t
    assert "Information, kein Signal" in t
    assert "keinen bestätigten Faktor" in t
    for w in ("DXY", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD"):
        assert f"| {w} |" in t
    assert "6E" not in t and "| DX |" not in t           # Währungskürzel statt Future-Codes


def test_bericht_termine_in_10_tagen():
    t = wb.bericht("2026-10-25")
    assert "Zinsentscheid" in t and "28.10.2026" in t       # Fed, BoC, RBNZ
    leer = wb.bericht("2026-12-20")
    assert "Termine der nächsten 10 Tage" in leer


def test_schreibe_legt_ordner_an_und_ueberschreibt_nie(tmp_path):
    pfad, neu = wb.schreibe(tmp_path, "2026-10-11")
    assert neu and pfad.exists() and pfad.name == "Trading Wochenbericht 2026-10-11.md"
    assert pfad.parent == tmp_path / wb.ORDNER
    pfad.write_text("von Hand geändert", encoding="utf-8")
    pfad2, neu2 = wb.schreibe(tmp_path, "2026-10-11")
    assert pfad2 == pfad and neu2 is False and pfad.read_text(encoding="utf-8") == "von Hand geändert"


def test_vz_und_prozent():
    assert wb.vz(1234) == "+1.234" and wb.vz(-0.5, 1) == "−0,5" and wb.vz(None) == "–"
    assert wb.prozent(3.456) == "3,46 %" and wb.prozent(None) == "–"


def test_bericht_mit_verlauf_zeigt_vs_vorwoche_und_ideenverlauf(tmp_path):
    import modell
    import modell_verlauf as mv
    auto = modell.automatik("2026-10-10")
    ein = modell.lese_eingaben()
    g = modell.gesamt(auto, ein)
    mv.erfassen(tmp_path, "2026-10-10", auto, ein, g)
    t = wb.bericht("2026-10-17", vault=tmp_path)
    assert "| **vs. Vorwoche** |" in t and "Verlauf der Trade-Ideen" in t and "Vorwoche = Bericht vom 10.10.2026" in t
    leer = wb.bericht("2026-10-17", vault=tmp_path / "leer")
    assert "Noch keine früheren Ideen erfasst" in leer and "| **vs. Vorwoche** |" not in leer


def test_schreibe_erfasst_den_verlauf_einmalig(tmp_path):
    import modell_verlauf as mv
    wb.schreibe(tmp_path, "2026-10-17")
    assert mv.erfasst(tmp_path, "2026-10-17") and len(mv.tabelle(tmp_path)) == 3
    wb.schreibe(tmp_path, "2026-10-17")                      # zweiter Lauf am selben Tag ändert nichts
    assert len(mv.tabelle(tmp_path)) == 3


def test_cot_tabelle_zeigt_netto_position_wie_tradingview():
    t = wb.bericht("2026-10-17")
    i = t.index("## COT-Positionierung")
    abschnitt = t[i:i + 2500]
    assert "Netto " in abschnitt and "Δ" in abschnitt and "letzten 52 Wochen" in abschnitt


def _ergebnis_fuer_erklaerung(technik_aud=2, saison_aud=0):
    import modell
    reihe = modell.REIHE
    zeilen = []
    for k, n, gew, auto in modell.FAKTOREN:
        punkte = {m: 0.0 for m in reihe}
        herkunft = {m: ("automatisch" if auto else "manuell") for m in reihe}
        zeilen.append({"key": k, "name": n, "gewicht": gew, "punkte": punkte, "herkunft": herkunft})
    z = {x["key"]: x for x in zeilen}
    z["zins"]["punkte"]["6A"] = 4.0
    z["immo"]["punkte"]["6A"] = -2.0
    z["technik"]["punkte"]["6A"] = float(technik_aud)
    z["saison"]["punkte"]["6A"] = float(saison_aud)
    fund = {m: sum(x["punkte"][m] for x in zeilen if x["key"] != "technik") for m in reihe}
    tech = {m: z["technik"]["punkte"][m] for m in reihe}
    ges = {m: fund[m] + tech[m] for m in reihe}
    g = {"zeilen": zeilen, "fundamental": fund, "technik": tech, "gesamt": ges,
         "bias": {m: modell.bias(ges[m]) for m in reihe}, "ideen": [], "fehlend": []}
    auto = {"lesung": {"zins": {"6A": "4,60 %, Rang 1 von 8"}, "saison": {"6A": "33 % / −1,11"}, "cot": {}, "inflation": {}, "arbeit": {}},
            "saison_fenster": ("2026-10-31", "2026-11-21")}
    return g, auto


def test_erklaerung_woher_und_veraenderung():
    import modell
    g, auto = _ergebnis_fuer_erklaerung(technik_aud=1, saison_aud=-2)
    vorher = {m: {k: 0.0 for k, *_ in modell.FAKTOREN} for m in modell.REIHE}
    for m in vorher:
        vorher[m].update({"gesamt": 0.0, "bias": "Neutral"})
    vorher["6A"].update({"zins": 4.0, "immo": -2.0, "technik": 2.0, "saison": 0.0, "gesamt": 4.0, "bias": "Neutral"})
    t = "\n".join(wb.erklaerung_zeilen(g, auto, vorher, "2026-10-25"))
    aud = t[t.index("**AUD:"):t.index("**CAD:")]
    assert "Zinsdifferenz +4 (4,60 %, Rang 1 von 8)" in aud and "Immobilien/Kredit −2 (deine Eingabe)" in aud
    assert "Technik +2 → +1 (deine Eingabe geändert)" in aud
    assert "Saisonalität 0 → −2 (neuer Zeitraum ab 31.10.2026: 33 % / −1,11)" in aud
    assert "Vorwoche +4, Neutral, Veränderung −3" in aud
    jpy = t[t.index("**JPY:"):t.index("**EUR:")]
    assert "Kein Faktor hat sich geändert" in jpy and "Kein Faktor ist positiv" in jpy


def test_erklaerung_ohne_vorwoche_und_bias_wechsel():
    import modell
    g, auto = _ergebnis_fuer_erklaerung(technik_aud=2)
    t = "\n".join(wb.erklaerung_zeilen(g, auto, None, None))
    assert t.count("noch keinen früheren Bericht") == 8
    vorher = {m: {**{k: 0.0 for k, *_ in modell.FAKTOREN}, "gesamt": 0.0, "bias": "Neutral"} for m in modell.REIHE}
    t2 = "\n".join(wb.erklaerung_zeilen(g, auto, vorher, "2026-10-25"))
    assert "Die Einstufung wechselt von Neutral auf Neutral" not in t2
    assert "Die Einstufung wechselt von Neutral auf" not in t2[t2.index("**JPY:"):t2.index("**EUR:")]
