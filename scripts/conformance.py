#!/usr/bin/env python3
"""siliconcraft DRC conformance -- compare decks on the same layout.

Runs two or more decks (reference / authoritative / official) on a layout and
reports per-rule violation-count deltas.  Deltas listed in the profile's
waivers.yaml are accepted (with provenance); unexplained deltas fail the run
(non-zero exit) so CI can gate on them.

waivers.yaml format (profiles/<proc>/waivers.yaml):
    rule_id: free-form reason / provenance

Usage:
  python3 scripts/conformance.py --profile ami06 --layout <in.gds> \\
      --decks reference,official --workdir build/conformance [--klayout ...]
"""

import argparse
import json
import sys
from pathlib import Path

import yamlish
import run_drc

ROOT = Path(__file__).resolve().parent.parent


def load_waivers(profile_dir: Path):
    p = profile_dir / "waivers.yaml"
    if not p.exists():
        return {}
    return yamlish.load(p.read_text()) or {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--decks", required=True, help="comma-separated, e.g. reference,official")
    ap.add_argument("--workdir", default="build/conformance")
    ap.add_argument("--klayout", default="klayout")
    ap.add_argument("--reference", default=None,
                    help="baseline deck name; default: first of --decks")
    args = ap.parse_args()

    profile_dir = ROOT / "profiles" / args.profile
    decks = [d.strip() for d in args.decks.split(",") if d.strip()]
    if len(decks) < 2:
        raise SystemExit("need at least two decks to compare")
    base = args.reference or decks[0]
    waivers = load_waivers(profile_dir)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    results = {}
    for deck in decks:
        deck_path, spec, deck_name = run_drc.resolve_deck(profile_dir, deck)
        if deck_path is None:
            raise SystemExit(f"deck '{deck}' not available for profile {args.profile}")
        meta, layermap, features = run_drc.load_profile(profile_dir)
        report = workdir / f"{deck_name}.gds"
        summary = run_drc.run_deck(deck_path, spec, meta, layermap, features,
                                   args.layout, report, args.klayout)
        results[deck_name] = summary.get("rule", {})
        (workdir / f"{deck_name}.json").write_text(json.dumps(summary, indent=2))

    base_rules = results[base]
    all_rules = sorted(set(base_rules) | {r for d in results.values() for r in d})
    failures = []
    rows = []
    for rule_id in all_rules:
        counts = {d: results[d].get(rule_id, 0) for d in decks}
        delta = max(counts.values()) - min(counts.values())
        if delta == 0:
            rows.append((rule_id, counts, delta, "ok"))
            continue
        if rule_id in waivers:
            rows.append((rule_id, counts, delta, f"waived: {waivers[rule_id]}"))
        else:
            rows.append((rule_id, counts, delta, "UNEXPLAINED"))
            failures.append(rule_id)

    print(f"conformance {args.profile} on {args.layout}")
    print(f"  decks: {decks}  baseline: {base}  rules: {len(all_rules)}")
    for rule_id, counts, delta, status in rows:
        print(f"  {rule_id:<14} {counts}  delta={delta:<4} {status}")
    out = workdir / "conformance.json"
    out.write_text(json.dumps({
        "profile": args.profile,
        "decks": decks,
        "results": results,
        "failures": failures,
        "waivers": waivers,
    }, indent=2))

    if failures:
        print(f"[conformance] FAIL: {len(failures)} unexplained rule deltas: {failures}")
        return 1
    print("[conformance] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
