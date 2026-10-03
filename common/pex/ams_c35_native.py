"""KLayout adapter for the estimated C35 Manhattan RC graph."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from common.pex.manhattan import (
    ManhattanGeometryError,
    ManhattanResistorGraph,
    Point,
    spice_identifier,
)


@dataclass
class NativeC35RC:
    graph: ManhattanResistorGraph
    nets: Any
    dbu_um: float
    graph_layers: frozenset[str]
    capacitor_lines: list[str]

    def node_for(self, component: int, point: Any) -> str:
        layer = self.nets.comps[component][0]
        if layer not in self.graph_layers:
            return self.nets.net_of(component)
        node = self.graph.node_at(layer, (point.x * self.dbu_um, point.y * self.dbu_um))
        return self.graph.node_name(node)

    def elements(self) -> list[str]:
        return self.graph.elements() + self.capacitor_lines


def extract_native_rc(D: dict[str, Any], nets: Any, dbu_um: float, config: dict[str, Any]) -> NativeC35RC:
    """Build sheet-R paths, contact/via elements, and estimated geometry C."""
    graph = ManhattanResistorGraph()
    conductors = config.get("conductors") or {}
    graph_layers = frozenset(conductors)
    components = nets.comps

    for layer, polygon in components:
        material = conductors.get(layer)
        if material is None:
            continue
        outline = _points(polygon.each_point_hull(), dbu_um)
        holes = tuple(
            _points(polygon.each_point_hole(index), dbu_um)
            for index in range(int(polygon.holes()))
        )
        graph.add_polygon(
            layer,
            outline,
            float(material["sheet_resistance_ohm_sq"]),
            float(material.get("width_correction_um", 0.0)),
            holes=holes,
        )

    _add_contacts(graph, D, nets, dbu_um, config.get("contacts") or {})
    _connect_well_taps(graph, D, nets, dbu_um, conductors)
    _label_substrate_taps(graph, D, nets, dbu_um, conductors)
    for label, component, point in nets.label_points:
        layer = components[component][0]
        if layer in graph_layers:
            graph.label(layer, (point.x * dbu_um, point.y * dbu_um), label)

    graph.finalize()
    cap_lines = _extract_capacitance(
        graph, D, nets, dbu_um, conductors, config.get("capacitance") or {}
    )
    return NativeC35RC(graph, nets, dbu_um, graph_layers, cap_lines)


def _add_contacts(
    graph: ManhattanResistorGraph,
    derived: dict[str, Any],
    nets: Any,
    dbu_um: float,
    contact_config: dict[str, Any],
) -> None:
    serial = 0
    for cut, candidates in contact_config.items():
        region = derived.get(cut)
        if region is None or region.is_empty():
            continue
        for raw in region.merge().each():
            polygon = _polygon(raw)
            center = polygon.bbox().center()
            point = (center.x * dbu_um, center.y * dbu_um)
            matches = []
            for candidate in candidates:
                layer_a, layer_b = candidate["layers"]
                a = nets.comp_at(center, layer_a)
                b = nets.comp_at(center, layer_b)
                if a is not None and b is not None:
                    matches.append((layer_a, layer_b, candidate))
            if len(matches) != 1:
                raise ManhattanGeometryError(
                    f"{cut} cut at {center} must overlap exactly one configured conductor pair; "
                    f"found {len(matches)}"
                )
            layer_a, layer_b, candidate = matches[0]
            serial += 1
            graph.add_contact(
                layer_a,
                layer_b,
                point,
                float(candidate["resistance_ohm"]),
                f"{cut}_{serial}",
            )


def _connect_well_taps(
    graph: ManhattanResistorGraph,
    derived: dict[str, Any],
    nets: Any,
    dbu_um: float,
    conductors: dict[str, Any],
) -> None:
    if "nOhmic" not in conductors or "nBulk" not in conductors:
        return
    taps = derived.get("nOhmic")
    if taps is None or taps.is_empty():
        return
    for raw in taps.merge().each():
        center = _polygon(raw).bbox().center()
        if nets.comp_at(center, "nBulk") is None:
            continue
        graph.connect("nOhmic", "nBulk", (center.x * dbu_um, center.y * dbu_um))

def _label_substrate_taps(
    graph: ManhattanResistorGraph,
    derived: dict[str, Any],
    nets: Any,
    dbu_um: float,
    conductors: dict[str, Any],
) -> None:
    if "pOhmic" not in conductors:
        return
    taps = derived.get("pOhmic")
    if taps is None or taps.is_empty():
        return
    for raw in taps.merge().each():
        center = _polygon(raw).bbox().center()
        component = nets.comp_at(center, "pOhmic")
        if component is not None:
            name = nets.net_of(component)
            if nets.uf.find(component) == nets.uf.find(nets.SUB):
                name = nets.substrate_net() or "SUBS"
            graph.label(
                "pOhmic",
                (center.x * dbu_um, center.y * dbu_um),
                name,
            )

def _extract_capacitance(
    graph: ManhattanResistorGraph,
    derived: dict[str, Any],
    nets: Any,
    dbu_um: float,
    conductors: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    area_caps = config.get("area_ff_per_um2") or {}
    fringe_caps = config.get("fringe_ff_per_um") or {}
    coupling_caps = config.get("same_layer_ff_per_um") or {}
    cross_layer_caps = config.get("cross_layer_ff_per_um") or {}
    vertical_caps = config.get("vertical_ff_per_um2") or {}
    lines: list[str] = []
    substrate_node = spice_identifier(nets.substrate_net() or "SUBS")
    serial = 0
    polygons: dict[str, list[tuple[int, Any, Point]]] = {}

    for index, (layer, polygon) in enumerate(nets.comps):
        if layer not in conductors:
            continue
        point = _sample_point(polygon, dbu_um)
        graph.node_at(layer, point)
        polygons.setdefault(layer, []).append((index, polygon, point))

    covered_by_lower = _vertical_coverage(polygons, vertical_caps)
    for layer, entries in polygons.items():
        for index, polygon, point in entries:
            if layer in ("nDiff", "pDiff", "nOhmic", "pOhmic", "nBulk"):
                continue  # junction capacitance is owned by the compact device model
            area_um2 = polygon.area() * dbu_um * dbu_um
            if layer in covered_by_lower:
                area_um2 = _area_outside(polygon, covered_by_lower[layer]) * dbu_um * dbu_um
            if layer == "poly" and derived.get("active") is not None:
                area_um2 = _area_outside(polygon, derived["active"]) * dbu_um * dbu_um
            perimeter_um = polygon.perimeter() * dbu_um
            capacitance_ff = (
                area_um2 * float(area_caps.get(layer, 0.0))
                + perimeter_um * float(fringe_caps.get(layer, 0.0))
            )
            if capacitance_ff <= 0:
                continue
            serial += 1
            graph_node = graph.node_at(layer, point)
            lines.append(
                f"Crcx{serial} {graph.node_name(graph_node)} {substrate_node} "
                f"{capacitance_ff * 1e-15:.9g}"
            )

    for layer, entry in coupling_caps.items():
        coefficient = float(entry["value_ff_per_um"])
        max_gap = float(entry["max_spacing_um"])
        entries = polygons.get(layer, ())
        for a_id, a_poly, a_point, b_id, b_poly, b_point in _nearby_pairs(entries, dbu_um, max_gap):
            if nets.uf.find(a_id) == nets.uf.find(b_id):
                continue
            length = _parallel_edge_length(a_poly, b_poly, dbu_um, max_gap)
            cap_ff = coefficient * length
            if cap_ff <= 0:
                continue
            serial += 1
            a_node = graph.node_at(layer, a_point)
            b_node = graph.node_at(layer, b_point)
            lines.append(
                f"Crcx{serial} {graph.node_name(a_node)} {graph.node_name(b_node)} "
                f"{cap_ff * 1e-15:.9g}"
            )

    for upper, lowers in cross_layer_caps.items():
        if upper not in polygons:
            continue
        for lower, entry in lowers.items():
            if lower not in polygons:
                continue
            coefficient = float(entry["value_ff_per_um"])
            max_gap = float(entry["max_spacing_um"])
            for a_id, a_poly, a_point, b_id, b_poly, b_point in _nearby_pairs(
                polygons[upper], dbu_um, max_gap, other=polygons[lower]
            ):
                if nets.uf.find(a_id) == nets.uf.find(b_id):
                    continue
                length = _parallel_edge_length(a_poly, b_poly, dbu_um, max_gap)
                cap_ff = coefficient * length
                if cap_ff <= 0:
                    continue
                serial += 1
                a_node = graph.node_at(upper, a_point)
                b_node = graph.node_at(lower, b_point)
                lines.append(
                    f"Crcx{serial} {graph.node_name(a_node)} {graph.node_name(b_node)} "
                    f"{cap_ff * 1e-15:.9g}"
                )

    for upper, lowers in vertical_caps.items():
        if upper not in polygons:
            continue
        for lower, coefficient in lowers.items():
            if lower not in polygons:
                continue
            shielding = _vertical_shielding_coverage(polygons, upper, lower)
            for a_id, a_poly, a_point, b_id, b_poly, b_point in _nearby_pairs(
                polygons[upper], dbu_um, 0.0, other=polygons[lower]
            ):
                if nets.uf.find(a_id) == nets.uf.find(b_id):
                    continue
                if shielding.is_empty():
                    overlap = _region_area(a_poly, b_poly)
                else:
                    import pya

                    overlap_region = pya.Region(a_poly) & pya.Region(b_poly)
                    overlap_region -= shielding
                    overlap = overlap_region.area()
                cap_ff = overlap * dbu_um * dbu_um * float(coefficient)
                if cap_ff <= 0:
                    continue
                serial += 1
                a_node = graph.node_at(upper, a_point)
                b_node = graph.node_at(lower, b_point)
                lines.append(
                    f"Crcx{serial} {graph.node_name(a_node)} {graph.node_name(b_node)} "
                    f"{cap_ff * 1e-15:.9g}"
                )
    return lines


def _vertical_coverage(
    polygons: dict[str, list[tuple[int, Any, Point]]],
    vertical_caps: dict[str, dict[str, float]],
) -> dict[str, Any]:
    import pya

    covered = {}
    for upper, lowers in vertical_caps.items():
        region = pya.Region()
        for lower in lowers:
            for _, polygon, _ in polygons.get(lower, ()):
                region += pya.Region(polygon)
        if not region.is_empty():
            covered[upper] = region
    return covered


_VERTICAL_STACK = ("nBulk", "metal1", "metal2", "metal3", "metal4")


def _vertical_shielding_coverage(
    polygons: dict[str, list[tuple[int, Any, Point]]], upper: str, lower: str
) -> Any:
    import pya

    if upper not in _VERTICAL_STACK or lower not in _VERTICAL_STACK:
        return pya.Region()
    lower_index = _VERTICAL_STACK.index(lower)
    upper_index = _VERTICAL_STACK.index(upper)
    if lower_index >= upper_index:
        return pya.Region()
    covered = pya.Region()
    for layer in _VERTICAL_STACK[lower_index + 1 : upper_index]:
        for _, polygon, _ in polygons.get(layer, ()):
            covered += pya.Region(polygon)
    return covered




def _nearby_pairs(entries: Any, dbu_um: float, max_gap_um: float, other: Any = None):
    second_entries = entries if other is None else other
    second = sorted(second_entries, key=lambda item: item[1].bbox().left)
    max_gap = max_gap_um / dbu_um
    for a_id, a_poly, a_point in entries:
        box = a_poly.bbox()
        for b_id, b_poly, b_point in second:
            other_box = b_poly.bbox()
            if other_box.left > box.right + max_gap:
                break
            if other_box.right < box.left - max_gap:
                continue
            if (
                other_box.top < box.bottom - max_gap
                or other_box.bottom > box.top + max_gap
            ):
                continue
            if b_id == a_id or (other is None and b_id <= a_id):
                continue
            yield a_id, a_poly, a_point, b_id, b_poly, b_point


def _parallel_edge_length(first: Any, second: Any, dbu_um: float, max_gap_um: float) -> float:
    max_gap = max_gap_um / dbu_um
    total = 0.0
    for edge_a in first.each_edge():
        ax1, ay1 = edge_a.p1.x, edge_a.p1.y
        ax2, ay2 = edge_a.p2.x, edge_a.p2.y
        for edge_b in second.each_edge():
            bx1, by1 = edge_b.p1.x, edge_b.p1.y
            bx2, by2 = edge_b.p2.x, edge_b.p2.y
            if ay1 == ay2 and by1 == by2:
                gap = abs(ay1 - by1)
                overlap = min(max(ax1, ax2), max(bx1, bx2)) - max(min(ax1, ax2), min(bx1, bx2))
            elif ax1 == ax2 and bx1 == bx2:
                gap = abs(ax1 - bx1)
                overlap = min(max(ay1, ay2), max(by1, by2)) - max(min(ay1, ay2), min(by1, by2))
            else:
                continue
            if 0 < gap <= max_gap and overlap > 0:
                total += overlap * dbu_um
    return total


def _area_outside(polygon: Any, subtract: Any) -> float:
    import pya

    return (pya.Region(polygon) - subtract).area()


def _region_area(first: Any, second: Any) -> float:
    import pya

    return (pya.Region(first) & pya.Region(second)).area()


def _points(points: Any, dbu_um: float) -> tuple[Point, ...]:
    return tuple((point.x * dbu_um, point.y * dbu_um) for point in points)


def _sample_point(polygon: Any, dbu_um: float) -> Point:
    rings = [_points(polygon.each_point_hull(), 1.0)]
    rings.extend(
        _points(polygon.each_point_hole(index), 1.0)
        for index in range(int(polygon.holes()))
    )
    ys = sorted({point[1] for ring in rings for point in ring})
    for bottom, top in zip(ys, ys[1:]):
        mid_y = (bottom + top) / 2
        crossings = []
        for ring in rings:
            for a, b in zip(ring, (*ring[1:], ring[0])):
                if a[0] == b[0] and min(a[1], b[1]) < mid_y < max(a[1], b[1]):
                    crossings.append(a[0])
        crossings.sort()
        if len(crossings) % 2:
            continue
        for left, right in zip(crossings[::2], crossings[1::2]):
            if right > left:
                return ((left + right) / 2 * dbu_um, mid_y * dbu_um)
    raise ManhattanGeometryError("cannot find an interior sample point for conductor polygon")




def _polygon(raw: Any) -> Any:
    import pya

    return pya.Polygon(raw)
