#!/usr/bin/env python3
"""Evaluate public typical R_wire_only for canonical wire segments.

Example:
  python3 scripts/run_r_only_pex.py --profile xh018 \
    --segment metal1:10:0.56 --segment metal2:20:0.56
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.r_only import ROnlyError, WireSegment, build_r_wire_only_report  # noqa: E402
from common.process_ir import load_process  # noqa: E402


def parse_segment(value: str) -> WireSegment:
    try:
        layer, length, width = value.split(":", 2)
        return WireSegment(layer=layer, length_um=float(length), width_um=float(width))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "segments must use LAYER:LENGTH_UM:WIDTH_UM"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pex-profile", default="public_r_only")
    parser.add_argument(
        "--segment",
        action="append",
        type=parse_segment,
        required=True,
        help="LAYER:LENGTH_UM:WIDTH_UM; repeat for each wire segment",
    )
    args = parser.parse_args()

    process = load_process(args.profile, ROOT)
    try:
        report = build_r_wire_only_report(
            process.pex_doc,
            args.segment,
            profile_name=args.pex_profile,
        )
    except ROnlyError as exc:
        raise SystemExit(f"R-only PEX error: {exc}") from exc
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
