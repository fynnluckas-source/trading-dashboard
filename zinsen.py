r"""Zinsen (Etappe 3a): Leitzinsen der 8 Länder (BIS) und US-Rendite 2 Jahre (FRED), Zinsabstand und Zinsrichtung je Markt.

Zinsabstand = Leitzins der Währung minus US-Leitzins (in Prozentpunkten). Ein höherer Abstand heißt: Die Währung bringt mehr Zins als der Dollar.
Beim DX gilt das Gegenteil, dort ist der Abstand US-Leitzins minus gewichteter Durchschnitt der Korb-Länder (Euro, Yen, Pfund, Kanada-Dollar, Franken).
Die Leitzinsen gelten ab dem Tag der BIS-Meldung und werden bis zum nächsten Eintrag fortgeschrieben (ein Leitzins bleibt, bis er geändert wird).

Start:  .venv/Scripts/python.exe zinsen.py          (lädt neu, speichert und zeigt die Kennzahlen)
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config

DATEN = Path(__file__).parent / "daten"
PFAD = DATEN / "zinsen.csv"
LAENDER = ["US", "XM", "GB", "JP", "CH", "AU", "NZ", "CA"]
KORB = {"XM": 57.6, "JP": 13.6, "GB": 11.9, "CA": 9.1, "CH": 3.6}      # Gewichte des Dollar-Index ohne Schweden (nicht in unserer Liste)
START = "1999-01-01"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D." + "+".join(LAENDER)
ZUSCHLAG_TAGE = 120      # beim täglichen Update die letzten 120 Tage neu laden (Korrekturen der BIS)


def lade_bis(start=START):
    r = requests.get(BIS_URL, params={"startPeriod": start, "format": "csv"}, timeout=300)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])
    d["TIME_PERIOD"] = pd.to_datetime(d["TIME_PERIOD"])
    w = d.pivot(index="TIME_PERIOD", columns="REF_AREA", values="OBS_VALUE").sort_index()
    fehlt = [c for c in LAENDER if c not in w.columns]
    if fehlt:
        raise RuntimeError(f"BIS: Länder fehlen (Format geändert?): {fehlt}")
    return w[LAENDER]


def lade_us2y(start=START):
    t = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2", timeout=90)
    t.raise_for_status()
    d = pd.read_csv(io.StringIO(t.text))
    s = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(d.iloc[:, 0])
    s = s.dropna()
    return s[s.index >= start].rename("US2Y")


def fortschreiben(roh):
    """Leitzinsen gelten bis zur nächsten Meldung weiter: je Land bis zum letzten Beobachtungstag nach vorn auffüllen (nicht darüber hinaus)."""
    tage = pd.date_range(roh.index.min(), roh.index.max(), freq="D")
    aus = roh.reindex(tage)
    for c in aus.columns:
        letzte = aus[c].last_valid_index()
        if letzte is None:
            continue
        aus.loc[:letzte, c] = aus.loc[:letzte, c].ffill()
        aus.loc[aus.index > letzte, c] = np.nan
    return aus


def pruefe(df):
    """Plausibilität: Zinsen zwischen -2 und 30 Prozent, jedes Land mit aktuellem Wert."""
    for c in LAENDER:
        s = df[c].dropna()
        if s.empty:
            raise RuntimeError(f"Zinsen: keine Daten für {c}")
        if (s < -2).any() or (s > 30).any():
            raise RuntimeError(f"Zinsen: unplausible Werte bei {c}")


def lade(neu=False):
    """Tägliche Zinstabelle (Länder und US2Y). Beim Update werden nur die letzten Monate neu geholt und eingefügt."""
    if PFAD.exists() and not neu:
        return pd.read_csv(PFAD, index_col=0, parse_dates=True)
    if PFAD.exists():
        alt = pd.read_csv(PFAD, index_col=0, parse_dates=True)
        ab = (alt.index.max() - pd.Timedelta(days=ZUSCHLAG_TAGE)).strftime("%Y-%m-%d")
        neu_bis = lade_bis(ab)
        roh = pd.concat([alt[LAENDER][alt.index < neu_bis.index.min()].dropna(how="all"), neu_bis]).sort_index()
        roh = roh[~roh.index.duplicated(keep="last")]
    else:
        roh = lade_bis(START)
    df = fortschreiben(roh)
    us2y = lade_us2y()
    df = df.join(us2y, how="left")
    pruefe(df)
    DATEN.mkdir(exist_ok=True)
    df.to_csv(PFAD, float_format="%.4f")
    return df


def abstand_serie(df, markt):
    """Zinsabstand je Markt (siehe oben). Gibt eine Reihe zurück, die nur dort Werte hat, wo alle beteiligten Länder Werte haben."""
    cfg = config.MAERKTE[markt]
    if markt == "DX":
        korb = sum(df[c] * w for c, w in KORB.items()) / sum(KORB.values())
        return (df["US"] - korb).dropna()
    return (df[cfg["bis"]] - df["US"]).dropna()


def aenderungen(s):
    """Zinsänderungen eines Landes: Reihe mit dem Datum der Änderung und der Größe in Prozentpunkten."""
    d = s.dropna().diff().dropna()
    return d[d.abs() > 1e-9]


def kennzahlen(df, markt):
    """Aktuelle Kennzahlen eines Marktes. Stichtag = der letzte Tag, für den alle beteiligten Länder Werte haben."""
    cfg = config.MAERKTE[markt]
    land = "US" if markt == "DX" else cfg["bis"]
    ab = abstand_serie(df, markt)
    ref = ab.index.max()
    aus = {"markt": markt, "land": land, "stichtag": ref.strftime("%Y-%m-%d"), "abstand": round(float(ab.iloc[-1]), 3),
           "leitzins": round(float(df[land].dropna().iloc[-1]), 3), "us_leitzins": round(float(df["US"].dropna().iloc[-1]), 3),
           "datenstand_land": df[land].last_valid_index().strftime("%Y-%m-%d")}
    for n in (3, 6, 12):
        frueher = ab.loc[:ref - pd.DateOffset(months=n)]
        aus[f"d_abstand_{n}m"] = round(float(ab.iloc[-1] - frueher.iloc[-1]), 3) if len(frueher) else None
    ae = aenderungen(df[land])
    if len(ae):
        aus["letzte_aenderung_datum"] = ae.index[-1].strftime("%Y-%m-%d")
        aus["letzte_aenderung_groesse"] = round(float(ae.iloc[-1]), 3)
    else:
        aus["letzte_aenderung_datum"], aus["letzte_aenderung_groesse"] = None, None
    j = ae[ae.index > ref - pd.DateOffset(months=12)]
    aus["aenderung_12m"] = round(float(j.sum()), 3)
    aus["anzahl_aenderungen_12m"] = int(len(j))
    aus["richtung_12m"] = "erhöht" if j.sum() > 0.01 else "gesenkt" if j.sum() < -0.01 else "unverändert"
    return aus


def verlauf_woechentlich(df, markt):
    """Verlauf für das Diagramm (alle 7 Tage): Leitzins der Währung (beim DX: Korb), US-Leitzins, Abstand."""
    cfg = config.MAERKTE[markt]
    ab = abstand_serie(df, markt)
    w = ab.index[::7]
    land = (sum(df[c] * wg for c, wg in KORB.items()) / sum(KORB.values())) if markt == "DX" else df[cfg["bis"]]
    return {"datum": [t.strftime("%Y-%m-%d") for t in w], "land": [round(float(land.loc[t]), 3) for t in w],
            "us": [round(float(df["US"].loc[t]), 3) for t in w], "abstand": [round(float(ab.loc[t]), 3) for t in w]}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    df = lade(neu=True)
    print(f"Zinsen gespeichert: {PFAD} ({len(df)} Tage, {df.index.min().date()} bis {df.index.max().date()}, Datei {PFAD.stat().st_size / 1e6:.1f} MB)")
    print(f"US-Rendite 2 Jahre: {df['US2Y'].dropna().iloc[-1]:.2f} % ({df['US2Y'].last_valid_index().date()})\n")
    print(f"{'Markt':6s}{'Leitzins':>9s}{'US':>7s}{'Abstand':>9s}{'Δ3M':>7s}{'Δ6M':>7s}{'Δ12M':>7s}  {'letzte Änderung':26s}{'12 Monate':>12s}  Datenstand")
    for m in config.MAERKTE:
        k = kennzahlen(df, m)
        le = f"{k['letzte_aenderung_datum']} ({k['letzte_aenderung_groesse']:+.2f})" if k["letzte_aenderung_datum"] else "–"
        print(f"{m:6s}{k['leitzins']:>9.3f}{k['us_leitzins']:>7.3f}{k['abstand']:>+9.3f}{k['d_abstand_3m']:>+7.2f}{k['d_abstand_6m']:>+7.2f}{k['d_abstand_12m']:>+7.2f}  {le:26s}"
              f"{k['richtung_12m']:>12s}  {k['datenstand_land']}")
