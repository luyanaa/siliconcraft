#!/usr/bin/env python3
"""Behavioral regressions for the native C35 Manhattan resistor graph."""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.manhattan import ManhattanGeometryError, ManhattanResistorGraph


def resistance(line: str) -> float:
    return float(line.split()[-1])


def check_rectangle_uses_sheet_resistance_and_effective_width() -> None:
    graph = ManhattanResistorGraph()
    graph.add_rectangle("M1", (0, 0, 10, 2), sheet_resistance=50)
    lines = graph.elements()
    assert len(lines) == 1
    assert math.isclose(resistance(lines[0]), 250.0)

    corrected = ManhattanResistorGraph()
    corrected.add_rectangle(
        "POLY2", (0, 0, 10, 2), sheet_resistance=50, width_correction=0.4
    )
    assert math.isclose(resistance(corrected.elements()[0]), 312.5)


def check_manhattan_path_splits_at_junction() -> None:
    graph = ManhattanResistorGraph()
    graph.add_path("M1", ((0, 5), (10, 5)), width=2, sheet_resistance=10)
    graph.add_path("M1", ((5, 5), (5, 10)), width=2, sheet_resistance=10)
    branch = graph.node_at("M1", (5, 5))
    horizontal = graph.node_at("M1", (5, 5))
    assert graph.find(branch) == graph.find(horizontal)
    lines = graph.elements()
    assert len(lines) == 3
    assert sorted(resistance(line) for line in lines) == [25.0, 25.0, 25.0]


def check_rectilinear_polygon_is_decomposed_conservatively() -> None:
    graph = ManhattanResistorGraph()
    graph.add_polygon(
        "M2",
        ((0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)),
        sheet_resistance=10,
    )
    lines = graph.elements()
    assert len(lines) == 3
    assert sorted(resistance(line) for line in lines) == [5.0, 40.0, 45.0]
    assert math.isclose(sum(resistance(line) for line in lines), 90.0)


def check_via_is_an_explicit_series_resistor() -> None:
    graph = ManhattanResistorGraph()
    graph.add_path("M1", ((0, 0), (10, 0)), width=2, sheet_resistance=10)
    graph.add_path("M2", ((0, 0), (10, 0)), width=2, sheet_resistance=20)
    graph.add_contact("M1", "M2", (5, 0), 2.1, name="VIA1")
    lines = graph.elements()
    assert len(lines) == 5
    assert math.isclose(resistance(lines[-1]), 2.1)


def check_disjoint_shapes_remain_electrically_disconnected() -> None:
    graph = ManhattanResistorGraph()
    graph.add_rectangle("M1", (0, 0, 10, 2), sheet_resistance=10)
    graph.add_rectangle("M1", (20, 0, 30, 2), sheet_resistance=10)
    first = graph.node_at("M1", (0, 1))
    second = graph.node_at("M1", (30, 1))
    assert graph.find(first) != graph.find(second)
    assert len(graph.elements()) == 2


def check_unsupported_geometry_fails_closed() -> None:
    graph = ManhattanResistorGraph()
    try:
        graph.add_path("M1", ((0, 0), (10, 10)), width=1, sheet_resistance=10)
    except ManhattanGeometryError:
        pass
    else:
        raise AssertionError("angled path must be rejected")

    graph = ManhattanResistorGraph()
    try:
        graph.add_polygon(
            "M1", ((0, 0), (10, 0), (8, 2), (0, 2)), sheet_resistance=10
        )
    except ManhattanGeometryError:
        pass
    else:
        raise AssertionError("angled polygon must be rejected")

    graph = ManhattanResistorGraph()
    try:
        graph.add_rectangle(
            "POLY2", (0, 0, 10, 0.4), sheet_resistance=50, width_correction=0.4
        )
    except ManhattanGeometryError:
        pass
    else:
        raise AssertionError("nonpositive effective width must be rejected")


def check_polygon_holes_remain_open():
    graph = ManhattanResistorGraph()
    graph.add_polygon(
        "M1",
        ((0, 0), (10, 0), (10, 10), (0, 10)),
        sheet_resistance=10,
        holes=(((2, 2), (8, 2), (8, 8), (2, 8)),),
    )
    try:
        graph.node_at("M1", (5, 5))
    except ManhattanGeometryError:
        pass
    else:
        raise AssertionError("polygon hole must not become a conductor")
    assert graph.elements()


def check_square_rectangle_keeps_one_sheet_of_resistance() -> None:
    graph = ManhattanResistorGraph()
    graph.add_rectangle("M1", (0, 0, 2, 2), sheet_resistance=50)
    lines = graph.elements()
    assert len(lines) == 1
    assert math.isclose(resistance(lines[0]), 50.0)


def check_ideal_cross_layer_short_unifies_nodes() -> None:
    graph = ManhattanResistorGraph()
    graph.add_path("nOhmic", ((0, 0), (10, 0)), width=2, sheet_resistance=10)
    graph.add_path("nBulk", ((0, 0), (10, 0)), width=2, sheet_resistance=20)
    graph.connect("nOhmic", "nBulk", (5, 0))
    graph.elements()
    ohmic = graph.node_at("nOhmic", (5, 0))
    bulk = graph.node_at("nBulk", (5, 0))
    assert graph.find(ohmic) == graph.find(bulk)



def check_node_names_wait_for_ideal_connectivity() -> None:
    graph = ManhattanResistorGraph()
    graph.add_path("nOhmic", ((0, 0), (10, 0)), width=2, sheet_resistance=10)
    graph.add_path("nBulk", ((0, 0), (10, 0)), width=2, sheet_resistance=20)
    graph.connect("nOhmic", "nBulk", (5, 0))
    ohmic = graph.node_at("nOhmic", (5, 0))
    bulk = graph.node_at("nBulk", (5, 0))
    try:
        graph.node_name(ohmic)
    except ManhattanGeometryError:
        pass
    else:
        raise AssertionError("node naming before finalization must be rejected")

    graph.finalize()
    canonical_name = graph.node_name(ohmic)
    assert graph.node_name(bulk) == canonical_name
    assert any(canonical_name in line.split()[1:3] for line in graph.elements())

def main() -> int:
    checks = (
        check_rectangle_uses_sheet_resistance_and_effective_width,
        check_manhattan_path_splits_at_junction,
        check_rectilinear_polygon_is_decomposed_conservatively,
        check_polygon_holes_remain_open,
        check_via_is_an_explicit_series_resistor,
        check_disjoint_shapes_remain_electrically_disconnected,
        check_unsupported_geometry_fails_closed,
        check_square_rectangle_keeps_one_sheet_of_resistance,
        check_ideal_cross_layer_short_unifies_nodes,
        check_node_names_wait_for_ideal_connectivity,
    )
    for check in checks:
        check()
    print(f"C35 native Manhattan graph checks: PASS ({len(checks)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
