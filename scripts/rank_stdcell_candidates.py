#!/usr/bin/env python3
"""Rank generated stdcell candidates by geometry-only Pareto dominance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.stdcell.pareto import rank_geometry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    candidates = manifest.get("candidates", [])
    if not candidates:
        parser.error("manifest contains no candidates")
    first = candidates[0]
    result = {
        "profile": manifest.get("profile") or first.get("profile"),
        "cell": manifest.get("cell") or first.get("cell"),
        "architecture": manifest.get("architecture") or first.get("architecture"),
        **rank_geometry(candidates),
    }
    output = args.output or args.manifest.with_suffix(".pareto.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"[rank_stdcell_candidates] PASS cell={result['cell']} "
        f"candidates={len(candidates)} front={result['front_candidate_indices']} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
