#!/usr/bin/env python3
"""Deterministic contract tests for the L0 RF workbench math."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.rf.workbench import (  # noqa: E402
    build_report,
    parse_lumped_elements,
    parse_spice_value,
    validate_rf_request,
)
from common.rf.policy import RFAnalysisPolicy  # noqa: E402


def main() -> int:
    assert parse_spice_value("1k") == 1000.0
    assert parse_spice_value("2.5p") == 2.5e-12

    elements, ignored = parse_lumped_elements(
        """* extracted fixture
R1 NET 0 10
R2 NET 0 20
C1 NET 0 1p
M1 D G S B ami06N
X1 A B C subckt
.end
"""
    )
    assert [element.name for element in elements] == ["R1", "R2", "C1"]
    assert ignored == Counter({"M": 1, "X": 1})

    manifest = {
        "flow": {"backend": "magic", "original_process": "AMI_C5N", "original_run": "N8BN"},
        "technology": {"scope": "L0 route RC"},
        "profiles": {"n8bn_reference": {"source": {"calibrated": False}}},
    }
    report = build_report(
        profile="ami06",
        pex_profile="n8bn_reference",
        manifest=manifest,
        elements=elements,
        ignored=ignored,
        frequencies_hz=[1.0e9, 3.0e9],
        die_width_um=5000.0,
        die_height_um=5000.0,
        critical_nets=["NET"],
    )
    assert report["status"] == "source_reference_lumped_rc"
    assert report["analysis_policy"]["name"] == "project_l0_default"
    assert report["signoff"] is False
    assert report["counts"]["resistors"] == 2
    assert report["counts"]["capacitors"] == 1
    assert report["counts"]["ignored_active_or_subcircuit_instances"] == {"M": 1, "X": 1}
    assert len(report["parallel_pairs"]) == 1
    response = report["parallel_pairs"][0]["responses"][0]
    expected_admittance = complex(0.15, 2.0 * 3.141592653589793 * 1.0e9 * 1.0e-12)
    assert abs(response["admittance_s"]["real"] - expected_admittance.real) < 1.0e-12
    assert abs(response["admittance_s"]["imag"] - expected_admittance.imag) < 1.0e-12

    assert validate_rf_request([1.0e9, 3.0e9], 5000.0, 5000.0) == (
        1.0e9,
        3.0e9,
    )
    expanded_policy = RFAnalysisPolicy(
        name="expanded_study",
        min_frequency_hz=500.0e6,
        max_frequency_hz=5.0e9,
        max_die_um=10000.0,
    )
    assert validate_rf_request(
        [500.0e6, 5.0e9], 10000.0, 10000.0, expanded_policy
    ) == (500.0e6, 5.0e9)
    for frequencies, width, height in (
        ([0.9e9], 5000.0, 5000.0),
        ([3.1e9], 5000.0, 5000.0),
        ([1.0e9], 5000.1, 5000.0),
    ):
        try:
            validate_rf_request(frequencies, width, height)
        except ValueError:
            pass
        else:
            raise AssertionError("out-of-envelope RF request was accepted")

    print("RF workbench contract checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
