#!/usr/bin/env python3
"""Generate a CNM25 layout reconstructed from the APDK PCell geometry
(cnm25modn_m/cnm25modp_m/cnm25cpoly_m) for LVS parity checking.

The geometry below reproduces the APDK PCells 1:1 (same layer rules and
offsets): gate x 0..l / y -2.5..(w+2.5), active x -5.5..(l+5.5) / y 0..w,
S/D contacts with n_cont=2 at y 1.0..3.5 and 6.5..9.0, metal straps,
NPLUS overhang 2.5um, NTUB overhang 5.0um, and a PiP capacitor with POLY0
plate overhang 3.0um plus POLY1 stubs for the top terminal.

Usage:
  python3 scripts/gen_cnm25_pcell_test_gds.py [--out common/tests/gds/cnm25_pcell_test.gds]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NTUB, GASAD, POLY0, POLY1 = (1, 0), (2, 0), (3, 0), (4, 0)
NPLUS, WINDOW, METAL, METAL2, VIA = (5, 0), (6, 0), (7, 0), (9, 0), (10, 0)
TEXT = (64, 0)
DBU = 0.25


def pcell_nmos(L, ox, oy, w, l, nplus=True):
    """APDK cnm25modn_m single element (mx=my=1), all units um."""
    def add(layer, x1, y1, x2, y2):
        L[layer].append((ox + x1, oy + y1, ox + x2, oy + y2))
    add(GASAD, -(2.0 + 2.5 + 1.0), 0, l + 2.0 + 2.5 + 1.0, w)
    add(POLY1, 0, -2.5, l, w + 2.5)
    # S contacts (n_cont=2 for w=10)
    for n in range(2):
        y = 1.0 + n * (2.5 + 3.0)
        add(WINDOW, -(2.0 + 2.5), y, -2.0, y + 2.5)
        add(WINDOW, l + 2.0, y, l + 2.0 + 2.5, y + 2.5)
    # metal straps
    add(METAL, -(2.0 + 2.5 + 1.25), -0.25, -2.0 + 1.25, w + 0.25)
    add(METAL, l + 2.0 - 1.25, -0.25, l + 2.0 + 2.5 + 1.25, w + 0.25)
    # NPLUS overhang (the APDK PMOS PCell draws no NPLUS)
    if nplus:
        add(NPLUS, -(2.0 + 2.5 + 1.0 + 2.5), -2.5,
            l + 2.0 + 2.5 + 1.0 + 2.5, w + 2.5)


def pcell_pmos(L, ox, oy, w, l):
    """APDK cnm25modp_m single element: NMOS geometry (no NPLUS) + NTUB."""
    pcell_nmos(L, ox, oy, w, l, nplus=False)
    L[NTUB].append((ox - (2.0 + 2.5 + 1.0 + 5.0), oy - 5.0,
                    ox + l + 2.0 + 2.5 + 1.0 + 5.0, oy + w + 5.0))


def pcell_cpoly(L, ox, oy, w, l):
    """APDK cnm25cpoly_m: POLY0 plate (ov 3um), POLY1 plate + stubs."""
    def add(layer, x1, y1, x2, y2):
        L[layer].append((ox + x1, oy + y1, ox + x2, oy + y2))
    add(POLY0, -3.0, -3.0, l + 3.0, w + 3.0)          # plate
    add(POLY0, l + 1.0, -12.0, l + 12.0, -1.5)       # bottom-contact stub
    add(POLY1, 0, 0, l, w)                           # top plate
    add(POLY1, l + 4.0, 0, l + 9.0, w)               # top stub (outside POLY0)
    # top contact (cp) on the POLY1 stub
    add(WINDOW, l + 5.25, 1.25, l + 7.75, 3.75)
    # bottom contact (ce) on the POLY0 stub: >= 4um from POLY1, >= 4um POLY0 enc
    add(WINDOW, l + 5.0, -8.0, l + 7.5, -5.5)
    # metal to contacts
    add(METAL, l + 3.25, -0.5, l + 9.5, 5.0)
    add(METAL, l + 3.75, -9.5, l + 8.75, -3.5)


def build() -> tuple[dict, list]:
    L: dict = {k: [] for k in (NTUB, GASAD, POLY0, POLY1, NPLUS, WINDOW,
                               METAL, METAL2, VIA)}
    labels = []
    pcell_nmos(L, 0, 0, 10, 5)
    pcell_pmos(L, 30, 0, 10, 5)
    pcell_cpoly(L, 60, 0, 30, 30)
    labels += [("GND", -3, 5), ("VDD", 26, 5), ("CAP", 68, 15)]
    return L, labels


def write_gds(path: Path, L: dict, labels: list) -> None:
    import pya  # noqa: PLC0415
    layout = pya.Layout()
    layout.dbu = DBU
    top = layout.create_cell("CNM25_PCELL_TEST")
    for layer, shapes in L.items():
        idx = layout.insert_layer(pya.LayerInfo(layer[0], layer[1]))
        for x1, y1, x2, y2 in shapes:
            top.shapes(idx).insert(
                pya.Box(round(x1 / DBU), round(y1 / DBU),
                        round(x2 / DBU), round(y2 / DBU)))
    tidx = layout.insert_layer(pya.LayerInfo(TEXT[0], TEXT[1]))
    for text, x, y in labels:
        top.shapes(tidx).insert(
            pya.Text(text, pya.Trans(pya.Vector(round(x / DBU), round(y / DBU)))))
    path.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(path))
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="common/tests/gds/cnm25_pcell_test.gds")
    args = ap.parse_args()
    L, labels = build()
    write_gds(ROOT / args.out, L, labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
