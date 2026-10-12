import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modell as m

# Leitzinse laut Fynns KW-42-Notizen (Stand 04.10.2026)
ZINSEN_KW42 = {"6A": 4.60, "DX": 3.875, "6B": 3.75, "6N": 2.75, "6E": 2.50, "6C": 2.25, "6J": 1.25, "6S": 0.0}


def test_zins_rangregel_ergibt_fynns_kw42_spalte():
    p = m.punkte_zins(ZINSEN_KW42)
    assert p == m.KW42_FYNN["zins"]


def test_zins_ohne_alle_acht_werte_gibt_nullen():
    z = dict(ZINSEN_KW42)
    z["6S"] = float("nan")
    assert set(m.punkte_zins(z).values()) == {0}


@pytest.mark.parametrize("idx,d,erwartet", [
    (100, -5, 2), (80, -5, 2), (79, 1, 2), (79, -1, 1), (50, 1, 2), (50, 0, 1), (49, 1, 1), (49, -1, 0),
    (21, -1, 0), (20, 1, 0), (20, -1, -1), (0, -1, -1), (None, 1, 0),
])
def test_cot_regel(idx, d, erwartet):
    assert m.punkte_cot(idx, d) == erwartet


def test_cot_gegen_fynns_kw42_bis_auf_dxy():
    # Daten aus der Seite (Commercials, 52 Wochen, Stichtag 06.10.2026): Index und Wochenveränderung
    daten = {"6J": (22, -5764), "6E": (100, 31447), "6B": (90, 10985), "6S": (29, -2854), "6A": (100, 38744), "6C": (63, 13938), "6N": (53, 12386), "DX": (26, -397)}
    abweichend = [k for k, (i, d) in daten.items() if m.punkte_cot(i, d) != m.KW42_FYNN["cot"][k]]
    assert abweichend == ["DX"]            # bekannte Abweichung: Fynn gab -1, die Regel gibt 0


@pytest.mark.parametrize("a,erwartet", [(2.0, 2), (1.5, 2), (1.49, 1), (0.75, 1), (0.74, 0), (0.0, 0), (-0.74, 0), (-0.75, -1), (-1.5, -2), (None, 0)])
def test_inflation_regel(a, erwartet):
    assert m.punkte_inflation(a) == erwartet


@pytest.mark.parametrize("v,erwartet", [(-0.6, 2), (-0.3, 1), (-0.29, 0), (0.0, 0), (0.29, 0), (0.3, -1), (0.6, -2), (None, 0)])
def test_arbeit_regel(v, erwartet):
    assert m.punkte_arbeit(v) == erwartet


@pytest.mark.parametrize("w,s,erwartet", [
    (65, 1.02, 2), (60, 1.0, 2), (60, 0.13, 0),          # Winrate 60 %, Sharpe nur 0,13: Widerspruch, laut Notiz neutral
    (57, 0.6, 1), (55, 0.5, 1), (50, 0.0, 0), (45, -0.4, 0),
    (48, -0.6, -1), (26, -1.26, -2), (40, -1.09, -2), (40, -0.9, -1), (None, 1.0, 0),
])
def test_saison_skala(w, s, erwartet):
    assert m.punkte_saison(w, s) == erwartet


@pytest.mark.parametrize("score,name", [
    (11, "Stark Bullish"), (10, "Stark Bullish"), (9, "Bullish"), (5, "Bullish"), (4, "Neutral"), (0, "Neutral"), (-4, "Neutral"),
    (-5, "Bearish"), (-9, "Bearish"), (-10, "Stark Bearish"), (-12, "Stark Bearish"),
])
def test_bias_skala_wie_im_vault(score, name):
    assert m.bias(score) == name


def test_automatik_laeuft_mit_den_echten_daten_und_nur_erlaubte_punkte():
    a = m.automatik("2026-10-12")
    assert set(a["punkte"]) == {"zins", "cot", "inflation", "arbeit", "saison"}
    for f, je_markt in a["punkte"].items():
        assert set(je_markt) == {"DX", "6A", "6B", "6S", "6N", "6J", "6E", "6C"}
        assert all(-2 <= p <= 2 for p in je_markt.values()), f
    assert a["saison_fenster"] == ("2026-10-12", "2026-11-02")             # Standard: heute, 3 Wochen


def test_saison_fenster_laesst_sich_in_die_zukunft_verschieben():
    a = m.automatik("2026-10-12", saison_start="2026-11-16", saison_tage=21)
    assert a["saison_fenster"] == ("2026-11-16", "2026-12-07")
