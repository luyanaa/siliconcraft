"""AMS/SCMOS GDS stream-map loading and output validation.

The process profiles own physical drawing layers in ``layers.yaml``.  A
profile that also ships ``gds_layer_map.yaml`` gets a stricter output gate:
all emitted layer/datatype pairs must be present in the checked-in map, and
profile aliases must resolve to the same stream pair as the source map.

The AMS C35 map is intentionally marked as a public reference snapshot, not
as a replacement for the licensed, current foundry kit.  Production signoff
must still use the current AMS/CMC runset and fab DRC/LVS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import yamlish


class GDSLayerMapError(ValueError):
    """Raised when a profile or layout violates its GDS stream contract."""


_MAP_NAME = "gds_layer_map.yaml"
_LEGACY_TEXT_STREAM = (64, 0)
_LEGACY_AUXILIARY = {"substrate_universe": (90, 0)}
_TEXT_ALIASES = {
    "M1": "metal1",
    "M2": "metal2",
    "M3": "metal3",
    "M4": "metal4",
    "POLY": "poly",
    "POLY1": "poly",
    "POLY2": "elec",
    "CC": "cc",
}


def load_gds_layer_map(profile_dir: Path) -> dict[str, Any] | None:
    """Load a profile's optional machine-readable GDS stream map."""
    path = Path(profile_dir) / _MAP_NAME
    if not path.exists():
        return None
    document = yamlish.load(path.read_text())
    if not isinstance(document, dict):
        raise GDSLayerMapError(f"{path}: expected a mapping")
    return document


def _stream(entry: dict[str, Any], context: str) -> tuple[int, int]:
    raw = entry.get("stream")
    if not isinstance(raw, dict):
        raise GDSLayerMapError(f"{context}: stream must be a mapping")
    try:
        layer = int(raw["layer"])
        datatype = int(raw["datatype"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GDSLayerMapError(
            f"{context}: stream requires integer layer and datatype"
        ) from exc
    if not 0 <= layer <= 65535:
        raise GDSLayerMapError(f"{context}: GDS layer out of range: {layer}")
    if not 0 <= datatype <= 255:
        raise GDSLayerMapError(f"{context}: GDS datatype out of range: {datatype}")
    return layer, datatype


def _entries(document: dict[str, Any], section: str) -> tuple[dict[str, Any], ...]:
    raw = document.get(section) or ()
    if not isinstance(raw, list):
        raise GDSLayerMapError(f"{section}: expected a sequence")
    result: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise GDSLayerMapError(f"{section}[{index}]: expected a mapping")
        result.append(entry)
    return tuple(result)


def _all_streams(document: dict[str, Any]) -> set[tuple[int, int]]:
    streams: set[tuple[int, int]] = set()
    for section in ("mask_layers", "recognition_layers", "text_layers"):
        for index, entry in enumerate(_entries(document, section)):
            streams.add(_stream(entry, f"{section}[{index}]"))
    return streams


def _profile_streams(layers_doc: dict[str, Any]) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for index, entry in enumerate(layers_doc.get("layers") or ()):
        if not isinstance(entry, dict) or not entry.get("name"):
            raise GDSLayerMapError(f"layers[{index}]: expected named mapping")
        raw_gds = entry.get("gds") or ()
        if not raw_gds:
            continue
        first = raw_gds[0]
        if not isinstance(first, dict):
            raise GDSLayerMapError(f"layers[{index}].gds[0]: expected mapping")
        try:
            pair = (int(first["layer"]), int(first["datatype"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise GDSLayerMapError(
                f"layers[{index}].gds[0]: invalid layer/datatype"
            ) from exc
        result[str(entry["name"])] = pair
    return result


def validate_profile_gds_map(
    profile_dir: Path,
    layers_doc: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Validate map metadata and its agreement with ``layers.yaml``.

    Profiles without a map retain the historical, permissive behavior.  A
    mapped profile is strict: source identity, grid, every stream entry, and
    every matching logical layer are checked before a GDS file is emitted.
    """
    profile_dir = Path(profile_dir)
    document = load_gds_layer_map(profile_dir)
    if document is None:
        return None

    if document.get("schema_version") != 1:
        raise GDSLayerMapError(
            f"{profile_dir / _MAP_NAME}: schema_version must be 1"
        )
    if document.get("profile") != profile_dir.name:
        raise GDSLayerMapError(
            f"{profile_dir / _MAP_NAME}: profile does not match {profile_dir.name!r}"
        )

    if layers_doc is None:
        layers_path = profile_dir / "layers.yaml"
        layers_doc = yamlish.load(layers_path.read_text())
    if not isinstance(layers_doc, dict):
        raise GDSLayerMapError(f"{profile_dir / 'layers.yaml'}: expected a mapping")
    meta = layers_doc.get("meta") or {}
    if document.get("process") != meta.get("process"):
        raise GDSLayerMapError(
            f"{profile_dir / _MAP_NAME}: process {document.get('process')!r} "
            f"does not match layers.yaml {meta.get('process')!r}"
        )
    database = document.get("database") or {}
    if float(database.get("grid_um", -1)) != float(meta.get("grid_um", -2)):
        raise GDSLayerMapError(
            f"{profile_dir / _MAP_NAME}: grid_um disagrees with layers.yaml"
        )

    mask_entries = _entries(document, "mask_layers")
    recognition_entries = _entries(document, "recognition_layers")
    text_entries = _entries(document, "text_layers")
    for section, entries in (
        ("mask_layers", mask_entries),
        ("recognition_layers", recognition_entries),
        ("text_layers", text_entries),
    ):
        for index, entry in enumerate(entries):
            if not entry.get("name"):
                raise GDSLayerMapError(f"{section}[{index}]: name is required")
            _stream(entry, f"{section}[{index}]")

    profile_streams = _profile_streams(layers_doc)
    mapped_logical = {
        str(entry["logical"]): _stream(entry, f"mask_layers[{index}]")
        for index, entry in enumerate(mask_entries)
        if entry.get("logical")
    }
    unmapped_profile_layers = sorted(
        logical
        for logical in profile_streams
        if logical != "glass" and logical not in mapped_logical
    )
    if unmapped_profile_layers:
        raise GDSLayerMapError(
            f"{profile_dir / _MAP_NAME}: profile layers missing from stream map: "
            + ", ".join(unmapped_profile_layers)
        )
    if profile_streams.get("glass") != profile_streams.get("pad"):
        raise GDSLayerMapError(
            f"{profile_dir / 'layers.yaml'}: glass must alias the PAD stream"
        )
    for logical, pair in profile_streams.items():
        # ``glass`` is an intentional profile alias of the PAD mask.
        if logical == "glass":
            continue
        expected = mapped_logical.get(logical)
        if expected is not None and pair != expected:
            raise GDSLayerMapError(
                f"{profile_dir / 'layers.yaml'}:{logical}: {pair} != "
                f"public stream map {expected}"
            )

    for logical, pair in mapped_logical.items():
        profile_pair = profile_streams.get(logical)
        if profile_pair is not None and profile_pair != pair:
            raise GDSLayerMapError(
                f"{profile_dir / _MAP_NAME}:{logical}: {pair} != "
                f"layers.yaml {profile_pair}"
            )

    return document


def require_fab_authority(profile_dir: Path) -> dict[str, Any]:
    """Require a current foundry-authoritative map for tapeout validation."""
    document = validate_profile_gds_map(profile_dir)
    if document is None:
        raise GDSLayerMapError(
            f"{profile_dir}: no {_MAP_NAME}; a foundry-supplied stream map is required"
        )
    source = document.get("source") or {}
    if source.get("authority") != "foundry_current" or source.get("fab_signoff") is not True:
        raise GDSLayerMapError(
            "production validation is blocked: the checked-in map is a public "
            "reference snapshot, not the current licensed AMS/CMC foundry map; "
            "install the current C35B4C3 stream map and rerun"
        )
    return document


def validate_layout_layer_pairs(layout: Any, profile_dir: Path) -> None:
    """Reject emitted GDS layer/datatype pairs absent from the profile map."""
    document = validate_profile_gds_map(profile_dir)
    if document is None:
        return
    allowed = _all_streams(document)
    bad: list[tuple[int, int]] = []
    for layer_index in layout.layer_indices():
        info = layout.get_info(layer_index)
        pair = (int(info.layer), int(info.datatype))
        if pair not in allowed:
            bad.append(pair)
    if bad:
        unique = ", ".join(f"{layer}/{datatype}" for layer, datatype in sorted(set(bad)))
        raise GDSLayerMapError(
            f"{profile_dir.name}: emitted GDS contains unmapped layer/datatype pair(s): {unique}"
        )


def gds_text_stream(
    profile_dir: Path,
    logical_layer: str | None = None,
    purpose: str = "net",
) -> tuple[int, int]:
    """Resolve a profile-aware text stream, with a legacy fallback."""
    document = load_gds_layer_map(Path(profile_dir))
    if document is None:
        return _LEGACY_TEXT_STREAM
    logical_name = str(logical_layer or "M1")
    logical = _TEXT_ALIASES.get(logical_name.upper(), logical_name)
    candidates = [
        entry
        for entry in _entries(document, "text_layers")
        if entry.get("logical") == logical and entry.get("purpose") == purpose
    ]
    if not candidates:
        raise GDSLayerMapError(
            f"{profile_dir.name}: no {purpose} text stream for logical layer {logical_layer!r}"
        )
    return _stream(candidates[0], f"text_layers/{logical}/{purpose}")


def auxiliary_stream(profile_dir: Path, name: str) -> tuple[int, int] | None:
    """Resolve an optional non-mask stream, preserving legacy profiles."""
    document = load_gds_layer_map(Path(profile_dir))
    if document is None:
        return _LEGACY_AUXILIARY.get(name)
    auxiliary = document.get("auxiliary") or {}
    raw = auxiliary.get(name)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GDSLayerMapError(f"auxiliary.{name}: expected a stream mapping or null")
    return _stream({"stream": raw}, f"auxiliary.{name}")


__all__ = [
    "GDSLayerMapError",
    "auxiliary_stream",
    "gds_text_stream",
    "load_gds_layer_map",
    "require_fab_authority",
    "validate_layout_layer_pairs",
    "validate_profile_gds_map",
]
