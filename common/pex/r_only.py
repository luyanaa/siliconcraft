"""Deterministic wire-only resistance extraction from public sheet data.

This backend is deliberately narrower than a foundry PEX engine.  It accepts
canonical wire segments, applies ``R = R_sheet * L / W``, and reports only
wire resistance.  Contact, via, junction, and substrate terms remain
explicitly unknown and are never folded into the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class ROnlyError(ValueError):
    """Raised when a wire-only resistance contract cannot be evaluated."""


@dataclass(frozen=True)
class WireSegment:
    """One rectangular, constant-width wire segment in micrometres."""

    layer: str
    length_um: float
    width_um: float


@dataclass(frozen=True)
class WireResistance:
    """Evaluated wire resistance with its source maturity preserved."""

    layer: str
    length_um: float
    width_um: float
    sheet_resistance_ohm_per_square: float
    resistance_ohm: float
    source_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "length_um": self.length_um,
            "width_um": self.width_um,
            "sheet_resistance_ohm_per_square": self.sheet_resistance_ohm_per_square,
            "resistance_ohm": self.resistance_ohm,
            "source_status": self.source_status,
        }


def _profile_spec(manifest: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profiles = manifest.get("profiles") or {}
    spec = profiles.get(profile_name)
    if not isinstance(spec, dict):
        raise ROnlyError(f"unknown R-only PEX profile {profile_name!r}")
    if spec.get("extractor") != "r_only_python":
        raise ROnlyError(
            f"PEX profile {profile_name!r} is not an r_only_python profile"
        )
    if spec.get("status") != "public_typical":
        raise ROnlyError(
            f"PEX profile {profile_name!r} is not public_typical; refusing R-only output"
        )
    return spec


def _sheet_record(spec: dict[str, Any], layer: str) -> tuple[float, str]:
    table = spec.get("sheet_resistance_ohm_sq") or {}
    raw = table.get(layer)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw), "public_typical"
    if not isinstance(raw, dict):
        raise ROnlyError(
            f"layer {layer!r} has no public sheet-resistance value in the R-only profile"
        )
    value = raw.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ROnlyError(
            f"layer {layer!r} has no numeric public sheet-resistance value"
        )
    status = str(raw.get("status") or "public_typical")
    if status != "public_typical":
        raise ROnlyError(
            f"layer {layer!r} sheet resistance status is {status!r}, not public_typical"
        )
    return float(value), status


def evaluate_segment(spec: dict[str, Any], segment: WireSegment) -> WireResistance:
    if not segment.layer:
        raise ROnlyError("wire segment layer is required")
    if segment.length_um <= 0 or segment.width_um <= 0:
        raise ROnlyError("wire segment length_um and width_um must be positive")
    sheet, status = _sheet_record(spec, segment.layer)
    resistance = sheet * segment.length_um / segment.width_um
    return WireResistance(
        layer=segment.layer,
        length_um=float(segment.length_um),
        width_um=float(segment.width_um),
        sheet_resistance_ohm_per_square=sheet,
        resistance_ohm=resistance,
        source_status=status,
    )


def build_r_wire_only_report(
    manifest: dict[str, Any],
    segments: Iterable[WireSegment],
    *,
    profile_name: str = "public_r_only",
) -> dict[str, Any]:
    """Return a JSON-serializable R_wire_only report.

    The report intentionally has no contact/via contribution.  Consumers must
    inspect the explicit ``excluded_terms`` block before using the result for
    rough relative timing or routing cost.
    """

    spec = _profile_spec(manifest, profile_name)
    evaluated = [evaluate_segment(spec, segment) for segment in segments]
    return {
        "profile": manifest.get("profile"),
        "pex_profile": profile_name,
        "mode": "R_wire_only",
        "maturity": "public_typical",
        "formula": "R_ohm = R_sheet_ohm_per_square * length_um / width_um",
        "segments": [item.as_dict() for item in evaluated],
        "wire_resistance_ohm": sum(item.resistance_ohm for item in evaluated),
        "excluded_terms": {
            "contact_resistance": "unknown",
            "via_resistance": "unknown",
            "junction_resistance": "not_applicable_to_wire_only",
            "substrate_network": "excluded_and_unavailable",
        },
        "use": "rough_relative_timing_or_routing_cost_only",
        "signoff": False,
    }


def segment_from_mapping(raw: dict[str, Any]) -> WireSegment:
    """Parse one canonical segment mapping used by scripts and tests."""

    if not isinstance(raw, dict):
        raise ROnlyError("wire segment must be a mapping")
    try:
        return WireSegment(
            layer=str(raw["layer"]),
            length_um=float(raw["length_um"]),
            width_um=float(raw["width_um"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ROnlyError(
            "wire segment requires layer, numeric length_um, and numeric width_um"
        ) from exc
