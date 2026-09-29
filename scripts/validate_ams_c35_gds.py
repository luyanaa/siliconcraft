#!/usr/bin/env python3
"""Validate AMS C35B4C3 GDS streams before DRC/fab handoff.

Reference-map check (plain Python):
  python3 scripts/validate_ams_c35_gds.py --profile ams_c35

GDS layer-pair check (inside KLayout's Python runtime):
  SILICONCRAFT_PROFILE=ams_c35 SILICONCRAFT_GDS=build/layout.gds \
    klayout -b -r scripts/validate_ams_c35_gds.py
Production mode is deliberately fail-closed.  The checked-in map is a
pinned public C35B4 HIT-Kit snapshot, not the current licensed AMS/CMC map;
``--require-fab-authority`` therefore remains blocked until the profile is
updated with the current foundry-supplied stream map.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.gds_layer_map import (  # noqa: E402
    GDSLayerMapError,
    require_fab_authority,
    validate_layout_layer_pairs,
    validate_profile_gds_map,
)
from common.process_ir import load_process  # noqa: E402


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=os.environ.get("SILICONCRAFT_PROFILE", "ams_c35"),
    )
    gds = os.environ.get("SILICONCRAFT_GDS")
    parser.add_argument("--gds", type=Path, default=Path(gds) if gds else None)
    parser.add_argument("--require-fab-authority", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        process = load_process(args.profile, ROOT)
        document = validate_profile_gds_map(process.profile_dir, process.layers_doc)
        if document is None:
            raise GDSLayerMapError(
                f"{args.profile}: no checked-in GDS stream map; reference validation is unavailable"
            )
        if args.require_fab_authority:
            require_fab_authority(process.profile_dir)
        if args.gds is not None:
            try:
                import pya
            except ImportError as exc:  # pragma: no cover - KLayout-only path
                raise GDSLayerMapError(
                    "--gds requires KLayout's Python runtime (pya)"
                ) from exc
            layout = pya.Layout()
            layout.read(str(args.gds))
            validate_layout_layer_pairs(layout, process.profile_dir)
    except (GDSLayerMapError, OSError, ValueError) as exc:
        print(f"[validate_ams_c35_gds] FAIL: {exc}", file=sys.stderr)
        return 2

    source = document.get("source") or {}
    checked = "profile map"
    if args.gds is not None:
        checked += f" + {args.gds}"
    print(
        f"[validate_ams_c35_gds] PASS profile={args.profile} checked={checked} "
        f"authority={source.get('authority', 'unknown')} "
        f"fab_signoff={source.get('fab_signoff', False)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
