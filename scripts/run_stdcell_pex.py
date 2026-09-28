#!/usr/bin/env python3
"""Extract one rendered stdcell with Magic and exercise its models in ngspice."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.runtime import run_magic_extract  # noqa: E402
from run_magic_pex_smoke import default_config, logical_spice_lines, parse_mosfet_lines, run_ngspice  # noqa: E402


def tool(argument: str | None, environment: str, name: str) -> str:
    value = argument or os.environ.get(environment) or shutil.which(name)
    if not value:
        raise SystemExit(f"{name} not found; pass --{name} or set {environment}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--top-cell", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--magic")
    parser.add_argument("--ngspice")
    args = parser.parse_args()

    magic = tool(args.magic, "MAGIC", "magic")
    ngspice = tool(args.ngspice, "NGSPICE", "ngspice")
    config = default_config(args.profile)
    tech = ROOT / f"profiles/{args.profile}/pex/{config['technology_profile']}.tech"
    models = ROOT / f"profiles/{args.profile}/models/{args.profile}.lib"
    for path in (args.layout, tech, models):
        if not path.exists():
            raise SystemExit(f"missing PEX input: {path}")

    output = args.output if args.output.is_absolute() else ROOT / args.output
    summary_path = args.summary if args.summary.is_absolute() else ROOT / args.summary
    workdir = args.workdir if args.workdir.is_absolute() else ROOT / args.workdir
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    extracted, magic_log = run_magic_extract(
        magic,
        args.layout.resolve(),
        tech.resolve(),
        output,
        workdir,
        config["style"],
        top_cell=args.top_cell,
    )
    devices = parse_mosfet_lines(extracted)
    capacitors = [line for line in logical_spice_lines(extracted) if line.startswith("C")]
    expected_models = {config["nmos_model"], config["pmos_model"]}
    models_found = {device[5] for device in devices}
    if not devices:
        raise SystemExit("Magic PEX emitted no MOS devices")
    if not expected_models.issubset(models_found):
        raise SystemExit(
            f"Magic PEX models mismatch: expected {sorted(expected_models)}, "
            f"found {sorted(models_found)}"
        )
    ngspice_log = run_ngspice(
        ngspice,
        extracted,
        models.resolve(),
        config["model_section"],
        workdir,
        args.profile,
    )
    summary = {
        "profile": args.profile,
        "top_cell": args.top_cell,
        "layout": str(args.layout),
        "output": str(output),
        "devices": len(devices),
        "models": sorted(models_found),
        "parasitic_capacitors": len(capacitors),
        "magic_warnings": "Warning:" in magic_log,
        "ngspice_operating_point": "No. of Data Rows" in ngspice_log,
        "status": "pex_and_model_smoke_pass",
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"[stdcell_pex] PASS profile={args.profile} top_cell={args.top_cell} "
        f"devices={len(devices)} capacitors={len(capacitors)} "
        f"models={','.join(sorted(models_found))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
