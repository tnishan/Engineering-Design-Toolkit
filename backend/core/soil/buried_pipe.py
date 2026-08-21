"""Surcharge pressure at the crown of a buried pipe from surface plant.

Everything here is metres, kN and kPa (see ``boussinesq`` for why).

The headline number is the Boussinesq free-field vertical stress at crown
level. Two spread approximations are reported beside it for comparison: the
classical 2:1 rule, and the code-style live-load distribution in which the
contact area grows by a prescribed factor times the depth.

What this does NOT do, and what the warnings say plainly: it does not model
the pipe. Free-field stress is the stress in undisturbed ground at the depth
the crown happens to occupy. A rigid pipe stiffer than its surround attracts
more than that; a flexible pipe sheds load into the sidefill and feels less.
Converting free-field stress into a design pressure needs a bedding factor and
a pipe-stiffness assessment, which is a separate exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.soil import contours, westergaard
from core.soil.boussinesq import point_stress_kpa, rectangle_stress_kpa, spread_stress_kpa
from core.soil.loads import LoadModel

# Sampling for the profile sweeps. Fine enough that the reported peak is not
# noticeably clipped, coarse enough to stay instant.
_OFFSET_SAMPLES = 241
_ALONG_SAMPLES = 61
_DEPTH_SAMPLES = 60
_ACROSS_PIPE_SAMPLES = 41
# Section grid for the pressure-bulb drawing.
_BULB_X_SAMPLES = 97
_BULB_Z_SAMPLES = 73
_PLAN_X_SAMPLES = 81
_PLAN_Y_SAMPLES = 61
# Westergaard is integrated numerically, so profile work uses a coarser
# subdivision than the headline figure.
_WESTERGAARD_PROFILE_SUBDIVISIONS = 24


@dataclass
class TermTrace:
    """One line of the working behind a method's answer."""

    label: str
    detail: str
    value_kpa: float


@dataclass
class MethodResult:
    key: str
    name: str
    pressure_kpa: float
    basis: str
    verified: bool = True
    note: str = ""
    formula: str = ""
    substitution: str = ""
    terms: list["TermTrace"] = field(default_factory=list)
    # True when the terms are contributions that add up to the answer, false
    # when they are candidate areas and the largest one is taken.
    terms_sum_to_total: bool = True


BOUSSINESQ_FORMULA = (
    "sigma_z = q x I           (Newmark corner factor, four corners superposed)\n"
    "I = 1/(4 pi) [ 2mn sqrt(S) / (S + m^2 n^2) x (S + 1)/S\n"
    "               + arctan2( 2mn sqrt(S), S - m^2 n^2 ) ]\n"
    "S = m^2 + n^2 + 1,   m = B/z,   n = L/z"
)
POINT_FORMULA = "sigma_z = 3 P z^3 / (2 pi (r^2 + z^2)^(5/2))"
WESTERGAARD_FORMULA = (
    "sigma_z = P eta / (2 pi z^2) x 1 / [ eta^2 + (r/z)^2 ]^(3/2)\n"
    "eta^2 = (1 - 2 nu) / (2 - 2 nu)        loaded areas integrated numerically"
)
SPREAD_FORMULA = (
    "sigma_z = Q / [ (B + f z)(L + f z) ]\n"
    "areas whose spreads overlap are merged and their loads combined"
)
SPREAD_SUPERPOSED_FORMULA = (
    "sigma_z = sum over i of  Q_i / [ (B_i + f z)(L_i + f z) ]   where the point\n"
    "lies inside contact area i's own grown footprint (0 otherwise); each\n"
    "footprint kept separate rather than merged"
)


@dataclass
class PipeSurchargeRequest:
    load: LoadModel
    cover_m: float
    pipe_od_m: float
    machine_offset_m: float = 0.0
    pipe_x_m: float = 0.0
    dla: float = 1.0
    spread_factor: float = 1.15
    spread_factor_source: str = ""
    spread_factor_verified: bool = False
    soil_unit_weight_kn_m3: float = 20.0
    poisson_ratio: float = 0.0
    # Skip the sweeps and section grid when only headline numbers are wanted
    # (the alternate-orientation comparison, for instance).
    with_profiles: bool = True


@dataclass
class PipeSurchargeResult:
    cover_m: float
    pipe_od_m: float
    crown_depth_m: float
    machine_offset_m: float
    load_description: str
    total_load_kn: float
    dla: float

    methods: list[MethodResult] = field(default_factory=list)
    live_pressure_kpa: float = 0.0
    average_over_pipe_kpa: float = 0.0
    load_per_m_kn_m: float = 0.0

    worst_offset_m: float = 0.0
    worst_offset_pressure_kpa: float = 0.0
    offset_is_worst: bool = False

    soil_pressure_kpa: float = 0.0
    live_to_dead_ratio: float = 0.0

    depth_profile: list[dict] = field(default_factory=list)
    offset_profile: list[dict] = field(default_factory=list)
    bulb: dict = field(default_factory=dict)
    crown_plan: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def stress_field_kpa(
    load: LoadModel,
    at_x_m: np.ndarray,
    at_y_m: np.ndarray,
    depth_m: float,
) -> np.ndarray:
    """Vertical stress on a grid of plan positions at one depth."""
    gx, gy = np.meshgrid(
        np.atleast_1d(np.asarray(at_x_m, dtype=float)),
        np.atleast_1d(np.asarray(at_y_m, dtype=float)),
        indexing="ij",
    )
    total = np.zeros_like(gx, dtype=float)
    for patch in load.patches:
        x0, x1, y0, y1 = patch.bounds
        total += rectangle_stress_kpa(
            patch.pressure_kpa, x0, x1, y0, y1, gx, gy, depth_m
        )
    for pt in load.points:
        r = np.hypot(gx - pt.x_m, gy - pt.y_m)
        total += point_stress_kpa(pt.load_kn, r, depth_m)
    return total


def westergaard_field_kpa(
    load: LoadModel,
    at_x_m: np.ndarray,
    at_y_m: np.ndarray,
    depth_m: float,
    poisson_ratio: float,
    subdivisions: int = westergaard._SUBDIVISIONS,
) -> np.ndarray:
    """Westergaard counterpart of ``stress_field_kpa``."""
    gx, gy = np.meshgrid(
        np.atleast_1d(np.asarray(at_x_m, dtype=float)),
        np.atleast_1d(np.asarray(at_y_m, dtype=float)),
        indexing="ij",
    )
    total = np.zeros_like(gx, dtype=float)
    for patch in load.patches:
        x0, x1, y0, y1 = patch.bounds
        total += westergaard.rectangle_stress_kpa(
            patch.pressure_kpa, x0, x1, y0, y1, gx, gy, depth_m,
            poisson_ratio, subdivisions,
        )
    for pt in load.points:
        r = np.hypot(gx - pt.x_m, gy - pt.y_m)
        total += westergaard.point_stress_kpa(pt.load_kn, r, depth_m, poisson_ratio)
    return total


def point_idealised_field_kpa(
    load: LoadModel,
    at_x_m: np.ndarray,
    at_y_m: np.ndarray,
    depth_m: float,
) -> np.ndarray:
    """Boussinesq with every contact area collapsed to a point at its centroid.

    Reported to show how much the point idealisation overstates stress at
    shallow cover, where it is singular and the contact area is anything but
    negligible against the depth.
    """
    gx, gy = np.meshgrid(
        np.atleast_1d(np.asarray(at_x_m, dtype=float)),
        np.atleast_1d(np.asarray(at_y_m, dtype=float)),
        indexing="ij",
    )
    total = np.zeros_like(gx, dtype=float)
    for patch in load.patches:
        r = np.hypot(gx - patch.x_m, gy - patch.y_m)
        total += point_stress_kpa(patch.total_kn, r, depth_m)
    for pt in load.points:
        r = np.hypot(gx - pt.x_m, gy - pt.y_m)
        total += point_stress_kpa(pt.load_kn, r, depth_m)
    return total


def _superposition_terms(
    load: LoadModel,
    at_x_m: float,
    at_y_m: float,
    depth_m: float,
    dla: float,
    kind: str,
    poisson_ratio: float = 0.0,
) -> list[TermTrace]:
    """Per-contact-area contributions at the point of interest.

    Each row carries enough to be checked by hand: the contact pressure, the
    patch edges measured from the point, and the influence factor that came
    out of them.
    """
    terms: list[TermTrace] = []
    for patch in load.patches:
        x0, x1, y0, y1 = patch.bounds
        q = patch.pressure_kpa
        if kind == "boussinesq":
            value = float(rectangle_stress_kpa(q, x0, x1, y0, y1, at_x_m, at_y_m, depth_m))
            extra = f"sum of 4 corner factors I = {value / q:.5f}"
        elif kind == "westergaard":
            value = float(westergaard.rectangle_stress_kpa(
                q, x0, x1, y0, y1, at_x_m, at_y_m, depth_m, poisson_ratio))
            eta2 = westergaard.eta_squared(poisson_ratio)
            extra = f"eta^2 = {eta2:.4f}, integrated numerically"
        else:  # point idealisation
            r = float(np.hypot(at_x_m - patch.x_m, at_y_m - patch.y_m))
            value = float(point_stress_kpa(patch.total_kn, r, depth_m))
            terms.append(TermTrace(
                label=patch.label,
                detail=(f"P = {patch.total_kn:.2f} kN at r = {r:.3f} m, "
                        f"z = {depth_m:.3f} m"),
                value_kpa=round(value * dla, 4),
            ))
            continue

        terms.append(TermTrace(
            label=patch.label,
            detail=(
                f"q = {q:.2f} kPa on {patch.width_x_m:.3f} x {patch.length_y_m:.3f} m; "
                f"edges at x {x0 - at_x_m:+.3f} to {x1 - at_x_m:+.3f} m, "
                f"y {y0 - at_y_m:+.3f} to {y1 - at_y_m:+.3f} m; {extra}"
            ),
            value_kpa=round(value * dla, 4),
        ))

    for pt in load.points:
        r = float(np.hypot(at_x_m - pt.x_m, at_y_m - pt.y_m))
        if kind == "westergaard":
            value = float(westergaard.point_stress_kpa(pt.load_kn, r, depth_m, poisson_ratio))
        else:
            value = float(point_stress_kpa(pt.load_kn, r, depth_m))
        terms.append(TermTrace(
            label=pt.label,
            detail=f"P = {pt.load_kn:.2f} kN at r = {r:.3f} m, z = {depth_m:.3f} m",
            value_kpa=round(value * dla, 4),
        ))

    return terms


def _spread_terms(
    load: LoadModel, depth_m: float, spread_factor: float, dla: float
) -> list[TermTrace]:
    """The merged spread areas a load-spread method ends up with."""
    boxes = _spread_boxes(load, depth_m, spread_factor)
    terms = []
    for i, box in enumerate(boxes, start=1):
        width = box["x1"] - box["x0"]
        length = box["y1"] - box["y0"]
        area = width * length
        terms.append(TermTrace(
            label=f"spread area {i}" if len(boxes) > 1 else "spread area",
            detail=(
                f"{box['load']:.2f} kN over {width:.3f} x {length:.3f} m "
                f"= {area:.3f} m^2 (grown by {spread_factor:g} x {depth_m:.3f} m)"
            ),
            value_kpa=round(box["load"] / area * dla, 4),
        ))
    return terms


def _spread_superposed_kpa(
    load: LoadModel,
    at_x_m: float,
    at_y_m: float,
    depth_m: float,
    spread_factor: float,
) -> float:
    """Load spread with each contact area kept separate and summed.

    ``_spread_pressure_kpa`` merges overlapping spread footprints into one
    bounding box and takes the load over that single combined area - the
    standard, conservative reading of the 2:1 and AASHTO rules. This is the
    alternative some offices use instead: grow each tyre or track footprint on
    its own, and at the point of interest add up whichever footprints reach
    it. Two wheels whose footprints overlap the point each contribute their
    own pressure rather than being folded into one wider, lower one - usually
    a smaller number than the merged-box method, since spreading a load over
    two smaller areas independently does not double the total the way merging
    can appear to.
    """
    half = max(spread_factor, 0.0) * max(depth_m, 0.0) / 2.0
    total = 0.0
    for p in load.patches:
        x0, x1, y0, y1 = p.bounds
        gx0, gx1, gy0, gy1 = x0 - half, x1 + half, y0 - half, y1 + half
        if gx0 <= at_x_m <= gx1 and gy0 <= at_y_m <= gy1:
            area = (gx1 - gx0) * (gy1 - gy0)
            total += p.total_kn / area
    return total


def _spread_superposed_field_kpa(
    load: LoadModel, at_x_m: np.ndarray, at_y_m: np.ndarray, depth_m: float,
    spread_factor: float,
) -> np.ndarray:
    """Grid version of ``_spread_superposed_kpa``, for the sweeps and profiles."""
    xs = np.atleast_1d(np.asarray(at_x_m, dtype=float))
    ys = np.atleast_1d(np.asarray(at_y_m, dtype=float))
    out = np.zeros((xs.size, ys.size), dtype=float)
    half = max(spread_factor, 0.0) * max(depth_m, 0.0) / 2.0
    for p in load.patches:
        x0, x1, y0, y1 = p.bounds
        gx0, gx1, gy0, gy1 = x0 - half, x1 + half, y0 - half, y1 + half
        area = (gx1 - gx0) * (gy1 - gy0)
        inside = (
            (xs[:, None] >= gx0) & (xs[:, None] <= gx1)
            & (ys[None, :] >= gy0) & (ys[None, :] <= gy1)
        )
        out += np.where(inside, p.total_kn / area, 0.0)
    return out


def _spread_superposed_terms(
    load: LoadModel,
    at_x_m: float,
    at_y_m: float,
    depth_m: float,
    spread_factor: float,
    dla: float,
) -> list[TermTrace]:
    half = max(spread_factor, 0.0) * max(depth_m, 0.0) / 2.0
    terms = []
    for p in load.patches:
        x0, x1, y0, y1 = p.bounds
        gx0, gx1, gy0, gy1 = x0 - half, x1 + half, y0 - half, y1 + half
        area = (gx1 - gx0) * (gy1 - gy0)
        inside = gx0 <= at_x_m <= gx1 and gy0 <= at_y_m <= gy1
        value = p.total_kn / area if inside else 0.0
        terms.append(TermTrace(
            label=p.label,
            detail=(
                f"{p.total_kn:.2f} kN over its own {gx1 - gx0:.3f} x {gy1 - gy0:.3f} m "
                f"spread footprint (grown by {spread_factor:g} x {depth_m:.3f} m); "
                + ("point falls inside" if inside else "point falls outside - no contribution")
            ),
            value_kpa=round(value * dla, 4),
        ))
    return terms


def _plan_extent(load: LoadModel) -> tuple[float, float]:
    """Half-extents of the loaded footprint in x and y."""
    xs, ys = [], []
    for p in load.patches:
        x0, x1, y0, y1 = p.bounds
        xs.extend((x0, x1))
        ys.extend((y0, y1))
    for pt in load.points:
        xs.append(pt.x_m)
        ys.append(pt.y_m)
    if not xs:
        return 1.0, 1.0
    return max(abs(min(xs)), abs(max(xs))), max(abs(min(ys)), abs(max(ys)))


def _along_pipe_samples(load: LoadModel, depth_m: float) -> np.ndarray:
    """Positions along the pipe to search for the worst point."""
    _, half_y = _plan_extent(load)
    reach = half_y + 3.0 * max(depth_m, 0.3)
    return np.linspace(-reach, reach, _ALONG_SAMPLES)


def _spread_boxes(
    load: LoadModel, depth_m: float, spread_factor: float
) -> list[dict]:
    """Contact areas grown by the spread factor, with overlaps merged.

    Both AASHTO and the classical 2:1 rule require that where the spread areas
    of separate wheels or tracks run into one another, the combined load is
    taken over the combined area rather than counted twice.
    """
    if not load.patches:
        return []

    grown = max(spread_factor, 0.0) * max(depth_m, 0.0) / 2.0
    boxes = []
    for p in load.patches:
        x0, x1, y0, y1 = p.bounds
        boxes.append({
            "x0": x0 - grown, "x1": x1 + grown,
            "y0": y0 - grown, "y1": y1 + grown,
            "load": p.total_kn,
        })

    # Merge overlapping boxes into their bounding box until nothing overlaps.
    merged = True
    while merged and len(boxes) > 1:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if (a["x0"] < b["x1"] and b["x0"] < a["x1"]
                        and a["y0"] < b["y1"] and b["y0"] < a["y1"]):
                    boxes[i] = {
                        "x0": min(a["x0"], b["x0"]), "x1": max(a["x1"], b["x1"]),
                        "y0": min(a["y0"], b["y0"]), "y1": max(a["y1"], b["y1"]),
                        "load": a["load"] + b["load"],
                    }
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break

    return boxes


def _spread_pressure_kpa(
    load: LoadModel, depth_m: float, spread_factor: float
) -> float:
    """The governing (largest) spread pressure at this depth."""
    boxes = _spread_boxes(load, depth_m, spread_factor)
    if not boxes:
        return 0.0
    return max(
        box["load"] / ((box["x1"] - box["x0"]) * (box["y1"] - box["y0"]))
        for box in boxes
    )


def analyse(req: PipeSurchargeRequest) -> PipeSurchargeResult:
    """Compute crown surcharge by each method and sweep the position."""
    if req.cover_m <= 0:
        raise ValueError("Depth of cover must be greater than zero.")
    if req.pipe_od_m <= 0:
        raise ValueError("Pipe outside diameter must be greater than zero.")
    if req.dla < 1.0:
        raise ValueError("Dynamic load allowance is a multiplier and cannot be below 1.0.")

    load = req.load
    z = req.cover_m  # stress is wanted at the crown, i.e. at the top of the pipe

    # The load model is built centred on x = 0. Moving the machine by +offset
    # and reading the pipe at pipe_x is the same as leaving the machine put
    # and reading at (pipe_x - offset), which makes the sweep a single
    # vectorised evaluation instead of rebuilding the model 241 times.
    x_eval = req.pipe_x_m - req.machine_offset_m
    y_samples = _along_pipe_samples(load, z)

    at_position = stress_field_kpa(load, np.array([x_eval]), y_samples, z)[0]
    worst_y_index = int(np.argmax(at_position))
    y_worst = float(y_samples[worst_y_index])
    boussinesq_kpa = float(at_position[worst_y_index]) * req.dla

    # --- sweep the machine across the pipe -------------------------------
    half_x, _ = _plan_extent(load)
    reach = half_x + 3.0 * max(z, 0.3)
    x_sweep = np.linspace(req.pipe_x_m - reach, req.pipe_x_m + reach, _OFFSET_SAMPLES)
    sweep = stress_field_kpa(load, x_sweep, y_samples, z).max(axis=1) * req.dla
    best = int(np.argmax(sweep))
    worst_offset = float(req.pipe_x_m - x_sweep[best])
    worst_pressure = float(sweep[best])

    offset_profile = []
    if req.with_profiles:
        offset_profile = [
            {"offset_m": round(float(req.pipe_x_m - x), 4),
             "pressure_kpa": round(float(s), 4)}
            for x, s in zip(x_sweep, sweep)
        ]
        offset_profile.sort(key=lambda p: p["offset_m"])

    # --- average across the pipe, and load per metre ----------------------
    across = np.linspace(
        x_eval - req.pipe_od_m / 2.0, x_eval + req.pipe_od_m / 2.0, _ACROSS_PIPE_SAMPLES
    )
    across_stress = stress_field_kpa(
        load, across, np.array([y_worst]), z
    )[:, 0] * req.dla
    load_per_m = float(np.trapezoid(across_stress, across))
    average_kpa = load_per_m / req.pipe_od_m

    # --- depth profile, every method side by side -------------------------
    depth_profile: list[dict] = []
    bulb: dict = {}
    crown_plan: dict = {}
    if req.with_profiles:
        depths = np.linspace(0.15, max(3.0 * z, z + 2.0), _DEPTH_SAMPLES)
        at = np.array([x_eval])
        for d in depths:
            depth = float(d)
            ys = _along_pipe_samples(load, depth)
            row = {
                "depth_m": round(depth, 4),
                "boussinesq": round(float(
                    stress_field_kpa(load, at, ys, depth).max()) * req.dla, 4),
                "boussinesq_point": round(float(
                    point_idealised_field_kpa(load, at, ys, depth).max()) * req.dla, 4),
                "westergaard": round(float(westergaard_field_kpa(
                    load, at, ys, depth, req.poisson_ratio,
                    _WESTERGAARD_PROFILE_SUBDIVISIONS).max()) * req.dla, 4),
                "spread_2to1": round(
                    _spread_pressure_kpa(load, depth, 1.0) * req.dla, 4),
                "spread_superposed": round(float(_spread_superposed_field_kpa(
                    load, np.array([x_eval]), ys, depth, 1.0).max()) * req.dla, 4),
            }
            if req.spread_factor > 0:
                row["code_spread"] = round(
                    _spread_pressure_kpa(load, depth, req.spread_factor) * req.dla, 4)
            depth_profile.append(row)

        bulb = _pressure_bulb(load, req, x_eval, y_worst, half_x)
        crown_plan = _crown_plan(load, req, x_eval, half_x)

    # --- comparison methods ----------------------------------------------
    def sub(total: float, n_terms: int) -> str:
        return (
            f"Sum of {n_terms} contribution(s) at x = {x_eval:.3f} m, "
            f"y = {y_worst:.3f} m, z = {z:.3f} m, "
            f"then x DLA {req.dla:.2f}  =  {total:.2f} kPa"
        )

    b_terms = _superposition_terms(load, x_eval, y_worst, z, req.dla, "boussinesq")
    p_terms = _superposition_terms(load, x_eval, y_worst, z, req.dla, "point")
    w_terms = _superposition_terms(
        load, x_eval, y_worst, z, req.dla, "westergaard", req.poisson_ratio)
    point_kpa = float(point_idealised_field_kpa(
        load, np.array([x_eval]), y_samples, z).max()) * req.dla
    west_kpa = float(westergaard_field_kpa(
        load, np.array([x_eval]), y_samples, z, req.poisson_ratio).max()) * req.dla

    two_to_one_kpa = _spread_pressure_kpa(load, z, 1.0) * req.dla
    two_to_one_terms = _spread_terms(load, z, 1.0, req.dla)

    methods = [
        MethodResult(
            key="boussinesq",
            name="Boussinesq (elastic half-space)",
            pressure_kpa=boussinesq_kpa,
            basis=(
                "Rectangular contact areas integrated by the Newmark corner "
                "influence factor; superposed over every track or tyre."
            ),
            verified=True,
            note="Free-field vertical stress. Independent of soil E and Poisson's ratio.",
            formula=BOUSSINESQ_FORMULA,
            substitution=sub(boussinesq_kpa, len(b_terms)),
            terms=b_terms,
        ),
        MethodResult(
            key="boussinesq_point",
            name="Boussinesq (point-load idealisation)",
            pressure_kpa=point_kpa,
            basis="Each contact area collapsed to a point load at its centroid.",
            verified=True,
            note=(
                "Shown to expose the error in the point idealisation. It is "
                "singular at the surface and overstates stress badly whenever the "
                "contact area is not small against the depth."
            ),
            formula=POINT_FORMULA,
            substitution=sub(point_kpa, len(p_terms)),
            terms=p_terms,
        ),
        MethodResult(
            key="westergaard",
            name="Westergaard (nu = " + format(req.poisson_ratio, "g") + ")",
            pressure_kpa=west_kpa,
            basis=(
                "Half-space restrained against lateral strain by rigid horizontal "
                "layers; contact areas integrated numerically."
            ),
            verified=True,
            note=(
                "Suits a layered or varved deposit, or backfill compacted in thin "
                "lifts. Lower than Boussinesq beneath the load and higher out to "
                "the side, crossing over near r = 1.5 z."
            ),
            formula=WESTERGAARD_FORMULA,
            substitution=sub(west_kpa, len(w_terms)),
            terms=w_terms,
        ),
        MethodResult(
            key="spread_2to1",
            name="2:1 load spread",
            pressure_kpa=two_to_one_kpa,
            basis="Contact area grown by z/2 on each side; total load spread evenly over it.",
            verified=True,
            note=(
                "A bookkeeping rule that conserves load but has no theoretical "
                "basis and no notion of position relative to the load."
            ),
            formula=SPREAD_FORMULA,
            substitution=(
                f"f = 1.0, z = {z:.3f} m; largest of {len(two_to_one_terms)} merged "
                f"area(s), x DLA {req.dla:.2f}  =  {two_to_one_kpa:.2f} kPa"
            ),
            terms=two_to_one_terms,
            terms_sum_to_total=False,
        ),
    ]

    superposed_kpa = _spread_superposed_kpa(load, x_eval, y_worst, z, 1.0) * req.dla
    superposed_terms = _spread_superposed_terms(load, x_eval, y_worst, z, 1.0, req.dla)
    methods.append(MethodResult(
        key="spread_superposed",
        name="2:1 spread (individual, summed)",
        pressure_kpa=superposed_kpa,
        basis=(
            "Each tyre or track's own footprint grown by z/2 independently; "
            "footprints that reach the point of interest are added together "
            "rather than merged into one combined area."
        ),
        verified=True,
        note=(
            "An alternative reading of the 2:1 rule some offices use instead of "
            "merging overlapping footprints. Still a bookkeeping rule, not a "
            "solution of elasticity."
        ),
        formula=SPREAD_SUPERPOSED_FORMULA,
        substitution=(
            f"f = 1.0, z = {z:.3f} m; sum of contributions from footprints "
            f"reaching x = {x_eval:.3f} m, y = {y_worst:.3f} m, "
            f"x DLA {req.dla:.2f}  =  {superposed_kpa:.2f} kPa"
        ),
        terms=superposed_terms,
        terms_sum_to_total=True,
    ))

    if req.spread_factor > 0:
        code_kpa = _spread_pressure_kpa(load, z, req.spread_factor) * req.dla
        code_terms = _spread_terms(load, z, req.spread_factor, req.dla)
        methods.append(MethodResult(
            key="code_spread",
            name=f"Code load spread (LLDF = {req.spread_factor:g})",
            pressure_kpa=code_kpa,
            basis=(
                f"Contact area grown by {req.spread_factor:g} x depth in each plan "
                "dimension; overlapping spread areas combined."
            ),
            verified=req.spread_factor_verified,
            note=req.spread_factor_source,
            formula=SPREAD_FORMULA,
            substitution=(
                f"f = {req.spread_factor:g}, z = {z:.3f} m; largest of "
                f"{len(code_terms)} merged area(s), x DLA {req.dla:.2f}  =  "
                f"{code_kpa:.2f} kPa"
            ),
            terms=code_terms,
            terms_sum_to_total=False,
        ))

    soil_pressure = req.soil_unit_weight_kn_m3 * z

    return PipeSurchargeResult(
        cover_m=req.cover_m,
        pipe_od_m=req.pipe_od_m,
        crown_depth_m=z,
        machine_offset_m=req.machine_offset_m,
        load_description=load.description,
        total_load_kn=load.total_kn,
        dla=req.dla,
        methods=methods,
        live_pressure_kpa=boussinesq_kpa,
        average_over_pipe_kpa=average_kpa,
        load_per_m_kn_m=load_per_m,
        worst_offset_m=worst_offset,
        worst_offset_pressure_kpa=worst_pressure,
        offset_is_worst=abs(worst_pressure - boussinesq_kpa) <= 0.01 * max(worst_pressure, 1e-9),
        soil_pressure_kpa=soil_pressure,
        live_to_dead_ratio=boussinesq_kpa / soil_pressure if soil_pressure else 0.0,
        depth_profile=depth_profile,
        offset_profile=offset_profile,
        bulb=bulb,
        crown_plan=crown_plan,
        warnings=_warnings(req, boussinesq_kpa, worst_pressure, worst_offset),
    )


def _pressure_bulb(
    load: LoadModel,
    req: PipeSurchargeRequest,
    x_eval: float,
    y_worst: float,
    half_x: float,
) -> dict:
    """Vertical stress on a grid through the section, plus its contours.

    Sampled on the plane containing the worst point along the pipe, so the
    drawing and the reported crown figure describe the same situation.
    """
    # Extend a bit past the pipe invert so the bulb's decay below the pipe is
    # visible, without the chart zooming out so far that the cover looks wrong
    # at a glance (2.4x cover+OD read as "6.2 m deep" for a 2 m, 600 mm pipe).
    z_max = max(1.6 * (req.cover_m + req.pipe_od_m), req.cover_m + 1.2)
    span = max(half_x + 1.5 * req.cover_m, req.pipe_od_m * 2.0, 1.5)
    xs = np.linspace(x_eval - span, x_eval + span, _BULB_X_SAMPLES)
    zs = np.linspace(0.06, z_max, _BULB_Z_SAMPLES)

    grid = np.zeros((_BULB_Z_SAMPLES, _BULB_X_SAMPLES), dtype=float)
    at_y = np.array([y_worst])
    for i, depth in enumerate(zs):
        grid[i, :] = stress_field_kpa(load, xs, at_y, float(depth))[:, 0]
    grid *= req.dla

    peak = float(grid.max())
    isolines = [
        {"level_kpa": level, "segments": contours.iso_segments(grid, xs, zs, level)}
        for level in contours.nice_levels(peak)
    ]

    # x is reported as a position relative to the pipe centreline so the
    # drawing reads the same way round as the rest of the tool.
    return {
        "x_m": [round(float(x - x_eval + req.pipe_x_m), 4) for x in xs],
        "depth_m": [round(float(d), 4) for d in zs],
        "grid_kpa": [[round(float(v), 3) for v in row] for row in grid],
        "peak_kpa": round(peak, 3),
        "isolines": isolines,
    }


def _crown_plan(
    load: LoadModel,
    req: PipeSurchargeRequest,
    x_eval: float,
    half_x: float,
) -> dict:
    """Vertical stress on the horizontal plane at crown level.

    Feeds the horizontal cut in the 3D view, and shows how the surcharge is
    distributed along the pipe as well as across it.
    """
    _, half_y = _plan_extent(load)
    span_x = max(half_x + 1.5 * req.cover_m, req.pipe_od_m * 2.0, 1.5)
    span_y = max(half_y + 1.5 * req.cover_m, 1.5)
    xs = np.linspace(x_eval - span_x, x_eval + span_x, _PLAN_X_SAMPLES)
    ys = np.linspace(-span_y, span_y, _PLAN_Y_SAMPLES)

    grid = stress_field_kpa(load, xs, ys, req.cover_m) * req.dla  # (nx, ny)
    return {
        "x_m": [round(float(x - x_eval + req.pipe_x_m), 4) for x in xs],
        "y_m": [round(float(y), 4) for y in ys],
        # Rows follow y, columns follow x, matching the bulb convention.
        "grid_kpa": [[round(float(v), 3) for v in row] for row in grid.T],
        "peak_kpa": round(float(grid.max()), 3),
    }


def _warnings(
    req: PipeSurchargeRequest,
    at_position_kpa: float,
    worst_kpa: float,
    worst_offset_m: float,
) -> list[str]:
    out = [
        "Boussinesq gives the FREE-FIELD vertical stress in undisturbed ground - "
        "it does not model the pipe. A rigid pipe stiffer than its surround "
        "attracts more load than this; a flexible pipe sheds load into the "
        "sidefill and feels less. Converting this to a design pressure needs a "
        "bedding factor and a pipe-stiffness assessment.",
        "The half-space is assumed homogeneous, isotropic and linearly elastic. "
        "Compacted granular backfill over softer native soil does not behave that "
        "way, and any rigid pavement or running surface above will spread load "
        "far more than this predicts.",
    ]

    if worst_kpa > at_position_kpa * 1.02:
        out.append(
            f"The position analysed is not the worst one. Moving the machine to "
            f"{worst_offset_m:+.2f} m from the pipe centreline raises the crown "
            f"stress from {at_position_kpa:.1f} to {worst_kpa:.1f} kPa "
            f"({worst_kpa / at_position_kpa - 1:+.0%}). For a wide-gauge machine "
            "over shallow cover the worst case is often one track beside the pipe "
            "rather than the machine straddling it."
        )

    if req.cover_m < 0.6:
        out.append(
            f"Cover of {req.cover_m:.2f} m is shallow. Elastic theory is least "
            "reliable close to the surface, local bearing failure and rutting can "
            "govern instead, and most pipe manufacturers set a minimum construction "
            "cover for plant crossings - check theirs."
        )

    if req.cover_m < 0.5 * req.pipe_od_m:
        out.append(
            f"Cover ({req.cover_m:.2f} m) is less than half the pipe diameter "
            f"({req.pipe_od_m:.2f} m). Stress varies substantially over the height "
            "of the pipe, so a single crown value is a coarse representation."
        )

    if req.dla <= 1.0:
        out.append(
            "No dynamic load allowance applied (DLA = 1.0). That suits a stationary "
            "or slowly tracking machine; a vehicle moving at speed over an uneven "
            "surface needs an impact allowance."
        )

    if req.spread_factor > 0 and not req.spread_factor_verified:
        out.append(
            "The load-spread factor is unverified - confirm it against a licensed "
            "copy of the code you are working to before relying on that column."
        )

    return out
