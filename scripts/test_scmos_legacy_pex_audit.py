#!/usr/bin/env python3
"""Validate the source boundary for non-TSMC SCMOS PEX research."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import yamlish  # noqa: E402


REQUIRED = {
    "sheet_resistance",
    "contact_and_via_resistance",
    "area_capacitance",
    "overlap_capacitance",
    "perimeter_and_sidewall_capacitance",
    "device_and_model_ownership",
}
EXPECTED = {
    "ami06",
    "hp06",
    "ami16",
    "orbit20_reference",
    "ami_abn12_reference",
    "hp_cmos34_reference",
    "ami_cwl_reference",
    "hp_cmos26b_reference",
    "hp_cmos26g_reference",
    "hp_cmos26g_subm_reference",
    "hp_mos14tb_reference",
    "hp_mos14tb_subm_reference",
    "hp_gmos10qa_reference",
    "hp_gmos10qa_subm_reference",
}


def main() -> int:
    path = ROOT / "schema" / "scmos_legacy_pex_audit.yaml"
    audit = yamlish.load(path.read_text())
    assert audit["scope"] == "non_tsmc_only"
    assert set(audit["required_parameter_families"]) == REQUIRED
    assert audit["source_policy"]["exact_run_pair_required"] is True
    assert audit["source_policy"]["model_and_rc_must_share_run"] is True

    profiles = {entry["profile"]: entry for entry in audit["profiles"]}
    assert set(profiles) == EXPECTED
    assert not (set(profiles) & set(audit["tsmc_boundary"]["profiles"]))

    for name, entry in profiles.items():
        supplied = set(entry["supplied_parameter_families"])
        assert supplied or entry.get("missing_parameter_families"), name
        assert supplied <= REQUIRED, (name, supplied - REQUIRED)
        assert entry["source_records"], name
        if name in {"ami06", "hp06", "ami16"}:
            assert entry["source_manifest"].startswith("profiles/")
            assert entry["status"].startswith("active_")
        else:
            assert entry["status"] == "historical_reference_blocked", name
            assert entry["blockers"], name

    assert audit["tsmc_boundary"]["pex_status"] == "deferred"
    print("Non-TSMC SCMOS PEX audit: PASS (3 active source references + 11 historical targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
