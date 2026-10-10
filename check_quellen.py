"""Fragt jede Datenquelle einmal an und zeigt, ob sie erreichbar und frisch ist."""
import io
import sys
import warnings
from datetime import datetime, timezone

import pandas as pd
import requests

import config

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
HEUTE = pd.Timestamp(datetime.now(timezone.utc).date())
ERGEBNISSE = []


def ampel(quelle, letztes_datum):
    gruen, gelb = config.FRISCHE[quelle]
    alter = (HEUTE - pd.Timestamp(letztes_datum)).days
    return ("OK  " if alter <= gruen else "GELB" if alter <= gelb else "ROT "), alter


def zeige(quelle, detail, status=None, alter=None):
    text = f"[{status or 'OK  '}] {quelle:11s} {detail}"
    if alter is not None:
        text += f" (Alter {alter} Tage)"
    print(text)
    ERGEBNISSE.append(status or "OK  ")


def cot():
    codes = [m["cftc"] for m in config.MAERKTE.values()]
    liste = ",".join(f"'{c}'" for c in codes)
    for art, ds in config.CFTC_DATASETS.items():
        try:
            r = requests.get(config.CFTC_URL + ds + ".json", timeout=60, params={
                "$select": "cftc_contract_market_code,max(report_date_as_yyyy_mm_dd) as letzte",
                "$where": f"cftc_contract_market_code in ({liste})",
                "$group": "cftc_contract_market_code"})
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            gefunden = len(df)
            letzte = pd.to_datetime(df["letzte"]).min()
            fehlt = set(codes) - set(df["cftc_contract_market_code"])
            status, alter = ampel("COT", letzte)
            if gefunden < len(codes):
                status = "ROT "
            zeige(f"CFTC {art}", f"{gefunden} von {len(codes)} Märkten, ältester letzter Stichtag {letzte.date()}"
                  + (f", FEHLT: {sorted(fehlt)}" if fehlt else ""), status, alter)
        except Exception as e:
            zeige(f"CFTC {art}", f"Fehler: {e}", "ROT ")


def yahoo():
    import yfinance as yf
    fehler, aeltester = [], None
    for k, m in config.MAERKTE.items():
        try:
            d = yf.download(m["yahoo"], period="10d", interval="1d", progress=False, auto_adjust=False)
            if d.empty:
                fehler.append(k)
                continue
            letzter = d.index[-1].tz_localize(None) if d.index.tz else d.index[-1]
            aeltester = letzter if aeltester is None else min(aeltester, letzter)
        except Exception:
            fehler.append(k)
    if aeltester is None:
        zeige("Yahoo", "keine Daten", "ROT ")
        return
    status, alter = ampel("Yahoo", aeltester)
    if fehler:
        status = "ROT "
    zeige("Yahoo", f"{len(config.MAERKTE) - len(fehler)} von {len(config.MAERKTE)} Märkten, ältester letzter Kurs {aeltester.date()}"
          + (f", FEHLT: {fehler}" if fehler else ""), status, alter)


def fred():
    serien = {k: m["fred"] for k, m in config.MAERKTE.items() if m["fred"]}
    aeltester, fehler = None, []
    for k, s in serien.items():
        try:
            t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}", timeout=60).text
            d = pd.read_csv(io.StringIO(t))
            d = d[pd.to_numeric(d.iloc[:, 1], errors="coerce").notna()]
            letzt = pd.Timestamp(d.iloc[-1, 0])
            aeltester = letzt if aeltester is None else min(aeltester, letzt)
        except Exception:
            fehler.append(k)
    if aeltester is None:
        zeige("FRED Kurse", "keine Daten", "ROT ")
        return
    status, alter = ampel("FRED Kurse", aeltester)
    if fehler:
        status = "ROT "
    zeige("FRED Kurse", f"{len(serien) - len(fehler)} von {len(serien)} Kassakursen, ältester letzter Wert {aeltester.date()}"
          + (f", FEHLT: {fehler}" if fehler else ""), status, alter)


def bis():
    laender = "+".join(m["bis"] for m in config.MAERKTE.values())
    try:
        r = requests.get(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{laender}",
                         params={"lastNObservations": 1, "format": "csv"}, timeout=60)
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text))
        d = d.groupby("REF_AREA")["TIME_PERIOD"].max()
        soll = {m["bis"] for m in config.MAERKTE.values()}
        letzt = pd.to_datetime(d).min()
        status, alter = ampel("BIS Zinsen", letzt)
        if soll - set(d.index):
            status = "ROT "
        zeige("BIS Zinsen", f"{len(d)} Länder, ältester letzter Wert {letzt.date()}", status, alter)
    except Exception as e:
        zeige("BIS Zinsen", f"Fehler: {e}", "ROT ")


def ezb_eurostat():
    try:
        r = requests.get("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
                         "?lastNObservations=1&format=csvdata", timeout=60)
        r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text))
        zeige("EZB", f"erreichbar, Einlagenzins {d['OBS_VALUE'].iloc[-1]} % ({d['TIME_PERIOD'].iloc[-1]})")
    except Exception as e:
        zeige("EZB", f"Fehler: {e}", "ROT ")
    try:
        r = requests.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m"
                         "?geo=EA21&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&lastTimePeriod=3", timeout=60)
        r.raise_for_status()
        j = r.json()
        zeit = {v: k for k, v in j["dimension"]["time"]["category"]["index"].items()}
        werte = {zeit[int(i)]: v for i, v in j["value"].items()}  # Zeiträume ohne Wert fehlen hier
        if not werte:
            zeige("Eurostat", "erreichbar, aber ohne Werte", "ROT ")
        else:
            letzt = max(werte)
            zeige("Eurostat", f"erreichbar, Euroraum (EA21) Arbeitslosenquote {werte[letzt]} % (letzter Wert {letzt})")
    except Exception as e:
        zeige("Eurostat", f"Fehler: {e}", "ROT ")


if __name__ == "__main__":
    print(f"Quellen-Prüfung vom {HEUTE.date()}\n")
    cot(); yahoo(); fred(); bis(); ezb_eurostat()
    rot = ERGEBNISSE.count("ROT ")
    print(f"\n{'ALLES OK' if rot == 0 and 'GELB' not in ERGEBNISSE else str(rot) + ' Quelle(n) ROT, ' + str(ERGEBNISSE.count('GELB')) + ' GELB'}")
