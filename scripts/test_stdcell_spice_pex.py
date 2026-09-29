#!/usr/bin/env python3
"""Validate the SPICE/PEX preparation contract for a future stdcell generator."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402
from common.process_ir import load_process, profile_names  # noqa: E402


EXPECTED_PROFILES = {"ami06", "ami16", "hp06", "cnm25", "ams_c35", "ls1u", "openrule1um"}


def model_sections(path: Path) -> set[str]:
    return set(re.findall(r"^\.lib\s+(\S+)", path.read_text(), re.MULTILINE))


def assert_model_contract(
    name: str, process, spec: dict, canonical_terminals: list[str]
) -> None:
    spice = spec["spice"]
    model_path = ROOT / spice["library"]
    assert model_path.exists(), f"{name}: model library is missing: {model_path}"
    if spice["representation"] != "model_contract_only":
        assert spice["section"] in model_sections(model_path), (
            f"{name}: missing model section {spice['section']!r}"
        )

    for device in spice.get("devices", []):
        binding_name = device.get("binding")
        if binding_name is None:
            assert process.model_contract_doc, f"{name}: model-only device lacks model contract"
            continue
        binding = process.device(binding_name)
        assert binding.simulation_name == device["model"]
        assert binding.simulation_representation == spice["representation"]
        assert binding.simulation.get("prefix") == device["prefix"]
        assert binding.terminal_order == tuple(canonical_terminals)
        for source, target in (spice.get("parameter_map") or {}).items():
            assert binding.parameter_map.get(source) == target, (
                f"{name}/{binding_name}: parameter {source} does not map to {target!r}"
            )


def assert_pex_contract(name: str, process, spec: dict) -> None:
    pex = spec["pex"]
    manifest_path = ROOT / pex["manifest"]
    assert manifest_path.exists(), f"{name}: PEX manifest is missing"
    manifest = process.pex_doc
    selected = manifest.get("profiles", {}).get(pex["profile"])
    assert isinstance(selected, dict), f"{name}: missing PEX profile {pex['profile']!r}"
    assert selected.get("status") == pex.get("selected_profile_status", pex["status"])
    assert process.capabilities.pex_topology is pex["topology"]
    assert process.capabilities.pex_runtime is pex["runtime"]
    assert process.capabilities.pex_rc == pex["rc"]

    ownership = process.parasitic_ownership
    for key, value in (
        ("transistor_intrinsic_capacitance", "model"),
        ("gate_overlap_capacitance", "model"),
        ("junction_area_capacitance", "model"),
        ("junction_sidewall_capacitance", "model"),
        ("diffusion_sheet_resistance", "pex"),
        ("metal_interconnect_rc", "pex"),
    ):
        if name != "openrule1um":
            assert ownership.get(key) == value, f"{name}: ownership mismatch for {key}"


def main() -> int:
    matrix_path = ROOT / "schema/stdcell_spice_pex_readiness.yaml"
    matrix = yamlish.load(matrix_path.read_text())
    assert matrix["schema_version"] == 1
    assert matrix["kind"] == "stdcell_spice_pex_readiness"
    assert matrix["status"] == "preparation_contract"
    policy = matrix["policy"]
    assert policy["generator_implementation"] == "geometry_candidate_planner"
    assert policy["active_stdcell_profiles"] == [
        "ami06",
        "ami16",
        "hp06",
        "cnm25",
        "ams_c35",
    ]
    assert "simulator_model_library_and_section" in policy["required_inputs"]
    assert "lef" in policy["required_output_views"]
    assert "liberty" in policy["required_output_views"]

    canonical = matrix["spice_contract"]["canonical_mos_requirements"]
    assert canonical["terminal_order"] == ["d", "g", "s", "b"]
    assert canonical["parasitic_ownership"]["gate_intrinsic"] == "model"
    assert canonical["parasitic_ownership"]["diffusion_sheet_r"] == "pex"
    assert matrix["pex_contract"]["backend"] == "magic"
    assert "contact_and_via_resistance_evidence" in matrix["pex_contract"]["signoff_requirements"]

    profiles = matrix["profiles"]
    assert set(profiles) == EXPECTED_PROFILES
    assert set(profile_names(ROOT)) >= EXPECTED_PROFILES
    for name, spec in profiles.items():
        process = load_process(name, ROOT)
        assert_model_contract(name, process, spec, canonical["terminal_order"])
        assert_pex_contract(name, process, spec)
        blockers = set(spec["readiness"]["blockers"])
        assert blockers, f"{name}: no readiness blockers"
        assert spec["readiness"]["signoff"] == "blocked"

    ami06_blockers = set(profiles["ami06"]["readiness"]["blockers"])
    assert "native_pin_access_not_verified" in ami06_blockers
    for name in ("ami16", "hp06", "cnm25", "ams_c35", "ls1u", "openrule1um"):
        blockers = set(profiles[name]["readiness"]["blockers"])
        if name in {"ami16", "hp06", "cnm25", "ams_c35"}:
            assert "no_stdcell_geometry_contract" not in blockers, name
        else:
            assert "no_stdcell_geometry_contract" in blockers, name

    for name in ("ami06", "ami16", "hp06"):
        spec = profiles[name]
        assert spec["spice"]["corners"]["available"] == ["nominal"]
        assert set(spec["spice"]["corners"]["missing"]) == {
            "slow",
            "fast",
            "fnsp",
            "snfp",
        }
        assert spec["pex"]["status"] == "source_reference_partial"
        assert "contact_and_via_resistance" not in spec["pex"]["withheld_terms"]
        assert "contact_and_via_resistance" in spec["pex"]["pex_owned_terms"]
        assert "direct_junction_and_substrate_capacitance_mapping" in spec["pex"][
            "withheld_terms"
        ]

    ls1u = profiles["ls1u"]
    assert ls1u["spice"]["representation"] == "subckt"
    assert ls1u["spice"]["corners"]["contract"] == "absent"
    assert "unmeasured_ngate" in ls1u["spice"]["limitations"]
    assert ls1u["pex"]["status"] == "topology_only"

    openrule = profiles["openrule1um"]
    assert openrule["spice"]["representation"] == "model_contract_only"
    assert openrule["pex"]["status"] == "deferred"
    assert openrule["reference_cells"]["gds_top_cells"] == 45
    assert openrule["reference_cells"]["xschem_symbols"] == 38
    assert openrule["reference_cells"]["lef"] == "unavailable"
    assert openrule["reference_cells"]["liberty"] == "unavailable"

    print(f"Stdcell SPICE/PEX readiness: PASS ({len(EXPECTED_PROFILES)} profiles, preparation-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
