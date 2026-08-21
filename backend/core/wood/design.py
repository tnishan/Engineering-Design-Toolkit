"""Design orchestrator: analysis + CSA O86 checks + automatic member sizing."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.analysis import beam
from core.analysis.beam import (
    BeamGeometry,
    DistributedLoad,
    PointLoad,
    Section,
    build_geometry,
    solve_case,
)
from core.loads import combinations as combos
from core.report.trace import CheckResult, DesignOutcome
from core.units import n_to_kn, nmm_to_knm
from core.wood import checks, materials
from core.wood.factors import Conditions
from core.wood.materials import (
    SCL_MAX_LATERAL_SPACING_MM,
    SCL_MIN_PLIES_DEPTH_MM,
    SCL_MIN_PLIES_WIDTH_MM,
    WoodMaterial,
)
from core.wood.sections import BuiltUpSection, candidates

CASES = ("D", "L", "S", "W")


@dataclass
class DeflectionLimits:
    live_ratio: float = 360.0
    total_ratio: float = 240.0
    # O86-19 Cl. 4.5.3 requires long-term deflection under permanent load to
    # include creep. 1.0 means creep is not applied; the tool warns when so.
    creep_factor: float = 1.0


@dataclass
class DesignRequest:
    spans_mm: list[float]
    support_kinds: list[str]
    material_key: str
    distributed: list[DistributedLoad] = field(default_factory=list)
    points: list[PointLoad] = field(default_factory=list)
    conditions: Conditions = field(default_factory=Conditions)
    limits: DeflectionLimits = field(default_factory=DeflectionLimits)
    left_overhang_mm: float = 0.0
    right_overhang_mm: float = 0.0
    section: BuiltUpSection | None = None  # None -> search for a size
    max_plies: int = 6
    include_wind: bool = False
    include_self_weight: bool = True
    custom_material: WoodMaterial | None = None


@dataclass
class Peak:
    """A labelled extreme value on a diagram, for annotation."""

    label: str
    x_mm: float
    value: float
    units: str
    combo: str


@dataclass
class Diagrams:
    x_mm: list[float]
    shear_min_kn: list[float]
    shear_max_kn: list[float]
    moment_min_knm: list[float]
    moment_max_knm: list[float]
    deflection_live_mm: list[float]
    deflection_total_mm: list[float]
    governing_shear_combo: str
    governing_moment_combo: str
    peaks: list[Peak] = field(default_factory=list)


@dataclass
class SpanLimit:
    """Deflection allowance for one span, so charts can draw the limit line."""

    name: str
    x_start_mm: float
    x_end_mm: float
    reference_length_mm: float
    live_limit_mm: float
    total_limit_mm: float


@dataclass
class ReactionResult:
    """Envelope reaction at one support, with its bearing consequence."""

    x_mm: float
    support_kind: str
    max_kn: float
    governing_combo: str
    required_bearing_mm: float
    bearing_ratio: float


@dataclass
class LoadEcho:
    """A resolved load, in the form the diagrams should draw it."""

    case: str
    kind: str  # "udl" | "point"
    magnitude: float  # kN/m for a UDL, kN for a point load
    units: str
    x_start_mm: float
    x_end_mm: float
    label: str
    is_self_weight: bool = False


@dataclass
class DesignResponse:
    section_label: str
    material_name: str
    material_source: str
    material_verified: bool
    plies: int
    width_mm: float
    depth_mm: float
    outcome: DesignOutcome
    diagrams: Diagrams
    reactions: list[ReactionResult]
    loads: list[LoadEcho]
    span_limits: list[SpanLimit]
    span_positions_mm: list[float]
    length_mm: float
    self_weight_n_per_mm: float
    combos_considered: list[str]
    combo_durations: list[str]
    alternatives: list[dict] = field(default_factory=list)


def _material(req: DesignRequest) -> WoodMaterial:
    if req.custom_material is not None:
        return req.custom_material
    return materials.get(req.material_key)


def _span_windows(geom: BeamGeometry) -> list[tuple[str, float, float, float]]:
    """(name, x_start, x_end, reference length) for each deflection region."""
    xs = sorted(s.x_mm for s in geom.supports if s.kind != "free")
    out: list[tuple[str, float, float, float]] = []
    if xs and xs[0] > 1e-6:
        out.append(("Left cantilever", 0.0, xs[0], 2.0 * xs[0]))
    for i, (a, b) in enumerate(zip(xs[:-1], xs[1:]), start=1):
        out.append((f"Span {i}", a, b, b - a))
    if xs and xs[-1] < geom.length_mm - 1e-6:
        tip = geom.length_mm - xs[-1]
        out.append(("Right cantilever", xs[-1], geom.length_mm, 2.0 * tip))
    return out


def _evaluate(
    req: DesignRequest,
    material: WoodMaterial,
    section: BuiltUpSection,
) -> tuple[
    DesignOutcome, Diagrams, list[ReactionResult], list[LoadEcho],
    list[SpanLimit], list[float], float, float, list[str], list[str],
]:
    sec = Section(
        E_mpa=material.e_mpa,
        I_mm4=section.inertia_mm4,
        A_shear_mm2=section.shear_area_mm2,
        G_mpa=material.g_mpa,
    )
    geom = build_geometry(
        req.spans_mm, req.support_kinds, sec,
        req.left_overhang_mm, req.right_overhang_mm,
    )

    self_weight = section.self_weight_n_per_mm(material) if req.include_self_weight else 0.0
    per_case: dict[str, list[DistributedLoad]] = {c: [] for c in CASES}
    for d in req.distributed:
        per_case.setdefault(d.case, []).append(d)
    if self_weight:
        per_case["D"].append(DistributedLoad(self_weight, 0.0, geom.length_mm, "D"))

    point_by_case: dict[str, list[PointLoad]] = {c: [] for c in CASES}
    for p in req.points:
        point_by_case.setdefault(p.case, []).append(p)

    # Every case must share one mesh: a point load or partial UDL carried by
    # only one case would otherwise put a break in that case's mesh but not
    # the others, giving the cases different-length result arrays and making
    # them impossible to envelope (min/max element-wise across cases).
    all_breaks_mm = [p.x_mm for p in req.points]
    for d in req.distributed:
        all_breaks_mm.extend((d.x_start_mm, d.x_end_mm))

    solved = {
        c: solve_case(geom, per_case.get(c, []), point_by_case.get(c, []), all_breaks_mm)
        for c in CASES
    }

    cset = combos.build(include_wind=req.include_wind)
    active = {c for c, loads in per_case.items() if loads} | {
        p.case for p in req.points
    }
    uls = combos.relevant(cset.uls, active)
    outcome = DesignOutcome()

    x = solved["D"].x_mm
    shear_min = np.full_like(x, np.inf)
    shear_max = np.full_like(x, -np.inf)
    moment_min = np.full_like(x, np.inf)
    moment_max = np.full_like(x, -np.inf)

    best_moment: CheckResult | None = None
    best_shear: CheckResult | None = None
    best_bearing: CheckResult | None = None
    gov_shear_combo = gov_moment_combo = ""
    peak_v = peak_m = 0.0
    # Track the signed extremes separately so the diagrams can be annotated
    # with both the sagging and the hogging peak, not just the larger one.
    peak_sag = {"value": 0.0, "x": 0.0, "combo": ""}
    peak_hog = {"value": 0.0, "x": 0.0, "combo": ""}
    peak_shear = {"value": 0.0, "x": 0.0, "combo": ""}
    reaction_state: dict[float, dict] = {}

    for combo in uls:
        r = beam.combine(solved, combo.factors)
        shear_min = np.minimum(shear_min, r.shear_n)
        shear_max = np.maximum(shear_max, r.shear_n)
        moment_min = np.minimum(moment_min, r.moment_nmm)
        moment_max = np.maximum(moment_max, r.moment_nmm)

        i_m = int(np.argmax(np.abs(r.moment_nmm)))
        i_v = int(np.argmax(np.abs(r.shear_n)))
        m_demand = float(r.moment_nmm[i_m])
        v_demand = float(r.shear_n[i_v])

        mc = checks.moment_check(
            material, section, req.conditions, combo.kd_duration,
            m_demand, combo.label, float(x[i_m]),
        )
        vc = checks.shear_check(
            material, section, req.conditions, combo.kd_duration,
            v_demand, combo.label, float(x[i_v]),
        )
        if best_moment is None or mc.ratio > best_moment.ratio:
            best_moment = mc
        if best_shear is None or vc.ratio > best_shear.ratio:
            best_shear = vc
        if abs(m_demand) > peak_m:
            peak_m, gov_moment_combo = abs(m_demand), combo.label
        if abs(v_demand) > peak_v:
            peak_v, gov_shear_combo = abs(v_demand), combo.label

        i_sag = int(np.argmax(r.moment_nmm))
        if r.moment_nmm[i_sag] > peak_sag["value"]:
            peak_sag.update(value=float(r.moment_nmm[i_sag]),
                            x=float(x[i_sag]), combo=combo.label)
        i_hog = int(np.argmin(r.moment_nmm))
        if r.moment_nmm[i_hog] < peak_hog["value"]:
            peak_hog.update(value=float(r.moment_nmm[i_hog]),
                            x=float(x[i_hog]), combo=combo.label)
        if abs(v_demand) > abs(peak_shear["value"]):
            peak_shear.update(value=v_demand, x=float(x[i_v]), combo=combo.label)

        for xr, rv in r.reactions_n.items():
            bc = checks.bearing_check(
                material, section, req.conditions, rv, combo.label, xr,
            )
            if best_bearing is None or bc.ratio > best_bearing.ratio:
                best_bearing = bc
            state = reaction_state.get(xr)
            if state is None or abs(rv) > state["n"]:
                reaction_state[xr] = {
                    "n": abs(rv),
                    "combo": combo.label,
                    "ratio": bc.ratio,
                    # Bearing resistance is proportional to bearing area, so
                    # the length needed scales directly with the utilisation.
                    "required_mm": req.conditions.bearing_length_mm * bc.ratio,
                }

    for c in (best_moment, best_shear, best_bearing):
        if c is not None:
            outcome.checks.append(c)

    # --- serviceability -------------------------------------------------
    windows = _span_windows(geom)
    span_limits = [
        SpanLimit(
            name=name,
            x_start_mm=a,
            x_end_mm=b,
            reference_length_mm=ref_len,
            live_limit_mm=ref_len / req.limits.live_ratio,
            total_limit_mm=ref_len / req.limits.total_ratio,
        )
        for name, a, b, ref_len in windows
    ]
    live_curve = np.zeros_like(x)
    total_curve = np.zeros_like(x)

    transient = beam.combine(solved, {"L": 1.0, "S": 1.0})
    dead_only = beam.combine(solved, {"D": 1.0})
    total = dead_only.deflection_mm * req.limits.creep_factor + transient.deflection_mm
    live_curve = transient.deflection_mm
    total_curve = total

    for name, a, b, ref_len in windows:
        mask = (x >= a - 1e-6) & (x <= b + 1e-6)
        if not mask.any():
            continue
        i_live = int(np.argmax(np.abs(live_curve[mask])))
        i_total = int(np.argmax(np.abs(total_curve[mask])))
        xs_window = x[mask]
        outcome.checks.append(
            checks.deflection_check(
                "deflection_live", "Live/snow", float(live_curve[mask][i_live]),
                ref_len, req.limits.live_ratio, "L + S (specified)", name,
                float(xs_window[i_live]),
            )
        )
        outcome.checks.append(
            checks.deflection_check(
                "deflection_total", "Total", float(total_curve[mask][i_total]),
                ref_len, req.limits.total_ratio, "D + L + S (specified)", name,
                float(xs_window[i_total]),
            )
        )

    diagrams = Diagrams(
        x_mm=[round(float(v), 2) for v in x],
        shear_min_kn=[round(n_to_kn(float(v)), 4) for v in shear_min],
        shear_max_kn=[round(n_to_kn(float(v)), 4) for v in shear_max],
        moment_min_knm=[round(nmm_to_knm(float(v)), 5) for v in moment_min],
        moment_max_knm=[round(nmm_to_knm(float(v)), 5) for v in moment_max],
        deflection_live_mm=[round(float(v), 4) for v in live_curve],
        deflection_total_mm=[round(float(v), 4) for v in total_curve],
        governing_shear_combo=gov_shear_combo,
        governing_moment_combo=gov_moment_combo,
        peaks=[
            p for p in (
                Peak("Max sagging", peak_sag["x"], nmm_to_knm(peak_sag["value"]),
                     "kN.m", peak_sag["combo"]),
                Peak("Max hogging", peak_hog["x"], nmm_to_knm(peak_hog["value"]),
                     "kN.m", peak_hog["combo"]),
                Peak("Max shear", peak_shear["x"], n_to_kn(peak_shear["value"]),
                     "kN", peak_shear["combo"]),
            ) if p.value
        ],
    )

    def _kind_at(xr: float) -> str:
        nearest = min(geom.supports, key=lambda s: abs(s.x_mm - xr))
        return nearest.kind

    reactions = [
        ReactionResult(
            x_mm=xr,
            support_kind=_kind_at(xr),
            max_kn=n_to_kn(st["n"]),
            governing_combo=st["combo"],
            required_bearing_mm=st["required_mm"],
            bearing_ratio=st["ratio"],
        )
        for xr, st in sorted(reaction_state.items())
    ]

    load_echo: list[LoadEcho] = []
    for case in CASES:
        for d in per_case.get(case, []):
            is_sw = req.include_self_weight and d.w == self_weight and self_weight
            load_echo.append(LoadEcho(
                case=case, kind="udl", magnitude=d.w, units="kN/m",
                x_start_mm=d.x_start_mm, x_end_mm=d.x_end_mm,
                label=f"{case}: {d.w:.3f} kN/m" + (" (self wt.)" if is_sw else ""),
                is_self_weight=bool(is_sw),
            ))
        for p in point_by_case.get(case, []):
            load_echo.append(LoadEcho(
                case=case, kind="point", magnitude=n_to_kn(p.P), units="kN",
                x_start_mm=p.x_mm, x_end_mm=p.x_mm,
                label=f"{case}: {n_to_kn(p.P):.2f} kN",
            ))

    labels = [c.label for c in uls]
    durations = [c.kd_duration for c in uls]
    supports_mm = [s.x_mm for s in geom.supports]
    return (outcome, diagrams, reactions, load_echo, span_limits, supports_mm,
            geom.length_mm, self_weight, labels, durations)


def _warnings(req: DesignRequest, material: WoodMaterial, section: BuiltUpSection,
              outcome: DesignOutcome) -> list[str]:
    out: list[str] = []

    if not material.verified:
        out.append(
            f"Material properties for {material.name} are a transcription of "
            f"{material.source}. Verify every value against a licensed copy of "
            f"CSA O86 before using this output on a project."
        )

    if material.family == "scl":
        out.append(
            f"{material.name} design values assume lateral support at bearings and at "
            f"{SCL_MAX_LATERAL_SPACING_MM / 25.4:.0f} in. ({SCL_MAX_LATERAL_SPACING_MM:.0f} mm) "
            "on-centre maximum along the span, per the TJ-9500 general assumptions."
        )
        if (
            section.plies == 1
            and abs(section.ply_width_mm - SCL_MIN_PLIES_WIDTH_MM) < 1e-6
            and section.depth_mm >= SCL_MIN_PLIES_DEPTH_MM - 1e-6
        ):
            out.append(
                "Weyerhaeuser requires beams 1-3/4 in. x 16 in. and deeper to be "
                "multiple plies. Use two or more plies, or confirm the single-ply "
                "exception with Weyerhaeuser software."
            )
        if section.plies > 1:
            out.append(
                "Multi-ply SCL must be fastened per TJ-9500 pages 16-18. Side-loaded "
                "plies beyond two require through-bolting or top-loading; confirm the "
                "connection detail transfers load to every ply."
            )

    if not req.conditions.laterally_supported:
        out.append(
            "Member declared without continuous lateral support. K_L was taken as 1.0; "
            "an explicit lateral-torsional stability check is required."
        )

    if req.limits.creep_factor <= 1.0:
        out.append(
            "Total deflection excludes creep (creep factor 1.0). CSA O86-19 Cl. 4.5.3 "
            "requires long-term deflection under permanent load to be multiplied by 2.0 "
            "for sawn lumber in dry service."
        )

    if req.conditions.system in ("case1", "case2"):
        out.append(
            "System factor K_H applied. Cl. 6.4.4 Case 1 requires at least three "
            "members spaced 610 mm or less sharing load through a distributing "
            "element - a single built-up girder does not qualify."
        )

    bearing = next((c for c in outcome.checks if c.check == "bearing"), None)
    if bearing is not None and bearing.note:
        out.append(bearing.note + " (increase bearing length or add a column cap if longer than provided).")

    return out


def run(req: DesignRequest) -> DesignResponse:
    """Analyse and check a member; if no section is given, search for one."""
    material = _material(req)

    if req.section is not None:
        trials = [req.section]
    else:
        trials = candidates(material, req.max_plies)

    first_pass: DesignResponse | None = None
    alternatives: list[dict] = []
    last: DesignResponse | None = None

    for section in trials:
        (outcome, diagrams, reactions, loads, span_limits, supports_mm,
         length_mm, sw, labels, durations) = _evaluate(req, material, section)
        outcome.warnings = _warnings(req, material, section, outcome)
        resp = DesignResponse(
            section_label=section.label(material),
            material_name=material.name,
            material_source=material.source,
            material_verified=material.verified,
            plies=section.plies,
            width_mm=section.width_mm,
            depth_mm=section.depth_mm,
            outcome=outcome,
            diagrams=diagrams,
            reactions=reactions,
            loads=loads,
            span_limits=span_limits,
            span_positions_mm=supports_mm,
            length_mm=length_mm,
            self_weight_n_per_mm=sw,
            combos_considered=labels,
            combo_durations=durations,
        )
        last = resp

        if outcome.passed:
            if first_pass is None:
                first_pass = resp
            gov = outcome.governing
            alternatives.append({
                "label": section.label(material),
                "plies": section.plies,
                "width_mm": section.width_mm,
                "depth_mm": section.depth_mm,
                "max_ratio": round(outcome.max_ratio, 3),
                "governing_check": gov.check if gov else "",
            })
            if len(alternatives) >= 8 and req.section is None:
                break

    result = first_pass or last
    assert result is not None
    result.alternatives = alternatives
    return result
