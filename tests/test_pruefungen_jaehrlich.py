import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pruefungen_jaehrlich as pj


def ergebnis(datum="11.10.2026", bestanden=0, tests=24):
    return {"berechnet": datum, "anzahl_tests": tests, "anzahl_bestanden": bestanden, "erwartet_zufall": 0.4, "testjahre": [2016, 2025],
            "zeitraum_von": "2007-07-01", "zeitraum_bis": "2026-06-30",
            "haupt_laenge": 28, "ergebnisse": [{"quelle": "kassa", "auswahl": "A", "laenge": 28, "n_trades": 872, "mean": -0.045, "trefferquote": 49.9, "p": 0.57}]}


def fake_tests(tmp_path, serie):
    """Zwei Schein-Prüfungen, die bei jedem Aufruf das nächste Ergebnis aus 'serie' liefern."""
    zaehler = {"n": 0}

    def runner():
        e = serie[min(zaehler["n"], len(serie) - 1)]
        zaehler["n"] += 1
        (tmp_path / "pruefung_x.json").write_text(json.dumps(e), encoding="utf-8")
        return e
    return [{"name": "Schein (Etappe X)", "runner": runner, "datei": "pruefung_x.json", "bis": pj.daten_bis_saison, "text": pj.beschreibung_saison}]


def test_erster_lauf_schreibt_archiv_und_verlauf(tmp_path):
    t = fake_tests(tmp_path, [ergebnis("11.10.2026")])
    assert pj.lauf(t, tmp_path) == 1
    assert (tmp_path / "pruefungen_archiv" / "pruefung_x_2026-10-11.json").exists()
    z = pj.lade_verlauf(tmp_path)
    assert len(z) == 1 and z[0]["lauf_datum"] == "2026-10-11" and z[0]["anzahl_bestanden"] == "0"
    assert z[0]["kennzahl"] == "Hauptfall (Kassa, 4 Wochen): Ø −0,045 %, 50 % Treffer, p 0,57"


def test_zweiter_lauf_am_selben_tag_doppelt_nichts(tmp_path):
    t = fake_tests(tmp_path, [ergebnis("11.10.2026")])
    pj.lauf(t, tmp_path)
    assert pj.lauf(t, tmp_path) == 0
    assert len(pj.lade_verlauf(tmp_path)) == 1


def test_naechstes_jahr_haengt_eine_zeile_an_und_archiv_bleibt(tmp_path):
    t = fake_tests(tmp_path, [ergebnis("11.10.2026"), ergebnis("01.02.2027", bestanden=1)])
    pj.lauf(t, tmp_path)
    erstes = (tmp_path / "pruefungen_archiv" / "pruefung_x_2026-10-11.json").read_text(encoding="utf-8")
    pj.lauf(t, tmp_path)
    z = pj.lade_verlauf(tmp_path)
    assert [x["lauf_datum"] for x in z] == ["2026-10-11", "2027-02-01"] and z[1]["anzahl_bestanden"] == "1"
    assert (tmp_path / "pruefungen_archiv" / "pruefung_x_2027-02-01.json").exists()
    assert (tmp_path / "pruefungen_archiv" / "pruefung_x_2026-10-11.json").read_text(encoding="utf-8") == erstes   # altes Archiv unverändert


def test_nur_erfassen_rechnet_nicht_neu(tmp_path):
    (tmp_path / "pruefung_x.json").write_text(json.dumps(ergebnis("10.10.2026", bestanden=0)), encoding="utf-8")
    aufgerufen = []
    t = [{"name": "Schein", "runner": lambda: aufgerufen.append(1), "datei": "pruefung_x.json", "bis": pj.daten_bis_saison, "text": pj.beschreibung_saison}]
    assert pj.lauf(t, tmp_path, nur_erfassen=True) == 1
    assert aufgerufen == []


def test_iso_datum():
    assert pj.iso("01.02.2027") == "2027-02-01"
