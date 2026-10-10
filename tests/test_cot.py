import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import cot


def test_codes_eindeutig():
    codes = [m["cftc"] for m in config.MAERKTE.values()]
    assert len(codes) == len(set(codes)) == 8


def roh(code, datum, **kw):
    z = {"report_date_as_yyyy_mm_dd": datum + "T00:00:00.000", "cftc_contract_market_code": code,
         "futonly_or_combined": "FutOnly"}
    z.update({alt: "10" for alt in cot.SPALTEN["legacy"].values()})
    z.update(kw)
    return z


def test_namenswechsel_egal_weil_code_zaehlt():
    # gleicher Code, unterschiedliche Namen vor und nach 2022 -> eine durchgehende Reihe
    a = roh("096742", "2021-12-28", market_and_exchange_names="BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE")
    b = roh("096742", "2022-02-08", market_and_exchange_names="BRITISH POUND - CHICAGO MERCANTILE EXCHANGE")
    df = cot.aufbereiten("legacy", [a, b])
    assert list(df["markt"]) == ["6B", "6B"]


def test_unbekannter_code_wird_verworfen():
    df = cot.aufbereiten("legacy", [roh("099741", "2026-10-06"), roh("000000", "2026-10-06")])
    assert list(df["markt"]) == ["6E"]


def test_fehlende_spalte_gibt_fehler():
    z = roh("099741", "2026-10-06")
    del z["open_interest_all"]
    with pytest.raises(RuntimeError, match="Spalten fehlen"):
        cot.aufbereiten("legacy", [z])


def test_negative_positionen_gelten_als_fehler():
    with pytest.raises(RuntimeError, match="negative"):
        cot.aufbereiten("legacy", [roh("099741", "2026-10-06", noncomm_positions_long_all="-5")])


def test_nicht_nur_futures_gibt_fehler():
    with pytest.raises(RuntimeError, match="nicht nur Futures"):
        cot.aufbereiten("legacy", [roh("099741", "2026-10-06", futonly_or_combined="Combined")])


def test_luecken_erkennung():
    df = pd.DataFrame({"markt": "6E", "datum": pd.to_datetime(["2026-01-06", "2026-01-13", "2026-02-10"])})
    assert cot.luecken(df) == {"6E": [pd.Timestamp("2026-02-10").date()]}
    assert cot.luecken(df.iloc[:2]) == {}
