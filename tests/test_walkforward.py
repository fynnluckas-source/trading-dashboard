import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import saisonalitaet as sa
import walkforward as wf

JAHRE = list(range(1999, 2027))


def zufallsreihe(seed, drift_fenster=None, staerke=0.0006):
    rng = np.random.default_rng(seed)
    tage = pd.bdate_range("1999-01-01", "2026-10-09")
    r = rng.normal(0, 0.005, len(tage))
    if drift_fenster is not None:                       # echte Saisonalität: in diesem Zeitraum jedes Jahr zusätzlicher Anstieg
        a, b = drift_fenster
        m = ((tage.month * 100 + tage.day) >= a) & ((tage.month * 100 + tage.day) <= b)
        r = r + np.where(m, staerke, 0.0)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=tage)


def test_kennzahlen_stimmen_mit_dem_zeitraum_rechner_ueberein():
    s = zufallsreihe(1)
    tab = wf.tabellen(s, JAHRE)
    yi = JAHRE.index(2020)
    for L in (7, 28):
        wr, sharpe = wf.kennzahlen(tab[L], yi - 15, yi)
        for k in (0, 10, 25, 40, 51):
            st = wf.STARTS[k]
            z = sa.zeitraum(s, st, wf.ende_md(st, L), 15, 2019)
            assert abs(wr[k] - z["winrate"]) < 0.06 and abs(sharpe[k] - z["sharpe"]) < 0.0006, (L, k, wr[k], z["winrate"], sharpe[k], z["sharpe"])


def test_kein_blick_in_die_zukunft_signale_aendern_sich_nicht():
    s = zufallsreihe(2)
    voll = wf.tabellen(s, JAHRE)
    bis = wf.tabellen(s[s.index < "2020-01-01"], JAHRE)   # alles ab dem Testjahr 2020 abgeschnitten
    yi = JAHRE.index(2020)
    for L in (14, 28):
        a = wf.kennzahlen(voll[L], yi - 15, yi)
        b = wf.kennzahlen(bis[L], yi - 15, yi)
        # Fenster, die über den Jahreswechsel laufen (Start Dezember), enden im Januar des Testjahres. Für einen Handel im Dezember
        # des Testjahres liegt dieses Vorjahres-Fenster schon in der Vergangenheit, das ist kein Blick in die Zukunft. Geprüft werden
        # deshalb alle Startpunkte, deren Fenster im selben Jahr endet.
        im_jahr = np.array([wf.ende_md(st, L) >= st for st in wf.STARTS])
        np.testing.assert_allclose(a[0][im_jahr], b[0][im_jahr], equal_nan=True)
        np.testing.assert_allclose(a[1][im_jahr], b[1][im_jahr], equal_nan=True)


def daten_aus(serien):
    return {name: {"kassa": wf.tabellen(s, JAHRE), "future": None} for name, s in serien.items()}


def test_der_test_findet_eingebaute_saisonalitaet_und_nicht_zufall(monkeypatch):
    monkeypatch.setattr(wf, "N_PERM", 300)
    rng = np.random.default_rng(5)
    mit = daten_aus({f"M{i}": zufallsreihe(10 + i, drift_fenster=(420, 520), staerke=0.0009) for i in range(8)})
    r = wf.auswerten(mit, JAHRE, "kassa", "A", 28, rng)
    assert r["n_trades"] > 20 and r["mean"] > 0.3 and r["p"] < 0.05 and r["bestanden"]
    ohne = daten_aus({f"M{i}": zufallsreihe(50 + i) for i in range(8)})
    r0 = wf.auswerten(ohne, JAHRE, "kassa", "A", 28, np.random.default_rng(6))
    assert not r0["bestanden"]


def test_auswahl_b_nimmt_pro_markt_und_jahr_hoechstens_einen_trade(monkeypatch):
    monkeypatch.setattr(wf, "N_PERM", 50)
    d = daten_aus({f"M{i}": zufallsreihe(20 + i, drift_fenster=(420, 520), staerke=0.0009) for i in range(4)})
    t = wf.trades(d, JAHRE, "kassa", "B", 28)
    paare = set(zip(t["jahr"], t["markt"]))
    assert len(paare) == len(t["jahr"])
    ta = wf.trades(d, JAHRE, "kassa", "A", 28)
    assert len(ta["jahr"]) >= len(t["jahr"])


def test_signal_regel_an_den_grenzen():
    wr = np.array([60.0, 59.9, 60.0, 40.0, 40.1, 40.0, np.nan])
    sh = np.array([1.0, 1.5, 0.99, -1.0, -2.0, -0.99, 1.0])
    s = wf.signal(wr, sh)
    assert list(s[:6]) == [1, 0, 0, -1, 0, 0] and np.isnan(s[6])


def test_stabil_ist_nie_aktiver_als_kassa_und_future(monkeypatch):
    monkeypatch.setattr(wf, "N_PERM", 50)
    d = {f"M{i}": {"kassa": wf.tabellen(zufallsreihe(30 + i, drift_fenster=(420, 520), staerke=0.0009), JAHRE),
                   "future": wf.tabellen(zufallsreihe(30 + i, drift_fenster=(420, 520), staerke=0.0009) * 1.01, JAHRE)} for i in range(3)}
    nk = len(wf.trades(d, JAHRE, "kassa", "A", 28)["jahr"])
    nf = len(wf.trades(d, JAHRE, "future", "A", 28)["jahr"])
    ns = len(wf.trades(d, JAHRE, "stabil", "A", 28)["jahr"])
    assert ns <= min(nk, nf)
