"""Printable calculation report for buried-pipe surcharge."""

from __future__ import annotations

from datetime import date

from jinja2 import Environment

_ENV = Environment(autoescape=True)

_TEMPLATE = _ENV.from_string(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ project }} - {{ member }} - Buried Pipe Surcharge</title>
<style>
  @page { size: A4 portrait; margin: 12mm 12mm; }
  * { box-sizing: border-box; }
  body { font: 11px/1.45 "Segoe UI", Arial, sans-serif; color: #111; margin: 0; background: #e2e8f0; padding: 24px 12px; }
  .report-container { max-width: 850px; margin: 0 auto; background: #ffffff; padding: 28px 32px; border-radius: 6px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
  h1 { font-size: 16px; margin: 0 0 2px; }
  h2 { font-size: 13px; margin: 16px 0 6px; padding-bottom: 3px;
       border-bottom: 1.5px solid #333; page-break-after: avoid; }
  .hdr { border: 1px solid #333; padding: 8px 10px; margin-bottom: 4px; }
  .hdr .row { display: flex; justify-content: space-between; gap: 12px; }
  .muted { color: #555; }
  table { border-collapse: collapse; width: 100%; margin: 6px 0 10px;
          page-break-inside: avoid; }
  th, td { border: 1px solid #bbb; padding: 3.5px 6px; text-align: left;
           vertical-align: top; }
  th { background: #eee; font-weight: 600; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .primary { background: #eef4fb; font-weight: 600; }
  .formula { font-family: "Cascadia Mono", Consolas, monospace; font-size: 10px;
             background: #f6f6f6; padding: 5px 7px; margin: 4px 0; white-space: pre-wrap; border: 1px solid #e2e8f0; border-radius: 4px; }
  .warn { border-left: 3px solid #c47f00; background: #fff8e8; padding: 6px 9px;
          margin: 5px 0; page-break-inside: avoid; }
  .method { border: 1px solid #999; padding: 8px 10px; margin: 10px 0;
            page-break-inside: avoid; border-radius: 4px; background: #fafafa; }
  .diagram-box { text-align: center; margin: 8px 0; padding: 4px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; }
  .verify { border: 1.5px solid #b40000; background: #fff2f2; padding: 8px 10px;
            margin: 10px 0; }
  footer { margin-top: 18px; border-top: 1px solid #999; padding-top: 5px;
           font-size: 9.5px; color: #555; }
  .sig { margin-top: 20px; display: flex; gap: 28px; }
  .sig div { flex: 1; border-top: 1px solid #333; padding-top: 3px; font-size: 10px; }

  @media print {
    body { background: #fff; padding: 0; }
    .report-container { max-width: 100%; margin: 0; padding: 0; box-shadow: none; border-radius: 0; }
  }
</style>
</head>
<body>

<div class="report-container">
<div class="hdr">
  <div class="row"><h1>Buried Pipe Surcharge from Surface Plant</h1><div>{{ today }}</div></div>
  <div class="row muted">
    <div><b>Project:</b> {{ project }}</div>
    <div><b>Element:</b> {{ member }}</div>
    <div><b>By:</b> {{ engineer }}</div>
  </div>
  <div class="row muted">
    <div><b>Basis:</b> Boussinesq elastic half-space</div>
    <div><b>Crown surcharge:</b> {{ '%.1f'|format(r.live_pressure_kpa) }} kPa</div>
  </div>
</div>

<div class="verify">
  <b>Comparative analysis only.</b> This calculation gives the FREE-FIELD
  vertical stress in undisturbed ground at the depth of the pipe crown. It does
  not model the pipe, and it is not a pipe design. Converting these numbers into
  a design pressure requires a bedding factor and an assessment of pipe
  stiffness relative to the surrounding soil.
</div>

<h2>1. Configuration</h2>
<table>
  <tr><th style="width:34%">Surface load</th><td>{{ r.load_description }}</td></tr>
  <tr><th>Total applied load</th><td>{{ '%.1f'|format(r.total_load_kn) }} kN</td></tr>
  <tr><th>Travel direction</th><td>{{ 'along the pipe' if orientation == 'along' else 'crossing the pipe' }}</td></tr>
  <tr><th>Depth of cover to crown</th><td>{{ '%.3f'|format(r.cover_m) }} m</td></tr>
  <tr><th>Pipe outside diameter</th><td>{{ '%.3f'|format(r.pipe_od_m) }} m</td></tr>
  <tr><th>Machine offset from pipe centreline</th><td>{{ '%.3f'|format(r.machine_offset_m) }} m</td></tr>
  <tr><th>Dynamic load allowance</th><td>{{ '%.2f'|format(r.dla) }} &mdash; {{ dla_basis }}</td></tr>
  <tr><th>Soil unit weight</th><td>{{ '%.1f'|format(soil_unit_weight_kn_m3) }} kN/m<sup>3</sup></td></tr>
  <tr><th>Poisson's ratio (Westergaard only)</th><td>{{ '%.2f'|format(poisson_ratio) }}</td></tr>
</table>

{% if vehicle %}
<h2>2. Vehicle configuration</h2>
<p>
  {{ vehicle.axle_count }}
  {{ 'track set' if vehicle.is_tracked else ('axle line' if vehicle.axle_count == 1 else 'axle lines') }},
  {{ '%.0f'|format(vehicle.total_load_kn) }} kN total,
  gauge {{ '%.2f'|format(vehicle.gauge_m) }} m{% if vehicle.wheelbase_m %},
  wheelbase {{ '%.2f'|format(vehicle.wheelbase_m) }} m{% endif %}.
  {% if vehicle_source %}Source: {{ vehicle_source }}{% endif %}
</p>
{% if vehicle_verified is false %}
<div class="warn">
  This vehicle is an <b>unverified transcription</b>. Every dimension below must
  be confirmed against the machine on site before the results are relied on.
</div>
{% endif %}
<table>
  <tr>
    <th>Axle line</th><th class="num">Axle load</th>
    <th class="num">Per {{ vehicle.contact_noun }}</th>
    <th class="num">{{ 'Tracks' if vehicle.is_tracked else 'Tyres' }}/side</th>
    <th class="num">Width</th><th class="num">Contact length</th>
    <th class="num">Dual spacing</th><th class="num">Spacing from previous</th>
  </tr>
  {% for a in vehicle.axles %}
  <tr>
    <td>{{ a.label }}</td>
    <td class="num">{{ '%.1f'|format(a.load_kn) }} kN</td>
    <td class="num">{{ '%.1f'|format(a.wheel_load_kn) }} kN</td>
    <td class="num">{{ a.tires_per_side }}</td>
    <td class="num">{{ '%.0f'|format(a.tire_width_m * 1000) }} mm</td>
    <td class="num">{{ '%.0f'|format(a.contact_length_m * 1000) }} mm{% if a.contact_length_is_derived %} *{% endif %}</td>
    {# An em dash, not 0 mm: a single tyre has no dual spacing to state. #}
    <td class="num">{% if a.dual_spacing_m is none %}&mdash;{% else %}{{ '%.0f'|format(a.dual_spacing_m * 1000) }} mm{% endif %}</td>
    <td class="num">{% if a.spacing_from_previous_m is none %}&mdash;{% else %}{{ '%.2f'|format(a.spacing_from_previous_m) }} m{% endif %}</td>
  </tr>
  {% endfor %}
</table>
{% if vehicle.axles | selectattr('contact_length_is_derived') | list %}
<p class="muted">
  * Contact length was computed from an assumed tyre inflation pressure rather
  than read off a sheet. The contact pressure on those axles therefore only
  returns the assumed pressure and is not independent evidence.
</p>
{% endif %}
{% if vehicle_assumptions %}
<p><b>Assumptions in this vehicle &mdash; must be confirmed:</b></p>
<ul>{% for a in vehicle_assumptions %}<li>{{ a }}</li>{% endfor %}</ul>
{% endif %}
{% endif %}

<h2>{{ 3 if vehicle else 2 }}. Method comparison at crown level</h2>
<table>
  <tr><th>Method</th><th class="num">Crown pressure</th><th>Basis</th></tr>
  {% for m in r.methods %}
  <tr {% if m.key == 'boussinesq' %}class="primary"{% endif %}>
    <td>{{ m.name }}{% if not m.verified %} <span style="color:#b40000">(unverified)</span>{% endif %}</td>
    <td class="num">{{ '%.1f'|format(m.pressure_kpa) }} kPa</td>
    <td class="muted">{{ m.basis }}{% if m.note %}<br>{{ m.note }}{% endif %}</td>
  </tr>
  {% endfor %}
</table>
<p class="muted">The Boussinesq row is the primary result. The others are shown
for comparison: the point idealisation exposes the error in treating a contact
area as a point; Westergaard suits a layered deposit and is the lower bound
beneath the load; the spread rules conserve total load but have no theoretical
basis and take no account of position relative to the load.</p>

<h2>{{ 4 if vehicle else 3 }}. Supporting calculations & Visual Diagrams</h2>
{% for m in r.methods %}
<div class="method">
  <div><b>3.{{ loop.index }} &nbsp; {{ m.name }}</b>
    <span style="float:right"><b>{{ '%.2f'|format(m.pressure_kpa) }} kPa</b></span></div>

  <div class="diagram-box">
    {% if m.key == 'boussinesq' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <rect x="170" y="23" width="100" height="14" fill="#3b82f6" fill-opacity="0.3" stroke="#1d4ed8" stroke-width="1.5" rx="2" />
        <text x="220" y="18" fill="#1d4ed8" font-size="10" font-weight="700" text-anchor="middle">Contact Patch q (kPa)</text>
        <path d="M 170 30 Q 140 80 220 110 Q 300 80 270 30 Z" fill="#93c5fd" fill-opacity="0.25" stroke="#2563eb" stroke-width="1.5" stroke-dasharray="4 3" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
        <text x="370" y="104" fill="#ef4444" font-size="9.5" font-weight="700">z = {{ '%.2f'|format(r.cover_m) }}m</text>
        <text x="80" y="75" fill="#1e293b" font-size="9" font-weight="600">Newmark 4-Corner Superposition</text>
      </svg>
    {% elif m.key == 'boussinesq_point' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <line x1="220" y1="5" x2="220" y2="30" stroke="#dc2626" stroke-width="3" stroke-linecap="round" />
        <polygon points="215,24 220,32 225,24" fill="#dc2626" />
        <text x="230" y="18" fill="#dc2626" font-size="10" font-weight="800">Point Load P</text>
        <line x1="220" y1="30" x2="160" y2="110" stroke="#f87171" stroke-width="1.5" stroke-dasharray="3 3" />
        <line x1="220" y1="30" x2="280" y2="110" stroke="#f87171" stroke-width="1.5" stroke-dasharray="3 3" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
        <text x="370" y="104" fill="#ef4444" font-size="9.5" font-weight="700">z = {{ '%.2f'|format(r.cover_m) }}m</text>
      </svg>
    {% elif m.key == 'westergaard' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <rect x="175" y="23" width="90" height="14" fill="#0891b2" fill-opacity="0.3" stroke="#0e7490" stroke-width="1.5" rx="2" />
        <line x1="50" y1="50" x2="390" y2="50" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="5 2" />
        <line x1="50" y1="70" x2="390" y2="70" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="5 2" />
        <line x1="50" y1="90" x2="390" y2="90" stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="5 2" />
        <path d="M 175 30 L 135 110 L 305 110 L 265 30 Z" fill="#67e8f9" fill-opacity="0.25" stroke="#0891b2" stroke-width="1.5" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
        <text x="370" y="104" fill="#ef4444" font-size="9.5" font-weight="700">z = {{ '%.2f'|format(r.cover_m) }}m</text>
      </svg>
    {% elif m.key == 'spread_2to1' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <rect x="180" y="23" width="80" height="14" fill="#d97706" fill-opacity="0.3" stroke="#b45309" stroke-width="1.5" rx="2" />
        <path d="M 180 30 L 135 110 L 305 110 L 260 30 Z" fill="#fcd34d" fill-opacity="0.3" stroke="#d97706" stroke-width="1.5" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
        <text x="220" y="122" fill="#b45309" font-size="9.5" font-weight="700" text-anchor="middle">Grown Footprint (B + z) Ã— (L + z)</text>
      </svg>
    {% elif m.key == 'spread_superposed' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <rect x="130" y="23" width="50" height="14" fill="#7c3aed" fill-opacity="0.3" stroke="#6d28d9" stroke-width="1.5" rx="2" />
        <rect x="260" y="23" width="50" height="14" fill="#7c3aed" fill-opacity="0.3" stroke="#6d28d9" stroke-width="1.5" rx="2" />
        <path d="M 130 30 L 90 110 L 220 110 L 180 30 Z" fill="#c4b5fd" fill-opacity="0.3" stroke="#7c3aed" stroke-width="1" stroke-dasharray="3 3" />
        <path d="M 260 30 L 220 110 L 350 110 L 310 30 Z" fill="#c4b5fd" fill-opacity="0.3" stroke="#7c3aed" stroke-width="1" stroke-dasharray="3 3" />
        <circle cx="220" cy="110" r="3.5" fill="#6d28d9" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
      </svg>
    {% elif m.key == 'code_spread' %}
      <svg viewBox="0 0 440 130" width="100%" height="120">
        <line x1="20" y1="30" x2="420" y2="30" stroke="#475569" stroke-width="2" />
        <rect x="170" y="23" width="100" height="14" fill="#475569" fill-opacity="0.3" stroke="#334155" stroke-width="1.5" rx="2" />
        <path d="M 170 30 L 115 110 L 325 110 L 270 30 Z" fill="#cbd5e1" fill-opacity="0.4" stroke="#475569" stroke-width="1.5" />
        <line x1="30" y1="110" x2="410" y2="110" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
        <text x="220" y="122" fill="#1e293b" font-size="9.5" font-weight="700" text-anchor="middle">Code Spread Area (LLDF Factor x z)</text>
      </svg>
    {% endif %}
  </div>

  <div class="formula">{{ m.formula }}</div>
  <table>
    <tr>
      <th>{{ 'Contribution' if m.terms_sum_to_total else 'Candidate area' }}</th>
      <th>Working</th>
      <th class="num">sigma_z</th>
    </tr>
    {% for t in m.terms %}
    <tr><td>{{ t.label }}</td><td class="muted">{{ t.detail }}</td>
        <td class="num">{{ '%.2f'|format(t.value_kpa) }} kPa</td></tr>
    {% endfor %}
    <tr><td colspan="2"><b>{{ 'Sum of contributions' if m.terms_sum_to_total
        else 'Governing (largest) area' }}</b></td>
        <td class="num"><b>{{ '%.2f'|format(m.pressure_kpa) }} kPa</b></td></tr>
  </table>
  <p class="muted">{{ m.substitution }}</p>
</div>
{% endfor %}

<h2>{{ 5 if vehicle else 4 }}. Governing position</h2>
<table>
  <tr><th style="width:44%">At the offset analysed ({{ '%.3f'|format(r.machine_offset_m) }} m)</th>
      <td class="num">{{ '%.1f'|format(r.live_pressure_kpa) }} kPa</td></tr>
  <tr><th>Worst offset found by sweep ({{ '%.3f'|format(r.worst_offset_m) }} m)</th>
      <td class="num">{{ '%.1f'|format(r.worst_offset_pressure_kpa) }} kPa</td></tr>
  <tr><th>Is the analysed position critical?</th>
      <td>{{ 'Yes' if r.offset_is_worst else 'NO - see warnings' }}</td></tr>
</table>

<h2>{{ 6 if vehicle else 5 }}. Derived quantities</h2>
<table>
  <tr><th style="width:44%">Peak crown pressure (Boussinesq, factored by DLA)</th>
      <td class="num">{{ '%.1f'|format(r.live_pressure_kpa) }} kPa</td></tr>
  <tr><th>Average across the pipe width</th>
      <td class="num">{{ '%.1f'|format(r.average_over_pipe_kpa) }} kPa</td></tr>
  <tr><th>Vertical load per metre of pipe</th>
      <td class="num">{{ '%.2f'|format(r.load_per_m_kn_m) }} kN/m</td></tr>
  <tr><th>Soil overburden at crown ({{ '%.1f'|format(soil_unit_weight_kn_m3) }} x {{ '%.3f'|format(r.cover_m) }})</th>
      <td class="num">{{ '%.1f'|format(r.soil_pressure_kpa) }} kPa</td></tr>
  <tr><th>Surcharge as a proportion of overburden</th>
      <td class="num">{{ '%.2f'|format(r.live_to_dead_ratio) }}</td></tr>
</table>
<div class="formula">Load per metre of pipe = integral of sigma_z across the pipe
outside diameter at crown level
                       = {{ '%.1f'|format(r.average_over_pipe_kpa) }} kPa x {{ '%.3f'|format(r.pipe_od_m) }} m
                       = {{ '%.2f'|format(r.load_per_m_kn_m) }} kN/m</div>

<h2>{{ 7 if vehicle else 6 }}. Notes and limitations</h2>
{% for w in r.warnings %}<div class="warn">{{ w }}</div>{% endfor %}

<div class="sig">
  <div>Calculated by / date</div>
  <div>Checked by / date</div>
</div>

<footer>
  Produced by the Engineering Design Toolkit. Comparative analysis aid only, not
  a pipe design. The engineer of record is responsible for verifying input,
  method selection, code provisions and the suitability of the result.
  Generated {{ today }}.
</footer>

</div>
</body>
</html>"""
)


def render(
    result,
    *,
    project: str = "",
    member: str = "",
    engineer: str = "",
    orientation: str = "across",
    dla_basis: str = "",
    soil_unit_weight_kn_m3: float = 20.0,
    poisson_ratio: float = 0.0,
    vehicle: dict | None = None,
    vehicle_source: str = "",
    vehicle_verified: bool | None = None,
    vehicle_assumptions: list[str] | None = None,
) -> str:
    """``vehicle`` is the geometry block, or None for custom rectangle loads -
    the vehicle section is then omitted and the later sections renumber.

    Deliberately a table and not a re-drawn SVG. The vehicle drawing in the UI
    is data-driven; reimplementing that geometry in Jinja would give two
    versions of the same picture that can silently disagree.
    """
    return _TEMPLATE.render(
        r=result,
        vehicle=vehicle,
        vehicle_source=vehicle_source,
        vehicle_verified=vehicle_verified,
        vehicle_assumptions=vehicle_assumptions or [],
        today=date.today().isoformat(),
        project=project or "(project not named)",
        member=member or "Buried pipe",
        engineer=engineer or "-",
        orientation=orientation,
        dla_basis=dla_basis,
        soil_unit_weight_kn_m3=soil_unit_weight_kn_m3,
        poisson_ratio=poisson_ratio,
    )

