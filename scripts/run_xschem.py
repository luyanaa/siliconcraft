#!/usr/bin/env python3
"""Run a profile xschem -> ngspice smoke gate.

The gate regenerates profile symbols, netlists a connected schematic, and
simulates the emitted primitive device lines against the profile's ngspice
model section.  Profile-specific expected netlist lines and the operating-
point probe are declared in ``profiles/<profile>/xschem_smoke.yaml``.

Invoke from the siliconcraft root:

  python3 scripts/run_xschem.py --profile ami06

XSCHEM and NGSPICE may be supplied explicitly when the binaries are not on
PATH.  Nix-store auto-discovery is a convenience for local development.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.process_ir import load_process  # noqa: E402


def find_tool(env_name, command, store_glob):
    explicit = os.environ.get(env_name)
    if explicit:
        return explicit
    matches = sorted(glob.glob(store_glob))
    if os.environ.get("IN_NIX_SHELL") and matches:
        return matches[-1]
    found = shutil.which(command)
    if found:
        return found
    if matches:
        return matches[-1]
    raise SystemExit(
        f"{command} not found; run inside ~/Documents/librelane nix-shell "
        f"or set {env_name}"
    )


def run(cmd, *, cwd=ROOT, env=None, stdout=None, check=False):
    print("+ " + " ".join(map(str, cmd)))
    return subprocess.run(
        cmd, cwd=cwd, env=env, stdout=stdout, text=True, check=check
    )


def device_lines(netlist):
    lines = []
    for line in netlist.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("."):
            continue
        lines.append(stripped)
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="ami06")
    ap.add_argument(
        "--schematic",
        type=Path,
        help="schematic fixture (default: common/tests/xschem/<profile>_nmos.sch)",
    )
    args = ap.parse_args()

    process = load_process(args.profile, ROOT)
    profile = process.profile_dir
    schematic = args.schematic or (ROOT / "common/tests/xschem" / f"{args.profile}_nmos.sch")
    schematic = schematic.resolve()
    if not schematic.exists():
        raise SystemExit(f"schematic not found: {schematic}")
    model = profile / "models" / f"{args.profile}.lib"
    if not model.exists():
        raise SystemExit(f"model library not found: {model}")
    smoke_path = profile / "xschem_smoke.yaml"
    if not smoke_path.exists():
        raise SystemExit(f"xschem smoke config not found: {smoke_path}")
    smoke = process.xschem_smoke_doc
    expected = tuple(smoke.get("expected_netlist") or ())
    probe = smoke.get("probe")
    if not expected or not probe:
        raise SystemExit(
            f"{smoke_path}: expected_netlist and probe are required"
        )
    try:
        min_current = float(smoke.get("min_current", 0.0))
    except (TypeError, ValueError):
        raise SystemExit(f"{smoke_path}: min_current must be numeric")

    xschem = find_tool(
        "XSCHEM",
        "xschem",
        "/nix/store/*xschem*/bin/xschem",
    )
    ngspice = find_tool(
        "NGSPICE",
        "ngspice",
        "/nix/store/*ngspice*/bin/ngspice",
    )

    run(
        [sys.executable, str(ROOT / "scripts/gen_symbols.py"), "--profile", args.profile],
        check=True,
    )

    env = os.environ.copy()
    generated = profile / "generated" / "xschem"
    env["XSCHEM_LIBRARY_PATH"] = str(generated)
    symbols = process.symbols
    missing_symbols = sorted(
        name for name in symbols if not (generated / f"{name}.sym").exists()
    )
    if missing_symbols:
        raise SystemExit(f"symbol generation missing files: {missing_symbols}")

    with tempfile.TemporaryDirectory(prefix="siliconcraft-xschem-") as tmp:
        netlist_dir = Path(tmp) / "netlist"
        netlist_dir.mkdir()
        proc = run(
            [xschem, "-b", "-q", "-n", "-o", str(netlist_dir), str(schematic)],
            env=env,
        )
        if proc.returncode != 0:
            raise SystemExit(f"xschem failed with exit code {proc.returncode}")

        netlists = sorted(netlist_dir.glob("*.spice"))
        if len(netlists) != 1:
            raise SystemExit(f"expected one xschem netlist, found {netlists}")
        netlist = netlists[0].read_text()
        if "MISSING" in netlist:
            raise SystemExit("xschem emitted a missing-symbol marker")

        missing = [line for line in expected if line not in netlist]
        if missing:
            raise SystemExit(f"xschem netlist missing expected lines: {missing}")

        devices = device_lines(netlist)
        deck = Path(tmp) / "smoke.cir"
        deck.write_text(
            "* generated xschem primitive netlist smoke test\n"
            f".lib '{model}' {args.profile}\n"
            + "\n".join(devices)
            + "\n.control\nop\n"
            f"print v(d) i(v2) {probe}\n"
            ".endc\n.end\n"
        )
        log = Path(tmp) / "ngspice.log"
        proc = run([ngspice, "-b", "-o", str(log), str(deck)], env=env)
        if proc.returncode != 0:
            raise SystemExit(f"ngspice failed with exit code {proc.returncode}")
        report = log.read_text()
        match = re.search(
            rf"{re.escape(str(probe))}\s*=\s*([-+0-9.eE]+)", report
        )
        if not match:
            raise SystemExit(f"ngspice output did not contain {probe}")
        drain_current = float(match.group(1))
        if not drain_current > min_current:
            raise SystemExit(
                f"unexpected probe value for {probe}: {drain_current}"
            )

    print(f"[run_xschem] PASS: {args.profile}, probe={drain_current:.6g} A")


if __name__ == "__main__":
    main()
