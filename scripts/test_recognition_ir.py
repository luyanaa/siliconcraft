#!/usr/bin/env python3
"""Validate recognition AST parsing and the KLayout compiler boundary."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.recognition import (  # noqa: E402
    RecognitionError,
    compile_derived_layers,
    parse_derived_layers,
    parse_expression,
)


KLAYOUT_PROBE = r'''
import os
import pya
import sys
sys.path.insert(0, os.environ["SILICONCRAFT_ROOT"])
from common.recognition import (
    RecognitionError,
    compile_derived_layers,
    compile_klayout,
    parse_derived_layers,
    parse_expression,
)

layout = pya.Layout()
layout.dbu = 0.001
top = layout.create_cell("TOP")
active = layout.layer(1, 0)
poly = layout.layer(2, 0)
top.shapes(active).insert(pya.Box(0, 0, 10000, 10000))
top.shapes(poly).insert(pya.Box(5000, 0, 15000, 10000))
edge = layout.layer(3, 0)
top.shapes(edge).insert(pya.Box(10000, 0, 20000, 10000))
regions = {
    "active": pya.Region(top.begin_shapes_rec(active)),
    "poly": pya.Region(top.begin_shapes_rec(poly)),
    "edge": pya.Region(top.begin_shapes_rec(edge)),
}
universe = pya.Region(pya.Box(-20000, -20000, 30000, 30000))
resolve = lambda name: regions[name]

assert not compile_klayout(
    parse_expression({"and": ["active", "poly"]}), resolve, universe, layout.dbu
).is_empty()
assert not compile_klayout(
    parse_expression({"or": ["active", "poly"]}), resolve, universe, layout.dbu
).is_empty()
assert not compile_klayout(
    parse_expression({"not": "active"}),
    resolve,
    universe,
    layout.dbu,
    universe_source="cell_bbox",
).is_empty()
try:
    compile_klayout(
        parse_expression({"not": "active"}), resolve, universe, layout.dbu
    )
except RecognitionError as exc:
    assert "universe_source" in str(exc)
else:
    raise AssertionError("not compiled without an explicit universe source")
try:
    compile_klayout(
        parse_expression({"and": ["active", "poly"]}), resolve, universe, 0.0
    )
except RecognitionError as exc:
    assert "dbu" in str(exc)
else:
    raise AssertionError("non-positive dbu accepted")
small_grow = compile_klayout(
    parse_expression({"grow": {"expr": "active", "distance_um": 0.0001}}),
    resolve,
    universe,
    layout.dbu,
)
assert small_grow.bbox().width() > regions["active"].bbox().width()
assert not compile_klayout(
    parse_expression(
        {"inside": ["active", {"grow": {"expr": "active", "distance_um": 1.0}}]}
    ),
    resolve,
    universe,
    layout.dbu,
).is_empty()
assert not compile_klayout(
    parse_expression({"enclose": [{"grow": {"expr": "active", "distance_um": 1.0}}, "active"]}),
    resolve, universe, layout.dbu,
).is_empty()
assert not compile_klayout(
    parse_expression({"overlap": ["active", "poly"]}), resolve, universe, layout.dbu
).is_empty()
assert compile_klayout(
    parse_expression({"touch": ["active", "poly"]}), resolve, universe, layout.dbu
).is_empty()
assert not compile_klayout(
    parse_expression({"touch": ["active", "edge"]}), resolve, universe, layout.dbu
).is_empty()
assert compile_klayout(
    parse_expression({"holes": "active"}), resolve, universe, layout.dbu
).is_empty()

connected = compile_klayout(
    parse_expression({"connected_to": ["active", "poly"]}),
    resolve,
    universe,
    layout.dbu,
    connected_to=lambda left, right: left & right,
)
assert not connected.is_empty()
try:
    compile_klayout(parse_expression({"connected_to": ["active", "poly"]}), resolve, universe, layout.dbu)
except Exception as exc:
    assert "explicit backend resolver" in str(exc)
else:
    raise AssertionError("connected_to compiled without a backend resolver")

compiled = compile_derived_layers(
    parse_derived_layers({"derived_layers": {"channel": {"and": ["active", "poly"]}}}),
    resolve,
    universe,
    layout.dbu,
)
assert not compiled["channel"].is_empty()
'''


def run_klayout(klayout: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(KLAYOUT_PROBE)
        probe = Path(handle.name)
    try:
        result = subprocess.run(
            [klayout, "-b", "-r", str(probe)],
            cwd=ROOT,
            env={**os.environ, "SILICONCRAFT_ROOT": str(ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"KLayout recognition probe failed:\n{result.stdout}\n{result.stderr}")
    finally:
        probe.unlink(missing_ok=True)


def main() -> int:
    expression = parse_expression(
        {
            "and": [
                "active",
                {"not": {"grow": {"expr": "hv_marker", "distance_um": 0.2}}},
            ]
        }
    )
    assert expression.as_dict() == {
        "and": ["active", {"not": {"grow": {"expr": "hv_marker", "distance_um": 0.2}}}]
    }
    assert expression.references() == ("active", "hv_marker")
    assert parse_derived_layers({"derived_layers": {"channel": "active"}})["channel"].as_dict() == "active"
    try:
        parse_expression({"unknown": "active"})
    except RecognitionError:
        pass
    else:
        raise AssertionError("unknown recognition operator accepted")
    for raw in ({"layer": None}, {"layer": ""}, {"layer": "   "}):
        try:
            parse_expression(raw)
        except RecognitionError:
            pass
        else:
            raise AssertionError(f"invalid layer expression accepted: {raw!r}")

    cycles = parse_derived_layers({"derived_layers": {"a": "b", "b": "a"}})
    try:
        compile_derived_layers(cycles, lambda name: object(), object(), 1.0)
    except RecognitionError as exc:
        assert "cyclic derived-layer reference" in str(exc)
    else:
        raise AssertionError("cyclic derived-layer registry accepted")

    klayout = shutil.which("klayout")
    if not klayout:
        raise SystemExit("klayout not found; run this test inside the KLayout environment")
    run_klayout(klayout)
    print("Recognition IR checks: PASS (parser + KLayout compiler)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
