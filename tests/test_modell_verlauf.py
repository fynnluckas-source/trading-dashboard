import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modell
import modell_verlauf as mv

REIHE = modell.REIHE


def ergebnis(gesamt_je_markt, ideen):
    zeilen = [{"key": k, "name": n, "gewicht": g, "punkte": {m: 0 for m in REIHE}, "herkunft": {m: "manuell" for m in REIHE}} for k, n, g, _ in modell.FAKTOREN]
    return {"zeilen": zeilen, "fundamental": dict(gesamt_je_markt), "technik": {m: 0 for m in REIHE}, "gesamt": dict(gesamt_je_markt),
            "bias": {m: modell.bias(v) for m, v in gesamt_je_markt.items()}, "ideen": ideen, "fehlend": []}


AUTO = {"saison_fenster": ("2026-10-12", "2026-11-02")}
EIN = {"stand": "2026-10-12"}
SCORES = {"6J": -3, "6E": 3, "6B": 3, "6S": -1, "6A": 11, "6C": -9, "6N": 5, "DX": 7}
IDEEN = [{"delta": 20, "long": "6A", "short": "6C"}, {"delta": 16, "long": "DX", "short": "6C"}, {"delta": 14, "long": "6N", "short": "6C"}]


def kassa(bis="2026-12-31", seed=0):
    tage = pd.bdate_range("2026-01-01", bis)
    rng = np.random.default_rng(seed)
    return pd.DataFrame({m: 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(tage)))) for m in REIHE}, index=tage)


def test_erfassen_einmalig_und_unveraenderlich(tmp_path):
    assert mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis(SCORES, IDEEN)) is True
    vorher = mv.pfad(tmp_path, mv.VERLAUF).read_text(encoding="utf-8")
    assert mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis({m: 0 for m in REIHE}, IDEEN)) is False
    assert mv.pfad(tmp_path, mv.VERLAUF).read_text(encoding="utf-8") == vorher
    d = pd.read_csv(mv.pfad(tmp_path, mv.VERLAUF))
    assert len(d) == 8 and d[d.markt == "6A"].iloc[0]["gesamt"] == 11
    assert len(mv.tabelle(tmp_path)) == 3


def test_vorwoche_nimmt_letzten_bericht_mindestens_4_tage_vorher(tmp_path):
    mv.erfassen(tmp_path, "2026-10-10", AUTO, EIN, ergebnis(SCORES, IDEEN))
    mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis({m: v + 1 for m, v in SCORES.items()}, IDEEN))
    vw, tag = mv.vorwoche(tmp_path, "2026-10-24")
    assert tag == "2026-10-17" and vw["6A"] == 12
    vw, tag = mv.vorwoche(tmp_path, "2026-10-17")          # derselbe Tag zählt nicht als Vorwoche
    assert tag == "2026-10-10" and vw["6A"] == 11
    assert mv.vorwoche(tmp_path, "2026-10-12") == (None, None)


def test_paar_rendite_mit_dxy():
    r = {"6A": 2.0, "6C": -1.0, "6E": 0.5}
    assert mv.paar_rendite(r, "6A", "6C") == 3.0
    assert mv.paar_rendite(r, "DX", "6C") == 1.0         # Long DXY gegen CAD = -Rendite von CAD
    assert mv.paar_rendite(r, "6E", "DX") == 0.5         # Short DXY = Rendite der Long-Währung


def test_auswerten_von_hand_und_nur_leere_felder(tmp_path):
    k = kassa()
    mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis(SCORES, IDEEN))      # Samstag
    n = mv.auswerten(tmp_path, k)
    assert n == 9                                                                  # 3 Ideen x 3 Haltedauern
    t = mv.tabelle(tmp_path)
    erste = t.iloc[0]                                                              # Long AUD / Short CAD
    start = k.index[k.index.searchsorted(pd.Timestamp("2026-10-17"), side="right")]
    assert start == pd.Timestamp("2026-10-19") and erste["start_handelstag"] == "2026-10-19"
    def rend(m, w):
        p = k[m]
        i0 = p.index.get_loc(start)
        i1 = p.index.searchsorted(start + pd.Timedelta(days=7 * w), side="right") - 1
        return (p.iloc[i1] / p.iloc[i0] - 1) * 100
    assert float(erste["r2w"]) == pytest.approx(rend("6A", 2) - rend("6C", 2), abs=1e-3)
    zweite = t.iloc[1]                                                             # Long DXY / Short CAD
    assert float(zweite["r1w"]) == pytest.approx(-rend("6C", 1), abs=1e-3)
    assert mv.auswerten(tmp_path, k) == 0                                          # zweiter Lauf: nichts zu tun


def test_offene_haltedauer_bleibt_leer(tmp_path):
    k = kassa("2026-10-30")                                                        # Kurse enden 13 Tage nach dem Einstieg
    mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis(SCORES, IDEEN))
    mv.auswerten(tmp_path, k)
    t = mv.tabelle(tmp_path).iloc[0]
    assert t["r1w"] != "" and t["r2w"] == "" and t["r4w"] == ""


def test_kein_urteil_am_anfang(tmp_path):
    mv.erfassen(tmp_path, "2026-10-17", AUTO, EIN, ergebnis(SCORES, IDEEN))
    mv.auswerten(tmp_path, kassa())
    z = mv.zusammenfassung(tmp_path)
    assert z["urteil_moeglich"] is False and z["berichtswochen"] == 1 and z["ausgewertet"] == 3 and "bestanden" not in z


def test_urteil_nur_mit_genug_wochen_und_ideen(tmp_path):
    for w in range(26):
        tag = (pd.Timestamp("2026-10-17") + pd.Timedelta(days=7 * w)).strftime("%Y-%m-%d")
        mv.erfassen(tmp_path, tag, AUTO, EIN, ergebnis(SCORES, IDEEN))
    mv.auswerten(tmp_path, kassa("2027-12-31", seed=3))
    z = mv.zusammenfassung(tmp_path)
    assert z["urteil_moeglich"] is True and z["ausgewertet"] == 78 and isinstance(z["bestanden"], bool)
