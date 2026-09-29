"""Small topology search primitives used by the first stdcell planner."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from common.stdcell.netlist import CellCircuit, MosInstance


@dataclass(frozen=True)
class NetworkOrdering:
    polarity: str
    devices: tuple[str, ...]
    shared_diffusion_edges: int
    diffusion_breaks: int

    @property
    def score(self) -> tuple[int, int, tuple[str, ...]]:
        return self.shared_diffusion_edges, -self.diffusion_breaks, self.devices

@dataclass(frozen=True)
class TopologyOption:
    kind: str
    priority: int
    requires_characterization: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "priority": self.priority,
            "requires_characterization": self.requires_characterization,
            "reason": self.reason,
        }


def symmetric_input_groups(circuit: CellCircuit) -> tuple[tuple[str, ...], ...]:
    """Find input permutations with identical transistor signatures."""
    signatures: dict[tuple[tuple[str, tuple[str, ...], str], ...], list[str]] = {}
    for input_name in circuit.inputs:
        signature = tuple(
            sorted(
                (
                    device.model,
                    tuple(sorted(device.diffusion_nets)),
                    device.bulk,
                )
                for device in circuit.devices
                if device.gate == input_name
            )
        )
        signatures.setdefault(signature, []).append(input_name)
    return tuple(
        tuple(sorted(group))
        for group in signatures.values()
        if len(group) > 1 and group[0]
    )


def pin_permutations(circuit: CellCircuit) -> tuple[tuple[str, ...], ...]:
    """Return deterministic equivalent-input orders for candidate generation."""
    raw = circuit.metadata.get("symmetric_inputs")
    groups = (tuple(raw),) if raw else symmetric_input_groups(circuit)
    orders: set[tuple[str, ...]] = {tuple(circuit.inputs)}
    for raw_group in groups:
        group = tuple(raw_group)
        if len(group) <= 1:
            continue
        group_orders = tuple(permutations(group))
        expanded: set[tuple[str, ...]] = set()
        for permutation in group_orders:
            replacement = dict(zip(group, permutation))
            expanded.update(
                tuple(replacement.get(name, name) for name in order)
                for order in orders
            )
        orders = expanded
    return tuple(sorted(orders))


def weak_device_names(circuit: CellCircuit) -> tuple[str, ...]:
    values = circuit.metadata.get("weak_devices", ())
    return tuple(name for name in values if name in {device.name for device in circuit.devices})


def weak_length_scales(circuit: CellCircuit) -> tuple[float, ...]:
    if not weak_device_names(circuit):
        return (1.0,)
    raw = circuit.metadata.get("weak_length_scales", ("1", "2"))
    values = sorted({max(1.0, float(value)) for value in raw})
    return tuple(values)


def topology_options(circuit: CellCircuit) -> tuple[TopologyOption, ...]:
    hints = {value.lower() for value in circuit.metadata.get("topology", ())}
    name = circuit.name.lower()
    options = [
        TopologyOption(
            "static_cmos",
            0,
            True,
            "baseline complementary static CMOS topology",
        )
    ]
    compound_hint = any(
        value in {"aoi", "oai", "aoi_oai"}
        or value.startswith(("aoi", "oai"))
        for value in hints
    )
    if compound_hint or name.startswith(("aoi", "oai")):
        options.insert(
            0,
            TopologyOption(
                "aoi_oai",
                -1,
                True,
                "prefer compound PUN/PDN over decomposed gates when the input circuit supplies it",
            ),
        )
    if hints & {"transmission_gate", "tg", "pass_transistor", "ptl"}:
        options.append(
            TopologyOption(
                "transmission_gate" if "transmission_gate" in hints or "tg" in hints else "pass_transistor",
                1,
                True,
                "opt-in topology; noise margin, control routing, and PEX remain required",
            )
        )
    return tuple(options)


def _shared_diffusion(left: MosInstance, right: MosInstance) -> bool:
    return bool(set(left.diffusion_nets) & set(right.diffusion_nets))


def enumerate_orderings(
    circuit: CellCircuit,
    polarity: str,
    limit: int | None = 8,
    model_names: dict[str, str] | None = None,
) -> tuple[NetworkOrdering, ...]:
    """Return deterministic high-scoring generalized Euler orderings.

    This version searches permutations for the small first cell family.  It
    records where diffusion sharing is possible; physical shared-active
    construction remains a separate layout operation rather than being
    silently inferred from a graph path.
    """

    if model_names is None:
        devices = tuple(
            device for device in circuit.devices if device.model.lower().endswith(polarity)
        )
    else:
        devices = tuple(
            device
            for device in circuit.devices
            if device.model == model_names.get(polarity)
        )
    if not devices:
        return ()
    candidates: list[NetworkOrdering] = []
    for ordered in permutations(devices):
        shared = sum(_shared_diffusion(a, b) for a, b in zip(ordered, ordered[1:]))
        breaks = max(0, len(ordered) - 1 - shared)
        candidates.append(NetworkOrdering(polarity, tuple(device.name for device in ordered), shared, breaks))
    candidates.sort(key=lambda item: item.score, reverse=True)
    if limit is not None and limit < 1:
        raise ValueError("ordering limit must be positive or None")
    unique: list[NetworkOrdering] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        if candidate.devices in seen:
            continue
        seen.add(candidate.devices)
        unique.append(candidate)
        if limit is not None and len(unique) >= limit:
            break
    return tuple(unique)


def best_ordering(
    circuit: CellCircuit,
    polarity: str,
    model_names: dict[str, str] | None = None,
) -> NetworkOrdering:
    orderings = enumerate_orderings(circuit, polarity, limit=1, model_names=model_names)
    if not orderings:
        raise ValueError(f"{circuit.name}: no {polarity} devices")
    return orderings[0]
