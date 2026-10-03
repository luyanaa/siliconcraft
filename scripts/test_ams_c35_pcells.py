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
variants = {{}}
for name, spec in profile.pcells.items():
    params = spec.get("parameters", {{}})
    defaults = {{
        key: value.get("default")
        for key, value in params.items()
        if isinstance(value, dict) and "default" in value
    }}
    if spec.get("kind") == "via":
        defaults = {{"rows": 2, "columns": 2}}
    variants[name] = defaults
logical_layers = tuple(
    name for name, spec in profile.layers.items() if spec.get("gds")
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
    for logical in ("elec", "highres"):
        if out[name][logical]:
            box = cell.bbox(layout.layer(profile.layer_info(logical)))
            out[name][f"bbox_{{logical}}"] = [
                box.left * layout.dbu,
                box.bottom * layout.dbu,
                box.right * layout.dbu,
                box.top * layout.dbu,
            ]
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
    required = {
        "nmos", "pmos", "nmosm", "pmosm", "ntap", "ptap",
        "via12", "via23", "via34", "cap_pip",
        "rp2", "rph", "rdiffn", "rdiffp", "rnwell",
        "diode_np", "diode_pn", "diode_nw",
    }
    if set(data) != required:
        raise AssertionError(f"unexpected PCell set: {sorted(data)}")

    def require(cell: str, *layers: str) -> None:
        for layer in layers:
            if data[cell][layer] <= 0:
                raise AssertionError(f"{cell}: expected geometry on {layer}")

    require("nmos", "active", "poly", "nselect", "cc", "metal1")
    if data["nmos"]["nwell"] or data["nmos"]["midox"]:
        raise AssertionError("nmos: unexpected well or MIDOX")
    require("pmos", "active", "poly", "pselect", "nwell", "cc", "metal1")
    require("nmosm", "active", "poly", "nselect", "midox", "cc", "metal1")
    require("pmosm", "active", "poly", "pselect", "nwell", "midox", "cc", "metal1")
    require("ntap", "active", "nselect", "nwell", "cc", "metal1")
    require("ptap", "active", "pselect", "cc", "metal1")
    if data["ptap"]["nwell"]:
        raise AssertionError("ptap: unexpected nwell")
    require("via12", "via", "metal1", "metal2")
    require("via23", "via2", "metal2", "metal3")
    require("via34", "via3", "metal3", "metal4")
    require("cap_pip", "poly", "elec", "cc", "metal1")
    require("rp2", "elec", "res_id", "restdm", "cc", "metal1")
    require("rph", "elec", "highres", "pselect", "cc", "metal1")
    elec_box = data["rph"]["bbox_elec"]
    highres_box = data["rph"]["bbox_highres"]
    enclosure = [
        round(elec_box[0] - highres_box[0], 3),
        round(elec_box[1] - highres_box[1], 3),
        round(highres_box[2] - elec_box[2], 3),
        round(highres_box[3] - elec_box[3], 3),
    ]
    if enclosure != [3.0, 3.0, 3.0, 3.0]:
        raise AssertionError(f"rph: expected 3um HRES enclosure, got {enclosure}")
    require("rdiffn", "active", "nselect", "res_id", "restdm", "cc", "metal1")
    require("rdiffp", "active", "pselect", "res_id", "restdm", "cc", "metal1")
    require("rnwell", "nwell", "tubdef", "restdm", "active", "nselect", "cc", "metal1")
    require("diode_np", "active", "nselect", "dio_id", "cc", "metal1")
    require(
        "diode_pn", "active", "pselect", "nwell", "nselect",
        "dio_id", "cc", "metal1",
    )
    require("diode_nw", "nwell", "active", "nselect", "dio_id", "cc", "metal1")
    if data["diode_np"]["nwell"] or data["diode_nw"]["pselect"]:
        raise AssertionError("diode PCells: unexpected well or implant geometry")
    print("AMS C35 KLayout PCells: PASS (18 variants, including MIDOX, passives, diodes)")


if __name__ == "__main__":
    main()
