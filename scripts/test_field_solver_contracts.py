#!/usr/bin/env python3
"""Check every advertised field-solver reconstruction contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.pex.field_solver import canonical_sweep_manifest  # noqa: E402
from common.process_ir import load_process  # noqa: E402


def main() -> int:
    expected = {
        "ams_c35": "field_solver_estimated",
        "cnm25": "field_solver_estimated",
        "tsmc018_deep": "field_solver_estimated",
        "xh018": "field_solver_estimated",
        "xh035": "field_solver_estimated",
    }
    for profile, pex_profile in expected.items():
        process = load_process(profile, ROOT)
        result = canonical_sweep_manifest(process.pex_doc, profile_name=pex_profile)
        assert result["profile"] == profile
        assert result["calibrated"] is False
        assert result["solver_candidates"]
        assert len(result["patterns"]) == 7
        assert result["signoff"] is False
        fit = Path(result["beol_fit"])
        assert any(
            candidate.exists()
            for candidate in (
                ROOT / f"profiles/{profile}/pex" / fit,
                ROOT / f"profiles/{profile}" / fit,
                ROOT / fit,
            )
        ), f"{profile}: missing BEOL fit {fit}"
    print(f"Field-solver contract checks: PASS ({len(expected)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
