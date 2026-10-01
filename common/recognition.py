"""Backend-neutral derived-layer and device-recognition expressions.

The IR intentionally describes topology, not a particular layout engine.  A
backend supplies layer resolution, database units, and (for CONNECTED_TO) an
explicit connectivity resolver.  No connectivity is inferred from geometric
proximity by default.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping


RECOGNITION_OPS = frozenset(
    {
        "and",
        "or",
        "not",
        "interact",
        "enclose",
        "inside",
        "touch",
        "overlap",
        "holes",
        "grow",
        "shrink",
        "connected_to",
    }
)


class RecognitionError(ValueError):
    """Raised when a recognition expression is malformed or unsupported."""


@dataclass(frozen=True)
class RecognitionExpr:
    """Immutable expression node for a derived layer or device terminal."""

    op: str
    args: tuple["RecognitionExpr", ...] = ()
    value: str | float | None = None

    def __post_init__(self) -> None:
        if self.op == "layer":
            if not isinstance(self.value, str) or not self.value.strip():
                raise RecognitionError("layer expressions require a non-empty name")
            if self.args:
                raise RecognitionError("layer expressions cannot have arguments")
            return
        if self.op not in RECOGNITION_OPS:
            raise RecognitionError(f"unknown recognition operator {self.op!r}")
        if self.value is not None and self.op not in {"grow", "shrink"}:
            raise RecognitionError(f"{self.op} does not accept a scalar value")

    @classmethod
    def layer(cls, name: str) -> "RecognitionExpr":
        return cls("layer", value=name)

    def references(self) -> tuple[str, ...]:
        """Return referenced raw/derived layer names in stable traversal order."""
        if self.op == "layer":
            return (str(self.value),)
        return tuple(name for arg in self.args for name in arg.references())

    def as_dict(self) -> Any:
        """Serialize to the normalized YAML/JSON expression shape."""
        if self.op == "layer":
            return self.value
        if self.op in {"and", "or"}:
            return {self.op: [arg.as_dict() for arg in self.args]}
        if self.op in {"not", "holes"}:
            return {self.op: self.args[0].as_dict()}
        if self.op in {"interact", "enclose", "inside", "touch", "overlap", "connected_to"}:
            return {self.op: [arg.as_dict() for arg in self.args]}
        if self.op in {"grow", "shrink"}:
            return {
                self.op: {
                    "expr": self.args[0].as_dict(),
                    "distance_um": self.value,
                }
            }
        raise RecognitionError(f"cannot serialize operator {self.op!r}")


def _parse_args(op: str, raw: Any, *, count: int | None = None) -> tuple[RecognitionExpr, ...]:
    if not isinstance(raw, list):
        raise RecognitionError(f"{op} requires a list of expressions")
    if count is not None and len(raw) != count:
        raise RecognitionError(f"{op} requires exactly {count} expressions")
    if count is None and not raw:
        raise RecognitionError(f"{op} requires at least one expression")
    return tuple(parse_expression(item) for item in raw)


def parse_expression(raw: Any) -> RecognitionExpr:
    """Parse a scalar or one-operator mapping into a normalized expression."""
    if isinstance(raw, str):
        return RecognitionExpr.layer(raw)
    if not isinstance(raw, Mapping) or len(raw) != 1:
        raise RecognitionError("recognition expressions must be a layer name or one-operator mapping")

    op, value = next(iter(raw.items()))
    op = str(op).lower()
    if op == "layer":
        if not isinstance(value, str) or not value.strip():
            raise RecognitionError("layer expressions require a non-empty name")
        return RecognitionExpr.layer(value)
    if op not in RECOGNITION_OPS:
        raise RecognitionError(f"unknown recognition operator {op!r}")
    if op in {"and", "or"}:
        return RecognitionExpr(op, _parse_args(op, value))
    if op in {"not", "holes"}:
        return RecognitionExpr(op, _parse_args(op, [value], count=1))
    if op in {"interact", "enclose", "inside", "touch", "overlap", "connected_to"}:
        return RecognitionExpr(op, _parse_args(op, value, count=2))
    if not isinstance(value, Mapping) or set(value) != {"expr", "distance_um"}:
        raise RecognitionError(f"{op} requires expr and distance_um")
    distance = value["distance_um"]
    if isinstance(distance, bool) or not isinstance(distance, (int, float)):
        raise RecognitionError(f"{op}.distance_um must be numeric")
    if not math.isfinite(float(distance)) or float(distance) < 0.0:
        raise RecognitionError(f"{op}.distance_um must be finite and non-negative")
    return RecognitionExpr(
        op,
        (parse_expression(value["expr"]),),
        float(distance),
    )


def parse_derived_layers(document: Mapping[str, Any]) -> dict[str, RecognitionExpr]:
    """Parse a document's optional ``derived_layers`` registry."""
    raw = document.get("derived_layers") or {}
    if not isinstance(raw, Mapping):
        raise RecognitionError("derived_layers must be a mapping")
    result: dict[str, RecognitionExpr] = {}
    for name, expression in raw.items():
        key = str(name)
        if not key:
            raise RecognitionError("derived layer names must be non-empty")
        result[key] = parse_expression(expression)
    return result
def _strict_touch(left: Any, right: Any) -> Any:
    """Return left-hand polygons that touch right without positive-area overlap."""
    if not hasattr(left, "each") or not hasattr(right, "each"):
        method = getattr(left, "strictly_touching", None)
        if callable(method):
            return method(right)
        raise RecognitionError(
            "touch requires a KLayout Region-like backend with polygon iteration"
        )
    result = type(left)()
    right_polygons = tuple(right.each())
    for left_polygon in left.each():
        left_region = type(left)(left_polygon)
        for right_polygon in right_polygons:
            right_region = type(left)(right_polygon)
            if left_region.interacting(right_region).is_empty():
                continue
            if not (left_region & right_region).is_empty():
                continue
            result.insert(left_polygon)
            break
    return result


def _quantize_distance(distance_um: float, dbu: float, op: str) -> int:
    if isinstance(dbu, bool) or not isinstance(dbu, (int, float)):
        raise RecognitionError("dbu must be a finite positive number")
    dbu_value = float(dbu)
    if not math.isfinite(dbu_value) or dbu_value <= 0.0:
        raise RecognitionError("dbu must be a finite positive number")
    distance = float(distance_um) / dbu_value
    if not math.isfinite(distance) or distance < 0.0:
        raise RecognitionError(f"{op} distance must be finite and non-negative")
    # A non-zero physical operation must not silently round to a no-op.
    return int(math.ceil(distance)) if distance else 0




def compile_klayout(
    expression: RecognitionExpr,
    resolve_layer: Callable[[str], Any],
    universe: Any,
    dbu: float,
    *,
    connected_to: Callable[[Any, Any], Any] | None = None,
    universe_source: str | None = None,
) -> Any:
    """Compile an expression to a KLayout-like ``Region`` object.

    ``universe_source`` is a required provenance label for complement
    expressions.  Passing a region without naming its source is ambiguous
    because complement semantics depend on the chosen cell boundary.
    """
    _quantize_distance(0.0, dbu, expression.op)
    if universe_source is not None and (
        not isinstance(universe_source, str) or not universe_source.strip()
    ):
        raise RecognitionError("universe_source must be a non-empty label")
    op = expression.op
    if op == "layer":
        return resolve_layer(str(expression.value))
    args = [
        compile_klayout(
            arg,
            resolve_layer,
            universe,
            dbu,
            connected_to=connected_to,
            universe_source=universe_source,
        )
        for arg in expression.args
    ]
    if op == "and":
        result = args[0]
        for arg in args[1:]:
            result = result & arg
        return result
    if op == "or":
        result = args[0]
        for arg in args[1:]:
            result = result + arg
        return result
    if op == "not":
        if universe_source is None:
            raise RecognitionError(
                "not requires an explicit universe_source label"
            )
        if universe is None:
            raise RecognitionError(
                f"not universe source {universe_source!r} resolved to None"
            )
        return universe - args[0]
    if op == "interact":
        return args[0].interacting(args[1])
    if op == "overlap":
        return args[0] & args[1]
    if op == "touch":
        return _strict_touch(args[0], args[1])
    if op == "inside":
        return args[0].inside(args[1])
    if op == "enclose":
        return args[1].inside(args[0])
    if op == "holes":
        return args[0].holes()
    if op in {"grow", "shrink"}:
        distance = _quantize_distance(float(expression.value), dbu, op)
        if op == "shrink":
            distance = -distance
        return args[0].sized(distance)
    if op == "connected_to":
        if connected_to is None:
            raise RecognitionError("connected_to requires an explicit backend resolver")
        return connected_to(args[0], args[1])
    raise RecognitionError(f"cannot compile operator {op!r}")


def compile_derived_layers(
    expressions: Mapping[str, RecognitionExpr],
    resolve_layer: Callable[[str], Any],
    universe: Any,
    dbu: float,
    *,
    connected_to: Callable[[Any, Any], Any] | None = None,
    universe_source: str | None = None,
) -> dict[str, Any]:
    """Compile a registry with cycle detection and explicit universe provenance."""
    cache: dict[str, Any] = {}
    resolving: set[str] = set()

    def resolve(name: str) -> Any:
        if name in cache:
            return cache[name]
        expression = expressions.get(name)
        if expression is None:
            return resolve_layer(name)
        if name in resolving:
            raise RecognitionError(f"cyclic derived-layer reference involving {name!r}")
        resolving.add(name)
        try:
            value = compile_klayout(
                expression,
                resolve,
                universe,
                dbu,
                connected_to=connected_to,
                universe_source=universe_source,
            )
        finally:
            resolving.remove(name)
        cache[name] = value
        return value

    for name in expressions:
        resolve(name)
    return cache


__all__ = [
    "RECOGNITION_OPS",
    "RecognitionError",
    "RecognitionExpr",
    "compile_derived_layers",
    "compile_klayout",
    "parse_derived_layers",
    "parse_expression",
]
