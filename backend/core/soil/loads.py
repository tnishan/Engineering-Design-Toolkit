"""Surface load configurations for construction plant and vehicles.

Plan coordinates, all in metres:

    x   transverse to the pipe (across it)
    y   along the pipe axis
    z   depth below the ground surface

The pipe runs parallel to y, so moving a machine in x changes how much of its
load reaches the pipe, while moving it in y does not (for a long pipe).

Machines are laid out in a travel frame - u along the direction of travel, v
across it - and then mapped into (x, y) according to whether the machine is
tracking along the pipe or crossing it. A tracked machine crossing the pipe
presents its long track axis transverse to the pipe, which is a materially
different load case from tracking along it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Orientation = str  # "along" | "across"
ORIENTATIONS = ("along", "across")


@dataclass(frozen=True)
class Patch:
    """A uniformly loaded rectangle of ground contact."""

    label: str
    x_m: float
    y_m: float
    width_x_m: float
    length_y_m: float
    total_kn: float

    def __post_init__(self) -> None:
        if self.width_x_m <= 0 or self.length_y_m <= 0:
            raise ValueError(f"{self.label}: contact area must be positive.")

    @property
    def area_m2(self) -> float:
        return self.width_x_m * self.length_y_m

    @property
    def pressure_kpa(self) -> float:
        return self.total_kn / self.area_m2

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x_min, x_max, y_min, y_max)."""
        return (
            self.x_m - self.width_x_m / 2.0,
            self.x_m + self.width_x_m / 2.0,
            self.y_m - self.length_y_m / 2.0,
            self.y_m + self.length_y_m / 2.0,
        )

    def moved_to_x(self, x_m: float) -> "Patch":
        return Patch(self.label, x_m, self.y_m, self.width_x_m,
                     self.length_y_m, self.total_kn)


@dataclass(frozen=True)
class PointLoad:
    label: str
    x_m: float
    y_m: float
    load_kn: float


@dataclass
class LoadModel:
    """A complete surface loading, plus a sentence describing where it came from."""

    patches: list[Patch] = field(default_factory=list)
    points: list[PointLoad] = field(default_factory=list)
    description: str = ""

    @property
    def total_kn(self) -> float:
        return (sum(p.total_kn for p in self.patches)
                + sum(p.load_kn for p in self.points))

    @property
    def centroid_x_m(self) -> float:
        total = self.total_kn
        if not total:
            return 0.0
        moment = (sum(p.total_kn * p.x_m for p in self.patches)
                  + sum(p.load_kn * p.x_m for p in self.points))
        return moment / total

    def shifted_x(self, dx_m: float) -> "LoadModel":
        """The same machine moved transversely across the pipe."""
        return LoadModel(
            patches=[p.moved_to_x(p.x_m + dx_m) for p in self.patches],
            points=[PointLoad(p.label, p.x_m + dx_m, p.y_m, p.load_kn)
                    for p in self.points],
            description=self.description,
        )


def _to_plan(u_m: float, v_m: float, orientation: Orientation) -> tuple[float, float]:
    """Map travel-frame (along, across) to plan (x, y).

    Tracking along the pipe: travel is parallel to the pipe, so u -> y.
    Crossing the pipe: travel is transverse, so u -> x.
    """
    if orientation == "along":
        return v_m, u_m
    if orientation == "across":
        return u_m, v_m
    raise ValueError(f"Orientation must be one of {ORIENTATIONS}, got {orientation!r}.")


def _oriented_dims(
    along_travel_m: float, across_travel_m: float, orientation: Orientation
) -> tuple[float, float]:
    """Return (width_x, length_y) for a patch given its travel-frame dimensions."""
    if orientation == "along":
        return across_travel_m, along_travel_m
    if orientation == "across":
        return along_travel_m, across_travel_m
    raise ValueError(f"Orientation must be one of {ORIENTATIONS}, got {orientation!r}.")


def tracked_machine(
    weight_kn: float,
    track_length_m: float,
    track_width_m: float,
    gauge_m: float,
    orientation: Orientation = "across",
    centre_x_m: float = 0.0,
    centre_y_m: float = 0.0,
) -> LoadModel:
    """Two-track plant (excavator, dozer) with the load split evenly.

    ``gauge_m`` is centre-to-centre between the two tracks. The even split is
    the standard idealisation; in reality slewing the upper structure shifts
    load onto one track, which the caller should account for separately.
    """
    if weight_kn <= 0:
        raise ValueError("Machine weight must be greater than zero.")
    if gauge_m <= 0:
        raise ValueError("Track gauge must be greater than zero.")

    per_track = weight_kn / 2.0
    width_x, length_y = _oriented_dims(track_length_m, track_width_m, orientation)

    patches = []
    for sign, name in ((-1.0, "left"), (+1.0, "right")):
        # Tracks are separated across the direction of travel.
        du, dv = 0.0, sign * gauge_m / 2.0
        dx, dy = _to_plan(du, dv, orientation)
        patches.append(Patch(
            label=f"{name} track",
            x_m=centre_x_m + dx,
            y_m=centre_y_m + dy,
            width_x_m=width_x,
            length_y_m=length_y,
            total_kn=per_track,
        ))

    contact = track_length_m * track_width_m
    return LoadModel(
        patches=patches,
        description=(
            f"Tracked machine, {weight_kn:.0f} kN operating weight on two "
            f"{track_length_m:.2f} m x {track_width_m:.2f} m tracks at "
            f"{gauge_m:.2f} m gauge, {'tracking along' if orientation == 'along' else 'crossing'} "
            f"the pipe. Nominal ground bearing pressure "
            f"{weight_kn / (2 * contact):.1f} kPa."
        ),
    )


def wheel_group(
    wheel_load_kn: float,
    patch_along_travel_m: float,
    patch_across_travel_m: float,
    axle_width_m: float,
    orientation: Orientation = "across",
    dual_spacing_m: float = 0.0,
    axle_count: int = 1,
    axle_spacing_m: float = 0.0,
    centre_x_m: float = 0.0,
    centre_y_m: float = 0.0,
) -> LoadModel:
    """A wheeled axle group.

    ``wheel_load_kn`` is the load on ONE tyre. Where ``dual_spacing_m`` is
    non-zero each wheel position carries two tyres at that centre-to-centre
    spacing, each taking ``wheel_load_kn``.
    """
    if wheel_load_kn <= 0:
        raise ValueError("Wheel load must be greater than zero.")
    if axle_count < 1:
        raise ValueError("There must be at least one axle.")
    if axle_width_m <= 0:
        raise ValueError("Axle width must be greater than zero.")

    width_x, length_y = _oriented_dims(
        patch_along_travel_m, patch_across_travel_m, orientation
    )

    # Axles are spaced along the direction of travel, centred on the group.
    axle_offsets = [
        (i - (axle_count - 1) / 2.0) * axle_spacing_m for i in range(axle_count)
    ]
    # Wheels sit either side of the vehicle centreline, across travel.
    wheel_offsets = [-axle_width_m / 2.0, +axle_width_m / 2.0]
    tyre_offsets = (
        [0.0] if dual_spacing_m <= 0
        else [-dual_spacing_m / 2.0, +dual_spacing_m / 2.0]
    )

    patches = []
    for a, du in enumerate(axle_offsets, start=1):
        for side, wheel_v in zip(("left", "right"), wheel_offsets):
            for t, tyre_v in enumerate(tyre_offsets, start=1):
                dx, dy = _to_plan(du, wheel_v + tyre_v, orientation)
                tyre_name = "" if len(tyre_offsets) == 1 else f" tyre {t}"
                patches.append(Patch(
                    label=f"axle {a} {side}{tyre_name}",
                    x_m=centre_x_m + dx,
                    y_m=centre_y_m + dy,
                    width_x_m=width_x,
                    length_y_m=length_y,
                    total_kn=wheel_load_kn,
                ))

    tyres = len(patches)
    return LoadModel(
        patches=patches,
        description=(
            f"{tyres} tyres at {wheel_load_kn:.1f} kN each "
            f"({wheel_load_kn * tyres:.0f} kN total) on "
            f"{patch_across_travel_m * 1000:.0f} x {patch_along_travel_m * 1000:.0f} mm "
            f"contact patches, {axle_count} axle(s) at {axle_width_m:.2f} m track, "
            f"{'travelling along' if orientation == 'along' else 'crossing'} the pipe. "
            f"Contact pressure {wheel_load_kn / (patch_along_travel_m * patch_across_travel_m):.0f} kPa."
        ),
    )


@dataclass(frozen=True)
class AxleSpec:
    """One axle (or tandem axle line) of a multi-axle vehicle.

    Mirrors the fields on a typical manufacturer axle-weight sheet: a load,
    a tyre count per side, a tyre width, and either a direct contact length
    or a tyre pressure to derive one from.
    """

    label: str
    load_kn: float                       # total load on this axle, both sides
    tires_per_side: int = 1              # 1 = single, 2 = dual
    tire_width_m: float = 0.3
    tire_length_m: float | None = None   # contact length along travel, if known
    tire_pressure_kpa: float | None = None  # else derive length from load/pressure
    dual_spacing_m: float = 0.0          # centre-to-centre between duals
    spacing_from_previous_m: float = 0.0  # 0 for the first axle (reference)

    def __post_init__(self) -> None:
        if self.load_kn <= 0:
            raise ValueError(f"{self.label}: axle load must be greater than zero.")
        if self.tires_per_side not in (1, 2):
            raise ValueError(f"{self.label}: tires_per_side must be 1 or 2.")
        if self.tire_width_m <= 0:
            raise ValueError(f"{self.label}: tyre width must be greater than zero.")
        if self.tire_length_m is None and not self.tire_pressure_kpa:
            raise ValueError(
                f"{self.label}: give either a contact length or a tyre pressure."
            )
        if self.tire_length_m is not None and self.tire_length_m <= 0:
            raise ValueError(f"{self.label}: contact length must be greater than zero.")
        if self.tire_pressure_kpa is not None and self.tire_pressure_kpa <= 0:
            raise ValueError(f"{self.label}: tyre pressure must be greater than zero.")
        if self.tires_per_side == 2 and self.dual_spacing_m <= 0:
            raise ValueError(f"{self.label}: dual tyres need a centre-to-centre spacing.")

    def wheel_load_kn(self) -> float:
        """Load on ONE tyre."""
        return self.load_kn / (2 * self.tires_per_side)

    def contact_length_m(self) -> float:
        """Contact patch length along travel.

        Where only a tyre pressure is given, the length is backed out from
        the standard pavement-engineering rule of thumb: contact area equals
        load divided by inflation pressure (kN / kPa = m^2, since 1 kPa =
        1 kN/m^2). This is an approximation - actual tyre footprints are not
        rectangular - adequate for a comparative surcharge check.
        """
        if self.tire_length_m is not None:
            return self.tire_length_m
        area_m2 = self.wheel_load_kn() / self.tire_pressure_kpa
        return area_m2 / self.tire_width_m


def multi_axle_vehicle(
    axles: list[AxleSpec],
    axle_width_m: float,
    orientation: Orientation = "across",
    centre_x_m: float = 0.0,
    centre_y_m: float = 0.0,
) -> LoadModel:
    """A general multi-axle vehicle: trucks, cranes, anything with a wheel plan.

    ``axle_width_m`` is the centre-to-centre distance between the left and
    right wheel lines (the vehicle's track width), assumed constant along the
    vehicle. ``axles`` are given in travel order; ``spacing_from_previous_m``
    on each (after the first) is the centre-to-centre distance to the axle
    ahead of it.
    """
    if not axles:
        raise ValueError("A vehicle needs at least one axle.")
    if axle_width_m <= 0:
        raise ValueError("Axle (track) width must be greater than zero.")

    positions_u: list[float] = [0.0]
    for axle in axles[1:]:
        if axle.spacing_from_previous_m <= 0:
            raise ValueError(
                f"{axle.label}: spacing from the previous axle must be greater than zero."
            )
        positions_u.append(positions_u[-1] + axle.spacing_from_previous_m)

    # Centre the vehicle on the midpoint of its wheelbase, matching how the
    # tracked and simple wheel-group builders are centred.
    mid_u = positions_u[-1] / 2.0
    wheel_v = [-axle_width_m / 2.0, +axle_width_m / 2.0]

    patches: list[Patch] = []
    for axle, u in zip(axles, positions_u):
        u_centered = u - mid_u
        wheel_load = axle.wheel_load_kn()
        length = axle.contact_length_m()
        width_x, length_y = _oriented_dims(length, axle.tire_width_m, orientation)
        tyre_offsets = (
            [0.0] if axle.tires_per_side == 1
            else [-axle.dual_spacing_m / 2.0, +axle.dual_spacing_m / 2.0]
        )
        for side, v in zip(("left", "right"), wheel_v):
            for t, tv in enumerate(tyre_offsets, start=1):
                dx, dy = _to_plan(u_centered, v + tv, orientation)
                tyre_name = "" if len(tyre_offsets) == 1 else f" dual {t}"
                patches.append(Patch(
                    label=f"{axle.label} {side}{tyre_name}",
                    x_m=centre_x_m + dx,
                    y_m=centre_y_m + dy,
                    width_x_m=width_x,
                    length_y_m=length_y,
                    total_kn=wheel_load,
                ))

    total = sum(a.load_kn for a in axles)
    wheelbase = positions_u[-1]
    return LoadModel(
        patches=patches,
        description=(
            f"{len(axles)}-axle vehicle, {total:.0f} kN total over a "
            f"{wheelbase:.2f} m wheelbase at {axle_width_m:.2f} m track, "
            f"{'tracking along' if orientation == 'along' else 'crossing'} the pipe. "
            f"Axle loads: {', '.join(f'{a.load_kn:.0f}' for a in axles)} kN."
        ),
    )


def custom_load(
    patches: list[Patch] | None = None,
    points: list[PointLoad] | None = None,
) -> LoadModel:
    """Raw rectangles and point loads, for ad-hoc checks and hand verification."""
    patches = patches or []
    points = points or []
    if not patches and not points:
        raise ValueError("Enter at least one rectangle or point load.")
    bits = []
    if patches:
        bits.append(f"{len(patches)} loaded rectangle(s)")
    if points:
        bits.append(f"{len(points)} point load(s)")
    return LoadModel(
        patches=patches,
        points=points,
        description="User-defined surface loading: " + " and ".join(bits) + ".",
    )
