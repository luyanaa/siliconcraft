#!/usr/bin/env python3
"""Compare normal and no-well-routing Magic extraction on one GDS fixture.

The diagnostic technology is derived from the active profile technology by
removing only the normal nwell/pwell self-connect rules.  This is the same
semantic check as the archived ``scmosWR.tech`` variant, but keeps the active
profile's GDS input map and source-driven extract section.
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

from common.pex.magic import assemble_technology, without_well_routing  # noqa: E402
from common.pex.runtime import run_magic_extract  # noqa: E402
from common.process_ir import load_process, profile_names  # noqa: E402

DEFAULT_LAYOUT = ROOT / "common/tests/gds/ami06_drc_test.gds"
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


def connectivity_signature(text: str) -> tuple[tuple[str, ...], ...]:
    """Return device terminal connectivity without parasitic values."""

    rows: list[tuple[str, ...]] = []
    for line in logical_spice_lines(text):
        fields = line.split()
        if not fields:
            continue
        name = fields[0]
        if name.startswith("M") and len(fields) >= 5:
            rows.append(("M", *fields[1:5]))
        elif name.startswith("C") and len(fields) >= 3:
            rows.append(("C", *fields[1:3]))
    return tuple(sorted(rows))


def load_profile(profile: str) -> tuple[dict, Path, str, dict]:
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
    return manifest, manifest_path, reference, process.device_bindings


def check_profile(
    profile: str,
    layout: Path,
    magic: str,
) -> tuple[int, int]:
    manifest, manifest_path, reference, device_bindings = load_profile(profile)
    normal = assemble_technology(
        manifest, reference, manifest_path.parent, device_bindings
    )
    diagnostic = without_well_routing(normal)
    style = str((manifest.get("topology") or {}).get("style"))
    with tempfile.TemporaryDirectory(prefix=f"{profile}-scmos-wr-") as temp:
        workdir = Path(temp)
        normal_tech = workdir / "normal.tech"
        diagnostic_tech = workdir / "scmosWR.tech"
        normal_tech.write_text(normal)
        diagnostic_tech.write_text(diagnostic)
        normal_spice = workdir / "normal.spice"
        diagnostic_spice = workdir / "scmosWR.spice"
        normal_text, _ = run_magic_extract(
            magic,
            layout.resolve(),
            normal_tech,
            normal_spice,
            workdir,
            style,
        )
        diagnostic_text, _ = run_magic_extract(
            magic,
            layout.resolve(),
            diagnostic_tech,
            diagnostic_spice,
            workdir,
            style,
        )

    normal_signature = connectivity_signature(normal_text)
    diagnostic_signature = connectivity_signature(diagnostic_text)
    if not normal_signature:
        raise RuntimeError(f"{profile}: normal extraction has no devices")
    if normal_signature == diagnostic_signature:
        raise RuntimeError(
            f"{profile}: fixture did not expose a normal-vs-scmosWR connectivity change"
        )
    changed = len(set(normal_signature) ^ set(diagnostic_signature))
    print(f"{profile} SCMOS well-route comparison: PASS")
    print(f"  normal connectivity rows: {len(normal_signature)}")
    print(f"  changed connectivity rows: {changed}")
    return len(normal_signature), changed


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
    print("SCMOS normal-vs-scmosWR connectivity gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
