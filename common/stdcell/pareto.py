"""Deterministic geometry-only Pareto filtering for stdcell candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MIN_OBJECTIVES = (
    "cell_area_um2",
    "internal_m2_length_um",
    "via_count",
)
RESOURCE_OBJECTIVES = (
    "route_permeability_per_um",
    "estimated_route_permeability_per_um",
    "feedthrough_count",
)
OBJECTIVES = MIN_OBJECTIVES + ("feedthrough_count",)
PLACEMENT_OBJECTIVES = (
    "diffusion_breaks",
    "gate_mismatches",
)
OBJECTIVE_DIRECTIONS = {
    **{name: "minimize" for name in MIN_OBJECTIVES + PLACEMENT_OBJECTIVES},
    "route_permeability_per_um": "maximize",
    "estimated_route_permeability_per_um": "maximize",
    "feedthrough_count": "maximize",
}


def _metrics(candidate: Any) -> Mapping[str, float]:
    if isinstance(candidate, Mapping):
        return candidate["metrics"]
    return candidate.metrics


def _objective_names(
    left_metrics: Mapping[str, float],
    right_metrics: Mapping[str, float],
) -> tuple[str, ...]:
    names = [
        name
        for name in MIN_OBJECTIVES
        if name in left_metrics and name in right_metrics
    ]
    permeability = next(
        (
            name
            for name in RESOURCE_OBJECTIVES
            if name != "feedthrough_count"
            and name in left_metrics
            and name in right_metrics
        ),
        None,
    )
    if permeability is not None:
        names.append(permeability)
    elif "feedthrough_count" in left_metrics and "feedthrough_count" in right_metrics:
        names.append("feedthrough_count")
    names.extend(
        name
        for name in PLACEMENT_OBJECTIVES
        if name in left_metrics and name in right_metrics
    )
    return tuple(names)


def dominates(left: Any, right: Any) -> bool:
    """Return whether ``left`` is no worse in the common geometry objectives."""
    left_metrics = _metrics(left)
    right_metrics = _metrics(right)
    names = _objective_names(left_metrics, right_metrics)
    if not names:
        return False
    values = [
        (
            float(left_metrics[name]),
            float(right_metrics[name]),
            OBJECTIVE_DIRECTIONS[name],
        )
        for name in names
    ]
    no_worse = all(
        left_value <= right_value
        if direction == "minimize"
        else left_value >= right_value
        for left_value, right_value, direction in values
    )
    strictly_better = any(
        left_value < right_value
        if direction == "minimize"
        else left_value > right_value
        for left_value, right_value, direction in values
    )
    return no_worse and strictly_better

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
    common_metrics = (
        {
            name
            for name in MIN_OBJECTIVES + RESOURCE_OBJECTIVES + PLACEMENT_OBJECTIVES
            if all(name in _metrics(candidate) for candidate in candidates)
        }
        if candidates
        else set()
    )
    objective_names = list(
        _objective_names(
            {name: 0.0 for name in common_metrics},
            {name: 0.0 for name in common_metrics},
        )
    )
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
        metrics = _metrics(candidate)
        rows.append(
            {
                "candidate_index": candidate_index,
                "input_position": position,
                "pareto_front": position in front,
                "dominated_by_positions": dominated_by,
                "objectives": {
                    name: float(metrics[name])
                    for name in objective_names
                    if name in metrics
                },
            }
        )
    rows.sort(
        key=lambda row: (
            not row["pareto_front"],
            len(row["dominated_by_positions"]),
            row["input_position"],
        )
    )
    return {
        "kind": "stdcell_geometry_pareto",
        "objective_direction": "mixed",
        "objective_directions": {
            name: OBJECTIVE_DIRECTIONS[name] for name in objective_names
        },
        "objectives": objective_names,
        "front_candidate_indices": [
            candidates[position].get("candidate_index", position)
            if isinstance(candidates[position], Mapping)
            else candidates[position].index
            for position in front
        ],
        "characterization_status": "not_run",
        "candidates": rows,
    }
