"""Regression test: SCL resistances must reproduce Weyerhaeuser's own tables.

Reference values are the published "Factored Resistances (Standard Term)" table
on page 4 of Trus Joist specifier's guide TJ-9500 (Eastern Canada, Feb 2026),
a copy of which is in Materials/TJ-9500.pdf. Published figures are rounded to
the nearest 5 ft-lb / 5 lb, so a 0.5% tolerance is used.

If a material constant or a resistance formula is ever changed incorrectly,
these numbers stop matching the manufacturer's document.
"""

import pytest

from core.units import MM_PER_INCH, NMM_PER_FTLB, N_PER_LBF
from core.wood import materials
from core.wood.checks import moment_check, shear_check
from core.wood.factors import Conditions
from core.wood.sections import BuiltUpSection

# Standard term, dry service, untreated, no system action, laterally supported
# per the guide's general assumptions (bracing at 24 in. o.c. maximum).
STANDARD = Conditions(
    load_duration="standard",
    service="dry",
    treatment="none",
    system="none",
    laterally_supported=True,
)

# product key -> width_in -> (depths_in, moment_ftlb, shear_lb)
PUBLISHED: dict[str, dict[float, tuple[tuple[float, ...], tuple[int, ...], tuple[int, ...]]]] = {
    "LVL-2.0E-Microllam": {
        1.75: (
            (9.25, 9.5, 11.25, 11.875, 14.0, 16.0, 18.0, 20.0),
            (9315, 9790, 13420, 14845, 20175, 25875, 32230, 39220),
            (5150, 5285, 6260, 6610, 7790, 8905, 10015, 11130),
        ),
    },
    "PSL-2.0E-Parallam": {
        3.5: (
            (9.5, 11.875, 14.0, 16.0, 18.0),
            (21720, 33105, 45180, 58145, 72635),
            (10775, 13465, 15875, 18145, 20410),
        ),
        5.25: (
            (9.5, 11.875, 14.0, 16.0, 18.0),
            (32580, 49660, 67775, 87220, 108950),
            (16160, 20200, 23815, 27215, 30620),
        ),
        7.0: (
            (9.5, 11.875, 14.0, 16.0, 18.0),
            (43440, 66215, 90365, 116290, 145270),
            (21545, 26935, 31750, 36290, 40825),
        ),
    },
    "LSL-1.55E-TimberStrand": {
        1.75: (
            (9.5, 11.875, 14.0, 16.0),
            (8665, 13260, 18155, 23425),
            (5735, 7170, 8455, 9660),
        ),
        3.5: (
            (9.5, 11.875, 14.0, 16.0),
            (17325, 26525, 36310, 46850),
            (11470, 14340, 16905, 19320),
        ),
    },
}


def _cases():
    for key, by_width in PUBLISHED.items():
        for width_in, (depths, moments, shears) in by_width.items():
            for d_in, m_ftlb, v_lb in zip(depths, moments, shears):
                yield key, width_in, d_in, m_ftlb, v_lb


ALL_CASES = list(_cases())
IDS = [f"{k.split('-')[0]}-{w}x{d}" for k, w, d, _, _ in ALL_CASES]


@pytest.mark.parametrize("key,width_in,depth_in,m_ftlb,v_lb", ALL_CASES, ids=IDS)
def test_published_factored_resistances(key, width_in, depth_in, m_ftlb, v_lb):
    mat = materials.get(key)
    section = BuiltUpSection(width_in * MM_PER_INCH, depth_in * MM_PER_INCH, plies=1)

    mr = moment_check(mat, section, STANDARD, "standard", 0.0, "-", 0.0)
    vr = shear_check(mat, section, STANDARD, "standard", 0.0, "-", 0.0)

    mr_ftlb = mr.resistance * 1e6 / NMM_PER_FTLB  # kN.m -> N.mm -> ft-lb
    vr_lb = vr.resistance * 1e3 / N_PER_LBF  # kN -> N -> lb

    assert mr_ftlb == pytest.approx(m_ftlb, rel=5e-3)
    assert vr_lb == pytest.approx(v_lb, rel=5e-3)


def test_published_moments_of_inertia():
    """Section geometry must match the guide's tabulated moment of inertia."""
    mat = materials.get("LVL-2.0E-Microllam")
    published_in4 = {9.25: 115, 9.5: 125, 11.25: 208, 11.875: 244,
                     14.0: 400, 16.0: 597, 18.0: 851, 20.0: 1167}
    for d_in, i_in4 in published_in4.items():
        s = BuiltUpSection(1.75 * MM_PER_INCH, d_in * MM_PER_INCH, plies=1)
        assert s.inertia_mm4 / MM_PER_INCH**4 == pytest.approx(i_in4, rel=5e-3)
    assert mat.verified


def test_multi_ply_scales_linearly():
    mat = materials.get("LVL-2.0E-Microllam")
    one = BuiltUpSection(1.75 * MM_PER_INCH, 14.0 * MM_PER_INCH, plies=1)
    three = BuiltUpSection(1.75 * MM_PER_INCH, 14.0 * MM_PER_INCH, plies=3)
    m1 = moment_check(mat, one, STANDARD, "standard", 0, "-", 0).resistance
    m3 = moment_check(mat, three, STANDARD, "standard", 0, "-", 0).resistance
    assert m3 == pytest.approx(3.0 * m1, rel=1e-9)


def test_snow_duration_raises_resistance_by_kd():
    mat = materials.get("LVL-2.0E-Microllam")
    s = BuiltUpSection(1.75 * MM_PER_INCH, 14.0 * MM_PER_INCH, plies=2)
    std = moment_check(mat, s, STANDARD, "standard", 0, "-", 0).resistance
    short = moment_check(mat, s, STANDARD, "short", 0, "-", 0).resistance
    assert short == pytest.approx(1.15 * std, rel=1e-9)


def test_sawn_lumber_values_are_flagged_unverified():
    """Transcribed O86 tables must not silently claim to be verified."""
    for key in ("SPF-No1No2", "SPF-SS", "DFirL-No1No2"):
        assert materials.get(key).verified is False
