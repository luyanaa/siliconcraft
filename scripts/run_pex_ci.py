#!/usr/bin/env python3
"""Run non-signoff native and Magic PEX contract and runtime gates.

Generated topology/source-reference technologies must render consistently,
load in their native extractors, and simulate against profile model libraries.
AMS C35 uses its estimated native Manhattan backend and supported-core
mixed-signal regression; other profiles retain the Magic PEX smoke.

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

# Runtime gates that request the `authoritative` LVS/DRC deck need the generated
# collateral under profiles/<name>/generated/, which is gitignored ("generated
# tool collateral (never hand-edited, always regenerated)") and therefore absent
# on a fresh checkout.  scripts/run_ci.py generates it for its own profile; this
# runner must do the same for the profiles whose runtime tests consume that deck,
# otherwise the PEX job fails only in CI.  Only ams_c35's tests request it today
# (test_ams_c35_native_pex.py and test_ams_c35_mixed_signal.py both pass
# deck="authoritative" to scripts/run_lvs.py).
AUTHORITATIVE_DECK_PROFILES = ("ams_c35",)
STATIC_GATES = (
    "test_process_ir.py",
    "test_ams_c35_maturity.py",
    "test_profile_collateral_matrix.py",
    "test_field_solver_contracts.py",
    "test_magic_pex.py",
    "test_ls1u_pex.py",
    "test_ls1u_devices.py",
    "test_ls1u_contracts.py",
    "test_ams_c35_native_graph.py",
    "test_tsmc035_pex.py",
    "run_wat_pex_smoke.py",
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
        help="run manifest/rendering contracts without native Magic/KLayout/ngspice",
    )
    mode.add_argument(
        "--runtime-only",
        action="store_true",
        help="run native Magic/KLayout/ngspice extraction smokes only",
    )
    args = parser.parse_args()

    if not args.runtime_only:
        for profile in PEX_PROFILES:
            run("gen_magic_pex.py", "--profile", profile, "--all")
        for gate in STATIC_GATES:
            run(gate)

    if not args.static_only:
        # Generate the authoritative decks these runtime gates consume.  Without
        # this the tests pass only on a machine that happens to have the
        # gitignored generated/ collateral from an earlier manual run.
        for profile in AUTHORITATIVE_DECK_PROFILES:
            run("gen_drc.py", "--profile", profile)
            run("gen_lvs.py", "--profile", profile)
        for profile in PEX_PROFILES:
            if profile == "ams_c35":
                run("test_ams_c35_passives.py")
                run("test_ams_c35_models.py")
                run("test_ams_c35_native_pex.py")
                run("test_ams_c35_mixed_signal.py")
            else:
                run("run_magic_pex_smoke.py", "--profile", profile)
        run("run_scmos_legacy_check.py")
        run("run_scmos_well_route_check.py")
        run("run_ls1u_magic_smoke.py")

    print("[run_pex_ci] PEX CONTRACT AND RUNTIME GATES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
