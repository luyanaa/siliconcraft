"""Small layer-aware routing graph for double-row CMOS cells."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
from typing import Iterable, Mapping


class RoutingError(ValueError):
    """Raised when a net has no legal path in the routing graph."""


@dataclass(frozen=True, order=True)
class RoutingNode:
    x_um: float
    y_um: float
    layer: str


@dataclass(frozen=True)
class RoutingEdge:
    start: RoutingNode
    end: RoutingNode
    cost: float
    kind: str
    capacity: int = 1

    @property
    def key(self) -> tuple[RoutingNode, RoutingNode, str]:
        first, second = sorted((self.start, self.end))
        return first, second, self.kind


@dataclass(frozen=True)
class AccessPoint:
    net: str
    node: RoutingNode
    purpose: str


@dataclass(frozen=True)
class RoutingPolicy:
    architecture: str
    layer_cost: Mapping[str, float]
    preferred_direction: Mapping[str, str]
    via_cost: Mapping[tuple[str, str], float]
    global_layer: str
    congestion_penalty: float = 10.0
    wrong_direction_penalty: float = 2.0
    allowed_layers: tuple[str, ...] = ()
    resistance_per_um: Mapping[str, float] = field(default_factory=dict)
    max_useful_length_um: Mapping[str, float] = field(default_factory=dict)
    resistance_weight: float = 1.0
    log_resistance: bool = True

    @classmethod
    def for_architecture(cls, architecture: str) -> "RoutingPolicy":
        if architecture == "two_metal_classic":
            return cls(
                architecture,
                {"M1": 1.0, "M2": 5.0},
                {"M1": "horizontal", "M2": "vertical"},
                {("M1", "M2"): 3.0},
                "M2",
            )
        if architecture == "two_metal_dense":
            return cls(
                architecture,
                {"M1": 1.0, "M2": 2.0},
                {"M1": "horizontal", "M2": "vertical"},
                {("M1", "M2"): 2.0},
                "M2",
            )
        if architecture == "three_metal_classic":
            return cls(
                architecture,
                {"M1": 1.0, "M2": 2.0, "M3": 8.0},
                {"M1": "horizontal", "M2": "horizontal", "M3": "vertical"},
                {("M1", "M2"): 2.0, ("M2", "M3"): 5.0},
                "M3",
            )
        raise RoutingError(f"unsupported routing architecture {architecture!r}")
    @classmethod
    def from_grammar(
        cls,
        grammar,
        *,
        region: str = "default",
        allow_experimental: bool = True,
        experimental_cost_multiplier: float = 4.0,
    ) -> "RoutingPolicy":
        from common.routing_grammar import EXPERIMENTAL

        layers = tuple(
            name
            for name in grammar.routing_layers(allow_experimental=allow_experimental)
            if grammar.conductor_allowed(name, region, allow_experimental=allow_experimental)
        )
        layer_cost = {}
        preferred_direction = {}
        resistance_per_um = {}
        max_useful_length_um = {}
        for index, name in enumerate(layers):
            conductor = grammar.conductors[name]
            cost = max(float(conductor.cost), 1e-9)
            if conductor.continuity.status == EXPERIMENTAL:
                cost *= experimental_cost_multiplier
            layer_cost[name] = cost
            preferred_direction[name] = "horizontal" if index % 2 == 0 else "vertical"
            electrical = conductor.electrical
            resistance = electrical.get("resistance_ohm_per_um")
            if resistance is None:
                sheet = electrical.get("sheet_resistance_ohm_per_square")
                width = electrical.get("nominal_width_um")
                if isinstance(sheet, (int, float)) and isinstance(width, (int, float)) and float(width) > 0:
                    resistance = float(sheet) / float(width)
            if isinstance(resistance, (int, float)) and float(resistance) >= 0:
                resistance_per_um[name] = float(resistance)
            maximum = conductor.max_useful_length_um
            if isinstance(maximum, (int, float)) and float(maximum) > 0:
                max_useful_length_um[name] = float(maximum)
        via_cost = {}
        for source in layers:
            for target in layers:
                if source != target and grammar.transition_allowed(
                    source, target, allow_experimental=allow_experimental
                ):
                    via_cost[(source, target)] = experimental_cost_multiplier
        return cls(
            architecture=f"grammar:{grammar.profile}",
            layer_cost=layer_cost,
            preferred_direction=preferred_direction,
            via_cost=via_cost,
            global_layer=layers[-1] if layers else "",
            resistance_per_um=resistance_per_um,
            max_useful_length_um=max_useful_length_um,
            allowed_layers=layers,
        )

    def edge_cost(self, layer: str, direction: str, length_um: float) -> float:
        length_um = max(length_um, 1e-9)
        base = self.layer_cost[layer] * length_um
        if self.preferred_direction.get(layer) != direction:
            base += self.wrong_direction_penalty * length_um
        resistance = self.resistance_per_um.get(layer)
        if resistance is not None:
            ohms = resistance * length_um
            base += self.resistance_weight * (
                math.log1p(ohms) if self.log_resistance else ohms
            )
        maximum = self.max_useful_length_um.get(layer)
        if maximum is not None and length_um > maximum:
            base += self.resistance_weight * 100.0 * (length_um / maximum - 1.0)
        return base



class RoutingGraph:
    """Rectilinear graph with explicit layer and via edges."""

    def __init__(
        self,
        nodes: Iterable[RoutingNode],
        edges: Iterable[RoutingEdge],
        congestion_penalty: float = 10.0,
    ):
        self.nodes = tuple(sorted(set(nodes)))
        self.adjacency: dict[RoutingNode, list[RoutingEdge]] = {node: [] for node in self.nodes}
        self.congestion_penalty = congestion_penalty
        for edge in edges:
            self.adjacency.setdefault(edge.start, []).append(edge)
            self.adjacency.setdefault(edge.end, []).append(
                RoutingEdge(edge.end, edge.start, edge.cost, edge.kind, edge.capacity)
            )

    @classmethod
    def rectangular(
        cls,
        x_coords: Iterable[float],
        y_coords: Iterable[float],
        layers: Iterable[str],
        policy: RoutingPolicy | None = None,
        *,
        grammar=None,
        region: str = "default",
        allow_experimental: bool = True,
    ) -> "RoutingGraph":
        if grammar is not None:
            if policy is not None:
                raise RoutingError("pass either policy or grammar, not both")
            policy = RoutingPolicy.from_grammar(
                grammar,
                region=region,
                allow_experimental=allow_experimental,
            )
        if policy is None:
            raise RoutingError("rectangular graph requires a routing policy or grammar")
        xs = tuple(sorted(set(float(value) for value in x_coords)))
        ys = tuple(sorted(set(float(value) for value in y_coords)))
        allowed = set(policy.allowed_layers)
        layer_names = tuple(
            layer
            for layer in layers
            if layer in policy.layer_cost and (not allowed or layer in allowed)
        )
        nodes = [RoutingNode(x, y, layer) for layer in layer_names for x in xs for y in ys]
        edges: list[RoutingEdge] = []
        for layer in layer_names:
            for y in ys:
                for left, right in zip(xs, xs[1:]):
                    edges.append(
                        RoutingEdge(
                            RoutingNode(left, y, layer),
                            RoutingNode(right, y, layer),
                            policy.edge_cost(layer, "horizontal", right - left),
                            "wire",
                        )
                    )
            for x in xs:
                for bottom, top in zip(ys, ys[1:]):
                    edges.append(
                        RoutingEdge(
                            RoutingNode(x, bottom, layer),
                            RoutingNode(x, top, layer),
                            policy.edge_cost(layer, "vertical", top - bottom),
                            "wire",
                        )
                    )
        ordered_layers = list(layer_names)
        for lower_index, lower in enumerate(ordered_layers):
            for upper in ordered_layers[lower_index + 1:]:
                via_cost = policy.via_cost.get((lower, upper))
                if via_cost is None:
                    via_cost = policy.via_cost.get((upper, lower))
                if via_cost is None:
                    continue
                for x in xs:
                    for y in ys:
                        edges.append(
                            RoutingEdge(
                                RoutingNode(x, y, lower),
                                RoutingNode(x, y, upper),
                                via_cost,
                                "via",
                            )
                        )
        return cls(nodes, edges, congestion_penalty=policy.congestion_penalty)
    def _edge_for_step(
        self,
        start: RoutingNode,
        end: RoutingNode,
        usage: Mapping[tuple[RoutingNode, RoutingNode, str], int],
        blocked: set[tuple[RoutingNode, RoutingNode, str]],
    ) -> RoutingEdge | None:
        candidates = [
            edge
            for edge in self.adjacency.get(start, ())
            if edge.end == end and edge.key not in blocked
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda edge: (
                edge.cost + usage.get(edge.key, 0) * self.congestion_penalty,
                edge.kind,
            ),
        )

    def _segment(
        self,
        start: RoutingNode,
        end: RoutingNode,
        usage: Mapping[tuple[RoutingNode, RoutingNode, str], int],
        blocked: set[tuple[RoutingNode, RoutingNode, str]],
    ) -> tuple[RoutingEdge, ...] | None:
        if start.layer != end.layer:
            return None
        if start.x_um != end.x_um and start.y_um != end.y_um:
            return None
        if start == end:
            return ()
        coordinates = (
            sorted(
                node.y_um
                for node in self.nodes
                if node.layer == start.layer
                and node.x_um == start.x_um
                and min(start.y_um, end.y_um) <= node.y_um <= max(start.y_um, end.y_um)
            )
            if start.x_um == end.x_um
            else sorted(
                node.x_um
                for node in self.nodes
                if node.layer == start.layer
                and node.y_um == start.y_um
                and min(start.x_um, end.x_um) <= node.x_um <= max(start.x_um, end.x_um)
            )
        )
        if start.x_um == end.x_um and start.y_um > end.y_um:
            coordinates.reverse()
        if start.y_um == end.y_um and start.x_um > end.x_um:
            coordinates.reverse()
        points = [
            RoutingNode(
                start.x_um if start.x_um == end.x_um else coordinate,
                coordinate if start.x_um == end.x_um else start.y_um,
                start.layer,
            )
            for coordinate in coordinates
        ]
        if not points or points[0] != start or points[-1] != end:
            return None
        path: list[RoutingEdge] = []
        for left, right in zip(points, points[1:]):
            edge = self._edge_for_step(left, right, usage, blocked)
            if edge is None:
                return None
            path.append(edge)
        return tuple(path)

    def pattern_route(
        self,
        starts: Iterable[RoutingNode],
        goals: Iterable[RoutingNode],
        usage: Mapping[tuple[RoutingNode, RoutingNode, str], int] | None = None,
        blocked: set[tuple[RoutingNode, RoutingNode, str]] | None = None,
    ) -> tuple[RoutingEdge, ...] | None:
        """Try straight, L, then two-bend Z patterns before maze search."""
        usage = usage or {}
        blocked = blocked or set()
        candidates: list[tuple[float, tuple[RoutingEdge, ...]]] = []
        for start in sorted(set(starts)):
            for goal in sorted(set(goals)):
                if start.layer != goal.layer:
                    continue
                layer_x = sorted(node.x_um for node in self.nodes if node.layer == start.layer)
                layer_y = sorted(node.y_um for node in self.nodes if node.layer == start.layer)
                waypoints: list[tuple[RoutingNode, ...]] = [
                    (start, goal),
                    (start, RoutingNode(goal.x_um, start.y_um, start.layer), goal),
                    (start, RoutingNode(start.x_um, goal.y_um, start.layer), goal),
                ]
                waypoints.extend(
                    (
                        start,
                        RoutingNode(x, start.y_um, start.layer),
                        RoutingNode(x, goal.y_um, start.layer),
                        goal,
                    )
                    for x in layer_x
                    if x not in {start.x_um, goal.x_um}
                )
                waypoints.extend(
                    (
                        start,
                        RoutingNode(start.x_um, y, start.layer),
                        RoutingNode(goal.x_um, y, start.layer),
                        goal,
                    )
                    for y in layer_y
                    if y not in {start.y_um, goal.y_um}
                )
                seen: set[tuple[RoutingNode, ...]] = set()
                for points in waypoints:
                    if points in seen:
                        continue
                    seen.add(points)
                    path: list[RoutingEdge] = []
                    valid = True
                    for left, right in zip(points, points[1:]):
                        segment = self._segment(left, right, usage, blocked)
                        if segment is None:
                            valid = False
                            break
                        path.extend(segment)
                    if valid:
                        path_tuple = tuple(path)
                        candidates.append(
                            (
                                sum(
                                    edge.cost + usage.get(edge.key, 0) * self.congestion_penalty
                                    for edge in path_tuple
                                ),
                                path_tuple,
                            )
                        )
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], tuple(edge.key for edge in item[1])))[1]

    def route_multi_terminal(
        self,
        terminals: Iterable[RoutingNode],
        usage: Mapping[tuple[RoutingNode, RoutingNode, str], int] | None = None,
        blocked: set[tuple[RoutingNode, RoutingNode, str]] | None = None,
    ) -> tuple[RoutingEdge, ...]:
        """Connect terminals by Manhattan-distance MST order plus incremental routes."""
        terminals = tuple(sorted(set(terminals)))
        if len(terminals) < 2:
            return ()
        usage_map = dict(usage or {})
        blocked = blocked or set()
        tree = {terminals[0]}
        remaining = set(terminals[1:])
        result: list[RoutingEdge] = []
        while remaining:
            target = min(
                remaining,
                key=lambda node: (
                    min(
                        abs(node.x_um - root.x_um)
                        + abs(node.y_um - root.y_um)
                        + (0.0 if node.layer == root.layer else 1.0)
                        for root in tree
                    ),
                    node,
                ),
            )
            path = self.route_two_terminal((target,), tree, usage=usage_map, blocked=blocked)
            result.extend(path)
            for edge in path:
                usage_map[edge.key] = usage_map.get(edge.key, 0) + 1
                tree.add(edge.start)
                tree.add(edge.end)
            tree.add(target)
            remaining.remove(target)
        return tuple(result)

    def route_two_terminal(
        self,
        starts: Iterable[RoutingNode],
        goals: Iterable[RoutingNode],
        usage: Mapping[tuple[RoutingNode, RoutingNode, str], int] | None = None,
        blocked: set[tuple[RoutingNode, RoutingNode, str]] | None = None,
    ) -> tuple[RoutingEdge, ...]:
        starts = tuple(sorted(set(starts)))
        goals = set(goals)
        if not starts or not goals:
            raise RoutingError("route requires at least one start and goal access point")
        usage = usage or {}
        blocked = blocked or set()
        pattern = self.pattern_route(starts, goals, usage=usage, blocked=blocked)
        if pattern is not None:
            return pattern
        goal_xy = tuple(sorted(goals))

        def heuristic(node: RoutingNode) -> float:
            return min(
                abs(node.x_um - goal.x_um) + abs(node.y_um - goal.y_um) + (0.0 if node.layer == goal.layer else 1.0)
                for goal in goal_xy
            )

        queue: list[tuple[float, float, RoutingNode]] = []
        previous: dict[RoutingNode, tuple[RoutingNode, RoutingEdge] | None] = {}
        distance: dict[RoutingNode, float] = {}
        for start in starts:
            if start not in self.adjacency:
                continue
            distance[start] = 0.0
            previous[start] = None
            heapq.heappush(queue, (heuristic(start), 0.0, start))
        while queue:
            _, cost, node = heapq.heappop(queue)
            if cost != distance.get(node):
                continue
            if node in goals:
                path: list[RoutingEdge] = []
                current = node
                while previous[current] is not None:
                    parent, edge = previous[current]
                    path.append(edge)
                    current = parent
                return tuple(reversed(path))
            for edge in self.adjacency.get(node, ()):
                if edge.key in blocked:
                    continue
                congestion = usage.get(edge.key, 0)
                next_cost = cost + edge.cost + congestion * self.congestion_penalty
                if next_cost >= distance.get(edge.end, math.inf):
                    continue
                distance[edge.end] = next_cost
                previous[edge.end] = (node, edge)
                heapq.heappush(queue, (next_cost + heuristic(edge.end), next_cost, edge.end))
        raise RoutingError(
            f"no route from {[start for start in starts]!r} to {sorted(goals)!r}; "
            f"blocked_edges={len(blocked)}"
        )


class NegotiatedRouter:
    """Deterministic rip-up/reroute router for small cell nets."""

    def __init__(self, graph: RoutingGraph, max_iterations: int = 32):
        self.graph = graph
        self.max_iterations = max_iterations

    def route(self, nets: Mapping[str, tuple[tuple[RoutingNode, ...], tuple[RoutingNode, ...]]]) -> dict[str, tuple[RoutingEdge, ...]]:
        names = tuple(sorted(nets))
        previous: dict[str, tuple[RoutingEdge, ...]] = {}
        history: dict[tuple[RoutingNode, RoutingNode, str], int] = {}
        overflow: list[tuple[RoutingNode, RoutingNode, str]] = []
        for _iteration in range(self.max_iterations):
            usage: dict[tuple[RoutingNode, RoutingNode, str], int] = dict(history)
            current: dict[str, tuple[RoutingEdge, ...]] = {}
            for name in names:
                starts, goals = nets[name]
                path = self.graph.route_two_terminal(starts, goals, usage=usage)
                current[name] = path
                for edge in path:
                    usage[edge.key] = usage.get(edge.key, 0) + 1
            overflow = [key for key, count in usage.items() if count > 1]
            if not overflow:
                return current
            previous = current
            for key in overflow:
                history[key] = history.get(key, 0) + usage[key] - 1
        raise RoutingError(
            f"negotiated routing failed after {self.max_iterations} iterations; "
            f"overflow_edges={len(overflow)} nets={list(previous)}"
        )
