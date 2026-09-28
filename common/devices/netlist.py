"""Typed canonical-device/netlist contracts.

Process fragments remain source files; this module exposes the stable contract
consumed by generators and verification gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from common.process_ir import DeviceBinding, ProcessIR, ProcessIRError


@dataclass(frozen=True)
class NetlistContract:
    """Simulation and LVS identity for one canonical device variant."""

    device: str
    canonical_variant: str
    terminals: tuple[str, ...]
    terminal_order: tuple[str, ...]
    symmetry_groups: tuple[tuple[str, ...], ...]
    representation: str
    name: str
    prefix: str
    model_library: str | None
    parameter_map: tuple[tuple[str, str], ...]
    lvs_class: str
    lvs_permutable: tuple[tuple[str, ...], ...]

    @classmethod
    def from_binding(cls, binding: DeviceBinding) -> "NetlistContract":
        representation = binding.simulation_representation
        name = binding.simulation_name
        prefix = binding.simulation.get("prefix")
        lvs_class = binding.lvs_class
        if not representation or not name or not prefix or not lvs_class:
            raise ProcessIRError(
                f"{binding.name}: incomplete simulation/LVS netlist binding"
            )
        if not binding.terminals or binding.terminal_order != binding.terminals:
            raise ProcessIRError(
                f"{binding.name}: terminal_order must match canonical terminals"
            )
        if any(
            terminal not in binding.terminals
            for group in binding.symmetry_groups
            for terminal in group
        ):
            raise ProcessIRError(
                f"{binding.name}: symmetry group contains an unknown terminal"
            )
        return cls(
            device=binding.name,
            canonical_variant=binding.canonical_variant,
            terminals=binding.terminals,
            terminal_order=binding.terminal_order,
            symmetry_groups=binding.symmetry_groups,
            representation=representation,
            name=name,
            prefix=str(prefix),
            model_library=(
                str(binding.simulation["model_library"])
                if binding.simulation.get("model_library") is not None
                else None
            ),
            parameter_map=tuple(sorted(binding.parameter_map.items())),
            lvs_class=lvs_class,
            lvs_permutable=binding.lvs_permutable,
        )


def netlist_contract(process: ProcessIR, device: str) -> NetlistContract:
    """Return the validated netlist contract for ``device``."""

    return NetlistContract.from_binding(process.device(device))


def validate_netlist_contracts(
    process: ProcessIR, devices: Iterable[str] | None = None
) -> tuple[NetlistContract, ...]:
    """Validate all selected bindings and return them in stable name order."""

    names = tuple(devices) if devices is not None else tuple(process.device_bindings)
    return tuple(netlist_contract(process, name) for name in sorted(names))
