"""Thin external-oracle adapter for IHP SG13G2 device observations."""

from __future__ import annotations

from pathlib import Path

from common.devices.oracle import ExternalDeviceOracle, OracleReport, OracleSpec


SG13G2_DEVICE_ORACLE = OracleSpec(
    name="sg13g2",
    root_env="SILICONCRAFT_SG13G2_ORACLE_ROOT",
    manifest_name="sg13g2_device_oracle.yaml",
)


def sg13g2_device_oracle(root: Path | None = None) -> ExternalDeviceOracle:
    """Return an adapter; all process data is loaded from ``root`` at run time."""
    return ExternalDeviceOracle(SG13G2_DEVICE_ORACLE, root)


def run_sg13g2_device_oracle(root: Path | None = None) -> OracleReport:
    return sg13g2_device_oracle(root).run()
