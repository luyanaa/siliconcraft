#!/usr/bin/env python3
"""Regression checks for the frozen LS1u DRC/LVS reference contracts.

This is deliberately a focused contract test, not a project-wide suite.  It
runs both profile dispatchers against temporary fake external tools, so a
future deck or manifest change cannot silently bypass the selected LS1u
reference deck or re-enable unavailable authoritative/official paths.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_drc  # noqa: E402
import run_lvs  # noqa: E402
import yamlish  # noqa: E402


PROFILE = ROOT / "profiles" / "ls1u"
REFERENCE = PROFILE / "reference"


FAKE_KLAYOUT = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path

# The real runners communicate through these environment variables.  Emit a
# valid zero-marker summary for DRC and a minimal extracted netlist for LVS.
if os.environ.get("EXTRACTED"):
    Path(os.environ["EXTRACTED"]).write_text(
        "* fake LS1u extracted netlist\\n.subckt TOP a b c d\\n.ends TOP\\n"
    )
if os.environ.get("REPORT"):
    Path(os.environ["REPORT"]).touch()
print(json.dumps({"summary_available": True, "external": True,
                  "markers": 0, "rule": {}, "devices": 2, "nets": 4}))
'''


FAKE_NETGEN = r'''#!/usr/bin/env python3
print("Circuit 1: match uniquely")
print("CIRCUITS MATCH UNIQUELY")
'''


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _assert_reference_manifest() -> None:
    manifest = yamlish.load((REFERENCE / "manifest.yaml").read_text())
    assert manifest["technology"]["lambda_um"] == 0.5
    assert manifest["technology"]["grid_um"] == 0.5
    assert manifest["decision"]["layout_drc_lvs_engine"] == "klayout"
    assert manifest["drc"]["file"] == "klayout/ls1u.lydrc"
    assert manifest["lvs"]["file"] == "klayout/ls1u.lylvs"
    assert manifest["lvs"]["netgen_setup"] == "klayout/ls1u.setup.tcl"

    _, _, drc_deck = run_drc.resolve_deck(PROFILE, "reference")
    assert drc_deck == "reference"
    assert run_drc.resolve_deck(PROFILE, "authoritative")[0] is None
    assert run_drc.resolve_deck(PROFILE, "official")[0] is None

    _, _, lvs_deck = run_lvs.resolve_deck(PROFILE, "reference")
    assert lvs_deck == "lvs"
    assert run_lvs.resolve_deck(PROFILE, "authoritative")[0] is None
    assert run_lvs.resolve_deck(PROFILE, "official")[0] is None


def _check_deck_syntax() -> None:
    for xml_path in (
        REFERENCE / "klayout" / "ls1u.lydrc",
        REFERENCE / "klayout" / "ls1u.lylvs",
    ):
        ET.parse(xml_path)

    ruby = shutil.which("ruby")
    if ruby:
        with tempfile.TemporaryDirectory(prefix="ls1u-ruby-") as tmp:
            for xml_path in (
                REFERENCE / "klayout" / "ls1u.lydrc",
                REFERENCE / "klayout" / "ls1u.lylvs",
            ):
                root = ET.parse(xml_path).getroot()
                script = root.findtext("text")
                assert script
                ruby_path = Path(tmp) / f"{xml_path.stem}.rb"
                ruby_path.write_text(script)
                proc = subprocess.run(
                    [ruby, "-c", str(ruby_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert proc.returncode == 0, proc.stderr
    setup = (REFERENCE / "klayout" / "ls1u.setup.tcl").read_text()
    assert "equate class {-circuit1 n} {-circuit2 LV1UNMOS}" in setup
    assert "equate class {-circuit1 p} {-circuit2 LV1UPMOS}" in setup
    lvs_script = ET.parse(REFERENCE / "klayout" / "ls1u.lylvs").getroot().findtext("text")
    assert lvs_script
    assert "reader = RBA::NetlistSpiceReader::new" in lvs_script
    assert "target_netlist(TARGET_FILE, write_spice(" in lvs_script
    manifest = yamlish.load((REFERENCE / "manifest.yaml").read_text())
    args = manifest["lvs"]["args"]
    assert "report=$LVS_REPORT" in args


def _check_fake_drc_and_lvs() -> None:
    with tempfile.TemporaryDirectory(prefix="ls1u-contract-") as tmp:
        work = Path(tmp)
        fake_klayout = work / "fake_klayout.py"
        fake_netgen = work / "fake_netgen.py"
        _write_executable(fake_klayout, FAKE_KLAYOUT)
        _write_executable(fake_netgen, FAKE_NETGEN)
        klayout_cmd = f"{sys.executable} {fake_klayout}"
        netgen_cmd = f"{sys.executable} {fake_netgen}"

        layout = work / "empty.gds"
        schematic = work / "empty.spice"
        layout.write_bytes(b"")
        schematic.write_text(".SUBCKT empty\n.ENDS empty\n")

        drc_report = work / "drc.lyrdb"
        drc_summary = run_drc.run_deck(
            REFERENCE / "klayout" / "ls1u.lydrc",
            {"format": "klayout-drc", "args": []},
            *run_drc.load_profile(PROFILE),
            layout,
            drc_report,
            klayout_cmd,
        )
        assert drc_summary["markers"] == 0

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "run_lvs.py"),
                "--profile",
                "ls1u",
                "--deck",
                "reference",
                "--layout",
                str(layout),
                "--schematic",
                str(schematic),
                "--workdir",
                str(work / "lvs"),
                "--klayout",
                klayout_cmd,
                "--netgen",
                netgen_cmd,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "CIRCUITS MATCH UNIQUELY" in proc.stdout


def main() -> int:
    _assert_reference_manifest()
    _check_deck_syntax()
    _check_fake_drc_and_lvs()
    print("LS1u frozen DRC/LVS contract checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
