"""Surcharge on a buried pipe: load models and the analysis orchestrator."""

import numpy as np
import pytest

from core.soil.boussinesq import point_stress_kpa
from core.soil.buried_pipe import (
    PipeSurchargeRequest,
    analyse,
    stress_field_kpa,
)
from core.soil.loads import Patch, PointLoad, custom_load, tracked_machine, wheel_group


def excavator(**kw):
    defaults = dict(
        weight_kn=200.0,          # ~20 t class
        track_length_m=3.2,
        track_width_m=0.6,
        gauge_m=2.2,
        orientation="across",
    )
    defaults.update(kw)
    return tracked_machine(**defaults)


def request_for(load, **kw):
    defaults = dict(cover_m=1.0, pipe_od_m=0.6, dla=1.0)
    defaults.update(kw)
    return PipeSurchargeRequest(load=load, **defaults)


# --------------------------------------------------------------------------
# Load models
# --------------------------------------------------------------------------

def test_tracked_machine_splits_weight_between_two_tracks():
    m = excavator()
    assert len(m.patches) == 2
    assert m.total_kn == pytest.approx(200.0)
    assert all(p.total_kn == pytest.approx(100.0) for p in m.patches)
    # Nominal ground bearing pressure = W / total contact area.
    assert m.patches[0].pressure_kpa == pytest.approx(100.0 / (3.2 * 0.6))


def test_track_orientation_swaps_the_plan_dimensions():
    across = excavator(orientation="across")
    along = excavator(orientation="along")
    # Crossing the pipe puts the long track axis transverse to it.
    assert across.patches[0].width_x_m == pytest.approx(3.2)
    assert across.patches[0].length_y_m == pytest.approx(0.6)
    assert along.patches[0].width_x_m == pytest.approx(0.6)
    assert along.patches[0].length_y_m == pytest.approx(3.2)


def test_tracks_are_separated_by_the_gauge_across_the_direction_of_travel():
    across = excavator(orientation="across")
    ys = sorted(p.y_m for p in across.patches)
    assert ys[1] - ys[0] == pytest.approx(2.2)
    along = excavator(orientation="along")
    xs = sorted(p.x_m for p in along.patches)
    assert xs[1] - xs[0] == pytest.approx(2.2)


def test_wheel_group_counts_tyres_and_places_duals():
    g = wheel_group(
        wheel_load_kn=50.0, patch_along_travel_m=0.25, patch_across_travel_m=0.51,
        axle_width_m=1.8, dual_spacing_m=0.35, axle_count=2, axle_spacing_m=1.2,
        orientation="across",
    )
    assert len(g.patches) == 2 * 2 * 2  # 2 axles x 2 sides x 2 tyres
    assert g.total_kn == pytest.approx(400.0)
    assert g.patches[0].pressure_kpa == pytest.approx(50.0 / (0.25 * 0.51))


def test_load_model_rejects_nonsense():
    with pytest.raises(ValueError):
        tracked_machine(weight_kn=0, track_length_m=3, track_width_m=0.6, gauge_m=2)
    with pytest.raises(ValueError):
        wheel_group(wheel_load_kn=-5, patch_along_travel_m=0.25,
                    patch_across_travel_m=0.5, axle_width_m=1.8)
    with pytest.raises(ValueError, match="at least one"):
        custom_load()
    with pytest.raises(ValueError, match="Orientation must be"):
        tracked_machine(weight_kn=100, track_length_m=3, track_width_m=0.6,
                        gauge_m=2, orientation="sideways")


def test_shifting_a_load_moves_every_patch_together():
    m = excavator()
    moved = m.shifted_x(1.5)
    for before, after in zip(m.patches, moved.patches):
        assert after.x_m == pytest.approx(before.x_m + 1.5)
    assert moved.total_kn == pytest.approx(m.total_kn)


# --------------------------------------------------------------------------
# Stress field
# --------------------------------------------------------------------------

def test_stress_field_superposes_patches_and_points():
    load = custom_load(
        patches=[Patch("a", 0.0, 0.0, 1.0, 1.0, 100.0)],
        points=[PointLoad("b", 5.0, 0.0, 50.0)],
    )
    z = 1.5
    total = float(stress_field_kpa(load, np.array([0.0]), np.array([0.0]), z)[0, 0])
    patch_only = float(stress_field_kpa(
        custom_load(patches=[Patch("a", 0.0, 0.0, 1.0, 1.0, 100.0)]),
        np.array([0.0]), np.array([0.0]), z)[0, 0])
    point_only = point_stress_kpa(50.0, 5.0, z)
    assert total == pytest.approx(patch_only + point_only, rel=1e-9)


def test_total_load_is_conserved_through_the_stress_field():
    """Integrating the field over a wide plane must recover the applied load."""
    load = excavator()
    span = np.linspace(-80.0, 80.0, 900)
    field = stress_field_kpa(load, span, span, 2.0)
    total = np.trapezoid(np.trapezoid(field, span, axis=1), span)
    assert total == pytest.approx(load.total_kn, rel=1e-2)


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def test_analysis_reports_every_method():
    r = analyse(request_for(excavator()))
    keys = [m.key for m in r.methods]
    assert keys == ["boussinesq", "boussinesq_point", "westergaard",
                    "spread_2to1", "spread_superposed", "code_spread",
                    "code_spread_superposed"]
    assert all(m.pressure_kpa > 0 for m in r.methods)


def test_point_idealisation_overstates_stress_at_shallow_cover():
    """The whole reason it is reported: it is badly wrong when the contact
    area is not small against the depth, and converges when it is."""
    shallow = analyse(request_for(excavator(), cover_m=0.4))
    deep = analyse(request_for(excavator(), cover_m=12.0))

    def ratio(r):
        by = {m.key: m.pressure_kpa for m in r.methods}
        return by["boussinesq_point"] / by["boussinesq"]

    assert ratio(shallow) > 2.0
    assert ratio(deep) == pytest.approx(1.0, abs=0.05)


def test_westergaard_sits_below_boussinesq_under_the_load():
    r = analyse(request_for(excavator(), cover_m=1.0))
    by = {m.key: m.pressure_kpa for m in r.methods}
    assert 0.5 * by["boussinesq"] < by["westergaard"] < by["boussinesq"]


def test_poisson_ratio_moves_the_westergaard_result():
    low = analyse(request_for(excavator(), poisson_ratio=0.0))
    high = analyse(request_for(excavator(), poisson_ratio=0.4))
    pick = lambda r: next(m.pressure_kpa for m in r.methods if m.key == "westergaard")
    assert pick(low) != pytest.approx(pick(high), rel=1e-3)


def test_pressure_falls_off_with_cover():
    shallow = analyse(request_for(excavator(), cover_m=0.6)).live_pressure_kpa
    deep = analyse(request_for(excavator(), cover_m=3.0)).live_pressure_kpa
    assert deep < shallow


def test_depth_profile_carries_every_method_and_decays():
    r = analyse(request_for(excavator(), cover_m=1.0))
    assert r.depth_profile
    for key in ("boussinesq", "boussinesq_point", "westergaard",
                "spread_2to1", "spread_superposed", "code_spread"):
        series = [row[key] for row in r.depth_profile]
        assert len(series) == len(r.depth_profile)
        assert all(v >= 0 for v in series), key

    # The continuous methods decay steadily past the immediate near-surface.
    for key in ("boussinesq", "boussinesq_point", "westergaard",
                "spread_2to1", "code_spread"):
        tail = [row[key] for row in r.depth_profile][5:]
        assert all(a >= b - 1e-6 for a, b in zip(tail, tail[1:])), (key, tail)


def test_spread_superposed_can_jump_as_a_footprint_first_reaches_the_point():
    """Unlike the continuous methods, this one is not required to decay
    smoothly: at shallow depth a point between two footprints sees nothing
    from either until one grows enough to reach it, which shows up as a jump
    up, not a decay, the instant that happens."""
    r = analyse(request_for(excavator(gauge_m=2.2, orientation="across"), cover_m=1.0))
    series = [row["spread_superposed"] for row in r.depth_profile]
    # Somewhere in the profile a footprint must newly reach the gap centre,
    # i.e. the series is not monotonically decreasing throughout.
    assert any(b > a + 1e-9 for a, b in zip(series, series[1:]))


def test_depth_profile_agrees_with_the_headline_at_crown_level():
    r = analyse(request_for(excavator(), cover_m=1.0))
    nearest = min(r.depth_profile, key=lambda row: abs(row["depth_m"] - 1.0))
    assert nearest["boussinesq"] == pytest.approx(r.live_pressure_kpa, rel=0.05)


# --------------------------------------------------------------------------
# Pressure bulb
# --------------------------------------------------------------------------

def test_pressure_bulb_grid_is_well_formed():
    r = analyse(request_for(excavator(), cover_m=1.0))
    b = r.bulb
    assert len(b["grid_kpa"]) == len(b["depth_m"])
    assert all(len(row) == len(b["x_m"]) for row in b["grid_kpa"])
    assert b["peak_kpa"] == pytest.approx(max(max(r) for r in b["grid_kpa"]))
    # Depth increases down the rows; stress decays down the middle.
    assert b["depth_m"] == sorted(b["depth_m"])


def test_pressure_bulb_isolines_lie_on_their_level():
    """Every contour vertex must sit at its own pressure, interpolated from
    the grid it came from."""
    r = analyse(request_for(excavator(), cover_m=1.0))
    b = r.bulb
    assert b["isolines"]
    grid = np.array(b["grid_kpa"])
    xs, zs = np.array(b["x_m"]), np.array(b["depth_m"])

    for line in b["isolines"]:
        level = line["level_kpa"]
        assert line["segments"], level
        for seg in line["segments"][:40]:
            for x, z in seg:
                i = int(np.clip(np.searchsorted(zs, z) - 1, 0, len(zs) - 2))
                j = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
                cell = grid[i:i + 2, j:j + 2]
                assert cell.min() - 1e-6 <= level <= cell.max() + 1e-6


def test_pressure_bulb_contour_levels_are_round_numbers_below_the_peak():
    r = analyse(request_for(excavator(), cover_m=1.0))
    levels = [line["level_kpa"] for line in r.bulb["isolines"]]
    assert levels == sorted(levels)
    assert all(0 < lv < r.bulb["peak_kpa"] for lv in levels)


def test_profiles_can_be_skipped_for_a_headline_only_run():
    full = analyse(request_for(excavator()))
    quick = analyse(request_for(excavator(), with_profiles=False))
    assert quick.live_pressure_kpa == pytest.approx(full.live_pressure_kpa)
    assert quick.worst_offset_pressure_kpa == pytest.approx(full.worst_offset_pressure_kpa)
    assert quick.depth_profile == [] and quick.offset_profile == [] and quick.bulb == {}


def test_dynamic_load_allowance_scales_the_result():
    plain = analyse(request_for(excavator(), dla=1.0)).live_pressure_kpa
    impact = analyse(request_for(excavator(), dla=1.3)).live_pressure_kpa
    assert impact == pytest.approx(plain * 1.3, rel=1e-9)


def test_dla_below_one_is_rejected():
    with pytest.raises(ValueError, match="cannot be below 1.0"):
        analyse(request_for(excavator(), dla=0.8))


def test_zero_cover_or_diameter_is_rejected():
    with pytest.raises(ValueError, match="cover"):
        analyse(request_for(excavator(), cover_m=0.0))
    with pytest.raises(ValueError, match="diameter"):
        analyse(request_for(excavator(), pipe_od_m=0.0))


def test_load_per_metre_is_consistent_with_the_average_pressure():
    r = analyse(request_for(excavator(), pipe_od_m=0.9))
    assert r.load_per_m_kn_m == pytest.approx(r.average_over_pipe_kpa * 0.9, rel=1e-9)


def test_straddling_machine_over_shallow_cover_is_not_the_worst_case():
    """Tracking ALONG the pipe, a wide-gauge machine centred on shallow cover
    leaves the pipe in the gap between its tracks; sliding one track over the
    pipe is worse. The tool must find that rather than assume centred governs."""
    r = analyse(request_for(excavator(gauge_m=2.4, orientation="along"),
                            cover_m=0.5, machine_offset_m=0.0))
    assert not r.offset_is_worst
    assert r.worst_offset_pressure_kpa > r.live_pressure_kpa
    assert abs(r.worst_offset_m) > 0.3
    assert any("not the worst one" in w for w in r.warnings)


def test_deep_cover_makes_the_centred_position_critical():
    """Once the stress bulbs merge with depth, straddling IS the worst case."""
    r = analyse(request_for(excavator(gauge_m=2.2, orientation="along"),
                            cover_m=4.0, machine_offset_m=0.0))
    assert r.offset_is_worst
    assert abs(r.worst_offset_m) < 0.35


def test_machine_crossing_the_pipe_has_no_gap_to_straddle():
    """Crossing, both tracks span the full transverse width, so the pipe is
    under both of them wherever it sits and centred is always critical."""
    r = analyse(request_for(excavator(gauge_m=2.4, orientation="across"),
                            cover_m=0.5, machine_offset_m=0.0))
    assert r.offset_is_worst


def test_offset_profile_peaks_at_the_reported_worst_offset():
    r = analyse(request_for(excavator(), cover_m=0.6))
    peak = max(r.offset_profile, key=lambda p: p["pressure_kpa"])
    assert peak["offset_m"] == pytest.approx(r.worst_offset_m, abs=0.05)
    assert peak["pressure_kpa"] == pytest.approx(r.worst_offset_pressure_kpa, rel=1e-6)


def test_moving_the_machine_far_away_leaves_almost_nothing_at_the_pipe():
    near = analyse(request_for(excavator(), machine_offset_m=0.0)).live_pressure_kpa
    far = analyse(request_for(excavator(), machine_offset_m=25.0)).live_pressure_kpa
    assert far < 0.02 * near


def test_spread_methods_merge_overlapping_contact_areas():
    """Two tracks whose spread areas overlap must not double-count the load:
    the merged pressure has to stay below the sum of the two separately."""
    load = excavator(gauge_m=2.2)
    deep = analyse(request_for(load, cover_m=4.0))
    spread = next(m for m in deep.methods if m.key == "spread_2to1")
    # All 200 kN over one merged area, which must exceed the machine footprint.
    footprint = 3.2 * (0.6 * 2 + 2.2)
    assert 0 < spread.pressure_kpa < 200.0 / footprint


def test_spread_and_boussinesq_stay_within_a_factor_of_two():
    r = analyse(request_for(excavator(), cover_m=1.5))
    b = next(m for m in r.methods if m.key == "boussinesq").pressure_kpa
    s = next(m for m in r.methods if m.key == "spread_2to1").pressure_kpa
    assert 0.5 < b / s < 2.0, (b, s)


def test_live_load_is_compared_against_the_soil_overburden():
    r = analyse(request_for(excavator(), cover_m=2.0, soil_unit_weight_kn_m3=20.0))
    assert r.soil_pressure_kpa == pytest.approx(40.0)
    assert r.live_to_dead_ratio == pytest.approx(r.live_pressure_kpa / 40.0)


def test_free_field_caveat_is_always_warned_about():
    r = analyse(request_for(excavator()))
    assert any("FREE-FIELD" in w for w in r.warnings)
    assert any("homogeneous" in w for w in r.warnings)


def test_shallow_cover_warnings_fire():
    r = analyse(request_for(excavator(), cover_m=0.4, pipe_od_m=1.2))
    assert any("shallow" in w for w in r.warnings)
    assert any("half the pipe diameter" in w for w in r.warnings)


def test_unverified_spread_factor_is_flagged():
    r = analyse(request_for(excavator(), spread_factor=1.15,
                            spread_factor_verified=False))
    assert any("unverified" in w for w in r.warnings)
    assert not next(m for m in r.methods if m.key == "code_spread").verified


def test_crossing_the_pipe_is_worse_than_tracking_along_it_when_centred():
    """Crossing puts both 3.2 m tracks over the pipe at once; tracking along
    leaves it in the gauge gap. Same machine, materially different demand."""
    across = analyse(request_for(excavator(orientation="across"),
                                 cover_m=0.8, machine_offset_m=0.0))
    along = analyse(request_for(excavator(orientation="along"),
                                cover_m=0.8, machine_offset_m=0.0))
    assert across.live_pressure_kpa > 1.5 * along.live_pressure_kpa


# --------------------------------------------------------------------------
# Supporting calculations
# --------------------------------------------------------------------------

def test_every_method_shows_its_formula_and_working():
    r = analyse(request_for(excavator()))
    for m in r.methods:
        assert m.formula, m.key
        assert m.substitution, m.key
        assert m.terms, m.key
        assert all(t.detail for t in m.terms), m.key


def test_superposition_terms_add_up_to_the_reported_answer():
    """The working must reconcile with the headline, or it is not working."""
    r = analyse(request_for(excavator(), cover_m=1.0, dla=1.3))
    for m in r.methods:
        if not m.terms_sum_to_total:
            continue
        total = sum(t.value_kpa for t in m.terms)
        assert total == pytest.approx(m.pressure_kpa, rel=1e-3), m.key


def test_spread_terms_are_candidate_areas_and_the_largest_is_taken():
    r = analyse(request_for(excavator()))
    for key in ("spread_2to1", "code_spread"):
        m = next(x for x in r.methods if x.key == key)
        assert not m.terms_sum_to_total
        assert max(t.value_kpa for t in m.terms) == pytest.approx(m.pressure_kpa, rel=1e-3)


def test_boussinesq_term_detail_carries_a_checkable_influence_factor():
    """A reviewer must be able to take q and I from the row and reproduce it."""
    r = analyse(request_for(excavator(), cover_m=1.0, dla=1.3))
    m = next(x for x in r.methods if x.key == "boussinesq")
    row = max(m.terms, key=lambda t: t.value_kpa)
    q = float(row.detail.split("q = ")[1].split(" kPa")[0])
    influence = float(row.detail.split("I = ")[1])
    assert q * influence * 1.3 == pytest.approx(row.value_kpa, rel=1e-3)


def test_point_term_detail_reproduces_the_closed_form_by_hand():
    r = analyse(request_for(excavator(), cover_m=1.0, dla=1.0))
    m = next(x for x in r.methods if x.key == "boussinesq_point")
    row = max(m.terms, key=lambda t: t.value_kpa)
    load_kn = float(row.detail.split("P = ")[1].split(" kN")[0])
    radius = float(row.detail.split("r = ")[1].split(" m")[0])
    depth = float(row.detail.split("z = ")[1].split(" m")[0])
    expected = 3 * load_kn * depth**3 / (2 * np.pi * (radius**2 + depth**2) ** 2.5)
    assert row.value_kpa == pytest.approx(expected, rel=1e-2)


def test_spread_term_detail_reproduces_its_own_pressure():
    r = analyse(request_for(excavator(), dla=1.0))
    m = next(x for x in r.methods if x.key == "spread_2to1")
    row = m.terms[0]
    load_kn = float(row.detail.split(" kN over ")[0])
    area = float(row.detail.split("= ")[1].split(" m^2")[0])
    assert load_kn / area == pytest.approx(row.value_kpa, rel=1e-3)


def test_terms_cover_every_contact_area():
    r = analyse(request_for(excavator()))
    m = next(x for x in r.methods if x.key == "boussinesq")
    assert {t.label for t in m.terms} == {"left track", "right track"}


# --------------------------------------------------------------------------
# Crown-level plan grid (feeds the 3D view)
# --------------------------------------------------------------------------

def test_crown_plan_grid_is_well_formed():
    r = analyse(request_for(excavator(), cover_m=1.0))
    cp = r.crown_plan
    assert len(cp["grid_kpa"]) == len(cp["y_m"])
    assert all(len(row) == len(cp["x_m"]) for row in cp["grid_kpa"])
    assert cp["peak_kpa"] == pytest.approx(max(max(row) for row in cp["grid_kpa"]))


def test_crown_plan_peak_matches_the_worst_crown_pressure():
    """Both describe the same plane, so their peaks must agree."""
    r = analyse(request_for(excavator(), cover_m=1.0))
    assert r.crown_plan["peak_kpa"] == pytest.approx(
        r.worst_offset_pressure_kpa, rel=0.03)


def test_crown_plan_and_bulb_agree_where_they_intersect():
    """The bulb row at crown depth and the plan row at the worst y describe
    the same line in space and must carry the same stresses."""
    r = analyse(request_for(excavator(), cover_m=1.0))
    bulb, plan = r.bulb, r.crown_plan

    depths = np.array(bulb["depth_m"])
    row_bulb = np.array(bulb["grid_kpa"])[int(np.argmin(np.abs(depths - r.cover_m)))]
    peak_bulb = float(row_bulb.max())

    peak_plan = max(max(row) for row in plan["grid_kpa"])
    assert peak_bulb == pytest.approx(peak_plan, rel=0.05)


# --------------------------------------------------------------------------
# Superposed (individual, per-footprint) spread method
# --------------------------------------------------------------------------

def test_spread_superposed_is_reported_and_sums_its_terms():
    r = analyse(request_for(excavator(), cover_m=1.0))
    m = next(x for x in r.methods if x.key == "spread_superposed")
    assert m.terms_sum_to_total
    assert sum(t.value_kpa for t in m.terms) == pytest.approx(m.pressure_kpa, rel=1e-3)


def test_spread_superposed_differs_from_the_merged_box_method():
    """Two well-separated tracks: neither box overlaps the other's, so the
    merged-box method and the per-footprint method must actually differ once
    the tracks are close enough for their SPREAD (not raw) footprints to
    overlap only partially - otherwise they coincide, which is not a useful
    test. Use a shallow, wide-gauge machine where spread footprints overlap
    only at one edge."""
    r = analyse(request_for(excavator(gauge_m=1.0, orientation="along"), cover_m=3.0))
    by_key = {m.key: m.pressure_kpa for m in r.methods}
    # Not asserting a direction - only that keeping footprints separate is a
    # distinct calculation from merging them into one box.
    assert by_key["spread_superposed"] != pytest.approx(by_key["spread_2to1"], rel=1e-6)


def test_spread_superposed_zero_outside_every_footprint():
    """Far from the machine, no footprint reaches the point: pressure is 0."""
    from core.soil.buried_pipe import _spread_superposed_kpa
    m = excavator()
    far = _spread_superposed_kpa(m, 500.0, 500.0, 1.0, 1.0)
    assert far == 0.0


def test_spread_superposed_terms_report_which_footprints_reach_the_point():
    from core.soil.buried_pipe import _spread_superposed_terms
    m = excavator()
    # The centre of the left track is inside that track's own footprint at
    # any depth, so this point is guaranteed a hit.
    left_track_y = m.patches[0].y_m
    terms = _spread_superposed_terms(m, 0.0, left_track_y, 1.0, 1.0, 1.0)
    assert len(terms) == len(m.patches)
    assert any("point falls inside" in t.detail for t in terms)
    assert any("falls outside" in t.detail for t in terms)
