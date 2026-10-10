import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kurse
import saisonalitaet as sa

HIER = os.path.dirname(os.path.abspath(__file__))
FAELLE = [
    {"start": [10, 22], "ende": [11, 10], "n": 15, "bis": 2025},    # das Seasonax-Beispiel
    {"start": [1, 5], "ende": [2, 2], "n": 10, "bis": 2025},        # 4 Wochen im Januar
    {"start": [12, 15], "ende": [1, 12], "n": 15, "bis": 2025},     # über den Jahreswechsel
    {"start": [2, 29], "ende": [3, 28], "n": 25, "bis": 2025},      # Schalttag als Start
    {"start": [6, 1], "ende": [6, 8], "n": 5, "bis": 2025},         # 1 Woche
    {"start": [7, 1], "ende": [7, 28], "n": 25, "bis": 2025},
]


def test_python_und_browser_rechnen_gleich():
    if shutil.which("node") is None:
        pytest.skip("node nicht installiert")
    d = kurse.lade()
    for markt in ["6E", "6J", "DX"]:
        s = d[markt].dropna()
        tage = [int(t.value // 86_400_000_000_000) for t in s.index]
        eingabe = json.dumps({"tage": tage, "preise": [float(x) for x in s.values], "faelle": FAELLE})
        aus = subprocess.run(["node", os.path.join(HIER, "zeitraum_node.js")], input=eingabe, capture_output=True, text=True, check=True)
        js = json.loads(aus.stdout)
        for fall, j in zip(FAELLE, js):
            p = sa.zeitraum(s, tuple(fall["start"]), tuple(fall["ende"]), fall["n"], fall["bis"])
            for feld in ["n", "plus", "ampel", "kalendertage"]:
                assert p[feld] == j[feld], (markt, fall, feld, p[feld], j[feld])
            for feld in ["winrate", "mean", "median", "std", "jahresrendite", "schwankung", "sharpe"]:
                if p[feld] is None or j[feld] is None:
                    assert p[feld] == j[feld], (markt, fall, feld)
                else:
                    # Python rundet die Ausgabe auf feste Nachkommastellen, JS nicht: erlaubt ist nur der Rundungsfehler
                    stellen = {"winrate": 1, "mean": 3, "median": 3, "std": 3, "jahresrendite": 2, "schwankung": 2, "sharpe": 3}[feld]
                    assert abs(p[feld] - j[feld]) <= 0.5 * 10 ** -stellen + 1e-9, (markt, fall, feld, p[feld], j[feld])


def test_kombi_ampel_python_und_browser_gleich():
    if shutil.which("node") is None:
        pytest.skip("node nicht installiert")
    werte = ["long", "short", "neutral"]
    faelle = [(a, b) for a in werte for b in werte + [None]]
    code = "const {zampelKombi}=require('./zeitraum.js'); const f=" + json.dumps(faelle) + "; console.log(JSON.stringify(f.map(([a,b])=>zampelKombi(a,b))));"
    aus = subprocess.run(["node", "-e", code], cwd=os.path.dirname(HIER), capture_output=True, text=True, check=True)
    for (a, b), js in zip(faelle, json.loads(aus.stdout)):
        assert sa.ampel_kombi(a, b) == js, (a, b)
