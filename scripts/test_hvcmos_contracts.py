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
if mode in ("well_bad", "well_pass"):
    box("deep_nwell", 1.0, 1.0, 10.0, 10.0)
    offset = 0.5 if mode == "well_bad" else 2.0
    box("pwell", offset, offset, 11.0 - offset, 11.0 - offset)

if mode in ("device", "drift"):
    # A single marker-derived nMOS.  No foundry contacts are assumed: the
    # extractor must still emit the provisional xh*Nhv identity.
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
    for mode in ("bad", "pass", "well_bad", "well_pass", "device", "drift"):
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
    print(f"{name}: DRC voltage policy + HV LVS + substrate hook PASS")


def main() -> int:
    klayout = shutil.which("klayout")
    if not klayout:
        raise SystemExit("klayout not found; run this test inside the KLayout environment")
    with tempfile.TemporaryDirectory(prefix="siliconcraft-hvcmos-") as tmp:
        work = Path(tmp)
        for name in ("xh035", "xh018"):
            check_profile(name, klayout, work)
    print("HVCMOS contract checks: PASS (xh035, xh018)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
