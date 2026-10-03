#!/usr/bin/env python3
"""Static contract tests for the process-neutral Magic PEX flow."""

from __future__ import annotations
from pathlib import Path
import shutil
import sys
import tempfile
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import (  # noqa: E402
    assemble_technology,
    capacitance_to_magic,
    convert_to_magic,
    generate_profile,
    render_profile_extract,
    without_well_routing,
)
from yamlish import load  # noqa: E402
from common.process_ir import load_process  # noqa: E402


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
    tr1um, tr1um_path = load_manifest("tr1um")
    tr1um_ir = load_process("tr1um", ROOT)
    ami06_ir = load_process("ami06", ROOT)
    hp06_ir = load_process("hp06", ROOT)
    ami16_ir = load_process("ami16", ROOT)
    ls1u_ir = load_process("ls1u", ROOT)
    ams_c35, ams_c35_path = load_manifest("ams_c35")
    ams_c35_ir = load_process("ams_c35", ROOT)
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
    assert ami16["flow"]["original_run"] == "N88Z"
    assert ami16["physical"]["lambda_um"] == 0.8
    assert ami16_ir.device("nmos_core").simulation_name == "ami16N"
    assert ami16_ir.device("pmos_core").simulation_name == "ami16P"
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
    assert hp06_ir.device("nmos_core").simulation_name == "hp14tbN"
    assert hp06_ir.device("pmos_core").simulation_name == "hp14tbP"
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
    assert ami06_ir.device("nmos_core").simulation_name == "ami06N"
    assert ami06_ir.device("pmos_core").simulation_name == "ami06P"
    for manifest in (ami06, hp06, ami16):
        assert "devices" not in (manifest.get("topology") or {})
    assert ami06_ir.parasitic_ownership["gate_overlap_capacitance"] == "model"
    assert ami06_ir.parasitic_ownership["diffusion_sheet_resistance"] == "pex"


    # Source values convert to Magic's units, preserving fractional capacitance
    # values supported by the extractor rather than rounding small C to zero.
    assert convert_to_magic(0.09, "ohm_per_square", 0.3) == 90
    assert convert_to_magic(93, "af_per_um2", 0.3) == 8
    assert convert_to_magic(798, "af_per_um2", 0.3) == 72
    assert convert_to_magic(77, "af_per_um", 0.3) == 23
    assert capacitance_to_magic(0.029, "ff_per_um2", 0.2) == "1.16"
    assert capacitance_to_magic(0.044, "ff_per_um", 0.2) == "8.8"

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
        ami06, "none", ami06_path.parent, ami06_ir.device_bindings
    )
    ami06_reference_technology = assemble_technology(
        ami06, "n8bn_reference", ami06_path.parent, ami06_ir.device_bindings
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
    assert "areacap cap 71.82" in reference
    assert "overlap metal2 metal1 3.06" in reference
    assert "contact ndc 4 51000" in reference
    assert "contact pdc 4 116000" in reference
    assert "contact pc 4 17700" in reference
    assert "contact ec 6 17100" in reference
    assert "contact m2c 4 1580" in reference
    assert "contact m3c 5 1850" in reference
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
        assemble_technology(hp06, "none", hp06_path.parent, hp06_ir.device_bindings)
    )
    hp_reference = extract_section(
        assemble_technology(
            hp06, "n8ag_reference", hp06_path.parent, hp06_ir.device_bindings
        )
    )
    assert "device mosfet hp14tbN" in hp_none
    assert "device mosfet hp14tbP" in hp_none
    assert "resist " not in hp_none
    assert "areacap " not in hp_none
    assert "device mosfet hp14tbN" in hp_reference
    assert "resist metal1 70" in hp_reference
    assert "resist rpoly 130000" in hp_reference
    assert "areacap wcap 207" in hp_reference
    assert "overlap metal3 metal2 4.32" in hp_reference
    assert "contact ndc 4 2300" in hp_reference
    assert "contact pdc 4 2000" in hp_reference
    assert "contact pc 4 1800" in hp_reference
    assert "contact m2c 4 880" in hp_reference
    assert "contact m3c 5 360" in hp_reference
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
        assemble_technology(
            ami16, "none", ami16_path.parent, ami16_ir.device_bindings
        )
    )
    ami16_reference = extract_section(
        assemble_technology(
            ami16, "n88z_reference", ami16_path.parent, ami16_ir.device_bindings
        )
    )
    assert "device mosfet ami16N" in ami16_none
    assert "device mosfet ami16P" in ami16_none
    assert "resist " not in ami16_none
    assert "areacap " not in ami16_none
    assert "device mosfet ami16N" in ami16_reference
    assert "resist metal1 50" in ami16_reference
    assert "areacap poly2 451.84" in ami16_reference
    assert "areacap cap 381.44" in ami16_reference
    assert "overlap metal2 metal1 24.32" in ami16_reference
    assert "perimc poly ~poly 35.2" in ami16_reference
    assert "contact ndc 4 65800" in ami16_reference
    assert "contact pdc 4 36300" in ami16_reference
    assert "contact pc 4 25700" in ami16_reference
    assert "contact ec 6 20200" in ami16_reference
    assert "contact m2c 4 60" in ami16_reference

    ami16_models = (ami16_path.parent.parent / "models/ami16.lib").read_text()
    assert ".lib ami16" in ami16_models
    assert ".MODEL ami16N" in ami16_models
    assert ".MODEL ami16P" in ami16_models
    assert ".LIB NMOS" not in ami16_models
    assert ".ENDL NMOS" not in ami16_models



    # The LS1u compatibility manifest still selects the legacy topology path;
    # its existing regression covers exact historical msubcircuit syntax.
    ls1u_extract = render_profile_extract(ls1u, "none", ls1u_ir.device_bindings)
    assert "device msubcircuit LV1UNMOS" in ls1u_extract
    assert "device msubcircuit LV1UPMOS" in ls1u_extract

    assert tr1um["physical"]["lambda_um"] == 0.5
    assert "legacy_backend" not in tr1um["source_technology"]
    assert tr1um_ir.device("nmos_core").simulation_name == "NMOS_mst"
    assert tr1um_ir.device("pmos_core").simulation_name == "PMOS_mst"
    tr1um_none = render_profile_extract(
        tr1um, "none", tr1um_ir.device_bindings
    )
    tr1um_reference = render_profile_extract(
        tr1um, "tr1um_engineering", tr1um_ir.device_bindings
    )
    assert "device mosfet NMOS_mst" in tr1um_none
    assert "device mosfet PMOS_mst" in tr1um_none
    assert "resist metal1 50" not in tr1um_none
    assert "resist metal1 50" in tr1um_reference
    assert "areacap (ndiff,ndc)/a 30" in tr1um_reference
    assert "lambda 50" in tr1um_reference
    assert (tr1um_path.parent.parent / "models/tr1um.lib").read_text().count(".lib tr1um") == 1
    with tempfile.TemporaryDirectory(prefix="siliconcraft-tr1um-") as temp_dir:
        temp_profile = Path(temp_dir) / "tr1um"
        shutil.copytree(tr1um_path.parent.parent, temp_profile)
        temp_manifest_path = temp_profile / "pex" / "manifest.yaml"
        temp_manifest = load(temp_manifest_path.read_text())
        generated = generate_profile(
            temp_manifest,
            temp_manifest_path,
            "tr1um_engineering",
            tr1um_ir.device_bindings,
        )
        assert generated.parent == temp_profile / "pex"
        tr1um_tech = generated.read_text()
    assert "calma CMF 48 0" in tr1um_tech
    assert "calma CMS 49 0" in tr1um_tech

    assert ams_c35["default"] == "estimated_rcx"
    assert ams_c35_ir.collateral_capabilities.pex_runtime is True
    assert ams_c35_ir.collateral_capabilities.pex_rc == "estimated"
    ams_c35_tech = assemble_technology(
        ams_c35, "estimated_rcx", ams_c35_path.parent, ams_c35_ir.device_bindings
    )
    ams_c35_extract = extract_section(ams_c35_tech)
    assert "device mosfet c35N" in ams_c35_extract
    assert "device mosfet c35P" in ams_c35_extract
    assert "WARNING: estimated parasitic coefficients" in ams_c35_extract
    assert "resist metal4 70" in ams_c35_extract
    assert "areacap metal1 1.16" in ams_c35_extract
    assert "contact m4c 3 2100" in ams_c35_extract
    assert "contact m4contact 5 metal3 0 metal4 0" in ams_c35_tech
    assert "calma M4LABEL 61 25" in ams_c35_tech
    assert "sidewall metal1 space metal1 space 17.4" in ams_c35_extract
    assert "calma UNUSED 62 14" in ams_c35_tech
    assert "metal4 metal4,m4" in ams_c35_tech

    with tempfile.TemporaryDirectory(prefix="siliconcraft-ams-c35-") as temp_dir:
        temp_root = Path(temp_dir)
        temp_pex = temp_root / "ams_c35" / "pex"
        temp_pex.mkdir(parents=True)
        shutil.copy2(ams_c35_path, temp_pex / "manifest.yaml")
        shutil.copy2(ams_c35_path.parent / "cifin-ams-c35.gen", temp_pex)
        (temp_root / "ls1u").symlink_to(
            ROOT / "profiles" / "ls1u", target_is_directory=True
        )
        temp_manifest_path = temp_pex / "manifest.yaml"
        generated = generate_profile(
            load(temp_manifest_path.read_text()),
            temp_manifest_path,
            "estimated_rcx",
            ams_c35_ir.device_bindings,
        )
        assert generated.name == "estimated_rcx.tech"

    print("Generic Magic PEX flow checks: PASS")
    print("  source-unit conversions: PASS")
    print("  AMI06 source map and profile rendering: PASS")
    print("  HP06 source map, model library, and profile rendering: PASS")
    print("  AMI16 source map, model library, electrode/NPN semantics, and rendering: PASS")
    print("  TR-1um primitive topology, native input streams, and rendering: PASS")
    print("  LS1u compatibility rendering: PASS")
    print("  AMS C35 estimated RCX coefficients and four-metal technology: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
