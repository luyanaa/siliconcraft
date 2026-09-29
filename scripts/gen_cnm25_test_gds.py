#!/usr/bin/env python3
"""Generate CNM25 DRC/LVS test fixtures (clean + tampered) as GDS.

The clean fixture is a native-rule-compliant inverter: NMOS + PMOS + PiP
capacitor with exact 2.5um contacts and 3.0um vias on the 0.25um grid, all
spacings/enclosures at or above the CNM25 native minima.  The tampered
fixture adds known violations (undersized contact/via, metal1 spacing,
poly1 spacing, GASAD spacing, POLY0-GASAD spacing).

Usage:
  python3 scripts/gen_cnm25_test_gds.py [--out common/tests/gds/cnm25_test.gds]
  python3 scripts/gen_cnm25_test_gds.py --tamper --out .../cnm25_test_bad.gds
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# layer map (APDK native names, GDS number/datatype from cnm25.tch)
NTUB, GASAD, POLY0, POLY1 = (1, 0), (2, 0), (3, 0), (4, 0)
NPLUS, WINDOW, METAL, CAPS, METAL2, VIA = (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)
TEXT = (64, 0)

DBU = 0.25  # um per grid unit; all coordinates are grid units


def box(x1, y1, x2, y2):
    return (x1 * DBU, y1 * DBU, x2 * DBU, y2 * DBU)


def build(tamper: bool) -> tuple[dict, list]:
    L: dict = {k: [] for k in (NTUB, GASAD, POLY0, POLY1, NPLUS,
                               WINDOW, METAL, METAL2, VIA, CAPS)}
    labels = []

    def add(layer, x1, y1, x2, y2):
        L[layer].append(box(x1, y1, x2, y2))

    # ================= NMOS (left) =================
    # GASAD x -16..24, y -34..48 (10um x 20.5um)
    add(GASAD, -16, -34, 24, 48)
    # gate POLY1 x -48..28, y 2..22 (5um wide), ext >= 2.5um past GASAD
    add(POLY1, -48, 2, 40, 22)
    # NPLUS over NMOS diffusion with >= 2.5um enclosure
    add(NPLUS, -32, -50, 40, 64)
    # S contact (exact 2.5um), >= 2um from gate
    add(WINDOW, -12, -30, -2, -20)
    # D contact
    add(WINDOW, 6, 30, 16, 40)
    # gate contact on poly field, >= 2.5um from GASAD
    add(WINDOW, -42, 7, -32, 17)
    # S pad + wire down + via
    add(METAL, -17, -36, 3, -14)
    add(METAL, -18, -36, 4, -66)
    add(VIA, -13, -52, -1, -40)
    add(METAL2, -22, -57, 4, -35)
    # D pad + wire up + via
    add(METAL, 1, 25, 21, 45)
    add(METAL, 0, 45, 22, 90)
    add(VIA, 5, 68, 17, 80)
    add(METAL2, 0, 63, 24, 87)
    # gate pad + wire left + via
    add(METAL, -47, 2, -27, 22)
    add(METAL, -96, -4, -42, 24)
    add(VIA, -90, 1, -78, 13)
    add(METAL2, -95, -4, -71, 18)

    # ================= PMOS (right) =================
    # GASAD x 120..160, y -34..48
    add(GASAD, 120, -34, 160, 48)
    # NTUB encloses PMOS by >= 5um
    add(NTUB, 92, -62, 188, 76)
    # gate POLY1 x 96..192, y 2..22
    add(POLY1, 96, 2, 192, 22)
    # S contact
    add(WINDOW, 124, -30, 134, -20)
    # D contact
    add(WINDOW, 140, 30, 150, 40)
    # gate contact on poly field, >= 2.5um from GASAD
    add(WINDOW, 172, 7, 182, 17)
    # S pad + wire down + via
    add(METAL, 119, -36, 139, -14)
    add(METAL, 118, -36, 142, -66)
    add(VIA, 123, -58, 135, -46)
    add(METAL2, 115, -63, 141, -41)
    # D pad + wire up + via
    add(METAL, 135, 25, 155, 45)
    add(METAL, 130, 45, 158, 90)
    add(VIA, 135, 68, 147, 80)
    add(METAL2, 124, 63, 152, 87)
    # gate pad + wire down + via
    add(METAL, 167, 2, 187, 22)
    add(METAL, 166, -30, 188, 2)
    add(VIA, 171, -22, 183, -10)
    add(METAL2, 166, -27, 194, -5)

    # ================= PiP capacitor (POLY0/POLY1) =================
    # POLY0 plate: >= 2.5um wide, >= 6um from GASAD (y gap 116-48 = 17um),
    # encloses POLY1 by >= 3um
    add(POLY0, 110, 116, 226, 220)
    # POLY1 top plate inside POLY0 (CPOLY = POLY0 & POLY1 = 134..176, 164..182)
    add(POLY1, 134, 164, 176, 186)
    # POLY0 contact: >= 4um (16 units) from CPOLY and >= 4um POLY0 enclosure
    add(WINDOW, 192, 132, 202, 142)
    add(METAL, 187, 127, 207, 147)
    add(METAL, 190, 147, 214, 186)
    add(VIA, 195, 168, 207, 180)
    add(METAL2, 187, 163, 213, 185)

    # labels sit inside their METAL2 polygons (label coords in um)
    labels += [("VDD", 34, 18), ("VSS", -2, -11), ("IN", -20, 2),
               ("OUT", 3, 18), ("CAP", 50, 43)]

    if tamper:
        # undersized contact (2.0um)
        add(WINDOW, 270, 10, 278, 18)
        add(METAL, 264, 4, 284, 24)
        # METAL1 spacing 1um (min 3um)
        add(METAL, 260, 30, 274, 40)
        add(METAL, 278, 30, 292, 40)
        # POLY1 spacing 1um (min 3um)
        add(POLY1, 260, 50, 274, 64)
        add(POLY1, 278, 50, 292, 64)
        # undersized via (2.0um)
        add(VIA, 270, 80, 278, 88)
        add(METAL, 264, 74, 284, 94)
        add(METAL2, 264, 74, 284, 94)
        # GASAD spacing 1um (min 4um)
        add(GASAD, 260, 100, 270, 120)
        add(GASAD, 274, 100, 284, 120)
        # POLY0 to GASAD spacing 1um (min 6um)
        add(POLY0, 300, 140, 320, 160)
        add(GASAD, 300, 164, 320, 184)
        labels.append(("TAMPER", 274, 90))

    return L, labels


def write_gds(path: Path, L: dict, labels: list) -> None:
    import pya  # noqa: PLC0415

    layout = pya.Layout()
    layout.dbu = DBU
    top = layout.create_cell("CNM25_TEST")
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
    ap.add_argument("--out", default="common/tests/gds/cnm25_test.gds")
    ap.add_argument("--tamper", action="store_true")
    args = ap.parse_args()
    L, labels = build(args.tamper)
    write_gds(ROOT / args.out, L, labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
