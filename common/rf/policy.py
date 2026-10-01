"""Project-level analysis policy for the conservative RF workbench.

These limits are analysis-envelope choices, not physical process capabilities.
Callers may supply a different policy for a different project or study.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RFAnalysisPolicy:
    """Frequency and die-size envelope for one RF analysis run."""

    name: str
    min_frequency_hz: float
    max_frequency_hz: float
    max_die_um: float
    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RF analysis policy name must be non-empty")
        limits = (
            self.min_frequency_hz,
            self.max_frequency_hz,
            self.max_die_um,
        )
        if any(not math.isfinite(float(value)) or float(value) <= 0.0 for value in limits):
            raise ValueError("RF analysis policy limits must be finite and positive")
        if self.min_frequency_hz > self.max_frequency_hz:
            raise ValueError("RF analysis policy minimum frequency exceeds its maximum")


    def as_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "min_frequency_hz": self.min_frequency_hz,
            "max_frequency_hz": self.max_frequency_hz,
            "max_die_um": self.max_die_um,
        }


PROJECT_RF_POLICY = RFAnalysisPolicy(
    name="project_l0_default",
    min_frequency_hz=1.0e9,
    max_frequency_hz=3.0e9,
    max_die_um=5000.0,
)


__all__ = ["PROJECT_RF_POLICY", "RFAnalysisPolicy"]
