"""KLayout analog PCells for siliconcraft SCMOS profiles.

The PCells emit geometry only.  They consume the profile layer map, feature
flags, and PCell parameter contract; Magic extraction is deliberately not part
of this module.

Load with KLayout's Python runner or through ``scripts/run_pcells.py``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import yamlish


class ProfileError(ValueError):
    """Raised when a profile cannot satisfy a PCell contract."""


class Profile:
    """Loaded profile data plus the small geometry contract used by PCells."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = Path(profile_dir)
        self.layers_doc = yamlish.load(
            (self.profile_dir / "layers.yaml").read_text()
        )
        self.rules_doc = yamlish.load(
            (self.profile_dir / "rules.yaml").read_text()
        )
        self.pcells_doc = yamlish.load(
            (self.profile_dir / "pcells.yaml").read_text()
        )
        self.meta = self.layers_doc["meta"]
        self.features = self.meta.get("features", {})
        self.layers = {
            item["name"]: item
            for item in self.layers_doc.get("layers", [])
        }
        self.pcells = self.pcells_doc.get("pcells", {})
        self.lambda_um = float(self.meta.get("lambda_um", 0.5))
        self.grid_um = float(self.meta["grid_um"])
        self.submicron = bool(self.meta.get("submicron_rules", False))
        self.deep = bool(self.meta.get("deep_rules", False))

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
            "submicron": self.submicron,
            "deep": self.deep,
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
            "metalcap": self.has_feature("metalcapAvailable"),
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

    def rule_or(self, group, rule_id, layer, layer2, fallback):
        try:
            return self.rule_value(group, rule_id, layer, layer2)
        except ProfileError:
            return fallback

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
        q = profile.lambda_um
        self.contact_size = profile.rule_or("width", "6.1", "ca", None, 2 * q)
        self.contact_spacing = profile.rule_or("spacing", "6.3", "ca", None, 3 * q)
        self.active_min = profile.rule_or("width", "2.1", "active", None, 3 * q)
        self.poly_min = profile.rule_or("width", "3.1", "poly", None, 2 * q)
        self.poly_spacing = profile.rule_or(
            "spacing", "3.2", "poly", None, 3 * q if profile.submicron else 2 * q
        )
        self.poly_contact_spacing = profile.rule_or(
            "spacing", "6.4", "poly", "ca", 2 * q
        )
        self.active_contact_enc = profile.rule_or(
            "enclosure", "6.2.b", "active", "ca", q
        )
        self.select_active_enc = profile.rule_or(
            "enclosure", "4.2", "nselect", "active", 2 * q
        )
        self.select_contact_enc = profile.rule_or(
            "enclosure", "4.3", "nselect", "ca", q
        )
        self.metal_contact_enc = profile.rule_or(
            "enclosure", "7.3", "metal1", "ca", q
        )
        self.nwell_active_enc = 6 * q if profile.submicron or profile.deep else 5 * q
        self.nwell_contact_enc = 3 * q
        self.nwell_min_width = 12 * q if profile.submicron or profile.deep else 10 * q
        self.via_size = profile.rule_or("width", "8.1", "via", None, 2 * q)
        self.via_spacing = profile.rule_or("spacing", "8.2", "via", None, 3 * q)
        self.via_lower_enc = profile.rule_or(
            "enclosure", "8.3", "metal1", "via", q
        )
        self.via_upper_enc = profile.rule_or(
            "enclosure", "9.3", "metal2", "via", q
        )
        self.via2_size = profile.rule_or("width", "14.1", "via2", None, 2 * q)
        self.via2_spacing = profile.rule_or("spacing", "14.2", "via2", None, 3 * q)
        self.via2_lower_enc = profile.rule_or(
            "enclosure", "14.3", "metal2", "via2", q
        )
        self.via2_upper_enc = profile.rule_or(
            "enclosure", "15.3", "metal3", "via2", 2 * q
        )
        self.poly_elec_enc = profile.rule_or(
            "enclosure", "11.3", "poly", "CapacitorElec", 1.5
        )
        self.cap_elec_min = profile.rule_or(
            "width", "11.1", "CapacitorElec", None, 2.1
        )

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
    def __init__(self, tech: Technology, polarity: str):
        super().__init__(tech)
        self.polarity = polarity
        name = "nmos" if polarity == "n" else "pmos"
        self.tech.profile.validate_pcell(name, "mos4")
        self.param("fingers", self.TypeInt, "Gate fingers", default=1)
        self.param("m", self.TypeInt, "Parallel multiplier", default=1)
        self.param("w_um", self.TypeDouble, "Channel width (um)", default=1.5)
        self.param("l_um", self.TypeDouble, "Channel length (um)", default=0.6)

    def display_text_impl(self):
        name = "nmos" if self.polarity == "n" else "pmos"
        return f"{name}(W={self.w_um:g},L={self.l_um:g},f={self.fingers},m={self.m})"

    def coerce_parameters_impl(self):
        self.fingers = max(1, int(round(self.fingers)))
        self.m = max(1, int(round(self.m)))
        self.w_um = self.tech.snap(max(float(self.w_um), self.tech.active_min))
        self.l_um = self.tech.snap(max(float(self.l_um), self.tech.poly_min))

    def produce_impl(self):
        f = max(self._positive_int("fingers", self.fingers), self._positive_int("m", self.m))
        w = self.tech.snap(max(float(self.w_um), self.tech.active_min))
        l = self.tech.snap(max(float(self.l_um), self.tech.poly_min))
        if self.m == 1:
            poly_pitch = l + self.tech.poly_spacing
        else:
            poly_pitch = l + 2 * (
                self.tech.profile.lambda_um + self.tech.poly_contact_spacing
            )
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
        select_enc = max(
            self.tech.select_active_enc,
            3 * self.tech.profile.lambda_um,
        )
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

        gate_extension = 2 * self.tech.profile.lambda_um
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
        if self.m == 1:
            contact_xs = (
                active_left + self.tech.active_contact_enc,
                active_right - self.tech.active_contact_enc - self.tech.contact_size,
            )
        else:
            parallel_step = 2 * (
                self.tech.profile.lambda_um + self.tech.poly_contact_spacing
            ) + l
            first = active_left + self.tech.active_contact_enc
            contact_xs = [
                first + index * parallel_step for index in range(f + 1)
            ]
        for x in contact_xs:
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
        else:
            size = self.tech.via2_size
            spacing = self.tech.via2_spacing
            lower_enc = self.tech.via2_lower_enc
            upper_enc = self.tech.via2_upper_enc
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
        # contact/metal strap is intentionally outside this PCell contract:
        # AMI06 Rule 11.6 forbids unrelated metal1 overlap of CapacitorElec.


class SiliconcraftLibrary(_Library):
    """Register the PCells for one siliconcraft profile."""

    def __init__(self, profile_dir: Path, library_name: str | None = None):
        super().__init__()
        self.profile = Profile(profile_dir)
        self.tech = Technology(self.profile)
        profile_name = self.profile.profile_dir.name
        self.description = f"siliconcraft {profile_name} analog PCells"
        self.layout().register_pcell("nmos", MosPCell(self.tech, "n"))
        self.layout().register_pcell("pmos", MosPCell(self.tech, "p"))
        self.layout().register_pcell("ntap", TapPCell(self.tech, "n"))
        self.layout().register_pcell("ptap", TapPCell(self.tech, "p"))
        if self.profile.has_feature("metal3Available"):
            self.layout().register_pcell("via12", ViaPCell(self.tech, "via12"))
            self.layout().register_pcell("via23", ViaPCell(self.tech, "via23"))
        if self.profile.has_feature("elecAvailable"):
            self.layout().register_pcell("cap_elec", ElectricalCapPCell(self.tech))
        self.register(library_name or f"siliconcraft_{profile_name}")


def register_profile(profile_dir: Path, library_name: str | None = None):
    """Register and return a profile's KLayout library."""
    if pya is None:
        raise RuntimeError("common/pcells/scmos.py must run inside KLayout")
    return SiliconcraftLibrary(Path(profile_dir), library_name)
