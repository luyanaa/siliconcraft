#!/usr/bin/env python3
"""Run matched archived SCMOS backends against the active profile fixture.

The active profile remains source-driven.  This gate selects ``scmos-sub`` for
lambda=0.3 profiles and ``scmos`` for the AMI16 lambda=0.8 profile only as a
legacy geometry/connectivity oracle, then compares primitive MOS connectivity
with the generated active technology.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.pex.magic import assemble_technology  # noqa: E402
from common.pex.runtime import run_magic_extract  # noqa: E402
from common.process_ir import load_process, profile_names  # noqa: E402

DEFAULT_LAYOUT = ROOT / "common/tests/magic/scmos_crosscheck.mag"
DEFAULT_PROFILES = tuple(
    profile
    for profile in profile_names(ROOT)
    if load_process(profile, ROOT).capabilities.pex_runtime
)


def logical_spice_lines(text: str) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("+") and result:
            result[-1] += " " + stripped[1:].strip()
        else:
            result.append(stripped)
    return result


def mos_records(text: str) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for line in logical_spice_lines(text):
        fields = line.split()
        if len(fields) >= 6 and fields[0].startswith("M"):
            rows.append(tuple(fields[1:6]))
    return tuple(sorted(rows))


def mos_polarities(records: tuple[tuple[str, ...], ...]) -> set[str]:
    polarities: set[str] = set()
    for record in records:
        model = record[4].lower()
        if model.startswith("n") or model.endswith("n"):
            polarities.add("n")
        if model.startswith("p") or model.endswith("p"):
            polarities.add("p")
    return polarities

def terminal_signature(
    records: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(record[:3] for record in records))


def load_profile(profile: str) -> tuple[dict, Path, str, dict, dict]:
    process = load_process(profile, ROOT)
    manifest_path = process.profile_dir / "pex" / "manifest.yaml"
    manifest = process.pex_doc
    profiles = manifest.get("profiles") or {}
    reference = next(
        name
        for name, spec in profiles.items()
        if name != "none"
        and isinstance(spec, dict)
        and spec.get("generated") is True
    )
    source = manifest.get("source_technology") or {}
    legacy = source.get("legacy_backend")
    if not isinstance(legacy, dict):
        raise RuntimeError(f"{profile}: source_technology.legacy_backend is missing")
    return manifest, manifest_path, reference, legacy, process.device_bindings


def check_profile(profile: str, layout: Path, magic: str) -> None:
    manifest, manifest_path, reference, legacy, device_bindings = load_profile(profile)
    expected_lambda = legacy.get("expected_lambda_um")
    actual_lambda = (manifest.get("physical") or {}).get("lambda_um")
    if expected_lambda != actual_lambda:
        raise RuntimeError(
            f"{profile}: legacy lambda {expected_lambda!r} does not match active {actual_lambda!r}"
        )
    technology_name = str(legacy.get("technology") or "")
    style = str(legacy.get("extraction_style") or "")
    if not technology_name or not style:
        raise RuntimeError(f"{profile}: incomplete legacy backend selection")
    active_style = str((manifest.get("topology") or {}).get("style"))
    active_technology = assemble_technology(
        manifest, reference, manifest_path.parent, device_bindings
    )
    with tempfile.TemporaryDirectory(prefix=f"{profile}-scmos-legacy-") as temp:
        workdir = Path(temp)
        active_tech = workdir / "active.tech"
        active_tech.write_text(active_technology)
        active_spice = workdir / "active.spice"
        legacy_spice = workdir / "legacy.spice"
        active_text, _ = run_magic_extract(
            magic,
            layout.resolve(),
            active_tech,
            active_spice,
            workdir,
            active_style,
        )
        legacy_text, _ = run_magic_extract(
            magic,
            layout.resolve(),
            Path(technology_name),
            legacy_spice,
            workdir,
            style,
            ignored_fatal_markers=(
                "Unknown layer/datatype",
                "Label on unknown layer/datatype",
            ),
        )

    active_rows = mos_records(active_text)
    legacy_rows = mos_records(legacy_text)
    if not active_rows or not legacy_rows:
        raise RuntimeError(
            f"{profile}: active/legacy extraction did not produce primitive MOS devices"
        )
    required_polarities = {"n", "p"}
    if not required_polarities.issubset(mos_polarities(active_rows)):
        raise RuntimeError(f"{profile}: active extraction is missing an NMOS or PMOS")
    if not required_polarities.issubset(mos_polarities(legacy_rows)):
        models = sorted(record[4] for record in legacy_rows)
        raise RuntimeError(
            f"{profile}: legacy extraction is missing an NMOS or PMOS; models={models}"
        )
    if terminal_signature(active_rows) != terminal_signature(legacy_rows):
        raise RuntimeError(
            f"{profile}: active/legacy drain-gate-source connectivity differs"
        )
    print(f"{profile} legacy SCMOS cross-check: PASS")
    print(f"  selected backend: {technology_name} ({style})")
    print(
        "  primitive MOS rows: "
        f"active={len(active_rows)}, legacy={len(legacy_rows)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=DEFAULT_PROFILES)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--magic", default=os.environ.get("MAGIC", "magic"))
    args = parser.parse_args()
    if not args.layout.exists():
        raise SystemExit(f"missing fixture: {args.layout}")
    profiles = (args.profile,) if args.profile else DEFAULT_PROFILES
    for profile in profiles:
        check_profile(profile, args.layout, args.magic)
    print("SCMOS legacy backend cross-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
