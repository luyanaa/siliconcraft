#!/usr/bin/env python3
"""Generate process-specific Magic PEX profiles.

The manifest is the process contract.  The generator does not infer RC values
from SCMOS defaults; it only converts explicitly unit-tagged source data and
renders the process-selected Magic topology.

Usage:
  python3 scripts/gen_magic_pex.py --profile ami06 --all
  python3 scripts/gen_magic_pex.py --profile ls1u --profile-name none
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import (  # noqa: E402
    MagicPexError,
    generate_profile,
    topology_fragment,
)
from common.process_ir import load_process  # noqa: E402


def manifest_path(profile: str) -> Path:
    return ROOT / "profiles" / profile / "pex" / "manifest.yaml"


def write_topology_fragment(
    manifest: dict, path: Path, device_bindings: dict | None = None
) -> None:
    fragment = manifest.get("topology_fragment")
    if not fragment:
        return
    output = (path.parent / str(fragment)).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(topology_fragment(manifest, device_bindings))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, help="profile directory name")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--profile-name", help="one PEX profile name")
    group.add_argument("--all", action="store_true", help="generate all enabled profiles")
    args = ap.parse_args()

    process = load_process(args.profile, ROOT)
    path = process.profile_dir / "pex" / "manifest.yaml"
    if not path.exists():
        raise SystemExit(f"PEX manifest not found: {path}")
    manifest = process.pex_doc
    try:
        write_topology_fragment(manifest, path, process.device_bindings)
        if args.all:
            names = [
                name
                for name, spec in (manifest.get("profiles") or {}).items()
                if isinstance(spec, dict) and spec.get("generated") is True
            ]
        else:
            names = [args.profile_name]
        for name in names:
            print(
                f"wrote {generate_profile(manifest, path, name, process.device_bindings)}"
            )
    except MagicPexError as exc:
        raise SystemExit(f"PEX manifest error: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
