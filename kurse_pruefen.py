r"""Prüft die gespeicherten Kurse (daten/kurse_tag.csv): Zeitraum, Lücken, größte Tagesbewegungen, Vergleich mit den Futures.

Start:  .venv/Scripts/python.exe kurse_pruefen.py
"""
import sys
import warnings

import numpy as np
import pandas as pd

import config
import kurse


def main():
    d = kurse.lade()
    heute = pd.Timestamp.now().normalize()
    print(f"Kurse aus {kurse.PFAD.name}, letzter Tag in der Datei: {d.index.max().date()}\n")
    print("1) Zeitraum, Lücken, letzter Kurs")
    print(f"{'Markt':6s}{'von':>12s}{'bis':>12s}{'Tage':>7s}{'größte Lücke':>14s}{'Alter':>7s}{'letzter Kurs':>14s}")
    for m in d:
        s = d[m].dropna()
        luecke = s.index.to_series().diff().dt.days.max()
        print(f"{m:6s}{str(s.index[0].date()):>12s}{str(s.index[-1].date()):>12s}{len(s):>7d}{int(luecke):>11d} T{(heute - s.index[-1]).days:>5d} T{s.iloc[-1]:>14.5g}")

    print("\n2) Die 3 größten Tagesbewegungen je Markt (log-Prozent, sollten echte Ereignisse sein)")
    for m in d:
        r = np.log(d[m].dropna()).diff().dropna()
        top = r.abs().nlargest(3).index
        print(f"{m}: " + ", ".join(f"{t.date()} {r[t] * 100:+.1f} %" for t in top))

    print("\n3) Vergleich mit den Yahoo-Futures (Wochenrenditen der letzten 5 Jahre; Kassakurs und Future sollten fast gleich laufen)")
    import yfinance as yf
    warnings.filterwarnings("ignore")
    for m, c in config.MAERKTE.items():
        if c["fred"] is None:
            print(f"{m}: Index DX-Y.NYB, kein Vergleich nötig (Yahoo-Index ist die Quelle)")
            continue
        f = yf.download(c["yahoo"], period="5y", interval="1d", progress=False, auto_adjust=False)["Close"].squeeze().dropna()
        f.index = pd.to_datetime(f.index).tz_localize(None).normalize()
        a = pd.concat([d[m].dropna(), f], axis=1, join="inner").dropna()
        a.columns = ["kasse", "future"]
        w = np.log(a.resample("W-FRI").last()).diff().dropna()
        print(f"{m}: Korrelation {w['kasse'].corr(w['future']):.3f} über {len(w)} Wochen")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
