"""Buried-pipe surcharge endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.soil import (
    AxleSpecIn,
    SurchargeRequestIn,
    SurchargeResponseOut,
    VehicleComparisonRequestIn,
    VehicleComparisonResponseOut,
    VehicleSpecIn,
)
from core.report import soil_report
from core.soil import vehicles as vehicle_presets
from core.soil.buried_pipe import PipeSurchargeRequest, analyse
from core.soil.loads import (
    AxleSpec,
    LoadModel,
    Patch,
    PointLoad,
    custom_load,
    multi_axle_vehicle,
    tracked_machine,
    wheel_group,
)
from core.units import MM_PER_FOOT, parse_length_mm

router = APIRouter(prefix="/api/soil", tags=["soil"])


# Load-spread factors. AASHTO's live-load distribution factor for fill over
# culverts is a transcription and is NOT verified against a licensed copy of
# the code; the app says so on every result that uses it. No CSA S6 values are
# built in - enter your own with the "custom" preset.
SPREAD_PRESETS: dict[str, tuple[float, str, bool]] = {
    "aashto_granular": (
        1.15,
        "AASHTO LRFD live-load distribution through fill, select granular "
        "backfill - UNVERIFIED transcription, check against a licensed copy.",
        False,
    ),
    "aashto_other": (
        1.0,
        "AASHTO LRFD live-load distribution through fill, backfill other than "
        "select granular - UNVERIFIED transcription, check against a licensed copy.",
        False,
    ),
    "custom": (0.0, "User-entered distribution factor.", False),
    "none": (0.0, "", True),
}


def _m(value, field: str) -> float:
    """Parse a length input and return metres."""
    try:
        return parse_length_mm(value) / 1000.0
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as text
        raise ValueError(f"{field}: {exc}") from exc


def _axle_spec(a: AxleSpecIn) -> AxleSpec:
    return AxleSpec(
        label=a.label,
        load_kn=a.load_kn,
        tires_per_side=a.tires_per_side,
        tire_width_m=_m(a.tire_width, f"{a.label} tyre width"),
        tire_length_m=_m(a.tire_length, f"{a.label} tyre length") if a.tire_length else None,
        tire_pressure_kpa=a.tire_pressure_kpa,
        dual_spacing_m=_m(a.dual_spacing, f"{a.label} dual spacing"),
        spacing_from_previous_m=_m(a.spacing_from_previous, f"{a.label} axle spacing"),
    )


def _build_load(payload: SurchargeRequestIn, orientation: str | None = None) -> LoadModel:
    orientation = orientation or payload.orientation
    if payload.load_type == "tracked":
        t = payload.tracked
        if t is None:
            raise ValueError("Tracked machine details are required.")
        return tracked_machine(
            weight_kn=t.weight_kn,
            track_length_m=_m(t.track_length, "track length"),
            track_width_m=_m(t.track_width, "track width"),
            gauge_m=_m(t.gauge, "track gauge"),
            orientation=orientation,
        )

    if payload.load_type == "wheels":
        w = payload.wheels
        if w is None:
            raise ValueError("Wheel group details are required.")
        return wheel_group(
            wheel_load_kn=w.wheel_load_kn,
            patch_along_travel_m=_m(w.patch_along_travel, "contact patch along travel"),
            patch_across_travel_m=_m(w.patch_across_travel, "contact patch across travel"),
            axle_width_m=_m(w.axle_width, "axle width"),
            orientation=orientation,
            dual_spacing_m=_m(w.dual_spacing, "dual spacing"),
            axle_count=w.axle_count,
            axle_spacing_m=_m(w.axle_spacing, "axle spacing"),
        )

    if payload.load_type == "truck":
        if not payload.truck_axles:
            raise ValueError("A truck needs at least one axle.")
        return multi_axle_vehicle(
            axles=[_axle_spec(a) for a in payload.truck_axles],
            axle_width_m=_m(payload.truck_axle_width, "axle (track) width"),
            orientation=orientation,
        )

    patches = [
        Patch(
            label=p.label,
            x_m=_m(p.x, f"{p.label} x"),
            y_m=_m(p.y, f"{p.label} y"),
            width_x_m=_m(p.width_x, f"{p.label} width"),
            length_y_m=_m(p.length_y, f"{p.label} length"),
            total_kn=p.total_kn,
        )
        for p in payload.custom_patches
    ]
    points = [
        PointLoad(
            label=p.label,
            x_m=_m(p.x, f"{p.label} x"),
            y_m=_m(p.y, f"{p.label} y"),
            load_kn=p.load_kn,
        )
        for p in payload.custom_points
    ]
    return custom_load(patches, points)


def _dla(dla_mode: str, dla_value: float, cover_m: float) -> tuple[float, str]:
    if dla_mode == "none":
        return 1.0, "No dynamic load allowance (static or slowly tracking plant)."
    if dla_mode == "manual":
        return dla_value, f"User-entered dynamic load allowance of {dla_value:.2f}."
    # Depth-reducing impact allowance, AASHTO form: IM% = 33(1 - 0.125 D_E),
    # D_E in feet, not less than zero.
    depth_ft = cover_m * 1000.0 / MM_PER_FOOT
    im_percent = max(0.0, 33.0 * (1.0 - 0.125 * depth_ft))
    return 1.0 + im_percent / 100.0, (
        f"Depth-reduced impact, AASHTO form IM = 33(1 - 0.125 x {depth_ft:.2f} ft) "
        f"= {im_percent:.1f}% - UNVERIFIED transcription, check against a licensed copy."
    )


@router.get("/vehicle-presets")
def vehicle_presets_endpoint() -> dict:
    """Reference tracked plant and trucks, for the vehicle picker.

    Every value here is a transcription (marked ``verified: false``, with an
    ``assumptions`` list for anything the source sheet did not give). The
    frontend uses this to pre-fill the tracked/truck sub-forms - the analysis
    itself only ever sees the plain fields, never a preset key.
    """
    return {
        "tracked": [
            {
                "key": p.key, "name": p.name, "weight_kn": round(p.weight_kn, 2),
                "track_length_m": round(p.track_length_m, 4),
                "track_width_m": round(p.track_width_m, 4),
                "gauge_m": round(p.gauge_m, 4),
                "source": p.source, "verified": p.verified,
                "assumptions": p.assumptions,
            }
            for p in vehicle_presets.TRACKED_PRESETS.values()
        ],
        "trucks": [
            {
                "key": p.key, "name": p.name, "axle_width_m": round(p.axle_width_m, 4),
                "source": p.source, "verified": p.verified, "assumptions": p.assumptions,
                "axles": [
                    {
                        "label": a.label, "load_kn": round(a.load_kn, 3),
                        "tires_per_side": a.tires_per_side,
                        "tire_width_m": round(a.tire_width_m, 4),
                        "tire_length_m": (
                            round(a.tire_length_m, 4) if a.tire_length_m is not None else None
                        ),
                        "tire_pressure_kpa": a.tire_pressure_kpa,
                        "dual_spacing_m": round(a.dual_spacing_m, 4),
                        "spacing_from_previous_m": round(a.spacing_from_previous_m, 4),
                    }
                    for a in p.axles
                ],
            }
            for p in vehicle_presets.TRUCK_PRESETS.values()
        ],
    }


def _load_for_vehicle_spec(spec: VehicleSpecIn) -> LoadModel:
    """Build a LoadModel for one entry in a vehicle comparison."""
    if spec.preset_key:
        if spec.load_type == "tracked":
            preset = vehicle_presets.TRACKED_PRESETS.get(spec.preset_key)
            if preset is None:
                raise ValueError(f"Unknown tracked-machine preset {spec.preset_key!r}.")
            return tracked_machine(
                weight_kn=preset.weight_kn, track_length_m=preset.track_length_m,
                track_width_m=preset.track_width_m, gauge_m=preset.gauge_m,
                orientation=spec.orientation,
            )
        if spec.load_type == "truck":
            preset = vehicle_presets.TRUCK_PRESETS.get(spec.preset_key)
            if preset is None:
                raise ValueError(f"Unknown truck preset {spec.preset_key!r}.")
            return multi_axle_vehicle(
                axles=preset.axles, axle_width_m=preset.axle_width_m,
                orientation=spec.orientation,
            )
        raise ValueError(f"{spec.load_type!r} has no presets.")

    if spec.load_type == "tracked":
        if spec.tracked is None:
            raise ValueError("Tracked machine details are required.")
        return tracked_machine(
            weight_kn=spec.tracked.weight_kn,
            track_length_m=_m(spec.tracked.track_length, "track length"),
            track_width_m=_m(spec.tracked.track_width, "track width"),
            gauge_m=_m(spec.tracked.gauge, "track gauge"),
            orientation=spec.orientation,
        )
    if spec.load_type == "wheels":
        if spec.wheels is None:
            raise ValueError("Wheel group details are required.")
        w = spec.wheels
        return wheel_group(
            wheel_load_kn=w.wheel_load_kn,
            patch_along_travel_m=_m(w.patch_along_travel, "contact patch along travel"),
            patch_across_travel_m=_m(w.patch_across_travel, "contact patch across travel"),
            axle_width_m=_m(w.axle_width, "axle width"),
            orientation=spec.orientation,
            dual_spacing_m=_m(w.dual_spacing, "dual spacing"),
            axle_count=w.axle_count,
            axle_spacing_m=_m(w.axle_spacing, "axle spacing"),
        )
    if spec.load_type == "truck":
        if not spec.truck_axles:
            raise ValueError("A truck needs at least one axle.")
        return multi_axle_vehicle(
            axles=[_axle_spec(a) for a in spec.truck_axles],
            axle_width_m=_m(spec.truck_axle_width, "axle (track) width"),
            orientation=spec.orientation,
        )
    raise ValueError(f"Unknown load_type {spec.load_type!r}.")


@router.post("/vehicle-comparison", response_model=VehicleComparisonResponseOut)
def vehicle_comparison(payload: VehicleComparisonRequestIn) -> VehicleComparisonResponseOut:
    """Worst-case crown surcharge for several vehicles on one site.

    One lane, one vehicle at a time - this sweeps each vehicle across the
    pipe independently and reports its own worst position; it does not model
    two vehicles present at once.
    """
    try:
        cover_m = _m(payload.cover, "depth of cover")
        pipe_od_m = _m(payload.pipe_od, "pipe outside diameter")
    except ValueError as exc:
        return VehicleComparisonResponseOut(ok=False, error=str(exc))

    dla, _ = _dla(payload.dla_mode, payload.dla, cover_m)
    factor, source, verified = SPREAD_PRESETS[payload.spread_preset]
    if payload.spread_preset == "custom":
        factor = payload.spread_factor
    elif payload.spread_preset == "none":
        factor = 0.0

    results: list[dict] = []
    for i, spec in enumerate(payload.vehicles):
        label = spec.label or f"Vehicle {i + 1}"
        try:
            load = _load_for_vehicle_spec(spec)
            r = analyse(PipeSurchargeRequest(
                load=load, cover_m=cover_m, pipe_od_m=pipe_od_m,
                dla=dla, spread_factor=factor, spread_factor_source=source,
                spread_factor_verified=verified,
                soil_unit_weight_kn_m3=payload.soil_unit_weight_kn_m3,
                poisson_ratio=payload.poisson_ratio, with_profiles=False,
            ))
            results.append({
                "ok": True, "label": label, "load_type": spec.load_type,
                "orientation": spec.orientation, "description": r.load_description,
                "total_load_kn": round(r.total_load_kn, 3),
                "live_pressure_kpa": round(r.live_pressure_kpa, 3),
                "worst_offset_m": round(r.worst_offset_m, 3),
                "worst_offset_pressure_kpa": round(r.worst_offset_pressure_kpa, 3),
            })
        except (ValueError, KeyError) as exc:
            results.append({
                "ok": False, "error": str(exc), "label": label,
                "load_type": spec.load_type, "orientation": spec.orientation,
            })

    return VehicleComparisonResponseOut(ok=True, results=results)


@router.post("/pipe-surcharge", response_model=SurchargeResponseOut)
def pipe_surcharge(payload: SurchargeRequestIn) -> SurchargeResponseOut:
    """Crown surcharge from surface plant.

    Input problems come back as ``ok: false`` with a message rather than an
    HTTP error, so the live drawing can hold its last good state while the
    engineer is mid-keystroke.
    """
    try:
        load = _build_load(payload)
        cover_m = _m(payload.cover, "depth of cover")
        pipe_od_m = _m(payload.pipe_od, "pipe outside diameter")
        offset_m = _m(payload.machine_offset, "machine offset")

        dla, dla_basis = _dla(payload.dla_mode, payload.dla, cover_m)

        factor, source, verified = SPREAD_PRESETS[payload.spread_preset]
        if payload.spread_preset == "custom":
            factor = payload.spread_factor
        elif payload.spread_preset == "none":
            factor = 0.0

        result = analyse(PipeSurchargeRequest(
            load=load,
            cover_m=cover_m,
            pipe_od_m=pipe_od_m,
            machine_offset_m=offset_m,
            dla=dla,
            spread_factor=factor,
            spread_factor_source=source,
            spread_factor_verified=verified,
            soil_unit_weight_kn_m3=payload.soil_unit_weight_kn_m3,
            poisson_ratio=payload.poisson_ratio,
        ))

        # The same machine turned through 90 degrees, for comparison. Only the
        # headline numbers are needed, so the sweeps and section grid are off.
        other = "along" if payload.orientation == "across" else "across"
        alternate = analyse(PipeSurchargeRequest(
            load=_build_load(payload, other),
            cover_m=cover_m,
            pipe_od_m=pipe_od_m,
            machine_offset_m=offset_m,
            dla=dla,
            spread_factor=factor,
            spread_factor_source=source,
            spread_factor_verified=verified,
            soil_unit_weight_kn_m3=payload.soil_unit_weight_kn_m3,
            poisson_ratio=payload.poisson_ratio,
            with_profiles=False,
        ))
        by_orientation = {payload.orientation: result, other: alternate}
    except (ValueError, KeyError) as exc:
        return SurchargeResponseOut(ok=False, error=str(exc))

    html = soil_report.render(
        result,
        project=payload.project,
        member=payload.member,
        engineer=payload.engineer,
        orientation=payload.orientation,
        dla_basis=dla_basis,
        soil_unit_weight_kn_m3=payload.soil_unit_weight_kn_m3,
        poisson_ratio=payload.poisson_ratio,
    )

    return SurchargeResponseOut(
        ok=True,
        cover_m=round(result.cover_m, 4),
        pipe_od_m=round(result.pipe_od_m, 4),
        machine_offset_m=round(result.machine_offset_m, 4),
        load_description=result.load_description,
        total_load_kn=round(result.total_load_kn, 3),
        dla=round(result.dla, 4),
        dla_basis=dla_basis,
        methods=[
            {
                "key": m.key, "name": m.name,
                "pressure_kpa": round(m.pressure_kpa, 3),
                "basis": m.basis, "verified": m.verified, "note": m.note,
                "formula": m.formula, "substitution": m.substitution,
                "terms_sum_to_total": m.terms_sum_to_total,
                "terms": [
                    {"label": t.label, "detail": t.detail,
                     "value_kpa": round(t.value_kpa, 3)}
                    for t in m.terms
                ],
            }
            for m in result.methods
        ],
        live_pressure_kpa=round(result.live_pressure_kpa, 3),
        average_over_pipe_kpa=round(result.average_over_pipe_kpa, 3),
        load_per_m_kn_m=round(result.load_per_m_kn_m, 3),
        worst_offset_m=round(result.worst_offset_m, 3),
        worst_offset_pressure_kpa=round(result.worst_offset_pressure_kpa, 3),
        offset_is_worst=result.offset_is_worst,
        soil_pressure_kpa=round(result.soil_pressure_kpa, 3),
        live_to_dead_ratio=round(result.live_to_dead_ratio, 4),
        patches=[
            {
                "label": p.label, "x_m": round(p.x_m, 4), "y_m": round(p.y_m, 4),
                "width_x_m": round(p.width_x_m, 4),
                "length_y_m": round(p.length_y_m, 4),
                "total_kn": round(p.total_kn, 3),
                "pressure_kpa": round(p.pressure_kpa, 2),
            }
            for p in load.patches
        ],
        points=[
            {"label": p.label, "x_m": round(p.x_m, 4), "y_m": round(p.y_m, 4),
             "load_kn": round(p.load_kn, 3)}
            for p in load.points
        ],
        depth_profile=result.depth_profile,
        bulb=result.bulb or {},
        crown_plan=result.crown_plan or {},
        orientations=[
            {
                "orientation": key,
                "label": ("Crossing the pipe" if key == "across"
                          else "Tracking along the pipe"),
                "is_current": key == payload.orientation,
                "pressure_at_offset_kpa": round(r.live_pressure_kpa, 3),
                "worst_offset_m": round(r.worst_offset_m, 3),
                "worst_pressure_kpa": round(r.worst_offset_pressure_kpa, 3),
            }
            for key, r in (
                ("across", by_orientation["across"]),
                ("along", by_orientation["along"]),
            )
        ],
        offset_profile=[
            {"offset_m": p["offset_m"], "pressure_kpa": p["pressure_kpa"]}
            for p in result.offset_profile
        ],
        warnings=result.warnings,
        report_html=html,
    )
