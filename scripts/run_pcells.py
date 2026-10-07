#!/usr/bin/env python3
"""Generate a profile's analog PCell regression layout.

Run inside a KLayout-enabled environment, normally from the LibreLane shell:

  SILICONCRAFT_PROFILE=ami06 SILICONCRAFT_OUTPUT=build/pcells/ami06.gds \
    klayout -b -r scripts/run_pcells.py


For module-gated profiles, `SILICONCRAFT_VARIANT` selects the process variant
(for example, `C35B4C3` for `ams_c35`).
The generated layout is a fixture, not a hand-authored PDK artifact.  It
contains one instance of every analog PCell declared by the selected profile,
spaced apart so that DRC can inspect each geometry independently.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from common.gds_layer_map import (
    auxiliary_stream,
    validate_layout_layer_pairs,
    validate_profile_gds_map,
)
from common.pcells.scmos import Profile, register_profile


def db(value: float, dbu: float) -> int:
    return int(round(value / dbu))


def main(argv=None):
    del argv
    profile_name = os.environ.get("SILICONCRAFT_PROFILE", "ami06")
    variant = os.environ.get("SILICONCRAFT_VARIANT") or None
    output_name = os.environ.get("SILICONCRAFT_OUTPUT")

    profile_dir = ROOT / "profiles" / profile_name
    profile = Profile(profile_dir, variant=variant)
    validate_profile_gds_map(profile_dir)
    suffix = f"_{variant}" if variant is not None else ""
    library_name = f"siliconcraft_{profile_name}{suffix}"
    register_profile(profile_dir, library_name, variant=variant)

    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell(f"{profile_name}_analog_pcell_test")
    # Legacy profiles use the historical substrate-universe helper.  Mapped
    # profiles must not emit an unregistered layer/datatype pair.
    substrate_stream = auxiliary_stream(profile_dir, "substrate_universe")
    if substrate_stream is not None:
        top.shapes(layout.layer(*substrate_stream)).insert(
            pya.Box(db(-20.0, layout.dbu), db(-20.0, layout.dbu),
                    db(220.0, layout.dbu), db(20.0, layout.dbu))
        )

    # Seed the regression set with the base PCells, but only those the profile
    # actually declares in pcells.yaml.  Profiles without a contract register
    # nothing, and layout.create_cell() returns None for an unregistered name.
    base_variants = (
        ("nmos", {"nf": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}),
        ("pmos", {"nf": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}),
        ("ntap", {"rows": 1, "columns": 1}),
        ("ptap", {"rows": 1, "columns": 1}),
    )
    variants = [
        (name, params) for name, params in base_variants if name in profile.pcells
    ]
    for name, spec in profile.pcells.items():
        if name in {cell_name for cell_name, _ in variants}:
            continue
        params = spec.get("parameters", {})
        defaults = {
            key: value.get("default")
            for key, value in params.items()
            if isinstance(value, dict) and "default" in value
        }
        if spec.get("kind") == "mos4":
            variants.append((name, defaults))
        elif spec.get("kind") == "via":
            variants.append((name, {"rows": 2, "columns": 2}))
        elif spec.get("kind") in {"resistor", "capacitor", "diode"}:
            variants.append((name, defaults))
    requested = os.environ.get("SILICONCRAFT_PCELLS")
    if requested is not None:
        selected = {name.strip() for name in requested.split(",") if name.strip()}
        available = {name for name, _ in variants}
        unknown = selected - available
        if not selected or unknown:
            raise ValueError(
                "SILICONCRAFT_PCELLS must name available PCells; "
                f"empty={not selected}, unknown={sorted(unknown)}"
            )
        variants = [variant for variant in variants if variant[0] in selected]

    x = 0.0
    for cell_name, params in variants:
        cell = layout.create_cell(cell_name, library_name, params)
        top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(db(x, layout.dbu), 0)))
        x += 30.0

    output = Path(
        output_name or (ROOT / "build" / "pcells" / f"{profile_name}.gds")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    validate_layout_layer_pairs(layout, profile_dir)
    layout.write(str(output))
    print(f"[run_pcells] profile={profile_name} cells={len(variants)} output={output}")
    print(f"[run_pcells] layers={layout.layer_infos()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
