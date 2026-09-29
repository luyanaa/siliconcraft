#!/usr/bin/env python3
"""Run static, KLayout DRC, and authoritative LVS HVCMOS contract checks.

This intentionally exercises the provisional X-FAB logical map, not a foundry
stream.  Run inside the KLayout environment, for example:

  nix develop ~/Documents/librelane --command python3 scripts/test_hvcmos_contracts.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_drc  # noqa: E402
import run_lvs  # noqa: E402
from common.process_ir import load_process  # noqa: E402


PROBE = r'''
import json, os, pya

profile = json.loads(os.environ["HVCMOS_PROFILE"])
mode = os.environ["HVCMOS_MODE"]
out_path = os.environ["HVCMOS_GDS"]
ly = pya.Layout()
ly.dbu = 0.001
cell = ly.create_cell("TOP")

def layer(name):
    gds, datatype = profile[name]
    return ly.layer(pya.LayerInfo(int(gds), int(datatype)))

def box(name, x1, y1, x2, y2):
    scale = 1000.0
    cell.shapes(layer(name)).insert(pya.Box(
        int(round(x1 * scale)), int(round(y1 * scale)),
        int(round(x2 * scale)), int(round(y2 * scale))))

def text(name, x, y):
    idx = ly.layer(pya.LayerInfo(64, 0))
    cell.shapes(idx).insert(pya.Text(name, pya.Trans(pya.Point(int(round(x * 1000)), int(round(y * 1000))))))

if mode in ("bad", "pass"):
    # HV metal is marker-classified; LV metal is label-classified.  The bad
    # case is below the provisional 8lambda LV<->HV policy.
    box("metal1", 1.0, 1.0, 3.0, 2.0)
    box("hv_n_marker", 0.5, 0.5, 3.5, 2.5)
    box("metal1", 3.4 if mode == "bad" else 5.2, 1.0,
        5.4 if mode == "bad" else 7.2, 2.0)
    text("HV:VHV", 2.0, 1.5)
    text("LV:VLV", 4.4 if mode == "bad" else 6.2, 1.5)
if mode == "authority":
    gap = 0.47 if profile["metal1"][0] == 140 else 0.25
    box("metal1", 1.0, 1.0, 3.0, 2.0)
    box("hv_n_marker", 0.5, 0.5, 3.5, 2.5)
    box("metal1", 3.0 + gap, 1.0, 5.0 + gap, 2.0)
    text("HV:VHV", 2.0, 1.5)
    text("LV:VLV", 4.0 + gap, 1.5)
if mode == "unknown":
    box("metal1", 1.0, 1.0, 3.0, 2.0)
if mode in ("well_bad", "well_pass"):
    box("deep_nwell", 1.0, 1.0, 10.0, 10.0)
    offset = 0.5 if mode == "well_bad" else 2.0
    box("pwell", offset, offset, 11.0 - offset, 11.0 - offset)

if mode in ("device", "drift"):
    # A single marker-derived nMOS.  No foundry contacts are assumed: the
    # device case emits xh*Nhv; drift adds the xh*Nldmos identity.
    box("active", 10.0, 1.0, 20.0, 4.0)
    box("nselect", 10.0, 1.0, 20.0, 4.0)
    box("poly", 14.5, 0.0, 15.0, 5.0)
    box("hv_n_marker", 9.0, 0.0, 21.0, 5.0)
    if mode == "drift":
        box("drift_n", 10.0, 1.0, 20.0, 4.0)
    text("HV:SOURCE", 12.0, 2.0)
    text("HV:DRAIN", 18.0, 2.0)
    text("HV:GATE", 14.75, 4.5)

ly.write(out_path)
'''

UNIT_PROBE = r'''
import os, sys, pya

sys.path.insert(0, os.environ["HVCMOS_ROOT"])
from common.drc.hvcmos import (  # noqa: E402
    _label_class,
    _potential,
    _relation_bad,
    _spacing,
    _net_groups,
    _voltage_policy,
)

assert _label_class("HV:VDD") == "hv"
assert _label_class("LV_VSS") == "lv"
assert _label_class("@POT=HV:VDD") == "hv"
assert _label_class("MYHVNET") == "unknown"
assert _potential("MYHVNET", 7) == "MYHVNET"
assert _voltage_policy({"voltage_classification": {"mode": "strict"}})[1:] == (
    False,
    True,
    "HVCMOS.VOLTAGE.UNKNOWN",
)
assert _voltage_policy({"voltage_classification": {"mode": "exploratory"}})[1:] == (
    True,
    False,
    "HVCMOS.VOLTAGE.UNKNOWN",
)
layout = pya.Layout()
layout.dbu = 1.0
top = layout.create_cell("TOP")
regions = {
    "metal1": pya.Region(pya.Box(0, 0, 10, 10)),
    "hvMarker": pya.Region(pya.Box(0, 0, 10, 10)),
}
resolve = lambda name: regions.get(name, pya.Region())
strict_groups = _net_groups(
    regions,
    resolve,
    layout,
    top,
    resolve,
    lambda _name: False,
    "N",
    1.0,
    "metal1",
    False,
)
exploratory_groups = _net_groups(
    regions,
    resolve,
    layout,
    top,
    resolve,
    lambda _name: False,
    "N",
    1.0,
    "metal1",
    True,
)
assert strict_groups["unknown"] and not strict_groups["hv"]
assert exploratory_groups["hv"] and not exploratory_groups["unknown"]


overlap_marker = pya.Region(pya.Box(0, 0, 10, 10))
overlap_target = pya.Region(pya.Box(5, 5, 15, 15))
assert _relation_bad(overlap_marker, overlap_target, "overlap").is_empty()
assert not _relation_bad(
    overlap_marker, pya.Region(pya.Box(20, 20, 30, 30)), "overlap"
).is_empty()

class Report:
    def __init__(self):
        self.items = []

    def item(self, region, rule_id, message):
        if not region.is_empty():
            self.items.append((region, rule_id, message))

left = pya.Region(pya.Box(0, 0, 10, 10))
left += pya.Region(pya.Box(12, 0, 22, 10))
report = Report()
_spacing(report, left, pya.Region(pya.Box(40, 0, 50, 10)), 3.0, "far", "far", 1.0)
assert not report.items, report.items
_spacing(report, left, pya.Region(pya.Box(24, 0, 34, 10)), 3.0, "near", "near", 1.0)
assert [item[1] for item in report.items] == ["near"], report.items
'''


def make_gds(layermap: dict[str, list[int]], mode: str, path: Path, klayout: str) -> None:
    env = dict(os.environ)
    env.update(
        HVCMOS_PROFILE=json.dumps(layermap),
        HVCMOS_MODE=mode,
        HVCMOS_GDS=str(path),
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(PROBE)
        probe = Path(fh.name)
    try:
        result = subprocess.run(
            [klayout, "-b", "-r", str(probe)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                f"KLayout GDS probe failed for {mode}:\n"
                f"{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
            )
    finally:
        probe.unlink(missing_ok=True)

def run_unit_contracts(klayout: str) -> None:
    env = dict(os.environ)
    env["HVCMOS_ROOT"] = str(ROOT)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(UNIT_PROBE)
        probe = Path(fh.name)
    try:
        result = subprocess.run(
            [klayout, "-b", "-r", str(probe)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                "HVCMOS unit probe failed:\n"
                f"{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
            )
    finally:
        probe.unlink(missing_ok=True)


def check_profile(name: str, klayout: str, work: Path) -> None:
    process = load_process(name, ROOT)
    features = process.meta["features"]
    assert process.meta["process"] in {"XH035", "XH018"}
    assert process.rule_family == "scmos_subm"
    assert features["hvcmosAvailable"] and features["hvcmosRuleOverride"]
    assert features["deepNwellAvailable"] and features["driftAvailable"]
    assert not features["guardRingRulesAvailable"]
    assert not features["latchupRulesAvailable"]
    assert set(process.layers) >= {
        "deep_nwell", "pwell", "hv_n_marker", "hv_p_marker", "drift_n", "drift_p",
    }
    assert process.rules_doc["hvcmos"]["voltage_spacing"]
    assert process.pex_doc["substrate_extraction"]["mode"] == "active_distributed"
    assert process.pex_doc["substrate_extraction"]["ordinary_rc_allowed"] is False

    _, layermap, _ = run_drc.load_profile(process.profile_dir)
    for mode in ("bad", "pass", "well_bad", "well_pass", "device", "drift", "authority", "unknown"):
        make_gds(layermap, mode, work / f"{name}_{mode}.gds", klayout)

    bad_report = work / f"{name}_bad_markers.gds"
    bad_summary = run_drc.run_deck(
        process.profile_dir / "generated/drc/run.py",
        {"format": "klayout-pya"},
        process.meta,
        layermap,
        {**features, "rule_family": process.rule_family, "stackedVias": False},
        work / f"{name}_bad.gds",
        bad_report,
        klayout,
    )
    bad_rules = bad_summary.get("rule", {})
    hv_lv_id = f"{name.upper()}.HV.S.LV_HV"
    assert bad_rules.get(hv_lv_id, 0) > 0, (name, bad_summary)

    pass_report = work / f"{name}_pass_markers.gds"
    pass_summary = run_drc.run_deck(
        process.profile_dir / "generated/drc/run.py",
        {"format": "klayout-pya"},
        process.meta,
        layermap,
        {**features, "rule_family": process.rule_family, "stackedVias": False},
        work / f"{name}_pass.gds",
        pass_report,
        klayout,
    )
    assert pass_summary.get("rule", {}).get(hv_lv_id, 0) == 0, (name, pass_summary)
    unknown_summary = run_drc.run_deck(
        process.profile_dir / "generated/drc/run.py",
        {"format": "klayout-pya"},
        process.meta,
        layermap,
        {**features, "rule_family": process.rule_family, "stackedVias": False},
        work / f"{name}_unknown.gds",
        work / f"{name}_unknown_markers.gds",
        klayout,
    )
    unknown_id = process.rules_doc["hvcmos"]["voltage_classification"]["unknown_rule_id"]
    assert unknown_summary.get("rule", {}).get(unknown_id, 0) > 0, (
        name,
        unknown_summary,
    )
    generated_dir = process.profile_dir / "generated" / "drc"
    public_deck = generated_dir / f"{name}-public.py"
    compat_deck = generated_dir / f"{name}-scmos-compat.py"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "gen_drc.py"),
            "--profile",
            name,
            "--authority",
            "public_native",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "gen_drc.py"),
            "--profile",
            name,
            "--authority",
            "scmos_compat",
            "--output",
            str(compat_deck),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    resolved_public, public_spec, _ = run_drc.resolve_deck(
        process.profile_dir, "public-native"
    )
    resolved_compat, compat_spec, _ = run_drc.resolve_deck(
        process.profile_dir, "scmos-compat"
    )
    assert resolved_public == public_deck
    assert resolved_compat == compat_deck
    assert public_spec["rule_authority"] == "public_native"
    assert compat_spec["rule_authority"] == "scmos_compat"
    authority_features = {
        **features,
        "rule_family": process.rule_family,
        "stackedVias": False,
    }
    public_summary = run_drc.run_deck(
        public_deck,
        {"format": "klayout-pya", "rule_authority": "public_native"},
        process.meta,
        layermap,
        authority_features,
        work / f"{name}_authority.gds",
        work / f"{name}_public_markers.gds",
        klayout,
    )
    compat_summary = run_drc.run_deck(
        compat_deck,
        {"format": "klayout-pya", "rule_authority": "scmos_compat"},
        process.meta,
        layermap,
        authority_features,
        work / f"{name}_authority.gds",
        work / f"{name}_compat_markers.gds",
        klayout,
    )
    public_rules = public_summary.get("rule", {})
    compat_rules = compat_summary.get("rule", {})
    assert public_rules.get(hv_lv_id, 0) == 0, (name, public_summary)
    assert public_rules.get(f"{name.upper()}.S.M1", 0) == 0, (name, public_summary)
    assert compat_rules.get(hv_lv_id, 0) > 0, (name, compat_summary)
    assert compat_rules.get(f"{name.upper()}.S.M1", 0) > 0, (name, compat_summary)
    well_id = f"{name.upper()}.HV.WELL.1"
    well_bad = run_drc.run_deck(
        process.profile_dir / "generated/drc/run.py",
        {"format": "klayout-pya"},
        process.meta,
        layermap,
        {**features, "rule_family": process.rule_family, "stackedVias": False},
        work / f"{name}_well_bad.gds",
        work / f"{name}_well_bad_markers.gds",
        klayout,
    )
    assert well_bad.get("rule", {}).get(well_id, 0) > 0, (name, well_bad)
    well_pass = run_drc.run_deck(
        process.profile_dir / "generated/drc/run.py",
        {"format": "klayout-pya"},
        process.meta,
        layermap,
        {**features, "rule_family": process.rule_family, "stackedVias": False},
        work / f"{name}_well_pass.gds",
        work / f"{name}_well_pass_markers.gds",
        klayout,
    )
    assert well_pass.get("rule", {}).get(well_id, 0) == 0, (name, well_pass)

    lvs_work = work / f"{name}_lvs"
    lvs_summary, spice_path = run_lvs.extract(
        process.profile_dir,
        work / f"{name}_device.gds",
        "authoritative",
        lvs_work,
        klayout,
    )
    spice = spice_path.read_text()
    assert lvs_summary.get("devices", {}).get("nmos_hv", 0) >= 1, (name, lvs_summary, spice)
    assert f"{name}Nhv" in spice, (name, spice)
    reference_summary, reference_spice_path = run_lvs.extract(
        process.profile_dir,
        work / f"{name}_device.gds",
        "reference",
        lvs_work / "reference",
        klayout,
    )
    assert reference_summary.get("devices", {}).get("nmos_hv", 0) >= 1, (
        name,
        reference_summary,
        reference_spice_path.read_text(),
    )
    drift_summary, drift_spice_path = run_lvs.extract(
        process.profile_dir,
        work / f"{name}_drift.gds",
        "authoritative",
        lvs_work / "drift",
        klayout,
    )
    assert drift_summary.get("devices", {}).get("nldmos", 0) >= 1, (
        name,
        drift_summary,
        drift_spice_path.read_text(),
    )
    assert f"{name}Nldmos" in drift_spice_path.read_text(), (name, drift_spice_path.read_text())
    print(f"{name}: DRC voltage policy + HV LVS + substrate hook PASS")


def main() -> int:
    klayout = shutil.which("klayout")
    if not klayout:
        raise SystemExit("klayout not found; run this test inside the KLayout environment")
    run_unit_contracts(klayout)
    with tempfile.TemporaryDirectory(prefix="siliconcraft-hvcmos-") as tmp:
        work = Path(tmp)
        for name in ("xh035", "xh018"):
            check_profile(name, klayout, work)
    print("HVCMOS contract checks: PASS (xh035, xh018)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
