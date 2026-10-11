r"""Vorwärtstest von Fynns Saisonalitäts-Regel: echte Signale festhalten, später die echte Rendite danebenschreiben.

So funktioniert es (vorab festgelegt, die Regeln werden NICHT mehr geändert):
  Erfassen:   Bei jedem Tageslauf werden alle Fenster, die in den nächsten 56 Tagen beginnen, mit ihrem Signal in
              daten/vorwaertstest.csv festgehalten (Startpunkte jede Woche, Länge 7, 14, 21, 28 Tage, je Markt).
              Ein Fenster wird nur EINMAL erfasst, Signal und Kennzahlen werden danach nie wieder verändert. Das Datum der Erfassung
              (erfasst_am) liegt immer vor dem Fensterstart, und die Datei steht samt Verlauf im öffentlichen GitHub (Nachweis).
  Signal:     Genau die Regel aus Etappe 2c: Long-Kandidat bei Winrate >= 60 % und Sharpe >= +1, Short-Kandidat bei Winrate <= 40 % und
              Sharpe <= -1, gerechnet über die 15 abgeschlossenen Jahre vor dem Jahr des Fensters (Kassa, Future, stabil = beide gleich).
  Auswerten:  Sobald ein Fenster vorbei ist (erster Handelstag ab dem Endtag liegt in den Daten), wird die Rendite je Quelle eingetragen.
  Urteil:     Wie in Etappe 2c: Ø Rendite > 0 und Zufallstest p < 0,05, in mindestens 60 % der Beobachtungsjahre und in mindestens
              5 Märkten im Plus, Trefferquote > 50 %. EIN Urteil gibt es frühestens nach 12 Monaten Beobachtung UND mindestens 300
              ausgewerteten Trades im Hauptfall (Kassa, alle Fenster, 28 Tage). Bis dahin ist alles nur Zwischenstand.
  Auswahl B:  „bestes Fenster je Markt und Jahr“ wird hier nachträglich aus den erfassten Signalen gewählt (nur über die Signale,
              nie über die Renditen, also ohne Blick auf das Ergebnis).

Start:  .venv/Scripts/python.exe vorwaerts.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import config
import kurse
import saisonalitaet as sa
import walkforward as wf

DATEN = Path(__file__).parent / "daten"
LOG = DATEN / "vorwaertstest.csv"
ERGEBNIS = DATEN / "vorwaertstest_ergebnis.json"
HORIZONT_TAGE = 56
REGEL = "2c-v1"
MIN_TAGE_URTEIL = 365
MIN_TRADES_URTEIL = 300
SPALTEN = ["erfasst_am", "jahr", "startpunkt", "fenster_start", "fenster_ende_soll", "laenge", "markt", "signal_kassa", "signal_future",
           "signal_stabil", "winrate_kassa", "sharpe_kassa", "winrate_future", "sharpe_future", "n_jahre", "regel",
           "rendite_kassa", "rendite_future"]


def lade_log(pfad=None):
    pfad = pfad or LOG
    if Path(pfad).exists():
        return pd.read_csv(pfad, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=SPALTEN)


def speichere_log(df, pfad=None):
    df[SPALTEN].to_csv(pfad or LOG, index=False)


def _ganz(x):
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(int(x))


def _zahl(x, stellen):
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{stellen}f}"


def erfassen(kassa, future, heute, pfad=None):
    """Hält neue Signale fest (nur Fenster, die nach heute beginnen und noch nicht im Protokoll stehen). Gibt die Zahl neuer Zeilen zurück."""
    heute = pd.Timestamp(heute).normalize()
    log = lade_log(pfad)
    vorhanden = set(zip(log["jahr"], log["startpunkt"], log["laenge"], log["markt"]))
    jahre = list(range(1999, heute.year + 2))
    daten = wf.baue(kassa, future, jahre)
    neu = []
    for Y in (heute.year, heute.year + 1):
        yi = jahre.index(Y)
        y0 = yi - wf.N_JAHRE
        ks = [k for k, st in enumerate(wf.STARTS) if heute < sa._tag(Y, *st) <= heute + pd.Timedelta(days=HORIZONT_TAGE)]
        if not ks or y0 < 0:
            continue
        for m, d in daten.items():
            for L in wf.LAENGEN:
                wr_k, sh_k = wf.kennzahlen(d["kassa"][L], y0, yi)
                sig_k = wf.signal(wr_k, sh_k)
                if d["future"] is not None:
                    wr_f, sh_f = wf.kennzahlen(d["future"][L], y0, yi)
                    sig_f = wf.signal(wr_f, sh_f)
                else:
                    wr_f = sh_f = sig_f = None
                for k in ks:
                    sk = sig_k[k]
                    sf = sig_f[k] if sig_f is not None else np.nan
                    aktiv_k, aktiv_f = sk in (1.0, -1.0), sf in (1.0, -1.0)
                    if not (aktiv_k or aktiv_f) or (str(Y), str(k), str(L), m) in vorhanden:
                        continue
                    st = wf.STARTS[k]
                    en = wf.ende_md(st, L)
                    wrap = 1 if (en[0], en[1]) < (st[0], st[1]) else 0
                    neu.append({
                        "erfasst_am": heute.strftime("%Y-%m-%d"), "jahr": str(Y), "startpunkt": str(k),
                        "fenster_start": sa._tag(Y, *st).strftime("%Y-%m-%d"), "fenster_ende_soll": sa._tag(Y + wrap, *en).strftime("%Y-%m-%d"),
                        "laenge": str(L), "markt": m,
                        "signal_kassa": _ganz(sk), "signal_future": _ganz(sf),
                        "signal_stabil": _ganz(sk if (aktiv_k and aktiv_f and sk == sf) else (0 if sig_f is not None else np.nan)),
                        "winrate_kassa": _zahl(float(wr_k[k]), 1), "sharpe_kassa": _zahl(float(sh_k[k]), 3),
                        "winrate_future": _zahl(float(wr_f[k]), 1) if wr_f is not None else "",
                        "sharpe_future": _zahl(float(sh_f[k]), 3) if sh_f is not None else "",
                        "n_jahre": str(int((~np.isnan(d["kassa"][L]["r"][y0:yi, k])).sum())), "regel": REGEL,
                        "rendite_kassa": "", "rendite_future": ""})
    if neu:
        speichere_log(pd.concat([log, pd.DataFrame(neu)], ignore_index=True), pfad)
    return len(neu)


def auswerten_log(kassa, future, pfad=None):
    """Trägt für vorbeigegangene Fenster die echte Rendite ein (nur leere Felder, Signale bleiben unverändert). Gibt die Zahl neuer Werte zurück."""
    log = lade_log(pfad)
    if log.empty:
        return 0
    neu = 0
    for i, row in log.iterrows():
        for feld, quellen in (("rendite_kassa", kassa), ("rendite_future", future)):
            if row[feld] != "" or row["markt"] not in quellen.columns:
                continue
            s = quellen[row["markt"]].dropna()
            idx = s.index
            i0 = idx.searchsorted(pd.Timestamp(row["fenster_start"]), side="left")
            i1 = idx.searchsorted(pd.Timestamp(row["fenster_ende_soll"]), side="left")
            if i0 >= len(idx) or i1 >= len(idx) or i1 <= i0:
                continue          # Fenster noch nicht vorbei oder Daten noch nicht da
            log.at[i, feld] = f"{(s.iloc[i1] / s.iloc[i0] - 1) * 100:.6f}"
            neu += 1
    if neu:
        speichere_log(log, pfad)
    return neu


def zusammenfassung(kassa, future, heute, pfad=None):
    heute = pd.Timestamp(heute).normalize()
    log = lade_log(pfad)
    jahre = list(range(1999, heute.year + 2))
    maerkte = list(kassa.columns)
    out = {"stand": heute.strftime("%d.%m.%Y"), "regel": REGEL, "erfasst": int(len(log)), "ergebnisse": [], "vorschau": [],
           "min_tage": MIN_TAGE_URTEIL, "min_trades": MIN_TRADES_URTEIL}
    if log.empty:
        out.update({"beginn": None, "tage": 0, "urteil_moeglich": False, "ausgewertet_haupt": 0})
        return out
    beginn = pd.Timestamp(log["erfasst_am"].min())
    out["beginn"] = beginn.strftime("%d.%m.%Y")
    out["tage"] = int((heute - beginn).days)
    num = log.copy()
    for c in ("signal_kassa", "signal_future", "signal_stabil", "winrate_kassa", "sharpe_kassa", "winrate_future", "sharpe_future",
              "rendite_kassa", "rendite_future", "jahr", "startpunkt", "laenge"):
        num[c] = pd.to_numeric(num[c], errors="coerce")
    daten = wf.baue(kassa, future, jahre)
    rng = np.random.default_rng(wf.SEED)
    for quelle in ("kassa", "future", "stabil"):
        for auswahl in ("A", "B"):
            for L in wf.LAENGEN:
                sig_col = {"kassa": "signal_kassa", "future": "signal_future", "stabil": "signal_stabil"}[quelle]
                d = num[(num["laenge"] == L) & num[sig_col].isin([1, -1])].copy()
                if d.empty:
                    out["ergebnisse"].append({"quelle": quelle, "auswahl": auswahl, "laenge": L, "n_trades": 0, "bestanden": False})
                    continue
                d["sh"] = (d["sharpe_future"] if quelle == "future" else d["sharpe_kassa"] if quelle == "kassa"
                           else d[["sharpe_kassa", "sharpe_future"]].mean(axis=1))
                if auswahl == "B":   # bestes Fenster je Markt und Jahr, nur nach dem Signal (Sharpe) gewählt, nie nach der Rendite
                    d = d.loc[d.groupby(["jahr", "markt"])["sh"].apply(lambda x: x.abs().idxmax())]
                t = {"jahr": d["jahr"].astype(int).values, "markt": np.array([maerkte.index(x) for x in d["markt"]]),
                     "w": d["startpunkt"].astype(int).values, "s": d[sig_col].astype(float).values}
                R = wf.ergebnis_matrix(daten, jahre, L, "future" if quelle == "future" else "kassa")
                out["ergebnisse"].append(wf.bewerte(t, R, maerkte, jahre, quelle, auswahl, L, rng))
    haupt = next((e for e in out["ergebnisse"] if e["quelle"] == "kassa" and e["auswahl"] == "A" and e["laenge"] == wf.HAUPT_LAENGE), {})
    out["ausgewertet_haupt"] = int(haupt.get("n_trades", 0))
    out["urteil_moeglich"] = bool(out["tage"] >= MIN_TAGE_URTEIL and out["ausgewertet_haupt"] >= MIN_TRADES_URTEIL)
    kommend = log[pd.to_datetime(log["fenster_start"]) > heute].copy()
    kommend = kommend.sort_values(["fenster_start", "markt", "laenge"]).head(60)
    out["vorschau"] = [{"start": r["fenster_start"], "ende": r["fenster_ende_soll"], "markt": r["markt"], "laenge": int(r["laenge"]),
                        "kassa": int(float(r["signal_kassa"])) if r["signal_kassa"] != "" else None,
                        "future": int(float(r["signal_future"])) if r["signal_future"] != "" else None,
                        "stabil": int(float(r["signal_stabil"])) if r["signal_stabil"] != "" else None,
                        "winrate": float(r["winrate_kassa"]) if r["winrate_kassa"] != "" else None,
                        "sharpe": float(r["sharpe_kassa"]) if r["sharpe_kassa"] != "" else None} for _, r in kommend.iterrows()]
    return out


def lauf(heute=None):
    """Ein Tageslauf: neue Signale erfassen, vorbeigegangene Fenster auswerten, Ergebnis speichern."""
    heute = pd.Timestamp.now().normalize() if heute is None else pd.Timestamp(heute).normalize()
    kassa, future = kurse.lade(), kurse.lade_future()
    n_neu = erfassen(kassa, future, heute)
    n_aus = auswerten_log(kassa, future)
    z = zusammenfassung(kassa, future, heute)
    ERGEBNIS.write_text(json.dumps(z, ensure_ascii=False, indent=1), encoding="utf-8")
    return n_neu, n_aus, z


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n_neu, n_aus, z = lauf()
    print(f"Neu erfasst: {n_neu}, neu ausgewertet: {n_aus}, im Protokoll insgesamt: {z['erfasst']}")
    print(f"Beobachtung seit {z['beginn']} ({z['tage']} Tage), ausgewertete Trades im Hauptfall: {z['ausgewertet_haupt']}, Urteil möglich: {z['urteil_moeglich']}")
    print(f"Vorschau (Signale für Fenster, die noch nicht begonnen haben): {len(z['vorschau'])} Einträge")
    for v in z["vorschau"][:10]:
        print(f"  {v['start']} bis {v['ende']}  {v['markt']}  {v['laenge']:>2d} Tage  Kassa {v['kassa']}, Future {v['future']}, stabil {v['stabil']}, Winrate {v['winrate']}, Sharpe {v['sharpe']}")
