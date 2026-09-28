#!/usr/bin/env python3
"""Focused regression checks for LS1u PEX generation and unit boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import gen_ls1u_pex as gen  # noqa: E402
import yamlish  # noqa: E402


PEX_DIR = ROOT / "profiles" / "ls1u" / "pex"
MANIFEST_PATH = PEX_DIR / "manifest.yaml"


def extract_block(text: str) -> str:
    lines = text.splitlines()
    start = lines.index("extract")
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "end")
    return "\n".join(lines[start : end + 1])


def assert_no_pex_directives(block: str) -> None:
    forbidden = ("resist ", "contact ", "areacap ", "perimc ", "overlap ")
    for line in block.splitlines():
        stripped = line.strip()
        assert not stripped.startswith(forbidden), line


def main() -> int:
    manifest = yamlish.load(MANIFEST_PATH.read_text())
    assert manifest["default"] == "none"
    assert manifest["physical"]["lambda_um"] == 0.5
    dry = manifest["profiles"]["ls1u_hkust_dry_est"]
    wet = manifest["profiles"]["ls1u_hkust_wet_est"]
    assert dry["process_recipe_url"].endswith("steps_dry.yaml")
    assert wet["process_recipe_url"].endswith("steps_wet.yaml")
    assert dry["stack"]["metal1"] != wet["stack"]["metal1"]
    assert wet["metal_sheet_resistance_ohm_sq"] == {}
    assert gen.sheet_to_magic_mohm("0.19") == 190
    assert gen.sheet_to_magic_mohm("0.22") == 220
    assert gen.area_cap_to_magic_af_per_lambda2("0.030", "0.5") == 8
    assert gen.edge_cap_to_magic_af_per_lambda("0.020", "0.5") == 10

    none_block = extract_block((PEX_DIR / "none.tech").read_text())
    assert manifest["topology"]["magic_device_class"] == "msubcircuit"
    assert manifest["topology"]["magic_terminal_order"] == "drain,gate,source,bulk"
    assert (
        "device msubcircuit LV1UNMOS nfet 2 ndiff,ndc ndiff,ndc,active "
        "pwell vss w=W l=L p1=PD p2=PS"
    ) in none_block
    assert (
        "device msubcircuit LV1UPMOS pfet 2 pdiff,pdc pdiff,pdc,active "
        "nwell vdd w=W l=L p1=PD p2=PS"
    ) in none_block

    dry_block = extract_block((PEX_DIR / "ls1u_hkust_dry_est.tech").read_text())
    for line in (
        "resist metal1 190",
        "resist metal2 220",
        "resist metal3 220",
        "overlap metal2 metal1 8",
        "overlap metal3 metal2 8",
    ):
        assert line in dry_block, line
    assert "contact " not in dry_block
    assert "diffusion, junction, and substrate capacitance" in dry["missing_measurements"]

    wet_block = extract_block((PEX_DIR / "ls1u_hkust_wet_est.tech").read_text())
    assert_no_pex_directives(wet_block)
    assert "wet-stack M1/M2/M3 sheet resistance" in wet["missing_measurements"]

    legacy_block = extract_block((PEX_DIR / "scmos_legacy.tech").read_text())
    assert "resist metal1 60" in legacy_block
    assert "contact pc 4 16210" in legacy_block
    assert "fetresis nfet linear 9700" in legacy_block

    cif_input = (ROOT / "profiles/ls1u/reference/magic/cifin-ls1u.gen").read_text()
    assert "calma CAA 43 *" in cif_input
    assert "calma CMF 49 *" in cif_input
    assert "calma CMT 62 *" in cif_input

    print("LS1u PEX profile checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
