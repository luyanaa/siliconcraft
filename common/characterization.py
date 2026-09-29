"""Validation helpers for planned silicon characterization structures."""

from __future__ import annotations

from typing import Any


class CharacterizationContractError(ValueError):
    """Raised when a characterization plan cannot gate model maturity."""


REQUIRED_STRUCTURE_IDS = (
    "mos_wl_matrix",
    "kelvin_interconnects",
    "contact_via_chains",
    "capacitor_plates_comb",
    "inverter_fo4",
    "ring_oscillator",
)


def validate_characterization_manifest(
    document: dict[str, Any], profile: str
) -> dict[str, Any]:
    if document.get("schema_version") != 1:
        raise CharacterizationContractError("schema_version must be 1")
    if document.get("profile") != profile:
        raise CharacterizationContractError(
            f"profile {document.get('profile')!r} does not match {profile!r}"
        )
    if document.get("status") != "planning_only":
        raise CharacterizationContractError(
            "public characterization manifest must remain planning_only until data is loaded"
        )
    structures = document.get("structures") or []
    if not isinstance(structures, list):
        raise CharacterizationContractError("structures must be a sequence")
    by_id: dict[str, dict[str, Any]] = {}
    for item in structures:
        if not isinstance(item, dict) or not item.get("id"):
            raise CharacterizationContractError("each structure needs an id")
        identifier = str(item["id"])
        if identifier in by_id:
            raise CharacterizationContractError(f"duplicate structure {identifier!r}")
        by_id[identifier] = item
        if not item.get("measurements"):
            raise CharacterizationContractError(
                f"structure {identifier!r} must declare measurements"
            )
    missing = [identifier for identifier in REQUIRED_STRUCTURE_IDS if identifier not in by_id]
    if missing:
        raise CharacterizationContractError(
            "missing required characterization structures: " + ", ".join(missing)
        )
    temperatures = (document.get("conditions") or {}).get("temperatures_c")
    if not isinstance(temperatures, list) or len(temperatures) < 2:
        raise CharacterizationContractError(
            "conditions.temperatures_c must contain at least two points"
        )
    gates = document.get("activation_gates") or {}
    for level in ("L1_public_surrogate", "L2_silicon_calibrated", "L3_foundry_private"):
        if not isinstance(gates.get(level), dict):
            raise CharacterizationContractError(f"missing activation gate {level!r}")
    return document
