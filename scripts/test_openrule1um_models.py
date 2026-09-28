#!/usr/bin/env python3
"""Check OpenRule1um model-card, primitive-symbol, and lambda-rule closure."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import yamlish  # noqa: E402


PROFILE = ROOT / "profiles" / "openrule1um"
MODELS = PROFILE / "models" / "openrule1um.lib"
SYMBOLS = PROFILE / "symbols.yaml"
RULES = PROFILE / "rules.yaml"
LAYERS = PROFILE / "layers.yaml"
CONTRACT = PROFILE / "model_contract.yaml"
CELLS = PROFILE / "cells.yaml"
GENERATED = PROFILE / "generated" / "xschem"
LVS_BATCH = PROFILE / "reference" / "lvs_batch.lylvs"


def _model_names(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^\s*\.model\s+(\S+)", text, re.IGNORECASE | re.MULTILINE)
    }


def _assert_close(actual: float, expected: float, message: str) -> None:
    if abs(actual - expected) > 1e-9:
        raise AssertionError(f"{message}: {actual} != {expected}")

def _assert_relative(actual: float, expected: float, message: str, tolerance: float = 0.05) -> None:
    if abs(actual - expected) > max(abs(expected) * tolerance, 1e-30):
        raise AssertionError(f"{message}: {actual} != {expected}")


def _check_teg_evidence(contract: dict) -> None:
    evidence = contract["measurement_evidence"]
    source = evidence["source"]
    if source["date"] != "2017-09-23" or source["author"] != "akita11":
        raise AssertionError("Phenitec TEG provenance date/author changed unexpectedly")
    if "physical microns" not in evidence["unit_policy"] or "not multiply" not in evidence["unit_policy"]:
        raise AssertionError("TEG unit policy does not prohibit lambda/process-node scaling")

    resistors = evidence["resistors"]
    for model_id in ("r_poly", "r_nwell", "r_pdiff"):
        item = resistors[model_id]
        squares = float(item["l_um"]) / float(item["w_um"])
        raw_sheet = float(item["measured_ohm"]) / squares
        declared_sheet = float(item["sheet_ohm_per_square"])
        card_sheet = float(contract["models"][model_id]["coefficient"]["value"])
        evidence_card_sheet = float(item["model_card_sheet_ohm_per_square"])
        _assert_relative(evidence_card_sheet, card_sheet, f"{model_id}: evidence/model-card sheet value")
        _assert_relative(declared_sheet, raw_sheet, f"{model_id}: TEG sheet value")
        _assert_relative(card_sheet, raw_sheet, f"{model_id}: model-card value")
    if resistors["r_ndiff"]["status"] != "not_measurable":
        raise AssertionError("Nact TEG must remain explicitly non-measurable")
    if not any(item.get("id") == "r_ndiff" for item in contract.get("missing_models") or ()):
        raise AssertionError("Nact TEG without a model card must remain simulator-unavailable")

    capacitors = evidence["capacitors"]
    poly = capacitors["poly_cap"]
    poly_card = float(contract["models"]["poly_cap"]["coefficient"]["value"])
    poly_raw = float(poly["measured_pf"]) * 1e-12 / float(poly["area_um2"])
    _assert_relative(poly_card, poly_raw, "poly_cap: model-card value")
    for model_id in ("ndiff_cap", "pdiff_cap"):
        item = capacitors[model_id]
        area = float(item["area_um2"])
        strong_raw = float(item["accumulation_measured_pf"]) * 1e-12 / area
        strong_card = float(contract["models"][model_id]["coefficient"]["value"])
        weak_raw = float(item["weak_inversion_measured_pf"]) * 1e-12 / area
        weak_card = float(item["weak_inversion_f_per_um2"])
        _assert_relative(strong_card, strong_raw, f"{model_id}: accumulation model-card value")
        _assert_relative(weak_card, weak_raw, f"{model_id}: weak-inversion evidence")



def _check_contract() -> dict:
    contract = yamlish.load(CONTRACT.read_text())
    rules = yamlish.load(RULES.read_text())
    layers = yamlish.load(LAYERS.read_text())
    symbols = yamlish.load(SYMBOLS.read_text()).get("symbols", {})
    cells = yamlish.load(CELLS.read_text())
    _check_teg_evidence(contract)
    r_ndiff_reference = (contract.get("reference_only_models") or {}).get("r_ndiff") or {}
    if (
        r_ndiff_reference.get("status") != "upstream_reference_only"
        or float((r_ndiff_reference.get("coefficient") or {}).get("value")) != 40.0
        or r_ndiff_reference.get("source") != "tech/tech/macros/pcells_v2.lym"
        or any(r_ndiff_reference.get(key) != "unavailable" for key in ("simulator", "lvs", "xschem_symbol"))
    ):
        raise AssertionError("R_ndiff must follow the upstream PCell reference without simulator/LVS exposure")
    r_ndiff_missing = next(
        (item for item in contract.get("missing_models") or () if item.get("id") == "r_ndiff"),
        None,
    )
    if not r_ndiff_missing or r_ndiff_missing.get("status") != "simulator_unavailable":
        raise AssertionError("R_ndiff simulator-card gap is not explicit")
    if "r_ndiff" not in (cells.get("reference_only_models") or ()):
        raise AssertionError("cells.yaml does not expose the upstream R_ndiff reference-only entry")
    r_ndiff_variant = (contract.get("variant_status") or {}).get("r_ndiff") or {}
    if (
        r_ndiff_variant.get("simulator") != "unavailable"
        or r_ndiff_variant.get("pcell") != "available_reference_only"
        or r_ndiff_variant.get("lvs") != "unavailable"
        or float(r_ndiff_variant.get("pcell_sheet_reference")) != 40.0
    ):
        raise AssertionError("R_ndiff variant status does not preserve the upstream reference boundary")

    meta = layers["meta"]
    lambda_rule = contract["lambda_rule"]
    rule_lambda = (rules.get("lambda_rule") or {})
    _assert_close(float(meta["lambda_um"]), float(lambda_rule["lambda_um"]), "profile/model lambda mismatch")
    _assert_close(float(meta["grid_um"]), float(lambda_rule["grid_um"]), "profile/model grid mismatch")
    _assert_close(float(lambda_rule["lambda_um"]), float(rule_lambda["lambda_um"]), "rules/model lambda mismatch")
    _assert_close(float(lambda_rule["grid_um"]), float(rule_lambda["grid_um"]), "rules/model grid mismatch")
    if meta["physical_units"] != "microns" or meta["lambda_is_geometry_scaling"] is not False:
        raise AssertionError("OpenRule1um physical-unit contract incorrectly scales geometry")
    _assert_close(float(meta["nominal_process_um"]), 0.6, "process-node metadata mismatch")
    _assert_close(float(meta["design_rule_um"]), 1.0, "design-rule metadata mismatch")
    if lambda_rule.get("units") != "microns" or lambda_rule.get("geometry_scaling") != "none":
        raise AssertionError("model lambda rule is being treated as a physical-unit scale")
    if contract["family"]["physical_geometry_units"] != "microns" or contract["family"]["lambda_is_geometry_scaling"] is not False:
        raise AssertionError("model family physical-unit contract is inconsistent")
    if rule_lambda.get("units") != "microns":
        raise AssertionError("reference rules do not declare physical micron units")
    models = contract.get("models") or {}
    lvs_only_models = contract.get("lvs_only_models") or {}
    policy = cells["policy"]
    if policy["pcell_policy"] != "preserve_existing":
        raise AssertionError("OpenRule1um cell policy would replace existing PCells")
    if policy["standard_cell_policy"] != "conformance_only":
        raise AssertionError("OpenRule1um standard-cell policy is not conformance-only")
    if policy.get("replacement_required") is not False:
        raise AssertionError("OpenRule1um cell policy unexpectedly requires replacement")
    gds_export = cells["gds_export"]
    converter = gds_export["converter_compatibility"]
    if gds_export["source_hierarchy"] != "preserve_until_primitive_conversion":
        raise AssertionError("OpenRule1um GDS export must preserve source hierarchy before conversion")
    if converter["multi_level_cells"] != "unsupported":
        raise AssertionError("OpenRule1um converter hierarchy limitation is not recorded")
    if converter["flatten_before_primitive_conversion"] != "forbidden":
        raise AssertionError("OpenRule1um export policy permits unsafe pre-conversion flattening")
    if converter["full_chip_flatten"] != "fallback_only":
        raise AssertionError("OpenRule1um export policy does not prefer selective flattening")
    preflight = gds_export["preflight"]
    if preflight["input_artifact"] != "immutable_hierarchical_source":
        raise AssertionError("OpenRule1um export may mutate the hierarchical source")
    if preflight["output_artifact"] != "staging_copy_only":
        raise AssertionError("OpenRule1um flatten output is not isolated to a staging copy")
    if preflight["top_cell_selection"] != "explicit" or preflight["ambiguous_top_cells"] != "reject":
        raise AssertionError("OpenRule1um export does not fail closed on ambiguous top cells")
    if preflight["flatten_scope"] != "reachable_affected_cells_only":
        raise AssertionError("OpenRule1um export policy permits unrelated hierarchy flattening")
    if preflight["prune_orphan_cells"] is not True:
        raise AssertionError("OpenRule1um export policy leaves orphan cells for the converter")
    equivalence = gds_export["equivalence_checks"]
    if equivalence["instance_transforms"] != "required" or equivalence["pin_text_and_properties"] != "required":
        raise AssertionError("OpenRule1um export does not require transform/pin preservation checks")
    if rule_lambda.get("lvs", {}).get("quantization") != "grid":
        raise AssertionError("OpenRule1um LVS lambda policy is not grid-quantized")
    if rule_lambda.get("lvs", {}).get("model_binding") != "exact_model_id":
        raise AssertionError("OpenRule1um LVS lambda policy does not require exact model IDs")
    source_policy = contract["source_policy"]
    if source_policy["simulator"]["authority"] != "model_card":
        raise AssertionError("simulation authority is not the exact model card")
    if source_policy["layout_lvs"]["authority"] != "calibrated_model_card_or_explicit_lvs_reference":
        raise AssertionError("LVS authority does not distinguish calibrated and reference-only values")
    if source_policy["pcell"]["authority"] != "upstream_pcell_reference":
        raise AssertionError("PCell authority is not the pinned upstream reference")
    if source_policy["wl_adjustment"]["allowed"] is not True:
        raise AssertionError("W/L adjustment policy is not enabled")
    if source_policy["numeric_equivalence"]["required_before_clean_claim"] is not True:
        raise AssertionError("numeric model/LVS equivalence can be claimed without closure")
    variants = contract["variant_status"]
    if (
        variants["r_nwell"]["lvs"] != "available"
        or variants["r_nwell"]["lvs_authority"] != "local_profile_adapter"
        or variants["r_nwell"]["simulator_lvs_equivalence"] != "calibrated"
    ):
        raise AssertionError("R_nwell local LVS extraction is not represented explicitly")
    if (
        variants["r_pdiff"]["lvs"] != "available"
        or variants["r_pdiff"]["simulator_lvs_equivalence"] != "calibrated"
        or variants["r_pdiff"]["pcell_equivalence"] != "unresolved"
    ):
        raise AssertionError("R_pdiff source precedence is not represented explicitly")
    if variants["ndiff_cap"]["simulator_lvs_equivalence"] != "calibrated_for_accumulation":
        raise AssertionError("nactive capacitor calibration is not represented explicitly")
    if variants["pdiff_cap"]["simulator_lvs_equivalence"] != "calibrated_for_accumulation":
        raise AssertionError("pactive capacitor calibration is not represented explicitly")
    for model_id in ("ndiff_cap", "pdiff_cap"):
        if variants[model_id]["weak_inversion"] != "evidence_only_not_modelled":
            raise AssertionError(f"{model_id} weak-inversion C-V must not be advertised as a constant model")


    stdcell = cells["standard_cell_conformance"]
    if stdcell["status"] != "materialized_reference_input" or stdcell["required_for_primitive_lvs"] is not False:
        raise AssertionError("OpenRule1um stdcell inputs became an implicit primitive-LVS dependency")
    if stdcell.get("catalog") != "compatibility/stdcell_catalog.yaml":
        raise AssertionError("materialized OpenRule1um stdcell catalog is not selected")
    support = cells["analog_support"]
    if support["status"] != "explicit_read_only_reference" or support["lookup"] != "explicit_instance_only":
        raise AssertionError("analog support-cell boundary is not explicit read-only lookup")
    if support["implicit_pcell_dependency"] != "forbidden" or support["required_for_primitive_lvs"] is not False:
        raise AssertionError("analog support cells became an implicit primitive-LVS dependency")
    _assert_close(
        float(stdcell["checks"]["grid_um"]),
        float(rule_lambda["grid_um"]),
        "stdcell/lambda grid mismatch",
    )


    available_xschem = set(cells.get("available", {}).get("primitive_xschem") or ())
    available_models = set(cells.get("available", {}).get("primitive_models") or ())
    if not available_xschem or not available_models:
        raise AssertionError("OpenRule1um cell coverage declaration is empty")
    missing_xschem = sorted(name for name in available_xschem if name not in symbols)
    if missing_xschem:
        raise AssertionError(f"cells.yaml names primitive symbols that are absent from symbols.yaml: {missing_xschem}")
    missing_models = sorted(name for name in available_models if name not in models)
    if missing_models:
        raise AssertionError(f"cells.yaml names primitive models absent from model_contract.yaml: {missing_models}")
    model_symbols = {entry.get("symbol") for entry in models.values()}
    if not model_symbols.issubset(available_xschem):
        raise AssertionError("cells.yaml primitive_xschem coverage does not include every declared model symbol")
    unavailable_models = {entry["id"] for entry in contract.get("missing_models") or ()}
    declared_symbol_models = {entry.get("model_id") for entry in symbols.values() if entry.get("model_id")}
    if unavailable_models & (set(models) | available_models | declared_symbol_models):
        raise AssertionError("an unavailable model card is exposed through the primitive contract")


    declared = _model_names(MODELS.read_text())
    missing_cards = sorted(set(models) - declared)
    if missing_cards:
        raise AssertionError(f"model contract names cards absent from openrule1um.lib: {missing_cards}")

    for model_id, entry in models.items():
        symbol = entry.get("symbol")
        if symbol not in symbols:
            raise AssertionError(f"{model_id}: missing Xschem symbol {symbol}")
        generated = GENERATED / f"{symbol}.sym"
        if not generated.exists():
            raise AssertionError(f"{model_id}: missing generated symbol {generated}")
        if f"model={model_id}" not in generated.read_text():
            raise AssertionError(f"{model_id}: generated symbol is not bound to that model")
        if entry.get("kind") == "capacitor":
            if entry.get("netlist_geometry_units") != "numeric_um":
                raise AssertionError(f"{model_id}: capacitor geometry-unit convention is not declared")
            template = symbols[symbol].get("template") or {}
            if any(str(template.get(parameter, "")).lower().endswith("u") for parameter in ("w", "l")):
                raise AssertionError(f"{model_id}: passive capacitor template must use numeric micron W/L")
        parameters = entry.get("parameters") or {}
        for parameter in ("w_um", "l_um"):
            spec = parameters.get(parameter)
            if not spec:
                continue
            value = float(spec["default"])
            minimum = float(spec["min"])
            grid = float(lambda_rule["grid_um"])
            if value < minimum or abs(value / grid - round(value / grid)) > 1e-9:
                raise AssertionError(f"{model_id}.{parameter} is outside lambda_rule: {value}")

    for symbol_name, entry in symbols.items():
        model_id = entry.get("model_id")
        if not model_id:
            continue
        if model_id not in models:
            raise AssertionError(f"{symbol_name}: model_id {model_id} is not in model_contract.yaml")
        if "@model" not in entry.get("format", ""):
            raise AssertionError(f"{symbol_name}: normal Xschem format bypasses model {model_id}")

    if any(entry.get("symbol") for entry in lvs_only_models.values()):
        raise AssertionError("LVS-only reference models must not expose simulator symbols")
    return contract


def _check_lvs_coefficients(contract: dict) -> None:
    text = LVS_BATCH.read_text()
    for conflict in contract.get("conflicts") or ():
        model_id = conflict.get("model_id")
        references = conflict.get("lvs_reference_values") or ()
        if not model_id or not references:
            continue
        model_entry = (contract.get("models") or {}).get(model_id) or (contract.get("lvs_only_models") or {}).get(model_id)
        kind = (model_entry or {}).get("kind")
        values = [
            float(value)
            for value in re.findall(
                rf'{re.escape(kind)}\("{re.escape(model_id)}",\s*([0-9.eE+-]+)\)',
                text,
            )
        ]
        for reference in references:
            expected = float(reference["value"])
            if not any(abs(actual - expected) <= max(abs(expected) * 1e-12, 1e-30) for actual in values):
                raise AssertionError(
                    f"{model_id}: declared LVS coefficient {expected} is absent from lvs_batch.lylvs"
                )


def _check_ngspice(contract: dict) -> None:
    ngspice = shutil.which("ngspice") or "ngspice"
    deck = """* OpenRule1um primitive model-card smoke
.lib '{model}' openrule1um
VDD vdd 0 5
VIN vg 0 0
M1 out vg 0 0 or1_nmos W=2u L=1u
M2 vdd vg out vdd or1_pmos W=6u L=1u
R1 rp 0 r_poly W=2u L=10u
R2 rn 0 r_nwell W=2u L=10u
R3 rpd 0 r_pdiff W=2u L=10u
R4 rh 0 hr_poly W=2u L=10u
C1 cp 0 poly_cap W=10 L=10
C2 cn 0 ndiff_cap W=10 L=10
C3 cpp 0 pdiff_cap W=10 L=10
D1 dp 0 or1_diode area=1 pj=0
.op
.end
""".format(model=MODELS)
    with tempfile.TemporaryDirectory(prefix="openrule1um-models-") as tmp:
        deck_path = Path(tmp) / "models.cir"
        log_path = Path(tmp) / "models.log"
        deck_path.write_text(deck)
        proc = subprocess.run(
            [ngspice, "-b", "-o", str(log_path), str(deck_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        log = log_path.read_text() if log_path.exists() else proc.stdout + proc.stderr
        if proc.returncode != 0:
            raise AssertionError(log)
        if "Error:" in log:
            raise AssertionError(log)
        for expected in ("3.06e-13", "5.42e-13", "5.34e-13"):
            if expected not in log:
                raise AssertionError(f"ngspice capacitor geometry does not report measured value {expected}")
        for model_id in contract["models"]:
            if model_id not in log:
                raise AssertionError(f"ngspice smoke did not report model {model_id}")


def main() -> int:
    contract = _check_contract()
    _check_lvs_coefficients(contract)
    _check_ngspice(contract)
    print("OpenRule1um model/symbol/lambda closure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
