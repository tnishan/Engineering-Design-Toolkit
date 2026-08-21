"""Beam design endpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import APIRouter, HTTPException

from api.schemas.beam import (
    DesignRequestIn,
    DesignResponseOut,
    LoadEchoOut,
    MaterialOut,
    PreviewOut,
    SectionPreviewOut,
)
from core.analysis.beam import BeamModelError, DistributedLoad, PointLoad
from core.report import calc_report
from core.units import parse_length_mm
from core.wood import materials
from core.wood.design import DeflectionLimits, DesignRequest, run
from core.wood.factors import Conditions
from core.wood.sections import BuiltUpSection

router = APIRouter(prefix="/api/beam", tags=["beam"])


@router.get("/materials", response_model=list[MaterialOut])
def list_materials() -> list[MaterialOut]:
    return [
        MaterialOut(
            key=m.key,
            name=m.name,
            family=m.family,
            verified=m.verified,
            source=m.source,
            fb_mpa=round(m.fb_mpa, 3),
            fv_mpa=round(m.fv_mpa, 3),
            fcp_mpa=round(m.fcp_mpa, 3),
            e_mpa=round(m.e_mpa, 1),
            available_widths_mm=[round(w, 1) for w in m.available_widths_mm],
            available_depths_mm=[round(d, 1) for d in m.available_depths_mm],
        )
        for m in materials.all_materials()
    ]


@dataclass
class ParsedInputs:
    """Everything a design or a preview needs, parsed once from the payload."""

    spans_mm: list[float]
    left_mm: float
    right_mm: float
    total_mm: float
    distributed: list[DistributedLoad]
    points: list[PointLoad]
    load_rows: list[dict]
    conditions: Conditions
    custom_material: object | None
    section: BuiltUpSection | None


def _parse(payload: DesignRequestIn) -> ParsedInputs:
    """Parse and validate a request. Shared by /design and /preview so the
    drawing on screen can never disagree with what is analysed."""
    spans = [parse_length_mm(s) for s in payload.spans]
    left = parse_length_mm(payload.left_overhang)
    right = parse_length_mm(payload.right_overhang)
    total = left + sum(spans) + right

    distributed: list[DistributedLoad] = []
    points: list[PointLoad] = []
    load_rows: list[dict] = []

    for load in payload.loads:
        if load.kind == "udl":
            w = load.resolve_line_load_n_per_mm()
            x0 = parse_length_mm(load.x_start) if load.x_start is not None else 0.0
            x1 = parse_length_mm(load.x_end) if load.x_end is not None else total
            distributed.append(DistributedLoad(w, x0, x1, load.case))
            if load.area_load_kpa is not None and load.tributary is not None:
                trib = parse_length_mm(load.tributary)
                magnitude = (
                    f"{load.area_load_kpa:g} kPa x {trib / 1000:.3f} m = {w:.3f} kN/m"
                )
            else:
                magnitude = f"{w:.3f} kN/m"
            extent = (
                "full length" if (x0 <= 0 and x1 >= total - 1e-6)
                else f"{x0 / 1000:.3f} to {x1 / 1000:.3f} m"
            )
            load_rows.append({"case": load.case, "kind": "UDL",
                              "magnitude": magnitude, "extent": extent})
        else:
            if load.p_kn is None or load.x is None:
                raise ValueError("A point load needs both p_kn and x.")
            x = parse_length_mm(load.x)
            points.append(PointLoad(load.p_kn * 1000.0, x, load.case))
            load_rows.append({"case": load.case, "kind": "Point",
                              "magnitude": f"{load.p_kn:g} kN",
                              "extent": f"at {x / 1000:.3f} m"})

    c = payload.conditions
    conditions = Conditions(
        service=c.service,
        treatment=c.treatment,
        system=c.system,
        laterally_supported=c.laterally_supported,
        bearing_length_mm=parse_length_mm(c.bearing_length),
        bearing_at_end=c.bearing_at_end,
    )

    custom = None
    if payload.custom_material is not None:
        cm = payload.custom_material
        custom = materials.custom(
            name=cm.name, fb_mpa=cm.fb_mpa, fv_mpa=cm.fv_mpa,
            fcp_mpa=cm.fcp_mpa, e_mpa=cm.e_mpa, fc_mpa=cm.fc_mpa,
            ft_mpa=cm.ft_mpa, e05_mpa=cm.e05_mpa, g_mpa=cm.g_mpa,
            density_kg_m3=cm.density_kg_m3, source=cm.source,
            depth_ref_mm=parse_length_mm(cm.depth_ref) if cm.depth_ref else None,
            depth_exponent=cm.depth_exponent,
        )
    elif payload.material_key not in {m.key for m in materials.all_materials()}:
        raise ValueError(f"Unknown material {payload.material_key!r}.")

    section = None
    if payload.section is not None:
        section = BuiltUpSection(
            parse_length_mm(payload.section.ply_width),
            parse_length_mm(payload.section.depth),
            payload.section.plies,
        )

    return ParsedInputs(spans, left, right, total, distributed, points,
                        load_rows, conditions, custom, section)


@router.post("/design", response_model=DesignResponseOut)
def design(payload: DesignRequestIn) -> DesignResponseOut:
    try:
        p = _parse(payload)
        spans, left, right = p.spans_mm, p.left_mm, p.right_mm
        distributed, points, load_rows = p.distributed, p.points, p.load_rows
        conditions, custom, section = p.conditions, p.custom_material, p.section

        dl = payload.deflection_limits
        request = DesignRequest(
            spans_mm=spans,
            support_kinds=list(payload.supports),
            material_key=payload.material_key,
            distributed=distributed,
            points=points,
            conditions=conditions,
            limits=DeflectionLimits(dl.live_ratio, dl.total_ratio, dl.creep_factor),
            left_overhang_mm=left,
            right_overhang_mm=right,
            section=section,
            max_plies=payload.max_plies,
            include_wind=payload.include_wind,
            include_self_weight=payload.include_self_weight,
            custom_material=custom,
        )

        result = run(request)

    except (BeamModelError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = calc_report.render(
        result,
        project=payload.project,
        member=payload.member,
        engineer=payload.engineer,
        spans_mm=spans,
        support_kinds=list(payload.supports),
        conditions=conditions,
        load_rows=load_rows,
        durations=result.combo_durations,
    )

    return DesignResponseOut(
        passed=result.outcome.passed,
        max_ratio=round(result.outcome.max_ratio, 4),
        section_label=result.section_label,
        material_name=result.material_name,
        material_source=result.material_source,
        material_verified=result.material_verified,
        plies=result.plies,
        width_mm=result.width_mm,
        depth_mm=result.depth_mm,
        checks=[
            {
                "check": c.check, "label": c.label, "demand": round(c.demand, 4),
                "resistance": round(c.resistance, 4), "units": c.units,
                "ratio": round(c.ratio, 4), "status": c.status,
                "combo_label": c.combo_label, "clause": c.clause,
                "formula": c.formula, "substitution": c.substitution,
                "location_mm": c.location_mm, "note": c.note,
                "factors": [
                    {"symbol": f.symbol, "value": round(f.value, 4),
                     "clause": f.clause, "description": f.description}
                    for f in c.factors
                ],
            }
            for c in result.outcome.checks
        ],
        warnings=result.outcome.warnings,
        diagrams=asdict(result.diagrams),
        reactions=[r.__dict__ for r in result.reactions],
        loads=[l.__dict__ for l in result.loads],
        span_limits=[s.__dict__ for s in result.span_limits],
        span_positions_mm=result.span_positions_mm,
        length_mm=result.length_mm,
        self_weight_kn_m=round(result.self_weight_n_per_mm, 4),
        combos_considered=result.combos_considered,
        combo_durations=result.combo_durations,
        alternatives=result.alternatives,
        report_html=html,
    )


@router.post("/preview", response_model=PreviewOut)
def preview(payload: DesignRequestIn) -> PreviewOut:
    """Geometry, loads and section properties without running the design.

    Drives the live drawing while the engineer types. Parse problems come back
    as data rather than an HTTP error so a half-typed span does not blank the
    screen - the caller keeps the last good drawing and shows the message.
    """
    try:
        p = _parse(payload)
    except (BeamModelError, ValueError, KeyError) as exc:
        return PreviewOut(ok=False, error=str(exc))

    material = p.custom_material or materials.get(payload.material_key)

    supports_mm: list[float] = []
    x = p.left_mm
    supports_mm.append(x)
    for span in p.spans_mm:
        x += span
        supports_mm.append(x)

    if len(payload.supports) != len(p.spans_mm) + 1:
        return PreviewOut(
            ok=False,
            error=(
                f"Expected {len(p.spans_mm) + 1} supports for {len(p.spans_mm)} "
                f"span(s), got {len(payload.supports)}."
            ),
        )

    self_weight = 0.0
    section_out = None
    description = ""
    if p.section is not None:
        s = p.section
        if payload.include_self_weight:
            self_weight = s.self_weight_n_per_mm(material)
        section_out = SectionPreviewOut(
            label=s.label(material),
            ply_width_mm=round(s.ply_width_mm, 2),
            depth_mm=round(s.depth_mm, 2),
            plies=s.plies,
            width_mm=round(s.width_mm, 2),
            area_mm2=round(s.area_mm2, 1),
            section_modulus_mm3=round(s.section_modulus_mm3, 1),
            inertia_mm4=round(s.inertia_mm4, 1),
            self_weight_kn_m=round(self_weight, 4),
            material_name=material.name,
            material_verified=material.verified,
        )
        description = _describe(s, material, self_weight)
    else:
        description = (
            "Auto-sizing is on: the tool will search its section list and report the "
            "lightest member that satisfies every check. Turn it off to draw and "
            "check a specific section."
        )

    loads_out: list[LoadEchoOut] = []
    for d in p.distributed:
        loads_out.append(LoadEchoOut(
            case=d.case, kind="udl", magnitude=d.w, units="kN/m",
            x_start_mm=d.x_start_mm, x_end_mm=d.x_end_mm,
            label=f"{d.case}: {d.w:.3f} kN/m", is_self_weight=False,
        ))
    if self_weight:
        loads_out.append(LoadEchoOut(
            case="D", kind="udl", magnitude=self_weight, units="kN/m",
            x_start_mm=0.0, x_end_mm=p.total_mm,
            label=f"D: {self_weight:.3f} kN/m (self wt.)", is_self_weight=True,
        ))
    for pt in p.points:
        loads_out.append(LoadEchoOut(
            case=pt.case, kind="point", magnitude=pt.P / 1000.0, units="kN",
            x_start_mm=pt.x_mm, x_end_mm=pt.x_mm,
            label=f"{pt.case}: {pt.P / 1000.0:.2f} kN", is_self_weight=False,
        ))

    return PreviewOut(
        ok=True,
        length_mm=round(p.total_mm, 2),
        span_positions_mm=[round(v, 2) for v in supports_mm],
        supports=list(payload.supports),
        loads=loads_out,
        section=section_out,
        description=description,
        total_load_kn=round(
            sum(abs(l.magnitude) * (l.x_end_mm - l.x_start_mm) / 1000.0
                for l in loads_out if l.kind == "udl")
            + sum(abs(l.magnitude) for l in loads_out if l.kind == "point"),
            2,
        ),
    )


def _describe(section: BuiltUpSection, material, self_weight: float) -> str:
    """A sentence an engineer would write on the drawing."""
    s = section
    ply = (
        f"{s.plies} plies of {s.ply_width_mm:.0f} x {s.depth_mm:.0f} mm"
        if s.plies > 1 else f"a single {s.ply_width_mm:.0f} x {s.depth_mm:.0f} mm member"
    )
    parts = [
        f"{material.name}: {ply}, giving {s.width_mm:.0f} x {s.depth_mm:.0f} mm overall.",
        f"A = {s.area_mm2 / 1e3:.1f} x 10\u00b3 mm\u00b2, "
        f"S = {s.section_modulus_mm3 / 1e3:.0f} x 10\u00b3 mm\u00b3, "
        f"I = {s.inertia_mm4 / 1e6:.0f} x 10\u2076 mm\u2074.",
    ]
    if self_weight:
        parts.append(f"Self weight {self_weight:.3f} kN/m, included as dead load.")
    if s.plies > 1:
        parts.append(
            "Plies must be fastened to act together; the section properties above "
            "assume full composite action."
        )
    return " ".join(parts)
