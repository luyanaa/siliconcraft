#!/usr/bin/env python3
"""Shared LVS machinery for siliconcraft SCMOS extractors.

Used by the reference extractor (common/lvs/scmos_reference_lvs.py, the
divaEXT.rul oracle) and the authoritative extractor
(common/lvs/scmos_authoritative_lvs.py, device definitions from the profile
devices.yaml) so both produce identical connectivity and netlists.

Connectivity follows the SCMOS conductor model (divaEXT saveInterconnect):
diffusion of the same doping as the well joins the well net (nOhmic ->
nwell, pOhmic -> substrate); junctions (nDiff in psub, pDiff in nwell) stay
separate nets.  Cuts (cc, via, via2..) bridge conductor layers; wells
connect only through same-type ohmic diffusion.  Text labels on GDS layer
64/0 name the nets; the substrate is one common net.
"""

import os

import pya

CONV = {"res_id": 65, "cap_id": 66, "dio_id": 67, "nolpe": 68}
TEXT_GDS = (64, 0)

MODEL_SUFFIX = {
    "nmos": "N", "pmos": "P", "nmos_hv": "Nhv", "pmos_hv": "Phv",
    "ndmos": "Nhv", "pdmos": "Phv", "nldmos": "Nldmos", "pldmos": "Pldmos",
    "nelec": "NE", "pelec": "PE", "npdiode": "NP", "pndiode": "PN",
    "nwpdiode": "NwP",
}

DEFAULT_SHEET_RES = {"poly": 20.0, "elec": 20.0, "highres": 1000.0,
                     "nwell": 1000.0, "sblock": 500.0}
DEFAULT_CAP_AREACAP = {"elec_poly": 1000.0, "poly_polycap": 700.0,
                       "metalcap": 300.0, "poly_cwell": 700.0}  # aF/um^2

CONDUCTORS = ["nDiff", "pDiff", "nOhmic", "pOhmic", "nBulk", "isoPwell",
              "poly", "elec", "metal1", "metal2", "metal3", "metal4",
              "metal5", "metal6"]
CUTS = ["cc", "via", "via2", "via3", "via4", "via5"]


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def poly_contains(poly, pt):
    """Point-in-polygon (ray casting); pya Polygon has no contains()."""
    x, y = pt.x, pt.y
    pts = list(poly.each_point_hull())
    n = len(pts)
    hit = False
    for i in range(n):
        x1, y1 = pts[i].x, pts[i].y
        x2, y2 = pts[(i + 1) % n].x, pts[(i + 1) % n].y
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            hit = not hit
    return hit


def coincident(a, b):
    """Coincident edges of two regions (Diva geomButting keep==2)."""
    return a.edges() & b.edges()


def offset_pt(edge, poly):
    """Point 2 dbu outside `poly` across `edge` (for side/end net lookup)."""
    m = edge.p1 + (edge.p2 - edge.p1) / 2
    d = edge.p2 - edge.p1
    for n in (pya.Vector(-d.y, d.x), pya.Vector(d.y, -d.x)):
        ox = 2 if n.x > 0 else (-2 if n.x < 0 else 0)
        oy = 2 if n.y > 0 else (-2 if n.y < 0 else 0)
        pt = m + pya.Vector(ox, oy)
        if not poly_contains(poly, pt):
            return pt
    return m


class Nets:
    """SCMOS connectivity result: conductor components + union-find + names."""

    def __init__(self, comps, uf, SUB, net_names, DBU, labels=()):
        self.comps = comps          # [(layer name, Polygon)]
        self.uf = uf                # UnionFind over comps + SUB node
        self.SUB = SUB              # synthetic substrate node index
        self.net_names = net_names  # root id -> label
        self.labels = tuple(labels) # (label, component index)
        self.DBU = DBU

    @property
    def net_count(self):
        return len(self.uf.p) - 1

    def comp_at(self, pt, layer=None):
        for i, (ln, poly) in enumerate(self.comps):
            if layer is not None and ln != layer:
                continue
            if poly_contains(poly, pt):
                return i
        return None

    def comp_at_smallest(self, pt):
        best, best_area = None, None
        for i, (ln, poly) in enumerate(self.comps):
            if poly_contains(poly, pt):
                a = poly.area()
                if best_area is None or a < best_area:
                    best, best_area = i, a
        return best

    def comps_interacting(self, region):
        reg = region if isinstance(region, pya.Region) else pya.Region(region)
        found = []
        for i, (ln, poly) in enumerate(self.comps):
            if not pya.Region(poly).interacting(reg).is_empty():
                found.append(i)
        return found

    def net_of(self, i):
        r = self.uf.find(i)
        return self.net_names.get(r, f"n{r}")

    def net_of_root(self, r):
        return self.net_names.get(r, f"n{r}")
    def port_nets(self):
        return {
            name: f"n{self.uf.find(component)}"
            for name, component in self.labels
        }

    def substrate_net(self):
        r = self.uf.find(self.SUB)
        return self.net_of_root(r) if r != self.SUB else None


def build_nets(D, L, F, WELL, layout, top, DBU):
    """Build SCMOS connectivity from derived layers; returns a Nets object."""
    comps = []  # (layer name, Polygon)
    for name in CONDUCTORS:
        region = D.get(name)
        if region is None or region.is_empty():
            continue
        for poly in region.merge().each():
            comps.append((name, pya.Polygon(poly)))
    uf = UnionFind(len(comps))
    SUB = len(comps)  # synthetic substrate node
    uf.p.append(SUB)

    def comp_at(pt, layer=None):
        for i, (ln, poly) in enumerate(comps):
            if layer is not None and ln != layer:
                continue
            if poly_contains(poly, pt):
                return i
        return None

    def comp_at_smallest(pt):
        best, best_area = None, None
        for i, (ln, poly) in enumerate(comps):
            if poly_contains(poly, pt):
                a = poly.area()
                if best_area is None or a < best_area:
                    best, best_area = i, a
        return best

    def comps_interacting(region):
        reg = region if isinstance(region, pya.Region) else pya.Region(region)
        found = []
        for i, (ln, poly) in enumerate(comps):
            if not pya.Region(poly).interacting(reg).is_empty():
                found.append(i)
        return found

    # same-type well contacts join the well/substrate nets
    if "nOhmic" in D and "nBulk" in D:
        for poly in D["nOhmic"].merge().each():
            for i in comps_interacting(pya.Region(pya.Polygon(poly))):
                if comps[i][0] == "nOhmic":
                    j = comp_at(pya.Polygon(poly).bbox().center(), "nBulk")
                    if j is not None:
                        uf.union(i, j)
    if "pOhmic" in D:
        for poly in D["pOhmic"].merge().each():
            polygon = pya.Polygon(poly)
            region = pya.Region(polygon)
            for i in comps_interacting(region):
                if comps[i][0] != "pOhmic":
                    continue
                iso = D.get("isoPwell")
                center = polygon.bbox().center()
                if iso is not None and not iso.is_empty() and not region.interacting(iso).is_empty():
                    j = comp_at(center, "isoPwell")
                    if j is not None:
                        uf.union(i, j)
                        continue
                uf.union(i, SUB)
    if "pwell" in D and not D["pwell"].is_empty():
        substrate_pwell = D["pwell"] - D.get("isoPwell", pya.Region())
        for poly in substrate_pwell.merge().each():
            for i in comps_interacting(pya.Region(pya.Polygon(poly))):
                uf.union(i, SUB)

    # cuts bridge conductor layers (wells connect only via same-type ohmic
    # diffusion above; the well polygon overlaps every cut inside it)
    for cut in CUTS:
        if cut not in D or D[cut].is_empty():
            continue
        for cpoly in D[cut].merge().each():
            touch = [i for i in comps_interacting(pya.Region(pya.Polygon(cpoly)))
                     if comps[i][0] not in ("nBulk", "pwell", "isoPwell")]
            for a in touch:
                for b in touch:
                    uf.union(a, b)

    # labels (text layer) name the nets
    net_names = {}
    labels = []
    tidx = layout.find_layer(TEXT_GDS[0], TEXT_GDS[1])
    if tidx is not None and tidx >= 0:
        for shp in top.shapes(tidx).each():
            if shp.is_text():
                t = shp.text
                pt = t.trans.disp
                i = comp_at_smallest(pt)
                if i is not None:
                    labels.append((t.string, i))
                    net_names[uf.find(i)] = t.string

    return Nets(comps, uf, SUB, net_names, DBU, labels)


def emit_spice(devices, counts, net_names, TECH, PREFIX, comment, nets_count):
    """Write the flat SPICE netlist to EXTRACTED (env) and return the lines."""
    ports = sorted(set(net_names.values()))
    lines = [f"* {comment} — {TECH} prefix={PREFIX}",
             f"* devices: {counts}", f"* nets: {nets_count}",
             f"* ports: {' '.join(ports)}"]
    lines += sorted(devices)
    lines.append(".end")
    out_path = os.environ.get("EXTRACTED", "extracted.spice")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return lines
