#!/usr/bin/env python3
"""Run the OpenRule1um reference LVS adapter through KLayout and Netgen."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import yamlish  # noqa: E402

PROFILE = ROOT / "profiles" / "openrule1um"
REFERENCE = PROFILE / "reference"
GENERATOR = ROOT / "common" / "tests" / "make_openrule1um_portable.py"
SCHEMATIC = ROOT / "common" / "tests" / "spice" / "openrule1um_lvs_schematic.spice"
RUN_LVS = SCRIPT_DIR / "run_lvs.py"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, env=env, check=False)


def _run_fixture(
    *,
    label: str,
    klayout: str,
    generator: Path,
    schematic_source: Path,
    expected_models: dict[str, int],
    lambda_rule: dict[str, object],
    model_ids: set[str],
    top_cell: str | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix=f"openrule1um-{label}-lvs-") as tmp:
        work = Path(tmp)
        layout = work / f"{label}.gds"
        lvs_work = work / "run"

        env = os.environ.copy()
        env["OUT"] = str(layout)
        generated = _run([klayout, "-b", "-r", str(generator)], env=env)
        if generated.returncode != 0:
            raise AssertionError(generated.stderr or generated.stdout)

        schematic = work / schematic_source.name
        shutil.copyfile(schematic_source, schematic)
        lvs_command = [
            sys.executable,
            str(RUN_LVS),
            "--profile",
            "openrule1um",
            "--deck",
            "auto",
            "--layout",
            str(layout),
            "--schematic",
            str(schematic),
            "--workdir",
            str(lvs_work),
        ]
        if top_cell:
            lvs_command.extend(["--top-cell", top_cell])
        result = _run(lvs_command)
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise AssertionError(f"{label} LVS failed:\n{output}")
        if "CIRCUITS MATCH UNIQUELY" not in output:
            raise AssertionError(f"{label} Netgen did not report a unique match:\n{output}")

        extracted = lvs_work / "extracted_reference.spice"
        text = extracted.read_text()
        device_lines = [
            line
            for line in text.splitlines()
            if line and line[0] in "MCRD" and not line.startswith("*")
        ]
        extracted_models: dict[str, int] = {}
        for line in device_lines:
            fields = line.split()
            device_type = line[0]
            model_index = {"M": 5, "C": 4, "R": 4, "D": 3}[device_type]
            if len(fields) <= model_index:
                raise AssertionError(f"extracted {device_type} device lacks a model binding: {line}")
            model_id = fields[model_index]
            if model_id not in model_ids:
                raise AssertionError(f"extracted device is not bound to a declared model: {line}")
            extracted_models[model_id] = extracted_models.get(model_id, 0) + 1

            if device_type == "M":
                match = re.search(r"\bL=([0-9.]+)U\b.*\bW=([0-9.]+)U\b", line)
                if not match:
                    raise AssertionError(f"extracted MOS lacks micron W/L: {line}")
                length_um, width_um = (float(value) for value in match.groups())
                grid_um = float(lambda_rule["grid_um"])
                if any(abs(value / grid_um - round(value / grid_um)) > 1e-9 for value in (length_um, width_um)):
                    raise AssertionError(f"extracted MOS is off lambda_rule grid: {line}")
                if length_um < float(lambda_rule["min_channel_um"]) or width_um < float(lambda_rule["min_width_um"]):
                    raise AssertionError(f"extracted MOS violates lambda_rule minima: {line}")

        if extracted_models != expected_models:
            raise AssertionError(
                f"{label} extracted model coverage differs from expected: "
                f"{extracted_models!r} != {expected_models!r}\n{text}"
            )


def main() -> int:
    klayout = shutil.which("klayout") or "klayout"
    lambda_rule = yamlish.load((PROFILE / "rules.yaml").read_text())["lambda_rule"]
    contract = yamlish.load((PROFILE / "model_contract.yaml").read_text())
    model_ids = set(contract.get("models") or {}) | set(contract.get("lvs_only_models") or {})

    _run_fixture(
        label="canonical",
        klayout=klayout,
        generator=GENERATOR,
        schematic_source=SCHEMATIC,
        expected_models={"or1_pmos": 2, "or1_nmos": 2},
        lambda_rule=lambda_rule,
        model_ids=model_ids,
        top_cell="openrule1um_portable",
    )
    _run_fixture(
        label="primitives",
        klayout=klayout,
        generator=ROOT / "common" / "tests" / "make_openrule1um_lvs_primitives.py",
        schematic_source=ROOT / "common" / "tests" / "spice" / "openrule1um_lvs_primitives.spice",
        expected_models={
            "or1_pmos": 2,
            "or1_nmos": 2,
            "poly_cap": 1,
            "lvs_cap_metal2": 1,
            "pdiff_cap": 1,
            "ndiff_cap": 1,
            "r_poly": 1,
            "r_pdiff": 1,
            "r_nwell": 1,
            "or1_diode": 1,
        },
        lambda_rule=lambda_rule,
        model_ids=model_ids,
        top_cell="openrule1um_portable",
    )

    if "AnagixLoader" in (REFERENCE / "lvs_batch.lylvs").read_text():
        raise AssertionError("default OpenRule1um LVS adapter still names AnagixLoader")

    print("OpenRule1um Anagix-free reference LVS: PASS; canonical MOS and mixed primitive fixtures (including r_pdiff and r_nwell) match uniquely")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
