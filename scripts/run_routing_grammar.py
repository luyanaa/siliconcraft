#!/usr/bin/env python3
"""Compile static PDK facts plus batched native DRC/LVS routing probes."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_drc  # noqa: E402
import run_lvs  # noqa: E402
from common.process_ir import load_process  # noqa: E402
from common.routing_grammar import UNKNOWN, inspect_profile  # noqa: E402
from common.routing_probes import (  # noqa: E402
    ProbeSpec,
    apply_probe_observation,
    classify_probe,
    default_probe_specs,
    local_rule_sweep_specs,
    native_feature_probe_specs,
)


def tool(argument: str | None, name: str) -> str:
    value = argument or shutil.which(name)
    if not value:
        raise SystemExit(f"{name} not found; pass --{name}")
    return value


def run(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=check)


def _drc_status(summary: dict[str, Any] | None, returncode: int) -> str:
    if returncode != 0 or not summary:
        return UNKNOWN
    markers = summary.get("markers")
    if markers is None:
        return UNKNOWN
    return "pass" if markers == 0 else "fail"


def _device_names(summary: dict[str, Any] | None) -> tuple[str, ...]:
    devices = (summary or {}).get("devices") or {}
    return tuple(sorted(name for name, count in devices.items() if count))


def _lvs_status(probe: ProbeSpec, summary: dict[str, Any] | None) -> str:
    if not summary:
        return UNKNOWN
    if probe.expected in {"forms_device", "no_device"} and "devices" in summary:
        return "pass"
    if "port_nets" not in summary:
        return UNKNOWN
    port_nets = summary["port_nets"]
    values = [port_nets.get(label) for label in probe.labels]
    if any(value is None for value in values):
        return UNKNOWN
    if probe.expected in {"connected", "short"}:
        return "pass" if len(set(values)) == 1 else "fail"
    if probe.expected == "isolated":
        isolated_pairs = (
            len(values) == 4
            and values[0] == values[1]
            and values[2] == values[3]
            and values[0] != values[2]
        )
        return "isolated" if isolated_pairs or len(set(values)) == len(values) else "fail"
    return "pass"
def _run_drc(profile: str, layout: Path, top_cell: str, workdir: Path, klayout: str) -> tuple[str, dict[str, Any]]:
    summary_path = workdir / "drc.json"
    report_path = workdir / "drc.gds"
    profile_dir = ROOT / "profiles" / profile
    deck = "authoritative" if (profile_dir / "generated" / "drc" / "run.py").exists() else "reference"
    result = run(
        [
            sys.executable,
            "scripts/run_drc.py",
            "--profile",
            profile,
            "--deck",
            deck,
            "--layout",
            str(layout),
            "--top-cell",
            top_cell,
            "--out",
            str(report_path),
            "--summary",
            str(summary_path),
            "--klayout",
            klayout,
        ],
        check=False,
    )
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    status = _drc_status(summary, result.returncode)
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
    return status, summary




def _run_lvs(
    profile: str,
    layout: Path,
    top_cell: str,
    workdir: Path,
    klayout: str,
) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    profile_dir = ROOT / "profiles" / profile
    deck = "authoritative" if (profile_dir / "generated" / "lvs" / "run.py").exists() else "reference"
    try:
        summary, _ = run_lvs.extract(
            profile_dir,
            layout,
            deck,
            workdir,
            klayout,
            top_cell=top_cell,
        )
    except (OSError, SystemExit) as exc:
        print(f"[run_routing_grammar] LVS unavailable for {top_cell}: {exc}", file=sys.stderr)
        return UNKNOWN, {}, ()
    return "pass" if summary and ("port_nets" in summary or "devices" in summary) else UNKNOWN, summary, _device_names(summary)


def _spec_from_record(record: dict[str, Any]) -> ProbeSpec:
    return ProbeSpec(
        name=record["name"],
        kind=record["kind"],
        conductor=record["conductor"],
        target=record.get("target"),
        cut=record.get("cut"),
        region=record.get("region"),
        width_um=record["width_um"],
        labels=tuple(record.get("labels", ())),
        expected=record["expected"],
        metadata=record.get("metadata", {}),
    )


def _summarize_sweeps(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    for result in results:
        metadata = result.get("metadata", {})
        sweep = metadata.get("sweep")
        if sweep:
            key = (result["conductor"], sweep, result.get("target"))
            groups.setdefault(key, []).append(result)
    summary: dict[str, Any] = {}
    for (conductor, sweep, target), values in sorted(groups.items()):
        values.sort(key=lambda item: float(item["metadata"]["sweep_value_um"]))
        statuses = [item["classification"]["status"] for item in values]
        supported = [
            float(item["metadata"]["sweep_value_um"])
            for item in values
            if item["classification"]["status"] == "SUPPORTED"
        ]
        first_supported = min(supported) if supported else None
        first_index = statuses.index("SUPPORTED") if "SUPPORTED" in statuses else None
        monotonic = None if first_index is None else (
            all(status == "SUPPORTED" for status in statuses[first_index:])
            and all(status not in {"UNKNOWN", "EXPERIMENTAL"} for status in statuses[:first_index])
        )
        key = f"{conductor}:{sweep}" + (f":{target}" if target else "")
        summary[key] = {
            "values_um": [float(item["metadata"]["sweep_value_um"]) for item in values],
            "statuses": statuses,
            "first_supported_um": first_supported,
            "monotonic": monotonic,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--klayout")
    parser.add_argument("--max-probes", type=int)
    parser.add_argument("--local-rule-sweeps", action="store_true",
                        help="also probe monotonic local width, spacing, and enclosure limits")
    parser.add_argument("--require-native", action="store_true",
                        help="fail if any probe lacks native DRC or extraction evidence")
    args = parser.parse_args()
    if args.max_probes is not None and args.max_probes < 1:
        parser.error("--max-probes must be >= 1")

    klayout = tool(args.klayout, "klayout")
    process = load_process(args.profile, ROOT)
    grammar = inspect_profile(args.profile, ROOT)
    specs = list(default_probe_specs(process, grammar))
    if args.local_rule_sweeps:
        specs.extend(local_rule_sweep_specs(process, grammar))
    specs.extend(native_feature_probe_specs(process, grammar))
    if args.max_probes is not None:
        specs = specs[: args.max_probes]
    workdir = args.workdir if args.workdir.is_absolute() else ROOT / args.workdir
    workdir.mkdir(parents=True, exist_ok=True)
    spec_path = workdir / "specs.json"
    spec_path.write_text(json.dumps([spec.as_dict() for spec in specs], indent=2, sort_keys=True) + "\n")
    probe_dir = workdir / "probes"
    env = dict(os.environ)
    env.update(
        {
            "SILICONCRAFT_PROBE_PROFILE": args.profile,
            "SILICONCRAFT_PROBE_GRAMMAR": str(workdir / "static_grammar.json"),
            "SILICONCRAFT_PROBE_SPECS": str(spec_path),
            "SILICONCRAFT_PROBE_OUTPUT": str(probe_dir),
        }
    )
    grammar.write(workdir / "static_grammar.json")
    generated = run([klayout, "-b", "-r", str(SCRIPT_DIR / "generate_routing_probes.py")], env=env)
    print(generated.stdout, end="")
    records = json.loads((probe_dir / "probes.json").read_text())
    results = []
    for record in records:
        spec = _spec_from_record(record)
        probe_workdir = workdir / spec.name
        drc, drc_summary = _run_drc(args.profile, Path(record["layout"]), record["top_cell"], probe_workdir, klayout)
        lvs_status, lvs_summary, devices = _run_lvs(
            args.profile,
            Path(record["layout"]),
            record["top_cell"],
            probe_workdir / "lvs",
            klayout,
        )
        lvs = _lvs_status(spec, lvs_summary) if lvs_status != UNKNOWN else UNKNOWN
        observation = classify_probe(
            spec,
            drc=drc,
            lvs=lvs,
            devices=devices,
            port_nets=(lvs_summary or {}).get("port_nets"),
        )
        if not spec.metadata.get("sweep"):
            grammar = apply_probe_observation(grammar, spec, observation)
        results.append(
            {
                **spec.as_dict(),
                "drc": {"status": drc, "summary": drc_summary},
                "lvs": {"status": lvs, "summary": lvs_summary, "devices": list(devices)},
                "classification": observation.as_dict(),
            }
        )
    grammar = replace(
        grammar,
        metadata={
            **grammar.metadata,
            "probe_count": len(results),
            "probe_results": results,
            "active_probes": "complete",
            "local_rule_sweeps": _summarize_sweeps(results) if args.local_rule_sweeps else {},
        },
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    grammar.write(output)
    (workdir / "report.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    counts: dict[str, int] = {}
    for result in results:
        status = result["classification"]["status"]
        counts[status] = counts.get(status, 0) + 1
    native_missing = [
        result["name"] for result in results
        if result["drc"]["status"] == UNKNOWN or result["lvs"]["status"] == UNKNOWN
    ]
    if args.require_native and native_missing:
        print(f"[run_routing_grammar] FAIL missing native evidence probes={native_missing}")
        return 1
    print(
        f"[run_routing_grammar] PASS profile={args.profile} probes={len(results)} "
        f"classification={counts} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
