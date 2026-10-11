import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import saisonalitaet as sa
import vorwaerts as vw
import walkforward as wf


def serie(seed, bis="2026-10-09", staerke=0.0, fenster=(420, 520)):
    rng = np.random.default_rng(seed)
    tage = pd.bdate_range("1999-01-01", bis)
    r = rng.normal(0, 0.005, len(tage))
    md = tage.month * 100 + tage.day
    r = r + np.where((md >= fenster[0]) & (md <= fenster[1]), staerke, 0.0)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=tage)


def daten(n=3, **kw):
    kassa = pd.DataFrame({f"M{i}": serie(100 + i, **kw) for i in range(n)})
    future = pd.DataFrame({f"M{i}": serie(100 + i, **kw) * 1.002 for i in range(n)})
    return kassa, future


def test_erfassen_ist_idempotent_und_veraendert_nichts(tmp_path):
    kassa, future = daten(staerke=0.0009)
    pfad = tmp_path / "log.csv"
    heute = pd.Timestamp("2026-04-01")
    n1 = vw.erfassen(kassa, future, heute, pfad)
    inhalt = pfad.read_text(encoding="utf-8")
    n2 = vw.erfassen(kassa, future, heute, pfad)      # gleicher Tag noch einmal: nichts Neues
    assert n1 > 0 and n2 == 0 and pfad.read_text(encoding="utf-8") == inhalt


def test_nur_zukuenftige_fenster_werden_erfasst(tmp_path):
    kassa, future = daten(staerke=0.0009)
    pfad = tmp_path / "log.csv"
    heute = pd.Timestamp("2026-04-01")
    vw.erfassen(kassa, future, heute, pfad)
    log = vw.lade_log(pfad)
    starts = pd.to_datetime(log["fenster_start"])
    assert (starts > heute).all() and (starts <= heute + pd.Timedelta(days=vw.HORIZONT_TAGE)).all()
    assert (log["erfasst_am"] == "2026-04-01").all()


def test_erfasste_signale_bleiben_eingefroren(tmp_path):
    kassa, future = daten(staerke=0.0009)
    pfad = tmp_path / "log.csv"
    vw.erfassen(kassa, future, pd.Timestamp("2026-04-01"), pfad)
    vorher = vw.lade_log(pfad)
    # Später sehen die Daten anders aus (die Vergangenheit wird nachträglich verändert) und es kommen neue Wochen dazu
    kassa2, future2 = kassa.copy() * 1.0, future.copy()
    kassa2.iloc[:2000] = kassa2.iloc[:2000] * 1.3
    vw.erfassen(kassa2, future2, pd.Timestamp("2026-04-08"), pfad)
    nachher = vw.lade_log(pfad)
    pd.testing.assert_frame_equal(nachher.iloc[:len(vorher)].reset_index(drop=True), vorher.reset_index(drop=True))
    assert len(nachher) >= len(vorher)
    assert not nachher.duplicated(["jahr", "startpunkt", "laenge", "markt"]).any()


def test_signal_nutzt_nur_jahre_vor_dem_fensterjahr(tmp_path):
    kassa, future = daten(staerke=0.0009)
    kassa_alt = kassa[kassa.index < "2026-01-01"]
    future_alt = future[future.index < "2026-01-01"]
    p1, p2 = tmp_path / "a.csv", tmp_path / "b.csv"
    heute = pd.Timestamp("2026-04-01")
    vw.erfassen(kassa, future, heute, p1)
    vw.erfassen(kassa_alt, future_alt, heute, p2)     # ohne alle Daten des Jahres 2026
    a, b = vw.lade_log(p1), vw.lade_log(p2)
    cols = ["fenster_start", "laenge", "markt", "signal_kassa", "signal_future", "winrate_kassa", "sharpe_kassa"]
    pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].reset_index(drop=True))


def test_auswertung_von_hand_und_nur_leere_felder(tmp_path):
    kassa, future = daten(staerke=0.0009)
    pfad = tmp_path / "log.csv"
    vw.erfassen(kassa, future, pd.Timestamp("2026-04-01"), pfad)   # Fenster im Frühjahr 2026 liegen komplett in der Vergangenheit der Daten
    n = vw.auswerten_log(kassa, future, pfad)
    log = vw.lade_log(pfad)
    assert n > 0
    z = log[log["rendite_kassa"] != ""].iloc[0]
    s = kassa[z["markt"]]
    i0 = s.index.searchsorted(pd.Timestamp(z["fenster_start"]))
    i1 = s.index.searchsorted(pd.Timestamp(z["fenster_ende_soll"]))
    assert abs(float(z["rendite_kassa"]) - (s.iloc[i1] / s.iloc[i0] - 1) * 100) < 1e-5
    vor = log.copy()
    assert vw.auswerten_log(kassa, future, pfad) == 0            # zweiter Lauf: nichts mehr zu tun
    pd.testing.assert_frame_equal(vw.lade_log(pfad), vor)
    # Signale wurden durch die Auswertung nicht berührt
    assert (log["signal_kassa"] == vor["signal_kassa"]).all()


def test_fenster_ohne_daten_bleiben_offen(tmp_path):
    kassa, future = daten(staerke=0.0009, bis="2026-04-10")
    pfad = tmp_path / "log.csv"
    vw.erfassen(kassa, future, pd.Timestamp("2026-04-01"), pfad)
    vw.auswerten_log(kassa, future, pfad)
    log = vw.lade_log(pfad)
    offen = log[pd.to_datetime(log["fenster_ende_soll"]) > pd.Timestamp("2026-04-10")]
    assert len(offen) > 0 and (offen["rendite_kassa"] == "").all()


def test_urteil_erst_nach_zwoelf_monaten_und_genug_trades(tmp_path):
    kassa, future = daten(staerke=0.0009)
    pfad = tmp_path / "log.csv"
    vw.erfassen(kassa, future, pd.Timestamp("2026-04-01"), pfad)
    vw.auswerten_log(kassa, future, pfad)
    z = vw.zusammenfassung(kassa, future, pd.Timestamp("2026-06-01"), pfad)
    assert z["urteil_moeglich"] is False and z["tage"] == 61 and z["erfasst"] > 0
