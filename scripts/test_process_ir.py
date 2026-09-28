#!/usr/bin/env python3
"""Validate normalized process/device/netlist contracts across profiles."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from common.devices.netlist import validate_netlist_contracts  # noqa: E402
from common.process_ir import load_process, profile_names  # noqa: E402


def main() -> int:
    profiles = profile_names(ROOT)
    assert profiles, "no process profiles discovered"
    processes = {name: load_process(name, ROOT) for name in profiles}

    for name, process in processes.items():
        assert process.meta.get("name") == name
        assert process.layers, f"{name}: no normalized layers"
        if process.capabilities.pex_runtime:
            assert process.capabilities.pex_topology
            assert process.pex_doc.get("topology", {}).get("magic_device_class") == "mosfet"
        if process.capabilities.xschem:
            assert process.symbols
            assert process.xschem_smoke_doc

    ls1u = processes["ls1u"]
    contracts = validate_netlist_contracts(ls1u)
    assert {contract.name for contract in contracts} == {"LV1UNMOS", "LV1UPMOS"}
    assert all(contract.terminals == ("d", "g", "s", "b") for contract in contracts)
    assert all(contract.symmetry_groups == (("d", "s"),) for contract in contracts)
    assert all(contract.lvs_permutable == (("d", "s"),) for contract in contracts)
    assert ls1u.parasitic_ownership["diffusion_sheet_resistance"] == "pex"
    ami06_contracts = validate_netlist_contracts(processes["ami06"])
    assert {contract.name for contract in ami06_contracts} == {"ami06N", "ami06P"}
    assert all(contract.representation == "primitive" for contract in ami06_contracts)
    pmos_model = ls1u.model_ir("pmos_core")
    assert pmos_model.simulation_name == "LV1UPMOS"
    assert pmos_model.fit_parameter("vth0_v") == -0.6
    assert pmos_model.evidence.status == "partial_characterization"
    openrule_model = processes["openrule1um"].model_ir("or1_nmos")
    assert openrule_model.capabilities.simulator
    assert openrule_model.authority == "simulation"

    print(f"ProcessIR contract checks: PASS ({len(processes)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
