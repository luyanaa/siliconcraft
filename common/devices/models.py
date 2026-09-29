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
    maturity_level: str | None
    model_form: str | None
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


def _maturity_view(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    maturity = raw.get("maturity") or {}
    if not isinstance(maturity, dict):
        return None, None
    level = maturity.get("level") or maturity.get("current_level")
    level_name = str(level) if level is not None else None
    levels = maturity.get("levels") or {}
    current = levels.get(level_name) if isinstance(levels, dict) and level_name else None
    if not isinstance(current, dict):
        current = {}
    model_form = current.get("model_form")
    if model_form is None:
        raw_form = raw.get("model_form") or {}
        if isinstance(raw_form, dict):
            model_form = raw_form.get("current")
    return level_name, (str(model_form) if model_form is not None else None)


def _evidence(raw: dict[str, Any]) -> ModelEvidence:
    source = raw.get("source")
    sources: list[str] = []
    if isinstance(source, str):
        sources.append(source)
    elif isinstance(source, dict):
        for key in ("repository", "path", "commit"):
            if source.get(key) is not None:
                sources.append(f"{key}={source[key]}")
    maturity_level, model_form = _maturity_view(raw)
    limitations = raw.get("limitations")
    if limitations is None and raw.get("limitation") is not None:
        limitations = [raw.get("limitation")]
    return ModelEvidence(
        status=(str(raw["evidence_status"]) if raw.get("evidence_status") is not None else None),
        confidence=(str(raw["confidence"]) if raw.get("confidence") is not None else None),
        maturity=tuple(sorted((raw.get("maturity") or {}).items())),
        maturity_level=maturity_level,
        model_form=model_form,
        limitations=tuple(str(item) for item in (limitations or ())),
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
    if not isinstance(maturity, dict):
        maturity = {}
    signoff = maturity.get("signoff") is True
    parameters = raw.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {"value": parameters}
    fit = raw.get("fit") or {}
    fit_parameters = fit.get("parameters") or {}
    if not isinstance(fit_parameters, dict):
        fit_parameters = {"value": fit_parameters}
    simulator_available = (
        default_simulator
        if "simulator" not in raw
        else bool(raw.get("simulator"))
    )
    return ModelIR(
        name=name,
        kind=(str(raw["kind"]) if raw.get("kind") is not None else None),
        simulation_name=(
            str(raw.get("subcircuit") or raw.get("model_id") or name)
            if raw.get("subcircuit") is not None
            or raw.get("model_id") is not None
            or simulator_available
            else None
        ),
        library=(str(raw["library"]) if raw.get("library") is not None else None),
        source=(str(raw["source"]) if isinstance(raw.get("source"), str) else None),
        parameters=tuple(sorted(parameters.items())),
        fit_parameters=tuple(sorted(fit_parameters.items())),
        evidence=_evidence(raw),
        capabilities=ModelCapabilities(
            simulator=simulator_available,
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
