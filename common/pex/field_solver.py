"""Public-stack field-solver reconstruction contract.

This module emits canonical sweep descriptions; it does not fabricate RC
coefficients and does not pretend to be a foundry QRC replacement.  An
external FastCap/FasterCap/Palace run consumes the emitted patterns and a
profile's parameterized BEOL fit, then a separate importer may write an
OpenRCX/custom research table.
"""

from __future__ import annotations

from typing import Any


class FieldSolverContractError(ValueError):
    """Raised when a field-solver reconstruction contract is incomplete."""


CANONICAL_PATTERNS = (
    "single_wire_over_plane",
    "parallel_wires",
    "adjacent_metal",
    "crossing_metal",
    "min_width_spacing",
    "scaled_width_spacing_2x",
    "scaled_width_spacing_4x",
)


def canonical_sweep_manifest(
    manifest: dict[str, Any],
    *,
    profile_name: str = "field_solver_estimated",
) -> dict[str, Any]:
    """Return an external-solver input contract without RC results."""

    profiles = manifest.get("profiles") or {}
    spec = profiles.get(profile_name)
    if not isinstance(spec, dict):
        raise FieldSolverContractError(f"unknown field-solver profile {profile_name!r}")
    if spec.get("extractor") != "field_solver_reconstruction":
        raise FieldSolverContractError(
            f"PEX profile {profile_name!r} is not a field-solver reconstruction profile"
        )
    if spec.get("maturity") != "field_solver_estimated":
        raise FieldSolverContractError(
            f"PEX profile {profile_name!r} is not field_solver_estimated"
        )
    flow = manifest.get("flow") or {}
    capacitance = flow.get("capacitance") or {}
    if capacitance.get("status") != "field_solver_estimated":
        raise FieldSolverContractError(
            "flow.capacitance must be field_solver_estimated"
        )
    if capacitance.get("calibrated") is not False:
        raise FieldSolverContractError(
            "field-solver capacitance must declare calibrated: false"
        )
    patterns = tuple(spec.get("canonical_patterns") or ())
    if patterns != CANONICAL_PATTERNS:
        raise FieldSolverContractError(
            "field-solver canonical_patterns must cover the required canonical sweep set"
        )
    fit = spec.get("beol_fit")
    if not isinstance(fit, str) or not fit:
        raise FieldSolverContractError("field-solver profile requires a BEOL fit path")
    return {
        "profile": manifest.get("profile"),
        "pex_profile": profile_name,
        "maturity": "field_solver_estimated",
        "calibrated": False,
        "solver_candidates": list(capacitance.get("solver_candidates") or ()),
        "beol_fit": fit,
        "patterns": list(patterns),
        "output": dict(spec.get("output") or {}),
        "signoff": False,
    }
