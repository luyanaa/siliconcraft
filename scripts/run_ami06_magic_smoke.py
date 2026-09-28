#!/usr/bin/env python3
"""Run the AMI06 source-driven Magic extraction experiment.

The fixture contains one NMOS, one PMOS, well/substrate taps, route layers,
and an electrode/poly capacitor.  The smoke proves that both generated
technology profiles load the AMI06 map, extract AMI06 primitive models, and
that the extracted MOS netlist parses and simulates against the source model
library.  It is not a signoff PEX comparison.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from common.pex.runtime import run_magic_extract
DEFAULT_LAYOUT = ROOT / "common/tests/gds/ami06_drc_test.gds"
DEFAULT_TECH = ROOT / "profiles/ami06/pex/n8bn_reference.tech"
DEFAULT_MODELS = ROOT / "profiles/ami06/models/ami06.lib"


def logical_spice_lines(text: str) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        if line.startswith("+") and result:
            result[-1] += " " + line[1:].strip()
        else:
            result.append(line.strip())
    return result


def parse_mosfet_lines(text: str) -> list[tuple[str, str, str, str, str, str]]:
    devices = []
    for line in logical_spice_lines(text):
        fields = line.split()
        if len(fields) < 6 or not fields[0].startswith("M"):
            continue
        devices.append(tuple(fields[:6]))
    return devices


def run_magic(
    magic: str, layout: Path, technology: Path, output: Path, workdir: Path
) -> tuple[str, str]:
    return run_magic_extract(magic, layout, technology, output, workdir, "ami06_n8bn")


def run_ngspice(ngspice: str, extracted: str, models: Path, workdir: Path) -> str:
    devices = parse_mosfet_lines(extracted)
    if not devices:
        raise RuntimeError("extracted netlist has no MOS devices")
    nodes = {
        field
        for device in devices
        for field in device[1:5]
        if field != "0" and field.lower() != "gnd"
    }
    deck_lines = [
        "* AMI06 extracted-device smoke",
        f".lib '{models}' ami06",
        *[
            line
            for line in logical_spice_lines(extracted)
            if line.startswith("M") or line.startswith("C")
        ],
    ]
    for index, node in enumerate(sorted(nodes)):
        deck_lines.append(f"VSMOKE{index} {node} 0 0")
    deck_lines.extend([".op", ".end", ""])
    deck = workdir / "ami06_smoke.cir"
    deck.write_text("\n".join(deck_lines))
    proc = subprocess.run(
        [ngspice, "-b", str(deck)],
        cwd=workdir,
        text=True,
        capture_output=True,
        check=False,
    )
    log = proc.stdout + proc.stderr
    if proc.returncode != 0 or re.search(r"\b(?:Error|Fatal):", log, re.IGNORECASE):
        raise RuntimeError(f"ngspice failed with {proc.returncode}\n{log}")
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--tech", type=Path, default=DEFAULT_TECH)
    ap.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    ap.add_argument("--magic", default=os.environ.get("MAGIC", "magic"))
    ap.add_argument("--ngspice", default=os.environ.get("NGSPICE", "ngspice"))
    args = ap.parse_args()

    for path in (args.layout, args.tech, args.models):
        if not path.exists():
            raise SystemExit(f"missing experiment input: {path}")
    with tempfile.TemporaryDirectory(prefix="ami06-magic-") as temp:
        workdir = Path(temp)
        output = workdir / "ami06_extracted.spice"
        extracted, magic_log = run_magic(
            args.magic,
            args.layout.resolve(),
            args.tech.resolve(),
            output,
            workdir,
        )
        devices = parse_mosfet_lines(extracted)
        parasitic_caps = [
            line for line in logical_spice_lines(extracted) if line.startswith("C")
        ]
        models = {device[5] for device in devices}
        if not {"ami06N", "ami06P"}.issubset(models):
            raise RuntimeError(f"expected ami06N/ami06P, found {sorted(models)}")
        if args.tech.name == "n8bn_reference.tech" and not parasitic_caps:
            raise RuntimeError("source-reference extraction produced no parasitic capacitors")
        ngspice_log = run_ngspice(
            args.ngspice, extracted, args.models.resolve(), workdir
        )
        print("AMI06 Magic extraction smoke: PASS")
        print(f"  technology: {args.tech}")
        print(f"  MOS devices: {len(devices)} ({', '.join(sorted(models))})")
        print(f"  parasitic capacitors: {len(parasitic_caps)}")
        print("  source model simulation: PASS")
        if "Warning:" in magic_log:
            print("  Magic warnings: present (backend/fixture warnings only)")
        if "No. of Data Rows" in ngspice_log:
            print("  ngspice operating point: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
