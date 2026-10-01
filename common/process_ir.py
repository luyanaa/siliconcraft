"""Normalized process-fragment loader.

Process profiles intentionally remain split into human-maintainable YAML
fragments.  This module is the only composition boundary: consumers receive a
single ``ProcessIR`` instead of independently loading layers, rules, devices,
models, symbols, and PEX fragments.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import yamlish  # noqa: E402


class ProcessIRError(ValueError):
    """Raised when process fragments cannot form a coherent ProcessIR."""


RULE_FAMILIES = frozenset({"scmos", "scmos_subm", "scmos_deep", "native"})

# HVCMOS is an undeclared SCMOS 7.2 option with marker layers (CVP/CVN) and
# no official rule section.  Lambda-expressed HV rules (the process-specific
# Magic scmos.tech.in AMI 1.5um 20.x set) are forbidden unless the profile
# explicitly opts in with this feature flag.
HVCMOS_LAMBDA_OVERRIDE = "hvcmosLambdaOverride"
HVCMOS_RULE_OVERRIDE = "hvcmosRuleOverride"
HVCMOS_FAMILY = "hvcmos"


def validate_hvcmos_lambda_override(
    rules_doc: dict[str, Any], meta: dict[str, Any], source: Path
) -> None:
    """Validate explicit HVCMOS rule families and the initial HV contract.

    ``family: hvcmos`` in the ordinary SCMOS rule tables remains reserved for
    the historical Magic AMI 1.5um 20.x lambda deck.  X-FAB-style voltage
    rules use the separate ``rules.hvcmos`` table and require an explicit
    ``hvcmosRuleOverride`` opt-in because their public datasheets do not
    publish a complete foundry DRC/LVS rule set.
    """
    rules = rules_doc.get("rules") or {}
    hv = [
        entry
        for group in rules.values()
        if isinstance(group, list)
        for entry in group
        if isinstance(entry, dict) and entry.get("family") == HVCMOS_FAMILY
    ]
    features = meta.get("features") or {}
    lambda_override = bool(features.get(HVCMOS_LAMBDA_OVERRIDE))
    hv_override = bool(features.get(HVCMOS_RULE_OVERRIDE))
    hvcmos = rules_doc.get("hvcmos") or {}
    if hv and not lambda_override:
        ids = ", ".join(str(entry.get("id", "?")) for entry in hv[:8])
        raise ProcessIRError(
            f"{source}: rules tagged family: {HVCMOS_FAMILY} ({ids}) are not "
            "SCMOS 7.2 lambda rules; declare "
            f"features.{HVCMOS_LAMBDA_OVERRIDE} explicitly for the historical "
            "Magic AMI 1.5um 20.x override."
        )
    if lambda_override and not hv:
        raise ProcessIRError(
            f"{source}: features.{HVCMOS_LAMBDA_OVERRIDE} is set but no "
            f"rules.yaml entry is tagged family: {HVCMOS_FAMILY}; remove the "
            "flag or mark the intended historical rules."
        )
    if hvcmos and not features.get("hvcmosAvailable"):
        raise ProcessIRError(
            f"{source}: rules.hvcmos requires features.hvcmosAvailable=true"
        )
    if hvcmos and not hv_override:
        raise ProcessIRError(
            f"{source}: rules.hvcmos is process-specific HV collateral; "
            f"declare features.{HVCMOS_RULE_OVERRIDE}=true and record its "
            "source/limitations in the profile metadata."
        )
    if hv_override and not hvcmos:
        raise ProcessIRError(
            f"{source}: features.{HVCMOS_RULE_OVERRIDE} is set but rules.hvcmos "
            "is absent; remove the flag or add the intended HV contract."
        )


def validate_rule_family(meta: dict[str, Any], source: Path) -> str:
    """Validate the normalized rule-family contract for one profile."""
    forbidden = {"submicron_rules", "deep_rules"} & set(meta)
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise ProcessIRError(
            f"{source}: legacy rule flags {names} are forbidden; use "
            "meta.rule_family"
        )
    family = meta.get("rule_family")
    if family not in RULE_FAMILIES:
        allowed = ", ".join(sorted(RULE_FAMILIES))
        raise ProcessIRError(
            f"{source}: meta.rule_family must be one of {allowed}; got {family!r}"
        )
    identifiers = (
        str(meta.get("process", "")),
        str(meta.get("mosis_code", "")),
    )
    is_deep = any("DEEP" in identifier.upper() for identifier in identifiers)
    if is_deep and family != "scmos_deep":
        raise ProcessIRError(
            f"{source}: SCMOS_DEEP process identifiers require "
            "meta.rule_family=scmos_deep"
        )
    if family == "scmos_deep" and not is_deep:
        raise ProcessIRError(
            f"{source}: meta.rule_family=scmos_deep requires a DEEP process "
            "or MOSIS identifier"
        )
    return str(family)

@dataclass(frozen=True)
class DeviceBinding:
    """Canonical device plus process-specific layout/simulation/LVS binding."""

    name: str
    canonical_variant: str
    canonical: dict[str, Any]
    layout: dict[str, Any]
    simulation: dict[str, Any]
    lvs: dict[str, Any]
    raw: dict[str, Any]

    @property
    def terminals(self) -> tuple[str, ...]:
        return tuple(self.canonical.get("terminals") or ())

    @property
    def terminal_order(self) -> tuple[str, ...]:
        return tuple(self.canonical.get("terminal_order") or self.terminals)

    @property
    def symmetry_groups(self) -> tuple[tuple[str, ...], ...]:
        groups = self.canonical.get("symmetry_groups") or []
        return tuple(tuple(group) for group in groups)
    @property
    def canonical_family(self) -> str:
        return str(self.canonical.get("canonical_family") or "mos4")

    @property
    def canonical_id(self) -> str:
        return str(self.canonical.get("canonical_id") or self.canonical_family)

    @property
    def voltage_class(self) -> str | None:
        value = self.canonical.get("voltage_class")
        return str(value) if value is not None else None

    @property
    def gate_stack(self) -> str | None:
        value = self.canonical.get("gate_stack")
        return str(value) if value is not None else None
    @property
    def oxide_class(self) -> str | None:
        value = self.canonical.get("oxide_class")
        return str(value) if value is not None else None

    @property
    def threshold_class(self) -> str | None:
        value = self.canonical.get("threshold_class")
        return str(value) if value is not None else None

    @property
    def channel_class(self) -> str | None:
        value = self.canonical.get("channel_class")
        return str(value) if value is not None else None

    @property
    def isolation(self) -> Any:
        return self.canonical.get("isolation")


    @property
    def isolation_domain(self) -> str | None:
        value = self.canonical.get("isolation_domain")
        return str(value) if value is not None else None
    @property
    def isolation_topology(self) -> Any:
        """Prefer the topology contract, with legacy well-domain fallback."""

        return self.isolation if self.isolation is not None else self.isolation_domain


    @property
    def topology(self) -> str | None:
        value = self.canonical.get("topology")
        return str(value) if value is not None else None

    @property
    def terminal_semantics(self) -> dict[str, Any]:
        value = self.canonical.get("terminal_semantics") or {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def simulation_name(self) -> str | None:
        value = self.simulation.get("name")
        return str(value) if value is not None else None

    @property
    def simulation_representation(self) -> str | None:
        value = self.simulation.get("representation")
        return str(value) if value is not None else None

    @property
    def parameter_map(self) -> dict[str, str]:
        return {
            str(source): str(target)
            for source, target in (self.simulation.get("parameter_map") or {}).items()
        }

    @property
    def lvs_class(self) -> str | None:
        value = self.lvs.get("netgen_class")
        return str(value) if value is not None else None

    @property
    def lvs_permutable(self) -> tuple[tuple[str, ...], ...]:
        groups = self.lvs.get("permutable") or []
        return tuple(tuple(group) for group in groups)


@dataclass(frozen=True)
class CollateralCapabilities:
    """Tool and collateral readiness derived from profile contracts."""

    drc: bool
    lvs: bool
    model: bool
    xschem: bool
    pcell: str | bool
    pex_topology: bool
    pex_runtime: bool
    pex_rc: str | bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "drc": self.drc,
            "lvs": self.lvs,
            "model": self.model,
            "xschem": self.xschem,
            "pcell": self.pcell,
            "pex": {
                "topology": self.pex_topology,
                "rc": self.pex_rc,
                "runtime": self.pex_runtime,
            },
        }


@dataclass(frozen=True)
class PhysicalCapabilities:
    """Physical process capabilities, separate from tool readiness."""

    values: dict[str, Any]
    legacy_features: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def enabled(self, name: str) -> bool:
        value = self.values.get(name, False)
        if isinstance(value, dict):
            if "enabled" in value:
                return bool(value["enabled"])
            state = str(value.get("state", "")).lower()
            if state:
                return state in {"supported", "partial", "enabled"}
            return bool(value)
        return bool(value)


@dataclass(frozen=True)
class ProcessIR:
    """Composed, normalized view of one profile's source fragments."""

    root: Path
    profile: str
    meta: dict[str, Any]
    layers_doc: dict[str, Any]
    rules_doc: dict[str, Any]
    devices_doc: dict[str, Any]
    canonical_doc: dict[str, Any]
    bindings_doc: dict[str, Any]
    pcells_doc: dict[str, Any]
    symbols_doc: dict[str, Any]
    symbol_netlist_doc: dict[str, Any]
    model_maturity_doc: dict[str, Any]
    model_contract_doc: dict[str, Any]
    pex_doc: dict[str, Any]
    characterization_doc: dict[str, Any]
    oracle_overlay_doc: dict[str, Any]
    xschem_smoke_doc: dict[str, Any]
    cells_doc: dict[str, Any]
    support_cells_doc: dict[str, Any]
    device_bindings: dict[str, DeviceBinding]
    physical_capabilities: PhysicalCapabilities
    collateral_capabilities: CollateralCapabilities

    @property
    def profile_dir(self) -> Path:
        return self.root / "profiles" / self.profile


    @property
    def rule_family(self) -> str:
        return str(self.meta["rule_family"])
    @property
    def lambda_um(self) -> float:
        return float(self.meta.get("lambda_um", 0.5))

    @property
    def grid_um(self) -> float:
        return float(self.meta["grid_um"])

    @property
    def layers(self) -> dict[str, dict[str, Any]]:
        return {
            entry["name"]: entry
            for entry in self.layers_doc.get("layers", [])
            if isinstance(entry, dict) and entry.get("name")
        }

    @property
    def rules(self) -> dict[str, Any]:
        return self.rules_doc.get("rules") or {}

    @property
    def devices(self) -> dict[str, Any]:
        return self.devices_doc.get("devices") or {}
    @property
    def derived_layers(self) -> dict[str, Any]:
        from common.recognition import parse_derived_layers

        document = {
            "derived_layers": {
                **(self.layers_doc.get("derived_layers") or {}),
                **(self.devices_doc.get("derived_layers") or {}),
            }
        }
        return parse_derived_layers(document)
    @property
    def stack_v2(self) -> dict[str, Any]:
        """Return the optional cross-section contract without fabricating data."""

        value = self.layers_doc.get("stack_v2")
        return dict(value) if isinstance(value, dict) else {}


    @property
    def scmos_extensions(self) -> dict[str, dict[str, Any]]:
        from common.scmos_extensions import extension_statuses

        return extension_statuses(self)

    @property
    def pcells(self) -> dict[str, Any]:
        return self.pcells_doc.get("pcells") or {}

    @property
    def symbols(self) -> dict[str, Any]:
        return self.symbols_doc.get("symbols") or {}
    @property
    def symbol_netlist(self) -> dict[str, Any]:
        return self.symbol_netlist_doc.get("symbols") or {}

    @property
    def pex_profiles(self) -> dict[str, Any]:
        return self.pex_doc.get("profiles") or {}

    @property
    def model_parameters(self) -> dict[str, Any]:
        return self.model_maturity_doc.get("models") or {}
    @property
    def models_ir(self) -> tuple[Any, ...]:
        from common.devices.models import model_irs

        return model_irs(self)

    def model_ir(self, name: str) -> Any:
        from common.devices.models import model_ir

        return model_ir(self, name)
    @property
    def parasitic_ownership(self) -> dict[str, str]:
        flow = self.pex_doc.get("flow") or {}
        ownership = flow.get("parasitic_ownership")
        if isinstance(ownership, dict):
            return {str(key): str(value) for key, value in ownership.items()}
        device = self.canonical_doc.get("device") or {}
        ownership = device.get("parasitics") or {}
        return {str(key): str(value) for key, value in ownership.items()}

    def device(self, name: str) -> DeviceBinding:
        try:
            return self.device_bindings[name]
        except KeyError as exc:
            raise ProcessIRError(
                f"{self.profile}: no canonical device binding {name!r}"
            ) from exc

    def has_capability(self, name: str) -> bool:
        value = getattr(self.collateral_capabilities, name, False)
        return bool(value)

    def has_physical_capability(self, name: str) -> bool:
        return self.physical_capabilities.enabled(name)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = yamlish.load(path.read_text())
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProcessIRError(f"{path}: expected a mapping")
    return value




def _canonical_path(root: Path, profile_dir: Path, bindings_path: Path, source: str) -> Path:
    candidates = [
        bindings_path.parent / source,
        profile_dir / source,
        root / source,
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return candidates[0].resolve()


def _device_bindings(
    canonical_doc: dict[str, Any], bindings_doc: dict[str, Any]
) -> dict[str, DeviceBinding]:
    canonical_families = canonical_doc.get("families") or {}
    default_family = str(canonical_doc.get("default_family") or "mos4")
    result: dict[str, DeviceBinding] = {}
    for name, raw in (bindings_doc.get("bindings") or {}).items():
        if not isinstance(raw, dict):
            raise ProcessIRError(f"device binding {name!r} must be a mapping")
        family_name = str(raw.get("canonical_family") or default_family)
        if canonical_families:
            family_doc = canonical_families.get(family_name)
            if not isinstance(family_doc, dict):
                raise ProcessIRError(
                    f"device binding {name!r} references unknown canonical family "
                    f"{family_name!r}"
                )
            canonical_device = family_doc.get("device") or {}
            variants = family_doc.get("variants") or {}
        else:
            # Compatibility with pre-family canonical documents.
            family_name = "mos4"
            canonical_device = canonical_doc.get("device") or {}
            variants = canonical_doc.get("variants") or {}
        variant_name = str(raw.get("canonical_variant") or name)
        variant = variants.get(variant_name)
        if not isinstance(variant, dict):
            raise ProcessIRError(
                f"device binding {name!r} references unknown canonical variant "
                f"{variant_name!r} in family {family_name!r}"
            )
        canonical = dict(canonical_device)
        canonical.update(variant)
        canonical["canonical_family"] = family_name
        canonical["canonical_id"] = str(canonical_device.get("id") or family_name)
        result[name] = DeviceBinding(
            name=name,
            canonical_variant=variant_name,
            canonical=canonical,
            layout=dict(raw.get("layout") or {}),
            simulation=dict(raw.get("simulation") or {}),
            lvs=dict(raw.get("lvs") or {}),
            raw=raw,
        )
    return result


def _physical_capabilities(
    meta: dict[str, Any],
    layers_doc: dict[str, Any],
) -> PhysicalCapabilities:
    features = {
        str(key): bool(value)
        for key, value in (meta.get("features") or {}).items()
        if isinstance(value, bool)
    }
    layer_names = {
        str(entry.get("name"))
        for entry in layers_doc.get("layers", [])
        if isinstance(entry, dict) and entry.get("name")
    }

    def feature(*names: str) -> bool:
        return any(features.get(name, False) for name in names)

    deep_nwell = feature("deepNwellAvailable", "deep_nwellAvailable")
    twin_well = feature("twinWellAvailable", "twin_wellAvailable")
    inferred: dict[str, Any] = {
        "cmos": {"enabled": {"active", "poly"} <= layer_names, "source": "layer_vocabulary"},
        "multiple_oxide": feature(
            "multipleOxideAvailable", "thickOxideAvailable", "extraThickOxideAvailable"
        ),
        "deep_nwell": deep_nwell,
        "bipolar": feature("bipolarAvailable", "bjtAvailable", "npnAvailable", "pnpAvailable"),
        "rf": feature("rfAvailable"),
        "hv": feature("hvAvailable", "hvcmosAvailable"),
        "power": feature("powerAvailable", "ldmosAvailable", "dmosAvailable"),
        "esd": feature("esdAvailable"),
        "opto": feature("optoAvailable", "photodiodeAvailable"),
        "mems": feature("memsAvailable"),
        "analog": feature(
            "analogAvailable",
            "elecAvailable",
            "highresAvailable",
            "polycapAvailable",
            "metalcapAvailable",
            "cwellAvailable",
        ),
        "passive": feature(
            "highresAvailable",
            "polycapAvailable",
            "metalcapAvailable",
            "cwellAvailable",
            "sblockAvailable",
        ),
        "isolation": {
            "legacy_well_type": meta.get("well_type"),
            "deep_nwell": deep_nwell,
            "twin_well": twin_well,
            "authority": "legacy_feature_projection",
        },
    }
    explicit = meta.get("physical_capabilities") or {}
    if not isinstance(explicit, dict):
        raise ProcessIRError("meta.physical_capabilities must be a mapping")
    for key, value in explicit.items():
        if key == "isolation" and isinstance(value, dict) and isinstance(
            inferred.get("isolation"), dict
        ):
            inferred["isolation"] = {**inferred["isolation"], **value}
        else:
            inferred[str(key)] = value
    return PhysicalCapabilities(values=inferred, legacy_features=features)


def _collateral_capabilities(
    profile_dir: Path,
    rules_doc: dict[str, Any],
    devices_doc: dict[str, Any],
    pex_doc: dict[str, Any],
    model_maturity_doc: dict[str, Any],
    model_contract_doc: dict[str, Any],
) -> CollateralCapabilities:
    pex_profiles = pex_doc.get("profiles") or {}
    generated_pex = any(
        isinstance(spec, dict) and spec.get("generated") is True
        for spec in pex_profiles.values()
    )
    # ``none`` may be marked generated to preserve a topology-only contract.
    # It must not promote an external/deferred profile into runtime PEX.
    runtime_pex = any(
        isinstance(spec, dict)
        and spec.get("generated") is True
        and name != "none"
        for name, spec in pex_profiles.items()
    )
    topology = pex_doc.get("topology") or {}
    pex_runtime = runtime_pex and topology.get("magic_device_class") == "mosfet"
    has_model_file = any((profile_dir / "models").glob("*.lib"))
    has_model_contract = bool(model_maturity_doc or model_contract_doc)
    r_only_profile = any(
        isinstance(spec, dict) and spec.get("extractor") == "r_only_python"
        for spec in pex_profiles.values()
    )
    rc_profile = any(
        isinstance(spec, dict)
        and (
            spec.get("magic_directives")
            or spec.get("legacy_directives")
            or spec.get("metal_sheet_resistance_ohm_sq")
            or spec.get("extractor") in {
                "r_only_python",
                "field_solver_reconstruction",
            }
        )
        for spec in pex_profiles.values()
    )
    if r_only_profile:
        pex_rc: str | bool = "public_typical_r_only"
    elif runtime_pex and rc_profile:
        pex_rc = "estimated"
    else:
        pex_rc = False
    return CollateralCapabilities(
        drc=(profile_dir / "rules.yaml").exists() and bool(rules_doc),
        lvs=(profile_dir / "devices.yaml").exists() and bool(devices_doc),
        model=has_model_file or has_model_contract,
        xschem=(profile_dir / "symbols.yaml").exists()
        and (profile_dir / "xschem_smoke.yaml").exists(),
        pcell=("partial" if (profile_dir / "pcells.yaml").exists() else False),
        pex_topology=(profile_dir / "pex" / "manifest.yaml").exists()
        and generated_pex,
        pex_runtime=pex_runtime,
        pex_rc=pex_rc,
    )


def _merge_canonical_catalog(
    canonical_doc: dict[str, Any],
    catalog_doc: dict[str, Any],
) -> dict[str, Any]:
    """Add shared family vocabulary without overriding profile source data."""

    if not catalog_doc:
        return canonical_doc
    merged = dict(canonical_doc)
    catalog_families = catalog_doc.get("families") or {}
    source_families = canonical_doc.get("families") or {}
    if isinstance(catalog_families, dict) and isinstance(source_families, dict):
        merged["families"] = {**catalog_families, **source_families}
    return merged


def load_process(profile: str | Path, root: Path | None = None) -> ProcessIR:
    """Load all profile fragments into one normalized ProcessIR."""

    repo_root = Path(root or ROOT).resolve()
    profile_dir = (
        Path(profile).resolve()
        if isinstance(profile, Path)
        else (repo_root / "profiles" / profile).resolve()
    )
    if not profile_dir.is_dir():
        raise ProcessIRError(f"profile directory not found: {profile_dir}")
    profile_name = profile_dir.name
    layers_path = profile_dir / "layers.yaml"
    if not layers_path.exists():
        raise ProcessIRError(f"{profile_dir}: layers.yaml is required")

    layers_doc = _load(layers_path)
    rules_doc = _load(profile_dir / "rules.yaml")
    devices_path = profile_dir / "devices.yaml"
    devices_doc = _load(devices_path)
    bindings_path = profile_dir / "devices" / "bindings.yaml"
    bindings_doc = _load(bindings_path)
    canonical_source = bindings_doc.get("canonical_source")
    if not canonical_source:
        canonical_source = devices_doc.get("canonical_source")
    canonical_doc = (
        _load(_canonical_path(repo_root, profile_dir, bindings_path, str(canonical_source)))
        if canonical_source
        else {}
    )
    canonical_doc = _merge_canonical_catalog(
        canonical_doc,
        _load(repo_root / "common" / "devices" / "canonical" / "families.yaml"),
    )
    pex_doc = _load(profile_dir / "pex" / "manifest.yaml")
    model_maturity_doc = _load(profile_dir / "model_maturity.yaml")
    model_contract_doc = _load(profile_dir / "model_contract.yaml")
    characterization_doc = _load(profile_dir / "characterization.yaml")
    oracle_overlay_doc = _load(profile_dir / "oracle_overlay.yaml")
    symbols_doc = _load(profile_dir / "symbols.yaml")
    symbol_netlist_doc = _load(profile_dir / "devices" / "symbol_netlist.yaml")
    pcells_doc = _load(profile_dir / "pcells.yaml")
    xschem_smoke_doc = _load(profile_dir / "xschem_smoke.yaml")
    cells_doc = _load(profile_dir / "cells.yaml")
    support_cells_doc = _load(profile_dir / "support_cells.yaml")

    meta = layers_doc.get("meta")
    if not isinstance(meta, dict):
        raise ProcessIRError(f"{layers_path}: missing meta mapping")
    if meta.get("name") and str(meta["name"]) != profile_name:
        raise ProcessIRError(
            f"{layers_path}: meta.name={meta['name']!r} does not match "
            f"profile directory {profile_name!r}"
        )
    validate_rule_family(meta, layers_path)
    validate_hvcmos_lambda_override(rules_doc, meta, profile_dir / "rules.yaml")

    return ProcessIR(
        root=repo_root,
        profile=profile_name,
        meta=meta,
        layers_doc=layers_doc,
        rules_doc=rules_doc,
        devices_doc=devices_doc,
        canonical_doc=canonical_doc,
        bindings_doc=bindings_doc,
        pcells_doc=pcells_doc,
        symbols_doc=symbols_doc,
        symbol_netlist_doc=symbol_netlist_doc,
        model_maturity_doc=model_maturity_doc,
        model_contract_doc=model_contract_doc,
        pex_doc=pex_doc,
        characterization_doc=characterization_doc,
        oracle_overlay_doc=oracle_overlay_doc,
        xschem_smoke_doc=xschem_smoke_doc,
        cells_doc=cells_doc,
        support_cells_doc=support_cells_doc,
        device_bindings=_device_bindings(canonical_doc, bindings_doc),
        physical_capabilities=_physical_capabilities(meta, layers_doc),
        collateral_capabilities=_collateral_capabilities(
            profile_dir,
            rules_doc,
            devices_doc,
            pex_doc,
            model_maturity_doc,
            model_contract_doc,
        ),
    )


def profile_names(root: Path | None = None) -> tuple[str, ...]:
    """Return every profile with a valid layers fragment, sorted by name."""

    profiles_root = Path(root or ROOT) / "profiles"
    return tuple(
        path.name
        for path in sorted(profiles_root.iterdir())
        if path.is_dir() and (path / "layers.yaml").exists()
    )
