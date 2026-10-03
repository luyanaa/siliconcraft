#!/usr/bin/env python3
"""Exercise the public C35 typical, worst-speed, and worst-power MOS cards."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "profiles" / "ams_c35" / "models" / "ams_c35.lib"
CORNERS = ("ams_c35", "ams_c35_ws", "ams_c35_wp")
VDD = 3.3
BIAS = 1.65


def _run(ngspice: str, deck: str, output: Path, workdir: Path) -> list[list[float]]:
    deck_path = workdir / f"{output.stem}.cir"
    log_path = workdir / f"{output.stem}.log"
    deck_path.write_text(deck)
    result = subprocess.run(
        [ngspice, "-b", "-o", str(log_path), str(deck_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    log = log_path.read_text(errors="replace") if log_path.exists() else result.stdout + result.stderr
    if result.returncode != 0 or "Error:" in log:
        raise AssertionError(f"ngspice failed for {output.stem}:\n{log[-4000:]}")
    if not output.exists():
        raise AssertionError(f"ngspice did not write {output}")
    rows = []
    for line in output.read_text().splitlines():
        try:
            row = [float(value) for value in line.split()]
        except ValueError:
            continue
        if len(row) >= 2 and all(math.isfinite(value) for value in row):
            rows.append(row)
    if len(rows) < 10:
        raise AssertionError(f"{output.stem}: expected a numeric sweep, got {len(rows)} rows")
    return rows


def _dc_deck(corner: str, polarity: str, sweep: str, output: Path) -> str:
    model = "c35N" if polarity == "n" else "c35P"
    body = "0" if polarity == "n" else "vdd"
    source = "0" if polarity == "n" else "vdd"
    if sweep == "idvd":
        gate = VDD if polarity == "n" else 0.0
        start, stop, step = (0.0, VDD, 0.1) if polarity == "n" else (VDD, 0.0, -0.1)
        control = f"dc VDS {start:g} {stop:g} {step:g}"
    else:
        start, stop, step = (0.0, VDD, 0.01) if polarity == "n" else (VDD, 0.0, -0.01)
        gate = start
        control = f"dc VGS {start:g} {stop:g} {step:g}"
    drain_voltage = VDD if sweep == "idvg" and polarity == "n" else 0.0 if sweep == "idvg" else start
    return f"""* C35 {corner} {polarity} {sweep}
.lib '{MODEL}' {corner}
VDD vdd 0 {VDD:g}
VDS d 0 {drain_voltage:g}
VGS g 0 {gate:g}
M1 d g {source} {body} {model} W=10u L=0.6u
.control
set noaskquit
set wr_singlescale
set wr_vecnames
{control}
let id = -i(VDS)
wrdata '{output}' id
quit
.endc
.end
"""


def _crossings(rows: list[list[float]], column: int, threshold: float, rising: bool) -> list[float]:
    result = []
    for previous, current in zip(rows, rows[1:]):
        before, after = previous[column], current[column]
        crossed = before < threshold <= after if rising else before > threshold >= after
        if crossed:
            fraction = (threshold - before) / (after - before)
            result.append(previous[0] + fraction * (current[0] - previous[0]))
    return result


def _delay_deck(corner: str, output: Path) -> str:
    return f"""* C35 {corner} inverter propagation delay
.lib '{MODEL}' {corner}
VDD vdd 0 {VDD:g}
VIN in 0 PULSE(0 {VDD:g} 1n 20p 20p 2n 4n)
MN out in 0 0 c35N W=10u L=0.6u
MP out in vdd vdd c35P W=20u L=0.6u
CLOAD out 0 10f
.control
set noaskquit
set wr_singlescale
set wr_vecnames
tran 5p 8n
wrdata '{output}' v(in) v(out)
quit
.endc
.end
"""


def _curve_metrics(
    rows: list[list[float]], polarity: str, sweep: str
) -> tuple[list[tuple[float, float]], float | None]:
    points = []
    for row in rows:
        x, current = row[0], row[-1]
        if sweep == "idvd":
            vds = x if polarity == "n" else VDD - x
            points.append((vds, abs(current)))
        else:
            vgs = x if polarity == "n" else VDD - x
            points.append((vgs, abs(current)))
    points.sort()
    if any(current < 0 or not math.isfinite(current) for _, current in points):
        raise AssertionError(f"{polarity} {sweep}: invalid current values")
    currents = [current for _, current in points]
    if any(right + 1e-12 < left for left, right in zip(currents, currents[1:])):
        raise AssertionError(f"{polarity} {sweep}: current is not monotonic")
    if points[-1][1] <= 0:
        raise AssertionError(f"{polarity} {sweep}: model produced no on-current")
    if sweep == "idvd":
        return points, None
    index = min(range(len(points)), key=lambda i: abs(points[i][0] - BIAS))
    if index == 0 or index == len(points) - 1:
        raise AssertionError(f"{polarity} gm bias lies outside the sweep")
    left, right = points[index - 1], points[index + 1]
    gm = (right[1] - left[1]) / (right[0] - left[0])
    if not math.isfinite(gm) or gm <= 0:
        raise AssertionError(f"{polarity} gm at {BIAS:g}V is not positive")
    return points, gm


def main() -> int:
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        raise SystemExit("ngspice is required for the public C35 model regression")
    if not MODEL.is_file():
        raise SystemExit(f"missing C35 model library: {MODEL}")

    results = {}
    with tempfile.TemporaryDirectory(prefix="ams-c35-models-") as directory:
        workdir = Path(directory)
        for corner in CORNERS:
            metrics = {}
            for polarity in ("n", "p"):
                for sweep in ("idvd", "idvg"):
                    output = workdir / f"{corner}-{polarity}-{sweep}.dat"
                    rows = _run(
                        ngspice,
                        _dc_deck(corner, polarity, sweep, output),
                        output,
                        workdir,
                    )
                    points, gm = _curve_metrics(rows, polarity, sweep)
                    if sweep == "idvd":
                        metrics[f"{polarity}_id_vd"] = {
                            "low_vds_magnitude_a": points[1][1],
                            "high_vds_magnitude_a": points[-1][1],
                            "samples": len(points),
                        }
                    else:
                        metrics[f"{polarity}_gm_siemens"] = gm
                        metrics[f"{polarity}_id_at_overdrive_1v65_a"] = points[
                            min(range(len(points)), key=lambda i: abs(points[i][0] - BIAS))
                        ][1]

            output = workdir / f"{corner}-delay.dat"
            rows = _run(ngspice, _delay_deck(corner, output), output, workdir)
            input_rises = _crossings(rows, 1, VDD / 2, True)
            input_falls = _crossings(rows, 1, VDD / 2, False)
            output_falls = _crossings(rows, 2, VDD / 2, False)
            output_rises = _crossings(rows, 2, VDD / 2, True)
            if not input_rises or not input_falls or not output_falls or not output_rises:
                raise AssertionError(f"{corner}: inverter did not produce both delay crossings")
            t_phl = next((t - input_rises[0] for t in output_falls if t > input_rises[0]), None)
            t_plh = next((t - input_falls[0] for t in output_rises if t > input_falls[0]), None)
            if t_phl is None or t_plh is None or min(t_phl, t_plh) <= 0:
                raise AssertionError(f"{corner}: invalid inverter propagation delay")
            metrics["delay_s"] = {"tphl": t_phl, "tplh": t_plh}
            results[corner] = metrics

    typical = results["ams_c35"]
    worst_speed = results["ams_c35_ws"]
    worst_power = results["ams_c35_wp"]
    for polarity in ("n", "p"):
        current_key = f"{polarity}_id_vd"
        gm_key = f"{polarity}_gm_siemens"
        if worst_speed[current_key]["high_vds_magnitude_a"] >= typical[current_key]["high_vds_magnitude_a"]:
            raise AssertionError(f"worst-speed {polarity} high-VDS current must be below typical")
        if worst_power[current_key]["high_vds_magnitude_a"] <= typical[current_key]["high_vds_magnitude_a"]:
            raise AssertionError(f"worst-power {polarity} high-VDS current must exceed typical")
        if worst_speed[gm_key] >= typical[gm_key]:
            raise AssertionError(f"worst-speed {polarity} gm must be below typical")
        if worst_power[gm_key] <= typical[gm_key]:
            raise AssertionError(f"worst-power {polarity} gm must exceed typical")
    for transition in ("tphl", "tplh"):
        if worst_speed["delay_s"][transition] <= typical["delay_s"][transition]:
            raise AssertionError(f"worst-speed {transition} must exceed typical")
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
