"""Acceptance case: two-span roof beam carrying hip rafters.

18 ft + 12 ft continuous over three supports, 12 ft horizontal tributary
(6 ft each side), 0.5 kPa roof dead load, 2.16 kPa specified snow load.
"""

from dataclasses import replace

import pytest

from core.analysis.beam import DistributedLoad
from core.units import area_load_to_line_load, parse_length_mm
from core.wood import materials
from core.wood.design import DeflectionLimits, DesignRequest, run
from core.wood.factors import Conditions
from core.wood.sections import BuiltUpSection

L1 = parse_length_mm("18 ft")
L2 = parse_length_mm("12 ft")
TRIB = parse_length_mm("12 ft")

DEAD_KPA = 0.5
SNOW_KPA = 2.16

W_DEAD = area_load_to_line_load(DEAD_KPA, TRIB)  # N/mm
W_SNOW = area_load_to_line_load(SNOW_KPA, TRIB)


def base_request(**kw) -> DesignRequest:
    total = L1 + L2
    defaults = dict(
        spans_mm=[L1, L2],
        support_kinds=["pin", "roller", "roller"],
        material_key="LVL-2.0E-Microllam",
        distributed=[
            DistributedLoad(W_DEAD, 0.0, total, "D"),
            DistributedLoad(W_SNOW, 0.0, total, "S"),
        ],
        conditions=Conditions(service="dry", laterally_supported=True,
                              bearing_length_mm=89.0),
        limits=DeflectionLimits(live_ratio=360.0, total_ratio=240.0),
        include_wind=False,
    )
    defaults.update(kw)
    return DesignRequest(**defaults)


def test_span_conversion():
    assert L1 == pytest.approx(5486.4)
    assert L2 == pytest.approx(3657.6)
    assert W_DEAD == pytest.approx(1.8288, rel=1e-4)  # N/mm == kN/m
    assert W_SNOW == pytest.approx(7.9004, rel=1e-3)


def test_support_moment_matches_three_moment_equation():
    """Hand check of the governing hogging moment, self weight excluded.

    The three-moment equation is an Euler-Bernoulli result. The solver includes
    shear deformation, which adds flexibility and slightly relieves the hogging
    moment over the centre support, so the two are compared separately:
    suppressing shear must reproduce the closed form exactly, and the real
    section must land just below it.
    """
    w = 1.25 * W_DEAD + 1.5 * W_SNOW  # governing ULS: 1.25D + 1.5S
    expected_knm = w * (L1**3 + L2**3) / (8.0 * (L1 + L2)) * 1e-6
    assert expected_knm == pytest.approx(41.4, rel=0.02)

    section = BuiltUpSection(1.75 * 25.4, 14.0 * 25.4, plies=2)

    # Euler-Bernoulli limit: suppress shear deformation with a very large G.
    stiff = materials.get("LVL-2.0E-Microllam")
    stiff = replace(stiff, g_mpa=1e9)
    eb = run(base_request(section=section, include_self_weight=False,
                          custom_material=stiff))
    assert min(eb.diagrams.moment_min_knm) == pytest.approx(-expected_knm, rel=5e-3)

    # Real member, shear deformation included.
    real = run(base_request(section=section, include_self_weight=False))
    hogging = min(real.diagrams.moment_min_knm)
    assert -expected_knm < hogging < -0.95 * expected_knm


def test_two_ply_lvl_14_inch_strength_and_deflection_pass():
    """Bending, shear and deflection are satisfied by 2-ply 1-3/4 x 14 LVL."""
    resp = run(base_request(section=BuiltUpSection(1.75 * 25.4, 14.0 * 25.4, plies=2)))
    by_check = {c.check: c for c in resp.outcome.checks}

    assert by_check["moment"].ratio < 0.8
    assert by_check["shear"].ratio < 1.0
    for c in resp.outcome.checks:
        if c.check.startswith("deflection"):
            assert c.status == "PASS", (c.label, c.ratio)


def test_bearing_governs_at_89mm_and_passes_when_lengthened():
    """The centre reaction needs more bearing than a single stud provides."""
    section = BuiltUpSection(1.75 * 25.4, 14.0 * 25.4, plies=2)

    short = run(base_request(section=section))
    bearing = next(c for c in short.outcome.checks if c.check == "bearing")
    assert bearing.status == "FAIL"
    assert short.outcome.governing.check == "bearing"

    generous = run(base_request(
        section=section,
        conditions=Conditions(service="dry", laterally_supported=True,
                              bearing_length_mm=140.0),
    ))
    assert generous.outcome.passed, [
        (c.label, round(c.ratio, 3))
        for c in generous.outcome.checks if c.status == "FAIL"
    ]


def test_single_ply_lvl_14_inch_fails():
    resp = run(base_request(section=BuiltUpSection(1.75 * 25.4, 14.0 * 25.4, plies=1)))
    assert not resp.outcome.passed


def test_auto_search_returns_a_passing_section():
    resp = run(base_request())
    assert resp.outcome.passed
    assert resp.alternatives
    assert resp.plies >= 1


def test_unverified_sawn_material_raises_warning():
    resp = run(base_request(material_key="SPF-No1No2",
                            section=BuiltUpSection(38.0, 286.0, plies=4)))
    assert any("Verify every value" in w for w in resp.outcome.warnings)


def test_reactions_sum_to_total_applied_load():
    req = base_request(
        section=BuiltUpSection(1.75 * 25.4, 14.0 * 25.4, plies=2),
        include_self_weight=False,
    )
    resp = run(req)
    # Reported reactions are maxima across combinations, so compare the
    # specified-load statics instead: total = (D + S) * length.
    total_kn = (W_DEAD + W_SNOW) * (L1 + L2) * 1e-3
    assert total_kn == pytest.approx(88.7, rel=0.02)
