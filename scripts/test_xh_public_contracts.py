#!/usr/bin/env python3
"""Validate the XH public PEX, model, characterization, and map contracts."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import yamlish  # noqa: E402
from common.characterization import validate_characterization_manifest  # noqa: E402
from common.layer_map_provenance import (  # noqa: E402
    LayerMapProvenanceError,
    load_reference_map,
    require_tapeout_authority,
)
from common.oracle_overlay import load_oracle_overlay  # noqa: E402
from common.pex.field_solver import canonical_sweep_manifest  # noqa: E402
from common.pex.r_only import (  # noqa: E402
    ROnlyError,
    WireSegment,
    build_r_wire_only_report,
)
from common.process_ir import load_process  # noqa: E402


SCHEMAS = (
    "pex_public_contract.yaml",
    "characterization_contract.yaml",
    "oracle_overlay_contract.yaml",
    "layer_map_provenance.yaml",
)


def check_profile(name: str) -> None:
    profile = ROOT / "profiles" / name
    process = load_process(name, ROOT)
    assert process.capabilities.pex_rc == "public_typical_r_only"
    assert process.parasitic_ownership["metal_interconnect_rc"] == "public_typical_r_only"
    assert process.parasitic_ownership["metal_sheet_resistance"] == "public_typical"
    assert process.parasitic_ownership["interconnect_capacitance"] == "estimated"
    assert process.parasitic_ownership["contact_resistance"] == "unknown"
    assert process.parasitic_ownership["via_resistance"] == "unknown"
    evidence = process.pex_doc["flow"]["electrical_evidence"]
    assert evidence["metal_sheet_resistance"]["status"] == "public_typical"
    assert evidence["diffusion_sheet_resistance"]["status"] == "public_typical"
    assert process.pex_doc["substrate_extraction"]["backend"] == (
        "external_foundry_or_calibrated_substrate_extractor"
    )

    report = build_r_wire_only_report(
        process.pex_doc,
        [WireSegment("metal1", 10.0, 0.56)],
    )
    expected_sheet = {"xh018": 0.095, "xh035": 0.090}[name]
    assert report["mode"] == "R_wire_only"
    assert report["maturity"] == "public_typical"
    assert report["segments"][0]["sheet_resistance_ohm_per_square"] == expected_sheet
    assert report["wire_resistance_ohm"] == expected_sheet * 10.0 / 0.56
    assert report["excluded_terms"]["contact_resistance"] == "unknown"
    assert report["excluded_terms"]["via_resistance"] == "unknown"
    try:
        build_r_wire_only_report(
            process.pex_doc,
            [WireSegment("poly", 1.0, 1.0)],
        )
    except ROnlyError:
        pass
    else:
        raise AssertionError("R-only PEX accepted a non-materialized poly value")

    field = canonical_sweep_manifest(process.pex_doc)
    assert field["maturity"] == "field_solver_estimated"
    assert field["calibrated"] is False
    assert field["solver_candidates"] == ["FastCap", "FasterCap", "Palace"]
    assert len(field["patterns"]) == 7
    assert field["output"]["signoff"] is False

    characterize = yamlish.load((profile / "characterization.yaml").read_text())
    validate_characterization_manifest(characterize, name)
    overlay = load_oracle_overlay(
        yamlish.load((profile / "oracle_overlay.yaml").read_text()), name
    )
    assert overlay.status == "optional_not_installed"
    assert overlay.root({}) is None
    try:
        overlay.root({overlay.root_environment: "relative/private/root"})
    except ValueError:
        pass
    else:
        raise AssertionError("relative private overlay root was accepted")

    models = {model.name: model for model in process.models_ir}
    core = models[f"{name}N"]
    assert core.capabilities.simulator is False
    assert core.evidence.maturity_level == "L0"
    assert core.evidence.model_form == "none"
    hv = models[f"{name}Nhv"]
    assert hv.evidence.model_form == "none"
    hv_l1 = dict(dict(hv.evidence.maturity)["levels"])["L1"]
    assert hv_l1["model_form"] == "bsim4_external_hv_elements"
    ldmos = models[f"{name}Nldmos"]
    assert "non-permutable" in " ".join(ldmos.evidence.limitations) or ldmos.evidence.maturity_level == "L0"

    assert (profile / "pex" / f"{name}_beol_public_fit.yaml").exists()


def main() -> int:
    for schema in SCHEMAS:
        assert isinstance(yamlish.load((ROOT / "schema" / schema).read_text()), dict)
    for name in ("xh018", "xh035"):
        check_profile(name)

    ref_path = ROOT / "profiles/xh018/reference_maps/EFXH018D_lite.yaml"
    reference = load_reference_map(ref_path)
    assert reference["authority"] == "public_reference"
    assert reference["tapeout_eligible"] is False
    anchors = {item["name"]: item["stream_pattern"] for item in reference["numeric_anchors"]}
    assert anchors == {
        "via1": "17/*",
        "via2": "27/*",
        "via3": "29/*",
        "viatp": "51/*",
        "viatpl": "36/*",
    }
    try:
        require_tapeout_authority(
            yamlish.load((ROOT / "profiles/xh018/layers.yaml").read_text())
        )
    except LayerMapProvenanceError:
        pass
    else:
        raise AssertionError("internal XH018 map passed the tapeout authority gate")

    print("XH public PEX/model/characterization/map contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
