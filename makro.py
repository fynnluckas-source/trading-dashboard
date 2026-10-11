r"""Makrodaten (Etappe 3b): Inflation (Jahresrate in Prozent) und Arbeitslosenquote der 8 Länder aus sechs Quellen.

Quellen je Land (alle kostenlos, ohne Schlüssel):
  USA            FRED (Preisindex CPIAUCNS, nicht saisonbereinigt wie die offizielle Jahresrate, selbst gerechnet; Arbeitslosenquote UNRATE)
  Euroraum       Eurostat (HICP, NEUE Tabelle prc_hicp_minr ab 2026; Arbeitslosenquote une_rt_m)
  Großbritannien ONS, das britische Statistikamt (CPI D7G7, Arbeitslosenquote MGSX)
  Japan          IMF (Preisindex CPI, Jahresrate selbst gerechnet); Arbeitslosenquote OECD über FRED
  Schweiz        SNB, die Nationalbank (Inflation TLK); Arbeitslosenquote OECD über FRED (quartalsweise)
  Australien     OECD (Inflation, monatlich); Arbeitslosenquote OECD über FRED
  Kanada         OECD (Inflation, monatlich); Arbeitslosenquote OECD über FRED
  Neuseeland     OECD (Inflation, quartalsweise); Arbeitslosenquote OECD über FRED (quartalsweise)
Warum so viele Quellen: Die alten Sammelreihen sind still eingestellt worden (OECD-Inflation bei FRED endet 2021 bis 2025, die alte Eurostat-
Tabelle endet im Dezember 2025). Jede Reihe hat deshalb eine eigene Frischeprüfung.

Datum einer Beobachtung = Ende der Periode (Monatsende bzw. Quartalsende). Das Datum der Veröffentlichung kennen wir nicht genau, stattdessen
steht je Reihe die übliche Verzögerung (Tage nach Periodenende) in SERIEN, für spätere Prüfungen mit Sicherheitsabstand.

Start:  .venv/Scripts/python.exe makro.py          (lädt neu, speichert daten/makro.csv und zeigt die Kennzahlen)
"""
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config

DATEN = Path(__file__).parent / "daten"
PFAD = DATEN / "makro.csv"
LETZTE_FEHLER = []      # Reihen, die beim letzten Neuladen ausgefallen sind (die alte Fassung bleibt dann erhalten)
START = "1999-01-01"
UA = {"User-Agent": "Mozilla/5.0"}

# Land: BIS-Code wie überall im Projekt (XM = Euroraum). ziel = Mitte des Inflationsziels der Notenbank.
INFLATIONSZIEL = {"US": 2.0, "XM": 2.0, "GB": 2.0, "JP": 2.0, "CH": 1.0, "AU": 2.5, "NZ": 2.0, "CA": 2.0}
# übliche Verzögerung der Veröffentlichung in Tagen nach Periodenende (grobe Annahme) und Länge der Periode
SERIEN = {
    ("US", "inflation"): {"quelle": "FRED", "lag": 14, "periode": 31},
    ("US", "arbeitslos"): {"quelle": "FRED", "lag": 7, "periode": 31},
    ("XM", "inflation"): {"quelle": "Eurostat", "lag": 17, "periode": 31},
    ("XM", "arbeitslos"): {"quelle": "Eurostat", "lag": 31, "periode": 31},
    ("GB", "inflation"): {"quelle": "ONS", "lag": 17, "periode": 31},
    ("GB", "arbeitslos"): {"quelle": "ONS", "lag": 50, "periode": 31},
    ("JP", "inflation"): {"quelle": "IMF", "lag": 25, "periode": 31},
    ("JP", "arbeitslos"): {"quelle": "OECD (FRED)", "lag": 40, "periode": 31},
    ("CH", "inflation"): {"quelle": "SNB", "lag": 8, "periode": 31},
    ("CH", "arbeitslos"): {"quelle": "OECD (FRED)", "lag": 70, "periode": 92},
    ("AU", "inflation"): {"quelle": "OECD", "lag": 30, "periode": 31},
    ("AU", "arbeitslos"): {"quelle": "OECD (FRED)", "lag": 45, "periode": 31},
    ("CA", "inflation"): {"quelle": "OECD", "lag": 20, "periode": 31},
    ("CA", "arbeitslos"): {"quelle": "OECD (FRED)", "lag": 40, "periode": 31},
    ("NZ", "inflation"): {"quelle": "OECD", "lag": 25, "periode": 92},
    ("NZ", "arbeitslos"): {"quelle": "OECD (FRED)", "lag": 45, "periode": 92},
}


def monatsende(jahr, monat):
    return pd.Timestamp(year=int(jahr), month=int(monat), day=1) + pd.offsets.MonthEnd(0)


def quartalsende(jahr, quartal):
    return pd.Timestamp(year=int(jahr), month=int(quartal) * 3, day=1) + pd.offsets.MonthEnd(0)


def monate_zurueck(datum, monate):
    """Datum (Monats- oder Quartalsende) um volle Monate zurück, wieder auf das Monatsende gelegt."""
    return (pd.Timestamp(datum) - pd.DateOffset(months=monate)) + pd.offsets.MonthEnd(0)


def jahresrate(index):
    """Veränderung zum Vorjahr in Prozent aus einem Preisindex. Der Vergleichsmonat wird über das DATUM gesucht, nicht über die Zeile:
    Fehlt ein Monat (z. B. US-Preisindex im Oktober 2025 wegen des Regierungsstillstands), bleibt die Jahresrate dieses Monats leer
    und alle anderen Monate vergleichen weiter mit dem richtigen Vorjahresmonat."""
    vor = index.reindex([monate_zurueck(t, 12) for t in index.index])
    vor.index = index.index
    return ((index / vor - 1) * 100).dropna()


def _get(url, **kw):
    r = requests.get(url, timeout=120, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- Parser (jeder arbeitet nur auf Text, damit er ohne Netz getestet werden kann)
def parse_fred(text, quartal=False):
    d = pd.read_csv(io.StringIO(text))
    s = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(d.iloc[:, 0])
    s = s.dropna()
    s.index = [quartalsende(t.year, (t.month - 1) // 3 + 1) if quartal else monatsende(t.year, t.month) for t in s.index]
    return s


def parse_eurostat(text):
    import json
    j = json.loads(text)
    zeit = {v: k for k, v in j["dimension"]["time"]["category"]["index"].items()}
    s = pd.Series({monatsende(*zeit[int(i)].split("-")): v for i, v in j["value"].items()}).sort_index()
    return s


def parse_ons(text):
    monate = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
    daten = {}
    for z in text.splitlines():
        m = re.match(r'^"(\d{4}) ([A-Z]{3})","([\d.\-]+)"', z)
        if m:
            daten[monatsende(m.group(1), monate[m.group(2)])] = float(m.group(3))
    return pd.Series(daten).sort_index()


def parse_imf(text):
    wurzel = ET.fromstring(text)
    daten = {}
    for o in wurzel.iter():
        if o.tag.endswith("Obs") and "TIME_PERIOD" in o.attrib and o.attrib.get("OBS_VALUE") not in (None, ""):
            m = re.match(r"(\d{4})-M(\d{2})", o.attrib["TIME_PERIOD"])
            if m:
                daten[monatsende(m.group(1), m.group(2))] = float(o.attrib["OBS_VALUE"])
    return pd.Series(daten).sort_index()


def parse_snb(text, kennung="TLK"):
    daten = {}
    for z in text.splitlines():
        m = re.match(r'^"(\d{4})-(\d{2})";"' + kennung + r'";"([\d.\-]+)"', z)
        if m:
            daten[monatsende(m.group(1), m.group(2))] = float(m.group(3))
    return pd.Series(daten).sort_index()


def parse_oecd(text, gebiet):
    d = pd.read_csv(io.StringIO(text), low_memory=False)
    d = d[d["REF_AREA"] == gebiet]
    daten = {}
    for _, r in d.iterrows():
        t = str(r["TIME_PERIOD"])
        m = re.match(r"(\d{4})-Q(\d)", t)
        m2 = re.match(r"(\d{4})-(\d{2})$", t)
        if m:
            daten[quartalsende(m.group(1), m.group(2))] = float(r["OBS_VALUE"])
        elif m2:
            daten[monatsende(m2.group(1), m2.group(2))] = float(r["OBS_VALUE"])
    return pd.Series(daten).sort_index()


# ---------------------------------------------------------------- Laden
def fred_text(serie):
    return _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}").text


def lade_alle():
    """Lädt alle 16 Reihen. Gibt (Tabelle, Fehlerliste) zurück. Eine kaputte Reihe stoppt die anderen nicht."""
    reihen, fehler = {}, []

    def versuche(schluessel, f):
        try:
            s = f()
            s = s[s.index >= START]
            if s.empty:
                raise RuntimeError("keine Daten")
            reihen[schluessel] = s
        except Exception as e:
            fehler.append((schluessel, str(e)[:120]))

    versuche(("US", "inflation"), lambda: jahresrate(parse_fred(fred_text("CPIAUCNS"))))
    versuche(("US", "arbeitslos"), lambda: parse_fred(fred_text("UNRATE")))
    versuche(("XM", "inflation"), lambda: parse_eurostat(_get(
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A&sinceTimePeriod=1999-01").text))
    versuche(("XM", "arbeitslos"), lambda: parse_eurostat(_get(
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?geo=EA21&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&sinceTimePeriod=2000-01").text))
    versuche(("GB", "inflation"), lambda: parse_ons(_get("https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7g7/mm23", headers=UA).text))
    versuche(("GB", "arbeitslos"), lambda: parse_ons(_get("https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms", headers=UA).text))
    versuche(("JP", "inflation"), lambda: jahresrate(parse_imf(_get("https://api.imf.org/external/sdmx/2.1/data/CPI/JPN.CPI._T.IX.M?startPeriod=1998").text)))
    versuche(("CH", "inflation"), lambda: parse_snb(_get("https://data.snb.ch/api/cube/plkoprinfla/data/csv/en").text, "TLK"))
    oecd = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{g}.{f}.N.CPI.PA._T.N.GY?startPeriod=1999&dimensionAtObservation=AllDimensions&format=csvfilewithlabels")
    for land, gebiet, freq in (("AU", "AUS", "M"), ("CA", "CAN", "M"), ("NZ", "NZL", "Q")):
        versuche((land, "inflation"), lambda g=gebiet, f=freq: parse_oecd(_get(oecd.format(g=g, f=f), headers={"Accept": "application/vnd.sdmx.data+csv"}).text, g))
    for land, serie, quartal in (("JP", "LRHUTTTTJPM156S", False), ("CH", "LRHUTTTTCHQ156S", True), ("AU", "LRHUTTTTAUM156S", False),
                                 ("CA", "LRHUTTTTCAM156S", False), ("NZ", "LRHUTTTTNZQ156S", True)):
        versuche((land, "arbeitslos"), lambda s=serie, q=quartal: parse_fred(fred_text(s), quartal=q))
    teile = [pd.DataFrame({"land": k[0], "groesse": k[1], "periode": s.index, "wert": s.values}) for k, s in reihen.items()]
    tab = pd.concat(teile, ignore_index=True) if teile else pd.DataFrame(columns=["land", "groesse", "periode", "wert"])
    return tab, fehler


def pruefe(tab):
    """Plausibilität: Inflation zwischen -5 und 40 Prozent, Arbeitslosigkeit zwischen 0 und 30 Prozent."""
    for (land, groesse), g in tab.groupby(["land", "groesse"]):
        lo, hi = (-5, 40) if groesse == "inflation" else (0, 30)
        if (g["wert"] < lo).any() or (g["wert"] > hi).any():
            raise RuntimeError(f"Makro: unplausible Werte bei {land} {groesse}")


def lade(neu=False):
    """Tabelle der Makrodaten (aus der Datei, oder neu geladen). Fällt eine Reihe aus, bleibt ihre alte Fassung erhalten."""
    alt = pd.read_csv(PFAD, parse_dates=["periode"]) if PFAD.exists() else None
    if alt is not None and not neu:
        return alt
    tab, fehler = lade_alle()
    LETZTE_FEHLER[:] = fehler
    if alt is not None:
        fehlen = {k for k, _ in fehler}
        behalten = alt[[(l, g) in fehlen for l, g in zip(alt["land"], alt["groesse"])]]
        tab = pd.concat([tab, behalten], ignore_index=True)
    pruefe(tab)
    tab = tab.sort_values(["land", "groesse", "periode"]).reset_index(drop=True)
    DATEN.mkdir(exist_ok=True)
    tab.to_csv(PFAD, index=False, float_format="%.4f", date_format="%Y-%m-%d")
    if fehler:
        print("Reihen mit Fehler:", fehler)
    return tab


# ---------------------------------------------------------------- Kennzahlen
def serie(tab, land, groesse):
    g = tab[(tab["land"] == land) & (tab["groesse"] == groesse)].sort_values("periode")
    return pd.Series(g["wert"].values, index=pd.DatetimeIndex(g["periode"]))


def ampel(land, groesse, letzte, heute):
    """Frische je Reihe: normal = übliche Verzögerung plus Periodenlänge. Grün bis 7 Tage darüber, Gelb bis 30 Tage darüber, sonst Rot."""
    cfg = SERIEN[(land, groesse)]
    alter = (pd.Timestamp(heute).normalize() - letzte).days
    normal = cfg["lag"] + cfg["periode"]
    return ("gruen" if alter <= normal + 7 else "gelb" if alter <= normal + 30 else "rot"), alter


def kennzahlen(tab, land, heute=None, leitzins=None):
    """Aktuelle Kennzahlen eines Landes: Inflation, Abstand zum Ziel, Trend, Arbeitslosenquote, Veränderung, Realzins."""
    heute = pd.Timestamp.now().normalize() if heute is None else pd.Timestamp(heute).normalize()
    inf, alo = serie(tab, land, "inflation"), serie(tab, land, "arbeitslos")
    quartal_inf = SERIEN[(land, "inflation")]["periode"] > 40
    quartal_alo = SERIEN[(land, "arbeitslos")]["periode"] > 40

    def vor(reihe, monate):
        t = monate_zurueck(reihe.index[-1], monate)
        return float(reihe.loc[t]) if t in reihe.index else None
    aus = {"land": land, "ziel": INFLATIONSZIEL[land]}
    if len(inf):
        aus["inflation"] = round(float(inf.iloc[-1]), 2)
        aus["inflation_periode"] = inf.index[-1].strftime("%Y-%m-%d")
        aus["inflation_abstand_ziel"] = round(float(inf.iloc[-1] - INFLATIONSZIEL[land]), 2)
        v = vor(inf, 3)
        aus["inflation_trend"] = round(float(inf.iloc[-1] - v), 2) if v is not None else None      # Veränderung der Jahresrate zu vor 3 Monaten
        aus["inflation_ampel"], aus["inflation_alter"] = ampel(land, "inflation", inf.index[-1], heute)
        aus["inflation_quartal"] = bool(quartal_inf)
        aus["inflation_quelle"] = SERIEN[(land, "inflation")]["quelle"]
    if len(alo):
        aus["arbeitslos"] = round(float(alo.iloc[-1]), 2)
        aus["arbeitslos_periode"] = alo.index[-1].strftime("%Y-%m-%d")
        v = vor(alo, 6)
        aus["arbeitslos_veraenderung"] = round(float(alo.iloc[-1] - v), 2) if v is not None else None   # Veränderung zu vor 6 Monaten
        aus["arbeitslos_ampel"], aus["arbeitslos_alter"] = ampel(land, "arbeitslos", alo.index[-1], heute)
        aus["arbeitslos_quartal"] = bool(quartal_alo)
        aus["arbeitslos_quelle"] = SERIEN[(land, "arbeitslos")]["quelle"]
    if leitzins is not None and len(inf):
        aus["realzins"] = round(float(leitzins - inf.iloc[-1]), 3)
    return aus


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tab = lade(neu=True)
    print(f"Makro gespeichert: {PFAD} ({len(tab)} Zeilen, {PFAD.stat().st_size / 1e3:.0f} KB)\n")
    import zinsen
    z = zinsen.lade()
    print(f"{'Land':5s}{'Inflation':>10s}{'Stand':>9s}{'Ziel':>6s}{'Abst.':>7s}{'Trend':>7s}{'Arbeitslos':>11s}{'Stand':>9s}{'Δ6M':>7s}{'Realzins':>9s}  Quellen / Frische")
    for land in ["US", "XM", "GB", "JP", "CH", "AU", "NZ", "CA"]:
        k = kennzahlen(tab, land, leitzins=float(z[land].dropna().iloc[-1]))
        print(f"{land:5s}{k.get('inflation', float('nan')):>9.2f}%{k.get('inflation_periode', '')[:7]:>9s}{k['ziel']:>6.1f}{k.get('inflation_abstand_ziel', float('nan')):>+7.2f}"
              f"{(k.get('inflation_trend') if k.get('inflation_trend') is not None else float('nan')):>+7.2f}{k.get('arbeitslos', float('nan')):>10.2f}%{k.get('arbeitslos_periode', '')[:7]:>9s}"
              f"{(k.get('arbeitslos_veraenderung') if k.get('arbeitslos_veraenderung') is not None else float('nan')):>+7.2f}{k.get('realzins', float('nan')):>+9.2f}  "
              f"{k.get('inflation_quelle')} {k.get('inflation_ampel')} ({k.get('inflation_alter')} T) / {k.get('arbeitslos_quelle')} {k.get('arbeitslos_ampel')} ({k.get('arbeitslos_alter')} T)")
