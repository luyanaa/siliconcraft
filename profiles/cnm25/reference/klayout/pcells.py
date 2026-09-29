#!/usr/bin/env python3
"""CNM25 KLayout PCells — port of the APDK Glade pcells.

Sources:
  apdk_cnm25_v2024_04_09/glade/pcells/cnm25modn_m.py
  apdk_cnm25_v2024_04_09/glade/pcells/cnm25modp_m.py
  apdk_cnm25_v2024_04_09/glade/pcells/cnm25cpoly_m.py

The Glade pcells generate complete device layouts (the plain cnm25modn/
modp/cpoly variants only draw a recognition region for Glade's own extractor,
which has no KLayout equivalent).  KLayout therefore implements the *_m
geometry: parameterized element arrays with common gate/drain/source (or
common plate) options, w/l in microns, mx*my elements.

KLayout PCell length parameters arrive in database units (DBU); all internal
geometry math here is done in microns and converted at draw time.

Layer mapping (GDS number/datatype from glade/cnm25.tch):
  GASAD 2/0, POLY0 3/0, POLY1 4/0, NPLUS 5/0, WINDOW 6/0, METAL 7/0,
  CAPS 8/0, METAL2 9/0, VIA 10/0, NTUB 1/0, PWELL 26/0.
  The Glade 'backgnd' bulk recognition layer maps to PWELL for NMOS
  (p-substrate) and NTUB for PMOS (n-well), matching cnm25modp_m.py.

Rules embedded here are taken verbatim from the APDK pcells (microns):
  xygrid 0.25; GASAD width/space 2.0/4.0; NTUB ov GASAD 5.0;
  NPLUS ov GASAD 2.5; POLY1 width/space 3.0/3.0; poly ext over GASAD 2.5;
  CONTACT 2.5 sq, space 3.0, space to poly 2.0; GASAD ov CONTACT 1.0;
  POLY1 ov CONTACT 1.25; METAL width/space 2.5/3.0; METAL ov CONTACT 1.25.
  cpoly: POLY0/POLY1 width 2.5, POLY0 space 6.0, POLY0 ov POLY1 3.0,
  CONTACT space to cpoly 4.0, POLY1 ov CONTACT 1.25.

Run under KLayout (klayout -b -r <this file>), or register the module with
the KLayout PCell manager.  This file is a hand port, not a generated
artifact; it is validated by scripts/test_cnm25_pcells.py.
"""

import pya

LAY = {
    "NTUB": (1, 0),
    "GASAD": (2, 0),
    "POLY0": (3, 0),
    "POLY1": (4, 0),
    "NPLUS": (5, 0),
    "WINDOW": (6, 0),
    "METAL": (7, 0),
    "CAPS": (8, 0),
    "METAL2": (9, 0),
    "VIA": (10, 0),
    "PWELL": (26, 0),
}

XYGRID = 0.25

# APDK rules, microns
R = {
    "gasad_w": 2.0, "gasad_s": 4.0, "ntub_ov": 5.0, "npl_ov": 2.5,
    "pol_w": 3.0, "pol_s": 3.0, "pol_ext": 2.5, "pol_s_gas": 1.25,
    "cont": 2.5, "cont_s": 3.0, "cont_s_pol": 2.0,
    "gas_ov_c": 1.0, "pol_ov_c": 1.25,
    "met_w": 2.5, "met_s": 3.0, "met_ov_c": 1.25,
    "pol0_s": 6.0, "p0_ov": 3.0, "cont_s_cp": 4.0,
}


class _Base(pya.PCellDeclarationHelper):
    """Shared layer/grid handling.  In KLayout 0.30 the PCell helper passes
    TypeDouble parameters as-is (microns here), not DBU-scaled; um() is kept
    as the single conversion point in case that behavior changes.  Every
    process layer is a TypeLayer parameter (defaults from glade/cnm25.tch),
    so `<NAME>_layer` attributes exist and layers can be remapped."""

    def declare_layers(self):
        for name, (gds, dt) in LAY.items():
            self.param(name, self.TypeLayer, name,
                       default=pya.LayerInfo(gds, dt))

    def um(self, dbunits):
        """Length parameter value in microns (already microns in 0.30)."""
        return dbunits

    def box(self, cell, layer, x1, y1, x2, y2):
        """Draw a rectangle with micron coordinates."""
        g = lambda v: int(round(v / self.layout.dbu))  # noqa: E731
        cell.shapes(getattr(self, layer + "_layer")).insert(
            pya.Box(g(x1), g(y1), g(x2), g(y2)))


class CNM25ModN(_Base):
    def __init__(self):
        super().__init__()
        self.declare_layers()
        self.param("w", self.TypeDouble, "Element width (um)", default=4.5)
        self.param("l", self.TypeDouble, "Element length (um)", default=3.0)
        self.param("mx", self.TypeInt, "X elements", default=1)
        self.param("my", self.TypeInt, "Y elements", default=1)
        self.param("common_d", self.TypeInt, "Common drain", default=0)
        self.param("common_g", self.TypeInt, "Common gate", default=0)
        self.param("common_s", self.TypeInt, "Common source", default=0)

    def display_text_impl(self):
        return (f"cnm25modn_m(w={self.um(self.w):g}u l={self.um(self.l):g}u "
                f"mx={self.mx} my={self.my})")

    def produce_impl(self):
        w = self.um(self.w)
        l = self.um(self.l)
        xelem = max(1, int(self.mx))
        yelem = max(1, int(self.my))
        commd = bool(self.common_d)
        commg = bool(self.common_g)
        comms = bool(self.common_s)
        r = R
        min_w = max(r["gasad_w"], r["cont"] + 2 * r["gas_ov_c"])
        min_l = r["pol_w"]
        # snap to grid, clamp to minima (APDK pcell behavior)
        w = max(min_w, int(w / XYGRID) * XYGRID)
        l = max(min_l, int(l / XYGRID) * XYGRID)

        dx_min = l + 2 * r["cont_s_pol"] + r["cont"]
        dx_extra = (r["cont"] + 2 * r["gas_ov_c"]
                    + max(r["gasad_s"],
                          (r["met_ov_c"] - r["gas_ov_c"]) + r["met_s"]))
        dx_alt = [dx_min + (not commd) * dx_extra,
                  dx_min + (not comms) * dx_extra]
        dy = w + max(r["gasad_s"],
                     (not commg) * (2 * r["pol_ext"] + r["pol_s"]),
                     ((not commd) or (not comms))
                     * (2 * (r["met_ov_c"] - r["gas_ov_c"]) + r["met_s"]))

        # per-layer regions so element arrays translate correctly
        layers = {name: pya.Region() for name in LAY}

        def add(layer, dx, dy, x1, y1, x2, y2):
            g = lambda v: int(round(v / self.layout.dbu))  # noqa: E731
            layers[layer].insert(
                pya.Box(g(x1 + dx), g(y1 + dy), g(x2 + dx), g(y2 + dy)))

        xoff = 0
        for x in range(xelem):
            yoff = 0
            for _y in range(yelem):
                # active
                add("GASAD", xoff, yoff,
                    -(r["cont_s_pol"] + r["cont"] + r["gas_ov_c"]), 0,
                    l + r["cont_s_pol"] + r["cont"] + r["gas_ov_c"], w)
                # gate
                ext = max(r["pol_ext"],
                          commg * max(r["gasad_s"] / 2,
                                      ((not commd) or (not comms))
                                      * ((r["met_ov_c"] - r["gas_ov_c"])
                                         + r["met_s"] / 2)))
                add("POLY1", xoff, yoff, 0, -ext, l, w + ext)
                # contacts
                n = int((w - 2 * r["gas_ov_c"] + r["cont_s"])
                        // (r["cont"] + r["cont_s"]))
                s = r["cont_s"] if n > 1 else 0
                for k in range(n):
                    add("WINDOW", xoff, yoff,
                        -r["cont_s_pol"] - r["cont"],
                        r["gas_ov_c"] + k * (r["cont"] + s),
                        -r["cont_s_pol"],
                        r["gas_ov_c"] + r["cont"] + k * (r["cont"] + s))
                    add("WINDOW", xoff, yoff,
                        l + r["cont_s_pol"],
                        r["gas_ov_c"] + k * (r["cont"] + s),
                        l + r["cont_s_pol"] + r["cont"],
                        r["gas_ov_c"] + r["cont"] + k * (r["cont"] + s))
                # source/drain metal
                ext_s = max(r["met_ov_c"] - r["gas_ov_c"],
                            ((x % 2 != 0) and commd or
                             (x % 2 == 0) and comms) * (dy - w) / 2)
                add("METAL", xoff, yoff,
                    -(r["cont_s_pol"] + r["cont"] + r["met_ov_c"]), -ext_s,
                    -r["cont_s_pol"] + r["met_ov_c"], w + ext_s)
                ext_d = max(r["met_ov_c"] - r["gas_ov_c"],
                            ((x % 2 == 0) and commd or
                             (x % 2 != 0) and comms) * (dy - w) / 2)
                add("METAL", xoff, yoff,
                    l + r["cont_s_pol"] - r["met_ov_c"], -ext_d,
                    l + r["cont_s_pol"] + r["cont"] + r["met_ov_c"], w + ext_d)
                yoff += dy
            xoff += dx_alt[x % 2 != 0]

        # N+ implant and bulk enclose the whole array
        ext_n = r["cont_s_pol"] + r["cont"] + r["gas_ov_c"] + r["npl_ov"]
        add("NPLUS", 0, 0, -ext_n, -r["npl_ov"],
            l + ext_n + xoff - dx_alt[xelem % 2 != 0],
            w + r["npl_ov"] + yoff - dy)
        ext_b = r["cont_s_pol"] + r["cont"] + r["gas_ov_c"] + r["ntub_ov"]
        add("PWELL", 0, 0, -ext_b, -r["ntub_ov"],
            l + ext_b + xoff - dx_alt[xelem % 2 != 0],
            w + r["ntub_ov"] + yoff - dy)

        for name, rgn in layers.items():
            if not rgn.is_empty():
                self.cell.shapes(getattr(self, name + "_layer")).insert(rgn)


class CNM25ModP(CNM25ModN):
    """PMOS: same geometry as NMOS; bulk is NTUB and no N+ implant is drawn
    (P+ is the intrinsic GASAD implant in this process)."""

    def display_text_impl(self):
        return (f"cnm25modp_m(w={self.um(self.w):g}u l={self.um(self.l):g}u "
                f"mx={self.mx} my={self.my})")

    def produce_impl(self):
        super().produce_impl()
        # drop the N+ implant and PWELL bulk; draw NTUB (n-well) instead
        self.cell.shapes(getattr(self, "NPLUS_layer")).clear()
        self.cell.shapes(getattr(self, "PWELL_layer")).clear()
        r = R
        w = self.um(self.w)
        l = self.um(self.l)
        xelem = max(1, int(self.mx))
        yelem = max(1, int(self.my))
        commd = bool(self.common_d)
        commg = bool(self.common_g)
        comms = bool(self.common_s)
        min_w = max(r["gasad_w"], r["cont"] + 2 * r["gas_ov_c"])
        w = max(min_w, int(w / XYGRID) * XYGRID)
        l = max(r["pol_w"], int(l / XYGRID) * XYGRID)
        dx_min = l + 2 * r["cont_s_pol"] + r["cont"]
        dx_extra = (r["cont"] + 2 * r["gas_ov_c"]
                    + max(r["gasad_s"],
                          (r["met_ov_c"] - r["gas_ov_c"]) + r["met_s"]))
        dx_alt = [dx_min + (not commd) * dx_extra,
                  dx_min + (not comms) * dx_extra]
        dy = w + max(r["gasad_s"],
                     (not commg) * (2 * r["pol_ext"] + r["pol_s"]),
                     ((not commd) or (not comms))
                     * (2 * (r["met_ov_c"] - r["gas_ov_c"]) + r["met_s"]))
        xoff = sum(dx_alt[x % 2 != 0] for x in range(xelem))
        ytot = dy * yelem
        ext = r["cont_s_pol"] + r["cont"] + r["gas_ov_c"] + r["ntub_ov"]
        rgn = pya.Region()
        g = lambda v: int(round(v / self.layout.dbu))  # noqa: E731
        rgn.insert(pya.Box(g(-ext), g(-r["ntub_ov"]),
                           g(l + ext + xoff),
                           g(w + r["ntub_ov"] + ytot - dy)))
        self.cell.shapes(getattr(self, "NTUB_layer")).insert(rgn)


class CNM25Cpoly(_Base):
    """Poly0/Poly1 PiP capacitor with 4-terminal contact stubs."""

    def __init__(self):
        super().__init__()
        self.declare_layers()
        self.param("w", self.TypeDouble, "Plate width (um)", default=30.0)
        self.param("l", self.TypeDouble, "Plate length (um)", default=30.0)
        self.param("mx", self.TypeInt, "X elements", default=1)
        self.param("my", self.TypeInt, "Y elements", default=1)
        self.param("common_p0", self.TypeInt, "Common bottom plate",
                   default=0)
        self.param("common_p1", self.TypeInt, "Common top plate", default=0)

    def display_text_impl(self):
        return (f"cnm25cpoly_m(w={self.um(self.w):g}u l={self.um(self.l):g}u "
                f"mx={self.mx} my={self.my})")

    def produce_impl(self):
        r = R
        w = self.um(self.w)
        l = self.um(self.l)
        xelem = max(1, int(self.mx))
        yelem = max(1, int(self.my))
        commp0 = bool(self.common_p0)
        commp1 = bool(self.common_p1)
        min_size = (4 * r["pol_ov_c"] + 2 * r["cont"]
                    + max(r["pol_w"], r["pol_s"],
                          r["met_ov_c"] - r["pol_ov_c"] + r["met_s"]))
        # snap to 2*grid like the APDK pcell
        w = max(min_size, int(w / (2 * XYGRID)) * 2 * XYGRID)
        l = max(min_size, int(l / (2 * XYGRID)) * 2 * XYGRID)

        dx = l + max(2 * (r["p0_ov"] + r["cont_s_cp"] + r["cont"]
                          + r["pol_ov_c"]), r["pol0_s"])
        dy = w + max(2 * (r["p0_ov"] + r["cont_s_cp"] + r["cont"]
                          + r["pol_ov_c"]), r["pol0_s"])

        xoff = 0
        for x in range(xelem):
            yoff = 0
            for _y in range(yelem):
                # bottom plate POLY0 with connecting stubs
                self.box(self.cell, "POLY0", -r["p0_ov"], -r["p0_ov"],
                         l + r["p0_ov"], w + r["p0_ov"])
                if not commp0:
                    self.box(self.cell, "POLY0",
                             -r["p0_ov"], (w - r["pol_w"]) / 2,
                             -(dx - l) / 2, (w + r["pol_w"]) / 2)
                    self.box(self.cell, "POLY0",
                             l + r["p0_ov"], (w - r["pol_w"]) / 2,
                             l + (dx - l) / 2, (w + r["pol_w"]) / 2)
                    self.box(self.cell, "POLY0",
                             (l - r["p0_ov"]) / 2, -r["p0_ov"],
                             (l + r["p0_ov"]) / 2, -(dy - w) / 2)
                    self.box(self.cell, "POLY0",
                             (l - r["p0_ov"]) / 2, w + r["p0_ov"],
                             (l + r["p0_ov"]) / 2, w + (dy - w) / 2)
                # top plate POLY1 + stubs
                self.box(self.cell, "POLY1", 0, 0, l, w)
                if not commp1:
                    sl = r["pol_w"]
                    sw = r["pol_w"]
                    self.box(self.cell, "POLY1", -sl, 0, 0, sw)
                    self.box(self.cell, "POLY1", l, w - sw, l + sl, w)
                    self.box(self.cell, "POLY1", l - sw, -sl, l, 0)
                    self.box(self.cell, "POLY1", 0, w, sw, w + sl)
                # contacts + metal on the four stubs
                stubs = (
                    # west (bottom-plate connect)
                    (-r["p0_ov"] - r["cont_s_cp"] - r["cont"], r["pol_ov_c"],
                     -r["p0_ov"] - r["cont_s_cp"], r["pol_ov_c"] + r["cont"],
                     -r["p0_ov"] - r["cont_s_cp"] - r["cont"] - r["met_ov_c"],
                     r["pol_ov_c"] - r["met_ov_c"],
                     -r["p0_ov"] - r["cont_s_cp"] + r["met_ov_c"],
                     r["pol_ov_c"] + r["cont"] + r["met_ov_c"]),
                    # east
                    (l + r["p0_ov"] + r["cont_s_cp"],
                     w - r["pol_ov_c"] - r["cont"],
                     l + r["p0_ov"] + r["cont_s_cp"] + r["cont"],
                     w - r["pol_ov_c"],
                     l + r["p0_ov"] + r["cont_s_cp"] - r["met_ov_c"],
                     w - r["pol_ov_c"] - r["cont"] - r["met_ov_c"],
                     l + r["p0_ov"] + r["cont_s_cp"] + r["cont"] + r["met_ov_c"],
                     w - r["pol_ov_c"] + r["met_ov_c"]),
                    # south
                    (l - r["pol_ov_c"] - r["cont"],
                     -r["p0_ov"] - r["cont_s_cp"] - r["cont"],
                     l - r["pol_ov_c"], -r["p0_ov"] - r["cont_s_cp"],
                     l - r["pol_ov_c"] - r["cont"] - r["met_ov_c"],
                     -r["p0_ov"] - r["cont_s_cp"] - r["cont"] - r["met_ov_c"],
                     l - r["pol_ov_c"] + r["met_ov_c"],
                     -r["p0_ov"] - r["cont_s_cp"] + r["met_ov_c"]),
                    # north
                    (r["pol_ov_c"], w + r["p0_ov"] + r["cont_s_cp"],
                     r["pol_ov_c"] + r["cont"],
                     w + r["p0_ov"] + r["cont_s_cp"] + r["cont"],
                     r["pol_ov_c"] - r["met_ov_c"],
                     w + r["p0_ov"] + r["cont_s_cp"] - r["met_ov_c"],
                     r["pol_ov_c"] + r["cont"] + r["met_ov_c"],
                     w + r["p0_ov"] + r["cont_s_cp"] + r["cont"] + r["met_ov_c"]),
                )
                for (cx1, cy1, cx2, cy2, mx1, my1, mx2, my2) in stubs:
                    self.box(self.cell, "WINDOW", cx1, cy1, cx2, cy2)
                    self.box(self.cell, "METAL", mx1, my1, mx2, my2)
                yoff += dy
            xoff += dx


# PCell registration --------------------------------------------------------

def register(layout):
    for cls in (CNM25ModN, CNM25ModP, CNM25Cpoly):
        name = {
            CNM25ModN: "cnm25modn_m",
            CNM25ModP: "cnm25modp_m",
            CNM25Cpoly: "cnm25cpoly_m",
        }[cls]
        layout.register_pcell(name, cls())


if __name__ == "__main__":
    # standalone GDS smoke: klayout -b -r pcells.py
    import os
    import sys
    out = (os.environ.get("CNM25_PCELL_OUT")
           or (sys.argv[1]
               if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
               else "/tmp/cnm25_pcells.gds"))
    ly = pya.Layout()
    for (gds, dt) in set(LAY.values()):
        ly.insert_layer(pya.LayerInfo(gds, dt))
    ly.dbu = 0.001
    register(ly)
    for name, params in (
        ("cnm25modn_m", dict(w=4.5, l=3.0)),
        ("cnm25modn_m", dict(w=10.0, l=3.0, mx=2, my=1, common_d=1)),
        ("cnm25modp_m", dict(w=4.5, l=3.0)),
        ("cnm25cpoly_m", dict(w=30.0, l=30.0)),
    ):
        cell = ly.create_cell(name, params)
        print(f"{cell.name}: bbox={cell.bbox()}")
    ly.write(out)
    print(f"wrote {out}")
