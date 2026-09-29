#!/usr/bin/env python3
"""Validate the profile-driven AMS C35 analog PCells under KLayout."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "profiles" / "ams_c35"

PROBE = f"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
import pya
from common.pcells.scmos import Profile, register_profile

profile_dir = Path({str(PROFILE_DIR)!r})
profile = Profile(profile_dir)
library_name = "siliconcraft_ams_c35_test"
register_profile(profile_dir, library_name)
layout = pya.Layout()
layout.dbu = 0.001
variants = {{
    "nmos": {{"nf": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}},
    "pmos": {{"nf": 1, "m": 1, "w_um": 1.5, "l_um": 0.6}},
    "ntap": {{"rows": 1, "columns": 1}},
    "ptap": {{"rows": 1, "columns": 1}},
    "via12": {{"rows": 2, "columns": 2}},
    "via23": {{"rows": 2, "columns": 2}},
    "via34": {{"rows": 2, "columns": 2}},
    "cap_elec": {{"width_um": 3.0, "height_um": 3.0}},
}}
logical_layers = (
    "nwell", "active", "poly", "elec", "nselect", "pselect", "cc",
    "metal1", "via", "metal2", "via2", "metal3", "via3", "metal4",
)
out = {{}}
for name, params in variants.items():
    cell = layout.create_cell(name, library_name, params)
    if cell is None:
        raise RuntimeError(f"failed to create {{name}}")
    out[name] = {{}}
    for logical in logical_layers:
        layer = layout.layer(profile.layer_info(logical))
        out[name][logical] = cell.shapes(layer).size()
with open(os.environ["AMS_C35_PCELL_JSON"], "w") as fh:
    json.dump(out, fh)
"""


def run() -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(PROBE)
        probe = Path(fh.name)
    fd, json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    env = dict(os.environ)
    env["AMS_C35_PCELL_JSON"] = json_path
    try:
        command = (
            f"cd {ROOT} && klayout -b -r {probe}"
        )
        result = subprocess.run(
            ["nix", "develop", str(Path.home() / "Documents" / "librelane"),
             "--command", "bash", "-c", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        if result.returncode != 0:
            raise AssertionError(
                "KLayout probe failed:\n"
                + result.stdout[-2000:]
                + result.stderr[-2000:]
            )
        return json.loads(Path(json_path).read_text())
    finally:
        probe.unlink(missing_ok=True)
        Path(json_path).unlink(missing_ok=True)


def main() -> None:
    data = run()
    required = {"nmos", "pmos", "ntap", "ptap", "via12", "via23", "via34", "cap_elec"}
    if set(data) != required:
        raise AssertionError(f"unexpected PCell set: {sorted(data)}")

    def require(cell: str, *layers: str) -> None:
        for layer in layers:
            if data[cell][layer] <= 0:
                raise AssertionError(f"{cell}: expected geometry on {layer}")

    require("nmos", "active", "poly", "nselect", "cc", "metal1")
    if data["nmos"]["nwell"]:
        raise AssertionError("nmos: unexpected nwell")
    require("pmos", "active", "poly", "pselect", "nwell", "cc", "metal1")
    require("ntap", "active", "nselect", "nwell", "cc", "metal1")
    require("ptap", "active", "pselect", "cc", "metal1")
    if data["ptap"]["nwell"]:
        raise AssertionError("ptap: unexpected nwell")
    require("via12", "via", "metal1", "metal2")
    require("via23", "via2", "metal2", "metal3")
    require("via34", "via3", "metal3", "metal4")
    require("cap_elec", "poly", "elec")
    print("AMS C35 KLayout PCells: PASS (8 variants, 4-metal path checked)")


if __name__ == "__main__":
    main()
