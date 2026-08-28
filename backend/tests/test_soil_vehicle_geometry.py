"""Vehicle geometry: the check-your-input block on the surcharge response.

This is the data behind the "did I enter this truck correctly?" drawing, so
these tests are mostly about it matching the source sheets exactly, and about
it being a property of the MACHINE rather than of the analysis - the same
vehicle turned through 90 degrees is the same vehicle.
"""

import pytest

from api.routers.soil import (
    _group_axles,
    _measure_axle_width,
    _resolve_vehicle,
    _vehicle_geometry,
    _vehicle_summary,
)
from api.schemas.soil import SurchargeRequestIn
from core.soil.loads import AxleSpec, multi_axle_vehicle
from core.soil.vehicles import VEHICLE_PRESETS


def geometry(preset_key: str, orientation: str = "across") -> dict:
    """Build the geometry block for a preset, the way the endpoint does."""
    preset = VEHICLE_PRESETS[preset_key]
    if preset.axles[0].label == "Tracks" and len(preset.axles) == 1:
        axle = preset.axles[0]
        payload = SurchargeRequestIn(
            load_type="tracked",
            orientation=orientation,
            tracked={
                "weight_kn": axle.load_kn,
                "track_length": f"{axle.contact_length_m()} m",
                "track_width": f"{axle.tire_width_m} m",
                "gauge": f"{preset.axle_width_m} m",
            },
        )
    else:
        payload = SurchargeRequestIn(
            load_type="truck",
            orientation=orientation,
            truck_axle_width=f"{preset.axle_width_m} m",
            truck_axles=[
                {
                    "label": a.label,
                    "load_kn": a.load_kn,
                    "tires_per_side": a.tires_per_side,
                    "tire_width": f"{a.tire_width_m} m",
                    "tire_length": f"{a.contact_length_m()} m",
                    "dual_spacing": f"{a.dual_spacing_m} m",
                    "spacing_from_previous": f"{a.spacing_from_previous_m} m",
                }
                for a in preset.axles
            ],
        )
    g = _vehicle_geometry(_resolve_vehicle(payload))
    assert g is not None
    return g


# --------------------------------------------------------------------------
# The geometry describes the machine, not the analysis
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["cl625", "western_star_4700sb", "cat_320"])
def test_geometry_is_identical_for_both_orientations(key):
    """Turning the machine 90 degrees changes where its wheels land relative
    to the pipe; it does not change the machine. If these ever diverge, the
    drawing has started restating the analysis instead of checking the input.
    """
    across = geometry(key, "across")
    along = geometry(key, "along")
    for field in ("wheelbase_m", "gauge_m", "total_load_kn", "axle_count",
                  "overall_width_m", "overall_length_m", "total_contact_area_m2"):
        assert across[field] == along[field], field
    assert across["axles"] == along["axles"]
    assert across["contacts"] == along["contacts"]


def test_orientation_is_still_reported_for_the_plan_mapping():
    """The frame is orientation-independent, but the consumer still needs to
    know which way to lay it down over the pipe."""
    assert geometry("cl625", "across")["plan_mapping"].startswith("u -> x")
    assert geometry("cl625", "along")["plan_mapping"].startswith("v -> x")


# --------------------------------------------------------------------------
# CL-625 - the sheet the user supplied
# --------------------------------------------------------------------------

def test_cl625_geometry_matches_the_source_sheet():
    g = geometry("cl625")
    assert g["axle_count"] == 5
    assert g["wheelbase_m"] == pytest.approx(18.0, abs=1e-6)
    assert g["gauge_m"] == pytest.approx(1.8)
    assert g["total_load_kn"] == pytest.approx(625.0)
    assert [a["load_kn"] for a in g["axles"]] == pytest.approx(
        [50.0, 140.0, 140.0, 175.0, 120.0])
    assert [a["spacing_from_previous_m"] for a in g["axles"][1:]] == pytest.approx(
        [3.6, 1.2, 6.6, 6.6])


def test_cl625_first_axle_has_no_spacing_and_no_dual():
    """None, not 0.0 - there is no dimension to draw, which the drawing must
    be able to tell apart from a dimension that happens to be zero."""
    first = geometry("cl625")["axles"][0]
    assert first["spacing_from_previous_m"] is None
    assert first["dual_spacing_m"] is None


def test_cl625_is_all_singles_with_ten_contact_patches():
    g = geometry("cl625")
    assert all(a["tires_per_side"] == 1 for a in g["axles"])
    assert g["contact_patch_count"] == 10
    assert all("dual" not in c["label"] for c in g["contacts"])


def test_cl625_axles_are_centred_on_the_wheelbase_midpoint():
    centred = [a["position_u_centred_m"] for a in geometry("cl625")["axles"]]
    assert centred[0] == pytest.approx(-9.0)
    assert centred[-1] == pytest.approx(9.0)
    assert sum(centred[0:1] + centred[-1:]) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Western Star - duals on the rear axles only
# --------------------------------------------------------------------------

def test_western_star_duals_are_on_the_rear_axles_only():
    """Dual spacing is a per-axle property. A single vehicle-level value would
    put duals under the steering axle."""
    axles = geometry("western_star_4700sb")["axles"]
    assert [a["tires_per_side"] for a in axles] == [1, 1, 2, 2]
    assert axles[0]["dual_spacing_m"] is None
    assert axles[1]["dual_spacing_m"] is None
    assert axles[2]["dual_spacing_m"] == pytest.approx(0.33)
    assert axles[3]["dual_spacing_m"] == pytest.approx(0.33)


def test_western_star_gauge_is_the_wheel_line_spacing_not_the_outer_span():
    """Regression: measuring the outer span of all patches over-reported this
    vehicle's gauge by exactly the dual spacing (2.730 against a true 2.400)."""
    assert geometry("western_star_4700sb")["gauge_m"] == pytest.approx(2.4)


def test_western_star_dual_tyres_straddle_their_wheel_line():
    g = geometry("western_star_4700sb")
    rear_right = [c for c in g["contacts"]
                  if c["axle_index"] == 3 and c["side"] == "right"]
    assert len(rear_right) == 2
    vs = sorted(c["v_m"] for c in rear_right)
    assert vs[1] - vs[0] == pytest.approx(0.33)
    assert (vs[0] + vs[1]) / 2 == pytest.approx(1.2)  # gauge / 2


def test_western_star_contact_labels_match_the_analysis_patch_labels():
    """The diagram must be joinable against the patches and the Boussinesq
    term breakdown, so the labels have to agree byte for byte."""
    preset = VEHICLE_PRESETS["western_star_4700sb"]
    model = multi_axle_vehicle(preset.axles, preset.axle_width_m)
    g = geometry("western_star_4700sb")
    assert {c["label"] for c in g["contacts"]} == {p.label for p in model.patches}


# --------------------------------------------------------------------------
# CAT 320 - the tracked special case
# --------------------------------------------------------------------------

def test_cat_320_is_one_axle_line_with_no_wheelbase():
    g = geometry("cat_320")
    assert g["axle_count"] == 1
    assert g["wheelbase_m"] == pytest.approx(0.0)
    assert g["gauge_m"] == pytest.approx(2.4079, abs=1e-3)
    assert g["is_tracked"] is True
    assert g["contact_noun"] == "track"
    assert g["contact_patch_count"] == 2


def test_tracked_overall_length_is_the_track_contact_length():
    """With no wheelbase to dimension, the drawing falls back to the track
    contact length - so that had better be what overall_length_m reports."""
    g = geometry("cat_320")
    assert g["overall_length_m"] == pytest.approx(g["axles"][0]["contact_length_m"])


# --------------------------------------------------------------------------
# Derived versus stated contact length
# --------------------------------------------------------------------------

def test_pressure_derived_contact_length_is_flagged_as_derived():
    """A length backed out of an assumed inflation pressure is an assumption.
    Reporting its contact pressure back without that flag would show the
    assumption to the user dressed up as a measurement."""
    payload = SurchargeRequestIn(
        load_type="truck",
        truck_axle_width="1.8 m",
        truck_axles=[{"label": "Axle", "load_kn": 140.0, "tire_width": "300",
                      "tire_pressure_kpa": 700.0}],
    )
    axle = _vehicle_geometry(_resolve_vehicle(payload))["axles"][0]
    assert axle["contact_length_is_derived"] is True
    assert axle["contact_pressure_kpa"] == pytest.approx(700.0, rel=1e-3)


def test_stated_contact_length_is_not_flagged_as_derived():
    assert all(not a["contact_length_is_derived"] for a in geometry("cl625")["axles"])


def test_tracked_preset_sent_as_a_truck_is_still_drawn_as_tracked():
    """Regression: the surcharge form normalises every vehicle into a one-axle
    "truck" before sending it, so an excavator arrived with load_type "truck"
    and was drawn with road wheels and labelled "per tyre". The preset registry
    is the authority on what the machine runs on, not the request's load_type.
    """
    preset = VEHICLE_PRESETS["cat_320"]
    axle = preset.axles[0]
    payload = SurchargeRequestIn(
        load_type="truck",  # exactly what the form sends
        truck_axle_width=f"{preset.axle_width_m} m",
        truck_axles=[{
            "label": axle.label, "load_kn": axle.load_kn,
            "tire_width": f"{axle.tire_width_m} m",
            "tire_length": f"{axle.contact_length_m()} m",
        }],
    )
    g = _vehicle_geometry(_resolve_vehicle(payload), preset)
    assert g["is_tracked"] is True
    assert g["contact_noun"] == "track"


def test_a_real_truck_preset_is_not_mistaken_for_tracked():
    preset = VEHICLE_PRESETS["cl625"]
    g = _vehicle_geometry(_resolve_vehicle(SurchargeRequestIn(
        load_type="truck",
        truck_axle_width=f"{preset.axle_width_m} m",
        truck_axles=[{"label": a.label, "load_kn": a.load_kn,
                      "tire_width": f"{a.tire_width_m} m",
                      "tire_length": f"{a.contact_length_m()} m",
                      "spacing_from_previous": f"{a.spacing_from_previous_m} m"}
                     for a in preset.axles],
    )), preset)
    assert g["is_tracked"] is False
    assert g["contact_noun"] == "tyre"


def test_custom_rectangles_have_no_vehicle_geometry():
    """Arbitrary rectangles are not a machine, and inventing axles for them
    would be a fiction."""
    payload = SurchargeRequestIn(
        load_type="custom",
        custom_patches=[{"label": "pad", "x": "0", "y": "0", "width_x": "1 m",
                         "length_y": "1 m", "total_kn": 50.0}],
    )
    assert _vehicle_geometry(_resolve_vehicle(payload)) is None


# --------------------------------------------------------------------------
# Regressions on the patch-derived helpers
# --------------------------------------------------------------------------

def test_group_axles_keeps_same_named_axles_apart():
    """Regression: grouping on the label alone welded three axles sharing the
    name "Axle" into a single 240 kN row with 3 tyres per side and no
    wheelbase - a physically impossible machine."""
    axles = [
        AxleSpec("Axle", 80.0, tire_width_m=0.3, tire_length_m=0.25),
        AxleSpec("Axle", 80.0, tire_width_m=0.3, tire_length_m=0.25,
                 spacing_from_previous_m=3.0),
        AxleSpec("Axle", 80.0, tire_width_m=0.3, tire_length_m=0.25,
                 spacing_from_previous_m=1.5),
    ]
    model = multi_axle_vehicle(axles, axle_width_m=1.8)
    rows = _group_axles(model.patches, "across")
    assert len(rows) == 3
    assert [r["load_kn"] for r in rows] == pytest.approx([80.0, 80.0, 80.0])
    assert all(r["tires_per_side"] == 1 for r in rows)
    assert [r["spacing_m"] for r in rows[1:]] == pytest.approx([3.0, 1.5])


@pytest.mark.parametrize("key,expected", [
    ("cl625", 1.8),
    ("western_star_4700sb", 2.4),
    ("dump_truck_3axle", 2.0),
    ("cat_320", 2.4079),
])
def test_measured_gauge_matches_the_preset_on_dual_and_single_vehicles(key, expected):
    """Regression: this over-reported the gauge by exactly the dual spacing.
    It passed against the CAT 320 alone, which has no duals to expose it."""
    preset = VEHICLE_PRESETS[key]
    for orientation in ("across", "along"):
        # Build and measure in the same frame - the cross-travel axis swaps
        # with orientation, so a model laid out one way must be read that way.
        model = multi_axle_vehicle(preset.axles, preset.axle_width_m,
                                   orientation=orientation)
        measured = _measure_axle_width(model.patches, orientation)
        assert measured == pytest.approx(expected, abs=1e-3), (key, orientation)


def test_saved_dual_tyre_vehicle_summary_reports_its_full_load():
    """Regression: the picker halved a dual-tyre vehicle's load, because the
    summary counted two tyres per axle where the analysis counts four."""
    data = {
        "name": "Tandem", "load_type": "wheels",
        "wheels": {"wheel_load_kn": 35.0, "axle_count": 4, "dual_spacing": "330"},
    }
    assert _vehicle_summary(data, "v1")["total_load_kn"] == pytest.approx(560.0)


def test_saved_single_tyre_vehicle_summary_is_unchanged():
    data = {
        "name": "Single", "load_type": "wheels",
        "wheels": {"wheel_load_kn": 35.0, "axle_count": 4, "dual_spacing": "0"},
    }
    assert _vehicle_summary(data, "v1")["total_load_kn"] == pytest.approx(280.0)


def test_every_unverified_preset_states_its_assumptions():
    """An empty list where assumptions are surfaced reads as "nothing to
    confirm", which is never true of an unverified transcription."""
    for key, preset in VEHICLE_PRESETS.items():
        if not preset.verified:
            assert preset.assumptions, key
