#!/usr/bin/env python3
"""Smoke native C35 extraction, geometry, naming, coupling, and PiP TC1."""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_lvs  # noqa: E402
from scripts.run_ams_c35_pex import (
    DEFAULT_TOP_CELL,
    _generate_fixture,
    _native_config,
)  # noqa: E402
from yamlish import load  # noqa: E402


def _smoke_deck(netlist: str) -> tuple[str, str, float]:
    lines = netlist.splitlines()
    end = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == ".end"),
        None,
    )
    if end is None:
        raise RuntimeError("native PEX output has no .end statement")
    resistor = next(
        (
            line.split()
            for line in lines
            if line.strip()
            and line.lstrip()[0].lower() == "r"
            and not line.lstrip().startswith("*")
        ),
        None,
    )
    if resistor is None or len(resistor) != 4:
        raise RuntimeError("native PEX output has no measurable two-terminal resistor")
    name, positive, negative, raw_resistance = resistor
    resistance = float(raw_resistance)
    if not math.isfinite(resistance) or resistance <= 0:
        raise RuntimeError(f"invalid extracted resistance: {raw_resistance}")
    probe = (
        f"Vsmoke_hi {positive} 0 1\n"
        f"Vsmoke_lo {negative} 0 0\n"
        ".control\n"
        "op\n"
        f"print @{name}[i]\n"
        ".endc"
    )
    lines[end:end] = probe.splitlines()
    return "\n".join(lines) + "\n", name, resistance


def _assert_graph_nodes_resolve(netlist: str) -> None:
    lines = [line.split() for line in netlist.splitlines() if line.strip()]
    resistor_nodes = {
        node
        for fields in lines
        if fields[0].lower().startswith("r") and len(fields) >= 4
        for node in fields[1:3]
    }
    external_nodes = {"0", "SUBS"}
    if not resistor_nodes:
        raise RuntimeError("native netlist has no distributed resistor nodes")

    for fields in lines:
        name = fields[0].lower()
        terminals: list[str] = []
        if name.startswith(("crcx", "cdev_")) and len(fields) >= 4:
            terminals = fields[1:3]
        elif name.startswith("m") and len(fields) >= 5:
            terminals = fields[1:4]
            if fields[4] != "SUBS":
                terminals.append(fields[4])
        elif name.startswith("xres_") and len(fields) >= 4:
            terminals = fields[1:3]
        missing = [
            node
            for node in terminals
            if node not in external_nodes and node not in resistor_nodes
        ]
        if missing:
            raise RuntimeError(
                f"{fields[0]} references nodes absent from the R network: {missing}"
            )


def _simulate_extracted_pip_tc1(
    ngspice: str, temp: Path, capacitor_line: str, expected_tc1: float
) -> tuple[float, float]:
    fields = capacitor_line.split()
    if len(fields) < 5:
        raise RuntimeError(f"extracted PIP capacitor lacks TC1: {capacitor_line}")
    name, positive, negative, raw_capacitance = fields[:4]
    tc1_params = [token for token in fields[4:] if token.lower().startswith("tc1=")]
    if len(tc1_params) != 1:
        raise RuntimeError(f"expected one PIP TC1 parameter: {capacitor_line}")
    tc1 = float(tc1_params[0].split("=", 1)[1])
    if not math.isclose(tc1, expected_tc1, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"native PIP TC1 {tc1:g}, expected {expected_tc1:g}")

    base_capacitance = float(raw_capacitance)
    frequency = 1e3
    temperature_c = 127.0
    deck_path = temp / "pip_tc1.spice"
    deck_path.write_text(
        "* Native extracted PiP capacitor TC1 behavior\n"
        f".temp {temperature_c:g}\n"
        f"{capacitor_line}\n"
        f"Vsmoke_hi {positive} 0 AC 1\n"
        f"Vsmoke_lo {negative} 0 AC 0\n"
        ".control\n"
        f"ac lin 1 {frequency:g} {frequency:g}\n"
        "print imag(i(Vsmoke_hi))\n"
        ".endc\n"
        ".end\n"
    )
    simulation = subprocess.run(
        [ngspice, "-b", str(deck_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if simulation.returncode:
        raise RuntimeError(
            "ngspice rejected the extracted PIP TC1 deck:\n"
            f"{simulation.stdout}\n{simulation.stderr}"
        )
    match = re.search(
        r"imag\(i\(vsmoke_hi\)\)\s*=\s*([-+0-9.eE]+)",
        simulation.stdout + simulation.stderr,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError(
            "ngspice did not report extracted PIP AC current:\n"
            f"{simulation.stdout}\n{simulation.stderr}"
        )
    current = abs(float(match.group(1)))
    expected_current = (
        2.0
        * math.pi
        * frequency
        * base_capacitance
        * (1.0 + tc1 * (temperature_c - 27.0))
    )
    if not math.isclose(current, expected_current, rel_tol=1e-5, abs_tol=1e-15):
        raise RuntimeError(
            f"native PIP current {current:g} A at {temperature_c:g} C, "
            f"expected {expected_current:g} A with TC1={tc1:g}"
        )
    return current, expected_current


def _run_pex(
    klayout: str, layout: Path, output: Path, report: Path
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts/run_ams_c35_pex.py"),
        "--layout",
        str(layout),
        "--top-cell",
        DEFAULT_TOP_CELL,
        "--out",
        str(output),
        "--report",
        str(report),
        "--klayout",
        klayout,
    ]
    return subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )


def _generate_coupling_fixture(klayout: str, layout_path: Path, temp: Path) -> None:
    macro_path = temp / "make_coupling_fixture.py"
    macro_path.write_text(
        "import os\n"
        "import pya\n"
        "layout = pya.Layout()\n"
        "layout.dbu = 0.001\n"
        f"top = layout.create_cell({DEFAULT_TOP_CELL!r})\n"
        "metal1 = layout.layer(35, 0)\n"
        "metal2 = layout.layer(37, 0)\n"
        "for layer, box in (\n"
        "    (metal1, pya.Box(0, 0, 10000, 1000)),\n"
        "    (metal1, pya.Box(0, 1450, 10000, 2450)),\n"
        "    (metal1, pya.Box(15000, 0, 25000, 1000)),\n"
        "    (metal2, pya.Box(15000, 1500, 25000, 2500)),\n"
        "):\n"
        "    top.shapes(layer).insert(box)\n"
        "layout.write(os.environ['COUPLING_GDS'])\n"
    )
    env = os.environ.copy()
    env["COUPLING_GDS"] = str(layout_path)
    result = subprocess.run(
        [klayout, "-b", "-r", str(macro_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "KLayout coupling fixture generation failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _generate_vertical_stack_fixture(
    klayout: str, layout_path: Path, temp: Path
) -> None:
    macro_path = temp / "make_vertical_stack_fixture.py"
    macro_path.write_text(
        "import os\n"
        "import pya\n"
        "layout = pya.Layout()\n"
        "layout.dbu = 0.001\n"
        f"top = layout.create_cell({DEFAULT_TOP_CELL!r})\n"
        "for layer, box in (\n"
        "    (35, pya.Box(0, 0, 10000, 10000)),\n"
        "    (37, pya.Box(0, 0, 10000, 10000)),\n"
        "    (39, pya.Box(0, 0, 5000, 10000)),\n"
        "    (42, pya.Box(0, 0, 10000, 10000)),\n"
        "):\n"
        "    top.shapes(layout.layer(layer, 0)).insert(box)\n"
        "layout.write(os.environ['VERTICAL_STACK_GDS'])\n"
    )
    env = os.environ.copy()
    env["VERTICAL_STACK_GDS"] = str(layout_path)
    result = subprocess.run(
        [klayout, "-b", "-r", str(macro_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "KLayout vertical-stack fixture generation failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _generate_nonmanhattan_fixture(
    klayout: str, layout_path: Path, temp: Path
) -> None:
    macro_path = temp / "make_nonmanhattan_fixture.py"
    macro_path.write_text(
        "import os\n"
        "import pya\n"
        "layout = pya.Layout()\n"
        "layout.dbu = 0.001\n"
        f"top = layout.create_cell({DEFAULT_TOP_CELL!r})\n"
        "top.shapes(layout.layer(35, 0)).insert(\n"
        "    pya.Polygon([\n"
        "        pya.Point(0, 0),\n"
        "        pya.Point(10000, 0),\n"
        "        pya.Point(8000, 10000),\n"
        "        pya.Point(0, 10000),\n"
        "    ])\n"
        ")\n"
        "layout.write(os.environ['NONMANHATTAN_GDS'])\n"
    )
    env = os.environ.copy()
    env["NONMANHATTAN_GDS"] = str(layout_path)
    result = subprocess.run(
        [klayout, "-b", "-r", str(macro_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "KLayout non-Manhattan fixture generation failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _generate_two_rp2_fixture(klayout: str, layout_path: Path, temp: Path) -> None:
    macro_path = temp / "make_two_rp2_fixture.py"
    macro_path.write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "import pya\n"
        "root = os.environ['REPO_ROOT']\n"
        "sys.path.insert(0, root)\n"
        "from common.pcells.scmos import Profile, register_profile\n"
        "profile_dir = Path(root) / 'profiles/ams_c35'\n"
        "variant = 'C35B4C3'\n"
        "library_name = f'siliconcraft_ams_c35_{variant}'\n"
        "profile = Profile(profile_dir, variant=variant)\n"
        "register_profile(profile_dir, library_name, variant=variant)\n"
        "parameters = profile.pcells['rp2'].get('parameters', {})\n"
        "defaults = {\n"
        "    key: value.get('default')\n"
        "    for key, value in parameters.items()\n"
        "    if isinstance(value, dict) and 'default' in value\n"
        "}\n"
        "layout = pya.Layout()\n"
        "layout.dbu = 0.001\n"
        f"top = layout.create_cell({DEFAULT_TOP_CELL!r})\n"
        "resistor = layout.create_cell('rp2', library_name, defaults)\n"
        "for x in (0, 30000):\n"
        "    top.insert(pya.CellInstArray(resistor.cell_index(), pya.Trans(x, 0)))\n"
        "layout.write(os.environ['MULTI_RP2_GDS'])\n"
    )
    env = os.environ.copy()
    env["REPO_ROOT"] = str(ROOT)
    env["MULTI_RP2_GDS"] = str(layout_path)
    result = subprocess.run(
        [klayout, "-b", "-r", str(macro_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "KLayout two-RPOLY2 fixture generation failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _add_substrate_label(klayout: str, layout_path: Path, temp: Path) -> None:
    macro_path = temp / "add_substrate_label.py"
    macro_path.write_text(
        "import os\n"
        "import pya\n"
        "layout = pya.Layout()\n"
        "layout.read(os.environ['SUBSTRATE_GDS'])\n"
        f"top = layout.cell({DEFAULT_TOP_CELL!r})\n"
        "if top is None:\n"
        "    raise RuntimeError('missing C35 test top cell')\n"
        "text_layer = layout.layer(61, 22)\n"
        "top.shapes(text_layer).insert(\n"
        "    pya.Text('Vss!', pya.Trans(pya.Point(30000, 0)))\n"
        ")\n"
        "layout.write(os.environ['SUBSTRATE_GDS'])\n"
    )
    env = os.environ.copy()
    env["SUBSTRATE_GDS"] = str(layout_path)
    result = subprocess.run(
        [klayout, "-b", "-r", str(macro_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "KLayout substrate-label fixture update failed:\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _assert_substrate_bulk_connected(netlist: str) -> None:
    resistor_nodes = {
        node
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("r")
        and len(fields) >= 4
        for node in fields[1:3]
    }
    mos = [
        line.split()
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("m")
        and len(fields) >= 5
    ]
    if len(mos) != 1 or mos[0][4] != "Vss_" or mos[0][4] not in resistor_nodes:
        raise RuntimeError(
            "native MOS bulk is not joined to the sanitized substrate tap: "
            f"MOS={mos}, R nodes={resistor_nodes}"
        )

    parasitic_capacitors = [
        fields
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("crcx")
        and len(fields) >= 4
    ]
    if not any(fields[2] == "Vss_" for fields in parasitic_capacitors):
        raise RuntimeError(
            "native area/fringe capacitance is not referenced to the "
            f"sanitized substrate tap: {parasitic_capacitors}"
        )


def _extract_native_fixture(
    klayout: str, layout: Path, workdir: Path, native_config: dict
) -> str:
    _, spice_path = run_lvs.extract(
        ROOT / "profiles/ams_c35",
        layout,
        "authoritative",
        workdir,
        klayout,
        extra_env={"C35_NATIVE_RC": json.dumps(native_config)},
        top_cell=DEFAULT_TOP_CELL,
    )
    return spice_path.read_text()


def _assert_native_failure_diagnostic(
    klayout: str, layout: Path, workdir: Path, native_config: dict
) -> None:
    captured_stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured_stderr):
            _extract_native_fixture(klayout, layout, workdir, native_config)
    except SystemExit as exc:
        if "klayout failed" not in str(exc):
            raise RuntimeError(
                f"unexpected native extraction failure: {exc}"
            ) from exc
    else:
        raise RuntimeError("native extraction accepted unsupported geometry")
    diagnostic = captured_stderr.getvalue()
    if (
        "native C35 RC extraction failed closed" not in diagnostic
        or "angled polygon edge is unsupported" not in diagnostic
    ):
        raise RuntimeError(
            f"native extraction diagnostic was not surfaced: {diagnostic}"
        )


def _assert_unique_rp2_names(netlist: str) -> None:
    names = [
        fields[0].lower()
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("xres_rp2_")
    ]
    if len(names) != 2 or len(set(names)) != 2:
        raise RuntimeError(
            f"expected two uniquely named RPOLY2 devices, got {names}"
        )


def _resistor_network_nodes(netlist: str) -> set[str]:
    return {
        node
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("r")
        and len(fields) >= 4
        for node in fields[1:3]
    }


def _assert_coupling_capacitances(
    netlist: str, same_layer_ff_per_um: float, cross_layer_ff_per_um: float
) -> None:
    resistor_nodes = _resistor_network_nodes(netlist)
    values = sorted(
        float(fields[-1])
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("crcx")
        and len(fields) >= 4
        and fields[1] in resistor_nodes
        and fields[2] in resistor_nodes
    )
    expected = sorted(
        (same_layer_ff_per_um * 10e-15, cross_layer_ff_per_um * 10e-15)
    )
    if len(values) != len(expected) or any(
        not math.isclose(actual, wanted, rel_tol=1e-8, abs_tol=1e-26)
        for actual, wanted in zip(values, expected)
    ):
        raise RuntimeError(
            f"native coupling capacitances {values}, expected {expected}"
        )


def _assert_vertical_stack_capacitances(
    netlist: str, native_config: dict
) -> None:
    resistor_nodes = _resistor_network_nodes(netlist)
    values = sorted(
        float(fields[-1])
        for line in netlist.splitlines()
        if (fields := line.split())
        and fields[0].lower().startswith("crcx")
        and len(fields) >= 4
        and fields[1] in resistor_nodes
        and fields[2] in resistor_nodes
    )
    vertical = native_config["capacitance"]["vertical_ff_per_um2"]
    expected_ff = (
        (50, "metal4", "metal3"),
        (50, "metal4", "metal2"),
        (50, "metal3", "metal2"),
        (100, "metal2", "metal1"),
    )
    expected = sorted(
        area * float(vertical[upper][lower]) * 1e-15
        for area, upper, lower in expected_ff
    )
    if len(values) != len(expected) or any(
        not math.isclose(actual, wanted, rel_tol=1e-8, abs_tol=1e-26)
        for actual, wanted in zip(values, expected)
    ):
        raise RuntimeError(
            f"native vertical stack capacitances {values}, expected {expected}"
        )

def main() -> int:
    klayout = os.environ.get("KLAYOUT") or shutil.which("klayout")
    ngspice = shutil.which("ngspice")
    if not klayout:
        raise RuntimeError("KLayout is required for the C35 native PEX regression")
    if not ngspice:
        raise RuntimeError("ngspice is required for the C35 native PEX regression")

    with tempfile.TemporaryDirectory(prefix="ams-c35-native-pex-") as temp_name:
        temp = Path(temp_name)
        layout = temp / "supported_c35.gds"
        output = temp / "extracted.spice"
        report = temp / "extracted.json"
        native_config = _native_config(
            load((ROOT / "profiles/ams_c35/pex/manifest.yaml").read_text())
        )
        pip_tc1 = native_config["capacitance_tempco1_per_c"]["c35_pip"]
        _generate_fixture(klayout, layout)
        result = _run_pex(klayout, layout, output, report)
        if result.returncode:
            raise RuntimeError(
                "native C35 PEX extraction failed:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        metadata = json.loads(report.read_text())
        elements = metadata["elements"]
        if not all(elements[name] > 0 for name in ("resistors", "capacitors", "mosfets")):
            raise RuntimeError(f"native extraction omitted R, C, or MOS: {elements}")
        if (
            metadata.get("backend") != "native_manhattan"
            or metadata.get("primary_backend") != "klayout_native_rcx"
            or metadata.get("process_maturity")
            != {"level": "L2", "status": "engineering_extracted"}
            or metadata.get("maturity") != "estimated"
            or metadata.get("calibrated") is not False
            or metadata.get("signoff") is not False
        ):
            raise RuntimeError(f"native PEX maturity contract regressed: {metadata}")
        warnings = metadata.get("warnings")
        if not isinstance(warnings, list) or not any(
            "estimated and uncalibrated" in warning.lower()
            and "not foundry signoff" in warning.lower()
            for warning in warnings
            if isinstance(warning, str)
        ):
            raise RuntimeError(f"native PEX warning contract regressed: {warnings}")

        native_netlist = output.read_text()
        _assert_graph_nodes_resolve(native_netlist)
        pip_line = next(
            (
                line
                for line in native_netlist.splitlines()
                if line.lower().startswith("cdev_pipcap_")
            ),
            None,
        )
        if pip_line is None:
            raise RuntimeError("native extraction emitted no PiP capacitor")
        pip_current, pip_expected = _simulate_extracted_pip_tc1(
            ngspice, temp, pip_line, float(pip_tc1)
        )
        deck, resistor_name, resistance = _smoke_deck(native_netlist)
        deck_path = temp / "extracted_op.spice"
        deck_path.write_text(deck)
        simulation = subprocess.run(
            [ngspice, "-b", str(deck_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if simulation.returncode:
            raise RuntimeError(
                "ngspice rejected the native extracted netlist:\n"
                f"{simulation.stdout}\n{simulation.stderr}"
            )
        match = re.search(
            rf"@{re.escape(resistor_name.lower())}\[i\]\s*=\s*([-+0-9.eE]+)",
            simulation.stdout + simulation.stderr,
            re.IGNORECASE,
        )
        if not match:
            raise RuntimeError(
                "ngspice did not report the native resistor branch current:\n"
                f"{simulation.stdout}\n{simulation.stderr}"
            )
        current = float(match.group(1))
        expected = 1.0 / resistance
        if not math.isclose(current, expected, rel_tol=1e-6, abs_tol=1e-10):
            raise RuntimeError(
                f"native resistor current {current:g} A, expected {expected:g} A"
            )
        print(
            "[test_ams_c35_native_pex] PASS: "
            f"{elements['resistors']} R, {elements['capacitors']} C, "
            f"{elements['mosfets']} MOS; {resistor_name}={resistance:g} ohm"
        )
        print(
            "[test_ams_c35_native_pex] PASS: extracted PiP TC1 AC current "
            f"{pip_current:.6g} A at 127 C (expected {pip_expected:.6g} A)"
        )
        coupling_layout = temp / "coupling.gds"
        _generate_coupling_fixture(klayout, coupling_layout, temp)
        coupling_netlist = _extract_native_fixture(
            klayout, coupling_layout, temp / "coupling_lvs", native_config
        )
        same_layer = native_config["capacitance"]["same_layer_ff_per_um"][
            "metal1"
        ]["value_ff_per_um"]
        cross_layer = native_config["capacitance"]["cross_layer_ff_per_um"][
            "metal2"
        ]["metal1"]["value_ff_per_um"]
        _assert_coupling_capacitances(
            coupling_netlist, float(same_layer), float(cross_layer)
        )
        print(
            "[test_ams_c35_native_pex] PASS: emitted same-layer and "
            "cross-layer coupling capacitances"
        )
        vertical_stack_layout = temp / "vertical_stack.gds"
        _generate_vertical_stack_fixture(klayout, vertical_stack_layout, temp)
        vertical_stack_netlist = _extract_native_fixture(
            klayout,
            vertical_stack_layout,
            temp / "vertical_stack_lvs",
            native_config,
        )
        _assert_vertical_stack_capacitances(vertical_stack_netlist, native_config)
        print(
            "[test_ams_c35_native_pex] PASS: intermediate metal shields "
            "non-adjacent vertical capacitance"
        )
        nonmanhattan_layout = temp / "nonmanhattan.gds"
        _generate_nonmanhattan_fixture(klayout, nonmanhattan_layout, temp)
        _assert_native_failure_diagnostic(
            klayout,
            nonmanhattan_layout,
            temp / "nonmanhattan_lvs",
            native_config,
        )
        print(
            "[test_ams_c35_native_pex] PASS: run_lvs exposes native "
            "fail-closed geometry diagnostics"
        )
        substrate_layout = temp / "substrate.gds"
        _generate_fixture(klayout, substrate_layout, ("nmos", "ptap"))
        _add_substrate_label(klayout, substrate_layout, temp)
        substrate_netlist = _extract_native_fixture(
            klayout, substrate_layout, temp / "substrate_lvs", native_config
        )
        _assert_graph_nodes_resolve(substrate_netlist)
        _assert_substrate_bulk_connected(substrate_netlist)
        print(
            "[test_ams_c35_native_pex] PASS: MOS bulk shares sanitized "
            "substrate tap node"
        )
        multi_rp2_layout = temp / "two_rp2.gds"
        _generate_two_rp2_fixture(klayout, multi_rp2_layout, temp)
        multi_rp2_netlist = _extract_native_fixture(
            klayout, multi_rp2_layout, temp / "two_rp2_lvs", native_config
        )
        _assert_unique_rp2_names(multi_rp2_netlist)
        print(
            "[test_ams_c35_native_pex] PASS: multiple RPOLY2 instances "
            "have unique SPICE names"
        )
        for pcell, expected_error in (
            ("rnwell", "C35 JFET classification is known"),
            ("diode_pn", "C35 diode compact-model parameters are unavailable"),
            (
                "nmosm",
                "native PEX has no verified primitive MOS card for MODNM",
            ),
            (
                "pmosm",
                "native PEX has no verified primitive MOS card for MODPM",
            ),
        ):
            unsupported_layout = temp / f"{pcell}.gds"
            _generate_fixture(klayout, unsupported_layout, ("nmos", pcell))
            rejected = _run_pex(
                klayout,
                unsupported_layout,
                temp / f"{pcell}.spice",
                temp / f"{pcell}.json",
            )
            diagnostic = rejected.stdout + rejected.stderr
            if rejected.returncode == 0 or expected_error not in diagnostic:
                raise RuntimeError(
                    f"native PEX did not fail closed for {pcell}:\n{diagnostic}"
                )
        print(
            "[test_ams_c35_native_pex] PASS: unsupported JFET, diode, "
            "and MIDOX MOS cards fail closed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
