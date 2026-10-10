import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kurse
import saisonalitaet as sa


def kassa_und_future(jahre=4, seed=1, praemie=0.004):
    """Zufällige Kassa-Reihe und ein Future daraus, der an jedem Kontraktwechsel (15. Mär/Jun/Sep/Dez) um die Prämie springt."""
    rng = np.random.default_rng(seed)
    tage = pd.bdate_range("2018-01-01", periods=jahre * 261)
    kassa = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(tage)))), index=tage)
    # Future = Kassa mal Prämie, die bis zum nächsten Wechsel auf 0 schrumpft und danach wieder auf den vollen Wert springt
    wechsel = pd.DatetimeIndex([pd.Timestamp(j, m, 15) for j in range(2018, 2024) for m in (3, 6, 9, 12)])
    praem = np.array([praemie * min((wechsel[wechsel >= t][0] - t).days, 90) / 90 for t in tage])
    return kassa, kassa * np.exp(praem)


def test_bereinigung_entfernt_wechselspruenge():
    kassa, fut = kassa_und_future()
    adj, n = kurse.future_bereinigen(fut, kassa)
    assert n >= 10  # etwa ein Wechsel pro Quartal bei vier Jahren
    # Fenster, die einen Wechsel enthalten: roh falsch um bis zu die Prämie, bereinigt nahe an der Kassa
    fehler_roh, fehler_adj = [], []
    for start in pd.date_range("2018-03-01", "2021-10-01", freq="14D"):
        ende = start + pd.Timedelta(days=21)
        a, b = kassa.asof(start), kassa.asof(ende)
        fehler_roh.append(abs((fut.asof(ende) / fut.asof(start)) / (b / a) - 1))
        fehler_adj.append(abs((adj.asof(ende) / adj.asof(start)) / (b / a) - 1))
    assert max(fehler_roh) > 0.003          # ohne Bereinigung Sprung sichtbar
    assert max(fehler_adj) < 0.0015         # bereinigt praktisch die Kassa


def test_grober_datenfehler_wird_ersetzt():
    kassa, fut = kassa_und_future()
    fut = fut.copy()
    fut.iloc[300:] = fut.iloc[300:] * 10   # Faktor 10 ab einem Tag, wie der Yahoo-Fehler beim Yen
    adj, n = kurse.future_bereinigen(fut, kassa)
    r = np.log(adj).diff().abs()
    assert r.max() < 0.05                  # kein Faktor-10-Sprung mehr


def test_ohne_spruenge_bleibt_die_reihe_fast_gleich():
    kassa, fut = kassa_und_future(praemie=0.0)
    adj, _ = kurse.future_bereinigen(fut, kassa)
    pd.testing.assert_series_equal(np.log(adj).diff().dropna().round(8), np.log(fut).diff().dropna().round(8), check_names=False,
                                   atol=1e-3)


def test_endtag_regel_erster_handelstag_ab_dem_datum():
    tage = pd.bdate_range("2010-01-01", "2026-10-09")
    p = pd.Series(100.0, index=tage)
    # Freitag 2021-10-15 = 100, Montag 2021-10-18 = 110, Samstag 2021-10-16 liegt dazwischen
    p[(p.index >= "2021-10-18")] = 110.0
    z = sa.zeitraum(p, (10, 11), (10, 16), 5, 2025)   # Ende Samstag 16.10.: neue Regel nimmt Montag 18.10.
    r2021 = [j for j in z["jahre"] if j["jahr"] == 2021][0]
    assert r2021["ende"] == "2021-10-18" and abs(r2021["rendite"] - 10.0) < 1e-9


def test_ampel_kombi():
    assert sa.ampel_kombi("long", "long") == {"status": "long", "stabil": True}
    assert sa.ampel_kombi("short", "short") == {"status": "short", "stabil": True}
    assert sa.ampel_kombi("neutral", "neutral") == {"status": "neutral", "stabil": True}
    assert sa.ampel_kombi("long", "neutral") == {"status": "long", "stabil": False}
    assert sa.ampel_kombi("neutral", "short") == {"status": "short", "stabil": False}
    assert sa.ampel_kombi("long", "short") == {"status": "widerspruch", "stabil": False}
    assert sa.ampel_kombi("long", None) == {"status": "long", "stabil": None}
