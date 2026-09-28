#!/usr/bin/env python3
"""
scmos_reference.py -- mechanical reference port of the NCSU CDK Diva SCMOS DRC deck.

This is the *oracle* deck: a 1:1 translation of techfile/divaDRC.rul +
techfile/divaLayerDef.il (NCSU CDK 1.6.0) into KLayout Python (pya).  It exists
to reproduce Cadence/Diva behavior so that the authoritative, data-driven deck
(generated from pdk.yaml `rules`) can be validated against it.  Rule message
strings keep the original Diva rule IDs (e.g. "(SCMOS_SUBM Rule 3.2)").

Approximations vs. Diva are marked "~" in comments; every one is a candidate
for a documented conformance waiver.  This deck is NOT the shipped DRC -- that
is the authoritative deck.

Run (pya inside `klayout -b -r`):
  LAYOUT=<input.gds> MARKERS=<out_markers.gds> PROFILE=<profile>/layers.yaml \
  LAMBDA=0.3 GRID=0.15 TECH=AMI_C5N WELL=N \
    klayout -b -r common/drc/scmos_reference.py
Writes a marker GDS (input layout + one layer per rule id:
layer = 1000 + crc32(rule_id) & 0x3FFF) plus a JSON summary on stdout:
  {"rule": {"<rule-id>": <count>}, "markers": <n>}
"""

import json
import os
import sys

import pya

# Shared Diva geom helpers + derived-layer computation (divaLayerDef.il port):
# identical geometry for the DRC reference and the LVS reference.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scmos_layers import (derive, or_, and_, andnot, inside, outside, avoiding,
                          overlap, straddle, butting, holes, sized)

DBU = 0.001  # set from layout in run(); used by local helpers


# ------------------------------------------------------------------- marker helper

class Report:
    """Collects violations per rule id; markers are written as per-rule GDS
    layers in the marker output (layer = 1000 + crc32(rule_id) & 0x3FFF)."""

    def __init__(self):
        self.markers = {}
        self.counts = {}

    def item(self, region, rule_id, message):
        if region is None or region.is_empty():
            return
        n = len(region)
        self.counts[rule_id] = self.counts.get(rule_id, 0) + n
        self.markers.setdefault(rule_id, pya.Region())
        self.markers[rule_id] += region

    def save_derived(self, region, message):
        if region is None or region.is_empty():
            return
        # saveDerived: pure check marker, no rule id
        self.item(region, "saveDerived", message)

    def off_grid(self, region, grid_um, message):
        if region is None or region.is_empty():
            return
        g = max(1, int(round(grid_um / DBU)))  # grid in dbu, integer math
        bad = pya.Region()
        for poly in region.each():
            pp = pya.Polygon(poly)
            for pt in pp.each_point_hull():
                if pt.x % g != 0 or pt.y % g != 0:
                    bad += pya.Region(poly)
                    break
        self.item(bad, "offgrid", message)


# ------------------------------------------------------------------- deck

def run():
    layout = pya.Layout()
    try:
        layout.read(os.environ["LAYOUT"])
    except Exception as e:
        print(json.dumps({"error": f"cannot read LAYOUT: {e}"}))
        sys.exit(1)
    top = layout.top_cell()
    dbu = layout.dbu
    global DBU
    DBU = dbu
    UNIVERSE = pya.Region(top.bbox())  # Diva geomNot operates within the cell bbox
    LAMBDA = float(os.environ.get("LAMBDA", "0.3"))
    GRID = float(os.environ.get("GRID", "0.15"))
    TECH = os.environ.get("TECH", "AMI_C5N")
    WELL = os.environ.get("WELL", "N")
    padType = os.environ.get("PAD", "Perimeter")

    def L(name):
        """Region from input layer by name -> (layer, datatype) from layers.yaml map."""
        info = LAYER_MAP.get(name)
        if info is None:
            return pya.Region()
        ln, dt = info
        idx = layout.find_layer(ln, dt)
        if idx is None or idx < 0:
            return pya.Region()
        return pya.Region(top.begin_shapes_rec(idx))

    # ---- layer map: populated by the runner from the profile layers.yaml
    #      via the env var LAYERMAP=<json>  {"name": [gds, datatype]}
    LAYER_MAP = json.loads(os.environ.get("LAYERMAP", "{}"))

    # feature flags (from profile layers.yaml `features`)
    def F(name):
        return FEATURES.get(name, False)

    FEATURES = json.loads(os.environ.get("FEATURES", "{}"))

    rule_family = os.environ.get("RULE_FAMILY") or FEATURES.get("rule_family", "scmos")
    if rule_family not in ("scmos", "scmos_subm"):
        raise ValueError(f"unsupported SCMOS rule family: {rule_family!r}")
    submicron = rule_family == "scmos_subm"
    stacked_vias = F("stackedVias")

    R = Report()

    # ------------------------------------------------------------ derived layers
    # shared with the LVS reference: scmos_layers.derive() = divaLayerDef.il port
    D = derive(L, F, WELL, TECH, LAMBDA, DBU, UNIVERSE)
    for _k, _v in D.items():
        globals()[_k] = _v

    # ------------------------------------------------------------ edge layers
    def E(r):
        return r.edges()

    nwellEdge, pwellEdge, activeEdge = E(nwell), E(pwell), E(active)
    nselectEdge, pselectEdge = E(nselect), E(pselect)
    polyEdge, metal1Edge = E(poly), E(metal1)
    caEdge, cpEdge = E(ca), E(cp)
    metal2Edge, viaEdge = E(metal2), E(via)
    glassEdge, padEdge = E(glass), E(pad)
    if F("metal3Available"):
        metal3Edge, via2Edge = E(metal3), E(via2)
    if F("metal4Available"):
        metal4Edge, via3Edge = E(metal4), E(via3)
    if F("metal5Available"):
        metal5Edge, via4Edge = E(metal5), E(via4)
    if F("metal6Available"):
        metal6Edge, via5Edge = E(metal6), E(via5)
    if F("elecAvailable"):
        ceEdge, elecEdge = E(ce), E(elec)
        CapacitorElecEdge = E(CapacitorElec)
        TransistorElecEdge = E(TransistorElec)
    nBulkEdge, pBulkEdge = E(nBulk), E(pBulk)
    nOhmicEdge, pOhmicEdge = E(nOhmic), E(pOhmic)
    nNotOhmicEdge, pNotOhmicEdge = E(nNotOhmic), E(pNotOhmic)
    GateEdge, fieldPolyEdge = E(Gate), E(fieldPoly)
    if F("npnAvailable"):
        npnCollectorEdge = E(npnCollector)
        npnCollectorContactEdge = E(npnCollectorContact)
        npnEmitterEdge = E(npnEmitter)
        npnBaseEdge = E(npnBase)
        npnBaseTapEdge = E(npnBaseTap)
        npnBaseContactEdge = E(npnBaseContact)
        npnEmitterContactEdge = E(npnEmitterContact)
    if F("ccdAvailable"):
        ccdDiffEdge = E(ccdDiff)
        ccdContactEdge = E(ccdContact)
    if F("cwellAvailable"):
        cwellEdge = E(cwell)
        lcDiffEdge = E(lcDiff)
        lcCapEdge = E(lcCap)
    if F("polycapAvailable"):
        polycapEdge = E(polycap)
        polycapCapEdge = E(polycapCap)
        cpolycapEdge = E(cpolycap)
    if F("sblockAvailable"):
        sblockEdge = E(sblock)
        polySResEdge = E(polySRes)
    if F("highresAvailable"):
        highresEdge = E(highres)
        elecHighresEdge = E(elecHighres)
    if F("memsAvailable"):
        pstopEdge = E(pstop)
        openEdge = E(open_)
    if F("metalcapAvailable"):
        metalcapCapEdge = E(metalcapCap)
        metalcapBottomEdge = E(metalcapBottom)
        if F("metal6Available"):
            via5metalcapEdge = E(via5metalcap)
        elif F("metal5Available"):
            via4metalcapEdge = E(via4metalcap)
    if F("hvAvailable"):
        tactiveEdge = E(tactive)

    # ------------------------------------------------------------ off-grid
    _og = [(nwell, "nwell"), (pwell, "pwell"), (active, "active"),
           (nselect, "nselect"), (pselect, "pselect"), (poly, "poly"),
           (metal1, "metal1"), (ca, "ca"), (cp, "cp"), (metal2, "metal2"),
           (via, "via")]
    if F("metal3Available"):
        _og += [(metal3, "metal3"), (via2, "via2")]
    if F("elecAvailable"):
        _og += [(elec, "elec"), (ce, "ce")]
    if F("highresAvailable"):
        _og += [(highres, "highres")]
    if F("hvAvailable"):
        _og += [(tactive, "tactive")]
    for _lyr, _nm in _og:
        R.off_grid(_lyr, GRID, "(SCMOS Inst) Edge not on grid")

    # ------------------------------------------------------------ checks
    # width / space / enclosure primitives.  KLayout >= 0.29 check methods
    # take distances in database units, use positional arguments and return
    # EdgePairs; Diva used edge-layer semantics with sep/notch split and
    # apposition filters.  Approximations vs Diva are marked ~ and are
    # candidates for conformance waivers:
    #   ~ sep+notch collapsed (KLayout space_check includes notches)
    #   ~ apposition filter not applied
    #   ~ markers drawn as edge-pair boxes
    def _dbu(d_um):
        return max(1, int(round(d_um / DBU)))

    def _to_region(ep):
        # edge bboxes of axis-aligned edges are degenerate (zero width);
        # enlarge by 1 dbu so Region keeps them as marker slivers
        d = max(1, int(round(0.001 / DBU)))
        out = pya.Region()
        for epair in ep.each():
            b = epair.first.bbox()
            out += pya.Region(b.enlarged(d))
            b = epair.second.bbox()
            out += pya.Region(b.enlarged(d))
        return out

    def wcheck(region, min_um, msg, rule_id):
        if region.is_empty():
            return
        R.item(_to_region(region.width_check(_dbu(min_um))), rule_id, msg)

    def scheck(region, min_um, msg, rule_id, other=None, notch=False, app=False):
        if region.is_empty() or notch:
            return  # ~ notch covered by space_check; Diva separates
        if other is not None:
            if other.is_empty():
                return
            ep = region.space_check(_dbu(min_um), other)
        else:
            ep = region.space_check(_dbu(min_um))
        R.item(_to_region(ep), rule_id, msg)

    def echeck(region, min_um, msg, rule_id, other):
        if region.is_empty() or other.is_empty():
            return
        # 0.30 binding: enclosing_check(other, d)
        R.item(_to_region(region.enclosing_check(other, _dbu(min_um))), rule_id, msg)

    def ocheck(region, min_um, msg, rule_id, other):
        if region.is_empty() or other.is_empty():
            return
        # 0.30 binding: overlap_check(other, d)
        R.item(_to_region(region.overlap_check(other, _dbu(min_um))), rule_id, msg)

    def areacheck(region, max_um2, msg, rule_id):
        if region.is_empty():
            return
        bad = pya.Region()
        for poly in region.each():
            if poly.area() * DBU * DBU > max_um2:
                bad += pya.Region(poly)
        R.item(bad, rule_id, msg)

    # ================= SCMOS 1. WELL =================
    if submicron:
        wcheck(nwell, LAMBDA * 12.0, "(SCMOS_SUBM Rule 1.1) well width: %.2f um" % (LAMBDA * 12.0), "1.1")
        wcheck(pwell, LAMBDA * 12.0, "(SCMOS_SUBM Rule 1.1) well width: %.2f um" % (LAMBDA * 12.0), "1.1")
        scheck(nwell, LAMBDA * 18.0, "(SCMOS_SUBM Rule 1.2) well spacing, different potential: %.2f um" % (LAMBDA * 18.0), "1.2", app=True)
        scheck(pwell, LAMBDA * 18.0, "(SCMOS_SUBM Rule 1.2) well spacing, different potential: %.2f um" % (LAMBDA * 18.0), "1.2", app=True)
    else:
        wcheck(nwell, LAMBDA * 10.0, "(SCMOS Rule 1.1) well width: %.2f um" % (LAMBDA * 10.0), "1.1")
        wcheck(pwell, LAMBDA * 10.0, "(SCMOS Rule 1.1) well width: %.2f um" % (LAMBDA * 10.0), "1.1")
        scheck(nwell, LAMBDA * 9.0, "(SCMOS Rule 1.2) well spacing, different potential: %.2f um" % (LAMBDA * 9.0), "1.2", app=True)
        scheck(pwell, LAMBDA * 9.0, "(SCMOS Rule 1.2) well spacing, different potential: %.2f um" % (LAMBDA * 9.0), "1.2", app=True)
    scheck(nwell, LAMBDA * 6.0, "(SCMOS Rule 1.3) well spacing, same potential: 0 or %.2f um" % (LAMBDA * 6.0), "1.3")
    scheck(pwell, LAMBDA * 6.0, "(SCMOS Rule 1.3) well spacing, same potential: 0 or %.2f um" % (LAMBDA * 6.0), "1.3")
    scheck(nwell, LAMBDA * 6.0, "(SCMOS Rule 1.3) well spacing, same potential: 0 or %.2f um" % (LAMBDA * 6.0), "1.3", notch=True)
    scheck(pwell, LAMBDA * 6.0, "(SCMOS Rule 1.3) well spacing, same potential: 0 or %.2f um" % (LAMBDA * 6.0), "1.3", notch=True)
    R.save_derived(and_(nwell, pwell), "(SCMOS Rule 1 note) n-wells and p-wells may not overlap")

    # ================= SCMOS 2. ACTIVE =================
    if TECH == "AMI_ABN":
        wcheck(active, LAMBDA * 5.0, "(SCMOS Rule 2.1) active width: %.2f um" % (LAMBDA * 5.0), "2.1")
    else:
        wcheck(active, LAMBDA * 3.0, "(SCMOS Rule 2.1) active width: %.2f um" % (LAMBDA * 3.0), "2.1")
    scheck(active, LAMBDA * 3.0, "(SCMOS Rule 2.2) active spacing: %.2f um" % (LAMBDA * 3.0), "2.2")
    scheck(active, LAMBDA * 3.0, "(SCMOS Rule 2.2) active spacing: %.2f um" % (LAMBDA * 3.0), "2.2", notch=True)
    if submicron:
        scheck(nNotOhmic, LAMBDA * 6.0, "(SCMOS_SUBM Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 6.0), "2.3", other=nBulk)
        scheck(pNotOhmic, LAMBDA * 6.0, "(SCMOS_SUBM Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 6.0), "2.3", other=pBulk)
        echeck(pBulk, LAMBDA * 6.0, "(SCMOS_SUBM Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 6.0), "2.3", other=nNotOhmic)
        echeck(nBulk, LAMBDA * 6.0, "(SCMOS_SUBM Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 6.0), "2.3", other=pNotOhmic)
    else:
        scheck(nNotOhmic, LAMBDA * 5.0, "(SCMOS Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 5.0), "2.3", other=nBulk)
        scheck(pNotOhmic, LAMBDA * 5.0, "(SCMOS Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 5.0), "2.3", other=pBulk)
        echeck(pBulk, LAMBDA * 5.0, "(SCMOS Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 5.0), "2.3", other=nNotOhmic)
        echeck(nBulk, LAMBDA * 5.0, "(SCMOS Rule 2.3) source/drain active to well edge: %.2f um" % (LAMBDA * 5.0), "2.3", other=pNotOhmic)
    echeck(nBulk, LAMBDA * 3.0, "(SCMOS Rule 2.4) substrate/well contact active to well edge: %.2f um" % (LAMBDA * 3.0), "2.4", other=nOhmic)
    scheck(nOhmic, LAMBDA * 3.0, "(SCMOS Rule 2.4) substrate/well contact active to well edge: %.2f um" % (LAMBDA * 3.0), "2.4", other=pBulk)
    scheck(pOhmic, LAMBDA * 3.0, "(SCMOS Rule 2.4) substrate/well contact active to well edge: %.2f um" % (LAMBDA * 3.0), "2.4", other=nBulk)
    echeck(pBulk, LAMBDA * 3.0, "(SCMOS Rule 2.4) substrate/well contact active to well edge: %.2f um" % (LAMBDA * 3.0), "2.4", other=pOhmic)
    # 2.5 (0 < sep < 4λ): flag sep < 4λ on opposite pairs
    scheck(nNotOhmic, LAMBDA * 4.0, "(SCMOS Rule 2.5) active of different implant spacing: 0 or %.2f um" % (LAMBDA * 4.0), "2.5", other=pOhmic, app=True)
    scheck(pNotOhmic, LAMBDA * 4.0, "(SCMOS Rule 2.5) active of different implant spacing: 0 or %.2f um" % (LAMBDA * 4.0), "2.5", other=nOhmic, app=True)

    # ================= SCMOS 3. POLY =================
    wcheck(poly, LAMBDA * 2.0, "(SCMOS Rule 3.1) poly width: %.2f um" % (LAMBDA * 2.0), "3.1")
    if submicron:
        scheck(poly, LAMBDA * 3.0, "(SCMOS_SUBM Rule 3.2) poly spacing: %.2f um" % (LAMBDA * 3.0), "3.2")
        scheck(poly, LAMBDA * 3.0, "(SCMOS_SUBM Rule 3.2) poly spacing: %.2f um" % (LAMBDA * 3.0), "3.2", notch=True)
    else:
        scheck(poly, LAMBDA * 2.0, "(SCMOS Rule 3.2) poly spacing: %.2f um" % (LAMBDA * 2.0), "3.2")
        scheck(poly, LAMBDA * 2.0, "(SCMOS Rule 3.2) poly spacing: %.2f um" % (LAMBDA * 2.0), "3.2", notch=True)
    echeck(poly, LAMBDA * 2.0, "(SCMOS Rule 3.3) gate enclosure of active: %.2f um" % (LAMBDA * 2.0), "3.3", other=active)
    echeck(active, LAMBDA * 3.0, "(SCMOS Rule 3.4) active enclosure of gate: %.2f um" % (LAMBDA * 3.0), "3.4", other=poly)
    scheck(poly, LAMBDA * 1.0, "(SCMOS Rule 3.5) field poly to active spacing: %.2f um" % (LAMBDA * 1.0), "3.5", other=active)

    # ================= SCMOS 4. SELECT =================
    scheck(nselect, LAMBDA * 3.0, "(SCMOS Rule 4.1) n select to channel spacing: %.2f um" % (LAMBDA * 3.0), "4.1", other=and_(poly, nNotOhmic), app=True)
    echeck(nselect, LAMBDA * 3.0, "(SCMOS Rule 4.1) n select to channel spacing: %.2f um" % (LAMBDA * 3.0), "4.1", other=and_(poly, nNotOhmic))
    scheck(pselect, LAMBDA * 3.0, "(SCMOS Rule 4.1) p select to channel spacing: %.2f um" % (LAMBDA * 3.0), "4.1", other=and_(poly, pNotOhmic), app=True)
    echeck(pselect, LAMBDA * 3.0, "(SCMOS Rule 4.1) p select to channel spacing: %.2f um" % (LAMBDA * 3.0), "4.1", other=and_(poly, pNotOhmic))
    sel = or_(nselect, pselect)
    scheck(sel, LAMBDA * 2.0, "(SCMOS Rule 4.2) select overlap of active: %.2f um" % (LAMBDA * 2.0), "4.2", other=active)
    echeck(sel, LAMBDA * 2.0, "(SCMOS Rule 4.2) select overlap of active: %.2f um" % (LAMBDA * 2.0), "4.2", other=active)
    scheck(nselect, LAMBDA * 1.0, "(SCMOS Rule 4.3) n select to active contact spacing: %.2f um" % (LAMBDA * 1.0), "4.3", other=ca)
    echeck(nselect, LAMBDA * 1.0, "(SCMOS Rule 4.3) n select to active contact spacing: %.2f um" % (LAMBDA * 1.0), "4.3", other=ca)
    scheck(pselect, LAMBDA * 1.0, "(SCMOS Rule 4.3) p select to active contact spacing: %.2f um" % (LAMBDA * 1.0), "4.3", other=ca)
    echeck(pselect, LAMBDA * 1.0, "(SCMOS Rule 4.3) p select to active contact spacing: %.2f um" % (LAMBDA * 1.0), "4.3", other=ca)
    R.save_derived(butting(and_(ca, nselect), and_(ca, pselect), 1), "(SCMOS Rule 4.3) select overlap of active contact: %.2f um" % (LAMBDA * 1.0))
    wcheck(nselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) n select width: %.2f um" % (LAMBDA * 2.0), "4.4")
    wcheck(pselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) p select width: %.2f um" % (LAMBDA * 2.0), "4.4")
    scheck(nselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) n select spacing: %.2f um" % (LAMBDA * 2.0), "4.4")
    scheck(nselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) n select spacing: %.2f um" % (LAMBDA * 2.0), "4.4", notch=True)
    scheck(pselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) p select spacing: %.2f um" % (LAMBDA * 2.0), "4.4")
    scheck(pselect, LAMBDA * 2.0, "(SCMOS Rule 4.4) p select spacing: %.2f um" % (LAMBDA * 2.0), "4.4", notch=True)
    R.save_derived(and_(nselect, pselect), "(SCMOS Rule 4.4) n select and p select may not overlap")

    # ================= SCMOS 5B. CONTACT TO POLY =================
    wcheck(cp, LAMBDA * 2.0, "(SCMOS Rule 5.1) poly contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "5.1")
    areacheck(cp, (LAMBDA * 2.0) ** 2 + (LAMBDA * 0.1) ** 2, "(SCMOS Rule 5.1) poly contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "5.1")
    echeck(poly, LAMBDA * 1.0, "(SCMOS Rule 5.2.b) poly enclosure of contact: %.2f um" % (LAMBDA * 1.0), "5.2.b", other=cp)
    R.save_derived(andnot(cp, poly), "(SCMOS Rule 5.2.b) poly enclosure of contact: %.2f um" % (LAMBDA * 1.0))
    if F("elecAvailable"):
        R.save_derived(andnot(cc, or_(poly, elec, active)), "Found a contact (cc) shape with no active/poly/poly2 overlap")
    if submicron:
        scheck(cp, LAMBDA * 3.0, "(SCMOS_SUBM Rule 5.3) poly contact spacing: %.2f um" % (LAMBDA * 3.0), "5.3")
        scheck(cp, LAMBDA * 3.0, "(SCMOS_SUBM Rule 5.3) poly contact spacing: %.2f um" % (LAMBDA * 3.0), "5.3", notch=True)
    else:
        scheck(cp, LAMBDA * 2.0, "(SCMOS Rule 5.3) poly contact spacing: %.2f um" % (LAMBDA * 2.0), "5.3")
        scheck(cp, LAMBDA * 2.0, "(SCMOS Rule 5.3) poly contact spacing: %.2f um" % (LAMBDA * 2.0), "5.3", notch=True)
    scheck(cp, LAMBDA * 2.0, "(SCMOS Rule 5.4) poly contact to gate spacing: %.2f um" % (LAMBDA * 2.0), "5.4", other=Gate)
    if submicron:
        if TECH not in ("HP_AMOS14TB", "HP_CMOS26G", "TSMC_CMOS025"):
            scheck(cp, LAMBDA * 5.0, "(SCMOS Rule 5.5.b) poly contact to poly spacing: %.2f um" % (LAMBDA * 5.0), "5.5.b", other=poly)
    else:
        scheck(cp, LAMBDA * 4.0, "(SCMOS Rule 5.5.b) poly contact to poly spacing: %.2f um" % (LAMBDA * 4.0), "5.5.b", other=poly)
    scheck(cp, LAMBDA * 2.0, "(SCMOS Rule 5.6.b) poly contact to active spacing: %.2f um" % (LAMBDA * 2.0), "5.6.b", other=active)
    R.save_derived(and_(cp, active), "(SCMOS Rule 5.6.b) poly contact to active spacing: %.2f um" % (LAMBDA * 2.0))
    # 5.7.b ~: flag the length of violation regions > 7λ (approximation: presence)
    R.save_derived(and_(cp, active), "(SCMOS Rule 5.7.b) poly contact to active spacing, many contacts: %.2f um" % (LAMBDA * 3.0))

    # ================= SCMOS 6B. CONTACT TO ACTIVE =================
    wcheck(ca, LAMBDA * 2.0, "(SCMOS Rule 6.1) active contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "6.1")
    areacheck(ca, (LAMBDA * 2.0) ** 2 + (LAMBDA * 0.1) ** 2, "(SCMOS Rule 6.1) active contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "6.1")
    echeck(active, LAMBDA * 1.0, "(SCMOS Rule 6.2.b) active enclosure of contact: %.2f um" % (LAMBDA * 1.0), "6.2.b", other=ca)
    R.save_derived(andnot(ca, active), "(SCMOS Rule 6.2.b) active enclosure of contact: %.2f um" % (LAMBDA * 1.0))
    if submicron:
        scheck(ca, LAMBDA * 3.0, "(SCMOS_SUBM Rule 6.3) active contact spacing: %.2f um" % (LAMBDA * 3.0), "6.3")
        scheck(ca, LAMBDA * 3.0, "(SCMOS_SUBM Rule 6.3) active contact spacing: %.2f um" % (LAMBDA * 3.0), "6.3", notch=True)
    else:
        scheck(ca, LAMBDA * 2.0, "(SCMOS Rule 6.3) active contact spacing: %.2f um" % (LAMBDA * 2.0), "6.3")
        scheck(ca, LAMBDA * 2.0, "(SCMOS Rule 6.3) active contact spacing: %.2f um" % (LAMBDA * 2.0), "6.3", notch=True)
    scheck(ca, LAMBDA * 2.0, "(SCMOS Rule 6.4) active contact to transistor gate spacing: %.2f um" % (LAMBDA * 2.0), "6.4", other=Gate)
    R.save_derived(and_(ca, Gate), "(SCMOS Rule 6.4) active contact to transistor gate spacing: %.2f um" % (LAMBDA * 2.0))
    scheck(ca, LAMBDA * 5.0, "(SCMOS Rule 6.5.b) active contact to active spacing: %.2f um" % (LAMBDA * 5.0), "6.5.b", other=active)
    scheck(ca, LAMBDA * 2.0, "(SCMOS Rule 6.6.b) active contact to field poly spacing: %.2f um" % (LAMBDA * 2.0), "6.6.b", other=fieldPoly)
    R.save_derived(and_(ca, fieldPoly), "(SCMOS Rule 6.6.b) active contact to field poly spacing: %.2f um" % (LAMBDA * 2.0))
    R.save_derived(and_(ca, fieldPoly), "(SCMOS Rule 6.7.b) active contact to field poly spacing, many contacts: %.2f um" % (LAMBDA * 3.0))
    scheck(ca, LAMBDA * 4.0, "(SCMOS Rule 6.8.b) active contact to poly contact spacing: %.2f um" % (LAMBDA * 4.0), "6.8.b", other=cp)
    R.save_derived(and_(ca, cp), "(SCMOS Rule 6.8.b) active contact to poly contact spacing: %.2f um" % (LAMBDA * 4.0))

    # ================= SCMOS 7. METAL1 =================
    wcheck(metal1, LAMBDA * 3.0, "(SCMOS Rule 7.1) metal1 width: %.2f um" % (LAMBDA * 3.0), "7.1")
    if submicron:
        scheck(metal1, LAMBDA * 3.0, "(SCMOS Rule 7.2) metal1 spacing: %.2f um" % (LAMBDA * 3.0), "7.2")
        scheck(metal1, LAMBDA * 3.0, "(SCMOS Rule 7.2) metal1 spacing: %.2f um" % (LAMBDA * 3.0), "7.2", notch=True)
    else:
        scheck(metal1, LAMBDA * 2.0, "(SCMOS Rule 7.2) metal1 spacing: %.2f um" % (LAMBDA * 2.0), "7.2")
        scheck(metal1, LAMBDA * 2.0, "(SCMOS Rule 7.2) metal1 spacing: %.2f um" % (LAMBDA * 2.0), "7.2", notch=True)
    echeck(metal1, LAMBDA * 1.0, "(SCMOS Rule 7.3) metal1 enclosure of contact: %.2f um" % (LAMBDA * 1.0), "7.3", other=cp)
    echeck(metal1, LAMBDA * 1.0, "(SCMOS Rule 7.3) metal1 enclosure of contact: %.2f um" % (LAMBDA * 1.0), "7.3", other=ca)
    R.save_derived(andnot(cp, metal1), "(SCMOS Rule 7.3) metal1 enclosure of contact: %.2f um" % (LAMBDA * 1.0))
    R.save_derived(andnot(ca, metal1), "(SCMOS Rule 7.3) metal1 enclosure of contact: %.2f um" % (LAMBDA * 1.0))

    # ================= SCMOS 8. VIA =================
    wcheck(via, LAMBDA * 2.0, "(SCMOS Rule 8.1) via size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "8.1")
    areacheck(via, (LAMBDA * 2.0) ** 2 + (LAMBDA * 0.1) ** 2, "(SCMOS Rule 8.1) via size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "8.1")
    scheck(via, LAMBDA * 3.0, "(SCMOS Rule 8.2) via spacing: %.2f um" % (LAMBDA * 3.0), "8.2")
    echeck(metal1, LAMBDA * 1.0, "(SCMOS Rule 8.3) metal1 enclosure of via: %.2f um" % (LAMBDA * 1.0), "8.3", other=via)
    R.save_derived(andnot(via, metal1), "(SCMOS Rule 8.3) metal1 enclosure of via: %.2f um" % (LAMBDA * 1.0))
    if not stacked_vias:
        scheck(via, LAMBDA * 2.0, "(SCMOS Rule 8.4) via to contact spacing: %.2f um" % (LAMBDA * 2.0), "8.4", other=ca)
        scheck(via, LAMBDA * 2.0, "(SCMOS Rule 8.4) via to contact spacing: %.2f um" % (LAMBDA * 2.0), "8.4", other=cp)
        R.save_derived(and_(via, or_(ca, cp)), "(SCMOS Rule 8.4) via to contact spacing: %.2f um" % (LAMBDA * 2.0))
    if not submicron:
        scheck(poly, LAMBDA * 2.0, "(SCMOS Rule 8.5) via to poly edge spacing: %.2f um" % (LAMBDA * 2.0), "8.5", other=via)
        echeck(poly, LAMBDA * 2.0, "(SCMOS Rule 8.5) via to poly edge spacing: %.2f um" % (LAMBDA * 2.0), "8.5", other=via)
        R.save_derived(straddle(via, poly), "(SCMOS Rule 8.5) via to poly edge spacing: %.2f um" % (LAMBDA * 2.0))
        scheck(active, LAMBDA * 2.0, "(SCMOS Rule 8.5) via to active edge spacing: %.2f um" % (LAMBDA * 2.0), "8.5", other=via)
        echeck(active, LAMBDA * 2.0, "(SCMOS Rule 8.5) via to active edge spacing: %.2f um" % (LAMBDA * 2.0), "8.5", other=via)
        R.save_derived(straddle(via, active), "(SCMOS Rule 8.5) via to active edge spacing: %.2f um" % (LAMBDA * 2.0))

    # ================= SCMOS 9. METAL2 =================
    wcheck(metal2, LAMBDA * 3.0, "(SCMOS Rule 9.1) metal2 width: %.2f um" % (LAMBDA * 3.0), "9.1")
    if submicron:
        scheck(metal2, LAMBDA * 3.0, "(SCMOS_SUBM Rule 9.2.b) metal2 spacing: %.2f um" % (LAMBDA * 3.0), "9.2")
        scheck(metal2, LAMBDA * 3.0, "(SCMOS_SUBM Rule 9.2.b) metal2 spacing: %.2f um" % (LAMBDA * 3.0), "9.2", notch=True)
    else:
        scheck(metal2, LAMBDA * 3.0, "(SCMOS Rule 9.2.a) metal2 spacing: %.2f um" % (LAMBDA * 3.0), "9.2")
        scheck(metal2, LAMBDA * 3.0, "(SCMOS Rule 9.2.a) metal2 spacing: %.2f um" % (LAMBDA * 3.0), "9.2", notch=True)
    echeck(metal2, LAMBDA * 1.0, "(SCMOS Rule 9.3) metal2 enclosure of via: %.2f um" % (LAMBDA * 1.0), "9.3", other=via)
    R.save_derived(andnot(via, metal2), "(SCMOS Rule 9.3) metal2 enclosure of via: %.2f um" % (LAMBDA * 1.0))

    # ================= SCMOS 10. OVERGLASS (perimeter pads) =================
    if padType == "Perimeter":
        R.save_derived(straddle(glass, pad), "Overglass straddling pad")
        BondingGlass = inside(glass, pad)
        ProbeGlass = outside(glass, pad)
        BondingPad = andnot(sized(BondingGlass, 6.0), holes(BondingGlass))
        ProbePad = andnot(sized(ProbeGlass, 6.0), holes(ProbeGlass))
        Pad = or_(BondingPad, ProbePad)
        wcheck(BondingPad, 60.0, "(SCMOS Rule 10.1) bonding pad width: 60 um", "10.1")
        wcheck(ProbePad, 20.0, "(SCMOS Rule 10.2) probe pad width: 20 um", "10.2")
        # geomGetByLayer(lyr "glass" d): lyr within d of glass, minus nodrc
        near = lambda lyr, d: andnot(and_(lyr, sized(glass, d)), L("nodrc"))
        if F("metal6Available"):
            echeck(near(metal6, 36.0), 6.0, "(SCMOS Rule 10.3) pad enclosure of glass: 6 um", "10.3", other=glass)
            R.save_derived(andnot(glass, metal6), "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
        elif F("metal5Available"):
            echeck(near(metal5, 36.0), 6.0, "(SCMOS Rule 10.3) pad enclosure of glass: 6 um", "10.3", other=glass)
            R.save_derived(andnot(glass, metal5), "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
        elif F("metal4Available"):
            echeck(near(metal4, 36.0), 6.0, "(SCMOS Rule 10.3) pad enclosure of glass: 6 um", "10.3", other=glass)
            R.save_derived(andnot(glass, metal4), "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
        elif F("metal3Available"):
            echeck(near(metal3, 36.0), 6.0, "(SCMOS Rule 10.3) pad enclosure of glass: 6 um", "10.3", other=glass)
            R.save_derived(andnot(glass, metal3), "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
        else:
            echeck(near(metal2, 36.0), 6.0, "(SCMOS Rule 10.3) pad enclosure of glass: 6 um", "10.3", other=glass)
            R.save_derived(andnot(glass, metal2), "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
        if F("metal6Available"):
            scheck(Pad, 30.0, "(SCMOS Rule 10.4) pad to unrelated metal6 spacing: 30 um", "10.4", other=near(metal6, 36.0))
        if F("metal5Available"):
            scheck(Pad, 30.0, "(SCMOS Rule 10.4) pad to unrelated metal5 spacing: 30 um", "10.4", other=near(metal5, 36.0))
        if F("metal4Available"):
            scheck(Pad, 30.0, "(SCMOS Rule 10.4) pad to unrelated metal4 spacing: 30 um", "10.4", other=near(metal4, 36.0))
        if F("metal3Available"):
            scheck(Pad, 30.0, "(SCMOS Rule 10.4) pad to unrelated metal3 spacing: 30 um", "10.4", other=near(metal3, 36.0))
        scheck(Pad, 30.0, "(SCMOS Rule 10.4) pad to unrelated metal2 spacing: 30 um", "10.4", other=near(metal2, 36.0))
        scheck(Pad, 15.0, "(SCMOS Rule 10.5) pad to unrelated metal1 spacing: 15 um", "10.5", other=near(metal1, 21.0))
        scheck(Pad, 15.0, "(SCMOS Rule 10.5) pad to unrelated poly spacing: 15 um", "10.5", other=near(poly, 21.0))
        scheck(Pad, 15.0, "(SCMOS Rule 10.5) pad to unrelated active spacing: 15 um", "10.5", other=near(active, 21.0))
        if F("elecAvailable"):
            scheck(Pad, 15.0, "(SCMOS Rule 10.5) pad to unrelated elec spacing: 15 um", "10.5", other=near(elec, 21.0))
        if TECH == "HP_GMOS10QA":
            for lyr, nm in ((metal3, "metal3"), (metal2, "metal2"), (metal1, "metal1")):
                R.save_derived(and_(lyr, BondingGlass), "(HP GMOS10QA) %s not allowed under bond pad glass cut" % nm)

    # ================= SCMOS 11-13. ELECTRODE (elec available) =================
    if F("elecAvailable"):
        if submicron:
            wcheck(CapacitorElec, LAMBDA * 7.0, "(SCMOS Rule 11.1) capacitor electrode width: %.2f um" % (LAMBDA * 7.0), "11.1")
        else:
            wcheck(CapacitorElec, LAMBDA * 3.0, "(SCMOS Rule 11.1) capacitor electrode width: %.2f um" % (LAMBDA * 3.0), "11.1")
        scheck(CapacitorElec, LAMBDA * 3.0, "(SCMOS Rule 11.2) capacitor electrode spacing: %.2f um" % (LAMBDA * 3.0), "11.2")
        scheck(CapacitorElec, LAMBDA * 3.0, "(SCMOS Rule 11.2) capacitor electrode spacing: %.2f um" % (LAMBDA * 3.0), "11.2", notch=True)
        if submicron:
            echeck(poly, LAMBDA * 5.0, "(SCMOS Rule 11.3) poly enclosure of capacitor electrode: %.2f um" % (LAMBDA * 5.0), "11.3", other=CapacitorElec)
        else:
            echeck(poly, LAMBDA * 2.0, "(SCMOS Rule 11.3) poly enclosure of capacitor electrode: %.2f um" % (LAMBDA * 2.0), "11.3", other=CapacitorElec)
        scheck(CapacitorElec, LAMBDA * 2.0, "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: %.2f um" % (LAMBDA * 2.0), "11.4", other=nBulk)
        scheck(CapacitorElec, LAMBDA * 2.0, "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: %.2f um" % (LAMBDA * 2.0), "11.4", other=pBulk)
        R.save_derived(straddle(CapacitorElec, nBulk), "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: %.2f um" % (LAMBDA * 2.0))
        R.save_derived(straddle(CapacitorElec, pBulk), "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: %.2f um" % (LAMBDA * 2.0))
        echeck(nBulk, LAMBDA * 2.0, "(SCMOS Rule 11.4) bulk enclosure of capacitor electrode: %.2f um" % (LAMBDA * 2.0), "11.4", other=CapacitorElec)
        echeck(pBulk, LAMBDA * 2.0, "(SCMOS Rule 11.4) bulk enclosure of capacitor electrode: %.2f um" % (LAMBDA * 2.0), "11.4", other=CapacitorElec)
        scheck(CapacitorElec, LAMBDA * 2.0, "(SCMOS Rule 11.4) capacitor electrode to active spacing: %.2f um" % (LAMBDA * 2.0), "11.4", other=active)
        R.save_derived(and_(CapacitorElec, active), "(SCMOS Rule 11.4) capacitor electrode to active spacing: %.2f um" % (LAMBDA * 2.0))
        if submicron:
            scheck(CapacitorElec, LAMBDA * 6.0, "(SCMOS Rule 11.5) capacitor electrode to poly contact spacing: %.2f um" % (LAMBDA * 6.0), "11.5", other=cp)
        else:
            scheck(CapacitorElec, LAMBDA * 3.0, "(SCMOS Rule 11.5) capacitor electrode to poly contact spacing: %.2f um" % (LAMBDA * 3.0), "11.5", other=cp)
        _metal_pairs = []
        if F("metal6Available"):
            _metal_pairs.append((L("metal6"), "metal6"))
        if F("metal5Available"):
            _metal_pairs.append((L("metal5"), "metal5"))
        if F("metal4Available"):
            _metal_pairs.append((L("metal4"), "metal4"))
        if F("metal3Available"):
            _metal_pairs.append((L("metal3"), "metal3"))
        _metal_pairs += [(L("metal2"), "metal2"), (L("metal1"), "metal1")]
        for lyr, nm in _metal_pairs:
            if lyr is not None and not lyr.is_empty():
                scheck(elec, LAMBDA * 2.0, "(SCMOS Rule 11.6) poly2 to unrelated %s spacing: %.2f um" % (nm, LAMBDA * 2.0), "11.6", other=lyr)
                R.save_derived(overlap(lyr, elec), "(SCMOS Rule 11.6) poly2 to unrelated %s spacing: %.2f um" % (nm, LAMBDA * 2.0))
        # 12. electrode for transistors
        wcheck(TransistorElec, LAMBDA * 2.0, "(SCMOS Rule 12.1) transistor electrode width: %.2f um" % (LAMBDA * 2.0), "12.1")
        scheck(TransistorElec, LAMBDA * 3.0, "(SCMOS Rule 12.2) transistor electrode spacing: %.2f um" % (LAMBDA * 3.0), "12.2")
        scheck(TransistorElec, LAMBDA * 3.0, "(SCMOS Rule 12.2) transistor electrode spacing: %.2f um" % (LAMBDA * 3.0), "12.2", notch=True)
        echeck(TransistorElec, LAMBDA * 2.0, "(SCMOS Rule 12.3) gate enclosure of active: %.2f um" % (LAMBDA * 2.0), "12.3", other=active)
        scheck(TransistorElec, LAMBDA * 1.0, "(SCMOS Rule 12.4) transistor electrode to active spacing: %.2f um" % (LAMBDA * 1.0), "12.4", other=active)
        scheck(TransistorElec, LAMBDA * 2.0, "(SCMOS Rule 12.5) transistor electrode to poly spacing: %.2f um" % (LAMBDA * 2.0), "12.5", other=poly)
        ocheck(TransistorElec, LAMBDA * 2.0, "(SCMOS Rule 12.5) transistor electrode overlap of poly: %.2f um" % (LAMBDA * 2.0), "12.5", other=poly)
        scheck(TransistorElec, LAMBDA * 3.0, "(SCMOS Rule 12.6) transistor electrode to poly contact spacing: %.2f um" % (LAMBDA * 3.0), "12.6", other=cp)
        R.save_derived(and_(TransistorElec, cp), "(SCMOS Rule 12.6) transistor electrode to poly contact spacing: %.2f um" % (LAMBDA * 3.0))
        scheck(TransistorElec, LAMBDA * 3.0, "(SCMOS Rule 12.6) transistor electrode to active contact spacing: %.2f um" % (LAMBDA * 3.0), "12.6", other=ca)
        R.save_derived(and_(TransistorElec, ca), "(SCMOS Rule 12.6) transistor electrode to active contact spacing: %.2f um" % (LAMBDA * 3.0))
        # 13. electrode contact
        wcheck(ce, LAMBDA * 2.0, "(SCMOS Rule 13.1) contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "13.1")
        areacheck(ce, (LAMBDA * 2.0) ** 2 + (LAMBDA * 0.1) ** 2, "(SCMOS Rule 13.1) contact size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "13.1")
        if submicron:
            scheck(ce, LAMBDA * 3.0, "(SCMOS Rule 13.2) contact spacing: %.2f um" % (LAMBDA * 3.0), "13.2")
            scheck(ce, LAMBDA * 3.0, "(SCMOS Rule 13.2) contact spacing: %.2f um" % (LAMBDA * 3.0), "13.2", notch=True)
        else:
            scheck(ce, LAMBDA * 2.0, "(SCMOS Rule 13.2) contact spacing: %.2f um" % (LAMBDA * 2.0), "13.2")
            scheck(ce, LAMBDA * 2.0, "(SCMOS Rule 13.2) contact spacing: %.2f um" % (LAMBDA * 2.0), "13.2", notch=True)
        echeck(CapacitorElec, LAMBDA * 3.0, "(SCMOS Rule 13.3) capacitor electrode enclosure of contact: %.2f um" % (LAMBDA * 3.0), "13.3", other=ce)
        echeck(TransistorElec, LAMBDA * 2.0, "(SCMOS Rule 13.4) electrode enclosure of contact (not on capacitor): %.2f um" % (LAMBDA * 2.0), "13.4", other=ce)
        R.save_derived(andnot(ce, elec), "(SCMOS Rules 13.3,13.4) electrode enclosure of contact")
        scheck(ce, LAMBDA * 3.0, "(SCMOS Rule 13.5) electrode contact to poly spacing: %.2f um" % (LAMBDA * 3.0), "13.5", other=poly)
        R.save_derived(outside(and_(ce, poly), CapacitorElec), "(SCMOS Rule 13.5) electrode contact to poly spacing: %.2f um" % (LAMBDA * 3.0))
        scheck(ce, LAMBDA * 3.0, "(SCMOS Rule 13.5) electrode contact to active spacing: %.2f um" % (LAMBDA * 3.0), "13.5", other=active)
        R.save_derived(and_(ce, active), "(SCMOS Rule 13.5) electrode contact to active spacing: %.2f um" % (LAMBDA * 3.0))

    # ================= SCMOS 14/15. VIA2 / METAL3 =================
    if F("metal3Available"):
        wcheck(via2, LAMBDA * 2.0, "(SCMOS Rule 14.1) via2 size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "14.1")
        areacheck(via2, (LAMBDA * 2.0) ** 2 + (LAMBDA * 0.1) ** 2, "(SCMOS Rule 14.1) via2 size, exactly: %.2f x %.2f um" % (LAMBDA * 2.0, LAMBDA * 2.0), "14.1")
        scheck(via2, LAMBDA * 3.0, "(SCMOS Rule 14.2) via2 spacing: %.2f um" % (LAMBDA * 3.0), "14.2")
        echeck(metal2, LAMBDA * 1.0, "(SCMOS Rule 14.3) metal2 enclosure of via2: %.2f um" % (LAMBDA * 1.0), "14.3", other=via2)
        R.save_derived(andnot(via2, metal2), "(SCMOS Rule 14.3) metal2 enclosure of via2: %.2f um" % (LAMBDA * 1.0))
        if not stacked_vias:
            scheck(via2, LAMBDA * 2.0, "(SCMOS Rule 14.4) via2 to via spacing: %.2f um" % (LAMBDA * 2.0), "14.4", other=via)
            R.save_derived(and_(outside(via2, glass), outside(via, glass)), "(SCMOS Rule 14.4) via2 to via spacing: %.2f um" % (LAMBDA * 2.0))
        if F("metal4Available"):
            wcheck(metal3, LAMBDA * 3.0, "(SCMOS_SUBM Rule 15.1) metal3 width: %.2f um" % (LAMBDA * 3.0), "15.1")
        elif submicron:
            wcheck(metal3, LAMBDA * 5.0, "(SCMOS_SUBM Rule 15.1) metal3 width: %.2f um" % (LAMBDA * 5.0), "15.1")
        else:
            wcheck(metal3, LAMBDA * 6.0, "(SCMOS Rule 15.1) metal3 width: %.2f um" % (LAMBDA * 6.0), "15.1")
        if submicron:
            scheck(metal3, LAMBDA * 3.0, "(SCMOS_SUBM Rule 15.2) metal3 spacing: %.2f um" % (LAMBDA * 3.0), "15.2")
            scheck(metal3, LAMBDA * 3.0, "(SCMOS_SUBM Rule 15.2) metal3 spacing: %.2f um" % (LAMBDA * 3.0), "15.2", notch=True)
        else:
            scheck(metal3, LAMBDA * 4.0, "(SCMOS Rule 15.2) metal3 spacing: %.2f um" % (LAMBDA * 4.0), "15.2")
            scheck(metal3, LAMBDA * 4.0, "(SCMOS Rule 15.2) metal3 spacing: %.2f um" % (LAMBDA * 4.0), "15.2", notch=True)
        if F("metal4Available"):
            echeck(metal3, LAMBDA * 1.0, "(SCMOS Rule 15.3) metal3 enclosure of via2: %.2f um" % (LAMBDA * 1.0), "15.3", other=via2)
        else:
            echeck(metal3, LAMBDA * 2.0, "(SCMOS Rule 15.3) metal3 enclosure of via2: %.2f um" % (LAMBDA * 2.0), "15.3", other=via2)
        R.save_derived(andnot(via2, metal3), "(SCMOS Rule 15.3) metal3 enclosure of via2: %.2f um" % (LAMBDA * 1.0))

    # ================= SCMOS 20. SILICIDE BLOCK =================
    if F("sblockAvailable"):
        wcheck(sblock, LAMBDA * 4.0, "(SCMOS Rule 20.1) sblock width: %.2f um" % (LAMBDA * 4.0), "20.1")
        scheck(sblock, LAMBDA * 4.0, "(SCMOS Rule 20.2) sblock spacing: %.2f um" % (LAMBDA * 4.0), "20.2")
        scheck(sblock, LAMBDA * 4.0, "(SCMOS Rule 20.2) sblock spacing: %.2f um" % (LAMBDA * 4.0), "20.2", notch=True)
        scheck(sblock, LAMBDA * 2.0, "(SCMOS Rule 20.3) sblock to contact spacing: %.2f um" % (LAMBDA * 2.0), "20.3", other=ca)
        scheck(sblock, LAMBDA * 2.0, "(SCMOS Rule 20.3) sblock to contact spacing: %.2f um" % (LAMBDA * 2.0), "20.3", other=cp)
        R.save_derived(and_(sblock, ca), "(SCMOS Rule 20.3) no contacts allowed inside sblock")
        R.save_derived(and_(sblock, cp), "(SCMOS Rule 20.3) no contacts allowed inside sblock")
        scheck(sblock, LAMBDA * 2.0, "(SCMOS Rule 20.4) sblock to external active spacing: %.2f um" % (LAMBDA * 2.0), "20.4", other=active)
        extpoly = andnot(poly, butting(poly, polySRes, 1)) if F("sblockAvailable") else poly
        scheck(sblock, LAMBDA * 2.0, "(SCMOS Rule 20.5) sblock to external poly spacing: %.2f um" % (LAMBDA * 2.0), "20.5", other=extpoly)
        R.save_derived(butting(polySRes, andnot(poly, polySRes), 1), "(SCMOS Rule 20.6) Resistor is poly inside sblock; poly ends stick out")
        wcheck(polySRes, LAMBDA * 5.0, "(SCMOS Rule 20.7) poly resistor width: %.2f um" % (LAMBDA * 5.0), "20.7")
        scheck(polySRes, LAMBDA * 7.0, "(SCMOS Rule 20.8) poly resistor spacing, same sblock: %.2f um" % (LAMBDA * 7.0), "20.8")
        scheck(polySRes, LAMBDA * 7.0, "(SCMOS Rule 20.8) poly resistor spacing, same sblock: %.2f um" % (LAMBDA * 7.0), "20.8", notch=True)
        echeck(sblock, LAMBDA * 2.0, "(SCMOS Rule 20.9) sblock enclosure of poly resistor: %.2f um" % (LAMBDA * 2.0), "20.9", other=polySRes)
        echeck(poly, LAMBDA * 3.0, "(SCMOS Rule 20.10) poly overlap of SB: %.2f um" % (LAMBDA * 3.0), "20.10", other=sblock)
        echeck(active, LAMBDA * 3.0, "(SCMOS Rule 20.10) active overlap of SB: %.2f um" % (LAMBDA * 3.0), "20.10", other=sblock)
        scheck(poly, LAMBDA * 3.0, "(SCMOS Rule 20.11) spacing SB to poly : %.2f um " % (LAMBDA * 3.0), "20.11", other=sblock)

    # ================= SCMOS 27. HIGHRES POLY =================
    if F("highresAvailable") and F("elecAvailable"):
        wcheck(highres, LAMBDA * 4.0, "(SCMOS Rule 27.1) highres width: %.2f um" % (LAMBDA * 4.0), "27.1")
        scheck(highres, LAMBDA * 4.0, "(SCMOS Rule 27.2) highres spacing: %.2f um" % (LAMBDA * 4.0), "27.2")
        scheck(highres, LAMBDA * 4.0, "(SCMOS Rule 27.2) highres spacing: %.2f um" % (LAMBDA * 4.0), "27.2", notch=True)
        scheck(highres, LAMBDA * 2.0, "(SCMOS Rule 27.3) highres to contact spacing: %.2f um" % (LAMBDA * 2.0), "27.3", other=ca)
        scheck(highres, LAMBDA * 2.0, "(SCMOS Rule 27.3) highres to contact spacing: %.2f um" % (LAMBDA * 2.0), "27.3", other=cp)
        R.save_derived(and_(highres, ca), "(SCMOS Rule 27.3) no contacts allowed inside highres")
        R.save_derived(and_(highres, cp), "(SCMOS Rule 27.3) no contacts allowed inside highres")
        scheck(highres, LAMBDA * 2.0, "(SCMOS Rule 27.4) highres to external active spacing: %.2f um" % (LAMBDA * 2.0), "27.4", other=active)
        extelec = andnot(elec, butting(elec, elecHighres, 1))
        scheck(highres, LAMBDA * 2.0, "(SCMOS Rule 27.5) highres to external elec spacing: %.2f um" % (LAMBDA * 2.0), "27.5", other=extelec)
        R.save_derived(butting(elecHighres, andnot(elec, elecHighres), 1), "(SCMOS Rule 27.6) Resistor is elec inside highres; elec ends stick out")
        R.save_derived(and_(elecHighres, nwell), "(SCMOS Rule 27.6) resistor must be outside well and over field")
        R.save_derived(and_(elecHighres, active), "(SCMOS Rule 27.6) resistor must be outside well and over field")
        wcheck(elecHighres, LAMBDA * 5.0, "(SCMOS Rule 27.7) elec resistor width: %.2f um" % (LAMBDA * 5.0), "27.7")
        scheck(elecHighres, LAMBDA * 7.0, "(SCMOS Rule 27.8) elec resistor spacing, same highres: %.2f um" % (LAMBDA * 7.0), "27.8")
        scheck(elecHighres, LAMBDA * 7.0, "(SCMOS Rule 27.8) elec resistor spacing, same highres: %.2f um" % (LAMBDA * 7.0), "27.8", notch=True)
        echeck(highres, LAMBDA * 2.0, "(SCMOS Rule 27.9) highres enclosure of elec resistor: %.2f um" % (LAMBDA * 2.0), "27.9", other=elecHighres)

    # ================= exp-98/99 MEMS (open/pstop) =================
    if F("memsAvailable"):
        wcheck(open_, 5.0, "(SCMOS Rule exp-98.1) open width: 5 um", "98.1")
        scheck(open_, 8.0, "(SCMOS Rule exp-98.2) open spacing: 8 um", "98.2")
        scheck(open_, 8.0, "(SCMOS Rule exp-98.2) open spacing: 8 um", "98.2", notch=True)
        _open_pairs = [(L("metal2"), "metal2"), (L("metal1"), "metal1"),
                       (poly, "poly")]
        if F("metal3Available"):
            _open_pairs.append((L("metal3"), "metal3"))
        if F("elecAvailable"):
            _open_pairs.append((elec, "elec"))
        for lyr, nm in _open_pairs:
            if lyr is not None and not lyr.is_empty():
                scheck(open_, 8.0, "(SCMOS Rule exp-98.3) open spacing to %s: 8 um" % nm, "98.3", other=lyr)
                scheck(open_, 8.0, "(SCMOS Rule exp-98.3) open spacing to %s: 8 um" % nm, "98.3", other=lyr, notch=True)
        wcheck(pstop, 5.0, "(SCMOS Rule exp-99.1) pstop width: 5 um", "99.1")

    # ================= DBM sanity rules =================
    if WELL == "E":
        R.save_derived(andnot(active, or_(nwell, pwell)), "(DBM Rule 1.0) Active must be inside well")
    if F("cwellAvailable"):
        R.save_derived(andnot(active, or_(nselect, pselect, cwell)), "(DBM Rule 1.1) Active must be inside select or cwell")
    else:
        R.save_derived(andnot(active, or_(nselect, pselect)), "(DBM Rule 1.1) Active must be inside select")
    if F("cwellAvailable"):
        R.save_derived(and_(cwell, pselect), "(DBM Rule 1.2) Pselect not allowed inside cwell")
    R.save_derived(and_(poly, nOhmic), "(DBM Rule 2.0) Poly cannot overlap ohmic diffusion")
    R.save_derived(and_(poly, pOhmic), "(DBM Rule 2.0) Poly cannot overlap ohmic diffusion")
    if F("elecAvailable"):
        R.save_derived(and_(elec, nOhmic), "(DBM Rule 2.1) Elec cannot overlap ohmic diffusion")
        R.save_derived(and_(elec, pOhmic), "(DBM Rule 2.1) Elec cannot overlap ohmic diffusion")
    R.save_derived(and_(L("pactive"), nselect), "(DBM Rule 3.1) Pactive and Nselect may not overlap")
    R.save_derived(and_(L("nactive"), pselect), "(DBM Rule 3.2) Nactive and Pselect may not overlap")
    if TECH in ("TSMC_CMOS035_4M2P", "TSMC_CMOS035_3M2P") and F("elecAvailable"):
        R.save_derived(and_(active, elec), "(DBM Rule 4.0, TSMC 0.4um) Elec and active may not overlap")
    if TECH == "AMI_C5N" and F("elecAvailable"):
        R.save_derived(and_(active, elec), "(DBM Rule 4.0, AMI 0.6um) Elec and active may not overlap")
    if F("hvAvailable"):
        R.save_derived(outside(tactive, active), "(DBM Rule 5.0) Thick-active without active does nothing")

    # ------------------------------------------------------------ save markers
    # Marker GDS: input layout + one layer per rule id
    # (layer = 1000 + crc32(rule_id) & 0x3FFF, datatype 0)
    import zlib
    try:
        out = pya.Layout()
        out.dbu = layout.dbu
        out.read(os.environ["LAYOUT"])
        top_out = out.top_cell()
        for rule_id, region in R.markers.items():
            if region.is_empty():
                continue
            li = out.insert_layer(pya.LayerInfo(1000 + (zlib.crc32(rule_id.encode()) & 0x3FFF), 0))
            top_out.shapes(li).insert(region)
        MARKERS = os.environ.get("MARKERS", "scmos_markers.gds")
        out.write(MARKERS)  # format by extension; always use a .gds path
    except Exception as e:
        print(json.dumps({"error": f"cannot write markers: {e}"}))
        sys.exit(1)
    print(json.dumps({"rule": R.counts, "markers": sum(R.counts.values())}))


if __name__ == "__main__":
    run()
