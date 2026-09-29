#!/usr/bin/env python3
"""Emit a canonical external field-solver sweep manifest for an XH profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.field_solver import (  # noqa: E402
    FieldSolverContractError,
    canonical_sweep_manifest,
)
from common.process_ir import load_process  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pex-profile", default="field_solver_estimated")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    process = load_process(args.profile, ROOT)
    try:
        result = canonical_sweep_manifest(
            process.pex_doc,
            profile_name=args.pex_profile,
        )
    except FieldSolverContractError as exc:
        raise SystemExit(f"field-solver contract error: {exc}") from exc
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
        print(f"wrote {args.output}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
