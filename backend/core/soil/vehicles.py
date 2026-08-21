"""Preset vehicles for comparative pipe-surcharge checks.

Every preset here is a transcription from a reference sheet, not a live
lookup against a current, licensed copy of CSA S6 or a manufacturer's spec
system. Each one is flagged with what was actually given and what had to be
assumed to fill a gap (a tyre pressure, a dual spacing, a track width) - the
assumed values are ordinary engineering defaults, not vehicle-specific data,
and the caller should confirm anything that governs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.soil.loads import AxleSpec
from core.units import MM_PER_FOOT, MM_PER_INCH, MPA_PER_PSI, N_PER_LBF


@dataclass(frozen=True)
class TruckPreset:
    key: str
    name: str
    axles: list[AxleSpec]
    axle_width_m: float
    source: str
    verified: bool
    assumptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrackedPreset:
    key: str
    name: str
    weight_kn: float
    track_length_m: float
    track_width_m: float
    gauge_m: float
    source: str
    verified: bool
    assumptions: list[str] = field(default_factory=list)


LB_TO_KN = N_PER_LBF / 1000.0
PSI_TO_KPA = MPA_PER_PSI * 1000.0


def _in(v: float) -> float:
    return v * MM_PER_INCH / 1000.0


def _ft(v: float) -> float:
    return v * MM_PER_FOOT / 1000.0


# --------------------------------------------------------------------------
# CL-625 design truck, CSA S6
# --------------------------------------------------------------------------
# Axle loads and spacing transcribed directly from the reference sheet
# (50 / 140 / 140 / 175 / 120 kN over 3.6 / 1.2 / 6.6 / 6.6 m, 18 m overall).
# Wheel loads on the sheet are exactly half the axle load throughout, so each
# axle is modelled as a single tyre line per side (no duals). Axle track width
# of 1.8 m is read from the accompanying clearance-envelope drawing
# (0.6 + 1.8 + 0.6 = 3.0 m). Tyre width and inflation pressure were not given
# on the sheet and are assumed at typical highway-truck values.
_CL625_TIRE_WIDTH_M = 0.3
_CL625_TIRE_PRESSURE_KPA = 700.0  # ~100 psi, a typical truck tyre inflation

CL625_TRUCK = TruckPreset(
    key="cl625",
    name="CL-625 design truck (CSA S6)",
    axles=[
        AxleSpec("Axle 1", 50.0, tire_width_m=_CL625_TIRE_WIDTH_M,
                 tire_pressure_kpa=_CL625_TIRE_PRESSURE_KPA),
        AxleSpec("Axle 2", 140.0, tire_width_m=_CL625_TIRE_WIDTH_M,
                 tire_pressure_kpa=_CL625_TIRE_PRESSURE_KPA,
                 spacing_from_previous_m=3.6),
        AxleSpec("Axle 3", 140.0, tire_width_m=_CL625_TIRE_WIDTH_M,
                 tire_pressure_kpa=_CL625_TIRE_PRESSURE_KPA,
                 spacing_from_previous_m=1.2),
        AxleSpec("Axle 4", 175.0, tire_width_m=_CL625_TIRE_WIDTH_M,
                 tire_pressure_kpa=_CL625_TIRE_PRESSURE_KPA,
                 spacing_from_previous_m=6.6),
        AxleSpec("Axle 5", 120.0, tire_width_m=_CL625_TIRE_WIDTH_M,
                 tire_pressure_kpa=_CL625_TIRE_PRESSURE_KPA,
                 spacing_from_previous_m=6.6),
    ],
    axle_width_m=1.8,
    source="Transcribed from a reference CL-625 design-truck sheet supplied by the user.",
    verified=False,
    assumptions=[
        "Tyre width (0.3 m) and inflation pressure (700 kPa) were not on the "
        "source sheet - assumed at typical highway-truck values to size the "
        "contact patch. Confirm against CSA S6:19 Clause 3.8 and the CL-625 "
        "commentary before relying on the absolute pressure this gives.",
    ],
)

# --------------------------------------------------------------------------
# Western Star 4700SB tri-axle roll-off (example heavy straight truck)
# --------------------------------------------------------------------------
_WS_TIRE_PRESSURE_KPA = 120.0 * PSI_TO_KPA
_WS_DUAL_SPACING_M = 0.33  # not on the source sheet - typical dual centre spacing

_WS_AXLE_LOAD_KN = 19840 * LB_TO_KN  # "Max loaded weight PER Axle", all four groups

WESTERN_STAR_4700SB = TruckPreset(
    key="western_star_4700sb",
    name="Western Star 4700SB tri-axle roll-off (example truck)",
    axles=[
        AxleSpec("Steering", _WS_AXLE_LOAD_KN, tires_per_side=1, tire_width_m=_in(10),
                 tire_pressure_kpa=_WS_TIRE_PRESSURE_KPA),
        AxleSpec("2nd", _WS_AXLE_LOAD_KN, tires_per_side=1, tire_width_m=_in(10),
                 tire_pressure_kpa=_WS_TIRE_PRESSURE_KPA, spacing_from_previous_m=_in(155)),
        AxleSpec("3rd", _WS_AXLE_LOAD_KN, tires_per_side=2, tire_width_m=_in(8),
                 tire_pressure_kpa=_WS_TIRE_PRESSURE_KPA, dual_spacing_m=_WS_DUAL_SPACING_M,
                 spacing_from_previous_m=_in(100)),
        AxleSpec("4th", _WS_AXLE_LOAD_KN, tires_per_side=2, tire_width_m=_in(8),
                 tire_pressure_kpa=_WS_TIRE_PRESSURE_KPA, dual_spacing_m=_WS_DUAL_SPACING_M,
                 spacing_from_previous_m=_in(56)),
    ],
    axle_width_m=2.4,
    source="Transcribed from a Western Star 4700SB axle-weight sheet supplied by the user.",
    verified=False,
    assumptions=[
        "Dual tyre centre-to-centre spacing (0.33 m) was not on the source sheet - "
        "assumed at a typical value for a tandem drive axle.",
        "Axle (track) width of 2.4 m was not on the source sheet - assumed at a "
        "typical value for a highway straight truck.",
    ],
)

TRUCK_PRESETS: dict[str, TruckPreset] = {
    p.key: p for p in (CL625_TRUCK, WESTERN_STAR_4700SB)
}


# --------------------------------------------------------------------------
# CAT 320 excavator (20 t class)
# --------------------------------------------------------------------------
CAT_320_EXCAVATOR = TrackedPreset(
    key="cat_320",
    name="CAT 320 excavator (20 t class)",
    weight_kn=49600 * LB_TO_KN,
    track_length_m=_in(176),
    track_width_m=_in(30),
    gauge_m=_ft(7.9),
    source="Transcribed from a CAT 320 equipment sheet supplied by the user.",
    verified=False,
)

TRACKED_PRESETS: dict[str, TrackedPreset] = {p.key: p for p in (CAT_320_EXCAVATOR,)}
