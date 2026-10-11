import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import makro as m


def T(s):
    return pd.Timestamp(s)


def test_monate_zurueck_auf_monatsende():
    assert m.monate_zurueck("2026-02-28", 12) == T("2025-02-28")
    assert m.monate_zurueck("2024-02-29", 12) == T("2023-02-28")     # Schaltjahr
    assert m.monate_zurueck("2026-06-30", 3) == T("2026-03-31")      # Quartalsende
    assert m.monate_zurueck("2026-03-31", 6) == T("2025-09-30")


def test_jahresrate_von_hand():
    tage = pd.date_range("2025-01-31", periods=24, freq="ME")
    idx = pd.Series(100 * 1.002 ** np.arange(24), index=tage)
    r = m.jahresrate(idx)
    assert len(r) == 12 and abs(r.iloc[0] - (1.002 ** 12 - 1) * 100) < 1e-9


def test_jahresrate_mit_fehlendem_monat_bleibt_richtig():
    """Wie beim US-Preisindex: Oktober 2025 fehlt. Die Jahresrate muss weiter mit dem richtigen Vorjahresmonat vergleichen."""
    tage = pd.date_range("2025-01-31", periods=24, freq="ME")
    idx = pd.Series(np.arange(100.0, 124.0), index=tage)           # jeden Monat +1
    luecke = idx.drop(T("2025-10-31"))
    r = m.jahresrate(luecke)
    # August 2026 gegen August 2025: (119 / 107 - 1) = 11,21 %. Index August 2026 = 100 + 19 = 119, August 2025 = 100 + 7 = 107
    assert abs(r.loc[T("2026-08-31")] - (119 / 107 - 1) * 100) < 1e-9
    # Der Monat nach der Lücke (Okt 2026 hätte Okt 2025 gebraucht) bekommt keinen Wert, statt eines falschen
    assert T("2026-10-31") not in r.index


def test_parse_fred_monatlich_und_quartal():
    text = "observation_date,X\n2026-01-01,4.1\n2026-02-01,.\n2026-03-01,4.3\n"
    s = m.parse_fred(text)
    assert list(s.index) == [T("2026-01-31"), T("2026-03-31")] and list(s) == [4.1, 4.3]
    q = m.parse_fred("observation_date,X\n2026-04-01,5.6\n2026-01-01,5.5\n", quartal=True).sort_index()
    assert list(q.index) == [T("2026-03-31"), T("2026-06-30")]       # 01.04. steht für das zweite Quartal


def test_parse_eurostat():
    j = {"dimension": {"time": {"category": {"index": {"2026-07": 0, "2026-08": 1, "2026-09": 2}}}}, "value": {"0": 3.0, "2": 3.8}}
    s = m.parse_eurostat(json.dumps(j))
    assert list(s.index) == [T("2026-07-31"), T("2026-09-30")] and list(s) == [3.0, 3.8]      # Monat ohne Wert fehlt, wird nicht erfunden


def test_parse_ons_ignoriert_quartals_und_jahreszeilen():
    text = '"Title","x"\n"2025","2.5"\n"2026 Q1","3.1"\n"2026 JUL","2.9"\n"2026 AUG","3.1"\n'
    s = m.parse_ons(text)
    assert list(s.index) == [T("2026-07-31"), T("2026-08-31")] and list(s) == [2.9, 3.1]


def test_parse_imf():
    xml = ('<?xml version="1.0"?><root><DataSet><Series COUNTRY="JPN"><Obs TIME_PERIOD="2026-M06" OBS_VALUE="113.6"/>'
           '<Obs TIME_PERIOD="2026-M07" OBS_VALUE="114.2"/><Obs TIME_PERIOD="2026-M08" OBS_VALUE=""/></Series></DataSet></root>')
    s = m.parse_imf(xml)
    assert list(s.index) == [T("2026-06-30"), T("2026-07-31")] and list(s) == [113.6, 114.2]


def test_parse_snb_nur_gewaehlte_kennung():
    text = '"CubeId";"plkoprinfla"\n"2026-07";"K2";"0.5"\n"2026-07";"TLK";"0.4"\n"2026-08";"TLK";"0.8"\n'
    s = m.parse_snb(text, "TLK")
    assert list(s.index) == [T("2026-07-31"), T("2026-08-31")] and list(s) == [0.4, 0.8]


def test_parse_oecd_monat_und_quartal():
    text = "REF_AREA,TIME_PERIOD,OBS_VALUE\nAUS,2026-07,3.9\nAUS,2026-08,3.97\nNZL,2026-Q2,4.06\nCAN,2026-08,3.0\n"
    assert list(m.parse_oecd(text, "AUS")) == [3.9, 3.97]
    q = m.parse_oecd(text, "NZL")
    assert list(q.index) == [T("2026-06-30")] and list(q) == [4.06]


def tabelle():
    inf = pd.Series([2.0, 2.2, 2.5, 2.9, 3.1, 3.4], index=pd.date_range("2026-03-31", periods=6, freq="ME"))     # Mär bis Aug 2026
    alo = pd.Series([4.0, 4.0, 4.1, 4.1, 4.2, 4.3, 4.3, 4.4, 4.5, 4.4], index=pd.date_range("2025-12-31", periods=10, freq="ME"))   # Dez 2025 bis Sep 2026
    teile = [pd.DataFrame({"land": "US", "groesse": "inflation", "periode": inf.index, "wert": inf.values}),
             pd.DataFrame({"land": "US", "groesse": "arbeitslos", "periode": alo.index, "wert": alo.values})]
    return pd.concat(teile, ignore_index=True)


def test_kennzahlen_von_hand():
    k = m.kennzahlen(tabelle(), "US", heute="2026-10-11", leitzins=3.875)
    assert k["inflation"] == 3.4 and k["inflation_periode"] == "2026-08-31"
    assert k["inflation_abstand_ziel"] == pytest.approx(1.4)
    assert k["inflation_trend"] == pytest.approx(3.4 - 2.5)          # gegen Mai 2026
    assert k["arbeitslos"] == 4.4 and k["arbeitslos_veraenderung"] == pytest.approx(4.4 - 4.1)   # Sep 2026 gegen März 2026
    assert k["realzins"] == pytest.approx(3.875 - 3.4)


def test_trend_mit_fehlendem_vergleichsmonat_ist_leer():
    t = tabelle()
    t = t[~((t["groesse"] == "inflation") & (t["periode"] == T("2026-05-31")))]
    assert m.kennzahlen(t, "US", heute="2026-10-11")["inflation_trend"] is None


def test_frische_ampel():
    # US Inflation: Verzögerung 14 plus Periode 31 = normal 45 Tage; grün bis 52, gelb bis 75, danach rot
    assert m.ampel("US", "inflation", T("2026-08-31"), "2026-10-11")[0] == "gruen"       # 41 Tage
    assert m.ampel("US", "inflation", T("2026-08-31"), "2026-10-20")[0] == "gruen"       # 50 Tage
    assert m.ampel("US", "inflation", T("2026-08-31"), "2026-11-05")[0] == "gelb"        # 66 Tage
    assert m.ampel("US", "inflation", T("2026-08-31"), "2026-12-31")[0] == "rot"         # 122 Tage: Reihe vermutlich eingestellt


def test_pruefe_und_ausgefallene_reihe_behaelt_alte_daten(tmp_path, monkeypatch):
    t = tabelle()
    m.pruefe(t)
    schlecht = t.copy()
    schlecht.loc[0, "wert"] = 90.0
    with pytest.raises(RuntimeError, match="unplausible"):
        m.pruefe(schlecht)
    # Eine Reihe fällt beim Neuladen aus: ihre alten Zeilen bleiben erhalten, die anderen werden aktualisiert
    monkeypatch.setattr(m, "PFAD", tmp_path / "makro.csv")
    monkeypatch.setattr(m, "DATEN", tmp_path)
    t.to_csv(tmp_path / "makro.csv", index=False)
    neu = t[t["groesse"] == "inflation"].copy()
    neu["wert"] = neu["wert"] + 1
    monkeypatch.setattr(m, "lade_alle", lambda: (neu, [(("US", "arbeitslos"), "Quelle nicht erreichbar")]))
    out = m.lade(neu=True)
    assert (out[out["groesse"] == "arbeitslos"]["wert"].values == t[t["groesse"] == "arbeitslos"]["wert"].values).all()
    assert out[out["groesse"] == "inflation"]["wert"].iloc[0] == pytest.approx(3.0)
