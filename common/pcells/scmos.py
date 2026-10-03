"""KLayout analog PCells for siliconcraft SCMOS profiles.

The PCells emit geometry only.  They consume the profile layer map, feature
flags, and PCell parameter contract; Magic extraction is deliberately not part
of this module.

Load with KLayout's Python runner or through ``scripts/run_pcells.py``.
"""

from __future__ import annotations

import math
from pathlib import Path

from common.process_ir import load_process

try:
    import pya
except ImportError:  # pragma: no cover - exercised only outside KLayout
    pya = None

if pya is None:  # Keep profile/technology parsing importable in plain Python.
    class _PCellDeclarationHelper:
        pass

    class _Library:
        pass
else:
    _PCellDeclarationHelper = pya.PCellDeclarationHelper
    _Library = pya.Library



class ProfileError(ValueError):
    """Raised when a profile cannot satisfy a PCell contract."""


class Profile:
    """Loaded profile data plus the small geometry contract used by PCells."""

    def __init__(self, profile_dir: Path, variant: str | None = None):
        self.profile_dir = Path(profile_dir)
        self.ir = load_process(self.profile_dir, variant=variant)
        self.layers_doc = self.ir.layers_doc
        self.rules_doc = self.ir.rules_doc
        self.pcells_doc = self.ir.pcells_doc
        self.meta = self.layers_doc["meta"]
        self.features = self.meta.get("features", {})
        self.layers = {
            item["name"]: item
            for item in self.layers_doc.get("layers", [])
        }
        self.pcells = self.pcells_doc.get("pcells", {})
        self.lambda_um = float(self.meta["lambda_um"])
        self.grid_um = float(self.meta["grid_um"])
        self.rule_family = self.ir.rule_family

    def has_feature(self, name: str) -> bool:
        return bool(self.features.get(name, False))

    def layer_info(self, name: str):
        if name not in self.layers:
            raise ProfileError(f"{self.profile_dir.name}: unknown layer {name}")
        entries = self.layers[name].get("gds", [])
        if not entries:
            raise ProfileError(f"{self.profile_dir.name}: layer {name} has no GDS mapping")
        entry = entries[0]
        return pya.LayerInfo(int(entry["layer"]), int(entry["datatype"]), name)

    def snap(self, value: float) -> float:
        return round(float(value) / self.grid_um) * self.grid_um

    def _condition_atom(self, atom: str) -> bool:
        atom = atom.strip()
        if not atom:
            return True
        if atom.startswith("tech-not-in:"):
            return self.meta.get("process") not in atom.split(":", 1)[1].split("/")
        if atom.startswith("tech:"):
            return self.meta.get("process") == atom.split(":", 1)[1]
        negate = atom.startswith("not-")
        name = atom[4:] if negate else atom
        aliases = {
            "scmos": self.rule_family == "scmos",
            "scmos_subm": self.rule_family == "scmos_subm",
            "scmos_deep": self.rule_family == "scmos_deep",
            "stacked": bool(self.meta.get("stacked_vias", False)),
            "elec": self.has_feature("elecAvailable"),
            "highres": self.has_feature("highresAvailable"),
            "metal3": self.has_feature("metal3Available"),
            "metal4": self.has_feature("metal4Available"),
            "metal5": self.has_feature("metal5Available"),
            "metal6": self.has_feature("metal6Available"),
            "cwell": self.has_feature("cwellAvailable"),
            "sblock": self.has_feature("sblockAvailable"),
            "polycap": self.has_feature("polycapAvailable"),
            "ccd": self.has_feature("ccdAvailable"),
            "npn": self.has_feature("npnAvailable"),
            "hv": self.has_feature("hvAvailable"),
            "scnpc": self.has_feature("scnpcAvailable"),
            "mems": self.has_feature("memsAvailable"),
        }
        value = aliases.get(name, False)
        return not value if negate else value

    def _condition_matches(self, condition) -> bool:
        if not condition:
            return True
        # Commas are AND; pipes are OR.  This mirrors rules.yaml semantics.
        return all(
            any(self._condition_atom(option) for option in group.split("|"))
            for group in str(condition).split(",")
        )

    def rule_value(self, group: str, rule_id: str, layer: str, layer2=None):
        rules = self.rules_doc.get("rules", {}).get(group, [])
        candidates = []
        for rule in rules:
            if str(rule.get("id")) != str(rule_id):
                continue
            if rule.get("layer") != layer:
                continue
            if layer2 is not None and rule.get("layer2") != layer2:
                continue
            if layer2 is None and rule.get("layer2") is not None:
                continue
            if self._condition_matches(rule.get("condition")):
                candidates.append(float(rule["value_um"]))
        if not candidates:
            raise ProfileError(
                f"{self.profile_dir.name}: no active {group} rule {rule_id} "
                f"for {layer}/{layer2 or ''}"
            )
        return candidates[0]

    def semantic_rule(self, key: str, fallback=None) -> float:
        """Resolve a consumer-facing stdcell rule through a profile adapter.

        Profile-specific ``rules.stdcell.rule_map`` entries own the mapping
        from semantic names to physical rule IDs.  ``fallback`` keeps the
        established SCMOS adapter available for profiles that predate the
        semantic map.
        """
        mapping = (self.rules_doc.get("rules", {}).get("stdcell") or {}).get(
            "rule_map", {}
        )
        spec = mapping.get(key) if isinstance(mapping, dict) else None
        if spec is not None:
            if "value_um" in spec:
                return float(spec["value_um"])
            try:
                return self.rule_value(
                    str(spec["group"]),
                    str(spec["id"]),
                    str(spec["layer"]),
                    spec.get("layer2"),
                )
            except KeyError as exc:
                raise ProfileError(
                    f"{self.profile_dir.name}: incomplete semantic stdcell rule {key}"
                ) from exc
        if fallback is None:
            raise ProfileError(
                f"{self.profile_dir.name}: no semantic stdcell rule {key}"
            )
        group, rule_id, layer, layer2 = fallback
        return self.rule_value(group, rule_id, layer, layer2)


    def validate_pcell(self, name: str, kind: str):
        spec = self.pcells.get(name)
        if spec is None:
            raise ProfileError(f"{self.profile_dir.name}: missing PCell contract {name}")
        if spec.get("kind") != kind:
            raise ProfileError(
                f"{self.profile_dir.name}: {name} is {spec.get('kind')}, expected {kind}"
            )
        return spec


class Technology:
    """AMI/SCMOS geometry constants derived from the profile and CDK rules."""

    def __init__(self, profile: Profile):
        self.profile = profile
        self.contact_size = self._rule("width", "6.1", "ca", None)
        self.contact_spacing = self._rule("spacing", "6.3", "ca", None)
        self.active_min = self._rule("width", "2.1", "active", None)
        self.poly_min = self._rule("width", "3.1", "poly", None)
        self.poly_spacing = self._rule("spacing", "3.2", "poly", None)
        self.poly_contact_spacing = self._rule(
            "spacing", "5.5.b", "cp", "poly"
        )
        self.poly_contact_enc = self._rule(
            "enclosure", "5.2.b", "poly", "cp"
        )
        self.active_contact_enc = self._rule(
            "enclosure", "6.2.b", "active", "ca"
        )
        self.select_active_enc = self._rule(
            "enclosure", "4.2", "nselect", "active"
        )
        self.select_channel_enc = max(
            self._rule("enclosure", "4.1", "nselect", "nChannel"),
            self._rule("enclosure", "4.1", "pselect", "pChannel"),
        )
        self.gate_extension = self._rule(
            "spacing", "5.4", "cp", "Gate"
        )
        self.select_contact_enc = self._rule(
            "enclosure", "4.3", "nselect", "ca"
        )
        self.metal_contact_enc = self._rule(
            "enclosure", "7.3", "metal1", "ca"
        )
        self.nwell_active_enc = self._rule(
            "spacing", "1.3", "nwell", None
        )
        self.nwell_contact_enc = self.nwell_active_enc
        self.nwell_min_width = self._rule(
            "width", "1.1", "nwell", None
        )
        self.via_size = self._rule("width", "8.1", "via", None)
        self.via_spacing = self._rule("spacing", "8.2", "via", None)
        self.via_lower_enc = self._rule(
            "enclosure", "8.3", "metal1", "via"
        )
        self.via_upper_enc = self._rule(
            "enclosure", "9.3", "metal2", "via"
        )
        self.via2_size = self._rule("width", "14.1", "via2", None)
        self.via2_spacing = self._rule("spacing", "14.2", "via2", None)
        self.via2_lower_enc = self._rule(
            "enclosure", "14.3", "metal2", "via2"
        )
        self.via2_upper_enc = self._rule(
            "enclosure", "15.3", "metal3", "via2"
        )
        self.poly_elec_enc = self._rule(
            "enclosure", "11.3", "poly", "CapacitorElec"
        )
        self.cap_elec_min = self._rule(
            "width", "11.1", "CapacitorElec", None
        )
        if profile.has_feature("metal4Available"):
            self.via3_size = self._rule("width", "28.1", "via3", None)
            self.via3_spacing = self._rule("spacing", "28.2", "via3", None)
            self.via3_lower_enc = self._rule(
                "enclosure", "28.3", "metal3", "via3"
            )
            self.via3_upper_enc = self._rule(
                "enclosure", "29.3", "metal4", "via3"
            )

    def _rule(
        self,
        group: str,
        rule_id: str,
        layer: str,
        layer2: str | None,
    ) -> float:
        return self.profile.rule_value(group, rule_id, layer, layer2)

    def snap(self, value: float) -> float:
        return self.profile.snap(value)


class _BasePCell(_PCellDeclarationHelper):
    def __init__(self, tech: Technology):
        super().__init__()
        self.tech = tech

    def _layer(self, name: str):
        return self.layout.layer(self.tech.profile.layer_info(name))

    def _db(self, value: float) -> int:
        return int(round(float(value) / self.layout.dbu))

    def _rect(self, layer: str, x1, y1, x2, y2):
        if x2 <= x1 or y2 <= y1:
            raise ProfileError(f"empty rectangle on {layer}: {(x1, y1, x2, y2)}")
        self.cell.shapes(self._layer(layer)).insert(
            pya.Box(self._db(x1), self._db(y1), self._db(x2), self._db(y2))
        )

    def _positive_int(self, name: str, value: int) -> int:
        value = int(round(value))
        if value < 1:
            raise ValueError(f"{name} must be >= 1")
        return value


class MosPCell(_BasePCell):
    def __init__(
        self,
        tech: Technology,
        polarity: str,
        pcell_name: str | None = None,
    ):
        super().__init__(tech)
        self.polarity = polarity
        self.pcell_name = pcell_name or ("nmos" if polarity == "n" else "pmos")
        self.midox = self.pcell_name in {"nmosm", "pmosm"}
        geometry = self.tech.profile.pcells[self.pcell_name].get("geometry", {})
        self.midox_enclosure_um = float(geometry.get("midox_enclosure_um", 0.6))
        self.tech.profile.validate_pcell(self.pcell_name, "mos4")
        if self.midox and not tech.profile.has_feature("midoxAvailable"):
            raise ProfileError(f"{self.pcell_name} requires midoxAvailable")
        self.param("nf", self.TypeInt, "Physical gate fingers", default=1)
        self.param("m", self.TypeInt, "Electrical multiplier", default=1)
        self.param("w_um", self.TypeDouble, "Channel width per finger (um)", default=1.5)
        self.param("l_um", self.TypeDouble, "Channel length (um)", default=0.6)
        self.param("left_contact", self.TypeBoolean, "Keep left diffusion contact", default=True)
        self.param("right_contact", self.TypeBoolean, "Keep right diffusion contact", default=True)

    def _minimum(self, name: str, fallback: float) -> float:
        params = self.tech.profile.pcells[self.pcell_name].get("parameters", {})
        return float(params.get(name, {}).get("min", fallback))

    def display_text_impl(self):
        return (
            f"{self.pcell_name}(W={self.w_um:g},L={self.l_um:g},nf={self.nf},m={self.m},"
            f"left_contact={self.left_contact},right_contact={self.right_contact})"
        )

    def coerce_parameters_impl(self):
        self.nf = max(1, int(round(self.nf)))
        self.m = max(1, int(round(self.m)))
        self.w_um = self.tech.snap(
            max(float(self.w_um), self._minimum("w_um", self.tech.active_min))
        )
        self.l_um = self.tech.snap(
            max(float(self.l_um), self._minimum("l_um", self.tech.poly_min))
        )

    def produce_impl(self):
        f = self._positive_int("nf", self.nf)
        w = self.tech.snap(
            max(float(self.w_um), self._minimum("w_um", self.tech.active_min))
        )
        l = self.tech.snap(
            max(float(self.l_um), self._minimum("l_um", self.tech.poly_min))
        )
        poly_pitch = l + self.tech.poly_spacing
        poly_edge = (
            self.tech.poly_contact_spacing
            + self.tech.contact_size
            + self.tech.active_contact_enc
        )
        active_width = 2 * poly_edge + (f - 1) * poly_pitch + l
        active_height = max(w, self.tech.active_min)
        active_left = -active_width / 2.0
        active_right = active_width / 2.0
        active_bottom = -active_height / 2.0
        active_top = active_height / 2.0

        active = "active"
        select = "nselect" if self.polarity == "n" else "pselect"
        self._rect(active, active_left, active_bottom, active_right, active_top)
        select_enc = self.tech.select_channel_enc
        self._rect(
            select,
            active_left - select_enc,
            active_bottom - select_enc,
            active_right + select_enc,
            active_top + select_enc,
        )
        if self.polarity == "p":
            well_enc = self.tech.nwell_active_enc
            well_left = active_left - well_enc
            well_right = active_right + well_enc
            well_bottom = active_bottom - well_enc
            well_top = active_top + well_enc
            well_width = well_right - well_left
            well_height = well_top - well_bottom
            if well_width < self.tech.nwell_min_width:
                extra = (self.tech.nwell_min_width - well_width) / 2.0
                well_left -= extra
                well_right += extra
            if well_height < self.tech.nwell_min_width:
                extra = (self.tech.nwell_min_width - well_height) / 2.0
                well_bottom -= extra
                well_top += extra
            self._rect("nwell", well_left, well_bottom, well_right, well_top)

        gate_extension = self.tech.gate_extension
        gate_span = (f - 1) * poly_pitch + l
        gate_left = -gate_span / 2.0
        for index in range(f):
            left = gate_left + index * poly_pitch
            self._rect(
                "poly",
                left,
                active_bottom - gate_extension,
                left + l,
                active_top + gate_extension,
            )
        if self.midox:
            self._rect(
                "midox",
                active_left - self.midox_enclosure_um,
                active_bottom - self.midox_enclosure_um,
                active_right + self.midox_enclosure_um,
                active_top + self.midox_enclosure_um,
            )

        contact_count = max(
            1,
            int(
                math.floor(
                    (active_height - 2 * self.tech.active_contact_enc + self.tech.contact_spacing)
                    / (self.tech.contact_size + self.tech.contact_spacing)
                )
            ),
        )
        contact_height = (
            contact_count * self.tech.contact_size
            + (contact_count - 1) * self.tech.contact_spacing
        )
        contact_bottom = (
            active_bottom
            + self.tech.active_contact_enc
            + (active_height - 2 * self.tech.active_contact_enc - contact_height) / 2.0
        )
        if f == 1:
            contact_xs = (
                active_left + self.tech.active_contact_enc,
                active_right - self.tech.active_contact_enc - self.tech.contact_size,
            )
        else:
            parallel_step = 2 * (
                self.tech.gate_extension / 2.0 + self.tech.poly_contact_spacing
            ) + l
            first = active_left + self.tech.active_contact_enc
            contact_xs = [
                first + index * parallel_step for index in range(f + 1)
            ]
        for index, x in enumerate(contact_xs):
            if index == 0 and not self.left_contact:
                continue
            if index == len(contact_xs) - 1 and not self.right_contact:
                continue
            for row in range(contact_count):
                y = contact_bottom + row * (self.tech.contact_size + self.tech.contact_spacing)
                self._rect("cc", x, y, x + self.tech.contact_size, y + self.tech.contact_size)
            self._rect(
                "metal1",
                x - self.tech.metal_contact_enc,
                contact_bottom - self.tech.metal_contact_enc,
                x + self.tech.contact_size + self.tech.metal_contact_enc,
                contact_bottom + contact_height + self.tech.metal_contact_enc,
            )


class ResistorPCell(_BasePCell):
    """Two-terminal C35 resistor layouts using the documented marker scheme."""

    def __init__(self, tech: Technology, name: str):
        super().__init__(tech)
        self.pcell_name = name
        self.spec = tech.profile.validate_pcell(name, "resistor")
        params = self.spec.get("parameters", {})
        self.param(
            "length_um",
            self.TypeDouble,
            "Resistor body length (um)",
            default=float(params.get("length_um", {}).get("default", 10.0)),
        )
        self.param(
            "width_um",
            self.TypeDouble,
            "Resistor body width (um)",
            default=float(params.get("width_um", {}).get("default", 1.0)),
        )

    def _effective_dimensions(self):
        length = self.tech.snap(max(float(self.length_um), self._minimum("length_um")))
        width = self.tech.snap(max(float(self.width_um), self._minimum("width_um")))
        if self.spec["material"] in {"poly2", "high_resistive_poly", "nwell"}:
            length = self.tech.snap(max(length, 5 * width))
        return length, width

    def _minimum(self, name: str) -> float:
        params = self.spec.get("parameters", {})
        return float(params.get(name, {}).get("min", 0.0))

    def _layout_value(self, name: str, fallback: float) -> float:
        return float(self.spec.get("geometry", {}).get(name, fallback))

    def display_text_impl(self):
        return f"{self.pcell_name}(L={self.length_um:g},W={self.width_um:g})"

    def coerce_parameters_impl(self):
        self.length_um, self.width_um = self._effective_dimensions()

    def produce_impl(self):
        length, width = self._effective_dimensions()
        contact = self.tech.contact_size
        contact_enc = self._layout_value("contact_enclosure_um", 0.25)
        metal_enc = self.tech.metal_contact_enc
        kind = self.spec["material"]

        if kind == "high_resistive_poly":
            terminal_width = max(width, contact + 2 * 0.6)
            terminal_length = self._layout_value("terminal_length_um", 1.6)
            gap = self._layout_value("terminal_gap_um", 0.35)
            body_length = length - 2 * gap
            if body_length <= 0:
                raise ProfileError(f"{self.pcell_name}: length is below terminal gaps")
            outer_length = body_length + 2 * (terminal_length + gap)
            left, right = -outer_length / 2.0, outer_length / 2.0
            body_left, body_right = -body_length / 2.0, body_length / 2.0
            left_terminal_right = left + terminal_length
            right_terminal_left = right - terminal_length
            self._rect(
                "elec",
                body_left,
                -width / 2,
                body_right,
                width / 2,
            )
            self._rect(
                "elec",
                left_terminal_right,
                -width / 2,
                body_left,
                width / 2,
            )
            self._rect(
                "elec",
                body_right,
                -width / 2,
                right_terminal_left,
                width / 2,
            )
            self._rect(
                "elec",
                left,
                -terminal_width / 2,
                left_terminal_right,
                terminal_width / 2,
            )
            self._rect(
                "elec",
                right_terminal_left,
                -terminal_width / 2,
                right,
                terminal_width / 2,
            )
            hres_enc = self._layout_value("hres_enclosure_um", 3.0)
            self._rect(
                "highres",
                left - hres_enc,
                -terminal_width / 2 - hres_enc,
                right + hres_enc,
                terminal_width / 2 + hres_enc,
            )
            for x1, x2 in ((left, left + terminal_length), (right - terminal_length, right)):
                self._rect(
                    "pselect",
                    x1,
                    -terminal_width / 2 - 0.6,
                    x2,
                    terminal_width / 2 + 0.6,
                )
                cx = (x1 + x2) / 2.0
                self._rect(
                    "cc",
                    cx - contact / 2,
                    -contact / 2,
                    cx + contact / 2,
                    contact / 2,
                )
                self._rect(
                    "metal1",
                    cx - contact / 2 - metal_enc,
                    -contact / 2 - metal_enc,
                    cx + contact / 2 + metal_enc,
                    contact / 2 + metal_enc,
                )
            return

        if kind == "nwell":
            terminal_length = self._layout_value("terminal_length_um", 1.2)
            terminal_width = contact + 2 * self._layout_value("contact_enclosure_um", 0.15)
            outer_length = length + 2 * terminal_length
            left, right = -outer_length / 2.0, outer_length / 2.0
            well_width = width
            well_enc = self._layout_value("well_active_enclosure_um", 0.2)
            well_left, well_right = left - well_enc, right + well_enc
            self._rect("nwell", well_left, -well_width / 2, well_right, well_width / 2)
            self._rect("tubdef", well_left, -well_width / 2, well_right, well_width / 2)
            active_enc = self._layout_value("select_enclosure_um", 0.45)
            terminals = (
                (left, left + terminal_length, True, False),
                (right - terminal_length, right, False, True),
            )
            for x1, x2, outer_left, outer_right in terminals:
                rest_left = x1 - well_enc if outer_left else x1
                rest_right = x2 + well_enc if outer_right else x2
                self._rect("restdm", rest_left, -well_width / 2, rest_right, well_width / 2)
                self._rect("active", x1, -terminal_width / 2, x2, terminal_width / 2)
                self._rect(
                    "nselect",
                    x1 - active_enc,
                    -terminal_width / 2 - active_enc,
                    x2 + active_enc,
                    terminal_width / 2 + active_enc,
                )
                cx = (x1 + x2) / 2.0
                self._rect(
                    "cc",
                    cx - contact / 2,
                    -contact / 2,
                    cx + contact / 2,
                    contact / 2,
                )
                self._rect(
                    "metal1",
                    cx - contact / 2 - metal_enc,
                    -contact / 2 - metal_enc,
                    cx + contact / 2 + metal_enc,
                    contact / 2 + metal_enc,
                )
            return

        if kind not in {"poly2", "n_diffusion", "p_diffusion"}:
            raise ProfileError(f"{self.pcell_name}: unsupported C35 resistor material {kind}")
        terminal_width = max(width, contact + 2 * contact_enc)
        terminal_length = self._layout_value("terminal_length_um", 1.2)
        outer_length = length + 2 * terminal_length
        left, right = -outer_length / 2.0, outer_length / 2.0
        material_layer = "elec" if kind == "poly2" else "active"
        self._rect(material_layer, left, -width / 2, right, width / 2)
        self._rect("res_id", left, -width / 2, right, width / 2)
        if kind == "p_diffusion":
            well_enc = self._layout_value("nwell_enclosure_um", 1.2)
            self._rect(
                "nwell",
                left - well_enc,
                -terminal_width / 2 - well_enc,
                right + well_enc,
                terminal_width / 2 + well_enc,
            )
        self._rect("restdm", left, -terminal_width / 2, left + terminal_length, terminal_width / 2)
        self._rect("restdm", right - terminal_length, -terminal_width / 2, right, terminal_width / 2)
        if kind != "poly2":
            select = "nselect" if kind == "n_diffusion" else "pselect"
            select_enc = self._layout_value("select_enclosure_um", 0.45)
            self._rect(
                select,
                left - select_enc,
                -terminal_width / 2 - select_enc,
                right + select_enc,
                terminal_width / 2 + select_enc,
            )
        for x1, x2 in ((left, left + terminal_length), (right - terminal_length, right)):
            if terminal_width > width:
                self._rect(material_layer, x1, -terminal_width / 2, x2, terminal_width / 2)
            cx = (x1 + x2) / 2.0
            self._rect(
                "cc",
                cx - contact / 2,
                -contact / 2,
                cx + contact / 2,
                contact / 2,
            )
            self._rect(
                "metal1",
                cx - contact / 2 - metal_enc,
                -contact / 2 - metal_enc,
                cx + contact / 2 + metal_enc,
                contact / 2 + metal_enc,
            )


class PiPCapPCell(_BasePCell):
    """Geometry-only POLY1/POLY2 overlap capacitor; C density is not assumed."""

    def __init__(self, tech: Technology):
        super().__init__(tech)
        self.spec = tech.profile.validate_pcell("cap_pip", "capacitor")
        self.param("width_um", self.TypeDouble, "POLY1 plate width (um)", default=8.0)
        self.param("height_um", self.TypeDouble, "POLY1 plate height (um)", default=8.0)

    def _minimum(self, name: str) -> float:
        return float(self.spec.get("parameters", {}).get(name, {}).get("min", 0.0))

    def coerce_parameters_impl(self):
        self.width_um = self.tech.snap(max(float(self.width_um), self._minimum("width_um")))
        self.height_um = self.tech.snap(max(float(self.height_um), self._minimum("height_um")))

    def produce_impl(self):
        width = self.tech.snap(max(float(self.width_um), self._minimum("width_um")))
        height = self.tech.snap(max(float(self.height_um), self._minimum("height_um")))
        left, right = -width / 2.0, width / 2.0
        bottom, top = -height / 2.0, height / 2.0
        overlap_inset = float(self.spec["geometry"]["poly2_inset_um"])
        terminal_inset = float(self.spec["geometry"]["terminal_inset_um"])
        contact = self.tech.contact_size
        self._rect("poly", left, bottom, right, top)
        self._rect(
            "elec",
            left + overlap_inset,
            bottom + overlap_inset,
            right - terminal_inset,
            top - terminal_inset,
        )

        # Poly1 contact occupies the lower-left plate extension; the poly2
        # contact sits inside CPOLY with the documented 0.6um enclosure.
        bottom_x, bottom_y = left + contact / 2 + 0.25, bottom + contact / 2 + 0.25
        top_x = (left + overlap_inset + right - terminal_inset) / 2.0
        top_y = (bottom + overlap_inset + top - terminal_inset) / 2.0
        for x, y in ((bottom_x, bottom_y), (top_x, top_y)):
            self._rect(
                "cc", x - contact / 2, y - contact / 2,
                x + contact / 2, y + contact / 2,
            )
            self._rect(
                "metal1",
                x - contact / 2 - self.tech.metal_contact_enc,
                y - contact / 2 - self.tech.metal_contact_enc,
                x + contact / 2 + self.tech.metal_contact_enc,
                y + contact / 2 + self.tech.metal_contact_enc,
            )

class JunctionDiodePCell(_BasePCell):
    """Parametric C35 junction-diode geometry from the ENG-183 element masks."""

    def __init__(self, tech: Technology, name: str):
        super().__init__(tech)
        self.pcell_name = name
        self.spec = tech.profile.validate_pcell(name, "diode")
        params = self.spec.get("parameters", {})
        self.param(
            "width_um",
            self.TypeDouble,
            "Junction width (um)",
            default=float(params.get("width_um", {}).get("default", 4.0)),
        )
        self.param(
            "height_um",
            self.TypeDouble,
            "Junction height (um)",
            default=float(params.get("height_um", {}).get("default", 4.0)),
        )

    def _minimum(self, name: str) -> float:
        return float(self.spec.get("parameters", {}).get(name, {}).get("min", 0.0))

    def _dimensions(self):
        return (
            self.tech.snap(max(float(self.width_um), self._minimum("width_um"))),
            self.tech.snap(max(float(self.height_um), self._minimum("height_um"))),
        )

    def coerce_parameters_impl(self):
        self.width_um, self.height_um = self._dimensions()

    def _active_terminal(self, bounds, select: str, center_x: float, center_y: float):
        left, bottom, right, top = bounds
        self._rect("active", left, bottom, right, top)
        select_enc = self.tech.select_active_enc
        self._rect(
            select,
            left - select_enc,
            bottom - select_enc,
            right + select_enc,
            top + select_enc,
        )
        contact = self.tech.contact_size
        metal_enc = self.tech.metal_contact_enc
        self._rect(
            "cc",
            center_x - contact / 2,
            center_y - contact / 2,
            center_x + contact / 2,
            center_y + contact / 2,
        )
        self._rect(
            "metal1",
            center_x - contact / 2 - metal_enc,
            center_y - contact / 2 - metal_enc,
            center_x + contact / 2 + metal_enc,
            center_y + contact / 2 + metal_enc,
        )

    def produce_impl(self):
        width, height = self._dimensions()
        junction = self.spec["junction"]
        contact = self.tech.contact_size
        active_enc = self.tech.active_contact_enc
        terminal_size = contact + 2 * active_enc
        left, right = -width / 2, width / 2
        bottom, top = -height / 2, height / 2

        if junction == "np_substrate":
            self._active_terminal(
                (left, bottom, right, top), "nselect", 0.0, 0.0
            )
            self._rect("dio_id", left, bottom, right, top)
            return

        if junction == "pplus_nwell":
            pactive = (left, bottom, right, top)
            self._active_terminal(pactive, "pselect", 0.0, 0.0)

            well_enc = float(self.spec["geometry"]["nwell_enclosure_um"])
            tap_enc = float(self.spec["geometry"]["well_tap_enclosure_um"])
            tap_spacing = float(self.spec["geometry"]["tap_spacing_um"])
            tap_left = right + tap_spacing
            tap_right = tap_left + terminal_size
            tap_bottom, tap_top = -terminal_size / 2, terminal_size / 2
            self._active_terminal(
                (tap_left, tap_bottom, tap_right, tap_top),
                "nselect",
                (tap_left + tap_right) / 2,
                0.0,
            )
            well_bounds = (
                left - well_enc,
                min(bottom - well_enc, tap_bottom - tap_enc),
                tap_right + tap_enc,
                max(top + well_enc, tap_top + tap_enc),
            )
            self._rect("nwell", *well_bounds)
            # C35's DIODE marker selects the p+/nwell junction and the
            # well/substrate parasitic represented by the same marked well.
            self._rect("dio_id", *well_bounds)
            return

        if junction == "nwell_substrate":
            tap_enc = float(self.spec["geometry"]["well_tap_enclosure_um"])
            well_left = min(left, -terminal_size / 2 - tap_enc)
            well_bottom = min(bottom, -terminal_size / 2 - tap_enc)
            well_right = max(right, terminal_size / 2 + tap_enc)
            well_top = max(top, terminal_size / 2 + tap_enc)
            self._rect("nwell", well_left, well_bottom, well_right, well_top)
            self._active_terminal(
                (
                    -terminal_size / 2,
                    -terminal_size / 2,
                    terminal_size / 2,
                    terminal_size / 2,
                ),
                "nselect",
                0.0,
                0.0,
            )
            self._rect("dio_id", well_left, well_bottom, well_right, well_top)
            return

        raise ProfileError(
            f"{self.pcell_name}: unsupported junction type {junction}"
        )


class TapPCell(_BasePCell):
    def __init__(self, tech: Technology, polarity: str):
        super().__init__(tech)
        self.polarity = polarity
        name = "ntap" if polarity == "n" else "ptap"
        self.tech.profile.validate_pcell(name, "tap")
        self.param("rows", self.TypeInt, "Contact rows", default=1)
        self.param("columns", self.TypeInt, "Contact columns", default=1)

    def display_text_impl(self):
        name = "ntap" if self.polarity == "n" else "ptap"
        return f"{name}(rows={self.rows},columns={self.columns})"

    def coerce_parameters_impl(self):
        self.rows = max(1, int(round(self.rows)))
        self.columns = max(1, int(round(self.columns)))

    def produce_impl(self):
        rows = self._positive_int("rows", self.rows)
        columns = self._positive_int("columns", self.columns)
        size = self.tech.contact_size
        spacing = self.tech.contact_spacing
        contact_w = columns * size + (columns - 1) * spacing
        contact_h = rows * size + (rows - 1) * spacing
        active_enc = self.tech.active_contact_enc
        metal_enc = self.tech.metal_contact_enc
        select_enc = self.tech.select_active_enc
        left = -contact_w / 2.0
        bottom = -contact_h / 2.0
        for column in range(columns):
            for row in range(rows):
                x = left + column * (size + spacing)
                y = bottom + row * (size + spacing)
                self._rect("cc", x, y, x + size, y + size)
        active = "active"
        select = "nselect" if self.polarity == "n" else "pselect"
        self._rect(
            active,
            left - active_enc,
            bottom - active_enc,
            left + contact_w + active_enc,
            bottom + contact_h + active_enc,
        )
        self._rect(
            "metal1",
            left - metal_enc,
            bottom - metal_enc,
            left + contact_w + metal_enc,
            bottom + contact_h + metal_enc,
        )
        select_extent = active_enc + select_enc
        self._rect(
            select,
            left - select_extent,
            bottom - select_extent,
            left + contact_w + select_extent,
            bottom + contact_h + select_extent,
        )
        if self.polarity == "n":
            well_extent = active_enc + self.tech.nwell_contact_enc
            well_left = left - well_extent
            well_bottom = bottom - well_extent
            well_right = left + contact_w + well_extent
            well_top = bottom + contact_h + well_extent
            if well_right - well_left < self.tech.nwell_min_width:
                extra = (self.tech.nwell_min_width - (well_right - well_left)) / 2.0
                well_left -= extra
                well_right += extra
            if well_top - well_bottom < self.tech.nwell_min_width:
                extra = (self.tech.nwell_min_width - (well_top - well_bottom)) / 2.0
                well_bottom -= extra
                well_top += extra
            self._rect("nwell", well_left, well_bottom, well_right, well_top)


class ViaPCell(_BasePCell):
    def __init__(self, tech: Technology, via_name: str):
        super().__init__(tech)
        self.via_name = via_name
        self.tech.profile.validate_pcell(via_name, "via")
        self.param("rows", self.TypeInt, "Via rows", default=1)
        self.param("columns", self.TypeInt, "Via columns", default=1)

    def display_text_impl(self):
        return f"{self.via_name}(rows={self.rows},columns={self.columns})"

    def coerce_parameters_impl(self):
        self.rows = max(1, int(round(self.rows)))
        self.columns = max(1, int(round(self.columns)))

    def produce_impl(self):
        rows = self._positive_int("rows", self.rows)
        columns = self._positive_int("columns", self.columns)
        spec = self.tech.profile.pcells[self.via_name]
        cut = spec["cut"]
        lower = spec["lower"]
        upper = spec["upper"]
        if self.via_name == "via12":
            size = self.tech.via_size
            spacing = self.tech.via_spacing
            lower_enc = self.tech.via_lower_enc
            upper_enc = self.tech.via_upper_enc
        elif self.via_name == "via23":
            size = self.tech.via2_size
            spacing = self.tech.via2_spacing
            lower_enc = self.tech.via2_lower_enc
            upper_enc = self.tech.via2_upper_enc
        elif self.via_name == "via34":
            size = self.tech.via3_size
            spacing = self.tech.via3_spacing
            lower_enc = self.tech.via3_lower_enc
            upper_enc = self.tech.via3_upper_enc
        else:
            raise ProfileError(f"unsupported via PCell {self.via_name}")
        cut_w = columns * size + (columns - 1) * spacing
        cut_h = rows * size + (rows - 1) * spacing
        left = -cut_w / 2.0
        bottom = -cut_h / 2.0
        for column in range(columns):
            for row in range(rows):
                x = left + column * (size + spacing)
                y = bottom + row * (size + spacing)
                self._rect(cut, x, y, x + size, y + size)
        self._rect(
            lower,
            left - lower_enc,
            bottom - lower_enc,
            left + cut_w + lower_enc,
            bottom + cut_h + lower_enc,
        )
        self._rect(
            upper,
            left - upper_enc,
            bottom - upper_enc,
            left + cut_w + upper_enc,
            bottom + cut_h + upper_enc,
        )


class ElectricalCapPCell(_BasePCell):
    def __init__(self, tech: Technology):
        super().__init__(tech)
        self.tech.profile.validate_pcell("cap_elec", "capacitor")
        if not tech.profile.has_feature("elecAvailable"):
            raise ProfileError("cap_elec requires elecAvailable")
        self.param("width_um", self.TypeDouble, "Poly width (um)", default=6.3)
        self.param("height_um", self.TypeDouble, "Poly height (um)", default=6.3)

    def _minimum(self):
        electrode_size = self.tech.cap_elec_min
        spec = self.tech.profile.pcells["cap_elec"].get("params", {})
        contract_width = float(spec.get("width_um", {}).get("min", 0.0))
        contract_height = float(spec.get("height_um", {}).get("min", 0.0))
        minimum = max(
            electrode_size + 2 * self.tech.poly_elec_enc,
            contract_width,
            contract_height,
        )
        return minimum, electrode_size

    def coerce_parameters_impl(self):
        minimum, _ = self._minimum()
        self.width_um = self.tech.snap(max(float(self.width_um), minimum))
        self.height_um = self.tech.snap(max(float(self.height_um), minimum))

    def produce_impl(self):
        minimum, electrode_size = self._minimum()
        width = self.tech.snap(max(float(self.width_um), minimum))
        height = self.tech.snap(max(float(self.height_um), minimum))
        outer_left, outer_bottom = -width / 2.0, -height / 2.0
        outer_right, outer_top = width / 2.0, height / 2.0
        self._rect("poly", outer_left, outer_bottom, outer_right, outer_top)

        electrode_left = outer_left + self.tech.poly_elec_enc
        electrode_width = electrode_size
        electrode_right = electrode_left + electrode_width
        electrode_height = electrode_size
        electrode_bottom = -electrode_height / 2.0
        electrode_top = electrode_height / 2.0
        if electrode_right > outer_right - self.tech.poly_elec_enc:
            raise ProfileError("cap_elec electrode is below the minimum width")
        self._rect(
            "elec",
            electrode_left,
            electrode_bottom,
            electrode_right,
            electrode_top,
        )

        # The electrical and poly layers are the capacitor terminals.  A
        # contact/metal strap is intentionally outside this generic PCell
        # contract; the profile's native capacitor-contact rules stay
        # process-specific.


class SiliconcraftLibrary(_Library):
    """Register the PCells for one siliconcraft profile."""

    def __init__(
        self,
        profile_dir: Path,
        library_name: str | None = None,
        variant: str | None = None,
    ):
        super().__init__()
        self.profile = Profile(profile_dir, variant=variant)
        self.tech = Technology(self.profile)
        profile_name = self.profile.profile_dir.name
        suffix = f"_{variant}" if variant is not None else ""
        self.description = f"siliconcraft {profile_name}{suffix} analog PCells"
        self.layout().register_pcell("nmos", MosPCell(self.tech, "n"))
        self.layout().register_pcell("pmos", MosPCell(self.tech, "p"))
        for name, polarity in (("nmosm", "n"), ("pmosm", "p")):
            if name in self.profile.pcells:
                self.layout().register_pcell(name, MosPCell(self.tech, polarity, name))
        self.layout().register_pcell("ntap", TapPCell(self.tech, "n"))
        self.layout().register_pcell("ptap", TapPCell(self.tech, "p"))
        if self.profile.has_feature("metal3Available"):
            self.layout().register_pcell("via12", ViaPCell(self.tech, "via12"))
            self.layout().register_pcell("via23", ViaPCell(self.tech, "via23"))
        if self.profile.has_feature("metal4Available"):
            self.layout().register_pcell("via34", ViaPCell(self.tech, "via34"))
        for name in ("rp2", "rph", "rdiffn", "rdiffp", "rnwell"):
            if name in self.profile.pcells:
                self.layout().register_pcell(name, ResistorPCell(self.tech, name))
        for name, spec in self.profile.pcells.items():
            if spec.get("kind") == "diode":
                self.layout().register_pcell(
                    name, JunctionDiodePCell(self.tech, name)
                )
        if "cap_pip" in self.profile.pcells:
            self.layout().register_pcell("cap_pip", PiPCapPCell(self.tech))
        elif "cap_elec" in self.profile.pcells and self.profile.has_feature("elecAvailable"):
            self.layout().register_pcell("cap_elec", ElectricalCapPCell(self.tech))
        self.register(
            library_name or f"siliconcraft_{profile_name}{suffix}"
        )


def register_profile(
    profile_dir: Path,
    library_name: str | None = None,
    variant: str | None = None,
):
    """Register and return a profile's PCell library, optionally for a variant."""
    if pya is None:
        raise RuntimeError("common/pcells/scmos.py must run inside KLayout")
    return SiliconcraftLibrary(Path(profile_dir), library_name, variant=variant)
