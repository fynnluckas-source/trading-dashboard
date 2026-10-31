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
import modell_verlauf
import punktesystem
import kurse as kurse_modul
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
            zelle.append(f"{idx:.0f}{marke}, Netto {vz(z['net'])}, Δ1W {vz(z['d_net'])}, Δ4W {vz(modell.veraenderung(s, 4))}, Δ8W {vz(modell.veraenderung(s, 8))}")
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


def verlauf_zeilen(vault):
    """Wie liefen die früheren Trade-Ideen? Zwischenstand des Vorwärtstests von Dein Modell."""
    z = []
    p = z.append
    t = modell_verlauf.tabelle(vault)
    s = modell_verlauf.zusammenfassung(vault, 2)
    p("**Verlauf der Trade-Ideen (Vorwärtstest deines Modells):**")
    if t.empty:
        p("Noch keine früheren Ideen erfasst. Ab diesem Bericht wird jede Woche die Top 3 festgehalten und nach 1, 2 und 4 Wochen mit den echten Kursen verglichen.")
        p("")
        return z
    p("")
    p("| Bericht vom | Idee | Δ | 1 Woche | 2 Wochen | 4 Wochen |")
    p("|---|---|---|---|---|---|")
    t = t.assign(_rang=pd.to_numeric(t["rang"])).sort_values(["datum", "_rang"], ascending=[False, True]).head(12)
    for _, r in t.iterrows():
        def erg(spalte):
            v = pd.to_numeric(r[spalte], errors="coerce")
            return "offen" if pd.isna(v) else prozent(v, 2).replace(" %", " %")
        p(f"| {datum(r['datum'])} | Long {modell.ANZEIGE[r['long']]} / Short {modell.ANZEIGE[r['short']]} | {r['delta']} | {erg('r1w')} | {erg('r2w')} | {erg('r4w')} |")
    p("")
    if s["ausgewertet"]:
        p(f"Zwischenstand (2 Wochen Haltedauer): {s['ausgewertet']} Ideen ausgewertet aus {s['berichtswochen']} Berichten, Ø {prozent(s['mittel'], 2)}, {prozent(s['treffer'], 0)} im Plus. "
          + ("**Urteil: " + ("bestanden" if s.get("bestanden") else "nicht bestanden") + ".**" if s["urteil_moeglich"] else
             f"Noch kein Urteil möglich, frühestens nach {modell_verlauf.URTEIL_WOCHEN} Berichten und {modell_verlauf.URTEIL_IDEEN} ausgewerteten Ideen (bestanden nur bei Ø über 0 und über {modell_verlauf.URTEIL_TREFFER:g} % im Plus)."))
    else:
        p("Noch keine Idee ausgewertet (die erste braucht 1 Woche nach dem Einstieg).")
    p("")
    p("Rendite = Long-Währung minus Short-Währung, Einstieg am ersten Handelstag nach dem Bericht, Kassakurse, ohne Kosten und Swap. Die Top-3 sind oft fast dieselbe Wette (zum Beispiel immer gegen CAD), die Ergebnisse sind also nicht unabhängig.")
    p("")
    return z


COT_REGEL_AB = "2026-10-18"      # ab diesem Bericht zählt bei COT der 4-Wochen-Trend (vorher 1 Woche)
KURZNAME = {"technik": "Technik", "zb": "Zentralbank-Bias", "immo": "Immobilien/Kredit", "inflation": "Inflation", "bip": "BIP/Wachstum"}


def _name(key):
    return KURZNAME.get(key, modell.NAME[key])


def _lesung_kurz(auto, key, m):
    t = auto["lesung"].get(key, {}).get(m)
    if not t:
        return ""
    if key == "cot":                                   # "Index 100, Netto .., Δ1W .., Δ4W .." -> "Index 100, Δ4W .."
        teile = t.split(", ")
        return f"{teile[0]}, {teile[-1]}"
    return t


def erklaerung_zeilen(g, auto, vw, vw_tag):
    """Kurzer Text je Währung: woher der Score kommt und was sich zur Vorwoche geändert hat. Regelbasiert aus der Tabelle, keine KI."""
    z = []
    p = z.append
    herkunft_text = {"manuell": "deine Eingabe", "ueberschrieben": "von dir überschrieben", "fehlt": "Eingabe fehlt"}
    p("**Erklärung je Währung**")
    p("")
    for m in modell.REIHE:
        werte = {zeile["key"]: (zeile["punkte"][m], zeile["herkunft"][m]) for zeile in g["zeilen"]}

        def teil(key):
            pkt, herkunft = werte[key]
            if herkunft == "automatisch":
                info = _lesung_kurz(auto, key, m)
            else:
                info = herkunft_text[herkunft]
            return f"{_name(key)} {punkt(pkt)}" + (f" ({info})" if info else "")

        pos = sorted([k for k in werte if werte[k][0] > 0], key=lambda k: -werte[k][0])[:3]
        neg = sorted([k for k in werte if werte[k][0] < 0], key=lambda k: werte[k][0])[:3]
        null = sum(1 for k in werte if werte[k][0] == 0)
        kopf = f"- **{modell.ANZEIGE[m]}: {punkt(g['gesamt'][m])}, {g['bias'][m]}**"
        alt = vw.get(m) if vw else None
        if alt:
            kopf += f" (Vorwoche {punkt(alt['gesamt'])}, {alt['bias']}, Veränderung {punkt(g['gesamt'][m] - alt['gesamt'])})"
        p(kopf)
        satz = "  Woher der Score kommt: "
        satz += ("Am stärksten tragen " + ", ".join(teil(k) for k in pos) + ". ") if pos else "Kein Faktor ist positiv. "
        satz += ("Dagegen wirken " + ", ".join(teil(k) for k in neg) + ". ") if neg else "Kein Faktor ist negativ. "
        satz += ("Kein Faktor steht bei 0. " if null == 0 else "1 Faktor steht bei 0. " if null == 1 else f"{null} Faktoren stehen bei 0. ") + f"Zusammen: fundamental {punkt(g['fundamental'][m])}, Technik {punkt(g['technik'][m])}."
        p(satz)
        if not alt:
            p("  Zur Vorwoche: Es gibt noch keinen früheren Bericht zum Vergleich.")
            continue
        aenderungen = []
        for key, *_ in modell.FAKTOREN:
            if key not in alt:
                continue
            jetzt, herkunft = werte[key]
            if abs(jetzt - alt[key]) < 1e-9:
                continue
            if herkunft in ("manuell", "ueberschrieben", "fehlt"):
                grund = "deine Eingabe geändert" if herkunft != "fehlt" else "Eingabe fehlt jetzt"
            elif key == "saison":
                grund = f"neuer Zeitraum ab {datum(auto['saison_fenster'][0])}: {_lesung_kurz(auto, key, m)}"
            else:
                grund = f"neue Daten: {_lesung_kurz(auto, key, m)}"
                if key == "cot" and vw_tag < COT_REGEL_AB:
                    grund += ", teils durch die neue 4-Wochen-Regel"
            aenderungen.append(f"{_name(key)} {punkt(alt[key])} → {punkt(jetzt)} ({grund})")
        if aenderungen:
            text = "  Zur Vorwoche: " + "; ".join(aenderungen) + "."
        else:
            text = "  Zur Vorwoche: Kein Faktor hat sich geändert."
        if alt["bias"] != g["bias"][m]:
            text += f" Die Einstufung wechselt von {alt['bias']} auf {g['bias'][m]}."
        p(text)
    p("")
    p("Die Texte werden aus der Tabelle erzeugt (keine KI), sie erklären die Rechnung, nicht den Markt.")
    p("")
    return z


def modell_zeilen(heute, eingaben_pfad=None, daten=None, vault=None):
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
    vw, vw_tag = modell_verlauf.vorwoche(vault, heute) if vault else (None, None)
    if vw:
        p("| **vs. Vorwoche** | | " + " | ".join(punkt(g["gesamt"][m] - vw[m]) if m in vw else "–" for m in modell.REIHE) + " |")
    p("")
    p("(ü) = von dir überschrieben, (fehlt) = Eingabe fehlt und zählt 0. Bias-Skala: ab +10 stark bullish, +5 bis +9 bullish, −4 bis +4 neutral, −5 bis −9 bearish, ab −10 stark bearish. Vorwoche = Bericht vom " + (datum(vw_tag) if vw_tag else "–") + (", die Spalte „vs. Vorwoche“ erscheint, sobald es einen früheren Bericht mit Modell gibt." if not vw else "."))
    p("")
    vw_detail, vw_detail_tag = modell_verlauf.vorwoche_detail(vault, heute) if vault else (None, None)
    z += erklaerung_zeilen(g, auto, vw_detail, vw_detail_tag)
    p("**Trade-Ideen nach Punktunterschied** (größte Differenz zwischen zwei Währungen, keine Handelsempfehlung):")
    for i, x in enumerate(g["ideen"], 1):
        p(f"{i}. Long {modell.ANZEIGE[x['long']]} / Short {modell.ANZEIGE[x['short']]} (Δ{punkt(x['delta']).lstrip('+')})")
    p("")
    if vault:
        z += verlauf_zeilen(vault)
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


def bericht(heute, daten=None, hinweis_pull="", eingaben_pfad=None, vault=None):
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
        zeilen += modell_zeilen(heute, eingaben_pfad, vault=vault)
    except Exception as e:
        p("## Dein Modell (Ansicht, nicht durch Tests belegt)")
        p(f"Der Abschnitt konnte nicht berechnet werden ({e}).")
        p("")

    # COT
    p("## COT-Positionierung (Index über 52 Wochen)")
    p("Index 0 = so short wie im letzten Jahr nie, 100 = so long wie nie (Lage der aktuellen Netto-Position zwischen dem Tiefst- und dem Höchstwert der letzten 52 Wochen). Netto = Long minus Short in Kontrakten, derselbe Wert wie rechts an der Linie in deinem TradingView-Indikator. Δ1W, Δ4W, Δ8W = Veränderung der Netto-Position über 1, 4 und 8 Wochen (so siehst du, ob eine einzelne Woche gegen den längeren Trend läuft). Im Scoring („Dein Modell“) zählt bei den Commercials der Index und die Veränderung über 4 Wochen. Das sind die drei Linien deines TradingView-Indikators.")
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
    try:
        modell_verlauf.auswerten(vault, kurse_modul.lade())             # frühere Ideen mit den echten Kursen vergleichen
    except Exception as e:
        print(f"Hinweis: Auswertung früherer Ideen nicht möglich ({e})")
    text = bericht(heute, daten, hinweis_pull, eingaben_pfad, vault)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text, encoding="utf-8")
    try:                                                                  # Score und Ideen dieses Berichts festhalten (einmalig)
        auto = modell.automatik(heute)
        ein = modell.lese_eingaben(eingaben_pfad)
        modell_verlauf.erfassen(vault, heute, auto, ein, modell.gesamt(auto, ein))
    except Exception as e:
        print(f"Hinweis: Der Verlauf konnte nicht gespeichert werden ({e})")
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
