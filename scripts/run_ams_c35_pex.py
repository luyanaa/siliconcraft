#!/usr/bin/env python3
"""Extract estimated AMS C35B4C3 RC parasitics with the native graph; never signoff."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_lvs  # noqa: E402
from common.process_ir import load_process  # noqa: E402
from yamlish import load  # noqa: E402

DEFAULT_LAYOUT = ROOT / "build/pcells/ams_c35_native_pex_smoke.gds"
DEFAULT_TOP_CELL = "ams_c35_analog_pcell_test"
WARNING = (
    "C35B4C3 parasitics are estimated and uncalibrated; this native Manhattan "
    "RC extraction is not foundry signoff."
)


def _spice_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("*")
    ]


def _element_counts(text: str) -> dict[str, int]:
    counts = {"resistors": 0, "capacitors": 0, "mosfets": 0}
    for line in _spice_lines(text):
        name = line.split(None, 1)[0].lower()
        if name.startswith("r") or name.startswith("xres_"):
            counts["resistors"] += 1
        elif name.startswith("c"):
            counts["capacitors"] += 1
        elif name.startswith("m"):
            counts["mosfets"] += 1
    return counts


def _generate_fixture(
    klayout: str, layout: Path, pcells: tuple[str, ...] = ("nmos", "rp2", "cap_pip")
) -> None:
    layout.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "SILICONCRAFT_PROFILE": "ams_c35",
            "SILICONCRAFT_VARIANT": "C35B4C3",
            "SILICONCRAFT_PCELLS": ",".join(pcells),
            "SILICONCRAFT_OUTPUT": str(layout),
        }
    )
    result = subprocess.run(
        [klayout, "-b", "-r", str(ROOT / "scripts/run_pcells.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"KLayout fixture generation failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    print(result.stdout.rstrip())


def _native_config(manifest: dict[str, object]) -> dict[str, object]:
    profile = manifest["profiles"]["estimated_rcx"]
    native = profile["native_rc"]
    layer_names = {
        "metal1": "metal1",
        "metal2": "metal2",
        "metal3": "metal3",
        "metal4": "metal4",
        "poly": "poly",
        "poly2": "elec",
        "nwell": "nBulk",
        "ndiff": "nDiff",
        "pdiff": "pDiff",
    }
    directives = profile["magic_directives"]
    sheet_values: dict[str, float] = {}
    conductors: dict[str, dict[str, float]] = {}
    area_caps: dict[str, float] = {}
    fringe_caps: dict[str, float] = {}
    coupling_caps: dict[str, dict[str, float]] = {}
    cross_layer_caps: dict[str, dict[str, dict[str, float]]] = {}
    vertical_caps: dict[str, dict[str, float]] = {}
    for item in directives:
        kind = item["kind"]
        value = float(item["value"])
        if kind == "resist":
            source_layer = item["layers"]
            layer = layer_names.get(source_layer)
            if layer:
                conductors[layer] = {
                    "sheet_resistance_ohm_sq": value,
                    "width_correction_um": 0.0,
                }
            if source_layer in ("metal1", "metal2", "metal3", "metal4"):
                sheet_values[source_layer] = value
            elif source_layer == "poly":
                sheet_values["poly"] = value
            elif source_layer == "poly2":
                sheet_values["rp2"] = value
                conductors["elec"] = {
                    "sheet_resistance_ohm_sq": value,
                    "width_correction_um": 0.0,
                }
            elif source_layer == "rpoly":
                sheet_values["highres"] = value
            elif source_layer == "nwell":
                sheet_values["nwell"] = value
                conductors["nBulk"] = {
                    "sheet_resistance_ohm_sq": value,
                    "width_correction_um": 0.0,
                }
            elif source_layer == "ndiff":
                sheet_values["n_diff"] = value
                conductors["nOhmic"] = {
                    "sheet_resistance_ohm_sq": value,
                    "width_correction_um": 0.0,
                }
            elif source_layer == "pdiff":
                sheet_values["p_diff"] = value
                conductors["pOhmic"] = {
                    "sheet_resistance_ohm_sq": value,
                    "width_correction_um": 0.0,
                }
        elif kind == "areacap":
            layer = layer_names.get(item["layers"])
            if layer:
                area_caps[layer] = value
        elif kind == "perimc":
            layer = layer_names.get(item["layers"])
            if layer:
                fringe_caps[layer] = value
        elif kind == "sidewall":
            layer = layer_names.get(item["upper"])
            if layer:
                coupling_caps[layer] = {
                    "value_ff_per_um": value,
                    "max_spacing_um": float(
                        native["same_layer_coupling_min_spacing_um"][item["upper"]]
                    ),
                }
        elif kind == "overlap":
            upper = layer_names.get(item["upper"])
            if upper:
                for raw_lower in str(item["lower"]).split(","):
                    lower = layer_names.get(raw_lower.strip())
                    if lower and lower in conductors:
                        vertical_caps.setdefault(upper, {})[lower] = value
        elif kind == "sideoverlap":
            upper = layer_names.get(item["upper"])
            lower = layer_names.get(item["lower"])
            if upper and lower:
                cross_layer_caps.setdefault(upper, {})[lower] = {
                    "value_ff_per_um": value,
                    "max_spacing_um": float(
                        native["same_layer_coupling_min_spacing_um"][item["upper"]]
                    ),
                }

    for source_layer in ("metal1", "metal2", "metal3", "metal4", "poly"):
        if source_layer not in sheet_values:
            raise ValueError(f"native C35 RC config lacks {source_layer} sheet resistance")
    for layer, source_layer in (
        ("metal1", "metal1"),
        ("metal2", "metal2"),
        ("metal3", "metal3"),
        ("metal4", "metal4"),
        ("poly", "poly"),
        ("elec", "poly2"),
        ("nBulk", "nwell"),
        ("nDiff", "ndiff"),
        ("pDiff", "pdiff"),
    ):
        if layer in conductors:
            continue
        directive = next(
            item
            for item in directives
            if item["kind"] == "resist" and item["layers"] == source_layer
        )
        conductors[layer] = {
            "sheet_resistance_ohm_sq": float(directive["value"]),
            "width_correction_um": 0.0,
        }
    for source_layer, spec in native["conductor_width_correction_um"].items():
        conductors[layer_names[source_layer]]["width_correction_um"] = float(spec["value"])

    contacts: dict[str, list[dict[str, object]]] = {}
    contact_map = {
        "ndc": ("ca", (("nDiff", "metal1"), ("nOhmic", "metal1"))),
        "pdc": ("ca", (("pDiff", "metal1"), ("pOhmic", "metal1"))),
        "pc": ("cp", (("poly", "metal1"),)),
        "ec": ("ce", (("elec", "metal1"),)),
        "m2c": ("via", (("metal1", "metal2"),)),
        "m3c": ("via2", (("metal2", "metal3"),)),
        "m4c": ("via3", (("metal3", "metal4"),)),
    }
    for item in directives:
        if item["kind"] != "contact":
            continue
        cut, pairs = contact_map[item["contact_type"]]
        contacts.setdefault(cut, []).extend(
            {"layers": list(pair), "resistance_ohm": float(item["value"])}
            for pair in pairs
        )

    corrections = {
        name: float(spec["value"])
        for name, spec in native["resistor_width_correction_um"].items()
    }
    pip = native["pip_capacitance"]
    return {
        "conductors": conductors,
        "contacts": contacts,
        "capacitance": {
            "area_ff_per_um2": area_caps,
            "fringe_ff_per_um": fringe_caps,
            "same_layer_ff_per_um": coupling_caps,
            "cross_layer_ff_per_um": cross_layer_caps,
            "vertical_ff_per_um2": vertical_caps,
        },
        "sheet_resistance_ohm_sq": sheet_values,
        "resistor_width_correction_um": corrections,
        "area_capacitance_ff_per_um2": {
            name: float(spec["area_ff_per_um2"]) for name, spec in pip.items()
        },
        "perimeter_capacitance_ff_per_um": {
            name: float(spec["perimeter_ff_per_um"]) for name, spec in pip.items()
        },
        "capacitance_tempco1_per_c": {
            name: float(spec["tc1_per_c"])
            for name, spec in pip.items()
            if "tc1_per_c" in spec
        },
    }


def _with_model_section(text: str, library: Path) -> str:
    lines = text.splitlines()
    end = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == ".end"),
        None,
    )
    if end is None:
        raise RuntimeError("native extractor output has no .end statement")
    lines.insert(end, f".lib '{library}' ams_c35")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--top-cell", default=DEFAULT_TOP_CELL)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "build/pex/ams_c35_extracted.spice"
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--klayout", default=os.environ.get("KLAYOUT", "klayout"))
    parser.add_argument(
        "--signoff",
        action="store_true",
        help="record that signoff was requested; this estimated flow cannot provide it",
    )
    args = parser.parse_args()

    process = load_process("ams_c35", ROOT)
    if process.collateral_capabilities.pex_rc != "estimated":
        raise SystemExit("AMS C35 PEX profile is not classified as estimated RCX")
    process_maturity = process.model_maturity_doc.get("process_maturity")
    if (
        not isinstance(process_maturity, dict)
        or process_maturity.get("level") != "L2"
        or process_maturity.get("status") != "engineering_extracted"
    ):
        raise SystemExit("AMS C35 process maturity must be L2 engineering_extracted")
    if process.pex_doc.get("flow", {}).get("signoff") is not False:
        raise SystemExit("AMS C35 PEX manifest must explicitly disable signoff")
    manifest_path = process.profile_dir / "pex/manifest.yaml"
    manifest = load(manifest_path.read_text())
    profile = manifest.get("profiles", {}).get("estimated_rcx")
    if not isinstance(profile, dict) or profile.get("maturity") != "estimated":
        raise SystemExit("estimated_rcx must remain explicitly estimated")
    flow = manifest.get("flow", {})
    if flow.get("primary_backend") != "klayout_native_rcx":
        raise SystemExit("AMS C35 native KLayout RCX must remain the primary backend")
    magic_resistance = (
        flow.get("optional_crosscheck", {})
        .get("magic", {})
        .get("resistance")
    )
    if magic_resistance != "disabled_known_failure":
        raise SystemExit("Magic resistance cross-check must remain explicitly disabled")

    if args.signoff:
        print(
            "WARNING: --signoff requested; this run remains estimated and non-signoff.",
            file=sys.stderr,
        )

    layout = (args.layout or DEFAULT_LAYOUT).expanduser().resolve()
    if args.layout is None and not layout.exists():
        _generate_fixture(args.klayout, layout)
    if not layout.is_file():
        raise SystemExit(f"layout not found: {layout}")

    output = args.out.expanduser().resolve()
    report = (args.report or output.with_suffix(".json")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    config = _native_config(manifest)
    with tempfile.TemporaryDirectory(prefix="ams-c35-native-") as temp_dir:
        workdir = Path(temp_dir)
        summary, extracted_path = run_lvs.extract(
            process.profile_dir,
            layout,
            "authoritative",
            workdir,
            args.klayout,
            extra_env={"C35_NATIVE_RC": json.dumps(config)},
            top_cell=args.top_cell,
        )
        extracted = extracted_path.read_text()

    counts = _element_counts(extracted)
    if not counts["resistors"] or not counts["capacitors"]:
        raise RuntimeError(
            "native extraction must produce actual R and C elements; "
            f"found {counts['resistors']} R and {counts['capacitors']} C"
        )
    if not counts["mosfets"]:
        raise RuntimeError("native extraction produced no MOS devices")

    library = process.profile_dir / "models/ams_c35.lib"
    if not library.is_file():
        raise RuntimeError(f"C35 MOS model library not found: {library}")
    output.write_text(
        "* WARNING: estimated and uncalibrated C35B4C3 parasitics; not foundry signoff.\n"
        + _with_model_section(extracted, library)
    )
    warnings = [WARNING]
    if args.signoff:
        warnings.append(
            "Signoff was requested, but this estimated open-source flow cannot provide signoff."
        )
    warnings.extend(summary.get("warnings", []))
    payload = {
        "profile": "ams_c35",
        "process": "C35B4C3",
        "backend": "native_manhattan",
        "primary_backend": "klayout_native_rcx",
        "process_maturity": {
            "level": process_maturity["level"],
            "status": process_maturity["status"],
        },
        "maturity": "estimated",
        "calibrated": False,
        "signoff": False,
        "signoff_requested": args.signoff,
        "layout": str(layout),
        "top_cell": args.top_cell,
        "extracted_spice": str(output),
        "elements": counts,
        "warnings": warnings,
    }
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("AMS C35B4C3 native PEX: PASS (L2 engineering-extracted; parasitics estimated, not signoff)")
    print(f"  layout: {layout}")
    print(f"  extracted SPICE: {output}")
    print(f"  elements: {counts}")
    print(f"  report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
