#!/usr/bin/env python3
"""Validate SCMOS option-device support boundaries for materialized profiles."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.process_ir import load_process, profile_names  # noqa: E402
from common.scmos_extensions import EXTENSION_IDS  # noqa: E402


def main() -> int:
    processes = {name: load_process(name, ROOT) for name in profile_names(ROOT)}
    assert "electrode_contact" in EXTENSION_IDS
    expected = set(EXTENSION_IDS)

    for name, process in processes.items():
        statuses = process.scmos_extensions
        assert set(statuses) == expected, name
        assert all(status["family"] == family for family, status in statuses.items())
        assert all(status["state"] in {"supported", "partial", "blocked", "unavailable"}
                   for status in statuses.values())
        assert not statuses["scnpc_poly_cap"]["enabled"], name
        assert not statuses["buried_ccd"]["enabled"], name
        assert not statuses["mems"]["enabled"], name

    ami06 = processes["ami06"].scmos_extensions
    assert ami06["electrode_capacitor"]["state"] == "supported"
    assert ami06["electrode_transistor"]["state"] == "partial"
    assert ami06["electrode_contact"]["state"] == "supported"

    ami16 = processes["ami16"].scmos_extensions
    assert ami16["electrode_transistor"]["state"] == "supported"
    npn = ami16["vertical_npn"]
    assert npn["enabled"] is True
    assert npn["state"] == "supported"
    assert npn["drc"] == "implemented"
    assert npn["lvs"] == "implemented"

    hp06 = processes["hp06"].scmos_extensions
    assert hp06["linear_capacitor"]["state"] == "supported"
    assert hp06["linear_capacitor"]["drc"] == "implemented"
    assert hp06["silicide_block"]["state"] == "partial"
    assert hp06["silicide_block"]["drc"] == "lambda_only"
    assert hp06["silicide_block"]["lvs"] == "recipe"

    for name in ("tr1um", "xh018", "xh035"):
        hv = processes[name].scmos_extensions["hvcmos"]
        assert hv["enabled"] is True
        assert hv["state"] in {"partial", "blocked"}

    print(f"SCMOS device-extension contracts: PASS ({len(processes)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
