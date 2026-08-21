"""Westergaard stress, checked against closed forms and against Boussinesq."""

import numpy as np
import pytest

from core.soil import boussinesq, westergaard


def test_eta_squared_is_one_half_at_zero_poisson():
    assert westergaard.eta_squared(0.0) == pytest.approx(0.5)


def test_poisson_ratio_is_range_checked():
    with pytest.raises(ValueError):
        westergaard.eta_squared(0.5)
    with pytest.raises(ValueError):
        westergaard.eta_squared(-0.1)


def test_point_load_on_axis_matches_the_closed_form():
    """At r = 0 with nu = 0 the solution is exactly P/(pi z^2)."""
    p, z = 120.0, 2.5
    got = float(westergaard.point_stress_kpa(p, 0.0, z, 0.0))
    assert got == pytest.approx(p / (np.pi * z**2), rel=1e-12)
    assert got == pytest.approx(0.3183 * p / z**2, rel=1e-3)


def test_westergaard_is_two_thirds_of_boussinesq_on_the_axis():
    """The classic relationship for nu = 0."""
    p, z = 200.0, 1.8
    w = float(westergaard.point_stress_kpa(p, 0.0, z, 0.0))
    b = float(boussinesq.point_stress_kpa(p, 0.0, z))
    assert w / b == pytest.approx(2.0 / 3.0, rel=1e-9)


def test_westergaard_spreads_load_wider_than_boussinesq():
    """Lower under the load, higher out to the side, so the curves cross.

    The ratio is not monotonic: it dips to a minimum near r/z = 0.5 before
    climbing through unity at about r/z = 1.5.
    """
    p, z = 100.0, 2.0
    over_z = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0)
    ratios = [
        float(westergaard.point_stress_kpa(p, r * z, z, 0.0))
        / float(boussinesq.point_stress_kpa(p, r * z, z))
        for r in over_z
    ]
    assert ratios[0] == pytest.approx(2.0 / 3.0, rel=1e-9)
    assert min(ratios) == ratios[over_z.index(0.5)]   # the dip
    assert ratios[-1] > 1.0                            # crosses over further out
    # Monotonic increase once past the dip.
    tail = ratios[over_z.index(0.5):]
    assert all(a < b for a, b in zip(tail, tail[1:]))


def test_point_load_stress_integrates_to_the_applied_load():
    """Equilibrium check - the strongest test of the formula's constants."""
    p, z = 250.0, 3.0
    r = np.linspace(0.0, 3000.0, 600_000)
    sigma = westergaard.point_stress_kpa(p, r, z, 0.0)
    total = np.trapezoid(sigma * 2.0 * np.pi * r, r)
    assert total == pytest.approx(p, rel=2e-3)


def test_equilibrium_holds_for_a_non_zero_poisson_ratio():
    p, z, nu = 250.0, 3.0, 0.3
    r = np.linspace(0.0, 3000.0, 600_000)
    sigma = westergaard.point_stress_kpa(p, r, z, nu)
    total = np.trapezoid(sigma * 2.0 * np.pi * r, r)
    assert total == pytest.approx(p, rel=2e-3)


def test_rectangle_at_great_depth_approaches_a_point_load():
    q, b, l, z = 150.0, 0.9, 1.4, 50.0
    rect = float(westergaard.rectangle_stress_kpa(
        q, -b / 2, b / 2, -l / 2, l / 2, 0.0, 0.0, z, 0.0))
    point = float(westergaard.point_stress_kpa(q * b * l, 0.0, z, 0.0))
    assert rect == pytest.approx(point, rel=2e-3)


def test_rectangle_is_below_boussinesq_under_the_middle_of_the_load():
    q, b, l, z = 120.0, 3.2, 0.6, 1.0
    w = float(westergaard.rectangle_stress_kpa(
        q, -b / 2, b / 2, -l / 2, l / 2, 0.0, 0.0, z, 0.0))
    bo = float(boussinesq.rectangle_stress_kpa(
        q, -b / 2, b / 2, -l / 2, l / 2, 0.0, 0.0, z))
    assert 0.5 * bo < w < bo


def test_rectangle_subdivision_has_converged():
    """The default subdivision must already be at the answer."""
    args = (120.0, -1.6, 1.6, -0.3, 0.3, 0.0, 0.0, 0.8, 0.0)
    coarse = float(westergaard.rectangle_stress_kpa(*args, subdivisions=48))
    fine = float(westergaard.rectangle_stress_kpa(*args, subdivisions=140))
    assert coarse == pytest.approx(fine, rel=2e-3)


def test_rectangle_accepts_an_array_of_field_points():
    xs = np.linspace(-2.0, 2.0, 9)
    out = westergaard.rectangle_stress_kpa(
        100.0, -1.0, 1.0, -1.0, 1.0, xs, np.zeros_like(xs), 1.0, 0.0)
    assert out.shape == xs.shape
    # Symmetric about the centre, and peaking there.
    assert out[0] == pytest.approx(out[-1], rel=1e-9)
    assert out.argmax() == 4


def test_degenerate_rectangle_is_rejected():
    with pytest.raises(ValueError, match="positive width and length"):
        westergaard.rectangle_stress_kpa(100, 1.0, 1.0, 0.0, 1.0, 0, 0, 1.0)
