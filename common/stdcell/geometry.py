"""Placement-independent geometry IR for a generated cell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.stdcell.compaction import CompactedGeometry, DifferenceConstraint, Feature


@dataclass(frozen=True)
class GeometryIR:
    features: tuple[Feature, ...]
    constraints: tuple[DifferenceConstraint, ...]
    compaction: CompactedGeometry
    height_um: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "features": [
                {"name": feature.name, "half_width_um": feature.half_width_um, "kind": feature.kind}
                for feature in self.features
            ],
            "compaction": self.compaction.as_dict(),
            "height_um": self.height_um,
        }
