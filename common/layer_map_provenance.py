"""Provenance and tapeout gates for logical and public-reference layer maps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import yamlish


class LayerMapProvenanceError(ValueError):
    """Raised when a layer-map authority claim is inconsistent."""


AUTHORITIES = {
    "internal_logical",
    "public_reference",
    "inferred_authorized",
    "foundry_authoritative",
}


def load_reference_map(path: Path) -> dict[str, Any]:
    value = yamlish.load(Path(path).read_text())
    if not isinstance(value, dict):
        raise LayerMapProvenanceError(f"{path}: expected a mapping")
    authority = value.get("authority")
    if authority not in AUTHORITIES:
        raise LayerMapProvenanceError(f"{path}: unsupported authority {authority!r}")
    if value.get("tapeout_eligible") is not False:
        raise LayerMapProvenanceError(
            f"{path}: public/reference maps must explicitly set tapeout_eligible: false"
        )
    if authority == "foundry_authoritative":
        raise LayerMapProvenanceError(
            f"{path}: foundry_authoritative maps belong in a private overlay"
        )
    return value


def require_tapeout_authority(layers_doc: dict[str, Any]) -> None:
    meta = layers_doc.get("meta") or {}
    authority = meta.get("mask_map_authority")
    if authority != "foundry_authoritative":
        raise LayerMapProvenanceError(
            "tapeout requires mask_map_authority=foundry_authoritative; "
            f"got {authority!r}"
        )
    policy = str(meta.get("gds_output_policy") or "")
    if "tapeout" not in policy.lower() or "foundry" not in policy.lower():
        raise LayerMapProvenanceError(
            "tapeout policy must name a foundry-authoritative GDS stream map"
        )
