"""CSA O86-19 resistance calculations for flexural members."""

from __future__ import annotations

from core.report.trace import CheckResult, FactorTrace
from core.units import n_to_kn, nmm_to_knm
from core.wood import factors as F
from core.wood.factors import Conditions
from core.wood.materials import WoodMaterial
from core.wood.sections import BuiltUpSection


def _fb(material: WoodMaterial, section: BuiltUpSection, conditions: Conditions,
        duration: str) -> tuple[float, list[FactorTrace]]:
    """Factored specified bending strength F_b and the factors behind it."""
    traces = [
        F.kd(duration),
        F.kh(conditions.system, "bending"),
        F.ks(conditions.service, "bending"),
        F.kt(conditions.treatment),
    ]
    base = material.fb_at_depth(section.depth_mm)
    if material.depth_ref_mm is not None:
        traces.append(FactorTrace(
            "depth adj.", material.depth_factor(section.depth_mm),
            material.source,
            f"(12 in./{section.depth_mm / 25.4:.3g} in.)^{material.depth_exponent} on f_b",
        ))
    value = base
    for t in traces:
        if t.symbol != "depth adj.":
            value *= t.value
    return value, traces


def moment_check(
    material: WoodMaterial,
    section: BuiltUpSection,
    conditions: Conditions,
    duration: str,
    demand_nmm: float,
    combo_label: str,
    location_mm: float,
) -> CheckResult:
    """M_r = phi * F_b * S * K_Zb * K_L  (O86-19 Cl. 6.5.4 / Cl. 13 for SCL)."""
    fb, traces = _fb(material, section, conditions, duration)
    kzb = F.kz(material, section, "bending")
    kl = F.kl(material, conditions)
    traces = traces + [kzb, kl]

    S = section.section_modulus_mm3
    mr = F.PHI_BENDING * fb * S * kzb.value * kl.value

    clause = "O86-19 Cl. 13.5" if material.family != "sawn" else "O86-19 Cl. 6.5.4"
    return CheckResult(
        check="moment",
        label="Bending moment",
        demand=nmm_to_knm(abs(demand_nmm)),
        resistance=nmm_to_knm(mr),
        units="kN.m",
        combo_label=combo_label,
        clause=clause,
        formula="M_r = phi_b * F_b * S * K_Zb * K_L",
        substitution=(
            f"M_r = 0.9 x {fb:.2f} MPa x {S / 1e3:.4g} x 10^3 mm^3 "
            f"x {kzb.value:.2f} x {kl.value:.2f} = {nmm_to_knm(mr):.2f} kN.m"
        ),
        location_mm=location_mm,
        factors=traces,
    )


def shear_check(
    material: WoodMaterial,
    section: BuiltUpSection,
    conditions: Conditions,
    duration: str,
    demand_n: float,
    combo_label: str,
    location_mm: float,
) -> CheckResult:
    """V_r = phi * F_v * (2/3) * A * K_Zv  (O86-19 Cl. 6.5.5 / Cl. 13 for SCL)."""
    traces = [
        F.kd(duration),
        F.kh(conditions.system, "shear"),
        F.ks(conditions.service, "shear"),
        F.kt(conditions.treatment),
    ]
    fv = material.fv_mpa
    for t in traces:
        fv *= t.value

    kzv = F.kz(material, section, "shear")
    traces = traces + [kzv]

    A = section.area_mm2
    vr = F.PHI_SHEAR * fv * (2.0 / 3.0) * A * kzv.value

    clause = "O86-19 Cl. 13.5" if material.family != "sawn" else "O86-19 Cl. 6.5.5"
    return CheckResult(
        check="shear",
        label="Longitudinal shear",
        demand=n_to_kn(abs(demand_n)),
        resistance=n_to_kn(vr),
        units="kN",
        combo_label=combo_label,
        clause=clause,
        formula="V_r = phi_v * F_v * (2/3) * A_g * K_Zv",
        substitution=(
            f"V_r = 0.9 x {fv:.3f} MPa x (2/3) x {A / 1e3:.4g} x 10^3 mm^2 "
            f"x {kzv.value:.2f} = {n_to_kn(vr):.2f} kN"
        ),
        location_mm=location_mm,
        factors=traces,
    )


def bearing_check(
    material: WoodMaterial,
    section: BuiltUpSection,
    conditions: Conditions,
    reaction_n: float,
    combo_label: str,
    location_mm: float,
) -> CheckResult:
    """Q_r = phi * F_cp * A_b * K_B * K_Zcp  (O86-19 Cl. 6.5.7).

    Duration of load K_D is deliberately not applied to compression
    perpendicular to grain, per O86 Cl. 6.5.7.
    """
    traces = [
        F.ks(conditions.service, "bearing"),
        F.kt(conditions.treatment),
    ]
    fcp = material.fcp_mpa
    for t in traces:
        fcp *= t.value

    kb = F.kb(conditions)
    kzcp = F.kz(material, section, "bearing")
    traces = traces + [kb, kzcp]

    ab = section.width_mm * conditions.bearing_length_mm
    qr = F.PHI_BEARING * fcp * ab * kb.value * kzcp.value

    return CheckResult(
        check="bearing",
        label="Bearing (compression perpendicular to grain)",
        demand=n_to_kn(abs(reaction_n)),
        resistance=n_to_kn(qr),
        units="kN",
        combo_label=combo_label,
        clause="O86-19 Cl. 6.5.7",
        formula="Q_r = phi_cp * F_cp * A_b * K_B * K_Zcp",
        substitution=(
            f"Q_r = 0.8 x {fcp:.2f} MPa x ({section.width_mm:.0f} x "
            f"{conditions.bearing_length_mm:.0f}) mm^2 x {kb.value:.2f} x "
            f"{kzcp.value:.2f} = {n_to_kn(qr):.2f} kN"
        ),
        location_mm=location_mm,
        note=f"Required bearing length at this support: {_required_bearing(qr, reaction_n, conditions):.0f} mm",
        factors=traces,
    )


def _required_bearing(qr_n: float, reaction_n: float, conditions: Conditions) -> float:
    if qr_n <= 0:
        return float("inf")
    return conditions.bearing_length_mm * abs(reaction_n) / qr_n


def deflection_check(
    kind: str,
    label: str,
    deflection_mm: float,
    span_mm: float,
    limit_ratio: float,
    combo_label: str,
    span_name: str,
    location_mm: float,
) -> CheckResult:
    limit = span_mm / limit_ratio
    return CheckResult(
        check=kind,
        label=f"{label} deflection - {span_name}",
        demand=abs(deflection_mm),
        resistance=limit,
        units="mm",
        combo_label=combo_label,
        clause="OBC 2024 Div. B Table 9.4.3.1 / O86-19 Cl. 4.5.3",
        formula=f"delta <= L / {limit_ratio:g}",
        substitution=(
            f"delta = {abs(deflection_mm):.2f} mm vs L/{limit_ratio:g} = "
            f"{span_mm:.0f}/{limit_ratio:g} = {limit:.2f} mm"
        ),
        location_mm=location_mm,
    )
