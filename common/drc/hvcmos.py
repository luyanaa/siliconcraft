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


_LABEL_HV = re.compile(r"(^|[:_@])HV($|[:_@])|HV", re.IGNORECASE)
_LABEL_LV = re.compile(r"(^|[:_@])LV($|[:_@])|LV", re.IGNORECASE)
_POTENTIAL = re.compile(r"(?:@POT=|HV[:_]|LV[:_]|HV_|LV_)([^:@]+)", re.IGNORECASE)


def _empty() -> pya.Region:
    return pya.Region()


def _as_region(value) -> pya.Region:
    return value if isinstance(value, pya.Region) else pya.Region(value)


def _to_region(edge_pairs) -> pya.Region:
    """Turn KLayout edge-pair markers into small visible polygons."""
    step = max(1, int(round(0.001 / _to_region.dbu)))
    out = pya.Region()
    for pair in edge_pairs.each():
        out += pya.Region(pair.first.bbox().enlarged(step))
        out += pya.Region(pair.second.bbox().enlarged(step))
    return out


_to_region.dbu = 0.001


def _label_class(label: str) -> str | None:
    if _LABEL_HV.search(label or ""):
        return "hv"
    if _LABEL_LV.search(label or ""):
        return "lv"
    return None


def _potential(label: str, root: int) -> str:
    match = _POTENTIAL.search(label or "")
    if match:
        return match.group(1).strip().upper()
    return label if label and not label.startswith("n") else f"ROOT:{root}"


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
        return marker.interacting(target)
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
def _net_groups(D, resolve, layout, top, L, F, WELL, DBU, layer: str):
    """Return voltage-class regions grouped by connected net root.

    Labels on GDS 64/0 use ``HV:<potential>`` or ``LV:<potential>``.  An
    unlabelled conductor falls back to the HV marker geometry; this keeps the
    deck useful for early layout work while making labelled connectivity the
    authoritative path for voltage-aware spacing.
    """
    conductor = _resolve(D, resolve, layer)
    if conductor.is_empty():
        return {"hv": {}, "lv": {}}
    nets = build_nets(D, L, F, WELL, layout, top, DBU)
    marker = D.get("hvMarker", _empty())
    groups = {"hv": {}, "lv": {}}
    for index, (name, polygon) in enumerate(nets.comps):
        if name != layer:
            continue
        region = pya.Region(polygon)
        label = nets.net_of(index)
        voltage_class = _label_class(label)
        if voltage_class is None:
            voltage_class = "hv" if not region.interacting(marker).is_empty() else "lv"
        root = nets.uf.find(index)
        key = (root, _potential(label, root))
        groups[voltage_class].setdefault(key, pya.Region())
        groups[voltage_class][key] += region
    return groups


def _spacing(report, left, right, value_um, rule_id, message, dbu, same_root=False):
    if left.is_empty() or right.is_empty() or same_root:
        return
    distance = max(1, int(round(value_um / dbu)))
    # KLayout's cross-region overload does not report the nearest edge pair
    # for all layer/region combinations.  The caller supplies only the two
    # voltage classes/potential groups being compared, so a union is exact.
    combined = left + right
    _to_region.dbu = dbu
    report.item(_to_region(combined.space_check(distance)), rule_id, message)


def _voltage_spacing(hvcmos, D, resolve, layout, top, L, F, WELL, DBU, report) -> None:
    for entry in hvcmos.get("voltage_spacing", []) or []:
        layer1 = str(entry["layer"])
        layer2 = str(entry.get("layer2", layer1))
        groups1 = _net_groups(D, resolve, layout, top, L, F, WELL, DBU, layer1)
        groups2 = groups1 if layer2 == layer1 else _net_groups(
            D, resolve, layout, top, L, F, WELL, DBU, layer2
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
