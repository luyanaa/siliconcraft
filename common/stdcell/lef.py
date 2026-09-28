"""LEF-compatible abstract views for planned stdcell candidates.

The writer intentionally emits a geometry-plan view, not a signoff library
view.  Pin access and blockage status remain visible in comments and metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _number(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def _rect(x0: float, y0: float, x1: float, y1: float) -> str:
    return "RECT " + " ".join(_number(value) for value in (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))) + " ;"


def _centerline_rect(segment: Mapping[str, Any], width: float) -> str:
    x0, y0 = float(segment["x0"]), float(segment["y0"])
    x1, y1 = float(segment["x1"]), float(segment["y1"])
    half = width / 2.0
    if y0 == y1:
        return _rect(x0, y0 - half, x1, y1 + half)
    if x0 == x1:
        return _rect(x0 - half, y0, x1 + half, y1)
    return _rect(x0 - half, y0 - half, x1 + half, y1 + half)


def _candidate(manifest: Mapping[str, Any], candidate_index: int) -> Mapping[str, Any]:
    candidates = manifest.get("candidates", [])
    for candidate in candidates:
        if int(candidate["candidate_index"]) == candidate_index:
            return candidate
    raise ValueError(f"candidate index {candidate_index} not present")


def lef_text(
    manifest: Mapping[str, Any],
    candidate_index: int = 0,
    *,
    layer_widths: Mapping[str, float] | None = None,
) -> str:
    """Render one candidate as syntactically complete LEF text."""
    candidate = _candidate(manifest, candidate_index)
    widths = {"M1": 0.9, "M2": 0.9, "M3": 0.9, **(layer_widths or {})}
    geometry = candidate["geometry"]
    circuit = manifest.get("circuit", {})
    ports = list(circuit.get("ports", ()))
    inputs = set(circuit.get("inputs", ()))
    outputs = set(circuit.get("outputs", ()))
    supplies = set(circuit.get("supplies", ()))
    pin_access = candidate["routing"].get("pin_access_regions", {})
    segments = candidate["routing"].get("segments", [])
    comments = [
        "# SiliconCraft geometry-plan abstract view; not signoff.",
        "# DRC/LVS/PEX status is owned by the external gate, not this LEF file.",
    ]
    lines = [
        "VERSION 5.8 ;",
        'BUSBITCHARS "[]" ;',
        'DIVIDERCHAR "/" ;',
        *comments,
        f"MACRO {candidate['cell']}",
        "  CLASS CORE ;",
        "  ORIGIN 0 0 ;",
        f"  SIZE {_number(geometry['width_um'])} BY {_number(geometry['height_um'])} ;",
        "  SYMMETRY X Y ;",
    ]

    rail_segments = {
        net: [
            segment
            for segment in segments
            if segment["net"] == net and segment["purpose"] == "rail"
        ]
        for net in supplies
    }
    for name in ports:
        if name in supplies:
            direction = "INOUT"
            use = "POWER" if name == "VDD" else "GROUND" if name == "VSS" else "SIGNAL"
        elif name in inputs:
            direction, use = "INPUT", "SIGNAL"
        elif name in outputs:
            direction, use = "OUTPUT", "SIGNAL"
        else:
            direction, use = "INOUT", "SIGNAL"
        lines.extend(
            [
                f"  PIN {name}",
                f"    DIRECTION {direction} ;",
                f"    USE {use} ;",
                "    PORT",
            ]
        )
        shapes = []
        if name in supplies:
            shapes.extend(
                (
                    segment["layer"],
                    _centerline_rect(segment, widths.get(segment["layer"], 0.9)),
                )
                for segment in rail_segments.get(name, [])
                if segment["layer"] in widths
            )
        else:
            access = pin_access.get(name)
            if access is not None:
                half = float(access["width_um"]) / 2.0
                x = float(access["x_um"])
                y = float(access["y_um"])
                shapes.append((access["layer"], _rect(x - half, y - half, x + half, y + half)))
                if access.get("access") != "legal":
                    lines.append(f"    # pin_access={access.get('access', 'unspecified')} ;")
        for layer, shape in shapes:
            lines.extend([f"      LAYER {layer} ;", f"        {shape}"])
        lines.extend(["    END", f"  END {name}"])

    lines.append("  OBS")
    for blockage in candidate["routing"].get("metal_blockage_map", []):
        layer = blockage["layer"]
        if layer not in widths:
            continue
        lines.extend(
            [
                f"    LAYER {layer} ;",
                f"      {_centerline_rect(blockage, widths[layer])}",
            ]
        )
    lines.extend(["  END", f"END {candidate['cell']}", "END LIBRARY", ""])
    return "\n".join(lines)
