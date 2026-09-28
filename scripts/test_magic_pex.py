#!/usr/bin/env python3
"""Static contract tests for the process-neutral Magic PEX flow."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import (  # noqa: E402
    assemble_technology,
    convert_to_magic,
    render_profile_extract,
    without_well_routing,
)
from yamlish import load  # noqa: E402


def load_manifest(profile: str) -> tuple[dict, Path]:
    path = ROOT / "profiles" / profile / "pex" / "manifest.yaml"
    return load(path.read_text()), path


def extract_section(text: str) -> str:
    start = text.index("extract\n")
    end = text.index("\nwiring\n", start)
    return text[start:end]


def main() -> int:
    ami06, ami06_path = load_manifest("ami06")
    ls1u, _ = load_manifest("ls1u")
    hp06, hp06_path = load_manifest("hp06")
    ami16, ami16_path = load_manifest("ami16")
    assert ami06["source_technology"]["legacy_backend"] == {
        "technology": "scmos-sub",
        "extraction_style": "lambda=0.30",
        "expected_lambda_um": 0.3,
        "purpose": "runtime SCMOS geometry/connectivity cross-check only; not the AMI06 coefficient source",
        "source": "OpenCircuitDesign Magic scmos-sub.tech / MOSIS SCMOS 8.2.8",
    }
    assert hp06["source_technology"]["legacy_backend"]["technology"] == "scmos-sub"
    assert hp06["source_technology"]["legacy_backend"]["expected_lambda_um"] == 0.3
    assert ami16["source_technology"]["legacy_backend"] == {
        "technology": "scmos",
        "extraction_style": "lambda=0.8(scna16_ami)",
        "expected_lambda_um": 0.8,
        "purpose": "runtime SCMOS geometry/connectivity cross-check only; not the AMI16 coefficient source",
        "source": "OpenCircuitDesign Magic scmos.tech / MOSIS SCMOS 8.2.8",
    }

    assert ami16["flow"]["source_driven"] is True
    assert ami16["flow"]["original_process"] == "AMI_ABN"
    assert ami16["flow"]["original_run"] == "N77H"
    assert ami16["physical"]["lambda_um"] == 0.8
    assert ami16["topology"]["devices"]["nmos"]["model"] == "ami16N"
    assert ami16["topology"]["devices"]["pmos"]["model"] == "ami16P"
    assert ami16["topology"]["features"] == {"elec": True, "npn": True}
    assert ami16["topology"]["device_semantics"]["mos4"] == [
        "nmos4", "pmos4", "nmos4_elec", "pmos4_elec"
    ]
    assert ami16["topology"]["device_semantics"]["npn"] == ["npnTran"]
    ami16_layers = load(
        (ami16_path.parent.parent / "layers.yaml").read_text()
    )
    cactive = next(layer for layer in ami16_layers["layers"] if layer["name"] == "cactive")
    assert cactive["available"] is True
    assert cactive["gds"] == [{"layer": 43, "datatype": 0}]
    assert "NPN collector-active alias" in cactive["note"]

    assert hp06["flow"]["source_driven"] is True
    assert hp06["flow"]["original_process"] == "HP_AMOS14TB"
    assert hp06["flow"]["original_run"] == "N8AG"
    assert hp06["physical"]["lambda_um"] == 0.3
    assert hp06["topology"]["devices"]["nmos"]["model"] == "hp14tbN"
    assert hp06["topology"]["devices"]["pmos"]["model"] == "hp14tbP"
    assert hp06["topology"]["features"] == {
        "cwell": True,
        "sblock": True,
        "metal3": True,
        "stacked_vias": True,
    }

    assert ami06["flow"]["source_driven"] is True
    assert ami06["flow"]["original_process"] == "AMI_C5N"
    assert ami06["flow"]["original_run"] == "N8BN"
    assert ami06["physical"]["lambda_um"] == 0.3
    assert ami06["topology"]["devices"]["nmos"]["model"] == "ami06N"
    assert ami06["topology"]["devices"]["pmos"]["model"] == "ami06P"

    # Source values must convert to Magic's integer units without importing
    # a process-specific constant into the renderer.
    assert convert_to_magic(0.09, "ohm_per_square", 0.3) == 90
    assert convert_to_magic(93, "af_per_um2", 0.3) == 8
    assert convert_to_magic(798, "af_per_um2", 0.3) == 72
    assert convert_to_magic(77, "af_per_um", 0.3) == 23

    expected_gds = {
        "CWP": 41,
        "CWN": 42,
        "CAA": 43,
        "CSP": 44,
        "CSN": 45,
        "CPG": 46,
        "CCC": 25,
        "CMF": 49,
        "CVA": 50,
        "CMS": 51,
    }
    input_map = (
        ami06_path.parent.parent / "reference/magic/cifin-ami06.gen"
    ).read_text()
    for layer, number in expected_gds.items():
        assert f"calma {layer} {number} *" in input_map

    ami06_none_technology = assemble_technology(
        ami06, "none", ami06_path.parent
    )
    ami06_reference_technology = assemble_technology(
        ami06, "n8bn_reference", ami06_path.parent
    )
    none = extract_section(ami06_none_technology)
    reference = extract_section(ami06_reference_technology)
    well_route_check = without_well_routing(ami06_reference_technology)
    assert "nwell,nsc,nsd nwell,nsc,nsd" not in well_route_check
    assert "pwell,psc,psd pwell,psc,psd" not in well_route_check
    assert "hnwell,hnsc,hnsd hnwell,hnsc,hnsd" in well_route_check
    assert "device mosfet ami06N" in none
    assert "device mosfet ami06P" in none
    assert "resist " not in none
    assert "areacap " not in none
    assert "device mosfet ami06N" in reference
    assert "resist metal1 90" in reference
    assert "areacap cap 72" in reference
    assert "overlap metal2 metal1 3" in reference
    assert "contact " not in reference
    assert "2400" not in reference
    hp_input_map = (
        hp06_path.parent.parent / "reference/magic/cifin-hp06.gen"
    ).read_text()
    for layer, number in {
        "CSB": 29,
        "CWC": 59,
        "CVS": 61,
        "CMT": 62,
    }.items():
        assert f"calma {layer} {number} *" in hp_input_map
    assert "layer rpoly CSB" in hp_input_map
    assert "layer wcap CPG" in hp_input_map

    hp_none = extract_section(
        assemble_technology(hp06, "none", hp06_path.parent)
    )
    hp_reference = extract_section(
        assemble_technology(hp06, "n8ag_reference", hp06_path.parent)
    )
    assert "device mosfet hp14tbN" in hp_none
    assert "device mosfet hp14tbP" in hp_none
    assert "resist " not in hp_none
    assert "areacap " not in hp_none
    assert "device mosfet hp14tbN" in hp_reference
    assert "resist metal1 70" in hp_reference
    assert "resist rpoly 130000" in hp_reference
    assert "areacap wcap 207" in hp_reference
    assert "overlap metal3 metal2 4" in hp_reference
    assert "contact " not in hp_reference
    assert "2400" not in hp_reference

    hp_models = (hp06_path.parent.parent / "models/hp06.lib").read_text()
    assert ".lib hp06" in hp_models
    assert ".MODEL hp14tbN" in hp_models
    assert ".MODEL hp14tbP" in hp_models
    assert ".LIB NMOS" not in hp_models
    assert ".ENDL NMOS" not in hp_models
    ami16_input_map = (
        ami16_path.parent.parent / "reference/magic/cifin-ami16.gen"
    ).read_text()
    for layer, number in {"CBA": 58, "CEL": 56, "CAA": 43, "CMS": 51}.items():
        assert f"calma {layer} {number} *" in ami16_input_map
    assert "layer pbase CBA" in ami16_input_map
    assert "layer electrode CEL" in ami16_input_map

    ami16_none = extract_section(
        assemble_technology(ami16, "none", ami16_path.parent)
    )
    ami16_reference = extract_section(
        assemble_technology(ami16, "n77h_reference", ami16_path.parent)
    )
    assert "device mosfet ami16N" in ami16_none
    assert "device mosfet ami16P" in ami16_none
    assert "resist " not in ami16_none
    assert "areacap " not in ami16_none
    assert "device mosfet ami16N" in ami16_reference
    assert "resist metal1 60" in ami16_reference
    assert "resist poly2 25000" in ami16_reference
    assert "areacap poly2 477" in ami16_reference
    assert "areacap cap 395" in ami16_reference
    assert "overlap metal2 metal1 28" in ami16_reference
    assert "perimc poly active 30" in ami16_reference
    assert "contact " not in ami16_reference

    ami16_models = (ami16_path.parent.parent / "models/ami16.lib").read_text()
    assert ".lib ami16" in ami16_models
    assert ".MODEL ami16N" in ami16_models
    assert ".MODEL ami16P" in ami16_models
    assert ".LIB NMOS" not in ami16_models
    assert ".ENDL NMOS" not in ami16_models



    # The LS1u compatibility manifest still selects the legacy topology path;
    # its existing regression covers exact historical msubcircuit syntax.
    ls1u_extract = render_profile_extract(ls1u, "none")
    assert "device msubcircuit LV1UNMOS" in ls1u_extract
    assert "device msubcircuit LV1UPMOS" in ls1u_extract

    print("Generic Magic PEX flow checks: PASS")
    print("  source-unit conversions: PASS")
    print("  AMI06 source map and profile rendering: PASS")
    print("  HP06 source map, model library, and profile rendering: PASS")
    print("  AMI16 source map, model library, electrode/NPN semantics, and rendering: PASS")
    print("  LS1u compatibility rendering: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
