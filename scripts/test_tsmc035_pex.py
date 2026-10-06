#!/usr/bin/env python3
"""Verify the TSMC 0.35um Mixed-Signal 2P4M Polycide 3.3/5V (TSRI D35) port.

Covers:
  * layer/process identity and the historical SCMOS GDS map provenance
  * PEX v0 (mosis_wat_rc): arithmetic, coefficient refusals, cross-check
  * PEX v1 (field_solver_estimated): sweep contract + BEOL fit fields
  * SPICE model cards (local N88Y first-hand)
  * process_ir collateral capabilities and option separation

Every assertion is about *honesty boundaries* as much as numbers: the test fails
if an unverified external set silently becomes the default, if a missing
coefficient is guessed, or if any flow claims signoff.
"""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
for path in (str(ROOT), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import yamlish  # noqa: E402

from common.pex.field_solver import canonical_sweep_manifest  # noqa: E402
from common.pex.wat_rc import (  # noqa: E402
    CouplingPair,
    WatRcError,
    WireSegment,
    build_wat_rc_report,
    compare_coupling,
    compare_sets,
    select_set,
)
from common.process_ir import load_process  # noqa: E402

PROFILE = "tsmc035_4m2p"
PROFILE_DIR = ROOT / "profiles" / PROFILE


def load(path: Path) -> dict:
    value = yamlish.load(path.read_text())
    assert isinstance(value, dict), f"{path}: expected a mapping"
    return value


def approx(actual: float, expected: float, tol: float = 1e-6) -> None:
    assert abs(actual - expected) <= tol, f"{actual} != {expected} (tol {tol})"


def layer_map(layers_doc: dict) -> dict:
    out = {}
    for entry in layers_doc["layers"]:
        out[entry["name"]] = [g["layer"] for g in entry["gds"]]
    return out


def check_identity_and_layers() -> dict:
    process = load_process(PROFILE, ROOT)
    meta = process.meta
    assert meta["process"] == "TSMC_CMOS035_4M2P"
    assert meta["mosis_code"] == "SCN4ME_SUBM"
    assert meta["lambda_um"] == 0.2
    assert meta["grid_um"] == 0.1
    assert meta["model_prefix"] == "tsmc35"
    assert meta["rule_family"] == "scmos_subm"
    assert meta["well_type"] == "n"
    features = meta["features"]
    for flag in ("metal3Available", "metal4Available", "elecAvailable", "hvAvailable"):
        assert features[flag] is True, f"{flag} must be true for the 4M2P option"
    for flag in ("metal5Available", "metal6Available", "polycapAvailable"):
        assert features[flag] is False, f"{flag} must be false for the 4M2P option"

    gds = layer_map(load(PROFILE_DIR / "layers.yaml"))
    expected = {
        "nwell": [42],
        "active": [43],
        "pselect": [44],
        "nselect": [45],
        "poly": [46],
        "elec": [56],
        "cc": [25, 47, 48, 55],
        "metal1": [49],
        "via": [50],
        "metal2": [51],
        "glass": [52],
        "tactive": [60],
        "via2": [61],
        "metal3": [62],
        "via3": [30],
        "metal4": [31],
        "pad": [26],
        "DEEP_N_WELL": [38],
    }
    for name, numbers in expected.items():
        assert name in gds, f"layer {name} missing from layers.yaml"
        assert gds[name] == numbers, f"{name}: {gds[name]} != {numbers}"
    return process


def check_gds_layer_map_provenance() -> None:
    doc = load(PROFILE_DIR / "gds_layer_map.yaml")
    assert doc["format"] == "GDSII"
    assert doc["source"]["historical_submission_map"] is True
    assert doc["source"]["tapeout_eligible"] is False
    policy = doc["gds_policy"]
    assert policy["public_map"]["authority"] == "historical_mosis_submission"
    assert policy["public_map"]["current_tsri_equivalence"] == "unverified"
    assert policy["public_map"]["tapeout_authority"] is False
    assert policy["datatype"]["value"] == 0
    assert policy["datatype"]["authority"] == "siliconcraft_convention"
    assert policy["purpose_matrix"]["status"] == "unavailable"
    assert doc["current_foundry_map"]["status"] == "unavailable"
    assert doc["current_foundry_map"]["tapeout_eligible"] is False

    # The provenance map must agree with the generated layer fragment.
    gds = layer_map(load(PROFILE_DIR / "layers.yaml"))
    for entry in doc["layers"]:
        name = entry["logical_name"]
        if name in gds:
            assert entry["gds_layer"] in gds[name], (
                f"gds_layer_map {name}={entry['gds_layer']} not in layers.yaml {gds[name]}"
            )

    contacts = doc["contact_compatibility"]
    assert contacts["canonical"] == {"logical_name": "cc", "gds_layer": 25}
    aliases = {item["gds_layer"]: item for item in contacts["legacy_aliases"]}
    assert set(aliases) == {47, 48, 55}
    assert all(item["physical_cut"] is False for item in aliases.values())

    semantics = doc["tsmc_specific_semantics"]
    assert semantics["tactive"]["gds_layer"] == 60
    assert semantics["elec"]["gds_layer"] == 56


def check_pex_v0(process) -> None:
    reference = load(PROFILE_DIR / "pex" / "tsmc035_wat_reference.yaml")
    manifest = process.pex_doc

    # The 4-metal MM_EPI set is the declared D35 reference; LO_EPI never is.
    assert reference["d35_reference_set"] == "t2af_mm_epi_4m"
    assert reference["capability_separation"]["rule"]
    sets = reference["coefficient_sets"]
    for name, dataset in sets.items():
        assert dataset["provenance"]["authority"], f"{name}: missing authority"
        assert dataset["provenance"].get("verification_status"), name
    assert sets["n88y_scn035h_3m"]["provenance"]["verification_status"] == (
        "verified_local_report"
    )
    for name in ("t2af_mm_epi_4m", "t59n_mm_epi_4m", "t19p_lo_epi_4m"):
        assert sets[name]["provenance"]["verification_status"] == (
            "not_reverified_offline"
        )
    assert sets["t2af_mm_epi_4m"]["provenance"]["process_option"] == "MM_EPI"
    assert sets["t19p_lo_epi_4m"]["provenance"]["process_option"] == "LO_EPI"

    # --- arithmetic -------------------------------------------------------
    report = build_wat_rc_report(
        manifest,
        reference,
        [
            # pure wire: 0.07 * 100 / 0.6
            WireSegment(layer="metal1", length_um=100.0, width_um=0.6),
            # wire + 1 via
            WireSegment(
                layer="metal2", length_um=50.0, width_um=0.6,
                vias=1, via_target="via",
            ),
            # diffusion + 2 contacts: 79.4 * 10 / 0.6 + 2 * 62.7
            WireSegment(
                layer="nactive", length_um=10.0, width_um=0.6,
                contacts=2, contact_target="nactive",
            ),
        ],
        [
            # 38 * 100 + 58 * 50
            CouplingPair(lower="metal1", upper="metal2",
                         overlap_area_um2=100.0, edge_length_um=50.0),
        ],
    )
    assert report["pex_profile"] == "mosis_wat_rc"
    assert report["coefficient_set"] == "t2af_mm_epi_4m"
    assert report["coefficient_set_verification"] == "external_unverified"
    assert report["calibrated_to_current_d35"] is False
    assert report["signoff"] is False

    segments = report["segments"]
    approx(segments[0]["resistance_ohm"], 0.07 * 100.0 / 0.6)
    approx(segments[1]["wire_resistance_ohm"], 0.07 * 50.0 / 0.6)
    approx(segments[1]["via_resistance_ohm"], 1.24)
    approx(segments[1]["resistance_ohm"], 0.07 * 50.0 / 0.6 + 1.24)
    approx(segments[2]["wire_resistance_ohm"], 79.4 * 10.0 / 0.6)
    approx(segments[2]["contact_resistance_ohm"], 2 * 62.7)
    approx(segments[2]["resistance_ohm"], 79.4 * 10.0 / 0.6 + 2 * 62.7)

    approx(report["resistance_ohm"], sum(s["resistance_ohm"] for s in segments))
    approx(report["contact_resistance_ohm"], 2 * 62.7)
    approx(report["via_resistance_ohm"], 1.24)
    assert report["excluded_terms"]["substrate_network"] == "excluded_and_unavailable"

    coupling = report["coupling"][0]
    approx(coupling["area_capacitance_aF"], 38 * 100.0)
    approx(coupling["fringe_capacitance_aF"], 58 * 50.0)
    approx(coupling["capacitance_aF"], 38 * 100.0 + 58 * 50.0)

    # A locally verified set produces the verified label.
    local = build_wat_rc_report(
        manifest, reference,
        [WireSegment(layer="metal1", length_um=10.0, width_um=0.6)],
        coefficient_set="n88y_scn035h_3m",
    )
    assert local["coefficient_set_verification"] == "verified_local_report"
    assert local["signoff"] is False

    # --- refusals: a missing coefficient is never guessed -----------------
    def refuses(segments=(), pairs=(), set_name=None, doc=None):
        try:
            build_wat_rc_report(
                manifest, doc if doc is not None else reference,
                segments, pairs, coefficient_set=set_name,
            )
        except WatRcError:
            return
        raise AssertionError("expected WatRcError")

    # metal5 is not a resistance layer of this process
    refuses([WireSegment(layer="metal5", length_um=10.0, width_um=0.6)])
    # metal1 has no contact coefficient in the WAT sets
    refuses([WireSegment(layer="metal1", length_um=10.0, width_um=0.6,
                         contacts=1, contact_target="metal1")])
    # N88Y (3-metal) has no metal4 sheet resistance
    refuses([WireSegment(layer="metal4", length_um=10.0, width_um=0.6)],
            set_name="n88y_scn035h_3m")
    # N88Y has no via3
    refuses([WireSegment(layer="metal2", length_um=10.0, width_um=0.6,
                         vias=1, via_target="via3")], set_name="n88y_scn035h_3m")
    # N88Y has no M2-M4 coupling entry
    refuses(pairs=[CouplingPair(lower="metal2", upper="metal4",
                                overlap_area_um2=1.0, edge_length_um=1.0)],
            set_name="n88y_scn035h_3m")
    # an unknown coefficient set
    refuses([WireSegment(layer="metal1", length_um=1.0, width_um=1.0)],
            set_name="does_not_exist")
    # a coefficient set without provenance
    refuses(
        [WireSegment(layer="metal1", length_um=1.0, width_um=1.0)],
        set_name="noprov",
        doc={"coefficient_sets": {"noprov": {"sheet_resistance_ohm_sq": {"metal1": 1.0}}}},
    )
    # a via count without an explicit target
    refuses([WireSegment(layer="metal1", length_um=1.0, width_um=1.0, vias=1)])

    # --- recorded cross-check must reproduce ------------------------------
    recorded = reference["cross_check"]["deltas_percent"]
    sheet = compare_sets(
        reference, "n88y_scn035h_3m", "t2af_mm_epi_4m",
        [
            ("sheet_resistance_ohm_sq", "nactive", "nactive"),
            ("sheet_resistance_ohm_sq", "pactive", "pactive"),
            ("sheet_resistance_ohm_sq", "poly", "poly"),
            ("sheet_resistance_ohm_sq", "elec", "elec"),
            ("sheet_resistance_ohm_sq", "metal1", "metal1"),
            ("sheet_resistance_ohm_sq", "metal2", "metal2"),
            ("sheet_resistance_ohm_sq", "nwell", "nwell"),
        ],
    )
    for key in ("nactive", "pactive", "poly", "elec", "metal1", "metal2", "nwell"):
        assert sheet["deltas_percent"][key] == recorded["sheet_resistance_ohm_sq"][key], (
            f"recorded sheet-resistance delta for {key} is stale"
        )
    contact = compare_sets(
        reference, "n88y_scn035h_3m", "t2af_mm_epi_4m",
        [
            ("contact_resistance_ohm", "nactive", "nactive"),
            ("contact_resistance_ohm", "pactive", "pactive"),
            ("contact_resistance_ohm", "poly", "poly"),
            ("contact_resistance_ohm", "elec", "elec"),
            ("via_resistance_ohm", "via", "via"),
            ("via_resistance_ohm", "via2", "via2"),
        ],
    )
    for key in ("nactive", "pactive", "poly", "elec"):
        assert contact["deltas_percent"][key] == recorded["contact_resistance_ohm"][key]
    assert contact["deltas_percent"]["via"] == recorded["via_resistance_ohm"]["via"]
    assert contact["deltas_percent"]["via2"] == recorded["via_resistance_ohm"]["via2"]

    coupling = compare_coupling(
        reference, "n88y_scn035h_3m", "t2af_mm_epi_4m",
        ["metal1-metal2", "metal1-metal3", "metal2-metal3"],
    )
    for pair in ("metal1-metal2", "metal1-metal3", "metal2-metal3"):
        for field_name in ("area", "fringe"):
            key = f"{pair}.{field_name}"
            assert coupling["deltas_percent"][key] == (
                recorded["capacitance_coupling"][pair][field_name]
            ), f"recorded coupling delta {key} is stale"

    # the top-metal tier mapping is the structural corroboration
    top = reference["cross_check"]["top_metal_mapping"]
    assert top["confidence"] == "high"
    assert sets["n88y_scn035h_3m"]["sheet_resistance_ohm_sq"]["metal3"] == (
        sets["t2af_mm_epi_4m"]["sheet_resistance_ohm_sq"]["metal4"]
    )


def check_pex_v1(process) -> None:
    manifest = process.pex_doc
    sweep = canonical_sweep_manifest(manifest, profile_name="field_solver_estimated")
    assert sweep["profile"] == PROFILE
    assert sweep["calibrated"] is False
    assert sweep["signoff"] is False
    assert len(sweep["patterns"]) == 7
    assert sweep["solver_candidates"]
    fit_path = PROFILE_DIR / "pex" / sweep["beol_fit"]
    assert fit_path.exists(), f"missing BEOL fit {fit_path}"

    fit = load(fit_path)
    assert fit["calibrated"] is False
    assert fit["signoff"]["foundry_qrc"] is False
    assert fit["signoff"]["tapeout_qualification"] is False
    for field_name in (
        "metal_thickness_um",
        "ild_thickness_um",
        "ild_relative_permittivity",
    ):
        assert field_name in fit["fit_parameters"], f"missing fit field {field_name}"
    assert fit["official_cross_section"]["metal_thickness_um"]["metal4"] == 0.925
    assert fit["fit_target"]["acceptance_band_percent"] == 15


def check_spice(process) -> None:
    lib = (PROFILE_DIR / "models" / "tsmc035_4m2p.lib").read_text()
    assert ".lib tsmc035_4m2p" in lib
    assert ".endl tsmc035_4m2p" in lib
    assert "run N88Y" in lib, "shipped cards must retain the N88Y run provenance"
    for model in ("tsmc35N", "tsmc35P"):
        assert f".MODEL {model} " in lib or f".MODEL {model}(" in lib, model
    assert "TOX     = 7.6E-9" in lib, "N88Y TOX must be preserved"

    maturity = load(PROFILE_DIR / "model_maturity.yaml")
    assert maturity["process_maturity"]["level"] == "L1"
    assert maturity["process_maturity"]["pex"]["calibrated"] is False
    assert maturity["process_maturity"]["pex"]["signoff"] is False
    for model in ("tsmc35N", "tsmc35P"):
        record = maturity["models"][model]
        assert record["run"] == "N88Y"
        assert record["fit_status"] == "local_first_hand_measured"
    reference_model = maturity["models"]["tsmc035_mosis_mm_epi_reference"]
    assert reference_model["calibrated_to_current_d35"] is False
    assert reference_model["fit_status"] == "historical_reference_not_reverified"
    for withheld in ("tsmc035_hv", "tsmc035_poly2_cap"):
        assert maturity["models"][withheld]["simulator"] is None
        assert maturity["models"][withheld]["representation"] == "contract_only"


def check_capabilities(process) -> None:
    caps = process.collateral_capabilities
    assert caps.drc is True
    assert caps.lvs is True
    assert caps.model is True
    assert caps.xschem is True
    assert caps.pex_topology is False
    assert caps.pex_runtime is False
    assert caps.pex_rc == "historical_measured_rc", caps.pex_rc


def check_option_separation() -> None:
    reference = load(PROFILE_DIR / "pex" / "tsmc035_wat_reference.yaml")
    # A LO_EPI set must never be selectable as the default 4M reference.
    assert reference["d35_reference_set"] != "t19p_lo_epi_4m"
    lo = reference["coefficient_sets"]["t19p_lo_epi_4m"]
    mm = reference["coefficient_sets"]["t2af_mm_epi_4m"]
    assert lo["sheet_resistance_ohm_sq"]["nactive"] < 10.0
    assert mm["sheet_resistance_ohm_sq"]["nactive"] > 70.0
    assert "never be blended" in reference["capability_separation"]["rule"]
    # provenance must record the offline verification gap
    sources = load(PROFILE_DIR / "sources.yaml")
    assert sources["requester_supplied_external"]["verification_status"] == (
        "not_reverified_offline"
    )
    assert sources["gds_stream_map"]["current_tsri_map_status"] == "unavailable"
    assert sources["gds_stream_map"]["tapeout_eligible"] is False


def check_no_block_scalars() -> None:
    """yamlish silently drops everything after a `|`/`>` block scalar.

    Guard the profile against that failure mode, which would otherwise let a
    truncated document pass a shallow parse.
    """

    import re

    marker = re.compile(r":\s*(\|-?|\+?\|[0-9-]*|>-?|\+?>[0-9-]*)\s*$")
    offenders = []
    for path in sorted(PROFILE_DIR.rglob("*.yaml")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if marker.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert not offenders, (
        "yamlish does not support block scalars; these would truncate the "
        f"document: {offenders}"
    )


def main() -> int:
    check_no_block_scalars()
    process = check_identity_and_layers()
    check_gds_layer_map_provenance()
    check_pex_v0(process)
    check_pex_v1(process)
    check_spice(process)
    check_capabilities(process)
    check_option_separation()
    print("TSMC 0.35um 4M2P (D35) port checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
