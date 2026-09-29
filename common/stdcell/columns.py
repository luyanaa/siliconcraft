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
    gap_columns: int
    shared_diffusion_edges: int
    routing_estimate: float

    @property
    def aligned_gate_columns(self) -> int:
        return sum(
            1
            for column in self.columns
            if column.kind == "gate"
            and column.p_gate_net is not None
            and column.p_gate_net == column.n_gate_net
        )

    @property
    def physical_gate_slots(self) -> tuple[Column, ...]:
        return tuple(column for column in self.columns if column.kind == "gate")

    @property
    def score(self) -> tuple[int, int, int, float, tuple[str, ...], tuple[str, ...]]:
        return (
            self.diffusion_breaks,
            self.gate_mismatches,
            self.gap_columns,
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
            "gap_columns": self.gap_columns,
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


def _align_gate_orders(
    p_devices: tuple[Any, ...],
    n_devices: tuple[Any, ...],
) -> tuple[tuple[Any | None, Any | None], ...]:
    """Align rows by a deterministic LCS, retaining explicit row gaps."""
    p_gates = tuple(device.gate for device in p_devices)
    n_gates = tuple(device.gate for device in n_devices)
    lcs = [[0] * (len(n_gates) + 1) for _ in range(len(p_gates) + 1)]
    for p_index in range(len(p_gates) - 1, -1, -1):
        for n_index in range(len(n_gates) - 1, -1, -1):
            lcs[p_index][n_index] = (
                1 + lcs[p_index + 1][n_index + 1]
                if p_gates[p_index] == n_gates[n_index]
                else max(lcs[p_index + 1][n_index], lcs[p_index][n_index + 1])
            )
    aligned: list[tuple[Any | None, Any | None]] = []
    p_index = n_index = 0
    while p_index < len(p_devices) or n_index < len(n_devices):
        if (
            p_index < len(p_devices)
            and n_index < len(n_devices)
            and p_gates[p_index] == n_gates[n_index]
        ):
            aligned.append((p_devices[p_index], n_devices[n_index]))
            p_index += 1
            n_index += 1
        elif n_index >= len(n_devices) or (
            p_index < len(p_devices)
            and lcs[p_index + 1][n_index] >= lcs[p_index][n_index + 1]
        ):
            aligned.append((p_devices[p_index], None))
            p_index += 1
        else:
            aligned.append((None, n_devices[n_index]))
            n_index += 1
    return tuple(aligned)


def _diffusion_net_between(
    circuit: CellCircuit,
    devices: tuple[Any, ...],
    left_index: int,
    right_index: int,
) -> str | None:
    left = devices[left_index]
    right = devices[right_index]
    shared = sorted(set(left.diffusion_nets) & set(right.diffusion_nets))
    return shared[0] if shared else None


def build_column_ir(circuit: CellCircuit, p_order: NetworkOrdering, n_order: NetworkOrdering) -> ColumnIR:
    devices = _device_map(circuit)
    p_devices = tuple(devices[name] for name in p_order.devices)
    n_devices = tuple(devices[name] for name in n_order.devices)
    aligned = _align_gate_orders(p_devices, n_devices)
    p_indices = {device.name: index for index, device in enumerate(p_devices)}
    n_indices = {device.name: index for index, device in enumerate(n_devices)}
    columns: list[Column] = []
    mismatches = 0
    gap_columns = 0
    for index, (p_device, n_device) in enumerate(aligned):
        p_gate = p_device.gate if p_device else None
        n_gate = n_device.gate if n_device else None
        if p_gate is not None and n_gate is not None and p_gate != n_gate:
            mismatches += 1
        if p_gate is None or n_gate is None:
            gap_columns += 1
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
        if index + 1 >= len(aligned):
            continue
        next_p = next(
            (candidate for candidate_index, candidate in enumerate(aligned[index + 1 :], index + 1)
             if candidate[0] is not None),
            (None, None),
        )[0]
        next_n = next(
            (candidate for candidate_index, candidate in enumerate(aligned[index + 1 :], index + 1)
             if candidate[1] is not None),
            (None, None),
        )[1]
        p_net = (
            _diffusion_net_between(circuit, p_devices, p_indices[p_device.name], p_indices[next_p.name])
            if p_device is not None and next_p is not None
            else None
        )
        n_net = (
            _diffusion_net_between(circuit, n_devices, n_indices[n_device.name], n_indices[next_n.name])
            if n_device is not None and next_n is not None
            else None
        )
        columns.append(
            Column(
                kind="diffusion",
                p_net=p_net,
                n_net=n_net,
                diffusion_shared=p_net is not None and n_net is not None,
            )
        )
    shared_edges = p_order.shared_diffusion_edges + n_order.shared_diffusion_edges
    breaks = p_order.diffusion_breaks + n_order.diffusion_breaks
    routing_estimate = float(mismatches * 4 + gap_columns * 2 + breaks)
    return ColumnIR(
        p_order,
        n_order,
        tuple(columns),
        breaks,
        mismatches,
        gap_columns,
        shared_edges,
        routing_estimate,
    )


def enumerate_column_ir(
    circuit: CellCircuit,
    process: StdcellProcess,
    limit: int | None = 32,
) -> tuple[ColumnIR, ...]:
    if limit is not None and limit < 1:
        raise ValueError("column limit must be positive or None")
    model_names = process.model_names
    p_orders = enumerate_orderings(circuit, "p", limit=limit, model_names=model_names)
    n_orders = enumerate_orderings(circuit, "n", limit=limit, model_names=model_names)
    if not p_orders or not n_orders:
        raise ValueError(f"{circuit.name}: both PUN and PDN are required")
    candidates = [
        build_column_ir(circuit, p_order, n_order)
        for p_order, n_order in product(p_orders, n_orders)
    ]
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
        if limit is not None and len(unique) >= limit:
            break
    return tuple(unique)
