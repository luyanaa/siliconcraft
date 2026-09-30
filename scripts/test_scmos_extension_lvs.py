#!/usr/bin/env python3
"""Exercise source-backed SCMOS extension LVS recognition in KLayout."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import run_lvs  # noqa: E402


PROBE = r'''
import os
import pya

mode = os.environ["SCMOS_EXTENSION_MODE"]
out_path = os.environ["SCMOS_EXTENSION_GDS"]
layout = pya.Layout()
layout.dbu = 0.001
top = layout.create_cell("TOP")

def box(layer, x1, y1, x2, y2):
    top.shapes(layout.layer(layer, 0)).insert(
        pya.Box(int(x1 * 1000), int(y1 * 1000), int(x2 * 1000), int(y2 * 1000))
    )

if mode == "ami16_npn":
    box(42, 0, 0, 100, 100)       # nwell
    box(58, 20, 20, 60, 60)       # pbase
    box(43, 30, 30, 40, 40)       # emitter active
    box(45, 30, 30, 40, 40)       # emitter select
    box(43, 70, 70, 80, 80)       # collector active
    box(43, 45, 45, 50, 50)       # base tap active
    box(44, 45, 45, 50, 50)       # base tap select
    contacts = ((33, 33, 37, 37), (73, 73, 77, 77), (46, 46, 49, 49))
    for x1, y1, x2, y2 in contacts:
        box(48, x1, y1, x2, y2)    # contact cut
        box(49, x1 - 1, y1 - 1, x2 + 1, y2 + 1)
elif mode == "hp06_lc":
    box(59, 0, 0, 40, 40)         # cwell
    box(43, 15, 5, 45, 35)        # active crossing cwell edge
    box(46, 20, 10, 30, 30)       # poly over cap-well diffusion
    box(48, 23, 14, 27, 18)       # contact cut
    box(49, 22, 13, 28, 19)        # metal1
else:
    raise RuntimeError(mode)

layout.write(out_path)
'''


def make_gds(klayout: str, mode: str, path: Path) -> None:
    env = dict(os.environ)
    env.update(SCMOS_EXTENSION_MODE=mode, SCMOS_EXTENSION_GDS=str(path))
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(PROBE)
        probe = Path(handle.name)
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
            raise AssertionError(f"KLayout probe failed for {mode}:\n{result.stdout}\n{result.stderr}")
    finally:
        probe.unlink(missing_ok=True)


def generate_lvs(profile: str) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPTS / "gen_lvs.py"), "--profile", profile],
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    klayout = shutil.which("klayout")
    if not klayout:
        raise SystemExit("klayout not found; run this test inside the KLayout environment")

    generate_lvs("ami16")
    generate_lvs("hp06")
    with tempfile.TemporaryDirectory(prefix="siliconcraft-scmos-ext-") as tmp:
        work = Path(tmp)
        npn_layout = work / "ami16_npn.gds"
        make_gds(klayout, "ami16_npn", npn_layout)
        for deck in ("authoritative", "reference"):
            summary, spice_path = run_lvs.extract(
                ROOT / "profiles" / "ami16",
                npn_layout,
                deck,
                work / f"ami16_npn_{deck}",
                klayout,
            )
            spice = spice_path.read_text()
            assert summary.get("devices", {}).get("npn") == 1, (deck, summary, spice)
            assert "Generic_NPN" in spice, (deck, spice)

        lc_layout = work / "hp06_lc.gds"
        make_gds(klayout, "hp06_lc", lc_layout)
        summary, spice_path = run_lvs.extract(
            ROOT / "profiles" / "hp06",
            lc_layout,
            "authoritative",
            work / "hp06_lc_authoritative",
            klayout,
        )
        spice = spice_path.read_text()
        assert summary.get("devices", {}).get("cap") == 1, (summary, spice)
        assert "c1 " in spice and "cap c=" in spice, spice
        assert not summary.get("warnings"), summary

    print("SCMOS extension LVS: PASS (AMI16 NPN authority/reference + HP06 LC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
