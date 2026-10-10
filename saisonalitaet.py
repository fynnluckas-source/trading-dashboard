r"""Saisonalität selbst gerechnet: Rendite je Kalendermonat und Kalenderwoche, Saisonkurve, Ausblick.

Es zählen nur ABGESCHLOSSENE Jahre (bis zum Vorjahr). Fenster: die letzten 5, 10, 15 oder 25 dieser Jahre.
Alle Renditen sind einfache Prozent-Renditen. Trefferquote = Anteil der Jahre mit Plus.
Kurse: Tageskurse aus daten/kurse_tag.csv (Kassakurse bzw. DX-Index, ohne Rollsprünge).
"""
import numpy as np
import pandas as pd
from scipy.stats import binomtest

JAHRE = (5, 10, 15, 25)
BASIS_JAHR = 2001  # Jahr ohne Schalttag, nur als Achse für die Saisonkurve
AUSBLICK_TAGE = 28


def _taeglich(preise):
    s = preise.dropna()
    return s.resample("D").ffill()


def _jahre(bis_jahr, n):
    return range(bis_jahr - n + 1, bis_jahr + 1)


def _stat(werte):
    """Kennzahlen einer Liste von Renditen (in Prozent)."""
    w = np.asarray(werte, dtype=float)
    w = w[~np.isnan(w)]
    if len(w) == 0:
        return {"mean": None, "median": None, "hit": None, "n": 0, "plus": 0}
    return {"mean": round(float(w.mean()), 3), "median": round(float(np.median(w)), 3),
            "hit": round(float((w > 0).mean() * 100), 1), "n": int(len(w)), "plus": int((w > 0).sum())}


def monate(preise, n, bis_jahr):
    """Rendite je Kalendermonat (Monatsende zu Monatsende) über die letzten n abgeschlossenen Jahre."""
    s = preise.dropna()
    m = s.groupby([s.index.year, s.index.month]).last()
    r = m.pct_change() * 100
    jahre = list(_jahre(bis_jahr, n))
    ys, ms = r.index.get_level_values(0), r.index.get_level_values(1)
    return [{"monat": mo, **_stat(r[(ms == mo) & np.isin(ys, jahre)].values)} for mo in range(1, 13)]


def wochen(preise, n, bis_jahr):
    """Rendite je Kalenderwoche (ISO, Wochenende zu Wochenende), Woche 53 wird weggelassen."""
    s = preise.dropna()
    iso = s.index.isocalendar()
    w = s.groupby([iso.year.values, iso.week.values]).last()
    r = w.pct_change() * 100
    jahre = list(_jahre(bis_jahr, n))
    ys, ws = r.index.get_level_values(0), r.index.get_level_values(1)
    return [{"woche": wo, **_stat(r[(ws == wo) & np.isin(ys, jahre)].values)} for wo in range(1, 53)]


def kurve(preise, n, bis_jahr):
    """Durchschnittlicher Verlauf über das Jahr in Prozent seit Jahresbeginn (365 Werte, ohne 29. Februar)."""
    d = _taeglich(preise)
    achse = [(t.month, t.day) for t in pd.date_range(f"{BASIS_JAHR}-01-01", f"{BASIS_JAHR}-12-31")]
    pfade = []
    for y in _jahre(bis_jahr, n):
        basis = d.loc[: f"{y - 1}-12-31"]
        seg = d.loc[f"{y}-01-01": f"{y}-12-31"]
        if basis.empty or len(seg) < 365:
            continue
        seg = seg[~((seg.index.month == 2) & (seg.index.day == 29))]
        pfade.append(((seg.values / basis.iloc[-1]) - 1) * 100)
    if not pfade:
        return None, 0
    return [round(float(v), 3) for v in np.mean(pfade, axis=0)], len(pfade)


def ausblick(preise, n, bis_jahr, ref, tage=AUSBLICK_TAGE):
    """Rendite der nächsten 'tage' Tage, wenn man in den letzten n Jahren am gleichen Kalendertag wie 'ref' eingestiegen wäre.

    Zum Vergleich: Basisrate = Rendite über 'tage' Tage von JEDEM Starttag in diesen Jahren (normale Drift)."""
    d = _taeglich(preise)
    werte = []
    for y in _jahre(bis_jahr, n):
        tag = 28 if (ref.month == 2 and ref.day == 29) else ref.day
        start = pd.Timestamp(year=y, month=ref.month, day=tag)
        ende = start + pd.Timedelta(days=tage)
        if start < d.index[0] or ende > d.index[-1]:
            continue
        werte.append((d.asof(ende) / d.asof(start) - 1) * 100)
    alle = (d.shift(-tage) / d - 1) * 100
    alle = alle.loc[f"{bis_jahr - n + 1}-01-01": f"{bis_jahr}-12-31"].dropna()
    return {**_stat(werte), "basis_mean": round(float(alle.mean()), 3), "basis_hit": round(float((alle > 0).mean() * 100), 1),
            "start": f"{ref.month:02d}-{ref.day:02d}", "tage": tage}


def zufallsgrenze(n):
    """Kleinste Trefferzahl (Jahre mit Plus), die bei n Jahren nicht mehr mit einer Münze (50 %) erklärbar ist (zweiseitig, p < 0,05)."""
    for k in range(n // 2 + 1, n + 1):
        if binomtest(k, n, 0.5).pvalue < 0.05:
            return k
    return None


def berechne(kurse, ref, bis_jahr=None):
    """Alles für die Seite: je Markt und Fenster Monate, Wochen, Kurve, Ausblick."""
    ref = pd.Timestamp(ref)
    bis = ref.year - 1 if bis_jahr is None else bis_jahr
    erg = {"ref": ref.strftime("%Y-%m-%d"), "bis_jahr": bis, "jahre": list(JAHRE),
           "zufall": {str(n): zufallsgrenze(n) for n in JAHRE}, "maerkte": {}}
    for m in kurse.columns:
        p = kurse[m].dropna()
        erg["maerkte"][m] = {}
        for n in JAHRE:
            k, anz = kurve(p, n, bis)
            erg["maerkte"][m][str(n)] = {"jahre_verfuegbar": anz, "monate": monate(p, n, bis), "wochen": wochen(p, n, bis),
                                         "kurve": k, "ausblick": ausblick(p, n, bis, ref)}
    return erg
