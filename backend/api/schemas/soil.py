"""Request/response contract for buried-pipe surcharge.

Lengths accept the same forms as the beam tool ("1.2 m", "4 ft", 1200 for mm).
Loads are in kN and pressures in kPa throughout.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.beam import LengthInput

Orientation = Literal["along", "across"]


class TrackedMachineIn(BaseModel):
    weight_kn: float = Field(gt=0, description="Operating weight, kN")
    track_length: LengthInput = "3.2 m"
    track_width: LengthInput = "600"
    gauge: LengthInput = "2.2 m"


class WheelGroupIn(BaseModel):
    wheel_load_kn: float = Field(gt=0, description="Load on ONE tyre, kN")
    # AASHTO's design tyre print: 510 mm across travel by 250 mm along it.
    patch_along_travel: LengthInput = "250"
    patch_across_travel: LengthInput = "510"
    axle_width: LengthInput = "1.8 m"
    dual_spacing: LengthInput = "0"
    axle_count: int = Field(default=1, ge=1, le=6)
    axle_spacing: LengthInput = "1.2 m"


class AxleSpecIn(BaseModel):
    label: str = "axle"
    load_kn: float = Field(gt=0, description="Total load on this axle, both sides, kN")
    tires_per_side: Literal[1, 2] = 1
    # Bare numbers mean millimetres everywhere in this app (see LengthInput) -
    # "300" here is a 300 mm tyre, not a 300 m one.
    tire_width: LengthInput = "300"
    tire_length: LengthInput | None = None  # contact length along travel, if known
    tire_pressure_kpa: float | None = Field(default=None, gt=0)
    dual_spacing: LengthInput = "0"          # required if tires_per_side == 2
    spacing_from_previous: LengthInput = "0"  # 0 for the first axle


class CustomPatchIn(BaseModel):
    label: str = "patch"
    x: LengthInput = "0"
    y: LengthInput = "0"
    width_x: LengthInput
    length_y: LengthInput
    total_kn: float = Field(gt=0)


class CustomPointIn(BaseModel):
    label: str = "point"
    x: LengthInput = "0"
    y: LengthInput = "0"
    load_kn: float = Field(gt=0)


class SurchargeRequestIn(BaseModel):
    load_type: Literal["tracked", "wheels", "truck", "custom"] = "tracked"
    tracked: TrackedMachineIn | None = None
    wheels: WheelGroupIn | None = None
    truck_axles: list[AxleSpecIn] = Field(default_factory=list)
    truck_axle_width: LengthInput = "1.8 m"
    custom_patches: list[CustomPatchIn] = Field(default_factory=list)
    custom_points: list[CustomPointIn] = Field(default_factory=list)

    orientation: Orientation = "across"
    cover: LengthInput = "1.0 m"
    pipe_od: LengthInput = "600"
    machine_offset: LengthInput = "0"
    soil_unit_weight_kn_m3: float = Field(default=20.0, gt=0, le=30.0)
    poisson_ratio: float = Field(default=0.0, ge=0.0, lt=0.5)

    # Dynamic load allowance
    dla_mode: Literal["none", "manual", "aashto_depth"] = "manual"
    dla: float = Field(default=1.3, ge=1.0, le=2.5)

    # Load-spread comparison method
    spread_preset: Literal[
        "aashto_granular", "aashto_other", "custom", "none"
    ] = "aashto_granular"
    spread_factor: float = Field(default=1.15, ge=0.0, le=3.0)

    project: str = ""
    member: str = ""
    engineer: str = ""


class TermOut(BaseModel):
    label: str
    detail: str
    value_kpa: float


class MethodOut(BaseModel):
    key: str
    name: str
    pressure_kpa: float
    basis: str
    verified: bool
    note: str
    formula: str = ""
    substitution: str = ""
    terms: list[TermOut] = Field(default_factory=list)
    terms_sum_to_total: bool = True


class PatchOut(BaseModel):
    label: str
    x_m: float
    y_m: float
    width_x_m: float
    length_y_m: float
    total_kn: float
    pressure_kpa: float


class PointOut(BaseModel):
    label: str
    x_m: float
    y_m: float
    load_kn: float


class IsolineOut(BaseModel):
    level_kpa: float
    segments: list[list[list[float]]]


class CrownPlanOut(BaseModel):
    x_m: list[float] = Field(default_factory=list)
    y_m: list[float] = Field(default_factory=list)
    grid_kpa: list[list[float]] = Field(default_factory=list)
    peak_kpa: float = 0.0


class BulbOut(BaseModel):
    x_m: list[float] = Field(default_factory=list)
    depth_m: list[float] = Field(default_factory=list)
    grid_kpa: list[list[float]] = Field(default_factory=list)
    peak_kpa: float = 0.0
    isolines: list[IsolineOut] = Field(default_factory=list)


class OrientationComparisonOut(BaseModel):
    orientation: str
    label: str
    is_current: bool
    pressure_at_offset_kpa: float
    worst_offset_m: float
    worst_pressure_kpa: float


class ProfilePointOut(BaseModel):
    depth_m: float | None = None
    offset_m: float | None = None
    pressure_kpa: float


class TrackedPresetOut(BaseModel):
    key: str
    name: str
    weight_kn: float
    track_length_m: float
    track_width_m: float
    gauge_m: float
    source: str
    verified: bool
    assumptions: list[str] = Field(default_factory=list)


class AxlePresetOut(BaseModel):
    label: str
    load_kn: float
    tires_per_side: int
    tire_width_m: float
    tire_length_m: float | None
    tire_pressure_kpa: float | None
    dual_spacing_m: float
    spacing_from_previous_m: float


class TruckPresetOut(BaseModel):
    key: str
    name: str
    axles: list[AxlePresetOut]
    axle_width_m: float
    source: str
    verified: bool
    assumptions: list[str] = Field(default_factory=list)


class VehiclePresetsOut(BaseModel):
    tracked: list[TrackedPresetOut]
    trucks: list[TruckPresetOut]


class VehicleSpecIn(BaseModel):
    """One vehicle to include in a cross-vehicle comparison.

    Either give ``preset_key`` (looked up against the tracked/truck preset
    registries according to ``load_type``) or fill in the same fields the
    single-vehicle endpoint takes.
    """

    label: str = ""
    load_type: Literal["tracked", "wheels", "truck"] = "tracked"
    preset_key: str | None = None
    orientation: Orientation = "across"
    tracked: TrackedMachineIn | None = None
    wheels: WheelGroupIn | None = None
    truck_axles: list[AxleSpecIn] = Field(default_factory=list)
    truck_axle_width: LengthInput = "1.8 m"


class VehicleComparisonRequestIn(BaseModel):
    vehicles: list[VehicleSpecIn] = Field(min_length=1, max_length=12)

    cover: LengthInput = "1.0 m"
    pipe_od: LengthInput = "600"
    soil_unit_weight_kn_m3: float = Field(default=20.0, gt=0, le=30.0)
    poisson_ratio: float = Field(default=0.0, ge=0.0, lt=0.5)
    dla_mode: Literal["none", "manual", "aashto_depth"] = "manual"
    dla: float = Field(default=1.3, ge=1.0, le=2.5)
    spread_preset: Literal[
        "aashto_granular", "aashto_other", "custom", "none"
    ] = "aashto_granular"
    spread_factor: float = Field(default=1.15, ge=0.0, le=3.0)


class VehicleResultOut(BaseModel):
    ok: bool = True
    error: str = ""
    label: str = ""
    load_type: str = ""
    orientation: str = ""
    description: str = ""
    total_load_kn: float = 0.0
    live_pressure_kpa: float = 0.0
    worst_offset_m: float = 0.0
    worst_offset_pressure_kpa: float = 0.0


class VehicleComparisonResponseOut(BaseModel):
    ok: bool = True
    error: str = ""
    results: list[VehicleResultOut] = Field(default_factory=list)


class SurchargeResponseOut(BaseModel):
    ok: bool = True
    error: str = ""

    cover_m: float = 0.0
    pipe_od_m: float = 0.0
    machine_offset_m: float = 0.0
    load_description: str = ""
    total_load_kn: float = 0.0
    dla: float = 1.0
    dla_basis: str = ""

    methods: list[MethodOut] = Field(default_factory=list)
    live_pressure_kpa: float = 0.0
    average_over_pipe_kpa: float = 0.0
    load_per_m_kn_m: float = 0.0

    worst_offset_m: float = 0.0
    worst_offset_pressure_kpa: float = 0.0
    offset_is_worst: bool = True

    soil_pressure_kpa: float = 0.0
    live_to_dead_ratio: float = 0.0

    patches: list[PatchOut] = Field(default_factory=list)
    points: list[PointOut] = Field(default_factory=list)
    depth_profile: list[dict[str, float]] = Field(default_factory=list)
    offset_profile: list[ProfilePointOut] = Field(default_factory=list)
    bulb: BulbOut = Field(default_factory=BulbOut)
    crown_plan: CrownPlanOut = Field(default_factory=CrownPlanOut)
    orientations: list[OrientationComparisonOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    report_html: str = ""
