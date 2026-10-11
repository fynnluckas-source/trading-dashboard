r"""Etappe 3c: Sagen Zinsen, Inflation oder Arbeitsmarkt etwas über die Kursbewegung der nächsten 1, 2 und 4 Wochen?

Vorab festgelegt (vor dem ersten Lauf, damit nichts schöngerechnet wird):
  Märkte:     7 Währungen gegen den US-Dollar (6A, 6B, 6S, 6N, 6J, 6E, 6C). DX wird nicht getestet (er ist der Gegenpart dieser 7).
  Faktoren:   Jeweils Unterschied der Währung zu den USA (Währung minus USA):
              F1 Zinsabstand (Leitzins), F2 Veränderung des Zinsabstands in 6 Monaten, F3 Inflationsabstand (Inflation zum Vorjahr),
              F4 Inflationstrend (Veränderung der Inflation in 3 Monaten), F5 Realzinsabstand (Leitzins minus Inflation),
              F6 Trend der Arbeitslosenquote (Veränderung in 6 Monaten).
  Wochen:     Jeden Freitag (ab 2001) werden die 7 Währungen nach dem Faktor sortiert. Obere Gruppe = die 3 Währungen mit dem höchsten Wert,
              untere Gruppe = die 3 mit dem niedrigsten. Gibt es weniger als 6 gültige Währungen, fällt die Woche aus.
  Einstieg:   Am ersten Handelstag NACH dem Freitag. Haltedauer 1, 2 und 4 Wochen (Kassakurs FRED).
  Makrodaten: Eine Beobachtung gilt erst ab Periodenende + übliche Veröffentlichungsverzögerung (makro.SERIEN) + 7 Tage Sicherheitsabstand.
              Leitzinsen gelten ab dem BIS-Datum.
  Messgröße:  Rendite in Schwankungs-Einheiten (Rendite / (Wochen-Schwankung * Wurzel(Wochen)), Schwankung nur aus Daten VOR dem Einstieg).
              S = Durchschnitt der Wochen von (Ø z der oberen Gruppe minus Ø z der unteren Gruppe). S > 0 heißt: Hoher Faktor, danach steigt die Währung.
  Aufteilung: Die ersten 70 % der Zeit legen die Richtung fest (Vorzeichen von S), die letzten 30 % prüfen sie.
  Bestanden, wenn ALLE vier Punkte erfüllt sind:
    1. Auf den letzten 30 %: Zufallstest einseitig in der festgelegten Richtung p < 0,05
       (die Faktor-Zeitreihe wird 2000 Mal zufällig in der Zeit verschoben, alle Märkte gleich weit, damit die Verbundenheit der Märkte erhalten bleibt).
    2. S hat auf den letzten 30 % dasselbe Vorzeichen wie im Training.
    3. Lässt man jeweils EINE der 7 Währungen weg, bleibt das Vorzeichen in mindestens 6 der 7 Fälle gleich.
    4. In mehr als 50 % der Wochen ist die Differenz in der festgelegten Richtung positiv.
  Nur zur Information: Ø Rendite der Differenz in Prozent je Woche (Long obere minus Short untere Gruppe), Anzahl Wochen.
  6 Faktoren * 3 Haltedauern = 18 Tests.

Start:  .venv/Scripts/python.exe pruefung_makro.py
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config
import kurse
import makro
import zinsen

DATEN = Path(__file__).parent / "daten"
WAEHRUNGEN = {"6A": "AU", "6B": "GB", "6S": "CH", "6N": "NZ", "6J": "JP", "6E": "XM", "6C": "CA"}
FAKTOREN = {
    "F1": "Zinsabstand",
    "F2": "Veränderung des Zinsabstands (6 Monate)",
    "F3": "Inflationsabstand",
    "F4": "Inflationstrend (3 Monate)",
    "F5": "Realzinsabstand",
    "F6": "Trend der Arbeitslosenquote (6 Monate)",
}
WOCHEN = (1, 2, 4)
START = pd.Timestamp("2001-01-05")
ANTEIL_TRAINING = 0.7
SICHERHEIT = 7          # Tage Sicherheitsabstand zur üblichen Veröffentlichungsverzögerung
N_PERM = 2000
SEED = 20261011
MIN_WAEHRUNGEN = 6
GRUPPE = 3
MIN_LOO = 6


# ------------------------------------------------------------------------------------------------ Faktoren
def veraenderung(s, monate):
    """Wert minus Wert vor 'monate' Monaten (über das Datum gesucht, fehlt der Vergleichsmonat, bleibt der Wert leer)."""
    vor = s.reindex([makro.monate_zurueck(t, monate) for t in s.index])
    vor.index = s.index
    return (s - vor).dropna()


def bekannt_ab(s, lag):
    """Beobachtungen mit dem Tag, ab dem sie öffentlich bekannt sind (Periodenende + Verzögerung + Sicherheitsabstand)."""
    k = s.copy()
    k.index = s.index + pd.Timedelta(days=lag + SICHERHEIT)
    return k


def zum_stichtag(s, wochen):
    """Letzter bekannter Wert zu jedem Stichtag (nichts aus der Zukunft)."""
    return s.reindex(s.index.union(wochen)).ffill().reindex(wochen)


def land_reihen(zdf, mk, land, wochen):
    inf, alo = makro.serie(mk, land, "inflation"), makro.serie(mk, land, "arbeitslos")
    lag_i, lag_a = makro.SERIEN[(land, "inflation")]["lag"], makro.SERIEN[(land, "arbeitslos")]["lag"]
    zins = zdf[land]
    return {"infl": zum_stichtag(bekannt_ab(inf, lag_i), wochen),
            "infl_trend": zum_stichtag(bekannt_ab(veraenderung(inf, 3), lag_i), wochen),
            "alo_chg": zum_stichtag(bekannt_ab(veraenderung(alo, 6), lag_a), wochen),
            "zins": zum_stichtag(zins.dropna(), wochen),                                # Leitzins gilt bis zur nächsten BIS-Meldung weiter
            "zins_6m": zum_stichtag(zins.dropna(), wochen - pd.DateOffset(months=6)).set_axis(wochen)}


def faktor_tabellen(zdf, mk, wochen):
    """Für jeden Faktor eine Tabelle (Wochen x 7 Währungen) mit dem Unterschied zu den USA."""
    us = land_reihen(zdf, mk, "US", wochen)
    out = {f: pd.DataFrame(index=wochen, columns=list(WAEHRUNGEN), dtype=float) for f in FAKTOREN}
    for markt, land in WAEHRUNGEN.items():
        r = land_reihen(zdf, mk, land, wochen)
        out["F1"][markt] = r["zins"] - us["zins"]
        out["F2"][markt] = (r["zins"] - us["zins"]) - (r["zins_6m"] - us["zins_6m"])
        out["F3"][markt] = r["infl"] - us["infl"]
        out["F4"][markt] = r["infl_trend"] - us["infl_trend"]
        out["F5"][markt] = (r["zins"] - r["infl"]) - (us["zins"] - us["infl"])
        out["F6"][markt] = r["alo_chg"] - us["alo_chg"]
    return out


# ------------------------------------------------------------------------------------------------ Renditen
def renditen(kassa, wochen, h):
    """Rendite je Woche und Währung für Einstieg am ersten Handelstag nach dem Stichtag, Haltedauer h Wochen.

    Gibt zwei Tabellen zurück: z (in Schwankungs-Einheiten) und r (Prozent)."""
    z = pd.DataFrame(index=wochen, columns=list(WAEHRUNGEN), dtype=float)
    r = z.copy()
    for m in WAEHRUNGEN:
        p = kassa[m].dropna()
        idx = p.index
        lg = np.log(p)
        woche = lg.diff().rolling(260, min_periods=200).std() * np.sqrt(5)
        for t in wochen:
            k = idx.searchsorted(t, side="right")                  # erster Handelstag nach dem Stichtag
            if k >= len(idx):
                continue
            ziel = idx[k] + pd.Timedelta(days=7 * h)
            if idx[-1] < ziel:
                continue
            k2 = idx.searchsorted(ziel, side="right") - 1
            s = woche.iloc[k]
            if np.isfinite(s) and s > 0:
                z.at[t, m] = (lg.iloc[k2] - lg.iloc[k]) / (s * np.sqrt(h))
                r.at[t, m] = (p.iloc[k2] / p.iloc[k] - 1) * 100
    return z, r


# ------------------------------------------------------------------------------------------------ Statistik
def spread(F, Z):
    """Wochen-Differenz (Ø obere Gruppe minus Ø untere Gruppe) je Woche. NaN, wenn weniger als 6 gültige Währungen."""
    F, Z = np.asarray(F, dtype=float), np.asarray(Z, dtype=float)
    ok = ~np.isnan(F)
    n = ok.sum(axis=1)
    order = np.argsort(np.where(ok, F, np.inf), axis=1)
    zs = np.take_along_axis(Z, order, axis=1)
    pos = np.arange(F.shape[1])[None, :]
    unten = pos < GRUPPE
    oben = (pos >= (n[:, None] - GRUPPE)) & (pos < n[:, None])
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # Woche ohne gültige Renditen in einer Gruppe: Ergebnis bleibt leer
        zu = np.where(unten, zs, np.nan)
        zo = np.where(oben, zs, np.nan)
        diff = np.nanmean(zo, axis=1) - np.nanmean(zu, axis=1)
    diff[n < MIN_WAEHRUNGEN] = np.nan
    return diff


def statistik(F, Z):
    d = spread(F, Z)
    ok = ~np.isnan(d)
    return (float(d[ok].mean()), int(ok.sum()), float((d[ok] > 0).mean())) if ok.sum() else (np.nan, 0, np.nan)


def perm_p(F, Z, s_beob, richtung, h, rng):
    """Einseitiger p-Wert: Faktor-Zeitreihe wird (für alle Märkte gleich) zufällig in der Zeit verschoben."""
    t = F.shape[0]
    luft = 4 * h + 13
    if not np.isfinite(s_beob) or t < 2 * luft + 10:
        return np.nan
    zaehler = 0
    for _ in range(N_PERM):
        k = int(rng.integers(luft, t - luft))
        s = statistik(np.roll(F, k, axis=0), Z)[0]
        if np.isfinite(s):
            zaehler += (s * richtung) >= (s_beob * richtung)
    return (1 + zaehler) / (1 + N_PERM)


def pruefe_faktor(F, Z, R, trainiert, test, h, rng):
    """Alle Kennzahlen eines Tests. F, Z, R sind numpy-Tabellen (Wochen x 7), 'trainiert' und 'test' je ein Boolean je Woche."""
    s_tr, n_tr, _ = statistik(F[trainiert], Z[trainiert])
    s_te, n_te, hit = statistik(F[test], Z[test])
    richtung = int(np.sign(s_tr)) if np.isfinite(s_tr) and s_tr != 0 else 0
    p_te = perm_p(F[test], Z[test], s_te, richtung, h, rng) if richtung else np.nan
    p_tr = np.nan
    if np.isfinite(s_tr):                                                   # zweiseitig: wie unwahrscheinlich ist ein so großer Betrag von S im Training?
        p_eins = perm_p(F[trainiert], Z[trainiert], s_tr, 1, h, np.random.default_rng(SEED))
        p_tr = min(1.0, 2 * min(p_eins, 1 - p_eins + 1 / (1 + N_PERM)))
    loo = 0
    for j in range(F.shape[1]):
        Fj, Zj = F[test].copy(), Z[test].copy()
        Fj[:, j], Zj[:, j] = np.nan, np.nan
        sj = statistik(Fj, Zj)[0]
        loo += int(richtung != 0 and np.isfinite(sj) and np.sign(sj) == richtung)
    d = spread(F[test], Z[test])
    treffer = float((d[~np.isnan(d)] * richtung > 0).mean() * 100) if richtung and (~np.isnan(d)).any() else np.nan
    dr = spread(F[test], R[test])
    pct = float(np.nanmean(dr)) * richtung if richtung else np.nan
    bestanden = bool(richtung and np.isfinite(s_te) and np.sign(s_te) == richtung and np.isfinite(p_te) and p_te < 0.05
                     and loo >= MIN_LOO and np.isfinite(treffer) and treffer > 50)
    f = lambda x, n=4: None if x is None or not np.isfinite(x) else round(float(x), n)
    return {"richtung": {1: "Mitläufer", -1: "Kontra", 0: "keine"}[richtung], "s_training": f(s_tr), "p_training": f(p_tr), "wochen_training": n_tr,
            "s_test": f(s_te), "p_test": f(p_te), "wochen_test": n_te, "loo": loo, "treffer_wochen": f(treffer, 1),
            "mittel_pct_test": f(pct), "bestanden": bestanden}


# ------------------------------------------------------------------------------------------------ Gesamtlauf
def baue(kassa, zdf, mk):
    letzter = kassa.index.max() - pd.Timedelta(days=7 * max(WOCHEN) + 10)
    wochen = pd.date_range(START, letzter, freq="W-FRI")
    return wochen, faktor_tabellen(zdf, mk, wochen)


def main():
    kassa, zdf, mk = kurse.lade(), zinsen.lade(), makro.lade()
    wochen, fakt = baue(kassa, zdf, mk)
    split = (START + (wochen[-1] - START) * ANTEIL_TRAINING).normalize()
    rng = np.random.default_rng(SEED)
    ergebnisse = []
    for h in WOCHEN:
        Z, R = renditen(kassa, wochen, h)
        tr = np.asarray((wochen + pd.Timedelta(days=7 * h + 10)) < split)       # Training: Kursfenster endet vor dem Split
        te = np.asarray(wochen >= split)                                          # Test: ab dem Split (Wochen dazwischen fallen aus)
        for f, name in FAKTOREN.items():
            erg = pruefe_faktor(fakt[f].values, Z.values, R.values, tr, te, h, rng)
            ergebnisse.append({"faktor": f, "name": name, "wochen": h, **erg})
    out = {"berechnet": datetime.now().strftime("%d.%m.%Y"), "zeitraum_von": str(wochen[0].date()), "zeitraum_bis": str(wochen[-1].date()),
           "split": str(split.date()), "n_perm": N_PERM, "sicherheit_tage": SICHERHEIT, "anzahl_tests": len(ergebnisse),
           "erwartet_zufall": round(len(ergebnisse) * 0.05 * 0.3, 1), "anzahl_bestanden": sum(e["bestanden"] for e in ergebnisse),
           "ergebnisse": ergebnisse}
    (DATEN / "pruefung_makro.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    o = main()
    print(f"Zeitraum {o['zeitraum_von']} bis {o['zeitraum_bis']}, Trennung Training/Test am {o['split']}")
    print(f"{o['anzahl_tests']} Tests, bestanden: {o['anzahl_bestanden']} (durch Zufall erwartet: ca. {o['erwartet_zufall']})\n")
    print(f"{'Faktor':44s}{'Wo':>3s} {'Richtung':10s}{'S_Train':>8s}{'p_Tr':>6s}{'S_Test':>8s}{'p_Test':>7s}{'LOO':>5s}{'Wochen+':>8s}{'Ø %':>8s}{'Wo.Test':>8s}  Ergebnis")
    for e in o["ergebnisse"]:
        g = lambda x, fmt: "   –  " if x is None else format(x, fmt)
        print(f"{e['faktor'] + ' ' + e['name']:44s}{e['wochen']:>3d} {e['richtung']:10s}{g(e['s_training'], '+.3f'):>8s}{g(e['p_training'], '.3f'):>6s}{g(e['s_test'], '+.3f'):>8s}"
              f"{g(e['p_test'], '.3f'):>7s}{e['loo']:>3d}/7{g(e['treffer_wochen'], '.1f'):>8s}{g(e['mittel_pct_test'], '+.3f'):>8s}{e['wochen_test']:>8d}  {'BESTANDEN' if e['bestanden'] else '-'}")
