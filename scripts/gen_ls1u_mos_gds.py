#!/usr/bin/env python3
"""Generate the small LS1u NMOS/PMOS GDS extraction fixture."""

from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "common" / "tests" / "magic" / "ls1u_mos_pair.gds"

# LS1u XML drawing-layer contract, datatype 0.
LAYERS = {
    "nwell": 42,
    "pwell": 41,
    "active": 43,
    "nimplant": 45,
    "pimplant": 44,
    "poly": 46,
    "contact": 25,
    "metal1": 49,
}


def record(code: int, data_type: int | None = None, payload: bytes = b"") -> bytes:
    record_type = (code >> 8) & 0xFF
    kind = (code & 0xFF) if data_type is None else data_type
    return struct.pack(">HBB", len(payload) + 4, record_type, kind) + payload


def i2(*values: int) -> bytes:
    return struct.pack(">" + "h" * len(values), *values)


def i4(*values: int) -> bytes:
    return struct.pack(">" + "i" * len(values), *values)


def ascii_record(kind: int, text: str) -> bytes:
    payload = text.encode("ascii")
    if len(payload) % 2:
        payload += b"\0"
    return record(kind, 6, payload)


def gds_real(value: float) -> bytes:
    """Encode one positive GDS-II base-16 real number."""
    if value == 0:
        return b"\0" * 8
    sign = 0x80 if value < 0 else 0
    value = abs(value)
    exponent = 0
    while value >= 1:
        value /= 16
        exponent += 1
    while value < 1 / 16:
        value *= 16
        exponent -= 1
    mantissa = int(round(value * (1 << 56)))
    if mantissa >= (1 << 56):
        mantissa >>= 4
        exponent += 1
    if not -64 <= exponent <= 63:
        raise ValueError(f"GDS real exponent out of range: {exponent}")
    return bytes([sign | (exponent + 64)]) + mantissa.to_bytes(7, "big")


def units() -> bytes:
    # User unit = 1um; database unit = 1nm.
    return record(0x0305, 5, gds_real(1e-6) + gds_real(1e-9))


def boundary(layer: str, x0: int, y0: int, x1: int, y1: int) -> bytes:
    xy = i4(x0, y0, x1, y0, x1, y1, x0, y1, x0, y0)
    return (
        record(0x0800)
        + record(0x0D02, 2, i2(LAYERS[layer]))
        + record(0x0E02, 2, i2(0))
        + record(0x1003, 3, xy)
        + record(0x1100)
    )


def label(layer: str, x: int, y: int, text: str) -> bytes:
    return (
        record(0x0C00)
        + record(0x0D02, 2, i2(LAYERS[layer]))
        + record(0x1602, 2, i2(0))
        + record(0x1003, 3, i4(x, y))
        + ascii_record(0x1906, text)
        + record(0x1100)
    )


def build() -> bytes:
    now = datetime.now()
    stamp = [now.year, now.month, now.day, now.hour, now.minute, now.second]
    dates = i2(*(stamp + stamp))
    out = record(0x0002, 2, i2(600))
    out += record(0x0102, 2, dates)
    out += ascii_record(0x0206, "siliconcraft_ls1u")
    out += units()
    out += record(0x0502, 2, dates)
    out += ascii_record(0x0606, "ls1u_mos_pair")

    # Left: NMOS in pwell.  Right: PMOS in nwell.  Coordinates are nm.
    shapes = [
        ("pwell", 0, 0, 40000, 30000),
        ("nwell", 50000, 0, 90000, 30000),
        ("active", 8000, 10000, 32000, 20000),
        ("nimplant", 8000, 10000, 32000, 20000),
        ("active", 58000, 10000, 82000, 20000),
        ("pimplant", 58000, 10000, 82000, 20000),
        ("active", 2000, 2000, 8000, 8000),
        ("pimplant", 2000, 2000, 8000, 8000),
        ("active", 82000, 2000, 88000, 8000),
        ("nimplant", 82000, 2000, 88000, 8000),
        ("poly", 18000, 4000, 22000, 26000),
        ("poly", 68000, 4000, 72000, 26000),
        ("contact", 8000, 12000, 14000, 18000),
        ("contact", 26000, 12000, 32000, 18000),
        ("contact", 58000, 12000, 64000, 18000),
        ("contact", 76000, 12000, 82000, 18000),
        ("contact", 18000, 4000, 22000, 9000),
        ("contact", 68000, 4000, 72000, 9000),
        ("contact", 2000, 2000, 8000, 8000),
        ("contact", 82000, 2000, 88000, 8000),
        ("metal1", 6000, 11000, 14000, 19000),
        ("metal1", 26000, 11000, 34000, 19000),
        ("metal1", 64000, 11000, 66000, 19000),
        ("metal1", 76000, 11000, 84000, 19000),
        ("metal1", 16000, 4000, 24000, 9000),
        ("metal1", 66000, 4000, 74000, 9000),
        ("metal1", 1000, 1000, 9000, 9000),
        ("metal1", 81000, 1000, 89000, 9000),
    ]
    for shape in shapes:
        out += boundary(*shape)

    labels = [
        ("metal1", 7000, 15000, "nsource"),
        ("metal1", 30000, 15000, "ndrain"),
        ("poly", 20000, 6000, "ngate"),
        ("metal1", 5000, 5000, "vss"),
        ("metal1", 62000, 15000, "psource"),
        ("metal1", 80000, 15000, "pdrain"),
        ("poly", 70000, 6000, "pgate"),
        ("metal1", 85000, 5000, "vdd"),
    ]
    for item in labels:
        out += label(*item)

    out += record(0x0700)
    out += record(0x0400)
    return out


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
