import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pruefung_cot as pc


def tag(s):
    return pd.Timestamp(s)


def test_veroeffentlichung_normale_woche_ist_freitag():
    assert pc.veroeffentlichung("2026-10-06") == tag("2026-10-09")  # Dienstag -> Freitag


def test_veroeffentlichung_montag_feiertag_verschiebt_auf_montag():
    # Columbus Day: Montag 12.10.2026, Stichtag Dienstag 13.10. -> Veröffentlichung Montag 19.10.
    assert pc.veroeffentlichung("2026-10-13") == tag("2026-10-19")


def test_veroeffentlichung_thanksgiving_woche():
    # Thanksgiving Donnerstag 27.11.2025 -> Bericht (Stichtag 25.11.) erst Montag 01.12.
    assert pc.veroeffentlichung("2025-11-25") == tag("2025-12-01")


def test_veroeffentlichung_freitag_feiertag():
    # Juneteenth Freitag 19.06.2026 -> Stichtag 16.06. erst Montag 22.06.
    assert pc.veroeffentlichung("2026-06-16") == tag("2026-06-22")


def preis(tage=3000, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=tage)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.005, tage))), index=idx)


def test_einstieg_erst_nach_veroeffentlichung_und_von_hand():
    p = preis()
    d = tag("2015-03-03")  # Dienstag
    z = pc.rendite_z(p, [d], 4)[0]
    pub = pc.veroeffentlichung(d)  # Freitag
    k = p.index.searchsorted(pub, side="right")
    assert p.index[k] > pub  # Einstieg strikt nach der Veröffentlichung (Montag)
    ziel = p.index[k] + pd.Timedelta(days=28)
    k2 = p.index.searchsorted(ziel, side="right") - 1
    log = np.log(p)
    sigma = log.diff().rolling(260, min_periods=200).std().iloc[k] * np.sqrt(5)
    erwartet = (log.iloc[k2] - log.iloc[k]) / (sigma * np.sqrt(4))
    assert abs(z - erwartet) < 1e-9


def test_kein_blick_in_die_zukunft_bei_der_schwankung():
    p = preis()
    d = tag("2015-03-03")
    z_voll = pc.rendite_z(p, [d], 4)[0]
    k = p.index.searchsorted(pc.veroeffentlichung(d), side="right")
    ende = p.index[k] + pd.Timedelta(days=28)
    z_kurz = pc.rendite_z(p[p.index <= ende], [d], 4)[0]  # alles nach dem Haltezeitraum abgeschnitten
    assert abs(z_voll - z_kurz) < 1e-12


def test_unvollstaendiger_zeitraum_gibt_nan():
    p = preis(tage=1500)
    letzter = p.index[-1]
    d = (letzter - pd.Timedelta(days=10)).normalize()
    assert np.isnan(pc.rendite_z(p, [d], 13)[0])


def test_stat_von_hand():
    sig = np.array([1, 1, -1, -1, 0] * 10, dtype=float).reshape(-1, 1)
    z = np.array([1.0, 3.0, -1.0, -3.0, 0.5] * 10).reshape(-1, 1)
    d, nh, nt = pc.stat(sig, z)
    assert d == 2.0 - (-2.0) and nh == 20 and nt == 20


def test_zu_wenige_signale_geben_nan():
    sig = np.array([1.0] * 5 + [-1.0] * 5 + [0.0] * 20).reshape(-1, 1)
    z = np.ones((30, 1))
    assert np.isnan(pc.stat(sig, z)[0])


def test_permutationstest_findet_eingebauten_effekt_und_nicht_zufall():
    rng = np.random.default_rng(1)
    T, M = 600, 8
    # Signal in Serien (wie echte Index-Daten), Rendite folgt dem Signal
    s = np.zeros((T, M))
    for j in range(M):
        zustand = 0
        for t in range(T):
            if rng.random() < 0.05:
                zustand = rng.choice([-1, 0, 1])
            s[t, j] = zustand
    z_effekt = s * 0.8 + rng.normal(0, 1, (T, M))
    d, _, _ = pc.stat(s, z_effekt)
    p_effekt = pc.perm_p(s, z_effekt, d, +1, 1, np.random.default_rng(2))
    assert d > 1 and p_effekt < 0.01
    z_zufall = rng.normal(0, 1, (T, M))
    d0, _, _ = pc.stat(s, z_zufall)
    p0 = pc.perm_p(s, z_zufall, d0, 0, 1, np.random.default_rng(3))
    assert p0 > 0.05


def test_phasen_zaehlen_serien():
    sig = np.array([[0, 1, 1, 0, -1, -1, 1, np.nan]], dtype=float).T
    assert pc.phasen(sig) == 3
