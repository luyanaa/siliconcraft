#!/usr/bin/env python3
"""Run the siliconcraft conformance gates end-to-end (local CI).

Steps for the given profile:
  1. regenerate the DRC/LVS testcases (clean + violations) with KLayout
  2. generate the authoritative DRC and LVS decks (gen_drc/gen_lvs)
  3. DRC gates: reference vs authoritative conformance on both testcases
  4. LVS gates: reference vs authoritative extraction + netlist conformance
  5. netgen LVS of the authoritative extraction vs the test schematic
     (positive must match, topology-mismatch schematic must fail)

Exit 0 only if every gate passes.  Tools: KLAYOUT/NETGEN env override, else
auto-detected in the nix store, else PATH.

Usage:
  python3 scripts/run_ci.py --profile ami06
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_tool(env_name, store_name):
    env = os.environ.get(env_name)
    if env:
        return env
    hits = sorted(glob.glob(f"/nix/store/*{store_name}*/bin/{store_name}"))
    if hits:
        return hits[-1]
    which = shutil.which(store_name)
    if which:
        return which
    raise SystemExit(f"{store_name} not found (set {env_name} or install it)")


def run(cmd, **kw):
    print(f"+ {cmd}"[:160])
    proc = subprocess.run(cmd, shell=True, **kw)
    if proc.returncode != 0:
        raise SystemExit(f"FAILED ({proc.returncode}): {cmd}")
    return proc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="ami06")
    ap.add_argument("--workdir", default="build/ci")
    args = ap.parse_args()

    K = find_tool("KLAYOUT", "klayout")
    N = find_tool("NETGEN", "netgen")
    p = args.profile
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KLAYOUT=K, NETGEN=N)
    r = ROOT

    clean = wd / "ami06_clean.gds"
    viol = wd / "ami06_drc_test.gds"

    # 1. testcases
    run(f"OUT={clean} CLEAN=1 {K} -b -r {r/'common/tests/make_drc_testcase.py'}", env=env)
    run(f"OUT={viol} {K} -b -r {r/'common/tests/make_drc_testcase.py'}", env=env)

    # 2. generate authoritative decks
    run(f"python3 {r/'scripts/gen_drc.py'} --profile {p}", env=env)
    run(f"python3 {r/'scripts/gen_lvs.py'} --profile {p}", env=env)

    # 2b. process-neutral Magic PEX contract (source/unit rendering)
    if p == "ami06":
        for pex_profile in ("ami06", "hp06", "ami16"):
            run(f"python3 {r/'scripts/gen_magic_pex.py'} --profile {pex_profile} --all", env=env)
        run(f"python3 {r/'scripts/test_magic_pex.py'}", env=env)

    # 3. DRC gates
    for name, layout in (("clean", clean), ("violations", viol)):
        run(f"python3 {r/'scripts/conformance.py'} --profile {p} --layout {layout} "
            f"--decks reference,authoritative --workdir {wd / ('drc_' + name)} --klayout '{K}'",
            env=env)

    # 4. LVS extraction + netlist conformance
    run(f"python3 {r/'scripts/lvs_conformance.py'} --profile {p} --layout {clean} "
        f"--workdir {wd/'lvs'} --klayout '{K}'", env=env)

    # 5. netgen LVS: positive + negative
    sch = r / "common/tests/spice/ami06_lvs_schematic.spice"
    sch_bad = r / "common/tests/spice/ami06_lvs_schematic_bad.spice"
    proc = subprocess.run(
        f"python3 {r/'scripts/run_lvs.py'} --profile {p} --layout {clean} "
        f"--schematic {sch} --workdir {wd/'netgen'} --deck authoritative "
        f"--klayout '{K}' --netgen '{N}'", shell=True, env=env,
        capture_output=True, text=True)
    if proc.returncode != 0 or "MATCH UNIQUELY" not in proc.stdout:
        raise SystemExit("netgen positive gate did not match uniquely")
    proc = subprocess.run(
        f"python3 {r/'scripts/run_lvs.py'} --profile {p} --layout {clean} "
        f"--schematic {sch_bad} --workdir {wd/'netgen_bad'} --deck authoritative "
        f"--klayout '{K}' --netgen '{N}'", shell=True, env=env,
        capture_output=True, text=True)
    if proc.returncode == 0:
        raise SystemExit("netgen negative gate did not fail")

    print("[run_ci] ALL GATES PASS")


if __name__ == "__main__":
    main()
