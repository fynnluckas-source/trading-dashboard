"""Täglicher Lauf: COT auffrischen, alle Quellen prüfen, Seite bauen.

Wird von GitHub Actions jeden Tag gestartet (siehe .github/workflows/update.yml).
Die Seite wird IMMER gebaut. Ist eine Quelle kaputt, steht sie rot auf der Seite, die alten Daten bleiben erhalten.
Endet mit Fehlercode 1, wenn etwas kaputt ist, damit GitHub eine Mail schickt.
"""
import sys

import build_seite
import check_quellen
import config
import cot
import kurse
import makro
import vorwaerts
import vorwaerts_realzins
import zinsen


def main():
    fehler = []
    for art in config.CFTC_DATASETS:
        try:
            df = cot.lade(art)
            print(f"COT {art}: {len(df)} Zeilen bis {df['datum'].max().date()}")
        except Exception as e:
            fehler.append(f"COT {art} konnte nicht geladen werden: {e}")
            print(f"::error::{fehler[-1]}")

    try:
        k = kurse.lade(neu=True)  # bei Fehler bleibt die alte Datei erhalten
        print(f"Kurse: {k.shape[1]} Märkte bis {k.index.max().date()}")
    except Exception as e:
        fehler.append(f"Kurse konnten nicht geladen werden (alte Datei bleibt): {e}")
        print(f"::error::{fehler[-1]}")

    try:
        fut = kurse.lade_future(neu=True)  # zweite Kursquelle, bei Fehler bleibt die alte Datei
        print(f"Future-Kurse: {fut.shape[1]} Märkte bis {fut.index.max().date()}")
    except Exception as e:
        fehler.append(f"Future-Kurse konnten nicht geladen werden (alte Datei bleibt): {e}")
        print(f"::error::{fehler[-1]}")

    try:
        zdf = zinsen.lade(neu=True)  # Leitzinsen (BIS) und US-Rendite 2 Jahre (FRED), bei Fehler bleibt die alte Datei
        print(f"Zinsen: {len(zdf)} Tage bis {zdf.index.max().date()}")
    except Exception as e:
        fehler.append(f"Zinsen konnten nicht geladen werden (alte Datei bleibt): {e}")
        print(f"::error::{fehler[-1]}")

    try:
        mdf = makro.lade(neu=True)  # Inflation und Arbeitsmarkt, eine ausgefallene Reihe behält ihre alten Werte
        print(f"Makro: {len(mdf)} Zeilen, neueste Periode {mdf['periode'].max().date()}")
        for schluessel, grund in makro.LETZTE_FEHLER:
            fehler.append(f"Makro-Reihe {schluessel[0]} {schluessel[1]} ausgefallen (alte Werte bleiben): {grund}")
            print(f"::warning::{fehler[-1]}")
    except Exception as e:
        fehler.append(f"Makrodaten konnten nicht geladen werden (alte Datei bleibt): {e}")
        print(f"::error::{fehler[-1]}")

    try:
        n_neu, n_aus, z = vorwaerts.lauf()      # Vorwärtstest: neue Signale festhalten, vorbeigegangene Fenster auswerten
        print(f"Vorwärtstest: {n_neu} neue Signale, {n_aus} neu ausgewertet, insgesamt {z['erfasst']}")
    except Exception as e:
        fehler.append(f"Vorwärtstest fehlgeschlagen: {e}")
        print(f"::error::{fehler[-1]}")

    try:
        n_neu, n_aus, z = vorwaerts_realzins.lauf()      # Vorwärtstest Realzinsabstand: Freitags-Signal festhalten, 2 Wochen später auswerten
        print(f"Vorwärtstest Realzins: {n_neu} neu erfasst, {n_aus} neu ausgewertet, insgesamt {z['erfasst']}")
    except Exception as e:
        fehler.append(f"Vorwärtstest Realzins fehlgeschlagen: {e}")
        print(f"::error::{fehler[-1]}")

    quellen = check_quellen.alle()
    for q in quellen:
        if q["status"] == "ROT":
            fehler.append(f"Quelle {q['quelle']} ROT: {q['text']}")
            print(f"::warning::{fehler[-1]}")

    ziel, daten = build_seite.baue(quellen)
    print(f"Seite gebaut: {ziel}, COT-Stand {daten['stand']} (Alter {daten['alter']} Tage)")
    if fehler:
        print("\nProbleme:\n- " + "\n- ".join(fehler))
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
