import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Diagrams as DiagramData, Peak, SpanLimit } from "../../api/types";

interface Props {
  diagrams: DiagramData;
  supportsAtMm: number[];
  spanLimits: SpanLimit[];
}

interface Row {
  x: number;
  vMin: number;
  vMax: number;
  mMin: number;
  mMax: number;
  dLive: number;
  dTotal: number;
}

// A fixed Y-axis width keeps the plot areas of all three charts identical, so
// a feature at a given x lines up vertically across SFD, BMD and deflection.
const Y_AXIS_W = 68;
const AXIS = { fontSize: 11 };

/**
 * A downward-only axis range ending on round numbers.
 *
 * Forcing an exact domain makes Recharts emit ticks like -5.289; snapping the
 * bound to a 1/2/2.5/5 x 10^n step keeps the labels readable.
 */
function niceDomain(depth: number): [number, number] {
  if (!Number.isFinite(depth) || depth <= 0) return [-1, 1];
  const target = (depth * 1.15) / 5; // aim for about five gridlines
  const magnitude = 10 ** Math.floor(Math.log10(target));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * magnitude >= target) ?? 10) * magnitude;
  return [-Math.ceil((depth * 1.05) / step) * step, step];
}

export default function Diagrams({ diagrams, supportsAtMm, spanLimits }: Props) {
  const [tensionSide, setTensionSide] = useState(true);

  const rows: Row[] = diagrams.x_mm.map((x, i) => ({
    x: x / 1000,
    vMin: diagrams.shear_min_kn[i],
    vMax: diagrams.shear_max_kn[i],
    mMin: diagrams.moment_min_knm[i],
    mMax: diagrams.moment_max_knm[i],
    dLive: diagrams.deflection_live_mm[i],
    dTotal: diagrams.deflection_total_mm[i],
  }));

  const supports = supportsAtMm.map((x) => x / 1000);

  // Keep every allowable-deflection line on screen even when the member is
  // comfortably inside its limit, so the margin is visible at a glance.
  const deepestLimit = Math.max(
    0,
    ...spanLimits.map((s) => Math.max(s.live_limit_mm, s.total_limit_mm)),
  );
  const deepestCurve = Math.abs(
    Math.min(0, ...rows.map((r) => Math.min(r.dLive, r.dTotal))),
  );
  const deflectionDomain: [number, number] = niceDomain(
    Math.max(deepestLimit, deepestCurve),
  );
  const peak = (label: string): Peak | undefined =>
    diagrams.peaks.find((p) => p.label === label);

  // Place the annotation on the side facing the middle of the plot, so it never
  // runs off the edge. A reversed axis flips which end of the screen a value sits at.
  const annotate = (p: Peak | undefined, colour: string, invert = false) => {
    if (!p) return null;
    const nearTopOfScreen = invert ? p.value < 0 : p.value > 0;
    return (
      <ReferenceDot
        x={p.x_mm / 1000}
        y={p.value}
        r={4}
        fill={colour}
        stroke="#fff"
        strokeWidth={1.5}
        label={{
          value: `${p.value.toFixed(2)} ${p.units} @ ${(p.x_mm / 1000).toFixed(2)} m`,
          position: nearTopOfScreen ? "bottom" : "top",
          fontSize: 11,
          fill: colour,
          fontWeight: 700,
        }}
      />
    );
  };

  const frame = (
    title: string,
    sub: string,
    yLabel: string,
    children: React.ReactNode,
    invert = false,
    extraHeader?: React.ReactNode,
    yDomain?: [number, number],
  ) => (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <p className="chart-title">{title}</p>
          <p className="chart-sub">{sub}</p>
        </div>
        {extraHeader}
      </div>
      <ResponsiveContainer width="100%" height={230}>
        <ComposedChart data={rows} margin={{ top: 20, right: 26, bottom: 20, left: 4 }}>
          <CartesianGrid stroke="#e6e9ed" />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, Number(rows[rows.length - 1]?.x ?? 0)]}
            tick={AXIS}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: "Distance along beam (m)",
              position: "insideBottom",
              offset: -12,
              style: AXIS,
            }}
          />
          <YAxis
            tick={AXIS}
            width={Y_AXIS_W}
            reversed={invert}
            domain={yDomain ?? ["auto", "auto"]}
            label={{ value: yLabel, angle: -90, position: "insideLeft", style: AXIS }}
          />
          <Tooltip
            formatter={(v: any, n: any) => [Number(v ?? 0).toFixed(3), String(n)]}
            labelFormatter={(v: any) => `x = ${Number(v ?? 0).toFixed(3)} m`}
            contentStyle={{ fontSize: 12 }}
          />

          <Legend verticalAlign="top" height={22} wrapperStyle={{ fontSize: 11.5 }} />
          <ReferenceLine y={0} stroke="#8a919b" strokeWidth={1.4} />
          {supports.map((x) => (
            <ReferenceLine key={x} x={x} stroke="#1f5fa8" strokeDasharray="4 3" />
          ))}
          {children}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );

  return (
    <div className="charts">
      {frame(
        "Shear force diagram (SFD)",
        `Factored envelope over all ULS combinations. Governing: ${diagrams.governing_shear_combo}`,
        "V (kN)",
        <>
          <Area type="monotone" dataKey="vMax" name="V max" stroke="#1f5fa8"
                fill="#1f5fa8" fillOpacity={0.16} strokeWidth={1.8}
                isAnimationActive={false} dot={false} />
          <Area type="monotone" dataKey="vMin" name="V min" stroke="#c02020"
                fill="#c02020" fillOpacity={0.12} strokeWidth={1.8}
                isAnimationActive={false} dot={false} />
          {annotate(peak("Max shear"), "#c02020")}
        </>,
      )}

      {frame(
        "Bending moment diagram (BMD)",
        `Factored envelope. Governing: ${diagrams.governing_moment_combo}`,
        "M (kN·m)",
        <>
          <Area type="monotone" dataKey="mMax" name="Sagging (+)" stroke="#1f5fa8"
                fill="#1f5fa8" fillOpacity={0.16} strokeWidth={1.8}
                isAnimationActive={false} dot={false} />
          <Area type="monotone" dataKey="mMin" name="Hogging (−)" stroke="#c02020"
                fill="#c02020" fillOpacity={0.12} strokeWidth={1.8}
                isAnimationActive={false} dot={false} />
          {annotate(peak("Max sagging"), "#1f5fa8", tensionSide)}
          {annotate(peak("Max hogging"), "#c02020", tensionSide)}
        </>,
        tensionSide,
        <label className="inline" style={{ margin: 0, whiteSpace: "nowrap" }}>
          <input
            type="checkbox"
            checked={tensionSide}
            onChange={(e) => setTensionSide(e.target.checked)}
          />
          <span style={{ marginBottom: 0 }}>Plot on tension side</span>
        </label>,
      )}

      {frame(
        "Deflection",
        "Specified (unfactored) loads; downward is negative. Dashed lines are the "
          + "allowable limits for each span.",
        "δ (mm)",
        <>
          {/* Limits are per span, so each is drawn only across its own span. */}
          {spanLimits.flatMap((s) => [
            <ReferenceLine
              key={`live-${s.name}`}
              stroke="#1f5fa8"
              strokeDasharray="5 4"
              strokeWidth={1.2}
              segment={[
                { x: s.x_start_mm / 1000, y: -s.live_limit_mm },
                { x: s.x_end_mm / 1000, y: -s.live_limit_mm },
              ]}
              label={{
                value: `L/${Math.round(s.reference_length_mm / s.live_limit_mm)}`,
                position: "insideBottomLeft",
                fontSize: 10,
                fill: "#1f5fa8",
              }}
            />,
            <ReferenceLine
              key={`total-${s.name}`}
              stroke="#a86a00"
              strokeDasharray="5 4"
              strokeWidth={1.2}
              segment={[
                { x: s.x_start_mm / 1000, y: -s.total_limit_mm },
                { x: s.x_end_mm / 1000, y: -s.total_limit_mm },
              ]}
              label={{
                value: `L/${Math.round(s.reference_length_mm / s.total_limit_mm)}`,
                position: "insideBottomLeft",
                fontSize: 10,
                fill: "#a86a00",
              }}
            />,
          ])}
          <Line type="monotone" dataKey="dTotal" name="Total (D+L+S)" stroke="#a86a00"
                strokeWidth={1.8} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="dLive" name="Live + snow" stroke="#1f5fa8"
                strokeWidth={1.8} dot={false} isAnimationActive={false} />
        </>,
        false,
        undefined,
        deflectionDomain,
      )}
    </div>
  );
}
