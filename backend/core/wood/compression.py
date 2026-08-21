"""Post and column design.

Sawn lumber is designed to CSA O86-19 Cl. 6.5.6:

    P_r  = phi * F_c * A * K_Zcg * K_C
    F_c  = f_c (K_D K_H K_Sc K_T)
    K_Zcg = 6.3 (d L)^-0.13  <= 1.3                       Cl. 6.5.6.2.2
    K_C  = [1 + (F_c K_Zcg C_c^3) / (35 E_05 K_SE K_T)]^-1  Cl. 6.5.6.2.3
    C_c  = L_e / d  <= 50                                  Cl. 6.5.6.2.3

Structural composite lumber columns are NOT computed from this formula - see
``scl_columns`` for why - and are read from the manufacturer's published table
instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.report.trace import CheckResult, DesignOutcome, FactorTrace
from core.units import n_to_kn
from core.wood import factors as F
from core.wood import scl_columns
from core.wood.factors import Conditions
from core.wood.materials import WoodMaterial
from core.wood.sections import BuiltUpSection

MAX_SLENDERNESS = 50.0

# Effective length factors, CSA O86-19 Table A.6.5.6.1. The values in
# parentheses in that table are the recommended design values, which are what
# is used here.
END_CONDITIONS: dict[str, tuple[float, str]] = {
    "pinned-pinned": (1.00, "Both ends pinned, translation restrained"),
    "fixed-pinned": (0.80, "One end fixed, one pinned, translation restrained"),
    "fixed-fixed": (0.65, "Both ends fixed, translation restrained"),
    "fixed-free": (2.40, "One end fixed, one end free (flagpole)"),
    "fixed-fixed-sway": (1.20, "Both ends rotation-fixed, one end free to sway"),
}


class PostDesignError(ValueError):
    """Raised for an invalid or out-of-range post."""


@dataclass
class PostRequest:
    length_mm: float
    axial_kn: dict[str, float] = field(default_factory=dict)  # by load case
    material_key: str = "SPF-No1No2"
    section: BuiltUpSection | None = None
    conditions: Conditions = field(default_factory=Conditions)
    end_condition_d: str = "pinned-pinned"
    end_condition_b: str = "pinned-pinned"
    # Unbraced length about each axis; defaults to the full length.
    unbraced_d_mm: float | None = None
    unbraced_b_mm: float | None = None
    plies_act_together: bool = True
    include_wind: bool = False
    # SCL products only
    scl_product: str | None = None
    scl_size_index: int = 0
    scl_bearing: str = "column_base"


@dataclass
class PostResponse:
    label: str
    material_name: str
    material_source: str
    material_verified: bool
    method: str  # "O86 Cl. 6.5.6" | "manufacturer table"
    width_mm: float
    depth_mm: float
    plies: int
    area_mm2: float
    slenderness: float
    slenderness_axis: str
    demand_kn: float
    resistance_kn: float
    governing_combo: str
    outcome: DesignOutcome
    capacity_curve: list[dict] = field(default_factory=list)
    independent_ply_resistance_kn: float | None = None


def effective_length(kind: str, unbraced_mm: float) -> tuple[float, FactorTrace]:
    if kind not in END_CONDITIONS:
        raise PostDesignError(
            f"Unknown end condition {kind!r}; expected one of {sorted(END_CONDITIONS)}"
        )
    ke, description = END_CONDITIONS[kind]
    return ke * unbraced_mm, FactorTrace(
        "K_e", ke, "O86-19 Table A.6.5.6.1", description
    )


def kzcg(least_dim_mm: float, length_mm: float) -> FactorTrace:
    """Size factor for compression, Cl. 6.5.6.2.2: 6.3 (dL)^-0.13 <= 1.3."""
    value = min(1.3, 6.3 * (least_dim_mm * length_mm) ** -0.13)
    return FactorTrace(
        "K_Zcg", value, "O86-19 Cl. 6.5.6.2.2",
        f"6.3 x ({least_dim_mm:.0f} x {length_mm:.0f})^-0.13, capped at 1.3",
    )


def kc(fc_mpa: float, kzcg_value: float, cc: float, e05_mpa: float) -> FactorTrace:
    """Slenderness factor, Cl. 6.5.6.2.3."""
    denominator = 35.0 * e05_mpa
    value = 1.0 / (1.0 + (fc_mpa * kzcg_value * cc**3) / denominator)
    return FactorTrace(
        "K_C", value, "O86-19 Cl. 6.5.6.2.3",
        f"[1 + ({fc_mpa:.2f} x {kzcg_value:.3f} x {cc:.1f}^3) / (35 x {e05_mpa:.0f})]^-1",
    )


def _sawn_resistance(
    material: WoodMaterial,
    section: BuiltUpSection,
    req: PostRequest,
    duration: str,
    width_mm: float,
    depth_mm: float,
) -> tuple[float, float, str, list[FactorTrace], str]:
    """Return (P_r in N, slenderness, governing axis, factor traces, substitution)."""
    traces = [
        F.kd(duration),
        F.kh(req.conditions.system, "compression"),
        F.ks(req.conditions.service, "compression"),
        F.kt(req.conditions.treatment),
    ]
    fc = material.fc_mpa
    for t in traces:
        fc *= t.value

    kse = F.ks(req.conditions.service, "E")
    kt_e = F.kt(req.conditions.treatment, "E")
    e05 = material.e05_mpa * kse.value * kt_e.value

    unbraced_d = req.unbraced_d_mm or req.length_mm
    unbraced_b = req.unbraced_b_mm or req.length_mm
    le_d, ke_d = effective_length(req.end_condition_d, unbraced_d)
    le_b, ke_b = effective_length(req.end_condition_b, unbraced_b)

    # Buckling is checked about both axes; the larger slenderness governs.
    cc_d = le_d / depth_mm
    cc_b = le_b / width_mm
    if cc_d >= cc_b:
        cc, axis, ke_trace, le = cc_d, "depth", ke_d, le_d
    else:
        cc, axis, ke_trace, le = cc_b, "width", ke_b, le_b

    if cc > MAX_SLENDERNESS:
        raise PostDesignError(
            f"Slenderness ratio C_c = {cc:.1f} exceeds the CSA O86 limit of 50 "
            f"(effective length {le:.0f} mm about the {axis} axis). "
            "Use a larger section or brace the post."
        )

    least = min(width_mm, depth_mm)
    kz = kzcg(least, req.length_mm)
    k_c = kc(fc, kz.value, cc, e05)

    area = width_mm * depth_mm
    pr = F.PHI_COMPRESSION * fc * area * kz.value * k_c.value

    substitution = (
        f"P_r = 0.8 x {fc:.2f} MPa x {area / 1e3:.4g} x 10^3 mm^2 "
        f"x {kz.value:.3f} x {k_c.value:.4f} = {n_to_kn(pr):.2f} kN"
    )
    return pr, cc, axis, traces + [kse, ke_trace, kz, k_c], substitution


def design(
    req: PostRequest,
    material: WoodMaterial | None = None,
) -> PostResponse:
    """Design a post for the given axial loads."""
    from core.loads import combinations as combos
    from core.wood import materials as materials_mod

    if req.length_mm <= 0:
        raise PostDesignError("Post length must be greater than zero.")

    active = {c for c, v in req.axial_kn.items() if v}
    if not active:
        raise PostDesignError("Enter at least one axial load.")

    uls = combos.relevant(
        combos.uls_combinations(include_wind=req.include_wind), active
    )

    outcome = DesignOutcome()

    # ---- SCL: read the manufacturer's published table -------------------
    if req.scl_product:
        product = scl_columns.PRODUCTS.get(req.scl_product)
        if product is None:
            raise PostDesignError(f"Unknown SCL column product {req.scl_product!r}.")
        size = product.sizes[req.scl_size_index]
        try:
            pr, note = scl_columns.capacity_n(
                req.scl_product, req.scl_size_index, req.length_mm, req.scl_bearing
            )
        except scl_columns.SclColumnError as exc:
            raise PostDesignError(str(exc)) from exc

        demand_n, combo_label = _worst_demand(uls, req.axial_kn)
        cc = req.length_mm / size.least_dimension_mm

        outcome.checks.append(CheckResult(
            check="compression",
            label="Axial compression",
            demand=n_to_kn(demand_n),
            resistance=n_to_kn(pr),
            units="kN",
            combo_label=combo_label,
            clause=scl_columns.TJ_SOURCE,
            formula="P_r read from the manufacturer's published factored resistance table",
            substitution=note,
            location_mm=None,
            note=(
                "Published values are standard term. Using them for a snow- or "
                "wind-governed case is conservative, since no short-term duration "
                "increase has been taken."
            ),
        ))
        outcome.warnings = _scl_warnings(product, size, req, cc)

        return PostResponse(
            label=f"{size.label} {product.name}",
            material_name=product.name,
            material_source=scl_columns.TJ_SOURCE,
            material_verified=True,
            method="manufacturer table",
            width_mm=size.width_mm,
            depth_mm=size.depth_mm,
            plies=1,
            area_mm2=size.width_mm * size.depth_mm,
            slenderness=cc,
            slenderness_axis="least dimension",
            demand_kn=n_to_kn(demand_n),
            resistance_kn=n_to_kn(pr),
            governing_combo=combo_label,
            outcome=outcome,
            capacity_curve=_scl_curve(req),
        )

    # ---- Sawn lumber: compute per O86 Cl. 6.5.6 -------------------------
    material = material or materials_mod.get(req.material_key)
    if req.section is None:
        raise PostDesignError("A section is required for a sawn lumber post.")
    section = req.section

    best: CheckResult | None = None
    best_pr = best_cc = 0.0
    best_axis = ""
    for combo in uls:
        demand_n = _combo_demand(combo, req.axial_kn)
        pr, cc, axis, traces, substitution = _sawn_resistance(
            material, section, req, combo.kd_duration,
            section.width_mm, section.depth_mm,
        )
        result = CheckResult(
            check="compression",
            label="Axial compression",
            demand=n_to_kn(demand_n),
            resistance=n_to_kn(pr),
            units="kN",
            combo_label=combo.label,
            clause="O86-19 Cl. 6.5.6",
            formula="P_r = phi_c * F_c * A * K_Zcg * K_C",
            substitution=substitution,
            location_mm=None,
            factors=traces,
        )
        if best is None or result.ratio > best.ratio:
            best, best_pr, best_cc, best_axis = result, pr, cc, axis

    assert best is not None
    outcome.checks.append(best)

    # Bearing of the post onto whatever supports it.
    bearing = _bearing_check(material, section, req, best.demand, best.combo_label)
    outcome.checks.append(bearing)

    independent_kn = None
    if section.plies > 1:
        independent_kn = _independent_ply_capacity(material, section, req)

    outcome.warnings = _sawn_warnings(material, section, req, best_cc, independent_kn, best)

    return PostResponse(
        label=section.label(material),
        material_name=material.name,
        material_source=material.source,
        material_verified=material.verified,
        method="O86 Cl. 6.5.6",
        width_mm=section.width_mm,
        depth_mm=section.depth_mm,
        plies=section.plies,
        area_mm2=section.area_mm2,
        slenderness=best_cc,
        slenderness_axis=best_axis,
        demand_kn=best.demand,
        resistance_kn=best.resistance,
        governing_combo=best.combo_label,
        outcome=outcome,
        capacity_curve=_sawn_curve(material, section, req),
        independent_ply_resistance_kn=independent_kn,
    )


def _combo_demand(combo, axial_kn: dict[str, float]) -> float:
    return sum(
        combo.factors.get(case, 0.0) * value * 1000.0
        for case, value in axial_kn.items()
    )


def _worst_demand(uls, axial_kn: dict[str, float]) -> tuple[float, str]:
    best_n, best_label = 0.0, ""
    for combo in uls:
        n = _combo_demand(combo, axial_kn)
        if n > best_n:
            best_n, best_label = n, combo.label
    return best_n, best_label


def _bearing_check(
    material: WoodMaterial,
    section: BuiltUpSection,
    req: PostRequest,
    demand_kn: float,
    combo_label: str,
) -> CheckResult:
    """Compression perpendicular to grain where the post lands on a plate."""
    traces = [
        F.ks(req.conditions.service, "bearing"),
        F.kt(req.conditions.treatment),
    ]
    fcp = material.fcp_mpa
    for t in traces:
        fcp *= t.value

    area = section.area_mm2
    qr = F.PHI_BEARING * fcp * area
    return CheckResult(
        check="bearing",
        label="Bearing of post on supporting plate",
        demand=demand_kn,
        resistance=n_to_kn(qr),
        units="kN",
        combo_label=combo_label,
        clause="O86-19 Cl. 6.5.7",
        formula="Q_r = phi_cp * F_cp * A",
        substitution=(
            f"Q_r = 0.8 x {fcp:.2f} MPa x {area / 1e3:.4g} x 10^3 mm^2 "
            f"= {n_to_kn(qr):.2f} kN"
        ),
        location_mm=None,
        note=(
            "Checks the post crushing the member it bears on, assuming that member "
            "has the same f_cp. If the post lands on a different species or on a "
            "steel plate or concrete, check that material instead."
        ),
        factors=traces,
    )


def _independent_ply_capacity(
    material: WoodMaterial, section: BuiltUpSection, req: PostRequest
) -> float | None:
    """Capacity if the plies buckle individually about their own weak axis.

    Returns None when a single ply is itself too slender to qualify as a
    column at all, which is the more serious case: the fastening is then not
    merely beneficial but load-bearing.
    """
    single = BuiltUpSection(section.ply_width_mm, section.depth_mm, plies=1)
    try:
        pr, _, _, _, _ = _sawn_resistance(
            material, single, req, "standard",
            single.width_mm, single.depth_mm,
        )
    except PostDesignError:
        return None
    return n_to_kn(pr * section.plies)


def _sawn_curve(
    material: WoodMaterial, section: BuiltUpSection, req: PostRequest
) -> list[dict]:
    """Capacity against unbraced length, for the chart."""
    out: list[dict] = []
    least = min(section.width_mm, section.depth_mm)
    max_len = MAX_SLENDERNESS * least  # Cc = 50 with Ke = 1.0
    steps = 40
    for i in range(1, steps + 1):
        length = max_len * i / steps
        probe = PostRequest(
            length_mm=length,
            axial_kn=req.axial_kn,
            material_key=req.material_key,
            section=section,
            conditions=req.conditions,
            end_condition_d=req.end_condition_d,
            end_condition_b=req.end_condition_b,
        )
        try:
            pr, _, _, _, _ = _sawn_resistance(
                material, section, probe, "standard",
                section.width_mm, section.depth_mm,
            )
        except PostDesignError:
            continue
        out.append({"length_mm": round(length, 1), "resistance_kn": round(n_to_kn(pr), 3)})
    return out


def _scl_curve(req: PostRequest) -> list[dict]:
    product = scl_columns.PRODUCTS[req.scl_product]
    table = product.tables[req.scl_bearing]
    lengths = sorted(l for l in table if table[l][req.scl_size_index] is not None)
    out = []
    for length_ft in lengths:
        value = table[length_ft][req.scl_size_index]
        out.append({
            "length_mm": round(length_ft * 304.8, 1),
            "resistance_kn": round(float(value) * 4.4482216153e-3, 3),
        })
    return out


def _sawn_warnings(
    material: WoodMaterial,
    section: BuiltUpSection,
    req: PostRequest,
    cc: float,
    independent_kn: float | None,
    check: CheckResult,
) -> list[str]:
    out: list[str] = []
    if not material.verified:
        out.append(
            f"Material properties for {material.name} are a transcription of "
            f"{material.source}. Verify f_c and E_05 against a licensed copy of "
            "CSA O86 before using this output on a project."
        )
    if cc > 40:
        out.append(
            f"Slenderness ratio C_c = {cc:.1f} is close to the CSA O86 limit of 50. "
            "Capacity falls off steeply here - a modest increase in section, or "
            "bracing at mid-height, buys a lot."
        )
    if section.plies > 1:
        out.append(
            "Built-up post. CSA O86 Cl. 6.5.6 requires the plies to be fastened so "
            "they act as a unit; otherwise each ply buckles about its own weak axis."
        )
        single_slenderness = req.length_mm / section.ply_width_mm
        if independent_kn is None:
            out.append(
                f"A single {section.ply_width_mm:.0f} mm ply over this length has a "
                f"slenderness ratio of about {single_slenderness:.0f}, past the limit "
                "of 50. The plies cannot be assumed to act individually at all, so the "
                "ply fastening is carrying the design, not merely improving it."
            )
        elif independent_kn < check.demand:
            out.append(
                f"If the plies are NOT adequately fastened the capacity drops to about "
                f"{independent_kn:.1f} kN, which is less than the {check.demand:.1f} kN "
                "demand. The ply connection is critical here, not incidental."
            )
    if req.conditions.service == "wet":
        out.append(
            "Wet service. Confirm the post is not in direct ground or concrete "
            "contact without preservative treatment."
        )
    return out


def _scl_warnings(product, size, req: PostRequest, cc: float) -> list[str]:
    out = [
        f"Capacity read from {scl_columns.TJ_SOURCE}, not computed. The CSA O86 "
        "Cl. 6.5.6 slenderness formula does not reproduce these published values, "
        "so the manufacturer's table governs.",
        "Published table assumes solid one-piece members, dry service, bracing in "
        "both directions at the column ends, and axial load only. For side loads or "
        "combined bending and axial load, use the CSA O86 provisions.",
    ]
    if req.scl_bearing == "wood_plate":
        out.append(
            "Bearing on a wood plate limits the capacity at short lengths through "
            "compression perpendicular to grain in the plate."
        )
    if cc > 40:
        out.append(
            f"Slenderness ratio is about {cc:.0f} on the least dimension; the "
            "published table stops where it would exceed 50."
        )
    return out
