#!/usr/bin/env python3
"""Round-trip the MOS PCell through KLayout and check nf/m semantics."""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.process_ir import load_process  # noqa: E402


def find_klayout(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.environ.get("KLAYOUT"):
        return os.environ["KLAYOUT"]
    found = shutil.which("klayout")
    if found:
        return found
    matches = sorted(glob.glob("/nix/store/*klayout*/bin/klayout"))
    if matches:
        return matches[-1]
    raise SystemExit("klayout not found; set KLAYOUT or install KLayout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="ami06")
    parser.add_argument("--klayout")
    args = parser.parse_args()
    process = load_process(args.profile, ROOT)
    for device_name in ("nmos", "pmos"):
        spec = process.pcells.get(device_name) or {}
        parameters = spec.get("parameters") or {}
        assert "nf" in parameters and "m" in parameters
        assert "fingers" not in parameters
        assert spec.get("canonical_device") in {"nmos_core", "pmos_core"}
    klayout = find_klayout(args.klayout)

    with tempfile.TemporaryDirectory(prefix="siliconcraft-pcell-") as tmp:
        workdir = Path(tmp)
        script = workdir / "roundtrip.py"
        output = workdir / f"{args.profile}_mos_roundtrip.gds"
        script.write_text(
            textwrap.dedent(
                """
                import os
                import sys
                import pya

                root = os.environ["SILICONCRAFT_ROOT"]
                sys.path.insert(0, root)
                from common.pcells.scmos import Profile, register_profile

                profile_name = os.environ["SILICONCRAFT_PROFILE"]
                profile_dir = os.path.join(root, "profiles", profile_name)
                profile = Profile(profile_dir)
                library_name = "siliconcraft_" + profile_name
                register_profile(profile_dir, library_name)

                layout = pya.Layout()
                layout.dbu = 0.001
                top = layout.create_cell("roundtrip_top")
                params = {"nf": 2, "m": 1, "w_um": 1.5, "l_um": 0.6}
                one = layout.create_cell("nmos", library_name, params)
                multiplied = layout.create_cell(
                    "nmos",
                    library_name,
                    dict(params, m=3),
                )
                more_fingers = layout.create_cell(
                    "nmos",
                    library_name,
                    dict(params, nf=3),
                )
                if one is None or multiplied is None or more_fingers is None:
                    raise RuntimeError("KLayout did not instantiate the MOS PCell")
                top.insert(pya.CellInstArray(one.cell_index(), pya.Trans(0, 0)))
                top.insert(pya.CellInstArray(multiplied.cell_index(), pya.Trans(100000, 0)))
                top.insert(pya.CellInstArray(more_fingers.cell_index(), pya.Trans(200000, 0)))

                if one.bbox() != multiplied.bbox():
                    raise RuntimeError("m changed one-instance PCell geometry")
                if one.bbox() == more_fingers.bbox():
                    raise RuntimeError("nf did not change PCell geometry")

                output = os.environ["SILICONCRAFT_PCell_OUTPUT"]
                layout.write(output)
                roundtrip = pya.Layout()
                roundtrip.read(output)
                for name in (one.name, multiplied.name, more_fingers.name):
                    if roundtrip.cell(name) is None:
                        raise RuntimeError("round-trip lost " + name)
                print("PCell nf/m round-trip: PASS")
                """
            ).strip()
            + "\n"
        )
        env = dict(
            os.environ,
            SILICONCRAFT_ROOT=str(ROOT),
            SILICONCRAFT_PROFILE=args.profile,
            SILICONCRAFT_PCell_OUTPUT=str(output),
        )
        proc = subprocess.run(
            [klayout, "-b", "-r", str(script)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(proc.stdout + proc.stderr)
        print(proc.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
