"""Etappe 7a: "Dein Modell". Fynns 12-Faktoren-Scoring (siehe Vault: Multi-Faktor-Scoring-Modell) als Ansicht, NICHT durch Tests belegt.

Dieses Modul rechnet nur die Faktoren, die sich aus den Dashboard-Daten ableiten lassen (Regeln unten, aus Fynns Tabellen abgeleitet).
Die übrigen Faktoren (Zentralbank-Bias, BIP, Handelsbilanz, Politik, DXY-Stärke, Immobilien, Technik) kommen später aus einer Eingabedatei.
Die geprüfte Gesamtbewertung (punktesystem.py) bleibt davon völlig getrennt.

Faktor-Skalen (Punkte vor Gewicht): Zinsdifferenz -2..+2 (Gewicht 2), alle anderen -2..+2 (Gewicht 1).
"""
import pandas as pd

import config

# Gewicht je Faktor und ob er automatisch gerechnet werden kann
FAKTOREN = [
    ("zb", "Zentralbank-Bias", 2, False),
    ("zins", "Zinsdifferenz", 2, True),
    ("cot", "COT Commercials", 1, True),
    ("inflation", "Inflation / CPI", 1, True),
    ("arbeit", "Arbeitsmarkt", 1, True),
    ("bip", "BIP / Wachstum", 1, False),
    ("saison", "Saisonalität", 1, True),
    ("handel", "Handelsbilanz", 1, False),
    ("politik", "Politische Stabilität", 1, False),
    ("dxy", "DXY-Stärke", 1, False),
    ("immo", "Immobilien / Kredit", 1, False),
    ("technik", "Technik (dein Bias)", 1, False),
]

BIAS = [(10, "Stark Bullish"), (5, "Bullish"), (-4, "Neutral"), (-9, "Bearish")]   # ab Schwelle aufwärts, darunter Stark Bearish


def bias(score):
    for schwelle, name in BIAS:
        if score >= schwelle:
            return name
    return "Stark Bearish"


def punkte_zins(leitzinsen):
    """Rang der Leitzinsen (1 = höchster) -> Punkte vor Gewicht. Rang 1 und 2: +2, 3: +1, 4 und 5: 0, 6: -1, 7 und 8: -2.
    Mit dieser Regel entsteht Fynns KW-42-Spalte exakt. leitzinsen: {Markt: Zins in %}. Fehlt ein Wert: 0."""
    s = pd.Series(leitzinsen, dtype=float).dropna().sort_values(ascending=False)
    tabelle = [2, 2, 1, 0, 0, -1, -2, -2]
    aus = {m: 0 for m in leitzinsen}
    if len(s) != 8:
        return aus
    for rang, m in enumerate(s.index):
        aus[m] = tabelle[rang]
    return aus


COT_WOCHEN = 4      # Trend der Commercials: Veränderung über 4 Wochen (5 Wochenberichte), so von Fynn am 17.10.2026 festgelegt (vorher 1 Woche)


def veraenderung(reihe, wochen):
    """Veränderung der Netto-Position über `wochen` Wochenberichte. reihe = nach Datum sortierte Zeilen mit "datum" und "net".
    None, wenn es zu wenige Berichte gibt oder eine Lücke dazwischen liegt (Abstand mehr als 10 Tage über der Sollzeit)."""
    if len(reihe) <= wochen:
        return None
    jetzt, frueher = reihe.iloc[-1], reihe.iloc[-1 - wochen]
    tage = (jetzt["datum"] - frueher["datum"]).days
    if tage > 7 * wochen + 10 or pd.isna(jetzt["net"]) or pd.isna(frueher["net"]):
        return None
    return float(jetzt["net"] - frueher["net"])


def punkte_cot(idx, d_net):
    """Commercials: Index (52 Wochen) und Veränderung der Netto-Position über COT_WOCHEN Wochen (Trend).
    Ab 80 gleich +2. Ab 50: steigend +2, sonst +1. 20 bis 50: steigend +1, sonst 0. Unter 20: steigend 0, sonst -1."""
    if idx is None or pd.isna(idx):
        return 0
    steigt = d_net is not None and not pd.isna(d_net) and d_net > 0
    if idx >= 80:
        return 2
    if idx >= 50:
        return 2 if steigt else 1
    if idx > 20:
        return 1 if steigt else 0
    return 0 if steigt else -1


def punkte_inflation(abstand_ziel):
    """Abstand der Inflationsrate zum Ziel der Notenbank in Prozentpunkten. Hoher Preisdruck gleich positiv (Zinserhöhungen wahrscheinlicher)."""
    if abstand_ziel is None or pd.isna(abstand_ziel):
        return 0
    a = abstand_ziel
    return 2 if a >= 1.5 else 1 if a >= 0.75 else 0 if a > -0.75 else -1 if a > -1.5 else -2


def punkte_arbeit(veraenderung_6m):
    """Veränderung der Arbeitslosenquote in 6 Monaten (Prozentpunkte). Sinkende Quote gleich positiv."""
    v = veraenderung_6m
    if v is None or pd.isna(v):
        return 0
    return 2 if v <= -0.6 else 1 if v <= -0.3 else 0 if v < 0.3 else -1 if v < 0.6 else -2


def punkte_saison(winrate, sharpe):
    """Fynns Skala (Vault: Scoring-Methodik Saisonalität). Winrate und Sharpe müssen gemeinsam in dieselbe Richtung zeigen, sonst 0."""
    if winrate is None or sharpe is None or pd.isna(winrate) or pd.isna(sharpe):
        return 0
    if winrate >= 60 and sharpe >= 1.0:
        return 2
    if winrate >= 55 and sharpe >= 0.5:
        return 1
    if winrate <= 40 and sharpe <= -1.0:
        return -2
    if winrate <= 50 and sharpe <= -0.5:
        return -1
    return 0


# Fynns eigene Bewertung KW 42 (Chat "COT Analyse", Daten bis 09.10.2026), Reihenfolge JPY EUR GBP CHF AUD CAD NZD USD.
_KW42_REIHE = ["6J", "6E", "6B", "6S", "6A", "6C", "6N", "DX"]
KW42_FYNN = {
    "zins": [-2, 0, 1, -2, 2, -1, 0, 2],          # in der Tabelle mit Gewicht 2 gezeigt (-4 bis +4), hier vor Gewicht
    "cot": [0, 2, 2, 0, 2, 2, 2, -1],
    "inflation": [0, 2, 2, 1, 2, 0, 2, 1],
    "arbeit": [1, 0, -1, 1, -1, -2, 0, -1],
    "saison": [-2, -2, 0, -1, 2, -1, 0, 0],
}
KW42_FYNN = {f: dict(zip(_KW42_REIHE, w)) for f, w in KW42_FYNN.items()}


def de(x, stellen=0, vorzeichen=False):
    """Zahl im deutschen Format (Komma als Dezimaltrenner, Punkt als Tausendertrenner)."""
    if x is None or pd.isna(x):
        return "–"
    t = f"{abs(x):,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" if x > 0 and vorzeichen else "−" if x < 0 else "") + t


def lade_daten():
    """Alle gespeicherten Daten, die die automatischen Faktoren brauchen."""
    import kennzahlen as kz
    import kurse as kurse_modul
    import makro
    import zinsen
    legacy = pd.read_csv(config_daten("cot_legacy.csv"), parse_dates=["datum"])
    tff = pd.read_csv(config_daten("cot_tff.csv"), parse_dates=["datum"])
    return {"k": kz.kennzahlen(legacy, tff), "zinsen": zinsen.lade(), "makro": makro.lade(), "kurse": kurse_modul.lade()}


def config_daten(name):
    from pathlib import Path
    return Path(__file__).parent / "daten" / name


def automatik(heute, daten=None, saison_start=None, saison_tage=21, jahre=15):
    """Rechnet die 5 automatischen Faktoren für alle 8 Währungen.

    Rückgabe: {"punkte": {faktor: {markt: Punkte vor Gewicht}}, "lesung": {faktor: {markt: kurzer Text}}, "saison_fenster": (start, ende)}.
    Die Saisonalität gilt für ein frei wählbares Fenster: saison_start (Standard: heute) und saison_tage (Standard: 21 Tage = 3 Wochen)."""
    import makro
    import saisonalitaet
    import zinsen
    heute = pd.Timestamp(heute).normalize()
    d = daten or lade_daten()
    start = pd.Timestamp(saison_start).normalize() if saison_start is not None else heute
    ende = start + pd.Timedelta(days=saison_tage)
    bis_jahr = heute.year - 1
    punkte = {f: {} for f in ("zins", "cot", "inflation", "arbeit", "saison")}
    lesung = {f: {} for f in punkte}

    leitzins = {}
    for m, cfg in config.MAERKTE.items():
        land = "US" if m == "DX" else cfg["bis"]
        leitzins[m] = float(d["zinsen"][land].dropna().iloc[-1])
    punkte["zins"] = punkte_zins(leitzins)
    for m in leitzins:
        lesung["zins"][m] = f"{leitzins[m]:.2f} %".replace(".", ",")

    for m, cfg in config.MAERKTE.items():
        reihe = d["k"][(d["k"].markt == m) & (d["k"].gruppe == "comm")].sort_values("datum")
        c = reihe.iloc[-1]
        d4 = veraenderung(reihe, COT_WOCHEN)
        punkte["cot"][m] = punkte_cot(c["idx52"], d4)
        lesung["cot"][m] = f"Index {c['idx52']:.0f}, Netto {de(c['net'], 0, True)}, Δ1W {de(c['d_net'], 0, True)}, Δ{COT_WOCHEN}W {de(d4, 0, True)}"

        mk = makro.kennzahlen(d["makro"], cfg["bis"], heute=heute, leitzins=leitzins[m])
        punkte["inflation"][m] = punkte_inflation(mk.get("inflation_abstand_ziel"))
        lesung["inflation"][m] = f"{de(mk.get('inflation'), 2)} % (Ziel {de(mk['ziel'], 1)})"
        punkte["arbeit"][m] = punkte_arbeit(mk.get("arbeitslos_veraenderung"))
        lesung["arbeit"][m] = f"{de(mk.get('arbeitslos'), 1)} %, Δ6M {de(mk.get('arbeitslos_veraenderung'), 1, True)}"

        z = saisonalitaet.zeitraum(d["kurse"][m], (start.month, start.day), (ende.month, ende.day), jahre, bis_jahr)
        punkte["saison"][m] = punkte_saison(z["winrate"], z["sharpe"])
        lesung["saison"][m] = "–" if z["winrate"] is None or z["sharpe"] is None else f"{z['winrate']:.0f} % / {de(z['sharpe'], 2, True)}"
    return {"punkte": punkte, "lesung": lesung, "saison_fenster": (start.strftime("%Y-%m-%d"), ende.strftime("%Y-%m-%d"))}


def abgleich_kw42(heute="2026-10-12", daten=None, **kw):
    """Vergleicht die automatischen Punkte mit Fynns KW-42-Bewertung. Gibt {faktor: [(markt, fynn, auto, lesung)]} und die Trefferzahl zurück."""
    a = automatik(heute, daten, **kw)
    aus, treffer, gesamt = {}, {}, {}
    for f, ref in KW42_FYNN.items():
        zeilen = [(m, ref[m], a["punkte"][f][m], a["lesung"][f][m]) for m in _KW42_REIHE]
        aus[f] = zeilen
        treffer[f] = sum(1 for _, x, y, _ in zeilen if x == y)
    return aus, treffer


# ---------------------------------------------------------------------------------------------------------------
# Etappe 7b: Eingabedatei, Gesamtscore, Trade-Ideen

import re
from pathlib import Path

VAULT = Path(r"C:\Users\fynnl\OneDrive\Dokumente\Obsidian Claude Fynn\Zweites Gehirn")
EINGABEN = VAULT / "04 Ressourcen" / "Trading & Charttechnik" / "COT-Analyse" / "Scoring-Eingaben.md"
WAEHRUNG = {"DXY": "DX", "USD": "DX", "EUR": "6E", "GBP": "6B", "JPY": "6J", "CHF": "6S", "AUD": "6A", "NZD": "6N", "CAD": "6C"}
ANZEIGE = {"DX": "DXY", "6E": "EUR", "6B": "GBP", "6J": "JPY", "6S": "CHF", "6A": "AUD", "6N": "NZD", "6C": "CAD"}
REIHE = ["6J", "6E", "6B", "6S", "6A", "6C", "6N", "DX"]            # wie in Fynns Notion-Tabelle
FAKTORNAME = {name.lower(): key for key, name, _, _ in FAKTOREN}
FAKTORNAME.update({"zinsdifferenz": "zins", "cot": "cot", "cot commercials": "cot", "inflation": "inflation", "arbeitsmarkt": "arbeit",
                   "technik": "technik", "saisonalität": "saison", "saisonalitaet": "saison", "dxy-stärke": "dxy", "dxy-staerke": "dxy"})
AUTOMATISCH = ["zins", "cot", "inflation", "arbeit", "saison"]
MANUELL = [key for key, _, _, auto in FAKTOREN if not auto]
GEWICHT = {key: g for key, _, g, _ in FAKTOREN}
NAME = {key: n for key, n, _, _ in FAKTOREN}
ALTER_WARNUNG_TAGE = 10


def _zahl(text):
    t = text.strip().replace("−", "-").replace(",", ".").replace("+", "")
    if t in ("", "-", "–"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def lese_eingaben(pfad=None):
    """Liest die Eingabedatei (Markdown-Tabellen). Gibt {"manuell": {faktor: {markt: Punkte}}, "ueberschreiben": {...}, "stand": Datum oder None} zurück.
    Leere Felder bleiben ungesetzt. Punkte vor Gewicht, -2 bis +2."""
    pfad = Path(pfad) if pfad else EINGABEN
    aus = {"manuell": {}, "ueberschreiben": {}, "stand": None, "vorhanden": pfad.exists()}
    if not pfad.exists():
        return aus
    text = pfad.read_text(encoding="utf-8")
    m = re.search(r"Stand der Eingaben:\s*(\d{4}-\d{2}-\d{2})", text)
    aus["stand"] = m.group(1) if m else None
    abschnitt, spalten = None, []
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            abschnitt = "ueberschreiben" if "berschreiben" in zeile else "manuell" if "anuell" in zeile else None
            spalten = []
            continue
        if abschnitt is None or not zeile.strip().startswith("|"):
            continue
        zellen = [z.strip() for z in zeile.strip().strip("|").split("|")]
        if zellen and set("".join(zellen)) <= set("-: "):
            continue
        if not spalten:
            spalten = [WAEHRUNG.get(z.upper()) for z in zellen[1:]]
            continue
        faktor = FAKTORNAME.get(zellen[0].lower().strip("* "))
        if faktor is None:
            continue
        for markt, z in zip(spalten, zellen[1:]):
            wert = _zahl(z)
            if markt is not None and wert is not None:
                aus[abschnitt].setdefault(faktor, {})[markt] = max(-2.0, min(2.0, wert))
    return aus


def gesamt(auto, eingaben):
    """Der volle Score je Währung. auto = Ergebnis von automatik(), eingaben = Ergebnis von lese_eingaben().
    Rückgabe: Zeilen je Faktor (Punkte mit Gewicht, Herkunft), Zwischensumme der 11 fundamentalen Faktoren, Technik, Gesamt, Bias, Trade-Ideen."""
    zeilen, fehlend = [], []
    summe_fund = {m: 0.0 for m in REIHE}
    technik = {}
    for key, name, gewicht, auto_faktor in FAKTOREN:
        punkte, herkunft = {}, {}
        for m in REIHE:
            ue = eingaben["ueberschreiben"].get(key, {}).get(m)
            if auto_faktor:
                if ue is not None:
                    p, h = ue, "ueberschrieben"
                else:
                    p, h = auto["punkte"][key][m], "automatisch"
            else:
                p = eingaben["manuell"].get(key, {}).get(m)
                h = "manuell"
                if p is None:
                    p, h = 0, "fehlt"
                    fehlend.append((name, m))
            punkte[m] = p * gewicht
            herkunft[m] = h
            if key == "technik":
                technik[m] = punkte[m]
            else:
                summe_fund[m] += punkte[m]
        zeilen.append({"key": key, "name": name, "gewicht": gewicht, "punkte": punkte, "herkunft": herkunft})
    gesamt_m = {m: summe_fund[m] + technik[m] for m in REIHE}
    ideen = sorted(((gesamt_m[a] - gesamt_m[b], a, b) for a in REIHE for b in REIHE if a != b), key=lambda x: (-x[0], REIHE.index(x[1]), REIHE.index(x[2])))[:3]
    return {"zeilen": zeilen, "fundamental": summe_fund, "technik": technik, "gesamt": gesamt_m,
            "bias": {m: bias(gesamt_m[m]) for m in REIHE}, "ideen": [{"delta": d, "long": a, "short": b} for d, a, b in ideen], "fehlend": fehlend}
