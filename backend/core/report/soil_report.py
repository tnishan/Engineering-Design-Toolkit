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
  @page { size: A4 portrait; margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body { font: 11px/1.45 "Segoe UI", Arial, sans-serif; color: #111; margin: 0; }
  h1 { font-size: 17px; margin: 0 0 2px; }
  h2 { font-size: 13px; margin: 18px 0 6px; padding-bottom: 3px;
       border-bottom: 1.5px solid #333; page-break-after: avoid; }
  .hdr { border: 1px solid #333; padding: 8px 10px; margin-bottom: 4px; }
  .hdr .row { display: flex; justify-content: space-between; gap: 12px; }
  .muted { color: #555; }
  table { border-collapse: collapse; width: 100%; margin: 6px 0 10px;
          page-break-inside: avoid; }
  th, td { border: 1px solid #bbb; padding: 3px 6px; text-align: left;
           vertical-align: top; }
  th { background: #eee; font-weight: 600; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .primary { background: #eef4fb; font-weight: 600; }
  .formula { font-family: "Cascadia Mono", Consolas, monospace; font-size: 10.5px;
             background: #f6f6f6; padding: 5px 7px; margin: 4px 0; white-space: pre-wrap; }
  .warn { border-left: 3px solid #c47f00; background: #fff8e8; padding: 6px 9px;
          margin: 5px 0; page-break-inside: avoid; }
  .method { border: 1px solid #999; padding: 7px 9px; margin: 7px 0;
            page-break-inside: avoid; }
  .verify { border: 1.5px solid #b40000; background: #fff2f2; padding: 8px 10px;
            margin: 10px 0; }
  footer { margin-top: 18px; border-top: 1px solid #999; padding-top: 5px;
           font-size: 9.5px; color: #555; }
  .sig { margin-top: 20px; display: flex; gap: 28px; }
  .sig div { flex: 1; border-top: 1px solid #333; padding-top: 3px; font-size: 10px; }
</style>
</head>
<body>

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

<h2>2. Method comparison at crown level</h2>
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

<h2>3. Supporting calculations</h2>
{% for m in r.methods %}
<div class="method">
  <div><b>3.{{ loop.index }} &nbsp; {{ m.name }}</b>
    <span style="float:right"><b>{{ '%.2f'|format(m.pressure_kpa) }} kPa</b></span></div>
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

<h2>4. Governing position</h2>
<table>
  <tr><th style="width:44%">At the offset analysed ({{ '%.3f'|format(r.machine_offset_m) }} m)</th>
      <td class="num">{{ '%.1f'|format(r.live_pressure_kpa) }} kPa</td></tr>
  <tr><th>Worst offset found by sweep ({{ '%.3f'|format(r.worst_offset_m) }} m)</th>
      <td class="num">{{ '%.1f'|format(r.worst_offset_pressure_kpa) }} kPa</td></tr>
  <tr><th>Is the analysed position critical?</th>
      <td>{{ 'Yes' if r.offset_is_worst else 'NO - see warnings' }}</td></tr>
</table>

<h2>5. Derived quantities</h2>
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

<h2>6. Notes and limitations</h2>
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
) -> str:
    return _TEMPLATE.render(
        r=result,
        today=date.today().isoformat(),
        project=project or "(project not named)",
        member=member or "Buried pipe",
        engineer=engineer or "-",
        orientation=orientation,
        dla_basis=dla_basis,
        soil_unit_weight_kn_m3=soil_unit_weight_kn_m3,
        poisson_ratio=poisson_ratio,
    )
