"""Typed canonical-device/netlist contracts.

Process fragments remain source files; this module exposes the stable contract
consumed by generators and verification gates.  Backend terminal order and
parameter normalization are explicit so a canonical device never inherits a
simulator or LVS convention by accident.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
from typing import Any, Iterable

from common.process_ir import DeviceBinding, ProcessIR, ProcessIRError


_ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Pow: lambda left, right: left**right,
}
_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: lambda value: +value,
    ast.USub: lambda value: -value,
}


def _finite_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProcessIRError(f"{context} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ProcessIRError(f"{context} must be a finite number")
    return number


def _evaluate_expression(expression: str, values: dict[str, Any], context: str) -> float:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ProcessIRError(f"{context}: invalid derive expression") from exc

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            return _finite_number(node.value, context)
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ProcessIRError(
                    f"{context}: derive expression needs parameter {node.id!r}"
                )
            return _finite_number(values[node.id], f"{context}.{node.id}")
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
            return _ALLOWED_UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            try:
                result = _ALLOWED_BINARY_OPERATORS[type(node.op)](left, right)
            except (ArithmeticError, OverflowError) as exc:
                raise ProcessIRError(f"{context}: derive expression failed") from exc
            return _finite_number(result, context)
        raise ProcessIRError(
            f"{context}: derive expressions allow numeric constants, parameter names, "
            "and + - * / ** only"
        )

    return evaluate(tree)


@dataclass(frozen=True)
class ParameterTransform:
    """One deterministic canonical-to-backend parameter transform."""

    operation: str
    source: str | None = None
    target: str | None = None
    factor: float | None = None
    expression: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any], context: str) -> "ParameterTransform":
        operation = str(raw.get("operation") or raw.get("op") or "").lower()
        allowed = {"rename", "scale", "multiply", "divide", "derive", "ignore"}
        if operation not in allowed:
            raise ProcessIRError(
                f"{context}: operation must be one of {sorted(allowed)}, got {operation!r}"
            )
        source = raw.get("source")
        target = raw.get("target")
        source_text = str(source) if source is not None else None
        target_text = str(target) if target is not None else None
        if operation in {"rename", "scale", "multiply", "divide", "ignore"} and not source_text:
            raise ProcessIRError(f"{context}: {operation} requires source")
        if operation in {"rename", "scale", "multiply", "divide"} and not target_text:
            raise ProcessIRError(f"{context}: {operation} requires target")
        factor = None
        if operation in {"scale", "multiply", "divide"}:
            if "factor" not in raw:
                raise ProcessIRError(f"{context}: {operation} requires factor")
            factor = _finite_number(raw["factor"], f"{context}.factor")
            if operation == "divide" and factor == 0:
                raise ProcessIRError(f"{context}: divide factor cannot be zero")
        expression = raw.get("expression")
        if operation == "derive" and (
            not isinstance(expression, str) or not expression.strip()
        ):
            raise ProcessIRError(f"{context}: derive requires expression")
        if operation == "derive" and not target_text:
            raise ProcessIRError(f"{context}: derive requires target")
        return cls(
            operation=operation,
            source=source_text,
            target=target_text,
            factor=factor,
            expression=str(expression) if expression is not None else None,
        )

    def apply(self, values: dict[str, Any], context: str) -> None:
        if self.operation == "ignore":
            values.pop(self.source, None)
            return
        if self.operation == "derive":
            values[self.target] = _evaluate_expression(
                self.expression or "", values, context
            )
            return
        if self.source not in values:
            # Geometry parameters are often optional; an absent source is a
            # deliberate no-op for rename/scale/multiply/divide.
            return
        value = values.pop(self.source)
        if self.operation == "rename":
            values[self.target] = value
            return
        number = _finite_number(value, f"{context}.{self.source}")
        if self.operation in {"scale", "multiply"}:
            values[self.target] = number * self.factor
        else:
            values[self.target] = number / self.factor


def _normalize_mos_geometry(values: dict[str, Any], context: str) -> dict[str, Any]:
    if not {"w", "total_width"} & set(values):
        return values
    normalized = dict(values)
    nf_value = normalized.get("nf", 1)
    m_value = normalized.get("m", 1)
    nf = _finite_number(nf_value, f"{context}.nf")
    m = _finite_number(m_value, f"{context}.m")
    if nf < 1 or m < 1 or not nf.is_integer() or not m.is_integer():
        raise ProcessIRError(f"{context}: nf and m must be positive integers")
    nf_int = int(nf)
    m_int = int(m)
    normalized["nf"] = nf_int
    normalized["m"] = m_int
    total = (
        _finite_number(normalized["total_width"], f"{context}.total_width")
        if "total_width" in normalized
        else None
    )
    width = (
        _finite_number(normalized["w"], f"{context}.w")
        if "w" in normalized
        else None
    )
    if total is not None and total <= 0:
        raise ProcessIRError(f"{context}: total_width must be positive")
    if width is not None and width <= 0:
        raise ProcessIRError(f"{context}: w must be positive")
    if total is not None and width is not None and not math.isclose(
        total, width * nf_int, rel_tol=1e-9, abs_tol=1e-12
    ):
        raise ProcessIRError(
            f"{context}: total_width must equal w * nf for MOS geometry"
        )
    if width is None:
        width = total / nf_int
        normalized["w"] = width
    total = width * nf_int
    normalized["total_width"] = total
    normalized["effective_width"] = total * m_int
    return normalized


@dataclass(frozen=True)
class NetlistContract:
    """Simulation and LVS identity for one canonical device variant."""

    device: str
    canonical_family: str
    canonical_id: str
    canonical_variant: str
    topology: str | None
    voltage_class: str | None
    oxide_class: str | None
    threshold_class: str | None
    channel_class: str | None
    gate_stack: str | None
    isolation: Any
    isolation_domain: str | None
    isolation_topology: str | None
    canonical_attributes: tuple[tuple[str, Any], ...]
    terminals: tuple[str, ...]
    canonical_terminal_order: tuple[str, ...]
    terminal_order: tuple[str, ...]
    terminal_semantics: tuple[tuple[str, str], ...]
    symmetry_groups: tuple[tuple[str, ...], ...]
    simulation_terminal_order: tuple[str, ...]
    simulation_terminal_map: tuple[tuple[str, str], ...]
    lvs_terminal_order: tuple[str, ...]
    lvs_terminal_map: tuple[tuple[str, str], ...]
    representation: str
    name: str
    prefix: str
    model_library: str | None
    parameter_map: tuple[tuple[str, str], ...]
    parameter_transforms: tuple[ParameterTransform, ...]
    lvs_parameter_transforms: tuple[ParameterTransform, ...]
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
        terminals = binding.terminals
        canonical_order = binding.canonical_terminal_order
        if not terminals or set(canonical_order) != set(terminals):
            raise ProcessIRError(
                f"{binding.name}: canonical terminal order must match terminals"
            )
        for domain, order, mapping in (
            (
                "simulation",
                binding.simulation_terminal_order,
                binding.simulation_terminal_map,
            ),
            ("lvs", binding.lvs_terminal_order, binding.lvs_terminal_map),
        ):
            if mapping:
                if set(mapping) != set(terminals) or set(mapping.values()) != set(order):
                    raise ProcessIRError(
                        f"{binding.name}: {domain} terminal map/order is incomplete"
                    )
            elif set(order) != set(terminals):
                raise ProcessIRError(
                    f"{binding.name}: {domain} terminal order must cover canonical terminals"
                )
        if any(
            terminal not in terminals
            for group in binding.symmetry_groups
            for terminal in group
        ):
            raise ProcessIRError(
                f"{binding.name}: symmetry group contains an unknown terminal"
            )
        if binding.topology == "asymmetric_drift" and binding.lvs_permutable:
            raise ProcessIRError(
                f"{binding.name}: asymmetric drift devices cannot permute terminals"
            )
        transforms = [
            ParameterTransform.from_raw(
                raw, f"{binding.name}.parameter_transforms[{index}]"
            )
            for index, raw in enumerate(binding.parameter_transforms)
        ]
        legacy_transforms = [
            ParameterTransform(
                operation="rename", source=source, target=target
            )
            for source, target in sorted(binding.parameter_map.items())
            if source not in {transform.source for transform in transforms}
        ]
        transforms.extend(legacy_transforms)
        lvs_transforms = tuple(
            ParameterTransform.from_raw(
                raw, f"{binding.name}.lvs.parameter_transforms[{index}]"
            )
            for index, raw in enumerate(binding.lvs_parameter_transforms)
        )
        return cls(
            device=binding.name,
            canonical_family=binding.canonical_family,
            canonical_id=binding.canonical_id,
            canonical_variant=binding.canonical_variant,
            topology=binding.topology,
            voltage_class=binding.voltage_class,
            oxide_class=binding.oxide_class,
            threshold_class=binding.threshold_class,
            channel_class=binding.channel_class,
            gate_stack=binding.gate_stack,
            isolation=binding.isolation,
            isolation_domain=binding.isolation_domain,
            isolation_topology=binding.isolation_topology,
            canonical_attributes=tuple(sorted(binding.canonical_attributes.items())),
            terminals=terminals,
            canonical_terminal_order=canonical_order,
            terminal_order=canonical_order,
            terminal_semantics=tuple(sorted(binding.terminal_semantics.items())),
            symmetry_groups=binding.symmetry_groups,
            simulation_terminal_order=binding.simulation_terminal_order,
            simulation_terminal_map=tuple(sorted(binding.simulation_terminal_map.items())),
            lvs_terminal_order=binding.lvs_terminal_order,
            lvs_terminal_map=tuple(sorted(binding.lvs_terminal_map.items())),
            representation=representation,
            name=name,
            prefix=str(prefix),
            model_library=(
                str(binding.simulation["model_library"])
                if binding.simulation.get("model_library") is not None
                else None
            ),
            parameter_map=tuple(sorted(binding.parameter_map.items())),
            parameter_transforms=tuple(transforms),
            lvs_parameter_transforms=lvs_transforms,
            lvs_class=lvs_class,
            lvs_permutable=binding.lvs_permutable,
        )
    def normalize_parameters(self, values: dict[str, Any]) -> dict[str, Any]:
        """Normalize MOS geometry, then apply declared backend transforms."""
        normalized = dict(values)
        if self.canonical_family in {"mos4", "asymmetric_mos4", "rf_mos4"}:
            normalized = _normalize_mos_geometry(normalized, self.device)
        for index, transform in enumerate(self.parameter_transforms):
            transform.apply(normalized, f"{self.device}.parameter_transforms[{index}]")
        return normalized
    def normalize_lvs_parameters(self, values: dict[str, Any]) -> dict[str, Any]:
        """Normalize MOS geometry, then apply declared LVS transforms."""
        normalized = dict(values)
        if self.canonical_family in {"mos4", "asymmetric_mos4", "rf_mos4"}:
            normalized = _normalize_mos_geometry(normalized, self.device)
        for index, transform in enumerate(self.lvs_parameter_transforms):
            transform.apply(
                normalized, f"{self.device}.lvs.parameter_transforms[{index}]"
            )
        return normalized

    def backend_terminal_values(
        self, nets: dict[str, Any], backend: str
    ) -> tuple[Any, ...]:
        """Return nets in the explicit simulation or LVS backend order."""
        if backend == "simulation":
            order = self.simulation_terminal_order
            mapping = dict(self.simulation_terminal_map)
        elif backend == "lvs":
            order = self.lvs_terminal_order
            mapping = dict(self.lvs_terminal_map)
        else:
            raise ProcessIRError(
                f"{self.device}: unsupported terminal backend {backend!r}"
            )
        if not mapping:
            mapping = {name: name for name in self.canonical_terminal_order}
        inverse = {backend_name: canonical for canonical, backend_name in mapping.items()}
        try:
            return tuple(nets[inverse[name]] for name in order)
        except KeyError as exc:
            raise ProcessIRError(
                f"{self.device}: missing canonical net for backend terminal {exc.args[0]!r}"
            ) from exc


def netlist_contract(process: ProcessIR, device: str) -> NetlistContract:
    """Return the validated netlist contract for ``device``."""

    return NetlistContract.from_binding(process.device(device))


def validate_netlist_contracts(
    process: ProcessIR, devices: Iterable[str] | None = None
) -> tuple[NetlistContract, ...]:
    """Validate all selected bindings and return them in stable name order."""

    names = tuple(devices) if devices is not None else tuple(process.device_bindings)
    return tuple(netlist_contract(process, name) for name in sorted(names))
