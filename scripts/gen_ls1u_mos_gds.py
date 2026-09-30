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
        ("pwell", -1000, -1000, 41000, 31000),
        ("nwell", 49000, -1000, 94000, 31000),
        ("active", 12000, 10000, 36000, 20000),
        ("nimplant", 11000, 9000, 37000, 21000),
        ("active", 54000, 10000, 78000, 20000),
        ("pimplant", 53000, 9000, 79000, 21000),
        ("active", 2000, 2000, 8000, 8000),
        ("pimplant", 1000, 1000, 9000, 9000),
        ("active", 84000, 2000, 90000, 8000),
        ("nimplant", 83000, 1000, 91000, 9000),
        ("poly", 18000, 4000, 22000, 26000),
        ("poly", 68000, 4000, 72000, 26000),
        ("contact", 14500, 14500, 15500, 15500),
        ("contact", 32500, 14500, 33500, 15500),
        ("contact", 56500, 14500, 57500, 15500),
        ("contact", 74500, 14500, 75500, 15500),
        ("contact", 19500, 5000, 20500, 6000),
        ("contact", 69500, 5000, 70500, 6000),
        ("contact", 4500, 4500, 5500, 5500),
        ("contact", 84500, 3500, 85500, 4500),
        ("metal1", 14000, 14000, 16000, 16000),
        ("metal1", 32000, 14000, 34000, 16000),
        ("metal1", 56000, 14000, 58000, 16000),
        ("metal1", 74000, 14000, 76000, 16000),
        ("metal1", 19000, 4500, 21000, 6500),
        ("metal1", 69000, 4500, 71000, 6500),
        ("metal1", 4000, 4000, 6000, 6000),
        ("metal1", 84000, 3000, 86000, 5000),
    ]
    for shape in shapes:
        out += boundary(*shape)

    labels = [
        ("metal1", 15000, 15000, "nsource"),
        ("metal1", 33000, 15000, "ndrain"),
        ("poly", 20000, 5500, "ngate"),
        ("metal1", 5000, 5000, "vss"),
        ("metal1", 57000, 15000, "psource"),
        ("metal1", 75000, 15000, "pdrain"),
        ("poly", 70000, 5500, "pgate"),
        ("metal1", 85000, 4000, "vdd"),
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
