import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import punktesystem as ps

WERTE = {"6A": -0.1, "6B": 0.17, "6S": -1.28, "6N": -1.79, "6J": -1.19, "6E": -1.18, "6C": -1.26}


def schreibe(tmp, datei, inhalt):
    (tmp / datei).write_text(json.dumps(inhalt), encoding="utf-8")


def makro(bestanden_ids):
    return {"ergebnisse": [{"faktor": f, "wochen": 2, "bestanden": f in bestanden_ids} for f in ["F1", "F2", "F3", "F4", "F5", "F6"]]}


def alles_durchgefallen(tmp):
    schreibe(tmp, "pruefung_cot.json", {"ergebnisse": [{"bestanden": False}] * 3})
    schreibe(tmp, "pruefung_saison.json", {"ergebnisse": [{"bestanden": False}] * 3})
    schreibe(tmp, "pruefung_makro.json", makro([]))


def test_ohne_bestandene_pruefung_alles_null_und_ohne_bewertung(tmp_path):
    alles_durchgefallen(tmp_path)
    r = ps.berechne(WERTE, tmp_path)
    assert all(f["status"] == "nicht_bestanden" for f in r["faktoren"]) and r["bestaetigt"] == 0
    assert all(m["gesamt"] == 0 and m["stufe"] == "ohne Bewertung" for m in r["maerkte"].values())


def test_hinweis_ohne_vorwaertsurteil_gibt_keine_punkte(tmp_path):
    alles_durchgefallen(tmp_path)
    schreibe(tmp_path, "pruefung_makro.json", makro(["F5"]))
    schreibe(tmp_path, "vorwaertstest_realzins_ergebnis.json", {"urteil_moeglich": False, "ausgewertet": 3})
    r = ps.berechne(WERTE, tmp_path)
    st = {f["key"]: f["status"] for f in r["faktoren"]}
    assert st["realzins"] == "hinweis" and st["zinsen"] == "nicht_bestanden" and r["bestaetigt"] == 0
    assert all(m["punkte"]["realzins"] == 0 and m["stufe"] == "ohne Bewertung" for m in r["maerkte"].values())
    assert r["maerkte"]["6N"]["realzins_gruppe"] == "lang" and r["maerkte"]["6B"]["realzins_gruppe"] == "kurz"      # Beobachtung läuft mit


def test_vorwaertsurteil_nicht_bestanden_bleibt_hinweis(tmp_path):
    alles_durchgefallen(tmp_path)
    schreibe(tmp_path, "pruefung_makro.json", makro(["F5"]))
    schreibe(tmp_path, "vorwaertstest_realzins_ergebnis.json", {"urteil_moeglich": True, "bestanden": False})
    assert ps.berechne(WERTE, tmp_path)["faktoren"][-1]["status"] == "hinweis"


def test_bestaetigt_gibt_punkte_nach_regel_kontra(tmp_path):
    alles_durchgefallen(tmp_path)
    schreibe(tmp_path, "pruefung_makro.json", makro(["F5"]))
    schreibe(tmp_path, "vorwaertstest_realzins_ergebnis.json", {"urteil_moeglich": True, "bestanden": True})
    r = ps.berechne(WERTE, tmp_path)
    assert r["bestaetigt"] == 1 and r["faktoren"][-1]["status"] == "bestaetigt"
    m = r["maerkte"]
    # niedrigste drei: 6N, 6S, 6C = +1, höchste drei: 6B, 6A, 6E = -1, Mitte: 6J = 0, DX ohne Wert = 0
    assert [m[k]["punkte"]["realzins"] for k in ("6N", "6S", "6C")] == [1, 1, 1]
    assert [m[k]["punkte"]["realzins"] for k in ("6B", "6A", "6E")] == [-1, -1, -1]
    assert m["6J"]["punkte"]["realzins"] == 0 and m["DX"]["punkte"]["realzins"] == 0
    assert m["6N"]["stufe"] == "leicht bullisch" and m["6B"]["stufe"] == "leicht bärisch" and m["6J"]["stufe"] == "neutral"


def test_rueckwaerts_bestanden_aber_andere_faktor_zaehlt_nicht(tmp_path):
    alles_durchgefallen(tmp_path)
    schreibe(tmp_path, "pruefung_makro.json", makro(["F1"]))              # Zinsen bestanden im Rückwärtstest
    r = ps.berechne(WERTE, tmp_path)
    st = {f["key"]: f["status"] for f in r["faktoren"]}
    assert st["zinsen"] == "hinweis" and st["realzins"] == "nicht_bestanden" and st["inflation"] == "nicht_bestanden"


def test_stufen_an_den_grenzen():
    assert ps.stufe(3, 1) == "stark bullisch" and ps.stufe(2, 1) == "leicht bullisch" and ps.stufe(1, 1) == "leicht bullisch"
    assert ps.stufe(0, 2) == "neutral" and ps.stufe(-1, 1) == "leicht bärisch" and ps.stufe(-2, 1) == "leicht bärisch" and ps.stufe(-3, 1) == "stark bärisch"
    assert ps.stufe(0, 0) == "ohne Bewertung" and ps.stufe(5, 0) == "ohne Bewertung"


def test_zu_wenige_werte_keine_gruppen():
    w = dict(WERTE)
    w["6A"] = float("nan")
    w["6B"] = float("nan")
    assert set(ps.realzins_gruppe(w).values()) == {None}


def test_mit_den_echten_dateien_gibt_es_noch_keinen_bestaetigten_faktor():
    r = ps.berechne(WERTE)
    assert r["bestaetigt"] == 0 and all(m["stufe"] == "ohne Bewertung" for m in r["maerkte"].values())
    assert {f["key"]: f["status"] for f in r["faktoren"]}["realzins"] == "hinweis"
