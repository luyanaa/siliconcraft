#!/usr/bin/env python3
"""Validate the end-to-end collateral contract for every materialized profile."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402

from common.pex.field_solver import canonical_sweep_manifest  # noqa: E402
from common.process_ir import load_process, profile_names  # noqa: E402


ALLOWED_PROMOTIONS = {
    "general_default",
    "source_backed_alternate",
    "blocked",
}


def _load(path: Path) -> dict:
    value = yamlish.load(path.read_text())
    assert isinstance(value, dict), f"{path}: expected mapping"
    return value


def main() -> int:
    matrix_path = ROOT / "schema/profile_collateral_matrix.yaml"
    matrix = _load(matrix_path)
    profiles = matrix.get("profiles") or {}
    discovered = set(profile_names(ROOT))
    assert set(profiles) == discovered, (set(profiles) ^ discovered)
    assert matrix["defaults"]["general"]["profile"] == "ami06"
    assert profiles["ami06"]["promotion"] == "general_default"
    assert all(
        entry.get("promotion") in ALLOWED_PROMOTIONS
        for entry in profiles.values()
    )

    for name in sorted(discovered):
        process = load_process(name, ROOT)
        entry = profiles[name]
        xschem = entry["xschem"]
        for key in ("symbols", "netlist"):
            assert (ROOT / xschem[key]).exists(), f"{name}: missing {key}"
        if xschem["status"] == "source_backed":
            assert xschem.get("smoke") not in (None, "unavailable")
            assert (ROOT / xschem["smoke"]).exists()
            assert process.collateral_capabilities.xschem, f"{name}: xschem capability not materialized"
        else:
            assert xschem["status"] == "contract_only"
            assert xschem.get("smoke") == "unavailable"
            assert not process.collateral_capabilities.xschem

        spice = entry["spice"]
        if spice["status"].startswith("simulatable"):
            library = ROOT / spice["library"]
            assert library.exists(), f"{name}: missing model library"
            text = library.read_text()
            for section in spice["sections"]:
                assert f".lib {section}" in text.lower(), f"{name}: missing .lib {section}"
            assert spice["devices"], f"{name}: no SPICE device identities"
        else:
            assert spice["status"] == "contract_only"
            assert spice["library"] is None
            assert (ROOT / f"profiles/{name}/model_maturity.yaml").exists()

        extraction = entry["extraction"]
        manifest_path = ROOT / extraction["manifest"]
        assert manifest_path.exists(), f"{name}: missing extraction manifest"
        manifest = _load(manifest_path)
        if extraction["route"] == "field_solver":
            sweep = canonical_sweep_manifest(
                manifest, profile_name=extraction["profile"]
            )
            assert sweep["calibrated"] is False
            assert sweep["signoff"] is False
            field_solver = entry.get("field_solver") or {}
            source = field_solver.get("source")
            assert source and (ROOT / source).exists(), (
                f"{name}: missing field-solver source {source!r}"
            )
        elif extraction["route"] == "deferred":
            assert extraction["runtime"] is False
            assert extraction["rc"] is False
            assert manifest.get("status") in {"deferred", "unavailable"}
        elif extraction["route"] == "magic_pex":
            assert extraction["topology"] is True
            assert extraction["profile"] in (manifest.get("profiles") or {})
        elif extraction["route"] == "public_r_only":
            assert extraction["profile"] in (manifest.get("profiles") or {})
            spec = manifest["profiles"][extraction["profile"]]
            assert spec.get("extractor") == "r_only_python"
        elif extraction["route"] == "wat_analytical_rc":
            profiles_doc = manifest.get("profiles") or {}
            assert extraction["profile"] in profiles_doc
            spec = profiles_doc[extraction["profile"]]
            assert spec.get("extractor") == "wat_analytical_rc"
            assert spec.get("calibrated_to_current_d35") is False
            reference = spec.get("reference_data")
            assert reference, f"{name}: wat_analytical_rc needs reference_data"
            assert (ROOT / f"profiles/{name}/pex" / reference).exists(), (
                f"{name}: missing WAT reference {reference!r}"
            )
            assert extraction["rc"] == "historical_measured_rc"
            # the declared field-solver companion must still be a real contract
            fs_profile = "field_solver_estimated"
            assert fs_profile in profiles_doc, (
                f"{name}: wat_analytical_rc profiles must also declare "
                f"{fs_profile!r}"
            )
            sweep = canonical_sweep_manifest(manifest, profile_name=fs_profile)
            assert sweep["calibrated"] is False
            assert sweep["signoff"] is False
            field_solver = entry.get("field_solver") or {}
            source = field_solver.get("source")
            assert source and (ROOT / source).exists(), (
                f"{name}: missing field-solver source {source!r}"
            )
        else:
            raise AssertionError(f"{name}: unknown extraction route")

    print(f"Profile collateral matrix: PASS ({len(discovered)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
