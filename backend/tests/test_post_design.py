"""Post and column design checks."""

import pytest

from core.units import MM_PER_FOOT, MM_PER_INCH, N_PER_LBF
from core.wood import materials, scl_columns
from core.wood.compression import (
    MAX_SLENDERNESS,
    PostDesignError,
    PostRequest,
    design,
    effective_length,
    kzcg,
)
from core.wood.factors import Conditions
from core.wood.sections import BuiltUpSection


def sawn_post(**kw) -> PostRequest:
    defaults = dict(
        length_mm=2440.0,  # 8 ft
        axial_kn={"D": 12.0, "S": 30.0},
        material_key="SPF-No1No2",
        section=BuiltUpSection(38.0, 140.0, plies=3),  # 3-ply 2x6
        conditions=Conditions(service="dry"),
    )
    defaults.update(kw)
    return PostRequest(**defaults)


# --------------------------------------------------------------------------
# Factor behaviour
# --------------------------------------------------------------------------

def test_effective_length_factors_match_o86_table():
    assert effective_length("pinned-pinned", 3000)[0] == pytest.approx(3000)
    assert effective_length("fixed-fixed", 3000)[0] == pytest.approx(1950)
    assert effective_length("fixed-pinned", 3000)[0] == pytest.approx(2400)
    assert effective_length("fixed-free", 3000)[0] == pytest.approx(7200)
    with pytest.raises(PostDesignError):
        effective_length("wishful", 3000)


def test_kzcg_is_capped_at_1_3():
    # A short stubby post would compute above the cap.
    assert kzcg(140.0, 500.0).value == pytest.approx(1.3)
    # A long slender one falls below it.
    assert kzcg(89.0, 6000.0).value < 1.3


def test_kzcg_matches_the_published_formula():
    d, L = 140.0, 2440.0
    expected = min(1.3, 6.3 * (d * L) ** -0.13)
    assert kzcg(d, L).value == pytest.approx(expected, rel=1e-9)


# --------------------------------------------------------------------------
# Sawn lumber posts
# --------------------------------------------------------------------------

def test_sawn_post_passes_and_reports_slenderness():
    r = design(sawn_post())
    assert r.method == "O86 Cl. 6.5.6"
    assert r.outcome.passed, [(c.label, c.ratio) for c in r.outcome.checks]
    # Buckling about the weak (width) axis of a 114 x 140 post.
    assert r.slenderness == pytest.approx(2440.0 / 114.0, rel=1e-3)
    assert r.slenderness_axis == "width"


def test_capacity_falls_as_the_post_gets_longer():
    short = design(sawn_post(length_mm=1800.0)).resistance_kn
    tall = design(sawn_post(length_mm=3600.0)).resistance_kn
    assert tall < short


def test_slenderness_over_50_is_rejected_with_a_clear_message():
    with pytest.raises(PostDesignError, match="exceeds the CSA O86 limit of 50"):
        design(sawn_post(length_mm=8000.0, section=BuiltUpSection(38.0, 140.0, plies=1)))


def test_bracing_one_axis_raises_capacity():
    unbraced = design(sawn_post(length_mm=3600.0)).resistance_kn
    braced = design(sawn_post(length_mm=3600.0, unbraced_b_mm=1800.0)).resistance_kn
    assert braced > unbraced


def test_fixed_ends_raise_capacity_over_pinned():
    pinned = design(sawn_post(length_mm=3600.0)).resistance_kn
    fixed = design(sawn_post(
        length_mm=3600.0,
        end_condition_d="fixed-fixed",
        end_condition_b="fixed-fixed",
    )).resistance_kn
    assert fixed > pinned


def test_built_up_post_reports_the_unfastened_alternative():
    """A short built-up post: individual plies still qualify as columns."""
    r = design(sawn_post(length_mm=1500.0))
    assert r.plies == 3
    assert r.independent_ply_resistance_kn is not None
    assert r.independent_ply_resistance_kn < r.resistance_kn
    assert any("fastened" in w for w in r.outcome.warnings)


def test_built_up_post_flags_when_a_single_ply_is_too_slender():
    """At 2.44 m a lone 38 mm ply exceeds C_c = 50, so fastening is load-bearing."""
    r = design(sawn_post())
    assert r.independent_ply_resistance_kn is None
    assert any("cannot be assumed to act individually" in w for w in r.outcome.warnings)


def test_bearing_perpendicular_can_govern_a_built_up_spf_post():
    """f_cp is low for S-P-F, so a heavily loaded post crushes before it buckles."""
    r = design(sawn_post(axial_kn={"D": 20.0, "S": 45.0}))
    by_check = {c.check: c for c in r.outcome.checks}
    assert by_check["bearing"].ratio > by_check["compression"].ratio
    assert not r.outcome.passed


def test_unverified_sawn_material_warns():
    r = design(sawn_post())
    assert any("Verify f_c and E_05" in w for w in r.outcome.warnings)


def test_no_axial_load_is_rejected():
    with pytest.raises(PostDesignError, match="at least one axial load"):
        design(sawn_post(axial_kn={"D": 0.0}))


def test_capacity_curve_stops_at_the_slenderness_limit():
    r = design(sawn_post())
    assert r.capacity_curve
    least = 114.0
    assert max(p["length_mm"] for p in r.capacity_curve) <= MAX_SLENDERNESS * least + 1
    # Capacity must decrease monotonically with length.
    values = [p["resistance_kn"] for p in r.capacity_curve]
    assert all(a >= b for a, b in zip(values, values[1:]))


# --------------------------------------------------------------------------
# SCL columns - published table lookup
# --------------------------------------------------------------------------

def test_scl_lookup_reproduces_published_values_exactly():
    """Every tabulated Parallam and TimberStrand value must be returned as-is."""
    for key, product in scl_columns.PRODUCTS.items():
        for bearing, table in product.tables.items():
            for length_ft, row in table.items():
                for i, published in enumerate(row):
                    if published is None:
                        continue
                    n, _ = scl_columns.capacity_n(
                        key, i, length_ft * MM_PER_FOOT, bearing
                    )
                    assert n / N_PER_LBF == pytest.approx(published, rel=1e-9), (
                        key, bearing, length_ft, i
                    )


def test_scl_interpolates_between_tabulated_lengths():
    # PSL 1.8E, 3.5 x 3.5, column base: 19,010 lb at 6 ft, 15,815 lb at 7 ft.
    n, note = scl_columns.capacity_n("PSL-1.8E-Column", 0, 6.5 * MM_PER_FOOT)
    assert n / N_PER_LBF == pytest.approx((19010 + 15815) / 2, rel=1e-6)
    assert "interpolated" in note


def test_scl_refuses_to_extrapolate_past_the_table():
    with pytest.raises(scl_columns.SclColumnError, match="slenderness ratio"):
        scl_columns.capacity_n("PSL-1.8E-Column", 0, 20 * MM_PER_FOOT)


def test_scl_below_table_start_uses_the_shortest_value_conservatively():
    n, note = scl_columns.capacity_n("PSL-1.8E-Column", 0, 4 * MM_PER_FOOT)
    assert n / N_PER_LBF == pytest.approx(19010)
    assert "conservative" in note


def test_scl_post_design_roundtrip():
    r = design(PostRequest(
        length_mm=8 * MM_PER_FOOT,
        axial_kn={"D": 12.0, "S": 30.0},
        scl_product="PSL-1.8E-Column",
        scl_size_index=1,  # 3.5 x 5.25
    ))
    assert r.method == "manufacturer table"
    # 19,330 lb published at 8 ft.
    assert r.resistance_kn == pytest.approx(19330 * N_PER_LBF / 1000, rel=1e-6)
    assert r.outcome.passed
    assert any("does not reproduce" in w for w in r.outcome.warnings)


def test_scl_size_and_product_validation():
    with pytest.raises(PostDesignError):
        design(PostRequest(length_mm=2400, axial_kn={"D": 10.0},
                           scl_product="Nope-1.0E"))
    with pytest.raises(scl_columns.SclColumnError):
        scl_columns.capacity_n("PSL-1.8E-Column", 99, 2400)


def test_wood_plate_bearing_is_never_stronger_than_column_base():
    for key, product in scl_columns.PRODUCTS.items():
        for i in range(len(product.sizes)):
            for length_ft in (6, 10, 12, 14):
                try:
                    base, _ = scl_columns.capacity_n(
                        key, i, length_ft * MM_PER_FOOT, "column_base")
                    plate, _ = scl_columns.capacity_n(
                        key, i, length_ft * MM_PER_FOOT, "wood_plate")
                except scl_columns.SclColumnError:
                    continue
                assert plate <= base + 1e-6, (key, i, length_ft)


def test_scl_dimensions_are_consistent_with_labels():
    size = scl_columns.PRODUCTS["PSL-1.8E-Column"].sizes[3]
    assert size.label == '5 1/4" x 5 1/4"'
    assert size.width_mm == pytest.approx(5.25 * MM_PER_INCH)
    assert size.least_dimension_mm == pytest.approx(5.25 * MM_PER_INCH)
