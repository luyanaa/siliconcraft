#!/usr/bin/env python3
"""Regression checks for the AMS C35B4C3 GDS stream contract."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.gds_layer_map import (  # noqa: E402
    GDSLayerMapError,
    auxiliary_stream,
    gds_text_stream,
    load_gds_layer_map,
    require_fab_authority,
    validate_profile_gds_map,
)
from common.process_ir import load_process  # noqa: E402


EXPECTED_MASKS = {
    "NTUB": (5, 0),
    "DIFF": (10, 0),
    "POLY1": (20, 0),
    "NPLUS": (23, 0),
    "PPLUS": (24, 0),
    "HRES": (29, 0),
    "POLY2": (30, 0),
    "CONT": (34, 0),
    "MET1": (35, 0),
    "VIA1": (36, 0),
    "MET2": (37, 0),
    "VIA2": (38, 0),
    "MET3": (39, 0),
    "PAD": (40, 0),
    "VIA3": (41, 0),
    "MET4": (42, 0),
}


def stream(entry: dict) -> tuple[int, int]:
    raw = entry["stream"]
    return int(raw["layer"]), int(raw["datatype"])


def main() -> int:
    profile_dir = ROOT / "profiles" / "ams_c35"
    process = load_process("ams_c35", ROOT)
    document = load_gds_layer_map(profile_dir)
    assert document is not None
    validate_profile_gds_map(profile_dir, process.layers_doc)
    assert document["process"] == "C35B4C3"
    assert document["database"]["grid_um"] == 0.025
    assert document["source"]["authority"] == "public_reference"
    assert document["source"]["fab_signoff"] is False

    masks = {entry["name"]: entry for entry in document["mask_layers"]}
    for name, expected in EXPECTED_MASKS.items():
        assert stream(masks[name]) == expected, (name, stream(masks[name]))

    assert gds_text_stream(profile_dir, "M1", "net") == (61, 22)
    assert gds_text_stream(profile_dir, "M2", "net") == (61, 23)
    assert gds_text_stream(profile_dir, "POLY", "net") == (61, 21)
    assert auxiliary_stream(profile_dir, "substrate_universe") is None

    try:
        require_fab_authority(profile_dir)
    except GDSLayerMapError as exc:
        assert "public reference snapshot" in str(exc)
    else:
        raise AssertionError("public reference map unexpectedly passed fab authority gate")

    print(
        f"AMS C35 GDS map: PASS ({len(document['mask_layers'])} mask entries, "
        f"{len(document['text_layers'])} text streams)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
