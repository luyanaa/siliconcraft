"""Process-side adapters for the stdcell candidate generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.process_ir import ProcessIR, load_process
from common.pcells.scmos import Profile, Technology


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
    tech: Technology
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
            logical_layers[logical] = LayerAlias(logical, physical, physical in ir.layers)
        if not logical_layers["M1"].available or not logical_layers["M2"].available:
            raise ProcessError(f"{ir.profile}: stdcell generation requires metal1 and metal2")
        return cls(root, ir, profile_data, Technology(profile_data), logical_layers)

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

    def feature(self, name: str) -> bool:
        return bool((self.ir.meta.get("features") or {}).get(name, False))

    @property
    def legal_orientations(self) -> tuple[str, ...]:
        configured = self.ir.meta.get("legal_orientations")
        if isinstance(configured, str):
            configured = (configured,)
        if configured:
            return tuple(str(value) for value in configured)
        return ("R0", "MY")

    @property
    def row_orientation_policy(self) -> dict[str, Any]:
        return {
            "mode": "alternate_rows",
            "even_row": "R0",
            "odd_row": "MY",
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


    def metal_width_um(self, logical: str) -> float:
        rule_ids = {"M1": "7.1", "M2": "9.1", "M3": "15.1"}
        logical = logical.upper()
        if logical not in rule_ids:
            raise ProcessError(f"{self.profile_name}: no standard-cell width rule for {logical}")
        physical = self.physical_layer(logical)
        return self.profile.rule_or("width", rule_ids[logical], physical, None, 3 * self.lambda_um)

    def metal_spacing_um(self, logical: str) -> float:
        rule_ids = {"M1": "7.2", "M2": "9.2", "M3": "15.2"}
        logical = logical.upper()
        if logical not in rule_ids:
            raise ProcessError(f"{self.profile_name}: no standard-cell spacing rule for {logical}")
        physical = self.physical_layer(logical)
        return self.profile.rule_or("spacing", rule_ids[logical], physical, None, 3 * self.lambda_um)

    def via_size_um(self, lower: str, upper: str) -> float:
        pair = (lower.upper(), upper.upper())
        if pair == ("M1", "M2"):
            return self.tech.via_size
        if pair == ("M2", "M3"):
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
            "legal_orientations": list(self.legal_orientations),
            "row_orientation_policy": self.row_orientation_policy,
            "native_probe_options": list(self.native_probe_options),
        }
