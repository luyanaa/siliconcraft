#!/usr/bin/env python3
"""Run one planned standard cell through DRC/LVS and optional PEX/LEF smoke.

The default gate is geometry/connectivity only. ``--pex`` adds persistent
Magic extraction and an ngspice operating-point smoke; ``--lef`` emits a
geometry-plan abstract. Neither mode claims library timing, power, or Liberty
characterization.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def tool(argument: str | None, environment: str, name: str) -> str:
    value = argument or os.environ.get(environment) or shutil.which(name)
    if not value:
        raise SystemExit(f"{name} not found; pass --{name} or set {environment}")
    return value


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def run_gate(args: argparse.Namespace) -> int:
    klayout = tool(args.klayout, "KLAYOUT", "klayout")
    netgen = tool(args.netgen, "NETGEN", "netgen")
    workdir = args.workdir if args.workdir.is_absolute() else ROOT / args.workdir
    workdir.mkdir(parents=True, exist_ok=True)
    manifest = workdir / f"{args.cell}.json"
    layout = workdir / f"{args.cell}.gds"
    drc_report = workdir / f"{args.cell}.drc.gds"
    drc_summary = workdir / f"{args.cell}.drc.json"
    lvs_workdir = workdir / "lvs"
    source = args.input if args.input.is_absolute() else ROOT / args.input
    schematic = args.schematic if args.schematic.is_absolute() else ROOT / args.schematic
    top_cell = args.top_cell or f"{args.cell}_c0"

    gen_command = [
        sys.executable,
        "scripts/gen_stdcell.py",
        "--profile",
        args.profile,
        "--input",
        str(source),
        "--architecture",
        args.architecture,
        "--output",
        str(manifest),
    ]
    if args.beam_width is not None:
        gen_command.extend(["--beam-width", str(args.beam_width)])
    run(gen_command)
    lef_output = None
    if args.lef:
        lef_output = workdir / f"{args.cell}.lef"
        run(
            [
                sys.executable,
                "scripts/emit_stdcell_lef.py",
                "--manifest",
                str(manifest),
                "--candidate",
                str(args.candidate),
                "--output",
                str(lef_output),
            ]
        )
    render_env = dict(os.environ)
    render_env.update(
        {
            "SILICONCRAFT_MANIFEST": str(manifest),
            "SILICONCRAFT_CANDIDATE": str(args.candidate),
            "SILICONCRAFT_OUTPUT": str(layout),
        }
    )
    run([klayout, "-b", "-r", str(ROOT / "scripts/render_stdcell.py")], env=render_env)
    run(
        [
            sys.executable,
            "scripts/run_drc.py",
            "--profile",
            args.profile,
            "--deck",
            "authoritative",
            "--layout",
            str(layout),
            "--out",
            str(drc_report),
            "--summary",
            str(drc_summary),
            "--klayout",
            klayout,
        ]
    )
    summary = json.loads(drc_summary.read_text())
    if summary.get("markers") != 0:
        raise SystemExit(f"{args.cell} DRC produced markers: {summary}")
    run(
        [
            sys.executable,
            "scripts/run_lvs.py",
            "--profile",
            args.profile,
            "--layout",
            str(layout),
            "--schematic",
            str(schematic),
            "--deck",
            "authoritative",
            "--top-cell",
            top_cell,
            "--workdir",
            str(lvs_workdir),
            "--klayout",
            klayout,
            "--netgen",
            netgen,
        ]
    )
    if args.pex:
        magic = tool(args.magic, "MAGIC", "magic")
        ngspice = tool(args.ngspice, "NGSPICE", "ngspice")
        pex_dir = workdir / "pex"
        pex_summary = pex_dir / f"{args.cell}.pex.json"
        run(
            [
                sys.executable,
                "scripts/run_stdcell_pex.py",
                "--profile",
                args.profile,
                "--layout",
                str(layout),
                "--top-cell",
                top_cell,
                "--output",
                str(pex_dir / f"{args.cell}.spice"),
                "--summary",
                str(pex_summary),
                "--workdir",
                str(pex_dir),
                "--magic",
                magic,
                "--ngspice",
                ngspice,
            ]
        )
    pex_status = " pex=pass" if args.pex else ""
    lef_status = " lef=pass" if args.lef else ""
    print(
        f"[stdcell_gate] PASS cell={args.cell} profile={args.profile} "
        f"architecture={args.architecture} drc_markers={summary['markers']} "
        f"lvs=match{pex_status}{lef_status}"
    )
    return 0


def main(defaults: dict[str, object] | None = None) -> int:
    defaults = defaults or {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=defaults.get("profile"))
    parser.add_argument("--architecture", default=defaults.get("architecture", "two_metal_classic"))
    parser.add_argument("--cell", default=defaults.get("cell"))
    parser.add_argument("--input", type=Path, default=defaults.get("input"))
    parser.add_argument("--schematic", type=Path, default=defaults.get("schematic"))
    parser.add_argument("--workdir", type=Path, default=defaults.get("workdir"))
    parser.add_argument("--candidate", type=int, default=defaults.get("candidate", 0))
    parser.add_argument("--beam-width", type=int)
    parser.add_argument("--top-cell", default=defaults.get("top_cell"))
    parser.add_argument("--klayout")
    parser.add_argument("--netgen")
    parser.add_argument("--pex", action="store_true")
    parser.add_argument("--magic")
    parser.add_argument("--ngspice")
    parser.add_argument("--lef", action="store_true")
    args = parser.parse_args()
    missing = [name for name in ("profile", "cell", "input", "schematic", "workdir") if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(f"--{name}" for name in missing))
    return run_gate(args)


if __name__ == "__main__":
    raise SystemExit(main())
