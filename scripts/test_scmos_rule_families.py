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

EXPECTED_DEEP = {
    "tsmc025_deep": ("TSMC_CMOS025_DEEP", "SCN5M_DEEP", 0.12, "tsmc_03d.tf", "tsmc25d"),
    "tsmc018_deep": ("TSMC_CMOS018_DEEP", "SCN6M_DEEP", 0.09, "tsmc_02d.tf", "tsmc18d"),
}


def main() -> int:
    matrix = yamlish.load((ROOT / "schema/scmos_process_matrix.yaml").read_text())
    assert matrix["schema_version"] == 1
    assert matrix["rule_families"] == ["scmos", "scmos_subm", "scmos_deep"]

    entries = {entry["name"]: entry for entry in matrix["profiles"]}
    assert set(entries) == {"ami16", "ami06", "hp06", "cnm25", "tr1um", "ams_c35", "xh035", "xh018", *EXPECTED_TSMC, *EXPECTED_DEEP}
    assert entries["ami16"]["rule_family"] == "scmos"
    assert entries["ami06"]["rule_family"] == "scmos_subm"
    assert entries["hp06"]["rule_family"] == "scmos_subm"
    assert entries["cnm25"]["rule_family"] == "scmos"
    assert entries["cnm25"]["lambda_um"] == 1.5
    assert entries["cnm25"]["source_process"] == "CNM25"
    assert entries["ams_c35"]["rule_family"] == "scmos_subm"
    assert entries["ams_c35"]["lambda_um"] == 0.2
    assert entries["ams_c35"]["mosis_code"] == "SCN4ME_SUBM"
    assert entries["ams_c35"]["source_process"] == "C35B4C3"
    assert entries["tr1um"]["rule_family"] == "scmos"
    assert entries["tr1um"]["lambda_um"] == 0.5
    assert entries["tr1um"]["source_process"] == "TR_1UM"

    for name, (source, mosis, lam, techfile) in EXPECTED_TSMC.items():
        entry = entries[name]
        assert entry["source_process"] == source
        assert entry["mosis_code"] == mosis
        assert entry["lambda_um"] == lam
        assert entry["techfile"] == techfile
        assert entry["rule_family"] == "scmos_subm"
        assert entry["deep_n_well_layer"] is None
        assert "DEEP" not in source
        assert "DEEP" not in mosis
        assert "d.tf" not in techfile

    for name, (source, mosis, lam, techfile, prefix) in EXPECTED_DEEP.items():
        entry = entries[name]
        assert entry["source_process"] == source
        assert entry["mosis_code"] == mosis
        assert entry["lambda_um"] == lam
        assert entry["techfile"] == techfile
        assert entry["model_prefix"] == prefix
        assert entry["rule_family"] == "scmos_deep"
        assert entry["deep_n_well_layer"] is None
        assert entry["pex_status"] == "deferred"

    forbidden = matrix["forbidden"]
    assert all(not values for values in forbidden.values())
    assert matrix["deep_rule_boundary"]["status"] == "explicit_source_backed_only"
    assert set(matrix["deep_rule_boundary"]["supported_profiles"]) == set(EXPECTED_DEEP)
    deep_rules = {
        name: yamlish.load((ROOT / "profiles" / name / "rules.yaml").read_text())["rules"]["deep_overrides"]
        for name in EXPECTED_DEEP
    }
    overrides = {
        name: {entry["id"]: entry for entry in entries}
        for name, entries in deep_rules.items()
    }
    assert overrides["tsmc025_deep"]["26.3"]["value_lambda"] == 2.0
    assert overrides["tsmc018_deep"]["26.1"]["value_lambda"] == 3.0
    assert overrides["tsmc018_deep"]["26.1"]["condition"] == "metal6"
    assert overrides["tsmc018_deep"]["26.3"]["value_lambda"] == 1.0
    assert overrides["tsmc018_deep"]["26.3"]["condition"] == "metal6"

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
    # Regression guard: GDS 38 / DEEP_N_WELL was injected without a source and
    # must not return. See scripts/parse_cdk_layers.py for the evidence.
    assert not [layer for layer in parsed["layers"] if layer["name"] == "DEEP_N_WELL"]
    assert parsed["meta"]["rule_family"] == "scmos_subm"
    deep_parsed = build_profile(
        "tsmc025_deep",
        "TSMC_CMOS025_DEEP",
        {
            "description": "test",
            "mosisCode": "SCN5M_DEEP",
            "deepRules": True,
            "lambda": "0.12",
            "gridRes": "0.06",
            "minL": 0.24,
            "minW": 0.36,
            "fetModelPrefix": "tsmc25d",
        },
        {},
        {"nwell": [(42, 0)]},
        {"nwell": ["CWN"]},
    )
    assert deep_parsed["meta"]["rule_family"] == "scmos_deep"
    assert not [layer for layer in deep_parsed["layers"] if layer["name"] == "DEEP_N_WELL"]
    assert rule_family_for({"deepRules": True}, "TSMC_CMOS025_DEEP") == "scmos_deep"
    validate_rule_family(
        {
            "process": "TSMC_CMOS025_DEEP",
            "mosis_code": "SCN5M_DEEP",
            "rule_family": "scmos_deep",
        },
        ROOT / "synthetic-layers.yaml",
    )
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
        assert "require meta.rule_family=scmos_deep" in str(exc)
    else:
        raise AssertionError("SCMOS_DEEP accepted under scmos_subm")
    try:
        validate_rule_family(
            {
                "process": "TSMC_CMOS025",
                "mosis_code": "SCN5M_SUBM",
                "rule_family": "scmos_deep",
            },
            ROOT / "synthetic-layers.yaml",
        )
    except ProcessIRError as exc:
        assert "requires a DEEP process" in str(exc)
    else:
        raise AssertionError("scmos_deep accepted without DEEP identifiers")

    for name in ("ami16", "ami06", "hp06"):
        process = load_process(name, ROOT)
        assert process.rule_family == entries[name]["rule_family"]
        assert "DEEP" not in str(process.meta.get("mosis_code", ""))
        if process.meta.get("features", {}).get("metal3Available"):
            via2 = next(layer for layer in process.layers_doc["layers"] if layer["name"] == "via2")
            assert via2["available"] is True, (name, "via2")
    for name in EXPECTED_DEEP:
        process = load_process(name, ROOT)
        assert process.rule_family == "scmos_deep"
        assert "DEEP" in str(process.meta.get("mosis_code", ""))
        if process.meta.get("features", {}).get("metal3Available"):
            via2 = next(layer for layer in process.layers_doc["layers"] if layer["name"] == "via2")
            assert via2["available"] is True, (name, "via2")

    print(f"SCMOS rule-family matrix: PASS ({len(EXPECTED_TSMC)} TSMC SUBM + {len(EXPECTED_DEEP)} DEEP targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
