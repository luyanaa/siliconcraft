#!/usr/bin/env python3
"""Run the non-signoff Magic PEX contract and runtime gates.

The suite deliberately covers the current PEX boundary rather than claiming
calibrated extraction: generated topology/source-reference technologies must
render consistently, load in Magic, extract the expected primitive MOS models,
and simulate against the profile model libraries.

Usage:
  python3 scripts/run_pex_ci.py
  python3 scripts/run_pex_ci.py --static-only
  python3 scripts/run_pex_ci.py --runtime-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.process_ir import load_process, profile_names  # noqa: E402


def capability_profiles(capability: str) -> tuple[str, ...]:
    return tuple(
        profile
        for profile in profile_names(ROOT)
        if bool(getattr(load_process(profile, ROOT).collateral_capabilities, capability, False))
    )


PEX_PROFILES = capability_profiles("pex_runtime")
STATIC_GATES = (
    "test_process_ir.py",
    "test_profile_collateral_matrix.py",
    "test_field_solver_contracts.py",
    "test_magic_pex.py",
    "test_ls1u_pex.py",
    "test_ls1u_devices.py",
    "test_ls1u_contracts.py",
)


def run(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *args]
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--static-only",
        action="store_true",
        help="run manifest/rendering contracts without native Magic/ngspice",
    )
    mode.add_argument(
        "--runtime-only",
        action="store_true",
        help="run native Magic/ngspice extraction smokes only",
    )
    args = parser.parse_args()

    if not args.runtime_only:
        for profile in PEX_PROFILES:
            run("gen_magic_pex.py", "--profile", profile, "--all")
        for gate in STATIC_GATES:
            run(gate)

    if not args.static_only:
        for profile in PEX_PROFILES:
            run("run_magic_pex_smoke.py", "--profile", profile)
        run("run_scmos_legacy_check.py")
        run("run_scmos_well_route_check.py")
        run("run_ls1u_magic_smoke.py")

    print("[run_pex_ci] PEX CONTRACT AND RUNTIME GATES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
