#!/usr/bin/env python3
"""scmos_authoritative_lvs.py — data-driven authoritative LVS extractor.

Device definitions come from the profile's devices.yaml (mos4/resistor/
capacitor/diode/npn tables); connectivity and geometry machinery are shared
with the reference extractor (common/lvs/scmos_lvs_core.py).  The reference
(divaEXT.rul oracle) and this extractor must produce identical netlists —
scripts/lvs_conformance.py enforces that.

Env: LAYOUT, EXTRACTED, LAYERMAP, FEATURES, PREFIX, TECH, WELL, LAMBDA,
GRID, DEVICES (path to devices.yaml), SHEET_RES, CAP_AREACAP.
Prints {"devices": {type: count}, "nets": n, "warnings": [...]}.
"""

import json
import os
import sys

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scmos_lvs_core import (CONV, MODEL_SUFFIX, DEFAULT_SHEET_RES, DEFAULT_CAP_AREACAP,
                            build_nets, coincident, offset_pt, emit_spice)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drc"))
from scmos_layers import derive

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import yamlish


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

    devices = []
    counts = {}

    def add(kind, line):
        devices.append(line)
        counts[kind] = counts.get(kind, 0) + 1

    table = yamlish.load(open(DEVICES).read())
    kinds = table.get("devices", {})

    # ---- MOSFETs (Diva extractMOS: W from S/D-butting edges, L = area/W)
    for entry in kinds.get("mos4", []):
        dev = entry["name"]
        channel = D.get(entry["channel"])
        diff = D.get(entry["diff"])
        if channel is None or diff is None or channel.is_empty() or diff.is_empty():
            continue
        shared = coincident(channel, diff)
        if shared.is_empty():
            continue
        devno = 0
        for cpoly in channel.merge().each():
            cpoly = pya.Polygon(cpoly)
            sedges = pya.Edges()
            for e in cpoly.each_edge():
                if not (pya.Edges(e) & shared).is_empty():
                    sedges += e
            W = sedges.length() * DBU / 2.0
            if W <= 0:
                continue
            devno += 1
            area = cpoly.area() * DBU * DBU
            L = area / W
            center = cpoly.bbox().center()
            g = comp_at(center, "poly")
            if g is None:
                warnings.append(f"{dev}: gate net not found at {center}")
                continue
            if entry.get("bulk_net") == "substrate":
                b_net = N.substrate_net()
            else:
                b = comp_at(center, entry["bulk_net"])
                b_net = net_of(b) if b is not None else None
            sides = []
            for e in sedges.each():
                pt = offset_pt(e, cpoly)
                ci = comp_at(pt, entry["diff"])
                if ci is None:
                    warnings.append(f"{dev}: side net not found at {pt}")
                    continue
                sides.append(ci)
            if len(sides) != 2:
                warnings.append(f"{dev}: expected 2 diff sides, got {len(sides)}")
                continue
            s0, s1 = sides
            island = comps[s0][1]
            ad = island.area() * DBU * DBU
            pd = island.perimeter() * DBU
            model = PREFIX + MODEL_SUFFIX[entry["model_suffix"]]
            add(dev, f"m{devno} {net_of(s0)} {net_of(g)} {net_of(s1)} "
                    f"{b_net if b_net else 'SUBS'} {model} "
                    f"w={W:.6g} l={L:.6g} ad={ad:.6g} as={ad:.6g} "
                    f"pd={pd:.6g} ps={pd:.6g}")

    # ---- resistors (Diva: W = butting-edge length/2, L = (P-Wtot)/2)
    for entry in kinds.get("resistor", []):
        key = entry["name"]
        region = D.get(entry["body"])
        conn = D.get(entry["conn"])
        if region is None or conn is None or region.is_empty():
            continue
        rno = 0
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
            Rs = SHEET_RES.get(entry["sheet"], 0.0)
            R = Rs * L / W if W > 0 else 0.0
            ends = []
            for e in bedges.each():
                pt = offset_pt(e, bpoly)
                ci = comp_at(pt, entry["conn"])
                if ci is not None:
                    ends.append(ci)
            if len(ends) != 2:
                warnings.append(f"{key}: expected 2 ends, got {len(ends)}")
                continue
            add("res", f"r{rno} {net_of(ends[0])} {net_of(ends[1])} res "
                       f"r={R:.6g} w={W:.6g} l={L:.6g}")

    # ---- capacitors (C = area * areaCap[aF/um2] * 1e-18 F)
    for entry in kinds.get("capacitor", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
        cno = 0
        areaCap = CAP_AREACAP.get(entry["area_cap"], 0.0)
        for cpoly in region.merge().each():
            cpoly = pya.Polygon(cpoly)
            cno += 1
            C = cpoly.area() * DBU * DBU * areaCap * 1e-18
            center = cpoly.bbox().center()
            pt = comp_at(center, entry["top"])
            pb = comp_at(center, entry["bottom"])
            if pt is None or pb is None:
                warnings.append(f"{key}: terminal net not found at {center}")
                continue
            add("cap", f"c{cno} {net_of(pt)} {net_of(pb)} cap c={C:.6g}")

    # ---- diodes (area, pj)
    for entry in kinds.get("diode", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
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
            model = PREFIX + MODEL_SUFFIX[entry["model_suffix"]]
            add("diode", f"d{dno} {net_of_root(uf.find(plus)) if plus == SUB else net_of(plus)} "
                         f"{net_of(minus)} {model} area={a:.6g} pj={pj:.6g}")

    # ---- NPN (hardcoded Generic_NPN model, as in divaEXT)
    for entry in kinds.get("npn", []):
        key = entry["name"]
        region = D.get(entry["region"])
        if region is None or region.is_empty():
            continue
        qno = 0
        for qpoly in region.merge().each():
            qpoly = pya.Polygon(qpoly)
            qno += 1
            c = comp_at(qpoly.bbox().center(), entry["collector"])
            e = comp_at(qpoly.bbox().center(), entry["emitter"])
            b = comp_at(qpoly.bbox().center(), entry["base"])
            if c is None or e is None or b is None:
                warnings.append(f"{key}: terminal net not found")
                continue
            add("npn", f"q{qno} {net_of(c)} {net_of(b)} {net_of(e)} Generic_NPN")

    emit_spice(devices, counts, N.net_names, TECH, PREFIX,
               "scmos_authoritative_lvs.py (devices.yaml)", N.net_count)
    summary = {"devices": counts, "nets": N.net_count, "warnings": warnings,
               "ports": sorted(set(N.net_names.values())), "port_nets": N.port_nets()}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(run())
