"""Post and column design endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.schemas.beam import ConditionsInput, LengthInput, SectionInput
from core.report import post_report
from core.units import parse_length_mm
from core.wood import materials, scl_columns
from core.wood.compression import (
    END_CONDITIONS,
    PostDesignError,
    PostRequest,
    design,
)
from core.wood.factors import Conditions
from core.wood.sections import BuiltUpSection

router = APIRouter(prefix="/api/post", tags=["post"])

EndCondition = Literal[
    "pinned-pinned", "fixed-pinned", "fixed-fixed", "fixed-free", "fixed-fixed-sway"
]


class PostRequestIn(BaseModel):
    length: LengthInput
    axial_kn: dict[str, float] = Field(default_factory=dict)

    # Either a sawn section...
    material_key: str = "SPF-No1No2"
    section: SectionInput | None = None
    # ...or a published SCL column.
    scl_product: str | None = None
    scl_size_index: int = 0
    scl_bearing: Literal["column_base", "wood_plate"] = "column_base"

    conditions: ConditionsInput = Field(default_factory=ConditionsInput)
    end_condition_d: EndCondition = "pinned-pinned"
    end_condition_b: EndCondition = "pinned-pinned"
    unbraced_d: LengthInput | None = None
    unbraced_b: LengthInput | None = None
    include_wind: bool = False

    project: str = ""
    member: str = ""
    engineer: str = ""


class CurvePointOut(BaseModel):
    length_mm: float
    resistance_kn: float


class PostCheckOut(BaseModel):
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
    note: str
    factors: list[dict]


class PostResponseOut(BaseModel):
    passed: bool
    max_ratio: float
    label: str
    material_name: str
    material_source: str
    material_verified: bool
    method: str
    width_mm: float
    depth_mm: float
    plies: int
    area_mm2: float
    slenderness: float
    slenderness_axis: str
    demand_kn: float
    resistance_kn: float
    governing_combo: str
    independent_ply_resistance_kn: float | None
    checks: list[PostCheckOut]
    warnings: list[str]
    capacity_curve: list[CurvePointOut]
    report_html: str


@router.get("/end-conditions")
def end_conditions() -> list[dict]:
    return [
        {"key": k, "ke": ke, "description": desc}
        for k, (ke, desc) in END_CONDITIONS.items()
    ]


@router.get("/scl-products")
def scl_products() -> list[dict]:
    return scl_columns.products()


@router.post("/design", response_model=PostResponseOut)
def design_post(payload: PostRequestIn) -> PostResponseOut:
    try:
        length = parse_length_mm(payload.length)
        c = payload.conditions
        conditions = Conditions(
            service=c.service,
            treatment=c.treatment,
            system=c.system,
            laterally_supported=c.laterally_supported,
            bearing_length_mm=parse_length_mm(c.bearing_length),
            bearing_at_end=c.bearing_at_end,
        )

        section = None
        if payload.section is not None and not payload.scl_product:
            section = BuiltUpSection(
                parse_length_mm(payload.section.ply_width),
                parse_length_mm(payload.section.depth),
                payload.section.plies,
            )

        if not payload.scl_product:
            if section is None:
                raise ValueError("A section is required for a sawn lumber post.")
            if payload.material_key not in {m.key for m in materials.all_materials()}:
                raise ValueError(f"Unknown material {payload.material_key!r}.")

        request = PostRequest(
            length_mm=length,
            axial_kn=payload.axial_kn,
            material_key=payload.material_key,
            section=section,
            conditions=conditions,
            end_condition_d=payload.end_condition_d,
            end_condition_b=payload.end_condition_b,
            unbraced_d_mm=parse_length_mm(payload.unbraced_d) if payload.unbraced_d else None,
            unbraced_b_mm=parse_length_mm(payload.unbraced_b) if payload.unbraced_b else None,
            include_wind=payload.include_wind,
            scl_product=payload.scl_product,
            scl_size_index=payload.scl_size_index,
            scl_bearing=payload.scl_bearing,
        )
        result = design(request)

    except (PostDesignError, scl_columns.SclColumnError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = post_report.render(
        result,
        project=payload.project,
        member=payload.member,
        engineer=payload.engineer,
        length_mm=length,
        conditions=conditions,
        axial_kn=payload.axial_kn,
        end_condition_d=payload.end_condition_d,
        end_condition_b=payload.end_condition_b,
    )

    return PostResponseOut(
        passed=result.outcome.passed,
        max_ratio=round(result.outcome.max_ratio, 4),
        label=result.label,
        material_name=result.material_name,
        material_source=result.material_source,
        material_verified=result.material_verified,
        method=result.method,
        width_mm=round(result.width_mm, 1),
        depth_mm=round(result.depth_mm, 1),
        plies=result.plies,
        area_mm2=round(result.area_mm2, 1),
        slenderness=round(result.slenderness, 2),
        slenderness_axis=result.slenderness_axis,
        demand_kn=round(result.demand_kn, 3),
        resistance_kn=round(result.resistance_kn, 3),
        governing_combo=result.governing_combo,
        independent_ply_resistance_kn=(
            round(result.independent_ply_resistance_kn, 3)
            if result.independent_ply_resistance_kn is not None else None
        ),
        checks=[
            {
                "check": ch.check, "label": ch.label, "demand": round(ch.demand, 3),
                "resistance": round(ch.resistance, 3), "units": ch.units,
                "ratio": round(ch.ratio, 4), "status": ch.status,
                "combo_label": ch.combo_label, "clause": ch.clause,
                "formula": ch.formula, "substitution": ch.substitution,
                "note": ch.note,
                "factors": [
                    {"symbol": f.symbol, "value": round(f.value, 4),
                     "clause": f.clause, "description": f.description}
                    for f in ch.factors
                ],
            }
            for ch in result.outcome.checks
        ],
        warnings=result.outcome.warnings,
        capacity_curve=result.capacity_curve,
        report_html=html,
    )
