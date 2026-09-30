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



def check_profile() -> dict:
    doc = yamlish.load((PROFILE / "rules.yaml").read_text())
    portable = doc.get("portable") or {}
    require(portable.get("policy") == "scmos_lambda_envelope", "portable policy is not SCMOS envelope")
    require(float(portable.get("lambda_um")) == 0.5, "portable lambda is not 0.5um")
    require(portable.get("scmos_variant") == "non_submicron", "unexpected SCMOS variant")

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
