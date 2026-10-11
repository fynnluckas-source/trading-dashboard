r"""Etappe 2c: Trägt Fynns Saisonalitäts-Regel? Test Jahr für Jahr, nur mit den Jahren davor.

Vorab festgelegt (vor dem ersten Lauf, damit nichts schöngerechnet wird):
  Regel:       Long-Kandidat bei Winrate >= 60 % UND Sharpe >= +1, Short-Kandidat bei Winrate <= 40 % UND Sharpe <= -1
               (Winrate und Sharpe wie im Zeitraum-Rechner, über die letzten 15 abgeschlossenen Jahre VOR dem Testjahr).
  Fenster:     Start jede Woche des Jahres (52 Startpunkte), Länge 7, 14, 21 und 28 Tage. Hauptfall: 28 Tage, Kassakurs, Auswahl A.
  Testjahre:   2016 bis 2025 (alle Quellen vergleichbar, der Future beginnt im Jahr 2000, 15 Jahre Vorlauf).
  Handel:      Im Testjahr wird das Fenster zu denselben Kalendertagen gehandelt. Long: +Rendite, Short: -Rendite (in Prozent).
  Auswahl A:   Alle Fenster, die die Regel erfüllen. Auswahl B: pro Markt, Jahr und Länge nur das beste Fenster (größter Betrag des Sharpe),
               so wie Fynn es von Hand tun würde.
  Quellen:     Kassa (FRED, DX: Yahoo-Index), Future (Yahoo, bereinigt, ohne DX), stabil (Kassa UND Future sagen dasselbe, ohne DX).
  Zufallstest: Die Kandidaten-Fenster werden je Testjahr zufällig im Jahr verschoben (alle Märkte gleich weit, Märkte hängen zusammen),
               2000 Mal. p = Anteil der Verschiebungen, die mindestens so viel Durchschnittsrendite bringen (einseitig).
  Bestanden, wenn ALLE vier Punkte erfüllt sind:
    1. Durchschnittliche Rendite je Trade > 0 und p < 0,05.
    2. In mindestens 60 % der Testjahre ist die Durchschnittsrendite > 0.
    3. In mindestens 5 Märkten ist die Durchschnittsrendite > 0.
    4. Trefferquote (Trades mit Gewinn) > 50 %.
  Nur zur Information: Rendite nach Kosten (0,03 % je Trade, Spread und Gebühren grob), Long und Short getrennt, Anzahl Trades und
  unabhängiger Phasen (zusammenhängende Serien von Startpunkten zählen als eine Phase).
  Die Schwellen (60/40, +1/-1) werden NICHT angepasst. Eine Empfindlichkeitsrechnung mit anderen Sharpe-Schwellen steht nur zur Ansicht da.

Start:  .venv/Scripts/python.exe walkforward.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config
import kurse
import saisonalitaet as sa

DATEN = Path(__file__).parent / "daten"
LAENGEN = (7, 14, 21, 28)
HAUPT_LAENGE = 28
N_JAHRE = 15
TESTJAHRE = range(2016, 2026)
STARTS = [(t.month, t.day) for t in pd.date_range("2001-01-01", periods=52, freq="7D")]   # 52 Startpunkte, wöchentlich
W = len(STARTS)
N_PERM = 2000
SEED = 20261011
KOSTEN = 0.03       # Prozent je Trade
MIN_JAHRE = sa.MIN_JAHRE
SCHWELLEN_SHARPE = (0.0, 0.5, 1.0, 1.5, 2.0)   # nur für die Empfindlichkeitsansicht


def ende_md(start_md, laenge):
    """Endtag (Monat, Tag) im Kalender 2001, Länge in Tagen (Jahreswechsel möglich)."""
    t = pd.Timestamp(2001, start_md[0], start_md[1]) + pd.Timedelta(days=laenge)
    return (t.month, t.day)


def tabellen(serie, jahre):
    """Für jedes Jahr und jeden Startpunkt: Fensterrendite (Prozent), Anzahl Tage, Summe und Quadratsumme der Tagesrenditen.

    Gibt je Länge vier Arrays der Form (Jahre, 52) zurück. NaN, wenn das Fenster nicht im Datenbereich liegt."""
    s = serie.dropna()
    idx, v = s.index, s.values.astype(float)
    r = np.r_[0.0, v[1:] / v[:-1] - 1]
    c1, c2 = np.cumsum(r), np.cumsum(r * r)
    out = {}
    for L in LAENGEN:
        R = np.full((len(jahre), W), np.nan)
        N = np.full((len(jahre), W), np.nan)
        S1 = np.full((len(jahre), W), np.nan)
        S2 = np.full((len(jahre), W), np.nan)
        for k, st in enumerate(STARTS):
            en = ende_md(st, L)
            wrap = 1 if (en[0], en[1]) < (st[0], st[1]) else 0
            for yi, y in enumerate(jahre):
                a, b = sa._tag(y, *st), sa._tag(y + wrap, *en)
                i0, i1 = idx.searchsorted(a, side="left"), idx.searchsorted(b, side="left")
                if a < idx[0] or i1 >= len(idx) or i1 <= i0:
                    continue
                R[yi, k] = (v[i1] / v[i0] - 1) * 100
                N[yi, k] = i1 - i0
                S1[yi, k] = c1[i1] - c1[i0]
                S2[yi, k] = c2[i1] - c2[i0]
        out[L] = {"r": R, "n": N, "s1": S1, "s2": S2}
    return out


def kennzahlen(tab, y0, y1, zins=sa.SHARPE_ZINS):
    """Winrate, Sharpe und Anzahl Jahre je Startpunkt aus den Jahren y0 bis y1 (Zeilenindizes, y1 ausgeschlossen)."""
    r, n, s1, s2 = (tab[x][y0:y1] for x in ("r", "n", "s1", "s2"))
    ok = ~np.isnan(r)
    k = ok.sum(axis=0)
    wr = np.where(k > 0, 100 * ((r > 0) & ok).sum(axis=0) / np.maximum(k, 1), np.nan)
    cnt = np.where(ok, n, 0).sum(axis=0)
    t1 = np.where(ok, s1, 0).sum(axis=0)
    t2 = np.where(ok, s2, 0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = t1 / cnt
        var = (t2 - cnt * m * m) / (cnt - 1)
        jr = ((1 + m) ** sa.HANDELSTAGE - 1) * 100
        vol = np.sqrt(np.maximum(var, 0)) * np.sqrt(sa.HANDELSTAGE) * 100
        sharpe = np.where(vol > 1e-6, (jr - zins) / vol, np.nan)
    wr = np.where(k >= MIN_JAHRE, wr, np.nan)
    sharpe = np.where(k >= MIN_JAHRE, sharpe, np.nan)
    return wr, sharpe


def signal(wr, sharpe, schwelle_long=1.0, schwelle_short=-1.0):
    s = np.zeros(wr.shape)
    s[(wr >= sa.REGEL_WINRATE_LONG) & (sharpe >= schwelle_long)] = 1
    s[(wr <= sa.REGEL_WINRATE_SHORT) & (sharpe <= schwelle_short)] = -1
    s[np.isnan(wr) | np.isnan(sharpe)] = np.nan
    return s


def baue(kassa, future, jahre):
    """Alles Nötige je Markt: Tabellen und je Testjahr Signale/Sharpe für Kassa und Future."""
    erg = {}
    for m in kassa.columns:
        tk = tabellen(kassa[m], jahre)
        tf = tabellen(future[m], jahre) if m in future.columns else None
        erg[m] = {"kassa": tk, "future": tf}
    return erg


def trades(daten, jahre, quelle, auswahl, laenge, sch_long=1.0, sch_short=-1.0):
    """Liste der Trades als Arrays (Jahr, Markt, Startpunkt, Richtung, Sharpe)."""
    maerkte = list(daten)
    zeilen = []
    for mi, m in enumerate(maerkte):
        d = daten[m]
        if quelle in ("future", "stabil") and d["future"] is None:
            continue
        for y in TESTJAHRE:
            yi = jahre.index(y)
            y0 = yi - N_JAHRE
            if y0 < 0:
                continue
            wr_k, sh_k = kennzahlen(d["kassa"][laenge], y0, yi)
            sig_k = signal(wr_k, sh_k, sch_long, sch_short)
            if quelle == "kassa":
                sig, sh = sig_k, sh_k
            else:
                wr_f, sh_f = kennzahlen(d["future"][laenge], y0, yi)
                sig_f = signal(wr_f, sh_f, sch_long, sch_short)
                if quelle == "future":
                    sig, sh = sig_f, sh_f
                else:   # stabil: beide Quellen sagen dasselbe (und nicht neutral)
                    sig = np.where((sig_k == sig_f) & (sig_k != 0), sig_k, 0.0)
                    sig = np.where(np.isnan(sig_k) | np.isnan(sig_f), np.nan, sig)
                    sh = (sh_k + sh_f) / 2
            kand = np.where((sig == 1) | (sig == -1))[0]
            if len(kand) == 0:
                continue
            if auswahl == "B":   # nur das beste Fenster (größter Betrag des Sharpe) je Markt, Jahr und Länge
                kand = np.array([kand[np.argmax(np.abs(sh[kand]))]])
            for w in kand:
                zeilen.append((y, mi, int(w), int(sig[w]), float(sh[w])))
    if not zeilen:
        return None
    a = np.array(zeilen)
    return {"jahr": a[:, 0].astype(int), "markt": a[:, 1].astype(int), "w": a[:, 2].astype(int), "s": a[:, 3], "sharpe": a[:, 4]}


def ergebnis_matrix(daten, jahre, laenge, quelle_ergebnis="kassa"):
    """Rendite im Testjahr: Array (Jahre, Märkte, 52). Die Handelsrendite im Testjahr zählt immer in der Quelle der Auswertung."""
    maerkte = list(daten)
    R = np.full((len(jahre), len(maerkte), W), np.nan)
    for mi, m in enumerate(maerkte):
        t = daten[m]["kassa"] if (quelle_ergebnis == "kassa" or daten[m]["future"] is None) else daten[m]["future"]
        R[:, mi, :] = t[laenge]["r"]
    return R


def auswerten(daten, jahre, quelle, auswahl, laenge, rng, mit_permutation=True, sch_long=1.0, sch_short=-1.0):
    maerkte = list(daten)
    t = trades(daten, jahre, quelle, auswahl, laenge, sch_long, sch_short)
    leer = {"quelle": quelle, "auswahl": auswahl, "laenge": laenge, "n_trades": 0, "bestanden": False}
    if t is None:
        return leer
    R = ergebnis_matrix(daten, jahre, laenge, "future" if quelle == "future" else "kassa")
    yi = np.array([jahre.index(y) for y in t["jahr"]])
    roh = R[yi, t["markt"], t["w"]]
    ok = ~np.isnan(roh)
    if ok.sum() < 5:
        return leer
    gewinn = t["s"][ok] * roh[ok]                    # Rendite des Trades (Long +r, Short -r)
    jahr, markt, w, s = t["jahr"][ok], t["markt"][ok], t["w"][ok], t["s"][ok]
    mean = float(gewinn.mean())
    # Phasen: zusammenhängende Startpunkte je Jahr, Markt und Richtung
    phasen = 0
    for (y, mk, sg), g in pd.DataFrame({"y": jahr, "m": markt, "s": s, "w": w}).groupby(["y", "m", "s"]):
        ws = np.sort(g["w"].values)
        phasen += 1 + int((np.diff(ws) > 1).sum())
    jahre_mean = {int(y): float(gewinn[jahr == y].mean()) for y in np.unique(jahr)}
    maerkte_mean = {maerkte[mk]: float(gewinn[markt == mk].mean()) for mk in np.unique(markt)}
    ergebnis = {"quelle": quelle, "auswahl": auswahl, "laenge": laenge, "n_trades": int(len(gewinn)), "n_phasen": phasen,
                "mean": round(mean, 4), "mean_nach_kosten": round(mean - KOSTEN, 4),
                "n_long": int((s == 1).sum()), "mean_long": round(float(gewinn[s == 1].mean()), 4) if (s == 1).any() else None,
                "n_short": int((s == -1).sum()), "mean_short": round(float(gewinn[s == -1].mean()), 4) if (s == -1).any() else None,
                "trefferquote": round(float((gewinn > 0).mean() * 100), 1),
                "jahre_positiv": int(sum(v > 0 for v in jahre_mean.values())), "jahre_gesamt": len(jahre_mean),
                "maerkte_positiv": int(sum(v > 0 for v in maerkte_mean.values())), "maerkte_gesamt": len(maerkte_mean),
                "jahre_mean": {str(k): round(v, 4) for k, v in sorted(jahre_mean.items())},
                "maerkte_mean": {k: round(v, 4) for k, v in maerkte_mean.items()}}
    p = None
    if mit_permutation:
        zufall = 0
        yvals = np.array(sorted(set(jahre[jahre.index(y)] for y in np.unique(jahr))))
        pos = {y: i for i, y in enumerate(yvals)}
        yp = np.array([pos[y] for y in jahr])
        for _ in range(N_PERM):
            k = rng.integers(1, W, size=len(yvals))          # je Testjahr eine Verschiebung, für alle Märkte gleich
            w2 = (w + k[yp]) % W
            o = R[yi[ok], markt, w2]
            v = ~np.isnan(o)
            if v.sum() == 0:
                continue
            zufall += (s[v] * o[v]).mean() >= mean
        p = (1 + zufall) / (1 + N_PERM)
    ergebnis["p"] = None if p is None else round(p, 4)
    anteil_jahre = ergebnis["jahre_positiv"] / ergebnis["jahre_gesamt"]
    ergebnis["bestanden"] = bool(p is not None and mean > 0 and p < 0.05 and anteil_jahre >= 0.6
                                 and ergebnis["maerkte_positiv"] >= 5 and ergebnis["trefferquote"] > 50)
    return ergebnis


def haupt(daten, jahre):
    rng = np.random.default_rng(SEED)
    erg = []
    for quelle in ("kassa", "future", "stabil"):
        for auswahl in ("A", "B"):
            for L in LAENGEN:
                erg.append(auswerten(daten, jahre, quelle, auswahl, L, rng))
    return erg


def empfindlichkeit(daten, jahre):
    """Nur zur Ansicht: andere Sharpe-Schwellen (Long ab x, Short bis -x) im Hauptfall, ohne Zufallstest."""
    rng = np.random.default_rng(SEED)
    aus = []
    for x in SCHWELLEN_SHARPE:
        r = auswerten(daten, jahre, "kassa", "A", HAUPT_LAENGE, rng, mit_permutation=False, sch_long=x, sch_short=-x)
        aus.append({"schwelle": x, "n_trades": r.get("n_trades", 0), "mean": r.get("mean"), "trefferquote": r.get("trefferquote")})
    return aus


def main():
    kassa, future = kurse.lade(), kurse.lade_future()
    jahre = list(range(1999, 2027))
    daten = baue(kassa, future, jahre)
    erg = haupt(daten, jahre)
    out = {"berechnet": datetime.now().strftime("%d.%m.%Y"), "testjahre": [min(TESTJAHRE), max(TESTJAHRE)], "n_jahre": N_JAHRE,
           "n_perm": N_PERM, "kosten": KOSTEN, "haupt_laenge": HAUPT_LAENGE, "ergebnisse": erg,
           "anzahl_tests": len(erg), "anzahl_bestanden": sum(e["bestanden"] for e in erg),
           "erwartet_zufall": round(len(erg) * 0.05 * 0.3, 1), "empfindlichkeit": empfindlichkeit(daten, jahre)}
    (DATEN / "pruefung_saison.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    o = main()
    print(f"Testjahre {o['testjahre'][0]} bis {o['testjahre'][1]}, {o['n_jahre']} Jahre Vorlauf, {o['anzahl_tests']} Tests, bestanden: "
          f"{o['anzahl_bestanden']} (durch Zufall erwartet: ca. {o['erwartet_zufall']})\n")
    print(f"{'Quelle':7s}{'Aus':>4s}{'Tage':>5s}{'Trades':>8s}{'Phasen':>7s}{'Ø %':>8s}{'nach K.':>8s}{'Long Ø':>8s}{'Short Ø':>8s}{'Treffer':>8s}{'Jahre+':>7s}{'Märkte+':>8s}{'p':>7s}  Ergebnis")
    for e in o["ergebnisse"]:
        if e["n_trades"] == 0:
            print(f"{e['quelle']:7s}{e['auswahl']:>4s}{e['laenge']:>5d}   keine Trades")
            continue
        f = lambda x: "   –   " if x is None else f"{x:+.3f}"
        print(f"{e['quelle']:7s}{e['auswahl']:>4s}{e['laenge']:>5d}{e['n_trades']:>8d}{e['n_phasen']:>7d}{e['mean']:>+8.3f}{e['mean_nach_kosten']:>+8.3f}"
              f"{(e['mean_long'] if e['mean_long'] is not None else float('nan')):>+8.3f}{(e['mean_short'] if e['mean_short'] is not None else float('nan')):>+8.3f}"
              f"{e['trefferquote']:>7.1f}%{e['jahre_positiv']:>4d}/{e['jahre_gesamt']:<2d}{e['maerkte_positiv']:>5d}/{e['maerkte_gesamt']:<2d}{e['p']:>7.3f}  {'BESTANDEN' if e['bestanden'] else '-'}")
    print("\nEmpfindlichkeit (nur Ansicht, Kassa, 28 Tage, Auswahl A): Sharpe-Schwelle, Trades, Ø %, Treffer")
    for x in o["empfindlichkeit"]:
        print(f"  ab {x['schwelle']:.1f}: {x['n_trades']:6d} Trades, Ø {x['mean'] if x['mean'] is not None else float('nan'):+.3f} %, Treffer {x['trefferquote'] if x['trefferquote'] is not None else float('nan'):.1f} %")
