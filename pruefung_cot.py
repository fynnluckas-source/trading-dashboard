r"""Etappe 1d: Sagt ein extremer COT-Index etwas über die Kursbewegung der nächsten 1 / 4 / 13 Wochen?

Vorab festgelegte Regeln (vor dem ersten Lauf, damit nichts schöngerechnet wird):
  Signal:    COT-Index über 52 Wochen. "hoch" = Index >= 80, "tief" = Index <= 20.
  Gruppen:   Großspekulanten, Commercials, Kleinanleger (Legacy), Leveraged Funds, Asset Manager (TFF).
  Horizonte: 1, 4 und 13 Wochen.
  Messgröße: Rendite nach dem Signal in Volatilitäts-Einheiten (Rendite / (Wochen-Schwankung * Wurzel(Wochen))),
             Schwankung nur aus Daten VOR dem Einstieg.
  Wert D:    Mittel der Rendite nach "hoch" minus Mittel der Rendite nach "tief", alle 8 Märkte zusammen.
             D > 0 heißt Mitläufer (nach hoher Positionierung steigt der Kurs eher), D < 0 heißt Kontra.
  Einstieg:  Ein Bericht gilt erst ab dem ersten Handelstag NACH seiner Veröffentlichung (normal Freitag 15:30 New York,
             in Wochen mit US-Feiertag einen Werktag später). Eingestiegen wird zum Kurs dieses Tages.
  Bestanden, wenn ALLE vier Punkte erfüllt sind:
    1. Die Richtung (Mitläufer/Kontra) wird nur auf den ersten 70 % der Zeit festgelegt (Vorzeichen von D).
    2. Auf den letzten 30 % hat D dasselbe Vorzeichen.
    3. Auf den letzten 30 % ist D im Permutationstest signifikant (einseitig, in der festgelegten Richtung, p < 0,05)
       und mindestens 5 von 8 Märkten zeigen dieselbe Richtung.
    4. Die Anzahl der Signale (n) steht immer dabei.
  Der Permutationstest verschiebt die Signalreihe zufällig gegen die Kurse (alle Märkte gleich weit, damit der
  Zusammenhang der Märkte erhalten bleibt) und fragt, wie oft Zufall mindestens so viel zeigt.

Start:  .venv/Scripts/python.exe pruefung_cot.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

import config
import kennzahlen as kz
import kurse as kurse_modul

DATEN = Path(__file__).parent / "daten"
HORIZONTE = (1, 4, 13)
FENSTER_HAUPT = 52
FENSTER_ROBUST = (26, 156)
HOCH, TIEF = 80, 20
START = pd.Timestamp("2007-07-01")  # ab hier gibt es in beiden Berichten volle Index-Fenster (TFF erst ab Juni 2006)
ANTEIL_TRAINING = 0.7
N_PERM = 2000
MIN_N = 10          # weniger Signale je Seite (hoch/tief) gelten als zu wenig
MIN_MAERKTE = 5
SEED = 20261010

_FEIERTAGE = USFederalHolidayCalendar().holidays(start="1999-01-01", end="2035-12-31")


def veroeffentlichung(stichtag):
    """Tag der Veröffentlichung. Normal der Freitag der Woche, bei US-Feiertag Montag bis Freitag der Woche der Montag danach."""
    stichtag = pd.Timestamp(stichtag).normalize()
    montag = stichtag - pd.Timedelta(days=stichtag.weekday())
    freitag = montag + pd.Timedelta(days=4)
    if ((_FEIERTAGE >= montag) & (_FEIERTAGE <= freitag)).any():
        return freitag + pd.Timedelta(days=3)
    return freitag


def rendite_z(preis, stichtage, h):
    """Rendite in Volatilitäts-Einheiten für Einstieg nach Veröffentlichung, Halten über h Wochen.

    Gibt ein Array je Stichtag zurück (NaN, wenn Kurse fehlen oder der Zeitraum noch nicht vorbei ist)."""
    p = preis.dropna()
    log = np.log(p)
    woche = log.diff().rolling(260, min_periods=200).std() * np.sqrt(5)  # Schwankung pro Woche, nur Vergangenheit
    idx = p.index
    aus = np.full(len(stichtage), np.nan)
    for i, d in enumerate(stichtage):
        k = idx.searchsorted(veroeffentlichung(d), side="right")  # erster Handelstag nach der Veröffentlichung
        if k >= len(idx):
            continue
        ziel = idx[k] + pd.Timedelta(days=7 * h)
        if idx[-1] < ziel:
            continue
        k2 = idx.searchsorted(ziel, side="right") - 1
        s = woche.iloc[k]
        if np.isfinite(s) and s > 0:
            aus[i] = (log.iloc[k2] - log.iloc[k]) / (s * np.sqrt(h))
    return aus


def stat(sig, z):
    """D = Mittel(z nach hoch) - Mittel(z nach tief). NaN, wenn eine Seite zu wenige Signale hat."""
    ok = ~np.isnan(z) & ~np.isnan(sig)
    hi, lo = z[ok & (sig == 1)], z[ok & (sig == -1)]
    if len(hi) < MIN_N or len(lo) < MIN_N:
        return np.nan, len(hi), len(lo)
    return hi.mean() - lo.mean(), len(hi), len(lo)


def perm_p(sig, z, d_beob, richtung, h, rng):
    """p-Wert durch Verschieben der Signale gegen die Kurse. richtung: +1, -1 (einseitig) oder 0 (zweiseitig)."""
    t = sig.shape[0]
    zu_kurz = h + 13
    if not np.isfinite(d_beob) or t < 2 * zu_kurz + 5:
        return np.nan
    zaehler = 0
    for _ in range(N_PERM):
        k = int(rng.integers(zu_kurz, t - zu_kurz))
        d = stat(np.roll(sig, k, axis=0), z)[0]
        if not np.isfinite(d):
            continue
        if richtung == 0:
            zaehler += abs(d) >= abs(d_beob)
        elif richtung > 0:
            zaehler += d >= d_beob
        else:
            zaehler += d <= d_beob
    return (1 + zaehler) / (1 + N_PERM)


def phasen(sig):
    """Anzahl zusammenhängender Serien von hoch bzw. tief (je Markt, zusammengezählt)."""
    n = 0
    for j in range(sig.shape[1]):
        s = sig[:, j]
        vor = np.concatenate([[np.nan], s[:-1]])
        n += int(np.sum(((s == 1) | (s == -1)) & (s != vor)))
    return n


def baue_panels():
    legacy = pd.read_csv(DATEN / "cot_legacy.csv", parse_dates=["datum"])
    tff = pd.read_csv(DATEN / "cot_tff.csv", parse_dates=["datum"])
    k = kz.kennzahlen(legacy, tff)
    k = k[k["datum"] >= START]
    stichtage = pd.DatetimeIndex(sorted(k["datum"].unique()))
    maerkte = list(config.MAERKTE)
    preise = kurse_modul.lade()
    z = {h: np.column_stack([rendite_z(preise[m], stichtage, h) for m in maerkte]) for h in HORIZONTE}
    index = {}
    for g in kz.GRUPPEN:
        for w in (FENSTER_HAUPT,) + FENSTER_ROBUST:
            pv = k[k.gruppe == g].pivot(index="datum", columns="markt", values=f"idx{w}").reindex(index=stichtage, columns=maerkte)
            index[(g, w)] = pv.values
    return stichtage, maerkte, z, index


def signal(idx):
    s = np.full(idx.shape, np.nan)
    s[idx >= HOCH] = 1
    s[idx <= TIEF] = -1
    s[(idx > TIEF) & (idx < HOCH)] = 0
    return s


def pruefe(stichtage, maerkte, z, index, split):
    rng = np.random.default_rng(SEED)
    ergebnisse = []
    for g, (bericht, _, name, _) in kz.GRUPPEN.items():
        for h in HORIZONTE:
            zh = z[h]
            ende_training = stichtage + pd.Timedelta(days=7 * h + 10) < split  # Training: Kursfenster endet vor dem Split
            m_is = np.asarray((stichtage >= START) & ende_training)
            m_oos = np.asarray(stichtage >= split)

            def teil(w, maske):
                return signal(index[(g, w)])[maske], zh[maske]

            s_is, z_is = teil(FENSTER_HAUPT, m_is)
            s_oo, z_oo = teil(FENSTER_HAUPT, m_oos)
            d_is, nh_is, nt_is = stat(s_is, z_is)
            d_oo, nh_oo, nt_oo = stat(s_oo, z_oo)
            richtung = int(np.sign(d_is)) if np.isfinite(d_is) and d_is != 0 else 0
            p_is = perm_p(s_is, z_is, d_is, 0, h, rng)
            p_oo = perm_p(s_oo, z_oo, d_oo, richtung, h, rng) if richtung else np.nan
            # je Markt auf den letzten 30 %
            einig, gueltig = 0, 0
            for j in range(len(maerkte)):
                dm = stat(s_oo[:, [j]], z_oo[:, [j]])[0]
                if np.isfinite(dm):
                    gueltig += 1
                    einig += int(richtung != 0 and np.sign(dm) == richtung)
            # Robustheit (nur zur Information): gleiche Richtung auch bei 26 und 156 Wochen?
            robust = True
            for w in FENSTER_ROBUST:
                a = stat(*teil(w, m_is))[0]
                b = stat(*teil(w, m_oos))[0]
                robust &= bool(np.isfinite(a) and np.isfinite(b) and np.sign(a) == richtung and np.sign(b) == richtung)
            ok = np.isfinite(d_oo) and richtung != 0
            bestanden = bool(ok and np.sign(d_oo) == richtung and np.isfinite(p_oo) and p_oo < 0.05 and einig >= MIN_MAERKTE)
            valid = ~np.isnan(z_oo) & ~np.isnan(s_oo)
            ergebnisse.append({
                "gruppe": g, "name": name, "bericht": bericht, "h": h,
                "richtung": {1: "Mitläufer", -1: "Kontra", 0: "keine"}[richtung],
                "d_training": _f(d_is), "p_training": _f(p_is), "n_hoch_training": nh_is, "n_tief_training": nt_is,
                "d_test": _f(d_oo), "p_test": _f(p_oo), "n_hoch_test": nh_oo, "n_tief_test": nt_oo,
                "phasen_test": phasen(s_oo),
                "maerkte_einig": einig, "maerkte_gueltig": gueltig,
                "mittel_hoch_test": _f(np.mean(z_oo[valid & (s_oo == 1)])) if np.any(valid & (s_oo == 1)) else None,
                "mittel_tief_test": _f(np.mean(z_oo[valid & (s_oo == -1)])) if np.any(valid & (s_oo == -1)) else None,
                "mittel_alle_test": _f(np.mean(z_oo[~np.isnan(z_oo)])),
                "robust_26_156": bool(robust), "bestanden": bestanden,
            })
    return ergebnisse


def _f(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


def main():
    stichtage, maerkte, z, index = baue_panels()
    ende = max(stichtage[~np.isnan(z[13]).all(axis=1)])  # letzter Stichtag mit voller 13-Wochen-Rendite
    split = START + (ende - START) * ANTEIL_TRAINING
    split = split.normalize()
    erg = pruefe(stichtage, maerkte, z, index, split)
    bestanden = [e for e in erg if e["bestanden"]]
    out = {
        "berechnet": datetime.now().strftime("%d.%m.%Y"), "stand_cot": str(stichtage[-1].date()),
        "zeitraum_von": str(START.date()), "zeitraum_bis": str(ende.date()), "split": str(split.date()),
        "n_perm": N_PERM, "schwelle_hoch": HOCH, "schwelle_tief": TIEF, "fenster": FENSTER_HAUPT,
        "anzahl_tests": len(erg), "erwartet_zufall": round(len(erg) * 0.05 * 0.35, 1),
        "anzahl_bestanden": len(bestanden), "ergebnisse": erg,
    }
    (DATEN / "pruefung_cot.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    o = main()
    print(f"Zeitraum {o['zeitraum_von']} bis {o['zeitraum_bis']}, Trennung Training/Test am {o['split']}")
    print(f"{o['anzahl_tests']} Tests, bestanden: {o['anzahl_bestanden']} (durch Zufall erwartet: ca. {o['erwartet_zufall']})\n")
    print(f"{'Gruppe':16s} {'Wo':>3s} {'Richtung':10s} {'D_Train':>8s} {'p_Tr':>6s} {'D_Test':>8s} {'p_Test':>7s} {'Märkte':>7s} {'n hoch/tief':>12s} {'Phasen':>6s} {'robust':>6s}  Ergebnis")
    for e in o["ergebnisse"]:
        print(f"{e['name']:16s} {e['h']:>3d} {e['richtung']:10s} {e['d_training'] if e['d_training'] is not None else float('nan'):>8.3f} "
              f"{e['p_training'] if e['p_training'] is not None else float('nan'):>6.3f} "
              f"{e['d_test'] if e['d_test'] is not None else float('nan'):>8.3f} "
              f"{e['p_test'] if e['p_test'] is not None else float('nan'):>7.3f} "
              f"{e['maerkte_einig']}/{e['maerkte_gueltig']:>5} {e['n_hoch_test']:>5d}/{e['n_tief_test']:<5d} {e['phasen_test']:>6d} "
              f"{'ja' if e['robust_26_156'] else 'nein':>6s}  {'BESTANDEN' if e['bestanden'] else '-'}")
