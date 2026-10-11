import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import makro
import pruefung_makro as pm


def test_veraenderung_ueber_datum_und_luecke():
    idx = pd.date_range("2025-01-31", periods=14, freq="ME")
    s = pd.Series(np.arange(14.0), index=idx).drop(pd.Timestamp("2025-04-30"))
    v = pm.veraenderung(s, 3)
    assert pd.Timestamp("2025-07-31") not in v.index          # Vergleichsmonat April fehlt: kein erfundener Wert
    assert v.loc[pd.Timestamp("2025-08-31")] == pytest.approx(3.0)


def test_bekannt_ab_und_stichtag_kein_blick_in_die_zukunft():
    s = pd.Series([2.0, 3.0], index=pd.to_datetime(["2026-01-31", "2026-02-28"]))
    k = pm.bekannt_ab(s, lag=14)                              # 14 Tage plus 7 Tage Sicherheit
    assert list(k.index) == [pd.Timestamp("2026-02-21"), pd.Timestamp("2026-03-21")]
    wochen = pd.DatetimeIndex(["2026-02-20", "2026-02-27", "2026-03-20", "2026-03-27"])
    w = pm.zum_stichtag(k, wochen)
    assert np.isnan(w.iloc[0]) and w.iloc[1] == 2.0 and w.iloc[2] == 2.0 and w.iloc[3] == 3.0     # 3,0 erst ab 21.03.


def test_spread_von_hand():
    F = np.array([[1, 2, 3, 4, 5, 6, 7.0],
                  [7, 6, 5, 4, 3, 2, 1.0]])
    Z = np.array([[0, 0, 0, 0, 1, 1, 1.0],
                  [0, 0, 0, 0, 1, 1, 1.0]])
    d = pm.spread(F, Z)
    # Woche 1: obere Gruppe = Währungen mit Faktor 5, 6, 7 (z = 1), untere = 1, 2, 3 (z = 0) -> +1. Woche 2: umgekehrt -> -1
    assert list(d) == [1.0, -1.0]
    s, n, hit = pm.statistik(F, Z)
    assert s == 0.0 and n == 2 and hit == 0.5


def test_spread_mit_fehlenden_werten():
    F = np.array([[1, 2, 3, 4, 5, 6, np.nan], [1, 2, 3, np.nan, np.nan, 6, 7.0]])
    Z = np.ones((2, 7))
    d = pm.spread(F, Z)
    assert d[0] == 0.0 and np.isnan(d[1])                     # Woche 2 hat nur 5 gültige Währungen und fällt aus


def test_renditen_einstieg_erst_nach_dem_stichtag_und_von_hand():
    tage = pd.bdate_range("2019-01-01", "2026-10-01")
    rng = np.random.default_rng(0)
    kassa = pd.DataFrame({m: 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(tage)))) for m in pm.WAEHRUNGEN}, index=tage)
    woche = pd.DatetimeIndex(["2024-03-08"])                  # Freitag
    z, r = pm.renditen(kassa, woche, 2)
    p = kassa["6A"]
    k = p.index.searchsorted(woche[0], side="right")
    assert p.index[k] == pd.Timestamp("2024-03-11")           # Montag, strikt nach dem Freitag
    ziel = p.index[k] + pd.Timedelta(days=14)
    k2 = p.index.searchsorted(ziel, side="right") - 1
    assert r.loc[woche[0], "6A"] == pytest.approx((p.iloc[k2] / p.iloc[k] - 1) * 100)


def test_renditen_vergangenheit_aendert_sich_nicht_durch_spaetere_daten():
    tage = pd.bdate_range("2019-01-01", "2026-10-01")
    rng = np.random.default_rng(1)
    kassa = pd.DataFrame({m: 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(tage)))) for m in pm.WAEHRUNGEN}, index=tage)
    woche = pd.DatetimeIndex(["2023-05-05"])
    z1, _ = pm.renditen(kassa, woche, 4)
    z2, _ = pm.renditen(kassa[kassa.index < "2023-07-01"], woche, 4)     # alles nach dem Haltezeitraum abgeschnitten
    pd.testing.assert_frame_equal(z1, z2)


def zufalls_welt(seed, effekt=0.0, wochen=520):
    """Künstliche Welt: Faktor je Währung (langsam veränderlich) und Renditen, die dem Faktor folgen (Stärke 'effekt')."""
    rng = np.random.default_rng(seed)
    F = np.cumsum(rng.normal(0, 0.3, (wochen, 7)), axis=0) * 0.2 + rng.normal(0, 1, (1, 7))
    F = F - F.mean(axis=1, keepdims=True)
    Z = rng.normal(0, 1, (wochen, 7)) + effekt * F
    return F, Z, Z.copy()


def test_findet_eingebauten_zusammenhang_und_nicht_zufall(monkeypatch):
    monkeypatch.setattr(pm, "N_PERM", 300)
    rng = np.random.default_rng(2)
    F, Z, R = zufalls_welt(3, effekt=0.35)
    tr = np.arange(len(F)) < 350
    te = ~tr
    e = pm.pruefe_faktor(F, Z, R, tr, te, 1, rng)
    assert e["richtung"] == "Mitläufer" and e["p_test"] < 0.05 and e["loo"] >= 6 and e["bestanden"]
    F0, Z0, R0 = zufalls_welt(4, effekt=0.0)
    e0 = pm.pruefe_faktor(F0, Z0, R0, tr, te, 1, np.random.default_rng(5))
    assert not e0["bestanden"]


def test_umgekehrter_zusammenhang_wird_als_kontra_erkannt(monkeypatch):
    monkeypatch.setattr(pm, "N_PERM", 300)
    F, Z, R = zufalls_welt(6, effekt=-0.35)
    tr = np.arange(len(F)) < 350
    e = pm.pruefe_faktor(F, Z, R, tr, ~tr, 1, np.random.default_rng(7))
    assert e["richtung"] == "Kontra" and e["bestanden"]


def test_richtung_dreht_sich_im_test_nicht_bestanden(monkeypatch):
    monkeypatch.setattr(pm, "N_PERM", 200)
    F, Z, R = zufalls_welt(8, effekt=0.0)
    Z = Z + np.where(np.arange(len(F))[:, None] < 350, 0.4 * F, -0.4 * F)       # im Training positiv, im Test negativ
    tr = np.arange(len(F)) < 350
    e = pm.pruefe_faktor(F, Z, Z.copy(), tr, ~tr, 1, np.random.default_rng(9))
    assert e["richtung"] == "Mitläufer" and not e["bestanden"] and e["s_test"] < 0


def test_faktor_tabellen_form_und_realzins():
    wochen = pd.date_range("2024-01-05", periods=20, freq="W-FRI")
    tage = pd.date_range("2023-01-01", "2025-01-01", freq="D")
    zdf = pd.DataFrame({c: 3.0 for c in ["US", "XM", "GB", "JP", "CH", "AU", "NZ", "CA"]}, index=tage)
    zdf["XM"] = 2.0
    perioden = pd.date_range("2023-01-31", "2024-12-31", freq="ME")
    teile = []
    for land, infl in (("US", 3.0), ("XM", 2.0), ("GB", 4.0), ("JP", 1.0), ("CH", 1.0), ("AU", 3.0), ("NZ", 3.0), ("CA", 3.0)):
        teile.append(pd.DataFrame({"land": land, "groesse": "inflation", "periode": perioden, "wert": infl}))
        teile.append(pd.DataFrame({"land": land, "groesse": "arbeitslos", "periode": perioden, "wert": 4.0}))
    mk = pd.concat(teile, ignore_index=True)
    f = pm.faktor_tabellen(zdf, mk, wochen)
    assert list(f["F1"].columns) == list(pm.WAEHRUNGEN)
    assert f["F1"]["6E"].iloc[-1] == pytest.approx(2.0 - 3.0)                       # Zinsabstand Euro gegen USA
    assert f["F3"]["6B"].iloc[-1] == pytest.approx(4.0 - 3.0)                       # Inflationsabstand Großbritannien
    assert f["F5"]["6E"].iloc[-1] == pytest.approx((2.0 - 2.0) - (3.0 - 3.0))       # Realzinsabstand Euro 0 minus USA 0
    assert f["F5"]["6B"].iloc[-1] == pytest.approx((3.0 - 4.0) - (3.0 - 3.0))
