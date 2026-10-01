#!/usr/bin/env python3
"""Validate the external GF180/SG13G2 device-oracle boundary."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.devices.oracle import OracleError  # noqa: E402
from common.devices.gf180_device_oracle import gf180_device_oracle  # noqa: E402
from common.devices.sg13g2_device_oracle import sg13g2_device_oracle  # noqa: E402


CASE = {
    "id": "mos4_contract",
    "canonical_family": "mos4",
    "terminals": ["d", "g", "s", "b"],
    "terminal_order": ["d", "g", "s", "b"],
    "terminal_map": {"d": "drain", "g": "gate", "s": "source", "b": "bulk"},
    "attributes": {"voltage_class": "lv"},
}
OBSERVATION = {
    "canonical_family": "mos4",
    "terminals": ["b", "s", "g", "d"],
    "terminal_order": ["d", "g", "s", "b"],
    "terminal_map": {"d": "drain", "g": "gate", "s": "source", "b": "bulk"},
    "attributes": {"voltage_class": "lv", "source": "external"},
}


def write_artifacts(root: Path, oracle_name: str, manifest_name: str, observation: dict) -> None:
    manifest = f"""oracle: {oracle_name}
source:
  kind: external
  artifact: unit-test-official-output
  revision: unit-test-revision
cases:
  - id: mos4_contract
    canonical_family: mos4
    terminals:
      - d
      - g
      - s
      - b
    terminal_order:
      - d
      - g
      - s
      - b
    terminal_map:
      d: drain
      g: gate
      s: source
      b: bulk
    attributes:
      voltage_class: lv
observations: observations.yaml
"""
    (root / manifest_name).write_text(manifest)
    attrs = observation.get("attributes", {})
    (root / "observations.yaml").write_text(
        """observations:
  mos4_contract:
    canonical_family: mos4
    terminals:
      - b
      - s
      - g
      - d
    terminal_order:
      - d
      - g
      - s
      - b
    terminal_map:
      d: drain
      g: gate
      s: source
      b: bulk
    attributes:
      voltage_class: lv
      source: external
"""
        if attrs
        else "observations: {}\n"
    )


def check_adapter(adapter, name: str, manifest_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"siliconcraft-{name}-oracle-") as directory:
        root = Path(directory)
        write_artifacts(root, name, manifest_name, OBSERVATION)
        report = adapter(root).run()
        assert report.oracle == name
        assert report.cases == ("mos4_contract",)

        (root / "observations.yaml").write_text(
            """observations:
  mos4_contract:
    canonical_family: mos4
    terminals:
      - d
      - g
      - s
    terminal_order:
      - d
      - g
      - s
    terminal_map:
      d: drain
      g: gate
      s: source
    attributes:
      voltage_class: lv
"""
        )
        try:
            adapter(root).run()
        except OracleError as exc:
            assert "terminals" in str(exc)
        else:
            raise AssertionError(f"{name}: malformed oracle observation accepted")


def main() -> int:
    check_adapter(gf180_device_oracle, "gf180", "gf180_device_oracle.yaml")
    check_adapter(sg13g2_device_oracle, "sg13g2", "sg13g2_device_oracle.yaml")
    print("External device oracle contract checks: PASS (GF180 + SG13G2 adapters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
