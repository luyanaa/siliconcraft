#!/usr/bin/env python3
"""siliconcraft DRC runner -- resolve and execute a profile's DRC deck.

Deck precedence (for users with an OFFICIAL foundry DRC):
    official      profiles/<proc>/official/manifest.yaml -> deck file (+ args)
                  This is the override slot: drop a foundry-approved KLayout
                  runset (or a pya script) there, declare it in manifest.yaml,
                  and it takes precedence over everything else.
    authoritative profiles/<proc>/generated/drc/run.py  (SCMOS compatibility
                  authority; generated from pdk.yaml `rules`)
    public-native  profiles/<proc>/generated/drc/<proc>-public.drc/.py
    scmos-compat   profiles/<proc>/generated/drc/<proc>-scmos-compat.drc/.py
    reference     profiles/<proc>/reference/manifest.yaml -> deck file (+ args)
                  or common/drc/scmos_reference.py fallback

The layer map (name -> GDS layer/datatype) and feature flags are exported to
the deck through the LAYERMAP/FEATURES env vars, so any deck -- ours or an
official one -- plugs in through the same interface.  The layer map is the
stable contract: an official deck needs no siliconcraft knowledge, just the
same GDS layer numbers.

Usage:
  python3 scripts/run_drc.py --profile ami06 --deck reference \\
      --layout <in.gds> --out <report.lyrdb> [--summary <rules.json>]
  --deck auto    official if present, else authoritative if generated, else reference
  --deck public-native|scmos-compat|foundry-private selects an explicit generated authority
  --klayout      command/prefix to invoke klayout (default "klayout"); may be a
                 compound shell command, e.g. 'nix develop ~/Documents/librelane --command klayout'
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yamlish

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.process_ir import load_process

DEFAULT_LAMBDA_UM = 0.5





def load_profile(profile_dir: Path):
    process = load_process(profile_dir, ROOT)
    meta = dict(process.meta)
    meta.setdefault("lambda_um", DEFAULT_LAMBDA_UM)
    layermap = {}
    for lyr in process.layers_doc.get("layers", []):
        gds = lyr.get("gds") or []
        if gds:
            layermap[lyr["name"]] = [int(gds[0]["layer"]), int(gds[0]["datatype"])]
    # The shared Diva-derived layer contract names the deep n-well isolation
    # layer in lower case (`deep_nwell`).  No profile currently supplies a
    # DEEP_N_WELL GDS layer: the NCSU CDK has no such stream layer and GDS 38 was
    # an unsourced injection (see schema/scmos_process_matrix.yaml
    # deep_n_well_layer_authority).  Keep the alias so a future source-backed
    # profile can expose it to both the DRC and LVS runners.
    if "DEEP_N_WELL" in layermap:
        layermap.setdefault("deep_nwell", layermap["DEEP_N_WELL"])
    features = dict(meta.get("features") or {})
    features["rule_family"] = process.rule_family
    features.setdefault("stackedVias", bool(meta.get("stacked_vias", False)))
    return meta, layermap, features




def resolve_deck(profile_dir: Path, deck: str):
    if deck == "official":
        manifest_path = profile_dir / "official" / "manifest.yaml"
        if manifest_path.exists():
            m = yamlish.load(manifest_path.read_text())
            spec = m.get("deck") or m.get("drc") or {}
            if spec.get("available") is False:
                return None, spec, "official"
            f = spec.get("file")
            if f:
                return profile_dir / "official" / f, spec, "official"
        return None, None, "official"
    if deck == "reference":
        # A profile may supply a native reference deck.  This is distinct from
        # the shared SCMOS reference oracle and avoids falsely treating every
        # process as SCMOS.
        manifest_path = profile_dir / "reference" / "manifest.yaml"
        if manifest_path.exists():
            m = yamlish.load(manifest_path.read_text())
            spec = m.get("deck") or m.get("drc") or {}
            if spec.get("available") is False:
                return None, spec, "reference"
            f = spec.get("file")
            if f:
                return profile_dir / "reference" / f, spec, "reference"
        return ROOT / "common/drc/scmos_reference.py", {"format": "klayout-pya"}, "reference"
    if deck in ("public-native", "scmos-compat", "foundry-private"):
        authority = {
            "public-native": "public_native",
            "scmos-compat": "scmos_compat",
            "foundry-private": "foundry_private",
        }[deck]
        suffix = {
            "public-native": "public",
            "scmos-compat": "scmos-compat",
            "foundry-private": "foundry-private",
        }[deck]
        p = profile_dir / "generated" / "drc" / f"{profile_dir.name}-{suffix}.drc"
        runtime_p = p.with_suffix(".py")
        if runtime_p.exists():
            p = runtime_p
        elif deck == "scmos-compat" and not p.exists():
            p = profile_dir / "generated" / "drc" / "run.py"
        if p.exists():
            return p, {"format": "klayout-pya", "rule_authority": authority}, deck
        return None, None, deck
    if deck == "authoritative":
        p = profile_dir / "generated" / "drc" / "run.py"
        if not p.exists():
            p = profile_dir / "generated" / "drc" / "run.drc"
        if p.exists():
            return p, {"format": "klayout-pya", "rule_authority": "scmos_compat"}, "authoritative"
        return None, None, "authoritative"
    raise SystemExit(
        f"unknown deck '{deck}' "
        "(reference|authoritative|public-native|scmos-compat|foundry-private|official|auto)"
    )


def _expand_args(args):
    return [os.path.expandvars(str(arg)) for arg in (args or [])]




def _parse_klayout_report(report):
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError):
        return None
    counts = {}
    for item in root.findall("./items/item"):
        category = item.findtext("category", default="").strip("'")
        if not category:
            continue
        try:
            multiplicity = int(item.findtext("multiplicity", default="1"))
        except ValueError:
            multiplicity = 1
        counts[category] = counts.get(category, 0) + multiplicity
    return {
        "summary_available": True,
        "external": True,
        "markers": sum(counts.values()),
        "rule": counts,
        "report": str(report),
    }


def _deck_command(klayout, deck_path, spec, extra_args=None):
    args = _expand_args((spec or {}).get("args"))
    args.extend(extra_args or [])
    return f"{klayout} -b -r {deck_path} {' '.join(args)}".strip()

def run_deck(deck_path, spec, meta, layermap, features, layout, report, klayout, top_cell=None):
    layout_path = Path(layout).resolve()
    report_path = Path(report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LAYOUT"] = str(layout_path)
    env["REPORT"] = str(report_path)
    env["LAMBDA"] = str(meta["lambda_um"])
    env["GRID"] = str(meta.get("grid_um", 0.15))
    env["TECH"] = str(meta.get("process", ""))
    env["WELL"] = str(meta.get("well_type", "n")).upper()
    env["PAD"] = "Perimeter"
    env["LAYERMAP"] = json.dumps(layermap)
    env["FEATURES"] = json.dumps(features)
    env["RULE_FAMILY"] = str(features["rule_family"])
    if (spec or {}).get("rule_authority"):
        env["RULE_AUTHORITY"] = str(spec["rule_authority"])
    extra_args = []
    if top_cell:
        env["TOPCELL"] = top_cell
        extra_args = ["-rd", f"topcell={top_cell}"]
    cmd = _deck_command(klayout, deck_path, spec, extra_args)
    proc = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
    summary = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
            except ValueError:
                pass
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"klayout failed ({proc.returncode}) for deck {deck_path}")
    if (spec or {}).get("format") == "klayout-drc" and not summary:
        if not report_path.exists():
            raise SystemExit(
                f"KLayout DRC deck {deck_path} produced no JSON summary or report; "
                "refusing to report a false clean result"
            )
        parsed = _parse_klayout_report(report_path)
        if parsed is not None:
            return parsed
        return {"summary_available": False, "report": str(report_path)}
    return summary




def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument(
        "--deck",
        default="auto",
        choices=[
            "auto",
            "reference",
            "authoritative",
            "public-native",
            "scmos-compat",
            "foundry-private",
            "official",
        ],
    )
    ap.add_argument("--layout", required=True)
    ap.add_argument("--top-cell", default=None,
                    help="optional explicit KLayout source top cell for multi-root GDS")
    ap.add_argument("--out", required=True, help="output markers GDS (one layer per rule id)")
    ap.add_argument("--summary", default=None, help="write per-rule counts JSON here")
    ap.add_argument("--klayout", default="klayout",
                    help="klayout invocation; may be a compound shell command")
    args = ap.parse_args()

    profile_dir = ROOT / "profiles" / args.profile
    if not (profile_dir / "layers.yaml").exists():
        raise SystemExit(f"profile {args.profile} not found under {profile_dir}")

    deck = args.deck
    if deck == "auto":
        for cand in ("official", "authoritative", "reference"):
            p, _, _ = resolve_deck(profile_dir, cand)
            if p is not None:
                deck = cand
                break
    if deck == "auto":
        raise SystemExit(f"no usable DRC deck for profile {args.profile}")
    deck_path, spec, deck_name = resolve_deck(profile_dir, deck)
    if deck_path is None:
        reason = (spec or {}).get("reason")
        detail = f": {reason}" if reason else ""
        raise SystemExit(
            f"deck '{deck}' not available for profile {args.profile}{detail} "
            "(official manifest/runset absent, authoritative not generated)"
        )

    meta, layermap, features = load_profile(profile_dir)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    summary = run_deck(deck_path, spec, meta, layermap, features,
                       args.layout, args.out, args.klayout, args.top_cell)
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, indent=2))
    if summary.get("summary_available") is False:
        print(f"[run_drc] deck={deck_name} layout={args.layout} markers=unknown report={args.out}")
        print("[run_drc] external deck produced a report without siliconcraft JSON counts")
        return
    n = summary.get("markers", 0)
    print(f"[run_drc] deck={deck_name} layout={args.layout} markers={n} report={args.out}")
    for rule_id, count in sorted(summary.get("rule", {}).items()):
        print(f"  {rule_id}: {count}")


if __name__ == "__main__":
    main()
