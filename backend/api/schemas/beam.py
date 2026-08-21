"""Request/response contract for the beam design endpoint.

Lengths may be given as a number (millimetres) or as a string with units
("18 ft", "12'-6\"", "3.5 m", '9 1/4"'). Loads are entered either as an area
load in kPa with a tributary width, or directly as a line load in kN/m.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.units import UnitError, parse_length_mm

LengthInput = float | int | str


def _length(value: LengthInput, field_name: str) -> float:
    try:
        return parse_length_mm(value)
    except UnitError as exc:
        raise ValueError(f"{field_name}: {exc}") from exc


class LoadInput(BaseModel):
    case: Literal["D", "L", "S", "W"] = "D"
    kind: Literal["udl", "point"] = "udl"

    # UDL: either an area load plus tributary width, or a line load directly.
    area_load_kpa: float | None = None
    tributary: LengthInput | None = None
    line_load_kn_m: float | None = None

    # Point load.
    p_kn: float | None = None
    x: LengthInput | None = None

    # Optional partial-UDL extent; defaults to the whole member.
    x_start: LengthInput | None = None
    x_end: LengthInput | None = None

    def resolve_line_load_n_per_mm(self) -> float:
        if self.line_load_kn_m is not None:
            return self.line_load_kn_m  # kN/m is numerically N/mm
        if self.area_load_kpa is not None and self.tributary is not None:
            trib = _length(self.tributary, "tributary")
            return self.area_load_kpa * 1e-3 * trib
        raise ValueError(
            "A UDL needs either line_load_kn_m, or area_load_kpa together with tributary."
        )


class ConditionsInput(BaseModel):
    service: Literal["dry", "wet"] = "dry"
    treatment: Literal["none", "preservative", "incised"] = "none"
    system: Literal["none", "case1", "case2"] = "none"
    laterally_supported: bool = True
    bearing_length: LengthInput = 89.0
    bearing_at_end: bool = False


class CustomMaterialInput(BaseModel):
    name: str = "Custom product"
    fb_mpa: float = Field(gt=0)
    fv_mpa: float = Field(gt=0)
    fcp_mpa: float = Field(gt=0)
    e_mpa: float = Field(gt=0)
    fc_mpa: float = 0.0
    ft_mpa: float = 0.0
    e05_mpa: float | None = None
    g_mpa: float | None = None
    density_kg_m3: float = 670.0
    source: str = "User-entered product evaluation report"
    depth_ref: LengthInput | None = None
    depth_exponent: float | None = None


class SectionInput(BaseModel):
    ply_width: LengthInput
    depth: LengthInput
    plies: int = Field(default=1, ge=1, le=12)


class DeflectionLimitsInput(BaseModel):
    live_ratio: float = Field(default=360.0, gt=0)
    total_ratio: float = Field(default=240.0, gt=0)
    creep_factor: float = Field(default=1.0, ge=1.0, le=3.0)


class DesignRequestIn(BaseModel):
    spans: list[LengthInput] = Field(min_length=1)
    supports: list[Literal["pin", "roller", "fixed", "free"]]
    left_overhang: LengthInput = 0.0
    right_overhang: LengthInput = 0.0

    material_key: str = "LVL-2.0E-Microllam"
    custom_material: CustomMaterialInput | None = None

    section: SectionInput | None = None  # omit to auto-search a size
    max_plies: int = Field(default=6, ge=1, le=12)

    loads: list[LoadInput] = Field(default_factory=list)
    conditions: ConditionsInput = Field(default_factory=ConditionsInput)
    deflection_limits: DeflectionLimitsInput = Field(default_factory=DeflectionLimitsInput)

    include_wind: bool = False
    include_self_weight: bool = True

    project: str = ""
    member: str = ""
    engineer: str = ""

    @field_validator("supports")
    @classmethod
    def _at_least_two(cls, v):
        if len(v) < 2:
            raise ValueError("A beam needs at least two supports.")
        return v


class FactorOut(BaseModel):
    symbol: str
    value: float
    clause: str
    description: str


class CheckOut(BaseModel):
    check: str
    label: str
    demand: float
    resistance: float
    units: str
    ratio: float
    status: str
    combo_label: str
    clause: str
    formula: str
    substitution: str
    location_mm: float | None
    note: str
    factors: list[FactorOut]


class PeakOut(BaseModel):
    label: str
    x_mm: float
    value: float
    units: str
    combo: str


class DiagramsOut(BaseModel):
    x_mm: list[float]
    shear_min_kn: list[float]
    shear_max_kn: list[float]
    moment_min_knm: list[float]
    moment_max_knm: list[float]
    deflection_live_mm: list[float]
    deflection_total_mm: list[float]
    governing_shear_combo: str
    governing_moment_combo: str
    peaks: list[PeakOut]


class SpanLimitOut(BaseModel):
    name: str
    x_start_mm: float
    x_end_mm: float
    reference_length_mm: float
    live_limit_mm: float
    total_limit_mm: float


class ReactionOut(BaseModel):
    x_mm: float
    support_kind: str
    max_kn: float
    governing_combo: str
    required_bearing_mm: float
    bearing_ratio: float


class LoadEchoOut(BaseModel):
    case: str
    kind: str
    magnitude: float
    units: str
    x_start_mm: float
    x_end_mm: float
    label: str
    is_self_weight: bool


class AlternativeOut(BaseModel):
    label: str
    plies: int
    width_mm: float
    depth_mm: float
    max_ratio: float
    governing_check: str


class DesignResponseOut(BaseModel):
    passed: bool
    max_ratio: float
    section_label: str
    material_name: str
    material_source: str
    material_verified: bool
    plies: int
    width_mm: float
    depth_mm: float
    checks: list[CheckOut]
    warnings: list[str]
    diagrams: DiagramsOut
    reactions: list[ReactionOut]
    loads: list[LoadEchoOut]
    span_limits: list[SpanLimitOut]
    span_positions_mm: list[float]
    length_mm: float
    self_weight_kn_m: float
    combos_considered: list[str]
    combo_durations: list[str]
    alternatives: list[AlternativeOut]
    report_html: str


class SectionPreviewOut(BaseModel):
    label: str
    ply_width_mm: float
    depth_mm: float
    plies: int
    width_mm: float
    area_mm2: float
    section_modulus_mm3: float
    inertia_mm4: float
    self_weight_kn_m: float
    material_name: str
    material_verified: bool


class PreviewOut(BaseModel):
    """Live drawing data. ``ok`` is False when the inputs cannot be parsed yet."""

    ok: bool
    error: str = ""
    length_mm: float = 0.0
    span_positions_mm: list[float] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    loads: list[LoadEchoOut] = Field(default_factory=list)
    section: SectionPreviewOut | None = None
    description: str = ""
    total_load_kn: float = 0.0


class MaterialOut(BaseModel):
    key: str
    name: str
    family: str
    verified: bool
    source: str
    fb_mpa: float
    fv_mpa: float
    fcp_mpa: float
    e_mpa: float
    available_widths_mm: list[float]
    available_depths_mm: list[float]
