"""Manifest-driven comparison of SiliconCraft device IR with external oracles.

The harness intentionally contains no GF180MCU or SG13G2 process facts.  An
operator provisions official PCell/test-GDS/LVS outputs in an external root;
this module validates the artifact provenance and compares its observations to
canonical expectations declared by that artifact.
"""

import os
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import yamlish


class OracleError(ValueError):
    """Raised for malformed or non-conforming external oracle artifacts."""


class OracleUnavailable(FileNotFoundError):
    """Raised when an external oracle root was not provisioned."""


@dataclass(frozen=True)
class OracleSpec:
    name: str
    root_env: str
    manifest_name: str


@dataclass(frozen=True)
class OracleReport:
    oracle: str
    source: dict[str, Any]
    cases: tuple[str, ...]


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise OracleUnavailable(f"oracle artifact is missing: {path}")
    value = yamlish.load(path.read_text())
    if not isinstance(value, dict):
        raise OracleError(f"{path}: expected a mapping")
    return value


def _strings(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise OracleError(f"{context} must be a non-empty list")
    result = tuple(str(item) for item in value)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise OracleError(f"{context} must contain unique non-empty strings")
    return result


def _case_expectation(case: dict[str, Any], context: str) -> dict[str, Any]:
    case_id = case.get("id")
    family = case.get("canonical_family")
    if not isinstance(case_id, str) or not case_id:
        raise OracleError(f"{context}.id must be a non-empty string")
    if not isinstance(family, str) or not family:
        raise OracleError(f"{context}.canonical_family must be a non-empty string")
    terminals = _strings(case.get("terminals"), f"{context}.terminals")
    order = _strings(case.get("terminal_order") or terminals, f"{context}.terminal_order")
    if set(order) != set(terminals):
        raise OracleError(f"{context}.terminal_order must cover exactly terminals")
    expectation = {
        "id": case_id,
        "canonical_family": family,
        "terminals": terminals,
        "terminal_order": order,
    }
    for key in ("terminal_map", "attributes", "geometry"):
        if key in case:
            if not isinstance(case[key], dict):
                raise OracleError(f"{context}.{key} must be a mapping")
            expectation[key] = dict(case[key])
    return expectation


def _compare_mapping(
    expected: dict[str, Any], actual: dict[str, Any], key: str, errors: list[str], context: str
) -> None:
    for name, value in expected.items():
        if actual.get(name) != value:
            errors.append(
                f"{context}.{key}.{name}: expected {value!r}, got {actual.get(name)!r}"
            )


def compare_case(expectation: dict[str, Any], observation: dict[str, Any]) -> tuple[str, ...]:
    """Compare one official observation without interpreting process geometry."""
    context = f"case {expectation['id']!r}"
    errors: list[str] = []
    if not isinstance(observation, dict):
        return (f"{context}: observation must be a mapping",)
    for key in ("canonical_family", "terminals", "terminal_order"):
        expected = expectation[key]
        actual = observation.get(key)
        if key == "terminals":
            try:
                actual = _strings(actual, f"{context}.{key}")
            except OracleError as exc:
                errors.append(str(exc))
                continue
            if set(actual) != set(expected):
                errors.append(f"{context}.terminals: expected {expected!r}, got {actual!r}")
        elif key == "terminal_order":
            if actual is None:
                actual = expected
            try:
                actual = _strings(actual, f"{context}.{key}")
            except OracleError as exc:
                errors.append(str(exc))
                continue
            if actual != expected:
                errors.append(f"{context}.terminal_order: expected {expected!r}, got {actual!r}")
        elif actual != expected:
            errors.append(f"{context}.{key}: expected {expected!r}, got {actual!r}")
    for key in ("terminal_map", "attributes", "geometry"):
        if key in expectation:
            actual = observation.get(key)
            if not isinstance(actual, dict):
                errors.append(f"{context}.{key}: observation must be a mapping")
                continue
            _compare_mapping(expectation[key], actual, key, errors, context)
    return tuple(errors)


class ExternalDeviceOracle:
    """Load and validate one externally provisioned device-oracle root."""

    def __init__(self, spec: OracleSpec, root: Path | None = None) -> None:
        self.spec = spec
        configured = root or (
            Path(os.environ[self.spec.root_env])
            if os.environ.get(self.spec.root_env)
            else None
        )
        if configured is None:
            raise OracleUnavailable(
                f"{self.spec.name}: set {self.spec.root_env} to an official oracle artifact root"
            )
        self.root = configured.resolve()

    def run(self) -> OracleReport:
        manifest_path = self.root / self.spec.manifest_name
        manifest = _load(manifest_path)
        if manifest.get("oracle") != self.spec.name:
            raise OracleError(
                f"{manifest_path}: oracle must be {self.spec.name!r}"
            )
        source = manifest.get("source")
        if not isinstance(source, dict) or source.get("kind") != "external":
            raise OracleError(
                f"{manifest_path}: source.kind=external and official provenance are required"
            )
        if not source.get("artifact") or not source.get("revision"):
            raise OracleError(
                f"{manifest_path}: source.artifact and source.revision are required"
            )
        cases = manifest.get("cases")
        if not isinstance(cases, list) or not cases:
            raise OracleError(f"{manifest_path}: cases must be a non-empty list")
        expectations = {}
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise OracleError(f"{manifest_path}: cases[{index}] must be a mapping")
            expectation = _case_expectation(case, f"{manifest_path}: cases[{index}]")
            if expectation["id"] in expectations:
                raise OracleError(f"{manifest_path}: duplicate case id {expectation['id']!r}")
            expectations[expectation["id"]] = expectation
        observation_path = self.root / str(manifest.get("observations", "observations.yaml"))
        observations_doc = _load(observation_path)
        observations = observations_doc.get("observations")
        if not isinstance(observations, dict):
            raise OracleError(f"{observation_path}: observations must be a mapping")
        errors: list[str] = []
        for case_id, expectation in expectations.items():
            if case_id not in observations:
                errors.append(f"case {case_id!r}: observation is missing")
                continue
            errors.extend(compare_case(expectation, observations[case_id]))
        unexpected = sorted(set(observations) - set(expectations))
        errors.extend(f"unexpected observation {case_id!r}" for case_id in unexpected)
        if errors:
            raise OracleError("\n".join(errors))
        return OracleReport(
            oracle=self.spec.name,
            source=dict(source),
            cases=tuple(expectations),
        )
