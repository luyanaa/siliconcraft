#!/usr/bin/env python3
"""Generate deterministic stdcell geometry/routing candidate manifests.

This first executable stage consumes one transistor-level SPICE/CDL subcircuit
and emits candidate JSON.  DRC/LVS/PEX and characterization remain explicit
later gates; no signoff view is inferred from this manifest.

Example:
  python3 scripts/gen_stdcell.py --profile ami06 \
    --input common/tests/spice/stdcell/inv.spice \
    --architecture two_metal_classic \
    --output build/stdcell/ami06/inv.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.stdcell.netlist import parse_spice  # noqa: E402
from common.stdcell.planner import generate_candidates  # noqa: E402
from common.stdcell.pareto import rank_geometry  # noqa: E402
from common.stdcell.process import StdcellProcess  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="ami06")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--architecture",
        default="two_metal_classic",
        choices=("two_metal_classic", "two_metal_dense", "three_metal_classic"),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-candidates", type=int, default=100)
    parser.add_argument(
        "--beam-width",
        type=int,
        help="retain this many cheap geometry/routing Pareto candidates before detailed routing",
    )
    args = parser.parse_args()

    source = args.input if args.input.is_absolute() else ROOT / args.input
    if not source.exists():
        raise SystemExit(f"input netlist not found: {source}")
    if args.max_candidates < 1:
        raise SystemExit("--max-candidates must be >= 1")
    if args.beam_width is not None and args.beam_width < 1:
        raise SystemExit("--beam-width must be >= 1")

    circuit = parse_spice(source.read_text())
    process = StdcellProcess.load(args.profile, ROOT)
    candidates = generate_candidates(
        circuit,
        process,
        architecture=args.architecture,
        max_candidates=args.max_candidates,
        beam_width=args.beam_width,
    )
    candidate_payload = [candidate.as_dict() for candidate in candidates]

    payload = {
        "schema_version": 1,
        "kind": "stdcell_candidate_manifest",
        "status": "geometry_planned",
        "process": process.to_metadata(),
        "circuit": {
            "name": circuit.name,
            "ports": list(circuit.ports),
            "inputs": list(circuit.inputs),
            "outputs": list(circuit.outputs),
            "supplies": list(circuit.supplies),
            "timing_arcs": [list(arc) for arc in circuit.timing_arcs],
            "internal_nets": list(circuit.internal_nets),
        },
        "candidate_count": len(candidates),
        "candidates": candidate_payload,
        "geometry_pareto": rank_geometry(candidate_payload),
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    feedthrough = candidates[0].feedthrough_layer
    print(
        f"[gen_stdcell] profile={process.profile_name} cell={circuit.name} "
        f"architecture={args.architecture} candidates={len(candidates)} "
        f"feedthrough={feedthrough} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
