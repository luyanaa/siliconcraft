#!/usr/bin/env python3
"""Validate the OpenRule1um portable envelope against the target DRC.

Three checks are intentionally separate:

* legality: synthetic canonical layer geometry must produce zero target-DRC
  markers; the upstream Basic GDS is not read;
* efficiency: report SCMOS(lambda=0.5) ratios, with BEOL kept out of the
  portable lambda decision and evaluated as native-routing overrides;
* semantics: nominal cut geometry, marker containment, and DRC thresholds are
  represented as different contracts.
"""

from __future__ import annotations

import argparse
import json
import os
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yamlish
import run_drc


ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profiles" / "openrule1um"
LAYERS = PROFILE / "layers.yaml"
REFERENCE = PROFILE / "reference"

GENERATOR = ROOT / "common" / "tests" / "make_openrule1um_portable.py"
RUN_DRC = ROOT / "scripts" / "run_drc.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[portable] FAIL: {message}")


def run_checked(command: list[str], env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if proc.returncode:
        detail = (proc.stdout + proc.stderr).strip()
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(command)}\n{detail}")
    return proc.stdout


def make_fixture(out: Path, klayout: str, *, well_gap: float = 5.0,
                 nwell_ndiff_gap: float = 3.0) -> None:
    env = os.environ.copy()
    env.update({
        "OUT": str(out),
        "WELL_GAP": str(well_gap),
        "NWL_NDIFF_GAP": str(nwell_ndiff_gap),
    })
    run_checked([klayout, "-b", "-r", str(GENERATOR)], env=env)


def run_target_drc(layout: Path, work: Path, python: str) -> dict:
    out = work / f"{layout.stem}.lyrdb"
    summary_path = work / f"{layout.stem}.json"
    run_checked([
        python,
        str(RUN_DRC),
        "--profile", "openrule1um",
        "--deck", "reference",
        "--layout", str(layout),
        "--out", str(out),
        "--summary", str(summary_path),
    ])
    return json.loads(summary_path.read_text())

def check_lambda_contract() -> None:
    layers = yamlish.load(LAYERS.read_text())
    meta = layers.get("meta") or {}
    manifest = yamlish.load((REFERENCE / "manifest.yaml").read_text())
    technology = manifest.get("technology") or {}
    rules = yamlish.load((PROFILE / "rules.yaml").read_text())
    require(rules.get("authoritative") is False, "authoritative OpenRule1um DRC is not disabled")
    authoritative_policy = rules.get("authoritative_policy") or {}
    require(authoritative_policy.get("status") == "disabled", "authoritative DRC policy status is not disabled")
    require((authoritative_policy.get("override") or {}).get("lambda_um") == 0.5,
            "authoritative DRC override slot lost lambda=0.5")
    require(run_drc.resolve_deck(PROFILE, "authoritative")[0] is None,
            "authoritative DRC unexpectedly resolves to a generated deck")
    require(run_drc.resolve_deck(PROFILE, "official")[0] is None,
            "official DRC unexpectedly resolves to an enabled deck")
    require(run_drc.resolve_deck(PROFILE, "reference")[2] == "reference",
            "reference DRC is not the available fallback")

    require(run_drc.DEFAULT_LAMBDA_UM == 0.5, "runtime lambda default is not 0.5um")
    require(float(meta.get("lambda_um")) == 0.5, "OpenRule layer metadata is not lambda=0.5um")
    require(float(technology.get("lambda_um")) == 0.5, "reference lambda metadata is not lambda=0.5um")
    require(float(technology.get("grid_um")) == float(meta.get("grid_um")), "DRC/LVS grid metadata diverges")

    ami06_meta, _, _ = run_drc.load_profile(ROOT / "profiles" / "ami06")
    require(float(ami06_meta["lambda_um"]) == 0.3, "explicit profile lambda was overridden")

    with tempfile.TemporaryDirectory(prefix="openrule1um-default-") as tmp:
        profile = Path(tmp) / "openrule1um"
        profile.mkdir()
        profile_layers = LAYERS.read_text().replace("  lambda_um: 0.5\n", "")
        (profile / "layers.yaml").write_text(profile_layers)
        default_meta, _, _ = run_drc.load_profile(profile)
        require(float(default_meta["lambda_um"]) == 0.5, "omitted lambda did not default to 0.5um")

    for deck in (
        REFERENCE / "drc.lydrc",
        REFERENCE / "lvs.lylvs",
        REFERENCE / "lvs_batch.lylvs",
    ):
        require("lambda" not in deck.read_text().lower(), f"{deck.name} unexpectedly uses lambda-scaled rules")

    lvs = manifest.get("lvs") or {}
    source_hash = hashlib.sha256((REFERENCE / "lvs.lylvs").read_bytes()).hexdigest()
    batch_hash = hashlib.sha256((REFERENCE / "lvs_batch.lylvs").read_bytes()).hexdigest()
    require(source_hash == lvs.get("upstream_source_sha256"), "local LVS source is not the pinned upstream file")
    require(batch_hash == lvs.get("adapter_sha256"), "local LVS adapter is not hash-pinned")
    require(lvs.get("upstream_dependency_commit") == "ca2da6795c4e216bae44cfd76b8fafeabff5c6b4", "upstream dependency is not pinned")
    require(lvs.get("available") is True, "Anagix-free OpenRule LVS is not enabled")
    require(lvs.get("file") == "lvs_batch.lylvs", "default OpenRule LVS adapter is not selected")
    require(lvs.get("netgen_circuit") == "auto", "OpenRule Netgen circuit policy is not automatic")
    require("AnagixLoader" not in (REFERENCE / "lvs_batch.lylvs").read_text(), "batch LVS still depends on AnagixLoader")
    drc = manifest.get("drc") or {}
    require(drc.get("top_cell_override") == "supported", "reference DRC top-cell override is not declared")
    require((drc.get("lambda_policy") or {}).get("geometry_scaling") == "none",
            "reference DRC lambda policy permits geometry scaling")
    require(lvs.get("top_cell_override") == "supported", "reference LVS top-cell override is not declared")
    lvs_lambda = lvs.get("lambda_policy") or {}
    require(lvs_lambda.get("override_required") is False, "LVS incorrectly requires a lambda geometry override")
    require(lvs_lambda.get("geometry_scaling") == "none", "LVS lambda policy permits geometry scaling")



def check_native_override_coverage() -> dict:
    """Every rule the native deck enforces must be represented in the profile.

    The portable envelope can only carry SCMOS semantic keys, so rules SCMOS
    cannot express (off-grid, marker semantics, high-poly, select-layer,
    marker-to-layer spacings) are declared as native_overrides instead.  This
    pins that claim to the deck: count the deck's own output() calls and require
    the profile to represent every one of them.
    """
    import re

    deck = (PROFILE / "reference" / "drc.lydrc").read_text()
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&quot;", '"')):
        deck = deck.replace(a, b)
    enforced = []
    for line in deck.split("\n"):
        m = re.search(
            r"^\s*([A-Za-z_0-9]+(?:\.[A-Za-z_0-9]+)?)\.(\w+)\((.*?)\)\s*\.output\(\s*\"([^\"]*)\"",
            line,
        )
        if m:
            enforced.append((m.group(1), m.group(2)))
    require(enforced, "no rules parsed out of the native deck")

    doc = yamlish.load((PROFILE / "rules.yaml").read_text())
    portable = doc.get("portable") or {}
    overrides = portable.get("native_overrides") or {}
    grid = overrides.get("grid") or {}
    grid_layers = grid.get("layers") or []
    declared = overrides.get("rules") or []

    grid_in_deck = [e for e in enforced if e[1] == "ongrid"]
    rest_in_deck = [e for e in enforced if e[1] != "ongrid"]
    require(
        len(grid_layers) == len(grid_in_deck),
        f"grid override covers {len(grid_layers)} layers but the deck checks {len(grid_in_deck)}",
    )
    require(
        len(declared) == len(rest_in_deck),
        f"profile declares {len(declared)} native overrides but the deck enforces {len(rest_in_deck)} non-grid rules",
    )
    require(
        len(grid_layers) + len(declared) == len(enforced),
        "native override coverage does not account for every rule in the deck",
    )
    # each declared override must cite a real deck line and carry the deck's value
    deck_lines = deck.split("\n")
    for item in declared:
        line = item.get("line")
        require(isinstance(line, int), f"override {item.get('id')} has no source line")
        src = deck_lines[line - 1]
        require(
            item["layer"] in src,
            f"override {item.get('id')} cites line {line} which does not mention {item['layer']}",
        )
        if item.get("value_um") is not None:
            require(
                f"{item['value_um']}".rstrip("0").rstrip(".") in src
                or f"{item['value_um']:g}" in src,
                f"override {item.get('id')} value {item['value_um']} not found on line {line}",
            )
    return {"deck_rules": len(enforced), "grid_layers": len(grid_layers), "overrides": len(declared)}


def check_profile() -> dict:
    doc = yamlish.load((PROFILE / "rules.yaml").read_text())
    portable = doc.get("portable") or {}
    require(portable.get("policy") == "scmos_lambda_envelope", "portable policy is not SCMOS envelope")
    require(float(portable.get("lambda_um")) == 0.5, "portable lambda is not 0.5um")
    # The deck's GDS is globally shrunk, so the FEOL and BEOL do not share a
    # lambda and land in different SCMOS arms.  A single scmos_variant could not
    # express that; the profile declares one entry per domain instead.
    require("scmos_variant" not in portable, "single scmos_variant should be replaced by per-domain entries")
    domains = portable.get("domains") or {}
    feol = domains.get("feol") or {}
    beol = domains.get("beol") or {}
    require(feol.get("variant") == "non_submicron", "FEOL is not the classic SCMOS arm")
    require(float(feol.get("lambda_um")) == 0.5, "FEOL lambda is not 0.5um")
    require(beol.get("variant") == "submicron", "BEOL is not the SUBM arm")
    require(abs(float(beol.get("lambda_um")) - 1.0 / 3.0) < 1e-4, "BEOL lambda is not 1/3um")
    require(beol.get("envelope") == "none", "BEOL must not layer a SCMOS envelope")
    require(
        abs(float(beol.get("lambda_um")) / float(feol.get("lambda_um")) - 2.0 / 3.0) < 1e-4,
        "lambda_BEOL / lambda_FEOL is not 2/3",
    )

    tightenings = portable.get("well_tightenings") or []
    require(len(tightenings) == 2, "portable envelope must declare exactly two well tightenings")
    by_id = {item.get("id"): item for item in tightenings}
    require(by_id["OR1-WELL-SPACE"]["base_um"] == 4.5, "wrong SCMOS well spacing base")
    require(by_id["OR1-WELL-SPACE"]["value_um"] == 5.0, "wrong target well spacing tightening")
    require(by_id["OR1-WELL-NDIFF"]["base_um"] == 2.5, "wrong SCMOS NWL-NDIFF base")
    require(by_id["OR1-WELL-NDIFF"]["value_um"] == 3.0, "wrong target NWL-NDIFF tightening")

    beol = portable.get("beol") or {}
    require(beol.get("policy") == "native_override", "BEOL is not native override")
    beol_rules = beol.get("rules") or []
    require(len(beol_rules) == 14, "portable BEOL override is incomplete")
    nominal = beol.get("nominal_geometry") or {}
    require(nominal.get("contact_cut_um") == 1.0, "contact nominal geometry missing")
    require(nominal.get("via1_cut_um") == 1.0, "via1 nominal geometry missing")
    require(nominal.get("via2_cut_um") == 1.0, "via2 nominal geometry missing")
    legality = portable.get("legality") or {}
    require(legality.get("upstream_basic_gds") == "optional_reference_input", "legality contract hides optional reference GDS")
    return portable


def print_efficiency(portable: dict) -> None:
    # (name, SCMOS multiplier, target direct threshold)
    feol_contact = [
        ("NWL width", 10, 4.0),
        ("NWL spacing", 9, 5.0),
        ("NWL-NDIFF spacing", 5, 3.0),
        ("DIFF width", 3, 1.0),
        ("DIFF spacing", 3, 1.5),
        ("POL width", 2, 1.0),
        ("POL spacing", 2, 1.0),
        ("POL-DIFF spacing", 1, 0.5),
        ("POL gate extension", 2, 1.0),
        ("Parea width", 2, 0.5),
        ("CNT cut nominal", 2, 1.0),
        ("Dcont marker spacing", 2, 1.0),
        ("CNT-DIFF enclosure", 1, 0.5),
        ("CNT-M1 enclosure", 1, 0.5),
    ]
    beol = [
        ("M1 width", 3, 1.0),
        ("M1 spacing", 2, 1.0),
        ("V1 spacing", 3, 0.5),
        ("M2 width", 3, 1.0),
        ("M2 spacing", 3, 1.0),
        ("V2 spacing", 3, 0.5),
        ("M3 width", 6, 1.0),
        ("M3 spacing", 4, 1.0),
    ]
    tightening_ratios = [
        ("NWL spacing after tightening", 5.0 / 5.0),
        ("NWL-NDIFF after tightening", 3.0 / 3.0),
    ]

    ratios = [(name, multiplier * 0.5 / target) for name, multiplier, target in feol_contact]
    native_ratios = [(name, 1.0) for name, _, _ in beol]
    beol_ratios = [(name, multiplier * 0.5 / target) for name, multiplier, target in beol]
    print("[portable] efficiency FEOL/contact SCMOS(lambda=.5) before target tightenings:")
    for name, ratio in ratios:
        print(f"  {name:<36} {ratio:.3f}")
    print("[portable] efficiency target well tightenings:")
    for name, ratio in tightening_ratios:
        print(f"  {name:<36} {ratio:.3f}")
    print("[portable] efficiency BEOL before native override:")
    for name, ratio in beol_ratios:
        print(f"  {name:<36} {ratio:.3f}")
    print("[portable] efficiency BEOL after native override: ratio=1.000 for all native rules")
    print(
        "[portable] efficiency bounds: "
        f"FEOL/contact={min(r for _, r in ratios):.3f}..{max(r for _, r in ratios):.3f}, "
        f"tightened-well={min(r for _, r in tightening_ratios):.3f}..{max(r for _, r in tightening_ratios):.3f}, "
        f"BEOL SCMOS={min(r for _, r in beol_ratios):.3f}..{max(r for _, r in beol_ratios):.3f}, "
        f"BEOL native={min(r for _, r in native_ratios):.3f}..{max(r for _, r in native_ratios):.3f}"
    )
    require(max(r for _, r in beol_ratios) >= 3.0, "efficiency test did not expose conservative via/M3 SCMOS rules")
    require((portable.get("beol") or {}).get("policy") == "native_override", "efficiency must use native BEOL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klayout", default=shutil.which("klayout") or "klayout")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    portable = check_profile()
    coverage = check_native_override_coverage()
    print(
        "[portable] native override coverage: PASS "
        f"{coverage['deck_rules']} deck rules = {coverage['grid_layers']} grid + "
        f"{coverage['overrides']} overrides"
    )
    check_lambda_contract()
    print("[portable] profile + lambda DRC/LVS contract: PASS lambda=0.5um")
    print("[portable] LVS default adapter contract: PASS; Anagix-free batch adapter selected")

    with tempfile.TemporaryDirectory(prefix="openrule1um-portable-") as tmp:
        work = Path(tmp)

        canonical = work / "canonical.gds"
        make_fixture(canonical, args.klayout)
        clean = run_target_drc(canonical, work, args.python)
        require(clean.get("markers") == 0, f"canonical geometry is not target-legal: {clean}")
        print("[portable] legality canonical: PASS markers=0")

        loose_well = work / "loose_well.gds"
        make_fixture(loose_well, args.klayout, well_gap=4.5)
        loose_well_summary = run_target_drc(loose_well, work, args.python)
        require(
            loose_well_summary.get("rule", {}).get("NWL space < 5.0", 0) > 0,
            "well-spacing tightening did not reject 4.5um boundary",
        )
        print("[portable] legality negative NWL spacing: PASS")

        loose_ndiff = work / "loose_ndiff.gds"
        make_fixture(loose_ndiff, args.klayout, nwell_ndiff_gap=2.5)
        loose_ndiff_summary = run_target_drc(loose_ndiff, work, args.python)
        require(
            loose_ndiff_summary.get("rule", {}).get("NWL-Ndiff space < 3.0", 0) > 0,
            "NWL-NDIFF tightening did not reject 2.5um boundary",
        )
        print("[portable] legality negative NWL-NDIFF: PASS")

    print_efficiency(portable)
    semantics = portable.get("semantic_tests") or {}
    require("zero markers" in semantics.get("legality", ""), "legality semantics are not explicit")
    require("native BEOL" in semantics.get("efficiency", ""), "efficiency semantics are not explicit")
    require("marker" in semantics.get("semantic", ""), "marker semantics are not explicit")
    print("[portable] semantic separation: PASS")
    print("[portable] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
