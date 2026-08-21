"""Continuous beam analysis by the direct stiffness method.

Two-node Timoshenko beam elements (2 DOF per node: transverse displacement v,
section rotation theta). Shear deformation is included through

    phi = 12 EI / (G A_s L^2)

because CSA O86 SCL products (LVL/PSL/LSL) have a published shear modulus and
their manufacturers require shear deflection be accounted for; for sawn lumber
the contribution is small but harmless. Setting G very large recovers the
Euler-Bernoulli solution.

Sign conventions (consistent throughout the toolkit):
    x       measured from the left end of the beam, mm
    loads   positive downward, N (point) or N/mm (distributed)
    v       positive upward, mm  (so a downward-loaded beam gives negative v)
    V       positive when the resultant of forces left of the cut acts upward, N
    M       positive sagging (tension on the bottom face), N.mm

Because the system is linear elastic, each load case (D, L, S, W) is solved once
and load combinations are formed by superposition of the case results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Supports that restrain vertical translation only. In a plane beam with no
# axial degree of freedom a pin and a roller are mechanically identical; both
# are accepted so the input reads the way an engineer would draw it.
_VERTICAL_ONLY = {"pin", "roller"}
_SUPPORT_KINDS = _VERTICAL_ONLY | {"fixed", "free"}

# Offset used to sample either side of a shear discontinuity (mm).
_EPS = 1e-6


class BeamModelError(ValueError):
    """Raised for an unstable or otherwise invalid beam model."""


@dataclass(frozen=True)
class Support:
    x_mm: float
    kind: str = "pin"

    def __post_init__(self) -> None:
        if self.kind not in _SUPPORT_KINDS:
            raise BeamModelError(
                f"Unknown support kind {self.kind!r}; expected one of {sorted(_SUPPORT_KINDS)}"
            )


@dataclass(frozen=True)
class DistributedLoad:
    """Uniformly distributed load, N/mm, positive downward."""

    w: float
    x_start_mm: float
    x_end_mm: float
    case: str = "D"


@dataclass(frozen=True)
class PointLoad:
    """Concentrated load, N, positive downward."""

    P: float
    x_mm: float
    case: str = "D"


@dataclass(frozen=True)
class Section:
    """Elastic properties of the (possibly built-up) cross-section."""

    E_mpa: float
    I_mm4: float
    A_shear_mm2: float
    G_mpa: float


@dataclass
class CaseResult:
    """Analysis results for one specified load case, sampled at stations."""

    x_mm: np.ndarray
    shear_n: np.ndarray
    moment_nmm: np.ndarray
    deflection_mm: np.ndarray
    reactions_n: dict[float, float]
    moment_reactions_nmm: dict[float, float] = field(default_factory=dict)


@dataclass
class BeamGeometry:
    length_mm: float
    supports: list[Support]
    section: Section
    elements_target: int = 120

    stations_mm: np.ndarray = field(init=False)
    _nodes: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.length_mm <= 0:
            raise BeamModelError("Beam length must be positive.")
        xs = sorted(s.x_mm for s in self.supports)
        if len(xs) < 2:
            raise BeamModelError("A beam needs at least two supports.")
        restrained = [s for s in self.supports if s.kind != "free"]
        if not restrained:
            raise BeamModelError("All supports are free; the beam is unstable.")
        if len(restrained) == 1 and restrained[0].kind != "fixed":
            raise BeamModelError(
                "A single vertical support cannot stabilise the beam; "
                "use a fixed support or add a second support."
            )
        for s in self.supports:
            if not (-_EPS <= s.x_mm <= self.length_mm + _EPS):
                raise BeamModelError(
                    f"Support at {s.x_mm:.0f} mm lies outside the beam (0 to {self.length_mm:.0f} mm)."
                )


def build_geometry(
    spans_mm: list[float],
    support_kinds: list[str],
    section: Section,
    left_overhang_mm: float = 0.0,
    right_overhang_mm: float = 0.0,
    elements_target: int = 120,
) -> BeamGeometry:
    """Assemble geometry from a list of clear spans plus optional cantilevers."""
    if not spans_mm:
        raise BeamModelError("At least one span is required.")
    if any(s <= 0 for s in spans_mm):
        raise BeamModelError("Every span must be greater than zero.")
    if len(support_kinds) != len(spans_mm) + 1:
        raise BeamModelError(
            f"Expected {len(spans_mm) + 1} supports for {len(spans_mm)} span(s), "
            f"got {len(support_kinds)}."
        )
    if left_overhang_mm < 0 or right_overhang_mm < 0:
        raise BeamModelError("Overhang lengths cannot be negative.")

    x = left_overhang_mm
    supports = [Support(x, support_kinds[0])]
    for span, kind in zip(spans_mm, support_kinds[1:]):
        x += span
        supports.append(Support(x, kind))

    total = left_overhang_mm + sum(spans_mm) + right_overhang_mm
    return BeamGeometry(total, supports, section, elements_target)


def _node_positions(
    geom: BeamGeometry,
    distributed: list[DistributedLoad],
    points: list[PointLoad],
    extra_breaks_mm: list[float] | None = None,
) -> np.ndarray:
    """Mesh the beam, forcing nodes at every geometric and load discontinuity.

    ``extra_breaks_mm`` lets a caller force additional break points that have
    nothing to do with this particular case's own loads - see ``solve_case``
    for why every load case needs an identical mesh.
    """
    breaks = {0.0, geom.length_mm}
    breaks.update(s.x_mm for s in geom.supports)
    breaks.update(p.x_mm for p in points)
    for d in distributed:
        breaks.add(d.x_start_mm)
        breaks.add(d.x_end_mm)
    if extra_breaks_mm:
        breaks.update(extra_breaks_mm)
    keys = sorted(x for x in breaks if -_EPS <= x <= geom.length_mm + _EPS)

    # Collapse near-duplicates so no zero-length elements are generated.
    anchors: list[float] = []
    for x in keys:
        if not anchors or x - anchors[-1] > 1e-3:
            anchors.append(x)
    anchors[0] = 0.0
    anchors[-1] = geom.length_mm

    per_mm = geom.elements_target / geom.length_mm
    nodes: list[float] = []
    for a, b in zip(anchors[:-1], anchors[1:]):
        n = max(2, int(round((b - a) * per_mm)))
        nodes.extend(np.linspace(a, b, n + 1)[:-1])
    nodes.append(geom.length_mm)
    return np.array(nodes)


def _element_stiffness(E: float, I: float, G: float, A_s: float, L: float) -> np.ndarray:
    """Timoshenko 2-node beam element stiffness in [v1, t1, v2, t2]."""
    phi = 12.0 * E * I / (G * A_s * L * L) if G * A_s > 0 else 0.0
    c = E * I / (L**3 * (1.0 + phi))
    L2 = L * L
    return c * np.array(
        [
            [12.0, 6.0 * L, -12.0, 6.0 * L],
            [6.0 * L, (4.0 + phi) * L2, -6.0 * L, (2.0 - phi) * L2],
            [-12.0, -6.0 * L, 12.0, -6.0 * L],
            [6.0 * L, (2.0 - phi) * L2, -6.0 * L, (4.0 + phi) * L2],
        ]
    )


def _solve_displacements(
    geom: BeamGeometry,
    nodes: np.ndarray,
    distributed: list[DistributedLoad],
    points: list[PointLoad],
) -> tuple[np.ndarray, dict[float, float], dict[float, float]]:
    n_nodes = len(nodes)
    ndof = 2 * n_nodes
    K = np.zeros((ndof, ndof))
    F = np.zeros(ndof)
    sec = geom.section

    for e in range(n_nodes - 1):
        L = nodes[e + 1] - nodes[e]
        ke = _element_stiffness(sec.E_mpa, sec.I_mm4, sec.G_mpa, sec.A_shear_mm2, L)
        dofs = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        K[np.ix_(dofs, dofs)] += ke

        # Consistent fixed-end forces for a full-element UDL (w positive down,
        # so the equivalent nodal loads act downward -> negative in v-up sign).
        w = 0.0
        mid = 0.5 * (nodes[e] + nodes[e + 1])
        for d in distributed:
            if d.x_start_mm - 1e-9 <= mid <= d.x_end_mm + 1e-9:
                w += d.w
        if w:
            F[dofs[0]] += -w * L / 2.0
            F[dofs[1]] += -w * L * L / 12.0
            F[dofs[2]] += -w * L / 2.0
            F[dofs[3]] += +w * L * L / 12.0

    for p in points:
        idx = int(np.argmin(np.abs(nodes - p.x_mm)))
        F[2 * idx] += -p.P

    fixed: list[int] = []
    for s in geom.supports:
        idx = int(np.argmin(np.abs(nodes - s.x_mm)))
        if s.kind in _VERTICAL_ONLY:
            fixed.append(2 * idx)
        elif s.kind == "fixed":
            fixed.extend((2 * idx, 2 * idx + 1))

    free = np.setdiff1d(np.arange(ndof), np.array(fixed, dtype=int))
    u = np.zeros(ndof)
    try:
        u[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
    except np.linalg.LinAlgError as exc:
        raise BeamModelError(
            "The beam model is unstable (singular stiffness matrix). "
            "Check that the supports restrain the member."
        ) from exc

    residual = K @ u - F
    reactions: dict[float, float] = {}
    moment_reactions: dict[float, float] = {}
    for s in geom.supports:
        if s.kind == "free":
            continue
        idx = int(np.argmin(np.abs(nodes - s.x_mm)))
        reactions[float(nodes[idx])] = float(residual[2 * idx])
        if s.kind == "fixed":
            moment_reactions[float(nodes[idx])] = float(residual[2 * idx + 1])

    return u, reactions, moment_reactions


def _internal_forces(
    stations: np.ndarray,
    distributed: list[DistributedLoad],
    points: list[PointLoad],
    reactions: dict[float, float],
    moment_reactions: dict[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Shear and moment by statics on the free body left of each station.

    Working from equilibrium rather than from element end forces keeps the
    diagrams independent of the mesh and makes them directly checkable by hand.
    """
    V = np.zeros_like(stations)
    M = np.zeros_like(stations)
    x = stations[:, None]

    def _accumulate(positions: list[float], magnitudes: list[float], sign: float) -> None:
        """Add point-like forces acting left of each station."""
        if not positions:
            return
        px = np.asarray(positions)[None, :]
        pv = np.asarray(magnitudes)[None, :] * sign
        left = px <= x + _EPS
        V[:] += np.where(left, pv, 0.0).sum(axis=1)
        M[:] += np.where(left, pv * (x - px), 0.0).sum(axis=1)

    _accumulate(list(reactions.keys()), list(reactions.values()), 1.0)
    _accumulate([p.x_mm for p in points], [p.P for p in points], -1.0)

    # A counter-clockwise restraint moment left of the cut reduces the sagging
    # moment there (check: cantilever fixed at x=0 with tip load P has
    # M_r = +PL, giving M(x) = Px - PL = -P(L-x) as required).
    if moment_reactions:
        mx = np.asarray(list(moment_reactions.keys()))[None, :]
        mv = np.asarray(list(moment_reactions.values()))[None, :]
        M[:] -= np.where(mx <= x + _EPS, mv, 0.0).sum(axis=1)

    for d in distributed:
        b = np.minimum(d.x_end_mm, stations)
        length = np.maximum(b - d.x_start_mm, 0.0)
        resultant = d.w * length
        centroid = 0.5 * (d.x_start_mm + b)
        V -= resultant
        M -= resultant * (stations - centroid)

    return V, M


def solve_case(
    geom: BeamGeometry,
    distributed: list[DistributedLoad],
    points: list[PointLoad],
    extra_breaks_mm: list[float] | None = None,
) -> CaseResult:
    """Analyse the beam under one set of specified loads.

    ``extra_breaks_mm`` forces additional mesh break points beyond this case's
    own loads. Pass the union of every case's point-load and partial-UDL
    locations when solving several cases on the same beam - otherwise a load
    that only one case carries gives that case a different mesh (and so a
    different-length ``x_mm``/result array) than the others, and combining the
    cases into an envelope fails.
    """
    nodes = _node_positions(geom, distributed, points, extra_breaks_mm)
    u, reactions, moment_reactions = _solve_displacements(geom, nodes, distributed, points)
    deflection = u[0::2]

    # Duplicate stations either side of each shear discontinuity so that the
    # jump in V is captured and peak shear is not missed.
    disc = set(
        [s.x_mm for s in geom.supports if s.kind != "free"]
        + [p.x_mm for p in points]
        + list(extra_breaks_mm or [])
    )
    stations = list(nodes)
    for x in disc:
        if _EPS < x < geom.length_mm - _EPS:
            stations.extend((x - _EPS, x + _EPS))
    stations_arr = np.array(sorted(stations))

    V, M = _internal_forces(stations_arr, distributed, points, reactions, moment_reactions)
    defl = np.interp(stations_arr, nodes, deflection)

    return CaseResult(stations_arr, V, M, defl, reactions, moment_reactions)


def combine(cases: dict[str, CaseResult], factors: dict[str, float]) -> CaseResult:
    """Superpose solved load cases using load-combination factors."""
    ref = next(iter(cases.values()))
    V = np.zeros_like(ref.shear_n)
    M = np.zeros_like(ref.moment_nmm)
    d = np.zeros_like(ref.deflection_mm)
    reactions: dict[float, float] = {x: 0.0 for x in ref.reactions_n}
    moment_reactions: dict[float, float] = {x: 0.0 for x in ref.moment_reactions_nmm}

    for case, f in factors.items():
        r = cases.get(case)
        if r is None or not f:
            continue
        V += f * r.shear_n
        M += f * r.moment_nmm
        d += f * r.deflection_mm
        for x, val in r.reactions_n.items():
            reactions[x] = reactions.get(x, 0.0) + f * val
        for x, val in r.moment_reactions_nmm.items():
            moment_reactions[x] = moment_reactions.get(x, 0.0) + f * val

    return CaseResult(ref.x_mm, V, M, d, reactions, moment_reactions)
