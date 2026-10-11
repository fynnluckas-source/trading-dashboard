import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import kalender as k


def test_alle_acht_maerkte_haben_eine_notenbank_und_termine():
    assert set(k.NOTENBANKEN) == set(config.MAERKTE) == set(k.TERMINE)
    assert all(len(v) >= 2 for v in k.TERMINE.values())


def test_termine_sortiert_gueltig_und_keine_wochenenden():
    for m, ts in k.TERMINE.items():
        d = [pd.Timestamp(t) for t in ts]          # wirft bei ungültigem Datum
        assert d == sorted(d) and len(set(d)) == len(d), m
        assert all(x.dayofweek < 5 for x in d), m  # Zinsentscheide fallen auf Werktage


def test_naechste_heute_zaehlt_mit():
    n = k.naechste("2026-10-28")
    assert n["DX"]["datum"] == "2026-10-28" and n["DX"]["tage"] == 0 and n["DX"]["danach"] == "2026-12-09"
    assert n["6B"]["datum"] == "2026-11-05" and n["6B"]["tage"] == 8


def test_naechste_am_11_10_2026():
    n = k.naechste("2026-10-11")
    assert n["6N"]["datum"] == "2026-10-28" and n["6S"]["datum"] == "2026-12-10" and n["6C"]["tage"] == 17


def test_leere_liste_gibt_none_und_warnung():
    r = k.berechne("2027-04-01")
    assert all(v["datum"] is None for v in r["naechste"].values()) and r["warnung"]


def test_warnung_wenn_liste_knapp():
    assert k.berechne("2026-10-11")["warnung"] is None
    assert "endet in" in k.berechne("2027-02-20")["warnung"] or "keinen kommenden" in k.berechne("2027-02-20")["warnung"]


def test_liste_ab_sortiert_und_begrenzt():
    z = k.liste_ab("2026-10-11", tage=30)
    assert [x["datum"] for x in z] == sorted(x["datum"] for x in z)
    assert all(0 <= x["tage"] <= 30 for x in z)
    assert {x["markt"] for x in z} == {"DX", "6E", "6J", "6N", "6C", "6A", "6B"}      # 6S entscheidet erst am 10.12.


def test_ereignisse_enthalten_zins_und_daten_sortiert():
    e = k.ereignisse("2026-10-11", 60)
    assert [x["datum"] for x in e] == sorted(x["datum"] for x in e)
    typen = {x["typ"] for x in e}
    assert typen == {"zins", "inflation", "arbeit"}
    assert any(x["markt"] == "DX" and x["typ"] == "arbeit" and x["datum"] == "2026-11-06" for x in e)
    assert all(0 <= x["tage"] <= 60 for x in e)


def test_datentermine_gueltig_werktage_und_bekannte_typen():
    for t, m, typ, text in k.DATEN_TERMINE:
        assert m in k.NOTENBANKEN and typ in ("inflation", "arbeit") and text
        assert pd.Timestamp(t).dayofweek < 5, (t, m)


def test_berechne_hat_ereignisse():
    r = k.berechne("2026-10-11")
    assert r["ereignisse"] and set(r["typen"]) == {"zins", "inflation", "arbeit"}
