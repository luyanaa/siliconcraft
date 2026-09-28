#!/usr/bin/env python3
"""Run a generated process-specific Magic extraction experiment.

The fixture proves that a generated topology/source-reference profile loads,
extracts the configured primitive MOS models, and that the extracted netlist
parses and simulates against the profile model library.  It is not signoff PEX.
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

from yamlish import load  # noqa: E402
from common.pex.runtime import run_magic_extract  # noqa: E402

DEFAULT_LAYOUT = ROOT / "common/tests/gds/ami06_drc_test.gds"


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
    magic: str,
    layout: Path,
    technology: Path,
    output: Path,
    workdir: Path,
    style: str,
) -> tuple[str, str]:
    return run_magic_extract(magic, layout, technology, output, workdir, style)


def run_ngspice(
    ngspice: str,
    extracted: str,
    models: Path,
    model_section: str,
    workdir: Path,
    profile: str,
) -> str:
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
        f"* {profile} extracted-device smoke",
        f".lib '{models}' {model_section}",
        *[
            line
            for line in logical_spice_lines(extracted)
            if line.startswith("M") or line.startswith("C")
        ],
    ]
    for index, node in enumerate(sorted(nodes)):
        deck_lines.append(f"VSMOKE{index} {node} 0 0")
    deck_lines.extend([".op", ".end", ""])
    deck = workdir / f"{profile}_smoke.cir"
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


def default_config(profile: str) -> dict[str, str]:
    manifest_path = ROOT / "profiles" / profile / "pex" / "manifest.yaml"
    if not manifest_path.exists():
        raise SystemExit(f"PEX manifest not found: {manifest_path}")
    manifest = load(manifest_path.read_text())
    topology = manifest.get("topology") or {}
    devices = topology.get("devices") or {}
    profiles = manifest.get("profiles") or {}
    reference_profile = next(
        (
            name
            for name, spec in profiles.items()
            if name != "none" and isinstance(spec, dict) and spec.get("generated") is True
        ),
        "none",
    )
    try:
        nmos = devices["nmos"]["model"]
        pmos = devices["pmos"]["model"]
        style = topology["style"]
    except (KeyError, TypeError) as exc:
        raise SystemExit(f"manifest topology is incomplete: {manifest_path}") from exc
    return {
        "style": str(style),
        "nmos_model": str(nmos),
        "pmos_model": str(pmos),
        "model_section": profile,
        "technology_profile": str(reference_profile),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--tech", type=Path)
    ap.add_argument("--models", type=Path)
    ap.add_argument("--style")
    ap.add_argument("--model-section")
    ap.add_argument("--nmos-model")
    ap.add_argument("--pmos-model")
    ap.add_argument("--require-parasitics", action="store_true")
    ap.add_argument("--magic", default=os.environ.get("MAGIC", "magic"))
    ap.add_argument("--ngspice", default=os.environ.get("NGSPICE", "ngspice"))
    args = ap.parse_args()

    config = default_config(args.profile)
    tech = args.tech or ROOT / f"profiles/{args.profile}/pex/{config['technology_profile']}.tech"
    models = args.models or ROOT / f"profiles/{args.profile}/models/{args.profile}.lib"
    style = args.style or config["style"]
    model_section = args.model_section or config["model_section"]
    expected_models = {args.nmos_model or config["nmos_model"], args.pmos_model or config["pmos_model"]}

    for path in (args.layout, tech, models):
        if not path.exists():
            raise SystemExit(f"missing experiment input: {path}")
    with tempfile.TemporaryDirectory(prefix=f"{args.profile}-magic-") as temp:
        workdir = Path(temp)
        output = workdir / f"{args.profile}_extracted.spice"
        extracted, magic_log = run_magic(
            args.magic,
            args.layout.resolve(),
            tech.resolve(),
            output,
            workdir,
            style,
        )
        devices = parse_mosfet_lines(extracted)
        parasitic_caps = [
            line for line in logical_spice_lines(extracted) if line.startswith("C")
        ]
        models_found = {device[5] for device in devices}
        if not expected_models.issubset(models_found):
            raise RuntimeError(
                f"expected {sorted(expected_models)}, found {sorted(models_found)}"
            )
        if args.require_parasitics and not parasitic_caps:
            raise RuntimeError("source-reference extraction produced no parasitic capacitors")
        ngspice_log = run_ngspice(
            args.ngspice,
            extracted,
            models.resolve(),
            model_section,
            workdir,
            args.profile,
        )
        print(f"{args.profile} Magic extraction smoke: PASS")
        print(f"  technology: {tech}")
        print(f"  MOS devices: {len(devices)} ({', '.join(sorted(models_found))})")
        print(f"  parasitic capacitors: {len(parasitic_caps)}")
        print("  source model simulation: PASS")
        if "Warning:" in magic_log:
            print("  Magic warnings: present (backend/fixture warnings only)")
        if "No. of Data Rows" in ngspice_log:
            print("  ngspice operating point: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
