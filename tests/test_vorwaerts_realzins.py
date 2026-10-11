import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pruefung_makro as pm
import vorwaerts_realzins as vr


def signal_stub(werte):
    """Ersatz für signal_fuer: liefert feste Realzinsabstände (Reihenfolge der Märkte 6A, 6B, 6S, 6N, 6J, 6E, 6C)."""
    return lambda zdf, mk, freitag: pd.Series(werte, index=list(pm.WAEHRUNGEN), dtype=float)


def kassa_df(bis="2026-10-30"):
    tage = pd.bdate_range("2019-01-01", bis)
    rng = np.random.default_rng(0)
    return pd.DataFrame({m: 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(tage)))) for m in pm.WAEHRUNGEN}, index=tage)


def test_letzter_freitag():
    assert vr.letzter_freitag("2026-10-11") == pd.Timestamp("2026-10-09")      # Sonntag
    assert vr.letzter_freitag("2026-10-09") == pd.Timestamp("2026-10-09")      # Freitag selbst
    assert vr.letzter_freitag("2026-10-13") == pd.Timestamp("2026-10-09")      # Dienstag


def test_erfassen_gruppen_kontra_und_einmalig(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([-1.0, 0.5, 2.0, -0.5, 1.0, 3.0, 0.0]))
    pfad = tmp_path / "log.csv"
    assert vr.erfassen(None, None, "2026-10-11", pfad) == 1
    z = vr.lade_log(pfad).iloc[0]
    # niedrigste drei: 6A (−1,0), 6N (−0,5), 6C (0,0) = Long. Höchste drei: 6S (2,0), 6E (3,0), 6J (1,0)? 6J 1,0 liegt vor 6S 2,0 und 6E 3,0
    assert set(z["lang"].split()) == {"6A", "6N", "6C"} and set(z["kurz"].split()) == {"6J", "6S", "6E"}
    assert z["signal_datum"] == "2026-10-09" and z["erfasst_am"] == "2026-10-11" and z["regel"] == vr.REGEL
    assert vr.erfassen(None, None, "2026-10-11", pfad) == 0                       # gleiche Woche nicht doppelt
    assert len(vr.lade_log(pfad)) == 1


def test_zu_spaet_wird_nicht_nachgetragen(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, 5, 6, 7]))
    pfad = tmp_path / "log.csv"
    assert vr.erfassen(None, None, "2026-10-13", pfad) == 0                        # Dienstag nach dem Freitag: zu spät
    assert vr.erfassen(None, None, "2026-10-12", pfad) == 1                        # Montag: noch erlaubt (Einstieg ist erst der Handelstag nach dem Signal)
    assert not (tmp_path / "log.csv").exists() or len(vr.lade_log(pfad)) == 1


def test_zu_wenige_gueltige_waehrungen_keine_woche(tmp_path, monkeypatch):
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, np.nan, np.nan, 7]))
    assert vr.erfassen(None, None, "2026-10-11", tmp_path / "log.csv") == 0


def test_eingefrorene_zeilen_aendern_sich_nicht(tmp_path, monkeypatch):
    pfad = tmp_path / "log.csv"
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, 5, 6, 7]))
    vr.erfassen(None, None, "2026-10-11", pfad)
    vorher = pfad.read_text(encoding="utf-8")
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([7, 6, 5, 4, 3, 2, 1]))       # Daten sehen später anders aus
    vr.erfassen(None, None, "2026-10-11", pfad)
    vr.erfassen(None, None, "2026-10-12", pfad)
    assert pfad.read_text(encoding="utf-8") == vorher
    vr.erfassen(None, None, "2026-10-18", pfad)                                        # nächste Woche: neue Zeile, alte unverändert
    nachher = vr.lade_log(pfad)
    assert len(nachher) == 2 and nachher.iloc[0]["lang"] == "6A 6B 6S"


def test_auswerten_von_hand_und_nur_leere_felder(tmp_path, monkeypatch):
    kassa = kassa_df("2026-11-06")
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, 5, 6, 7]))        # Long: 6A, 6B, 6S, Short: 6J, 6E, 6C
    pfad = tmp_path / "log.csv"
    vr.erfassen(None, None, "2026-10-11", pfad)
    assert vr.auswerten(kassa, pfad) == 1
    z = vr.lade_log(pfad).iloc[0]
    fr = pd.Timestamp("2026-10-09")
    r = {}
    for m in pm.WAEHRUNGEN:
        p = kassa[m]
        k = p.index.searchsorted(fr, side="right")                                      # Montag 12.10.
        k2 = p.index.searchsorted(p.index[k] + pd.Timedelta(days=14), side="right") - 1
        r[m] = (p.iloc[k2] / p.iloc[k] - 1) * 100
    erwartet = np.mean([r["6A"], r["6B"], r["6S"]]) - np.mean([r["6J"], r["6E"], r["6C"]])
    assert float(z["ergebnis_pct"]) == pytest.approx(erwartet, abs=1e-5)
    assert z["start_handelstag"] == "2026-10-12"
    assert vr.auswerten(kassa, pfad) == 0                                              # zweiter Lauf: nichts zu tun
    assert z["lang"] == "6A 6B 6S"


def test_offene_woche_bleibt_offen(tmp_path, monkeypatch):
    kassa = kassa_df("2026-10-16")                                                     # Kurse enden vor dem Haltedauer-Ende (26.10.)
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, 5, 6, 7]))
    pfad = tmp_path / "log.csv"
    vr.erfassen(None, None, "2026-10-11", pfad)
    assert vr.auswerten(kassa, pfad) == 0 and vr.lade_log(pfad).iloc[0]["ergebnis_pct"] == ""


def test_kein_urteil_am_anfang(tmp_path, monkeypatch):
    kassa = kassa_df("2026-11-06")
    monkeypatch.setattr(vr, "signal_fuer", signal_stub([1, 2, 3, 4, 5, 6, 7]))
    pfad = tmp_path / "log.csv"
    vr.erfassen(None, None, "2026-10-11", pfad)
    vr.auswerten(kassa, pfad)
    z = vr.zusammenfassung(kassa, "2026-11-06", pfad)
    assert z["urteil_moeglich"] is False and z["ausgewertet"] == 1 and z["erfasst"] == 1 and "bestanden" not in z
