"""Etappe 6: Wochenbericht als Notiz im Obsidian-Vault.

Holt (wenn möglich) die neuesten Daten von GitHub, liest die gespeicherten Daten und schreibt eine Markdown-Notiz:
  03 Bereiche/Finanzen & Wirtschaft/Trading Wochenberichte/Trading Wochenbericht JJJJ-MM-TT.md

Die Notiz ist nur eine Zusammenfassung der Seite (Termine, COT, Zinsen, Inflation, Status der Prüfungen), kein Signal.
Eine bestehende Notiz wird nie überschrieben (läuft der Bericht am selben Tag nochmal, passiert nichts).

Start:  .venv/Scripts/python.exe wochenbericht.py            (schreibt in den Vault)
        .venv/Scripts/python.exe wochenbericht.py --vault "Pfad"   (anderer Vault-Ordner, zum Testen)
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
import kalender
import kennzahlen as kz
import makro
import modell
import punktesystem
import vorwaerts_realzins
import zinsen

HIER = Path(__file__).parent
VAULT = Path(r"C:\Users\fynnl\OneDrive\Dokumente\Obsidian Claude Fynn\Zweites Gehirn")
ORDNER = Path("03 Bereiche") / "Finanzen & Wirtschaft" / "Trading Wochenberichte"
SEITE = "https://fynnluckas-source.github.io/trading-dashboard/"

NAMEN = {"DX": "DXY", "6E": "EUR", "6B": "GBP", "6J": "JPY", "6S": "CHF", "6A": "AUD", "6N": "NZD", "6C": "CAD"}
WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
TYP = {"zins": "Zinsentscheid", "inflation": "Inflation", "arbeit": "Arbeitsmarkt"}
STATUS = {"nicht_bestanden": "nicht bestanden", "hinweis": "Hinweis (Beobachtung)", "bestaetigt": "bestätigt"}


def datum(s):
    return pd.Timestamp(s).strftime("%d.%m.%Y")


def vz(x, d=0):
    if x is None or pd.isna(x):
        return "–"
    t = f"{abs(x):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" if x > 0 else "−" if x < 0 else "") + t


def prozent(x, d=2):
    return "–" if x is None or pd.isna(x) else f"{x:.{d}f}".replace(".", ",") + " %"


def aktualisieren():
    """Neueste Daten von GitHub holen. Gibt einen Satz für die Notiz zurück. Klappt es nicht, werden die lokalen Daten benutzt."""
    try:
        r = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=HIER, capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            return "Daten von GitHub aktualisiert."
        return "Aktualisierung von GitHub nicht möglich, die Notiz nutzt die zuletzt gespeicherten Daten auf diesem PC."
    except Exception:
        return "Aktualisierung von GitHub nicht möglich (kein Internet?), die Notiz nutzt die zuletzt gespeicherten Daten auf diesem PC."


def cot_zeilen(legacy, tff):
    k = kz.kennzahlen(legacy, tff)
    zeilen, neu = [], []
    for m in config.MAERKTE:
        zelle = []
        for g in ("spec", "comm", "small"):
            s = k[(k.markt == m) & (k.gruppe == g)].sort_values("datum")
            z, v = s.iloc[-1], s.iloc[-2] if len(s) > 1 else None
            idx = z["idx52"]
            if pd.isna(idx):
                zelle.append("–")
                continue
            marke = " (hoch)" if idx >= 80 else " (tief)" if idx <= 20 else ""
            zelle.append(f"{idx:.0f}{marke}, Δ {vz(z['d_net'])}")
            if v is not None and not pd.isna(v["idx52"]):
                vorher = "hoch" if v["idx52"] >= 80 else "tief" if v["idx52"] <= 20 else "mitte"
                jetzt = "hoch" if idx >= 80 else "tief" if idx <= 20 else "mitte"
                if jetzt != vorher and jetzt != "mitte":
                    neu.append(f"{NAMEN[m]} {kz.GRUPPEN[g][2]}: neu im Bereich „{jetzt}“ (Index {idx:.0f})")
        zeilen.append(f"| {NAMEN[m]} | " + " | ".join(zelle) + " |")
    return zeilen, neu


def punkt(x):
    if x is None:
        return "–"
    x = round(float(x), 1)
    return "0" if x == 0 else f"{x:+g}".replace("-", "−").replace(".", ",")


def modell_zeilen(heute, eingaben_pfad=None, daten=None):
    """Abschnitt "Dein Modell": Fynns 12-Faktoren-Score (Ansicht, nicht durch Tests belegt)."""
    heute = pd.Timestamp(heute).normalize()
    z = []
    p = z.append
    auto = modell.automatik(heute, daten)
    ein = modell.lese_eingaben(eingaben_pfad)
    g = modell.gesamt(auto, ein)
    start, ende = auto["saison_fenster"]
    p("## Dein Modell (Ansicht, nicht durch Tests belegt)")
    p("Dein 12-Faktoren-Scoring mit denselben Gewichten und derselben Bias-Skala wie in der Notion-Tabelle. **Das ist eine Zusammenfassung der Lage, kein geprüftes Signal.** "
      "Die einzelnen Datenfaktoren haben in den Prüfungen keine Vorhersagekraft für 1 bis 4 Wochen gezeigt. Ob die Summe besser ist als die Teile, ist offen.")
    p("")
    p(f"Saisonalität gilt für **{datum(start)} bis {datum(ende)}** (Standard: ab Berichtstag, 3 Wochen, 15 Jahre, Kassakurse). "
      "Zeitraum frei wählen kannst du auf der Seite im Zeitraum-Rechner.")
    if not ein["vorhanden"]:
        p("")
        p("> **Eingabedatei nicht gefunden.** Alle manuellen Faktoren zählen als 0.")
    else:
        alter = (heute - pd.Timestamp(ein["stand"])).days if ein["stand"] else None
        if alter is None:
            p("")
            p("> **Hinweis:** In der Eingabedatei fehlt „Stand der Eingaben: JJJJ-MM-TT“.")
        elif alter > modell.ALTER_WARNUNG_TAGE:
            p("")
            p(f"> **Hinweis:** Die manuellen Eingaben (Technik, Zentralbank und so weiter) stammen vom {datum(ein['stand'])}, sind also {alter} Tage alt. Bitte in der Datei [[Scoring-Eingaben]] aktualisieren.")
    p("")
    kopf = "| Faktor | Gewicht | " + " | ".join(modell.ANZEIGE[m] for m in modell.REIHE) + " |"
    p(kopf)
    p("|---|---|" + "---|" * len(modell.REIHE))
    marke = {"ueberschrieben": " (ü)", "fehlt": " (fehlt)", "automatisch": "", "manuell": ""}
    for zeile in g["zeilen"]:
        if zeile["key"] == "technik":
            continue
        zellen = [punkt(zeile["punkte"][m]) + marke[zeile["herkunft"][m]] for m in modell.REIHE]
        p(f"| {zeile['name']} | ×{zeile['gewicht']} | " + " | ".join(zellen) + " |")
    p("| **Zwischensumme fundamental** | | " + " | ".join(f"**{punkt(g['fundamental'][m])}**" for m in modell.REIHE) + " |")
    technik = next(x for x in g["zeilen"] if x["key"] == "technik")
    p("| **Technik (dein Bias)** | ×1 | " + " | ".join(punkt(technik["punkte"][m]) + marke[technik["herkunft"][m]] for m in modell.REIHE) + " |")
    p("| **GESAMT** | | " + " | ".join(f"**{punkt(g['gesamt'][m])}**" for m in modell.REIHE) + " |")
    p("| **Bias** | | " + " | ".join(g["bias"][m] for m in modell.REIHE) + " |")
    p("")
    p("(ü) = von dir überschrieben, (fehlt) = Eingabe fehlt und zählt 0. Bias-Skala: ab +10 stark bullish, +5 bis +9 bullish, −4 bis +4 neutral, −5 bis −9 bearish, ab −10 stark bearish. Die Spalte „vs. Vorwoche“ kommt mit dem Verlauf.")
    p("")
    p("**Trade-Ideen nach Punktunterschied** (größte Differenz zwischen zwei Währungen, keine Handelsempfehlung):")
    for i, x in enumerate(g["ideen"], 1):
        p(f"{i}. Long {modell.ANZEIGE[x['long']]} / Short {modell.ANZEIGE[x['short']]} (Δ{punkt(x['delta']).lstrip('+')})")
    p("")
    p("Gelesene Werte der automatischen Faktoren:")
    p("")
    p("| Faktor | " + " | ".join(modell.ANZEIGE[m] for m in modell.REIHE) + " |")
    p("|---|" + "---|" * len(modell.REIHE))
    for f in modell.AUTOMATISCH:
        p(f"| {modell.NAME[f]} | " + " | ".join(auto["lesung"][f][m] for m in modell.REIHE) + " |")
    p("")
    if g["fehlend"]:
        p(f"Fehlende manuelle Eingaben: {len(g['fehlend'])} Felder (zählen 0).")
        p("")
    return z


def bericht(heute, daten=None, hinweis_pull="", eingaben_pfad=None):
    """Der Text der Notiz. `heute` ist ein Datum, `daten` der Ordner mit den gespeicherten Dateien."""
    heute = pd.Timestamp(heute).normalize()
    d = Path(daten) if daten else HIER / "daten"
    legacy = pd.read_csv(d / "cot_legacy.csv", parse_dates=["datum"])
    tff = pd.read_csv(d / "cot_tff.csv", parse_dates=["datum"])
    stand = legacy["datum"].max()
    alter = int((heute - stand).days)
    z = zinsen.lade()
    mk = makro.lade()

    zeilen = []
    p = zeilen.append
    p("---")
    p("tags: [trading, dashboard, wochenbericht]")
    p("status: aktiv")
    p(f"date: {heute.strftime('%Y-%m-%d')}")
    p("---")
    p("")
    p(f"# Trading Wochenbericht {datum(heute)}")
    p("")
    p(f"Automatisch erstellt aus dem [Trading Dashboard]({SEITE}) (Projekt: [[Trading Dashboard]], Erklärung der Seite: [[Trading Dashboard Seite erklärt]]). "
      "**Information, kein Signal.** Kein Faktor hat bisher Prüfung und Vorwärtstest bestanden.")
    p("")
    p(f"COT-Stand: Stichtag **{datum(stand)}** (Alter {alter} Tage" + (", normal)" if alter <= 10 else ", **veraltet**, bitte die Seite prüfen)") + ". " + hinweis_pull)
    p("")

    # Termine
    p("## Termine der nächsten 10 Tage")
    ereignisse = kalender.ereignisse(heute, 10)
    if ereignisse:
        p("| Tag | Was | Währung | Einzelheiten |")
        p("|---|---|---|---|")
        for e in ereignisse:
            t = pd.Timestamp(e["datum"])
            p(f"| {WOCHENTAG[t.dayofweek]} {datum(t)} | {TYP[e['typ']]} | {NAMEN[e['markt']]} | {e['text']} |")
    else:
        p("Keine erfassten Zinsentscheide oder Datentermine in den nächsten 10 Tagen.")
    k = kalender.berechne(heute)
    if k["warnung"]:
        p("")
        p(f"> **Hinweis zur Terminliste:** {k['warnung']}")
    p("")
    p("Datentermine sind bisher nur für die USA vollständig erfasst (Australien und Kanada nur der nächste Termin).")
    p("")

    # Dein Modell
    try:
        zeilen += modell_zeilen(heute, eingaben_pfad)
    except Exception as e:
        p("## Dein Modell (Ansicht, nicht durch Tests belegt)")
        p(f"Der Abschnitt konnte nicht berechnet werden ({e}).")
        p("")

    # COT
    p("## COT-Positionierung (Index über 52 Wochen)")
    p("Index 0 = so short wie im letzten Jahr nie, 100 = so long wie nie. Δ = Veränderung der Netto-Position zur Vorwoche (Kontrakte). Das sind die drei Linien deines TradingView-Indikators.")
    p("")
    p("| Währung | Großspekulanten | Commercials | Kleinanleger |")
    p("|---|---|---|---|")
    cz, neu = cot_zeilen(legacy, tff)
    zeilen += cz
    p("")
    if neu:
        p("**Neu in dieser Woche im Extrembereich:**")
        for n in neu:
            p(f"- {n}")
    else:
        p("Keine Gruppe ist diese Woche neu in den Extrembereich (ab 80 oder bis 20) gewandert.")
    p("")
    p("Die COT-Prüfung (0 von 15 bestanden) sagt: Ein Extremwert hat in den alten Daten nichts über die Kursrichtung der nächsten Wochen verraten. Die Markierungen sind Hintergrund, kein Signal.")
    p("")

    # Zinsen und Inflation
    p("## Zinsen, Inflation, Arbeitsmarkt")
    p("| Währung | Leitzins | Abstand zu USA | Inflation | Arbeitslosenquote | Realzins |")
    p("|---|---|---|---|---|---|")
    aenderungen = []
    for m, cfg in config.MAERKTE.items():
        land = cfg["bis"]
        zk = zinsen.kennzahlen(z, m)
        mkk = makro.kennzahlen(mk, land, leitzins=float(z[land].dropna().iloc[-1]))
        p(f"| {NAMEN[m]} | {prozent(zk['leitzins'])} | {vz(zk['abstand'], 2)} | {prozent(mkk.get('inflation'))} | {prozent(mkk.get('arbeitslos'), 1)} | {vz(mkk.get('realzins'), 2)} |")
        if zk["letzte_aenderung_datum"] and (heute - pd.Timestamp(zk["letzte_aenderung_datum"])).days <= 14:
            aenderungen.append(f"{NAMEN[m]}: Leitzins am {datum(zk['letzte_aenderung_datum'])} um {vz(zk['letzte_aenderung_groesse'], 2)} Prozentpunkte geändert")
    p("")
    if aenderungen:
        p("**Zinsänderungen der letzten 14 Tage:**")
        for a in aenderungen:
            p(f"- {a}")
    else:
        p("Keine Leitzinsänderung in den letzten 14 Tagen.")
    p("")
    p("Abstand zu USA = Leitzins der Währung minus US-Leitzins (beim DXY gegen einen Währungskorb). Realzins = Leitzins minus Inflation (beim DXY die USA).")
    p("")

    # Status der Prüfungen
    p("## Status der Prüfungen")
    try:
        fr = vorwaerts_realzins.letzter_freitag(heute)
        f5 = vorwaerts_realzins.signal_fuer(z, mk, fr)
        ps = punktesystem.berechne({m: (float(v) if pd.notna(v) else float("nan")) for m, v in f5.items()}, daten=d)
    except Exception as e:
        ps = None
        p(f"Der Status konnte nicht berechnet werden ({e}).")
    if ps:
        p("| Faktor | Prüfergebnis | Status |")
        p("|---|---|---|")
        for f in ps["faktoren"]:
            p(f"| {f['name']} | {f['text']} | {STATUS[f['status']]} |")
        p("")
        if ps["bestaetigt"] == 0:
            p("Es gibt **keinen bestätigten Faktor**. Deshalb steht bei allen Währungen „ohne Bewertung“, 0 Punkte.")
        else:
            p(f"**{ps['bestaetigt']} bestätigte(r) Faktor(en).** Punkte und Einstufung stehen auf der Seite unter „Gesamtbewertung“.")
        gruppen = {"lang": [], "kurz": [], "mitte": []}
        for m, v in ps["maerkte"].items():
            if v["realzins_gruppe"]:
                gruppen[v["realzins_gruppe"]].append(NAMEN[m])
        if gruppen["lang"] or gruppen["kurz"]:
            p("")
            p(f"Beobachtung Realzinsabstand (Regel „Kontra“, nur zur Beobachtung, keine Empfehlung), Signal vom {datum(fr)}: "
              f"Long-Gruppe {', '.join(gruppen['lang'])}, Short-Gruppe {', '.join(gruppen['kurz'])}, Mitte {', '.join(gruppen['mitte']) or '–'}.")
    p("")

    # Vorwärtstests
    p("## Vorwärtstests")
    for name, datei in (("Realzinsabstand", "vorwaertstest_realzins_ergebnis.json"), ("Saisonalität", "vorwaertstest_ergebnis.json")):
        j = punktesystem._lade(datei, d)
        if j is None:
            p(f"- {name}: noch keine Datei.")
            continue
        if "wochen_beobachtung" in j:
            p(f"- {name}: seit {j['beginn']}, {j['wochen_beobachtung']} Wochen beobachtet, {j['ausgewertet']} Wochen ausgewertet. "
              f"{'Urteil möglich.' if j['urteil_moeglich'] else 'Noch kein Urteil möglich (frühestens nach ' + str(j['min_wochen_beobachtung']) + ' Wochen).'}")
        else:
            p(f"- {name}: seit {j['beginn']}, {j['tage']} Tage beobachtet, {j['ausgewertet_haupt']} Trades ausgewertet. "
              f"{'Urteil möglich.' if j['urteil_moeglich'] else 'Noch kein Urteil möglich (frühestens nach ' + str(j['min_tage']) + ' Tagen).'}")
    p("")
    p("---")
    p("Nächster Bericht am nächsten Samstag. Die Prüfungen laufen jedes Jahr am 1. Februar noch einmal mit unveränderten Regeln.")
    return "\n".join(zeilen) + "\n"


def schreibe(vault, heute=None, daten=None, hinweis_pull="", eingaben_pfad=None):
    """Schreibt die Notiz. Gibt (Pfad, geschrieben?) zurück. Eine vorhandene Datei wird nie überschrieben."""
    heute = pd.Timestamp(datetime.now().date() if heute is None else heute).normalize()
    ziel = Path(vault) / ORDNER / f"Trading Wochenbericht {heute.strftime('%Y-%m-%d')}.md"
    if ziel.exists():
        return ziel, False
    text = bericht(heute, daten, hinweis_pull, eingaben_pfad)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text, encoding="utf-8")
    return ziel, True


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    a = ap.parse_args()
    print("Neueste Daten holen ...")
    hinweis = aktualisieren()
    print(hinweis)
    pfad, neu = schreibe(a.vault, hinweis_pull=hinweis)
    print(f"Notiz geschrieben: {pfad}" if neu else f"Für heute gibt es schon eine Notiz, nichts geändert: {pfad}")
