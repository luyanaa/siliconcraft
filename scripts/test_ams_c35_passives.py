#!/usr/bin/env python3
"""Check source-backed AMS C35 passive and VERT10 cards with ngspice."""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "profiles/ams_c35/models/ams_c35.lib"


def _run_fixture(
    ngspice: str,
    fixture: str,
    section: str,
    circuit: str,
    outputs: tuple[str, ...],
) -> dict[str, float]:
    deck = f"""* Independent C35 {fixture} model regression
.lib '{MODEL}' {section}
{circuit}
.end
"""
    with tempfile.TemporaryDirectory(prefix=f"ams-c35-{fixture}-") as temp_dir:
        deck_path = Path(temp_dir) / f"{fixture}.cir"
        deck_path.write_text(deck)
        result = subprocess.run(
            [ngspice, "-b", str(deck_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(
            f"ngspice {fixture} regression failed:\n{result.stdout}\n{result.stderr}"
        )
    values = {}
    for name in outputs:
        match = re.search(
            rf"{re.escape(name)}\s*=\s*([-+0-9.eE]+)",
            result.stdout,
            re.IGNORECASE,
        )
        if match is None:
            raise AssertionError(
                f"ngspice {fixture} fixture did not report {name}:\n{result.stdout}"
            )
        values[name] = float(match.group(1))
    return values


def main() -> int:
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        raise RuntimeError("ngspice is required for C35 passive-card regressions")
    if not MODEL.is_file():
        raise RuntimeError(f"generated C35 model library not found: {MODEL}")

    corners = {
        "ams_c35": (50, 0.40, 1204, 0.2022, 0.860, 0.086),
        "ams_c35_ws": (60, 0.50, 1400, 0.3000, 0.960, 0.089),
        "ams_c35_wp": (40, 0.30, 1000, 0.1000, 0.780, 0.083),
    }
    voltage, width, length = 0.1, 1e-6, 10e-6
    for section, (
        rsh,
        correction,
        rph,
        rph_correction,
        cap_area,
        cap_edge,
    ) in corners.items():
        rpoly2_values = _run_fixture(
            ngspice,
            "rpoly2",
            section,
            "VRP RP 0 1\n"
            "XRP RP 0 RPOLY2 W=1e-6 L=10e-6\n"
            ".control\nop\nprint i(VRP)\n.endc",
            ("i(vrp)",),
        )
        rpoly2 = rsh * length / (width - correction * 1e-6) + 2 * 45
        assert math.isclose(
            abs(rpoly2_values["i(vrp)"]), 1 / rpoly2, rel_tol=2e-5
        )
        print(f"[test_ams_c35_passives] PASS RPOLY2 {section}")

        rpolyh_values = _run_fixture(
            ngspice,
            "rpolyh",
            section,
            "VRH RH 0 0.1\n"
            "XRH RH 0 RPOLYH W=1e-6 L=10e-6\n"
            ".control\nop\nprint i(VRH)\n.endc",
            ("i(vrh)",),
        )
        voltage_factor = (
            1
            + 7.745e-5
            * -7.468e-4
            * width
            * (voltage / length) ** 2
            / (1 + 50 ** ((29.8e-6 - length) * 1e6))
            / (1 + 50 ** (4.8 - length / width))
        )
        rpolyh = (
            rph
            * length
            / (width - rph_correction * 1e-6)
            * voltage_factor
        )
        assert math.isclose(
            abs(rpolyh_values["i(vrh)"]), voltage / rpolyh, rel_tol=2e-5
        )
        print(f"[test_ams_c35_passives] PASS RPOLYH {section}")

        pip_values = _run_fixture(
            ngspice,
            "pip-capacitor",
            section,
            "VCP CP 0 AC 1\n"
            "XCP CP 0 CPOLY AREA=100e-12 PERI=40e-6\n"
            ".control\nac lin 1 1k 1k\nprint imag(i(VCP))\n.endc",
            ("imag(i(vcp))",),
        )
        expected_c = (cap_area * 100 + cap_edge * 40) * 1e-15
        measured_c = abs(pip_values["imag(i(vcp))"]) / (2 * math.pi * 1e3)
        assert math.isclose(measured_c, expected_c, rel_tol=2e-5)
        print(f"[test_ams_c35_passives] PASS PiP {section}")

    pip_tc1_values = _run_fixture(
        ngspice,
        "pip-tc1",
        "ams_c35",
        ".temp 127\n"
        "VCP CP 0 AC 1\n"
        "XCP CP 0 CPOLY AREA=100e-12 PERI=40e-6\n"
        ".control\nac lin 1 1k 1k\nprint imag(i(VCP))\n.endc",
        ("imag(i(vcp))",),
    )
    pip_tc1_cap = (
        corners["ams_c35"][4] * 100 + corners["ams_c35"][5] * 40
    ) * 1e-15 * (1 + 3e-5 * (127 - 27))
    measured_tc1_cap = abs(pip_tc1_values["imag(i(vcp))"]) / (
        2 * math.pi * 1e3
    )
    assert math.isclose(measured_tc1_cap, pip_tc1_cap, rel_tol=2e-5)
    print("[test_ams_c35_passives] PASS PiP TC1 at 127 C")

    vert10_values = _run_fixture(
        ngspice,
        "vert10",
        "ams_c35",
        ".temp 127\n"
        "VE E 0 1\nVB B 0 0.3\nVC C 0 0\nQ1 C B E VERT10\n"
        ".control\nop\nprint i(VB)\n.endc",
        ("i(vb)",),
    )
    vert10_current = vert10_values["i(vb)"]
    assert math.isfinite(vert10_current) and abs(vert10_current) > 1e-8
    print("[test_ams_c35_passives] PASS VERT10 typical model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


