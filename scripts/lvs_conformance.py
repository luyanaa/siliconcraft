#!/usr/bin/env python3
"""siliconcraft LVS conformance — reference vs authoritative netlists.

Runs both LVS extractors on the same layout and diffs the extracted SPICE
netlists (device lines only; header comments differ).  Identical netlists
are the gate; any difference fails (non-zero exit) so CI can enforce it.

Usage:
  python3 scripts/lvs_conformance.py --profile ami06 --layout <in.gds> \
      --workdir build/lvs_conformance [--klayout ...]
"""

import argparse
import sys
from pathlib import Path

import run_lvs

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--workdir", default="build/lvs_conformance")
    ap.add_argument("--klayout", default="klayout")
    args = ap.parse_args()

    profile_dir = ROOT / "profiles" / args.profile
    if not (profile_dir / "generated" / "lvs" / "run.py").exists():
        raise SystemExit("authoritative LVS deck not generated; "
                         "run: python3 scripts/gen_lvs.py --profile "
                         f"{args.profile}")

    results = {}
    for deck in ("reference", "authoritative"):
        summary, spice = run_lvs.extract(profile_dir, args.layout, deck,
                                         args.workdir, args.klayout)
        results[deck] = (summary, spice)

    def device_lines(path):
        """Electrical content of each device line, ignoring instance names.

        The reference and authoritative extraction paths assign device instance
        names independently (the reference path even reuses `m1` for two
        different MOS devices), so the leading instance token carries no
        connectivity meaning and must not decide conformance.  Real LVS matches
        devices by topology and parameters, so compare everything after the
        instance name: device type, terminals, and parameters.  Net names are
        retained, so connectivity differences still fail.
        """
        lines = []
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("."):
                continue
            fields = line.split(None, 1)
            if len(fields) < 2:
                continue
            lines.append(fields[1])
        return sorted(lines)

    ref_lines = device_lines(results["reference"][1])
    auth_lines = device_lines(results["authoritative"][1])
    print(f"lvs_conformance {args.profile} on {args.layout}")
    print(f"  reference devices: {results['reference'][0].get('devices')} "
          f"nets: {results['reference'][0].get('nets')}")
    print(f"  authoritative devices: {results['authoritative'][0].get('devices')} "
          f"nets: {results['authoritative'][0].get('nets')}")
    if ref_lines == auth_lines:
        print("[lvs_conformance] PASS: netlists identical")
        return 0
    print("[lvs_conformance] FAIL: netlists differ", file=sys.stderr)
    for a, b in zip(ref_lines, auth_lines):
        if a != b:
            print(f"  ref : {a}", file=sys.stderr)
            print(f"  auth: {b}", file=sys.stderr)
    if len(ref_lines) != len(auth_lines):
        print(f"  ref {len(ref_lines)} lines vs auth {len(auth_lines)} lines",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
