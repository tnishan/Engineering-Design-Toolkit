"""Multi-axle vehicle load models and preset vehicles."""

import pytest

from core.soil.loads import AxleSpec, multi_axle_vehicle
from core.soil.vehicles import (
    CAT_320_EXCAVATOR,
    CL625_TRUCK,
    TRACKED_PRESETS,
    TRUCK_PRESETS,
    WESTERN_STAR_4700SB,
)
from core.units import MM_PER_FOOT, MM_PER_INCH, N_PER_LBF


def two_axle_truck(**kw):
    defaults = dict(
        axles=[
            AxleSpec("front", 50.0, tire_width_m=0.3, tire_length_m=0.25),
            AxleSpec("rear", 100.0, tire_width_m=0.3, tire_length_m=0.25,
                     spacing_from_previous_m=4.0),
        ],
        axle_width_m=1.8,
    )
    defaults.update(kw)
    return multi_axle_vehicle(**defaults)


# --------------------------------------------------------------------------
# AxleSpec
# --------------------------------------------------------------------------

def test_wheel_load_splits_across_side_and_duals():
    single = AxleSpec("a", 100.0, tires_per_side=1, tire_width_m=0.3, tire_length_m=0.25)
    dual = AxleSpec("a", 100.0, tires_per_side=2, tire_width_m=0.3, tire_length_m=0.25,
                    dual_spacing_m=0.3)
    assert single.wheel_load_kn() == pytest.approx(50.0)
    assert dual.wheel_load_kn() == pytest.approx(25.0)


def test_contact_length_from_pressure_matches_the_load_over_pressure_rule():
    axle = AxleSpec("a", 140.0, tires_per_side=1, tire_width_m=0.3, tire_pressure_kpa=700.0)
    wheel_load = 70.0
    expected_area = wheel_load / 700.0
    assert axle.contact_length_m() == pytest.approx(expected_area / 0.3, rel=1e-9)


def test_direct_contact_length_is_used_when_given():
    axle = AxleSpec("a", 100.0, tire_length_m=0.4, tire_pressure_kpa=999.0)
    assert axle.contact_length_m() == pytest.approx(0.4)


def test_axle_spec_validation():
    with pytest.raises(ValueError, match="load must be"):
        AxleSpec("a", 0.0, tire_length_m=0.3)
    with pytest.raises(ValueError, match="1 or 2"):
        AxleSpec("a", 100.0, tires_per_side=3, tire_length_m=0.3)
    with pytest.raises(ValueError, match="length or a tyre pressure"):
        AxleSpec("a", 100.0)
    with pytest.raises(ValueError, match="dual .* spacing"):
        AxleSpec("a", 100.0, tires_per_side=2, tire_length_m=0.3, dual_spacing_m=0.0)


# --------------------------------------------------------------------------
# multi_axle_vehicle
# --------------------------------------------------------------------------

def test_two_axle_truck_places_four_wheels():
    m = two_axle_truck()
    assert len(m.patches) == 4
    assert m.total_kn == pytest.approx(150.0)


def test_axles_are_spaced_along_travel_and_centred():
    """Crossing the pipe: travel is along x, so axle spacing shows in x."""
    m = two_axle_truck(orientation="across")
    xs = sorted({round(p.x_m, 6) for p in m.patches})
    assert len(xs) == 2
    assert xs[1] - xs[0] == pytest.approx(4.0)
    # Centred on the wheelbase midpoint.
    assert xs[0] == pytest.approx(-2.0)
    assert xs[1] == pytest.approx(2.0)


def test_axle_width_separates_wheels_across_travel():
    m = two_axle_truck(orientation="across")
    front = [p for p in m.patches if p.label.startswith("front")]
    ys = sorted(p.y_m for p in front)
    assert ys[1] - ys[0] == pytest.approx(1.8)


def test_orientation_swaps_which_axis_carries_the_spacing():
    across = two_axle_truck(orientation="across")
    along = two_axle_truck(orientation="along")
    ax_spread = max(p.x_m for p in across.patches) - min(p.x_m for p in across.patches)
    al_spread = max(p.y_m for p in along.patches) - min(p.y_m for p in along.patches)
    assert ax_spread == pytest.approx(4.0)
    assert al_spread == pytest.approx(4.0)
    # And across becomes the axle-width direction when tracking along.
    al_x_spread = max(p.x_m for p in along.patches) - min(p.x_m for p in along.patches)
    assert al_x_spread == pytest.approx(1.8)


def test_dual_tyres_are_placed_either_side_of_the_wheel_line():
    m = multi_axle_vehicle(
        axles=[AxleSpec("drive", 200.0, tires_per_side=2, tire_width_m=0.25,
                        tire_length_m=0.3, dual_spacing_m=0.35)],
        axle_width_m=1.8,
    )
    assert len(m.patches) == 4  # 2 sides x 2 duals
    assert m.total_kn == pytest.approx(200.0)
    left = [p for p in m.patches if p.y_m < 0]
    assert len(left) == 2
    ys = sorted(p.y_m for p in left)
    assert ys[1] - ys[0] == pytest.approx(0.35)


def test_empty_axle_list_is_rejected():
    with pytest.raises(ValueError, match="at least one axle"):
        multi_axle_vehicle(axles=[], axle_width_m=1.8)


def test_zero_axle_width_is_rejected():
    with pytest.raises(ValueError, match="track. width"):
        multi_axle_vehicle(
            axles=[AxleSpec("a", 100.0, tire_length_m=0.3)], axle_width_m=0.0)


def test_nonpositive_spacing_is_rejected():
    with pytest.raises(ValueError, match="spacing from the previous axle"):
        multi_axle_vehicle(
            axles=[
                AxleSpec("a", 100.0, tire_length_m=0.3),
                AxleSpec("b", 100.0, tire_length_m=0.3, spacing_from_previous_m=0.0),
            ],
            axle_width_m=1.8,
        )


# --------------------------------------------------------------------------
# Preset vehicles
# --------------------------------------------------------------------------

def test_cl625_total_load_matches_its_name():
    """The whole point of the designation: axle loads sum to 625 kN."""
    assert sum(a.load_kn for a in CL625_TRUCK.axles) == pytest.approx(625.0)


def test_cl625_wheelbase_matches_the_source_sheet():
    m = multi_axle_vehicle(CL625_TRUCK.axles, CL625_TRUCK.axle_width_m)
    xs = [p.x_m for p in m.patches]
    assert max(xs) - min(xs) == pytest.approx(18.0, abs=1e-6)


def test_cl625_wheel_loads_are_half_the_axle_loads():
    for axle, expected in zip(CL625_TRUCK.axles, (25.0, 70.0, 70.0, 87.5, 60.0)):
        assert axle.wheel_load_kn() == pytest.approx(expected)


def test_cl625_builds_without_error_and_is_flagged_unverified():
    m = multi_axle_vehicle(CL625_TRUCK.axles, CL625_TRUCK.axle_width_m)
    assert m.total_kn == pytest.approx(625.0)
    assert not CL625_TRUCK.verified
    assert CL625_TRUCK.assumptions


def test_western_star_axle_loads_match_the_source_sheet():
    total = sum(a.load_kn for a in WESTERN_STAR_4700SB.axles)
    assert total == pytest.approx(19840 * 4 * N_PER_LBF / 1000.0, rel=1e-6)


def test_western_star_third_and_fourth_axles_are_dual():
    by_label = {a.label: a for a in WESTERN_STAR_4700SB.axles}
    assert by_label["Steering"].tires_per_side == 1
    assert by_label["3rd"].tires_per_side == 2
    assert by_label["4th"].tires_per_side == 2


def test_western_star_builds_without_error():
    m = multi_axle_vehicle(WESTERN_STAR_4700SB.axles, WESTERN_STAR_4700SB.axle_width_m)
    assert len(m.patches) == 2 + 2 + 4 + 4  # steer, 2nd single; 3rd, 4th dual


def test_cat_320_weight_and_dimensions_match_the_source_sheet():
    assert CAT_320_EXCAVATOR.weight_kn == pytest.approx(49600 * N_PER_LBF / 1000.0, rel=1e-6)
    assert CAT_320_EXCAVATOR.track_width_m == pytest.approx(30 * MM_PER_INCH / 1000.0)
    assert CAT_320_EXCAVATOR.track_length_m == pytest.approx(176 * MM_PER_INCH / 1000.0)
    assert CAT_320_EXCAVATOR.gauge_m == pytest.approx(7.9 * MM_PER_FOOT / 1000.0)


def test_preset_registries_are_keyed_consistently():
    assert TRUCK_PRESETS["cl625"] is CL625_TRUCK
    assert TRUCK_PRESETS["western_star_4700sb"] is WESTERN_STAR_4700SB
    assert TRACKED_PRESETS["cat_320"] is CAT_320_EXCAVATOR
