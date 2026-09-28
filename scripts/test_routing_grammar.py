#!/usr/bin/env python3
"""Deterministic tests for routing grammar inference and router compilation."""

from __future__ import annotations

from dataclasses import replace

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402

from common.process_ir import load_process  # noqa: E402
from common.routing_grammar import (  # noqa: E402
    EXPERIMENTAL,
    FORBIDDEN,
    SUPPORTED,
    UNKNOWN,
    ConductorGrammar,
    Evidence,
    RoutingGrammar,
    inspect_lvs_connectivity,
    inspect_profile,
)
from common.routing_probes import (  # noqa: E402
    ProbeSpec,
    apply_probe_observation,
    classify_probe,
    default_probe_specs,
    local_rule_sweep_specs,
    native_feature_probe_specs,
)
from common.stdcell.routing import RoutingGraph, RoutingNode, RoutingPolicy  # noqa: E402
from run_routing_grammar import _summarize_sweeps  # noqa: E402


def grammar_fixture() -> RoutingGrammar:
    def conductor(name: str, status: str, cost: float) -> ConductorGrammar:
        return ConductorGrammar(
            name=name,
            continuity=Evidence(status=status, evidence=(f"fixture:{name}",)),
            regions={},
            connections={},
            electrical={"sheet_resistance": None},
            cost=cost,
        )

    m1 = conductor("M1", SUPPORTED, 1.0)
    m1 = ConductorGrammar(
        **{
            **m1.__dict__,
            "electrical": {
                "status": "characterized",
                "sheet_resistance_ohm_per_square": 100.0,
                "nominal_width_um": 1.0,
            },
            "max_useful_length_um": 1.5,
        }
    )
    m2 = conductor("M2", EXPERIMENTAL, 2.0)
    m3 = conductor("M3", EXPERIMENTAL, 3.0)
    m1 = ConductorGrammar(**{**m1.__dict__, "connections": {
        "M2": Evidence(status=SUPPORTED),
        "M3": Evidence(status=SUPPORTED),
    }})
    m2 = ConductorGrammar(**{**m2.__dict__, "connections": {"M1": Evidence(status=SUPPORTED)}})
    m3 = ConductorGrammar(**{**m3.__dict__, "connections": {"M1": Evidence(status=SUPPORTED)}})
    return RoutingGrammar(
        profile="fixture",
        source_kind="fixture",
        source_files=(),
        conductors={"M1": m1, "M2": m2, "M3": m3},
    )


def main() -> int:
    contract = yamlish.load((ROOT / "schema/routing_grammar_contract.yaml").read_text())
    assert contract["states"]["UNKNOWN"]["router_use"] == "forbidden_by_default"
    assert contract["native_gate_boundary"]["final_cell_gate_owns"] == [
        "authoritative_DRC",
        "full_LVS_or_Netgen_equivalence",
        "PEX_and_model_smoke",
    ]
    assert contract["evidence_fields"]["confidence"] == "one_of_high_medium_low_unknown"

    facts = inspect_lvs_connectivity(
        (ROOT / "fixtures/routing_grammar_fixture.lylvs").read_text(),
        source="fixtures/routing_grammar_fixture.lylvs",
    )
    assert facts["single_connect"] == ("M1",)
    assert facts["pair_connect"] == (("M1", "V1"),)
    assert facts["device_terminals"]["mos4"]["G"] == "M1"

    static = inspect_profile("ls1u", ROOT)
    assert static.source_kind == "klayout_lvs_static"
    assert static.conductors
    process = load_process("ami06", ROOT)
    ami_static = inspect_profile("ami06", ROOT)
    specs = default_probe_specs(process, ami_static)
    names = tuple(spec.name for spec in specs)
    assert names == tuple(spec.name for spec in default_probe_specs(process, ami_static))
    assert any(name.startswith("tee_") for name in names)
    assert any(name.startswith("isolation_") for name in names)
    assert any(name.startswith("over_active_") for name in names)
    sweeps = local_rule_sweep_specs(process, ami_static)
    assert tuple(spec.metadata["sweep"] for spec in sweeps[:5]) == ("width",) * 5
    assert any(spec.kind == "spacing" for spec in sweeps)
    assert any(spec.kind == "enclosure" for spec in sweeps)
    assert native_feature_probe_specs(process, ami_static) == ()
    feature_process = replace(
        process,
        meta={
            **process.meta,
            "native_probe_options": (
                "butting_contact",
                "alternate_contact_enclosure",
                "local_interconnect_shortcut",
            ),
            "butting_contact": {"source": "metal1", "target": "metal2"},
            "local_interconnect_layer": "elec",
        },
    )
    feature_specs = native_feature_probe_specs(feature_process, ami_static)
    assert any(spec.kind == "butting_contact" for spec in feature_specs)
    assert any(
        spec.metadata.get("native_feature") == "alternate_contact_enclosure"
        for spec in feature_specs
    )
    assert any(
        spec.name == "local_shortcut_elec"
        and spec.metadata.get("native_feature") == "local_interconnect_shortcut"
        for spec in feature_specs
    )
    sweep_summary = _summarize_sweeps(
        [
            {
                "conductor": "M1",
                "target": target,
                "metadata": {"sweep": "enclosure", "sweep_value_um": value},
                "classification": {"status": status},
            }
            for target, statuses in (
                ("M2", ("FORBIDDEN", "SUPPORTED")),
                ("M3", ("FORBIDDEN", "FORBIDDEN")),
            )
            for value, status in zip((0.0, 0.3), statuses)
        ]
    )
    assert sweep_summary["M1:enclosure:M2"]["monotonic"] is True
    assert sweep_summary["M1:enclosure:M3"]["monotonic"] is None

    wire = ProbeSpec(name="wire", kind="wire", conductor="M1")
    assert classify_probe(wire, drc="pass", lvs="pass", port_nets={"A": "n0", "B": "n0"}).confidence == "high"
    assert classify_probe(wire, drc="pass", lvs="pass", port_nets={"A": "n0", "B": "n0"}).status == SUPPORTED
    isolated = ProbeSpec(name="iso", kind="isolated_crossing", conductor="M1", target="M2", labels=("A", "B", "C", "D"), expected="isolated")
    assert classify_probe(isolated, drc="pass", lvs="isolated", port_nets={"A": "n0", "B": "n0", "C": "n1", "D": "n1"}).status == SUPPORTED
    assert classify_probe(wire, drc="pass", lvs="unknown").status == EXPERIMENTAL
    assert classify_probe(wire, drc="unknown", lvs="pass", port_nets={"A": "n0", "B": "n0"}).status == UNKNOWN
    assert classify_probe(wire, drc="fail", lvs="pass", port_nets={"A": "n0", "B": "n0"}).status == FORBIDDEN
    device = ProbeSpec(name="mos", kind="active_crossing", conductor="M1", expected="forms_device")
    assert classify_probe(device, drc="pass", lvs="pass", devices=("nmos4",)).status == SUPPORTED
    no_device = ProbeSpec(name="safe", kind="active_crossing", conductor="M1", expected="no_device")
    assert classify_probe(no_device, drc="pass", lvs="pass").status == SUPPORTED

    grammar = grammar_fixture()
    observed = Evidence(status=SUPPORTED, evidence=("fixture:wire",), drc="pass", lvs="pass")
    merged = apply_probe_observation(grammar, wire, observed)
    assert merged.conductors["M1"].continuity.status == SUPPORTED
    transition = ProbeSpec(name="via", kind="transition", conductor="M1", target="M2")
    merged = apply_probe_observation(merged, transition, observed)
    assert merged.conductors["M1"].connections["M2"].status == SUPPORTED
    assert merged.conductors["M2"].connections["M1"].status == SUPPORTED

    policy = RoutingPolicy.from_grammar(grammar)
    assert policy.allowed_layers == ("M1", "M2", "M3")
    assert policy.layer_cost["M2"] > policy.layer_cost["M1"]
    assert policy.resistance_per_um["M1"] == 100.0
    assert policy.log_resistance is True
    assert policy.edge_cost("M1", "horizontal", 1.0) > policy.layer_cost["M1"]
    assert policy.edge_cost("M1", "horizontal", 3.0) > policy.edge_cost("M1", "horizontal", 1.0)
    graph = RoutingGraph.rectangular(
        (0.0, 1.0, 2.0),
        (0.0, 1.0, 2.0),
        ("M1", "M2", "M3"),
        grammar=grammar,
    )
    assert {node.layer for node in graph.nodes} == {"M1", "M2", "M3"}
    assert any(
        edge.kind == "via" and {edge.start.layer, edge.end.layer} == {"M1", "M3"}
        for edge in graph.adjacency[RoutingNode(0.0, 0.0, "M1")]
    )
    route = graph.route_two_terminal(
        (RoutingNode(0.0, 0.0, "M1"),),
        (RoutingNode(2.0, 2.0, "M1"),),
    )
    multi = graph.route_multi_terminal(
        (
            RoutingNode(0.0, 0.0, "M1"),
            RoutingNode(2.0, 0.0, "M1"),
            RoutingNode(2.0, 2.0, "M1"),
        )
    )
    assert multi

    print("Routing grammar: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
