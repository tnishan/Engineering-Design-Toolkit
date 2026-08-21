"""Standalone printable calculation report.

Renders a DesignResponse into a self-contained HTML document styled for A4/
Letter printing, so it can be reviewed or filed like a hand calculation.
"""

from __future__ import annotations

from datetime import date

from jinja2 import Environment

_ENV = Environment(autoescape=True)

_TEMPLATE = _ENV.from_string(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ project }} - {{ member }} - Beam Design Calculation</title>
<style>
  @page { size: A4 portrait; margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body { font: 11px/1.45 "Segoe UI", Arial, sans-serif; color: #111; margin: 0; }
  h1 { font-size: 17px; margin: 0 0 2px; }
  h2 { font-size: 13px; margin: 18px 0 6px; padding-bottom: 3px;
       border-bottom: 1.5px solid #333; page-break-after: avoid; }
  h3 { font-size: 11.5px; margin: 12px 0 4px; page-break-after: avoid; }
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
  .check .title { font-weight: 700; }
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
  <div class="row"><h1>Beam Design Calculation</h1><div>{{ today }}</div></div>
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

<h2>1. Member and materials</h2>
<table>
  <tr><th style="width:32%">Section</th><td>{{ r.section_label }}</td></tr>
  <tr><th>Overall width x depth</th><td>{{ '%.0f'|format(r.width_mm) }} x {{ '%.0f'|format(r.depth_mm) }} mm ({{ r.plies }} ply)</td></tr>
  <tr><th>Material</th><td>{{ r.material_name }}</td></tr>
  <tr><th>Property source</th><td>{{ r.material_source }}</td></tr>
  <tr><th>Section modulus S</th><td>{{ '%.4g'|format(S / 1000) }} x 10<sup>3</sup> mm<sup>3</sup></td></tr>
  <tr><th>Moment of inertia I</th><td>{{ '%.4g'|format(I / 1e6) }} x 10<sup>6</sup> mm<sup>4</sup></td></tr>
  <tr><th>Gross area A</th><td>{{ '%.4g'|format(A / 1000) }} x 10<sup>3</sup> mm<sup>2</sup></td></tr>
  <tr><th>Self weight</th><td>{{ '%.3f'|format(r.self_weight_n_per_mm) }} kN/m {{ '(included)' if r.self_weight_n_per_mm else '(excluded)' }}</td></tr>
</table>

{% if not r.material_verified %}
<div class="verify">
  <b>Material values require verification.</b> The properties used for
  {{ r.material_name }} are a transcription and have not been checked against a
  licensed copy of CSA O86-19. The engineer of record must confirm every
  specified strength and modulus before this calculation is relied upon.
</div>
{% endif %}

<h2>2. Geometry and loads</h2>
<table>
  <tr><th style="width:32%">Spans</th><td>{{ spans_text }}</td></tr>
  <tr><th>Supports</th><td>{{ supports_text }}</td></tr>
  <tr><th>Bearing length assumed</th><td>{{ '%.0f'|format(bearing_mm) }} mm</td></tr>
  <tr><th>Service condition</th><td>{{ conditions.service }}</td></tr>
  <tr><th>Treatment</th><td>{{ conditions.treatment }}</td></tr>
  <tr><th>Lateral support</th><td>{{ 'Compression edge restrained throughout' if conditions.laterally_supported else 'NOT restrained - see warnings' }}</td></tr>
</table>

<h3>Specified (unfactored) loads</h3>
<table>
  <tr><th>Case</th><th>Type</th><th class="num">Magnitude</th><th>Extent</th></tr>
  {% for l in load_rows %}
  <tr><td>{{ l.case }}</td><td>{{ l.kind }}</td><td class="num">{{ l.magnitude }}</td><td>{{ l.extent }}</td></tr>
  {% endfor %}
</table>

<h2>3. Load combinations considered</h2>
<p class="muted">NBC 2020 Table 4.1.3.2, adopted by OBC 2024. Every combination
was analysed; the governing one is reported against each check.</p>
<table>
  <tr><th>Combination</th><th>Duration (K<sub>D</sub> basis)</th></tr>
  {% for c in combos %}<tr><td>{{ c }}</td><td>{{ durations[loop.index0] }}</td></tr>{% endfor %}
</table>

<h2>4. Analysis results</h2>
<table>
  <tr><th>Quantity</th><th class="num">Value</th><th>Location / combination</th></tr>
  <tr><td>Maximum sagging moment</td><td class="num">{{ '%.2f'|format(max_sag) }} kN&middot;m</td><td>{{ r.diagrams.governing_moment_combo }}</td></tr>
  <tr><td>Maximum hogging moment</td><td class="num">{{ '%.2f'|format(max_hog) }} kN&middot;m</td><td>{{ r.diagrams.governing_moment_combo }}</td></tr>
  <tr><td>Maximum shear</td><td class="num">{{ '%.2f'|format(max_shear) }} kN</td><td>{{ r.diagrams.governing_shear_combo }}</td></tr>
</table>

<h3>Support reactions and bearing</h3>
<table>
  <tr><th>Support</th><th>Type</th><th class="num">Max reaction</th>
      <th>Governing combination</th><th class="num">Bearing required</th>
      <th class="num">Bearing ratio</th></tr>
  {% for rx in r.reactions %}
  <tr>
    <td>x = {{ '%.3f'|format(rx.x_mm / 1000) }} m</td>
    <td>{{ rx.support_kind }}</td>
    <td class="num">{{ '%.2f'|format(rx.max_kn) }} kN</td>
    <td>{{ rx.governing_combo }}</td>
    <td class="num">{{ '%.0f'|format(rx.required_bearing_mm) }} mm</td>
    <td class="num {{ 'fail' if rx.bearing_ratio > 1 else 'pass' }}">{{ '%.3f'|format(rx.bearing_ratio) }}</td>
  </tr>
  {% endfor %}
</table>
<p class="muted">Bearing required is the length needed at that support for the
provided bearing width; compare against what the supporting element actually
delivers.</p>
<p class="muted">Analysis is a direct-stiffness solution using two-node
Timoshenko beam elements, so shear deformation is included in both the
deflections and the distribution of moments in the continuous member.</p>

<h2>5. Design checks (CSA O86-19)</h2>
{% for c in r.outcome.checks %}
<div class="check">
  <div class="title">5.{{ loop.index }} &nbsp; {{ c.label }}
    <span class="{{ 'pass' if c.status == 'PASS' else 'fail' }}" style="float:right">
      {{ c.status }} &nbsp; ratio {{ '%.3f'|format(c.ratio) }}</span>
  </div>
  <div class="muted">{{ c.clause }} &nbsp;|&nbsp; combination: {{ c.combo_label }}
    {%- if c.location_mm is not none %} &nbsp;|&nbsp; at x = {{ '%.0f'|format(c.location_mm) }} mm{% endif %}</div>
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

<h2>6. Summary</h2>
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
<p><b>Governing check:</b>
  {{ r.outcome.governing.label if r.outcome.governing else 'n/a' }}
  at ratio {{ '%.3f'|format(r.outcome.max_ratio) }} -
  <span class="{{ 'pass' if r.outcome.passed else 'fail' }}">{{ 'MEMBER ADEQUATE' if r.outcome.passed else 'MEMBER INADEQUATE' }}</span>
</p>

{% if r.outcome.warnings %}
<h2>7. Notes and warnings</h2>
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
    spans_mm: list[float] | None = None,
    support_kinds: list[str] | None = None,
    conditions=None,
    load_rows: list[dict] | None = None,
    durations: list[str] | None = None,
) -> str:
    r = response
    d = r.diagrams

    S = r.width_mm * r.depth_mm**2 / 6.0
    I = r.width_mm * r.depth_mm**3 / 12.0
    A = r.width_mm * r.depth_mm

    spans_mm = spans_mm or []
    spans_text = " + ".join(
        f"{s / 1000:.3f} m ({s / 304.8:.2f} ft)" for s in spans_mm
    ) or "-"
    supports_text = ", ".join(support_kinds or []) or "-"

    return _TEMPLATE.render(
        r=r,
        today=date.today().isoformat(),
        project=project or "(project not named)",
        member=member or "Beam",
        engineer=engineer or "-",
        S=S, I=I, A=A,
        spans_text=spans_text,
        supports_text=supports_text,
        bearing_mm=getattr(conditions, "bearing_length_mm", 0.0),
        conditions=conditions,
        load_rows=load_rows or [],
        combos=r.combos_considered,
        durations=durations or ["-"] * len(r.combos_considered),
        max_sag=max(d.moment_max_knm) if d.moment_max_knm else 0.0,
        max_hog=abs(min(d.moment_min_knm)) if d.moment_min_knm else 0.0,
        max_shear=max(max(d.shear_max_kn), abs(min(d.shear_min_kn))) if d.shear_max_kn else 0.0,
    )
