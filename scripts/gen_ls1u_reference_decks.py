#!/usr/bin/env python3
"""Derive provisional LS1u DRC/LVS decks from pinned SCMOS references.

The source decks are kept verbatim under profiles/ls1u/reference/openram.
This generator applies the LS1u physical lambda, the three-metal scope, and
the LS1u layer/rule overlay.  OpenRAM's incompatible SCMOS DRC checks remain
in the generated DSL but are disabled; it does not create signoff decks.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LS1U_LAMBDA_UM = 0.5
LS1U_METALS = 3

DRC_HEADER = """
# LS1u adaptation of the pinned OpenRAM SCMOS DRC reference.
# Physical lambda is 0.5um; LS1u executable rule coverage is provisional.
"""

LS1U_DRC_OVERLAY = r'''
# LS1u normalized rule overlay.  Values are physical microns, derived from
# process_design_rules.tex (1um node: lambda = 0.5um, grid = 1 lambda).
LS1U_NW = input(42, 0)
LS1U_PW = input(41, 0)
LS1U_ACTIVE = input(43, 0)
LS1U_NSEL = input(45, 0)
LS1U_PSEL = input(44, 0)
LS1U_POLY = input(46, 0)
LS1U_CT = input(25, 0)
LS1U_M1 = input(49, 0)
LS1U_V1 = input(50, 0)
LS1U_M2 = input(51, 0)
LS1U_V2 = input(61, 0)
LS1U_M3 = input(62, 0)
LS1U_GLASS = input(52, 0)

LS1U_NW.ongrid(0.5.um).output("LS1U.0.NW_GRID", "N-well off-grid")
LS1U_PW.ongrid(0.5.um).output("LS1U.0.PW_GRID", "P-well off-grid")
LS1U_ACTIVE.ongrid(0.5.um).output("LS1U.0.ACTIVE_GRID", "Active off-grid")
LS1U_POLY.ongrid(0.5.um).output("LS1U.0.POLY_GRID", "Poly off-grid")
LS1U_CT.ongrid(0.5.um).output("LS1U.0.CONTACT_GRID", "Contact off-grid")
LS1U_M1.ongrid(0.5.um).output("LS1U.0.M1_GRID", "Metal1 off-grid")
LS1U_V1.ongrid(0.5.um).output("LS1U.0.VIA1_GRID", "Via1 off-grid")
LS1U_M2.ongrid(0.5.um).output("LS1U.0.M2_GRID", "Metal2 off-grid")
LS1U_V2.ongrid(0.5.um).output("LS1U.0.VIA2_GRID", "Via2 off-grid")
LS1U_M3.ongrid(0.5.um).output("LS1U.0.M3_GRID", "Metal3 off-grid")
LS1U_GLASS.ongrid(0.5.um).output("LS1U.0.GLASS_GRID", "Glass off-grid")

LS1U_NW.width(5.0.um).output("LS1U.2.2.1", "N-well width < 5.0um")
LS1U_PW.width(5.0.um).output("LS1U.2.1.1", "P-well width < 5.0um")
LS1U_NW.separation(LS1U_PW, 6.0.um, euclidian).output("LS1U.2.1.4", "N-well/P-well spacing < 6.0um")
LS1U_PW.separation(LS1U_NW, 6.0.um, euclidian).output("LS1U.2.2.4", "P-well/N-well spacing < 6.0um")
LS1U_NW.enclosing(LS1U_ACTIVE, 3.0.um, euclidian).output("LS1U.2.3.3.NW", "N-well active enclosure < 3.0um")
LS1U_PW.enclosing(LS1U_ACTIVE, 3.0.um, euclidian).output("LS1U.2.3.3.PW", "P-well active enclosure < 3.0um")

LS1U_ACTIVE.width(1.5.um).output("LS1U.2.3.1", "Active width < 1.5um")
LS1U_ACTIVE.space(1.5.um, euclidian).output("LS1U.2.3.2", "Active spacing < 1.5um")
LS1U_POLY.width(1.0.um).output("LS1U.2.4.1", "Poly width < 1.0um")
LS1U_POLY.space(1.0.um, euclidian).output("LS1U.2.4.3", "Poly spacing < 1.0um")
LS1U_POLY.separation(LS1U_ACTIVE, 1.0.um, euclidian).output("LS1U.2.4.2", "Poly/active spacing < 1.0um")
LS1U_POLY.enclosing(LS1U_ACTIVE, 1.0.um, projection).output("LS1U.2.4.4", "Poly gate extension < 1.0um")
LS1U_ACTIVE.enclosing(LS1U_POLY, 1.5.um, projection).output("LS1U.2.4.5", "Active extension < 1.5um")
LS1U_PW.enclosing(LS1U_POLY, 0.5.um, euclidian).output("LS1U.2.4.7", "P-well/poly enclosure < 0.5um")
LS1U_NW.enclosing(LS1U_POLY, 0.5.um, euclidian).output("LS1U.2.4.7.NW", "N-well/poly enclosure < 0.5um")

LS1U_NSEL.separation(LS1U_POLY, 1.5.um, euclidian).output("LS1U.2.5.1", "N implant/poly spacing < 1.5um")
LS1U_NSEL.enclosing(LS1U_ACTIVE, 1.0.um, euclidian).output("LS1U.2.5.2.N", "N implant/active enclosure < 1.0um")
LS1U_PSEL.enclosing(LS1U_ACTIVE, 1.0.um, euclidian).output("LS1U.2.5.2.P", "P implant/active enclosure < 1.0um")
LS1U_NSEL.separation(LS1U_PSEL, 2.0.um, euclidian).output("LS1U.2.5.3", "N/P implant spacing < 2.0um")

LS1U_CT.width(1.0.um).output("LS1U.2.6.1", "Contact width < 1.0um")
LS1U_CT.without_area(1.0.um * 1.0.um).output("LS1U.2.6.1.A", "Contact area is not 1.0um2")
LS1U_ACTIVE.enclosing(LS1U_CT, 0.5.um, euclidian).output("LS1U.2.6.2.A", "Active/contact enclosure < 0.5um")
LS1U_POLY.enclosing(LS1U_CT, 0.5.um, euclidian).output("LS1U.2.6.2.P", "Poly/contact enclosure < 0.5um")
LS1U_CT.space(1.0.um, euclidian).output("LS1U.2.6.3", "Contact spacing < 1.0um")
LS1U_CT.separation(LS1U_POLY, 1.0.um, euclidian).output("LS1U.2.6.4", "Contact/gate spacing < 1.0um")

LS1U_M1.width(2.0.um).output("LS1U.2.7.1", "Metal1 width < 2.0um")
LS1U_M1.space(2.0.um, euclidian).output("LS1U.2.7.2", "Metal1 spacing < 2.0um")
LS1U_M1.enclosing(LS1U_CT, 0.5.um, euclidian).output("LS1U.2.7.3.CT", "Metal1/contact enclosure < 0.5um")
LS1U_M1.enclosing(LS1U_V1, 0.5.um, euclidian).output("LS1U.2.7.3.V1", "Metal1/via1 enclosure < 0.5um")

LS1U_V1.width(1.0.um).output("LS1U.2.8.1", "Via1 width < 1.0um")
LS1U_V1.without_area(1.0.um * 1.0.um).output("LS1U.2.8.1.A", "Via1 area is not 1.0um2")
LS1U_V1.space(1.5.um, euclidian).output("LS1U.2.8.2", "Via1 spacing < 1.5um")
LS1U_V1.separation(LS1U_CT, 1.0.um, euclidian).output("LS1U.2.8.3", "Via1/contact spacing < 1.0um")
LS1U_V1.separation(LS1U_ACTIVE, 1.0.um, euclidian).output("LS1U.2.8.4", "Via1/active spacing < 1.0um")

LS1U_M2.width(2.0.um).output("LS1U.2.9.1", "Metal2 width < 2.0um")
LS1U_M2.space(2.0.um, euclidian).output("LS1U.2.9.2", "Metal2 spacing < 2.0um")
LS1U_M2.enclosing(LS1U_V1, 0.5.um, euclidian).output("LS1U.2.9.3", "Metal2/via1 enclosure < 0.5um")

LS1U_V2.width(1.0.um).output("LS1U.2.10.1", "Via2 width < 1.0um")
LS1U_V2.without_area(1.0.um * 1.0.um).output("LS1U.2.10.1.A", "Via2 area is not 1.0um2")
LS1U_V2.space(1.5.um, euclidian).output("LS1U.2.10.2", "Via2 spacing < 1.5um")
LS1U_M2.enclosing(LS1U_V2, 0.5.um, euclidian).output("LS1U.2.10.3.M2", "Metal2/via2 enclosure < 0.5um")
LS1U_M3.enclosing(LS1U_V2, 0.5.um, euclidian).output("LS1U.2.10.3.M3", "Metal3/via2 enclosure < 0.5um")

LS1U_M3.width(3.0.um).output("LS1U.2.11.1", "Metal3 width < 3.0um")
LS1U_M3.space(2.0.um, euclidian).output("LS1U.2.11.2", "Metal3 spacing < 2.0um")
LS1U_M3.enclosing(LS1U_GLASS, 6.0.um, euclidian).output("LS1U.2.12.2", "Metal3/glass overlap < 6.0um")
LS1U_GLASS.width(60.0.um).output("LS1U.2.12.1", "Glass opening width < 60.0um")
'''


def _replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise ValueError(f"source pattern not found: {old[:80]!r}")
    return text.replace(old, new, 1)


def derive_drc(source: str) -> str:
    text = source
    text = _replace_once(text, " <description/>", " <description>LS1u provisional SCMOS DRC</description>")
    text = _replace_once(text, "#    MOSIS SCMOS DRC", "#    LS1u provisional DRC derived from the OpenRAM MOSIS SCMOS deck")
    text = _replace_once(text, "LAMBDA = 0.2", f"LAMBDA = {LS1U_LAMBDA_UM}")
    text = _replace_once(text, "SUBM = true", "SUBM = false")
    text = _replace_once(text, "NBR_OF_METALS = 6", f"NBR_OF_METALS = {LS1U_METALS}")
    text = text.replace("0.5*LAMBDA", "LAMBDA")

    old_layers = """  Contact = input(25,0)\n  ContactPoly = input(47,0)\n  ContactActive = input(48,0)\n  ContactPoly2 = input(55, 0)\n  CT = Contact + ContactPoly + ContactActive + ContactPoly2\n  M1 = input(49,0)\n  V1 = input(50,0)\n  M2 = input(51,0)\n  V2 = input(61,0)\n  M3 = input(62,0)\n  V3 = input(30,0)\n  M4 = input(31,0)\n  CTM = input(35,0)\n  V4 = input(32,0)\n  M5 = input(33,0)\n  V5 = input(36,0)\n  M6 = input(37,0)\n  Glass = input(52,0)\n"""
    new_layers = """  Contact = input(25,0)\n  CT = Contact\n  M1 = input(49,0)\n  V1 = input(50,0)\n  M2 = input(51,0)\n  V2 = input(61,0)\n  M3 = input(62,0)\n  Glass = input(52,0)\n"""
    text = _replace_once(text, old_layers, new_layers)

    for start, end in (("### Metal 4\n", "### Via 4\n"), ("### Metal 5\n", "### Via 5\n")):
        begin = text.index(start)
        finish = text.index(end, begin)
        text = text[:begin] + text[finish:]
    begin = text.index("### Metal 6\n")
    finish = text.index("\nend\nend\nend\n\n# time spent for the DRC", begin)
    text = text[:begin] + "### Metal 6\n# LS1u has no executable rules above metal3.\n" + text[finish:]

    rule_marker = "\n### Deep NWell\n"
    text = _replace_once(
        text,
        rule_marker,
        "\nLS1U_BASE_SCMOS_RULES = false\n"
        "if LS1U_BASE_SCMOS_RULES\n### Deep NWell\n",
    )
    marker = "\n# time spent for the DRC"
    overlay = LS1U_DRC_OVERLAY.replace("<", "&lt;")
    text = text.replace(
        marker,
        "\nend\n" + DRC_HEADER + overlay + marker,
        1,
    )
    return text


def derive_lvs(source: str) -> str:
    text = source
    text = _replace_once(text, " <description/>", " <description>LS1u provisional SCMOS LVS</description>")
    text = _replace_once(text, "# Extraction for freePDK45", "# LS1u provisional LVS derived from the OpenRAM SCMOS extraction deck")

    old_layers = """  DNW = input(38,0)\n  nwell = input(42,0)\n  pwell = input(41,0)\n  CW = input(59,0)\n  active = input(43,0)\n  TA = input(60,0)\n  PBase = input(58,0)\n  poly = input(46,0)\n  SB = input(29,0)\n  nplus = input(45,0)\n  pplus = input(44,0)\n  PO2 = input(56,0)\n  HR = input(34,0)\n  Contact = input(25,0)\n  ContactPoly = input(47,0)\n  ContactActive = input(48,0)\n  ContactPoly2 = input(55, 0)\n  CT = Contact + ContactPoly + ContactActive + ContactPoly2\n  M1 = input(49,0)\n  V1 = input(50,0)\n  M2 = input(51,0)\n  V2 = input(61,0)\n  M3 = input(62,0)\n  V3 = input(30,0)\n  M4 = input(31,0)\n  CTM = input(35,0)\n  V4 = input(32,0)\n  M5 = input(33,0)\n  V5 = input(36,0)\n  M6 = input(37,0)\n  Glass = input(52,0)\n  Pads = input(26,0)\n"""
    new_layers = """  nwell = input(42,0)\n  pwell = input(41,0)\n  active = input(43,0)\n  poly = input(46,0)\n  nplus = input(45,0)\n  pplus = input(44,0)\n  Contact = input(25,0)\n  CT = Contact\n  M1 = input(49,0)\n  V1 = input(50,0)\n  M2 = input(51,0)\n  V2 = input(61,0)\n  M3 = input(62,0)\n  Glass = input(52,0)\n"""
    text = _replace_once(text, old_layers, new_layers)
    text = re.sub(r'cheat\([^)]*\) \{\n', '', text, count=1)
    text = text.replace(
        'extract_devices(mos4("n"), { "SD" =&gt; nsd, "G" =&gt; ngate, '
        '"tS" =&gt; nsd, "tD" =&gt; nsd, "tG" =&gt; poly, "W" =&gt; pwell })\n\n}\n',
        'extract_devices(mos4("n"), { "SD" =&gt; nsd, "G" =&gt; ngate, '
        '"tS" =&gt; nsd, "tD" =&gt; nsd, "tG" =&gt; poly, "W" =&gt; pwell })\n\n',
        1,
    )
    text = text.replace("connect(M3,   V3)\nconnect(V3,   M4)\nconnect(M4,   V4)\nconnect(V4,   M5)\nconnect(M5,   V5)\nconnect(V5,   M6)\n", "")
    text = text.replace("for pat in %w(pinv* pnor* pnand* and?_dec* write_driver* port_address* replica_bitcell_array*)\n  connect_explicit(pat, [ \"NWELL\", \"vdd\" ])\n  connect_explicit(pat, [ \"BULK\", \"PWELL\", \"gnd\" ])\nend\n\n", "")
    return text

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="ls1u")
    args = parser.parse_args()
    profile = ROOT / "profiles" / args.profile
    source_dir = profile / "reference" / "openram"
    out_dir = profile / "reference" / "klayout"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ls1u.lydrc").write_text(
        derive_drc((source_dir / "scn4m_subm.lydrc").read_text())
    )
    (out_dir / "ls1u.lylvs").write_text(
        derive_lvs((source_dir / "scn4m_subm.lylvs").read_text())
    )
    (out_dir / "ls1u.setup.tcl").write_text(
        "# LS1u adaptation of OpenRAM setup.tcl; device model names are profile-specific.\n"
        "ignore class c\n"
        "equate class {-circuit1 nfet} {-circuit2 LV1UNMOS}\n"
        "equate class {-circuit1 pfet} {-circuit2 LV1UPMOS}\n"
        "property {-circuit1 nfet} remove as ad ps pd\n"
        "property {-circuit1 pfet} remove as ad ps pd\n"
        "property {-circuit2 LV1UNMOS} remove as ad ps pd\n"
        "property {-circuit2 LV1UPMOS} remove as ad ps pd\n"
        "permute transistors\n"
    )
    print(f"wrote provisional LS1u KLayout DRC/LVS and Netgen setup to {out_dir}")


if __name__ == "__main__":
    main()
