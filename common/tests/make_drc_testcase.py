#!/usr/bin/env python3
"""Generate common/tests/gds/ami06_drc_test.gds.

Contains two known-good devices (nmos in p-substrate, pmos in n-well with an
n-well tap) and a battery of deliberate DRC violations for the ami06 profile
(AMI_C5N, lambda=0.3 um, grid=0.15 um -- all coordinates are on the 0.15 um
grid except the deliberate off-grid violation).  GDS database unit: 0.005 um.

Expected violations (reference deck, ami06):
  3.1   poly width            (V1)
  3.2   poly spacing          (V2)
  7.1   metal1 width          (V3)
  7.2   metal1 spacing        (V4)
  8.3   via not on metal1     (V6)
  2.1   active width          (V7)
  offgrid                     (V8)
  4.4   nselect width         (V9)
  6.2.b active enc of contact (V10)
  5.2.b poly enc of contact   (V11)
  8.3   metal1 enc of via     (V12)
  saveDerived: stray cc with no active/poly/elec overlap (V5)

Run (inside klayout python):
  OUT=<gds> klayout -b -r common/tests/make_drc_testcase.py
"""

import os

import pya

LY = {
    "nwell": 42, "active": 43, "pselect": 44, "nselect": 45, "poly": 46,
    "cc": 25, "metal1": 49, "via": 50, "metal2": 51,
}


def main():
    out = os.environ.get("OUT", "common/tests/gds/ami06_drc_test.gds")
    ly = pya.Layout()
    ly.dbu = 0.005  # 5 nm database unit; grid 0.15 um == 30 dbu
    top = ly.create_cell("ami06_drc_test")
    dbu = ly.dbu

    def put(name, x, y, w, h):
        li = ly.layer(LY[name], 0)
        top.shapes(li).insert(pya.Box(pya.DBox(x, y, x + w, y + h).to_itype(dbu)))

    # background on an unused layer: extends the cell bbox so the pBulk
    # complement region does not create spurious rule-2.3 edges
    top.shapes(ly.layer(90, 0)).insert(
        pya.Box(pya.DBox(-20.0, -20.0, 90.0, 90.0).to_itype(dbu)))

    # ---- known-good NMOS (p-substrate, n-well process) ---------------------
    put("active", 9.00, 9.90, 3.90, 3.00)
    put("nselect", 8.40, 9.00, 5.10, 4.80)
    put("poly", 10.50, 8.85, 0.90, 5.10)
    put("cc", 9.30, 11.25, 0.60, 0.60)
    put("cc", 12.00, 11.25, 0.60, 0.60)
    put("metal1", 9.00, 10.95, 1.20, 1.80)
    put("metal1", 11.70, 10.95, 1.20, 1.80)
    put("via", 9.30, 11.85, 0.60, 0.60)
    put("via", 12.00, 11.85, 0.60, 0.60)
    put("metal2", 8.85, 11.55, 1.50, 1.50)
    put("metal2", 11.55, 11.55, 1.50, 1.50)

    # ---- known-good PMOS in n-well + n-well tap ----------------------------
    put("nwell", 19.50, 19.50, 13.50, 13.50)
    put("active", 21.45, 21.45, 3.90, 3.00)
    put("pselect", 20.85, 20.55, 5.10, 4.80)
    put("poly", 22.95, 20.40, 0.90, 5.10)
    put("cc", 21.75, 22.65, 0.60, 0.60)
    put("cc", 24.45, 22.65, 0.60, 0.60)
    put("metal1", 21.45, 22.35, 1.20, 1.80)
    put("metal1", 24.15, 22.35, 1.20, 1.80)
    put("via", 21.75, 22.95, 0.60, 0.60)
    put("via", 24.45, 22.95, 0.60, 0.60)
    put("metal2", 21.30, 22.65, 1.50, 1.50)
    put("metal2", 24.00, 22.65, 1.50, 1.50)
    # n-well tap (nOhmic): >=6 lambda from well edge (rules 2.3/2.4)
    put("active", 29.10, 29.10, 2.10, 2.10)
    put("nselect", 28.50, 28.50, 3.30, 3.30)
    put("cc", 29.40, 29.40, 0.60, 0.60)
    put("metal1", 29.10, 29.10, 1.20, 1.20)

    # p-substrate tap (pOhmic)
    put("active", 35.10, 10.50, 2.10, 2.10)
    put("pselect", 34.50, 9.90, 3.30, 3.30)
    put("cc", 35.40, 10.80, 0.60, 0.60)
    put("metal1", 35.10, 10.50, 1.20, 1.20)

    # poly resistor (res_id on poly over field; res_id spans full poly width
    # so the poly ends form two separate nets)
    put("poly", 38.55, 15.00, 1.20, 5.25)
    top.shapes(ly.layer(65, 0)).insert(  # res_id
        pya.Box(pya.DBox(38.55, 15.60, 39.75, 19.50).to_itype(dbu)))

    # poly2-poly capacitor (elec inside poly; poly enc of elec >= 5 lambda)
    put("poly", 42.00, 15.00, 6.00, 6.00)
    top.shapes(ly.layer(56, 0)).insert(  # elec
        pya.Box(pya.DBox(43.65, 16.65, 46.35, 19.35).to_itype(dbu)))

    # net labels (text layer 64/0) — LVS net names
    tlay = ly.layer(64, 0)
    def label(s, x, y):
        top.shapes(tlay).insert(pya.Text(s, pya.Trans(pya.DPoint(x, y).to_itype(dbu))))

    label("IN", 10.95, 13.50)     # nmos gate poly overhang
    label("NSS", 9.60, 12.60)     # nmos source metal2
    label("NOUT", 12.60, 12.60)   # nmos drain metal2
    label("IN", 23.40, 20.85)     # pmos gate poly overhang
    label("PVDD", 22.05, 23.85)   # pmos source metal2
    label("POUT", 24.75, 23.85)   # pmos drain metal2
    label("VDD", 29.70, 29.10)    # n-well tap metal1
    label("VSS", 35.70, 10.50)    # p-substrate tap metal1

    # ---- deliberate violations (skip with CLEAN=1) -------------------------
    if not os.environ.get("CLEAN"):
        put("poly", 39.60, 9.90, 0.45, 3.00)       # V1: poly width < 2 lambda
        put("poly", 41.70, 9.90, 0.90, 1.05)       # V2: poly spacing 0.30 < 3 lambda
        put("poly", 42.90, 9.90, 0.90, 1.05)
        put("metal1", 44.40, 9.90, 0.60, 2.10)     # V3: metal1 width < 3 lambda
        put("metal1", 46.20, 9.90, 1.05, 1.05)     # V4: metal1 spacing 0.30 < 3 lambda
        put("metal1", 47.55, 9.90, 1.05, 1.05)
        put("cc", 49.50, 9.90, 0.60, 0.60)         # V5: stray cc on field
        put("via", 51.30, 9.90, 0.60, 0.60)        # V6: via not on metal1
        put("active", 53.10, 9.90, 0.45, 2.10)     # V7: active width < 3 lambda
        put("nselect", 52.35, 9.30, 2.10, 3.30)
        put("metal2", 55.07, 9.90, 1.05, 1.05)     # V8: off-grid edge (0.07)
        put("nselect", 57.00, 9.90, 0.45, 2.10)    # V9: nselect width < 2 lambda
        put("active", 59.10, 9.90, 1.20, 1.20)     # V10: active encloses cc by 0.15 < 1 lambda
        put("cc", 59.25, 9.90, 0.60, 0.60)
        put("poly", 60.90, 9.90, 1.05, 2.10)       # V11: poly encloses cp by 0.225 < 1 lambda
        put("cc", 61.05, 9.90, 0.60, 0.60)
        put("metal1", 62.70, 9.90, 0.90, 2.10)     # V12: metal1 encloses via by 0.15 < 1 lambda
        put("via", 62.85, 9.90, 0.60, 0.60)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    ly.write(out)
    print(f"wrote {out} cells={ly.cells()}")


if __name__ == "__main__":
    main()
