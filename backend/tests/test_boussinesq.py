"""Elastic stress distribution, checked against closed forms and by integration."""

import numpy as np
import pytest

from core.soil.boussinesq import (
    corner_influence,
    point_stress_kpa,
    rectangle_stress_kpa,
    spread_stress_kpa,
)


# --------------------------------------------------------------------------
# Point load
# --------------------------------------------------------------------------

def test_point_load_directly_beneath_matches_closed_form():
    """At r = 0 the solution collapses to 3P/(2 pi z^2) = 0.4775 P/z^2."""
    p, z = 100.0, 2.0
    expected = 3.0 * p / (2.0 * np.pi * z**2)
    assert point_stress_kpa(p, 0.0, z) == pytest.approx(expected, rel=1e-12)
    assert point_stress_kpa(p, 0.0, z) == pytest.approx(0.4775 * p / z**2, rel=1e-3)


def test_point_load_decays_with_depth_and_offset():
    assert point_stress_kpa(100, 0, 4) < point_stress_kpa(100, 0, 2)
    assert point_stress_kpa(100, 3, 2) < point_stress_kpa(100, 0, 2)


def test_point_load_stress_integrates_to_the_applied_load():
    """Equilibrium: the stress on any horizontal plane must carry all of P."""
    p, z = 250.0, 3.0
    r = np.linspace(0.0, 400.0, 400_000)
    sigma = point_stress_kpa(p, r, z)
    # Axisymmetric, so integrate sigma * 2 pi r dr.
    total = np.trapezoid(sigma * 2.0 * np.pi * r, r)
    assert total == pytest.approx(p, rel=1e-4)


# --------------------------------------------------------------------------
# Newmark corner influence factor
# --------------------------------------------------------------------------

def test_corner_influence_matches_published_table_value():
    """m = n = 1 is the value most often tabulated: I = 0.1752."""
    assert float(corner_influence(1.0, 1.0)) == pytest.approx(0.1752, abs=5e-5)


def test_corner_influence_is_symmetric():
    for m, n in ((0.5, 2.0), (1.3, 0.2), (4.0, 7.0)):
        assert float(corner_influence(m, n)) == pytest.approx(float(corner_influence(n, m)))


def test_corner_influence_tends_to_one_quarter_for_a_huge_area():
    """Four corners of an effectively infinite loaded area must give sigma = q."""
    assert float(corner_influence(1e4, 1e4)) == pytest.approx(0.25, abs=1e-4)


def test_corner_influence_vanishes_for_zero_sized_rectangle():
    assert float(corner_influence(0.0, 5.0)) == pytest.approx(0.0, abs=1e-12)


def test_corner_influence_stays_on_the_correct_arctan_branch():
    """When m^2 n^2 > m^2+n^2+1 the arctan denominator goes negative; if the
    branch were wrong the factor would fall back down instead of increasing."""
    values = [float(corner_influence(v, v)) for v in (0.5, 1.0, 2.0, 5.0, 20.0, 200.0)]
    assert all(a < b for a, b in zip(values, values[1:])), values
    assert values[-1] == pytest.approx(0.25, abs=1e-3)


# --------------------------------------------------------------------------
# Rectangular loaded area
# --------------------------------------------------------------------------

def _integrate_point_loads_over_rectangle(
    q, x_min, x_max, y_min, y_max, px, py, z, n=600
):
    """Reference solution: chop the rectangle up and superpose point loads."""
    xs = np.linspace(x_min, x_max, n)
    ys = np.linspace(y_min, y_max, n)
    dx = (x_max - x_min) / (n - 1)
    dy = (y_max - y_min) / (n - 1)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    r = np.hypot(gx - px, gy - py)
    contribution = point_stress_kpa(q * dx * dy, r, z)
    return float(np.trapezoid(np.trapezoid(contribution, ys, axis=1), xs) / (dx * dy))


@pytest.mark.parametrize(
    "px, py, z",
    [
        (0.0, 0.0, 1.0),    # under the centre
        (0.0, 0.0, 3.0),    # deeper
        (1.5, 0.0, 1.0),    # under an edge
        (3.0, 2.0, 1.5),    # well outside the loaded area
        (0.8, -0.4, 0.6),   # shallow, off-centre
    ],
)
def test_rectangle_closed_form_matches_numerical_integration(px, py, z):
    """The strongest check available: the Newmark closed form must reproduce a
    brute-force superposition of Boussinesq point loads over the same area."""
    q = 150.0
    x_min, x_max, y_min, y_max = -1.5, 1.5, -1.0, 1.0
    closed = float(
        rectangle_stress_kpa(q, x_min, x_max, y_min, y_max, px, py, z)
    )
    numeric = _integrate_point_loads_over_rectangle(
        q, x_min, x_max, y_min, y_max, px, py, z
    )
    assert closed == pytest.approx(numeric, rel=2e-3), (closed, numeric)


def test_rectangle_at_great_depth_approaches_a_point_load():
    q, b, l = 200.0, 0.8, 1.2
    z = 60.0  # many times the plan size
    rect = float(rectangle_stress_kpa(q, -b / 2, b / 2, -l / 2, l / 2, 0, 0, z))
    equivalent_point = point_stress_kpa(q * b * l, 0.0, z)
    assert rect == pytest.approx(equivalent_point, rel=1e-3)


def test_rectangle_just_below_surface_returns_the_contact_pressure():
    q = 90.0
    inside = float(rectangle_stress_kpa(q, -2, 2, -2, 2, 0.0, 0.0, 1e-4))
    assert inside == pytest.approx(q, rel=1e-3)


def test_rectangle_stress_outside_the_loaded_area_is_small_but_positive():
    q = 100.0
    outside = float(rectangle_stress_kpa(q, -1, 1, -1, 1, 8.0, 0.0, 1.0))
    assert 0.0 < outside < 0.02 * q


def test_rectangle_superposition_is_consistent_when_split_in_two():
    """One rectangle must equal the sum of the two halves it is cut into."""
    q, z = 120.0, 1.7
    whole = float(rectangle_stress_kpa(q, -2, 2, -1, 1, 0.3, 0.2, z))
    left = float(rectangle_stress_kpa(q, -2, 0, -1, 1, 0.3, 0.2, z))
    right = float(rectangle_stress_kpa(q, 0, 2, -1, 1, 0.3, 0.2, z))
    assert whole == pytest.approx(left + right, rel=1e-10)


def test_rectangle_stress_integrates_to_the_applied_load():
    q, b, l, z = 100.0, 1.0, 2.0, 1.5
    total_applied = q * b * l
    span = np.linspace(-60.0, 60.0, 1500)
    gx, gy = np.meshgrid(span, span, indexing="ij")
    sigma = rectangle_stress_kpa(q, -b / 2, b / 2, -l / 2, l / 2, gx, gy, z)
    total = np.trapezoid(np.trapezoid(sigma, span, axis=1), span)
    assert total == pytest.approx(total_applied, rel=5e-3)


def test_zero_sized_rectangle_is_rejected():
    with pytest.raises(ValueError, match="positive width and length"):
        rectangle_stress_kpa(100, 1.0, 1.0, 0.0, 2.0, 0, 0, 1.0)


# --------------------------------------------------------------------------
# Spread approximation
# --------------------------------------------------------------------------

def test_spread_method_conserves_total_load():
    q_total, b, l, z, f = 300.0, 1.0, 2.0, 2.5, 1.0
    sigma = spread_stress_kpa(q_total, b, l, z, f)
    area = (b + f * z) * (l + f * z)
    assert sigma * area == pytest.approx(q_total)


def test_spread_at_the_surface_is_just_the_contact_pressure():
    assert spread_stress_kpa(200.0, 1.0, 2.0, 0.0) == pytest.approx(100.0)


def test_larger_spread_factor_gives_lower_stress():
    assert spread_stress_kpa(300, 1, 2, 3, 1.15) < spread_stress_kpa(300, 1, 2, 3, 1.0)


def test_spread_and_boussinesq_are_the_same_order_of_magnitude():
    """Not equal - different idealisations - but a large gap would signal a
    unit error in one of them."""
    q, b, l, z = 150.0, 1.0, 3.0, 1.5
    boussinesq = float(rectangle_stress_kpa(q, -b / 2, b / 2, -l / 2, l / 2, 0, 0, z))
    spread = spread_stress_kpa(q * b * l, b, l, z, 1.0)
    assert 0.5 < boussinesq / spread < 2.0, (boussinesq, spread)


def test_spread_rejects_nonsense_input():
    with pytest.raises(ValueError):
        spread_stress_kpa(100, 0.0, 1.0, 1.0)
    with pytest.raises(ValueError):
        spread_stress_kpa(100, 1.0, 1.0, 1.0, spread_factor=-0.5)
