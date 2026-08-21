"""HTTP round-trip tests for buried-pipe surcharge."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

EXCAVATOR = {
    "load_type": "tracked",
    "tracked": {
        "weight_kn": 200.0,
        "track_length": "3.2 m",
        "track_width": "600",
        "gauge": "2.2 m",
    },
    "orientation": "across",
    "cover": "1.0 m",
    "pipe_od": "600",
    "dla_mode": "manual",
    "dla": 1.3,
    "spread_preset": "aashto_granular",
    "project": "Trunk main crossing",
    "member": "MH12-MH13",
}


def test_excavator_roundtrip():
    r = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["ok"] is True
    assert d["total_load_kn"] == pytest.approx(200.0)
    assert d["cover_m"] == pytest.approx(1.0)
    assert d["pipe_od_m"] == pytest.approx(0.6)
    assert d["live_pressure_kpa"] > 0

    keys = [m["key"] for m in d["methods"]]
    assert keys == ["boussinesq", "boussinesq_point", "westergaard",
                    "spread_2to1", "spread_superposed", "code_spread"]

    assert len(d["patches"]) == 2
    assert d["patches"][0]["width_x_m"] == pytest.approx(3.2)

    assert d["depth_profile"] and d["offset_profile"]
    assert "<!doctype html>" in d["report_html"].lower()
    assert "MH12-MH13" in d["report_html"]
    assert "FREE-FIELD" in d["report_html"] or "FREE-FIELD" in " ".join(d["warnings"])


def test_dynamic_load_allowance_is_applied():
    static = client.post("/api/soil/pipe-surcharge",
                         json=dict(EXCAVATOR, dla_mode="none")).json()
    impact = client.post("/api/soil/pipe-surcharge",
                         json=dict(EXCAVATOR, dla_mode="manual", dla=1.3)).json()
    assert impact["live_pressure_kpa"] == pytest.approx(
        static["live_pressure_kpa"] * 1.3, rel=1e-6)
    assert static["dla"] == 1.0


def test_depth_reduced_impact_falls_off_with_cover():
    shallow = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, dla_mode="aashto_depth", cover="0.6 m")).json()
    deep = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, dla_mode="aashto_depth", cover="3.0 m")).json()
    assert shallow["dla"] > deep["dla"]
    assert deep["dla"] == pytest.approx(1.0)  # 33(1-0.125*9.84 ft) floors at zero
    assert "UNVERIFIED" in shallow["dla_basis"]


def test_spread_presets_change_the_comparison_column():
    granular = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, spread_preset="aashto_granular")).json()
    other = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, spread_preset="aashto_other")).json()

    g = next(m for m in granular["methods"] if m["key"] == "code_spread")
    o = next(m for m in other["methods"] if m["key"] == "code_spread")
    # A wider spread must give a lower pressure.
    assert g["pressure_kpa"] < o["pressure_kpa"]
    assert g["verified"] is False
    assert "UNVERIFIED" in g["note"]


def test_custom_spread_factor_is_honoured():
    d = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, spread_preset="custom", spread_factor=0.75)).json()
    m = next(x for x in d["methods"] if x["key"] == "code_spread")
    assert "0.75" in m["name"]


def test_spread_preset_none_drops_the_column():
    d = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, spread_preset="none")).json()
    assert "code_spread" not in [m["key"] for m in d["methods"]]
    assert all("code_spread" not in row for row in d["depth_profile"])


def test_wheel_load_roundtrip():
    r = client.post("/api/soil/pipe-surcharge", json={
        "load_type": "wheels",
        "wheels": {
            "wheel_load_kn": 70.0,
            "axle_width": "1.8 m",
            "dual_spacing": "350",
            "axle_count": 2,
            "axle_spacing": "1.2 m",
        },
        "orientation": "across",
        "cover": "0.9 m",
        "pipe_od": "450",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["patches"]) == 8          # 2 axles x 2 sides x 2 tyres
    assert d["total_load_kn"] == pytest.approx(560.0)
    # AASHTO tyre print defaults, 510 across travel by 250 along it.
    assert d["patches"][0]["pressure_kpa"] == pytest.approx(70.0 / (0.25 * 0.51), rel=1e-3)


def test_custom_patches_and_points():
    r = client.post("/api/soil/pipe-surcharge", json={
        "load_type": "custom",
        "custom_patches": [
            {"label": "pad", "x": "0", "y": "0", "width_x": "1 m",
             "length_y": "1 m", "total_kn": 150.0},
        ],
        "custom_points": [
            {"label": "leg", "x": "2 m", "y": "0", "load_kn": 40.0},
        ],
        "cover": "1.5 m",
        "pipe_od": "600",
        "dla_mode": "none",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_load_kn"] == pytest.approx(190.0)
    assert len(d["patches"]) == 1 and len(d["points"]) == 1


def test_bad_input_returns_ok_false_not_an_http_error():
    r = client.post("/api/soil/pipe-surcharge", json=dict(EXCAVATOR, cover="deep"))
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "cover" in r.json()["error"]


def test_zero_cover_is_reported_as_data():
    r = client.post("/api/soil/pipe-surcharge", json=dict(EXCAVATOR, cover="0"))
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_missing_machine_details_is_reported():
    r = client.post("/api/soil/pipe-surcharge",
                    json={"load_type": "tracked", "cover": "1 m"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "required" in r.json()["error"]


def test_negative_weight_is_rejected_by_validation():
    r = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, tracked=dict(EXCAVATOR["tracked"], weight_kn=-5)))
    assert r.status_code == 422


def test_worst_position_is_surfaced_when_it_differs():
    """Tracking along the pipe on shallow cover: centred is not critical."""
    d = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, orientation="along", cover="0.5 m", machine_offset="0")).json()
    assert d["offset_is_worst"] is False
    assert d["worst_offset_pressure_kpa"] > d["live_pressure_kpa"]
    assert any("not the worst one" in w for w in d["warnings"])


def test_surcharge_is_compared_against_overburden():
    d = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, cover="2.0 m", soil_unit_weight_kn_m3=20.0)).json()
    assert d["soil_pressure_kpa"] == pytest.approx(40.0)
    assert d["live_to_dead_ratio"] == pytest.approx(
        d["live_pressure_kpa"] / 40.0, rel=1e-3)


# --------------------------------------------------------------------------
# Extra methods, pressure bulb, orientation comparison
# --------------------------------------------------------------------------

def test_depth_profile_carries_a_series_per_method():
    d = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR).json()
    assert d["depth_profile"]
    row = d["depth_profile"][0]
    for key in ("depth_m", "boussinesq", "boussinesq_point", "westergaard",
                "spread_2to1", "spread_superposed", "code_spread"):
        assert key in row, key


def test_poisson_ratio_feeds_the_westergaard_row():
    low = client.post("/api/soil/pipe-surcharge",
                      json=dict(EXCAVATOR, poisson_ratio=0.0)).json()
    high = client.post("/api/soil/pipe-surcharge",
                       json=dict(EXCAVATOR, poisson_ratio=0.4)).json()
    pick = lambda d: next(m for m in d["methods"] if m["key"] == "westergaard")
    assert pick(low)["pressure_kpa"] != pytest.approx(
        pick(high)["pressure_kpa"], rel=1e-3)
    assert "nu = 0.4" in pick(high)["name"]


def test_poisson_ratio_at_the_singularity_is_rejected():
    r = client.post("/api/soil/pipe-surcharge",
                    json=dict(EXCAVATOR, poisson_ratio=0.5))
    assert r.status_code == 422


def test_pressure_bulb_is_returned_and_self_consistent():
    d = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR).json()
    b = d["bulb"]
    assert len(b["grid_kpa"]) == len(b["depth_m"])
    assert all(len(row) == len(b["x_m"]) for row in b["grid_kpa"])
    assert b["peak_kpa"] > 0
    assert b["isolines"]
    assert all(0 < line["level_kpa"] < b["peak_kpa"] for line in b["isolines"])
    assert all(line["segments"] for line in b["isolines"])


def test_both_orientations_are_reported_every_time():
    d = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR).json()
    by = {o["orientation"]: o for o in d["orientations"]}
    assert set(by) == {"across", "along"}
    assert by["across"]["is_current"] is True
    assert by["along"]["is_current"] is False
    # The current orientation must agree with the headline result.
    assert by["across"]["pressure_at_offset_kpa"] == pytest.approx(
        d["live_pressure_kpa"], rel=1e-6)
    assert by["across"]["worst_pressure_kpa"] == pytest.approx(
        d["worst_offset_pressure_kpa"], rel=1e-6)


def test_orientation_comparison_flips_with_the_selection():
    across = client.post("/api/soil/pipe-surcharge",
                         json=dict(EXCAVATOR, orientation="across")).json()
    along = client.post("/api/soil/pipe-surcharge",
                        json=dict(EXCAVATOR, orientation="along")).json()

    def pressures(d):
        return {o["orientation"]: o["pressure_at_offset_kpa"] for o in d["orientations"]}

    # Whichever is selected, the pair of numbers reported must be the same.
    assert pressures(across)["across"] == pytest.approx(pressures(along)["across"], rel=1e-6)
    assert pressures(across)["along"] == pytest.approx(pressures(along)["along"], rel=1e-6)


def test_crossing_is_worse_than_tracking_along_when_centred():
    d = client.post("/api/soil/pipe-surcharge", json=dict(
        EXCAVATOR, cover="0.8 m", machine_offset="0")).json()
    by = {o["orientation"]: o for o in d["orientations"]}
    assert by["across"]["pressure_at_offset_kpa"] > by["along"]["pressure_at_offset_kpa"]
    # But at their respective worst positions they are close, because the
    # worst case for tracking along is one track sat over the pipe.
    ratio = by["across"]["worst_pressure_kpa"] / by["along"]["worst_pressure_kpa"]
    assert 0.8 < ratio < 1.25


def test_methods_carry_their_working_over_http():
    d = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR).json()
    for m in d["methods"]:
        assert m["formula"] and m["substitution"] and m["terms"], m["key"]
        if m["terms_sum_to_total"]:
            total = sum(t["value_kpa"] for t in m["terms"])
            assert total == pytest.approx(m["pressure_kpa"], rel=1e-2), m["key"]
        else:
            assert max(t["value_kpa"] for t in m["terms"]) == pytest.approx(
                m["pressure_kpa"], rel=1e-2), m["key"]


def test_crown_plan_is_returned_for_the_three_dimensional_view():
    d = client.post("/api/soil/pipe-surcharge", json=EXCAVATOR).json()
    cp = d["crown_plan"]
    assert len(cp["grid_kpa"]) == len(cp["y_m"])
    assert all(len(row) == len(cp["x_m"]) for row in cp["grid_kpa"])
    assert cp["peak_kpa"] > 0


# --------------------------------------------------------------------------
# Multi-axle truck loads
# --------------------------------------------------------------------------

TWO_AXLE_TRUCK = {
    "load_type": "truck",
    "truck_axles": [
        {"label": "front", "load_kn": 50.0, "tire_width": "0.3 m", "tire_length": "0.25 m"},
        {"label": "rear", "load_kn": 100.0, "tire_width": "0.3 m", "tire_length": "0.25 m",
         "spacing_from_previous": "4 m"},
    ],
    "truck_axle_width": "1.8 m",
    "orientation": "across",
    "cover": "1.0 m",
    "pipe_od": "600",
    "dla_mode": "none",
}


def test_truck_load_type_roundtrip():
    r = client.post("/api/soil/pipe-surcharge", json=TWO_AXLE_TRUCK)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["total_load_kn"] == pytest.approx(150.0)
    assert len(d["patches"]) == 4


def test_truck_with_dual_tyres():
    payload = dict(TWO_AXLE_TRUCK, truck_axles=[
        {"label": "drive", "load_kn": 200.0, "tires_per_side": 2,
         "tire_width": "0.25 m", "tire_length": "0.3 m", "dual_spacing": "0.35 m"},
    ])
    d = client.post("/api/soil/pipe-surcharge", json=payload).json()
    assert d["ok"] is True
    assert len(d["patches"]) == 4  # 2 sides x 2 duals


def test_truck_from_tire_pressure():
    payload = dict(TWO_AXLE_TRUCK, truck_axles=[
        {"label": "a", "load_kn": 140.0, "tire_width": "0.3 m", "tire_pressure_kpa": 700.0},
    ])
    d = client.post("/api/soil/pipe-surcharge", json=payload).json()
    assert d["ok"] is True
    p = d["patches"][0]
    # width_x_m carries the contact length (along travel = x, crossing the pipe);
    # length_y_m carries the tyre width (across travel).
    assert p["length_y_m"] == pytest.approx(0.3, rel=1e-3)
    assert p["width_x_m"] == pytest.approx((70.0 / 700.0) / 0.3, rel=1e-3)


def test_truck_without_axles_is_reported_as_data():
    d = client.post("/api/soil/pipe-surcharge",
                    json=dict(TWO_AXLE_TRUCK, truck_axles=[])).json()
    assert d["ok"] is False
    assert "axle" in d["error"]


def test_truck_axle_missing_length_or_pressure_is_rejected():
    payload = dict(TWO_AXLE_TRUCK, truck_axles=[
        {"label": "a", "load_kn": 100.0, "tire_width": "0.3 m"},
    ])
    d = client.post("/api/soil/pipe-surcharge", json=payload).json()
    assert d["ok"] is False


# --------------------------------------------------------------------------
# Vehicle presets and comparison
# --------------------------------------------------------------------------

def test_vehicle_presets_lists_cl625_and_cat_320():
    d = client.get("/api/soil/vehicle-presets").json()
    truck_keys = {t["key"] for t in d["trucks"]}
    tracked_keys = {t["key"] for t in d["tracked"]}
    assert "cl625" in truck_keys
    assert "western_star_4700sb" in truck_keys
    assert "cat_320" in tracked_keys

    cl625 = next(t for t in d["trucks"] if t["key"] == "cl625")
    assert sum(a["load_kn"] for a in cl625["axles"]) == pytest.approx(625.0)
    assert cl625["verified"] is False
    assert cl625["assumptions"]


def test_vehicle_comparison_ranks_multiple_vehicles():
    r = client.post("/api/soil/vehicle-comparison", json={
        "vehicles": [
            {"label": "CL-625 truck", "load_type": "truck", "preset_key": "cl625",
             "orientation": "across"},
            {"label": "CAT 320 excavator", "load_type": "tracked", "preset_key": "cat_320",
             "orientation": "across"},
        ],
        "cover": "1.2 m",
        "pipe_od": "600",
        "dla_mode": "none",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert len(d["results"]) == 2
    for res in d["results"]:
        assert res["ok"] is True
        assert res["worst_offset_pressure_kpa"] > 0


def test_vehicle_comparison_with_custom_truck():
    r = client.post("/api/soil/vehicle-comparison", json={
        "vehicles": [
            {"label": "Custom rig", "load_type": "truck", "orientation": "across",
             "truck_axles": [
                 {"label": "a", "load_kn": 100.0, "tire_width": "0.3", "tire_length": "0.3"},
             ],
             "truck_axle_width": "1.8 m"},
        ],
        "cover": "1.0 m", "pipe_od": "600", "dla_mode": "none",
    })
    d = r.json()
    assert d["results"][0]["ok"] is True


def test_vehicle_comparison_reports_bad_vehicle_without_failing_the_others():
    r = client.post("/api/soil/vehicle-comparison", json={
        "vehicles": [
            {"label": "Broken", "load_type": "truck", "orientation": "across"},
            {"label": "CAT 320", "load_type": "tracked", "preset_key": "cat_320"},
        ],
        "cover": "1.0 m", "pipe_od": "600", "dla_mode": "none",
    })
    d = r.json()
    assert d["results"][0]["ok"] is False
    assert d["results"][1]["ok"] is True


def test_vehicle_comparison_unknown_preset_key():
    r = client.post("/api/soil/vehicle-comparison", json={
        "vehicles": [{"label": "x", "load_type": "truck", "preset_key": "nope"}],
        "cover": "1.0 m", "pipe_od": "600",
    })
    d = r.json()
    assert d["results"][0]["ok"] is False
