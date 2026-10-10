r"""COT-Daten der CFTC laden und in daten/cot_legacy.csv und daten/cot_tff.csv speichern.

Start:  .venv\Scripts\python.exe cot.py          (Historie laden bzw. letzte 4 Wochen auffrischen)
        .venv\Scripts\python.exe cot.py --voll   (alles neu laden)
Gefiltert wird immer über den CFTC-Code, nie über den Namen (Namen haben sich 2022 geändert).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

import config

DATEN = Path(__file__).parent / "daten"
AUFFRISCHEN_TAGE = 28  # die CFTC korrigiert manchmal Vorwochen, deshalb immer 4 Wochen neu laden

# Spalten je Berichtsart: neuer Name -> CFTC-Name
SPALTEN = {
    "legacy": {
        "oi": "open_interest_all",
        "spec_long": "noncomm_positions_long_all", "spec_short": "noncomm_positions_short_all",
        "spec_spread": "noncomm_postions_spread_all",
        "comm_long": "comm_positions_long_all", "comm_short": "comm_positions_short_all",
        "small_long": "nonrept_positions_long_all", "small_short": "nonrept_positions_short_all",
        "d_oi": "change_in_open_interest_all",
        "d_spec_long": "change_in_noncomm_long_all", "d_spec_short": "change_in_noncomm_short_all",
        "d_comm_long": "change_in_comm_long_all", "d_comm_short": "change_in_comm_short_all",
    },
    "tff": {
        "oi": "open_interest_all",
        "dealer_long": "dealer_positions_long_all", "dealer_short": "dealer_positions_short_all",
        "am_long": "asset_mgr_positions_long", "am_short": "asset_mgr_positions_short",
        "lev_long": "lev_money_positions_long", "lev_short": "lev_money_positions_short",
        "other_long": "other_rept_positions_long", "other_short": "other_rept_positions_short",
        "small_long": "nonrept_positions_long_all", "small_short": "nonrept_positions_short_all",
        "d_oi": "change_in_open_interest_all",
        "d_am_long": "change_in_asset_mgr_long", "d_am_short": "change_in_asset_mgr_short",
        "d_lev_long": "change_in_lev_money_long", "d_lev_short": "change_in_lev_money_short",
    },
}
CODE_ZU_MARKT = {m["cftc"]: k for k, m in config.MAERKTE.items()}


def hole(art, seit=None):
    """Lädt alle Zeilen der 8 Märkte (ab Datum 'seit') von der CFTC."""
    codes = ",".join(f"'{c}'" for c in CODE_ZU_MARKT)
    where = f"cftc_contract_market_code in ({codes})"
    if seit is not None:
        where += f" and report_date_as_yyyy_mm_dd >= '{seit:%Y-%m-%d}'"
    zeilen, offset = [], 0
    while True:
        r = requests.get(config.CFTC_URL + config.CFTC_DATASETS[art] + ".json", timeout=120, params={
            "$where": where, "$order": "report_date_as_yyyy_mm_dd", "$limit": 5000, "$offset": offset})
        r.raise_for_status()
        teil = r.json()
        zeilen += teil
        if len(teil) < 5000:
            break
        offset += 5000
    return zeilen


def aufbereiten(art, zeilen):
    roh = pd.DataFrame(zeilen)
    if roh.empty:
        raise RuntimeError(f"CFTC {art}: keine Daten erhalten")
    fehlt = [c for c in SPALTEN[art].values() if c not in roh.columns]
    if fehlt:
        raise RuntimeError(f"CFTC {art}: Spalten fehlen (Format geändert?): {fehlt}")
    if "futonly_or_combined" in roh.columns and set(roh["futonly_or_combined"].unique()) - {"FutOnly"}:
        raise RuntimeError(f"CFTC {art}: unerwartet nicht nur Futures: {roh['futonly_or_combined'].unique()}")
    df = pd.DataFrame({
        "datum": pd.to_datetime(roh["report_date_as_yyyy_mm_dd"]).dt.normalize(),
        "markt": roh["cftc_contract_market_code"].map(CODE_ZU_MARKT),
    })
    for neu, alt in SPALTEN[art].items():
        df[neu] = pd.to_numeric(roh[alt], errors="coerce")
    df = df[df["datum"] >= config.COT_START]  # vor 1993 gibt es nur zwei Berichte im Monat
    df = df.dropna(subset=["markt"]).drop_duplicates(["datum", "markt"], keep="last")
    # small_ ist ein Restwert (in alten Daten negativ), deshalb nicht geprüft
    positionen = [c for c in df.columns if c.endswith(("_long", "_short")) and not c.startswith(("d_", "small_"))] + ["oi"]
    if (df[positionen].dropna() < 0).any().any():
        raise RuntimeError(f"CFTC {art}: negative Positionen, Daten unplausibel")
    return df.sort_values(["markt", "datum"]).reset_index(drop=True)


def lade(art, voll=False):
    """Aktualisiert die CSV-Datei einer Berichtsart und gibt die Tabelle zurück."""
    DATEN.mkdir(exist_ok=True)
    pfad = DATEN / f"cot_{art}.csv"
    if pfad.exists() and not voll:
        alt = pd.read_csv(pfad, parse_dates=["datum"])
        seit = alt["datum"].max() - pd.Timedelta(days=AUFFRISCHEN_TAGE)
        neu = aufbereiten(art, hole(art, seit))
        df = pd.concat([alt[alt["datum"] < neu["datum"].min()], neu])  # Überlappung: neue Werte gewinnen
    else:
        df = aufbereiten(art, hole(art))
    df = df.sort_values(["markt", "datum"]).reset_index(drop=True)
    df.to_csv(pfad, index=False, date_format="%Y-%m-%d")
    return df


def luecken(df, max_tage=14):
    """Findet Lücken in der Wochenreihe je Markt (normal 7 Tage Abstand)."""
    ergebnis = {}
    for markt, g in df.groupby("markt"):
        abstand = g["datum"].diff().dt.days.dropna()
        if (abstand > max_tage).any():
            ergebnis[markt] = g.loc[abstand[abstand > max_tage].index, "datum"].dt.date.tolist()
    return ergebnis


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--voll", action="store_true", help="alles neu laden")
    voll = p.parse_args().voll
    for art in config.CFTC_DATASETS:
        df = lade(art, voll)
        print(f"\n=== {art.upper()}: {len(df)} Zeilen, {df['datum'].min().date()} bis {df['datum'].max().date()}")
        info = df.groupby("markt").agg(von=("datum", "min"), bis=("datum", "max"), wochen=("datum", "count"))
        print(info.to_string())
        l = luecken(df)
        print("Lücken über 14 Tage:", {m: f"{len(d)}x, zuletzt {d[-1]}" for m, d in l.items()} if l else "keine")
