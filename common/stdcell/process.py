"""Process-side adapters for the stdcell candidate generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.process_ir import ProcessIR, load_process
from common.pcells.scmos import Profile
from common.stdcell.technology import StdcellTechnology


class ProcessError(ValueError):
    """Raised when a profile cannot satisfy a stdcell geometry contract."""


@dataclass(frozen=True)
class LayerAlias:
    logical: str
    physical: str
    available: bool


@dataclass(frozen=True)
class StdcellProcess:
    """Resolved process information used without importing a layout backend."""

    root: Path
    ir: ProcessIR
    profile: Profile
    tech: StdcellTechnology
    layers_by_logical: dict[str, LayerAlias]

    @classmethod
    def load(cls, profile: str | Path, root: Path | None = None) -> "StdcellProcess":
        root = Path(root or Path(__file__).resolve().parents[2])
        ir = load_process(profile, root)
        profile_dir = ir.profile_dir
        profile_data = Profile(profile_dir)
        logical_layers: dict[str, LayerAlias] = {}
        for index in range(1, 7):
            logical = f"M{index}"
            physical = f"metal{index}"
            layer = ir.layers.get(physical)
            available = bool(layer) and bool(layer.get("available", True))
            logical_layers[logical] = LayerAlias(logical, physical, available)
        if not logical_layers["M1"].available or not logical_layers["M2"].available:
            raise ProcessError(f"{ir.profile}: stdcell generation requires metal1 and metal2")
        return cls(
            root,
            ir,
            profile_data,
            StdcellTechnology.from_profile(profile_data),
            logical_layers,
        )

    @property
    def profile_name(self) -> str:
        return self.ir.profile

    @property
    def lambda_um(self) -> float:
        return self.ir.lambda_um

    @property
    def grid_um(self) -> float:
        return self.ir.grid_um

    @property
    def lmin_um(self) -> float:
        return float(self.ir.meta.get("min_channel_um", self.tech.poly_min))

    @property
    def available_metal_count(self) -> int:
        return sum(1 for alias in self.layers_by_logical.values() if alias.available)

    @property
    def model_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for polarity, binding in (("n", "nmos_core"), ("p", "pmos_core")):
            try:
                name = self.ir.device(binding).simulation_name
            except Exception as exc:
                raise ProcessError(f"{self.profile_name}: missing {binding} device binding") from exc
            if not name:
                raise ProcessError(f"{self.profile_name}: {binding} has no simulator model name")
            names[polarity] = name
        return names

    def polarity_for_model(self, model: str) -> str:
        models = self.model_names
        for polarity, name in models.items():
            if model == name:
                return polarity
        raise ProcessError(
            f"{self.profile_name}: model {model!r} is not an active nmos/pmos binding "
            f"({models['n']!r}, {models['p']!r})"
        )

    def snap(self, value_um: float) -> float:
        return self.profile.snap(float(value_um))

    def physical_layer(self, logical: str) -> str:
        try:
            alias = self.layers_by_logical[logical.upper()]
        except KeyError as exc:
            raise ProcessError(f"{self.profile_name}: unknown logical layer {logical!r}") from exc
        if not alias.available:
            raise ProcessError(f"{self.profile_name}: {logical} maps to unavailable {alias.physical}")
        return alias.physical

    def has_layer(self, logical: str) -> bool:
        alias = self.layers_by_logical.get(logical.upper())
        return bool(alias and alias.available)

    def stdcell_layer(self, semantic: str, polarity: str | None = None) -> str:
        """Resolve a stdcell shape token, allowing native polarity layers.

        Legacy profiles use one ``ACTIVE`` token and polarity-specific
        ``NSELECT``/``PSELECT`` tokens.  Processes such as TR-1um draw N+
        and P+ active on different streams, so their profile metadata can
        override ``active_n`` and ``active_p`` without changing the planner's
        geometry contract.
        """
        configured = self.ir.meta.get("stdcell_layers") or {}
        key = str(semantic).lower()
        if polarity:
            configured_value = configured.get(f"{key}_{str(polarity).lower()}")
            if configured_value:
                return str(configured_value)
        defaults = {
            "active": "ACTIVE",
            "select": "NSELECT" if polarity == "n" else "PSELECT",
            "well": "NWELL",
        }
        try:
            return defaults[key]
        except KeyError as exc:
            raise ProcessError(
                f"{self.profile_name}: unknown stdcell semantic layer {semantic!r}"
            ) from exc

    def feature(self, name: str) -> bool:
        return bool((self.ir.meta.get("features") or {}).get(name, False))

    @property
    def stdcell_contract(self) -> dict[str, Any]:
        contract = self.ir.cells_doc.get("stdcell") or {}
        if not isinstance(contract, dict):
            raise ProcessError(f"{self.profile_name}: cells.yaml stdcell contract must be a mapping")
        return contract

    @property
    def site_height_um(self) -> float:
        value = self.stdcell_contract.get("site_height_um")
        if not isinstance(value, (int, float)) or float(value) <= 0:
            raise ProcessError(
                f"{self.profile_name}: stdcell site_height_um is required for fixed-height generation"
            )
        return self.snap(float(value))

    def row_height_um(self, polarity: str) -> float:
        values = self.stdcell_contract.get("row_heights_um") or {}
        value = values.get(polarity) if isinstance(values, dict) else None
        if not isinstance(value, (int, float)) or float(value) <= 0:
            raise ProcessError(
                f"{self.profile_name}: missing fixed {polarity} row height in cells.yaml"
            )
        return self.snap(float(value))

    def row_active_capacity_um(self, polarity: str) -> float:
        select_enc = self.tech.select_channel_enc
        capacity = self.row_height_um(polarity) - 2 * select_enc
        if polarity == "p":
            capacity = min(
                capacity,
                self.row_height_um("p") - 2 * self.tech.nwell_active_enc,
            )
        return self.snap(capacity) if capacity > 0 else 0.0

    @property
    def row_gap_um(self) -> float:
        value = self.stdcell_contract.get("row_gap_um")
        if not isinstance(value, (int, float)) or float(value) < 0:
            raise ProcessError(f"{self.profile_name}: invalid fixed row_gap_um")
        return self.snap(float(value))

    @property
    def rail_margin_um(self) -> float:
        value = self.stdcell_contract.get("rail_margin_um")
        if not isinstance(value, (int, float)) or float(value) < 0:
            raise ProcessError(f"{self.profile_name}: invalid fixed rail_margin_um")
        return self.snap(float(value))

    @property
    def tap_policy(self) -> str:
        value = self.stdcell_contract.get("tap_policy")
        if value not in {"external_tapcell", "self_tapped"}:
            raise ProcessError(
                f"{self.profile_name}: tap_policy must be external_tapcell or self_tapped"
            )
        return str(value)

    @property
    def tapcell_contract(self) -> dict[str, Any]:
        value = self.stdcell_contract.get("tapcell") or {}
        if not isinstance(value, dict):
            raise ProcessError(f"{self.profile_name}: tapcell contract must be a mapping")
        return value

    @property
    def legal_orientations(self) -> tuple[str, ...]:
        configured = (self.stdcell_contract.get("orientations") or {}).get("legal")
        if isinstance(configured, str):
            configured = (configured,)
        if configured:
            return tuple(str(value) for value in configured)
        configured = self.ir.meta.get("legal_orientations")
        if isinstance(configured, str):
            configured = (configured,)
        if configured:
            return tuple(str(value) for value in configured)
        return ("R0", "MX")

    @property
    def row_orientation_policy(self) -> dict[str, Any]:
        orientations = self.stdcell_contract.get("orientations") or {}
        return {
            "mode": "alternate_rows",
            "even_row": orientations.get("even_row", "R0"),
            "odd_row": orientations.get("odd_row", "MX"),
            "legal_orientations": list(self.legal_orientations),
            "rail_abutment": "fixed_height_continuous_vdd_vss",
        }

    @property
    def native_probe_options(self) -> tuple[str, ...]:
        configured = self.ir.meta.get("native_probe_options", ())
        if isinstance(configured, str):
            configured = (configured,)
        return tuple(str(value) for value in configured)
    def supply_contact_capacity(self, supply: str) -> float | None:
        configured = self.ir.meta.get("supply_contact_capacity") or {}
        value = configured.get(supply) if isinstance(configured, dict) else None
        if isinstance(value, (int, float)) and float(value) > 0:
            return float(value)
        for layer in self.ir.layers.values():
            electrical = layer.get("electrical") or {}
            value = electrical.get("contact_current_capacity")
            if isinstance(value, (int, float)) and float(value) > 0:
                return float(value)
        return None

    def supply_current_demand(self, supply: str) -> float | None:
        configured = self.ir.meta.get("supply_current_demand") or {}
        value = configured.get(supply) if isinstance(configured, dict) else None
        if isinstance(value, (int, float)) and float(value) >= 0:
            return float(value)
        return None


    def routing_grammar(self):
        from common.routing_grammar import RoutingGrammar, inspect_profile

        candidates = (
            self.root / "build" / "routing_grammar" / f"{self.profile_name}.json",
            self.root / "build" / "routing_grammar" / f"{self.profile_name}-native.json",
            self.root / "build" / "routing_grammar" / f"{self.profile_name}-static.json",
        )
        for path in candidates:
            if path.exists():
                return RoutingGrammar.load(path)
        return inspect_profile(self.profile_name, self.root)

    def metal_width_um(self, logical: str) -> float:
        logical = logical.upper()
        keys = {
            "M1": "metal.M1.min_width",
            "M2": "metal.M2.min_width",
            "M3": "metal.M3.min_width",
        }
        if logical not in keys:
            raise ProcessError(f"{self.profile_name}: no standard-cell width rule for {logical}")
        self.physical_layer(logical)
        return self.tech.semantic_rule(keys[logical])

    def metal_spacing_um(self, logical: str) -> float:
        logical = logical.upper()
        keys = {
            "M1": "metal.M1.min_spacing",
            "M2": "metal.M2.min_spacing",
            "M3": "metal.M3.min_spacing",
        }
        if logical not in keys:
            raise ProcessError(f"{self.profile_name}: no standard-cell spacing rule for {logical}")
        self.physical_layer(logical)
        return self.tech.semantic_rule(keys[logical])

    def via_size_um(self, lower: str, upper: str) -> float:
        pair = (lower.upper(), upper.upper())
        if pair == ("M1", "M2"):
            return self.tech.via_size
        if pair == ("M2", "M3") and self.tech.via2_size is not None:
            return self.tech.via2_size
        raise ProcessError(f"{self.profile_name}: no via sizing for {lower}/{upper}")

    def architecture_metal_limit(self, architecture: str) -> int:
        if architecture.startswith("three_metal"):
            if not self.has_layer("M3"):
                raise ProcessError(f"{self.profile_name}: {architecture} requires M3")
            return 3
        if architecture.startswith("two_metal"):
            return 2
        raise ProcessError(f"unsupported routing architecture {architecture!r}")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "process": self.ir.meta.get("process"),
            "lambda_um": self.lambda_um,
            "grid_um": self.grid_um,
            "lmin_um": self.lmin_um,
            "model_names": self.model_names,
            "layers": {
                logical: alias.physical
                for logical, alias in self.layers_by_logical.items()
                if alias.available
            },
            "site_height_um": self.site_height_um,
            "row_heights_um": {
                "n": self.row_height_um("n"),
                "p": self.row_height_um("p"),
            },
            "row_gap_um": self.row_gap_um,
            "tap_policy": self.tap_policy,
            "tapcell": self.tapcell_contract,
            "legal_orientations": list(self.legal_orientations),
            "row_orientation_policy": self.row_orientation_policy,
            "native_probe_options": list(self.native_probe_options),
        }
