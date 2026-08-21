"""Load combinations - NBC 2020 Table 4.1.3.2, adopted by OBC 2024 Div. B Part 4.

Cases: D (dead), L (live/occupancy), S (snow), W (wind).
Earthquake (E) is out of scope for gravity beam design.

ULS combinations return factors applied to *specified* loads.
Each principal-load case is paired with its companion factors; the 0.9D
counterparts are included so that load-reversal cases (uplift under wind)
are captured when dead load resists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CASES = ("D", "L", "S", "W")


@dataclass(frozen=True)
class Combination:
    label: str
    factors: dict[str, float]
    limit_state: str  # "ULS" or "SLS"
    kd_duration: str  # governing load duration for CSA O86 K_D, per Cl. 5.3.2
    note: str = ""

    def factor(self, case: str) -> float:
        return self.factors.get(case, 0.0)


@dataclass
class CombinationSet:
    uls: list[Combination] = field(default_factory=list)
    sls: list[Combination] = field(default_factory=list)

    def all(self) -> list[Combination]:
        return self.uls + self.sls


def _nonzero(factors: dict[str, float]) -> dict[str, float]:
    return {k: v for k, v in factors.items() if v}


def _label(factors: dict[str, float]) -> str:
    parts = []
    for case in CASES:
        f = factors.get(case, 0.0)
        if f:
            parts.append(f"{f:g}{case}")
    return " + ".join(parts) if parts else "0"


def uls_combinations(
    include_wind: bool = True,
    dead_can_resist: bool = False,
) -> list[Combination]:
    """NBC 2020 Table 4.1.3.2 ultimate limit states combinations.

    ``dead_can_resist`` adds the 0.9D counterparts, which only govern when
    dead load acts opposite to the principal load (e.g. wind uplift).
    """
    combos: list[Combination] = []

    # Case 1: 1.4D
    combos.append(
        Combination("1.4D", {"D": 1.4}, "ULS", "permanent",
                    "NBC 2020 T4.1.3.2 Case 1 - dead load alone, permanent duration")
    )

    # Case 2: 1.25D + 1.5L + companion (1.0S or 0.4W)
    for comp_label, comp in (("S", {"S": 1.0}), ("W", {"W": 0.4}), ("none", {})):
        if comp_label == "W" and not include_wind:
            continue
        f = _nonzero({"D": 1.25, "L": 1.5, **comp})
        combos.append(
            Combination(_label(f), f, "ULS", "standard",
                        "NBC 2020 T4.1.3.2 Case 2 - live principal")
        )

    # Case 3: 1.25D + 1.5S + companion (1.0L or 0.4W)
    for comp_label, comp in (("L", {"L": 1.0}), ("W", {"W": 0.4}), ("none", {})):
        if comp_label == "W" and not include_wind:
            continue
        f = _nonzero({"D": 1.25, "S": 1.5, **comp})
        combos.append(
            Combination(_label(f), f, "ULS", "short",
                        "NBC 2020 T4.1.3.2 Case 3 - snow principal, short-term duration")
        )

    # Case 4: 1.25D + 1.4W + companion (0.5L or 0.5S)
    if include_wind:
        for comp in ({"L": 0.5}, {"S": 0.5}, {}):
            f = _nonzero({"D": 1.25, "W": 1.4, **comp})
            combos.append(
                Combination(_label(f), f, "ULS", "short",
                            "NBC 2020 T4.1.3.2 Case 4 - wind principal, short-term duration")
            )

    if dead_can_resist:
        counterparts = []
        for c in combos:
            if c.factors.get("D") and len(c.factors) > 1:
                f = dict(c.factors)
                f["D"] = 0.9
                counterparts.append(
                    Combination(_label(f), f, "ULS", c.kd_duration,
                                "0.9D counterpart - dead load resists")
                )
        combos.extend(counterparts)

    # De-duplicate on label, preserving order.
    seen: set[str] = set()
    unique = []
    for c in combos:
        if c.label not in seen:
            seen.add(c.label)
            unique.append(c)
    return unique


def sls_combinations() -> list[Combination]:
    """Serviceability cases for deflection checks (specified loads, no factors).

    Live deflection is checked under the transient loads alone; total deflection
    under dead plus transient. Snow is treated as the transient load for roof
    members, live for floor members - both are included and the governing one
    is reported.
    """
    return [
        Combination("L (specified)", {"L": 1.0}, "SLS", "standard",
                    "Live-load deflection"),
        Combination("S (specified)", {"S": 1.0}, "SLS", "short",
                    "Snow-load deflection"),
        Combination("L + S (specified)", {"L": 1.0, "S": 1.0}, "SLS", "short",
                    "Transient deflection"),
        Combination("D + L + S (specified)", {"D": 1.0, "L": 1.0, "S": 1.0}, "SLS",
                    "standard", "Total deflection"),
    ]


def build(include_wind: bool = True, dead_can_resist: bool = False) -> CombinationSet:
    return CombinationSet(
        uls=uls_combinations(include_wind, dead_can_resist),
        sls=sls_combinations(),
    )


def relevant(uls: list[Combination], active: set[str]) -> list[Combination]:
    """Drop combinations that duplicate another once absent load cases are removed.

    With no live load present, "1.25D + 1.5L + 1.0S" and "1.25D + 1.0S" produce
    identical results; reporting the first as governing reads wrong on a calc
    sheet. The survivor is relabelled to the loads that actually act, so a
    member carrying no live load never has a "1.5L" term quoted against it.
    """
    from dataclasses import replace

    best: dict[tuple, tuple[int, Combination]] = {}
    for order, c in enumerate(uls):
        effective = {case: f for case, f in c.factors.items() if case in active and f}
        if not effective:
            continue
        key = (tuple(sorted(effective.items())), c.kd_duration)
        incumbent = best.get(key)
        if incumbent is not None and len(incumbent[1].factors) <= len(c.factors):
            continue
        best[key] = (order, replace(
            c,
            factors=effective,
            label=_label(effective),
            note=c.note + (
                f" (shown as acting loads only; full NBC case is {c.label})"
                if len(effective) != len(c.factors) else ""
            ),
        ))
    return [c for _, c in sorted(best.values(), key=lambda pair: pair[0])]


# Duration-of-load factor K_D, CSA O86-19 Cl. 5.3.2 Table 5.3.2.2.
KD_BY_DURATION = {
    "permanent": 0.65,
    "standard": 1.00,
    "short": 1.15,
}
