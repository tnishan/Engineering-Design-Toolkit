"""Vertical stress in soil under surface loads (elastic half-space).

Unlike the rest of ``core`` (which works in mm and N), this package works in
**metres, kN and kPa**. Depths, machine dimensions and bearing pressures are
universally quoted that way in geotechnical practice, and converting them to
millimetres would make every formula unrecognisable against a textbook. The
API layer converts at the boundary.

Boussinesq (1885) solves a point load on a homogeneous, isotropic, linearly
elastic half-space. For *vertical* stress the solution is independent of E and
Poisson's ratio, which is why no soil stiffness appears anywhere below::

    Point load P at the surface, stress at radius r, depth z:

        sigma_z = 3 P z^3 / (2 pi (r^2 + z^2)^(5/2))

    Uniform pressure q on a rectangle, stress under one CORNER at depth z,
    with m = B/z and n = L/z (Newmark 1935):

        I = 1/(4 pi) [ 2 m n sqrt(S) / (S + m^2 n^2) * (S + 1) / S
                     + arctan( 2 m n sqrt(S) / (S - m^2 n^2) ) ]
        where S = m^2 + n^2 + 1,  and  sigma_z = q I

    The arctangent must be taken on (0, pi): when m^2 n^2 > S the denominator
    turns negative and pi has to be added. ``arctan2`` does exactly that.

Stress under an arbitrary point is assembled from four signed corner terms,
which works whether the point lies inside or outside the loaded rectangle.

IMPORTANT: this is the *free-field* stress, computed with no structure
present. It is not the pressure a buried pipe actually feels - a rigid pipe
attracts load above free field, a flexible one sheds it into the sidefill.
See ``buried_pipe`` for how that limitation is reported.
"""

from __future__ import annotations

import numpy as np

# Below this depth the closed forms are singular; the surface value is used.
_MIN_Z_M = 1e-9


def point_stress_kpa(
    load_kn: float,
    radius_m: float | np.ndarray,
    depth_m: float | np.ndarray,
) -> float | np.ndarray:
    """Vertical stress under a surface point load."""
    r = np.asarray(radius_m, dtype=float)
    z = np.asarray(depth_m, dtype=float)
    z = np.maximum(z, _MIN_Z_M)
    return 3.0 * load_kn * z**3 / (2.0 * np.pi * (r * r + z * z) ** 2.5)


def corner_influence(m: float | np.ndarray, n: float | np.ndarray) -> np.ndarray:
    """Newmark influence factor for the corner of a uniformly loaded rectangle.

    ``m`` and ``n`` are the rectangle's two side lengths divided by the depth,
    and must be non-negative. Symmetric in m and n; tends to 1/4 as both grow,
    so a point under the middle of a very wide loaded area sees the full
    surface pressure (four corners x 1/4).
    """
    m = np.abs(np.asarray(m, dtype=float))
    n = np.abs(np.asarray(n, dtype=float))
    s = m * m + n * n + 1.0
    root = np.sqrt(s)
    mn = m * n

    algebraic = (2.0 * mn * root) / (s + mn * mn) * (s + 1.0) / s
    angular = np.arctan2(2.0 * mn * root, s - mn * mn)
    return (algebraic + angular) / (4.0 * np.pi)


def _signed_corner(
    x_m: float | np.ndarray, y_m: float | np.ndarray, depth_m: float
) -> np.ndarray:
    """Corner influence carrying the sign of its two side lengths.

    Making the corner term odd in each argument is what lets four of them be
    superposed for a point anywhere in the plane, inside the rectangle or out.
    """
    z = max(depth_m, _MIN_Z_M)
    x = np.asarray(x_m, dtype=float)
    y = np.asarray(y_m, dtype=float)
    return np.sign(x) * np.sign(y) * corner_influence(x / z, y / z)


def rectangle_stress_kpa(
    pressure_kpa: float,
    x_min_m: float,
    x_max_m: float,
    y_min_m: float,
    y_max_m: float,
    at_x_m: float | np.ndarray,
    at_y_m: float | np.ndarray,
    depth_m: float,
) -> np.ndarray:
    """Vertical stress under a uniformly loaded rectangle at any plan position."""
    if x_max_m <= x_min_m or y_max_m <= y_min_m:
        raise ValueError("Loaded rectangle must have positive width and length.")

    px = np.asarray(at_x_m, dtype=float)
    py = np.asarray(at_y_m, dtype=float)

    # Distances from the point of interest to each edge, signed.
    x1, x2 = x_min_m - px, x_max_m - px
    y1, y2 = y_min_m - py, y_max_m - py

    influence = (
        _signed_corner(x2, y2, depth_m)
        - _signed_corner(x1, y2, depth_m)
        - _signed_corner(x2, y1, depth_m)
        + _signed_corner(x1, y1, depth_m)
    )
    return pressure_kpa * influence


def spread_stress_kpa(
    total_load_kn: float,
    width_m: float,
    length_m: float,
    depth_m: float,
    spread_factor: float = 1.0,
) -> float:
    """Stress from the load-spread approximation used by the culvert codes.

    The contact area is assumed to grow by ``spread_factor * depth`` in each
    plan dimension, with the load spread uniformly over it. A factor of 1.0 is
    the classical 2:1 method (the area gains z/2 on every side). AASHTO-style
    live-load distribution factors are of the same form with a different
    number.

    This is a bookkeeping rule, not a solution of elasticity: it conserves
    total load but says nothing about how stress is really distributed, and it
    has no notion of a point being off to one side of the load.
    """
    if width_m <= 0 or length_m <= 0:
        raise ValueError("Contact area must have positive dimensions.")
    if spread_factor < 0:
        raise ValueError("Spread factor cannot be negative.")
    z = max(depth_m, 0.0)
    return total_load_kn / ((width_m + spread_factor * z) * (length_m + spread_factor * z))
