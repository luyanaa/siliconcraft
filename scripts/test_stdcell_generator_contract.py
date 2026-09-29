#!/usr/bin/env python3
"""Validate the stdcell architecture and implemented-backend contract."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402


EXPECTED_CELLS = ["inv", "nand2", "nor2", "aoi21", "oai21", "mux2"]
EXPECTED_LIFECYCLE = [
    "topology_normalize",
    "enumerate_orderings_and_diffusion_breaks",
    "enumerate_folding",
    "exact_geometry_compaction",
    "generate_internal_routing_candidates",
    "drc",
    "lvs",
    "pex",
    "spice_characterization",
    "pareto_filter",
]


def main() -> int:
    path = ROOT / "schema/stdcell_generator_contract.yaml"
    contract = yamlish.load(path.read_text())

    assert contract["schema_version"] == 1
    assert contract["kind"] == "stdcell_generator_contract"
    assert contract["status"] == "architecture_contract"
    assert (ROOT / contract["readiness_contract"]).exists()

    policy = contract["policy"]
    assert policy["implementation"] == "geometry_candidate_planner"
    assert policy["first_backend_scope"] == "scmos_fixed_height"
    assert policy["supported_profiles"] == [
        "ami06",
        "ami16",
        "hp06",
        "cnm25",
        "ams_c35",
        "tr1um",
    ]
    assert policy["solver_escalation"] == "exhaustive_first_then_constraint_solver"
    assert "buried_or_local_interconnect" in policy["unsupported_assumptions"]

    api = contract["api"]
    assert set(api) == {"cell_circuit", "process", "architecture", "candidate"}
    assert api["cell_circuit"]["initial_cell_families"] == EXPECTED_CELLS
    assert api["cell_circuit"]["missing_l_policy"] == (
        "preserve_explicit_or_default_to_process_lmin"
    )
    assert api["process"]["source_of_truth"] == "ProcessIR"
    assert api["architecture"]["default_cell_structure"]["rows"] == ["pmos", "nmos"]
    assert api["candidate"]["lifecycle"] == EXPECTED_LIFECYCLE

    search = contract["search"]
    assert search["initial_method"] == "exhaustive_enumeration_then_pareto_beam"
    assert search["device_variables"]["nf"]["values"] == "row_active_capacity_derived"
    assert search["device_variables"]["l"]["optimize_initially"] is False
    assert search["folding"]["every_folding_is_a_candidate"] is True
    assert search["compaction"]["method"] == "difference_constraints_longest_path"
    assert search["compaction"]["milp_required_for_initial_cells"] is False
    assert search["routing"]["primary_layer"] == "grammar_compiled"
    assert search["routing"]["secondary_layer"] == "grammar_compiled"
    assert search["routing"]["pattern_order"] == [
        "straight",
        "L",
        "Z",
        "A_star_maze",
        "negotiated_congestion_rip_up_reroute",
    ]
    assert search["routing"]["multi_terminal"] == "manhattan_mst_plus_incremental_routes"

    resources = contract["routing_resource_contract"]
    physical = resources["physical_interpretation"]
    assert physical["metal_over_active_is_allowed"] is True
    assert physical["buried_or_local_interconnect"] == "unsupported_by_default"
    assert resources["conductor_hierarchy"]["diffusion"]["ordinary_routing"] == "forbidden"
    assert resources["conductor_hierarchy"]["poly"]["ordinary_intercell_routing"] == "forbidden"
    assert resources["conductor_hierarchy"]["M2"]["preserve_for_external_routing"] is True

    architectures = resources["architectures"]
    classic = architectures["two_metal_classic"]
    dense = architectures["two_metal_dense"]
    assert classic["preserve_m2_feedthrough"] is True
    assert classic["min_feedthrough_tracks"] >= 1
    assert classic["internal_m2_policy"] == "limited"
    assert classic["max_internal_m2_segments_for_combinationals"] <= 2
    assert dense["preserve_m2_feedthrough"] is False
    assert dense["internal_m2_policy"] == "allowed_with_blockage_accounting"
    three_metal = architectures["three_metal_classic"]
    assert three_metal["global_routing_layer"] == "M3"
    assert three_metal["preserve_m2_feedthrough"] is False
    assert three_metal["preserve_m3_feedthrough"] is True
    assert three_metal["min_global_feedthrough_tracks"] >= 1
    assert three_metal["complex_cells_may_use_internal_m2"] is True
    assert "m3_feedthrough_columns" in resources["routing_resource_outputs"]
    assert "m2_feedthrough_columns" in resources["routing_resource_outputs"]

    evaluation = contract["candidate_evaluation"]
    for constraint in ("drc_clean", "lvs_clean", "pin_access_legal", "routing_contract_satisfied"):
        assert constraint in evaluation["hard_constraints"]
    assert evaluation["required_stage_order"] == [
        "drc",
        "lvs",
        "pex",
        "spice_characterization",
    ]
    assert evaluation["timing"]["standard_load_points"] == ["FO1", "FO2", "FO4"]
    for metric in ("cell_area", "worst_case_delay", "input_capacitance", "route_permeability"):
        assert metric in evaluation["metrics"]
    assert evaluation["pareto"]["dominated_candidates_are_removed"] is True
    assert evaluation["drive_variants"]["physical_ratio_is_not_fixed"] is True

    block = contract["block_evaluation"]
    assert block["required_after_cell_pareto"] is True
    assert block["tool"] == "OpenROAD"
    assert block["baseline"]["type"] == "fixed_lambda_geometry_and_fixed_wp_wn_ratio"
    assert block["selection_rule"] == "retain_block_level_non_dominated_libraries"

    outputs = contract["outputs"]
    for artifact in ("layout_gds", "extracted_spice", "drc_report", "lvs_report", "pex_report"):
        assert artifact in outputs["candidate_artifacts"]
    assert outputs["library_artifacts_after_signoff_inputs_exist"] == [
        "lef",
        "liberty",
        "cell_catalog",
    ]

    print("Stdcell generator architecture contract: PASS (architecture-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
