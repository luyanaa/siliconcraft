#!/usr/bin/env python3
"""siliconcraft LVS runner — extract + netgen compare.

Extracts devices with the selected profile's reference/authoritative deck
into a flat SPICE netlist and compares against the schematic with netgen.
Reference manifests may point to native profile decks; otherwise the shared
SCMOS reference is used.  Deck precedence mirrors DRC: authoritative
(generated) if present, else reference; --deck overrides.
For KLayout-LVS manifests, `netgen_circuit: auto` selects the first `.subckt`
from the schematic and passes explicit `file circuit` operands to Netgen.

Usage:
  python3 scripts/run_lvs.py --profile ami06 --layout <in.gds> \
      --schematic <sch.spice> --workdir build/lvs \
      [--deck reference|authoritative|auto] [--klayout <cmd>] [--netgen <cmd>] \
      [--circuit <subckt>]

The schematic must mirror the layout topology (same nets, incl. floating
ones) and device parameters; netgen applies its value tolerances.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import run_drc
import yamlish

ROOT = Path(__file__).resolve().parent.parent
REF_DECK = ROOT / "common/lvs/scmos_reference_lvs.py"

def _manifest_deck(profile_dir, directory, key):
    manifest_path = profile_dir / directory / "manifest.yaml"
    if not manifest_path.exists():
        return None
    manifest = yamlish.load(manifest_path.read_text())
    spec = manifest.get(key) or {}
    if spec.get("available") is False:
        return None, spec, key
    file_name = spec.get("file")
    if not file_name:
        return None
    return profile_dir / directory / file_name, spec, key


def resolve_deck(profile_dir, deck):
    if deck == "authoritative":
        p = profile_dir / "generated" / "lvs" / "run.py"
        if p.exists():
            return p, {"format": "klayout-pya"}, "authoritative"
        return None, None, "authoritative"
    if deck == "reference":
        native = _manifest_deck(profile_dir, "reference", "lvs")
        if native:
            return native
        return REF_DECK, {"format": "klayout-pya"}, "reference"
    if deck == "official":
        native = _manifest_deck(profile_dir, "official", "lvs")
        if native:
            return native
        return None, None, "official"
    return REF_DECK, {"format": "klayout-pya"}, "reference"


def resolve_netgen_setup(profile_dir, deck):
    """Return a profile-provided Netgen setup file, if declared."""
    if deck not in ("reference", "official"):
        return None
    manifest_path = profile_dir / deck / "manifest.yaml"
    if not manifest_path.exists():
        return None
    manifest = yamlish.load(manifest_path.read_text())
    setup = (manifest.get("lvs") or {}).get("netgen_setup")
    if not setup:
        return None
    path = profile_dir / deck / setup
    return path if path.exists() else None
def generated_netgen_permutation_setup(profile_dir):
    """Translate canonical LVS symmetry groups to Netgen pin names."""
    from common.process_ir import load_process

    process = load_process(profile_dir.name, ROOT)
    pin_names = {"d": "drain", "s": "source", "g": "gate", "b": "bulk"}
    lines = []
    for binding in process.device_bindings.values():
        model = binding.lvs_class
        if not model:
            continue
        for group in binding.lvs_permutable:
            pins = tuple(pin_names.get(pin, pin) for pin in group)
            if len(pins) == 2:
                lines.append(f"permute {model} {pins[0]} {pins[1]}")
    return "\n".join(lines)


def _first_spice_subckt(path: Path) -> str | None:
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].lower() == ".subckt":
            return fields[1]
    return None


def _netgen_circuit(profile_dir, deck, schematic, override=None):
    if override:
        return override
    _, spec, _ = resolve_deck(profile_dir, deck)
    configured = (spec or {}).get("netgen_circuit")
    if configured and configured != "auto":
        return str(configured)
    if configured == "auto":
        circuit = _first_spice_subckt(schematic)
        if circuit is None:
            raise SystemExit(
                f"{schematic} has no .subckt; {profile_dir.name} requires a Netgen circuit name"
            )
        return circuit
    return None



def extract(profile_dir, layout, deck, workdir, klayout, extra_env=None, top_cell=None):
    """Run the selected LVS deck; returns (summary dict, spice path)."""
    meta, layermap, features = run_drc.load_profile(profile_dir)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    spice = workdir / f"extracted_{deck}.spice"
    env = os.environ.copy()
    env.update({
        "LAYOUT": str(Path(layout).resolve()),
        "REPORT": str(spice),
        "LVS_REPORT": str(workdir / f"lvs_{deck}.lvsdb"),
        "MARKERS": str(spice),
        "EXTRACTED": str(spice),
        "PREFIX": meta.get("model_prefix", ""),
        "TECH": meta.get("process", ""),
        "WELL": str(meta.get("well_type", "n")).upper(),
        "LAMBDA": str(meta["lambda_um"]),
        "GRID": str(meta.get("grid_um", 0.15)),
        "LAYERMAP": json.dumps(layermap),
        "FEATURES": json.dumps(features),
    })
    if extra_env:
        env.update(extra_env)
    deck_path, spec, resolved_deck = resolve_deck(profile_dir, deck)
    if deck_path is None:
        reason = (spec or {}).get("reason")
        detail = f": {reason}" if reason else ""
        raise SystemExit(f"{resolved_deck} LVS deck unavailable{detail}")
    args = [os.path.expandvars(str(arg)) for arg in (spec or {}).get("args", [])]
    if top_cell:
        env["TOPCELL"] = top_cell
        args.extend(["-rd", f"topcell={top_cell}"])
    cmd = f"{klayout} -b -r {deck_path} {' '.join(args)}".strip()
    proc = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
    summary = {}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
            except ValueError:
                pass
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"klayout failed ({proc.returncode}) for {resolved_deck} deck {deck_path}")
    if (spec or {}).get("format") == "klayout-lvs" and not spice.exists():
        raise SystemExit(
            f"KLayout LVS deck {deck_path} did not emit {spice}; "
            "the selected deck/input contract is incomplete"
        )
    return summary, spice


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--top-cell", default=None,
                    help="optional explicit KLayout source top cell for multi-root GDS")
    ap.add_argument("--schematic", required=True)
    ap.add_argument("--workdir", default="build/lvs")
    ap.add_argument("--deck", default="auto",
                    choices=["auto", "reference", "authoritative"])
    ap.add_argument("--klayout", default="klayout")
    ap.add_argument("--netgen", default="netgen")
    ap.add_argument("--circuit", default=None,
                    help="Netgen circuit/subckt name; profile 'auto' derives it from the schematic")
    args = ap.parse_args()

    profile_dir = ROOT / "profiles" / args.profile
    deck = args.deck
    if deck == "auto":
        deck = "authoritative" if (profile_dir / "generated" / "lvs" / "run.py").exists() \
            else "reference"

    sch = Path(args.schematic).resolve()
    workdir = Path(args.workdir).resolve()
    summary, spice = extract(
        profile_dir,
        args.layout,
        deck,
        workdir,
        args.klayout,
        extra_env={"SCHEMATIC": str(sch)},
        top_cell=args.top_cell,
    )
    print(f"[run_lvs] deck={deck} devices={summary.get('devices')} "
          f"nets={summary.get('nets')} warnings={len(summary.get('warnings', []))}")
    for w in summary.get("warnings", []):
        print(f"  warning: {w}")

    setup = workdir / "netgen.setup"
    sch_arg = os.path.relpath(sch, workdir)
    setup_source = resolve_netgen_setup(profile_dir, deck)
    setup_text = setup_source.read_text().rstrip() if setup_source else ""
    circuit = _netgen_circuit(profile_dir, deck, sch, args.circuit)
    permutation_setup = generated_netgen_permutation_setup(profile_dir)
    setup_parts = [setup_text, permutation_setup, "set tcl_precision 6"]
    setup_body = "\n".join(part for part in setup_parts if part) + "\n"
    if circuit:
        setup.write_text(setup_body)
        circuit1 = f"{spice.name} {circuit}"
        circuit2 = f"{sch_arg} {circuit}"
        netgen_cmd = (
            f"cd {shlex.quote(str(workdir))} && {args.netgen} -batch lvs "
            f"{shlex.quote(circuit1)} {shlex.quote(circuit2)} netgen.setup"
        )
    else:
        setup.write_text(setup_body + f"compare {spice.name} {sch_arg}\n")
        netgen_cmd = (
            f"cd {shlex.quote(str(workdir))} && {args.netgen} -batch lvs "
            f"{shlex.quote(spice.name)} {shlex.quote(sch_arg)} netgen.setup"
        )
    proc = subprocess.run(netgen_cmd, shell=True, capture_output=True, text=True)
    log = (proc.stdout or "") + (proc.stderr or "")
    if "match uniquely" in log:
        print("[run_lvs] netgen: CIRCUITS MATCH UNIQUELY")
        return 0
    if "do not match" in log or "MISMATCH" in log:
        print("[run_lvs] netgen: NETLISTS DO NOT MATCH", file=sys.stderr)
        print(log[-3000:], file=sys.stderr)
        return 1
    print(log[-3000:])
    print("[run_lvs] netgen: verdict not recognized (see log above)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
