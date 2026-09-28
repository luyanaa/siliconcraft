"""Deterministic geometry-only Pareto filtering for stdcell candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


OBJECTIVES = (
    "cell_area_um2",
    "internal_m2_length_um",
    "via_count",
    "feedthrough_count",
)
PLACEMENT_OBJECTIVES = (
    "diffusion_breaks",
    "gate_mismatches",
)


def _metrics(candidate: Any) -> Mapping[str, float]:
    if isinstance(candidate, Mapping):
        return candidate["metrics"]
    return candidate.metrics


def _objective_names(metrics: Mapping[str, float]) -> tuple[str, ...]:
    return OBJECTIVES + tuple(
        name for name in PLACEMENT_OBJECTIVES if name in metrics
    )


def dominates(left: Any, right: Any) -> bool:
    """Return whether ``left`` is no worse in available geometry objectives."""
    left_metrics = _metrics(left)
    right_metrics = _metrics(right)
    names = _objective_names(left_metrics)
    if any(name not in right_metrics for name in names):
        names = OBJECTIVES
    values = [
        (float(left_metrics[name]), float(right_metrics[name]))
        for name in names
    ]
    return all(left_value <= right_value for left_value, right_value in values) and any(
        left_value < right_value for left_value, right_value in values
    )

def pareto_front(candidates: Sequence[Any]) -> tuple[int, ...]:
    """Return non-dominated candidate positions in stable input order."""
    return tuple(
        index
        for index, candidate in enumerate(candidates)
        if not any(
            other_index != index and dominates(other, candidate)
            for other_index, other in enumerate(candidates)
        )
    )


def rank_geometry(candidates: Sequence[Any]) -> dict[str, Any]:
    """Return an auditable geometry-only ranking without timing assumptions."""
    front = pareto_front(candidates)
    rows = []
    for position, candidate in enumerate(candidates):
        candidate_index = (
            candidate.get("candidate_index", position)
            if isinstance(candidate, Mapping)
            else candidate.index
        )
        dominated_by = [
            other_position
            for other_position, other in enumerate(candidates)
            if other_position != position and dominates(other, candidate)
        ]
        rows.append(
            {
                "candidate_index": candidate_index,
                "input_position": position,
                "pareto_front": position in front,
                "dominated_by_positions": dominated_by,
                "objectives": {
                    name: float(_metrics(candidate)[name])
                    for name in _objective_names(_metrics(candidate))
                },
            }
        )
    rows.sort(key=lambda row: (not row["pareto_front"], len(row["dominated_by_positions"]), row["input_position"]))
    available_placement = [
        name
        for name in PLACEMENT_OBJECTIVES
        if all(name in _metrics(candidate) for candidate in candidates)
    ]
    objective_names = OBJECTIVES + tuple(available_placement)
    return {
        "kind": "stdcell_geometry_pareto",
        "objective_direction": "minimize",
        "objectives": list(objective_names),
        "front_candidate_indices": [candidates[position].get("candidate_index", position) if isinstance(candidates[position], Mapping) else candidates[position].index for position in front],
        "characterization_status": "not_run",
        "candidates": rows,
    }
