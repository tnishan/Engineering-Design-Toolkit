import { useState } from "react";
import type {
  Orientation, SoilPatch, SoilPoint, VehicleGeometry,
} from "../../api/types";
import {
  DimLine, TravelArrow, TravelIntoPage, VDimLine,
  LOAD_EDGE, LOAD_FILL, PIPE, SOIL,
} from "./drawing";

interface Props {
  patches: SoilPatch[];
  points: SoilPoint[];
  coverM: number;
  pipeOdM: number;
  offsetM: number;
  worstOffsetM: number;
  offsetIsWorst: boolean;
  orientation: Orientation;
  /** Optional: lets the plan dimension the real gauge and wheelbase. */
  vehicle?: VehicleGeometry | null;
  /** Callback to update offset in parent */
  onOffsetChange?: (offsetM: number) => void;
}

const BADGE_COLORS = [
  "#2563eb", "#d97706", "#059669", "#dc2626", "#7c3aed",
  "#0891b2", "#ea580c", "#4f46e5", "#65a30d", "#db2777",
];

interface SymmetricalAxleLine {
  tagIndex: number;
  label: string;
  loadKn: number;
  configText: string;
  dimText: string;
  gaugeText: string;
  pressureKpa: number;
  distanceToPipeCrownM: number;
  targetOffsetToAlignM: number;
  patchIndices: number[];
}

export default function SiteDrawing({
  patches,
  points,
  coverM,
  pipeOdM,
  offsetM,
  worstOffsetM,
  offsetIsWorst,
  orientation,
  vehicle,
  onOffsetChange,
}: Props) {
  const [hoveredAxleIdx, setHoveredAxleIdx] = useState<number | null>(null);

  if (!patches.length && !points.length) return null;

  // Build Symmetrical Axle Lines (no separate Left and Right rows)
  const axleLines: SymmetricalAxleLine[] = [];
  if (vehicle && vehicle.axles && vehicle.axles.length > 0) {
    vehicle.axles.forEach((a, i) => {
      // Find matching patches for this axle
      const matchingIndices: number[] = [];
      patches.forEach((p, pIdx) => {
        const normPatch = p.label.toLowerCase();
        const normAxle = a.label.toLowerCase();
        if (normPatch.includes(normAxle) || normPatch.startsWith(`axle ${a.index + 1}`)) {
          matchingIndices.push(pIdx);
        }
      });

      const distM = orientation === "across"
        ? (offsetM + a.position_u_centred_m)
        : offsetM;
      const targetOffset = orientation === "across"
        ? -a.position_u_centred_m
        : 0;

      axleLines.push({
        tagIndex: i + 1,
        label: a.label,
        loadKn: a.load_kn,
        configText: vehicle.is_tracked
          ? "2 Continuous Steel Tracks"
          : (a.tires_per_side === 2 ? "4 Dual Tyres (2 / side)" : "2 Single Tyres (1 / side)"),
        dimText: `${Math.round(a.tire_width_m * 1000)} mm × ${Math.round(a.contact_length_m * 1000)} mm`,
        gaugeText: `${vehicle.gauge_m.toFixed(2)} m`,
        pressureKpa: a.contact_pressure_kpa,
        distanceToPipeCrownM: distM,
        targetOffsetToAlignM: targetOffset,
        patchIndices: matchingIndices.length > 0 ? matchingIndices : [i],
      });
    });
  } else {
    // Fallback: group patches by base label name
    const grouped = new Map<string, number[]>();
    patches.forEach((p, idx) => {
      const baseLabel = p.label.replace(/\s+(left|right)(\s+dual\s+\d+)?$/i, "").trim() || `Axle ${idx + 1}`;
      const list = grouped.get(baseLabel) ?? [];
      list.push(idx);
      grouped.set(baseLabel, list);
    });

    let tag = 1;
    grouped.forEach((indices, label) => {
      const first = patches[indices[0]];
      const totalKn = indices.reduce((sum, idx) => sum + patches[idx].total_kn, 0);
      const isTracks = label.toLowerCase().includes("track");
      axleLines.push({
        tagIndex: tag,
        label,
        loadKn: totalKn,
        configText: isTracks ? "2 Continuous Tracks" : `${indices.length} Contact Patches (Symmetric)`,
        dimText: `${Math.round(first.width_x_m * 1000)} mm × ${Math.round(first.length_y_m * 1000)} mm`,
        gaugeText: `${(Math.abs(first.x_m) * 2).toFixed(2)} m`,
        pressureKpa: first.pressure_kpa,
        distanceToPipeCrownM: first.x_m + offsetM,
        targetOffsetToAlignM: -first.x_m,
        patchIndices: indices,
      });
      tag++;
    });
  }

  // Calculate extent bounds for Section and Plan
  const patchXCoords = patches.flatMap((p) => [
    p.x_m + offsetM - p.width_x_m / 2,
    p.x_m + offsetM + p.width_x_m / 2,
  ]).concat(points.map((p) => p.x_m + offsetM));

  const allX = [...patchXCoords, -pipeOdM / 2, pipeOdM / 2, 0];
  if (!offsetIsWorst) allX.push(worstOffsetM);

  const minX = Math.min(...allX);
  const maxX = Math.max(...allX);
  const padX = Math.max(0.45, (maxX - minX) * 0.12);
  const extMinX = minX - padX;
  const extMaxX = maxX + padX;
  const spanX = Math.max(extMaxX - extMinX, 1.4);
  const midX = (extMinX + extMaxX) / 2;

  // =====================================================================
  // Section: Looking along the pipe (x across screen, z down)
  // =====================================================================
  const SW = 760;
  const SH = 330;
  const groundY = 88;
  const maxDepth = coverM + pipeOdM + 0.4;

  const scaleX = (SW - 60) / spanX;
  const scaleZ = (SH - groundY - 48) / maxDepth;
  const sectionScale = Math.min(scaleX, scaleZ);

  const sx = (m: number) => SW / 2 + (m - midX) * sectionScale;
  const sz = (m: number) => groundY + m * sectionScale;

  const pipeCy = sz(coverM + pipeOdM / 2);
  const pipeR = Math.max(5, (pipeOdM * sectionScale) / 2);

  // Helper to map patch index to axle tag
  const getAxleTagForPatch = (patchIdx: number): { tag: number; color: string; axleIdx: number } => {
    for (let i = 0; i < axleLines.length; i++) {
      if (axleLines[i].patchIndices.includes(patchIdx)) {
        return { tag: axleLines[i].tagIndex, color: BADGE_COLORS[i % BADGE_COLORS.length], axleIdx: i };
      }
    }
    return { tag: patchIdx + 1, color: BADGE_COLORS[patchIdx % BADGE_COLORS.length], axleIdx: patchIdx };
  };

  const section = (
    <svg viewBox={`0 0 ${SW} ${SH}`}
         style={{ width: "100%", height: "auto", maxHeight: 340, background: "#ffffff", borderRadius: 6 }}
         role="img" aria-label="Section through pipe and surface loads">
      {/* Ground & Soil Block */}
      <rect x={0} y={groundY} width={SW} height={SH - groundY} fill={SOIL} opacity={0.65} />
      <line x1={0} y1={groundY} x2={SW} y2={groundY} stroke="#5c5344" strokeWidth={2.5} />

      {/* Travel Direction */}
      {orientation === "across" ? (
        <TravelArrow x1={sx(midX) - 70} y1={22} x2={sx(midX) + 70} y2={22}
                     label="direction of travel (crossing pipe)" />
      ) : (
        <TravelIntoPage x={sx(midX) - 90} y={22} />
      )}

      {/* Surface load contact patches */}
      {patches.map((p, i) => {
        const x0 = sx(p.x_m + offsetM - p.width_x_m / 2);
        const x1 = sx(p.x_m + offsetM + p.width_x_m / 2);
        const cx = (x0 + x1) / 2;
        const w = Math.max(x1 - x0, 4);
        const h = 20;
        const { tag, color, axleIdx } = getAxleTagForPatch(i);
        const isHovered = hoveredAxleIdx === axleIdx;

        return (
          <g
            key={i}
            onMouseEnter={() => setHoveredAxleIdx(axleIdx)}
            onMouseLeave={() => setHoveredAxleIdx(null)}
            style={{ cursor: "pointer" }}
          >
            {/* Bearing footprint rectangle */}
            <rect
              x={x0}
              y={groundY - h}
              width={w}
              height={h}
              fill={isHovered ? "#fbbf24" : LOAD_FILL}
              stroke={isHovered ? "#b45309" : LOAD_EDGE}
              strokeWidth={isHovered ? 2.5 : 1.5}
            />

            {/* Load direction arrow */}
            <line x1={cx} y1={groundY - h - 16} x2={cx} y2={groundY - h - 2}
                  stroke={LOAD_EDGE} strokeWidth={1.6} />
            <polygon
              points={`${cx},${groundY - h} ${cx - 4},${groundY - h - 6} ${cx + 4},${groundY - h - 6}`}
              fill={LOAD_EDGE}
            />

            {/* Symmetrical Axle Tag Badge */}
            <circle
              cx={cx}
              cy={groundY - h - 26}
              r={9.5}
              fill={isHovered ? "#f59e0b" : color}
              stroke="#ffffff"
              strokeWidth={1.6}
            />
            <text
              x={cx}
              y={groundY - h - 22.5}
              textAnchor="middle"
              fontSize={10.5}
              fontWeight={700}
              fill="#ffffff"
            >
              {tag}
            </text>
          </g>
        );
      })}

      {points.map((p, i) => {
        const px = sx(p.x_m + offsetM);
        return (
          <g key={`pt-${i}`}>
            <line x1={px} y1={groundY - 38} x2={px} y2={groundY - 4}
                  stroke={LOAD_EDGE} strokeWidth={2.4} />
            <polygon points={`${px},${groundY} ${px - 5},${groundY - 8} ${px + 5},${groundY - 8}`}
                     fill={LOAD_EDGE} />
            <text x={px} y={groundY - 42} textAnchor="middle" fontSize={11}
                  fill={LOAD_EDGE} fontWeight={700}>{p.load_kn.toFixed(0)} kN</text>
          </g>
        );
      })}

      {/* Pipe Body & Centerline */}
      <circle cx={sx(0)} cy={pipeCy} r={pipeR} fill="#ffffff" stroke={PIPE} strokeWidth={2.8} />
      <line x1={sx(0)} y1={pipeCy - pipeR - 10} x2={sx(0)} y2={pipeCy + pipeR + 10}
            stroke={PIPE} strokeDasharray="5 3" strokeWidth={1.2} />
      <line x1={sx(0) - pipeR - 10} y1={pipeCy} x2={sx(0) + pipeR + 10} y2={pipeCy}
            stroke={PIPE} strokeDasharray="5 3" strokeWidth={1.2} />

      {/* Cover Dimension String */}
      <g stroke="#334155" fill="#334155" strokeWidth={1.2}>
        <line x1={sx(0) + pipeR + 32} y1={groundY} x2={sx(0) + pipeR + 32} y2={sz(coverM)} />
        <line x1={sx(0) + pipeR + 25} y1={groundY} x2={sx(0) + pipeR + 39} y2={groundY} />
        <line x1={sx(0) + pipeR + 25} y1={sz(coverM)} x2={sx(0) + pipeR + 39} y2={sz(coverM)} />
        <text x={sx(0) + pipeR + 45} y={(groundY + sz(coverM)) / 2 + 4}
              stroke="none" fontSize={11.5} fontWeight={700}>
          cover {coverM.toFixed(2)} m
        </text>
      </g>

      <text x={sx(0)} y={pipeCy + pipeR + 22} textAnchor="middle" fontSize={11.5} fontWeight={600} fill={PIPE}>
        OD {(pipeOdM * 1000).toFixed(0)} mm
      </text>

      {/* Machine Offset Dimension Line */}
      {Math.abs(offsetM) > 0.01 && (
        <DimLine
          x1={sx(0)}
          x2={sx(offsetM)}
          y={groundY + 38}
          label={`offset ${offsetM >= 0 ? "+" : ""}${offsetM.toFixed(2)} m`}
          fontSize={10.5}
        />
      )}

      {/* Pipe Centerline Vertical Reference Line */}
      <line x1={sx(0)} y1={groundY - 10} x2={sx(0)} y2={groundY + 28} stroke={PIPE} strokeWidth={1.2} strokeDasharray="4 3" />
      <text x={sx(0)} y={groundY + 54} textAnchor="middle" fontSize={10} fontWeight={600} fill={PIPE}>
        pipe CL
      </text>

      {/* Worst Position Callout */}
      {!offsetIsWorst && (
        <g>
          <line x1={sx(worstOffsetM)} y1={groundY - 6} x2={sx(worstOffsetM)} y2={groundY + 28}
                stroke="#dc2626" strokeWidth={1.8} strokeDasharray="4 3" />
          <text x={sx(worstOffsetM)} y={groundY + 70} textAnchor="middle"
                fontSize={10} fill="#dc2626" fontWeight={700}>
            worst position ({worstOffsetM >= 0 ? "+" : ""}{worstOffsetM.toFixed(2)} m)
          </text>
        </g>
      )}
    </svg>
  );

  // =====================================================================
  // Plan: Looking down (pipe along y horizontally, x across vertically)
  // =====================================================================
  const PW = 760;
  const PH = 300;
  const ys = patches.flatMap((p) => [
    p.y_m - p.length_y_m / 2, p.y_m + p.length_y_m / 2,
  ]).concat(points.map((p) => p.y_m));

  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padY = Math.max(0.6, (maxY - minY) * 0.15);
  const extMinY = minY - padY;
  const extMaxY = maxY + padY;
  const spanY = Math.max(extMaxY - extMinY, 1.6);

  const pScaleX = (PW - 70) / spanY;
  const pScaleY = (PH - 60) / spanX;
  const planScale = Math.min(pScaleX, pScaleY);

  const midY = (extMinY + extMaxY) / 2;
  const px_ = (m: number) => PW / 2 + (m - midY) * planScale;
  const py_ = (m: number) => PH / 2 - (m - midX) * planScale;

  const plan = (
    <svg viewBox={`0 0 ${PW} ${PH}`}
         style={{ width: "100%", height: "auto", maxHeight: 310, background: "#ffffff", borderRadius: 6 }}
         role="img" aria-label="Plan of surface loads relative to pipe">
      <rect x={0} y={0} width={PW} height={PH} fill={SOIL} opacity={0.45} />

      {/* Pipe Band & Centerline */}
      <rect x={0} y={py_(pipeOdM / 2)} width={PW} height={Math.max(Math.abs(py_(-pipeOdM / 2) - py_(pipeOdM / 2)), 4)}
            fill={PIPE} opacity={0.2} />
      <line x1={0} y1={py_(0)} x2={PW} y2={py_(0)} stroke={PIPE}
            strokeWidth={1.8} strokeDasharray="8 4" />
      <text x={12} y={py_(0) - 7} fontSize={11.5} fill={PIPE} fontWeight={700}>
        pipe centreline (y-axis)
      </text>

      {/* Travel Direction */}
      {orientation === "along" ? (
        <TravelArrow x1={PW - 100} y1={22} x2={PW - 30} y2={22} label="travel (along pipe)" />
      ) : (
        <TravelArrow x1={PW - 65} y1={36} x2={PW - 65} y2={86} label="travel (crossing)" />
      )}

      {/* Vehicle Symmetrical Centerline */}
      {orientation === "across" ? (
        <line x1={px_(-spanY / 2)} y1={py_(offsetM)} x2={px_(spanY / 2)} y2={py_(offsetM)}
              stroke="#64748b" strokeWidth={1.2} strokeDasharray="5 3" />
      ) : (
        <line x1={px_(0)} y1={py_(extMinX)} x2={px_(0)} y2={py_(extMaxX)}
              stroke="#64748b" strokeWidth={1.2} strokeDasharray="5 3" />
      )}

      {/* Symmetrical Contact Patches */}
      {patches.map((p, i) => {
        const x0 = px_(p.y_m - p.length_y_m / 2);
        const x1 = px_(p.y_m + p.length_y_m / 2);
        const y0 = py_(p.x_m + offsetM + p.width_x_m / 2);
        const y1 = py_(p.x_m + offsetM - p.width_x_m / 2);
        const cx = (x0 + x1) / 2;
        const cy = (y0 + y1) / 2;
        const { tag, color, axleIdx } = getAxleTagForPatch(i);
        const isHovered = hoveredAxleIdx === axleIdx;

        return (
          <g
            key={i}
            onMouseEnter={() => setHoveredAxleIdx(axleIdx)}
            onMouseLeave={() => setHoveredAxleIdx(null)}
            style={{ cursor: "pointer" }}
          >
            <rect
              x={Math.min(x0, x1)}
              y={Math.min(y0, y1)}
              width={Math.max(Math.abs(x1 - x0), 4)}
              height={Math.max(Math.abs(y1 - y0), 4)}
              fill={isHovered ? "#fbbf24" : LOAD_FILL}
              fillOpacity={isHovered ? 0.9 : 0.6}
              stroke={isHovered ? "#b45309" : LOAD_EDGE}
              strokeWidth={isHovered ? 2.4 : 1.5}
            />

            {/* Symmetrical Axle Tag Badge */}
            <circle
              cx={cx}
              cy={cy}
              r={8.5}
              fill={isHovered ? "#f59e0b" : color}
              stroke="#ffffff"
              strokeWidth={1.4}
            />
            <text
              x={cx}
              y={cy + 3.4}
              textAnchor="middle"
              fontSize={9.5}
              fontWeight={700}
              fill="#ffffff"
            >
              {tag}
            </text>
          </g>
        );
      })}

      {points.map((p, i) => (
        <circle key={i} cx={px_(p.y_m)} cy={py_(p.x_m + offsetM)} r={5.5}
                fill={LOAD_FILL} stroke={LOAD_EDGE} strokeWidth={1.6} />
      ))}

      {/* Perimeter Dimensions */}
      {vehicle && vehicle.wheelbase_m > 0 && (
        orientation === "across" ? (
          <VDimLine x={PW - 80}
                    y1={py_(offsetM - vehicle.wheelbase_m / 2)}
                    y2={py_(offsetM + vehicle.wheelbase_m / 2)}
                    label={`wheelbase ${vehicle.wheelbase_m.toFixed(2)} m`} />
        ) : (
          <DimLine x1={px_(-vehicle.wheelbase_m / 2)} x2={px_(vehicle.wheelbase_m / 2)}
                   y={PH - 28}
                   label={`wheelbase ${vehicle.wheelbase_m.toFixed(2)} m`} />
        )
      )}
      {vehicle && vehicle.gauge_m > 0 && (
        orientation === "across" ? (
          <DimLine x1={px_(-vehicle.gauge_m / 2)} x2={px_(vehicle.gauge_m / 2)}
                   y={PH - 28}
                   label={`${vehicle.is_tracked ? "track gauge" : "axle gauge"} ${vehicle.gauge_m.toFixed(2)} m`} />
        ) : (
          <VDimLine x={PW - 80}
                    y1={py_(offsetM - vehicle.gauge_m / 2)}
                    y2={py_(offsetM + vehicle.gauge_m / 2)}
                    label={`${vehicle.is_tracked ? "track gauge" : "axle gauge"} ${vehicle.gauge_m.toFixed(2)} m`} />
        )
      )}

      <text x={PW - 10} y={PH - 10} textAnchor="end" fontSize={10.5} fill="#475569">
        pipe runs left–right (horizontal); offset across pipe is vertical
      </text>
    </svg>
  );

  return (
    <div className="panel">
      {/* Panel Header */}
      <div style={{ marginBottom: 12 }}>
        <h2>Arrangement relative to pipe</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
          True-scale engineering sketches. Axles are symmetrical about vehicle centerline.
        </p>
      </div>

      {/* Vertical Stacked Layout: Plan View First (Top), Section View Second (Bottom) */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
        {/* 1. Plan View */}
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 6, padding: 10, background: "#fafafa" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>
              1. Plan View — Looking from above (Pipe runs left–right)
            </span>
            <span className="muted" style={{ fontSize: 11 }}>
              Scale: 1:1 true proportions (auto-zoomed to extent)
            </span>
          </div>
          {plan}
        </div>

        {/* 2. Section View */}
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 6, padding: 10, background: "#fafafa" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>
              2. Section View — Looking along pipe axis (x across, z depth)
            </span>
            <span className="muted" style={{ fontSize: 11 }}>
              Scale: 1:1 true proportions
            </span>
          </div>
          {section}
        </div>
      </div>

      {/* Symmetrical Axle & Footprint Schedule Table */}
      <div style={{ marginTop: 18 }}>
        <h3 style={{ fontSize: 13, marginBottom: 6, color: "#334155" }}>
          Symmetrical Vehicle Axle & Track Schedule
        </h3>
        <table>
          <thead>
            <tr>
              <th style={{ width: 44, textAlign: "center" }}>Tag</th>
              <th>Axle Line / Plant Component</th>
              <th>Symmetrical Configuration</th>
              <th className="num">Axle Load</th>
              <th className="num">Contact Dimensions</th>
              <th className="num">Track / Gauge</th>
              <th className="num">Contact Pressure</th>
              <th className="num">Distance to Crown</th>
              {onOffsetChange && <th style={{ textAlign: "center", width: 90 }}>Action</th>}
            </tr>
          </thead>
          <tbody>
            {axleLines.map((a, idx) => {
              const isHovered = hoveredAxleIdx === idx;
              const badgeColor = BADGE_COLORS[idx % BADGE_COLORS.length];
              const isDirectlyOverPipe = Math.abs(a.distanceToPipeCrownM) < 0.05;

              return (
                <tr
                  key={idx}
                  onMouseEnter={() => setHoveredAxleIdx(idx)}
                  onMouseLeave={() => setHoveredAxleIdx(null)}
                  style={{
                    background: isHovered ? "#fef3c7" : (isDirectlyOverPipe ? "#f0fdf4" : (idx % 2 === 1 ? "#fafafa" : "#ffffff")),
                    cursor: "pointer",
                    transition: "background 0.15s ease",
                  }}
                >
                  <td style={{ textAlign: "center" }}>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: badgeColor,
                        color: "#ffffff",
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      {a.tagIndex}
                    </span>
                  </td>
                  <td>
                    <b>{a.label}</b>
                    {isDirectlyOverPipe && (
                      <span style={{ fontSize: 10, marginLeft: 6, color: "#166534", fontWeight: 700, background: "#bbf7d0", padding: "1px 5px", borderRadius: 3 }}>
                        ON CROWN
                      </span>
                    )}
                  </td>
                  <td>
                    {a.configText}
                  </td>
                  <td className="num">
                    <b>{a.loadKn.toFixed(1)} kN</b>
                  </td>
                  <td className="num">
                    {a.dimText}
                  </td>
                  <td className="num">
                    {a.gaugeText}
                  </td>
                  <td className="num">
                    {a.pressureKpa.toFixed(0)} kPa
                  </td>
                  <td className="num">
                    <b style={{ color: isDirectlyOverPipe ? "#166534" : "inherit" }}>
                      {a.distanceToPipeCrownM >= 0 ? "+" : ""}{a.distanceToPipeCrownM.toFixed(2)} m
                    </b>
                  </td>
                  {onOffsetChange && (
                    <td style={{ textAlign: "center" }}>
                      <button
                        type="button"
                        style={{ padding: "3px 8px", fontSize: 11 }}
                        disabled={isDirectlyOverPipe}
                        onClick={(e) => {
                          e.stopPropagation();
                          onOffsetChange(Number(a.targetOffsetToAlignM.toFixed(2)));
                        }}
                      >
                        {isDirectlyOverPipe ? "Aligned" : "Align"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
