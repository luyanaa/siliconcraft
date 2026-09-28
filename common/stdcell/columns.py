"""Placement-independent transistor column IR and compatibility search."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

from common.stdcell.netlist import CellCircuit
from common.stdcell.process import StdcellProcess
from common.stdcell.topology import NetworkOrdering, enumerate_orderings


@dataclass(frozen=True)
class Column:
    kind: str
    gate_net: str | None = None
    p_gate_net: str | None = None
    n_gate_net: str | None = None
    p_device: str | None = None
    n_device: str | None = None
    p_net: str | None = None
    n_net: str | None = None
    diffusion_shared: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "gate_net": self.gate_net,
            "p_gate_net": self.p_gate_net,
            "n_gate_net": self.n_gate_net,
            "p_device": self.p_device,
            "n_device": self.n_device,
            "p_net": self.p_net,
            "n_net": self.n_net,
            "diffusion_shared": self.diffusion_shared,
        }


@dataclass(frozen=True)
class ColumnIR:
    p_order: NetworkOrdering
    n_order: NetworkOrdering
    columns: tuple[Column, ...]
    diffusion_breaks: int
    gate_mismatches: int
    shared_diffusion_edges: int
    routing_estimate: float

    @property
    def aligned_gate_columns(self) -> int:
        return sum(
            1
            for column in self.columns
            if column.kind == "gate" and column.gate_net is not None
        )

    @property
    def score(self) -> tuple[int, int, float, tuple[str, ...], tuple[str, ...]]:
        return (
            self.diffusion_breaks,
            self.gate_mismatches,
            self.routing_estimate,
            self.p_order.devices,
            self.n_order.devices,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "p_order": list(self.p_order.devices),
            "n_order": list(self.n_order.devices),
            "columns": [column.as_dict() for column in self.columns],
            "diffusion_breaks": self.diffusion_breaks,
            "gate_mismatches": self.gate_mismatches,
            "aligned_gate_columns": self.aligned_gate_columns,
            "shared_diffusion_edges": self.shared_diffusion_edges,
            "routing_estimate": self.routing_estimate,
        }


def _device_map(circuit: CellCircuit) -> dict[str, Any]:
    return {device.name: device for device in circuit.devices}


def _gates(circuit: CellCircuit, ordering: NetworkOrdering) -> tuple[str, ...]:
    devices = _device_map(circuit)
    return tuple(devices[name].gate for name in ordering.devices)


def _diffusion_net(circuit: CellCircuit, ordering: NetworkOrdering, index: int) -> str | None:
    devices = _device_map(circuit)
    left = devices[ordering.devices[index]]
    right = devices[ordering.devices[index + 1]]
    shared = sorted(set(left.diffusion_nets) & set(right.diffusion_nets))
    return shared[0] if shared else None


def build_column_ir(circuit: CellCircuit, p_order: NetworkOrdering, n_order: NetworkOrdering) -> ColumnIR:
    devices = _device_map(circuit)
    p_gates = _gates(circuit, p_order)
    n_gates = _gates(circuit, n_order)
    count = max(len(p_gates), len(n_gates))
    columns: list[Column] = []
    mismatches = 0
    breaks = p_order.diffusion_breaks + n_order.diffusion_breaks
    shared_edges = 0
    for index in range(count):
        p_device = devices[p_order.devices[index]] if index < len(p_order.devices) else None
        n_device = devices[n_order.devices[index]] if index < len(n_order.devices) else None
        p_gate = p_device.gate if p_device else None
        n_gate = n_device.gate if n_device else None
        if p_gate != n_gate:
            mismatches += 1
        columns.append(
            Column(
                kind="gate",
                gate_net=p_gate if p_gate == n_gate else None,
                p_gate_net=p_gate,
                n_gate_net=n_gate,
                p_device=p_device.name if p_device else None,
                n_device=n_device.name if n_device else None,
            )
        )
        if index + 1 < count:
            p_net = _diffusion_net(circuit, p_order, index) if index + 1 < len(p_order.devices) else None
            n_net = _diffusion_net(circuit, n_order, index) if index + 1 < len(n_order.devices) else None
            shared = p_net is not None and n_net is not None
            columns.append(
                Column(
                    kind="diffusion",
                    p_net=p_net,
                    n_net=n_net,
                    diffusion_shared=shared,
                )
            )
            if shared:
                shared_edges += 1
            else:
                breaks += 1
    routing_estimate = float(mismatches * 4 + breaks)
    return ColumnIR(
        p_order,
        n_order,
        tuple(columns),
        breaks,
        mismatches,
        shared_edges,
        routing_estimate,
    )


def enumerate_column_ir(circuit: CellCircuit, process: StdcellProcess, limit: int = 32) -> tuple[ColumnIR, ...]:
    model_names = process.model_names
    p_orders = enumerate_orderings(circuit, "p", limit=limit, model_names=model_names)
    n_orders = enumerate_orderings(circuit, "n", limit=limit, model_names=model_names)
    if not p_orders or not n_orders:
        raise ValueError(f"{circuit.name}: both PUN and PDN are required")
    candidates = [build_column_ir(circuit, p_order, n_order) for p_order, n_order in product(p_orders, n_orders)]
    candidates.sort(key=lambda candidate: candidate.score)
    unique: list[ColumnIR] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        signature = tuple(
            f"{column.kind}:{column.p_device}:{column.n_device}:{column.p_net}:{column.n_net}"
            for column in candidate.columns
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return tuple(unique)
