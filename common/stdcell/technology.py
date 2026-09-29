"""SCMOS geometry adapter owned by the fixed-height stdcell flow.

This is deliberately separate from ``common.pcells.scmos.Technology``.  The
analog PCell adapter models the shared SCMOS PCell contract; a standard-cell
row needs a smaller, explicit set of process rules and must not inherit analog
PCell assumptions such as a poly-contact rule that some processes omit.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.pcells.scmos import Profile, ProfileError


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
        rule = profile.rule_value

        def r(group: str, rule_id: str, layer: str, layer2: str | None = None) -> float:
            return rule(group, rule_id, layer, layer2)

        def optional_r(group: str, rule_id: str, layer: str, layer2: str) -> float:
            try:
                return r(group, rule_id, layer, layer2)
            except ProfileError:
                return 0.0

        metal3 = profile.has_feature("metal3Available")
        return cls(
            profile=profile,
            contact_size=r("width", "6.1", "ca"),
            contact_spacing=r("spacing", "6.3", "ca"),
            active_min=r("width", "2.1", "active"),
            poly_min=r("width", "3.1", "poly"),
            poly_spacing=r("spacing", "3.2", "poly"),
            poly_contact_enc=r("enclosure", "5.2.b", "poly", "cp"),
            active_contact_enc=r("enclosure", "6.2.b", "active", "ca"),
            active_contact_gate_spacing=r("spacing", "6.4", "ca", "Gate"),
            select_active_enc=max(
                r("enclosure", "4.2", "nselect", "active"),
                r("enclosure", "4.2", "pselect", "active"),
            ),
            select_channel_enc=max(
                r("enclosure", "4.1", "nselect", "nChannel"),
                r("enclosure", "4.1", "pselect", "pChannel"),
            ),
            gate_extension=r("spacing", "5.4", "cp", "Gate"),
            select_contact_enc=max(
                r("enclosure", "4.3", "nselect", "ca"),
                r("enclosure", "4.3", "pselect", "ca"),
            ),
            metal_contact_enc=r("enclosure", "7.3", "metal1", "ca"),
            nwell_active_enc=r("spacing", "1.3", "nwell"),
            nwell_min_width=r("width", "1.1", "nwell"),
            via_size=r("width", "8.1", "via"),
            via_spacing=r("spacing", "8.2", "via"),
            via_lower_enc=r("enclosure", "8.3", "metal1", "via"),
            via_upper_enc=r("enclosure", "9.3", "metal2", "via"),
            via_poly_spacing=optional_r("spacing", "8.5", "poly", "via"),
            via_active_spacing=optional_r("spacing", "8.5", "active", "via"),
            via2_size=r("width", "14.1", "via2") if metal3 else None,
            via2_spacing=r("spacing", "14.2", "via2") if metal3 else None,
            via2_lower_enc=(
                r("enclosure", "14.3", "metal2", "via2") if metal3 else None
            ),
            via2_upper_enc=(
                r("enclosure", "15.3", "metal3", "via2") if metal3 else None
            ),
        )

    def snap(self, value: float) -> float:
        return self.profile.snap(value)
