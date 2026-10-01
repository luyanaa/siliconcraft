"""Conservative RF reporting built on the existing Magic PEX netlist.

The current project boundary is L0 lumped RC.  This module intentionally does
not infer inductance, distributed effects, matching, or EM behavior.  It only
reports extracted R/C elements and performs exact parallel reduction for
branches that share the same two terminals.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
from typing import Any, Iterable

from .policy import PROJECT_RF_POLICY, RFAnalysisPolicy

_SPICE_VALUE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(meg|[tgkmunpf])?\s*$",
    re.IGNORECASE,
)
_SPICE_SUFFIX = {
    "t": 1.0e12,
    "g": 1.0e9,
    "meg": 1.0e6,
    "k": 1.0e3,
    "m": 1.0e-3,
    "u": 1.0e-6,
    "n": 1.0e-9,
    "p": 1.0e-12,
    "f": 1.0e-15,
}


@dataclass(frozen=True)
class LumpedElement:
    """One positive-valued SPICE resistor or capacitor."""

    name: str
    kind: str
    node1: str
    node2: str
    value: float
    source_value: str

    @property
    def unit(self) -> str:
        return "ohm" if self.kind == "R" else "farad"

    @property
    def node_pair(self) -> tuple[str, str]:
        return tuple(sorted((self.node1, self.node2)))


def parse_spice_value(token: str) -> float:
    """Parse the scalar suffixes emitted by ngspice/Magic."""

    match = _SPICE_VALUE.match(token.strip().rstrip(","))
    if not match:
        raise ValueError(f"unsupported SPICE scalar {token!r}")
    suffix = (match.group(2) or "").lower()
    value = float(match.group(1)) * _SPICE_SUFFIX.get(suffix, 1.0)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"SPICE scalar must be finite and positive: {token!r}")
    return value


def _logical_lines(text: str) -> Iterable[str]:
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+"):
            if current:
                current += " " + line[1:].strip()
            continue
        if current:
            yield current
        current = line
    if current:
        yield current


def parse_lumped_elements(
    text: str,
) -> tuple[list[LumpedElement], Counter[str]]:
    """Extract R/C elements and count other SPICE instance prefixes.

    MOS and subcircuit instances are intentionally counted as ignored devices;
    they are not silently treated as passive RF elements.
    """

    elements: list[LumpedElement] = []
    ignored: Counter[str] = Counter()
    for line in _logical_lines(text):
        if line.startswith(("*", ".")):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        prefix = fields[0][0].upper()
        if prefix not in {"R", "C"}:
            ignored[prefix] += 1
            continue
        value = parse_spice_value(fields[3])
        elements.append(
            LumpedElement(
                name=fields[0],
                kind=prefix,
                node1=fields[1],
                node2=fields[2],
                value=value,
                source_value=fields[3],
            )
        )
    return elements, ignored


def validate_rf_request(
    frequencies_hz: Iterable[float],
    die_width_um: float,
    die_height_um: float,
    policy: RFAnalysisPolicy = PROJECT_RF_POLICY,
) -> tuple[float, ...]:
    """Validate and normalize a request against an explicit analysis policy."""

    frequencies = tuple(sorted({float(value) for value in frequencies_hz}))
    if not frequencies:
        raise ValueError("at least one RF frequency is required")
    if any(
        not math.isfinite(value)
        or value < policy.min_frequency_hz
        or value > policy.max_frequency_hz
        for value in frequencies
    ):
        raise ValueError(
            "RF frequency must stay within the inclusive "
            f"{policy.min_frequency_hz:g}–{policy.max_frequency_hz:g} Hz "
            f"envelope ({policy.name})"
        )
    for name, value in (("die width", die_width_um), ("die height", die_height_um)):
        if not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"{name} must be positive")
        if float(value) > policy.max_die_um:
            raise ValueError(
                f"{name} exceeds the {policy.max_die_um:g} um analysis envelope "
                f"({policy.name})"
            )
    return frequencies


def _complex_record(value: complex) -> dict[str, float]:
    return {
        "real": value.real,
        "imag": value.imag,
        "magnitude": abs(value),
        "phase_deg": math.degrees(math.atan2(value.imag, value.real)),
    }


def _element_admittance(element: LumpedElement, frequency_hz: float) -> complex:
    if element.kind == "R":
        return complex(1.0 / element.value, 0.0)
    return complex(0.0, 2.0 * math.pi * frequency_hz * element.value)


def _element_response(
    element: LumpedElement, frequencies_hz: tuple[float, ...]
) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for frequency_hz in frequencies_hz:
        admittance = _element_admittance(element, frequency_hz)
        impedance = 1.0 / admittance
        responses.append(
            {
                "frequency_hz": frequency_hz,
                "admittance_s": _complex_record(admittance),
                "impedance_ohm": _complex_record(impedance),
            }
        )
    return responses


def build_report(
    *,
    profile: str,
    pex_profile: str,
    manifest: dict[str, Any],
    elements: list[LumpedElement],
    ignored: Counter[str],
    frequencies_hz: Iterable[float],
    die_width_um: float,
    die_height_um: float,
    critical_nets: Iterable[str] = (),
    policy: RFAnalysisPolicy = PROJECT_RF_POLICY,
) -> dict[str, Any]:
    """Build a JSON-safe L0 report from a Magic PEX netlist."""

    frequencies = validate_rf_request(
        frequencies_hz, die_width_um, die_height_um, policy
    )
    requested_nets = tuple(dict.fromkeys(str(net) for net in critical_nets if str(net)))
    if requested_nets:
        net_set = set(requested_nets)
        selected = [
            element
            for element in elements
            if element.node1 in net_set or element.node2 in net_set
        ]
    else:
        selected = list(elements)

    profile_spec = (manifest.get("profiles") or {}).get(pex_profile) or {}
    source = profile_spec.get("source") or {}
    flow = manifest.get("flow") or {}
    technology = manifest.get("technology") or {}
    pair_groups: defaultdict[tuple[str, str], list[LumpedElement]] = defaultdict(list)
    for element in selected:
        pair_groups[element.node_pair].append(element)

    serialized_elements = [
        {
            "name": element.name,
            "kind": element.kind,
            "nodes": [element.node1, element.node2],
            "value": element.value,
            "unit": element.unit,
            "source_value": element.source_value,
            "responses": _element_response(element, frequencies),
        }
        for element in selected
    ]

    parallel_pairs: list[dict[str, Any]] = []
    for node_pair in sorted(pair_groups):
        branches = pair_groups[node_pair]
        responses = []
        for frequency_hz in frequencies:
            admittance = sum(
                (_element_admittance(element, frequency_hz) for element in branches),
                complex(0.0, 0.0),
            )
            responses.append(
                {
                    "frequency_hz": frequency_hz,
                    "admittance_s": _complex_record(admittance),
                    "impedance_ohm": _complex_record(1.0 / admittance),
                }
            )
        parallel_pairs.append(
            {
                "nodes": list(node_pair),
                "elements": [element.name for element in branches],
                "responses": responses,
            }
        )

    return {
        "status": "source_reference_lumped_rc",
        "signoff": False,
        "profile": profile,
        "pex_profile": pex_profile,
        "analysis_policy": policy.as_dict(),
        "source": {
            "backend": flow.get("backend"),
            "process": flow.get("original_process"),
            "run": flow.get("original_run"),
            "calibrated": source.get("calibrated"),
            "technology_scope": technology.get("scope"),
        },
        "envelope": {
            "die_width_um": float(die_width_um),
            "die_height_um": float(die_height_um),
            "frequency_hz": list(frequencies),
        },
        "analysis": {
            "level": "L0",
            "elements": "Magic-extracted R/C only",
            "parallel_reduction": "identical terminal pairs only",
            "inductance": "not inferred",
            "distributed_effects": "not modeled",
            "full_wave_em": "not modeled",
        },
        "critical_nets": list(requested_nets),
        "counts": {
            "resistors": sum(element.kind == "R" for element in selected),
            "capacitors": sum(element.kind == "C" for element in selected),
            "ignored_active_or_subcircuit_instances": dict(sorted(ignored.items())),
        },
        "elements": serialized_elements,
        "parallel_pairs": parallel_pairs,
    }
