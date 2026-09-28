"""Emit synthetic canonical geometry for the OpenRule1um legality test.

This fixture deliberately does not read the upstream Basic GDS.  It uses the
portable SCMOS(lambda=0.5) envelope, the two target well-side tightenings, and
native three-metal routing geometry as raw layer rectangles.  The target DRC,
not nominal library geometry, decides legality.
"""

from __future__ import annotations

import os
from pathlib import Path

import pya

OUT = Path(os.environ.get("OUT", "/tmp/openrule1um_portable.gds"))
DBU = 0.001
WELL_GAP = float(os.environ.get("WELL_GAP", "5.0"))
NWL_NDIFF_GAP = float(os.environ.get("NWL_NDIFF_GAP", "3.0"))
WELL_LEFTS = (21.0, 21.0 + 20.0 + WELL_GAP)

LY = {
    "nwell": 1,
    "diff": 3,
    "hpol": 6,
    "res": 15,
    "cap": 16,
    "dio": 17,

    "pol": 5,
    "cnt": 7,
    "ml1": 8,
    "via1": 9,
    "ml2": 10,
    "via2": 11,
    "ml3": 12,
    "parea": 18,
    "narea": 19,
    "dm_dcn": 101,
    "dm_pcn": 102,
    "dm_via1": 105,
    "dm_via2": 106,
}

layout = pya.Layout()
layout.dbu = DBU
top = layout.create_cell("openrule1um_portable")


def rect(layer: str, x1: float, y1: float, x2: float, y2: float) -> None:
    layer_index = layout.layer(LY[layer], 0)
    top.shapes(layer_index).insert(
        pya.Box(pya.DBox(x1, y1, x2, y2).to_itype(DBU))
    )


def contact(cx: float, cy: float, marker: str) -> None:
    rect(marker, cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0)
    rect("cnt", cx - 0.5, cy - 0.5, cx + 0.5, cy + 0.5)
    rect("ml1", cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5)


def via(cx: float, cy: float, marker: str, lower: str, upper: str) -> None:
    rect(marker, cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0)
    cut = "via1" if marker == "dm_via1" else "via2"
    rect(cut, cx - 0.5, cy - 0.5, cx + 0.5, cy + 0.5)
    rect(lower, cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5)
    rect(upper, cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5)


# NMOS outside the left edge of nwell-1.
left_active_right = WELL_LEFTS[0] - NWL_NDIFF_GAP
left_active_left = left_active_right - 8.0
rect("diff", left_active_left, 40.0, left_active_right, 46.0)
rect("narea", left_active_left - 1.0, 39.0, left_active_right + 1.0, 47.0)
rect("pol", left_active_left + 3.5, 39.0, left_active_left + 4.5, 47.0)
contact(left_active_left + 1.5, 43.0, "dm_dcn")
contact(left_active_left + 6.5, 43.0, "dm_dcn")

# Two nwell islands; WELL_GAP is the target 5um spacing tightening.
for left in WELL_LEFTS:
    rect("nwell", left, 35.0, left + 20.0, 55.0)

# PMOS in each well; dimensions meet the SCMOS(lambda=0.5) envelope.
for left in WELL_LEFTS:
    rect("diff", left + 6.0, 42.0, left + 14.0, 48.0)
    rect("parea", left + 5.0, 41.0, left + 15.0, 49.0)
    rect("pol", left + 9.5, 41.0, left + 10.5, 49.0)
    contact(left + 7.5, 45.0, "dm_dcn")
    contact(left + 12.5, 45.0, "dm_dcn")

# NMOS outside the right edge of nwell-2; exact target NWL-NDIFF gap.
right_active_left = WELL_LEFTS[1] + 20.0 + NWL_NDIFF_GAP
right_active_right = right_active_left + 8.0
rect("diff", right_active_left, 40.0, right_active_right, 46.0)
rect("narea", right_active_left - 1.0, 39.0, right_active_right + 1.0, 47.0)
rect("pol", right_active_left + 3.5, 39.0, right_active_left + 4.5, 47.0)
contact(right_active_left + 1.5, 43.0, "dm_dcn")
contact(right_active_left + 6.5, 43.0, "dm_dcn")

# Field-poly contact, kept away from diffusion and MOS poly.
rect("pol", 5.0, 25.0, 9.0, 29.0)
contact(7.0, 27.0, "dm_pcn")
# HPOL option: a legal 20-80um poly edge, separate from MOS and contacts.
rect("hpol", 5.0, 65.0, 95.0, 105.0)
rect("pol", 15.0, 70.0, 85.0, 100.0)
# Wide-metal conditional checks with legal marker enclosures.
rect("diff", 86.0, 40.0, 94.0, 46.0)
rect("narea", 85.0, 39.0, 95.0, 47.0)
rect("ml1", 80.0, 35.0, 100.0, 55.0)
contact(87.5, 43.0, "dm_dcn")
contact(92.5, 43.0, "dm_dcn")
rect("ml2", 80.0, 10.0, 100.0, 30.0)
rect("ml3", 80.0, 10.0, 100.0, 30.0)
via(90.0, 20.0, "dm_via2", "ml2", "ml3")


# Native three-metal routing geometry; no upstream nominal GDS is consulted.
via(10.0, 10.0, "dm_via1", "ml1", "ml2")
via(20.0, 10.0, "dm_via2", "ml2", "ml3")

# Expand the top-cell bbox without adding process-layer geometry.
background = layout.layer(200, 0)
top.shapes(background).insert(
    pya.Box(pya.DBox(0.0, 0.0, 100.0, 100.0).to_itype(DBU))
)

OUT.parent.mkdir(parents=True, exist_ok=True)
layout.write(str(OUT))
print(f"wrote {OUT} cells={layout.cells()} dbu={layout.dbu}")
