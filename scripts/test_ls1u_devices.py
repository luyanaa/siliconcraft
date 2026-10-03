#!/usr/bin/env python3
"""Focused regression checks for LS1u device contracts and model maturity."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import yamlish  # noqa: E402


PROFILE = ROOT / "profiles" / "ls1u"


def main() -> int:
    canonical = yamlish.load(
        (ROOT / "common/devices/canonical/mos.yaml").read_text()
    )
    bindings = yamlish.load((PROFILE / "devices/bindings.yaml").read_text())
    maturity = yamlish.load((PROFILE / "model_maturity.yaml").read_text())
    mos4 = canonical["families"]["mos4"]["device"]
    assert mos4["id"] == "mos4"
    assert mos4["terminals"] == ["d", "g", "s", "b"]
    assert mos4["geometry"]["required"] == ["w", "l"]
    assert mos4["geometry"]["parameter_semantics"]["w"] == (
        "channel width per physical gate finger"
    )
    assert mos4["geometry"]["parameter_semantics"]["nf"].startswith(
        "physical gate-finger"
    )
    assert mos4["symmetry_groups"] == [["d", "s"]]
    assert mos4["parasitics"]["diffusion_sheet_r"] == "pex"
    assert set(canonical["families"]["mos4"]["variants"]) == {
        "nmos_core",
        "pmos_core",
        "nmos_hv_sym",
        "pmos_hv_sym",
        "nmos_isolated",
        "pmos_isolated",
    }

    assert bindings["bindings"]["nmos_core"]["simulation"]["name"] == "LV1UNMOS"
    assert bindings["bindings"]["pmos_core"]["simulation"]["name"] == "LV1UPMOS"
    assert bindings["bindings"]["nmos_core"]["simulation"]["representation"] == "subckt"
    assert bindings["bindings"]["pmos_core"]["simulation"]["representation"] == "subckt"
    assert bindings["bindings"]["nmos_core"]["lvs"]["extracted_class"] == "nfet"
    assert bindings["bindings"]["pmos_core"]["lvs"]["extracted_class"] == "pfet"

    pmos = maturity["models"]["pmos_core"]
    assert pmos["fit"]["parameters"]["vth0_v"] == -0.6
    assert pmos["fit"]["parameters"]["u0_cm2_per_v_s"] == 83.0
    assert pmos["fit"]["fit_window_vsg_v"] == [1.5, 5.0]
    assert pmos["maturity"]["signoff"] is False
    assert maturity["models"]["nmos_core"]["evidence_status"] == "insufficient_for_fit"

    model = (PROFILE / "models/ls1u.lib").read_text()
    assert "* empirical PMOS fit: VTH0=-0.6 V, U0=83 cm^2/V/s" in model
    pmos_block = model.split(".SUBCKT LV1UPMOS", 1)[1].split(".ENDS LV1UPMOS", 1)[0]
    assert "+ U0      = 83.0" in pmos_block
    assert "+ VTH0    = -0.6" in pmos_block

    print("LS1u device and model checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
