"""Pure routing-probe specifications and result classification."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from common.process_ir import ProcessIR
from common.routing_grammar import (
    EXPERIMENTAL,
    FORBIDDEN,
    SUPPORTED,
    UNKNOWN,
    Evidence,
    ConductorGrammar,
    RoutingGrammar,
)


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    kind: str
    conductor: str
    target: str | None = None
    cut: str | None = None
    region: str = "field"
    width_um: float = 1.5
    labels: tuple[str, ...] = ("A", "B")
    expected: str = "connected"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "conductor": self.conductor,
            "target": self.target,
            "cut": self.cut,
            "region": self.region,
            "width_um": self.width_um,
            "labels": list(self.labels),
            "expected": self.expected,
            "metadata": self.metadata,
        }


def _layer_gds(process: ProcessIR, name: str) -> tuple[int, int]:
    values = process.layers[name].get("gds") or ()
    if not values:
        raise ValueError(f"{process.profile}: layer {name!r} has no GDS mapping")
    return int(values[0]["layer"]), int(values[0]["datatype"])


def _cut_details(process: ProcessIR, source: str, target: str) -> tuple[str, float] | None:
    source_layer = process.layers[source]
    target_layer = process.layers[target]
    source_role = source_layer.get("role")
    target_role = target_layer.get("role")
    cuts = [
        name
        for name, layer in process.layers.items()
        if layer.get("available", False) and layer.get("role") == "cut"
    ]
    if not cuts:
        return None
    if {source_role, target_role} == {"gate", "metal"}:
        named = [
            name
            for name in cuts
            if name.lower() in {"cc", "contact", "contactpoly", "ct"}
            or any("CC" in str(cif).upper() for cif in process.layers[name].get("cif", ()))
        ]
        contact = sorted(named or cuts)[0]
        return contact, 2.0 * process.lambda_um
    if source_role == target_role == "metal":
        metal_layers = sorted(
            (_layer_gds(process, name)[0], name)
            for name, layer in process.layers.items()
            if layer.get("available", False) and layer.get("role") == "metal"
        )
        source_gds = _layer_gds(process, source)[0]
        target_gds = _layer_gds(process, target)[0]
        metal_positions = {name: index for index, (_, name) in enumerate(metal_layers)}
        if abs(metal_positions[source] - metal_positions[target]) != 1:
            return None
        lower, upper = sorted((source_gds, target_gds))
        between = [
            name
            for name in cuts
            if lower < _layer_gds(process, name)[0] < upper
        ]
        if between:
            return min(between, key=lambda name: abs(_layer_gds(process, name)[0] - upper)), 2.0 * process.lambda_um
    return None


def _cut_for_pair(process: ProcessIR, source: str, target: str) -> str | None:
    details = _cut_details(process, source, target)
    return details[0] if details else None


def default_probe_specs(
    process: ProcessIR,
    grammar: RoutingGrammar,
    *,
    include_crossings: bool = True,
) -> tuple[ProbeSpec, ...]:
    """Build a bounded, deterministic probe suite from PDK layer availability."""
    width = max(3.0 * process.lambda_um, float(process.meta.get("min_width_um", 0.0)))
    conductors = tuple(sorted(grammar.conductors))
    specs: list[ProbeSpec] = []
    for conductor in conductors:
        specs.append(
            ProbeSpec(
                name=f"wire_{conductor}",
                kind="wire",
                conductor=conductor,
                width_um=width,
                metadata={"positive": "lateral continuity"},
            )
        )
        specs.append(
            ProbeSpec(
                name=f"tee_{conductor}",
                kind="tee",
                conductor=conductor,
                width_um=width,
                labels=("A", "B", "C"),
                metadata={"positive": "same-layer T-junction"},
            )
        )
        if include_crossings:
            specs.append(
                ProbeSpec(
                    name=f"cross_same_{conductor}",
                    kind="same_layer_crossing",
                    conductor=conductor,
                    width_um=width,
                    labels=("A", "B", "C", "D"),
                    expected="short",
                )
            )
            if "active" in process.layers and process.layers["active"].get("available", False):
                for region, select in (("active_n", "nselect"), ("active_p", "pselect")):
                    if select not in process.layers or not process.layers[select].get("available", False):
                        continue
                    specs.append(
                        ProbeSpec(
                            name=f"over_{region}_{conductor}",
                            kind="active_crossing",
                            conductor=conductor,
                            region=region,
                            width_um=width,
                            expected="forms_device" if conductor == "poly" else "no_device",
                            metadata={"active_select": select},
                        )
                    )
    for source in conductors:
        for target in conductors:
            if source >= target:
                continue
            cut_details = _cut_details(process, source, target)
            if cut_details is not None:
                cut, cut_width = cut_details
                specs.append(
                    ProbeSpec(
                        name=f"transition_{source}_{target}_{cut}",
                        kind="transition",
                        conductor=source,
                        target=target,
                        cut=cut,
                        width_um=width,
                        metadata={
                            "positive": "explicit contact/via transition",
                            "cut_width_um": cut_width,
                        },
                    )
                )
            if include_crossings:
                specs.append(
                    ProbeSpec(
                        name=f"isolation_{source}_{target}",
                        kind="isolated_crossing",
                        conductor=source,
                        target=target,
                        width_um=width,
                        labels=("A", "B", "C", "D"),
                        expected="isolated",
                    )
                )
    return tuple(specs)
def local_rule_sweep_specs(
    process: ProcessIR,
    grammar: RoutingGrammar,
) -> tuple[ProbeSpec, ...]:
    """Return optional monotonic width, spacing, and enclosure probes."""
    base_width = max(3.0 * process.lambda_um, float(process.meta.get("min_width_um", 0.0)))
    widths = tuple(round(process.lambda_um * value, 6) for value in (1, 2, 3, 4, 5))
    spacings = tuple(round(process.lambda_um * value, 6) for value in (1, 2, 3, 4, 5))
    enclosures = tuple(round(process.lambda_um * value, 6) for value in (0, 0.5, 1, 2, 3))
    specs: list[ProbeSpec] = []
    for conductor in sorted(grammar.conductors):
        for index, width in enumerate(widths):
            specs.append(
                ProbeSpec(
                    name=f"sweep_width_{conductor}_{index}",
                    kind="wire",
                    conductor=conductor,
                    width_um=width,
                    metadata={"sweep": "width", "sweep_value_um": width},
                )
            )
        for index, spacing in enumerate(spacings):
            specs.append(
                ProbeSpec(
                    name=f"sweep_spacing_{conductor}_{index}",
                    kind="spacing",
                    conductor=conductor,
                    width_um=base_width,
                    labels=("A", "B", "C", "D"),
                    expected="isolated",
                    metadata={"sweep": "spacing", "sweep_value_um": spacing, "spacing_um": spacing},
                )
            )
    for source in sorted(grammar.conductors):
        for target in sorted(grammar.conductors):
            if source >= target:
                continue
            cut_details = _cut_details(process, source, target)
            if cut_details is None:
                continue
            cut, cut_width = cut_details
            for index, enclosure in enumerate(enclosures):
                specs.append(
                    ProbeSpec(
                        name=f"sweep_enclosure_{source}_{target}_{index}",
                        kind="enclosure",
                        conductor=source,
                        target=target,
                        cut=cut,
                        width_um=base_width,
                        metadata={
                            "sweep": "enclosure",
                            "sweep_value_um": enclosure,
                            "enclosure_um": enclosure,
                            "cut_width_um": cut_width,
                        },
                    )
                )
    return tuple(specs)
def native_feature_probe_specs(
    process: ProcessIR,
    grammar: RoutingGrammar,
) -> tuple[ProbeSpec, ...]:
    """Build process-specific probes only from explicit profile declarations."""
    configured = process.meta.get("native_probe_options") or ()
    if isinstance(configured, str):
        configured = (configured,)
    options = {str(value).lower() for value in configured}
    specs: list[ProbeSpec] = []

    if "butting_contact" in options:
        details = process.meta.get("butting_contact") or {}
        source = details.get("source")
        target = details.get("target")
        if source in grammar.conductors and target in grammar.conductors:
            specs.append(
                ProbeSpec(
                    name=f"butting_{source}_{target}",
                    kind="butting_contact",
                    conductor=source,
                    target=target,
                    width_um=max(
                        3.0 * process.lambda_um,
                        float(process.meta.get("min_width_um", 0.0)),
                    ),
                    metadata={"native_feature": "butting_contact"},
                )
            )

    if "alternate_contact_enclosure" in options:
        specs.extend(
            replace(
                spec,
                metadata={
                    **spec.metadata,
                    "native_feature": "alternate_contact_enclosure",
                },
            )
            for spec in local_rule_sweep_specs(process, grammar)
            if spec.kind == "enclosure"
        )

    if "local_interconnect_shortcut" in options:
        conductor = process.meta.get("local_interconnect_layer")
        if conductor in grammar.conductors:
            specs.append(
                ProbeSpec(
                    name=f"local_shortcut_{conductor}",
                    kind="wire",
                    conductor=conductor,
                    width_um=max(
                        3.0 * process.lambda_um,
                        float(process.meta.get("min_width_um", 0.0)),
                    ),
                    metadata={"native_feature": "local_interconnect_shortcut"},
                )
            )
    return tuple(specs)






def _probe_observation(
    status: str,
    probe: ProbeSpec,
    *,
    drc: str,
    lvs: str,
    devices: tuple[str, ...] = (),
    details: dict[str, Any] | None = None,
) -> Evidence:
    return Evidence(
        status=status,
        evidence=(f"active_probe:{probe.name}",),
        drc=drc,
        lvs=lvs,
        devices=devices,
        confidence=(
            "unknown"
            if status == UNKNOWN
            else "medium"
            if status == EXPERIMENTAL
            else "high"
        ),
        details=details or {},
    )


def classify_probe(
    probe: ProbeSpec,
    *,
    drc: str,
    lvs: str,
    devices: tuple[str, ...] = (),
    port_nets: dict[str, str] | None = None,
) -> Evidence:
    """Classify one probe without turning missing LVS semantics into FORBIDDEN."""
    port_nets = port_nets or {}
    values = [port_nets[label] for label in probe.labels if label in port_nets]
    all_connected = len(values) == len(probe.labels) and len(set(values)) == 1
    isolated_pairs = (
        len(values) == 4
        and values[0] == values[1]
        and values[2] == values[3]
        and values[0] != values[2]
    )
    all_isolated = isolated_pairs or (
        len(values) == len(probe.labels) and len(set(values)) == len(values)
    )
    lvs_known = len(values) == len(probe.labels)
    expected_ok = (
        (probe.expected == "connected" and all_connected)
        or (probe.expected == "short" and all_connected)
        or (probe.expected == "isolated" and all_isolated)
        or (probe.expected == "forms_device" and bool(devices))
        or (probe.expected == "no_device" and not devices)
    )
    if drc != "pass":
        drc_missing = str(drc).lower() in {"unknown", "not_run"}
        return _probe_observation(
            UNKNOWN if drc_missing else FORBIDDEN,
            probe,
            drc=drc,
            lvs=lvs,
            devices=devices,
            details={"reason": "native DRC result unavailable"} if drc_missing else None,
        )
    if lvs == "unknown" or (probe.expected in {"connected", "short", "isolated"} and not lvs_known):
        return _probe_observation(
            EXPERIMENTAL,
            probe,
            drc=drc,
            lvs=lvs,
            devices=devices,
            details={"reason": "probe result lacks complete LVS port equivalence"},
        )
    if expected_ok and drc == "pass" and lvs in {"pass", "connected", "isolated"}:
        return _probe_observation(SUPPORTED, probe, drc=drc, lvs=lvs, devices=devices)
    return _probe_observation(
        FORBIDDEN,
        probe,
        drc=drc,
        lvs=lvs,
        devices=devices,
        details={"expected": probe.expected, "port_nets": port_nets},
    )


def apply_probe_observation(
    grammar: RoutingGrammar,
    probe: ProbeSpec,
    observation: Evidence,
) -> RoutingGrammar:
    """Merge one observed result into an immutable grammar."""
    conductor = grammar.conductors.get(probe.conductor)
    if conductor is None:
        return grammar
    regions = dict(conductor.regions)
    connections = dict(conductor.connections)
    if probe.kind == "wire":
        continuity = observation
        regions["field"] = observation
    elif probe.kind == "active_crossing":
        regions[probe.region] = observation
        continuity = conductor.continuity
    elif probe.kind in {"transition", "butting_contact"} and probe.target:
        connections[probe.target] = observation
        continuity = conductor.continuity
    else:
        continuity = conductor.continuity
    updated = ConductorGrammar(
        name=conductor.name,
        continuity=continuity,
        regions=regions,
        connections=connections,
        electrical=conductor.electrical,
        cost=conductor.cost,
        max_useful_length_um=conductor.max_useful_length_um,
    )
    conductors = dict(grammar.conductors)
    conductors[probe.conductor] = updated
    if probe.kind in {"transition", "butting_contact"} and probe.target in conductors:
        target_conductor = conductors[probe.target]
        target_connections = dict(target_conductor.connections)
        target_connections[probe.conductor] = observation
        conductors[probe.target] = ConductorGrammar(
            name=target_conductor.name,
            continuity=target_conductor.continuity,
            regions=target_conductor.regions,
            connections=target_connections,
            electrical=target_conductor.electrical,
            cost=target_conductor.cost,
            max_useful_length_um=target_conductor.max_useful_length_um,
        )
    metadata = dict(grammar.metadata)
    metadata["active_probes"] = "complete"
    return RoutingGrammar(
        profile=grammar.profile,
        source_kind=grammar.source_kind,
        source_files=grammar.source_files,
        conductors=conductors,
        metadata=metadata,
    )
