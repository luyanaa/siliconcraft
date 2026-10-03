#!/usr/bin/env python3
"""Generate a wired C35 current-mirror differential-pair regression macro in KLayout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.gds_layer_map import (  # noqa: E402
    gds_text_stream,
    validate_layout_layer_pairs,
    validate_profile_gds_map,
)
from common.pcells.scmos import Profile, Technology, register_profile  # noqa: E402

PROFILE_DIR = ROOT / "profiles/ams_c35"
VARIANT = "C35B4C3"
TOP_CELL = "ams_c35_mixed_signal"
DBU = 0.001


def main() -> int:
    output = Path(os.environ["AMS_C35_MIXED_SIGNAL_GDS"]).resolve()
    profile = Profile(PROFILE_DIR, variant=VARIANT)
    tech = Technology(profile)
    grid = profile.grid_um

    def snap(value: float) -> float:
        return round(round(value / grid) * grid, 6)

    def db(value: float) -> int:
        return int(round(snap(value) / DBU))

    layout = pya.Layout()
    layout.dbu = DBU
    library_name = f"siliconcraft_ams_c35_{VARIANT}"
    register_profile(PROFILE_DIR, library_name, variant=VARIANT)
    top = layout.create_cell(TOP_CELL)

    def logical_layer(name: str) -> int:
        entry = profile.layers[name]["gds"][0]
        return layout.layer(int(entry["layer"]), int(entry["datatype"]))

    layers = {
        name: logical_layer(name)
        for name in (
            "poly",
            "cc",
            "nwell",
            "metal1",
            "metal2",
        )
    }

    def rect(layer: int, x0: float, y0: float, x1: float, y1: float) -> None:
        top.shapes(layer).insert(
            pya.Box(db(min(x0, x1)), db(min(y0, y1)), db(max(x0, x1)), db(max(y0, y1)))
        )

    def place(name: str, x: float, params: dict[str, object]) -> None:
        cell = layout.create_cell(name, library_name, params)
        top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(db(x), 0)))

    pins: list[tuple[str, float, float, str]] = []

    def pin(name: str, x: float, y: float, net: str) -> None:
        pins.append((name, snap(x), snap(y), net))

    mos = (
        ("MREF", "nmos", 400.0, 2.4, "IBIAS", "IBIAS", "0"),
        ("MTAIL", "nmos", 460.0, 2.4, "TAIL", "IBIAS", "0"),
        ("MLEFT", "nmos", 520.0, 2.4, "NDL", "INP", "TAIL"),
        ("MRIGHT", "nmos", 580.0, 2.4, "VOUT", "INM", "TAIL"),
        ("MPREF", "pmos", 640.0, 4.8, "NDL", "NDL", "VDD"),
        ("MPOUT", "pmos", 700.0, 4.8, "VOUT", "NDL", "VDD"),
    )
    for name, cell_name, center, width, drain_net, gate_net, source_net in mos:
        length = 0.6
        place(
            cell_name,
            center,
            {"nf": 1, "m": 1, "w_um": width, "l_um": length},
        )
        poly_edge = (
            tech.poly_contact_spacing + tech.contact_size + tech.active_contact_enc
        )
        active_width = 2 * poly_edge + length
        left = -active_width / 2 + tech.active_contact_enc + tech.contact_size / 2
        right = active_width / 2 - tech.active_contact_enc - tech.contact_size / 2
        pin(f"{name}.D", center + left, 0.0, drain_net)
        pin(f"{name}.S", center + right, 0.0, source_net)

        active_height = max(width, tech.active_min)
        gate_y = active_height / 2 + tech.gate_extension + 2.8
        gate_x = center + 5.0
        contact = tech.contact_size
        poly_half = max(contact / 2 + tech.poly_contact_enc, 0.7)
        metal_half = contact / 2 + tech.metal_contact_enc
        gate_bottom = active_height / 2 + tech.gate_extension - 0.1
        rect(layers["poly"], center - 0.7, gate_bottom, center + 0.7, gate_y + poly_half)
        rect(layers["poly"], center - 0.7, gate_y - 0.7, gate_x + poly_half, gate_y + 0.7)
        rect(
            layers["cc"],
            gate_x - contact / 2,
            gate_y - contact / 2,
            gate_x + contact / 2,
            gate_y + contact / 2,
        )
        rect(
            layers["metal1"],
            gate_x - metal_half,
            gate_y - metal_half,
            gate_x + metal_half,
            gate_y + metal_half,
        )
        pin(f"{name}.G", gate_x, gate_y, gate_net)

    resistor_length = 200.0
    resistor_width = 0.65
    resistor_center = 130.0
    place(
        "rp2",
        resistor_center,
        {"length_um": resistor_length, "width_um": resistor_width},
    )
    terminal_length = 1.2
    outer_half = (resistor_length + 2 * terminal_length) / 2
    pin("RBIAS.P", resistor_center - outer_half + terminal_length / 2, 0.0, "VDD")
    pin("RBIAS.N", resistor_center + outer_half - terminal_length / 2, 0.0, "IBIAS")

    rpolyh_length = 60.0
    rpolyh_width = 1.0
    rpolyh_center = 830.0
    place(
        "rph",
        rpolyh_center,
        {"length_um": rpolyh_length, "width_um": rpolyh_width},
    )
    terminal_length = 1.6
    terminal_gap = 0.35
    rpolyh_body = rpolyh_length - 2 * terminal_gap
    rpolyh_outer = rpolyh_body + 2 * (terminal_length + terminal_gap)
    pin("RLOAD.P", rpolyh_center - rpolyh_outer / 2 + terminal_length / 2, 0.0, "VOUT")
    pin("RLOAD.N", rpolyh_center + rpolyh_outer / 2 - terminal_length / 2, 0.0, "0")

    cap_width = 24.0
    cap_height = 24.0
    place("cap_pip", 920.0, {"width_um": cap_width, "height_um": cap_height})
    bottom_x = -cap_width / 2 + tech.contact_size / 2 + 0.25
    bottom_y = -cap_height / 2 + tech.contact_size / 2 + 0.25
    top_x = (-cap_width / 2 + 2.0 + cap_width / 2 - 1.0) / 2
    top_y = (-cap_height / 2 + 2.0 + cap_height / 2 - 1.0) / 2
    pin("CPIP.BOTTOM", 920.0 + bottom_x, bottom_y, "0")
    pin("CPIP.TOP", 920.0 + top_x, top_y, "VOUT")

    place("ptap", 350.0, {"rows": 2, "columns": 2})
    pin("SUBSTRATE.TAP", 350.0, 0.0, "0")
    place("ntap", 760.0, {"rows": 2, "columns": 2})
    pin("NWELL.TAP", 760.0, 0.0, "VDD")
    rect(layers["nwell"], 630.0, -9.0, 770.0, 9.0)

    net_order = ("0", "VDD", "IBIAS", "TAIL", "NDL", "VOUT", "INP", "INM")
    y_by_net = {net: 100.0 + 6.0 * index for index, net in enumerate(net_order)}
    pin_x_by_net: dict[str, list[float]] = {net: [] for net in net_order}
    all_x: dict[float, tuple[str, str]] = {}
    for name, x, _y, net in pins:
        previous = all_x.get(x)
        if previous is not None and previous[1] != net:
            raise RuntimeError(
                f"vertical M1 routes would short {previous[0]} ({previous[1]}) "
                f"to {name} ({net}) at x={x:g}um"
            )
        all_x[x] = (name, net)
        pin_x_by_net[net].append(x)

    via = layout.create_cell("via12", library_name, {"rows": 1, "columns": 1})
    for net in net_order:
        y_track = y_by_net[net]
        xs = pin_x_by_net[net]
        if not xs:
            raise RuntimeError(f"mixed-signal macro has no physical pins on net {net}")
        for name, x, y, pin_net in pins:
            if pin_net != net:
                continue
            half = 0.5
            rect(layers["metal1"], x - half, min(y, y_track) - half, x + half, max(y, y_track) + half)
            top.insert(pya.CellInstArray(via.cell_index(), pya.Trans(db(x), db(y_track))))
        rect(layers["metal2"], min(xs) - 5.0, y_track - 0.6, max(xs) + 5.0, y_track + 0.6)
        text_layer = layout.layer(*gds_text_stream(PROFILE_DIR, "metal2", "net"))
        top.shapes(text_layer).insert(
            pya.Text(net, pya.Trans(pya.Point(db((min(xs) + max(xs)) / 2), db(y_track))))
        )

    validate_profile_gds_map(PROFILE_DIR)
    validate_layout_layer_pairs(layout, PROFILE_DIR)
    output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output))
    print(
        f"[generate_ams_c35_mixed_signal] top={TOP_CELL} "
        f"devices={len(mos)} R=2 PiP=1 nets={len(net_order)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
