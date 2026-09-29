#!/usr/bin/env python3
"""Exercise the fixed-height stdcell contract for every supported profile."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile

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
    "tr1um": "two_metal_classic",
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


def xh_lv_smoke() -> None:
    """Exercise XH LV adapters without promoting either profile to support."""
    cases = (
        ("xh035", 0.5, 0.5, 0.525),
        ("xh018", 0.22, 0.23, 0.27),
    )
    with tempfile.TemporaryDirectory(prefix="siliconcraft-xh-stdcell-") as tmp:
        for name, active_min, metal_width, metal_spacing in cases:
            overlay = Path(tmp) / name
            shutil.copytree(ROOT / "profiles" / name, overlay)
            bindings = overlay / "devices" / "bindings.yaml"
            bindings.write_text(
                bindings.read_text().replace(
                    "../../../common/devices/canonical/mos.yaml",
                    str(ROOT / "common/devices/canonical/mos.yaml"),
                )
            )
            (overlay / "cells.yaml").write_text(
                f"""schema_version: 1
profile: {name}
stdcell:
  site_height_um: 10.5
  row_heights_um:
    n: 4.0
    p: 5.0
  row_gap_um: 0.5
  rail_margin_um: 0.5
  tap_policy: self_tapped
  tapcell:
    required: false
  orientations:
    even_row: R0
    odd_row: MX
    legal:
      - R0
      - MX
"""
            )
            process = StdcellProcess.load(overlay, ROOT)
            assert process.tech.active_min == active_min
            assert process.metal_width_um("M1") == metal_width
            assert process.metal_spacing_um("M1") == metal_spacing
            candidates = generate_candidates(
                inverter(process),
                process,
                architecture="two_metal_classic",
                max_candidates=1,
            )
            assert candidates[0].profile == name
            assert candidates[0].constraints["rail_contract"]["fixed_height"] is True

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
        if name == "tr1um":
            assert candidates[0].row_geometry["n"]["active"][0]["layer"] == "nactive"
            assert candidates[0].row_geometry["p"]["active"][0]["layer"] == "pactive"
            assert candidates[0].row_geometry["n"]["select"][0]["layer"] == "nselect"
            assert candidates[0].row_geometry["p"]["select"][0]["layer"] == "pselect"
        if architecture.startswith("three_metal"):
            assert process.has_layer("M3")
            assert candidates[0].feedthrough_layer == "M3"
        else:
            assert not architecture.startswith("three_metal")
            assert candidates[0].feedthrough_layer == "M2"
    xh_lv_smoke()
    print(
        f"Stdcell profile contracts: PASS ({len(PROFILES)} supported profiles; "
        "xh035/xh018 LV adapter smoke)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
