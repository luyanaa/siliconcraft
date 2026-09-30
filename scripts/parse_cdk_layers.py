#!/usr/bin/env python3
"""siliconcraft Phase 0 — NCSU CDK layer/process parser.

Reads NCSU CDK 1.6.0 collateral and emits a process profile's layers.yaml
(a partial pdk.yaml conforming to schema/pdk.yaml.schema).

Sources (all inside the CDK tree):
  pipo/streamInLayermap    GDSII (layer, datatype) -> Cadence layer  [authoritative GDS]
  pipo/cifInLayermap       CIF layer codes                            [cross-check]
  skill/globalData.il      NCSU_techData[]: per-process meta          [lambda, minL/W,
                           gridRes, mosisCode, model prefix, flags]
  techfile/<proc>.tf       techParams feature flags                   [metal3Available, ...]

Usage:
  python3 scripts/parse_cdk_layers.py --cdk ../ncsu-cdk-1.6.0 --process ami06 \
      --out profiles/ami06/layers.yaml

No third-party dependencies (includes a minimal YAML emitter).
"""

import argparse
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ sources

def parse_stream_map(text: str) -> dict:
    """GDSII layermap: 'name purpose gds_layer datatype' lines, '#' comments."""
    layers = {}  # name -> [(gds_layer, datatype)]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 4 or parts[1] != "drawing":
            continue
        layers.setdefault(parts[0], []).append((int(parts[2]), int(parts[3])))
    return layers


def parse_cif_map(text: str) -> dict:
    """CIF layermap: 'name purpose CIFcode' lines, '#' comments."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3 or parts[1] != "drawing":
            continue
        out.setdefault(parts[0], []).append(parts[2])
    return out


def parse_techdata(text: str) -> dict:
    """NCSU_techData['NAME'] = make_globalEntry( ?key value ... ) blocks."""
    entries = {}
    # block ends at a ')' at the start of a line (comments may contain ')')
    block_re = re.compile(
        r'NCSU_techData\[\s*"([^"]+)"\s*\]\s*=\s*make_globalEntry\((.*?)\n\s*\)\s*\n',
        re.S,
    )
    field_re = re.compile(r'\?(\w+)\s+("(?:[^"\\]|\\.)*"|t|nil|[-+]?\d*\.?\d+)')
    for m in block_re.finditer(text):
        name, body = m.group(1), m.group(2)
        fields = {}
        for f in field_re.finditer(body):
            key, raw = f.group(1), f.group(2)
            if raw == "t":
                val = True
            elif raw == "nil":
                val = None
            elif raw.startswith('"'):
                val = raw[1:-1]
            else:
                val = float(raw)
            fields[key] = val
        entries[name] = fields
    return entries


def parse_tf(text: str) -> dict:
    """Cadence techParams: '( key value )' pairs."""
    params = {}
    pair_re = re.compile(r'\(\s*(\w+)\s+("(?:[^"\\]|\\.)*"|t|nil|[-+]?\d*\.?\d+)\s*\)')
    for m in pair_re.finditer(text):
        key, raw = m.group(1), m.group(2)
        if raw == "t":
            val = True
        elif raw == "nil":
            val = None
        elif raw.startswith('"'):
            val = raw[1:-1]
        else:
            val = float(raw)
        params[key] = val
    return params


# ------------------------------------------------------------------ mapping

ROLES = {
    "nwell": "well", "pwell": "well", "cwell": "well", "gwell": "well",
    "active": "active", "cactive": "active", "tactive": "active", "ccd": "active",
    "nselect": "select", "pselect": "select", "gselect": "select",
    "poly": "gate", "polycap": "capacitor", "elec": "gate",
    "cc": "cut", "via": "cut", "via2": "cut", "via3": "cut",
    "via4": "cut", "via5": "cut",
    "metal1": "metal", "metal2": "metal", "metal3": "metal",
    "metal4": "metal", "metal5": "metal", "metal6": "metal",
    "metalcap": "capacitor", "highres": "resistor",
    "glass": "pad", "pad": "pad",
    "sblock": "misc", "open": "misc", "pstop": "misc", "pbase": "misc",
}

# layers present in every SCMOS variant
BASE_LAYERS = {
    "nwell", "pwell", "active", "nselect", "pselect", "poly", "cc",
    "metal1", "via", "metal2", "glass", "pad", "open", "pstop",
}

# techfile feature flag -> layers it gates on
GATED_LAYERS = {
    "metal3Available": ["metal3", "via2"],
    "metal4Available": ["metal4", "via3"],
    "metal5Available": ["metal5", "via4"],
    "metal6Available": ["metal6", "via5"],
    "elecAvailable": ["elec"],
    "highresAvailable": ["highres"],
    "metalcapAvailable": ["metalcap"],
    "polycapAvailable": ["polycap"],
    "sblockAvailable": ["sblock"],
    "hvAvailable": ["tactive"],
    "ccdAvailable": ["ccd"],
    "cwellAvailable": ["cwell"],
    "npnAvailable": ["pbase", "cactive"],
}

# MOSIS SCN4M/5M/6M layer maps retain this optional capability in SUBM and DEEP.
DEEP_N_WELL_MOSIS_PREFIXES = ("SCN4M", "SCN5M", "SCN6M")


def well_type_of(mosis_code: str) -> str:
    """devices.tf: wellType = substring(mosisCode 3 1) — 3rd char, 1-based."""
    code = mosis_code or ""
    return code[2].lower() if len(code) >= 3 and code[2].lower() in "npe" else "?"


# ------------------------------------------------------------------- output

def yaml_scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if re.search(r"[^A-Za-z0-9_./\-]", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def emit_yaml(obj, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return pad + "{}\n"
        lines = []
        for k, v in obj.items():
            key = yaml_scalar(k)
            if isinstance(v, dict) and v:
                lines.append(f"{pad}{key}:")
                lines.append(emit_yaml(v, indent + 1).rstrip("\n"))
            elif isinstance(v, list) and v:
                lines.append(f"{pad}{key}:")
                lines.append(emit_yaml(v, indent + 1).rstrip("\n"))
            elif isinstance(v, (dict, list)):
                lines.append(f"{pad}{key}: " + ("{}" if isinstance(v, dict) else "[]"))
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(v)}")
        return "\n".join(lines) + "\n"
    if isinstance(obj, list):
        if not obj:
            return pad + "[]\n"
        lines = []
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(pad + "-")
                lines.append(emit_yaml(item, indent + 1).rstrip("\n"))
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    return pad + yaml_scalar(obj) + "\n"


def _num(v):
    """Coerce numeric strings/values to float (lambda, gridRes, minL, minW)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"[-+]?\d*\.?\d+", v.strip()):
        return float(v)
    return v



def rule_family_for(techdata: dict, process: str) -> str:
    if techdata.get("deepRules"):
        return "scmos_deep"
    return "scmos_subm" if techdata.get("submicronRules") else "scmos"


def build_profile(name: str, process: str, td: dict, tf: dict, stream: dict, cif: dict) -> dict:
    mosis = td.get("mosisCode") or ""
    rule_family = rule_family_for(td, process)
    features = {}
    for flag in sorted(GATED_LAYERS):
        features[flag] = bool(tf.get(flag))
    gated_available = {
        layer: any(tf.get(flag) for flag in (f for f, ls in GATED_LAYERS.items() if layer in ls))
        for layer in {l for ls in GATED_LAYERS.values() for l in ls}
    }
    meta = {
        "name": name,
        "process": process,
        "description": td.get("description"),
        "mosis_code": mosis,
        "cdk_techlib": td.get("techLib"),
        "lambda_um": _num(td.get("lambda")),
        "grid_um": _num(td.get("gridRes")),
        "min_channel_um": _num(td.get("minL")),
        "min_width_um": _num(td.get("minW")),
        "model_prefix": td.get("fetModelPrefix"),
        "well_type": well_type_of(mosis),
        "rule_family": rule_family,
        "stacked_vias": td.get("stackedVias") or False,
        "features": features,
        "license": "NCSU CDK (NC State University; free use with notice preserved)",
        "sources": ["ncsu-cdk-1.6.0 (pipo/*, skill/globalData.il, techfile)"],
    }
    layers = []
    for name in sorted(stream, key=lambda n: (stream[n][0][0], stream[n][0][1])):
        entry = {
            "name": name,
            "purpose": "drawing",
            "gds": [{"layer": g, "datatype": d} for g, d in stream[name]],
            "role": ROLES.get(name, "misc"),
            "available": name in BASE_LAYERS or gated_available.get(name, False),
        }
        if name in cif:
            entry["cif"] = cif[name]
        if name == "cactive":
            entry["note"] = "NPN collector-active alias shares the active GDS stream layer in the CDK input map"
        elif name == "pwell" and meta["well_type"] == "n":
            entry["note"] = "n-well process; pwell layer unused for this variant"
        layers.append(entry)
    if mosis.startswith(DEEP_N_WELL_MOSIS_PREFIXES):
        layers.append({
            "name": "DEEP_N_WELL",
            "purpose": "drawing",
            "gds": [{"layer": 38, "datatype": 0}],
            "cif": ["CDNW"],
            "role": "well",
            "available": True,
            "note": "MOSIS SCN4M/5M/6M layer capability shared by SUBM and DEEP variants",
        })
    return {"meta": meta, "layers": layers}


# --------------------------------------------------------------------- main

HEADER = (
    "# Generated by scripts/parse_cdk_layers.py from the NCSU CDK 1.6.0.\n"
    "# Do not hand-edit: regenerate. Schema: schema/pdk.yaml.schema.\n"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cdk", default="../ncsu-cdk-1.6.0", help="NCSU CDK tree root")
    ap.add_argument("--process", required=True, help="NCSU_techData key, e.g. AMI_C5N")
    ap.add_argument("--name", default=None, help="profile name (default: process lowercased)")
    ap.add_argument("--out", required=True, help="output layers.yaml path")
    args = ap.parse_args()

    cdk = Path(args.cdk)
    try:
        techdata = parse_techdata((cdk / "skill/globalData.il").read_text())
    except FileNotFoundError as e:
        print(f"error: cannot read CDK file: {e}", file=sys.stderr)
        return 1
    if args.process not in techdata:
        known = ", ".join(sorted(techdata))
        print(f"error: unknown process '{args.process}'. Known: {known}", file=sys.stderr)
        return 1

    td = techdata[args.process]
    tf = parse_tf((cdk / "techfile" / td["techFile"]).read_text())
    stream = parse_stream_map((cdk / "pipo/streamInLayermap").read_text())
    cif = parse_cif_map((cdk / "pipo/cifInLayermap").read_text())
    if tf.get("npnAvailable") and "cactive" not in stream:
        stream["cactive"] = list(stream.get("active", []))
        cif["cactive"] = list(cif.get("active", []))

    try:
        profile = build_profile(args.name or args.process.lower(), args.process, td, tf, stream, cif)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEADER + emit_yaml(profile))
    n_avail = sum(1 for l in profile["layers"] if l["available"])
    print(f"wrote {out}: {len(profile['layers'])} layers, {n_avail} available "
          f"(lambda={profile['meta']['lambda_um']} um, grid={profile['meta']['grid_um']} um, "
          f"model prefix={profile['meta']['model_prefix']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
