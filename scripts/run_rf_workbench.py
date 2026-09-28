#!/usr/bin/env python3
"""Run the conservative L0 RF workbench on a generated Magic PEX profile.

The command re-renders the selected process PEX technology, runs the existing
GDS -> Magic -> ext2spice flow, and writes an R/C frequency report.  It does
not infer inductance, distributed effects, matching, or full-wave EM models.

Examples:
  python3 scripts/run_rf_workbench.py --profile ami06 \
      --pex-profile n8bn_reference --require-rc
  python3 scripts/run_rf_workbench.py --profile hp06 \
      --pex-profile n8ag_reference --frequency-hz 1e9 --frequency-hz 3e9
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import MagicPexError, generate_profile, topology_fragment  # noqa: E402
from common.pex.runtime import run_magic_extract  # noqa: E402
from common.rf.workbench import (  # noqa: E402
    build_report,
    parse_lumped_elements,
    validate_rf_request,
)
from common.process_ir import load_process  # noqa: E402

DEFAULT_LAYOUT = ROOT / "common/tests/gds/ami06_drc_test.gds"


def manifest_path(profile: str) -> Path:
    return ROOT / "profiles" / profile / "pex" / "manifest.yaml"


def default_pex_profile(manifest: dict) -> str:
    for name, spec in (manifest.get("profiles") or {}).items():
        if name != "none" and isinstance(spec, dict) and spec.get("generated") is True:
            return str(name)
    return "none"


def render_profile(
    manifest: dict,
    path: Path,
    profile_name: str,
    device_bindings: dict | None = None,
) -> Path:
    spec = (manifest.get("profiles") or {}).get(profile_name)
    if not isinstance(spec, dict):
        raise SystemExit(f"unknown PEX profile {profile_name!r} in {path}")
    if spec.get("generated") is False:
        raise SystemExit(f"PEX profile {profile_name!r} is reserved and not generated")
    fragment = manifest.get("topology_fragment")
    if fragment:
        fragment_path = (path.parent / str(fragment)).resolve()
        fragment_path.parent.mkdir(parents=True, exist_ok=True)
        fragment_path.write_text(topology_fragment(manifest, device_bindings))
    try:
        return generate_profile(manifest, path, profile_name, device_bindings)
    except MagicPexError as exc:
        raise SystemExit(f"PEX manifest error: {exc}") from exc


def frequencies_from_args(args: argparse.Namespace) -> list[float]:
    if args.frequency_hz and (
        args.start_ghz is not None or args.stop_ghz is not None
    ):
        raise SystemExit("--frequency-hz cannot be combined with a GHz sweep")
    if args.frequency_hz:
        return list(args.frequency_hz)
    if args.start_ghz is None and args.stop_ghz is None:
        return [1.0e9, 2.0e9, 3.0e9]
    if args.start_ghz is None or args.stop_ghz is None:
        raise SystemExit("--start-ghz and --stop-ghz must be supplied together")
    if args.points < 2:
        raise SystemExit("--points must be at least 2")
    step = (args.stop_ghz - args.start_ghz) / (args.points - 1)
    return [(args.start_ghz + index * step) * 1.0e9 for index in range(args.points)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pex-profile")
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extracted-output", type=Path)
    parser.add_argument("--frequency-hz", type=float, action="append")
    parser.add_argument("--start-ghz", type=float)
    parser.add_argument("--stop-ghz", type=float)
    parser.add_argument("--points", type=int, default=3)
    parser.add_argument("--die-width-um", type=float, default=5000.0)
    parser.add_argument("--die-height-um", type=float, default=5000.0)
    parser.add_argument("--net", dest="critical_nets", action="append", default=[])
    parser.add_argument("--require-rc", action="store_true")
    parser.add_argument("--magic", default=os.environ.get("MAGIC", "magic"))
    args = parser.parse_args()

    process = load_process(args.profile, ROOT)
    path = process.profile_dir / "pex" / "manifest.yaml"
    if not path.exists():
        raise SystemExit(f"PEX manifest not found: {path}")
    manifest = process.pex_doc
    pex_profile = args.pex_profile or default_pex_profile(manifest)
    frequencies = frequencies_from_args(args)
    try:
        validate_rf_request(
            frequencies, args.die_width_um, args.die_height_um
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    layout = args.layout.resolve()
    if not layout.exists():
        raise SystemExit(f"layout not found: {layout}")
    technology = render_profile(
        manifest, path, pex_profile, process.device_bindings
    ).resolve()
    output = (
        args.output
        or ROOT / "build" / "rf" / f"{args.profile}_{pex_profile}.json"
    ).resolve()
    extracted_output = (
        args.extracted_output or output.with_suffix(".spice")
    ).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    extracted_output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{args.profile}-rf-pex-") as temp:
        extracted, magic_log = run_magic_extract(
            args.magic,
            layout,
            technology,
            extracted_output,
            Path(temp),
            str(
                (manifest.get("technology") or {})
                .get("topology", {})
                .get("style", "scmos")
            ),
        )

    elements, ignored = parse_lumped_elements(extracted)
    if args.require_rc and not elements:
        raise SystemExit("RF workbench found no extracted resistor/capacitor elements")
    report = build_report(
        profile=args.profile,
        pex_profile=pex_profile,
        manifest=manifest,
        elements=elements,
        ignored=ignored,
        frequencies_hz=frequencies,
        die_width_um=args.die_width_um,
        die_height_um=args.die_height_um,
        critical_nets=args.critical_nets,
    )
    report["artifacts"] = {
        "technology": str(technology),
        "extracted_spice": str(extracted_output),
    }
    report["runtime"] = {
        "magic_warning_lines": sum(
            1 for line in magic_log.splitlines() if "Warning:" in line
        ),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"[run_rf_workbench] PASS: {args.profile}/{pex_profile}")
    print(f"  extracted R/C elements: {len(elements)}")
    print(f"  parallel terminal pairs: {len(report['parallel_pairs'])}")
    print(f"  report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
