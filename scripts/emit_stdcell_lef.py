#!/usr/bin/env python3
"""Emit a LEF-compatible geometry-plan abstract for one stdcell candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.stdcell.lef import lef_text  # noqa: E402
from common.stdcell.process import StdcellProcess  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=int, default=0)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    profile = manifest["process"]["profile"]
    process = StdcellProcess.load(profile, ROOT)
    widths = {layer: process.metal_width_um(layer) for layer in ("M1", "M2", "M3") if process.has_layer(layer)}
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(lef_text(manifest, args.candidate, layer_widths=widths))
    candidate = next(
        item for item in manifest["candidates"] if item["candidate_index"] == args.candidate
    )
    print(
        f"[emit_stdcell_lef] PASS cell={candidate['cell']} "
        f"candidate={args.candidate} status=geometry_plan output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
