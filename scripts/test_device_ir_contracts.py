#!/usr/bin/env python3
"""Validate canonical family, binding, geometry, and typed netlist contracts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.devices.netlist import NetlistContract  # noqa: E402
from common.process_ir import (  # noqa: E402
    DeviceBinding,
    ProcessIRError,
    _device_bindings,
    load_process,
    profile_names,
)


def mos_binding() -> DeviceBinding:
    canonical = {
        "id": "mos4",
        "kind": "mos4",
        "terminals": ["d", "g", "s", "b"],
        "terminal_order": ["d", "g", "s", "b"],
        "topology": "symmetric",
        "voltage_class": "lv",
        "oxide_class": "core",
        "threshold_class": "standard",
        "channel_class": "bulk",
        "gate_stack": "core",
        "isolation": "bulk",
        "isolation_topology": "bulk",
        "attributes": {
            "voltage_class": "profile_defined",
            "oxide_class": "profile_defined",
            "threshold_class": "profile_defined",
            "channel_class": "profile_defined",
            "gate_stack": "profile_defined",
            "isolation": "profile_defined",
            "isolation_topology": "profile_defined",
        },
        "geometry": {"mode": "scalable", "required": ["w", "l"]},
        "symmetry_groups": [["d", "s"]],
    }
    return DeviceBinding(
        name="synthetic_mos",
        canonical_variant="synthetic",
        canonical=canonical,
        layout={},
        simulation={
            "representation": "primitive",
            "name": "NMOS_SYNTH",
            "prefix": "m",
            "parameter_transforms": [
                {"operation": "rename", "source": "l", "target": "channel_length"},
                {"operation": "scale", "source": "w", "target": "scaled_w", "factor": 2},
                {"operation": "multiply", "source": "m", "target": "multiplicity", "factor": 3},
                {"operation": "divide", "source": "total_width", "target": "half_total", "factor": 2},
                {"operation": "derive", "target": "derived_width", "expression": "scaled_w * nf"},
                {"operation": "ignore", "source": "unused"},
            ],
        },
        lvs={
            "netgen_class": "NMOS_SYNTH",
            "parameter_transforms": [
                {"operation": "rename", "source": "l", "target": "lvs_length"}
            ],
        },
        raw={
            "terminal_maps": {
                "simulation": {
                    "map": {"d": "D", "g": "G", "s": "S", "b": "B"},
                    "order": ["D", "G", "S", "B"],
                },
                "lvs": {
                    "map": {"d": "drain", "g": "gate", "s": "source", "b": "bulk"},
                    "order": ["bulk", "source", "gate", "drain"],
                },
            }
        },
    )


def check_binding_override() -> None:
    family = {
        "families": {
            "resistor": {
                "device": {
                    "id": "resistor",
                    "kind": "resistor",
                    "terminals": ["p", "n", "substrate"],
                    "terminal_order": ["p", "n", "substrate"],
                    "attributes": {"material": "profile_defined"},
                    "geometry": {"mode": "fixed"},
                },
                "variants": {"resistor3": {"id": "resistor3"}},
            }
        }
    }
    valid = _device_bindings(
        family,
        {
            "bindings": {
                "r": {
                    "canonical_family": "resistor",
                    "canonical_variant": "resistor3",
                    "canonical_attributes": {"material": "poly"},
                }
            }
        },
    )
    assert valid["r"].canonical_attributes == {"material": "poly"}
    assert valid["r"].canonical_id == "resistor3"
    try:
        _device_bindings(
            family,
            {
                "bindings": {
                    "r": {
                        "canonical_family": "resistor",
                        "canonical_variant": "resistor3",
                        "canonical_attributes": {"unsupported": True},
                    }
                }
            },
        )
    except ProcessIRError as exc:
        assert "undeclared attributes" in str(exc)
    else:
        raise AssertionError("undeclared canonical attribute accepted")
    for mode, geometry in (
        ("fixed", {"mode": "fixed"}),
        ("scalable", {"mode": "scalable"}),
        ("enumerated", {"mode": "enumerated", "legal_values": [1, 2]}),
        ("derived", {"mode": "derived", "derive": "w * nf"}),
    ):
        document = {
            "families": {
                "resistor": {
                    "device": {
                        "id": "resistor",
                        "kind": "resistor",
                        "terminals": ["p", "n"],
                        "terminal_order": ["p", "n"],
                        "geometry": geometry,
                        "attributes": {},
                    },
                    "variants": {"default": {}},
                }
            }
        }
        binding = _device_bindings(
            document,
            {
                "bindings": {
                    "r": {
                        "canonical_family": "resistor",
                        "canonical_variant": "default",
                    }
                }
            },
        )["r"]
        assert binding.geometry_mode == mode
    invalid = {
        "families": {
            "resistor": {
                "device": {
                    "id": "resistor",
                    "kind": "resistor",
                    "terminals": ["p", "n"],
                    "terminal_order": ["p", "n"],
                    "geometry": {"mode": "unsupported"},
                    "attributes": {},
                },
                "variants": {"default": {}},
            }
        }
    }
    try:
        _device_bindings(
            invalid,
            {"bindings": {"r": {"canonical_family": "resistor", "canonical_variant": "default"}}},
        )
    except ProcessIRError as exc:
        assert "geometry.mode" in str(exc)
    else:
        raise AssertionError("unsupported geometry mode accepted")


def check_typed_netlist() -> None:
    contract = NetlistContract.from_binding(mos_binding())
    assert contract.oxide_class == "core"
    assert contract.canonical_terminal_order == ("d", "g", "s", "b")
    assert contract.simulation_terminal_order == ("D", "G", "S", "B")
    assert contract.lvs_terminal_order == ("bulk", "source", "gate", "drain")
    nets = {"d": "ND", "g": "NG", "s": "NS", "b": "NB"}
    assert contract.backend_terminal_values(nets, "simulation") == ("ND", "NG", "NS", "NB")
    assert contract.backend_terminal_values(nets, "lvs") == ("NB", "NS", "NG", "ND")
    normalized = contract.normalize_parameters(
        {"w": 1.0, "l": 0.5, "nf": 2, "m": 1, "unused": 7}
    )
    assert normalized["scaled_w"] == 2.0
    assert normalized["multiplicity"] == 3.0
    assert normalized["half_total"] == 1.0
    assert normalized["derived_width"] == 4.0
    assert normalized["channel_length"] == 0.5
    assert "unused" not in normalized
    lvs_normalized = contract.normalize_lvs_parameters(
        {"w": 1.0, "l": 0.5, "nf": 2, "m": 1}
    )
    assert lvs_normalized["lvs_length"] == 0.5
    assert "l" not in lvs_normalized


def check_catalog_and_schema() -> None:
    processes = [load_process(name, ROOT) for name in profile_names(ROOT)]
    assert processes
    for process in processes:
        assert process.device_inventory == process.devices
        assert process.canonical_catalog is not process.canonical_doc
        assert "resistor3" in process.canonical_catalog["families"]["resistor"]["variants"]
        assert "power_device" not in process.canonical_catalog["families"]
        for binding in process.device_bindings.values():
            assert binding.geometry_mode in {"scalable", None}
    schema = json.loads((ROOT / "schema/pdk.yaml.schema").read_text())
    properties = schema["properties"]
    assert {"device_inventory", "device_bindings", "canonical_catalog"} <= set(properties)
    assert schema["$defs"]["parameter_transform"]["properties"]["operation"]["enum"] == [
        "rename", "scale", "multiply", "divide", "derive", "ignore"
    ]


def main() -> int:
    check_binding_override()
    check_typed_netlist()
    check_catalog_and_schema()
    print("Device IR contract checks: PASS (families + bindings + netlist normalization)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
