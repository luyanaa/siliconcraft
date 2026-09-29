#!/usr/bin/env python3
"""CNM25 APDK library symbol/netlist contract tests.

Verifies the generated xschem symbol table (profiles/cnm25/symbols.gen.yaml +
devices/symbol_netlist.gen.yaml) and the emitted .sym files:

- every generated entry has a corresponding .sym in generated/xschem;
- the .sym header/card structure is well-formed (v/G/K/V/S/E blocks, K line
  with format + template, pins as B records);
- key netlist contracts expand to the expected SPICE/code-model syntax:
  SPICE3Lib primitives use native prefixes (q/d/j/m/r/c/l/v/i/e/g/h/t/o...),
  XSpiceLib instances netlist to an instance line plus a .model code-model
  line resolved through the .ifs union (d_and2 -> d_and, mult_2 -> mult).

No simulator or xschem binary is required; this is a contract test.
"""

import re
import sys
from pathlib import Path

import yamlish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))

PROFILE = ROOT / "profiles" / "cnm25"


def load():
    sym_doc = yamlish.load((PROFILE / "symbols.gen.yaml").read_text())
    nl_doc = yamlish.load(
        (PROFILE / "devices" / "symbol_netlist.gen.yaml").read_text())
    return sym_doc["symbols"], nl_doc["symbols"]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    symbols, netlist = load()
    out_dir = PROFILE / "generated" / "xschem"

    # every generated symbol has an emitted .sym
    missing = [n for n in symbols if not (out_dir / f"{n}.sym").exists()]
    check(not missing, f"missing .sym files: {missing}")

    # every netlist binding is covered by a symbol and vice versa
    check(set(symbols) == set(netlist),
          f"symbol/binding mismatch: {set(symbols) ^ set(netlist)}")

    # count expectations: SPICE3Lib 34 (cap skipped) + XSpiceLib 72 +
    # XtendedLib 11 = 117, minus ground replacement kept = 116
    check(len(symbols) == 116, f"expected 116 APDK symbols, got {len(symbols)}")

    # --- SPICE3Lib native prefixes -------------------------------
    prefix_expect = {
        "res": "r", "ind": "l", "diode": "d", "bjtnpn": "q", "bjtpnp": "q",
        "jfetn": "j", "mosfetn": "m", "vdc": "v", "idc": "i",
        "vcvs": "e", "vccs": "g", "ccvs": "h", "cccs": "f",
        "line": "t", "linelossy": "o", "linerc": "u",
    }
    for name, prefix in prefix_expect.items():
        e = symbols[name]
        check(e["spiceprefix"] == prefix,
              f"{name}: expected prefix {prefix}, got {e['spiceprefix']}")
        check(e["format"].startswith("@spiceprefix@name @pinlist"),
              f"{name}: bad format {e['format']}")

    check(symbols["bjtnpn"]["pins"] == [
        {"name": "C", "dir": "inout", "x1": 17.5, "y1": -2.5,
         "x2": 22.5, "y2": 2.5},
        {"name": "B", "dir": "in", "x1": -22.5, "y1": -2.5,
         "x2": -17.5, "y2": 2.5},
        {"name": "E", "dir": "inout", "x1": -2.5, "y1": 17.5,
         "x2": 2.5, "y2": 22.5},
    ], "bjtnpn pin geometry changed")

    # --- XSpiceLib code-model resolution -------------------------
    check(symbols["d_and2"]["template"]["model"] == "d_and",
          f"d_and2 should resolve to d_and: "
          f"{symbols['d_and2']['template']}")
    check(symbols["mult_2"]["template"]["model"] == "mult",
          f"mult_2 should resolve to mult: {symbols['mult_2']['template']}")
    check(symbols["d_source8"]["template"]["model"] == "d_source",
          f"d_source8 should resolve to d_source")
    check(symbols["d_ram8"]["template"]["model"] == "d_ram",
          f"d_ram8 should resolve to d_ram")
    check(symbols["gain"]["template"]["model"] == "gain",
          f"gain model wrong: {symbols['gain']['template']}")

    # instance line + .model line with parameters (literal \n escape, as
    # xschem interprets in the K format attribute)
    fmt = symbols["d_and2"]["format"]
    check("\\n.model @model d_and(" in fmt,
          f"d_and2 format must carry a .model line: {fmt!r}")
    for p in ("rise_delay", "fall_delay", "input_load"):
        check(f"{p}=@{p}" in fmt, f"d_and2 missing parameter {p}")

    # digital element pin directions come from the .ifs PORT_TABLE
    pins = {p["name"]: p["dir"] for p in symbols["d_and2"]["pins"]}
    check(pins.get("in") == "in" and pins.get("out") == "out",
          f"d_and2 pin directions wrong: {pins}")

    # ground is a global node symbol with no device format
    check(symbols["ground"]["kind"] == "gnd"
          and symbols["ground"].get("global") is True,
          "ground must be a global node symbol")
    check(symbols["ground"]["format"] == "@name",
          f"ground format wrong: {symbols['ground']['format']}")

    # --- .sym file structure --------------------------------------
    for name in ("d_and2", "bjtnpn", "res", "ground", "gain"):
        text = (out_dir / f"{name}.sym").read_text()
        check(text.startswith("v {xschem version="),
              f"{name}.sym: missing xschem header")
        m = re.search(r"^K \{type=(.*?)\n(.*)format=\"(.*)\"\n"
                      r"template=\"(.*)\"\n\}", text, re.M | re.S)
        check(m, f"{name}.sym: malformed K card")
        check(re.search(r"^B 5 .*\{name=.*dir=", text, re.M),
              f"{name}.sym: missing pin records")

    # netlist expansion sanity (format template substitution)
    from scripts.gen_symbols import template_string  # noqa: E402
    e = symbols["bjtnpn"]
    tmpl = template_string(e["template"])
    check("name=BJTNPN1" in tmpl, f"bjtnpn template wrong: {tmpl}")

    print(f"CNM25 APDK symbol contract: PASS ({len(symbols)} symbols, "
          f"{len(netlist)} bindings)")


if __name__ == "__main__":
    main()
