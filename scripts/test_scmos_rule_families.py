#!/usr/bin/env python3
"""Validate the normalized SCMOS rule-family and TSMC target contracts."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402
from common.process_ir import (  # noqa: E402
    ProcessIRError,
    load_process,
    validate_rule_family,
)
from scripts.parse_cdk_layers import build_profile, rule_family_for  # noqa: E402


EXPECTED_TSMC = {
    "tsmc035_4m2p": ("TSMC_CMOS035_4M2P", "SCN4ME_SUBM", 0.2, "tsmc_04_4m2p.tf"),
    "tsmc035_4m": ("TSMC_CMOS035_4M", "SCN4M_SUBM", 0.2, "tsmc_04_4m.tf"),
    "tsmc03": ("TSMC_CMOS025", "SCN5M_SUBM", 0.15, "tsmc_03.tf"),
    "tsmc02": ("TSMC_CMOS020", "SCN6M_SUBM", 0.1, "tsmc_02.tf"),
}


def main() -> int:
    matrix = yamlish.load((ROOT / "schema/scmos_process_matrix.yaml").read_text())
    assert matrix["schema_version"] == 1
    assert matrix["rule_families"] == ["scmos", "scmos_subm"]

    entries = {entry["name"]: entry for entry in matrix["profiles"]}
    assert set(entries) == {"ami16", "ami06", "hp06", *EXPECTED_TSMC}
    assert entries["ami16"]["rule_family"] == "scmos"
    assert entries["ami06"]["rule_family"] == "scmos_subm"
    assert entries["hp06"]["rule_family"] == "scmos_subm"

    for name, (source, mosis, lam, techfile) in EXPECTED_TSMC.items():
        entry = entries[name]
        assert entry["source_process"] == source
        assert entry["mosis_code"] == mosis
        assert entry["lambda_um"] == lam
        assert entry["techfile"] == techfile
        assert entry["rule_family"] == "scmos_subm"
        assert entry["deep_n_well_layer"] == "DEEP_N_WELL"
        assert "DEEP" not in source
        assert "DEEP" not in mosis
        assert "d.tf" not in techfile

    forbidden = matrix["forbidden"]
    assert set(forbidden["process_names"]) == {"TSMC_CMOS025_DEEP", "TSMC_CMOS018_DEEP"}
    assert set(forbidden["mosis_codes"]) == {"SCN5M_DEEP", "SCN6M_DEEP"}
    assert set(forbidden["techfiles"]) == {"tsmc_03d.tf", "tsmc_02d.tf"}
    assert set(forbidden["lambda_um"]) == {0.12, 0.09}

    parsed = build_profile(
        "tsmc03",
        "TSMC_CMOS025",
        {
            "description": "test",
            "mosisCode": "SCN5M_SUBM",
            "submicronRules": True,
            "lambda": "0.15",
            "gridRes": "0.075",
            "minL": 0.30,
            "minW": 0.45,
            "fetModelPrefix": "tsmc25",
        },
        {},
        {"nwell": [(42, 0)]},
        {"nwell": ["CWN"]},
    )
    deep_well = next(layer for layer in parsed["layers"] if layer["name"] == "DEEP_N_WELL")
    assert deep_well["gds"] == [{"layer": 38, "datatype": 0}]
    assert deep_well["cif"] == ["CDNW"]
    assert parsed["meta"]["rule_family"] == "scmos_subm"
    try:
        rule_family_for({"deepRules": True}, "TSMC_CMOS025_DEEP")
    except ValueError as exc:
        assert "SCMOS_DEEP" in str(exc)
    else:
        raise AssertionError("SCMOS_DEEP parser input was accepted")
    try:
        validate_rule_family(
            {
                "process": "TSMC_CMOS025_DEEP",
                "mosis_code": "SCN5M_DEEP",
                "rule_family": "scmos_subm",
            },
            ROOT / "synthetic-layers.yaml",
        )
    except ProcessIRError as exc:
        assert "SCMOS_DEEP" in str(exc)
    else:
        raise AssertionError("SCMOS_DEEP ProcessIR metadata was accepted")

    for name in ("ami16", "ami06", "hp06"):
        process = load_process(name, ROOT)
        assert process.rule_family == entries[name]["rule_family"]
        assert "DEEP" not in str(process.meta.get("mosis_code", ""))

    print(f"SCMOS rule-family matrix: PASS ({len(EXPECTED_TSMC)} TSMC SUBM targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
