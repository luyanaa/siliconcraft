"""Typed model evidence, authority, and simulation bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.process_ir import ProcessIR, ProcessIRError


@dataclass(frozen=True)
class ModelEvidence:
    """Evidence and maturity metadata without changing source YAML."""

    status: str | None
    confidence: str | None
    maturity: tuple[tuple[str, Any], ...]
    limitations: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ModelCapabilities:
    simulator: bool
    lvs: bool
    calibrated: bool


@dataclass(frozen=True)
class ModelIR:
    """One model identity plus its source/evidence and capabilities."""

    name: str
    kind: str | None
    simulation_name: str | None
    library: str | None
    source: str | None
    parameters: tuple[tuple[str, Any], ...]
    fit_parameters: tuple[tuple[str, Any], ...]
    evidence: ModelEvidence
    capabilities: ModelCapabilities
    authority: str

    def parameter(self, name: str) -> Any:
        values = dict(self.parameters)
        try:
            return values[name]
        except KeyError as exc:
            raise ProcessIRError(f"{self.name}: model parameter {name!r} is absent") from exc

    def fit_parameter(self, name: str) -> Any:
        values = dict(self.fit_parameters)
        try:
            return values[name]
        except KeyError as exc:
            raise ProcessIRError(f"{self.name}: fit parameter {name!r} is absent") from exc


def _evidence(raw: dict[str, Any]) -> ModelEvidence:
    source = raw.get("source")
    sources: list[str] = []
    if isinstance(source, str):
        sources.append(source)
    elif isinstance(source, dict):
        for key in ("repository", "path", "commit"):
            if source.get(key) is not None:
                sources.append(f"{key}={source[key]}")
    return ModelEvidence(
        status=(str(raw["evidence_status"]) if raw.get("evidence_status") is not None else None),
        confidence=(str(raw["confidence"]) if raw.get("confidence") is not None else None),
        maturity=tuple(sorted((raw.get("maturity") or {}).items())),
        limitations=tuple(str(item) for item in (raw.get("limitations") or ())),
        sources=tuple(sources),
    )


def _model(
    name: str,
    raw: dict[str, Any],
    *,
    authority: str,
    default_simulator: bool,
    default_lvs: bool,
) -> ModelIR:
    maturity = raw.get("maturity") or {}
    signoff = maturity.get("signoff") is True
    coefficient = raw.get("coefficient")
    parameters = raw.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {"value": parameters}
    fit = raw.get("fit") or {}
    fit_parameters = fit.get("parameters") or {}
    if not isinstance(fit_parameters, dict):
        fit_parameters = {"value": fit_parameters}
    return ModelIR(
        name=name,
        kind=(str(raw["kind"]) if raw.get("kind") is not None else None),
        simulation_name=(
            str(raw.get("subcircuit") or raw.get("model_id") or name)
            if raw.get("subcircuit") is not None
            or raw.get("model_id") is not None
            or default_simulator
            else None
        ),
        library=(str(raw["library"]) if raw.get("library") is not None else None),
        source=(str(raw["source"]) if isinstance(raw.get("source"), str) else None),
        parameters=tuple(sorted(parameters.items())),
        fit_parameters=tuple(sorted(fit_parameters.items())),
        evidence=_evidence(raw),
        capabilities=ModelCapabilities(
            simulator=default_simulator,
            lvs=default_lvs,
            calibrated=signoff or raw.get("status") == "calibrated",
        ),
        authority=authority,
    )


def model_irs(process: ProcessIR) -> tuple[ModelIR, ...]:
    """Normalize maturity, simulator, LVS-only, and reference model records."""

    result: dict[str, ModelIR] = {}
    for name, raw in process.model_parameters.items():
        if isinstance(raw, dict):
            result[str(name)] = _model(
                str(name), raw, authority="maturity", default_simulator=True, default_lvs=True
            )

    contract = process.model_contract_doc
    for section, authority, simulator, lvs in (
        ("models", "simulation", True, True),
        ("lvs_only_models", "lvs_only", False, True),
        ("reference_only_models", "reference_only", False, False),
    ):
        for name, raw in (contract.get(section) or {}).items():
            if isinstance(raw, dict) and name not in result:
                result[str(name)] = _model(
                    str(name), raw, authority=authority,
                    default_simulator=simulator, default_lvs=lvs,
                )
    return tuple(result[name] for name in sorted(result))


def model_ir(process: ProcessIR, name: str) -> ModelIR:
    for model in model_irs(process):
        if model.name == name:
            return model
    raise ProcessIRError(f"{process.profile}: model {name!r} is absent")
