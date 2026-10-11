r"""Vorwärtstest des Realzinsabstands (Hinweis aus Etappe 3c): Jede Woche das Signal festhalten, nach 2 Wochen die echte Rendite danebenschreiben.

Vorab festgelegt (die Regeln werden NICHT mehr geändert, jede Zeile trägt die Version "3c-v1"):
  Signal:    Jeden Freitag werden die 7 Währungen (6A, 6B, 6S, 6N, 6J, 6E, 6C) nach dem Realzinsabstand sortiert (Leitzins minus Inflation,
             Währung minus USA, wie in Etappe 3c, mit Veröffentlichungsverzögerung plus 7 Tage Sicherheit). Richtung KONTRA (so im Training festgelegt):
             Long = die 3 Währungen mit dem NIEDRIGSTEN Realzinsabstand, Short = die 3 mit dem HÖCHSTEN. Weniger als 6 gültige Währungen: keine Woche.
  Erfassen:  Der tägliche Lauf hält das Signal des letzten Freitags fest, wenn es noch nicht im Protokoll steht UND der Lauf spätestens am Montag
             danach stattfindet. Später wird nichts nachgetragen (kein nachträgliches Erfassen mit Kenntnis der Kurse). Erfasste Zeilen werden nie geändert.
  Handel:    Einstieg am ersten Handelstag nach dem Freitag, Haltedauer 14 Tage (Kassakurs FRED, wie im Test). Ergebnis je Woche = Ø Rendite der
             Long-Gruppe minus Ø Rendite der Short-Gruppe in Prozent (ohne Kosten und ohne Swap).
  Urteil:    Frühestens nach 52 Wochen Beobachtung UND mindestens 40 ausgewerteten Wochen. Dann dieselben Kriterien wie in Etappe 3c:
             Ø Ergebnis > 0 und Zufallstest einseitig p < 0,05, ohne jede einzelne Währung in mindestens 6 von 7 Fällen gleiche Richtung und
             in mehr als 50 % der Wochen im Plus. Bis dahin nur Zwischenstand.

Start:  .venv/Scripts/python.exe vorwaerts_realzins.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import kurse
import makro
import pruefung_makro as pm
import zinsen

DATEN = Path(__file__).parent / "daten"
LOG = DATEN / "vorwaertstest_realzins.csv"
ERGEBNIS = DATEN / "vorwaertstest_realzins_ergebnis.json"
REGEL = "3c-v1"
HALTEDAUER_WOCHEN = 2
MIN_WOCHEN_BEOBACHTUNG = 52
MIN_WOCHEN_AUSGEWERTET = 40
MAX_TAGE_NACH_FREITAG = 3          # Erfassen nur bis Montag
M = list(pm.WAEHRUNGEN)
SPALTEN = ["signal_datum", "erfasst_am", "regel"] + [f"w_{m}" for m in M] + ["lang", "kurz", "start_handelstag", "ende_handelstag"] + [f"r_{m}" for m in M] + ["ergebnis_pct"]


def letzter_freitag(heute):
    heute = pd.Timestamp(heute).normalize()
    return heute - pd.Timedelta(days=(heute.weekday() - 4) % 7)


def lade_log(pfad=None):
    pfad = Path(pfad or LOG)
    return pd.read_csv(pfad, dtype=str, keep_default_na=False) if pfad.exists() else pd.DataFrame(columns=SPALTEN)


def speichere_log(df, pfad=None):
    df[SPALTEN].to_csv(pfad or LOG, index=False)


def signal_fuer(zdf, mk, freitag):
    """Realzinsabstand der 7 Währungen für einen Freitag (nur Wissen bis dahin)."""
    return pm.faktor_tabellen(zdf, mk, pd.DatetimeIndex([freitag]))["F5"].iloc[0]


def erfassen(zdf, mk, heute, pfad=None):
    """Hält das Signal des letzten Freitags fest. Gibt 1 zurück, wenn eine Zeile neu ist, sonst 0."""
    heute = pd.Timestamp(heute).normalize()
    fr = letzter_freitag(heute)
    if (heute - fr).days > MAX_TAGE_NACH_FREITAG:
        return 0                                                    # zu spät: nicht mehr nachtragen
    log = lade_log(pfad)
    if (log["signal_datum"] == fr.strftime("%Y-%m-%d")).any():
        return 0
    f = signal_fuer(zdf, mk, fr)
    if f.notna().sum() < pm.MIN_WAEHRUNGEN:
        return 0
    rang = f.dropna().sort_values()
    lang, kurz = list(rang.index[:pm.GRUPPE]), list(rang.index[-pm.GRUPPE:])         # Kontra: Long = niedrigster, Short = höchster Realzinsabstand
    zeile = {"signal_datum": fr.strftime("%Y-%m-%d"), "erfasst_am": heute.strftime("%Y-%m-%d"), "regel": REGEL,
             "lang": " ".join(lang), "kurz": " ".join(kurz), "start_handelstag": "", "ende_handelstag": "", "ergebnis_pct": ""}
    for m in M:
        zeile[f"w_{m}"] = "" if pd.isna(f[m]) else f"{f[m]:.4f}"
        zeile[f"r_{m}"] = ""
    speichere_log(pd.concat([log, pd.DataFrame([zeile])], ignore_index=True), pfad)
    return 1


def auswerten(kassa, pfad=None):
    """Trägt die Renditen für Wochen ein, deren 2 Wochen vorbei sind (nur leere Felder, Signale bleiben unverändert). Gibt die Zahl neuer Ergebnisse zurück."""
    log = lade_log(pfad)
    neu = 0
    for i, row in log.iterrows():
        if row["ergebnis_pct"] != "":
            continue
        fr = pd.Timestamp(row["signal_datum"])
        z, r = pm.renditen(kassa, pd.DatetimeIndex([fr]), HALTEDAUER_WOCHEN)
        werte = r.iloc[0]
        if werte.isna().any():
            continue                                                # Haltedauer noch nicht vorbei oder Kurse fehlen
        lang, kurz = row["lang"].split(), row["kurz"].split()
        log.at[i, "ergebnis_pct"] = f"{werte[lang].mean() - werte[kurz].mean():.6f}"
        for m in M:
            log.at[i, f"r_{m}"] = f"{werte[m]:.6f}"
        p = kassa["6E"].dropna()
        k = p.index.searchsorted(fr, side="right")
        log.at[i, "start_handelstag"] = p.index[k].strftime("%Y-%m-%d")
        log.at[i, "ende_handelstag"] = p.index[p.index.searchsorted(p.index[k] + pd.Timedelta(days=7 * HALTEDAUER_WOCHEN), side="right") - 1].strftime("%Y-%m-%d")
        neu += 1
    if neu:
        speichere_log(log, pfad)
    return neu


def zusammenfassung(kassa, heute, pfad=None):
    heute = pd.Timestamp(heute).normalize()
    log = lade_log(pfad)
    out = {"stand": heute.strftime("%d.%m.%Y"), "regel": REGEL, "erfasst": int(len(log)), "min_wochen_beobachtung": MIN_WOCHEN_BEOBACHTUNG,
           "min_wochen_ausgewertet": MIN_WOCHEN_AUSGEWERTET, "letzte": []}
    if log.empty:
        out.update({"beginn": None, "wochen_beobachtung": 0, "ausgewertet": 0, "urteil_moeglich": False})
        return out
    beginn = pd.Timestamp(log["erfasst_am"].min())
    out["beginn"] = beginn.strftime("%d.%m.%Y")
    out["wochen_beobachtung"] = int((heute - beginn).days // 7)
    wochen = pd.DatetimeIndex(pd.to_datetime(log["signal_datum"]))
    F = np.array([[np.nan if log.iloc[i][f"w_{m}"] == "" else float(log.iloc[i][f"w_{m}"]) for m in M] for i in range(len(log))])
    Z, R = pm.renditen(kassa, wochen, HALTEDAUER_WOCHEN)
    ok = ~np.isnan(pm.spread(F, Z.values))
    out["ausgewertet"] = int(ok.sum())
    out["urteil_moeglich"] = bool(out["wochen_beobachtung"] >= MIN_WOCHEN_BEOBACHTUNG and out["ausgewertet"] >= MIN_WOCHEN_AUSGEWERTET)
    if ok.sum():
        ergebnis = -pm.spread(F, R.values)[ok]                      # Long niedrigster minus Short höchster Realzinsabstand, in Prozent
        out["mittel_pct"] = round(float(ergebnis.mean()), 4)
        out["trefferquote"] = round(float((ergebnis > 0).mean() * 100), 1)
        out["summe_pct"] = round(float(ergebnis.sum()), 3)
    if out["urteil_moeglich"]:
        rng = np.random.default_rng(pm.SEED)
        s = pm.statistik(F, Z.values)[0]
        p = pm.perm_p(F, Z.values, s, -1, HALTEDAUER_WOCHEN, rng)
        loo = 0
        for j in range(len(M)):
            Fj, Zj = F.copy(), Z.values.copy()
            Fj[:, j], Zj[:, j] = np.nan, np.nan
            sj = pm.statistik(Fj, Zj)[0]
            loo += int(np.isfinite(sj) and sj < 0)
        out.update({"s": round(float(s), 4), "p": None if not np.isfinite(p) else round(float(p), 4), "loo": loo,
                    "bestanden": bool(np.isfinite(p) and s < 0 and p < 0.05 and loo >= pm.MIN_LOO and out["trefferquote"] > 50)})
    for _, r in log.tail(10).iloc[::-1].iterrows():
        out["letzte"].append({"signal": r["signal_datum"], "lang": r["lang"], "kurz": r["kurz"],
                              "ergebnis": float(r["ergebnis_pct"]) if r["ergebnis_pct"] != "" else None})
    return out


def lauf(heute=None):
    heute = pd.Timestamp.now().normalize() if heute is None else pd.Timestamp(heute).normalize()
    kassa, zdf, mk = kurse.lade(), zinsen.lade(), makro.lade()
    n_neu = erfassen(zdf, mk, heute)
    n_aus = auswerten(kassa)
    z = zusammenfassung(kassa, heute)
    ERGEBNIS.write_text(json.dumps(z, ensure_ascii=False, indent=1), encoding="utf-8")
    return n_neu, n_aus, z


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n_neu, n_aus, z = lauf()
    print(f"Neu erfasst: {n_neu}, neu ausgewertet: {n_aus}, im Protokoll: {z['erfasst']}, Beobachtung seit {z['beginn']} ({z['wochen_beobachtung']} Wochen), ausgewertet: {z['ausgewertet']}")
    for v in z["letzte"][:5]:
        print(f"  Signal {v['signal']}: Long {v['lang']} | Short {v['kurz']} | Ergebnis {v['ergebnis'] if v['ergebnis'] is not None else 'offen'}")
