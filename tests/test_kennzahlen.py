import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kennzahlen as k


def tabelle(longs, shorts, start="2026-01-06", oi=1000):
    n = len(longs)
    d = pd.DataFrame({"datum": pd.date_range(start, periods=n, freq="7D"), "markt": "6E", "oi": oi})
    for p in ("spec", "comm", "small", "lev", "am"):
        d[f"{p}_long"] = longs
        d[f"{p}_short"] = shorts
    return d


def test_netto_prozent_und_veraenderung_von_hand():
    d = tabelle([300, 350, 330], [200, 100, 130])
    r = k.kennzahlen(d, d)
    s = r[r.gruppe == "spec"].reset_index(drop=True)
    assert list(s["net"]) == [100, 250, 200]
    assert list(s["net_pct"]) == [10.0, 25.0, 20.0]
    assert pd.isna(s["d_net"][0]) and list(s["d_net"][1:]) == [150, -50]


def test_index_liegt_zwischen_0_und_100_und_trifft_extreme():
    d = tabelle(list(range(100, 100 + 60)), [0] * 60)  # Netto steigt jede Woche
    s = k.kennzahlen(d, d).query("gruppe == 'spec'").reset_index(drop=True)
    assert s["idx26"].dropna().between(0, 100).all()
    assert s["idx26"].iloc[-1] == 100  # aktuelles Hoch = 100
    assert s["idx26"].iloc[:25].isna().all()  # vor vollem Fenster kein Wert
    d2 = tabelle(list(range(160, 100, -1)), [0] * 60)  # Netto fällt jede Woche
    assert k.kennzahlen(d2, d2).query("gruppe == 'spec'")["idx26"].iloc[-1] == 0


def test_index_von_hand():
    # Fenster 26: Netto 0..24 und dann 12 -> (12-0)/(25-0)? Wert 25 gehört nicht dazu, hier Max 24 plus aktuelle 12
    netto = list(range(26)) + [13]
    d = tabelle(netto, [0] * len(netto))
    s = k.kennzahlen(d, d).query("gruppe == 'spec'").reset_index(drop=True)
    fenster = netto[-26:]  # letzte 26 Werte inkl. aktuellem
    erwartet = (13 - min(fenster)) / (max(fenster) - min(fenster)) * 100
    assert abs(s["idx26"].iloc[-1] - erwartet) < 1e-9


def test_kein_blick_in_die_zukunft():
    import numpy as np
    rng = np.random.default_rng(1)
    longs = list(rng.integers(100, 1000, 200))
    d = tabelle(longs, [50] * 200)
    voll = k.kennzahlen(d, d).query("gruppe == 'comm'").reset_index(drop=True)
    kurz = k.kennzahlen(d.iloc[:120], d.iloc[:120]).query("gruppe == 'comm'").reset_index(drop=True)
    pd.testing.assert_frame_equal(voll.iloc[:120], kurz)


def test_luecke_in_den_berichten_keine_veraenderung():
    d = tabelle([100, 200, 300], [0, 0, 0])
    d.loc[2, "datum"] = d.loc[1, "datum"] + pd.Timedelta(days=28)
    s = k.kennzahlen(d, d).query("gruppe == 'spec'").reset_index(drop=True)
    assert s["d_net"][1] == 100 and pd.isna(s["d_net"][2])
