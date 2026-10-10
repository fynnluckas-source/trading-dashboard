"""Zeigt die neuesten COT-Zahlen aus den gespeicherten Dateien (zum Nachprüfen)."""
import sys
from pathlib import Path

import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATEN = Path(__file__).parent / "daten"
legacy = pd.read_csv(DATEN / "cot_legacy.csv", parse_dates=["datum"])
tff = pd.read_csv(DATEN / "cot_tff.csv", parse_dates=["datum"])

markt = sys.argv[1].upper() if len(sys.argv) > 1 else None
maerkte = [markt] if markt else list(config.MAERKTE)

print(f"Stand der Daten: Stichtag {legacy['datum'].max():%d.%m.%Y}\n")
for m in maerkte:
    if m not in config.MAERKTE:
        print(f"Unbekannter Markt {m}. Möglich: {', '.join(config.MAERKTE)}")
        continue
    a = legacy[legacy["markt"] == m].iloc[-1]
    b = tff[tff["markt"] == m].iloc[-1]
    print(f"{m} ({config.MAERKTE[m]['name']}), Stichtag {a['datum']:%d.%m.%Y}, Open Interest {a['oi']:,.0f}".replace(",", "."))
    print(f"  Legacy  Großspekulanten  Long {a['spec_long']:>9,.0f}  Short {a['spec_short']:>9,.0f}  Netto {a['spec_long'] - a['spec_short']:>+9,.0f}".replace(",", "."))
    print(f"  Legacy  Commercials      Long {a['comm_long']:>9,.0f}  Short {a['comm_short']:>9,.0f}  Netto {a['comm_long'] - a['comm_short']:>+9,.0f}".replace(",", "."))
    print(f"  TFF     Leveraged Funds  Long {b['lev_long']:>9,.0f}  Short {b['lev_short']:>9,.0f}  Netto {b['lev_long'] - b['lev_short']:>+9,.0f}".replace(",", "."))
    print(f"  TFF     Asset Manager    Long {b['am_long']:>9,.0f}  Short {b['am_short']:>9,.0f}  Netto {b['am_long'] - b['am_short']:>+9,.0f}".replace(",", "."))
    print()
