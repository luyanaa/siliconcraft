#!/usr/bin/env python3
"""Smoke the measured-WAT analytical RC flow (PEX v0) for every profile that
declares a ``wat_analytical_rc`` extractor.

For each such profile this builds one canonical probe per declared coefficient
family and asserts the report is sane and explicitly non-signoff:

  * every segment yields a positive resistance,
  * every coupling pair yields a positive capacitance,
  * the report carries ``calibrated_to_current_d35: false`` and ``signoff: false``,
  * the coefficient set's provenance is surfaced.

No external tools are required.

Usage:
  python3 scripts/run_wat_pex_smoke.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
for path in (str(ROOT), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import yamlish  # noqa: E402

from common.pex.wat_rc import (  # noqa: E402
    CouplingPair,
    WireSegment,
    build_wat_rc_report,
)
from common.process_ir import load_process, profile_names  # noqa: E402


def wat_profiles() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for profile in profile_names(ROOT):
        pex_doc = load_process(profile, ROOT).pex_doc
        for name, spec in (pex_doc.get("profiles") or {}).items():
            if isinstance(spec, dict) and spec.get("extractor") == "wat_analytical_rc":
                found.append((profile, name))
    return found


def resolve_reference(profile: str, spec: dict) -> Path:
    name = str(spec.get("reference_data") or "")
    for candidate in (
        ROOT / "profiles" / profile / "pex" / name,
        ROOT / "profiles" / profile / name,
        ROOT / name,
    ):
        if candidate.exists():
            return candidate
    raise SystemExit(f"{profile}: reference data {name!r} not found")


def canonical_probe(spec: dict) -> tuple[list[WireSegment], list[CouplingPair]]:
    layers = [str(item) for item in spec.get("resistance_layers") or []]
    if not layers:
        raise SystemExit("wat_analytical_rc profile declares no resistance_layers")
    metals = [item for item in layers if item.startswith("metal")]
    via_host = metals[0] if metals else layers[0]

    segments = [WireSegment(layer=layer, length_um=10.0, width_um=1.0) for layer in layers]
    for target in spec.get("contact_targets") or []:
        segments.append(
            WireSegment(
                layer=str(target), length_um=1.0, width_um=1.0,
                contacts=1, contact_target=str(target),
            )
        )
    for target in spec.get("via_targets") or []:
        segments.append(
            WireSegment(
                layer=via_host, length_um=1.0, width_um=1.0,
                vias=1, via_target=str(target),
            )
        )

    pairs = []
    for pair in spec.get("coupling_pairs") or []:
        lower, _, upper = str(pair).partition("-")
        pairs.append(
            CouplingPair(
                lower=lower, upper=upper,
                overlap_area_um2=1.0, edge_length_um=1.0,
            )
        )
    return segments, pairs


def main() -> int:
    targets = wat_profiles()
    if not targets:
        print("WAT analytical PEX smoke: no wat_analytical_rc profiles found")
        return 0

    for profile, pex_profile in targets:
        process = load_process(profile, ROOT)
        spec = process.pex_doc["profiles"][pex_profile]
        reference = yamlish.load(resolve_reference(profile, spec).read_text())
        segments, pairs = canonical_probe(spec)
        report = build_wat_rc_report(
            process.pex_doc, reference, segments, pairs, profile_name=pex_profile
        )
        assert report["signoff"] is False, profile
        assert report["calibrated_to_current_d35"] is False, profile
        assert report["coefficient_set"], profile
        assert report["coefficient_set_provenance"].get("authority"), profile
        for segment in report["segments"]:
            assert segment["resistance_ohm"] > 0, (profile, segment)
        assert report["coupling"], profile
        for pair in report["coupling"]:
            assert pair["capacitance_aF"] > 0, (profile, pair)
        print(
            f"  {profile}/{pex_profile}: set={report['coefficient_set']} "
            f"({report['coefficient_set_verification']}) "
            f"R={report['resistance_ohm']:.4g} ohm over {len(report['segments'])} "
            f"segments, C={report['capacitance_aF']:.4g} aF over "
            f"{len(report['coupling'])} pairs, signoff={report['signoff']}"
        )

    print("WAT analytical PEX smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
