"""Preset vehicles for comparative pipe-surcharge checks.

Every preset here is a transcription from a reference sheet, not a live
lookup against a current, licensed copy of CSA S6 or a manufacturer's spec
system. Each one is flagged with what was actually given and what had to be
assumed to fill a gap (a tyre pressure, a dual spacing, a track width) - the
assumed values are ordinary engineering defaults, not vehicle-specific data,
and the caller should confirm anything that governs.

All vehicles are expressed in a single unified axle-based model. A tracked
excavator is simply a 1-axle vehicle with wide, long contact patches (the
tracks). A highway truck is a multi-axle vehicle with small contact patches
(tyres). The analysis engine treats both identically as rectangular contact
areas on the ground surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.soil.loads import AxleSpec
from core.units import MM_PER_FOOT, MM_PER_INCH, MPA_PER_PSI, N_PER_LBF


@dataclass(frozen=True)
class VehiclePreset:
    """Unified vehicle definition — tracks and tyres are all axle specs."""

    key: str
    name: str
    category: str  # "excavator", "truck", "crane", "other"
    axles: list[AxleSpec]
    axle_width_m: float  # track gauge or axle track width
    source: str
    verified: bool
    assumptions: list[str] = field(default_factory=list)

    @property
    def total_load_kn(self) -> float:
        return sum(a.load_kn for a in self.axles)

    @property
    def weight_kn(self) -> float:
        return self.total_load_kn

    @property
    def gauge_m(self) -> float:
        return self.axle_width_m

    @property
    def track_length_m(self) -> float:
        return self.axles[0].contact_length_m() if self.axles else 0.0

    @property
    def track_width_m(self) -> float:
        return self.axles[0].tire_width_m if self.axles else 0.0


# Keep old names as aliases for backward compatibility in tests
TruckPreset = VehiclePreset
TrackedPreset = VehiclePreset

LB_TO_KN = N_PER_LBF / 1000.0
PSI_TO_KPA = MPA_PER_PSI * 1000.0


def _in(v: float) -> float:
    return v * MM_PER_INCH / 1000.0


def _ft(v: float) -> float:
    return v * MM_PER_FOOT / 1000.0


# --------------------------------------------------------------------------
# CAT 320 excavator (20 t class)
# --------------------------------------------------------------------------
# For a tracked machine: 1 axle carrying the full operating weight, with
# tire_width = shoe width and tire_length = ground contact length. The
# multi_axle_vehicle() builder splits load evenly to left/right sides.
_CAT320_WEIGHT_KN = 49600 * LB_TO_KN
_CAT320_TRACK_LENGTH = _in(176)
_CAT320_TRACK_WIDTH = _in(30)

CAT_320_EXCAVATOR = VehiclePreset(
    key="cat_320",
    name="CAT 320 excavator (20 t class)",
    category="excavator",
    axles=[
        AxleSpec(
            "Tracks", _CAT320_WEIGHT_KN, tires_per_side=1,
            tire_width_m=_CAT320_TRACK_WIDTH,
            tire_length_m=_CAT320_TRACK_LENGTH,
        ),
    ],
    axle_width_m=_ft(7.9),
    source="Transcribed from a CAT 320 equipment sheet supplied by the user.",
    verified=False,
    # This was the only unverified preset carrying an empty assumptions list.
    # Everywhere assumptions are surfaced - the report, the AI export - an
    # empty list reads as "nothing to confirm here", which is the opposite of
    # what an unverified transcription means.
    assumptions=[
        "Operating weight (49,600 lb), 30 in shoe width and 176 in ground "
        "contact length are read off the supplied sheet; the 7.9 ft figure is "
        "taken as the track centre-to-centre gauge.",
        "The full operating weight is assumed to sit evenly on both tracks over "
        "the full contact length - a machine slewed, on a slope, or digging "
        "loads one track far more heavily and is not covered by this preset.",
        "Confirm the shoe width against the machine on site: the 320 is offered "
        "with 600/700/800 mm shoes, and shoe width sets the contact pressure "
        "directly.",
    ],
)

# --------------------------------------------------------------------------
# CAT 330 excavator (30 t class)
# --------------------------------------------------------------------------
CAT_330_EXCAVATOR = VehiclePreset(
    key="cat_330",
    name="CAT 330 excavator (30 t class)",
    category="excavator",
    axles=[
        AxleSpec(
            "Tracks", 309.0, tires_per_side=1,
            tire_width_m=0.80,
            tire_length_m=3.99,
        ),
    ],
    axle_width_m=2.59,
    source="Transcribed from CAT 330 equipment specification sheet.",
    verified=False,
    assumptions=["Standard 800 mm shoes and long undercarriage."],
)

# --------------------------------------------------------------------------
# CL-625 design truck, CSA S6
# --------------------------------------------------------------------------
# Axle loads (50/140/140/175/120 kN) and spacing are read directly off the
# source sheet - real data, not assumed. Tyre width and inflation pressure
# were NOT on the sheet; rather than store that assumed pressure and leave it
# sitting next to the real loads (where it reads as if it were equally
# authoritative), the contact length it implies is computed once, here, and
# stored directly as a fixed dimension. The axle table the user sees then
# shows LOAD (real, from the sheet) and LENGTH (a stated dimension) - not
# load next to an invented pressure.
_CL625_TIRE_WIDTH_M = 0.3
_CL625_ASSUMED_PRESSURE_KPA = 700.0  # ~100 psi, used only to size the patch once


def _cl625_axle(label: str, load_kn: float, spacing_from_previous_m: float = 0.0) -> AxleSpec:
    wheel_load_kn = load_kn / 2.0  # single tyre per side
    contact_length_m = (wheel_load_kn / _CL625_ASSUMED_PRESSURE_KPA) / _CL625_TIRE_WIDTH_M
    return AxleSpec(
        label, load_kn, tire_width_m=_CL625_TIRE_WIDTH_M,
        tire_length_m=round(contact_length_m, 4),
        spacing_from_previous_m=spacing_from_previous_m,
    )


CL625_TRUCK = VehiclePreset(
    key="cl625",
    name="CL-625 design truck (CSA S6)",
    category="truck",
    axles=[
        _cl625_axle("Axle 1", 50.0),
        _cl625_axle("Axle 2", 140.0, spacing_from_previous_m=3.6),
        _cl625_axle("Axle 3", 140.0, spacing_from_previous_m=1.2),
        _cl625_axle("Axle 4", 175.0, spacing_from_previous_m=6.6),
        _cl625_axle("Axle 5", 120.0, spacing_from_previous_m=6.6),
    ],
    axle_width_m=1.8,
    source="Transcribed from a reference CL-625 design-truck sheet supplied by the user.",
    verified=False,
    assumptions=[
        "Axle loads (50/140/140/175/120 kN) and spacing are read directly off "
        "the source sheet. Tyre width (0.3 m) was not given and is assumed at "
        "a typical highway-truck value. Contact length is not given either; it "
        "is computed once from an assumed 700 kPa (~100 psi) tyre inflation "
        "pressure and then stored as a fixed dimension, so the axle table "
        "shows the real load next to a stated length rather than next to an "
        "invented pressure. Confirm the tyre width and the resulting lengths "
        "against CSA S6:19 Clause 3.8 and the CL-625 commentary.",
    ],
)

# --------------------------------------------------------------------------
# Western Star 4700SB tri-axle roll-off (example heavy straight truck)
# --------------------------------------------------------------------------
_WS_TIRE_PRESSURE_KPA = 120.0 * PSI_TO_KPA
_WS_DUAL_SPACING_M = 0.33
_WS_AXLE_LOAD_KN = 19840 * LB_TO_KN

WESTERN_STAR_4700SB = VehiclePreset(
    key="western_star_4700sb",
    name="Western Star 4700SB tri-axle roll-off (example truck)",
    category="truck",
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

# --------------------------------------------------------------------------
# CAT 349 excavator (50 t class)
# --------------------------------------------------------------------------
CAT_349_EXCAVATOR = VehiclePreset(
    key="cat_349",
    name="CAT 349 excavator (50 t class)",
    category="excavator",
    axles=[
        AxleSpec(
            "Tracks", 480.0, tires_per_side=1,
            tire_width_m=0.90,
            tire_length_m=4.40,
        ),
    ],
    axle_width_m=2.74,
    source="Transcribed from CAT 349 equipment specification sheet.",
    verified=False,
    assumptions=["Standard 900 mm shoes and heavy undercarriage."],
)

# --------------------------------------------------------------------------
# CAT D6 crawler dozer (20 t class)
# --------------------------------------------------------------------------
CAT_D6_DOZER = VehiclePreset(
    key="cat_d6",
    name="CAT D6 crawler dozer (20 t class)",
    category="excavator",
    axles=[
        AxleSpec(
            "Tracks", 210.0, tires_per_side=1,
            tire_width_m=0.61,
            tire_length_m=2.80,
        ),
    ],
    axle_width_m=1.88,
    source="Transcribed from CAT D6 equipment specification sheet.",
    verified=False,
    assumptions=["Standard 610 mm shoes."],
)

# --------------------------------------------------------------------------
# CAT 950 wheel loader (2-axle heavy plant)
# --------------------------------------------------------------------------
CAT_950_LOADER = VehiclePreset(
    key="cat_950",
    name="CAT 950 wheel loader (2-axle)",
    category="truck",
    axles=[
        AxleSpec("Front Axle", 95.0, tires_per_side=1, tire_width_m=0.65,
                 tire_length_m=0.50),
        AxleSpec("Rear Axle", 95.0, tires_per_side=1, tire_width_m=0.65,
                 tire_length_m=0.50, spacing_from_previous_m=3.35),
    ],
    axle_width_m=2.15,
    source="Transcribed from CAT 950 medium wheel loader specifications.",
    verified=False,
    assumptions=["Even 50/50 static load split assumed across both axles."],
)

# --------------------------------------------------------------------------
# AASHTO HL-93 / HS-20 design truck
# --------------------------------------------------------------------------
AASHTO_HL93_TRUCK = VehiclePreset(
    key="hl93",
    name="AASHTO HL-93 design truck",
    category="truck",
    axles=[
        AxleSpec("Steer", 35.6, tires_per_side=1, tire_width_m=0.30,
                 tire_pressure_kpa=700.0),
        AxleSpec("Drive", 142.4, tires_per_side=1, tire_width_m=0.30,
                 tire_pressure_kpa=700.0, spacing_from_previous_m=4.30),
        AxleSpec("Trailer", 142.4, tires_per_side=1, tire_width_m=0.30,
                 tire_pressure_kpa=700.0, spacing_from_previous_m=4.30),
    ],
    axle_width_m=1.80,
    source="AASHTO LRFD Bridge Design Specifications (US customary converted).",
    verified=True,
    assumptions=["Standard 4.3 m (14 ft) minimum rear axle spacing."],
)

# --------------------------------------------------------------------------
# Standard 3-axle dump truck (tri-axle)
# --------------------------------------------------------------------------
TANDEM_DUMP_TRUCK = VehiclePreset(
    key="dump_truck_3axle",
    name="Standard 3-axle dump truck (24 t GVW)",
    category="truck",
    axles=[
        AxleSpec("Steering", 60.0, tires_per_side=1, tire_width_m=0.30,
                 tire_pressure_kpa=750.0),
        AxleSpec("Drive 1", 90.0, tires_per_side=2, tire_width_m=0.28,
                 tire_pressure_kpa=750.0, dual_spacing_m=0.33,
                 spacing_from_previous_m=4.20),
        AxleSpec("Drive 2", 90.0, tires_per_side=2, tire_width_m=0.28,
                 tire_pressure_kpa=750.0, dual_spacing_m=0.33,
                 spacing_from_previous_m=1.35),
    ],
    axle_width_m=2.00,
    source="Typical North American highway straight dump truck configuration.",
    verified=False,
    assumptions=["Dual tires on both tandem drive axles."],
)

# --------------------------------------------------------------------------
# Liebherr LTM 1050-3.1 50t mobile crane (3-axle)
# --------------------------------------------------------------------------
LIEBHERR_LTM_1050 = VehiclePreset(
    key="liebherr_ltm1050",
    name="Liebherr LTM 1050-3.1 50t crane (travel mode)",
    category="truck",
    axles=[
        AxleSpec("Axle 1", 120.0, tires_per_side=1, tire_width_m=0.44,
                 tire_pressure_kpa=900.0),
        AxleSpec("Axle 2", 120.0, tires_per_side=1, tire_width_m=0.44,
                 tire_pressure_kpa=900.0, spacing_from_previous_m=1.65),
        AxleSpec("Axle 3", 120.0, tires_per_side=1, tire_width_m=0.44,
                 tire_pressure_kpa=900.0, spacing_from_previous_m=1.65),
    ],
    axle_width_m=2.15,
    source="Transcribed from Liebherr LTM 1050-3.1 data sheet (36t on-road GVW).",
    verified=False,
    assumptions=["385/95 R 25 (14.00 R 25) single tyres throughout."],
)

# --------------------------------------------------------------------------
# Unified presets dictionary
# --------------------------------------------------------------------------
VEHICLE_PRESETS: dict[str, VehiclePreset] = {
    p.key: p for p in (
        CAT_320_EXCAVATOR,
        CAT_330_EXCAVATOR,
        CAT_349_EXCAVATOR,
        CAT_D6_DOZER,
        CAT_950_LOADER,
        CL625_TRUCK,
        AASHTO_HL93_TRUCK,
        WESTERN_STAR_4700SB,
        TANDEM_DUMP_TRUCK,
        LIEBHERR_LTM_1050,
    )
}

# Backward compatibility aliases
TRUCK_PRESETS: dict[str, VehiclePreset] = {
    p.key: p for p in (CL625_TRUCK, WESTERN_STAR_4700SB, AASHTO_HL93_TRUCK, TANDEM_DUMP_TRUCK, LIEBHERR_LTM_1050, CAT_950_LOADER)
}
TRACKED_PRESETS: dict[str, VehiclePreset] = {
    p.key: p for p in (CAT_320_EXCAVATOR, CAT_330_EXCAVATOR, CAT_349_EXCAVATOR, CAT_D6_DOZER)
}
