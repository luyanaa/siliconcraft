#!/usr/bin/env python3
"""Render one planned stdcell candidate into a KLayout GDS file.

Run inside KLayout because this script uses ``pya``:

  SILICONCRAFT_MANIFEST=build/stdcell/ami06/inv.json \
  SILICONCRAFT_CANDIDATE=0 \
  SILICONCRAFT_OUTPUT=build/stdcell/ami06/inv.gds \
  klayout -b -r scripts/render_stdcell.py

The result is a geometry artifact for subsequent DRC/LVS/PEX.  The script
never marks those checks as passed.
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
    auxiliary_stream,
    gds_text_stream,
    validate_layout_layer_pairs,
    validate_profile_gds_map,
)
from common.stdcell.process import StdcellProcess  # noqa: E402

def render_tap(top, layout, layer, process, tap):
    """Render the small self-tap geometry without the analog PCell library."""
    tech = process.tech
    polarity = "n" if tap["cell"].lower() == "ntap" else "p"
    active_layer = process.stdcell_layer("active", polarity)
    select_layer_name = process.stdcell_layer("select", polarity)
    well_layer = process.stdcell_layer("well", polarity)
    rows = max(1, int(tap["rows"]))
    columns = max(1, int(tap["columns"]))
    size = tech.contact_size
    spacing = tech.contact_spacing
    contact_w = columns * size + (columns - 1) * spacing
    contact_h = rows * size + (rows - 1) * spacing
    left = -contact_w / 2.0
    bottom = -contact_h / 2.0
    x_offset = float(tap["x_um"])
    y_offset = float(tap["y_um"])

    def rect(logical, x0, y0, x1, y1):
        top.shapes(layer(logical)).insert(
            pya.Box(
                db(x_offset + x0, layout.dbu),
                db(y_offset + y0, layout.dbu),
                db(x_offset + x1, layout.dbu),
                db(y_offset + y1, layout.dbu),
            )
        )

    for column in range(columns):
        for row in range(rows):
            x = left + column * (size + spacing)
            y = bottom + row * (size + spacing)
            rect("cc", x, y, x + size, y + size)
    active_enc = tech.active_contact_enc
    active_left = left - active_enc
    active_bottom = bottom - active_enc
    active_right = left + contact_w + active_enc
    active_top = bottom + contact_h + active_enc
    if active_right - active_left < tech.active_min:
        extra = (tech.active_min - (active_right - active_left)) / 2.0
        active_left -= extra
        active_right += extra
    if active_top - active_bottom < tech.active_min:
        extra = (tech.active_min - (active_top - active_bottom)) / 2.0
        active_bottom -= extra
        active_top += extra
    rect(active_layer, active_left, active_bottom, active_right, active_top)
    metal_enc = tech.metal_contact_enc
    rect(
        "metal1",
        left - metal_enc,
        bottom - metal_enc,
        left + contact_w + metal_enc,
        bottom + contact_h + metal_enc,
    )
    select = str(select_layer_name).lower()
    select_layer = process.ir.layers.get(select)
    select_available = bool(select_layer and select_layer.get("available", True))
    select_enc = tech.select_active_enc
    if select_available:
        rect(
            select,
            active_left - select_enc,
            active_bottom - select_enc,
            active_right + select_enc,
            active_top + select_enc,
        )
    elif not (
        select == "pselect"
        and process.ir.layers_doc.get("meta", {}).get("features", {}).get("pselectFromActive")
    ):
        raise RuntimeError(f"{process.profile_name}: tap requires layer {select}")
    if select == "nselect":
        well_extent = tech.nwell_active_enc
        well_left = active_left - well_extent
        well_bottom = active_bottom - well_extent
        well_right = active_right + well_extent
        well_top = active_top + well_extent
        if well_right - well_left < tech.nwell_min_width:
            extra = (tech.nwell_min_width - (well_right - well_left)) / 2.0
            well_left -= extra
            well_right += extra
        if well_top - well_bottom < tech.nwell_min_width:
            extra = (tech.nwell_min_width - (well_top - well_bottom)) / 2.0
            well_bottom -= extra
            well_top += extra
        rect(well_layer, well_left, well_bottom, well_right, well_top)

def db(value: float, dbu: float) -> int:
    return int(round(float(value) / dbu))


def rectangle(top, layout, layer, x0, y0, x1, y1, width, endpoint_overlap=False):
    half = width / 2.0
    if abs(x1 - x0) >= abs(y1 - y0):
        left, right = sorted((x0, x1))
        bottom, top_edge = sorted((y0, y1))
        if endpoint_overlap:
            left -= half
            right += half
        bottom -= half
        top_edge += half
    else:
        left, right = sorted((x0, x1))
        bottom, top_edge = sorted((y0, y1))
        if endpoint_overlap:
            bottom -= half
            top_edge += half
        left -= half
        right += half
    top.shapes(layer).insert(
        pya.Box(db(left, layout.dbu), db(bottom, layout.dbu), db(right, layout.dbu), db(top_edge, layout.dbu))
    )


def main() -> int:
    manifest_path = Path(os.environ["SILICONCRAFT_MANIFEST"])
    output = Path(os.environ["SILICONCRAFT_OUTPUT"])
    candidate_index = int(os.environ.get("SILICONCRAFT_CANDIDATE", "0"))
    payload = json.loads(manifest_path.read_text())
    candidate = payload["candidates"][candidate_index]
    profile_name = payload["process"]["profile"]
    process = StdcellProcess.load(profile_name, ROOT)
    profile = process.profile
    profile_dir = ROOT / "profiles" / profile_name
    validate_profile_gds_map(profile_dir, profile.layers_doc)

    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell(f"{candidate['cell']}_c{candidate_index}")

    physical = {
        "NWELL": "nwell",
        "ACTIVE": "active",
        "NSELECT": "nselect",
        "PSELECT": "pselect",
        "M1": "metal1",
        "M2": "metal2",
        "M3": "metal3",
        "POLY": "poly",
        "CC": "cc",
        "CP": "cc",
        "VIA12": "via",
        "VIA23": "via2",
    }
    layer_cache = {}

    def layer(logical):
        key = str(logical).upper()
        physical_name = physical.get(key, str(logical).lower())
        if physical_name not in layer_cache:
            layer_cache[physical_name] = layout.layer(profile.layer_info(physical_name))
        return layer_cache[physical_name]

    rows = candidate["geometry"].get("rows", {})
    if not rows:
        raise RuntimeError("candidate manifest has no row-level geometry")
    for row in rows.values():
        for shape_group in ("active", "select", "wells", "gates", "contacts"):
            for shape in row.get(shape_group, ()):
                if (
                    str(shape["layer"]).upper() == "PSELECT"
                    and not bool(
                        process.ir.layers.get("pselect")
                        and process.ir.layers["pselect"].get("available", True)
                    )
                    and process.ir.layers_doc.get("meta", {}).get("features", {}).get("pselectFromActive")
                ):
                    continue
                top.shapes(layer(shape["layer"])).insert(
                    pya.Box(
                        db(shape["x0"], layout.dbu),
                        db(shape["y0"], layout.dbu),
                        db(shape["x1"], layout.dbu),
                        db(shape["y1"], layout.dbu),
                    )
                )

    cell_width = candidate["geometry"]["width_um"]
    cell_height = candidate["geometry"]["height_um"]
    support_taps = candidate.get("support_taps", ())
    for tap in support_taps:
        render_tap(top, layout, layer, process, tap)

    substrate_stream = auxiliary_stream(profile_dir, "substrate_universe")
    if substrate_stream is not None:
        # Legacy SCMOS profiles use this helper layer for substrate extraction.
        # AMS C35 deliberately leaves it unset: 90/0 is not a C35 stream.
        max_support_x = max(
            [cell_width, *(tap["x_um"] for tap in support_taps)]
        )
        top.shapes(layout.layer(*substrate_stream)).insert(
            pya.Box(
                db(-20.0, layout.dbu),
                db(-20.0, layout.dbu),
                db(max_support_x + 20.0, layout.dbu),
                db(cell_height + 20.0, layout.dbu),
            )
        )

    widths = {
        "M1": process.metal_width_um("M1"),
        "M2": process.metal_width_um("M2"),
        "POLY": profile.semantic_rule("poly.min_width", ("width", "3.1", "poly", None)),
        "VIA12": process.via_size_um("M1", "M2"),
    }
    if process.has_layer("M3"):
        widths["M3"] = process.metal_width_um("M3")
        widths["VIA23"] = process.via_size_um("M2", "M3")
    for segment in candidate["routing"]["segments"]:
        logical = segment["layer"]
        if logical not in physical:
            continue
        rectangle(
            top,
            layout,
            layer(logical),
            segment["x0"],
            segment["y0"],
            segment["x1"],
            segment["y1"],
            widths[logical],
            endpoint_overlap=segment["purpose"] == "graph_route" and logical in {"M1", "M2", "M3"},
        )

    via_layers = {
        "VIA12": ("M1", "M2", process.tech.via_lower_enc, process.tech.via_upper_enc),
    }
    if process.has_layer("M3"):
        via_layers["VIA23"] = (
            "M2",
            "M3",
            process.tech.via2_lower_enc,
            process.tech.via2_upper_enc,
        )
    for via in candidate["routing"]["via_blockage_map"]:
        top.shapes(layer(via["layer"])).insert(
            pya.Box(
                db(via["x0"], layout.dbu),
                db(via["y0"], layout.dbu),
                db(via["x1"], layout.dbu),
                db(via["y1"], layout.dbu),
            )
        )
        lower, upper, lower_enc, upper_enc = via_layers[via["layer"]]
        via_size = max(via["x1"] - via["x0"], via["y1"] - via["y0"])
        center_x = (via["x0"] + via["x1"]) / 2.0
        center_y = (via["y0"] + via["y1"]) / 2.0
        for metal, enclosure in ((lower, lower_enc), (upper, upper_enc)):
            landing_half = via_size / 2.0 + enclosure
            top.shapes(layer(metal)).insert(
                pya.Box(
                    db(center_x - landing_half, layout.dbu),
                    db(center_y - landing_half, layout.dbu),
                    db(center_x + landing_half, layout.dbu),
                    db(center_y + landing_half, layout.dbu),
                )
            )
    for shape in candidate["routing"].get("pin_shapes", ()):
        top.shapes(layer(shape["layer"])).insert(
            pya.Box(
                db(shape["x0"], layout.dbu),
                db(shape["y0"], layout.dbu),
                db(shape["x1"], layout.dbu),
                db(shape["y1"], layout.dbu),
            )
        )

    def label(name, x_um, y_um, logical_layer_name="M1"):
        text_layer = layout.layer(
            *gds_text_stream(profile_dir, logical_layer_name, "net")
        )
        top.shapes(text_layer).insert(
            pya.Text(name, pya.Trans(pya.DPoint(x_um, y_um).to_itype(layout.dbu)))
        )

    segments = candidate["routing"]["segments"]
    for name, access in candidate["routing"]["pin_access_regions"].items():
        gate_segments = [
            segment
            for segment in segments
            if segment["net"] == name and segment["purpose"] == "gate_connection"
        ]
        if gate_segments:
            segment = gate_segments[0]
            label(
                name,
                segment["x0"],
                (segment["y0"] + segment["y1"]) / 2.0,
                profile.ir.meta.get("stdcell_pin_label_layer") or segment["layer"],
            )
            continue
        net_segments = [segment for segment in segments if segment["net"] == name]
        if net_segments:
            segment = net_segments[0]
            label(
                name,
                (segment["x0"] + segment["x1"]) / 2.0,
                (segment["y0"] + segment["y1"]) / 2.0,
                segment["layer"],
            )

    for supply in ("VDD", "VSS"):
        rails = [
            segment
            for segment in segments
            if segment["net"] == supply and segment["purpose"] == "rail"
        ]
        if rails:
            rail = rails[0]
            label(
                supply,
                (rail["x0"] + rail["x1"]) / 2.0,
                (rail["y0"] + rail["y1"]) / 2.0,
                rail["layer"],
            )

    for tap in support_taps:
        label(tap["net"], tap["x_um"], tap["y_um"], "M1")

    for row in rows.values():
        for name, x_um, y_um in row.get("labels", ()):
            label(name, x_um, y_um, "M1")
        for well in row.get("wells", ()):
            if well.get("net"):
                # Keep the well label inside NWELL but outside active/poly;
                # a center label can land on the row's common gate.
                label(
                    well["net"],
                    well["x0"] + profile.lambda_um,
                    (well["y0"] + well["y1"]) / 2.0,
                )
    validate_layout_layer_pairs(layout, profile_dir)

    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output))
    print(
        f"[render_stdcell] profile={profile_name} cell={candidate['cell']} "
        f"candidate={candidate_index} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
