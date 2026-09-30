"""SCMOS option-device capability contracts.

The SCMOS 7.2 option layers are not interchangeable device models.  This
module exposes the normalized, profile-local support boundary without
promoting historical geometry or Magic extraction data to foundry collateral.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from common.process_ir import ProcessIR


EXTENSION_IDS = (
    "hvcmos",
    "electrode_capacitor",
    "electrode_transistor",
    "electrode_contact",
    "vertical_npn",
    "linear_capacitor",
    "buried_ccd",
    "silicide_block",
    "mems",
    "scnpc_poly_cap",
)

_RULE_TABLES = ("width", "spacing", "enclosure", "extension", "area", "notch", "overlap")


def _rule_ids(process: "ProcessIR") -> set[str]:
    ids: set[str] = set()
    for table in _RULE_TABLES:
        for entry in process.rules.get(table, []) or []:
            if isinstance(entry, dict) and entry.get("id") is not None:
                ids.add(str(entry["id"]))
    return ids


def _has_rule_sections(rule_ids: set[str], sections: tuple[str, ...]) -> bool:
    return all(any(rule_id.startswith(section + ".") for rule_id in rule_ids)
               for section in sections)


def _device_names(process: "ProcessIR") -> set[str]:
    names: set[str] = set()
    for entries in process.devices.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name") is not None:
                names.add(str(entry["name"]))
    return names


def _status(
    family: str,
    enabled: bool,
    drc: str,
    lvs: str,
    reason: str,
) -> dict[str, Any]:
    if not enabled:
        state = "unavailable"
    elif drc == "none" and lvs in {"none", "not_applicable"}:
        state = "blocked"
    elif drc in {"implemented", "lambda_only"} and lvs in {
        "implemented", "recipe", "not_applicable", "none"
    }:
        state = "supported" if drc == "implemented" and lvs in {
            "implemented", "not_applicable"
        } else "partial"
    else:
        state = "partial"
    return {
        "family": family,
        "enabled": enabled,
        "state": state,
        "drc": drc,
        "lvs": lvs,
        "reason": reason,
    }


def extension_statuses(process: "ProcessIR") -> dict[str, dict[str, Any]]:
    """Return profile-local SCMOS option support statuses.

    ``enabled`` reflects the profile's physical feature flag.  ``drc`` and
    ``lvs`` describe the collateral actually present for that enabled option;
    they deliberately preserve ``lambda_only`` and ``recipe`` states instead
    of treating historical rules as signoff data.
    """

    features = process.meta.get("features") or {}
    rules = _rule_ids(process)
    devices = _device_names(process)
    elec = bool(features.get("elecAvailable"))
    npn = bool(features.get("npnAvailable"))
    cwell = bool(features.get("cwellAvailable"))
    ccd = bool(features.get("ccdAvailable"))
    sblock = bool(features.get("sblockAvailable"))
    scnpc = bool(features.get("scnpcAvailable"))
    hv = bool(features.get("hvcmosAvailable") or features.get("hvAvailable"))
    mems = bool(features.get("memsAvailable"))
    hvcmos_rules = bool(process.rules_doc.get("hvcmos"))

    result = {
        "hvcmos": _status(
            "hvcmos",
            hv,
            "partial" if hv and hvcmos_rules else "none",
            "partial" if hv else "none",
            "SCMOS 7.2 has no official generic HV lambda section; marker/net-aware collateral remains profile-specific.",
        ),
        "electrode_capacitor": _status(
            "electrode_capacitor",
            elec,
            "implemented" if _has_rule_sections(rules, ("11",)) else "none",
            "implemented" if "CapacitorElec" in devices else "none",
            "poly2-over-poly1 capacitor contract; model and PEX coefficients remain profile-owned.",
        ),
        "electrode_transistor": _status(
            "electrode_transistor",
            elec,
            "implemented" if _has_rule_sections(rules, ("12",)) else "none",
            "implemented" if {"nmos4_elec", "pmos4_elec"} <= devices else "none",
            "electrode-gated MOS recognition is only complete when both layout and LVS device rows exist.",
        ),
        "electrode_contact": _status(
            "electrode_contact",
            elec,
            "implemented" if _has_rule_sections(rules, ("13",)) else "none",
            "implemented" if elec else "none",
            "electrode contact classification is part of the SCMOS connectivity contract, not a standalone extracted device.",
        ),
        "vertical_npn": _status(
            "vertical_npn",
            npn,
            "implemented" if _has_rule_sections(rules, ("16",)) else "none",
            "implemented" if "npnTran" in devices else "none",
            "Generic_NPN is a source-backed LVS identity; calibrated NPN model cards are not implied.",
        ),
        "linear_capacitor": _status(
            "linear_capacitor",
            cwell,
            "implemented" if _has_rule_sections(rules, ("17", "18")) else "none",
            "implemented" if "lcCap" in devices else "none",
            "cap-well/linear capacitor; do not alias it to an electrode or SCNPC capacitor.",
        ),
        "buried_ccd": _status(
            "buried_ccd",
            ccd,
            "implemented" if _has_rule_sections(rules, ("19",)) else "none",
            "not_applicable",
            "charge-coupled geometry has no extracted three-terminal LVS device in SCMOS.",
        ),
        "silicide_block": _status(
            "silicide_block",
            sblock,
            "lambda_only" if _has_rule_sections(rules, ("20",)) else "none",
            "recipe" if "polySRes" in devices else "none",
            "unsilicided-poly resistor rules are lambda-scalable; resistor coefficients and foundry signoff remain separate.",
        ),
        "mems": _status(
            "mems",
            mems,
            "none",
            "none",
            "MEMS open/etch-stop layers have process-specific micrometer guidelines and no SCMOS lambda deck.",
        ),
        "scnpc_poly_cap": _status(
            "scnpc_poly_cap",
            scnpc,
            "lambda_only" if _has_rule_sections(rules, ("23",)) else "none",
            "none",
            "AMI CWL POLY_CAP1 is distinct from both cap-well and electrode capacitors; no native LVS contract is claimed.",
        ),
    }
    return {family: result[family] for family in EXTENSION_IDS}


__all__ = ["EXTENSION_IDS", "extension_statuses"]
