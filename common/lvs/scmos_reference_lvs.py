#!/usr/bin/env python3
"""scmos_reference_lvs.py -- reference LVS extraction (divaEXT.rul port).

Extracts devices from SCMOS layout into a flat SPICE netlist using the same
device names and parameters as the NCSU CDK Diva deck (divaEXT.rul):

  nmos4/pmos4 (d g s b; w/l/ad/as/pd/ps; model = <PREFIX><suffix>)
  hvn/hvp, n/pElecChannelTran (poly2-gate; not extracted for TSMC035/AMI_C5N)
  res    (r, w, l; sheet resistance from SHEET_RES, placeholders pending
          MOSIS parametric reports)
  cap    (c; area capacitance from CAP_AREACAP, placeholders pending)
  diode  (area, pj; models <PREFIX>NP/PN/NwP)
  npn    (c b e; model Generic_NPN)

Connectivity is shared with the authoritative extractor
(common/lvs/scmos_lvs_core.py).  Text labels on GDS layer 64/0 name the
nets; siliconcraft convenience layers res_id=65 cap_id=66 dio_id=67
nolpe=68.

Run:
  LAYOUT=<in.gds> EXTRACTED=<out.spice> LAYERMAP=<json> FEATURES=<json> \
  PREFIX=ami06 TECH=AMI_C5N WELL=N \
    klayout -b -r common/lvs/scmos_reference_lvs.py
Prints {"devices": {type: count}, "nets": n, "warnings": [...]}.
"""

import json
import os
import sys

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scmos_lvs_core import (CONV, MODEL_SUFFIX, DEFAULT_SHEET_RES, DEFAULT_CAP_AREACAP,
                            build_nets, coincident, offset_pt, poly_contains, emit_spice)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drc"))
from scmos_layers import derive


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
    comp_at_smallest = N.comp_at_smallest
    net_of = N.net_of
    net_of_root = N.net_of_root
    uf, SUB, comps = N.uf, N.SUB, N.comps

    # ------------------------------------------------------------ devices
    devices = []  # spice lines
    counts = {}

    def add(kind, line):
        devices.append(line)
        counts[kind] = counts.get(kind, 0) + 1

    # ---- MOSFETs (Diva extractMOS: W from S/D-butting edges, L = area/W)
    for dev, ch_key, df_key, suffix, is_nwell_bulk in (
            ("nmos4", "nChannel", "nDiff", "nmos", False),
            ("pmos4", "pChannel", "pDiff", "pmos", True)):
        channel = D.get(ch_key)
        diff = D.get(df_key)
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
            W = sedges.length() * DBU / 2.0  # one S/D edge; sedges has both
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
            if is_nwell_bulk:
                b = comp_at(center, "nBulk")
                b_net = net_of(b) if b is not None else None
            else:
                b_net = N.substrate_net()
            sides = []
            for e in sedges.each():
                pt = offset_pt(e, cpoly)
                ci = comp_at(pt, df_key)
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
            model = PREFIX + MODEL_SUFFIX[suffix]
            add(dev, f"m{devno} {net_of(s0)} {net_of(g)} {net_of(s1)} "
                    f"{b_net if b_net else 'SUBS'} {model} "
                    f"w={W:.6g} l={L:.6g} ad={ad:.6g} as={ad:.6g} "
                    f"pd={pd:.6g} ps={pd:.6g}")

    # ---- resistors (Diva: W = butting-edge length/2, L = (P-Wtot)/2,
    #      R = Rs*L/W - corner correction (corners not ported, ~0))
    for key, conn_key, rs_key in (("polyRes", "poly", "poly"),
                                  ("polySRes", "poly", "sblock"),
                                  ("elecRes", "elec", "elec"),
                                  ("elecHighres", "elec", "highres"),
                                  ("nwellRes", "nBulk", "nwell")):
        region = D.get(key)
        conn = D.get(conn_key)
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
            Rs = SHEET_RES.get(rs_key, 0.0)
            R = Rs * L / W if W > 0 else 0.0
            ends = []
            for e in bedges.each():
                pt = offset_pt(e, bpoly)
                ci = comp_at(pt, conn_key)
                if ci is not None:
                    ends.append(ci)
            if len(ends) != 2:
                warnings.append(f"{key}: expected 2 ends, got {len(ends)}")
                continue
            add("res", f"r{rno} {net_of(ends[0])} {net_of(ends[1])} res "
                       f"r={R:.6g} w={W:.6g} l={L:.6g}")

    # ---- capacitors (C = area * areaCap[aF/um2] * 1e-18 F)
    for key, top_key, bot_key, cap_key in (("CapacitorElec", "elec", "poly", "elec_poly"),
                                           ("polycapCap", "poly", "polycap", "poly_polycap"),
                                           ("metalcapCap", "metalcap", "metalcap_bottom", "metalcap"),
                                           ("lcCap", "poly", "lcDiff", "poly_cwell")):
        region = D.get(key)
        if region is None or region.is_empty():
            continue
        cno = 0
        areaCap = CAP_AREACAP.get(cap_key, 0.0)
        for cpoly in region.merge().each():
            cpoly = pya.Polygon(cpoly)
            cno += 1
            C = cpoly.area() * DBU * DBU * areaCap * 1e-18
            center = cpoly.bbox().center()
            pt = comp_at(center, top_key)
            pb = comp_at(center, bot_key)
            if pt is None or pb is None:
                warnings.append(f"{key}: terminal net not found at {center}")
                continue
            add("cap", f"c{cno} {net_of(pt)} {net_of(pb)} cap c={C:.6g}")

    # ---- diodes (area, pj; PLUS/MINUS per divaEXT)
    for key, plus_key, minus_key, suffix in (("NPdiode", None, "nDiff", "npdiode"),
                                             ("PNdiode", "pDiff", "nBulk", "pndiode"),
                                             ("NwPdiode", None, "nBulk", "nwpdiode")):
        region = D.get(key)
        if region is None or region.is_empty():
            continue
        dno = 0
        for dpoly in region.merge().each():
            dpoly = pya.Polygon(dpoly)
            dno += 1
            center = dpoly.bbox().center()
            minus = comp_at(center, minus_key)
            if plus_key is not None:
                plus = comp_at(center, plus_key)
            else:
                plus = SUB if uf.find(SUB) != SUB else None
            if minus is None or plus is None:
                warnings.append(f"{key}: terminal net not found at {center}")
                continue
            a = dpoly.area() * DBU * DBU
            pj = dpoly.perimeter() * DBU
            model = PREFIX + MODEL_SUFFIX[suffix]
            add("diode", f"d{dno} {net_of_root(uf.find(plus)) if plus == SUB else net_of(plus)} "
                         f"{net_of(minus)} {model} area={a:.6g} pj={pj:.6g}")

    # ---- NPN (hardcoded Generic_NPN model, as in divaEXT)
    if "npnTran" in D and not D["npnTran"].is_empty():
        qno = 0
        for qpoly in D["npnTran"].merge().each():
            qpoly = pya.Polygon(qpoly)
            qno += 1
            c = comp_at(qpoly.bbox().center(), "npnCollector")
            e = comp_at(qpoly.bbox().center(), "npnEmitter")
            b = comp_at(qpoly.bbox().center(), "npnBaseTap")
            if c is None or e is None or b is None:
                warnings.append("npn: terminal net not found")
                continue
            add("npn", f"q{qno} {net_of(c)} {net_of(b)} {net_of(e)} Generic_NPN")

    emit_spice(devices, counts, N.net_names, TECH, PREFIX,
               "scmos_reference_lvs.py (divaEXT.rul port)", N.net_count)
    summary = {"devices": counts, "nets": N.net_count, "warnings": warnings,
               "ports": sorted(set(N.net_names.values())), "port_nets": N.port_nets()}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(run())
