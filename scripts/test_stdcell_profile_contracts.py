#!/usr/bin/env python3
"""Exercise the fixed-height stdcell contract for every supported profile."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.stdcell.netlist import parse_spice  # noqa: E402
from common.stdcell.planner import generate_candidates  # noqa: E402
from common.stdcell.process import StdcellProcess  # noqa: E402


PROFILES = {
    "ami06": "two_metal_classic",
    "ami16": "two_metal_classic",
    "hp06": "three_metal_classic",
    "cnm25": "two_metal_classic",
    "ams_c35": "three_metal_classic",
}


def inverter(process: StdcellProcess):
    width = max(
        float(process.ir.meta.get("min_width_um", 0.0)),
        process.tech.active_min,
        1.5,
    )
    length = max(process.lmin_um, process.tech.poly_min)
    models = process.model_names
    return parse_spice(
        "\n".join(
            (
                "* siliconcraft inputs: A",
                "* siliconcraft outputs: Y",
                "* siliconcraft supplies: VDD VSS",
                ".subckt inv A Y VDD VSS",
                f"M0 Y A VSS VSS {models['n']} W={width:g}u L={length:g}u",
                f"M1 Y A VDD VDD {models['p']} W={width:g}u L={length:g}u",
                ".ends inv",
            )
        )
    )


def main() -> int:
    for name, architecture in PROFILES.items():
        process = StdcellProcess.load(name, ROOT)
        circuit = inverter(process)
        candidates = generate_candidates(
            circuit,
            process,
            architecture=architecture,
            max_candidates=1,
        )
        assert candidates[0].profile == name
        assert candidates[0].height_um == process.site_height_um
        assert candidates[0].constraints["rail_contract"]["fixed_height"] is True
        if architecture.startswith("three_metal"):
            assert process.has_layer("M3")
            assert candidates[0].feedthrough_layer == "M3"
        else:
            assert not architecture.startswith("three_metal")
            assert candidates[0].feedthrough_layer == "M2"
    print(f"Stdcell profile contracts: PASS ({len(PROFILES)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
