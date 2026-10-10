import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import saisonalitaet as sa


def preise_monatlich_plus_1_prozent(von="1999-01-01", bis="2026-10-09"):
    """Kurs steigt jeden Monat genau um 1 % (am Monatsanfang), dazwischen konstant."""
    tage = pd.bdate_range(von, bis)
    monate = (tage.year - 1999) * 12 + tage.month
    return pd.Series(100 * 1.01 ** monate, index=tage)


def test_monate_von_hand_jeder_monat_plus_1_prozent():
    p = preise_monatlich_plus_1_prozent()
    for z in sa.monate(p, 10, 2025):
        assert abs(z["mean"] - 1.0) < 0.01 and z["hit"] == 100.0 and z["n"] == 10 and z["plus"] == 10


def test_nur_abgeschlossene_jahre_und_richtige_anzahl():
    p = preise_monatlich_plus_1_prozent()
    z = sa.monate(p, 5, 2025)[0]
    assert z["n"] == 5  # 2021 bis 2025
    z2 = sa.monate(p, 5, 2024)[0]
    assert z2["n"] == 5


def test_kein_blick_in_die_zukunft_spaetere_jahre_aendern_nichts():
    rng = np.random.default_rng(0)
    tage = pd.bdate_range("1999-01-01", "2026-10-09")
    p = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.006, len(tage)))), index=tage)
    voll = sa.monate(p, 15, 2020)
    abgeschnitten = sa.monate(p[p.index < "2021-01-01"], 15, 2020)
    assert voll == abgeschnitten
    assert sa.wochen(p, 15, 2020) == sa.wochen(p[p.index < "2021-01-04"], 15, 2020)


def test_trefferquote_und_median_von_hand():
    # Januar-Renditen 2021 bis 2025: +1, +2, -1, +4, -3 Prozent
    tage = pd.bdate_range("2020-12-01", "2025-12-31")
    p = pd.Series(100.0, index=tage)
    # Monatsende Dezember = Basis, Monatsende Januar = Basis * (1 + r): von Hand gebaut
    basis = 100.0
    werte = {}
    for jahr, r in zip(range(2021, 2026), [1, 2, -1, 4, -3]):
        p[(p.index >= f"{jahr - 1}-12-01") & (p.index < f"{jahr}-01-01")] = basis
        p[(p.index >= f"{jahr}-01-01") & (p.index < f"{jahr}-02-01")] = basis * (1 + r / 100)
        basis = basis * (1 + r / 100)
        p[(p.index >= f"{jahr}-02-01") & (p.index < f"{jahr}-12-01")] = basis
    z = sa.monate(p, 5, 2025)[0]
    assert z["n"] == 5 and z["plus"] == 3 and z["hit"] == 60.0 and z["median"] == 1.0
    assert abs(z["mean"] - np.mean([1, 2, -1, 4, -3])) < 1e-6


def test_kurve_laenge_und_wert_von_hand():
    p = preise_monatlich_plus_1_prozent()
    k, anz = sa.kurve(p, 5, 2025)
    assert anz == 5 and len(k) == 365
    # Ende Dezember: 12 Monatsschritte von je 1 % ab dem letzten Dezember-Kurs (der Januar springt zum 1. Handelstag) -> 12 %
    assert abs(k[-1] - (1.01 ** 12 - 1) * 100) < 0.01
    # 1. Januar: Der Monatssprung liegt am ersten Handelstag. Ist Neujahr ein Wochentag (2021, 2024, 2025), zeigt der 1. Januar schon +1 %,
    # sonst (2022, 2023) noch 0 %. Mittel über 5 Jahre also 3/5 = 0,6 %.
    assert abs(k[0] - 0.6) < 0.01


def test_ausblick_von_hand_und_basisrate():
    p = preise_monatlich_plus_1_prozent()
    a = sa.ausblick(p, 10, 2025, pd.Timestamp("2026-10-10"))
    assert a["n"] == 10 and a["hit"] > 0
    # Mittelwert über alle 28-Tage-Fenster ist etwa 28/30 Prozent bei 1 % im Monat
    assert 0.7 < a["basis_mean"] < 1.1


def test_schalttag_start_29_februar_wird_28_februar():
    p = preise_monatlich_plus_1_prozent()
    a = sa.ausblick(p, 5, 2025, pd.Timestamp("2024-02-29"))
    assert a["n"] == 5


def test_zufallsgrenze_binomial():
    assert sa.zufallsgrenze(5) is None  # auch 5 von 5 ist mit Zufall vereinbar (p = 0,0625)
    assert sa.zufallsgrenze(10) == 9
    assert sa.zufallsgrenze(15) == 12
    assert sa.zufallsgrenze(25) == 18


def test_wochen_52_eintraege_und_von_hand():
    p = preise_monatlich_plus_1_prozent()
    w = sa.wochen(p, 5, 2025)
    assert len(w) == 52 and all(x["n"] <= 5 for x in w)
    # Wochen ohne Monatswechsel haben 0 %, Wochen mit Monatswechsel 1 %: Mittelwert liegt zwischen 0 und 1
    assert all(0 <= x["mean"] <= 1.0 + 1e-9 for x in w)
