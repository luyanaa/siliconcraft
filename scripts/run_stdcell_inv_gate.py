#!/usr/bin/env python3
"""Compatibility entry point for the AMI06 inverter geometry/LVS gate."""

from pathlib import Path

from run_stdcell_gate import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            {
                "profile": "ami06",
                "architecture": "two_metal_classic",
                "cell": "inv_drc",
                "input": Path("common/tests/spice/stdcell/inv_drc.spice"),
                "schematic": Path("common/tests/spice/stdcell/inv_drc_reference.spice"),
                "workdir": Path("build/stdcell/ami06/inv_gate"),
            }
        )
    )
