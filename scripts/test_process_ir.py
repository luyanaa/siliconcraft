#!/usr/bin/env python3
"""Validate normalized process/device/netlist contracts across profiles."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from common.devices.netlist import validate_netlist_contracts  # noqa: E402
from common.process_ir import (  # noqa: E402
    HVCMOS_LAMBDA_OVERRIDE,
    ProcessIRError,
    load_process,
    profile_names,
    validate_hvcmos_lambda_override,
)


def main() -> int:
    profiles = profile_names(ROOT)
    assert profiles, "no process profiles discovered"
    processes = {name: load_process(name, ROOT) for name in profiles}

    for name, process in processes.items():
        assert process.meta.get("name") == name
        assert process.rule_family in {"scmos", "scmos_subm", "native"}
        assert "deep_rules" not in process.meta
        assert "submicron_rules" not in process.meta
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
    for name, expected_process in (("xh035", "XH035"), ("xh018", "XH018")):
        xh_contracts = {
            contract.device: contract
            for contract in validate_netlist_contracts(processes[name])
        }
        assert set(xh_contracts) == {
            "nmos_core",
            "pmos_core",
            "nmos_hv",
            "pmos_hv",
            "nmos_isolated",
            "pmos_isolated",
            "nldmos",
            "pldmos",
        }
        assert xh_contracts["nmos_hv"].canonical_variant == "nmos_hv_sym"
        assert xh_contracts["nmos_hv"].canonical_family == "mos4"
        assert xh_contracts["nmos_hv"].voltage_class == "hv"
        assert xh_contracts["nmos_hv"].gate_stack == "hv"
        assert xh_contracts["nmos_isolated"].isolation_domain == "deep_nwell_pwell"
        for variant in ("nldmos", "pldmos"):
            contract = xh_contracts[variant]
            assert contract.canonical_family == "asymmetric_mos4"
            assert contract.topology == "asymmetric_drift"
            assert contract.lvs_permutable == ()
            assert dict(contract.terminal_semantics)["d"].startswith("drain side")
            assert dict(contract.terminal_semantics)["s"].startswith("source side")
        assert xh_contracts["nldmos"].name == f"{name}Nldmos"
        assert xh_contracts["pldmos"].name == f"{name}Pldmos"
        assert processes[name].meta["process"] == expected_process
    assert processes["ami16"].rule_family == "scmos"
    assert processes["ami06"].rule_family == "scmos_subm"
    assert processes["hp06"].rule_family == "scmos_subm"
    assert processes["ls1u"].rule_family == "native"
    assert processes["openrule1um"].rule_family == "native"
    pmos_model = ls1u.model_ir("pmos_core")
    assert pmos_model.simulation_name == "LV1UPMOS"
    assert pmos_model.fit_parameter("vth0_v") == -0.6
    assert pmos_model.evidence.status == "partial_characterization"
    openrule_model = processes["openrule1um"].model_ir("or1_nmos")
    assert openrule_model.capabilities.simulator
    assert openrule_model.authority == "simulation"

    # --- HVCMOS lambda-rule override gate (SCMOS 7.2 has no HV rules) ------
    hv_rule = {"id": "HV.1", "family": "hvcmos", "layer": "nwell",
               "value_um": 7.2, "source": "scmos.tech.in 20.x", "note": "override-gated"}
    src = Path("rules.yaml")
    rules_with_hv = {"rules": {"spacing": [{"id": "1.2", "layer": "nwell",
                                            "value_um": 5.4}, hv_rule]}}
    try:
        validate_hvcmos_lambda_override(rules_with_hv, {"features": {}}, src)
    except ProcessIRError as exc:
        assert "hvcmos" in str(exc) and HVCMOS_LAMBDA_OVERRIDE in str(exc)
    else:
        raise AssertionError("hvcmos lambda rules accepted without override")
    # explicit opt-in feature permits the gated rules
    validate_hvcmos_lambda_override(
        rules_with_hv, {"features": {HVCMOS_LAMBDA_OVERRIDE: True}}, src
    )
    # override flag without any hvcmos rule is an error too
    try:
        validate_hvcmos_lambda_override(
            {"rules": {"width": [{"id": "3.1", "layer": "poly", "value_um": 0.6}]}},
            {"features": {HVCMOS_LAMBDA_OVERRIDE: True}},
            src,
        )
    except ProcessIRError as exc:
        assert "remove the flag" in str(exc)
    else:
        raise AssertionError("orphan hvcmosLambdaOverride flag accepted")
    # no profile may carry the flag or the family today (default = none)
    for name, process in processes.items():
        features = process.meta.get("features") or {}
        assert not features.get(HVCMOS_LAMBDA_OVERRIDE), f"{name}: hvcmos override on by default"

    print(f"ProcessIR contract checks: PASS ({len(processes)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
