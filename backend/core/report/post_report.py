"""Printable calculation report for a post or column."""

from __future__ import annotations

from datetime import date

from jinja2 import Environment

_ENV = Environment(autoescape=True)

_TEMPLATE = _ENV.from_string(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ project }} - {{ member }} - Post Design Calculation</title>
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
  .pass { color: #096b1f; font-weight: 700; }
  .fail { color: #b40000; font-weight: 700; }
  .check { border: 1px solid #999; padding: 7px 9px; margin: 7px 0;
           page-break-inside: avoid; }
  .formula { font-family: "Cascadia Mono", Consolas, monospace; font-size: 10.5px;
             background: #f6f6f6; padding: 4px 6px; margin: 4px 0; white-space: pre-wrap; }
  .warn { border-left: 3px solid #c47f00; background: #fff8e8; padding: 6px 9px;
          margin: 5px 0; page-break-inside: avoid; }
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
  <div class="row"><h1>Post / Column Design Calculation</h1><div>{{ today }}</div></div>
  <div class="row muted">
    <div><b>Project:</b> {{ project }}</div>
    <div><b>Member:</b> {{ member }}</div>
    <div><b>By:</b> {{ engineer }}</div>
  </div>
  <div class="row muted">
    <div><b>Code:</b> OBC 2024 Div. B Part 4 / NBC 2020 / CSA O86-19</div>
    <div><b>Result:</b>
      <span class="{{ 'pass' if r.outcome.passed else 'fail' }}">
        {{ 'PASS' if r.outcome.passed else 'FAIL' }} - governing ratio {{ '%.2f'|format(r.outcome.max_ratio) }}
      </span>
    </div>
  </div>
</div>

<h2>1. Member</h2>
<table>
  <tr><th style="width:32%">Section</th><td>{{ r.label }}</td></tr>
  <tr><th>Overall width x depth</th><td>{{ '%.0f'|format(r.width_mm) }} x {{ '%.0f'|format(r.depth_mm) }} mm{% if r.plies > 1 %} ({{ r.plies }} ply){% endif %}</td></tr>
  <tr><th>Gross area A</th><td>{{ '%.4g'|format(r.area_mm2 / 1000) }} x 10<sup>3</sup> mm<sup>2</sup></td></tr>
  <tr><th>Unbraced length</th><td>{{ '%.0f'|format(length_mm) }} mm ({{ '%.2f'|format(length_mm / 304.8) }} ft)</td></tr>
  <tr><th>End conditions</th><td>about depth axis: {{ end_condition_d }} &nbsp;|&nbsp; about width axis: {{ end_condition_b }}</td></tr>
  <tr><th>Slenderness ratio C<sub>c</sub></th><td>{{ '%.1f'|format(r.slenderness) }} (governs about the {{ r.slenderness_axis }} axis; CSA O86 limit is 50)</td></tr>
  <tr><th>Material</th><td>{{ r.material_name }}</td></tr>
  <tr><th>Property source</th><td>{{ r.material_source }}</td></tr>
  <tr><th>Design basis</th><td>{{ r.method }}</td></tr>
  <tr><th>Service condition</th><td>{{ conditions.service }}, treatment: {{ conditions.treatment }}</td></tr>
</table>

{% if not r.material_verified %}
<div class="verify">
  <b>Material values require verification.</b> The properties used for
  {{ r.material_name }} are a transcription and have not been checked against a
  licensed copy of CSA O86-19. The engineer of record must confirm f<sub>c</sub>
  and E<sub>05</sub> before this calculation is relied upon.
</div>
{% endif %}

<h2>2. Axial loads (specified / unfactored)</h2>
<table>
  <tr><th>Case</th><th class="num">Axial load</th></tr>
  {% for case, value in axial_kn.items() %}{% if value %}
  <tr><td>{{ case }}</td><td class="num">{{ '%.2f'|format(value) }} kN</td></tr>
  {% endif %}{% endfor %}
</table>
<p class="muted">Load combinations to NBC 2020 Table 4.1.3.2. Governing combination:
<b>{{ r.governing_combo }}</b>, giving a factored axial load of
<b>{{ '%.2f'|format(r.demand_kn) }} kN</b>.</p>

<h2>3. Design checks (CSA O86-19)</h2>
{% for c in r.outcome.checks %}
<div class="check">
  <div><b>3.{{ loop.index }} &nbsp; {{ c.label }}</b>
    <span class="{{ 'pass' if c.status == 'PASS' else 'fail' }}" style="float:right">
      {{ c.status }} &nbsp; ratio {{ '%.3f'|format(c.ratio) }}</span>
  </div>
  <div class="muted">{{ c.clause }} &nbsp;|&nbsp; combination: {{ c.combo_label }}</div>
  <div class="formula">{{ c.formula }}
{{ c.substitution }}</div>
  <table>
    <tr><th class="num" style="width:33%">Demand</th>
        <th class="num" style="width:33%">Resistance</th>
        <th class="num">Utilisation</th></tr>
    <tr><td class="num">{{ '%.3f'|format(c.demand) }} {{ c.units }}</td>
        <td class="num">{{ '%.3f'|format(c.resistance) }} {{ c.units }}</td>
        <td class="num {{ 'pass' if c.status == 'PASS' else 'fail' }}">{{ '%.3f'|format(c.ratio) }}</td></tr>
  </table>
  {% if c.factors %}
  <table>
    <tr><th>Factor</th><th class="num">Value</th><th>Clause</th><th>Basis</th></tr>
    {% for f in c.factors %}
    <tr><td>{{ f.symbol }}</td><td class="num">{{ '%.3f'|format(f.value) }}</td>
        <td>{{ f.clause }}</td><td>{{ f.description }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}
  {% if c.note %}<div class="muted">{{ c.note }}</div>{% endif %}
</div>
{% endfor %}

{% if r.independent_ply_resistance_kn is not none %}
<p class="muted"><b>Built-up post:</b> if the plies were not fastened to act
together, the capacity would be about
{{ '%.1f'|format(r.independent_ply_resistance_kn) }} kN.</p>
{% endif %}

<h2>4. Summary</h2>
<table>
  <tr><th>Check</th><th>Combination</th><th class="num">Demand</th>
      <th class="num">Resistance</th><th class="num">Ratio</th><th>Status</th></tr>
  {% for c in r.outcome.checks %}
  <tr><td>{{ c.label }}</td><td>{{ c.combo_label }}</td>
      <td class="num">{{ '%.2f'|format(c.demand) }} {{ c.units }}</td>
      <td class="num">{{ '%.2f'|format(c.resistance) }} {{ c.units }}</td>
      <td class="num">{{ '%.3f'|format(c.ratio) }}</td>
      <td class="{{ 'pass' if c.status == 'PASS' else 'fail' }}">{{ c.status }}</td></tr>
  {% endfor %}
</table>
<p><b>Result:</b>
  <span class="{{ 'pass' if r.outcome.passed else 'fail' }}">{{ 'POST ADEQUATE' if r.outcome.passed else 'POST INADEQUATE' }}</span>
</p>

{% if r.outcome.warnings %}
<h2>5. Notes and warnings</h2>
{% for w in r.outcome.warnings %}<div class="warn">{{ w }}</div>{% endfor %}
{% endif %}

<div class="sig">
  <div>Calculated by / date</div>
  <div>Checked by / date</div>
</div>

<footer>
  Produced by the Engineering Design Toolkit. This calculation is a design aid,
  not a substitute for engineering judgement. The engineer of record is
  responsible for verifying input, material properties, code clauses and the
  suitability of the result. Generated {{ today }}.
</footer>

</body>
</html>"""
)


def render(
    response,
    *,
    project: str = "",
    member: str = "",
    engineer: str = "",
    length_mm: float = 0.0,
    conditions=None,
    axial_kn: dict[str, float] | None = None,
    end_condition_d: str = "",
    end_condition_b: str = "",
) -> str:
    return _TEMPLATE.render(
        r=response,
        today=date.today().isoformat(),
        project=project or "(project not named)",
        member=member or "Post",
        engineer=engineer or "-",
        length_mm=length_mm,
        conditions=conditions,
        axial_kn=axial_kn or {},
        end_condition_d=end_condition_d,
        end_condition_b=end_condition_b,
    )
