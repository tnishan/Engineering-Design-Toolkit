"""The AI-tool export: does it round-trip, and does it carry its caveats?

The export exists to be read by something that was not in the room when the
analysis was run - another engineer, or an agent working the repo. So the
tests here are about self-description: units on every field, assumptions as
data rather than prose, and a payload that feeds back through the API and
lands on the same number.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.soil import EXPORT_DIR

client = TestClient(app)


CL625_REQUEST = {
    "load_type": "truck",
    "orientation": "across",
    "vehicle_preset_key": "cl625",
    "truck_axle_width": "1.8 m",
    "truck_axles": [
        {"label": "Axle 1", "load_kn": 50.0, "tire_width": "300",
         "tire_length": "119", "spacing_from_previous": "0"},
        {"label": "Axle 2", "load_kn": 140.0, "tire_width": "300",
         "tire_length": "333", "spacing_from_previous": "3.6 m"},
        {"label": "Axle 3", "load_kn": 140.0, "tire_width": "300",
         "tire_length": "333", "spacing_from_previous": "1.2 m"},
        {"label": "Axle 4", "load_kn": 175.0, "tire_width": "300",
         "tire_length": "417", "spacing_from_previous": "6.6 m"},
        {"label": "Axle 5", "load_kn": 120.0, "tire_width": "300",
         "tire_length": "286", "spacing_from_previous": "6.6 m"},
    ],
    "cover": "1.5 m",
    "pipe_od": "600",
    "project": "Highway 7 culvert",
    "member": "CSP 600",
    "engineer": "N. Thapa",
}


# A machine sitting squarely over the pipe, where collapsing the footprint to a
# point diverges hardest from the real integrated stress.
TRACKED_OVER_PIPE = {
    "load_type": "truck",
    "vehicle_preset_key": "cat_320",
    "truck_axle_width": "2.408 m",
    "truck_axles": [{"label": "Tracks", "load_kn": 220.6,
                     "tire_width": "762", "tire_length": "4.47 m"}],
    "cover": "1.0 m",
}


@pytest.fixture
def export(tmp_path, monkeypatch):
    """Write exports to a temp folder, not into the developer's repo."""
    monkeypatch.setattr("api.routers.soil.EXPORT_DIR", tmp_path)

    def run(name="Test export", **overrides):
        payload = {**CL625_REQUEST, **overrides}
        r = client.post("/api/soil/export", json={"name": name, "payload": payload})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"], body["error"]
        return body

    return run


# --------------------------------------------------------------------------
# Round trip - the point of the reimport block
# --------------------------------------------------------------------------

def test_reimport_payload_reproduces_the_same_crown_pressure(export):
    """An export that cannot be fed back in is a dead end. This is the check
    that the file is a working record rather than a screenshot in JSON."""
    body = export()
    exported = body["data"]["results"]["crown_pressure_kpa"]

    again = client.post("/api/soil/pipe-surcharge",
                        json=body["data"]["reimport"]["payload"])
    assert again.status_code == 200
    reanalysed = again.json()
    assert reanalysed["ok"], reanalysed["error"]
    assert reanalysed["live_pressure_kpa"] == pytest.approx(exported, rel=1e-9)


def test_reimport_names_the_endpoint_that_accepts_it(export):
    assert export()["data"]["reimport"]["endpoint"] == "/api/soil/pipe-surcharge"


# --------------------------------------------------------------------------
# Self-description
# --------------------------------------------------------------------------

def test_export_declares_its_schema_and_units(export):
    data = export()["data"]
    assert data["schema"].endswith("pipe-surcharge")
    assert data["schema_version"]
    assert data["generated_at"]
    assert data["units"]["load"] == "kN"
    assert data["units"]["pressure"] == "kPa"


def test_every_numeric_leaf_field_names_its_unit(export):
    """A reader picking one field out of the file must not have to guess. The
    unit belongs in the name, because the name is what survives being quoted
    out of context."""
    unitless_ok = {
        "schema_version", "axle_count", "index", "tires_per_side", "tyre_index",
        "contact_patch_count", "poisson_ratio", "dynamic_load_allowance",
        "live_to_dead_ratio", "spread_factor", "dla", "axle_index",
        "wheel_load_kn", "total_load_kn",
    }
    suffixes = ("_m", "_kn", "_kpa", "_m2", "_m3", "_kn_per_m", "_kn_per_m3",
                "_deg", "_ratio", "_count", "_index")
    offenders: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if path.startswith("reimport"):
                    continue  # verbatim request echo, not our field naming
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if k not in unitless_ok and not k.endswith(suffixes):
                        offenders.append(f"{path}.{k}")
                else:
                    walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(export()["data"])
    assert not offenders, offenders


def test_assumptions_are_structured_data_not_prose(export):
    """An agent must be able to see that a figure is unconfirmed without
    parsing English out of a note field."""
    data = export()["data"]
    assert isinstance(data["assumptions"], list)
    assert data["assumptions"], "a CL-625 export always carries assumptions"
    assert all(isinstance(a, str) and a for a in data["assumptions"])


def test_preset_assumptions_and_source_reach_the_export(export):
    """vehicle_preset_key is the only route by which the preset's provenance
    gets to the server - the axles themselves arrive as bare numbers."""
    data = export()["data"]
    assert "CL-625" in data["vehicle"]["source"]
    assert data["vehicle"]["verified"] is False
    assert any("700 kPa" in a or "inflation" in a for a in data["assumptions"])


def test_unverified_methods_are_named_in_the_assumptions(export):
    data = export()["data"]
    unverified = [m["name"] for m in data["results"]["methods"] if not m["verified"]]
    assert unverified
    joined = " ".join(data["assumptions"])
    for name in unverified:
        assert name in joined


def test_free_field_caveat_is_present_and_says_what_this_is_not(export):
    caveat = export()["data"]["caveat"].lower()
    assert "free-field" in caveat
    assert "not" in caveat


def test_point_idealisation_can_never_be_reported_as_governing(export):
    """It runs several times Boussinesq at shallow cover - the UI keeps it off
    its own charts for swamping the scale. An agent reading this file has no
    way to know that from the number, so letting it win "governing" would hand
    over a design value the tool itself does not believe."""
    data = export(**TRACKED_OVER_PIPE)["data"]
    by_key = {m["key"]: m for m in data["results"]["methods"]}
    point = by_key["boussinesq_point"]

    assert point["is_design_candidate"] is False
    assert data["results"]["governing_method_key"] != "boussinesq_point"
    assert "boussinesq_point" in data["results"]["governing_excludes"]
    # The premise of the test: here it really is the biggest number in the
    # table, so excluding it is doing actual work rather than passing by luck.
    assert point["pressure_kpa"] > max(
        m["pressure_kpa"] for m in data["results"]["methods"]
        if m["is_design_candidate"])


def test_markdown_says_the_point_idealisation_is_comparison_only(export):
    md = export(**TRACKED_OVER_PIPE)["markdown"]
    assert "comparison only" in md
    assert "not a value to design to" in md


def test_primary_result_is_boussinesq(export):
    res = export()["data"]["results"]
    assert res["primary_method_key"] == "boussinesq"
    assert res["primary_pressure_kpa"] == pytest.approx(res["crown_pressure_kpa"])


def test_all_methods_are_exported_not_just_the_governing_one(export):
    """Picking one number here would be answering "is this conservative?" on
    the reader's behalf."""
    data = export()["data"]
    keys = {m["key"] for m in data["results"]["methods"]}
    assert "boussinesq" in keys
    assert len(keys) >= 4
    assert data["results"]["governing_method_key"] in keys


# --------------------------------------------------------------------------
# Files on disk
# --------------------------------------------------------------------------

def test_both_files_are_written_in_one_action(export, tmp_path):
    body = export(name="Highway 7 culvert")
    assert (tmp_path / "highway-7-culvert.json").exists()
    assert (tmp_path / "highway-7-culvert.md").exists()
    assert body["json_path"].endswith(".json")
    assert body["markdown_path"].endswith(".md")


def test_written_json_matches_the_returned_payload(export, tmp_path):
    body = export(name="Roundtrip")
    on_disk = json.loads((tmp_path / "roundtrip.json").read_text(encoding="utf-8"))
    assert on_disk == body["data"]


def test_export_name_cannot_escape_the_export_folder(export, tmp_path):
    """The name is free text from the browser, so it is slugged before it
    touches the filesystem."""
    body = export(name="../../etc/passwd")
    written = list(tmp_path.iterdir())
    assert written, "files should still be written, just somewhere safe"
    for path in written:
        assert path.parent == tmp_path
    assert ".." not in body["json_path"]


# --------------------------------------------------------------------------
# Markdown view
# --------------------------------------------------------------------------

def test_markdown_leads_with_the_caveat_before_any_number(export):
    md = export()["markdown"]
    assert md.index("What this is not") < md.index("## Result")


def test_markdown_lists_the_assumptions_under_their_own_heading(export):
    md = export()["markdown"]
    assert "## Assumptions — must be confirmed" in md
    assert md.index("## Assumptions") < md.index("## Site")


def test_markdown_axle_table_shows_loads_and_marks_derived_lengths(export):
    md = export()["markdown"]
    assert "## Vehicle configuration" in md
    for load in ("50.0", "140.0", "175.0", "120.0"):
        assert load in md
    assert "18.00 m" in md  # wheelbase


def test_markdown_flags_an_unverified_vehicle(export):
    assert "unverified transcription" in export()["markdown"]


def test_markdown_shows_an_em_dash_not_zero_for_absent_dual_spacing(export):
    """CL-625 runs singles throughout. "0 mm" would assert a measurement that
    does not exist."""
    md = export()["markdown"]
    assert "| — |" in md


# --------------------------------------------------------------------------
# Custom loads are not a vehicle
# --------------------------------------------------------------------------

def test_custom_rectangles_export_without_a_vehicle_block(export):
    body = export(
        load_type="custom",
        vehicle_preset_key="",
        custom_patches=[{"label": "crane pad", "x": "0", "y": "0",
                         "width_x": "1.5 m", "length_y": "1.5 m",
                         "total_kn": 300.0}],
    )
    assert body["data"]["vehicle"] is None
    assert "## Load" in body["markdown"]
    assert "## Vehicle configuration" not in body["markdown"]


def test_bad_input_is_reported_without_writing_a_file(export, tmp_path):
    r = client.post("/api/soil/export", json={
        "name": "Broken", "payload": {**CL625_REQUEST, "cover": "not a length"},
    })
    assert r.status_code == 200
    body = r.json()
    assert not body["ok"]
    assert body["error"]
    assert not list(tmp_path.iterdir())
