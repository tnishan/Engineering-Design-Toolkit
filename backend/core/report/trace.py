"""Calculation trace records.

Every design check emits both a number and a trace line so the calc report can
show clause, symbolic formula, substituted values, and result the way a hand
calculation would. Nothing in this module knows about HTTP or HTML.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FactorTrace:
    symbol: str
    value: float
    clause: str
    description: str


@dataclass(frozen=True)
class CheckResult:
    check: str  # "moment" | "shear" | "bearing" | "deflection_live" | ...
    label: str
    demand: float
    resistance: float
    units: str
    combo_label: str
    clause: str
    formula: str
    substitution: str
    location_mm: float | None = None
    factors: list[FactorTrace] = field(default_factory=list)
    note: str = ""

    @property
    def ratio(self) -> float:
        if self.resistance == 0:
            return float("inf")
        return abs(self.demand) / abs(self.resistance)

    @property
    def status(self) -> str:
        return "PASS" if self.ratio <= 1.0 else "FAIL"


@dataclass
class DesignOutcome:
    checks: list[CheckResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def governing(self) -> CheckResult | None:
        return max(self.checks, key=lambda c: c.ratio) if self.checks else None

    @property
    def passed(self) -> bool:
        return all(c.status == "PASS" for c in self.checks)

    @property
    def max_ratio(self) -> float:
        return max((c.ratio for c in self.checks), default=0.0)
