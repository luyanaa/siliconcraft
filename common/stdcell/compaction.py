"""One-dimensional feature compaction by difference constraints."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Iterable


class CompactionError(ValueError):
    """Raised when placement constraints are inconsistent."""


@dataclass(frozen=True)
class Feature:
    name: str
    half_width_um: float
    kind: str


@dataclass(frozen=True)
class DifferenceConstraint:
    left: str
    right: str
    minimum_distance_um: float
    reason: str


@dataclass(frozen=True)
class CompactedGeometry:
    coordinates_um: dict[str, float]
    width_um: float
    constraints: tuple[DifferenceConstraint, ...]

    def as_dict(self) -> dict:
        return {
            "coordinates_um": self.coordinates_um,
            "width_um": self.width_um,
            "constraints": [
                {
                    "left": constraint.left,
                    "right": constraint.right,
                    "minimum_distance_um": constraint.minimum_distance_um,
                    "reason": constraint.reason,
                }
                for constraint in self.constraints
            ],
        }


def compact_linear(
    features: Iterable[Feature],
    constraints: Iterable[DifferenceConstraint],
    left_edge_um: float = 0.0,
) -> CompactedGeometry:
    """Solve ``x[right] - x[left] >= d`` by longest-path relaxation."""

    features = tuple(features)
    constraints = tuple(constraints)
    names = {feature.name for feature in features}
    if len(names) != len(features):
        raise CompactionError("feature names must be unique")
    if any(constraint.left not in names or constraint.right not in names for constraint in constraints):
        raise CompactionError("constraint references an unknown feature")
    distances = {name: -inf for name in names}
    distances[features[0].name] = left_edge_um + features[0].half_width_um if features else left_edge_um
    edges = list(constraints)
    for feature in features[1:]:
        distances[feature.name] = left_edge_um + feature.half_width_um
    for _ in range(len(features)):
        changed = False
        for constraint in edges:
            candidate = distances[constraint.left] + constraint.minimum_distance_um
            if candidate > distances[constraint.right]:
                distances[constraint.right] = candidate
                changed = True
        if not changed:
            break
    else:
        raise CompactionError("difference constraints contain a positive cycle")
    coordinates = {
        feature.name: distances[feature.name]
        for feature in features
    }
    right = max(
        coordinates[feature.name] + feature.half_width_um
        for feature in features
    ) if features else left_edge_um
    return CompactedGeometry(coordinates, right - left_edge_um, constraints)
