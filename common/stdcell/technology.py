"""SCMOS geometry adapter owned by the fixed-height stdcell flow.

This is deliberately separate from ``common.pcells.scmos.Technology``.  The
analog PCell adapter models the shared SCMOS PCell contract; a standard-cell
row needs a smaller, explicit set of process rules and must not inherit analog
PCell assumptions such as a poly-contact rule that some processes omit.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.pcells.scmos import Profile, ProfileError


_SCMOS_RULE_MAP = {
    "contact.cut_size": ("width", "6.1", "ca", None),
    "contact.cut_spacing": ("spacing", "6.3", "ca", None),
    "active.min_width": ("width", "2.1", "active", None),
    "poly.min_width": ("width", "3.1", "poly", None),
    "poly.min_spacing": ("spacing", "3.2", "poly", None),
    "poly.contact_enclosure": ("enclosure", "5.2.b", "poly", "cp"),
    "active.contact_enclosure": ("enclosure", "6.2.b", "active", "ca"),
    "active.contact_gate_spacing": ("spacing", "6.4", "ca", "Gate"),
    "select.active_enclosure.n": ("enclosure", "4.2", "nselect", "active"),
    "select.active_enclosure.p": ("enclosure", "4.2", "pselect", "active"),
    "select.channel_enclosure.n": ("enclosure", "4.1", "nselect", "nChannel"),
    "select.channel_enclosure.p": ("enclosure", "4.1", "pselect", "pChannel"),
    "gate.extension": ("spacing", "5.4", "cp", "Gate"),
    "select.contact_enclosure.n": ("enclosure", "4.3", "nselect", "ca"),
    "select.contact_enclosure.p": ("enclosure", "4.3", "pselect", "ca"),
    "metal1.contact_enclosure": ("enclosure", "7.3", "metal1", "ca"),
    "nwell.active_enclosure": ("spacing", "1.3", "nwell", None),
    "nwell.min_width": ("width", "1.1", "nwell", None),
    "via12.cut_size": ("width", "8.1", "via", None),
    "via12.cut_spacing": ("spacing", "8.2", "via", None),
    "via12.lower_enclosure": ("enclosure", "8.3", "metal1", "via"),
    "via12.upper_enclosure": ("enclosure", "9.3", "metal2", "via"),
    "via12.poly_spacing": ("spacing", "8.5", "poly", "via"),
    "via12.active_spacing": ("spacing", "8.5", "active", "via"),
    "via23.cut_size": ("width", "14.1", "via2", None),
    "via23.cut_spacing": ("spacing", "14.2", "via2", None),
    "via23.lower_enclosure": ("enclosure", "14.3", "metal2", "via2"),
    "via23.upper_enclosure": ("enclosure", "15.3", "metal3", "via2"),
    "metal.M1.min_width": ("width", "7.1", "metal1", None),
    "metal.M1.min_spacing": ("spacing", "7.2", "metal1", None),
    "metal.M2.min_width": ("width", "9.1", "metal2", None),
    "metal.M2.min_spacing": ("spacing", "9.2", "metal2", None),
    "metal.M3.min_width": ("width", "15.1", "metal3", None),
    "metal.M3.min_spacing": ("spacing", "15.2", "metal3", None),
}


@dataclass(frozen=True)
class StdcellTechnology:
    """Rule-derived geometry constants consumed by the row planner."""

    profile: Profile
    contact_size: float
    contact_spacing: float
    active_min: float
    poly_min: float
    poly_spacing: float
    poly_contact_enc: float
    active_contact_enc: float
    active_contact_gate_spacing: float
    select_active_enc: float
    select_channel_enc: float
    gate_extension: float
    select_contact_enc: float
    metal_contact_enc: float
    nwell_active_enc: float
    nwell_min_width: float
    via_size: float
    via_spacing: float
    via_lower_enc: float
    via_upper_enc: float
    via_poly_spacing: float
    via_active_spacing: float
    via2_size: float | None
    via2_spacing: float | None
    via2_lower_enc: float | None
    via2_upper_enc: float | None

    @classmethod
    def from_profile(cls, profile: Profile) -> "StdcellTechnology":
        def r(key: str) -> float:
            return profile.semantic_rule(key, _SCMOS_RULE_MAP[key])

        def optional_r(key: str) -> float:
            try:
                return r(key)
            except ProfileError:
                return 0.0

        metal3 = profile.has_feature("metal3Available")
        return cls(
            profile=profile,
            contact_size=r("contact.cut_size"),
            contact_spacing=r("contact.cut_spacing"),
            active_min=r("active.min_width"),
            poly_min=r("poly.min_width"),
            poly_spacing=r("poly.min_spacing"),
            poly_contact_enc=r("poly.contact_enclosure"),
            active_contact_enc=r("active.contact_enclosure"),
            active_contact_gate_spacing=r("active.contact_gate_spacing"),
            select_active_enc=max(
                r("select.active_enclosure.n"),
                r("select.active_enclosure.p"),
            ),
            select_channel_enc=max(
                r("select.channel_enclosure.n"),
                r("select.channel_enclosure.p"),
            ),
            gate_extension=r("gate.extension"),
            select_contact_enc=max(
                r("select.contact_enclosure.n"),
                r("select.contact_enclosure.p"),
            ),
            metal_contact_enc=r("metal1.contact_enclosure"),
            nwell_active_enc=r("nwell.active_enclosure"),
            nwell_min_width=r("nwell.min_width"),
            via_size=r("via12.cut_size"),
            via_spacing=r("via12.cut_spacing"),
            via_lower_enc=r("via12.lower_enclosure"),
            via_upper_enc=r("via12.upper_enclosure"),
            via_poly_spacing=optional_r("via12.poly_spacing"),
            via_active_spacing=optional_r("via12.active_spacing"),
            via2_size=r("via23.cut_size") if metal3 else None,
            via2_spacing=r("via23.cut_spacing") if metal3 else None,
            via2_lower_enc=r("via23.lower_enclosure") if metal3 else None,
            via2_upper_enc=r("via23.upper_enclosure") if metal3 else None,
        )


    def semantic_rule(self, key: str) -> float:
        return self.profile.semantic_rule(key, _SCMOS_RULE_MAP[key])

    def snap(self, value: float) -> float:
        return self.profile.snap(value)
