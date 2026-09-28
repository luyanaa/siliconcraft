#!/usr/bin/env python3
"""Run the LS1u GDS -> Magic -> ext2spice -> ngspice MOS smoke.

The flow requires native Magic and ngspice.  It intentionally fails closed
when either binary is unavailable; no fake extractor is accepted as proof.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT = ROOT / "common/tests/magic/ls1u_mos_pair.gds"
DEFAULT_TECH = ROOT / "profiles/ls1u/pex/none.tech"
DEFAULT_MODEL = ROOT / "profiles/ls1u/models/ls1u.lib"


def resolve_tool(explicit: str | None, env_name: str, command: str) -> str:
    value = explicit or os.environ.get(env_name) or shutil.which(command)
    if not value:
        raise SystemExit(
            f"{command} is unavailable; install native Magic/ngspice or set {env_name}"
        )
    return value


def logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("+"):
            current += " " + stripped[1:].strip()
            continue
        if current:
            lines.append(current)
        current = stripped
    if current:
        lines.append(current)
    return lines


def extracted_instances(text: str) -> list[tuple[str, list[str], list[str]]]:
    instances = []
    for line in logical_lines(text):
        if not line or line.startswith("*") or line.startswith("."):
            continue
        fields = line.split()
        if not fields or fields[0][0].upper() != "X":
            continue
        model_index = next(
            (i for i, token in enumerate(fields[1:], start=1)
             if token.upper() in {"LV1UNMOS", "LV1UPMOS"}),
            None,
        )
        if model_index is None:
            continue
        instances.append((fields[model_index].upper(), fields[1:model_index], fields[model_index + 1:]))
    return instances


def numeric_parameter(params: list[str], name: str) -> float:
    match = None
    for token in params:
        candidate = re.match(
            rf"^{name}=([-+0-9.eE]+)([munpfkK]?)(?:$|\s)", token, re.I
        )
        if candidate:
            match = candidate
            break
    if not match:
        raise SystemExit(f"extracted MOS is missing {name}=...: {params}")
    scale = {
        "": 1.0,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
        "k": 1e3,
    }[match.group(2).lower()]
    value = float(match.group(1)) * scale
    if not value > 0:
        raise SystemExit(f"extracted {name} is not positive: {value}")
    return value


def run_magic(magic: str, tech: Path, layout: Path, output: Path) -> str:
    commands = "\n".join(
        [
            f"gds read {layout}",
            f"load {layout.stem}",
            "select top cell",
            "extract style ls1u_topology",
            "extract all",
            "ext2spice lvs",
            "ext2spice subcircuit on",
            f"ext2spice -o {output}",
            "quit -noprompt",
            "",
        ]
    )
    proc = subprocess.run(
        [magic, "-dnull", "-noconsole", "-T", str(tech)],
        input=commands,
        cwd=output.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "Magic extraction failed:\n" + (proc.stdout or "") + (proc.stderr or "")
        )
    if not output.exists():
        raise SystemExit("Magic completed without producing an ext2spice netlist")
    return output.read_text()


def run_ngspice(ngspice: str, model: Path, instances: list[tuple[str, list[str], list[str]]], work: Path) -> None:
    nodes = sorted({node for _, node_list, _ in instances for node in node_list if node != "0"})
    deck_lines = ["* LS1u extracted MOS subcircuit smoke", f".lib '{model}' ls1u"]
    for index, node in enumerate(nodes):
        safe = re.sub(r"[^A-Za-z0-9_]", "_", node)
        deck_lines.append(f"Vbias_{index}_{safe} {node} 0 0")
    for index, (model_name, node_list, params) in enumerate(instances):
        deck_lines.append(
            "Xsmoke{} {} {}".format(index, " ".join(node_list), model_name)
            + (" " + " ".join(params) if params else "")
        )
    deck_lines += [".control", "op", "print all", ".endc", ".end", ""]
    deck = work / "ngspice_smoke.cir"
    log = work / "ngspice_smoke.log"
    deck.write_text("\n".join(deck_lines))
    proc = subprocess.run(
        [ngspice, "-b", "-o", str(log), str(deck)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = log.read_text() if log.exists() else proc.stderr
        raise SystemExit("ngspice failed:\n" + detail)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument("--tech", type=Path, default=DEFAULT_TECH)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--workdir", type=Path)
    ap.add_argument("--magic")
    ap.add_argument("--ngspice")
    args = ap.parse_args()

    for path in (args.layout, args.tech, args.model):
        if not path.exists():
            raise SystemExit(f"fixture input not found: {path}")
    magic = resolve_tool(args.magic, "MAGIC", "magic")
    ngspice = resolve_tool(args.ngspice, "NGSPICE", "ngspice")

    if args.workdir:
        args.workdir.mkdir(parents=True, exist_ok=True)
        work_context = tempfile.TemporaryDirectory(prefix="ls1u-magic-", dir=args.workdir)
    else:
        work_context = tempfile.TemporaryDirectory(prefix="ls1u-magic-")
    with work_context as tmp:
        work = Path(tmp)
        extracted = work / "extracted.spice"
        text = run_magic(magic, args.tech.resolve(), args.layout.resolve(), extracted)
        lower = text.lower()
        if ".subckt" not in lower or ".ends" not in lower:
            raise SystemExit("ext2spice output lacks a subcircuit boundary")
        if re.search(r"^m\S*\s+.*LV1U(?:N|P)MOS", text, re.I | re.M):
            raise SystemExit("ext2spice emitted an MOS primitive instead of an X subcircuit")

        instances = extracted_instances(text)
        if {name for name, _, _ in instances} != {"LV1UNMOS", "LV1UPMOS"}:
            raise SystemExit(f"expected one NMOS and one PMOS subcircuit, got {instances}")
        for model_name, nodes, params in instances:
            if len(nodes) < 4:
                raise SystemExit(f"{model_name} does not have D/G/S/B nodes: {nodes}")
            numeric_parameter(params, "W")
            numeric_parameter(params, "L")
            body = nodes[3].lower()
            expected_body = "vss" if model_name == "LV1UNMOS" else "vdd"
            if expected_body not in body:
                raise SystemExit(f"{model_name} body node is {nodes[3]}, expected {expected_body}")

        run_ngspice(ngspice, args.model.resolve(), instances, work)

    print("LS1u Magic MOS extraction smoke: PASS (NMOS/PMOS X subcircuits, W/L/body, ngspice)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
