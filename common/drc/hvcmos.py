#!/usr/bin/env python3
"""Initial marker/net-aware HVCMOS checks for profile-specific DRC decks.

The public X-FAB datasheets expose device/module classes and basic geometry,
but not the foundry marker stream map or a complete HV rule deck.  This module
therefore implements the explicit profile contract only: marker coverage,
well/drift hierarchy, and voltage-class spacing.  It deliberately does not
add guard-ring or latch-up rules to ordinary SCMOS checks.
"""

from __future__ import annotations

import os
import re
import sys

import pya

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from common.lvs.scmos_lvs_core import build_nets  # noqa: E402


_LABEL = re.compile(
    r"^\s*(?:@POT=)?(?P<class>HV|LV)"
    r"(?:(?::|_)(?P<potential>[^:@\s]+))?\s*$",
    re.IGNORECASE,
)


def _empty() -> pya.Region:
    return pya.Region()




def _label_match(label: str):
    return _LABEL.fullmatch(str(label or ""))


def _label_class(label: str) -> str:
    match = _label_match(label)
    return match.group("class").lower() if match else "unknown"


def _potential(label: str, root: int) -> str:
    match = _label_match(label)
    if match and match.group("potential"):
        return match.group("potential").strip().upper()
    if match:
        return match.group("class").upper()
    return str(label).strip().upper() if label else f"ROOT:{root}"


def _resolve(D, resolver, name: str) -> pya.Region:
    region = D.get(name)
    if region is not None:
        return region
    return resolver(name)


def _relation_bad(marker: pya.Region, target: pya.Region, relation: str) -> pya.Region:
    if marker.is_empty() or target.is_empty():
        return _empty()
    relation = relation.lower()
    if relation in {"inside", "covered_by", "enclosed"}:
        return target - marker
    if relation in {"marker_inside", "marker_covered_by"}:
        return marker - target
    if relation in {"disjoint", "forbid_overlap"}:
        return marker.interacting(target)
    if relation == "overlap":
        # ``overlap`` is a positive relation: an empty intersection is the
        # violation.  ``interacting`` itself is the violating region for the
        # opposite ``disjoint`` relation.
        if not marker.interacting(target).is_empty():
            return _empty()
        return target
    raise ValueError(f"unsupported HVCMOS relation {relation!r}")


def _run_geometry_contracts(hvcmos, D, resolve, report) -> None:
    for entry in hvcmos.get("markers", []) or []:
        marker = _resolve(D, resolve, str(entry["marker"]))
        target = _resolve(D, resolve, str(entry["target"]))
        bad = _relation_bad(marker, target, entry.get("relation", "inside"))
        report.item(bad, entry["id"], entry.get("note", "HVCMOS marker contract"))
        forbidden = entry.get("forbid_overlap")
        if forbidden:
            bad = marker.interacting(_resolve(D, resolve, str(forbidden)))
            report.item(bad, entry["id"] + ".EXCL", entry.get("note", "HVCMOS marker exclusivity"))

    for entry in hvcmos.get("hierarchy", []) or []:
        outer = _resolve(D, resolve, str(entry["outer"]))
        inner = _resolve(D, resolve, str(entry["inner"]))
        bad = _relation_bad(outer, inner, "inside")
        report.item(bad, entry["id"], entry.get("note", "HVCMOS well hierarchy"))

    for entry in hvcmos.get("drift", []) or []:
        marker = _resolve(D, resolve, str(entry["marker"]))
        target = _resolve(D, resolve, str(entry["target"]))
        bad = _relation_bad(marker, target, entry.get("relation", "inside"))
        report.item(bad, entry["id"], entry.get("note", "HVCMOS drift contract"))
        parent = entry.get("parent")
        if parent:
            bad = marker - _resolve(D, resolve, str(parent))
            report.item(
                bad,
                entry["id"] + ".PARENT",
                entry.get("note", "HVCMOS drift parent"),
            )
def _voltage_policy(hvcmos) -> tuple[str, bool, bool, str]:
    config = hvcmos.get("voltage_classification") or {}
    mode = str(config.get("mode", "strict")).lower()
    if mode not in {"strict", "exploratory"}:
        raise ValueError(f"unsupported HVCMOS voltage classification mode {mode!r}")
    infer_marker = bool(config.get("marker_inference", mode == "exploratory"))
    require_annotation = bool(config.get("require_annotation", mode == "strict"))
    unknown_rule_id = str(config.get("unknown_rule_id", "HVCMOS.VOLTAGE.UNKNOWN"))
    return mode, infer_marker, require_annotation, unknown_rule_id


def _net_groups(
    D, resolve, layout, top, L, F, WELL, DBU, layer: str, infer_marker: bool
):
    """Return LV/HV/UNKNOWN regions grouped by connected net root.

    ``UNKNOWN`` is intentionally preserved.  Marker inference is an explicit
    exploratory-mode policy, never an implicit LV fallback.
    """
    conductor = _resolve(D, resolve, layer)
    if conductor.is_empty():
        return {"hv": {}, "lv": {}, "unknown": {}}
    nets = build_nets(D, L, F, WELL, layout, top, DBU)
    marker = D.get("hvMarker", _empty())
    groups = {"hv": {}, "lv": {}, "unknown": {}}
    for index, (name, polygon) in enumerate(nets.comps):
        if name != layer:
            continue
        region = pya.Region(polygon)
        label = nets.net_of(index)
        voltage_class = _label_class(label)
        if voltage_class == "unknown" and infer_marker:
            if not region.interacting(marker).is_empty():
                voltage_class = "hv"
        root = nets.uf.find(index)
        key = (root, _potential(label, root))
        groups[voltage_class].setdefault(key, pya.Region())
        groups[voltage_class][key] += region
    return groups


def _spacing(report, left, right, value_um, rule_id, message, dbu, same_root=False):
    if left.is_empty() or right.is_empty() or same_root:
        return
    distance = max(1, int(round(value_um / dbu)))
    # Expand only the left class and intersect the right class.  A union
    # followed by space_check() also checks left-left/right-right polygon
    # spacing and creates false cross-class violations for multi-polygon nets.
    report.item(
        left.sized(distance) & right,
        rule_id,
        message,
    )


def _voltage_spacing(hvcmos, D, resolve, layout, top, L, F, WELL, DBU, report) -> None:
    _mode, infer_marker, require_annotation, unknown_rule_id = _voltage_policy(hvcmos)
    unknown_reported: set[str] = set()
    for entry in hvcmos.get("voltage_spacing", []) or []:
        layer1 = str(entry["layer"])
        layer2 = str(entry.get("layer2", layer1))
        groups1 = _net_groups(
            D, resolve, layout, top, L, F, WELL, DBU, layer1, infer_marker
        )
        groups2 = groups1 if layer2 == layer1 else _net_groups(
            D, resolve, layout, top, L, F, WELL, DBU, layer2, infer_marker
        )
        if require_annotation:
            for layer, groups in ((layer1, groups1), (layer2, groups2)):
                if layer in unknown_reported:
                    continue
                unknown_reported.add(layer)
                for region in groups["unknown"].values():
                    report.item(
                        region,
                        unknown_rule_id,
                        f"{layer}: voltage class annotation is required",
                    )
        class1 = str(entry["class1"]).lower()
        class2 = str(entry.get("class2", class1)).lower()
        potential = str(entry.get("potential", "any")).lower()
        left = list(groups1.get(class1, {}).items())
        right = list(groups2.get(class2, {}).items())
        if not left or not right:
            continue
        rid = str(entry["id"])
        message = entry.get("note", "HVCMOS voltage-aware spacing")
        distance = float(entry["value_um"])
        for (root1, pot1), region1 in left:
            for (root2, pot2), region2 in right:
                if layer1 == layer2 and root1 == root2:
                    continue
                if potential == "different" and pot1 == pot2:
                    continue
                if potential == "same" and pot1 != pot2:
                    continue
                _spacing(
                    report,
                    region1,
                    region2,
                    distance,
                    rid,
                    message,
                    DBU,
                    same_root=root1 == root2,
                )


def run_hvcmos_checks(
    hvcmos,
    D,
    resolve,
    layout,
    top,
    L,
    F,
    WELL,
    DBU,
    report,
) -> None:
    """Run the explicit profile HVCMOS contract, if one is present."""
    if not hvcmos or not F("hvcmosAvailable"):
        return
    _run_geometry_contracts(hvcmos, D, resolve, report)
    _voltage_spacing(hvcmos, D, resolve, layout, top, L, F, WELL, DBU, report)
