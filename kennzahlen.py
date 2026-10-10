"""COT-Kennzahlen: Netto-Position, Netto in % vom Open Interest, Veränderung zur Vorwoche, COT-Index.

COT-Index = wo steht die Netto-Position im Bereich der letzten N Wochen (0 = tiefster Wert, 100 = höchster).
Jeder Wert nutzt nur Daten bis zu seiner eigenen Woche (kein Blick in die Zukunft).
"""
import pandas as pd

# Schlüssel: (Bericht, Spalten-Präfix, Name, Erklärung)
GRUPPEN = {
    "spec": ("legacy", "spec", "Großspekulanten",
             "Legacy: Hedgefonds, Trendfolger und große Fonds, die am Kurs verdienen wollen (TradingView: Large Traders, rote Linie)."),
    "comm": ("legacy", "comm", "Commercials",
             "Legacy: Banken, Konzerne und Händler, die echte Geschäfte absichern. Stehen meist gegen den Trend (TradingView: blaue Linie)."),
    "small": ("legacy", "small", "Kleinanleger",
              "Legacy: alle Händler unter der Meldegrenze, meist Privatanleger (TradingView: Small Traders, grüne Linie)."),
    "lev": ("tff", "lev", "Leveraged Funds",
            "TFF: Hedgefonds und schnelle Fonds mit Kredithebel, die kurzfristige Spekulationsgruppe."),
    "am": ("tff", "am", "Asset Manager",
           "TFF: langfristige Anleger wie Pensionskassen, Versicherungen und Fondsgesellschaften."),
}
FENSTER = (26, 52, 156)  # Wochen


def _gruppe(df, key, praefix):
    teile = []
    for markt, g in df.groupby("markt"):
        g = g.sort_values("datum").reset_index(drop=True)
        net = g[f"{praefix}_long"] - g[f"{praefix}_short"]
        res = pd.DataFrame({"datum": g["datum"], "markt": markt, "gruppe": key,
                            "net": net, "net_pct": net / g["oi"] * 100})
        abstand = g["datum"].diff().dt.days
        res["d_net"] = net.diff().where(abstand <= 10)  # über Berichtslücken hinweg keine Veränderung rechnen
        for w in FENSTER:
            tief = net.rolling(w, min_periods=w).min()
            hoch = net.rolling(w, min_periods=w).max()
            res[f"idx{w}"] = ((net - tief) / (hoch - tief) * 100).where(hoch > tief)
        teile.append(res)
    return pd.concat(teile)


def kennzahlen(legacy, tff):
    """Gibt eine lange Tabelle zurück: eine Zeile je Woche, Markt und Gruppe."""
    teile = []
    for key, (bericht, praefix, _, _) in GRUPPEN.items():
        teile.append(_gruppe(legacy if bericht == "legacy" else tff, key, praefix))
    return pd.concat(teile).sort_values(["gruppe", "markt", "datum"]).reset_index(drop=True)
