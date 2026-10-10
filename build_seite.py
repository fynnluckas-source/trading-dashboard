"""Baut die Webseite docs/index.html aus den gespeicherten COT-Daten (plus Kursen von Yahoo für den Chart).

Start:  .venv/Scripts/python.exe build_seite.py          (baut docs/index.html)
        .venv/Scripts/python.exe build_seite.py --auf    (baut und öffnet im Browser)
"""
import argparse
import json
import sys
import warnings
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import check_quellen
import config
import kennzahlen as kz

HIER = Path(__file__).parent
DOCS = HIER / "docs"


def kurse(markt):
    """Tageskurse von Yahoo (nur für die Chart-Anzeige). Gibt None zurück, wenn es nicht klappt."""
    try:
        import yfinance as yf
        warnings.filterwarnings("ignore")
        d = yf.download(config.MAERKTE[markt]["yahoo"], start="2000-01-01", interval="1d",
                        progress=False, auto_adjust=False)
        s = d["Close"].squeeze().dropna()
        if s.empty:
            return None
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        med = s.rolling(21, center=True, min_periods=5).median()
        s = s[(s / med).between(0.5, 2.0)]  # grobe Ausreißer (z. B. Faktor 10) entfernen
        return s
    except Exception:
        return None


def ampel(alter):
    gruen, gelb = config.FRISCHE["COT"]
    return "gruen" if alter <= gruen else "gelb" if alter <= gelb else "rot"


def zahl(x, ndigits=None):
    if pd.isna(x):
        return None
    return round(float(x), ndigits) if ndigits is not None else float(x)


def baue(quellen=None):
    legacy = pd.read_csv(HIER / "daten" / "cot_legacy.csv", parse_dates=["datum"])
    tff = pd.read_csv(HIER / "daten" / "cot_tff.csv", parse_dates=["datum"])
    k = kz.kennzahlen(legacy, tff)
    stand = legacy["datum"].max()
    alter = (pd.Timestamp(datetime.now(timezone.utc).date()) - stand).days

    maerkte = list(config.MAERKTE)
    latest, serie, kurs_fehler = {}, {}, []
    for m in maerkte:
        gruppen = {}
        for g in kz.GRUPPEN:
            z = k[(k.markt == m) & (k.gruppe == g)].iloc[-1]
            gruppen[g] = {"net": zahl(z.net), "net_pct": zahl(z.net_pct, 1), "d_net": zahl(z.d_net),
                          **{f"idx{w}": zahl(z[f"idx{w}"], 1) for w in kz.FENSTER}}
        latest[m] = {"name": config.MAERKTE[m]["name"], "gruppen": gruppen}

        datum = sorted(legacy.loc[legacy.markt == m, "datum"])
        idx = pd.DatetimeIndex(datum)
        s = {"datum": [d.strftime("%Y-%m-%d") for d in idx]}
        for g in kz.GRUPPEN:
            ser = k[(k.markt == m) & (k.gruppe == g)].set_index("datum")["net"].reindex(idx)
            s[g] = [zahl(v) for v in ser]
        kurs = kurse(m)
        if kurs is None:
            kurs_fehler.append(m)
            s["kurs"] = [None] * len(idx)
        else:
            kurs = kurs.reindex(kurs.index.union(idx)).ffill().reindex(idx)  # Kurs am Stichtag, sonst letzter Handelstag
            s["kurs"] = [zahl(v, 6) for v in kurs]
        serie[m] = s

    if quellen is None:
        try:
            quellen = check_quellen.alle()
        except Exception as e:
            print(f"::warning::Quellenprüfung fehlgeschlagen: {e}")
            quellen = []
    jetzt = datetime.now(timezone.utc)
    daten = {
        "gebaut_iso": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "quellen": quellen,
        "stand": stand.strftime("%Y-%m-%d"), "alter": int(alter), "ampel": ampel(alter),
        "gebaut": datetime.now().strftime("%d.%m.%Y %H:%M"), "maerkte": maerkte,
        "gruppen": {g: {"name": v[2], "text": v[3], "bericht": v[0]} for g, v in kz.GRUPPEN.items()},
        "latest": latest, "serie": serie, "kurs_fehler": kurs_fehler,
    }
    html = (HIER / "seite_vorlage.html").read_text(encoding="utf-8").replace("__DATEN__", json.dumps(daten, ensure_ascii=False))
    DOCS.mkdir(exist_ok=True)
    ziel = DOCS / "index.html"
    ziel.write_text(html, encoding="utf-8")
    return ziel, daten


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--auf", action="store_true", help="danach im Browser öffnen")
    args = p.parse_args()
    ziel, d = baue()
    print(f"Seite gebaut: {ziel} ({ziel.stat().st_size / 1e6:.1f} MB)")
    print(f"COT-Stand {d['stand']} (Alter {d['alter']} Tage, Ampel {d['ampel']}), Kurse fehlen für: {d['kurs_fehler'] or 'keinen Markt'}")
    if args.auf:
        webbrowser.open(ziel.as_uri())
