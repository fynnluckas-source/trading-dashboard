"""Etappe 7c: Verlauf von "Dein Modell". Jede Woche wird der Score festgehalten, damit es (1) die Spalte "vs. Vorwoche" gibt und
(2) die Trade-Ideen später mit den echten Kursen verglichen werden können (Vorwärtstest wie bei den anderen Prüfungen).

Die Dateien liegen NUR im Vault (sie enthalten deine privaten Eingaben wie die Technik), nicht im öffentlichen GitHub:
  03 Bereiche/Finanzen & Wirtschaft/Trading Wochenberichte/Modell-Verlauf.csv   (eine Zeile je Berichtstag und Währung)
  03 Bereiche/Finanzen & Wirtschaft/Trading Wochenberichte/Modell-Ideen.csv     (die Top-3-Trade-Ideen je Berichtstag, Ergebnisse werden später ergänzt)

Regeln (vor dem ersten Lauf festgelegt, 12.10.2026):
- Ein Berichtstag wird nur einmal erfasst, bestehende Zeilen werden nie verändert. Nichts wird nachträglich eingetragen.
- Einstieg: Schlusskurs des ersten Handelstags NACH dem Berichtstag. Ausstieg: letzter Handelstag höchstens 7, 14 oder 28 Tage nach dem Einstieg.
- Rendite einer Idee = Kursänderung der Long-Währung minus Kursänderung der Short-Währung (Kassakurse in US-Dollar). Beim DXY: Long DXY gegen eine
  Währung = Minus ihrer Kursänderung, Short DXY = ihre Kursänderung. Das ist eine Näherung für das Kreuzpaar, kein exakter Handelskurs, ohne Kosten und Swap.
- Ein Urteil gibt es frühestens nach 26 Berichtswochen mit mindestens 52 ausgewerteten Ideen (2 Wochen Haltedauer). Bestanden nur, wenn die
  Durchschnittsrendite über 0 liegt und die Trefferquote über 55 % (Zufall wäre 50 %). Bis dahin gibt es nur einen Zwischenstand.
"""
import csv
from pathlib import Path

import pandas as pd

import modell

ORDNER = Path("03 Bereiche") / "Finanzen & Wirtschaft" / "Trading Wochenberichte"
VERLAUF = "Modell-Verlauf.csv"
IDEEN = "Modell-Ideen.csv"
HORIZONTE = (1, 2, 4)                    # Wochen
URTEIL_WOCHEN, URTEIL_IDEEN, URTEIL_TREFFER = 26, 52, 55.0

VERLAUF_SPALTEN = ["datum", "eingaben_stand", "saison_start", "saison_ende", "markt"] + [k for k, *_ in modell.FAKTOREN] + ["fundamental", "gesamt", "bias"]
IDEEN_SPALTEN = ["datum", "rang", "long", "short", "delta", "start_handelstag"] + [f"r{w}w" for w in HORIZONTE]


def pfad(vault, name):
    return Path(vault) / ORDNER / name


def _lese(p, spalten):
    if not p.exists():
        return pd.DataFrame(columns=spalten)
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def erfasst(vault, heute):
    """Ist dieser Berichtstag schon im Verlauf?"""
    d = _lese(pfad(vault, VERLAUF), VERLAUF_SPALTEN)
    return pd.Timestamp(heute).strftime("%Y-%m-%d") in set(d["datum"])


def erfassen(vault, heute, auto, eingaben, g):
    """Hängt den Berichtstag an (einmalig). g = Ergebnis von modell.gesamt(). Gibt True zurück, wenn neu erfasst."""
    heute = pd.Timestamp(heute).normalize().strftime("%Y-%m-%d")
    if erfasst(vault, heute):
        return False
    pv, pi = pfad(vault, VERLAUF), pfad(vault, IDEEN)
    pv.parent.mkdir(parents=True, exist_ok=True)
    neu_v = not pv.exists()
    with pv.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if neu_v:
            w.writerow(VERLAUF_SPALTEN)
        start, ende = auto["saison_fenster"]
        for m in modell.REIHE:
            zeile = {z["key"]: z["punkte"][m] for z in g["zeilen"]}
            w.writerow([heute, eingaben.get("stand") or "", start, ende, m] + [f"{zeile[k]:g}" for k, *_ in modell.FAKTOREN]
                       + [f"{g['fundamental'][m]:g}", f"{g['gesamt'][m]:g}", g["bias"][m]])
    neu_i = not pi.exists()
    with pi.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if neu_i:
            w.writerow(IDEEN_SPALTEN)
        for rang, x in enumerate(g["ideen"], 1):
            w.writerow([heute, rang, x["long"], x["short"], f"{x['delta']:g}", ""] + [""] * len(HORIZONTE))
    return True


def vorwoche(vault, heute):
    """Gesamtscore je Währung vom letzten Berichtstag, der mindestens 4 Tage vor heute liegt. {markt: Score} oder None."""
    d = _lese(pfad(vault, VERLAUF), VERLAUF_SPALTEN)
    if d.empty:
        return None, None
    grenze = (pd.Timestamp(heute).normalize() - pd.Timedelta(days=4)).strftime("%Y-%m-%d")
    frueher = d[d["datum"] <= grenze]
    if frueher.empty:
        return None, None
    tag = frueher["datum"].max()
    z = frueher[frueher["datum"] == tag]
    return {r["markt"]: float(r["gesamt"]) for _, r in z.iterrows()}, tag


def paar_rendite(r, long, short):
    """Rendite einer Idee aus den Renditen (in %) der Währungen. DXY: Long DXY gegen X = -r(X), Short DXY = r(X)."""
    if long == "DX":
        return -r[short]
    if short == "DX":
        return r[long]
    return r[long] - r[short]


def auswerten(vault, kassa):
    """Ergänzt die Ergebnisse für alle Ideen, deren Haltedauer vorbei ist. Nur leere Felder werden gefüllt. Gibt die Zahl neu gefüllter Felder zurück."""
    pi = pfad(vault, IDEEN)
    if not pi.exists():
        return 0
    d = _lese(pi, IDEEN_SPALTEN)
    gefuellt = 0
    for i, z in d.iterrows():
        tag = pd.Timestamp(z["datum"])
        for w in HORIZONTE:
            if z[f"r{w}w"] != "":
                continue
            ergebnis = _rendite_idee(kassa, tag, z["long"], z["short"], w)
            if ergebnis is None:
                continue
            start, wert = ergebnis
            d.at[i, "start_handelstag"] = start
            d.at[i, f"r{w}w"] = f"{wert:.4f}"
            gefuellt += 1
    if gefuellt:
        d.to_csv(pi, index=False, encoding="utf-8")
    return gefuellt


def _rendite_idee(kassa, tag, long, short, wochen):
    r = {}
    start = None
    for m in {long, short} - {"DX"}:
        p = kassa[m].dropna()
        k = p.index.searchsorted(tag, side="right")                      # erster Handelstag nach dem Berichtstag
        if k >= len(p):
            return None
        ziel = p.index[k] + pd.Timedelta(days=7 * wochen)
        if p.index[-1] < ziel:                                            # Haltedauer noch nicht vorbei
            return None
        k2 = p.index.searchsorted(ziel, side="right") - 1
        r[m] = (p.iloc[k2] / p.iloc[k] - 1) * 100
        start = p.index[k].strftime("%Y-%m-%d")
    return start, paar_rendite(r, long, short)


def tabelle(vault):
    """Alle erfassten Ideen mit Ergebnissen."""
    return _lese(pfad(vault, IDEEN), IDEEN_SPALTEN)


def zusammenfassung(vault, horizont=2):
    """Zwischenstand und (später) Urteil der Trade-Ideen bei gegebener Haltedauer."""
    d = tabelle(vault)
    wochen = d["datum"].nunique() if len(d) else 0
    s = pd.to_numeric(d[f"r{horizont}w"], errors="coerce").dropna() if len(d) else pd.Series(dtype=float)
    aus = {"berichtswochen": int(wochen), "ausgewertet": int(len(s)), "horizont": horizont,
           "mittel": float(s.mean()) if len(s) else None, "treffer": float((s > 0).mean() * 100) if len(s) else None}
    moeglich = wochen >= URTEIL_WOCHEN and len(s) >= URTEIL_IDEEN
    aus["urteil_moeglich"] = bool(moeglich)
    if moeglich:
        aus["bestanden"] = bool(aus["mittel"] > 0 and aus["treffer"] > URTEIL_TREFFER)
    return aus
