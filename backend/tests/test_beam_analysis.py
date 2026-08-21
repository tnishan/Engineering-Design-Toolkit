"""Closed-form validation of the continuous beam solver."""

import numpy as np
import pytest

from core.analysis.beam import (
    BeamModelError,
    DistributedLoad,
    PointLoad,
    Section,
    build_geometry,
    solve_case,
)

# Sawn-lumber-ish elastic properties; G set high where Euler-Bernoulli
# closed-form results are the reference.
E = 9500.0  # MPa
STIFF_G = 1e9  # effectively suppresses shear deformation


def bernoulli_section(b: float, d: float) -> Section:
    I = b * d**3 / 12.0
    return Section(E_mpa=E, I_mm4=I, A_shear_mm2=b * d / 1.2, G_mpa=STIFF_G)


def rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b)


def test_simple_span_udl_moment_shear_deflection():
    L = 5000.0
    w = 10.0  # N/mm
    sec = bernoulli_section(89.0, 285.0)
    geom = build_geometry([L], ["pin", "roller"], sec)
    res = solve_case(geom, [DistributedLoad(w, 0.0, L)], [])

    assert rel(res.moment_nmm.max(), w * L**2 / 8.0) < 5e-3
    assert rel(res.shear_n.max(), w * L / 2.0) < 5e-3
    expected = 5.0 * w * L**4 / (384.0 * E * sec.I_mm4)
    assert rel(abs(res.deflection_mm.min()), expected) < 5e-3


def test_simple_span_midpoint_point_load():
    L = 4000.0
    P = 20000.0  # N
    sec = bernoulli_section(89.0, 235.0)
    geom = build_geometry([L], ["pin", "roller"], sec)
    res = solve_case(geom, [], [PointLoad(P, L / 2.0)])

    assert rel(res.moment_nmm.max(), P * L / 4.0) < 5e-3
    assert rel(res.shear_n.max(), P / 2.0) < 5e-3
    expected = P * L**3 / (48.0 * E * sec.I_mm4)
    assert rel(abs(res.deflection_mm.min()), expected) < 5e-3


def test_two_equal_span_continuous_udl():
    """Classic result: support moment = wL^2/8, end reactions = 3wL/8."""
    L = 4000.0
    w = 12.0
    sec = bernoulli_section(89.0, 285.0)
    geom = build_geometry([L, L], ["pin", "roller", "roller"], sec)
    res = solve_case(geom, [DistributedLoad(w, 0.0, 2 * L)], [])

    assert rel(abs(res.moment_nmm.min()), w * L**2 / 8.0) < 5e-3
    assert rel(res.moment_nmm.max(), 9.0 * w * L**2 / 128.0) < 1e-2

    reactions = res.reactions_n
    ends = [reactions[0.0], reactions[max(reactions)]]
    for r in ends:
        assert rel(r, 3.0 * w * L / 8.0) < 5e-3
    interior = reactions[L]
    assert rel(interior, 10.0 * w * L / 8.0) < 5e-3


def test_two_unequal_span_continuous_udl():
    """Three-moment equation: M_B = w (L1^3 + L2^3) / (8 (L1 + L2))."""
    L1, L2 = 5486.4, 3657.6  # 18 ft, 12 ft
    w = 14.0
    sec = bernoulli_section(89.0, 400.0)
    geom = build_geometry([L1, L2], ["pin", "roller", "roller"], sec)
    res = solve_case(geom, [DistributedLoad(w, 0.0, L1 + L2)], [])

    expected = w * (L1**3 + L2**3) / (8.0 * (L1 + L2))
    assert rel(abs(res.moment_nmm.min()), expected) < 5e-3


def test_cantilever_tip_point_load():
    L = 2000.0
    P = 5000.0
    sec = bernoulli_section(89.0, 235.0)
    # Fixed at the left, free tip modelled as a right overhang.
    geom = build_geometry([L], ["fixed", "free"], sec)
    res = solve_case(geom, [], [PointLoad(P, L)])

    assert rel(abs(res.moment_nmm.min()), P * L) < 5e-3
    expected = P * L**3 / (3.0 * E * sec.I_mm4)
    assert rel(abs(res.deflection_mm.min()), expected) < 5e-3


def test_partial_udl_resultant_statics():
    """A UDL over the right half only: reactions must satisfy statics."""
    L = 6000.0
    w = 8.0
    sec = bernoulli_section(89.0, 285.0)
    geom = build_geometry([L], ["pin", "roller"], sec)
    res = solve_case(geom, [DistributedLoad(w, L / 2.0, L)], [])

    total = w * L / 2.0
    assert rel(sum(res.reactions_n.values()), total) < 1e-3
    # Resultant acts at 3L/4, so R_left = total/4, R_right = 3*total/4.
    assert rel(res.reactions_n[0.0], total / 4.0) < 5e-3


def test_shear_deformation_increases_deflection():
    """Timoshenko deflection must exceed Euler-Bernoulli for a real G."""
    L = 3000.0
    w = 15.0
    b, d = 89.0, 400.0
    I = b * d**3 / 12.0
    A_s = b * d / 1.2

    thin = Section(E, I, A_s, STIFF_G)
    real = Section(E, I, A_s, 600.0)

    geom_thin = build_geometry([L], ["pin", "roller"], thin)
    geom_real = build_geometry([L], ["pin", "roller"], real)
    d_thin = abs(solve_case(geom_thin, [DistributedLoad(w, 0, L)], []).deflection_mm.min())
    d_real = abs(solve_case(geom_real, [DistributedLoad(w, 0, L)], []).deflection_mm.min())

    assert d_real > d_thin
    # Closed form: delta = 5wL^4/(384EI) + wL^2/(8 G A_s)
    expected = 5 * w * L**4 / (384 * E * I) + w * L**2 / (8 * 600.0 * A_s)
    assert rel(d_real, expected) < 1e-2


def test_moment_diagram_is_zero_at_simple_ends():
    L = 4000.0
    sec = bernoulli_section(89.0, 235.0)
    geom = build_geometry([L], ["pin", "roller"], sec)
    res = solve_case(geom, [DistributedLoad(10.0, 0, L)], [])
    assert abs(res.moment_nmm[0]) < 1e-6 * abs(res.moment_nmm).max()
    assert abs(res.moment_nmm[-1]) < 1e-3 * abs(res.moment_nmm).max()


def test_rejects_unstable_and_malformed_models():
    sec = bernoulli_section(89.0, 235.0)
    with pytest.raises(BeamModelError):
        build_geometry([4000.0], ["pin"], sec)  # wrong support count
    with pytest.raises(BeamModelError):
        build_geometry([], ["pin", "roller"], sec)  # no spans
    with pytest.raises(BeamModelError):
        build_geometry([-100.0], ["pin", "roller"], sec)  # negative span
    with pytest.raises(BeamModelError):
        build_geometry([4000.0], ["free", "free"], sec)  # unstable
