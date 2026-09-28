#!/usr/bin/env python3
"""Compatibility entry point for the process-neutral Magic PEX generator.

The LS1u manifest remains the source of LS1u topology and coefficients. This
wrapper preserves the historical command and helper imports while the shared
renderer supports additional process profiles.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import (  # noqa: E402,F401
    MagicPexError,
    area_cap_to_magic_af_per_lambda2,
    edge_cap_to_magic_af_per_lambda,
    render_profile_extract,
    render_topology,
    sheet_to_magic_mohm,
)


def main() -> int:
    from gen_magic_pex import main as generic_main

    args = sys.argv[1:]
    if "--profile" in args:
        index = args.index("--profile")
        if index + 1 >= len(args):
            raise SystemExit("--profile requires an LS1u PEX profile name")
        profile_name = args[index + 1]
        args = args[:index] + args[index + 2 :]
        args[0:0] = ["--profile-name", profile_name]
    args[0:0] = ["--profile", "ls1u"]
    sys.argv[1:] = args
    return generic_main()


if __name__ == "__main__":
    raise SystemExit(main())
