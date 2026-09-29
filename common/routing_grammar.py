"""Process-neutral routing grammar inferred from PDK connectivity evidence.

The router consumes conductor IDs, transitions, region constraints, and costs.
It does not assign physical meaning such as ``M0`` or ``local interconnect``;
that interpretation belongs to the PDK import/probe boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any

from common.process_ir import ProcessIR, load_process


SUPPORTED = "SUPPORTED"
EXPERIMENTAL = "EXPERIMENTAL"
UNKNOWN = "UNKNOWN"
FORBIDDEN = "FORBIDDEN"
STATES = frozenset({SUPPORTED, EXPERIMENTAL, UNKNOWN, FORBIDDEN})


@dataclass(frozen=True)
class Evidence:
    status: str = UNKNOWN
    evidence: tuple[str, ...] = ()
    drc: str = "unknown"
    lvs: str = "unknown"
    devices: tuple[str, ...] = ()
    confidence: str = "unknown"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATES:
            raise ValueError(f"unknown routing grammar state: {self.status!r}")
        if self.confidence not in {"high", "medium", "low", "unknown"}:
            raise ValueError(f"unknown routing grammar confidence: {self.confidence!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence": list(self.evidence),
            "drc": self.drc,
            "lvs": self.lvs,
            "devices": list(self.devices),
            "confidence": self.confidence,
            "details": self.details,
        }


@dataclass(frozen=True)
class ConductorGrammar:
    name: str
    continuity: Evidence
    regions: dict[str, Evidence]
    connections: dict[str, Evidence]
    electrical: dict[str, Any]
    cost: float
    max_useful_length_um: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "continuity": self.continuity.as_dict(),
            "regions": {name: value.as_dict() for name, value in self.regions.items()},
            "connections": {name: value.as_dict() for name, value in self.connections.items()},
            "electrical": self.electrical,
            "routing_policy": {
                "cost": self.cost,
                "max_useful_length_um": self.max_useful_length_um,
            },
        }


@dataclass(frozen=True)
class RoutingGrammar:
    profile: str
    source_kind: str
    source_files: tuple[str, ...]
    conductors: dict[str, ConductorGrammar]
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "routing_grammar",
            "profile": self.profile,
            "source_kind": self.source_kind,
            "source_files": list(self.source_files),
            "metadata": self.metadata,
            "conductors": {
                name: conductor.as_dict()
                for name, conductor in self.conductors.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoutingGrammar":
        conductors = {}
        for name, value in (payload.get("conductors") or {}).items():
            continuity = Evidence(**_evidence_kwargs(value.get("continuity")))
            regions = {
                region: Evidence(**_evidence_kwargs(observation))
                for region, observation in (value.get("regions") or {}).items()
            }
            connections = {
                target: Evidence(**_evidence_kwargs(observation))
                for target, observation in (value.get("connections") or {}).items()
            }
            policy = value.get("routing_policy") or {}
            conductors[name] = ConductorGrammar(
                name=name,
                continuity=continuity,
                regions=regions,
                connections=connections,
                electrical=dict(value.get("electrical") or {}),
                cost=float(policy.get("cost", 10.0)),
                max_useful_length_um=policy.get("max_useful_length_um"),
            )
        return cls(
            profile=str(payload.get("profile", "unknown")),
            source_kind=str(payload.get("source_kind", "unknown")),
            source_files=tuple(str(item) for item in payload.get("source_files", ())),
            conductors=conductors,
            metadata=dict(payload.get("metadata") or {}),
        )

    @classmethod
    def load(cls, path: Path) -> "RoutingGrammar":
        import json

        return cls.from_dict(json.loads(path.read_text()))

    def write(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n")

    def conductor_allowed(self, name: str, region: str, *, allow_experimental: bool = True) -> bool:
        conductor = self.conductors.get(name)
        if conductor is None:
            return False
        observation = conductor.regions.get(region, conductor.continuity)
        allowed = {SUPPORTED}
        if allow_experimental:
            allowed.add(EXPERIMENTAL)
        return observation.status in allowed

    def transition_allowed(
        self,
        source: str,
        target: str,
        *,
        allow_experimental: bool = True,
    ) -> bool:
        conductor = self.conductors.get(source)
        if conductor is None:
            return False
        observation = conductor.connections.get(target)
        if observation is None:
            return False
        allowed = {SUPPORTED}
        if allow_experimental:
            allowed.add(EXPERIMENTAL)
        return observation.status in allowed

    def routing_layers(self, *, allow_experimental: bool = True) -> tuple[str, ...]:
        return tuple(
            name
            for name, conductor in self.conductors.items()
            if conductor_allowed_for(conductor, allow_experimental)
        )


def conductor_allowed_for(conductor: ConductorGrammar, allow_experimental: bool) -> bool:
    allowed = {SUPPORTED}
    if allow_experimental:
        allowed.add(EXPERIMENTAL)
    return conductor.continuity.status in allowed


def _evidence_kwargs(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    return {
        "status": str(value.get("status", UNKNOWN)),
        "evidence": tuple(str(item) for item in value.get("evidence", ())),
        "drc": str(value.get("drc", "unknown")),
        "lvs": str(value.get("lvs", "unknown")),
        "devices": tuple(str(item) for item in value.get("devices", ())),
        "confidence": str(value.get("confidence", "unknown")),
        "details": dict(value.get("details") or {}),
    }


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def inspect_lvs_connectivity(text: str, source: str = "<memory>") -> dict[str, Any]:
    """Extract conservative static facts from a KLayout ``.lylvs`` source."""
    text = _strip_comments(text)
    input_specs = {
        match.group(1): (int(match.group(2)), int(match.group(3)))
        for match in re.finditer(
            r"\b([A-Za-z_]\w*)\s*=\s*input\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)",
            text,
        )
    }
    input_layers = tuple(input_specs)
    aliases = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*$",
            text,
            re.MULTILINE,
        )
        if match.group(1) != match.group(2)
    }
    single_connect = tuple(
        dict.fromkeys(
            match.group(1)
            for match in re.finditer(
                r"\bconnect\s*\(\s*([A-Za-z_]\w*)\s*\)", text
            )
        )
    )
    pair_connect = tuple(
        dict.fromkeys(
            (match.group(1), match.group(2))
            for match in re.finditer(
                r"\bconnect\s*\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)",
                text,
            )
        )
    )
    device_terminals: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r"extract_devices\s*\(\s*([^,\s(]+)\s*\([^)]*\)\s*,\s*\{(.*?)\}\s*\)",
        text,
        re.DOTALL,
    ):
        device_kind = match.group(1)
        terminal_map = {
            key.upper(): layer
            for key, layer in re.findall(
                r"[\"']?([A-Za-z][A-Za-z0-9_]*)[\"']?\s*=>\s*([A-Za-z_]\w*)",
                match.group(2),
            )
        }
        device_terminals.setdefault(device_kind, {}).update(terminal_map)
    return {
        "source": source,
        "input_layers": input_layers,
        "input_specs": input_specs,
        "aliases": aliases,
        "single_connect": single_connect,
        "pair_connect": pair_connect,
        "device_terminals": device_terminals,
    }


def _available_lvs_sources(process: ProcessIR) -> tuple[Path, ...]:
    sources: list[Path] = []
    for directory in ("official", "reference"):
        directory_path = process.profile_dir / directory
        if not directory_path.exists():
            continue
        sources.extend(sorted(directory_path.rglob("*.lylvs")))
    return tuple(sources)


def _layer_candidates(process: ProcessIR, facts: list[dict[str, Any]]) -> list[str]:
    roles = {"metal", "gate", "interconnect"}
    return sorted(
        name
        for name, layer in process.layers.items()
        if layer.get("available", True) and layer.get("role") in roles
    )
def _canonicalize_facts(
    process: ProcessIR,
    facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gds_to_layer = {}
    for name, layer in process.layers.items():
        for gds in layer.get("gds") or ():
            gds_to_layer[(int(gds["layer"]), int(gds["datatype"]))] = name

    canonical_facts = []
    for fact in facts:
        aliases = dict(fact.get("aliases") or {})
        input_specs = dict(fact.get("input_specs") or {})

        def resolve(name: str) -> str:
            seen = set()
            current = name
            while current in aliases and current not in seen:
                seen.add(current)
                current = aliases[current]
            spec = input_specs.get(current)
            if spec is not None:
                return gds_to_layer.get(tuple(spec), current)
            return current

        canonical_facts.append(
            {
                **fact,
                "canonical_single_connect": tuple(
                    dict.fromkeys(resolve(name) for name in fact["single_connect"])
                ),
                "canonical_pair_connect": tuple(
                    dict.fromkeys(
                        (resolve(source), resolve(target))
                        for source, target in fact["pair_connect"]
                    )
                ),
                "canonical_device_terminals": {
                    kind: {
                        key: resolve(layer)
                        for key, layer in terminals.items()
                    }
                    for kind, terminals in fact["device_terminals"].items()
                },
            }
        )
    return canonical_facts


def _confidence_for_status(status: str, *, native: bool) -> str:
    if status == UNKNOWN:
        return "unknown"
    if status == EXPERIMENTAL:
        return "medium" if native else "low"
    return "high" if native else "medium"


def _electrical_for_layer(layer: dict[str, Any]) -> dict[str, Any]:
    source = dict(layer.get("electrical") or {})
    values = {
        "status": str(source.get("status", "unknown")),
        "sheet_resistance_ohm_per_square": source.get("sheet_resistance_ohm_per_square"),
        "resistance_ohm_per_um": source.get("resistance_ohm_per_um"),
        "nominal_width_um": source.get("nominal_width_um"),
        "current_limit": source.get("current_limit", "unknown"),
        "reliability": source.get("reliability", "unknown"),
    }
    return {key: value for key, value in values.items() if value is not None}


def _static_observation(
    status: str,
    evidence: tuple[str, ...],
    *,
    details: dict[str, Any] | None = None,
) -> Evidence:
    return Evidence(
        status=status,
        evidence=evidence,
        drc="not_run",
        lvs="static",
        confidence=_confidence_for_status(status, native=False),
        details=details or {},
    )

def inspect_profile(profile: str, root: Path) -> RoutingGrammar:
    """Build a conservative grammar from profile layers and readable LVS decks."""
    root = root.resolve()
    process = load_process(profile, root)
    source_paths = _available_lvs_sources(process)
    facts = [
        inspect_lvs_connectivity(path.read_text(), str(path.relative_to(root)))
        for path in source_paths
    ]
    canonical_facts = _canonicalize_facts(process, facts)
    candidates = _layer_candidates(process, canonical_facts)
    canonical_pairs = {
        pair
        for fact in canonical_facts
        for pair in fact["canonical_pair_connect"]
    }
    canonical_singles = {
        layer
        for fact in canonical_facts
        for layer in fact["canonical_single_connect"]
    }
    device_gate_layers = {
        layer
        for fact in canonical_facts
        for terminals in fact["canonical_device_terminals"].values()
        for key, layer in terminals.items()
        if key in {"G", "TG"}
    }
    cut_layers = {
        name
        for name, layer in process.layers.items()
        if layer.get("available", True) and layer.get("role") == "cut"
    }
    source_kind = "klayout_lvs_static" if source_paths else "no_readable_klayout_lvs"

    def evidence_for_pair(source: str, target: str) -> tuple[str, ...]:
        return tuple(
            fact["source"]
            for fact in canonical_facts
            if (source, target) in fact["canonical_pair_connect"]
            or (target, source) in fact["canonical_pair_connect"]
        )

    conductors: dict[str, ConductorGrammar] = {}
    for name in candidates:
        if not source_paths:
            continuity = _static_observation(
                UNKNOWN,
                (),
                details={"reason": "no readable KLayout LVS deck"},
            )
        elif name in canonical_singles:
            continuity = _static_observation(
                SUPPORTED,
                tuple(
                    fact["source"]
                    for fact in canonical_facts
                    if name in fact["canonical_single_connect"]
                ),
                details={"explicit_single_layer_connect": True},
            )
        elif any(name in pair for pair in canonical_pairs):
            continuity = _static_observation(
                EXPERIMENTAL,
                tuple(
                    fact["source"]
                    for fact in canonical_facts
                    if any(name in pair for pair in fact["canonical_pair_connect"])
                ),
                details={
                    "explicit_single_layer_connect": False,
                    "reason": "layer only appears in inter-layer connectivity",
                },
            )
        else:
            continuity = _static_observation(
                UNKNOWN,
                (),
                details={"reason": "layer absent from readable connectivity declarations"},
            )
        forms_device = name in device_gate_layers
        regions = {
            "field": continuity,
            "active": _static_observation(
                SUPPORTED,
                ("extract_devices gate terminal",),
                details={"forms_device": True},
            ) if forms_device else _static_observation(UNKNOWN, ()),
            "active_n": _static_observation(UNKNOWN, ()),
            "active_p": _static_observation(UNKNOWN, ()),
            "gate": _static_observation(
                SUPPORTED,
                ("extract_devices gate terminal",),
                details={"forms_device": True},
            ) if forms_device else _static_observation(UNKNOWN, ()),
        }
        connections: dict[str, Evidence] = {}
        for target in candidates:
            if target == name:
                continue
            direct_evidence = evidence_for_pair(name, target)
            via_paths = [
                cut
                for cut in sorted(cut_layers)
                if (
                    ((name, cut) in canonical_pairs or (cut, name) in canonical_pairs)
                    and ((cut, target) in canonical_pairs or (target, cut) in canonical_pairs)
                )
            ]
            if direct_evidence:
                connections[target] = _static_observation(
                    SUPPORTED,
                    direct_evidence,
                    details={"direct_inter_layer_connect": True},
                )
            elif via_paths:
                connections[target] = _static_observation(
                    EXPERIMENTAL,
                    tuple(
                        fact["source"]
                        for fact in canonical_facts
                        if any(
                            (
                                (name, cut) in fact["canonical_pair_connect"]
                                or (cut, name) in fact["canonical_pair_connect"]
                            )
                            and (
                                (cut, target) in fact["canonical_pair_connect"]
                                or (target, cut) in fact["canonical_pair_connect"]
                            )
                            for cut in via_paths
                        )
                    ),
                    details={"via_layers": via_paths},
                )
            else:
                connections[target] = _static_observation(UNKNOWN, ())
        layer = process.layers.get(name, {})
        role = layer.get("role")
        electrical = _electrical_for_layer(layer)
        electrical.setdefault("current_limit", "unknown")
        electrical.setdefault("reliability", "unknown")
        electrical.setdefault("status", "unknown")
        routing_cost = layer.get("routing_cost")
        if not isinstance(routing_cost, (int, float)):
            routing_cost = 10.0 if role not in {"metal"} else 1.0
        max_length = layer.get("max_useful_length_um")
        if not isinstance(max_length, (int, float)):
            max_length = electrical.get("max_useful_length_um")
        conductors[name] = ConductorGrammar(
            name=name,
            continuity=continuity,
            regions=regions,
            connections=connections,
            electrical=electrical,
            cost=float(routing_cost),
            max_useful_length_um=float(max_length) if isinstance(max_length, (int, float)) else None,
        )
    return RoutingGrammar(
        profile=profile,
        source_kind=source_kind,
        source_files=tuple(str(path.relative_to(root)) for path in source_paths),
        conductors=conductors,
        metadata={
            "layer_roles_are_import_hints_only": True,
            "static_facts": canonical_facts,
            "active_probes": "not_run",
            "legality_is_separate_from_electrical_desirability": True,
        },
    )
