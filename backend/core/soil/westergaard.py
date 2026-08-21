"""Westergaard (1938) vertical stress - the stiff-layered counterpart to Boussinesq.

Westergaard models a half-space reinforced by closely spaced, infinitely rigid
horizontal sheets that prevent lateral strain. That is a better idealisation of
a varved or layered deposit, or of well-compacted granular backfill in thin
lifts, than Boussinesq's isotropic continuum. It concentrates stress less
directly beneath the load and spreads it wider, so it is the lower bound of the
pair on the load axis::

    sigma_z = P eta / (2 pi z^2) * 1 / [eta^2 + (r/z)^2]^(3/2)

    with   eta^2 = (1 - 2 nu) / (2 - 2 nu)

At nu = 0 (the classical case, and the one most often tabulated) eta^2 = 1/2
and the stress directly under the load is P/(pi z^2) = 0.3183 P/z^2, exactly
two thirds of the Boussinesq value of 0.4775 P/z^2.

There is no equally standard closed form for a rectangle, so loaded areas are
integrated numerically by subdivision. That is slower than the Newmark factor
used for Boussinesq, which is why the profile sweeps stay on Boussinesq and
Westergaard is evaluated only where it is reported.
"""

from __future__ import annotations

import numpy as np

_MIN_Z_M = 1e-9
# Sub-loads per side when integrating a rectangle. 48 x 48 keeps the error
# under about 0.1% against the point-load limit even at shallow depth.
_SUBDIVISIONS = 48


def eta_squared(poisson_ratio: float) -> float:
    """The Westergaard parameter, guarded away from the nu = 0.5 singularity."""
    if not 0.0 <= poisson_ratio < 0.5:
        raise ValueError(
            f"Poisson's ratio must be at least 0 and below 0.5, got {poisson_ratio}."
        )
    return (1.0 - 2.0 * poisson_ratio) / (2.0 - 2.0 * poisson_ratio)


def point_stress_kpa(
    load_kn: float,
    radius_m: float | np.ndarray,
    depth_m: float | np.ndarray,
    poisson_ratio: float = 0.0,
) -> np.ndarray:
    """Vertical stress under a surface point load, Westergaard."""
    e2 = eta_squared(poisson_ratio)
    eta = np.sqrt(e2)
    r = np.asarray(radius_m, dtype=float)
    z = np.maximum(np.asarray(depth_m, dtype=float), _MIN_Z_M)
    return load_kn * eta / (2.0 * np.pi * z**2) / (e2 + (r / z) ** 2) ** 1.5


def rectangle_stress_kpa(
    pressure_kpa: float,
    x_min_m: float,
    x_max_m: float,
    y_min_m: float,
    y_max_m: float,
    at_x_m: float | np.ndarray,
    at_y_m: float | np.ndarray,
    depth_m: float,
    poisson_ratio: float = 0.0,
    subdivisions: int = _SUBDIVISIONS,
) -> np.ndarray:
    """Vertical stress under a uniformly loaded rectangle, by subdivision."""
    if x_max_m <= x_min_m or y_max_m <= y_min_m:
        raise ValueError("Loaded rectangle must have positive width and length.")

    n = max(int(subdivisions), 2)
    # Midpoint rule: one point load at the centre of each sub-rectangle.
    dx = (x_max_m - x_min_m) / n
    dy = (y_max_m - y_min_m) / n
    sub_x = x_min_m + dx * (np.arange(n) + 0.5)
    sub_y = y_min_m + dy * (np.arange(n) + 0.5)
    sub_load = pressure_kpa * dx * dy

    raw_x = np.asarray(at_x_m, dtype=float)
    raw_y = np.asarray(at_y_m, dtype=float)
    scalar_input = raw_x.ndim == 0 and raw_y.ndim == 0
    px = np.atleast_1d(raw_x)
    py = np.atleast_1d(raw_y)
    shape = np.broadcast(px, py).shape

    total = np.zeros(shape, dtype=float)
    gx, gy = np.meshgrid(sub_x, sub_y, indexing="ij")
    flat_x, flat_y = gx.ravel(), gy.ravel()

    # Chunk the sub-loads so a large field of interest cannot blow up memory.
    chunk = max(1, 200_000 // max(int(np.prod(shape)), 1))
    for start in range(0, flat_x.size, chunk):
        cx = flat_x[start:start + chunk]
        cy = flat_y[start:start + chunk]
        r = np.hypot(
            px[..., None] - cx,
            py[..., None] - cy,
        )
        total += point_stress_kpa(sub_load, r, depth_m, poisson_ratio).sum(axis=-1)

    # Give a scalar back for scalar input, matching the Boussinesq helpers.
    return total.reshape(()) if scalar_input else total
