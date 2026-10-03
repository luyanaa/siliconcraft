"""Estimated sheet-resistance graph for Manhattan layout conductors.

The graph models rectangles, Manhattan paths, and simple rectilinear polygons.
Polygon decomposition and contact spreading are engineering approximations;
unsupported geometry is rejected rather than silently converted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Iterable, Sequence


Point = tuple[float, float]


class ManhattanGeometryError(ValueError):
    """Raised when geometry cannot be represented without guessing."""


@dataclass
class _Node:
    layer: str
    point: Point
    parent: int
    rank: int = 0


@dataclass
class _Segment:
    layer: str
    start: Point
    end: Point
    width: float
    sheet_resistance: float
    width_correction: float
    cuts: dict[float, int] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return abs(self.end[0] - self.start[0]) + abs(self.end[1] - self.start[1])

    @property
    def horizontal(self) -> bool:
        return self.start[1] == self.end[1]

    def point_at(self, distance: float) -> Point:
        length = self.length
        ratio = distance / length
        return (
            self.start[0] + (self.end[0] - self.start[0]) * ratio,
            self.start[1] + (self.end[1] - self.start[1]) * ratio,
        )


@dataclass
class _Footprint:
    layer: str
    bounds: tuple[float, float, float, float]
    segment: int | None = None
    pad_node: int | None = None


@dataclass(frozen=True)
class _Contact:
    layer_a: str
    layer_b: str
    point: Point
    resistance: float
    name: str


class ManhattanResistorGraph:
    """Builds an estimated resistor network from Manhattan conductors.

    Dimensions use microns; sheet resistance uses ohms/square; contact
    resistance uses ohms per cut. ``width_correction`` is subtracted from the
    drawn wire width, matching the C35 effective-width convention.
    """

    def __init__(self) -> None:
        self._nodes: list[_Node] = []
        self._segments: list[_Segment] = []
        self._footprints: list[_Footprint] = []
        self._shorts: list[tuple[str, str, Point]] = []
        self._contacts: list[_Contact] = []
        self._labels: dict[int, str] = {}
        self._prepared = False
        self._finalized = False
        self._contact_nodes: list[tuple[_Contact, int, int]] = []
        self._node_at_cache: dict[tuple[str, Point], int] = {}

    def add_path(
        self,
        layer: str,
        points: Sequence[Point],
        width: float,
        sheet_resistance: float,
        width_correction: float = 0.0,
    ) -> None:
        """Add a Manhattan path, retaining each straight run as a resistor."""
        self._require_open()
        self._validate_material(layer, sheet_resistance, width, width_correction)
        if len(points) < 2:
            raise ManhattanGeometryError("path requires at least two points")
        path = tuple((float(x), float(y)) for x, y in points)
        for first, second in zip(path, path[1:]):
            dx, dy = second[0] - first[0], second[1] - first[1]
            if dx and dy:
                raise ManhattanGeometryError(
                    f"non-Manhattan path segment on {layer}: {first} to {second}"
                )
            if not dx and not dy:
                continue
            segment_id = self._add_segment(
                layer, first, second, width, sheet_resistance, width_correction
            )
            self._footprints.append(
                _Footprint(layer, self._segment_bounds(self._segments[segment_id]), segment_id)
            )

    def add_rectangle(
        self,
        layer: str,
        bounds: tuple[float, float, float, float],
        sheet_resistance: float,
        width_correction: float = 0.0,
    ) -> None:
        """Add a conductor rectangle as one principal-axis resistor or pad."""
        self._require_open()
        left, bottom, right, top = map(float, bounds)
        if right <= left or top <= bottom:
            raise ManhattanGeometryError(f"empty rectangle on {layer}: {bounds}")
        dx, dy = right - left, top - bottom
        width = min(dx, dy)
        self._validate_material(layer, sheet_resistance, width, width_correction)
        if dx >= dy:
            start, end = (left, (bottom + top) / 2), (right, (bottom + top) / 2)
        else:
            start, end = ((left + right) / 2, bottom), ((left + right) / 2, top)
        segment_id = self._add_segment(
            layer, start, end, width, sheet_resistance, width_correction
        )
        self._footprints.append(
            _Footprint(layer, (left, bottom, right, top), segment_id)
        )

    def add_polygon(
        self,
        layer: str,
        points: Sequence[Point],
        sheet_resistance: float,
        width_correction: float = 0.0,
        holes: Sequence[Sequence[Point]] = (),
    ) -> None:
        """Decompose a Manhattan polygon, including explicit interior holes."""
        self._require_open()
        outline = _clean_outline(points)
        hole_outlines = tuple(_clean_outline(hole) for hole in holes)
        rectangles = _decompose_orthogonal_polygon(outline, hole_outlines)
        for bounds in rectangles:
            self.add_rectangle(layer, bounds, sheet_resistance, width_correction)

    def add_contact(
        self,
        layer_a: str,
        layer_b: str,
        point: Point,
        resistance: float,
        name: str | None = None,
    ) -> None:
        """Connect two conductor layers through one explicit contact/via cut."""
        self._require_open()
        if layer_a == layer_b:
            raise ManhattanGeometryError("contact must connect two different layers")
        if resistance <= 0:
            raise ManhattanGeometryError("contact resistance must be positive")
        p = float(point[0]), float(point[1])
        self._contacts.append(
            _Contact(layer_a, layer_b, p, float(resistance), name or f"contact{len(self._contacts) + 1}")
        )

    def connect(self, layer_a: str, layer_b: str, point: Point) -> None:
        """Join overlapping conductors through an ideal ohmic interface."""
        self._require_open()
        if layer_a == layer_b:
            raise ManhattanGeometryError("short must connect two different layers")
        self._shorts.append((layer_a, layer_b, (float(point[0]), float(point[1]))))

    def prepare(self) -> None:
        """Join same-layer shapes that overlap or share a nonzero edge."""
        if self._prepared:
            return
        by_layer: dict[str, list[int]] = {}
        for index, footprint in enumerate(self._footprints):
            by_layer.setdefault(footprint.layer, []).append(index)
        for indices in by_layer.values():
            ordered = sorted(indices, key=lambda i: self._footprints[i].bounds[0])
            active: list[int] = []
            for current_index in ordered:
                current = self._footprints[current_index]
                left, bottom, right, top = current.bounds
                active = [i for i in active if self._footprints[i].bounds[2] >= left]
                for other_index in active:
                    other = self._footprints[other_index]
                    overlap_x = min(right, other.bounds[2]) - max(left, other.bounds[0])
                    overlap_y = min(top, other.bounds[3]) - max(bottom, other.bounds[1])
                    if overlap_x < 0 or overlap_y < 0 or (overlap_x == 0 and overlap_y == 0):
                        continue
                    self._join_footprints(current, other, left, bottom, right, top)
                active.append(current_index)
        self._prepared = True

    def finalize(self) -> None:
        """Resolve ideal shorts and contact endpoints before naming graph nodes."""
        if self._finalized:
            return
        self.prepare()
        for layer_a, layer_b, point in self._shorts:
            self._union(self.node_at(layer_a, point), self.node_at(layer_b, point))
        self._contact_nodes = [
            (
                contact,
                self.find(self.node_at(contact.layer_a, contact.point)),
                self.find(self.node_at(contact.layer_b, contact.point)),
            )
            for contact in self._contacts
        ]
        self._finalized = True

    def node_at(self, layer: str, point: Point) -> int:
        """Return/split the nearest conductor node containing ``point``."""
        self.prepare()
        p = float(point[0]), float(point[1])
        key = (layer, p)
        cached = self._node_at_cache.get(key)
        if cached is not None:
            return self.find(cached)
        choices: list[tuple[float, int]] = []
        for footprint in self._footprints:
            if footprint.layer != layer:
                continue
            left, bottom, right, top = footprint.bounds
            if p[0] < left - 1e-9 or p[0] > right + 1e-9 or p[1] < bottom - 1e-9 or p[1] > top + 1e-9:
                continue
            if footprint.pad_node is not None:
                choices.append((0.0, footprint.pad_node))
            else:
                segment = self._segments[footprint.segment]
                projected, distance = self._project(segment, p)
                if distance <= segment.width / 2 + 1e-9:
                    node = self._split_at(segment, projected)
                    choices.append((distance, node))
        if not choices:
            raise ManhattanGeometryError(f"no {layer} conductor at anchor {p}")
        _, node = min(choices, key=lambda choice: choice[0])
        self._node_at_cache[key] = node
        return self.find(node)

    def label(self, layer: str, point: Point, name: str) -> int:
        """Attach a SPICE net name to a physical conductor point."""
        node = self.find(self.node_at(layer, point))
        self._labels.setdefault(node, spice_identifier(name))
        return node

    def node_name(self, node: int) -> str:
        """Return the canonical SPICE name after all ideal connectivity is resolved."""
        if not self._finalized:
            raise ManhattanGeometryError("finalize graph before naming nodes")
        root = self.find(node)
        return self._labels.get(root, f"rcx_n{root}")

    def elements(self) -> list[str]:
        """Finalize and emit graph resistors as SPICE R elements."""
        self.finalize()
        contact_nodes = self._contact_nodes
        lines: list[str] = []
        serial = 0
        for segment in self._segments:
            effective_width = segment.width - segment.width_correction
            if effective_width <= 0:
                raise ManhattanGeometryError(
                    f"effective width is nonpositive on {segment.layer}: "
                    f"drawn={segment.width:g}um correction={segment.width_correction:g}um"
                )
            for start, end in zip(sorted(segment.cuts), sorted(segment.cuts)[1:]):
                a, b = self.find(segment.cuts[start]), self.find(segment.cuts[end])
                if a == b or end <= start:
                    continue
                resistance = segment.sheet_resistance * (end - start) / effective_width
                if resistance <= 0:
                    raise ManhattanGeometryError("computed wire resistance is nonpositive")
                serial += 1
                lines.append(
                    f"Rrcx{serial} {self.node_name(a)} {self.node_name(b)} {resistance:.9g}"
                )
        for contact, a, b in contact_nodes:
            if a == b:
                raise ManhattanGeometryError(
                    f"{contact.name} unexpectedly shorts {contact.layer_a} to {contact.layer_b}"
                )
            serial += 1
            lines.append(
                f"Rrcx{serial} {self.node_name(a)} {self.node_name(b)} {contact.resistance:.9g}"
            )
        return lines

    def find(self, node: int) -> int:
        parent = self._nodes[node].parent
        if parent != node:
            self._nodes[node].parent = self.find(parent)
        return self._nodes[node].parent

    def _require_open(self) -> None:
        if self._prepared:
            raise ManhattanGeometryError("cannot add geometry after graph preparation")

    @staticmethod
    def _validate_material(layer: str, sheet_resistance: float, width: float, correction: float) -> None:
        if not layer:
            raise ManhattanGeometryError("conductor layer name is empty")
        if sheet_resistance <= 0:
            raise ManhattanGeometryError(f"sheet resistance must be positive for {layer}")
        if width <= 0 or correction < 0 or width <= correction:
            raise ManhattanGeometryError(
                f"invalid effective width for {layer}: drawn={width:g}um correction={correction:g}um"
            )

    def _new_node(self, layer: str, point: Point) -> int:
        node = len(self._nodes)
        self._nodes.append(_Node(layer, point, node))
        return node

    def _add_segment(
        self,
        layer: str,
        start: Point,
        end: Point,
        width: float,
        sheet_resistance: float,
        correction: float,
    ) -> int:
        if start[0] != end[0] and start[1] != end[1]:
            raise ManhattanGeometryError(f"non-Manhattan segment: {start} to {end}")
        length = abs(end[0] - start[0]) + abs(end[1] - start[1])
        if length <= 0:
            raise ManhattanGeometryError("zero-length conductor segment")
        segment = _Segment(layer, start, end, width, sheet_resistance, correction)
        start_node = self._new_node(layer, start)
        end_node = self._new_node(layer, end)
        segment.cuts = {0.0: start_node, length: end_node}
        segment_id = len(self._segments)
        self._segments.append(segment)
        return segment_id

    @staticmethod
    def _segment_bounds(segment: _Segment) -> tuple[float, float, float, float]:
        half = segment.width / 2
        return (
            min(segment.start[0], segment.end[0]) - (0 if segment.horizontal else half),
            min(segment.start[1], segment.end[1]) - (half if segment.horizontal else 0),
            max(segment.start[0], segment.end[0]) + (0 if segment.horizontal else half),
            max(segment.start[1], segment.end[1]) + (half if segment.horizontal else 0),
        )


    def _join_footprints(
        self,
        a: _Footprint,
        b: _Footprint,
        left: float,
        bottom: float,
        right: float,
        top: float,
    ) -> None:
        point = ((max(left, b.bounds[0]) + min(right, b.bounds[2])) / 2,
                 (max(bottom, b.bounds[1]) + min(top, b.bounds[3])) / 2)
        if a.segment is not None and b.segment is not None:
            first, second = self._segments[a.segment], self._segments[b.segment]
            if first.horizontal != second.horizontal:
                horizontal, vertical = (first, second) if first.horizontal else (second, first)
                crossing = (vertical.start[0], horizontal.start[1])
                if (
                    min(horizontal.start[0], horizontal.end[0]) <= crossing[0]
                    <= max(horizontal.start[0], horizontal.end[0])
                    and min(vertical.start[1], vertical.end[1]) <= crossing[1]
                    <= max(vertical.start[1], vertical.end[1])
                ):
                    point = crossing
            elif first.horizontal and first.start[1] == second.start[1]:
                point = (
                    (max(min(first.start[0], first.end[0]), min(second.start[0], second.end[0]))
                     + min(max(first.start[0], first.end[0]), max(second.start[0], second.end[0]))) / 2,
                    first.start[1],
                )
            elif not first.horizontal and first.start[0] == second.start[0]:
                point = (
                    first.start[0],
                    (max(min(first.start[1], first.end[1]), min(second.start[1], second.end[1]))
                     + min(max(first.start[1], first.end[1]), max(second.start[1], second.end[1]))) / 2,
                )
        if a.pad_node is not None and b.pad_node is not None:
            self._union(a.pad_node, b.pad_node)
            return
        a_node = a.pad_node if a.pad_node is not None else self._split_at(
            self._segments[a.segment], self._project(self._segments[a.segment], point)[0]
        )
        b_node = b.pad_node if b.pad_node is not None else self._split_at(
            self._segments[b.segment], self._project(self._segments[b.segment], point)[0]
        )
        self._union(a_node, b_node)

    @staticmethod
    def _project(segment: _Segment, point: Point) -> tuple[Point, float]:
        left, bottom = min(segment.start[0], segment.end[0]), min(segment.start[1], segment.end[1])
        right, top = max(segment.start[0], segment.end[0]), max(segment.start[1], segment.end[1])
        projected = (min(max(point[0], left), right), segment.start[1]) if segment.horizontal else (
            segment.start[0], min(max(point[1], bottom), top)
        )
        return projected, hypot(point[0] - projected[0], point[1] - projected[1])

    def _split_at(self, segment: _Segment, point: Point) -> int:
        projected, distance = self._project(segment, point)
        if distance > segment.width / 2 + 1e-9:
            raise ManhattanGeometryError(
                f"anchor {point} is outside {segment.layer} conductor width"
            )
        scalar = abs(projected[0] - segment.start[0]) + abs(projected[1] - segment.start[1])
        for existing_scalar, node in segment.cuts.items():
            if abs(existing_scalar - scalar) <= 1e-9:
                return node
        node = self._new_node(segment.layer, projected)
        segment.cuts[scalar] = node
        return node

    def _union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        na, nb = self._nodes[ra], self._nodes[rb]
        if na.rank < nb.rank:
            na.parent = rb
        elif na.rank > nb.rank:
            nb.parent = ra
        else:
            nb.parent = ra
            na.rank += 1
        name_a, name_b = self._labels.pop(ra, None), self._labels.pop(rb, None)
        root = self.find(ra)
        if name_a or name_b:
            self._labels.setdefault(root, name_a or name_b)


def _clean_outline(points: Sequence[Point]) -> tuple[Point, ...]:
    outline = tuple((float(x), float(y)) for x, y in points)
    if len(outline) > 1 and outline[0] == outline[-1]:
        outline = outline[:-1]
    if len(outline) < 4:
        raise ManhattanGeometryError("polygon requires at least four distinct vertices")
    if len(set(outline)) != len(outline):
        raise ManhattanGeometryError("self-touching or repeated polygon vertices are unsupported")
    for a, b in zip(outline, (*outline[1:], outline[0])):
        if a[0] != b[0] and a[1] != b[1]:
            raise ManhattanGeometryError(f"angled polygon edge is unsupported: {a} to {b}")
        if a == b:
            raise ManhattanGeometryError("zero-length polygon edge")
    return outline


def _decompose_orthogonal_polygon(
    outline: Sequence[Point],
    holes: Sequence[Sequence[Point]] = (),
) -> list[tuple[float, float, float, float]]:
    rings = (outline, *holes)
    ys = sorted({point[1] for ring in rings for point in ring})
    rectangles: list[tuple[float, float, float, float]] = []
    for bottom, top in zip(ys, ys[1:]):
        if top <= bottom:
            continue
        mid_y = (bottom + top) / 2
        crossings: list[float] = []
        for ring in rings:
            for a, b in zip(ring, (*ring[1:], ring[0])):
                if a[0] == b[0] and min(a[1], b[1]) < mid_y < max(a[1], b[1]):
                    crossings.append(a[0])
        crossings.sort()
        if len(crossings) % 2:
            raise ManhattanGeometryError("invalid rectilinear polygon crossing parity")
        for left, right in zip(crossings[::2], crossings[1::2]):
            if right > left:
                rectangles.append((left, bottom, right, top))
    if not rectangles:
        raise ManhattanGeometryError("polygon has no positive-area Manhattan decomposition")

    def area(ring: Sequence[Point]) -> float:
        return abs(sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(ring, (*ring[1:], ring[0]))
        )) / 2

    polygon_area = area(outline) - sum(area(hole) for hole in holes)
    decomposed_area = sum(
        (right - left) * (top - bottom)
        for left, bottom, right, top in rectangles
    )
    if polygon_area <= 0 or abs(polygon_area - decomposed_area) > max(
        1e-9, polygon_area * 1e-9
    ):
        raise ManhattanGeometryError("polygon is self-intersecting or not decomposable")
    return rectangles


def spice_identifier(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "_$" else "_" for c in name)
    if not cleaned:
        raise ManhattanGeometryError("SPICE net label is empty")
    return cleaned
