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

from common.pcells.scmos import Profile, register_profile  # noqa: E402


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
    profile_dir = ROOT / "profiles" / profile_name
    profile = Profile(profile_dir)
    library_name = f"siliconcraft_{profile_name}"
    register_profile(profile_dir, library_name)

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
        "VIA12": "via",
        "VIA23": "via2",
    }
    layer_cache = {}

    def layer(logical):
        if logical not in layer_cache:
            physical_name = physical[logical]
            layer_cache[logical] = layout.layer(profile.layer_info(physical_name))
        return layer_cache[logical]

    for device in candidate["devices"]:
        pcell_name = "nmos" if device["polarity"] == "n" else "pmos"
        pcell = layout.create_cell(
            pcell_name,
            library_name,
            {
                "nf": device["nf"],
                "m": 1,
                "w_um": device["width_per_finger_um"],
                "l_um": device["length_um"],
                "left_contact": "left" not in device.get("contactless_sides", ()),
                "right_contact": "right" not in device.get("contactless_sides", ()),
            },
        )
        if pcell is None:
            raise RuntimeError(f"KLayout failed to instantiate {pcell_name}")
        top.insert(
            pya.CellInstArray(
                pcell.cell_index(),
                pya.Trans(db(device["x_um"], layout.dbu), db(device["y_um"], layout.dbu)),
            )
        )

    pmos = [device for device in candidate["devices"] if device["polarity"] == "p"]
    if pmos:
        x0 = min(device["x_um"] - device["footprint"]["width_um"] / 2.0 for device in pmos)
        y0 = min(device["y_um"] - device["footprint"]["height_um"] / 2.0 for device in pmos)
        x1 = max(device["x_um"] + device["footprint"]["width_um"] / 2.0 for device in pmos)
        y1 = max(device["y_um"] + device["footprint"]["height_um"] / 2.0 for device in pmos)
        top.shapes(layer("NWELL")).insert(
            pya.Box(
                db(x0, layout.dbu),
                db(y0, layout.dbu),
                db(x1, layout.dbu),
                db(y1, layout.dbu),
            )
        )
    for bridge in candidate["geometry"].get("diffusion_bridges", ()):
        logical = bridge["layer"]
        if logical not in physical:
            continue
        top.shapes(layer(logical)).insert(
            pya.Box(
                db(bridge["x0"], layout.dbu),
                db(bridge["y0"], layout.dbu),
                db(bridge["x1"], layout.dbu),
                db(bridge["y1"], layout.dbu),
            )
        )

    cell_width = candidate["geometry"]["width_um"]
    cell_height = candidate["geometry"]["height_um"]
    support_taps = candidate.get("support_taps", ())
    for tap in support_taps:
        tap_cell = layout.create_cell(
            tap["cell"],
            library_name,
            {"rows": tap["rows"], "columns": tap["columns"]},
        )
        if tap_cell is None:
            raise RuntimeError(f"KLayout failed to instantiate {tap['cell']}")
        top.insert(
            pya.CellInstArray(
                tap_cell.cell_index(),
                pya.Trans(db(tap["x_um"], layout.dbu), db(tap["y_um"], layout.dbu)),
            )
        )

    # Preserve the substrate universe used by the authoritative SCMOS
    # extraction/DRC decks; without it pBulk is clipped at the top-cell bbox.
    max_support_x = max(
        [cell_width, *(tap["x_um"] for tap in support_taps)]
    )
    top.shapes(layout.layer(90, 0)).insert(
        pya.Box(
            db(-20.0, layout.dbu),
            db(-20.0, layout.dbu),
            db(max_support_x + 20.0, layout.dbu),
            db(cell_height + 20.0, layout.dbu),
        )
    )

    widths = {
        "M1": profile.rule_or("width", "7.1", "metal1", None, 3 * profile.lambda_um),
        "M2": profile.rule_or("width", "9.1", "metal2", None, 3 * profile.lambda_um),
        "M3": profile.rule_or("width", "15.1", "metal3", None, 3 * profile.lambda_um),
        "POLY": profile.rule_or("width", "3.1", "poly", None, 2 * profile.lambda_um),
        "VIA12": 2 * profile.lambda_um,
        "VIA23": 2 * profile.lambda_um,
    }
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
        "VIA12": ("M1", "M2", "8.3", "9.3", "via"),
        "VIA23": ("M2", "M3", "14.3", "15.3", "via2"),
    }
    for via in candidate["routing"]["via_blockage_map"]:
        top.shapes(layer(via["layer"])).insert(
            pya.Box(
                db(via["x0"], layout.dbu),
                db(via["y0"], layout.dbu),
                db(via["x1"], layout.dbu),
                db(via["y1"], layout.dbu),
            )
        )
        lower, upper, lower_rule, upper_rule, rule_layer = via_layers[via["layer"]]
        via_size = max(via["x1"] - via["x0"], via["y1"] - via["y0"])
        lower_enc = profile.rule_or(
            "enclosure", lower_rule, physical[lower], rule_layer, profile.lambda_um
        )
        upper_enc = profile.rule_or(
            "enclosure", upper_rule, physical[upper], rule_layer, profile.lambda_um
        )
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

    text_layer = layout.layer(64, 0)

    def label(name, x_um, y_um):
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
            label(name, segment["x0"], (segment["y0"] + segment["y1"]) / 2.0)
            continue
        net_segments = [segment for segment in segments if segment["net"] == name]
        if net_segments:
            segment = net_segments[0]
            label(name, (segment["x0"] + segment["x1"]) / 2.0, (segment["y0"] + segment["y1"]) / 2.0)

    for supply in ("VDD", "VSS"):
        rails = [
            segment
            for segment in segments
            if segment["net"] == supply and segment["purpose"] == "rail"
        ]
        if rails:
            rail = rails[0]
            label(supply, (rail["x0"] + rail["x1"]) / 2.0, (rail["y0"] + rail["y1"]) / 2.0)

    for tap in support_taps:
        label(tap["net"], tap["x_um"], tap["y_um"])

    for device in candidate["devices"]:
        footprint = device["footprint"]
        contactless = set(device.get("contactless_sides", ()))
        if "left" not in contactless:
            label(
                device["left_net"],
                device["x_um"] + footprint["left_contact_x_um"],
                device["y_um"],
            )
        if "right" not in contactless:
            label(
                device["right_net"],
                device["x_um"] + footprint["right_contact_x_um"],
                device["y_um"],
            )

    for device in candidate["devices"]:
        if device["polarity"] != "p":
            continue
        # Label the n-well away from the active/poly center so LVS can name
        label(
            "VDD",
            device["x_um"],
            device["y_um"] + device["footprint"]["height_um"] / 2.0 - profile.lambda_um,
        )

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
