#!/usr/bin/env python3
"""Keep C35 engineering maturity separate from estimated PEX data quality."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.process_ir import load_process  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    process = load_process("ams_c35", ROOT)
    maturity = process.model_maturity_doc.get("process_maturity", {})
    scope = maturity.get("scope")
    require(
        isinstance(scope, str)
        and all(
            term in scope
            for term in ("supported core", "MOS", "RPOLY2", "RPOLYH", "PiP")
        )
        and "VERT10" not in scope
        and "non-signoff" in scope,
        (
            "L2 scope must stay limited to supported core devices "
            "and estimated non-signoff PEX"
        ),
    )
    require(maturity.get("level") == "L2", "C35 process maturity must be L2")
    require(
        maturity.get("status") == "engineering_extracted",
        "C35 process maturity must be engineering_extracted",
    )
    require(
        maturity.get("structural", {}).get("status") == "complete"
        and maturity.get("structural", {}).get("scope") == "supported_core_pcell_set",
        "structural completeness must be scoped to supported core PCells",
    )
    require(
        maturity.get("lvs", {}).get("status") == "functional"
        and maturity.get("lvs", {}).get("circuit_level_comparison")
        == "pending_mixed_signal_regression",
        "LVS status must not imply an unrun mixed-signal comparison",
    )
    require(
        maturity.get("pex", {}).get("status") == "engineering_extracted"
        and maturity.get("pex", {}).get("coefficient_quality") == "estimated"
        and maturity.get("pex", {}).get("calibrated") is False
        and maturity.get("pex", {}).get("signoff") is False,
        "engineering extraction must remain distinct from calibration/signoff",
    )
    require(
        maturity.get("physical_layout_limitations", {}).get("VERT10")
        == "contract_only"
        and maturity.get("simulation", {}).get("vert10")
        == "functional_typical_model_only",
        "VERT10 model simulation must not imply physical recognition support",
    )
    unsupported = set(maturity.get("unsupported_devices", []))
    require(
        {
            "RNWELL_JFET",
            "ND_DIODE",
            "PD_DIODE",
            "NWD_DIODE",
            "MIDOX_MODNM",
            "MIDOX_MODPM",
            "LAT2",
        }.issubset(unsupported),
        "unavailable numerical device cards must be explicit unsupported scope",
    )
    require(
        maturity.get("external_validation", {}).get(
            "qualified_ams_pre_post_correlation"
        )
        == "unavailable"
        and maturity.get("external_validation", {}).get("foundry_signoff")
        == "unavailable",
        "external correlation and signoff must remain unavailable",
    )

    flow = process.pex_doc.get("flow", {})
    require(
        flow.get("backend") == "native_manhattan"
        and flow.get("primary_backend") == "klayout_native_rcx",
        "KLayout native RCX must remain the primary C35 backend",
    )
    require(
        flow.get("maturity") == "estimated"
        and flow.get("signoff") is False
        and process.collateral_capabilities.pex_rc == "estimated",
        "PEX coefficient quality must remain estimated and non-signoff",
    )
    require(
        flow.get("optional_crosscheck", {})
        .get("magic", {})
        .get("resistance")
        == "disabled_known_failure",
        "Magic resistance extraction must remain an optional disabled cross-check",
    )
    contact = next(
        (
            directive
            for directive in process.pex_doc["profiles"]["estimated_rcx"][
                "magic_directives"
            ]
            if directive.get("kind") == "contact"
            and directive.get("contact_type") == "ec"
        ),
        None,
    )
    require(
        isinstance(contact, dict)
        and contact.get("value") == 45
        and contact.get("unit") == "ohm_per_contact"
        and "n+ CONT midpoint" in contact.get("source", "")
        and "no C35 coefficient" in contact.get("source", ""),
        "RPOLY2 contact must retain its 45 ohm/cut estimate and provenance",
    )
    contact_provenance = maturity.get("estimated_parameters", {}).get(
        "rpoly2_contact", {}
    )
    require(
        contact_provenance.get("value") == 45
        and contact_provenance.get("unit") == "ohm_per_cut"
        and contact_provenance.get("status") == "estimated"
        and "n+ CONT midpoint" in contact_provenance.get("provenance", "")
        and "not a supplied POLY2-specific value"
        in contact_provenance.get("provenance", ""),
        "RPOLY2 maturity metadata must preserve the 45 ohm/cut estimate provenance",
    )
    print("[test_ams_c35_maturity] L2 scope and estimated-PEX provenance PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
