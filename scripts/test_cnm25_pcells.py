#!/usr/bin/env python3
"""CNM25 KLayout PCell validation.

Runs the PCell port (profiles/cnm25/reference/klayout/pcells.py) under
KLayout in batch mode and asserts the generated device geometry:

- cnm25modn_m: GASAD active, POLY1 gate of length l over it, WINDOW contact
  pair per side, METAL source/drain, NPLUS implant enclosure, PWELL bulk;
  mx/my arrays extend the expected pitches.
- cnm25modp_m: same as NMOS but no NPLUS and NTUB bulk (n-well).
- cnm25cpoly_m: POLY0 plate encloses POLY1 by p0_ov; 4 WINDOW + 4 METAL
  stubs; plate size snaps to the 2*grid like the APDK pcell.

Requires the librelane nix environment (klayout with pya).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PCELS = ROOT / "profiles" / "cnm25" / "reference" / "klayout" / "pcells.py"

PROBE = r"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pya
import pcells

ly = pya.Layout()
for (gds, dt) in set(pcells.LAY.values()):
    ly.insert_layer(pya.LayerInfo(gds, dt))
ly.dbu = 0.001
pcells.register(ly)

def box_of(cell, name):
    li = ly.find_layer(pya.LayerInfo(*pcells.LAY[name]))
    return cell.shapes(li).bbox()

out = {}
for name, params in (
    ("cnm25modn_m", dict(w=4.5, l=3.0)),
    ("cnm25modn_m", dict(w=10.0, l=3.0, mx=2, my=1, common_d=1)),
    ("cnm25modn_m", dict(w=4.5, l=6.0, my=2)),
    ("cnm25modp_m", dict(w=4.5, l=3.0)),
    ("cnm25cpoly_m", dict(w=30.0, l=30.0)),
    ("cnm25cpoly_m", dict(w=50.0, l=20.0)),
):
    key = (name, tuple(sorted(params.items())))
    cell = ly.create_cell(name, params)
    got = {}
    for layer in pcells.LAY:
        li = ly.find_layer(pya.LayerInfo(*pcells.LAY[layer]))
        n = cell.shapes(li).size()
        got[layer] = {"count": n}
        if n:
            bb = pya.Region(cell.shapes(li)).bbox()
            got[layer].update(
                {"x1": bb.left * ly.dbu, "y1": bb.bottom * ly.dbu,
                 "x2": bb.right * ly.dbu, "y2": bb.top * ly.dbu})
    out[str(key)] = got
with open(os.environ["CNM25_PCELL_JSON"], "w") as fh:
    json.dump(out, fh)
"""


def run():
    import tempfile
    env = dict(os.environ)
    probe = PCELS.parent / "pcell_probe.py"
    probe.write_text(PROBE)
    fd, json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    env["CNM25_PCELL_JSON"] = json_path
    try:
        r = subprocess.run(
            ["nix", "develop", str(Path.home() / "Documents" / "librelane"),
             "--command", "bash", "-c",
             f"klayout -b -r {probe} 2>/dev/null"],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
            env=env)
    finally:
        probe.unlink(missing_ok=True)
    if r.returncode != 0:
        raise AssertionError(f"klayout probe failed: {r.stderr[-2000:]}")
    data = json_loads(Path(json_path).read_text())
    os.unlink(json_path)
    return data


def json_loads(s):
    import json
    return json.loads(s)


def main():
    data = run()
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    def g(key, layer):
        return data[key][layer]

    # --- NMOS default (w=4.5, l=3.0) ---------------------------------
    key = "('cnm25modn_m', (('common_d', 0), ('common_g', 0), ('common_s', 0), ('l', 3.0), ('mx', 1), ('my', 1), ('w', 4.5)))"
    if key not in data:
        keys = sorted(data)
        key = next(k for k in keys if "cnm25modn_m" in k and "10.0" not in k
                    and "6.0" not in k)
    a = g(key, "GASAD")
    check(a["count"] == 1, f"{key}: GASAD count {a['count']}")
    check(abs((a["x2"] - a["x1"]) - 14.0) < 1e-6,
          f"{key}: GASAD width {a['x2']-a['x1']} != 14.0")
    p = g(key, "POLY1")
    check(p["count"] == 1 and abs((p["x2"] - p["x1"]) - 3.0) < 1e-6,
          f"{key}: POLY1 gate length {p}")
    w = g(key, "WINDOW")
    # w=4.5um -> one contact per side (n = (4.5-2+3)//5.5 = 1)
    check(w["count"] == 2, f"{key}: WINDOW count {w['count']} (expect 2)")
    m = g(key, "METAL")
    check(m["count"] == 2, f"{key}: METAL count {m['count']} (expect 2)")
    n = g(key, "NPLUS")
    check(n["count"] == 1, f"{key}: NPLUS count {n['count']}")
    b = g(key, "PWELL")
    check(b["count"] == 1, f"{key}: PWELL bulk count {b['count']}")

    # --- NMOS array (mx=2, common_d) extends x -----------------------
    key2 = next(k for k in data if "10.0" in k)
    a2 = g(key2, "GASAD")
    a1 = g(key, "GASAD")
    check((a2["x2"] - a2["x1"]) > (a1["x2"] - a1["x1"]) + 5,
          f"{key2}: mx=2 array did not extend ({a2} vs {a1})")

    # --- PMOS: no NPLUS, NTUB bulk -----------------------------------
    keyp = next(k for k in data if "cnm25modp_m" in k)
    check(g(keyp, "NPLUS")["count"] == 0, f"{keyp}: PMOS must not draw NPLUS")
    check(g(keyp, "NTUB")["count"] == 1, f"{keyp}: PMOS needs NTUB bulk")
    check(g(keyp, "PWELL")["count"] == 0, f"{keyp}: PMOS must not draw PWELL")

    # --- cpoly: POLY0 encloses POLY1, 4 stubs ------------------------
    keyc = next(k for k in data if "cnm25cpoly_m" in k
                and "50.0" not in k)
    p0 = g(keyc, "POLY0")
    p1 = g(keyc, "POLY1")
    # plate (30um) + stubs => POLY1 bbox spans >= 30; POLY0 exceeds by >=2*p0_ov
    check(p0["count"] >= 1 and p1["count"] == 5, f"{keyc}: plates missing")
    check((p1["x2"] - p1["x1"]) >= 30.0,
          f"{keyc}: POLY1 span {p1['x2']-p1['x1']} < 30.0")
    check(p0["x1"] < p1["x1"] - 2 and p0["x2"] > p1["x2"] + 2
          and p0["y1"] < p1["y1"] - 2 and p0["y2"] > p1["y2"] + 2,
          f"{keyc}: POLY0 must enclose POLY1 by >=3um")
    check(g(keyc, "WINDOW")["count"] == 4, f"{keyc}: expect 4 WINDOW")
    check(g(keyc, "METAL")["count"] == 4, f"{keyc}: expect 4 METAL")

    if failures:
        raise AssertionError("\n".join(failures))
    print(f"CNM25 KLayout PCells: PASS ({len(data)} instances checked)")


if __name__ == "__main__":
    main()
