#!/usr/bin/env python3
"""Generate a profile's analog PCell regression layout.

Run inside a KLayout-enabled environment, normally from the LibreLane shell:

  SILICONCRAFT_PROFILE=ami06 SILICONCRAFT_OUTPUT=build/pcells/ami06.gds \
    klayout -b -r scripts/run_pcells.py

The generated layout is a fixture, not a hand-authored PDK artifact.  It
contains one instance of every AMI06-supported analog PCell, spaced apart so
that DRC can inspect each geometry independently.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from common.pcells.scmos import Profile, register_profile


def db(value: float, dbu: float) -> int:
    return int(round(value / dbu))


def main(argv=None):
    del argv
    profile_name = os.environ.get("SILICONCRAFT_PROFILE", "ami06")
    output_name = os.environ.get("SILICONCRAFT_OUTPUT")

    profile_dir = ROOT / "profiles" / profile_name
    profile = Profile(profile_dir)
    library_name = f"siliconcraft_{profile_name}"
    register_profile(profile_dir, library_name)

    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell(f"{profile_name}_analog_pcell_test")
    # Extend the top-cell universe so pBulk complement checks do not terminate
    # at the first or last PCell geometry.
    top.shapes(layout.layer(90, 0)).insert(
        pya.Box(db(-20.0, layout.dbu), db(-20.0, layout.dbu),
                db(220.0, layout.dbu), db(20.0, layout.dbu))
    )


    variants = [
        ("nmos", {"fingers": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}),
        ("pmos", {"fingers": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}),
        ("ntap", {"rows": 1, "columns": 1}),
        ("ptap", {"rows": 1, "columns": 1}),
        ("via12", {"rows": 2, "columns": 2}),
        ("via23", {"rows": 2, "columns": 2}),
        ("cap_elec", {"width_um": 6.3, "height_um": 6.3}),
    ]
    x = 0.0
    for cell_name, params in variants:
        cell = layout.create_cell(cell_name, library_name, params)
        top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(db(x, layout.dbu), 0)))
        x += 30.0

    output = Path(
        output_name or (ROOT / "build" / "pcells" / f"{profile_name}.gds")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output))
    print(f"[run_pcells] profile={profile_name} cells={len(variants)} output={output}")
    print(f"[run_pcells] layers={layout.layer_infos()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
