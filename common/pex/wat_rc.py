"""MOSIS WAT analytical RC extraction (PEX v0).

This backend turns *measured* MOSIS wafer-acceptance-test (WAT) coefficients
into a deterministic research RC report:

    R_ohm = R_sheet * length_um / width_um
          + n_contact * R_contact
          + n_via * R_via

    C_aF  = C_area * overlap_area_um2
          + C_fringe * edge_length_um

It is deliberately narrower than a foundry PEX engine and deliberately wider
than the wire-only backend in :mod:`common.pex.r_only`:

* unlike ``r_only`` it *does* include per-cut contact and via resistance, but
  only from a coefficient set that carries explicit provenance;
* it never guesses a missing coefficient and never blends two process options;
* every report carries the coefficient set's provenance and an explicit
  ``calibrated_to_current_d35``/``signoff`` false flag.

A coefficient set whose ``provenance.verification_status`` is not
``verified_local_report`` is still usable, but the report flags it as
``external_unverified`` so no consumer can mistake it for signoff data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

VERIFIED_STATUS = "verified_local_report"


class WatRcError(ValueError):
    """Raised when a WAT analytical RC contract cannot be evaluated."""


@dataclass(frozen=True)
class WireSegment:
    """One rectangular wire segment in micrometres, with optional cuts."""

    layer: str
    length_um: float
    width_um: float
    contacts: int = 0
    contact_target: str | None = None
    vias: int = 0
    via_target: str | None = None


@dataclass(frozen=True)
class CouplingPair:
    """One overlapping conductor pair for area/fringe capacitance."""

    lower: str
    upper: str
    overlap_area_um2: float = 0.0
    edge_length_um: float = 0.0


@dataclass(frozen=True)
class SegmentResult:
    layer: str
    length_um: float
    width_um: float
    sheet_resistance_ohm_per_square: float
    wire_resistance_ohm: float
    contacts: int
    contact_target: str | None
    contact_resistance_each_ohm: float
    contact_resistance_ohm: float
    vias: int
    via_target: str | None
    via_resistance_each_ohm: float
    via_resistance_ohm: float
    resistance_ohm: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "length_um": self.length_um,
            "width_um": self.width_um,
            "sheet_resistance_ohm_per_square": self.sheet_resistance_ohm_per_square,
            "wire_resistance_ohm": self.wire_resistance_ohm,
            "contacts": self.contacts,
            "contact_target": self.contact_target,
            "contact_resistance_each_ohm": self.contact_resistance_each_ohm,
            "contact_resistance_ohm": self.contact_resistance_ohm,
            "vias": self.vias,
            "via_target": self.via_target,
            "via_resistance_each_ohm": self.via_resistance_each_ohm,
            "via_resistance_ohm": self.via_resistance_ohm,
            "resistance_ohm": self.resistance_ohm,
        }


@dataclass(frozen=True)
class CouplingResult:
    pair: str
    overlap_area_um2: float
    edge_length_um: float
    area_coefficient_aF_per_um2: float
    fringe_coefficient_aF_per_um: float
    area_capacitance_aF: float
    fringe_capacitance_aF: float
    capacitance_aF: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "overlap_area_um2": self.overlap_area_um2,
            "edge_length_um": self.edge_length_um,
            "area_coefficient_aF_per_um2": self.area_coefficient_aF_per_um2,
            "fringe_coefficient_aF_per_um": self.fringe_coefficient_aF_per_um,
            "area_capacitance_aF": self.area_capacitance_aF,
            "fringe_capacitance_aF": self.fringe_capacitance_aF,
            "capacitance_aF": self.capacitance_aF,
        }


# --------------------------------------------------------------------- lookup


def profile_spec(manifest: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Return the validated ``wat_analytical_rc`` profile spec."""

    profiles = manifest.get("profiles") or {}
    spec = profiles.get(profile_name)
    if not isinstance(spec, dict):
        raise WatRcError(f"unknown WAT analytical PEX profile {profile_name!r}")
    if spec.get("extractor") != "wat_analytical_rc":
        raise WatRcError(
            f"PEX profile {profile_name!r} is not a wat_analytical_rc profile"
        )
    if not spec.get("reference_data"):
        raise WatRcError(
            f"PEX profile {profile_name!r} requires a reference_data file"
        )
    return spec


def coefficient_sets(reference_doc: dict[str, Any]) -> dict[str, Any]:
    sets = reference_doc.get("coefficient_sets") or {}
    if not isinstance(sets, dict) or not sets:
        raise WatRcError("reference data has no coefficient_sets")
    return sets


def select_set(
    reference_doc: dict[str, Any], name: str
) -> dict[str, Any]:
    """Return one coefficient set, validating that it carries provenance."""

    sets = coefficient_sets(reference_doc)
    dataset = sets.get(name)
    if not isinstance(dataset, dict):
        known = ", ".join(sorted(sets))
        raise WatRcError(f"unknown coefficient set {name!r}; known: {known}")
    provenance = dataset.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("authority"):
        raise WatRcError(
            f"coefficient set {name!r} has no provenance authority; refusing to use it"
        )
    return dataset


def _numeric(dataset: dict[str, Any], table: str, key: str, *, context: str) -> float:
    values = dataset.get(table) or {}
    raw = values.get(key)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    raise WatRcError(
        f"{context}: coefficient {table}.{key} is not available in this set; "
        "a missing coefficient is never guessed"
    )


def _resistance_layers(spec: dict[str, Any]) -> tuple[str, ...]:
    layers = spec.get("resistance_layers")
    if not isinstance(layers, list) or not layers:
        raise WatRcError("wat_analytical_rc profile requires resistance_layers")
    return tuple(str(layer) for layer in layers)


def _pair_key(lower: str, upper: str) -> str:
    return f"{lower}-{upper}"


def _coupling_entry(dataset: dict[str, Any], pair: str) -> dict[str, Any]:
    coupling = ((dataset.get("capacitance_aF") or {}).get("coupling")) or {}
    entry = coupling.get(pair)
    if entry is None:
        first, _, second = pair.partition("-")
        entry = coupling.get(_pair_key(second, first))
    if not isinstance(entry, dict):
        raise WatRcError(
            f"coefficient set has no coupling data for pair {pair!r}; "
            "a missing coefficient is never guessed"
        )
    return entry


# ---------------------------------------------------------------- evaluation


def evaluate_segment(
    spec: dict[str, Any], dataset: dict[str, Any], segment: WireSegment
) -> SegmentResult:
    if not segment.layer:
        raise WatRcError("wire segment layer is required")
    if segment.length_um <= 0 or segment.width_um <= 0:
        raise WatRcError("wire segment length_um and width_um must be positive")
    if segment.layer not in _resistance_layers(spec):
        raise WatRcError(
            f"layer {segment.layer!r} is not a resistance layer of this PEX profile"
        )
    sheet = _numeric(
        dataset, "sheet_resistance_ohm_sq", segment.layer,
        context=f"segment on {segment.layer}",
    )
    wire = sheet * segment.length_um / segment.width_um

    contact_each = 0.0
    if segment.contacts:
        target = segment.contact_target or segment.layer
        contact_each = _numeric(
            dataset, "contact_resistance_ohm", target,
            context=f"{segment.contacts} contact(s) on {target}",
        )
    contact_total = contact_each * int(segment.contacts)

    via_each = 0.0
    if segment.vias:
        target = segment.via_target
        if not target:
            raise WatRcError("a via count requires an explicit via_target")
        via_each = _numeric(
            dataset, "via_resistance_ohm", target,
            context=f"{segment.vias} via(s) on {target}",
        )
    via_total = via_each * int(segment.vias)

    return SegmentResult(
        layer=segment.layer,
        length_um=float(segment.length_um),
        width_um=float(segment.width_um),
        sheet_resistance_ohm_per_square=sheet,
        wire_resistance_ohm=wire,
        contacts=int(segment.contacts),
        contact_target=segment.contact_target if segment.contacts else None,
        contact_resistance_each_ohm=contact_each,
        contact_resistance_ohm=contact_total,
        vias=int(segment.vias),
        via_target=segment.via_target if segment.vias else None,
        via_resistance_each_ohm=via_each,
        via_resistance_ohm=via_total,
        resistance_ohm=wire + contact_total + via_total,
    )


def evaluate_coupling(
    dataset: dict[str, Any], pair: CouplingPair
) -> CouplingResult:
    key = _pair_key(pair.lower, pair.upper)
    entry = _coupling_entry(dataset, key)
    area = entry.get("area")
    fringe = entry.get("fringe")
    if not isinstance(area, (int, float)) or isinstance(area, bool):
        raise WatRcError(f"coupling pair {key!r} has no numeric area coefficient")
    if not isinstance(fringe, (int, float)) or isinstance(fringe, bool):
        raise WatRcError(
            f"coupling pair {key!r} has no numeric fringe coefficient"
        )
    area_cap = float(area) * pair.overlap_area_um2
    fringe_cap = float(fringe) * pair.edge_length_um
    return CouplingResult(
        pair=key,
        overlap_area_um2=float(pair.overlap_area_um2),
        edge_length_um=float(pair.edge_length_um),
        area_coefficient_aF_per_um2=float(area),
        fringe_coefficient_aF_per_um=fringe,
        area_capacitance_aF=area_cap,
        fringe_capacitance_aF=fringe_cap,
        capacitance_aF=area_cap + fringe_cap,
    )


def build_wat_rc_report(
    manifest: dict[str, Any],
    reference_doc: dict[str, Any],
    segments: Iterable[WireSegment] = (),
    pairs: Iterable[CouplingPair] = (),
    *,
    profile_name: str = "mosis_wat_rc",
    coefficient_set: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable analytical RC report with provenance."""

    spec = profile_spec(manifest, profile_name)
    selected = coefficient_set or str(spec.get("coefficient_set") or "")
    if not selected:
        raise WatRcError("no coefficient set selected")
    dataset = select_set(reference_doc, selected)
    provenance = dict(dataset.get("provenance") or {})
    verified = provenance.get("verification_status") == VERIFIED_STATUS

    segment_results = [evaluate_segment(spec, dataset, item) for item in segments]
    coupling_results = [evaluate_coupling(dataset, item) for item in pairs]

    return {
        "profile": manifest.get("profile"),
        "pex_profile": profile_name,
        "mode": "wat_analytical_rc",
        "maturity": "historical_measured",
        "coefficient_set": selected,
        "coefficient_set_provenance": provenance,
        "coefficient_set_verification": (
            "verified_local_report" if verified else "external_unverified"
        ),
        "calibrated_to_current_d35": bool(
            spec.get("calibrated_to_current_d35", False)
        ),
        "formulas": dict(spec.get("formulas") or {}),
        "segments": [item.as_dict() for item in segment_results],
        "coupling": [item.as_dict() for item in coupling_results],
        "resistance_ohm": sum(item.resistance_ohm for item in segment_results),
        "wire_resistance_ohm": sum(
            item.wire_resistance_ohm for item in segment_results
        ),
        "contact_resistance_ohm": sum(
            item.contact_resistance_ohm for item in segment_results
        ),
        "via_resistance_ohm": sum(
            item.via_resistance_ohm for item in segment_results
        ),
        "capacitance_aF": sum(item.capacitance_aF for item in coupling_results),
        "excluded_terms": {
            "junction_capacitance": "owned_by_compact_model",
            "substrate_network": "excluded_and_unavailable",
            "lateral_sidewall_coupling": "not_in_overlap_edge_model",
            "temperature_correction": "no_coefficients_materialized",
        },
        "use": "research_rc_estimate_only",
        "signoff": False,
    }


def compare_sets(
    reference_doc: dict[str, Any],
    basis: str,
    other: str,
    quantities: Iterable[tuple[str, str, str]],
) -> dict[str, Any]:
    """Recompute recorded cross-check deltas between two coefficient sets.

    ``quantities`` is an iterable of ``(table, key, label)`` triples.  The
    returned mapping is ``{label: percent_delta}`` where the delta is relative
    to ``basis``.
    """

    base = select_set(reference_doc, basis)
    alt = select_set(reference_doc, other)
    out: dict[str, Any] = {"basis": basis, "other": other, "deltas_percent": {}}
    for table, key, label in quantities:
        base_value = _numeric(base, table, key, context=f"cross-check {label}")
        alt_value = _numeric(alt, table, key, context=f"cross-check {label}")
        if base_value == 0:
            raise WatRcError(f"cross-check {label}: basis value is zero")
        out["deltas_percent"][label] = round(
            (alt_value - base_value) / base_value * 100.0, 1
        )
    return out


def compare_coupling(
    reference_doc: dict[str, Any],
    basis: str,
    other: str,
    pairs: Iterable[str],
) -> dict[str, Any]:
    """Recompute recorded coupling-capacitance deltas between two sets."""

    base = select_set(reference_doc, basis)
    alt = select_set(reference_doc, other)
    out: dict[str, Any] = {"basis": basis, "other": other, "deltas_percent": {}}
    for pair in pairs:
        base_entry = _coupling_entry(base, pair)
        alt_entry = _coupling_entry(alt, pair)
        for field_name in ("area", "fringe"):
            base_value = base_entry.get(field_name)
            alt_value = alt_entry.get(field_name)
            if not isinstance(base_value, (int, float)) or isinstance(
                base_value, bool
            ):
                raise WatRcError(
                    f"cross-check {pair}.{field_name}: basis value unavailable"
                )
            if not isinstance(alt_value, (int, float)) or isinstance(
                alt_value, bool
            ):
                raise WatRcError(
                    f"cross-check {pair}.{field_name}: comparison value unavailable"
                )
            if base_value == 0:
                raise WatRcError(
                    f"cross-check {pair}.{field_name}: basis value is zero"
                )
            out["deltas_percent"][f"{pair}.{field_name}"] = round(
                (float(alt_value) - float(base_value)) / float(base_value) * 100.0,
                1,
            )
    return out


def segment_from_mapping(raw: dict[str, Any]) -> WireSegment:
    if not isinstance(raw, dict):
        raise WatRcError("wire segment must be a mapping")
    try:
        return WireSegment(
            layer=str(raw["layer"]),
            length_um=float(raw["length_um"]),
            width_um=float(raw["width_um"]),
            contacts=int(raw.get("contacts") or 0),
            contact_target=(
                str(raw["contact_target"]) if raw.get("contact_target") else None
            ),
            vias=int(raw.get("vias") or 0),
            via_target=str(raw["via_target"]) if raw.get("via_target") else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WatRcError(
            "wire segment requires layer, numeric length_um and width_um, and "
            "optional integer contacts/vias"
        ) from exc


def pair_from_mapping(raw: dict[str, Any]) -> CouplingPair:
    if not isinstance(raw, dict):
        raise WatRcError("coupling pair must be a mapping")
    try:
        return CouplingPair(
            lower=str(raw["lower"]),
            upper=str(raw["upper"]),
            overlap_area_um2=float(raw.get("overlap_area_um2") or 0.0),
            edge_length_um=float(raw.get("edge_length_um") or 0.0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WatRcError(
            "coupling pair requires lower and upper layer names and numeric "
            "overlap_area_um2 / edge_length_um"
        ) from exc
