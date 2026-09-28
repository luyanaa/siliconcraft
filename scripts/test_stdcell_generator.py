#!/usr/bin/env python3
"""Exercise the first transistor-to-candidate stdcell generation stage."""

from __future__ import annotations

from dataclasses import replace

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.stdcell.columns import enumerate_column_ir  # noqa: E402
from common.stdcell.compaction import DifferenceConstraint, Feature, compact_linear  # noqa: E402
from common.stdcell.netlist import parse_spice  # noqa: E402
from common.stdcell.planner import generate_candidates  # noqa: E402
from common.stdcell.process import StdcellProcess  # noqa: E402
from common.stdcell.pareto import dominates, pareto_front, rank_geometry  # noqa: E402
from common.stdcell.topology import pin_permutations, topology_options  # noqa: E402
from common.stdcell.routing import (  # noqa: E402
    NegotiatedRouter,
    RoutingGraph,
    RoutingNode,
    RoutingPolicy,
)


FIXTURES = ROOT / "common/tests/spice/stdcell"


def load_fixture(name: str):
    return parse_spice((FIXTURES / f"{name}.spice").read_text())


def main() -> int:
    process = StdcellProcess.load("ami06", ROOT)
    inv = load_fixture("inv")
    nand2 = load_fixture("nand2")
    nor2_drc = load_fixture("nor2_drc")
    nor2 = load_fixture("nor2")
    optimization_hints = load_fixture("optimization_hints")
    columns = enumerate_column_ir(nand2, process, limit=8)
    assert columns
    assert columns[0].gate_mismatches == 0
    assert columns[0].diffusion_breaks == 0
    assert [column.kind for column in columns[0].columns] == ["gate", "diffusion", "gate"]

    compacted = compact_linear(
        (Feature("A", 1.0, "gate"), Feature("B", 1.0, "gate")),
        (DifferenceConstraint("A", "B", 2.0, "gate_spacing"),),
    )
    assert compacted.coordinates_um["B"] - compacted.coordinates_um["A"] >= 2.0
    assert compacted.width_um == 4.0

    policy_2m = RoutingPolicy.for_architecture("two_metal_classic")
    graph_2m = RoutingGraph.rectangular(
        (0.0, 1.0, 2.0),
        (0.0, 1.0, 2.0),
        ("M1", "M2"),
        policy_2m,
    )
    route = graph_2m.route_two_terminal(
        (RoutingNode(0.0, 0.0, "M1"),),
        (RoutingNode(2.0, 2.0, "M1"),),
    )
    assert route

    negotiated = NegotiatedRouter(graph_2m, max_iterations=8).route(
        {
            "N0": (
                (RoutingNode(0.0, 0.0, "M1"),),
                (RoutingNode(2.0, 2.0, "M1"),),
            ),
            "N1": (
                (RoutingNode(0.0, 0.0, "M1"),),
                (RoutingNode(2.0, 2.0, "M1"),),
            ),
        }
    )
    assert set(negotiated) == {"N0", "N1"}
    assert all(negotiated[name] for name in negotiated)
    p_graph = nand2.diffusion_graph("p", process.model_names)
    n_graph = nand2.diffusion_graph("n", process.model_names)
    assert {device.name for device in p_graph.devices} == {"MP0", "MP1"}
    assert {device.name for device in n_graph.devices} == {"MN0", "MN1"}
    assert policy_2m.global_layer == "M2"
    policy_3m = RoutingPolicy.for_architecture("three_metal_classic")
    assert policy_3m.global_layer == "M3"
    assert policy_3m.layer_cost["M2"] < policy_3m.layer_cost["M3"]


    assert inv.timing_arcs == (("A", "Y"),)
    assert inv.internal_nets == ()
    assert len(generate_candidates(inv, process, "two_metal_classic")) == 3
    assert len(generate_candidates(nand2, process, "two_metal_classic")) == 36
    assert len(generate_candidates(nor2, process, "two_metal_classic")) == 36

    classic = generate_candidates(inv, process, "two_metal_classic", max_candidates=1)[0]
    assert classic.feedthrough_layer == "M2"
    assert len(classic.feedthrough_columns) >= 1
    assert classic.metrics["internal_m2_length_um"] == 0
    assert classic.constraints["internal_m2_within_limit"] is True
    assert classic.constraints["feedthrough_required"] is True
    assert {placement.polarity for placement in classic.placements} == {"n", "p"}
    assert classic.height_um > classic.width_um
    assert classic.metrics["worst_case_delay"] is None
    assert classic.metrics["input_capacitance"] is None
    assert classic.orientation_policy["mode"] == "alternate_rows"
    assert classic.constraints["rail_contract"]["fixed_height"] is True

    nand2_plan = generate_candidates(nand2, process, "two_metal_classic", max_candidates=1)[0]
    nand2_manifest = nand2_plan.as_dict()
    assert nand2_manifest["topology"]["physical_diffusion_sharing"] is True
    assert nand2_plan.metrics["diffusion_breaks"] == 0
    assert nand2_plan.metrics["gate_mismatches"] == 0
    assert nand2_plan.metrics["aligned_gate_columns"] == 2
    assert nand2_plan.metrics["contactless_internal_diffusion_count"] >= 1
    assert any(
        bridge["purpose"] == "shared_diffusion"
        for bridge in nand2_manifest["geometry"]["diffusion_bridges"]
    )
    assert any(
        "right" in device["contactless_sides"] or "left" in device["contactless_sides"]
        for device in nand2_manifest["devices"]
    )
    assert nand2_plan.supply_contact_plan
    assert all(
        item["status"] == "geometry_candidate_only"
        and item["current_capacity_per_contact"] is None
        for item in nand2_plan.supply_contact_plan
    )
    capacity_process = replace(
        process,
        ir=replace(
            process.ir,
            meta={
                **process.ir.meta,
                "supply_contact_capacity": {"VDD": 1.0, "VSS": 1.0},
                "supply_current_demand": {"VDD": 2.0, "VSS": 1.0},
            },
        ),
    )
    capacity_plan = generate_candidates(
        nand2, capacity_process, "two_metal_classic", max_candidates=1
    )[0]
    vdd_plan = next(item for item in capacity_plan.supply_contact_plan if item["net"] == "VDD")
    assert vdd_plan["required_contact_count"] == 2
    assert vdd_plan["contact_count"] >= 2
    assert vdd_plan["capacity_sufficient"] is True
    assert vdd_plan["status"] == "capacity_checked"
    assert nand2_plan.pin_permutations == (("A", "B"),)
    assert pin_permutations(optimization_hints) == (("A", "B"), ("B", "A"))
    assert [option.kind for option in topology_options(optimization_hints)] == [
        "aoi_oai",
        "static_cmos",
        "transmission_gate",
    ]
    hinted_candidates = generate_candidates(
        optimization_hints,
        process,
        "two_metal_classic",
        max_candidates=100,
    )
    assert {candidate.sizing_variant["scale"] for candidate in hinted_candidates} == {1.0, 2.0}
    long_l = [
        candidate
        for candidate in hinted_candidates
        if candidate.sizing_variant["scale"] == 2.0
    ][0]
    assert next(
        placement.length_um
        for placement in long_l.placements
        if placement.device.name == "MN0"
    ) == 1.2
    assert long_l.as_dict()["topology"]["topology_candidates"][0]["kind"] == "aoi_oai"

    three_metal = generate_candidates(nand2, process, "three_metal_classic", max_candidates=1)[0]
    assert three_metal.feedthrough_layer == "M3"
    assert len(three_metal.feedthrough_columns) >= 1
    assert all(access["layer"] == "M2" for access in three_metal.pin_access.values())
    assert three_metal.constraints["feedthrough_required"] is True
    nor2_three_metal = generate_candidates(
        nor2_drc, process, "three_metal_classic", max_candidates=1
    )[0]
    assert nor2_three_metal.feedthrough_layer == "M3"
    assert (
        any(
            edge["layer"] == "M2"
            for edge in nor2_three_metal.graph_routes.get("NINT", ())
            if edge["kind"] == "wire"
        )
        or any(
            bridge["net"] == "NINT"
            for bridge in nor2_three_metal.as_dict()["geometry"]["diffusion_bridges"]
        )
    )

    beam = generate_candidates(
        nand2,
        process,
        "two_metal_classic",
        max_candidates=12,
        beam_width=3,
    )
    assert len(beam) == 3
    assert all(
        candidate.metrics["routing_estimate"]["status"] == "pre_route_estimate"
        for candidate in beam
    )
    assert all(candidate.route_conflicts == () for candidate in beam)

    pareto_candidates = [
        {
            "candidate_index": 10,
            "metrics": {
                "cell_area_um2": 10,
                "internal_m2_length_um": 4,
                "via_count": 2,
                "feedthrough_count": 1,
            },
        },
        {
            "candidate_index": 11,
            "metrics": {
                "cell_area_um2": 12,
                "internal_m2_length_um": 3,
                "via_count": 1,
                "feedthrough_count": 1,
            },
        },
        {
            "candidate_index": 12,
            "metrics": {
                "cell_area_um2": 14,
                "internal_m2_length_um": 5,
                "via_count": 3,
                "feedthrough_count": 2,
            },
        },
    ]
    assert dominates(pareto_candidates[0], pareto_candidates[2])
    assert pareto_front(pareto_candidates) == (0, 1)
    assert rank_geometry(pareto_candidates)["front_candidate_indices"] == [10, 11]

    manifest = classic.as_dict()
    assert manifest["status"] == "geometry_planned"
    assert manifest["topology"]["physical_diffusion_sharing"] is False
    assert manifest["routing"]["feedthrough_columns_um"]
    assert manifest["routing"]["graph_routes"]["Y"]
    assert manifest["verification"] == {"drc": "not_run", "lvs": "not_run", "pex": "not_run"}

    print("Stdcell candidate planner: PASS (AMI06 INV/NAND2/NOR2, 2M/3M routing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
