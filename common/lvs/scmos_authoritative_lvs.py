#!/usr/bin/env python3
"""scmos_authoritative_lvs.py — data-driven authoritative LVS extractor.

Device definitions come from the profile's devices.yaml (mos4/resistor/
capacitor/diode/npn tables); connectivity and geometry machinery are shared
with the reference extractor (common/lvs/scmos_lvs_core.py).  The reference
(divaEXT.rul oracle) and this extractor must produce identical netlists —
scripts/lvs_conformance.py enforces that.

Env: LAYOUT, EXTRACTED, LAYERMAP, FEATURES, PREFIX, TECH, WELL, LAMBDA,
GRID, DEVICES (path to devices.yaml), PROCESS_VARIANT (optional profile module
variant), SHEET_RES, CAP_AREACAP.
Prints {"devices": {type: count}, "nets": n, "warnings": [...]}.
"""

import json
import math
import os
import sys

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scmos_lvs_core import (CONV, MODEL_SUFFIX, DEFAULT_SHEET_RES, DEFAULT_CAP_AREACAP,
                            build_nets, coincident, offset_pt, emit_spice)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drc"))
from scmos_layers import derive


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from common.process_ir import ProcessIRError, load_process


def run():
    layout = pya.Layout()
    try:
        layout.read(os.environ["LAYOUT"])
    except Exception as e:
        print(json.dumps({"error": f"cannot read LAYOUT: {e}"}))
        sys.exit(1)
    top = layout.top_cell()
    DBU = layout.dbu
    LAMBDA = float(os.environ.get("LAMBDA", "0.3"))
    TECH = os.environ.get("TECH", "")
    WELL = os.environ.get("WELL", "N")
    PREFIX = os.environ.get("PREFIX", "ami06")
    SHEET_RES = dict(DEFAULT_SHEET_RES)
    SHEET_RES.update(json.loads(os.environ.get("SHEET_RES", "{}")))
    CAP_AREACAP = dict(DEFAULT_CAP_AREACAP)
    CAP_AREACAP.update(json.loads(os.environ.get("CAP_AREACAP", "{}")))
    LAYER_MAP = json.loads(os.environ.get("LAYERMAP", "{}"))
    for k, v in CONV.items():
        LAYER_MAP.setdefault(k, [v, 0])
    FEATURES = json.loads(os.environ.get("FEATURES", "{}"))
    DEVICES = os.environ.get("DEVICES", "")
    if not DEVICES or not os.path.exists(DEVICES):
        print(json.dumps({"error": f"DEVICES not found: {DEVICES}"}))
        sys.exit(1)
    warnings = []

    def F(name):
        return FEATURES.get(name, False)

    def L(name):
        info = LAYER_MAP.get(name)
        if not info:
            return pya.Region()
        idx = layout.find_layer(int(info[0]), int(info[1]))
        if idx is None or idx < 0:
            return pya.Region()
        return pya.Region(top.begin_shapes_rec(idx))

    UNIVERSE = pya.Region(top.bbox())
    D = derive(L, F, WELL, TECH, LAMBDA, DBU, UNIVERSE)
    N = build_nets(D, L, F, WELL, layout, top, DBU)

    comp_at = N.comp_at
    net_of = N.net_of
    net_of_root = N.net_of_root
    uf, SUB, comps = N.uf, N.SUB, N.comps
    native_rc = None
    native_config = os.environ.get("C35_NATIVE_RC")
    if native_config:
        from common.pex.ams_c35_native import extract_native_rc
        from common.pex.manhattan import ManhattanGeometryError, spice_identifier

        config = json.loads(native_config)
        SHEET_RES.update(config.get("sheet_resistance_ohm_sq", {}))
        CAP_AREACAP.update(config.get("area_capacitance_ff_per_um2", {}))
        try:
            native_rc = extract_native_rc(D, N, DBU, config)
        except (ManhattanGeometryError, KeyError, TypeError, ValueError) as exc:
            print(json.dumps({"error": f"native C35 RC extraction failed closed: {exc}"}))
            sys.exit(1)

    def node_of(component, point):
        if native_rc is None:
            return net_of(component)
        return native_rc.node_for(component, point)

    def substrate_net():
        name = N.substrate_net()
        return (
            spice_identifier(name)
            if native_rc is not None and name is not None
            else name
        )

    devices = []
    counts = {}

    def add(kind, line):
        devices.append(line)
        counts[kind] = counts.get(kind, 0) + 1
    width_correction = (config.get("resistor_width_correction_um", {})
                        if native_rc is not None else {})

    try:
        process = load_process(
            os.path.dirname(os.path.abspath(DEVICES)),
            variant=os.environ.get("PROCESS_VARIANT") or None,
        )
    except ProcessIRError as exc:
        print(json.dumps({"error": f"invalid process device configuration: {exc}"}))
        sys.exit(1)
    kinds = process.devices_doc.get("devices", {})

    # ---- MOSFETs (Diva extractMOS: W from S/D-butting edges, L = area/W)
    # SPICE element names are global across MOS model classes.
    mos_instance_number = 0

    def extract_mos(entry, kind):
        nonlocal mos_instance_number
        dev = entry["name"]
        channel = D.get(entry["channel"])
        if kind == "ldmos":
            source_diff = D.get(entry["source_diff"])
            drain_diff = D.get(entry["drain_diff"])
        else:
            source_diff = D.get(entry["diff"])
            drain_diff = source_diff
        if (
            channel is None
            or source_diff is None
            or drain_diff is None
            or channel.is_empty()
            or source_diff.is_empty()
            or drain_diff.is_empty()
        ):
            return
        source_shared = coincident(channel, source_diff)
        drain_shared = coincident(channel, drain_diff)
        shared = source_shared | drain_shared
        if shared.is_empty():
            return
        for raw_channel in channel.merge().each():
            cpoly = pya.Polygon(raw_channel)
            edge_roles = []
            for edge in cpoly.each_edge():
                edge_region = pya.Edges(edge)
                if not (edge_region & shared).is_empty():
                    if kind == "ldmos" and not (edge_region & drain_shared).is_empty():
                        role = "drain"
                    else:
                        role = "source"
                    edge_roles.append((edge, role))
            if not edge_roles:
                continue
            W = sum(edge.length() for edge, _ in edge_roles) * DBU / 2.0
            if W <= 0:
                continue
            mos_instance_number += 1
            area = cpoly.area() * DBU * DBU
            length = area / W
            center = cpoly.bbox().center()
            g = comp_at(center, "poly")
            if g is None:
                warnings.append(f"{dev}: gate net not found at {center}")
                continue
            if entry.get("bulk_net") == "substrate":
                b_net = substrate_net()
            elif entry.get("bulk_net") == "auto_hv":
                b = comp_at(center, "isoPwell")
                b_net = node_of(b, center) if b is not None else substrate_net()
            else:
                b = comp_at(center, entry["bulk_net"])
                b_net = node_of(b, center) if b is not None else None
            sides = []
            for edge, role in edge_roles:
                pt = offset_pt(edge, cpoly)
                diff_layer = (
                    entry["drain_diff"] if role == "drain" else entry.get("source_diff", entry["diff"])
                )
                ci = comp_at(pt, diff_layer)
                if ci is None:
                    # Derived HV/DRIFT regions are recognition masks, not
                    # independent conductors in the SCMOS net graph.
                    physical_layer = {
                        "nHVDiff": "nDiff",
                        "pHVDiff": "pDiff",
                        "nDmosDiff": "nDiff",
                        "pDmosDiff": "pDiff",
                    }.get(diff_layer)
                    if physical_layer:
                        ci = comp_at(pt, physical_layer)
                if ci is None:
                    warnings.append(f"{dev}: {role} net not found at {pt}")
                    continue
                sides.append((ci, role, pt))
            if len(sides) != 2:
                warnings.append(f"{dev}: expected 2 diff sides, got {len(sides)}")
                continue
            if kind == "mos4":
                # Preserve the reference extractor's terminal ordering for
                # interchangeable SCMOS source/drain terminals.
                drain, source = sides[0][0], sides[1][0]
                drain_pt, source_pt = sides[0][2], sides[1][2]
            else:
                source, _, source_pt = next((item for item in sides if item[1] == "source"), sides[0])
                drain, _, drain_pt = next((item for item in sides if item[1] == "drain"), sides[-1])
            source_poly = comps[source][1]
            drain_poly = comps[drain][1]
            ad = drain_poly.area() * DBU * DBU
            a_s = source_poly.area() * DBU * DBU
            pd = drain_poly.perimeter() * DBU
            ps = source_poly.perimeter() * DBU
            model = entry.get("model_name") or PREFIX + MODEL_SUFFIX[entry["model_suffix"]]
            model_record = process.model_parameters.get(model)
            if native_rc is not None and not (
                isinstance(model_record, dict)
                and model_record.get("simulator") == "ngspice"
                and model_record.get("representation") == "primitive"
            ):
                raise RuntimeError(
                    f"{dev}: native PEX has no verified primitive MOS card for {model}"
                )
            add(
                dev,
                f"m{mos_instance_number} {node_of(drain, drain_pt)} {node_of(g, center)} "
                f"{node_of(source, source_pt)} "
                f"{b_net if b_net else 'SUBS'} {model} "
                f"w={W:.6g} l={length:.6g} ad={ad:.6g} as={a_s:.6g} "
                f"pd={pd:.6g} ps={ps:.6g}",
            )

    for entry in kinds.get("mos4", []):
        extract_mos(entry, "mos4")
    for entry in kinds.get("ldmos", []):
        extract_mos(entry, "ldmos")
    # ---- resistors
    def box_distance_um(a, b):
        dx = max(a.left - b.right, b.left - a.right, 0)
        dy = max(a.bottom - b.top, b.bottom - a.top, 0)
        return math.hypot(dx, dy) * DBU

    for entry in kinds.get("jfet", []):
        region = D.get(entry.get("region", entry.get("body")))
        if region is None or region.is_empty():
            continue
        message = (
            f"{entry['name']}: C35 JFET classification is known, but its "
            "compact-model card and layout terminal contract are unavailable"
        )
        if native_rc is not None:
            raise RuntimeError(message)
        warnings.append(message)

    for entry in kinds.get("resistor", []):
        key = entry["name"]
        region = D.get(entry.get("body", entry.get("region")))
        if region is None or region.is_empty():
            continue
        Rs = SHEET_RES.get(entry["sheet"])
        if not isinstance(Rs, (int, float)):
            message = f"{key}: sheet resistance unavailable; numeric resistor not emitted"
            if native_rc is not None:
                raise RuntimeError(message)
            warnings.append(message)
            continue

        rno = 0
        if entry.get("terminal_marker"):
            markers = D.get(entry["terminal_marker"])
            terminal_layer = entry["terminal_layer"]
            if markers is None or markers.is_empty():
                message = f"{key}: terminal marker {entry['terminal_marker']} missing"
                if native_rc is not None:
                    raise RuntimeError(message)
                warnings.append(message)
                continue
            for raw_body in region.merge().each():
                body = pya.Polygon(raw_body)
                body_region = pya.Region(body)
                body_box = body.bbox()
                ends = []
                for raw_marker in markers.merge().each():
                    marker = pya.Polygon(raw_marker)
                    marker_box = marker.bbox()
                    if entry["terminal_marker"] == "restdm":
                        adjacent = not coincident(
                            body_region, pya.Region(marker)
                        ).is_empty()
                    else:
                        adjacent = (
                            box_distance_um(body_box, marker_box)
                            <= float(entry.get("terminal_gap_um", 0.0)) + 1e-9
                        )
                    if not adjacent:
                        continue
                    point = marker_box.center()
                    terminal = comp_at(point, terminal_layer)
                    if terminal is not None and all(ci != terminal for ci, _ in ends):
                        ends.append((terminal, point))
                if len(ends) != 2:
                    message = f"{key}: expected 2 marked terminals, got {len(ends)}"
                    if native_rc is not None:
                        raise RuntimeError(message)
                    warnings.append(message)
                    continue
                width = min(body_box.width(), body_box.height()) * DBU
                length = max(body_box.width(), body_box.height()) * DBU
                correction = float(width_correction.get(entry["sheet"], 0.0))
                effective_width = width - correction
                if effective_width <= 0:
                    raise RuntimeError(
                        f"{key}: effective width is nonpositive "
                        f"(drawn {width:g}um, correction {correction:g}um)"
                    )
                resistance = Rs * length / effective_width
                if native_rc is None:
                    add(
                        "res",
                        f"r{rno} {net_of(ends[0][0])} {net_of(ends[1][0])} res "
                        f"r={resistance:.6g} w={width:.6g} l={length:.6g}",
                    )
                elif key in ("rp2", "rph"):
                    model = "RPOLY2_CORE" if key == "rp2" else "RPOLYH"
                    add(
                        "res",
                        f"Xres_{key}_{rno} {node_of(ends[0][0], ends[0][1])} "
                        f"{node_of(ends[1][0], ends[1][1])} {model} "
                        f"W={width * 1e-6:.9g} L={length * 1e-6:.9g}",
                    )
                else:
                    add(
                        "res",
                        f"Rdev_{key}_{rno} {node_of(ends[0][0], ends[0][1])} "
                        f"{node_of(ends[1][0], ends[1][1])} {resistance:.9g}",
                    )
                rno += 1
            continue

        conn = D.get(entry["conn"])
        if conn is None:
            continue
        shared = coincident(region, conn)
        for bpoly in region.merge().each():
            bpoly = pya.Polygon(bpoly)
            bedges = pya.Edges()
            for e in bpoly.each_edge():
                if not (pya.Edges(e) & shared).is_empty():
                    bedges += e
            Wtot = bedges.length() * DBU
            if Wtot <= 0:
                continue
            rno += 1
            W = Wtot / 2.0
            perim = bpoly.perimeter() * DBU
            L = (perim - Wtot) / 2.0
            ends = []
            for e in bedges.each():
                pt = offset_pt(e, bpoly)
                ci = comp_at(pt, entry["conn"])
                if ci is not None:
                    ends.append((ci, pt))
            if len(ends) != 2:
                warnings.append(f"{key}: expected 2 ends, got {len(ends)}")
                continue
            R = Rs * L / W
            add(
                "res",
                f"Rdev_{key}_{rno} {node_of(ends[0][0], ends[0][1])} "
                f"{node_of(ends[1][0], ends[1][1])} {R:.9g}"
                if native_rc is not None
                else f"r{rno} {net_of(ends[0][0])} {net_of(ends[1][0])} res "
                f"r={R:.6g} w={W:.6g} l={L:.6g}",
            )

    # ---- capacitors (C = area * areaCap[aF/um2] * 1e-18 F)
    for entry in kinds.get("capacitor", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
        cno = 0
        areaCap = CAP_AREACAP.get(entry.get("area_cap"))
        if not isinstance(areaCap, (int, float)):
            message = f"{key}: area capacitance unavailable; numeric capacitor not emitted"
            if native_rc is not None:
                raise RuntimeError(message)
            warnings.append(message)
            continue
        for cpoly in region.merge().each():
            cpoly = pya.Polygon(cpoly)
            cno += 1
            center = cpoly.bbox().center()
            pt = comp_at(center, entry["top"])
            pb = comp_at(center, entry["bottom"])
            if pt is None or pb is None:
                warnings.append(f"{key}: terminal net not found at {center}")
                continue
            if native_rc is None:
                C = cpoly.area() * DBU * DBU * areaCap * 1e-18
                add("cap", f"c{cno} {net_of(pt)} {net_of(pb)} cap c={C:.6g}")
            else:
                perimeterCap = float(config.get("perimeter_capacitance_ff_per_um", {}).get(
                    entry.get("area_cap"), 0.0
                ))
                capacitance_ff = (
                    cpoly.area() * DBU * DBU * areaCap
                    + cpoly.perimeter() * DBU * perimeterCap
                )
                tempco1 = config.get("capacitance_tempco1_per_c", {}).get(
                    entry.get("area_cap")
                )
                tempco = (
                    f" TC1={float(tempco1):.9g}"
                    if isinstance(tempco1, (int, float))
                    else ""
                )
                add(
                    "cap",
                    f"Cdev_{key}_{cno} {node_of(pt, center)} "
                    f"{node_of(pb, center)} {capacitance_ff * 1e-15:.9g}{tempco}",
                )

    # ---- diodes (area, pj)
    for entry in kinds.get("diode", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
        if native_rc is not None:
            raise RuntimeError(
                f"{key}: C35 diode compact-model parameters are unavailable; "
                "native PEX refuses to emit an unmodeled junction"
            )
        dno = 0
        for dpoly in region.merge().each():
            dpoly = pya.Polygon(dpoly)
            dno += 1
            center = dpoly.bbox().center()
            minus = comp_at(center, entry["minus"])
            if entry.get("plus") == "substrate":
                plus = SUB if uf.find(SUB) != SUB else None
            else:
                plus = comp_at(center, entry["plus"])
            if minus is None or plus is None:
                warnings.append(f"{key}: terminal net not found at {center}")
                continue
            a = dpoly.area() * DBU * DBU
            pj = dpoly.perimeter() * DBU
            model = entry.get("model_name") or PREFIX + MODEL_SUFFIX[entry["model_suffix"]]
            add("diode", f"d{dno} {net_of_root(uf.find(plus)) if plus == SUB else net_of(plus)} "
                         f"{net_of(minus)} {model} area={a:.6g} pj={pj:.6g}")

    # ---- NPN (hardcoded Generic_NPN model, as in divaEXT)
    def npn_terminal(region, layer_name):
        terminal = D.get(layer_name)
        if terminal is None or terminal.is_empty():
            return None
        for polygon in (terminal & region).merge().each():
            component = comp_at(pya.Polygon(polygon).bbox().center(), layer_name)
            if component is not None:
                return component
        return None

    for entry in kinds.get("npn", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
        if native_rc is not None:
            raise RuntimeError(f"{key}: no verified C35 NPN model is configured")
        c = npn_terminal(region, entry["collector"])
        e = npn_terminal(region, entry["emitter"])
        b = npn_terminal(region, entry["base"])
        if c is None or e is None or b is None:
            warnings.append(f"{key}: terminal net not found")
            continue
        add("npn", f"q1 {net_of(c)} {net_of(b)} {net_of(e)} Generic_NPN")
    if native_rc is not None:
        for line in native_rc.elements():
            add("pex", line)

    emit_spice(devices, counts, N.net_names, TECH, PREFIX,
               "scmos_authoritative_lvs.py (devices.yaml)", N.net_count)
    summary = {"devices": counts, "nets": N.net_count, "warnings": warnings,
               "ports": sorted(set(N.net_names.values())), "port_nets": N.port_nets()}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(run())
