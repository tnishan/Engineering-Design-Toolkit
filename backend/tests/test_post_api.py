"""HTTP round-trip tests for post design."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SAWN_POST = {
    "length": "8 ft",
    "axial_kn": {"D": 12.0, "S": 30.0},
    "material_key": "SPF-No1No2",
    "section": {"ply_width": 38, "depth": 140, "plies": 3},
    "project": "Test residence",
    "member": "P1",
}


def test_end_conditions_endpoint():
    r = client.get("/api/post/end-conditions")
    assert r.status_code == 200
    by_key = {e["key"]: e for e in r.json()}
    assert by_key["pinned-pinned"]["ke"] == 1.0
    assert by_key["fixed-fixed"]["ke"] == 0.65


def test_scl_products_endpoint_lists_sizes():
    r = client.get("/api/post/scl-products")
    assert r.status_code == 200
    by_key = {p["key"]: p for p in r.json()}
    psl = by_key["PSL-1.8E-Column"]
    assert len(psl["sizes"]) == 6
    assert psl["sizes"][0]["label"] == '3 1/2" x 3 1/2"'


def test_sawn_post_roundtrip():
    r = client.post("/api/post/design", json=SAWN_POST)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["method"] == "O86 Cl. 6.5.6"
    assert d["plies"] == 3
    assert d["width_mm"] == pytest.approx(114.0)
    assert d["slenderness"] == pytest.approx(2438.4 / 114.0, rel=1e-2)
    assert d["slenderness_axis"] == "width"

    by_check = {c["check"]: c for c in d["checks"]}
    assert "compression" in by_check and "bearing" in by_check
    assert "P_r = phi_c" in by_check["compression"]["formula"]
    assert any(f["symbol"] == "K_C" for f in by_check["compression"]["factors"])
    assert any(f["symbol"] == "K_Zcg" for f in by_check["compression"]["factors"])

    assert d["capacity_curve"]
    assert "<!doctype html>" in d["report_html"].lower()
    assert "P1" in d["report_html"]
    assert "CSA O86" in d["report_html"]


def test_scl_post_roundtrip_uses_published_table():
    r = client.post("/api/post/design", json={
        "length": "10 ft",
        "axial_kn": {"D": 12.0, "S": 30.0},
        "scl_product": "PSL-1.8E-Column",
        "scl_size_index": 2,
        "member": "P2",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["method"] == "manufacturer table"
    # 17,110 lb published at 10 ft for 3.5 x 7.
    assert d["resistance_kn"] == pytest.approx(17110 * 4.4482216153 / 1000, rel=1e-5)
    assert any("does not reproduce" in w for w in d["warnings"])
    assert d["capacity_curve"]


def test_too_slender_post_is_a_400():
    r = client.post("/api/post/design", json=dict(
        SAWN_POST, length="20 ft", section={"ply_width": 38, "depth": 140, "plies": 1}))
    assert r.status_code == 400
    assert "50" in r.json()["detail"]


def test_scl_beyond_published_length_is_a_400():
    r = client.post("/api/post/design", json={
        "length": "20 ft",
        "axial_kn": {"D": 10.0},
        "scl_product": "PSL-1.8E-Column",
        "scl_size_index": 0,
    })
    assert r.status_code == 400
    assert "published" in r.json()["detail"]


def test_missing_section_is_a_400():
    payload = {k: v for k, v in SAWN_POST.items() if k != "section"}
    r = client.post("/api/post/design", json=payload)
    assert r.status_code == 400


def test_no_load_is_a_400():
    r = client.post("/api/post/design", json=dict(SAWN_POST, axial_kn={}))
    assert r.status_code == 400


def test_beam_reaction_can_be_carried_into_a_post():
    """The 84.5 kN centre reaction from the roof beam needs a real post."""
    beam = client.post("/api/beam/design", json={
        "spans": ["18 ft", "12 ft"],
        "supports": ["pin", "roller", "roller"],
        "material_key": "LVL-2.0E-Microllam",
        "section": {"ply_width": '1 3/4"', "depth": '14"', "plies": 2},
        "loads": [
            {"case": "D", "kind": "udl", "area_load_kpa": 0.5, "tributary": "12 ft"},
            {"case": "S", "kind": "udl", "area_load_kpa": 2.16, "tributary": "12 ft"},
        ],
        "conditions": {"bearing_length": 140.0},
    }).json()

    centre = max(beam["reactions"], key=lambda r: r["max_kn"])
    assert centre["max_kn"] > 80

    # Split the factored reaction back into cases in the same proportion as the
    # applied loads, so the post sees an equivalent unfactored pair.
    post = client.post("/api/post/design", json={
        "length": "9 ft",
        "axial_kn": {"D": 6.9, "S": 29.8},
        "scl_product": "PSL-1.8E-Column",
        "scl_size_index": 3,
    })
    assert post.status_code == 200, post.text
    assert post.json()["passed"] is True
