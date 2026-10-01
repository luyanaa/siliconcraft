"""Thin external-oracle adapter for GF180MCU device observations."""

from __future__ import annotations

from pathlib import Path

from common.devices.oracle import ExternalDeviceOracle, OracleReport, OracleSpec


GF180_DEVICE_ORACLE = OracleSpec(
    name="gf180",
    root_env="SILICONCRAFT_GF180_ORACLE_ROOT",
    manifest_name="gf180_device_oracle.yaml",
)


def gf180_device_oracle(root: Path | None = None) -> ExternalDeviceOracle:
    """Return an adapter; all process data is loaded from ``root`` at run time."""
    return ExternalDeviceOracle(GF180_DEVICE_ORACLE, root)


def run_gf180_device_oracle(root: Path | None = None) -> OracleReport:
    return gf180_device_oracle(root).run()
