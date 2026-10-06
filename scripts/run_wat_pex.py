#!/usr/bin/env python3
"""Evaluate the MOSIS WAT analytical RC flow (PEX v0) for a profile.

Example:
  python3 scripts/run_wat_pex.py --profile tsmc035_4m2p \
    --segment metal1:100:0.6 --segment metal1:5:0.6:contacts=2,contact_target=metal1 \
    --pair metal1:metal2:area=40,edge=20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402

from common.pex.wat_rc import (  # noqa: E402
    WatRcError,
    build_wat_rc_report,
    pair_from_mapping,
    segment_from_mapping,
)
from common.process_ir import load_process  # noqa: E402


def _kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in text.split(","):
        if not chunk:
            continue
        if "=" not in chunk:
            raise argparse.ArgumentTypeError(
                f"option {chunk!r} must use key=value"
            )
        key, value = chunk.split("=", 1)
        out[key.strip()] = value.strip()
    return out


# Friendly aliases.  An unknown key is an error: silently ignoring it would
# turn a typo into a confidently wrong RC number.
SEGMENT_KEYS = {
    "length_um": "length_um", "length": "length_um", "len": "length_um",
    "l": "length_um",
    "width_um": "width_um", "width": "width_um", "w": "width_um",
    "contacts": "contacts", "nc": "contacts",
    "contact_target": "contact_target", "ct": "contact_target",
    "vias": "vias", "nv": "vias",
    "via_target": "via_target", "vt": "via_target",
}
PAIR_KEYS = {
    "overlap_area_um2": "overlap_area_um2", "area": "overlap_area_um2",
    "a": "overlap_area_um2",
    "edge_length_um": "edge_length_um", "edge": "edge_length_um",
    "e": "edge_length_um",
}


def _canonicalize(raw: dict, allowed: dict, kind: str) -> dict:
    out = {}
    for key, value in raw.items():
        if key not in allowed:
            raise argparse.ArgumentTypeError(
                f"unknown {kind} option {key!r}; allowed: "
                + ", ".join(sorted(allowed))
            )
        out[allowed[key]] = value
    return out


def parse_segment(value: str) -> dict:
    """LAYER:LENGTH_UM:WIDTH_UM[:key=value,...]"""

    parts = value.split(":", 3)
    if len(parts) < 3:
        raise argparse.ArgumentTypeError(
            "segments must use LAYER:LENGTH_UM:WIDTH_UM[:key=value,...]"
        )
    raw = {"layer": parts[0], "length_um": parts[1], "width_um": parts[2]}
    if len(parts) == 4:
        raw.update(_canonicalize(_kv(parts[3]), SEGMENT_KEYS, "segment"))
    return raw


def parse_pair(value: str) -> dict:
    """LOWER:UPPER[:key=value,...]"""

    parts = value.split(":", 2)
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            "pairs must use LOWER:UPPER[:key=value,...]"
        )
    raw = {"lower": parts[0], "upper": parts[1]}
    if len(parts) == 3:
        raw.update(_canonicalize(_kv(parts[2]), PAIR_KEYS, "pair"))
    return raw


def resolve_reference(profile_dir: Path, spec: dict) -> Path:
    name = str(spec.get("reference_data") or "")
    if not name:
        raise SystemExit("PEX profile has no reference_data file")
    for candidate in (
        profile_dir / "pex" / name,
        profile_dir / name,
        ROOT / name,
    ):
        if candidate.exists():
            return candidate
    raise SystemExit(f"reference data file not found: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pex-profile", default="mosis_wat_rc")
    parser.add_argument("--coefficient-set", default=None)
    parser.add_argument("--segment", action="append", type=parse_segment, default=[])
    parser.add_argument("--pair", action="append", type=parse_pair, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    process = load_process(args.profile, ROOT)
    spec = (process.pex_doc.get("profiles") or {}).get(args.pex_profile)
    if not isinstance(spec, dict):
        raise SystemExit(f"unknown PEX profile {args.pex_profile!r}")

    profile_dir = ROOT / "profiles" / args.profile
    reference_path = resolve_reference(profile_dir, spec)
    reference_doc = yamlish.load(reference_path.read_text())
    if not isinstance(reference_doc, dict):
        raise SystemExit(f"{reference_path}: expected a mapping")

    try:
        report = build_wat_rc_report(
            process.pex_doc,
            reference_doc,
            [segment_from_mapping(item) for item in args.segment],
            [pair_from_mapping(item) for item in args.pair],
            profile_name=args.pex_profile,
            coefficient_set=args.coefficient_set,
        )
    except WatRcError as exc:
        raise SystemExit(f"WAT analytical PEX error: {exc}") from exc

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
        print(f"wrote {args.output}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
