r"""Tageskurse der 8 Märkte, gespeichert in daten/kurse_tag.csv.

Währungen: Kassakurse der US-Notenbank (FRED, ohne Rollsprünge wie bei Futures), so gedreht, dass
"Kurs steigt" immer "Währung wird stärker gegen den US-Dollar" heißt (wie bei den Futures 6E, 6J, ...).
DX: Yahoo-Index DX-Y.NYB (ein Index, kein Future, deshalb ohne Rollsprünge).

Start:  .venv/Scripts/python.exe kurse.py          (lädt neu und speichert)
"""
import io
import sys
import warnings
from pathlib import Path

import pandas as pd
import requests

import config

DATEN = Path(__file__).parent / "daten"
PFAD = DATEN / "kurse_tag.csv"
# Reihen, die "Fremdwährung je US-Dollar" liefern, werden umgedreht (1/x)
UMDREHEN = {"DEXSZUS", "DEXJPUS", "DEXCAUS"}
START = "1999-01-01"


def fred(serie):
    t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}", timeout=90)
    t.raise_for_status()
    d = pd.read_csv(io.StringIO(t.text))
    s = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(d.iloc[:, 0])
    s = s.dropna()
    if (s <= 0).any():
        raise RuntimeError(f"FRED {serie}: Kurs kleiner oder gleich 0")
    return 1 / s if serie in UMDREHEN else s


def yahoo(symbol):
    import yfinance as yf
    warnings.filterwarnings("ignore")
    d = yf.download(symbol, start=START, interval="1d", progress=False, auto_adjust=False)
    s = d["Close"].squeeze().dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s


def ausreisser_entfernen(s, grenze=0.3):
    """Entfernt einzelne Tageswerte, die um mehr als 'grenze' (log) vom Median der Umgebung abweichen (z. B. Faktor-10-Fehler)."""
    import numpy as np
    log = np.log(s)
    med = log.rolling(11, center=True, min_periods=3).median()
    return s[(log - med).abs() < grenze]


def lade(neu=False):
    """Gibt die Tageskurse zurück (aus der Datei, oder neu geladen und gespeichert)."""
    if PFAD.exists() and not neu:
        return pd.read_csv(PFAD, index_col=0, parse_dates=True)
    reihen = {}
    for m, c in config.MAERKTE.items():
        s = yahoo(c["yahoo"]) if c["fred"] is None else fred(c["fred"])
        reihen[m] = ausreisser_entfernen(s[s.index >= START])
    df = pd.DataFrame(reihen).sort_index()
    DATEN.mkdir(exist_ok=True)
    df.to_csv(PFAD, float_format="%.6g")
    return df


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    df = lade(neu=True)
    print(f"Kurse gespeichert: {PFAD}")
    for m in df:
        s = df[m].dropna()
        print(f"{m}: {len(s)} Tage, {s.index[0].date()} bis {s.index[-1].date()}, letzter Kurs {s.iloc[-1]:.5g}")
