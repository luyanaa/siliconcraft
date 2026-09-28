#!/usr/bin/env python3
"""Compile readable PDK LVS connectivity into a conservative routing grammar."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.routing_grammar import inspect_profile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    grammar = inspect_profile(args.profile, ROOT)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    grammar.write(output)
    print(
        f"[inspect_routing_grammar] PASS profile={args.profile} "
        f"source={grammar.source_kind} conductors={len(grammar.conductors)} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
