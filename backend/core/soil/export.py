"""Self-describing export of a pipe surcharge analysis.

Written for an AI tool reading the workspace, so the design rule throughout is
that **no field should be ambiguous read in isolation**:

* every numeric field name carries its unit (``load_kn``, ``contact_length_m``,
  ``soil_unit_weight_kn_per_m3``), and a ``units`` block states them again;
* ``assumptions`` and ``verified`` are structured data, not prose buried in a
  note - an agent must be able to see that a number is unconfirmed without
  parsing English;
* a ``reimport`` block carries the exact request payload back, so the file
  round-trips into the app rather than being a dead end.

One builder produces the payload; the markdown renderer is a view over the same
dict. Two independent renderers would drift, and a human and an agent reading
the same export must not be told different things.

Pure: no FastAPI, no filesystem, matching the rest of ``core/``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA = "engineering-design-toolkit/pipe-surcharge"
SCHEMA_VERSION = "1.0.0"

UNITS = {
    "length": "m unless the field name says mm",
    "load": "kN",
    "pressure": "kPa",
    "unit_weight": "kN/m3",
    "area": "m2",
    "angle": "degrees",
    "convention": (
        "Field names carry their own units as a suffix. Depths are positive "
        "downward from ground surface. In the vehicle frame u runs along "
        "travel and v across it, with u = 0 at the wheelbase midpoint."
    ),
}


# The point idealisation collapses each contact area to a point, which blows up
# at shallow cover - it runs 3-4x Boussinesq at 1 m and the UI already keeps it
# off its charts for swamping the scale. It is a teaching comparison showing the
# error in treating a footprint as a point, never a candidate design value, so
# it must not be able to win "governing": an agent reading this file has no way
# to know that from the number alone.
_NOT_A_DESIGN_CANDIDATE = {"boussinesq_point"}


def build_export(
    *,
    result,
    vehicle: dict | None,
    request_payload: dict,
    project: str = "",
    member: str = "",
    designer: str = "",
    soil_unit_weight_kn_m3: float = 0.0,
    poisson_ratio: float = 0.0,
    preset_source: str = "",
    preset_verified: bool | None = None,
    preset_assumptions: list[str] | None = None,
) -> dict:
    """Assemble the export payload from an analysis result.

    ``vehicle`` is the geometry block, or ``None`` for custom rectangle loads.
    """
    candidates = [m for m in result.methods if m.key not in _NOT_A_DESIGN_CANDIDATE]
    governing = max(candidates, key=lambda m: m.pressure_kpa, default=None)
    primary = next((m for m in result.methods if m.key == "boussinesq"), None)

    # Every method, not just the governing one. An agent asked "is this
    # conservative?" needs the spread, and picking one number for it here would
    # be answering that question on its behalf.
    methods = [
        {
            "key": m.key,
            "name": m.name,
            "pressure_kpa": round(m.pressure_kpa, 3),
            "basis": m.basis,
            # False means the method's own transcription is unconfirmed - it is
            # not a comment on the arithmetic.
            "verified": m.verified,
            "note": m.note,
            # Marks the point idealisation: a comparison that shows the error in
            # treating a footprint as a point, not a value anything is designed to.
            "is_design_candidate": m.key not in _NOT_A_DESIGN_CANDIDATE,
            "formula": m.formula,
            "substitution": m.substitution,
            "terms": [
                {"label": t.label, "detail": t.detail,
                 "value_kpa": round(t.value_kpa, 4)}
                for t in m.terms
            ],
            "terms_sum_to_total": m.terms_sum_to_total,
        }
        for m in result.methods
    ]

    assumptions = list(preset_assumptions or [])
    if vehicle:
        for axle in vehicle["axles"]:
            if axle["contact_length_is_derived"]:
                assumptions.append(
                    f"{axle['label']}: contact length "
                    f"{axle['contact_length_m'] * 1000:.0f} mm is not a stated "
                    f"dimension - it was computed from an assumed "
                    f"{axle['tire_pressure_kpa'] or 0:.0f} kPa inflation pressure, so "
                    f"its reported contact pressure only returns that assumption."
                )
    unverified = [m["name"] for m in methods if not m["verified"]]
    if unverified:
        assumptions.append(
            "Unverified method transcriptions, not to be relied on without "
            "checking against the source code of practice: " + ", ".join(unverified) + "."
        )

    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Engineering Design Toolkit - pipe surcharge tool",
        "units": UNITS,
        "caveat": (
            "These are FREE-FIELD vertical stresses in an elastic half-space. "
            "They are not pipe wall stresses, ring deflections or a design "
            "check: no soil-structure interaction, bedding factor, pipe "
            "stiffness or trench condition is modelled. An engineer must apply "
            "the relevant code (CSA S6, CSA B182, AASHTO) to turn these into a "
            "design outcome."
        ),
        "project": {
            "name": project,
            "member": member,
            "designer": designer,
        },
        "site": {
            "cover_m": round(result.cover_m, 4),
            "pipe_od_m": round(result.pipe_od_m, 4),
            "crown_depth_m": round(result.crown_depth_m, 4),
            "machine_offset_m": round(result.machine_offset_m, 4),
            "soil_unit_weight_kn_per_m3": soil_unit_weight_kn_m3,
            "poisson_ratio": poisson_ratio,
            "dynamic_load_allowance": round(result.dla, 4),
            "soil_overburden_pressure_kpa": round(result.soil_pressure_kpa, 3),
        },
        "vehicle": (
            {**vehicle, "source": preset_source, "verified": preset_verified}
            if vehicle else None
        ),
        "load_description": result.load_description,
        "total_load_kn": round(result.total_load_kn, 3),
        "results": {
            # Boussinesq is the tool's primary result; "governing" is the
            # highest of the methods that could legitimately be designed to.
            # They are reported separately because they answer different
            # questions and can differ.
            "primary_method_key": primary.key if primary else "",
            "primary_pressure_kpa": round(primary.pressure_kpa, 3) if primary else 0.0,
            "governing_method_key": governing.key if governing else "",
            "governing_pressure_kpa": round(governing.pressure_kpa, 3) if governing else 0.0,
            "governing_excludes": sorted(_NOT_A_DESIGN_CANDIDATE),
            "crown_pressure_kpa": round(result.live_pressure_kpa, 3),
            "average_over_pipe_kpa": round(result.average_over_pipe_kpa, 3),
            "load_per_m_of_pipe_kn_per_m": round(result.load_per_m_kn_m, 3),
            "live_to_dead_ratio": round(result.live_to_dead_ratio, 4),
            "worst_offset_m": round(result.worst_offset_m, 4),
            "worst_offset_pressure_kpa": round(result.worst_offset_pressure_kpa, 3),
            "current_offset_is_worst": result.offset_is_worst,
            "methods": methods,
        },
        "assumptions": assumptions,
        "warnings": list(result.warnings),
        "reimport": {
            "note": (
                "POST this object to /api/soil/pipe-surcharge to reproduce this "
                "analysis exactly."
            ),
            "endpoint": "/api/soil/pipe-surcharge",
            "payload": request_payload,
        },
    }


# --------------------------------------------------------------------------
# Markdown view over the same payload
# --------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *["| " + " | ".join(r) + " |" for r in rows],
    ]


def render_markdown(data: dict) -> str:
    """Human- and LLM-readable view of the export payload."""
    v = data["vehicle"]
    site = data["site"]
    res = data["results"]
    project = data["project"]

    title = (f"{project['name']} — pipe surcharge" if project["name"]
             else "Pipe surcharge analysis")
    lines: list[str] = [f"# {title}", ""]

    meta = [f"**{k}:** {project[k]}" for k in ("member", "designer") if project[k]]
    if meta:
        lines += ["  \n".join(meta), ""]
    lines += [f"*Generated {data['generated_at']} by {data['generated_by']}.*", ""]

    # The caveat leads. It is the thing most likely to be skipped and most
    # consequential if it is.
    lines += [f"> **What this is not.** {data['caveat']}", ""]

    lines += ["## Result", "",
              f"**{res['crown_pressure_kpa']:.1f} kPa** free-field vertical stress at the "
              f"pipe crown under {site['cover_m']:.2f} m of cover "
              f"({res['load_per_m_of_pipe_kn_per_m']:.1f} kN per metre of pipe, "
              f"{res['live_to_dead_ratio']:.2f}× the "
              f"{site['soil_overburden_pressure_kpa']:.1f} kPa soil overburden).", ""]
    if not res["current_offset_is_worst"]:
        lines += [f"> This is **not** the worst machine position. At "
                  f"{res['worst_offset_m']:+.2f} m the crown stress rises to "
                  f"**{res['worst_offset_pressure_kpa']:.1f} kPa**.", ""]

    # Assumptions get their own heading, ahead of the numbers they qualify.
    if data["assumptions"]:
        lines += ["## Assumptions — must be confirmed", ""]
        lines += [f"{i}. {a}" for i, a in enumerate(data["assumptions"], 1)]
        lines += [""]

    if v:
        noun = v["contact_noun"]
        lines += ["## Vehicle configuration", "",
                  f"**{v['axle_count']}** {'track set' if v['is_tracked'] else 'axle line(s)'}, "
                  f"**{v['total_load_kn']:.0f} kN** total, gauge **{v['gauge_m']:.2f} m**"
                  + (f", wheelbase **{v['wheelbase_m']:.2f} m**" if v["wheelbase_m"] else "")
                  + f", travelling **{'across' if v['orientation'] == 'across' else 'along'}** the pipe.", ""]
        if v.get("source"):
            lines += [f"Source: {v['source']}", ""]
        if v.get("verified") is False:
            lines += ["> This vehicle is an **unverified transcription**. "
                      "Confirm every dimension against the machine on site.", ""]
        lines += _table(
            ["Axle", f"Load (kN)", f"Per {noun} (kN)", f"{noun.title()}s/side",
             "Width (mm)", "Contact length (mm)", "Dual spacing (mm)",
             "Spacing from previous (m)"],
            [[
                a["label"],
                f"{a['load_kn']:.1f}",
                f"{a['wheel_load_kn']:.1f}",
                str(a["tires_per_side"]),
                f"{a['tire_width_m'] * 1000:.0f}",
                f"{a['contact_length_m'] * 1000:.0f}"
                + (" *(derived)*" if a["contact_length_is_derived"] else ""),
                "—" if a["dual_spacing_m"] is None else f"{a['dual_spacing_m'] * 1000:.0f}",
                "—" if a["spacing_from_previous_m"] is None
                else f"{a['spacing_from_previous_m']:.2f}",
            ] for a in v["axles"]],
        )
        lines += [""]
    else:
        lines += ["## Load", "", data["load_description"],
                  f"\nTotal **{data['total_load_kn']:.1f} kN**.", ""]

    lines += ["## Site", ""]
    lines += _table(["Property", "Value"], [
        ["Depth of cover", f"{site['cover_m']:.3f} m"],
        ["Pipe outside diameter", f"{site['pipe_od_m']:.3f} m"],
        ["Depth to crown", f"{site['crown_depth_m']:.3f} m"],
        ["Machine offset from pipe", f"{site['machine_offset_m']:+.3f} m"],
        ["Soil unit weight", f"{site['soil_unit_weight_kn_per_m3']:.1f} kN/m³"],
        ["Poisson's ratio", f"{site['poisson_ratio']:.2f}"],
        ["Dynamic load allowance", f"{site['dynamic_load_allowance']:.2f}"],
    ])
    lines += [""]

    lines += ["## Methods compared at crown level", ""]
    lines += _table(
        ["Method", "Crown pressure (kPa)", "Verified", "Design candidate", "Basis"],
        [[
            m["name"],
            f"{m['pressure_kpa']:.1f}",
            "yes" if m["verified"] else "**no**",
            "yes" if m["is_design_candidate"] else "**no — comparison only**",
            m["basis"].replace("\n", " "),
        ] for m in res["methods"]],
    )
    lines += ["",
              f"Primary result: **{res['primary_method_key']}** at "
              f"{res['primary_pressure_kpa']:.1f} kPa. "
              f"Highest of the methods that could be designed to: "
              f"**{res['governing_method_key']}** at "
              f"{res['governing_pressure_kpa']:.1f} kPa.", ""]
    excluded = [m["name"] for m in res["methods"] if not m["is_design_candidate"]]
    if excluded:
        lines += ["> Excluded from that comparison: " + ", ".join(excluded) +
                  ". The point idealisation collapses each contact area to a "
                  "point and diverges at shallow cover; it shows the error in "
                  "that simplification and is not a value to design to.", ""]

    if data["warnings"]:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in data["warnings"]]
        lines += [""]

    lines += ["## Reproducing this", "",
              f"POST the `reimport.payload` object from the companion JSON file to "
              f"`{data['reimport']['endpoint']}`.", ""]

    return "\n".join(lines)
