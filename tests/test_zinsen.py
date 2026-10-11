import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zinsen as z


def tabelle():
    """Künstliche Leitzinsen: tägliche Reihen ab 2023-01-01 bis 2026-10-06, AU endet früher (Datenverzug)."""
    tage = pd.date_range("2023-01-01", "2026-10-06", freq="D")
    df = pd.DataFrame(index=tage, columns=z.LAENDER + ["US2Y"], dtype=float)
    df["US"] = 4.0
    df.loc["2025-06-01":, "US"] = 3.5            # US senkt am 1.6.2025 um 0,5
    df["XM"] = 2.0
    df.loc["2026-03-01":, "XM"] = 2.5            # EZB erhöht am 1.3.2026 um 0,5
    df["JP"], df["GB"], df["CA"], df["CH"], df["NZ"] = 0.5, 4.5, 3.0, 1.0, 5.0
    df["AU"] = 4.0
    df.loc["2026-09-25":, "AU"] = np.nan         # AU-Daten enden am 24.9.
    df["US2Y"] = 4.2
    return df


def test_fortschreiben_nur_bis_zum_letzten_wert():
    roh = pd.DataFrame({"US": [3.0, np.nan, 3.5, np.nan, np.nan], "XM": [2.0, np.nan, np.nan, np.nan, np.nan]},
                       index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]))
    f = z.fortschreiben(roh)
    assert list(f["US"].iloc[:3]) == [3.0, 3.0, 3.5] and f["US"].iloc[3:].isna().all()    # nach dem letzten Wert nichts erfunden
    assert f["XM"].iloc[0] == 2.0 and f["XM"].iloc[1:].isna().all()


def test_abstand_von_hand():
    df = tabelle()
    k = z.kennzahlen(df, "6E")
    assert k["abstand"] == pytest.approx(2.5 - 3.5)             # EUR minus USD
    k2 = z.kennzahlen(df, "6B")
    assert k2["abstand"] == pytest.approx(4.5 - 3.5)


def test_dx_abstand_ist_us_minus_gewichteter_korb():
    df = tabelle()
    korb = (2.5 * 57.6 + 0.5 * 13.6 + 4.5 * 11.9 + 3.0 * 9.1 + 1.0 * 3.6) / (57.6 + 13.6 + 11.9 + 9.1 + 3.6)
    assert z.kennzahlen(df, "DX")["abstand"] == pytest.approx(3.5 - korb, abs=1e-3)


def test_aenderung_des_abstands_ueber_monate_von_hand():
    df = tabelle()
    k = z.kennzahlen(df, "6E")       # Stichtag 6.10.2026
    # vor 12 Monaten (6.10.2025): EUR 2,0 und USD 3,5 -> Abstand -1,5; heute -1,0 -> Änderung +0,5
    assert k["d_abstand_12m"] == pytest.approx(0.5)
    # vor 6 Monaten (6.4.2026): EUR schon 2,5 -> Abstand -1,0 wie heute -> 0
    assert k["d_abstand_6m"] == pytest.approx(0.0)
    assert k["d_abstand_3m"] == pytest.approx(0.0)


def test_letzte_aenderung_und_richtung():
    df = tabelle()
    k = z.kennzahlen(df, "6E")
    assert k["letzte_aenderung_datum"] == "2026-03-01" and k["letzte_aenderung_groesse"] == pytest.approx(0.5)
    assert k["aenderung_12m"] == pytest.approx(0.5) and k["richtung_12m"] == "erhöht" and k["anzahl_aenderungen_12m"] == 1
    k_us = z.kennzahlen(df, "DX")                   # DX: Zinsänderungen des Dollars
    assert k_us["letzte_aenderung_datum"] == "2025-06-01" and k_us["letzte_aenderung_groesse"] == pytest.approx(-0.5)
    assert z.kennzahlen(df, "6J")["richtung_12m"] == "unverändert" and z.kennzahlen(df, "6J")["letzte_aenderung_datum"] is None


def test_stichtag_ist_der_letzte_gemeinsame_tag():
    df = tabelle()
    k = z.kennzahlen(df, "6A")                      # AU endet am 24.9.
    assert k["stichtag"] == "2026-09-24" and k["datenstand_land"] == "2026-09-24"
    assert z.kennzahlen(df, "6E")["stichtag"] == "2026-10-06"


def test_pruefe_erkennt_unplausible_und_fehlende_daten():
    df = tabelle()
    z.pruefe(df)
    df2 = df.copy()
    df2.loc["2026-01-01", "CH"] = 99.0
    with pytest.raises(RuntimeError, match="unplausible"):
        z.pruefe(df2)
    df3 = df.copy()
    df3["JP"] = np.nan
    with pytest.raises(RuntimeError, match="keine Daten"):
        z.pruefe(df3)


def test_verlauf_woechentlich_laenge_und_werte():
    df = tabelle()
    v = z.verlauf_woechentlich(df, "6E")
    assert len(v["datum"]) == len(v["land"]) == len(v["us"]) == len(v["abstand"])
    assert v["abstand"][-1] == pytest.approx(v["land"][-1] - v["us"][-1])
