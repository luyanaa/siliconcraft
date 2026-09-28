#!/usr/bin/env python3
"""Validate the provenance-only historical SCMOS matrix contract."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402


EXPECTED_PROCESSES = {
    "orbit_20",
    "ami_abn_12",
    "hp_cmos34",
    "ami_cwl",
    "hp_cmos26b_legacy",
    "hp_cmos26g",
    "hp_cmos26g_subm",
    "hp_mos14tb",
    "hp_mos14tb_subm",
    "hp_gmos10qa",
    "hp_gmos10qa_subm",
}


def main() -> int:
    matrix = yamlish.load(
        (ROOT / "schema/historical_scmos_process_matrix.yaml").read_text()
    )

    assert matrix["schema_version"] == 1
    assert matrix["kind"] == "historical_scmos_process_matrix"
    assert matrix["authority"] == "reference_only"
    policy = matrix["active_profile_policy"]
    assert policy["status"] == "metadata_only"
    assert policy["active_profiles"] == []
    assert "calibrated_device_models" in policy["do_not_claim"]
    assert "signoff_pex" in policy["do_not_claim"]

    sources = matrix["sources"]
    for source_name in (
        "mosis_scmos_7_2",
        "southampton_scmos_8_0",
        "magic_catalog",
        "magic_2001a",
        "magic_2002a",
    ):
        assert source_name in sources
    assert sources["mosis_scmos_7_2"]["url"].endswith("mosis_scmos7_2.pdf")
    assert sources["southampton_scmos_8_0"]["url"].endswith("scmos-main.html")
    assert sources["magic_catalog"]["url"] == "https://opencircuitdesign.com/magic/tech.html"

    release = matrix["magic_release_contract"]
    assert release["archive_releases_are_distinct"] == ["magic_2001a", "magic_2002a"]
    assert release["bundled_technology_is_distinct"] is True
    assert release["bundled_name"] == "scmos.tech"
    distribution_names = {entry["name"] for entry in release["distribution_files"]}
    assert distribution_names == {"scmos-sub.tech", "scmos-tm.tech", "scmosWR.tech", "scmos.tech"}

    processes = {entry["name"]: entry for entry in matrix["processes"]}
    assert set(processes) == EXPECTED_PROCESSES
    assert all("active_profile" not in entry for entry in processes.values())

    orbit = processes["orbit_20"]
    assert orbit["lambda_um"] == 1.0
    assert set(orbit["mosis_codes"]) == {"SCNA", "SCNE", "SCN", "SCNA_MEMS"}
    assert {
        "analog_npn",
        "buried_ccd",
        "floating_gate",
        "electrode_poly2",
        "mems",
    } <= set(orbit["capabilities"])
    assert orbit["magic"]["exact_orbit_archive_target"] is False
    assert "SCNA20(ORB)" in orbit["magic"]["bundled_historical_styles"]

    ami12 = processes["ami_abn_12"]
    assert ami12["lambda_um"] == 0.6
    assert ami12["mosis_codes"] == ["SCNA", "SCNE", "SCN"]
    assert {"analog_npn", "buried_ccd", "electrode_poly2", "high_voltage"} <= set(
        ami12["capabilities"]
    )
    assert ami12["magic"]["exact_12um_archive_target"] is False
    assert ami12["magic"]["generic_archive_feature_size_um"] == 1.6

    hp34 = processes["hp_cmos34"]
    assert hp34["lambda_um"] == 0.6
    assert set(hp34["capabilities"]) == {"linear_capacitor", "tight_metal"}
    assert hp34["magic"]["bundled_historical_style"] == "SCN12LC(HP)"

    cwl = processes["ami_cwl"]
    assert cwl["mosis_codes"] == ["SCNPC"]
    assert set(cwl["capabilities"]) == {"poly_capacitor", "tight_metal"}
    assert "SCNLC" not in cwl["mosis_codes"]

    cmos26b = processes["hp_cmos26b_legacy"]
    assert cmos26b["lambda_um"] == 0.5
    assert cmos26b["capabilities"] == ["metal3", "tight_metal"]
    assert cmos26b["magic"]["rich_pex"] is True
    assert cmos26b["magic"]["exact_process_alias"] is False

    cmos26g_standard = processes["hp_cmos26g"]
    assert cmos26g_standard["feature_size_um"] == 0.8
    assert cmos26g_standard["mosis_codes"] == ["SCN3M", "SCN"]
    assert cmos26g_standard["magic"]["exact_process_alias"] is True
    assert cmos26g_standard["magic"]["archive_header_target_label"] == "HPcmos26g"

    cmos26g = processes["hp_cmos26g_subm"]
    assert cmos26g["rule_family"] == "scmos_subm"
    assert cmos26g["lambda_um"] == 0.4
    assert cmos26g["magic"]["exact_process_alias"] is True
    assert "SCN3M_SUBM.40.HP.tech27" in cmos26g["magic"]["archive_2002a_techfile"]

    mos14 = processes["hp_mos14tb"]
    mos14_subm = processes["hp_mos14tb_subm"]
    assert "SCN3MLC" in mos14["mosis_codes"]
    assert "SCN3MLC_SUBM" in mos14_subm["mosis_codes"]
    assert mos14["magic"]["exact_process_alias"] is True
    assert mos14_subm["magic"]["exact_process_alias"] is True

    gmos10 = processes["hp_gmos10qa"]
    gmos10_subm = processes["hp_gmos10qa_subm"]
    assert gmos10["mosis_codes"] == ["SCN4N"]
    assert gmos10["magic"]["exact_archive_techfile"] is False
    assert gmos10_subm["mosis_codes"] == ["SCN4M_SUBM"]
    assert gmos10_subm["magic"]["exact_process_alias"] is False
    assert gmos10_subm["magic"]["backend_header_target_label"] == "TSMC35"

    layers = {entry["name"]: entry for entry in matrix["layers"]}
    expected_layers = {
        "mems_open": (23, "COP"),
        "mems_etch_stop": (24, "CPS"),
        "poly_cap1": (28, "CPC"),
        "silicide_block": (29, "CSB"),
        "via3": (30, "CVT"),
        "metal4": (31, "CMQ"),
        "via2": (61, "CVS"),
        "metal3": (62, "CMT"),
        "thick_active": (60, "CTA"),
        "cap_well": (59, "CWC"),
        "buried_ccd": (57, "CCD"),
        "pbase": (58, "CBA"),
        "electrode": (56, "CEL"),
    }
    assert set(layers) == set(expected_layers)
    for name, (gds_layer, cif) in expected_layers.items():
        assert layers[name]["gds_layer"] == gds_layer
        assert layers[name]["cif"] == cif

    pex = matrix["magic_pex_method"]
    assert {
        "planeorder",
        "resist",
        "contact",
        "areacap",
        "overlap",
        "perimc",
        "sideoverlap",
        "sidewall",
        "fet",
        "fetresis",
        "device",
    } <= set(pex["directive_families"])
    assert any("MODEL HANDLES THIS" in note for note in pex["ownership_rules"])
    assert pex["native_units"]["lambda"] == "centimicron"

    pex_references = {entry["id"]: entry for entry in matrix["magic_pex_references"]}
    assert pex_references["orbit20_scna20_legacy"]["measured_run"] == "n34o"
    assert pex_references["hp_cmos26b_scn08"]["sheet_resistance"]["metal3"] == 29
    assert pex_references["hp_cmos26g_subm_2002a_rich"]["extra_methods"][0]["stacked_contact"] == "m123c"
    assert pex_references["hp_mos14tb_subm_scn3mlc"]["capacitor_methods"]["cwell_area"] == 9.09
    assert pex_references["hp_gmos10qa_subm_backend_only"]["exact_process_match"] is False

    print(f"Historical SCMOS matrix: PASS ({len(EXPECTED_PROCESSES)} reference families)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
