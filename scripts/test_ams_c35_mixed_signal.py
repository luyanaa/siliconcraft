#!/usr/bin/env python3
"""Run C35 schematic-to-layout mixed-signal regression with estimated native RCX."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILE_DIR = ROOT / "profiles/ams_c35"
MODEL = PROFILE_DIR / "models/ams_c35.lib"
WORK = ROOT / "build/ams_c35_mixed_signal"
TOP_CELL = "ams_c35_mixed_signal"
MOS = (
    "MREF ibias ibias 0 0 c35N w=2.4 l=0.6",
    "MTAIL tail ibias 0 0 c35N w=2.4 l=0.6",
    "MLEFT ndl inp tail 0 c35N w=2.4 l=0.6",
    "MRIGHT vout inm tail 0 c35N w=2.4 l=0.6",
    "MPREF ndl ndl vdd vdd c35P w=4.8 l=0.6",
    "MPOUT vout ndl vdd vdd c35P w=4.8 l=0.6",
)
RPOLYH_LAYOUT_LENGTH_UM = 60.0
PIP_LAYOUT_AREA_UM2 = 441.0
PIP_LAYOUT_PERIMETER_UM = 84.0


def _tool(name: str) -> str:
    value = shutil.which(name)
    if value is None:
        raise RuntimeError(f"{name} is required for the C35 mixed-signal regression")
    return value


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    show_output: bool = True,
) -> str:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if output and show_output:
        print(output.rstrip(), flush=True)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{output}"
        )
    return output


def _lvs_reference() -> str:
    rpoly2 = 50.0 * 200.0 / 0.65
    rpolyh = 1204.0 * RPOLYH_LAYOUT_LENGTH_UM / 1.0
    pip = PIP_LAYOUT_AREA_UM2 * 860.0e-18
    lines = [
        "* C35 supported-core LVS view; geometry-derived passive values.",
        "* LVS PiP is area-only; the CPOLY simulation model also applies perimeter.",
        *MOS,
        f"RBIAS vdd ibias res r={rpoly2:.9g} w=0.65 l=200",
        f"RLOAD vout 0 res r={rpolyh:.9g} w=1 l={RPOLYH_LAYOUT_LENGTH_UM:g}",
        f"CPIP vout 0 cap c={pip:.9g}",
        ".end",
        "",
    ]
    return "\n".join(lines)


def _assert_layout_passives(lvs_netlist: str, pex_netlist: str) -> None:
    resistors = [
        fields
        for line in lvs_netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("r")
        and len(fields) >= 5
        and fields[3].lower() == "res"
    ]
    rpolyh = []
    for fields in resistors:
        params = {
            key.lower(): float(value)
            for key, value in (
                token.split("=", 1) for token in fields[4:] if "=" in token
            )
        }
        if math.isclose(params.get("w", math.nan), 1.0, abs_tol=1e-9) and math.isclose(
            params.get("l", math.nan),
            RPOLYH_LAYOUT_LENGTH_UM,
            abs_tol=1e-9,
        ):
            rpolyh.append(params)
    if len(rpolyh) != 1 or not math.isclose(
        rpolyh[0].get("r", math.nan),
        1204.0 * RPOLYH_LAYOUT_LENGTH_UM,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise RuntimeError(f"LVS RPOLYH geometry/value mismatch: {resistors}")

    pip_lvs = [
        fields
        for line in lvs_netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("c")
        and len(fields) >= 5
        and fields[3].lower() == "cap"
    ]
    expected_lvs_pip = PIP_LAYOUT_AREA_UM2 * 860e-18
    if len(pip_lvs) != 1 or not math.isclose(
        float(pip_lvs[0][4].split("=", 1)[1]),
        expected_lvs_pip,
        rel_tol=1e-8,
    ):
        raise RuntimeError(f"LVS PiP geometry/value mismatch: {pip_lvs}")

    pip_pex = [
        fields
        for line in pex_netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("cdev_pipcap_")
        and len(fields) >= 4
    ]
    expected_pex_pip = (
        0.00086 * PIP_LAYOUT_AREA_UM2 * 1e-12
        + 8.6e-11 * PIP_LAYOUT_PERIMETER_UM * 1e-6
    )
    if len(pip_pex) != 1 or not math.isclose(
        float(pip_pex[0][3]),
        expected_pex_pip,
        rel_tol=1e-8,
    ):
        raise RuntimeError(f"native PEX PiP geometry/value mismatch: {pip_pex}")


def _prelayout_deck(ac_path: Path, tran_path: Path) -> str:
    devices = [
        *MOS,
        "XRBias vdd ibias RPOLY2 W=0.65u L=200u",
        f"XRLoad vout 0 RPOLYH W=1u L={RPOLYH_LAYOUT_LENGTH_UM:g}u",
        f"XCPip vout 0 CPOLY AREA={PIP_LAYOUT_AREA_UM2:g}e-12 "
        f"PERI={PIP_LAYOUT_PERIMETER_UM:g}e-6",
    ]
    return _simulation_deck(devices, f".lib '{MODEL}' ams_c35", ac_path, tran_path)


def _simulation_deck(
    devices: list[str], model_line: str, ac_path: Path, tran_path: Path
) -> str:
    return "\n".join(
        (
            "* C35 current mirror and differential-pair schematic / extracted macro.",
            ".option scale=1e-6",
            ".temp 27",
            "VDD vdd 0 3.3",
            "VINP inp 0 DC 1.65 AC 1 PULSE(1.65 1.66 10n 100p 100p 250n 500n)",
            "VINM inm 0 DC 1.65 AC 0",
            *devices,
            model_line,
            ".control",
            "set noaskquit",
            "set wr_singlescale",
            "op",
            "print v(vout)",
            "print v(ndl)",
            "print v(tail)",
            "print v(ibias)",
            "print i(vdd)",
            "ac dec 80 1k 1G",
            f"wrdata '{ac_path}' vdb(vout)",
            "tran 50p 300n",
            f"wrdata '{tran_path}' v(inp) v(vout)",
            "quit",
            ".endc",
            ".end",
            "",
        )
    )


def _run_simulation(ngspice: str, label: str, deck: str) -> dict[str, object]:
    deck_path = WORK / f"{label}.spice"
    log_path = WORK / f"{label}.log"
    ac_path = WORK / f"{label}_ac.dat"
    tran_path = WORK / f"{label}_tran.dat"
    deck_path.write_text(deck)
    output = _run([ngspice, "-b", str(deck_path)], show_output=False)
    log_path.write_text(output)
    print(f"  ngspice {label}: PASS; detailed log {log_path}", flush=True)

    operating_point: dict[str, float] = {}
    for key, expression in (
        ("vout_v", r"v\(vout\)"),
        ("ndl_v", r"v\(ndl\)"),
        ("tail_v", r"v\(tail\)"),
        ("ibias_v", r"v\(ibias\)"),
        ("vdd_current_a", r"i\(vdd\)"),
    ):
        match = re.search(
            rf"{expression}\s*=\s*([-+0-9.eE]+)", output, re.IGNORECASE
        )
        if match is None:
            raise RuntimeError(f"{label} ngspice output omitted {key}:\n{output}")
        operating_point[key] = float(match.group(1))

    ac_rows = _read_numeric_rows(ac_path, 2)
    if len(ac_rows) < 2:
        raise RuntimeError(f"{label} AC analysis returned fewer than two points")
    frequencies = [row[0] for row in ac_rows]
    gain_db = [row[1] for row in ac_rows]
    midband_db = sum(gain_db[:3]) / min(3, len(gain_db))
    threshold_db = midband_db - 3.01029995664
    pole_hz = None
    for index in range(1, len(gain_db)):
        if gain_db[index] <= threshold_db < gain_db[index - 1]:
            f0, f1 = frequencies[index - 1], frequencies[index]
            d0, d1 = gain_db[index - 1], gain_db[index]
            fraction = (threshold_db - d0) / (d1 - d0)
            pole_hz = math.exp(math.log(f0) + fraction * math.log(f1 / f0))
            break
    if pole_hz is None:
        raise RuntimeError(
            f"{label} AC response has no -3 dB pole in the swept frequency range"
        )
    gain_v_per_v = 10.0 ** (midband_db / 20.0)

    transient = _read_numeric_rows(tran_path, 3)
    if len(transient) < 2:
        raise RuntimeError(f"{label} transient analysis returned fewer than two points")
    input_cross = _crossing_time(transient, 1, 1.655, 9e-9, 20e-9, rising=True)
    before = [row[2] for row in transient if row[0] < 9e-9]
    after = [row[2] for row in transient if row[0] > 200e-9]
    if not before or not after:
        raise RuntimeError(f"{label} transient omitted initial or settled output samples")
    initial = sum(before[-20:]) / min(20, len(before))
    final = sum(after[-20:]) / min(20, len(after))
    if math.isclose(initial, final, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError(f"{label} transient output did not respond to the input step")
    output_cross = _crossing_time(
        transient,
        2,
        (initial + final) / 2.0,
        input_cross,
        200e-9,
        rising=final > initial,
    )
    delay_s = output_cross - input_cross
    if delay_s <= 0:
        raise RuntimeError(f"{label} propagation delay is not positive: {delay_s:g}s")

    for key, value in operating_point.items():
        if not math.isfinite(value):
            raise RuntimeError(f"{label} operating point {key} is not finite")
    if not 0.0 < operating_point["vout_v"] < 3.3:
        raise RuntimeError(f"{label} output is not biased between the rails")
    if abs(operating_point["vdd_current_a"]) <= 0:
        raise RuntimeError(f"{label} has no measurable supply current")
    if not math.isfinite(gain_v_per_v) or gain_v_per_v <= 0:
        raise RuntimeError(f"{label} midband gain is invalid")

    return {
        "operating_point": operating_point,
        "gain_v_per_v": gain_v_per_v,
        "gain_db": midband_db,
        "pole_hz": pole_hz,
        "delay_s": delay_s,
    }


def _read_numeric_rows(path: Path, min_columns: int) -> list[list[float]]:
    rows = []
    for line in path.read_text().splitlines():
        try:
            row = [float(token) for token in line.split()]
        except ValueError:
            continue
        if len(row) >= min_columns and all(math.isfinite(value) for value in row[:min_columns]):
            rows.append(row[:min_columns])
    return rows


def _crossing_time(
    rows: list[list[float]],
    column: int,
    threshold: float,
    start: float,
    stop: float,
    *,
    rising: bool,
) -> float:
    candidates = [row for row in rows if start <= row[0] <= stop]
    for first, second in zip(candidates, candidates[1:]):
        y0, y1 = first[column], second[column]
        crossed = y0 <= threshold <= y1 if rising else y0 >= threshold >= y1
        if not crossed or y1 == y0:
            continue
        fraction = (threshold - y0) / (y1 - y0)
        return first[0] + fraction * (second[0] - first[0])
    raise RuntimeError("transient response did not cross its 50% threshold")


def _deltas(pre: dict[str, object], post: dict[str, object]) -> dict[str, object]:
    def change(before: float, after: float) -> dict[str, float | None]:
        absolute = after - before
        return {
            "pre": before,
            "post": after,
            "absolute": absolute,
            "relative_percent": absolute / before * 100.0 if before else None,
        }

    pre_op = pre["operating_point"]
    post_op = post["operating_point"]
    return {
        "operating_point": {
            key: change(value, post_op[key]) for key, value in pre_op.items()
        },
        "gain_v_per_v": change(pre["gain_v_per_v"], post["gain_v_per_v"]),
        "pole_hz": change(pre["pole_hz"], post["pole_hz"]),
        "delay_s": change(pre["delay_s"], post["delay_s"]),
    }


def main() -> int:
    klayout = _tool("klayout")
    netgen = _tool("netgen")
    ngspice = _tool("ngspice")
    if not MODEL.is_file():
        raise RuntimeError(f"C35 model library is missing: {MODEL}")
    WORK.mkdir(parents=True, exist_ok=True)
    layout_path = WORK / "ams_c35_mixed_signal.gds"
    env = dict(
        os.environ,
        AMS_C35_MIXED_SIGNAL_GDS=str(layout_path),
        SHEET_RES=json.dumps({"rp2": 50.0, "highres": 1204.0}),
        CAP_AREACAP=json.dumps({"c35_pip": 860.0}),
    )
    _run([klayout, "-b", "-r", str(ROOT / "scripts/generate_ams_c35_mixed_signal.py")], env=env)

    drc_summary_path = WORK / "drc_summary.json"
    _run(
        [
            sys.executable,
            str(ROOT / "scripts/run_drc.py"),
            "--profile",
            "ams_c35",
            "--deck",
            "reference",
            "--layout",
            str(layout_path),
            "--out",
            str(WORK / "drc_markers.gds"),
            "--summary",
            str(drc_summary_path),
            "--klayout",
            klayout,
        ],
        env=env,
    )
    drc_summary = json.loads(drc_summary_path.read_text())
    if drc_summary.get("markers") != 0:
        raise RuntimeError(f"C35 reference DRC found violations: {drc_summary}")

    schematic_lvs = WORK / "schematic_lvs.spice"
    schematic_lvs.write_text(_lvs_reference())
    lvs_output = _run(
        [
            sys.executable,
            str(ROOT / "scripts/run_lvs.py"),
            "--profile",
            "ams_c35",
            "--variant",
            "C35B4C3",
            "--layout",
            str(layout_path),
            "--top-cell",
            TOP_CELL,
            "--schematic",
            str(schematic_lvs),
            "--workdir",
            str(WORK / "lvs"),
            "--deck",
            "authoritative",
            "--klayout",
            klayout,
            "--netgen",
            netgen,
        ],
        env=env,
    )
    if "CIRCUITS MATCH UNIQUELY" not in lvs_output:
        raise RuntimeError("C35 authoritative LVS did not report a unique match")

    pex_path = WORK / "native_pex.spice"
    pex_report_path = WORK / "native_pex.json"
    _run(
        [
            sys.executable,
            str(ROOT / "scripts/run_ams_c35_pex.py"),
            "--layout",
            str(layout_path),
            "--top-cell",
            TOP_CELL,
            "--out",
            str(pex_path),
            "--report",
            str(pex_report_path),
            "--klayout",
            klayout,
        ],
        env=env,
    )
    pex_report = json.loads(pex_report_path.read_text())
    _assert_layout_passives(
        (WORK / "lvs" / "extracted_authoritative.spice").read_text(),
        pex_path.read_text(),
    )
    if (
        pex_report.get("signoff") is not False
        or pex_report.get("calibrated") is not False
        or pex_report.get("primary_backend") != "klayout_native_rcx"
        or pex_report.get("process_maturity")
        != {"level": "L2", "status": "engineering_extracted"}
    ):
        raise RuntimeError("native PEX report lost its estimated L2/non-signoff contract")
    elements = pex_report.get("elements", {})
    if (
        elements.get("resistors", 0) <= 0
        or elements.get("capacitors", 0) <= 0
        or elements.get("mosfets", 0) < len(MOS)
    ):
        raise RuntimeError("native PEX did not extract actual R, C, and all macro MOS devices")
    ac_pre = WORK / "prelayout_ac.dat"
    tran_pre = WORK / "prelayout_tran.dat"
    pre = _run_simulation(
        ngspice,
        "prelayout",
        _prelayout_deck(ac_pre, tran_pre),
    )
    pex_lines = [
        line
        for line in pex_path.read_text().splitlines()
        if line.strip().lower() != ".end"
    ]
    ac_post = WORK / "postlayout_ac.dat"
    tran_post = WORK / "postlayout_tran.dat"
    post = _run_simulation(
        ngspice,
        "postlayout",
        "\n".join(pex_lines) + "\n" + "\n".join(
            _simulation_deck([], "", ac_post, tran_post).splitlines()[1:]
        ),
    )
    deltas = _deltas(pre, post)
    result = {
        "process": "C35B4C3",
        "scope": "supported core MOS/RPOLY2/RPOLYH/PiP; VERT10 model-only separate fixture",
        "drc": drc_summary,
        "lvs": "unique_match",
        "pex": pex_report,
        "prelayout": pre,
        "postlayout": post,
        "deltas": deltas,
        "calibration_status": "estimated_uncalibrated_non_signoff",
    }
    report_path = WORK / "mixed_signal_report.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("[test_ams_c35_mixed_signal] PASS C35 schematic/layout/DRC/LVS/native-R+C-PEX/postlayout")
    print(json.dumps({"prelayout": pre, "postlayout": post, "deltas": deltas}, indent=2, sort_keys=True))
    print(f"  report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
