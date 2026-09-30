#!/usr/bin/env python3
"""scmos_authoritative.py — data-driven authoritative DRC deck.

Geometric design rules come from the profile's rules.yaml (typed tables
width/spacing/enclosure/extension/area/overlap; notch collapsed into
spacing, same approximation as the reference deck).  Universal checks —
DBM sanity rules, off-grid, pad geometry, saveDerived markers — are code
mirroring the reference deck (common/drc/scmos_reference.py), so per-rule
violation accounting matches the oracle.

Condition syntax (rules.yaml): comma = AND, | = OR, not- = negate.
Rule-family terms: scmos, scmos_subm, scmos_deep.
Feature keys: stacked, elec, highres, metal3..metal6,
cwell, sblock, polycap, ccd, npn, hv, metalcap, mems.

Layer names resolve to raw input layers, Diva-derived layers
(scmos_layers.derive), or pad-derived names (BondingPad, ProbePad, Pad,
near_<layer>).

Env: LAYOUT, MARKERS, LAYERMAP, FEATURES, LAMBDA, GRID, TECH, RULE_FAMILY,
WELL, PAD, RULES, RULE_AUTHORITY (public_native, scmos_compat, or
foundry_private). Same output contract as the reference deck: marker GDS
(layer = 1000 + crc32(rule_id) & 0x3FFF) + JSON summary.
"""

import json
import os
import sys
import zlib

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scmos_layers import (derive, or_, and_, andnot, inside, outside, avoiding,
                          overlap, straddle, butting, holes, sized)
from hvcmos import run_hvcmos_checks

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import yamlish


# ------------------------------------------------------------------- marker helper

class Report:
    """Collects violations per rule id; markers written as per-rule GDS layers."""

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


# ------------------------------------------------------------------ conditions

def _cond_one(term, F, TECH, RULE_FAMILY):
    neg = term.startswith("not-")
    name = term[4:] if neg else term
    if name == "scmos":
        v = RULE_FAMILY == "scmos"
    elif name == "scmos_subm":
        v = RULE_FAMILY == "scmos_subm"
    elif name == "scmos_deep":
        v = RULE_FAMILY == "scmos_deep"
    elif name == "stacked":
        v = F("stackedVias")
    elif name == "elec":
        v = F("elecAvailable")
    elif name == "highres":
        v = F("highresAvailable")
    elif name == "metal3":
        v = F("metal3Available")
    elif name == "metal4":
        v = F("metal4Available")
    elif name == "metal5":
        v = F("metal5Available")
    elif name == "metal6":
        v = F("metal6Available")
    elif name == "cwell":
        v = F("cwellAvailable")
    elif name == "sblock":
        v = F("sblockAvailable")
    elif name == "polycap":
        v = F("polycapAvailable")
    elif name == "ccd":
        v = F("ccdAvailable")
    elif name == "npn":
        v = F("npnAvailable")
    elif name == "hv":
        v = F("hvAvailable")
    elif name in {"hvcmos", "hvcmosAvailable"}:
        v = F("hvcmosAvailable")
    elif name in {"deepWell", "deepWellAvailable"}:
        v = F("deepNwellAvailable") or F("deepPwellAvailable")
    elif name in {"drift", "driftAvailable"}:
        v = F("driftAvailable")
    elif name in {"voltageAware", "voltageAwareSpacing"}:
        v = F("voltageAwareSpacing")
    elif name == "metalcap":
        v = F("metalcapAvailable")
    elif name == "mems":
        v = F("memsAvailable")
    elif name == "pselectFromActive":
        v = F("pselectFromActive")
    elif name.startswith("tech:"):
        v = (TECH == name[5:])
    elif name.startswith("tech-not-in:"):
        v = TECH not in [t.strip() for t in name[len("tech-not-in:"):].split("/")]
    else:
        raise SystemExit(f"unknown condition term '{term}' in rules.yaml")
    return (not v) if neg else v


def cond_ok(cond, F, TECH, RULE_FAMILY):
    if not cond:
        return True
    for term in str(cond).split(","):
        term = term.strip()
        if not term:
            continue
        ok = any(_cond_one(alt.strip(), F, TECH, RULE_FAMILY) for alt in term.split("|"))
        if not ok:
            return False
    return True




RULE_AUTHORITIES = {
    "public_native": {"public_native"},
    "scmos_compat": {"public_native", "scmos_compat", "provisional_hv_policy", "legacy"},
    "foundry_private": {
        "public_native",
        "scmos_compat",
        "provisional_hv_policy",
        "foundry_private",
        "legacy",
    },
}


def _entry_authority(entry, table: str) -> str:
    explicit = entry.get("authority")
    if explicit:
        return str(explicit)
    if table == "hvcmos":
        return "provisional_hv_policy"
    source = str(entry.get("source", "")).lower()
    if "public" in source:
        return "public_native"
    if "scmos" in source:
        return "scmos_compat"
    return "legacy"


def _authority_allowed(entry, table: str, selected: str) -> bool:
    try:
        allowed = RULE_AUTHORITIES[selected]
    except KeyError as exc:
        raise SystemExit(f"unsupported RULE_AUTHORITY {selected!r}") from exc
    return _entry_authority(entry, table) in allowed


def _filtered_hvcmos(hvcmos: dict, selected: str) -> dict:
    result = dict(hvcmos)
    for table in ("markers", "hierarchy", "drift", "voltage_spacing"):
        result[table] = [
            entry
            for entry in hvcmos.get(table, []) or []
            if _authority_allowed(entry, "hvcmos", selected)
        ]
    return result


# ------------------------------------------------------------------- run

def run():
    layout = pya.Layout()
    try:
        layout.read(os.environ["LAYOUT"])
    except Exception as e:
        print(json.dumps({"error": f"cannot read LAYOUT: {e}"}))
        sys.exit(1)
    top = layout.top_cell()
    global DBU
    DBU = layout.dbu
    UNIVERSE = pya.Region(top.bbox())
    LAMBDA = float(os.environ.get("LAMBDA", "0.3"))
    GRID = float(os.environ.get("GRID", "0.15"))
    TECH = os.environ.get("TECH", "")
    WELL = os.environ.get("WELL", "N")
    padType = os.environ.get("PAD", "Perimeter")
    RULES = os.environ.get("RULES", "")
    if not RULES or not os.path.exists(RULES):
        print(json.dumps({"error": f"RULES not found: {RULES}"}))
        sys.exit(1)

    LAYER_MAP = json.loads(os.environ.get("LAYERMAP", "{}"))
    FEATURES = json.loads(os.environ.get("FEATURES", "{}"))
    RULE_FAMILY = os.environ.get("RULE_FAMILY") or FEATURES.get("rule_family", "scmos")
    if RULE_FAMILY not in ("scmos", "scmos_subm", "scmos_deep"):
        raise SystemExit(f"unsupported SCMOS rule family: {RULE_FAMILY!r}")
    SELECTED_AUTHORITY = os.environ.get("RULE_AUTHORITY", "scmos_compat")
    if SELECTED_AUTHORITY not in RULE_AUTHORITIES:
        raise SystemExit(f"unsupported RULE_AUTHORITY {SELECTED_AUTHORITY!r}")

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

    D = derive(L, F, WELL, TECH, LAMBDA, DBU, UNIVERSE)
    R = Report()

    def resolve(name):
        if name in D:
            return D[name]
        if name == "BondingPad":
            return BondingPad
        if name == "ProbePad":
            return ProbePad
        if name == "Pad":
            return Pad
        if name.startswith("near_"):
            return NEAR.get(name[5:], pya.Region())
        return L(name)

    # ------------------------------------------------------------ pad geometry
    BondingGlass = inside(glass := D["glass"], D["pad"])
    ProbeGlass = outside(D["glass"], D["pad"])
    BondingPad = andnot(sized(BondingGlass, 6.0), holes(BondingGlass))
    ProbePad = andnot(sized(ProbeGlass, 6.0), holes(ProbeGlass))
    Pad = or_(BondingPad, ProbePad)
    NEAR = {}
    for nm, lyr, d in (("metal6", "metal6", 36.0), ("metal5", "metal5", 36.0),
                       ("metal4", "metal4", 36.0), ("metal3", "metal3", 36.0),
                       ("metal2", "metal2", 36.0), ("metal1", "metal1", 21.0),
                       ("poly", "poly", 21.0), ("active", "active", 21.0),
                       ("elec", "elec", 21.0)):
        if nm in D and not D[nm].is_empty():
            NEAR[nm] = andnot(and_(D[nm], sized(D["glass"], d)), L("nodrc"))

    # ------------------------------------------------------------ universal checks
    # DBM sanity rules
    if WELL == "E":
        R.save_derived(andnot(D["active"], or_(D["nwell"], D["pwell"])),
                       "(DBM Rule 1.0) Active must be inside well")
    if F("cwellAvailable"):
        R.save_derived(andnot(D["active"], or_(D["nselect"], D["pselect"], D["cwell"])),
                       "(DBM Rule 1.1) Active must be inside select or cwell")
    else:
        R.save_derived(andnot(D["active"], or_(D["nselect"], D["pselect"])),
                       "(DBM Rule 1.1) Active must be inside select")
    if F("cwellAvailable"):
        R.save_derived(and_(D["cwell"], D["pselect"]),
                       "(DBM Rule 1.2) Pselect not allowed inside cwell")
    R.save_derived(and_(D["poly"], D["nOhmic"]),
                   "(DBM Rule 2.0) Poly cannot overlap ohmic diffusion")
    R.save_derived(and_(D["poly"], D["pOhmic"]),
                   "(DBM Rule 2.0) Poly cannot overlap ohmic diffusion")
    if F("elecAvailable"):
        R.save_derived(and_(D["elec"], D["nOhmic"]),
                       "(DBM Rule 2.1) Elec cannot overlap ohmic diffusion")
        R.save_derived(and_(D["elec"], D["pOhmic"]),
                       "(DBM Rule 2.1) Elec cannot overlap ohmic diffusion")
    R.save_derived(and_(L("pactive"), D["nselect"]),
                   "(DBM Rule 3.1) Pactive and Nselect may not overlap")
    R.save_derived(and_(L("nactive"), D["pselect"]),
                   "(DBM Rule 3.2) Nactive and Pselect may not overlap")
    if F("elecAvailable") and TECH in ("TSMC_CMOS035_4M2P", "TSMC_CMOS035_3M2P"):
        R.save_derived(and_(D["active"], D["elec"]),
                       "(DBM Rule 4.0, TSMC 0.4um) Elec and active may not overlap")
    if F("elecAvailable") and TECH == "AMI_C5N":
        R.save_derived(and_(D["active"], D["elec"]),
                       "(DBM Rule 4.0, AMI 0.6um) Elec and active may not overlap")
    if F("hvAvailable"):
        R.save_derived(outside(D["tactive"], D["active"]),
                       "(DBM Rule 5.0) Thick-active without active does nothing")

    # saveDerived markers (same set as the reference deck, for count parity)
    R.save_derived(and_(D["nwell"], D["pwell"]),
                   "(SCMOS Rule 1 note) n-wells and p-wells may not overlap")
    R.save_derived(butting(and_(D["ca"], D["nselect"]), and_(D["ca"], D["pselect"]), 1),
                   "(SCMOS Rule 4.3) select overlap of active contact: 1 lambda")
    R.save_derived(and_(D["nselect"], D["pselect"]),
                   "(SCMOS Rule 4.4) n select and p select may not overlap")
    R.save_derived(andnot(D["cp"], D["poly"]),
                   "(SCMOS Rule 5.2.b) poly enclosure of contact: 1 lambda")
    if F("elecAvailable"):
        R.save_derived(andnot(D["cc"], or_(D["poly"], D["elec"], D["active"])),
                       "Found a contact (cc) shape with no active/poly/poly2 overlap")
    R.save_derived(and_(D["cp"], D["active"]),
                   "(SCMOS Rule 5.6.b) poly contact to active spacing: 2 lambda")
    R.save_derived(and_(D["cp"], D["active"]),
                   "(SCMOS Rule 5.7.b) poly contact to active spacing, many contacts: 3 lambda")
    R.save_derived(andnot(D["ca"], D["active"]),
                   "(SCMOS Rule 6.2.b) active enclosure of contact: 1 lambda")
    R.save_derived(and_(D["ca"], D["Gate"]),
                   "(SCMOS Rule 6.4) active contact to transistor gate spacing: 2 lambda")
    R.save_derived(and_(D["ca"], D["fieldPoly"]),
                   "(SCMOS Rule 6.6.b) active contact to field poly spacing: 2 lambda")
    R.save_derived(and_(D["ca"], D["fieldPoly"]),
                   "(SCMOS Rule 6.7.b) active contact to field poly spacing, many contacts: 3 lambda")
    R.save_derived(and_(D["ca"], D["cp"]),
                   "(SCMOS Rule 6.8.b) active contact to poly contact spacing: 4 lambda")
    R.save_derived(andnot(D["cp"], D["metal1"]),
                   "(SCMOS Rule 7.3) metal1 enclosure of contact: 1 lambda")
    R.save_derived(andnot(D["ca"], D["metal1"]),
                   "(SCMOS Rule 7.3) metal1 enclosure of contact: 1 lambda")
    R.save_derived(andnot(D["via"], D["metal1"]),
                   "(SCMOS Rule 8.3) metal1 enclosure of via: 1 lambda")
    if not F("stackedVias"):
        R.save_derived(and_(D["via"], or_(D["ca"], D["cp"])),
                       "(SCMOS Rule 8.4) via to contact spacing: 2 lambda")
    if RULE_FAMILY == "scmos":
        R.save_derived(straddle(D["via"], D["poly"]),
                       "(SCMOS Rule 8.5) via to poly edge spacing: 2 lambda")
        R.save_derived(straddle(D["via"], D["active"]),
                       "(SCMOS Rule 8.5) via to active edge spacing: 2 lambda")
    R.save_derived(andnot(D["via"], D["metal2"]),
                   "(SCMOS Rule 9.3) metal2 enclosure of via: 1 lambda")
    if padType == "Perimeter":
        R.save_derived(straddle(D["glass"], D["pad"]), "Overglass straddling pad")
        for nm in ("metal6", "metal5", "metal4", "metal3", "metal2"):
            if nm in D and not D[nm].is_empty():
                R.save_derived(andnot(D["glass"], D[nm]),
                               "(SCMOS Rule 10.3) pad enclosure of glass: 6 um")
    if F("elecAvailable"):
        R.save_derived(straddle(D["CapacitorElec"], D["nBulk"]),
                       "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: 2 lambda")
        R.save_derived(straddle(D["CapacitorElec"], D["pBulk"]),
                       "(SCMOS Rule 11.4) capacitor electrode to bulk spacing: 2 lambda")
        R.save_derived(and_(D["CapacitorElec"], D["active"]),
                       "(SCMOS Rule 11.4) capacitor electrode to active spacing: 2 lambda")
        for nm in ("metal6", "metal5", "metal4", "metal3", "metal2", "metal1"):
            if nm in D and not D[nm].is_empty():
                R.save_derived(overlap(D[nm], D["elec"]),
                               f"(SCMOS Rule 11.6) poly2 to unrelated {nm} spacing: 2 lambda")
        R.save_derived(and_(D["TransistorElec"], D["cp"]),
                       "(SCMOS Rule 12.6) transistor electrode to poly contact spacing: 3 lambda")
        R.save_derived(and_(D["TransistorElec"], D["ca"]),
                       "(SCMOS Rule 12.6) transistor electrode to active contact spacing: 3 lambda")
        R.save_derived(andnot(D["ce"], D["elec"]),
                       "(SCMOS Rules 13.3,13.4) electrode enclosure of contact")
        R.save_derived(outside(and_(D["ce"], D["poly"]), D["CapacitorElec"]),
                       "(SCMOS Rule 13.5) electrode contact to poly spacing: 3 lambda")
        R.save_derived(and_(D["ce"], D["active"]),
                       "(SCMOS Rule 13.5) electrode contact to active spacing: 3 lambda")
    if F("metal3Available"):
        R.save_derived(andnot(D["via2"], D["metal2"]),
                       "(SCMOS Rule 14.3) metal2 enclosure of via2: 1 lambda")
        if not F("stackedVias"):
            R.save_derived(and_(outside(D["via2"], D["glass"]), outside(D["via"], D["glass"])),
                           "(SCMOS Rule 14.4) via2 to via spacing: 2 lambda")
        R.save_derived(andnot(D["via2"], D["metal3"]),
                       "(SCMOS Rule 15.3) metal3 enclosure of via2: 1 lambda")
    if F("highresAvailable") and F("elecAvailable"):
        R.save_derived(and_(D["highres"], D["ca"]),
                       "(SCMOS Rule 27.3) no contacts allowed inside highres")
        R.save_derived(and_(D["highres"], D["cp"]),
                       "(SCMOS Rule 27.3) no contacts allowed inside highres")
        R.save_derived(butting(D["elecHighres"], andnot(D["elec"], D["elecHighres"]), 1),
                       "(SCMOS Rule 27.6) Resistor is elec inside highres; elec ends stick out")
        R.save_derived(and_(D["elecHighres"], D["nwell"]),
                       "(SCMOS Rule 27.6) resistor must be outside well and over field")
        R.save_derived(and_(D["elecHighres"], D["active"]),
                       "(SCMOS Rule 27.6) resistor must be outside well and over field")

    # off-grid (same layer set as the reference deck)
    _og = [(D["nwell"], "nwell"), (D["pwell"], "pwell"), (D["active"], "active"),
           (D["nselect"], "nselect"), (D["pselect"], "pselect"), (D["poly"], "poly"),
           (D["metal1"], "metal1"), (D["ca"], "ca"), (D["cp"], "cp"),
           (D["metal2"], "metal2"), (D["via"], "via")]
    if F("metal3Available"):
        _og += [(D["metal3"], "metal3"), (D["via2"], "via2")]
    if F("metal4Available"):
        _og += [(D["metal4"], "metal4"), (D["via3"], "via3")]
    if F("metal5Available"):
        _og += [(D["metal5"], "metal5"), (D["via4"], "via4")]
    if F("metal6Available"):
        _og += [(D["metal6"], "metal6"), (D["via5"], "via5")]
    for _lyr, _nm in _og:
        R.off_grid(_lyr, GRID, "(SCMOS Inst) Edge not on grid")

    # ------------------------------------------------------------ data-driven checks
    def _dbu(d_um):
        return max(1, int(round(d_um / DBU)))

    def _to_region(ep):
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
        R.item(_to_region(region.enclosing_check(other, _dbu(min_um))), rule_id, msg)

    def ocheck(region, min_um, msg, rule_id, other):
        if region.is_empty() or other.is_empty():
            return
        R.item(_to_region(region.overlap_check(other, _dbu(min_um))), rule_id, msg)

    def areacheck(region, max_um2, msg, rule_id):
        if region.is_empty():
            return
        bad = pya.Region()
        for poly in region.each():
            if poly.area() * DBU * DBU > max_um2:
                bad += pya.Region(poly)
        R.item(bad, rule_id, msg)

    rules = yamlish.load(open(RULES).read())
    tables = rules.get("rules", {})
    grid = tables.get("grid") or {}
    for kind, fn in (("width", wcheck), ("spacing", scheck),
                     ("enclosure", echeck), ("extension", echeck),
                     ("area", areacheck), ("overlap", ocheck)):
        for entry in tables.get(kind, []):
            if not _authority_allowed(entry, kind, SELECTED_AUTHORITY):
                continue
            if not cond_ok(entry.get("condition"), F, TECH, RULE_FAMILY):
                continue
            rid = entry["id"]
            msg = f"({rid}) {entry.get('note', '')}".strip()
            r = resolve(entry["layer"])
            if r.is_empty():
                continue
            layer2 = entry.get("layer2")
            if kind == "spacing":
                other = resolve(layer2) if layer2 else None
                fn(r, entry["value_um"], msg, rid, other=other,
                   app=bool(entry.get("app", False)))
            elif kind in ("enclosure", "extension", "overlap"):
                other = resolve(layer2) if layer2 else r
                fn(r, entry["value_um"], msg, rid, other=other)
            else:
                fn(r, entry["value_um"], msg, rid)

    run_hvcmos_checks(
        _filtered_hvcmos(rules.get("hvcmos") or {}, SELECTED_AUTHORITY),
        D,
        resolve,
        layout,
        top,
        L,
        F,
        WELL,
        DBU,
        R,
    )
    # ------------------------------------------------------------ save markers
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
