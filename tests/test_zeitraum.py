import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import saisonalitaet as sa


def wachsend(tagesrendite=0.001, von="1999-01-01", bis="2026-10-09"):
    tage = pd.bdate_range(von, bis)
    return pd.Series(100 * (1 + tagesrendite) ** np.arange(len(tage)), index=tage)


def test_fenster_von_hand_konstantes_wachstum():
    p = wachsend(0.001)
    # Montag bis Montag eine Woche später: 5 Handelstage * 0,1 % -> 1,001^5 - 1
    z = sa.zeitraum(p, (6, 1), (6, 8), 10, 2025)
    erwartet = (1.001 ** 5 - 1) * 100
    assert z["n"] == 10 and z["plus"] == 10 and z["winrate"] == 100.0
    # je nach Wochentag liegen 4 bis 5 Handelstage im Fenster: Mittel zwischen 4 und 5 Tagen Wachstum
    assert (1.001 ** 4 - 1) * 100 - 1e-9 <= z["mean"] <= erwartet + 1e-9
    assert z["kalendertage"] == 7


def test_jahresrendite_und_schwankung_bei_konstantem_wachstum():
    p = wachsend(0.001)
    z = sa.zeitraum(p, (3, 1), (3, 28), 15, 2025)
    assert abs(z["jahresrendite"] - ((1.001 ** 252 - 1) * 100)) < 0.05
    assert z["schwankung"] is not None and z["schwankung"] < 1e-6  # keine Schwankung -> Sharpe nicht definiert
    assert z["sharpe"] is None and z["ampel"] == "neutral"


def test_jahreswechsel_fenster():
    p = wachsend(0.001)
    z = sa.zeitraum(p, (12, 15), (1, 12), 10, 2025)
    assert z["n"] == 10 and z["kalendertage"] == 28
    assert z["jahre"][0]["ende"].startswith(str(z["jahre"][0]["jahr"] + 1))


def test_nur_abgeschlossene_jahre_kein_blick_in_die_zukunft():
    rng = np.random.default_rng(3)
    tage = pd.bdate_range("1999-01-01", "2026-10-09")
    p = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.006, len(tage)))), index=tage)
    voll = sa.zeitraum(p, (9, 1), (9, 28), 15, 2020)
    kurz = sa.zeitraum(p[p.index < "2021-01-01"], (9, 1), (9, 28), 15, 2020)
    assert voll == kurz


def test_zu_wenige_jahre_keine_kennzahlen():
    p = wachsend()
    z = sa.zeitraum(p, (6, 1), (6, 28), 3, 2025)
    assert z["n"] == 3 and z["winrate"] is None and z["sharpe"] is None and z["ampel"] == "neutral"


def test_ampel_regel_genau_an_den_grenzen():
    assert sa.ampel(60.0, 1.0) == "long"
    assert sa.ampel(59.9, 1.5) == "neutral"
    assert sa.ampel(70.0, 0.99) == "neutral"
    assert sa.ampel(40.0, -1.0) == "short"
    assert sa.ampel(40.1, -2.0) == "neutral"
    assert sa.ampel(30.0, -0.5) == "neutral"
    assert sa.ampel(None, 2.0) == "neutral"


def test_schalttag_als_start_wird_28_februar():
    p = wachsend()
    z = sa.zeitraum(p, (2, 29), (3, 28), 10, 2025)
    assert z["n"] == 10 and z["jahre"][0]["start"].endswith("-02-28") or z["jahre"][0]["start"].endswith("-02-29")


def test_winrate_und_median_von_hand():
    # Fenster 1.5. bis 8.5.: Jahre 2021 bis 2025 mit Renditen +2, +1, -1, +4, -3 Prozent
    tage = pd.bdate_range("2020-01-01", "2025-12-31")
    p = pd.Series(100.0, index=tage)
    for jahr, r in zip(range(2021, 2026), [2, 1, -1, 4, -3]):
        p[(p.index >= f"{jahr}-05-01") & (p.index <= f"{jahr}-05-08")] = np.linspace(100, 100 * (1 + r / 100), ((p.index >= f"{jahr}-05-01") & (p.index <= f"{jahr}-05-08")).sum())
        p[(p.index > f"{jahr}-05-08")] = 100 * (1 + r / 100)
        p[(p.index >= f"{jahr + 1}-01-01")] = 100.0
    z = sa.zeitraum(p, (5, 1), (5, 8), 5, 2025)
    assert z["n"] == 5 and z["plus"] == 3 and z["winrate"] == 60.0
    assert abs(z["median"] - 1.0) < 1e-6 and abs(z["mean"] - 0.6) < 1e-6
