import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modell as m

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_punkte_saison_python_und_js_stimmen_ueberein():
    werte = [(w, s) for w in (None, 0, 26, 33, 40, 41, 45, 50, 51, 55, 57, 60, 65, 100) for s in (None, -2.6, -1.26, -1.0, -0.9, -0.5, -0.2, 0, 0.13, 0.5, 0.6, 1.0, 1.02, 2)]
    js = "const z=require('./zeitraum.js');const w=%s;console.log(JSON.stringify(w.map(([a,b])=>z.zpunkteSaison(a,b))))" % json.dumps(werte)
    try:
        r = subprocess.run(["node", "-e", js], cwd=HIER, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        pytest.skip("Node nicht installiert")
    assert r.returncode == 0, r.stderr
    erwartet = [m.punkte_saison(a, b) for a, b in werte]
    assert json.loads(r.stdout) == erwartet
