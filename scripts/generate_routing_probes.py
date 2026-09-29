#!/usr/bin/env python3
"""Generate deterministic KLayout GDS micro-layouts for routing probes.

This script is executed inside KLayout's Python runtime.  It only draws probe
geometry; DRC/LVS execution and classification stay in the host runner.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pya

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.gds_layer_map import (  # noqa: E402
    gds_text_stream,
    validate_layout_layer_pairs,
    validate_profile_gds_map,
)
from common.process_ir import load_process  # noqa: E402
from common.routing_probes import ProbeSpec  # noqa: E402

DBU = 0.001
GRID = 0.15


def snap(value: float) -> float:
    return round(round(value / GRID) * GRID, 6)


def db(value: float) -> int:
    return int(round(snap(value) / DBU))


def logical_layer(layout: pya.Layout, process, name: str, gds_index: int = 0) -> int:
    layer = process.layers[name]
    gds = (layer.get("gds") or [])[gds_index]
    return layout.layer(int(gds["layer"]), int(gds["datatype"]))


def rect(top: pya.Cell, layer: int, x0: float, y0: float, x1: float, y1: float) -> None:
    top.shapes(layer).insert(pya.Box(db(min(x0, x1)), db(min(y0, y1)), db(max(x0, x1)), db(max(y0, y1))))


def wire(top: pya.Cell, layer: int, x0: float, y0: float, x1: float, y1: float, width: float) -> None:
    half = width / 2.0
    if y0 == y1:
        rect(top, layer, x0, y0 - half, x1, y1 + half)
    elif x0 == x1:
        rect(top, layer, x0 - half, y0, x1 + half, y1)
    else:
        rect(top, layer, x0 - half, y0 - half, x1 + half, y1 + half)


def label(top: pya.Cell, text_layer: int, name: str, x: float, y: float) -> None:
    top.shapes(text_layer).insert(pya.Text(name, pya.Trans(pya.Point(db(x), db(y)))))


def generate(process, spec: ProbeSpec, output: Path) -> None:
    global GRID
    GRID = float(process.grid_um)
    layout = pya.Layout()
    layout.dbu = DBU
    top = layout.create_cell(spec.name)
    source_layer = logical_layer(layout, process, spec.conductor)
    target_layer = logical_layer(layout, process, spec.target) if spec.target else None
    cut_layer = (
        logical_layer(layout, process, spec.cut, int(spec.metadata.get("cut_gds_index", 0)))
        if spec.cut
        else None
    )
    width = spec.width_um

    def emit_label(name: str, x: float, y: float, logical_layer_name: str) -> None:
        text_layer = layout.layer(
            *gds_text_stream(process.profile_dir, logical_layer_name, "net")
        )
        label(top, text_layer, name, x, y)

    if spec.kind == "wire":
        wire(top, source_layer, 20, 50, 100, 50, width)
        emit_label("A", 21.5, 50, spec.conductor)
        emit_label("B", 98.5, 50, spec.conductor)
    elif spec.kind == "tee":
        wire(top, source_layer, 20, 50, 100, 50, width)
        wire(top, source_layer, 60, 50, 60, 85, width)
        emit_label("A", 21.5, 50, spec.conductor)
        emit_label("B", 98.5, 50, spec.conductor)
        emit_label("C", 60, 83.5, spec.conductor)
    elif spec.kind == "same_layer_crossing":
        wire(top, source_layer, 20, 45, 100, 45, width)
        wire(top, source_layer, 60, 20, 60, 80, width)
        emit_label("A", 21.5, 45, spec.conductor)
        emit_label("B", 98.5, 45, spec.conductor)
        emit_label("C", 60, 21.5, spec.conductor)
        emit_label("D", 60, 78.5, spec.conductor)
    elif spec.kind == "isolated_crossing":
        assert target_layer is not None
        wire(top, source_layer, 20, 45, 100, 45, width)
        wire(top, target_layer, 60, 20, 60, 80, width)
        emit_label("A", 21.5, 45, spec.conductor)
        emit_label("B", 98.5, 45, spec.conductor)
        emit_label("C", 60, 21.5, spec.target)
        emit_label("D", 60, 78.5, spec.target)
    elif spec.kind == "spacing":
        spacing = float(spec.metadata["spacing_um"])
        center_gap = width + spacing
        lower = 50 - center_gap / 2
        upper = 50 + center_gap / 2
        wire(top, source_layer, 20, lower, 100, lower, width)
        wire(top, source_layer, 20, upper, 100, upper, width)
        emit_label("A", 21.5, lower, spec.conductor)
        emit_label("B", 98.5, lower, spec.conductor)
        emit_label("C", 21.5, upper, spec.conductor)
        emit_label("D", 98.5, upper, spec.conductor)
    elif spec.kind == "butting_contact":
        assert target_layer is not None
        wire(top, source_layer, 20, 50, 55, 50, width)
        wire(top, target_layer, 55, 50, 100, 50, width)
        emit_label("A", 21.5, 50, spec.conductor)
        emit_label("B", 98.5, 50, spec.target)
    elif spec.kind in {"transition", "enclosure"}:
        assert target_layer is not None and cut_layer is not None
        enclosure = float(spec.metadata.get("enclosure_um", 0.0))
        conductor_width = width + 2 * enclosure
        wire(top, source_layer, 20, 50, 55 + conductor_width / 2, 50, conductor_width)
        wire(top, target_layer, 55 - conductor_width / 2, 50, 100, 50, conductor_width)
        cut_width = float(spec.metadata.get("cut_width_um", width))
        rect(
            top,
            cut_layer,
            55 - cut_width / 2,
            50 - cut_width / 2,
            55 + cut_width / 2,
            50 + cut_width / 2,
        )
        emit_label("A", 21.5, 50, spec.conductor)
        emit_label("B", 98.5, 50, spec.target)
    elif spec.kind == "active_crossing":
        active = logical_layer(layout, process, "active")
        rect(top, active, 40, 42, 80, 68)
        select_name = spec.metadata.get("active_select", "nselect")
        if select_name in process.layers and process.layers[select_name].get("available", True):
            select = logical_layer(layout, process, select_name)
            rect(top, select, 38, 40, 82, 70)
        if spec.region == "active_p" and "nwell" in process.layers:
            well = logical_layer(layout, process, "nwell")
            rect(top, well, 32, 34, 88, 76)
        wire(top, source_layer, 60, 20, 60, 90, width)
        emit_label("A", 60, 21.5, spec.conductor)
        emit_label("B", 60, 88.5, spec.conductor)
    else:
        raise ValueError(f"unsupported probe kind {spec.kind!r}")

    validate_layout_layer_pairs(layout, process.profile_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output))


def main() -> int:
    profile = os.environ["SILICONCRAFT_PROBE_PROFILE"]
    grammar_path = Path(os.environ["SILICONCRAFT_PROBE_GRAMMAR"])
    output_dir = Path(os.environ["SILICONCRAFT_PROBE_OUTPUT"])
    specs = [ProbeSpec(**item) for item in json.loads(Path(os.environ["SILICONCRAFT_PROBE_SPECS"]).read_text())]
    process = load_process(profile, ROOT)
    validate_profile_gds_map(process.profile_dir, process.layers_doc)
    records = []
    for spec in specs:
        output = output_dir / f"{spec.name}.gds"
        generate(process, spec, output)
        records.append({**spec.as_dict(), "layout": str(output), "top_cell": spec.name})
    (output_dir / "probes.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(f"[generate_routing_probes] PASS profile={profile} probes={len(records)} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
