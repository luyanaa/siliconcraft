#!/usr/bin/env python3
"""Generate CNM25 xschem symbol bindings from the APDK Glade libraries.

Parses the Glade binary symbol files (SPICE3Lib / XSpiceLib / XtendedLib) and
the XSpice .ifs port tables, then merges xschem symbol entries into
profiles/cnm25/symbols.yaml and devices/symbol_netlist.yaml.

The generated symbols are UI + netlist-contract artifacts.  They do not claim
simulator support beyond what the APDK code models provide; XSpice digital
elements netlist with an instance line plus a .model line (code-model syntax),
which requires an ngspice/SpiceOpus build with XSpice enabled.

Usage:
  python3 scripts/gen_cnm25_apdk_symbols.py [--apdk /path/to/apdk_cnm25_v2024_04_09]
"""

import argparse
import re
import sys
from pathlib import Path

import yamlish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))


def flow(v):
    """Minimal YAML flow emitter for simple nested dict/list values."""
    if isinstance(v, dict):
        inner = ", ".join(f"{k}: {flow(x)}" for k, x in v.items())
        return "{" + inner + "}"
    if isinstance(v, list):
        return "[" + ", ".join(flow(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{v}"'


def dump_table(table):
    """Render a {name: entry} dict as 2-space-indented YAML mapping."""
    lines = []
    for name, entry in table.items():
        lines.append(f"  {name}:")
        for key, val in entry.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                lines.append(f"    {key}:")
                for item in val:
                    lines.append(f"      - {flow(item)}")
            elif isinstance(val, dict):
                lines.append(f"    {key}: {flow(val)}")
            else:
                lines.append(f"    {key}: {flow(val)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Glade binary symbol parsing
# --------------------------------------------------------------------------

def glade_strings(path: Path):
    s = path.read_bytes().decode("latin-1", errors="ignore")
    return re.findall(r"[\x20-\x7e]{2,}", s)


def parse_glade_symbol(path: Path):
    """Return (pins, nlp_format) from a Glade symbol file."""
    toks = glade_strings(path)
    pins = []
    for i, t in enumerate(toks):
        if t == "pin" and i + 1 < len(toks) and toks[i + 1] == "drawing":
            for j in range(i + 2, min(i + 5, len(toks))):
                nm = toks[j]
                if nm in ("pin", "drawing", "symbol", "boundary", "device",
                          "annotate", "NLPDeviceFormat", "out", "tpos",
                          "tneg", "F"):
                    continue
                if len(nm) <= 16 and not nm.startswith("@"):
                    pins.append(nm)
                break
    fmt = None
    for i, t in enumerate(toks):
        if t == "NLPDeviceFormat" and i + 1 < len(toks):
            fmt = toks[i + 1]
            break
    return pins, fmt


def split_format(fmt: str):
    """Split an NLPDeviceFormat into (instance_line, model_line, prefix)."""
    if not fmt:
        return None, None, None
    lines = fmt.replace("\\n", "\n").split("\n")
    inst = lines[0]
    model = "\n".join(lines[1:]).strip() if len(lines) > 1 else None
    m = re.match(r"^[0-9]?([a-zA-Z])", inst)
    prefix = m.group(1).lower() if m else "x"
    # pull ordered pin names from the [|name:%] fragments
    pins = re.findall(r"\[\|([A-Za-z0-9_+]+):", inst)
    return inst, model, prefix, pins


def parse_ifs(path: Path):
    """Return {ports: [(name, direction)], params: [names]}."""
    text = path.read_text(encoding="latin-1", errors="ignore")
    ports, params = [], []
    in_port = False
    for line in text.splitlines():
        ls = line.strip()
        if ls.startswith("Port_Name:"):
            names = re.split(r"\s+", ls.split(":", 1)[1].strip())
            in_port = True
            _ports = names
            continue
        if in_port and ls.startswith("Direction:"):
            dirs = re.split(r"\s+", ls.split(":", 1)[1].strip())
            for nm, d in zip(_ports, dirs):
                ports.append((nm, d.lower()))
            in_port = False
        if ls.startswith("Parameter_Name:"):
            params.extend(re.split(r"\s+", ls.split(":", 1)[1].strip()))
    return ports, params


def build_model_index(xspice_root: Path):
    """Union of code-model names across all xspice library .ifs files."""
    models = set()
    for sub in ("digital", "analog", "xtendedlib", "xtradev", "xtraevt"):
        for p in sorted((xspice_root / sub).glob("*.ifs")):
            models.add(p.stem)
    return models


def resolve_model(name, models):
    """Map a Glade instance name (d_and2, mult_2, d_source8) to its code
    model (d_and, mult, d_source) using the .ifs union."""
    if name in models:
        return name
    stripped = re.sub(r"[0-9]+$", "", name)
    if stripped and stripped in models:
        return stripped
    stripped2 = re.sub(r"_[0-9]+$", "", name)
    if stripped2 and stripped2 in models:
        return stripped2
    return name


# --------------------------------------------------------------------------
# xschem entry builders
# --------------------------------------------------------------------------

def box_pins(pins, box_w=40, box_h=24, dirs=None):
    """Distribute pins: west = inputs, east = outputs, else south."""
    dirs = dirs or {}
    west = [p for p in pins if dirs.get(p) in ("in", "inout", None)]
    east = [p for p in pins if dirs.get(p) == "out"]
    south = [p for p in pins if dirs.get(p) in ("vdd", "gnd", "0")]
    out = []
    if west:
        step = box_h / (len(west) + 1)
        for i, p in enumerate(west):
            y = -box_h / 2 + step * (i + 1)
            out.append({"name": p, "dir": "in",
                        "x1": -box_w / 2 - 2.5, "y1": y - 2.5,
                        "x2": -box_w / 2 + 2.5, "y2": y + 2.5})
    if east:
        step = box_h / (len(east) + 1)
        for i, p in enumerate(east):
            y = -box_h / 2 + step * (i + 1)
            out.append({"name": p, "dir": "out",
                        "x1": box_w / 2 - 2.5, "y1": y - 2.5,
                        "x2": box_w / 2 + 2.5, "y2": y + 2.5})
    if south:
        step = box_w / (len(south) + 1)
        for i, p in enumerate(south):
            x = -box_w / 2 + step * (i + 1)
            out.append({"name": p, "dir": "inout",
                        "x1": x - 2.5, "y1": box_h / 2 - 2.5,
                        "x2": x + 2.5, "y2": box_h / 2 + 2.5})
    return out


SPICE3_SPECS = {
    # name: (kind, type, prefix, format-tail, params)
    "res": ("two_pin", "resistor", "r", "@res", "res"),
    "cap": ("two_pin", "capacitor", "c", "@cap", "cap"),
    "ind": ("two_pin", "inductor", "l", "@ind", "ind"),
    "diode": ("two_pin", "diode", "d", "@model", "model"),
    "bjtnpn": ("bjt", "npn", "q", "@model", "model"),
    "bjtpnp": ("bjt", "pnp", "q", "@model", "model"),
    "jfetn": ("box", "njf", "j", "@model", "model"),
    "jfetp": ("box", "pjf", "j", "@model", "model"),
    "mesfetn": ("box", "nmesfet", "z", "@model", "model"),
    "mesfetp": ("box", "pmesfet", "z", "@model", "model"),
    "mosfetn": ("box", "nmos", "m", "@model", "model"),
    "mosfetp": ("box", "pmos", "m", "@model", "model"),
    "vdc": ("src", "vdc", "v", "@dc", "dc"),
    "vac": ("src", "vac", "v", "@ac", "ac"),
    "vpulse": ("src", "vpulse", "v", "@pulse", "pulse"),
    "vpwl": ("src", "vpwl", "v", "@pwl", "pwl"),
    "vsin": ("src", "vsin", "v", "@sin", "sin"),
    "vexp": ("src", "vexp", "v", "@exp", "exp"),
    "idc": ("src", "idc", "i", "@dc", "dc"),
    "iac": ("src", "iac", "i", "@ac", "ac"),
    "ipulse": ("src", "ipulse", "i", "@pulse", "pulse"),
    "ipwl": ("src", "ipwl", "i", "@pwl", "pwl"),
    "isin": ("src", "isin", "i", "@sin", "sin"),
    "iexp": ("src", "iexp", "i", "@exp", "exp"),
    "vcvs": ("box", "vcvs", "e", "@gain", "gain"),
    "vccs": ("box", "vccs", "g", "@transconductance", "transconductance"),
    "ccvs": ("box", "ccvs", "h", "@transresistance", "transresistance"),
    "cccs": ("box", "cccs", "f", "@gain", "gain"),
    "line": ("box", "tline", "t", "@z0", "z0"),
    "linelossy": ("box", "tline_lossy", "o", "@model", "model"),
    "linerc": ("box", "urc", "u", "@model", "model"),
    "swptc": ("box", "sw", "s", "@model", "model"),
    "swvsc": ("box", "vsw", "w", "@model", "model"),
    "mutual": ("box", "mutual", "k", "@coupling", "coupling"),
    "ground": ("gnd", "ground", "", "", ""),
}

XSPICE_PREFIX = "a"


def xspice_entry(name, model_name, ports, params):
    """XSpiceLib/XtendedLib symbol entry (box kind, code-model netlist)."""
    dirs = {p: d for p, d in ports}
    pins = box_pins([p for p, _ in ports], dirs=dirs)
    tmpl = {"name": f"X{name.upper()}", "model": model_name}
    for p in params:
        tmpl.setdefault(p, "")
    fmt = "a@name @pinlist @model"
    model_tail = "\\n.model @model " + model_name + "(" + " ".join(
        f"{p}=@{p}" for p in params) + ")"
    return {
        "kind": "box",
        "type": name,
        "box_w": max(30, 8 * len(ports) + 20),
        "pins": pins,
        "format": fmt + model_tail,
        "template": tmpl,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apdk", type=Path,
                    default=Path.home() / "Downloads" / "apdk_cnm25_v2024_04_09")
    args = ap.parse_args()

    glade = args.apdk / "glade"
    out_sym = ROOT / "profiles" / "cnm25" / "symbols.gen.yaml"
    out_nl = ROOT / "profiles" / "cnm25" / "devices" / "symbol_netlist.gen.yaml"

    sym_table = {}
    nl_table = {}

    # --- SPICE3Lib primitives -----------------------------------------
    for name, (kind, typ, prefix, fmt_tail, param) in SPICE3_SPECS.items():
        if name == "cap":
            continue  # handwritten cnm25 cap symbol (PiP) takes precedence
        sym = {
            "kind": kind, "type": typ, "spiceprefix": prefix,
            "format": f"@spiceprefix@name @pinlist {fmt_tail}",
            "template": {"name": name.upper() + "1", param: ""},
        }
        if kind == "two_pin":
            sym["shape"] = typ
            sym["pins"] = [
                {"name": "PLUS", "dir": "inout", "x1": -12.5, "y1": -2.5,
                 "x2": -7.5, "y2": 2.5},
                {"name": "MINUS", "dir": "inout", "x1": 7.5, "y1": -2.5,
                 "x2": 12.5, "y2": 2.5},
            ]
        elif kind == "bjt":
            sym["pins"] = [
                {"name": "C", "dir": "inout", "x1": 17.5, "y1": -2.5,
                 "x2": 22.5, "y2": 2.5},
                {"name": "B", "dir": "in", "x1": -22.5, "y1": -2.5,
                 "x2": -17.5, "y2": 2.5},
                {"name": "E", "dir": "inout", "x1": -2.5, "y1": 17.5,
                 "x2": 2.5, "y2": 22.5},
            ]
        elif kind == "src":
            sym["pins"] = [
                {"name": "PLUS", "dir": "inout", "x1": -12.5, "y1": -2.5,
                 "x2": -7.5, "y2": 2.5},
                {"name": "MINUS", "dir": "inout", "x1": 7.5, "y1": -2.5,
                 "x2": 12.5, "y2": 2.5},
            ]
        elif kind == "box":
            sym["box_w"] = 40
            sym["pins"] = box_pins(
                ["PLUS", "MINUS", "CTRL"] if name in ("vcvs", "vccs",
                                                      "ccvs", "cccs")
                else ["P1", "P2"], dirs={})
        elif kind == "gnd":
            sym["pins"] = [{"name": "0", "dir": "inout", "x1": -2.5,
                            "y1": -2.5, "x2": 2.5, "y2": 2.5}]
        sym_table[name] = sym
        nl_table[name] = {
            "format": sym["format"],
            "template": sym["template"],
        }

    # --- XSpiceLib / XtendedLib code models ---------------------------
    models = build_model_index(args.apdk / "spiceopus" / "xspice")
    for lib in ("XSpiceLib", "XtendedLib"):
        for model_dir in sorted((glade / lib).iterdir()):
            if not model_dir.is_dir():
                continue
            sym_file = model_dir / "symbol"
            if not sym_file.exists():
                continue
            name = model_dir.name
            model_name = resolve_model(name, models)
            # .ifs lookup for ports/directions/parameters
            ports, params = [], []
            found = False
            for sub in ("digital", "analog", "xtendedlib", "xtradev",
                        "xtraevt"):
                p = args.apdk / "spiceopus" / "xspice" / sub / f"{model_name}.ifs"
                if p.exists():
                    ports, params = parse_ifs(p)
                    found = True
                    break
            if not found:
                # fall back to the Glade symbol's pin list (no direction info)
                _, fmt = parse_glade_symbol(sym_file)
                _, _, _, fmt_pins = split_format(fmt)
                ports = [(pin, "inout") for pin in fmt_pins]
                params = []
            entry = xspice_entry(name, model_name, ports, params)
            sym_table[name] = entry
            nl_table[name] = {
                "format": entry["format"],
                "template": entry["template"],
            }

    # ground is a global node symbol, not a device
    if "ground" in sym_table:
        sym_table["ground"] = {
            "kind": "gnd", "type": "label", "global": True,
            "format": "@name", "template": {"name": "0"},
            "pins": [{"name": "p", "dir": "inout", "x1": -2.5, "y1": -2.5,
                      "x2": 2.5, "y2": 2.5}],
        }
        nl_table["ground"] = {"format": "@name", "template": {"name": "0"}}

    out_sym.write_text("# Generated by scripts/gen_cnm25_apdk_symbols.py — DO NOT HAND-EDIT.\n"
                       "# Merged by scripts/gen_symbols.py into the xschem library.\n"
                       "symbols:\n" + dump_table(sym_table) + "\n")
    out_nl.write_text("# Generated by scripts/gen_cnm25_apdk_symbols.py — DO NOT HAND-EDIT.\n"
                      "# Merged by scripts/gen_symbols.py into the xschem netlist bindings.\n"
                      "symbols:\n" + dump_table(nl_table) + "\n")
    print(f"wrote {len(sym_table)} APDK symbols to {out_sym}")
    print(f"wrote {len(nl_table)} APDK netlist bindings to {out_nl}")


if __name__ == "__main__":
    main()
