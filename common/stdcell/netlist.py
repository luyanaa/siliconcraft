"""Small, deterministic transistor-level SPICE/CDL parser for stdcell input."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable


class NetlistError(ValueError):
    """Raised when a stdcell transistor netlist violates its input contract."""


_SUFFIXES = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1.0,
    "n": 1e-3,
    "p": 1e-6,
    "f": 1e-9,
}


def _dimension_um(value: str) -> float:
    """Parse a SPICE dimension and return micrometres.

    Plain values are interpreted as micrometres because the canonical
    siliconcraft device contract uses um geometry.  Explicit ``u``/``um``
    suffixes are also accepted; SI metre exponents are converted to um.
    """

    text = value.strip().lower()
    if not text:
        raise NetlistError("empty geometry value")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)([a-z]+)?", text)
    if not match:
        raise NetlistError(f"invalid geometry value {value!r}")
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix is None:
        return number
    if suffix in {"um", "micron", "microns"}:
        return number
    if suffix in {"m", "mm", "nm", "pm"}:
        scale = {"m": 1e6, "mm": 1e3, "nm": 1e-3, "pm": 1e-6}[suffix]
        return number * scale
    if suffix in _SUFFIXES:
        return number * _SUFFIXES[suffix]
    raise NetlistError(f"unsupported geometry suffix in {value!r}")


def _int_value(value: str, field: str) -> int:
    try:
        parsed = int(float(value))
    except ValueError as exc:
        raise NetlistError(f"{field} must be an integer, got {value!r}") from exc
    if parsed < 1:
        raise NetlistError(f"{field} must be >= 1")
    return parsed


@dataclass(frozen=True)
class MosInstance:
    name: str
    drain: str
    gate: str
    source: str
    bulk: str
    model: str
    width_um: float
    length_um: float | None
    nf: int = 1
    multiplicity: int = 1

    @property
    def diffusion_nets(self) -> tuple[str, str]:
        return self.drain, self.source

    @property
    def terminals(self) -> tuple[str, str, str, str]:
        return self.drain, self.gate, self.source, self.bulk


@dataclass(frozen=True)
class DiffusionGraph:
    polarity: str
    devices: tuple[MosInstance, ...]
    nets: dict[str, tuple[str, ...]]

    def edge(self, device: MosInstance) -> tuple[str, str, str]:
        return device.source, device.gate, device.drain


@dataclass(frozen=True)
class CircuitIR:
    name: str
    ports: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    supplies: tuple[str, ...]
    devices: tuple[MosInstance, ...]
    metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)
    @property
    def internal_nets(self) -> tuple[str, ...]:
        ports = set(self.ports)
        return tuple(
            sorted(
                {
                    node
                    for device in self.devices
                    for node in device.terminals
                    if node not in ports
                }
            )
        )

    @property
    def timing_arcs(self) -> tuple[tuple[str, str], ...]:
        return tuple((input_name, output_name) for input_name in self.inputs for output_name in self.outputs)

    def devices_for_model(self, models: Iterable[str]) -> tuple[MosInstance, ...]:
        accepted = set(models)
        return tuple(device for device in self.devices if device.model in accepted)

    def diffusion_graph(self, polarity: str, model_names: dict[str, str]) -> DiffusionGraph:
        model = model_names.get(polarity)
        if not model:
            raise NetlistError(f"{self.name}: missing model binding for {polarity} network")
        devices = tuple(device for device in self.devices if device.model == model)
        if not devices:
            raise NetlistError(f"{self.name}: no {polarity} devices for model {model!r}")
        nets: dict[str, list[str]] = {}
        for device in devices:
            for net in device.diffusion_nets:
                nets.setdefault(net, []).append(device.name)
        return DiffusionGraph(
            polarity=polarity,
            devices=devices,
            nets={net: tuple(names) for net, names in nets.items()},
        )


CellCircuit = CircuitIR


def _comment_metadata(line: str, metadata: dict[str, tuple[str, ...]]) -> None:
    body = line.lstrip()[1:].strip()
    match = re.match(r"siliconcraft\s+([a-z][a-z0-9_]*)\s*:\s*(.*)$", body, re.IGNORECASE)
    if not match:
        return
    key = match.group(1).lower()
    values = tuple(value for value in re.split(r"[\s,]+", match.group(2).strip()) if value)
    metadata[key] = values


def _parse_mos(tokens: list[str], line_number: int) -> MosInstance:
    if len(tokens) < 6:
        raise NetlistError(f"line {line_number}: MOS instance needs name, four terminals, and model")
    name, drain, gate, source, bulk, model = tokens[:6]
    params: dict[str, str] = {}
    for token in tokens[6:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[key.strip().lower()] = value.strip()
    if "w" not in params:
        raise NetlistError(f"line {line_number}: {name} is missing W")
    width = _dimension_um(params["w"])
    if width <= 0:
        raise NetlistError(f"line {line_number}: {name} W must be positive")
    length = _dimension_um(params["l"]) if "l" in params else None
    nf = _int_value(params.get("nf", "1"), f"{name} NF")
    multiplicity = _int_value(params.get("m", "1"), f"{name} M")
    return MosInstance(name, drain, gate, source, bulk, model, width, length, nf, multiplicity)


def parse_spice(text: str) -> CellCircuit:
    """Parse one annotated ``.subckt`` containing primitive MOS instances."""

    subckt: str | None = None
    ports: tuple[str, ...] = ()
    devices: list[MosInstance] = []
    metadata: dict[str, tuple[str, ...]] = {}
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            _comment_metadata(stripped, metadata)
            continue
        line = stripped.split("$", 1)[0].strip()
        if not line:
            continue
        tokens = line.replace(",", " ").split()
        directive = tokens[0].lower()
        if directive == ".subckt":
            if subckt is not None:
                raise NetlistError(f"line {line_number}: nested .subckt is not supported")
            if len(tokens) < 3:
                raise NetlistError(f"line {line_number}: .subckt needs a name and ports")
            subckt = tokens[1]
            ports = tuple(tokens[2:])
            continue
        if directive == ".ends":
            continue
        if directive.startswith("."):
            continue
        if tokens[0][0].lower() == "m":
            devices.append(_parse_mos(tokens, line_number))

    if subckt is None:
        raise NetlistError("missing .subckt")
    if not devices:
        raise NetlistError(f"{subckt}: no primitive MOS instances")
    if len(set(ports)) != len(ports):
        raise NetlistError(f"{subckt}: duplicate subcircuit ports")

    supply_names = metadata.get("supplies") or tuple(
        port
        for port in ports
        if port.lower() in {"vdd", "vdd!", "vss", "vss!", "gnd", "gnd!", "0"}
    )
    inputs = metadata.get("inputs")
    outputs = metadata.get("outputs")
    if not inputs or not outputs:
        raise NetlistError(
            f"{subckt}: add '* siliconcraft inputs: ...' and '* siliconcraft outputs: ...' metadata"
        )
    for label, values in (("inputs", inputs), ("outputs", outputs), ("supplies", supply_names)):
        missing = sorted(set(values) - set(ports))
        if missing:
            raise NetlistError(f"{subckt}: {label} reference unknown ports {missing}")
    if set(inputs) & set(outputs):
        raise NetlistError(f"{subckt}: inputs and outputs overlap")
    if set(inputs) & set(supply_names) or set(outputs) & set(supply_names):
        raise NetlistError(f"{subckt}: signal port is also a supply")
    return CellCircuit(
        subckt,
        ports,
        tuple(inputs),
        tuple(outputs),
        tuple(supply_names),
        tuple(devices),
        metadata,
    )
