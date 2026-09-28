"""Process-parameterized stdcell topology, geometry, and routing planner.

The planner emits deterministic candidate manifests.  It intentionally stops
before claiming DRC/LVS/PEX or timing results; those gates consume the emitted
geometry and routing resources in later stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import product
import math

from common.stdcell.columns import ColumnIR, enumerate_column_ir
from common.stdcell.pareto import pareto_front
from common.stdcell.compaction import DifferenceConstraint, Feature, compact_linear
from common.stdcell.geometry import GeometryIR
from common.stdcell.netlist import CellCircuit, MosInstance
from common.stdcell.process import StdcellProcess
from common.stdcell.routing import RoutingGraph, RoutingNode, RoutingPolicy
from common.stdcell.topology import (
    NetworkOrdering,
    pin_permutations,
    topology_options,
    weak_device_names,
    weak_length_scales,
)


class PlannerError(ValueError):
    """Raised when a circuit cannot be represented by the initial planner."""


@dataclass(frozen=True)
class Segment:
    layer: str
    x0: float
    y0: float
    x1: float
    y1: float
    net: str | None
    purpose: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "net": self.net,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class Rect:
    layer: str
    x0: float
    y0: float
    x1: float
    y1: float
    net: str | None
    purpose: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "net": self.net,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class MosFootprint:
    width_um: float
    height_um: float
    active_width_um: float
    active_height_um: float
    gate_xs_um: tuple[float, ...]
    left_contact_x_um: float
    right_contact_x_um: float
    gate_extension_um: float


@dataclass(frozen=True)
class DevicePlacement:
    device: MosInstance
    polarity: str
    x_um: float
    y_um: float
    width_per_finger_um: float
    length_um: float
    nf: int
    footprint: MosFootprint
    left_net: str | None = None
    right_net: str | None = None
    contactless_sides: tuple[str, ...] = ()

    def side_points(self) -> dict[str, tuple[str, tuple[float, float]]]:
        y = self.y_um
        return {
            "left": (
                self.left_net or self.device.drain,
                (self.x_um + self.footprint.left_contact_x_um, y),
            ),
            "right": (
                self.right_net or self.device.source,
                (self.x_um + self.footprint.right_contact_x_um, y),
            ),
        }

    def routable_diffusion_points(self) -> tuple[tuple[str, tuple[float, float]], ...]:
        return tuple(
            value
            for side, value in self.side_points().items()
            if side not in self.contactless_sides
        )

    def terminal_points(self) -> dict[str, tuple[float, float]]:
        half_height = self.footprint.active_height_um / 2.0
        points = {
            "g": (self.x_um, self.y_um - half_height - self.footprint.gate_extension_um)
        }
        side_points = self.side_points()
        for terminal, net in (("d", self.device.drain), ("s", self.device.source)):
            for side, (side_net, point) in side_points.items():
                if side not in self.contactless_sides and side_net == net:
                    points[terminal] = point
                    break
        return points

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.device.name,
            "polarity": self.polarity,
            "model": self.device.model,
            "gate": self.device.gate,
            "drain": self.device.drain,
            "source": self.device.source,
            "bulk": self.device.bulk,
            "left_net": self.left_net or self.device.drain,
            "right_net": self.right_net or self.device.source,
            "contactless_sides": list(self.contactless_sides),
            "x_um": self.x_um,
            "y_um": self.y_um,
            "width_per_finger_um": self.width_per_finger_um,
            "total_width_um": self.width_per_finger_um * self.nf,
            "length_um": self.length_um,
            "nf": self.nf,
            "multiplicity": self.device.multiplicity,
            "footprint": {
                "width_um": self.footprint.width_um,
                "height_um": self.footprint.height_um,
                "active_width_um": self.footprint.active_width_um,
                "active_height_um": self.footprint.active_height_um,
                "gate_xs_um": list(self.footprint.gate_xs_um),
                "left_contact_x_um": self.footprint.left_contact_x_um,
                "right_contact_x_um": self.footprint.right_contact_x_um,
            },
        }


@dataclass(frozen=True)
class CandidatePlan:
    cell: str
    profile: str
    architecture: str
    index: int
    columns: ColumnIR
    geometry_ir: GeometryIR
    support_taps: tuple[dict[str, Any], ...]
    width_um: float
    height_um: float
    placements: tuple[DevicePlacement, ...]
    orderings: tuple[NetworkOrdering, ...]
    segments: tuple[Segment, ...]
    blockages: tuple[Rect, ...]
    via_blockages: tuple[Rect, ...]
    graph_routes: dict[str, tuple[dict[str, Any], ...]]
    feedthrough_columns: tuple[float, ...]
    feedthrough_layer: str
    pin_access: dict[str, dict[str, Any]]
    metrics: dict[str, Any]
    constraints: dict[str, Any]
    route_conflicts: tuple[dict[str, Any], ...]
    diffusion_bridges: tuple[Rect, ...] = ()
    supply_contact_plan: tuple[dict[str, Any], ...] = ()
    topology_candidates: tuple[dict[str, Any], ...] = ()
    pin_permutations: tuple[tuple[str, ...], ...] = ()
    sizing_variant: dict[str, Any] = field(default_factory=dict)
    orientation_policy: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "geometry_planned",
            "cell": self.cell,
            "profile": self.profile,
            "architecture": self.architecture,
            "candidate_index": self.index,
            "geometry": {
                "width_um": self.width_um,
                "height_um": self.height_um,
                "ir": self.geometry_ir.as_dict(),
                "diffusion_bridges": [rect.as_dict() for rect in self.diffusion_bridges],
            },
            "placement": {
                **self.columns.as_dict(),
                "orientation_policy": self.orientation_policy,
            },
            "support_taps": list(self.support_taps),
            "devices": [placement.as_dict() for placement in self.placements],
            "supply_contact_plan": list(self.supply_contact_plan),
            "topology": {
                "orderings": [
                    {
                        "polarity": ordering.polarity,
                        "devices": list(ordering.devices),
                        "shared_diffusion_edges": ordering.shared_diffusion_edges,
                        "diffusion_breaks": ordering.diffusion_breaks,
                    }
                    for ordering in self.orderings
                ],
                "physical_diffusion_sharing": bool(self.diffusion_bridges),
                "contactless_internal_diffusion": [
                    {
                        "device": placement.device.name,
                        "sides": list(placement.contactless_sides),
                    }
                    for placement in self.placements
                    if placement.contactless_sides
                ],
                "topology_candidates": list(self.topology_candidates),
                "pin_permutations": [list(order) for order in self.pin_permutations],
                "sizing_variant": self.sizing_variant,
                "routing_fallback": "explicit_diffusion_breaks",
            },
            "routing": {
                "segments": [segment.as_dict() for segment in self.segments],
                "metal_blockage_map": [rect.as_dict() for rect in self.blockages],
                "via_blockage_map": [rect.as_dict() for rect in self.via_blockages],
                "graph_routes": {
                    net: list(route) for net, route in self.graph_routes.items()
                },
                "feedthrough_layer": self.feedthrough_layer,
                "feedthrough_columns_um": list(self.feedthrough_columns),
                "pin_access_regions": self.pin_access,
                "route_conflicts": list(self.route_conflicts),
            },
            "metrics": self.metrics,
            "constraints": self.constraints,
            "characterization": {
                "status": "not_run",
                "reason": "candidate planner emits geometry and routing resources only",
            },
            "verification": {"drc": "not_run", "lvs": "not_run", "pex": "not_run"},
        }


def _ceil_grid(process: StdcellProcess, value: float) -> float:
    steps = math.ceil((value - 1e-9) / process.grid_um)
    return process.snap(max(process.grid_um, steps * process.grid_um))


def _footprint(process: StdcellProcess, device: MosInstance, nf: int, width_per_finger: float) -> MosFootprint:
    tech = process.tech
    length = device.length_um or process.lmin_um
    poly_pitch = length + tech.poly_spacing
    poly_edge = tech.poly_contact_spacing + tech.contact_size + tech.active_contact_enc
    active_width = 2 * poly_edge + (nf - 1) * poly_pitch + length
    active_height = max(width_per_finger, tech.active_min)
    select_enc = max(tech.select_active_enc, 3 * process.lambda_um)
    select_width = active_width + 2 * select_enc
    select_height = active_height + 2 * select_enc
    if process.polarity_for_model(device.model) == "p":
        well_enc = tech.nwell_active_enc
        well_width = max(select_width, tech.nwell_min_width + 2 * well_enc)
        well_height = max(select_height, tech.nwell_min_width + 2 * well_enc)
        width = well_width
        height = well_height
    else:
        width = select_width
        height = select_height
    active_left = -active_width / 2.0
    active_right = active_width / 2.0
    if nf == 1:
        left_contact = active_left + tech.active_contact_enc + tech.contact_size / 2.0
        right_contact = active_right - tech.active_contact_enc - tech.contact_size / 2.0
    else:
        parallel_step = 2 * (process.lambda_um + tech.poly_contact_spacing) + length
        first = active_left + tech.active_contact_enc + tech.contact_size / 2.0
        contact_xs = tuple(first + index * parallel_step for index in range(nf + 1))
        left_contact = contact_xs[0]
        right_contact = contact_xs[-1]
    gate_span = (nf - 1) * poly_pitch + length
    gate_left = -gate_span / 2.0
    gate_xs = tuple(gate_left + index * poly_pitch + length / 2.0 for index in range(nf))
    return MosFootprint(
        width_um=width,
        height_um=height,
        active_width_um=active_width,
        active_height_um=active_height,
        gate_xs_um=gate_xs,
        left_contact_x_um=left_contact,
        right_contact_x_um=right_contact,
        gate_extension_um=2 * process.lambda_um,
    )


def _nf_options(process: StdcellProcess, device: MosInstance) -> tuple[int, ...]:
    total_width = device.width_um * device.nf
    maximum = min(3, max(1, int(total_width / process.tech.active_min + 1e-9)))
    options = set(range(1, maximum + 1))
    options.add(device.nf)
    return tuple(sorted(options))
def _shared_diffusion_layout(
    process: StdcellProcess,
    circuit: CellCircuit,
    column_ir: ColumnIR,
    placements: dict[str, DevicePlacement],
) -> tuple[dict[str, DevicePlacement], tuple[Rect, ...], tuple[dict[str, Any], ...]]:
    """Build shared active bridges and suppress only redundant diffusion contacts."""
    orderings = (("p", column_ir.p_order), ("n", column_ir.n_order))
    side_nets = {
        name: [placement.device.drain, placement.device.source]
        for name, placement in placements.items()
    }
    contactless: dict[str, set[str]] = {name: set() for name in placements}
    bridges: list[Rect] = []

    def orient(name: str, side_index: int, net: str) -> None:
        values = side_nets[name]
        try:
            current_index = values.index(net)
        except ValueError as exc:
            raise PlannerError(
                f"{circuit.name}: shared diffusion net {net!r} is not on {name}"
            ) from exc
        if current_index != side_index:
            values[0], values[1] = values[1], values[0]

    external = set(circuit.ports) | set(circuit.supplies)
    required_supply_contacts = {
        supply: (
            math.ceil(demand / capacity)
            if (capacity := process.supply_contact_capacity(supply)) is not None
            and (demand := process.supply_current_demand(supply)) is not None
            and demand > 0
            else 1
        )
        for supply in circuit.supplies
    }
    for _, ordering in orderings:
        for left_name, right_name in zip(ordering.devices, ordering.devices[1:]):
            left = placements[left_name]
            right = placements[right_name]
            shared = sorted(
                set(left.device.diffusion_nets) & set(right.device.diffusion_nets)
            )
            if not shared:
                continue
            net = shared[0]
            orient(left_name, 1, net)
            orient(right_name, 0, net)
            if net in external:
                if net not in circuit.supplies or required_supply_contacts.get(net, 1) <= 1:
                    contactless[left_name].add("right")
            else:
                contactless[left_name].add("right")
                contactless[right_name].add("left")
            left_edge = left.x_um + left.footprint.active_width_um / 2.0
            right_edge = right.x_um - right.footprint.active_width_um / 2.0
            x0, x1 = sorted((left_edge, right_edge))
            y_half = min(left.footprint.active_height_um, right.footprint.active_height_um) / 2.0
            y0 = left.y_um - y_half
            y1 = left.y_um + y_half
            bridges.append(Rect("ACTIVE", x0, y0, x1, y1, net, "shared_diffusion"))
            select = "PSELECT" if left.polarity == "p" else "NSELECT"
            select_enc = max(process.tech.select_active_enc, 3 * process.lambda_um)
            bridges.append(
                Rect(
                    select,
                    x0 - select_enc,
                    y0 - select_enc,
                    x1 + select_enc,
                    y1 + select_enc,
                    net,
                    "shared_diffusion_select",
                )
            )
    updated = {
        name: replace(
            placement,
            left_net=side_nets[name][0],
            right_net=side_nets[name][1],
            contactless_sides=tuple(sorted(contactless[name])),
        )
        for name, placement in placements.items()
    }
    supply_plan = []
    for supply in circuit.supplies:
        points = [
            point
            for placement in updated.values()
            for net, point in placement.routable_diffusion_points()
            if net == supply
        ]
        capacity = process.supply_contact_capacity(supply)
        demand = process.supply_current_demand(supply)
        required_count = (
            math.ceil(demand / capacity)
            if capacity is not None and demand is not None and demand > 0
            else None
        )
        supply_plan.append(
            {
                "net": supply,
                "contact_count": len(points),
                "required_contact_count": required_count,
                "capacity_sufficient": (
                    None
                    if required_count is None
                    else len(points) >= required_count
                ),
                "shared_contact_optimization": len(points) < sum(
                    1
                    for placement in updated.values()
                    if supply in placement.device.diffusion_nets
                ),
                "current_capacity_per_contact": capacity,
                "current_demand": demand,
                "status": (
                    "capacity_checked"
                    if required_count is not None and len(points) >= required_count
                    else "capacity_insufficient"
                    if required_count is not None
                    else "geometry_candidate_only"
                ),
            }
        )
    return updated, tuple(bridges), tuple(supply_plan)



def _column_layout(
    process: StdcellProcess,
    circuit: CellCircuit,
    fold_map: dict[str, int],
    column_ir: ColumnIR,
) -> tuple[
    dict[str, DevicePlacement],
    float,
    float,
    float,
    GeometryIR,
    tuple[dict[str, Any], ...],
    tuple[Rect, ...],
    tuple[dict[str, Any], ...],
]:
    model_to_polarity = {model: polarity for polarity, model in process.model_names.items()}
    devices_by_gate: dict[str, list[MosInstance]] = {}
    for device in circuit.devices:
        if device.model not in model_to_polarity:
            raise PlannerError(
                f"{circuit.name}: model {device.model!r} is not bound by {process.profile_name}"
            )
        devices_by_gate.setdefault(device.gate, []).append(device)
    gate_order: list[str] = []
    for column in column_ir.columns:
        if column.kind != "gate":
            continue
        for gate in (column.gate_net, column.p_gate_net, column.n_gate_net):
            if gate and gate not in gate_order:
                gate_order.append(gate)
    gate_order.extend(gate for gate in circuit.inputs if gate not in gate_order)
    gate_order.extend(sorted(gate for gate in devices_by_gate if gate not in gate_order))
    if any(len(devices_by_gate[gate]) > 2 for gate in gate_order):
        raise PlannerError(f"{circuit.name}: more than two devices on gate {gate_order!r} is not supported")

    footprints: dict[str, MosFootprint] = {}
    for device in circuit.devices:
        nf = fold_map[device.name]
        total_width = device.width_um * device.nf
        width_per_finger = total_width / nf
        footprints[device.name] = _footprint(process, device, nf, width_per_finger)

    column_widths = {
        gate: max(footprints[device.name].width_um for device in devices_by_gate[gate])
        for gate in gate_order
    }
    margin = max(2 * process.lambda_um, process.tech.contact_size)
    gap = max(2 * process.lambda_um, process.tech.poly_spacing)
    features = tuple(
        Feature(gate, column_widths[gate] / 2.0, "gate")
        for gate in gate_order
    )
    constraints = tuple(
        DifferenceConstraint(
            left=left.name,
            right=right.name,
            minimum_distance_um=left.half_width_um + right.half_width_um + gap,
            reason="gate_column_spacing",
        )
        for left, right in zip(features, features[1:])
    )
    compacted = compact_linear(features, constraints, left_edge_um=margin)
    centers = {
        gate: _ceil_grid(process, compacted.coordinates_um[gate])
        for gate in gate_order
    }
    width = _ceil_grid(process, compacted.width_um + margin)

    by_p = [device for device in circuit.devices if model_to_polarity[device.model] == "p"]
    by_n = [device for device in circuit.devices if model_to_polarity[device.model] == "n"]
    p_height = max(footprints[device.name].height_um for device in by_p)
    n_height = max(footprints[device.name].height_um for device in by_n)
    rail_width = process.metal_width_um("M1")
    row_gap = max(2 * process.lambda_um, process.tech.poly_spacing)
    bottom_margin = rail_width + 2 * process.lambda_um
    top_margin = bottom_margin
    height = _ceil_grid(process, bottom_margin + n_height + row_gap + p_height + top_margin)
    n_y = bottom_margin + n_height / 2.0
    p_y = height - top_margin - p_height / 2.0

    placements: dict[str, DevicePlacement] = {}
    for device in circuit.devices:
        polarity = model_to_polarity[device.model]
        footprint = footprints[device.name]
        y = p_y if polarity == "p" else n_y
        placements[device.name] = DevicePlacement(
            device=device,
            polarity=polarity,
            x_um=centers[device.gate],
            y_um=y,
            width_per_finger_um=device.width_um * device.nf / fold_map[device.name],
            length_um=device.length_um or process.lmin_um,
            nf=fold_map[device.name],
            footprint=footprint,
        )
    placements, diffusion_bridges, supply_contact_plan = _shared_diffusion_layout(
        process, circuit, column_ir, placements
    )
    tap_half_extent = (
        process.tech.contact_size / 2.0
        + process.tech.active_contact_enc
        + process.tech.select_active_enc
    )
    right_edge = max(
        placement.x_um + placement.footprint.width_um / 2.0
        for placement in placements.values()
    )
    tap_clearance = max(2 * process.lambda_um, process.metal_spacing_um("M1"))
    tap_x = _ceil_grid(process, right_edge + tap_clearance + tap_half_extent)
    width = _ceil_grid(process, max(width, tap_x + tap_half_extent))
    support_taps = (
        {
            "cell": "ptap",
            "net": "VSS",
            "x_um": tap_x,
            "y_um": _ceil_grid(process, height / 2.0),
            "rows": 1,
            "columns": 1,
        },
    )
    geometry_ir = GeometryIR(features, constraints, compacted, height)
    return (
        placements,
        width,
        height,
        n_y,
        geometry_ir,
        support_taps,
        diffusion_bridges,
        supply_contact_plan,
    )


def _add_segment(
    segments: list[Segment],
    layer: str,
    a: tuple[float, float],
    b: tuple[float, float],
    net: str,
    purpose: str,
) -> None:
    if a == b:
        return
    segment = Segment(layer, a[0], a[1], b[0], b[1], net, purpose)
    if segments:
        previous = segments[-1]
        same_identity = (
            previous.layer == segment.layer
            and previous.net == segment.net
            and previous.purpose == segment.purpose
        )
        horizontal = previous.y0 == previous.y1 == segment.y0 == segment.y1
        vertical = previous.x0 == previous.x1 == segment.x0 == segment.x1
        if same_identity and (horizontal or vertical):
            px0, py0, px1, py1 = _segment_bbox(previous)
            sx0, sy0, sx1, sy1 = _segment_bbox(segment)
            if horizontal and sy0 <= py1 and sx0 <= px1 and px0 <= sx1:
                segments[-1] = Segment(
                    layer,
                    min(px0, sx0),
                    previous.y0,
                    max(px1, sx1),
                    previous.y1,
                    net,
                    purpose,
                )
                return
            if vertical and sx0 <= px1 and sy0 <= py1 and py0 <= sy1:
                segments[-1] = Segment(
                    layer,
                    previous.x0,
                    min(py0, sy0),
                    previous.x1,
                    max(py1, sy1),
                    net,
                    purpose,
                )
                return
    segments.append(segment)

def _segment_bbox(segment: Segment) -> tuple[float, float, float, float]:
    return min(segment.x0, segment.x1), min(segment.y0, segment.y1), max(segment.x0, segment.x1), max(segment.y0, segment.y1)


def _segments_conflict(left: Segment, right: Segment) -> bool:
    if left.layer != right.layer or left.net == right.net:
        return False
    lx0, ly0, lx1, ly1 = _segment_bbox(left)
    rx0, ry0, rx1, ry1 = _segment_bbox(right)
    return lx0 <= rx1 and rx0 <= lx1 and ly0 <= ry1 and ry0 <= ly1



def _feedthrough_positions(
    process: StdcellProcess,
    width: float,
    count: int,
    layer: str,
    placements: dict[str, DevicePlacement],
    extra_blocked_xs: tuple[float, ...] = (),
) -> tuple[float, ...]:
    if count == 0:
        return ()
    track_half_width = process.metal_width_um(layer) / 2.0
    contact_half_width = process.tech.contact_size / 2.0
    clearance = track_half_width + contact_half_width + process.grid_um
    blocked_xs = tuple(
        point[0]
        for placement in placements.values()
        for _, point in placement.routable_diffusion_points()
    ) + tuple(extra_blocked_xs)
    lower = track_half_width
    upper = width - track_half_width
    selected: list[float] = []
    for index in range(count):
        ideal = _ceil_grid(process, width * (index + 1) / (count + 1))
        found = None
        max_steps = int(math.ceil(width / process.grid_um)) + 1
        for step in range(max_steps):
            offsets = (0.0,) if step == 0 else (step * process.grid_um, -step * process.grid_um)
            for offset in offsets:
                candidate = _ceil_grid(process, ideal + offset)
                if candidate < lower or candidate > upper:
                    continue
                if any(abs(candidate - blocked) < clearance for blocked in blocked_xs):
                    continue
                if any(
                    abs(candidate - prior)
                    < process.metal_width_um(layer) + process.metal_spacing_um(layer)
                    for prior in selected
                ):
                    continue
                found = candidate
                break
            if found is not None:
                break
        if found is None:
            raise PlannerError(
                f"cannot place {layer} feedthrough {index + 1}/{count} "
                f"without crossing active contacts"
            )
        selected.append(found)
    return tuple(selected)

def _graph_route_net(
    process: StdcellProcess,
    net: str,
    points: list[tuple[float, float]],
    track_y: float,
    graph: RoutingGraph,
    usage: dict[tuple[RoutingNode, RoutingNode, str], int],
    blocked: set[tuple[RoutingNode, RoutingNode, str]],
    occupied_nodes: set[RoutingNode],
    segments: list[Segment],
    via_blockages: list[Rect],
    track_layer: str = "M1",
) -> tuple[dict[str, Any], ...]:
    if len(points) < 2:
        return ()
    trunk = RoutingNode(min(point[0] for point in points), track_y, track_layer)
    used_keys: set[tuple[RoutingNode, RoutingNode, str]] = set()
    net_nodes: set[RoutingNode] = {trunk}
    route_edges: list[dict[str, Any]] = []
    for point in points:
        start = RoutingNode(point[0], point[1], "M1")
        dynamic_blocked = set(blocked)
        dynamic_blocked.update(
            edge.key
            for edges in graph.adjacency.values()
            for edge in edges
            if edge.kind == "wire"
            and (edge.start in occupied_nodes or edge.end in occupied_nodes)
        )
        path = graph.route_two_terminal(
            (start,), (trunk,), usage=usage, blocked=dynamic_blocked
        )
        for edge in path:
            if edge.kind == "wire":
                _add_segment(
                    segments,
                    edge.start.layer,
                    (edge.start.x_um, edge.start.y_um),
                    (edge.end.x_um, edge.end.y_um),
                    net,
                    "graph_route",
                )
            else:
                lower, upper = sorted((edge.start.layer, edge.end.layer))
                via_name = "VIA12" if (lower, upper) == ("M1", "M2") else "VIA23"
                via_size = process.via_size_um(lower, upper)
                via_blockages.append(
                    Rect(
                        via_name,
                        edge.start.x_um - via_size / 2.0,
                        edge.start.y_um - via_size / 2.0,
                        edge.start.x_um + via_size / 2.0,
                        edge.start.y_um + via_size / 2.0,
                        net,
                        "graph_route_via",
                    )
                )
            used_keys.add(edge.key)
            net_nodes.update((edge.start, edge.end))
            route_edges.append(
                {
                    "kind": edge.kind,
                    "layer": edge.start.layer,
                    "to_layer": edge.end.layer,
                    "x0": edge.start.x_um,
                    "y0": edge.start.y_um,
                    "x1": edge.end.x_um,
                    "y1": edge.end.y_um,
                    "cost": edge.cost,
                }
            )
    occupied_nodes.update(net_nodes)
    for key in used_keys:
        usage[key] = usage.get(key, 0) + 1
    return tuple(route_edges)


def _route(
    process: StdcellProcess,
    circuit: CellCircuit,
    architecture: str,
    placements: dict[str, DevicePlacement],
    width: float,
    height: float,
    n_y: float,
    support_taps: tuple[dict[str, Any], ...],
) -> tuple[
    list[Segment],
    list[Rect],
    list[Rect],
    dict[str, dict[str, Any]],
    dict[str, tuple[dict[str, Any], ...]],
    tuple[float, ...],
    str,
    tuple[dict[str, Any], ...],
]:
    segments: list[Segment] = []
    blockages: list[Rect] = []
    via_blockages: list[Rect] = []
    rail_width = process.metal_width_um("M1")
    segments.append(Segment("M1", 0.0, rail_width / 2, width, rail_width / 2, "VSS", "rail"))
    segments.append(Segment("M1", 0.0, height - rail_width / 2, width, height - rail_width / 2, "VDD", "rail"))

    for tap in support_taps:
        _add_segment(
            segments,
            "M1",
            (tap["x_um"], tap["y_um"]),
            (tap["x_um"], rail_width / 2.0),
            tap["net"],
            "support_tap_drop",
        )

    net_points: dict[str, list[tuple[float, float]]] = {}
    gate_xs: dict[str, list[float]] = {}
    for placement in placements.values():
        for node, point in placement.routable_diffusion_points():
            net_points.setdefault(node, []).append(point)
            if node in circuit.supplies:
                rail_y = (
                    rail_width / 2
                    if node.lower().startswith(("vss", "gnd", "0"))
                    else height - rail_width / 2
                )
                _add_segment(segments, "M1", point, (point[0], rail_y), node, "supply_drop")
        gate_xs.setdefault(placement.device.gate, []).append(placement.x_um)

    for gate, xs in gate_xs.items():
        x = sum(xs) / len(xs)
        gate_devices = [device for device in placements.values() if device.device.gate == gate]
        low = min(
            device.y_um
            - device.footprint.active_height_um / 2
            - device.footprint.gate_extension_um
            for device in gate_devices
        )
        high = max(
            device.y_um
            + device.footprint.active_height_um / 2
            + device.footprint.gate_extension_um
            for device in gate_devices
        )
        segments.append(Segment("POLY", x, low, x, high, gate, "gate_connection"))

    internal = [node for node in sorted(net_points) if node not in circuit.supplies]
    p_row = max(
        placement.y_um for placement in placements.values() if placement.polarity == "p"
    )
    p_top = max(
        placement.y_um + placement.footprint.active_height_um / 2.0
        for placement in placements.values()
        if placement.polarity == "p"
    )
    n_top = max(
        placement.y_um + placement.footprint.active_height_um / 2.0
        for placement in placements.values()
        if placement.polarity == "n"
    )
    tracks_start = _ceil_grid(
        process,
        n_top + process.metal_width_um("M1") / 2.0 + process.metal_spacing_um("M1"),
    )
    via_landing_half = process.via_size_um("M1", "M2") / 2.0 + process.lambda_um
    track_spacing = process.metal_width_um("M1") / 2.0 + via_landing_half + process.metal_spacing_um("M1")
    p_track_start = _ceil_grid(
        process,
        p_top + process.metal_width_um("M2") / 2.0 + process.metal_spacing_um("M2"),
    )
    p_only = {
        node
        for node in internal
        if any(y == p_row for _, y in net_points[node])
        and not any(y == n_y for _, y in net_points[node])
    }
    track_ys: dict[str, float] = {}
    regular_index = 0
    p_only_index = 0
    for node in internal:
        if node in p_only:
            track_ys[node] = p_track_start + p_only_index * track_spacing
            p_only_index += 1
        else:
            track_ys[node] = tracks_start + regular_index * track_spacing
            regular_index += 1
    graph_xs = sorted(
        {
            point[0]
            for node in internal
            for point in net_points[node]
        }
    )
    graph_ys = sorted(
        {
            point[1]
            for node in internal
            for point in net_points[node]
        }
        | set(track_ys.values())
    )
    row_net_xs: dict[float, dict[str, set[str]]] = {}
    for net, points in net_points.items():
        for x, y in points:
            if y == p_row:
                row_net_xs.setdefault(x, {}).setdefault("p", set()).add(net)
            elif y == n_y:
                row_net_xs.setdefault(x, {}).setdefault("n", set()).add(net)
    row_conflict_xs = {
        x
        for x, rows in row_net_xs.items()
        if rows.get("p") and rows.get("n") and rows["p"] != rows["n"]
    }
    p_only_track_ys = set(track_ys[node] for node in p_only)
    policy = RoutingPolicy.for_architecture(architecture)
    graph = RoutingGraph.rectangular(graph_xs, graph_ys, tuple(policy.layer_cost), policy)
    row_ys = {n_y, p_row}
    blocked = {
        edge.key
        for edges in graph.adjacency.values()
        for edge in edges
        if edge.kind == "wire"
        and (
            (
                edge.start.layer == "M1"
                and edge.end.layer == "M1"
                and (
                    (edge.start.y_um in row_ys and edge.end.y_um in row_ys)
                    or (
                        edge.start.x_um == edge.end.x_um
                        and edge.start.x_um in row_conflict_xs
                        and p_row in (edge.start.y_um, edge.end.y_um)
                    )
                    or (
                        edge.start.y_um == edge.end.y_um
                        and edge.start.y_um in p_only_track_ys
                    )
                )
            )
            or (
                p_only
                and edge.start.layer == "M2"
                and edge.end.layer == "M2"
                and edge.start.y_um == edge.end.y_um == p_row
            )
        )
    }
    graph_usage: dict[tuple[RoutingNode, RoutingNode, str], int] = {}
    graph_routes: dict[str, tuple[dict[str, Any], ...]] = {}
    occupied_nodes: set[RoutingNode] = set()
    route_order = [node for node in internal if node not in p_only] + [
        node for node in internal if node in p_only
    ]
    for node in route_order:
        graph_routes[node] = _graph_route_net(
            process,
            node,
            net_points[node],
            track_ys[node],
            graph,
            graph_usage,
            blocked,
            occupied_nodes,
            segments,
            via_blockages,
            track_layer="M2" if node in p_only else "M1",
        )

    if architecture == "two_metal_classic":
        feedthrough_layer = "M2"
        count = max(1, int(width / max(12 * process.lambda_um, process.grid_um)))
    elif architecture == "two_metal_dense":
        feedthrough_layer = "M2"
        count = 0
    elif architecture == "three_metal_classic":
        feedthrough_layer = "M3"
        count = max(1, int(width / max(12 * process.lambda_um, process.grid_um)))
    else:
        raise PlannerError(f"unsupported routing architecture {architecture!r}")
    route_blocked_xs = tuple(
        sorted(
            {
                segment.x0
                for segment in segments
                if segment.layer == feedthrough_layer
                and segment.purpose == "graph_route"
                and segment.x0 == segment.x1
            }
        )
    )
    feedthrough = _feedthrough_positions(
        process,
        width,
        count,
        feedthrough_layer,
        placements,
        extra_blocked_xs=route_blocked_xs,
    )

    pin_layer = "M2" if architecture == "three_metal_classic" else feedthrough_layer
    pin_access: dict[str, dict[str, Any]] = {}
    for input_name in circuit.inputs:
        xs = gate_xs.get(input_name)
        if not xs:
            raise PlannerError(f"{circuit.name}: input {input_name} has no MOS gate")
        x = _ceil_grid(process, sum(xs) / len(xs))
        pin_access[input_name] = {
            "layer": pin_layer,
            "x_um": x,
            "y_um": _ceil_grid(process, height / 2),
            "width_um": process.metal_width_um(pin_layer),
            "access": "legal_region_pending_drc",
        }
    for output_name in circuit.outputs:
        points = net_points.get(output_name, [])
        if not points:
            raise PlannerError(f"{circuit.name}: output {output_name} has no diffusion terminal")
        x = _ceil_grid(process, max(point[0] for point in points))
        pin_access[output_name] = {
            "layer": pin_layer,
            "x_um": x,
            "y_um": _ceil_grid(process, height / 2),
            "width_um": process.metal_width_um(pin_layer),
            "access": "legal_region_pending_drc",
        }

    blockages.extend(
        Rect(segment.layer, min(segment.x0, segment.x1), min(segment.y0, segment.y1), max(segment.x0, segment.x1), max(segment.y0, segment.y1), segment.net, segment.purpose)
        for segment in segments
        if segment.purpose not in {"feedthrough", "rail"} and segment.layer in {"M2", "M3"}
    )
    conflicts: list[dict[str, Any]] = []
    route_segments = [
        segment
        for segment in segments
        if segment.purpose.startswith("internal_net") or segment.purpose == "graph_route"
    ]
    for index, left in enumerate(route_segments):
        for right in route_segments[index + 1 :]:
            if _segments_conflict(left, right):
                conflicts.append({"left": left.as_dict(), "right": right.as_dict()})
    return segments, blockages, via_blockages, pin_access, graph_routes, feedthrough, feedthrough_layer, tuple(conflicts)


def _cheap_routing_estimate(
    process: StdcellProcess,
    circuit: CellCircuit,
    architecture: str,
    placements: dict[str, DevicePlacement],
    width: float,
    height: float,
) -> dict[str, float | int | str]:
    """Estimate routing pressure before constructing a detailed graph."""
    net_points: dict[str, list[tuple[float, float]]] = {}
    for placement in placements.values():
        for node, point in placement.routable_diffusion_points():
            net_points.setdefault(node, []).append(point)

    supplies = set(circuit.supplies)
    internal = [net for net in sorted(net_points) if net not in supplies]
    p_row = max(
        placement.y_um for placement in placements.values() if placement.polarity == "p"
    )
    n_row = max(
        placement.y_um for placement in placements.values() if placement.polarity == "n"
    )
    estimated_m2 = 0.0
    estimated_vias = 0
    estimated_span = 0.0
    cross_row_nets = 0
    for net in internal:
        points = net_points[net]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        estimated_span += span_x + span_y
        has_p_row = p_row in ys
        has_n_row = n_row in ys
        if has_p_row and has_n_row:
            cross_row_nets += 1
            estimated_m2 += span_x + process.grid_um
            estimated_vias += 2
        elif has_p_row:
            estimated_m2 += span_x + process.grid_um
            estimated_vias += 2
    if architecture == "two_metal_dense":
        feedthrough_count = 0
    else:
        feedthrough_count = max(1, int(width / max(12 * process.lambda_um, process.grid_um)))
    return {
        "cell_area_um2": width * height,
        "internal_m2_length_um": estimated_m2,
        "via_count": estimated_vias,
        "feedthrough_count": feedthrough_count,
        "estimated_route_span_um": estimated_span,
        "cross_row_net_count": cross_row_nets,
        "status": "pre_route_estimate",
    }


def _select_beam(
    options: list[dict[str, object]],
    beam_width: int,
) -> list[dict[str, object]]:
    if beam_width >= len(options):
        return options
    pareto_inputs = []
    for option in options:
        estimate = dict(option["estimate"])
        column_ir = option["column_ir"]
        estimate.update(
            diffusion_breaks=column_ir.diffusion_breaks,
            gate_mismatches=column_ir.gate_mismatches,
        )
        pareto_inputs.append({"metrics": estimate})
    front = pareto_front(pareto_inputs)
    front_set = set(front)
    def sort_key(index: int) -> tuple[object, ...]:
        column_ir = options[index]["column_ir"]
        estimate = options[index]["estimate"]
        return (
            column_ir.diffusion_breaks,
            column_ir.gate_mismatches,
            -column_ir.shared_diffusion_edges,
            float(estimate["cell_area_um2"]),
            float(estimate["internal_m2_length_um"]),
            float(estimate["via_count"]),
            float(estimate["feedthrough_count"]),
            index,
        )

    ordered = sorted(front, key=sort_key)
    ordered.extend(
        index
        for index in sorted(range(len(options)), key=sort_key)
        if index not in front_set
    )
    return [options[index] for index in ordered[:beam_width]]

def generate_candidates(
    circuit: CellCircuit,
    process: StdcellProcess,
    architecture: str = "two_metal_classic",
    max_candidates: int = 100,
    beam_width: int | None = None,
) -> tuple[CandidatePlan, ...]:
    """Generate deterministic column/geometry/routing candidate manifests."""

    process.architecture_metal_limit(architecture)
    if max_candidates < 1:
        raise PlannerError("max_candidates must be >= 1")
    if beam_width is not None and beam_width < 1:
        raise PlannerError("beam_width must be >= 1")
    if not circuit.devices_for_model(process.model_names.values()):
        raise PlannerError(f"{circuit.name}: no devices match {process.profile_name} bindings")
    topology_manifest = tuple(option.as_dict() for option in topology_options(circuit))
    input_permutations = pin_permutations(circuit)
    weak_names = weak_device_names(circuit)
    weak_scales = weak_length_scales(circuit)
    sizing_variants: list[tuple[CellCircuit, dict[str, Any]]] = []
    for scale in weak_scales:
        if scale == 1.0 or not weak_names:
            sizing_variants.append(
                (
                    circuit,
                    {
                        "scale": 1.0,
                        "weak_devices": list(weak_names),
                        "status": "baseline",
                    },
                )
            )
            continue
        devices = tuple(
            replace(
                device,
                length_um=(device.length_um or process.lmin_um) * scale
                if device.name in weak_names
                else device.length_um,
            )
            for device in circuit.devices
        )
        sizing_variants.append(
            (
                replace(circuit, devices=devices),
                {
                    "scale": scale,
                    "weak_devices": list(weak_names),
                    "status": "explicit_weak_device_long_l",
                },
            )
        )
    layout_options: list[dict[str, object]] = []
    for variant_circuit, sizing_variant in sizing_variants:
        nf_options = [_nf_options(process, device) for device in variant_circuit.devices]
        column_irs = enumerate_column_ir(variant_circuit, process, limit=8)
        for column_ir in column_irs:
            for folds in product(*nf_options):
                if len(layout_options) >= max_candidates:
                    break
                fold_map = {device.name: nf for device, nf in zip(variant_circuit.devices, folds)}
                (
                    placements,
                    width,
                    height,
                    n_y,
                    geometry_ir,
                    support_taps,
                    diffusion_bridges,
                    supply_contact_plan,
                ) = _column_layout(process, variant_circuit, fold_map, column_ir)
                layout_options.append(
                    {
                        "circuit": variant_circuit,
                        "column_ir": column_ir,
                        "placements": placements,
                        "width": width,
                        "height": height,
                        "n_y": n_y,
                        "geometry_ir": geometry_ir,
                        "support_taps": support_taps,
                        "diffusion_bridges": diffusion_bridges,
                        "supply_contact_plan": supply_contact_plan,
                        "topology_candidates": topology_manifest,
                        "pin_permutations": input_permutations,
                        "sizing_variant": sizing_variant,
                        "orientation_policy": process.row_orientation_policy,
                        "estimate": _cheap_routing_estimate(
                            process,
                            variant_circuit,
                            architecture,
                            placements,
                            width,
                            height,
                        ),
                    }
                )
            if len(layout_options) >= max_candidates:
                break
        if len(layout_options) >= max_candidates:
            break
    if beam_width is not None:
        layout_options = _select_beam(layout_options, min(beam_width, max_candidates))

    candidates: list[CandidatePlan] = []
    for index, option in enumerate(layout_options):
        variant_circuit = option["circuit"]
        column_ir = option["column_ir"]
        placements = option["placements"]
        width = option["width"]
        height = option["height"]
        n_y = option["n_y"]
        geometry_ir = option["geometry_ir"]
        support_taps = option["support_taps"]
        diffusion_bridges = option["diffusion_bridges"]
        supply_contact_plan = option["supply_contact_plan"]
        (
            segments,
            blockages,
            via_blockages,
            pin_access,
            graph_routes,
            feedthrough,
            feedthrough_layer,
            conflicts,
        ) = _route(
            process,
            variant_circuit,
            architecture,
            placements,
            width,
            height,
            n_y,
            support_taps,
        )
        internal_m2 = sum(
            abs(segment.y1 - segment.y0) + abs(segment.x1 - segment.x0)
            for segment in segments
            if segment.layer == "M2"
            and (segment.purpose.startswith("internal_net") or segment.purpose == "graph_route")
        )
        internal_m2_segments = sum(
            1
            for segment in segments
            if segment.layer == "M2"
            and (segment.purpose.startswith("internal_net") or segment.purpose == "graph_route")
        )
        via_count = len(via_blockages)
        route_width = max(width, process.grid_um)
        contactless_internal = sum(
            1
            for placement in placements.values()
            if placement.contactless_sides
            and any(
                net not in variant_circuit.ports and net not in variant_circuit.supplies
                for net, _ in placement.side_points().values()
                if net in {placement.device.drain, placement.device.source}
            )
        )
        metrics = {
            "cell_area_um2": width * height,
            "internal_m2_length_um": internal_m2,
            "internal_m2_segment_count": internal_m2_segments,
            "via_count": via_count,
            "feedthrough_count": len(feedthrough),
            "route_permeability_per_um": len(feedthrough) / route_width,
            "pin_access_count": len(pin_access),
            "diffusion_breaks": column_ir.diffusion_breaks,
            "shared_diffusion_edges": column_ir.shared_diffusion_edges,
            "gate_mismatches": column_ir.gate_mismatches,
            "aligned_gate_columns": column_ir.aligned_gate_columns,
            "line_of_diffusion_edge_count": len(diffusion_bridges) // 2,
            "contactless_internal_diffusion_count": contactless_internal,
            "routing_estimate": option["estimate"],
            "worst_case_delay": None,
            "input_capacitance": None,
            "characterization_status": "not_run",
        }
        classic_limit = 2 if architecture == "two_metal_classic" else None
        internal_m2_allowed = (
            classic_limit is None or internal_m2_segments <= classic_limit
        )
        constraints = {
            "drc": "not_run",
            "lvs": "not_run",
            "pex": "not_run",
            "pin_access": "planned",
            "rail_and_bulk_connectivity": "planned",
            "routing_contract": "planned" if internal_m2_allowed else "requires_routing_refinement",
            "internal_m2_limit_segments": classic_limit,
            "internal_m2_segment_count": internal_m2_segments,
            "internal_m2_within_limit": internal_m2_allowed,
            "feedthrough_required": architecture != "two_metal_dense",
            "feedthrough_resource_contract": {
                "preserve_over_cell_columns": True,
                "layer": feedthrough_layer,
                "count": len(feedthrough),
            },
            "rail_contract": {
                "fixed_height": True,
                "bottom_rail": "VSS",
                "top_rail": "VDD",
                "abutment": "continuous_across_site",
            },
            "orientation_policy": option["orientation_policy"],
            "supply_contact_capacity": "unknown_until_pex_or_process_data",
        }
        candidates.append(
            CandidatePlan(
                cell=variant_circuit.name,
                profile=process.profile_name,
                architecture=architecture,
                index=index,
                columns=column_ir,
                geometry_ir=geometry_ir,
                support_taps=support_taps,
                width_um=width,
                height_um=height,
                placements=tuple(placements.values()),
                orderings=(column_ir.p_order, column_ir.n_order),
                segments=tuple(segments),
                blockages=tuple(blockages),
                via_blockages=tuple(via_blockages),
                graph_routes=graph_routes,
                feedthrough_columns=feedthrough,
                feedthrough_layer=feedthrough_layer,
                pin_access=pin_access,
                metrics=metrics,
                constraints=constraints,
                route_conflicts=conflicts,
                diffusion_bridges=diffusion_bridges,
                supply_contact_plan=supply_contact_plan,
                topology_candidates=option["topology_candidates"],
                pin_permutations=option["pin_permutations"],
                sizing_variant=option["sizing_variant"],
                orientation_policy=option["orientation_policy"],
            )
        )
    if not candidates:
        raise PlannerError(f"{circuit.name}: no folding candidates")
    return tuple(candidates)
