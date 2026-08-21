"""Round-trip tests for the HTTP layer."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

ROOF_BEAM = {
    "spans": ["18 ft", "12 ft"],
    "supports": ["pin", "roller", "roller"],
    "material_key": "LVL-2.0E-Microllam",
    "section": {"ply_width": '1 3/4"', "depth": '14"', "plies": 2},
    "loads": [
        {"case": "D", "kind": "udl", "area_load_kpa": 0.5, "tributary": "12 ft"},
        {"case": "S", "kind": "udl", "area_load_kpa": 2.16, "tributary": "12 ft"},
    ],
    "conditions": {"service": "dry", "laterally_supported": True,
                   "bearing_length": 140.0},
    "project": "Test residence",
    "member": "B1 hip girder",
}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_materials_listing_includes_lvl_and_flags_sawn():
    r = client.get("/api/beam/materials")
    assert r.status_code == 200
    by_key = {m["key"]: m for m in r.json()}
    assert by_key["LVL-2.0E-Microllam"]["verified"] is True
    assert by_key["SPF-No1No2"]["verified"] is False
    assert 355.6 in [round(d, 1) for d in by_key["LVL-2.0E-Microllam"]["available_depths_mm"]]


def test_design_roundtrip_on_roof_beam():
    r = client.post("/api/beam/design", json=ROOF_BEAM)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["passed"] is True
    assert d["plies"] == 2
    assert d["width_mm"] == pytest.approx(88.9, rel=1e-3)
    assert d["depth_mm"] == pytest.approx(355.6, rel=1e-3)

    by_check = {c["check"]: c for c in d["checks"]}
    assert by_check["moment"]["ratio"] < 0.8
    assert by_check["moment"]["units"] == "kN.m"
    assert "M_r = phi_b" in by_check["moment"]["formula"]
    assert any(f["symbol"] == "K_D" for f in by_check["moment"]["factors"])

    assert len(d["diagrams"]["x_mm"]) == len(d["diagrams"]["moment_min_knm"])
    assert min(d["diagrams"]["moment_min_knm"]) < -35
    assert min(d["diagrams"]["deflection_total_mm"]) < 0

    reactions = {round(r["x_mm"]): r for r in d["reactions"]}
    assert set(reactions) == {0, 5486, 9144}
    centre = reactions[5486]
    assert centre["max_kn"] > 80
    assert centre["required_bearing_mm"] > 100
    assert centre["support_kind"] == "roller"

    cases = {l["case"] for l in d["loads"]}
    assert cases == {"D", "S"}
    assert any(l["is_self_weight"] for l in d["loads"])
    assert d["length_mm"] == pytest.approx(9144.0, rel=1e-3)
    assert [round(x) for x in d["span_positions_mm"]] == [0, 5486, 9144]

    peaks = {p["label"]: p for p in d["diagrams"]["peaks"]}
    assert peaks["Max hogging"]["value"] < -35
    assert peaks["Max sagging"]["value"] > 30
    assert abs(peaks["Max shear"]["value"]) > 40

    assert "<!doctype html>" in d["report_html"].lower()
    assert "CSA O86-19" in d["report_html"]
    assert "B1 hip girder" in d["report_html"]


def test_imperial_and_metric_inputs_agree():
    metric = dict(ROOF_BEAM, spans=[5486.4, 3657.6])
    metric["loads"] = [
        {"case": "D", "kind": "udl", "line_load_kn_m": 1.8288},
        {"case": "S", "kind": "udl", "line_load_kn_m": 7.9004},
    ]
    a = client.post("/api/beam/design", json=ROOF_BEAM).json()
    b = client.post("/api/beam/design", json=metric).json()
    assert a["max_ratio"] == pytest.approx(b["max_ratio"], rel=1e-3)


def test_auto_search_without_section():
    payload = {k: v for k, v in ROOF_BEAM.items() if k != "section"}
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["passed"] is True
    assert d["alternatives"]


def test_custom_material_is_accepted():
    payload = dict(ROOF_BEAM)
    payload["custom_material"] = {
        "name": "Some other LVL 1.9E",
        "fb_mpa": 30.0, "fv_mpa": 3.5, "fcp_mpa": 9.0, "e_mpa": 13100.0,
        "source": "CCMC 12345-R Table 1",
    }
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["material_name"] == "Some other LVL 1.9E"


def test_bad_support_count_is_a_400_not_a_500():
    payload = dict(ROOF_BEAM, supports=["pin", "roller"])
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 400
    assert "support" in r.json()["detail"].lower()


def test_unparseable_length_is_rejected():
    payload = dict(ROOF_BEAM, spans=["eighteen feet", "12 ft"])
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 400


def test_unknown_material_is_rejected():
    payload = dict(ROOF_BEAM, material_key="Unobtainium-9000")
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 400


# --------------------------------------------------------------------------
# Saved projects
# --------------------------------------------------------------------------

import shutil

from api.routers.projects import PROJECT_DIR


@pytest.fixture(autouse=True)
def _clean_projects():
    """Keep saved-project tests from touching real work on disk."""
    backup = None
    if PROJECT_DIR.exists():
        backup = PROJECT_DIR.with_name("projects_test_backup")
        shutil.rmtree(backup, ignore_errors=True)
        PROJECT_DIR.rename(backup)
    yield
    shutil.rmtree(PROJECT_DIR, ignore_errors=True)
    if backup is not None:
        backup.rename(PROJECT_DIR)


def test_project_save_list_load_delete_roundtrip():
    saved = client.post("/api/projects",
                        json={"name": "Smith Residence B1", "payload": ROOF_BEAM})
    assert saved.status_code == 200, saved.text
    pid = saved.json()["id"]
    assert pid == "smith-residence-b1"

    listing = client.get("/api/projects").json()
    assert [p["id"] for p in listing] == [pid]
    assert listing[0]["member"] == "B1 hip girder"

    loaded = client.get(f"/api/projects/{pid}").json()
    assert loaded["payload"]["spans"] == ["18 ft", "12 ft"]
    assert loaded["name"] == "Smith Residence B1"

    # A loaded project must still design successfully.
    again = client.post("/api/beam/design", json=loaded["payload"])
    assert again.status_code == 200
    assert again.json()["passed"] is True

    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get("/api/projects").json() == []


def test_saving_same_name_overwrites_rather_than_duplicating():
    client.post("/api/projects", json={"name": "Same Name", "payload": ROOF_BEAM})
    other = dict(ROOF_BEAM, member="B2 revised")
    client.post("/api/projects", json={"name": "Same Name", "payload": other})
    listing = client.get("/api/projects").json()
    assert len(listing) == 1
    assert listing[0]["member"] == "B2 revised"


def test_missing_project_is_404():
    assert client.get("/api/projects/nope").status_code == 404
    assert client.delete("/api/projects/nope").status_code == 404


def test_project_id_cannot_escape_the_projects_directory():
    for bad in ("../secrets", "..%2Fsecrets", "a/b"):
        r = client.get(f"/api/projects/{bad}")
        assert r.status_code in (400, 404), (bad, r.status_code)


def test_project_payload_is_validated_on_save():
    r = client.post("/api/projects",
                    json={"name": "Bad", "payload": {"spans": ["18 ft"]}})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Live model preview
# --------------------------------------------------------------------------

def test_preview_returns_geometry_loads_and_section():
    r = client.post("/api/beam/preview", json=ROOF_BEAM)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["ok"] is True
    assert d["length_mm"] == pytest.approx(9144.0, rel=1e-4)
    assert [round(x) for x in d["span_positions_mm"]] == [0, 5486, 9144]
    assert d["supports"] == ["pin", "roller", "roller"]

    s = d["section"]
    assert s["plies"] == 2
    assert s["width_mm"] == pytest.approx(88.9, rel=1e-3)
    assert s["depth_mm"] == pytest.approx(355.6, rel=1e-3)
    # Section properties must match the closed form for a rectangle.
    assert s["area_mm2"] == pytest.approx(88.9 * 355.6, rel=1e-3)
    assert s["section_modulus_mm3"] == pytest.approx(88.9 * 355.6**2 / 6, rel=1e-3)
    assert s["inertia_mm4"] == pytest.approx(88.9 * 355.6**3 / 12, rel=1e-3)

    cases = [l["case"] for l in d["loads"]]
    assert cases.count("D") == 2  # applied dead plus self weight
    assert any(l["is_self_weight"] for l in d["loads"])
    assert "Microllam" in d["description"]
    assert "fastened to act together" in d["description"]


def test_preview_matches_what_design_analyses():
    """The drawing must not be able to disagree with the calculation."""
    p = client.post("/api/beam/preview", json=ROOF_BEAM).json()
    d = client.post("/api/beam/design", json=ROOF_BEAM).json()

    assert p["length_mm"] == pytest.approx(d["length_mm"])
    assert p["span_positions_mm"] == pytest.approx(d["span_positions_mm"])
    assert p["section"]["self_weight_kn_m"] == pytest.approx(d["self_weight_kn_m"])

    def signature(loads):
        return sorted(
            (l["case"], l["kind"], round(l["magnitude"], 6), l["is_self_weight"])
            for l in loads
        )

    assert signature(p["loads"]) == signature(d["loads"])


def test_preview_reports_parse_errors_as_data_not_http_errors():
    r = client.post("/api/beam/preview", json=dict(ROOF_BEAM, spans=["eighteen", "12 ft"]))
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "eighteen" in r.json()["error"]


def test_preview_reports_mismatched_support_count():
    r = client.post("/api/beam/preview", json=dict(ROOF_BEAM, supports=["pin", "roller"]))
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert "3 supports" in d["error"]


def test_preview_without_a_section_explains_auto_sizing():
    payload = {k: v for k, v in ROOF_BEAM.items() if k != "section"}
    d = client.post("/api/beam/preview", json=payload).json()
    assert d["ok"] is True
    assert d["section"] is None
    assert "Auto-sizing" in d["description"]
    # No section means no self weight can be included yet.
    assert not any(l["is_self_weight"] for l in d["loads"])


def test_preview_single_ply_description_reads_naturally():
    payload = dict(ROOF_BEAM, section={"ply_width": '1 3/4"', "depth": '14"', "plies": 1})
    d = client.post("/api/beam/preview", json=payload).json()
    assert "a single" in d["description"]
    assert "fastened to act together" not in d["description"]


# --------------------------------------------------------------------------
# Point loads
# --------------------------------------------------------------------------

def test_point_load_on_only_one_case_does_not_break_the_envelope():
    """Regression: a point load carried by only D (not S) used to leave D's
    mesh with an extra break the other cases lacked, so min()/max() across
    cases failed with a numpy broadcast error."""
    payload = dict(ROOF_BEAM, loads=ROOF_BEAM["loads"] + [
        {"case": "D", "kind": "point", "p_kn": 12.0, "x": "9 ft"},
    ])
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()

    n = len(d["diagrams"]["x_mm"])
    for key in ("shear_min_kn", "shear_max_kn", "moment_min_knm",
                "moment_max_knm", "deflection_live_mm", "deflection_total_mm"):
        assert len(d["diagrams"][key]) == n, key

    loads = {(l["case"], l["kind"]) for l in d["loads"]}
    assert ("D", "point") in loads


def test_point_load_and_partial_udl_together_across_mixed_cases():
    """A harder version: a point load on D and a partial UDL on S, neither
    case sharing the other's break points."""
    payload = dict(ROOF_BEAM, loads=[
        {"case": "D", "kind": "udl", "area_load_kpa": 0.5, "tributary": "12 ft"},
        {"case": "D", "kind": "point", "p_kn": 8.0, "x": "4 m"},
        {"case": "S", "kind": "udl", "area_load_kpa": 2.16, "tributary": "12 ft",
         "x_start": "2 m", "x_end": "7 m"},
    ])
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    n = len(d["diagrams"]["x_mm"])
    assert all(len(d["diagrams"][k]) == n for k in
               ("shear_min_kn", "shear_max_kn", "moment_min_knm", "moment_max_knm"))


def test_point_load_only_beam_still_designs():
    payload = dict(ROOF_BEAM, loads=[
        {"case": "L", "kind": "point", "p_kn": 20.0, "x": "9 m"},
    ])
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    assert len(r.json()["reactions"]) == 3


def test_partial_udl_only_covers_its_stated_extent():
    """A UDL confined to part of the span must not act outside that range."""
    payload = dict(ROOF_BEAM)
    payload["loads"] = [
        {"case": "D", "kind": "udl", "area_load_kpa": 0.5, "tributary": "12 ft"},
        {"case": "S", "kind": "udl", "area_load_kpa": 2.16, "tributary": "12 ft",
         "x_start": "3 ft", "x_end": "12 ft"},
    ]
    r = client.post("/api/beam/design", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()

    snow = next(l for l in d["loads"] if l["case"] == "S")
    assert snow["x_start_mm"] == pytest.approx(3 * 304.8, rel=1e-4)
    assert snow["x_end_mm"] == pytest.approx(12 * 304.8, rel=1e-4)
    assert snow["x_end_mm"] - snow["x_start_mm"] < d["length_mm"]

    n = len(d["diagrams"]["x_mm"])
    assert all(len(d["diagrams"][k]) == n for k in
               ("shear_min_kn", "shear_max_kn", "moment_min_knm", "moment_max_knm"))


def test_preview_echoes_partial_udl_extent():
    payload = dict(ROOF_BEAM)
    payload["loads"] = [
        {"case": "S", "kind": "udl", "area_load_kpa": 2.16, "tributary": "12 ft",
         "x_start": "3 ft", "x_end": "12 ft"},
    ]
    d = client.post("/api/beam/preview", json=payload).json()
    assert d["ok"] is True
    load = d["loads"][0]
    assert load["x_start_mm"] == pytest.approx(3 * 304.8, rel=1e-4)
    assert load["x_end_mm"] == pytest.approx(12 * 304.8, rel=1e-4)
