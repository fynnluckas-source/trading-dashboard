import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modell as m

# Leitzinse laut Fynns KW-42-Notizen (Stand 04.10.2026)
ZINSEN_KW42 = {"6A": 4.60, "DX": 3.875, "6B": 3.75, "6N": 2.75, "6E": 2.50, "6C": 2.25, "6J": 1.25, "6S": 0.0}


def test_zins_rangregel_ergibt_fynns_kw42_spalte():
    p = m.punkte_zins(ZINSEN_KW42)
    assert p == m.KW42_FYNN["zins"]


def test_zins_ohne_alle_acht_werte_gibt_nullen():
    z = dict(ZINSEN_KW42)
    z["6S"] = float("nan")
    assert set(m.punkte_zins(z).values()) == {0}


@pytest.mark.parametrize("idx,d,erwartet", [
    (100, -5, 2), (80, -5, 2), (79, 1, 2), (79, -1, 1), (50, 1, 2), (50, 0, 1), (49, 1, 1), (49, -1, 0),
    (21, -1, 0), (20, 1, 0), (20, -1, -1), (0, -1, -1), (None, 1, 0),
])
def test_cot_regel(idx, d, erwartet):
    assert m.punkte_cot(idx, d) == erwartet


def test_cot_regel_mit_einer_woche_gegen_fynns_kw42_bis_auf_dxy():
    # Alte Variante (1 Woche, bis 17.10.2026) als Prüfung der Punkte-Regel selbst: Index und Wochenveränderung, Stichtag 06.10.2026
    daten = {"6J": (22, -5764), "6E": (100, 31447), "6B": (90, 10985), "6S": (29, -2854), "6A": (100, 38744), "6C": (63, 13938), "6N": (53, 12386), "DX": (26, -397)}
    abweichend = [k for k, (i, d) in daten.items() if m.punkte_cot(i, d) != m.KW42_FYNN["cot"][k]]
    assert abweichend == ["DX"]            # bekannte Abweichung: Fynn gab -1, die Regel gibt 0


@pytest.mark.parametrize("a,erwartet", [(2.0, 2), (1.5, 2), (1.49, 1), (0.75, 1), (0.74, 0), (0.0, 0), (-0.74, 0), (-0.75, -1), (-1.5, -2), (None, 0)])
def test_inflation_regel(a, erwartet):
    assert m.punkte_inflation(a) == erwartet


@pytest.mark.parametrize("v,erwartet", [(-0.6, 2), (-0.3, 1), (-0.29, 0), (0.0, 0), (0.29, 0), (0.3, -1), (0.6, -2), (None, 0)])
def test_arbeit_regel(v, erwartet):
    assert m.punkte_arbeit(v) == erwartet


@pytest.mark.parametrize("w,s,erwartet", [
    (65, 1.02, 2), (60, 1.0, 2), (60, 0.13, 0),          # Winrate 60 %, Sharpe nur 0,13: Widerspruch, laut Notiz neutral
    (57, 0.6, 1), (55, 0.5, 1), (50, 0.0, 0), (45, -0.4, 0),
    (48, -0.6, -1), (26, -1.26, -2), (40, -1.09, -2), (40, -0.9, -1), (None, 1.0, 0),
])
def test_saison_skala(w, s, erwartet):
    assert m.punkte_saison(w, s) == erwartet


@pytest.mark.parametrize("score,name", [
    (11, "Stark Bullish"), (10, "Stark Bullish"), (9, "Bullish"), (5, "Bullish"), (4, "Neutral"), (0, "Neutral"), (-4, "Neutral"),
    (-5, "Bearish"), (-9, "Bearish"), (-10, "Stark Bearish"), (-12, "Stark Bearish"),
])
def test_bias_skala_wie_im_vault(score, name):
    assert m.bias(score) == name


def test_automatik_laeuft_mit_den_echten_daten_und_nur_erlaubte_punkte():
    a = m.automatik("2026-10-12")
    assert set(a["punkte"]) == {"zins", "cot", "inflation", "arbeit", "saison"}
    for f, je_markt in a["punkte"].items():
        assert set(je_markt) == {"DX", "6A", "6B", "6S", "6N", "6J", "6E", "6C"}
        assert all(-2 <= p <= 2 for p in je_markt.values()), f
    assert a["saison_fenster"] == ("2026-10-12", "2026-11-02")             # Standard: heute, 3 Wochen


def test_saison_fenster_laesst_sich_in_die_zukunft_verschieben():
    a = m.automatik("2026-10-12", saison_start="2026-11-16", saison_tage=21)
    assert a["saison_fenster"] == ("2026-11-16", "2026-12-07")


def test_de_format():
    assert m.de(-5764, 0, True) == "−5.764" and m.de(31447, 0, True) == "+31.447" and m.de(3.456, 2) == "3,46" and m.de(None) == "–"


def test_lesung_ohne_stoerende_zeichen():
    a = m.automatik("2026-10-12")
    for f, je in a["lesung"].items():
        for mk, t in je.items():
            assert ". Δ" not in t and "nan" not in t.lower(), (f, mk, t)


def test_gesamt_reproduziert_fynns_kw42_summen():
    """Mit Fynns eigenen KW-42-Werten für alle Faktoren muss genau seine Tabelle herauskommen (Summen JPY -3, EUR +3, GBP +3, CHF -1, AUD +11, CAD -9, NZD +5, USD +7)."""
    auto = {"punkte": {f: dict(w) for f, w in m.KW42_FYNN.items()}}
    ein = {"manuell": {
        "zb": dict(zip(m._KW42_REIHE, [0, 0, 1, -1, 2, -1, 1, 1])),
        "bip": dict(zip(m._KW42_REIHE, [1, 2, 0, 2, 0, -1, 0, 1])),
        "handel": dict(zip(m._KW42_REIHE, [2, 1, -1, 2, -1, 1, -1, -2])),
        "politik": dict(zip(m._KW42_REIHE, [1, 1, 1, 2, 1, 1, 1, -1])),
        "dxy": dict(zip(m._KW42_REIHE, [-1, -1, -1, -1, -1, -2, -1, 2])),
        "immo": dict(zip(m._KW42_REIHE, [1, 0, -1, 1, -2, -1, -1, 0])),
        "technik": dict(zip(m._KW42_REIHE, [-2, -2, -2, -2, 1, -2, 1, 2])),
    }, "ueberschreiben": {}}
    g = m.gesamt(auto, ein)
    assert g["gesamt"] == {"6J": -3, "6E": 3, "6B": 3, "6S": -1, "6A": 11, "6C": -9, "6N": 5, "DX": 7}
    assert g["fundamental"]["6A"] == 10 and g["fundamental"]["6C"] == -7
    assert [g["bias"][k] for k in ("6A", "6C", "6N", "DX", "6J")] == ["Stark Bullish", "Bearish", "Bullish", "Bullish", "Neutral"]
    assert g["fehlend"] == []
    # seine Trade-Ideen aus KW 42: AUD/CAD Δ20, USD/CAD Δ16, dann NZD/CAD und AUD/JPY mit Δ14
    assert [(x["delta"], x["long"], x["short"]) for x in g["ideen"]][:2] == [(20, "6A", "6C"), (16, "DX", "6C")]


def test_ueberschreiben_gewinnt_und_fehlende_manuelle_zaehlen_null(tmp_path):
    datei = tmp_path / "e.md"
    datei.write_text("""**Stand der Eingaben: 2026-10-09**

## Manuelle Faktoren
| Faktor | JPY | EUR | GBP | CHF | AUD | CAD | NZD | DXY |
|---|---|---|---|---|---|---|---|---|
| Technik | -2 | -2 | | -2 | 1 | -2 | 1 | +2 |
| Zentralbank-Bias | 0 | 0 | 1 | -1 | 2 | -1 | 1 | 1 |

## Überschreiben (leer = automatisch)
| Faktor | JPY | EUR | GBP | CHF | AUD | CAD | NZD | DXY |
|---|---|---|---|---|---|---|---|---|
| Arbeitsmarkt | | | | | | -2 | | |
""", encoding="utf-8")
    e = m.lese_eingaben(datei)
    assert e["stand"] == "2026-10-09" and e["vorhanden"]
    assert e["manuell"]["technik"]["DX"] == 2 and "6B" not in e["manuell"]["technik"]
    assert e["ueberschreiben"] == {"arbeit": {"6C": -2.0}}
    auto = {"punkte": {f: {k: 0 for k in m.REIHE} for f in m.AUTOMATISCH}}
    g = m.gesamt(auto, e)
    zeile = next(z for z in g["zeilen"] if z["key"] == "arbeit")
    assert zeile["punkte"]["6C"] == -2 and zeile["herkunft"]["6C"] == "ueberschrieben" and zeile["herkunft"]["6J"] == "automatisch"
    assert ("Technik (dein Bias)", "6B") in g["fehlend"]


def test_fehlende_datei_gibt_nur_nullen(tmp_path):
    e = m.lese_eingaben(tmp_path / "gibt es nicht.md")
    assert e["vorhanden"] is False and e["manuell"] == {}


def test_eingabedatei_im_vault_ist_lesbar():
    e = m.lese_eingaben()
    if not e["vorhanden"]:
        pytest.skip("Vault nicht erreichbar")
    assert e["stand"] is not None
    assert set(e["manuell"]) == set(m.MANUELL)
    assert all(len(v) == 8 for v in e["manuell"].values())


def test_veraenderung_ueber_wochen_und_luecken():
    import pandas as pd
    tage = pd.date_range("2026-08-04", periods=10, freq="7D")
    r = pd.DataFrame({"datum": tage, "net": [100, 110, 90, 120, 130, 125, 140, 150, 145, 160]})
    assert m.veraenderung(r, 1) == 15 and m.veraenderung(r, 4) == 160 - 125 and m.veraenderung(r, 8) == 160 - 110
    assert m.veraenderung(r, 10) is None                                       # zu wenige Berichte
    luecke = r.drop(index=[6, 7, 8]).reset_index(drop=True)                     # drei Wochen fehlen
    assert m.veraenderung(luecke, 4) is None


def test_cot_mit_vier_wochen_gegen_fynns_kw42():
    """Mit dem 4-Wochen-Trend (Stand 06.10.2026) stimmen 7 von 8 Währungen mit Fynns KW-42-Bewertung überein, nur DXY weicht ab."""
    import pandas as pd
    import kennzahlen as kz
    l = pd.read_csv(m.config_daten("cot_legacy.csv"), parse_dates=["datum"])
    t = pd.read_csv(m.config_daten("cot_tff.csv"), parse_dates=["datum"])
    k = kz.kennzahlen(l, t)
    abweichend = []
    for mk in m.REIHE:
        reihe = k[(k.markt == mk) & (k.gruppe == "comm") & (k.datum <= "2026-10-06")].sort_values("datum")
        if m.punkte_cot(reihe.iloc[-1]["idx52"], m.veraenderung(reihe, m.COT_WOCHEN)) != m.KW42_FYNN["cot"][mk]:
            abweichend.append(mk)
    assert m.COT_WOCHEN == 4 and abweichend == ["DX"]
