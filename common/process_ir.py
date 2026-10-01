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
    def canonical_terminal_order(self) -> tuple[str, ...]:
        return self.terminal_order

    @property
    def terminal_maps(self) -> dict[str, dict[str, Any]]:
        value = self.raw.get("terminal_maps") or {}
        if not isinstance(value, dict):
            raise ProcessIRError(f"{self.name}: terminal_maps must be a mapping")
        maps = {}
        for domain, spec in value.items():
            if not isinstance(spec, dict):
                raise ProcessIRError(
                    f"{self.name}: terminal_maps.{domain} must be a mapping"
                )
            maps[str(domain)] = dict(spec)
        for domain in ("simulation", "lvs"):
            backend = self.raw.get(domain)
            if not isinstance(backend, dict):
                continue
            inline = {}
            if "terminal_map" in backend:
                terminal_map = backend["terminal_map"]
                if not isinstance(terminal_map, dict):
                    raise ProcessIRError(
                        f"{self.name}: {domain}.terminal_map must be a mapping"
                    )
                if set(terminal_map) & {
                    "map",
                    "canonical_to_backend",
                    "order",
                    "terminal_order",
                }:
                    inline.update(terminal_map)
                else:
                    inline["map"] = terminal_map
            if "canonical_to_backend" in backend:
                inline["canonical_to_backend"] = backend["canonical_to_backend"]
            if "terminal_order" in backend:
                inline["order"] = backend["terminal_order"]
            if inline:
                base = maps.get(domain) or {}
                if not isinstance(base, dict):
                    raise ProcessIRError(
                        f"{self.name}: terminal_maps.{domain} must be a mapping"
                    )
                maps[domain] = {**inline, **base}
        return maps

    def _terminal_spec(self, domain: str) -> dict[str, Any]:
        value = self.terminal_maps.get(domain) or {}
        if not isinstance(value, dict):
            return {}
        return value

    def terminal_map(self, domain: str) -> dict[str, str]:
        spec = self._terminal_spec(domain)
        mapping = spec.get("map") or spec.get("canonical_to_backend") or {}
        if not isinstance(mapping, dict):
            return {}
        return {str(source): str(target) for source, target in mapping.items()}

    def backend_terminal_order(self, domain: str) -> tuple[str, ...]:
        spec = self._terminal_spec(domain)
        order = spec.get("order") or spec.get("terminal_order")
        if order is not None:
            return tuple(str(item) for item in order)
        mapping = self.terminal_map(domain)
        if mapping:
            return tuple(mapping.get(name, name) for name in self.canonical_terminal_order)
        return self.canonical_terminal_order

    @property
    def simulation_terminal_order(self) -> tuple[str, ...]:
        return self.backend_terminal_order("simulation")

    @property
    def lvs_terminal_order(self) -> tuple[str, ...]:
        return self.backend_terminal_order("lvs")

    @property
    def simulation_terminal_map(self) -> dict[str, str]:
        return self.terminal_map("simulation")

    @property
    def lvs_terminal_map(self) -> dict[str, str]:
        return self.terminal_map("lvs")

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
    def canonical_attributes(self) -> dict[str, Any]:
        declared = self.canonical.get("attributes") or {}
        if not isinstance(declared, dict):
            return {}
        return {
            str(name): self.canonical[name]
            for name in declared
            if name in self.canonical
        }

    @property
    def geometry(self) -> dict[str, Any]:
        value = self.canonical.get("geometry") or {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def geometry_mode(self) -> str | None:
        value = self.geometry.get("mode")
        return str(value) if value is not None else None


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
        value = self.simulation.get("parameter_map") or {}
        if not isinstance(value, dict):
            raise ProcessIRError(f"{self.name}: simulation.parameter_map must be a mapping")
        return {str(source): str(target) for source, target in value.items()}

    @property
    def parameter_transforms(self) -> tuple[dict[str, Any], ...]:
        value = self.simulation.get("parameter_transforms") or ()
        if not isinstance(value, (list, tuple)):
            raise ProcessIRError(
                f"{self.name}: simulation.parameter_transforms must be a list"
            )
        transforms = []
        for transform in value:
            if not isinstance(transform, dict):
                raise ProcessIRError(
                    f"{self.name}: parameter transforms must be mappings"
                )
            transforms.append(dict(transform))
        return tuple(transforms)
    @property
    def lvs_parameter_transforms(self) -> tuple[dict[str, Any], ...]:
        value = self.lvs.get("parameter_transforms") or ()
        if not isinstance(value, (list, tuple)):
            raise ProcessIRError(
                f"{self.name}: lvs.parameter_transforms must be a list"
            )
        transforms = []
        for transform in value:
            if not isinstance(transform, dict):
                raise ProcessIRError(
                    f"{self.name}: LVS parameter transforms must be mappings"
                )
            transforms.append(dict(transform))
        return tuple(transforms)

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
    canonical_catalog_doc: dict[str, Any]
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
    def device_inventory(self) -> dict[str, Any]:
        value = self.devices_doc.get("devices") or {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def devices(self) -> dict[str, Any]:
        """Compatibility alias for the legacy grouped inventory."""
        return self.device_inventory

    @property
    def canonical_catalog(self) -> dict[str, Any]:
        return dict(self.canonical_catalog_doc)

    @property
    def bound_device_families(self) -> frozenset[str]:
        return frozenset(
            binding.canonical_family for binding in self.device_bindings.values()
        )
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


def _terminal_sequence(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ProcessIRError(f"{context} must be a non-empty terminal list")
    terminals = tuple(str(item) for item in value)
    if any(not item for item in terminals):
        raise ProcessIRError(f"{context} contains an empty terminal name")
    if len(set(terminals)) != len(terminals):
        raise ProcessIRError(f"{context} contains duplicate terminals")
    return terminals


def _validate_geometry_contract(
    geometry: Any, context: str
) -> None:
    if geometry is None:
        return
    if not isinstance(geometry, dict):
        raise ProcessIRError(f"{context}.geometry must be a mapping")
    mode = geometry.get("mode")
    if mode is None:
        return
    allowed = {"fixed", "scalable", "enumerated", "derived"}
    if mode not in allowed:
        raise ProcessIRError(
            f"{context}.geometry.mode must be one of {sorted(allowed)}, got {mode!r}"
        )
    if mode == "enumerated" and not isinstance(
        geometry.get("legal_values"), (list, tuple, dict)
    ):
        raise ProcessIRError(
            f"{context}.geometry.mode=enumerated requires legal_values"
        )
    if mode == "derived" and (
        not isinstance(geometry.get("derive"), str)
        or not geometry["derive"].strip()
    ):
        raise ProcessIRError(
            f"{context}.geometry.mode=derived requires a non-empty derive expression"
        )


def _validate_terminal_maps(
    raw: dict[str, Any], canonical: dict[str, Any], context: str
) -> None:
    terminals = _terminal_sequence(canonical.get("terminals"), f"{context}.terminals")
    canonical_order = _terminal_sequence(
        canonical.get("terminal_order") or terminals,
        f"{context}.terminal_order",
    )
    if set(canonical_order) != set(terminals):
        raise ProcessIRError(
            f"{context}.terminal_order must contain exactly the canonical terminals"
        )
    raw_maps = raw.get("terminal_maps") or {}
    if not isinstance(raw_maps, dict):
        raise ProcessIRError(f"{context}.terminal_maps must be a mapping")
    maps = dict(raw_maps)
    for domain in ("simulation", "lvs"):
        backend = raw.get(domain)
        if not isinstance(backend, dict):
            continue
        inline = {}
        if "terminal_map" in backend:
            terminal_map = backend["terminal_map"]
            if not isinstance(terminal_map, dict):
                raise ProcessIRError(
                    f"{context}.terminal_maps.{domain}.terminal_map must be a mapping"
                )
            if set(terminal_map) & {
                "map",
                "canonical_to_backend",
                "order",
                "terminal_order",
            }:
                inline.update(terminal_map)
            else:
                inline["map"] = terminal_map
        if "canonical_to_backend" in backend:
            inline["canonical_to_backend"] = backend["canonical_to_backend"]
        if "terminal_order" in backend:
            inline["order"] = backend["terminal_order"]
        if inline:
            base = maps.get(domain) or {}
            if not isinstance(base, dict):
                raise ProcessIRError(
                    f"{context}.terminal_maps.{domain} must be a mapping"
                )
            maps[domain] = {**inline, **base}
    for domain, spec in maps.items():
        if domain not in {"simulation", "lvs"}:
            raise ProcessIRError(
                f"{context}.terminal_maps has unsupported domain {domain!r}"
            )
        if not isinstance(spec, dict):
            raise ProcessIRError(
                f"{context}.terminal_maps.{domain} must be a mapping"
            )
        mapping = spec.get("map") or spec.get("canonical_to_backend") or {}
        if not isinstance(mapping, dict):
            raise ProcessIRError(
                f"{context}.terminal_maps.{domain}.map must be a mapping"
            )
        if set(mapping) - set(terminals):
            unknown = sorted(set(mapping) - set(terminals))
            raise ProcessIRError(
                f"{context}.terminal_maps.{domain} has unknown canonical terminals "
                f"{unknown}"
            )
        if mapping and set(mapping) != set(terminals):
            missing = sorted(set(terminals) - set(mapping))
            raise ProcessIRError(
                f"{context}.terminal_maps.{domain}.map must cover all canonical "
                f"terminals; missing {missing}"
            )
        mapped = tuple(str(value) for value in mapping.values())
        if len(set(mapped)) != len(mapped):
            raise ProcessIRError(
                f"{context}.terminal_maps.{domain}.map has duplicate backend terminals"
            )
        order = spec.get("order") or spec.get("terminal_order")
        if order is not None:
            backend_order = _terminal_sequence(
                order, f"{context}.terminal_maps.{domain}.order"
            )
            expected = set(mapping.values()) if mapping else set(terminals)
            if set(backend_order) != expected:
                raise ProcessIRError(
                    f"{context}.terminal_maps.{domain}.order does not match its map"
                )


def _canonical_attribute_overrides(
    raw: dict[str, Any], canonical_device: dict[str, Any], context: str
) -> dict[str, Any]:
    overrides = raw.get("canonical_attributes")
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise ProcessIRError(f"{context}.canonical_attributes must be a mapping")
    declared = canonical_device.get("attributes") or {}
    if not isinstance(declared, dict):
        raise ProcessIRError(
            f"{context}: canonical family attributes must be a mapping"
        )
    unknown = sorted(set(overrides) - set(declared))
    if unknown:
        raise ProcessIRError(
            f"{context}.canonical_attributes contains undeclared attributes "
            f"{unknown}"
        )
    return {str(key): value for key, value in overrides.items()}


def _device_bindings(
    canonical_doc: dict[str, Any],
    bindings_doc: dict[str, Any],
    catalog_doc: dict[str, Any] | None = None,
) -> dict[str, DeviceBinding]:
    source_families = canonical_doc.get("families") or {}
    catalog_families = (catalog_doc or {}).get("families") or {}
    if not isinstance(source_families, dict) or not isinstance(catalog_families, dict):
        raise ProcessIRError("canonical family documents must contain mapping families")
    canonical_families = {**catalog_families, **source_families}
    default_family = str(
        canonical_doc.get("default_family")
        or (catalog_doc or {}).get("default_family")
        or "mos4"
    )
    result: dict[str, DeviceBinding] = {}
    for name, raw in (bindings_doc.get("bindings") or {}).items():
        if not isinstance(raw, dict):
            raise ProcessIRError(f"device binding {name!r} must be a mapping")
        context = f"device binding {name!r}"
        family_name = str(raw.get("canonical_family") or default_family)
        if canonical_families:
            family_doc = canonical_families.get(family_name)
            if not isinstance(family_doc, dict):
                raise ProcessIRError(
                    f"{context} references unknown canonical family {family_name!r}"
                )
            canonical_device = family_doc.get("device") or {}
            variants = family_doc.get("variants") or {}
        else:
            # Compatibility with pre-family canonical documents.
            family_name = "mos4"
            canonical_device = canonical_doc.get("device") or {}
            variants = canonical_doc.get("variants") or {}
        if not isinstance(canonical_device, dict) or not isinstance(variants, dict):
            raise ProcessIRError(f"{context} has malformed canonical family {family_name!r}")
        variant_name = str(raw.get("canonical_variant") or name)
        variant = variants.get(variant_name)
        if not isinstance(variant, dict):
            raise ProcessIRError(
                f"{context} references unknown canonical variant {variant_name!r} "
                f"in family {family_name!r}"
            )
        canonical = dict(canonical_device)
        canonical.update(variant)
        canonical.update(
            _canonical_attribute_overrides(raw, canonical_device, context)
        )
        canonical["canonical_family"] = family_name
        canonical["canonical_id"] = str(canonical.get("id") or family_name)
        _validate_geometry_contract(canonical.get("geometry"), context)
        _validate_terminal_maps(raw, canonical, context)
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
    device_bindings: dict[str, DeviceBinding],
    devices_doc: dict[str, Any],
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
    bound_families = {
        binding.canonical_family for binding in device_bindings.values()
    }
    inventory_kinds: set[str] = set()
    inventory = devices_doc.get("devices") or {}
    if isinstance(inventory, dict):
        for entries in inventory.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("kind") is not None:
                    inventory_kinds.add(str(entry["kind"]))

    def feature(*names: str) -> bool:
        return any(features.get(name, False) for name in names)

    deep_nwell = feature("deepNwellAvailable", "deep_nwellAvailable")
    twin_well = feature("twinWellAvailable", "twin_wellAvailable")
    mos_bound = bool(
        bound_families & {"mos4", "asymmetric_mos4", "rf_mos4"}
    ) or bool(inventory_kinds & {"mos", "mos4", "soi_mos", "rf_mos4"})
    bipolar_bound = bool(bound_families & {"bjt", "hbt"}) or bool(
        inventory_kinds & {"bjt", "bjt3", "hbt", "hbt3", "npn", "pnp"}
    )
    rf_bound = "rf_mos4" in bound_families or "rf_mos4" in inventory_kinds
    power_bound = "asymmetric_mos4" in bound_families or any(
        binding.topology == "asymmetric_drift"
        for binding in device_bindings.values()
    )
    esd_bound = "esd" in bound_families or bool(
        inventory_kinds & {"esd", "esd2", "esd_device"}
    )
    isolation_domains = sorted(
        {
            binding.isolation_domain
            for binding in device_bindings.values()
            if binding.isolation_domain
            and binding.isolation_domain not in {"bulk", "none", "None"}
        }
    )
    cmos_enabled = mos_bound or ({"active", "poly"} <= layer_names)
    cmos_source = (
        "effective_bindings"
        if mos_bound
        else "device_inventory"
        if inventory_kinds & {"mos", "mos4", "soi_mos", "rf_mos4"}
        else "layer_vocabulary_fallback"
    )
    inferred: dict[str, Any] = {
        "cmos": {"enabled": cmos_enabled, "source": cmos_source},
        "multiple_oxide": feature(
            "multipleOxideAvailable",
            "thickOxideAvailable",
            "extraThickOxideAvailable",
        ),
        "deep_nwell": deep_nwell,
        "bipolar": feature(
            "bipolarAvailable", "bjtAvailable", "npnAvailable", "pnpAvailable"
        )
        or bipolar_bound,
        "rf": feature("rfAvailable") or rf_bound,
        "hv": feature("hvAvailable", "hvcmosAvailable")
        or any(binding.voltage_class == "hv" for binding in device_bindings.values()),
        "power": feature("powerAvailable", "ldmosAvailable", "dmosAvailable")
        or power_bound,
        "esd": feature("esdAvailable") or esd_bound,
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
        "well_topology": {
            "enabled": meta.get("well_type") in {"n", "p", "e"},
            "legacy_well_type": meta.get("well_type"),
            "authority": "legacy_well_type",
        },
        "advanced_isolation": {
            "enabled": bool(deep_nwell or twin_well or isolation_domains),
            "deep_nwell": deep_nwell,
            "twin_well": twin_well,
            "domains": isolation_domains,
            "authority": (
                "effective_bindings"
                if isolation_domains
                else "feature_projection"
            ),
        },
    }
    # ``isolation`` remains a compatibility key, but it now means advanced
    # isolation only; legacy well topology is available separately.
    inferred["isolation"] = dict(inferred["advanced_isolation"])
    explicit = meta.get("physical_capabilities") or {}
    if not isinstance(explicit, dict):
        raise ProcessIRError("meta.physical_capabilities must be a mapping")
    legacy_isolation = explicit.get("isolation")
    if isinstance(legacy_isolation, dict):
        legacy_well_type = legacy_isolation.get("legacy_well_type")
        if legacy_well_type is not None:
            inferred["well_topology"] = {
                **inferred["well_topology"],
                "legacy_well_type": legacy_well_type,
                "enabled": True,
            }
        inferred["advanced_isolation"] = {
            **inferred["advanced_isolation"],
            **{
                key: value
                for key, value in legacy_isolation.items()
                if key != "legacy_well_type"
            },
        }
    elif legacy_isolation is not None:
        inferred["advanced_isolation"] = legacy_isolation
    for key, value in explicit.items():
        if key == "isolation":
            continue
        if key in {"well_topology", "advanced_isolation"} and isinstance(
            value, dict
        ) and isinstance(inferred.get(key), dict):
            inferred[key] = {**inferred[key], **value}
        else:
            inferred[str(key)] = value
    inferred["isolation"] = dict(inferred["advanced_isolation"])
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
    canonical_catalog_doc = _load(
        repo_root / "common" / "devices" / "canonical" / "families.yaml"
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

    device_bindings = _device_bindings(
        canonical_doc, bindings_doc, canonical_catalog_doc
    )
    return ProcessIR(
        root=repo_root,
        profile=profile_name,
        meta=meta,
        layers_doc=layers_doc,
        rules_doc=rules_doc,
        devices_doc=devices_doc,
        canonical_doc=canonical_doc,
        canonical_catalog_doc=canonical_catalog_doc,
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
        device_bindings=device_bindings,
        physical_capabilities=_physical_capabilities(
            meta, layers_doc, device_bindings, devices_doc
        ),
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
