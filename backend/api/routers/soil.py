import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.schemas.soil import (
    AxleConfigIn,
    AxleConfigOut,
    AxleConfigSummary,
    AxleSpecIn,
    SavedVehicleIn,
    SavedVehicleOut,
    SavedVehicleSummary,
    SoilExportIn,
    SoilExportOut,
    SurchargeRequestIn,
    SurchargeResponseOut,
    VehicleComparisonRequestIn,
    VehicleComparisonResponseOut,
    VehicleSpecIn,
)

from core.report import soil_report
from core.soil import vehicles as vehicle_presets
from core.soil import export as soil_export
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

REPO_ROOT = Path(__file__).resolve().parents[3]
AXLE_CONFIG_DIR = Path(__file__).resolve().parents[2] / "projects" / "axles"
EXPORT_DIR = Path(__file__).resolve().parents[2] / "projects" / "exports"
_SAFE_SLUG = re.compile(r"[^a-z0-9]+")
_MAX_AXLE_CONFIGS = 200


def _export_path(slug: str, suffix: str) -> Path:
    """Resolve an export filename, refusing anything that escapes the folder."""
    path = (EXPORT_DIR / f"{slug}.{suffix}").resolve()
    if path.parent != EXPORT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid export name.")
    return path


def _repo_relative(path: Path) -> str:
    """Path as an agent working in this workspace would write it."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _axle_slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = _SAFE_SLUG.sub("-", ascii_name.lower()).strip("-")
    return slug or "axle-config"


def _axle_path(config_id: str) -> Path:
    if config_id != _axle_slug(config_id):
        raise HTTPException(status_code=400, detail="Invalid axle config id.")
    path = (AXLE_CONFIG_DIR / f"{config_id}.json").resolve()
    if path.parent != AXLE_CONFIG_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid axle config id.")
    return path


def _axle_summary(data: dict, config_id: str) -> dict:
    axles = data.get("truck_axles", [])
    total_load = sum(float(a.get("load_kn", 0)) for a in axles)
    return {
        "id": config_id,
        "name": data.get("name", config_id),
        "saved_at": data.get("saved_at", ""),
        "axle_count": len(axles),
        "total_load_kn": round(total_load, 2),
    }


@router.get("/axle-configs", response_model=list[AxleConfigSummary])
def list_axle_configs() -> list[dict]:
    if not AXLE_CONFIG_DIR.exists():
        return []
    out = []
    for path in AXLE_CONFIG_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(_axle_summary(data, path.stem))
    out.sort(key=lambda p: p["saved_at"], reverse=True)
    return out


@router.put("/axle-configs/{config_id}", response_model=AxleConfigSummary)
@router.post("/axle-configs", response_model=AxleConfigSummary)
def save_axle_config(config: AxleConfigIn, config_id: str | None = None) -> dict:
    AXLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cid = config_id or _axle_slug(config.name)
    path = _axle_path(cid)

    if not path.exists() and len(list(AXLE_CONFIG_DIR.glob("*.json"))) >= _MAX_AXLE_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Axle configuration limit of {_MAX_AXLE_CONFIGS} reached; delete some first.",
        )

    record = {
        "name": config.name,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "truck_axles": [a.model_dump(mode="json") for a in config.truck_axles],
        "truck_axle_width": config.truck_axle_width,
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return _axle_summary(record, cid)


@router.get("/axle-configs/{config_id}", response_model=AxleConfigOut)
def load_axle_config(config_id: str) -> dict:
    path = _axle_path(config_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No axle configuration named {config_id!r}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Axle config file unreadable: {exc}") from exc
    return {
        **_axle_summary(data, config_id),
        "truck_axles": data.get("truck_axles", []),
        "truck_axle_width": data.get("truck_axle_width", "1.8 m"),
    }


@router.delete("/axle-configs/{config_id}")
def delete_axle_config(config_id: str) -> dict[str, str]:
    path = _axle_path(config_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No axle configuration named {config_id!r}.")
    path.unlink()
    return {"status": "deleted", "id": config_id}


# --- Saved Custom Vehicles ---

SAVED_VEHICLE_DIR = Path(__file__).resolve().parents[2] / "projects" / "vehicles"
_MAX_SAVED_VEHICLES = 300


def _vehicle_slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = _SAFE_SLUG.sub("-", ascii_name.lower()).strip("-")
    return slug or "saved-vehicle"


def _vehicle_path(vehicle_id: str) -> Path:
    if vehicle_id != _vehicle_slug(vehicle_id):
        raise HTTPException(status_code=400, detail="Invalid vehicle id.")
    path = (SAVED_VEHICLE_DIR / f"{vehicle_id}.json").resolve()
    if path.parent != SAVED_VEHICLE_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid vehicle id.")
    return path


def _vehicle_summary(data: dict, vehicle_id: str) -> dict:
    load_type = data.get("load_type", "tracked")
    total_load = 0.0
    if load_type == "tracked" and data.get("tracked"):
        total_load = float(data["tracked"].get("weight_kn", 0))
    elif load_type == "wheels" and data.get("wheels"):
        w = data["wheels"]
        # Count the duals. _build_load reads a non-zero dual spacing as two
        # tyres per side and loads the axle at wheel_load * 2 * tires_per_side;
        # summarising at wheel_load * 2 reported a dual-tyre vehicle at half its
        # real load in the picker - a wrong number on the label, in the feature
        # whose whole job is confirming the load is right.
        # dual_spacing is a free-text length ("330", "0.33 m"), and this dict
        # came off disk, so it may be anything. An unreadable value falls back
        # to singles rather than failing the whole listing.
        try:
            dual_spacing_m = _m(w.get("dual_spacing", "0"), "dual spacing")
        except (ValueError, TypeError):
            dual_spacing_m = 0.0
        tires_per_side = 2 if dual_spacing_m > 0 else 1
        total_load = (
            float(w.get("wheel_load_kn", 0))
            * 2.0 * tires_per_side * int(w.get("axle_count", 1))
        )
    elif load_type == "truck":
        total_load = sum(float(a.get("load_kn", 0)) for a in data.get("truck_axles", []))

    return {
        "id": vehicle_id,
        "name": data.get("name", vehicle_id),
        "saved_at": data.get("saved_at", ""),
        "load_type": load_type,
        "total_load_kn": round(total_load, 2),
    }


@router.get("/vehicles", response_model=list[SavedVehicleSummary])
def list_saved_vehicles() -> list[dict]:
    if not SAVED_VEHICLE_DIR.exists():
        return []
    out = []
    for path in SAVED_VEHICLE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(_vehicle_summary(data, path.stem))
    out.sort(key=lambda p: p["saved_at"], reverse=True)
    return out


@router.put("/vehicles/{vehicle_id}", response_model=SavedVehicleSummary)
@router.post("/vehicles", response_model=SavedVehicleSummary)
def save_vehicle(vehicle: SavedVehicleIn, vehicle_id: str | None = None) -> dict:
    SAVED_VEHICLE_DIR.mkdir(parents=True, exist_ok=True)
    vid = vehicle_id or _vehicle_slug(vehicle.name)
    path = _vehicle_path(vid)

    if not path.exists() and len(list(SAVED_VEHICLE_DIR.glob("*.json"))) >= _MAX_SAVED_VEHICLES:
        raise HTTPException(
            status_code=400,
            detail=f"Vehicle limit of {_MAX_SAVED_VEHICLES} reached; delete some first.",
        )

    record = {
        "name": vehicle.name,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "load_type": vehicle.load_type,
        "tracked": vehicle.tracked.model_dump(mode="json") if vehicle.tracked else None,
        "wheels": vehicle.wheels.model_dump(mode="json") if vehicle.wheels else None,
        "truck_axles": [a.model_dump(mode="json") for a in vehicle.truck_axles],
        "truck_axle_width": vehicle.truck_axle_width,
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return _vehicle_summary(record, vid)


@router.get("/vehicles/{vehicle_id}", response_model=SavedVehicleOut)
def load_saved_vehicle(vehicle_id: str) -> dict:
    path = _vehicle_path(vehicle_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No vehicle named {vehicle_id!r}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Vehicle file unreadable: {exc}") from exc
    return {
        **_vehicle_summary(data, vehicle_id),
        "load_type": data.get("load_type", "tracked"),
        "tracked": data.get("tracked"),
        "wheels": data.get("wheels"),
        "truck_axles": data.get("truck_axles", []),
        "truck_axle_width": data.get("truck_axle_width", "1.8 m"),
    }


@router.delete("/vehicles/{vehicle_id}")
def delete_saved_vehicle(vehicle_id: str) -> dict[str, str]:
    path = _vehicle_path(vehicle_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No vehicle named {vehicle_id!r}.")
    path.unlink()
    return {"status": "deleted", "id": vehicle_id}




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


# Every ground-contact patch is labelled "{axle line} {side}[ dual {n}]" by
# multi_axle_vehicle/tracked_machine/wheel_group - e.g. "Tracks left",
# "Axle 1 right dual 2", "Steering left". Stripping that fixed suffix recovers
# the axle-line name reliably, including for axle labels that contain spaces
# ("Front Axle") or no leading "Axle" word at all ("Steering", "3rd").
_SIDE_SUFFIX = re.compile(r"\s+(left|right)(\s+dual\s+\d+)?$", re.IGNORECASE)


def _axle_line_name(patch_label: str) -> str:
    return _SIDE_SUFFIX.sub("", patch_label) or patch_label


def _group_axles(patches: list[Patch], orientation: str) -> list[dict]:
    """Group ground-contact patches into per-axle-line rows: load, tyre count,
    contact dimensions, and centre-to-centre spacing along the direction of
    travel, ordered from the first axle to the last.

    A patch's ``width_x_m``/``length_y_m`` swap physical meaning with
    orientation (``_oriented_dims`` maps the along-travel/across-travel pair
    onto x/y differently depending on which way the machine is heading), so
    they are mapped back here to the orientation-independent, physically
    meaningful pair every reader actually wants: tyre/track width and contact
    length along travel.
    """
    # Position along the direction of travel: x when crossing, y when tracking.
    def travel_pos(p: Patch) -> float:
        return p.x_m if orientation == "across" else p.y_m

    # Key on label AND travel position, not label alone. Axle labels are not
    # unique - the wheels builder emits "Axle 1", "Axle 2", ..., but a saved or
    # hand-entered vehicle can repeat a label across axles, and grouping on the
    # label alone silently welds those axles into one row: their loads add up,
    # tires_per_side becomes the patch count over two, and the spacing between
    # them disappears, erasing the wheelbase. Two patches at the same travel
    # station genuinely are one axle line; two at different stations never are.
    groups: dict[tuple[str, float], list[Patch]] = {}
    for p in patches:
        groups.setdefault((_axle_line_name(p.label), round(travel_pos(p), 6)), []).append(p)

    def contact_length_and_width(p: Patch) -> tuple[float, float]:
        if orientation == "across":
            return p.width_x_m, p.length_y_m  # (along travel, across travel)
        return p.length_y_m, p.width_x_m

    rows = []
    for (name, _station), group in groups.items():
        contact_length_m, tire_width_m = contact_length_and_width(group[0])
        rows.append({
            "label": name,
            "load_kn": sum(p.total_kn for p in group),
            "tires_per_side": max(1, len(group) // 2),
            "tire_width_m": tire_width_m,
            "contact_length_m": contact_length_m,
            "position": sum(travel_pos(p) for p in group) / len(group),
        })
    rows.sort(key=lambda r: r["position"])

    out = []
    previous_pos = None
    for r in rows:
        spacing = 0.0 if previous_pos is None else abs(r["position"] - previous_pos)
        previous_pos = r["position"]
        out.append({
            "label": r["label"], "load_kn": round(r["load_kn"], 2),
            "tires_per_side": r["tires_per_side"],
            "width_m": round(r["tire_width_m"], 4),
            "length_m": round(r["contact_length_m"], 4),
            "spacing_m": round(spacing, 4),
        })
    return out


def _measure_axle_width(patches: list[Patch], orientation: str) -> float:
    """The real left/right track or wheel gauge, read back from the built
    geometry rather than trusted from ``spec.truck_axle_width`` - a preset
    vehicle bypasses that field entirely and builds its own gauge, so trusting
    the request field there silently reports the wrong number.

    Gauge is centre-of-left-wheel-line to centre-of-right-wheel-line. The outer
    span of all patches is NOT that: on a dual-tyre axle the outermost tyres sit
    half a dual spacing outboard of their wheel lines on each side, so the span
    over-reports the gauge by exactly the dual spacing (Western Star: 2.730 m
    measured against a true 2.400 m). Averaging each side's tyres back onto its
    wheel line removes that, and is a no-op for single tyres.

    Measured per axle line, because dual spacing is a per-axle property - the
    Western Star runs singles on axles 1-2 and duals on 3-4.
    """
    if not patches:
        return 0.0
    cross = (lambda p: p.y_m) if orientation == "across" else (lambda p: p.x_m)
    travel = (lambda p: p.x_m) if orientation == "across" else (lambda p: p.y_m)

    stations: dict[float, list[Patch]] = {}
    for p in patches:
        stations.setdefault(round(travel(p), 6), []).append(p)

    gauges = []
    for group in stations.values():
        values = [cross(p) for p in group]
        mid = sum(values) / len(values)
        left = [v for v in values if v < mid]
        right = [v for v in values if v > mid]
        if not left or not right:
            # A single track/tyre straddling the centreline has no gauge to
            # measure; fall back to the outer span rather than inventing one.
            gauges.append(max(values) - min(values))
        else:
            gauges.append(sum(right) / len(right) - sum(left) / len(left))
    return max(gauges) if gauges else 0.0


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


@dataclass(frozen=True)
class ResolvedVehicle:
    """A vehicle with every dimension already parsed into metres.

    ``_build_load`` used to construct these ``AxleSpec`` objects, hand them to
    ``multi_axle_vehicle`` and then throw the list away, leaving downstream code
    to reverse-engineer the machine out of ``Patch`` labels and coordinates.
    That round trip is lossy in ways that matter:

    * ``tire_length_m is None`` records that the contact length was BACKED OUT
      of an assumed inflation pressure. Patch geometry cannot tell you whether a
      dimension was stated or derived, and the CL-625 preset depends on that
      distinction.
    * ``dual_spacing_m`` is exact here, and known to be inapplicable when
      ``tires_per_side == 1``. Measured from patches it is a float difference,
      and for a single tyre there is simply nothing to measure.
    * Axles are identified by index. Grouping patches by label silently merges
      two axles that share a name - see the regression test.

    ``axles`` is empty and ``axle_width_m`` zero for ``load_type == "custom"``,
    which is arbitrary rectangles rather than a vehicle.
    """

    load: LoadModel
    axles: list[AxleSpec]
    axle_width_m: float
    load_type: str
    orientation: str


def _resolve_vehicle(
    payload: SurchargeRequestIn, orientation: str | None = None
) -> ResolvedVehicle:
    orientation = orientation or payload.orientation

    # --- Tracked: convert to 1-axle vehicle ---
    if payload.load_type == "tracked":
        t = payload.tracked
        if t is None:
            raise ValueError("Tracked machine details are required.")
        track_length_m = _m(t.track_length, "track length")
        track_width_m = _m(t.track_width, "track width")
        gauge_m = _m(t.gauge, "track gauge")
        axles = [AxleSpec(
            "Tracks", t.weight_kn, tires_per_side=1,
            tire_width_m=track_width_m, tire_length_m=track_length_m,
        )]
        return ResolvedVehicle(
            multi_axle_vehicle(axles=axles, axle_width_m=gauge_m, orientation=orientation),
            axles, gauge_m, payload.load_type, orientation,
        )

    # --- Wheels: convert to N identical axles ---
    if payload.load_type == "wheels":
        w = payload.wheels
        if w is None:
            raise ValueError("Wheel group details are required.")
        patch_along = _m(w.patch_along_travel, "contact patch along travel")
        patch_across = _m(w.patch_across_travel, "contact patch across travel")
        axle_width_m = _m(w.axle_width, "axle width")
        dual_spacing_m = _m(w.dual_spacing, "dual spacing")
        axle_spacing_m = _m(w.axle_spacing, "axle spacing")
        tires_per_side = 2 if dual_spacing_m > 0 else 1
        axle_load = w.wheel_load_kn * 2 * tires_per_side
        axles = []
        for i in range(w.axle_count):
            axles.append(AxleSpec(
                f"Axle {i + 1}", axle_load, tires_per_side=tires_per_side,
                tire_width_m=patch_across, tire_length_m=patch_along,
                dual_spacing_m=dual_spacing_m,
                spacing_from_previous_m=axle_spacing_m if i > 0 else 0.0,
            ))
        return ResolvedVehicle(
            multi_axle_vehicle(axles=axles, axle_width_m=axle_width_m,
                               orientation=orientation),
            axles, axle_width_m, payload.load_type, orientation,
        )

    # --- Truck / multi-axle: pass through directly ---
    if payload.load_type == "truck":
        if not payload.truck_axles:
            raise ValueError("A vehicle needs at least one axle.")
        axles = [_axle_spec(a) for a in payload.truck_axles]
        axle_width_m = _m(payload.truck_axle_width, "axle (track) width")
        return ResolvedVehicle(
            multi_axle_vehicle(axles=axles, axle_width_m=axle_width_m,
                               orientation=orientation),
            axles, axle_width_m, payload.load_type, orientation,
        )

    # --- Custom patches: not a vehicle ---
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
    return ResolvedVehicle(
        custom_load(patches, points), [], 0.0, payload.load_type, orientation,
    )


def _build_load(payload: SurchargeRequestIn, orientation: str | None = None) -> LoadModel:
    return _resolve_vehicle(payload, orientation).load


def _vehicle_geometry(resolved: ResolvedVehicle, preset=None) -> dict | None:
    """The machine in its OWN frame, for the check-your-input diagram.

    Deliberately independent of which way the vehicle crosses the pipe: u runs
    along travel (+u forward), v across it (+v to the right), with u = 0 at the
    wheelbase midpoint to match how ``multi_axle_vehicle`` centres the model.
    That is what makes the drawing a check of the vehicle rather than a
    restatement of the analysis.

    ``None`` for custom rectangles - those are not a vehicle and inventing one
    from arbitrary patches would be a fiction.

    Note the ``null`` versus ``0.0`` distinction: a dimension that does not
    exist (spacing before the first axle, dual spacing on a single tyre) is
    ``None`` so the drawing knows not to draw it. ``0.0`` would render as a
    real zero-length dimension line.
    """
    if not resolved.axles:
        return None

    gauge_m = resolved.axle_width_m

    # load_type alone is not enough. The pipe surcharge form normalises every
    # vehicle - excavators included - into a one-axle "truck" before sending
    # it, so a CAT 320 arrives as load_type "truck" and would be drawn with
    # road wheels and labelled "per tyre". The preset registry is the
    # authoritative statement of what the machine actually runs on.
    is_tracked = (
        resolved.load_type == "tracked"
        or (preset is not None and preset.key in vehicle_presets.TRACKED_PRESETS)
    )

    positions: list[float] = [0.0]
    for axle in resolved.axles[1:]:
        positions.append(positions[-1] + axle.spacing_from_previous_m)
    wheelbase_m = positions[-1]
    mid = wheelbase_m / 2.0

    axles_out: list[dict] = []
    contacts_out: list[dict] = []
    max_overall_width = 0.0

    for index, (axle, pos) in enumerate(zip(resolved.axles, positions)):
        length_m = axle.contact_length_m()
        wheel_load = axle.wheel_load_kn()
        area = axle.tire_width_m * length_m
        dual = axle.dual_spacing_m if axle.tires_per_side == 2 else None

        axles_out.append({
            "index": index,
            "label": axle.label,
            "load_kn": round(axle.load_kn, 3),
            "wheel_load_kn": round(wheel_load, 3),
            "tires_per_side": axle.tires_per_side,
            "tire_width_m": round(axle.tire_width_m, 4),
            "contact_length_m": round(length_m, 4),
            # True when the length was backed out of an assumed inflation
            # pressure rather than stated - an assumption, not a measurement.
            "contact_length_is_derived": axle.tire_length_m is None,
            "tire_pressure_kpa": axle.tire_pressure_kpa,
            "dual_spacing_m": round(dual, 4) if dual is not None else None,
            "spacing_from_previous_m": (
                None if index == 0 else round(axle.spacing_from_previous_m, 4)
            ),
            "position_u_m": round(pos, 4),
            "position_u_centred_m": round(pos - mid, 4),
            "contact_area_m2": round(area, 6),
            "axle_contact_area_m2": round(area * 2 * axle.tires_per_side, 6),
            "contact_pressure_kpa": round(wheel_load / area, 2) if area else 0.0,
        })

        tyre_offsets = (
            [0.0] if axle.tires_per_side == 1
            else [-axle.dual_spacing_m / 2.0, +axle.dual_spacing_m / 2.0]
        )
        for side, wheel_v in (("left", -gauge_m / 2.0), ("right", +gauge_m / 2.0)):
            for tyre_index, tv in enumerate(tyre_offsets, start=1):
                v = wheel_v + tv
                # Byte-identical to Patch.label from multi_axle_vehicle, so the
                # diagram can join against patches and Boussinesq term labels.
                suffix = "" if axle.tires_per_side == 1 else f" dual {tyre_index}"
                contacts_out.append({
                    "label": f"{axle.label} {side}{suffix}",
                    "axle_index": index,
                    "side": side,
                    "tyre_index": tyre_index,
                    "u_m": round(pos - mid, 4),
                    "v_m": round(v, 4),
                    "length_u_m": round(length_m, 4),
                    "width_v_m": round(axle.tire_width_m, 4),
                    "load_kn": round(wheel_load, 3),
                    "pressure_kpa": round(wheel_load / area, 2) if area else 0.0,
                })
                max_overall_width = max(max_overall_width, abs(v) * 2 + axle.tire_width_m)

    total_area = sum(a["axle_contact_area_m2"] for a in axles_out)
    total_load = sum(a["load_kn"] for a in axles_out)
    first_len = axles_out[0]["contact_length_m"]
    last_len = axles_out[-1]["contact_length_m"]

    return {
        "frame": "travel",
        "travel_axis_note": (
            "u along travel (+u forward), v across travel (+v right); "
            "u = 0 at the wheelbase midpoint on the vehicle centreline."
        ),
        "orientation": resolved.orientation,
        "plan_mapping": (
            "u -> x (across pipe), v -> y (along pipe)"
            if resolved.orientation == "across"
            else "v -> x (across pipe), u -> y (along pipe)"
        ),
        "load_type": resolved.load_type,
        "is_tracked": is_tracked,
        "contact_noun": "track" if is_tracked else "tyre",
        "axle_count": len(axles_out),
        "wheelbase_m": round(wheelbase_m, 4),
        "gauge_m": round(gauge_m, 4),
        "overall_width_m": round(max_overall_width, 4),
        "overall_length_m": round(wheelbase_m + first_len / 2 + last_len / 2, 4),
        "total_load_kn": round(total_load, 3),
        "contact_patch_count": len(contacts_out),
        "total_contact_area_m2": round(total_area, 6),
        "mean_contact_pressure_kpa": (
            round(total_load / total_area, 2) if total_area else 0.0
        ),
        "axles": axles_out,
        "contacts": contacts_out,
    }


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
    """Unified vehicle presets — all vehicles expressed as axle configurations.

    Every value here is a transcription (marked ``verified: false``, with an
    ``assumptions`` list for anything the source sheet did not give). The
    frontend uses this to pre-fill the axle editor.
    """
    vehicles = []
    for p in vehicle_presets.VEHICLE_PRESETS.values():
        vehicles.append({
            "key": p.key,
            "name": p.name,
            "category": p.category,
            "axle_width_m": round(p.axle_width_m, 4),
            "total_load_kn": round(p.total_load_kn, 2),
            "source": p.source,
            "verified": p.verified,
            "assumptions": p.assumptions,
            "axles": [
                {
                    "label": a.label,
                    "load_kn": round(a.load_kn, 3),
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
        })
    tracked = []
    trucks = []
    for p in vehicle_presets.VEHICLE_PRESETS.values():
        if p.category == "excavator":
            tracked.append({
                "key": p.key, "name": p.name, "weight_kn": round(p.weight_kn, 2),
                "track_length_m": round(p.track_length_m, 4),
                "track_width_m": round(p.track_width_m, 4),
                "gauge_m": round(p.gauge_m, 4),
                "source": p.source, "verified": p.verified,
                "assumptions": p.assumptions,
            })
        else:
            trucks.append({
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
            })
    return {"vehicles": vehicles, "tracked": tracked, "trucks": trucks}


def _load_for_vehicle_spec(spec: VehicleSpecIn) -> LoadModel:
    """Build a LoadModel for one entry in a vehicle comparison."""
    if spec.preset_key:
        preset = vehicle_presets.VEHICLE_PRESETS.get(spec.preset_key)
        if preset is None:
            raise ValueError(f"Unknown vehicle preset {spec.preset_key!r}.")
        return multi_axle_vehicle(
            axles=preset.axles, axle_width_m=preset.axle_width_m,
            orientation=spec.orientation,
        )

    if spec.load_type == "tracked":
        if spec.tracked is None:
            raise ValueError("Tracked machine details are required.")
        track_length_m = _m(spec.tracked.track_length, "track length")
        track_width_m = _m(spec.tracked.track_width, "track width")
        gauge_m = _m(spec.tracked.gauge, "track gauge")
        axle = AxleSpec(
            "Tracks", spec.tracked.weight_kn, tires_per_side=1,
            tire_width_m=track_width_m, tire_length_m=track_length_m,
        )
        return multi_axle_vehicle(
            axles=[axle], axle_width_m=gauge_m, orientation=spec.orientation,
        )
    if spec.load_type == "wheels":
        if spec.wheels is None:
            raise ValueError("Wheel group details are required.")
        w = spec.wheels
        patch_along = _m(w.patch_along_travel, "contact patch along travel")
        patch_across = _m(w.patch_across_travel, "contact patch across travel")
        axle_width_m = _m(w.axle_width, "axle width")
        dual_spacing_m = _m(w.dual_spacing, "dual spacing")
        axle_spacing_m = _m(w.axle_spacing, "axle spacing")
        tires_per_side = 2 if dual_spacing_m > 0 else 1
        axle_load = w.wheel_load_kn * 2 * tires_per_side
        axles = []
        for i in range(w.axle_count):
            axles.append(AxleSpec(
                f"Axle {i + 1}", axle_load, tires_per_side=tires_per_side,
                tire_width_m=patch_across, tire_length_m=patch_along,
                dual_spacing_m=dual_spacing_m,
                spacing_from_previous_m=axle_spacing_m if i > 0 else 0.0,
            ))
        return multi_axle_vehicle(
            axles=axles, axle_width_m=axle_width_m, orientation=spec.orientation,
        )
    if spec.load_type == "truck":
        if not spec.truck_axles:
            raise ValueError("A vehicle needs at least one axle.")
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

            axles_out = _group_axles(load.patches, spec.orientation)

            # Which axle line is critical, from Boussinesq's own term contributions.
            critical_axle = ""
            critical_contrib = 0.0
            bouss_method = next((m for m in r.methods if m.key == "boussinesq"), None)
            if bouss_method and bouss_method.terms:
                axle_contribs: dict[str, float] = {}
                for t in bouss_method.terms:
                    name = _axle_line_name(t.label)
                    axle_contribs[name] = axle_contribs.get(name, 0.0) + t.value_kpa
                best_ax, best_val = max(axle_contribs.items(), key=lambda x: x[1])
                best_row = next((a for a in axles_out if a["label"] == best_ax), None)
                best_load = best_row["load_kn"] if best_row else 0.0
                critical_axle = f"{best_ax} ({best_load:.0f} kN)" if best_load else best_ax
                critical_contrib = round(best_val, 2)

            if len(axles_out) == 1 and axles_out[0]["label"] == "Tracks":
                a = axles_out[0]
                dims_summary = f"2 tracks: {a['width_m']:.2f} x {a['length_m']:.2f} m contact"
            else:
                dims_summary = f"{len(axles_out)} axle line(s), {len(load.patches)} contact patch(es)"

            results.append({
                "ok": True,
                "label": label,
                "load_type": spec.load_type,
                "orientation": spec.orientation,
                "description": r.load_description,
                "total_load_kn": round(r.total_load_kn, 3),
                "live_pressure_kpa": round(r.live_pressure_kpa, 3),
                "worst_offset_m": round(r.worst_offset_m, 3),
                "worst_offset_pressure_kpa": round(r.worst_offset_pressure_kpa, 3),
                "axle_count": len(axles_out),
                "axle_width_m": round(_measure_axle_width(load.patches, spec.orientation), 3),
                "dimensions_summary": dims_summary,
                "critical_axle": critical_axle,
                "critical_axle_contribution_kpa": critical_contrib,
                "axles": axles_out,
            })
        except (ValueError, KeyError) as exc:
            results.append({
                "ok": False, "error": str(exc), "label": label,
                "load_type": spec.load_type, "orientation": spec.orientation,
            })

    return VehicleComparisonResponseOut(ok=True, results=results)


@router.post("/export", response_model=SoilExportOut)
def export_analysis(payload: SoilExportIn) -> SoilExportOut:
    """Write the analysis to the workspace as .md and .json, for an AI tool.

    Both files land in one action, from one builder, so the human-readable and
    machine-readable views cannot disagree. They are written INTO the repo
    (``backend/projects/exports/``, which is gitignored) so an agent reading
    the workspace picks them up without being handed a path.

    Re-runs the analysis rather than accepting numbers from the client: an
    export is a record, and a record assembled from whatever the browser last
    held is not one.
    """
    req = payload.payload
    try:
        resolved = _resolve_vehicle(req)
        cover_m = _m(req.cover, "depth of cover")
        pipe_od_m = _m(req.pipe_od, "pipe outside diameter")
        offset_m = _m(req.machine_offset, "machine offset")
        dla, _basis = _dla(req.dla_mode, req.dla, cover_m)

        factor, source, verified = SPREAD_PRESETS[req.spread_preset]
        if req.spread_preset == "custom":
            factor = req.spread_factor
        elif req.spread_preset == "none":
            factor = 0.0

        result = analyse(PipeSurchargeRequest(
            load=resolved.load,
            cover_m=cover_m,
            pipe_od_m=pipe_od_m,
            machine_offset_m=offset_m,
            dla=dla,
            spread_factor=factor,
            spread_factor_source=source,
            spread_factor_verified=verified,
            soil_unit_weight_kn_m3=req.soil_unit_weight_kn_m3,
            poisson_ratio=req.poisson_ratio,
            with_profiles=False,
        ))
    except (ValueError, KeyError) as exc:
        return SoilExportOut(ok=False, error=str(exc))

    preset = vehicle_presets.VEHICLE_PRESETS.get(req.vehicle_preset_key)

    data = soil_export.build_export(
        result=result,
        vehicle=_vehicle_geometry(resolved, preset),
        request_payload=req.model_dump(mode="json"),
        project=req.project,
        member=req.member,
        designer=req.engineer,
        soil_unit_weight_kn_m3=req.soil_unit_weight_kn_m3,
        poisson_ratio=req.poisson_ratio,
        preset_source=preset.source if preset else "",
        preset_verified=preset.verified if preset else None,
        preset_assumptions=list(preset.assumptions) if preset else None,
    )
    markdown = soil_export.render_markdown(data)

    slug = _axle_slug(payload.name)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _export_path(slug, "json")
    md_path = _export_path(slug, "md")
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    return SoilExportOut(
        ok=True,
        json_path=_repo_relative(json_path),
        markdown_path=_repo_relative(md_path),
        markdown=markdown,
        data=data,
    )


@router.post("/pipe-surcharge", response_model=SurchargeResponseOut)
def pipe_surcharge(payload: SurchargeRequestIn) -> SurchargeResponseOut:
    """Crown surcharge from surface plant.

    Input problems come back as ``ok: false`` with a message rather than an
    HTTP error, so the live drawing can hold its last good state while the
    engineer is mid-keystroke.
    """
    try:
        resolved = _resolve_vehicle(payload)
        load = resolved.load
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

    preset = vehicle_presets.VEHICLE_PRESETS.get(payload.vehicle_preset_key)
    geometry = _vehicle_geometry(resolved, preset)

    html = soil_report.render(
        result,
        project=payload.project,
        member=payload.member,
        engineer=payload.engineer,
        orientation=payload.orientation,
        dla_basis=dla_basis,
        soil_unit_weight_kn_m3=payload.soil_unit_weight_kn_m3,
        poisson_ratio=payload.poisson_ratio,
        vehicle=geometry,
        vehicle_source=preset.source if preset else "",
        vehicle_verified=preset.verified if preset else None,
        vehicle_assumptions=list(preset.assumptions) if preset else None,
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
        axles=_group_axles(load.patches, payload.orientation),
        vehicle=geometry,
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
