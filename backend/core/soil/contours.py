"""Iso-line extraction for pressure-bulb drawings (marching squares).

Given vertical stress sampled on a regular grid through a section, this
produces the polyline segments of chosen pressure contours. Doing it here
rather than in the browser keeps the algorithm testable and the frontend a
straight renderer.
"""

from __future__ import annotations

import numpy as np

# Which cell edges a contour crosses, keyed by the four-corner inside/outside
# bit pattern: 1 = top-left, 2 = top-right, 4 = bottom-right, 8 = bottom-left.
# The two saddle cases (5 and 10) are resolved arbitrarily; at drawing
# resolution the choice is not visible.
_EDGE_PAIRS: dict[int, list[tuple[str, str]]] = {
    0: [], 1: [("L", "T")], 2: [("T", "R")], 3: [("L", "R")],
    4: [("R", "B")], 5: [("L", "T"), ("R", "B")], 6: [("T", "B")],
    7: [("L", "B")], 8: [("B", "L")], 9: [("T", "B")],
    10: [("T", "R"), ("B", "L")], 11: [("R", "B")], 12: [("L", "R")],
    13: [("T", "R")], 14: [("L", "T")], 15: [],
}


def _interpolate(v0: float, v1: float, p0: float, p1: float, level: float) -> float:
    """Position along an edge where the field crosses ``level``."""
    span = v1 - v0
    if abs(span) < 1e-12:
        return p0
    return p0 + (p1 - p0) * (level - v0) / span


def iso_segments(
    grid: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    level: float,
) -> list[list[list[float]]]:
    """Contour segments at ``level`` as [[x0, y0], [x1, y1]] pairs.

    ``grid`` is indexed [row, column] with rows following ``y_coords`` and
    columns following ``x_coords``.
    """
    segments: list[list[list[float]]] = []
    rows, cols = grid.shape

    for r in range(rows - 1):
        for c in range(cols - 1):
            tl, tr = grid[r, c], grid[r, c + 1]
            bl, br = grid[r + 1, c], grid[r + 1, c + 1]
            index = (
                (1 if tl > level else 0)
                | (2 if tr > level else 0)
                | (4 if br > level else 0)
                | (8 if bl > level else 0)
            )
            pairs = _EDGE_PAIRS[index]
            if not pairs:
                continue

            x0, x1 = float(x_coords[c]), float(x_coords[c + 1])
            y0, y1 = float(y_coords[r]), float(y_coords[r + 1])
            points = {
                "T": [_interpolate(tl, tr, x0, x1, level), y0],
                "B": [_interpolate(bl, br, x0, x1, level), y1],
                "L": [x0, _interpolate(tl, bl, y0, y1, level)],
                "R": [x1, _interpolate(tr, br, y0, y1, level)],
            }
            for a, b in pairs:
                segments.append([points[a], points[b]])

    return segments


def nice_levels(peak: float, count: int = 6) -> list[float]:
    """Round contour values spanning a sensible fraction of the peak stress."""
    if not np.isfinite(peak) or peak <= 0:
        return []
    steps = (1.0, 2.0, 2.5, 5.0, 10.0)
    target = peak / (count + 1)
    magnitude = 10.0 ** np.floor(np.log10(max(target, 1e-6)))
    step = next((s * magnitude for s in steps if s * magnitude >= target),
                10.0 * magnitude)
    levels = []
    value = step
    while value < peak and len(levels) < count:
        levels.append(round(float(value), 6))
        value += step
    return levels
