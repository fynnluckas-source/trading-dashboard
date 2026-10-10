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


# ---------------------------------------------------------------------------------------------
# Zeitraum-Rechner (wie bei Seasonax): frei gewähltes Fenster, Winrate, Sharpe Ratio, Ampel
# ---------------------------------------------------------------------------------------------
import calendar

SHARPE_ZINS = 1.6   # Prozent pro Jahr, aus dem Seasonax-Screenshot abgeleitet (6E 22.10.-10.11.: -19,41 % / 9,03 % -> Sharpe -2,33)
HANDELSTAGE = 252
MIN_JAHRE = 5       # weniger Jahre mit Daten: keine Kennzahlen
REGEL_WINRATE_LONG, REGEL_SHARPE_LONG = 60.0, 1.0
REGEL_WINRATE_SHORT, REGEL_SHARPE_SHORT = 40.0, -1.0


def _tag(jahr, monat, tag):
    return pd.Timestamp(year=jahr, month=monat, day=min(tag, calendar.monthrange(jahr, monat)[1]))


def ampel(winrate, sharpe):
    """Fynns Seasonax-Regel: Long ab Winrate 60 % und Sharpe +1, Short bis Winrate 40 % und Sharpe -1."""
    if winrate is None or sharpe is None:
        return "neutral"
    if winrate >= REGEL_WINRATE_LONG and sharpe >= REGEL_SHARPE_LONG:
        return "long"
    if winrate <= REGEL_WINRATE_SHORT and sharpe <= REGEL_SHARPE_SHORT:
        return "short"
    return "neutral"


def zeitraum(preise, start, ende, n, bis_jahr, zins=SHARPE_ZINS):
    """Kennzahlen eines frei gewählten Fensters (start, ende = (Monat, Tag)) über die letzten n abgeschlossenen Jahre.

    Einstieg = erster Handelstag ab dem Starttag, Ausstieg = letzter Handelstag bis zum Endtag (Ende vor Start = Jahreswechsel).
    Winrate = Anteil der Jahre mit Plus. Jahresrendite und Schwankung kommen aus den Tagesrenditen aller Fenstertage
    (wie bei Seasonax), Sharpe = (Jahresrendite - Zins) / Schwankung."""
    s = preise.dropna()
    idx, vals = s.index, s.values
    jahre_liste, fenster, tages = [], [], []
    for y in _jahre(bis_jahr, n):
        ey = y + (1 if (ende[0], ende[1]) < (start[0], start[1]) else 0)
        a, b = _tag(y, *start), _tag(ey, *ende)
        if a < idx[0] or b > idx[-1]:
            continue
        i0 = idx.searchsorted(a, side="left")
        i1 = idx.searchsorted(b, side="right") - 1
        if i1 <= i0:
            continue
        fenster.append(vals[i1] / vals[i0] - 1)
        tages.extend(vals[i0 + 1:i1 + 1] / vals[i0:i1] - 1)
        jahre_liste.append({"jahr": y, "start": a.strftime("%Y-%m-%d"), "ende": b.strftime("%Y-%m-%d"), "rendite": round(float((vals[i1] / vals[i0] - 1) * 100), 3)})
    k = len(fenster)
    ergebnis = {"n": k, "jahre": jahre_liste, "kalendertage": int((_tag(2001 + (1 if (ende[0], ende[1]) < (start[0], start[1]) else 0), *ende) - _tag(2001, *start)).days)}
    if k < MIN_JAHRE:
        return {**ergebnis, "plus": None, "minus": None, "winrate": None, "mean": None, "median": None, "std": None,
                "jahresrendite": None, "schwankung": None, "sharpe": None, "ampel": "neutral"}
    f = np.array(fenster) * 100
    t = np.array(tages)
    jr = ((1 + t.mean()) ** HANDELSTAGE - 1) * 100
    vol = t.std(ddof=1) * np.sqrt(HANDELSTAGE) * 100
    sharpe = (jr - zins) / vol if vol > 1e-6 else None  # praktisch keine Schwankung: nicht definiert
    winrate = float((f > 0).mean() * 100)
    return {**ergebnis, "plus": int((f > 0).sum()), "minus": int((f <= 0).sum()), "winrate": round(winrate, 1),
            "mean": round(float(f.mean()), 3), "median": round(float(np.median(f)), 3), "std": round(float(f.std(ddof=1)), 3),
            "jahresrendite": round(float(jr), 2), "schwankung": round(float(vol), 2),
            "sharpe": None if sharpe is None else round(float(sharpe), 3), "ampel": ampel(winrate, sharpe)}
