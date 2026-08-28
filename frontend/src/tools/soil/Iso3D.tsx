import { useMemo, useState } from "react";
import type { SoilBulb, SoilCrownPlan, SoilPatch } from "../../api/types";
import { fieldToPng } from "./colourRamp";

interface Props {
  bulb: SoilBulb;
  crownPlan: SoilCrownPlan;
  patches: SoilPatch[];
  offsetM: number;
  coverM: number;
  pipeOdM: number;
  orientation?: "along" | "across";
}

const VB_W = 780;
const VB_H = 340;
const COS30 = Math.cos(Math.PI / 6);
const SIN30 = 0.5;

type P2 = { x: number; y: number };

/**
 * Isometric projection.
 *
 * x runs across the pipe, y along it, z down into the ground. Rendering in
 * SVG rather than WebGL keeps the view printable in the calc report and costs
 * no dependency; the projection of a rectangle is a parallelogram, so the
 * stress fields can be painted onto the cut planes with an affine transform
 * with no distortion.
 */
function project(x: number, y: number, z: number, scale: number, o: P2): P2 {
  return {
    x: o.x + (x - y) * COS30 * scale,
    y: o.y + ((x + y) * SIN30 + z) * scale,
  };
}

/** Affine matrix mapping an image's own box onto a projected parallelogram. */
function imageMatrix(p0: P2, pu: P2, pv: P2, w: number, h: number): string {
  const a = (pu.x - p0.x) / w;
  const b = (pu.y - p0.y) / w;
  const c = (pv.x - p0.x) / h;
  const d = (pv.y - p0.y) / h;
  return `matrix(${a} ${b} ${c} ${d} ${p0.x} ${p0.y})`;
}

/** Andrew monotone chain — used for the pipe's silhouette. */
function convexHull(points: P2[]): P2[] {
  const pts = [...points].sort((p, q) => (p.x - q.x) || (p.y - q.y));
  const cross = (o: P2, a: P2, b: P2) =>
    (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const build = (src: P2[]) => {
    const out: P2[] = [];
    for (const p of src) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], p) <= 0) {
        out.pop();
      }
      out.push(p);
    }
    out.pop();
    return out;
  };
  return [...build(pts), ...build([...pts].reverse())];
}

const path = (pts: P2[]) =>
  pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("") + "Z";

export default function Iso3D({
  bulb, crownPlan, patches, offsetM, coverM, pipeOdM, orientation = "across",
}: Props) {
  const [showCrown, setShowCrown] = useState(true);

  const sectionPng = useMemo(
    () => fieldToPng(bulb.grid_kpa, bulb.peak_kpa), [bulb.grid_kpa, bulb.peak_kpa],
  );
  /*
   * Only the rows in the cut-away quarter are painted, and both planes are
   * normalised to the same peak so a colour means the same stress on each.
   * Normalising them separately made the crown slice look as hot as the
   * surface, which it is not.
   */
  const revealed = useMemo(() => {
    const rows = (crownPlan.y_m ?? []).map((y, i) => ({ y, i }))
      .filter((r) => r.y >= 0);
    return rows.map((r) => crownPlan.grid_kpa[r.i]);
  }, [crownPlan.y_m, crownPlan.grid_kpa]);

  const planPng = useMemo(
    () => fieldToPng(revealed, bulb.peak_kpa, 0.32), [revealed, bulb.peak_kpa],
  );

  const geometry = useMemo(() => {
    const xs = bulb.x_m ?? [];
    const zs = bulb.depth_m ?? [];
    const ys = crownPlan.y_m ?? [];
    if (!xs.length || !zs.length || !ys.length) return null;

    const xMin = xs[0];
    const xMax = xs[xs.length - 1];
    const yMin = ys[0];
    const yMax = ys[ys.length - 1];
    const zMax = zs[zs.length - 1];

    // Choose a scale that fits the projected bounding box into the viewBox.
    const probe = (s: number, o: P2) => {
      const corners: P2[] = [];
      for (const x of [xMin, xMax]) {
        for (const y of [yMin, yMax]) {
          for (const z of [0, zMax]) corners.push(project(x, y, z, s, o));
        }
      }
      return corners;
    };
    const unit = probe(1, { x: 0, y: 0 });
    const w = Math.max(...unit.map((p) => p.x)) - Math.min(...unit.map((p) => p.x));
    const h = Math.max(...unit.map((p) => p.y)) - Math.min(...unit.map((p) => p.y));
    const scale = Math.min((VB_W - 150) / w, (VB_H - 70) / h);

    const raw = probe(scale, { x: 0, y: 0 });
    const origin: P2 = {
      x: (VB_W - 34) / 2 - (Math.min(...raw.map((p) => p.x))
        + Math.max(...raw.map((p) => p.x))) / 2,
      y: 38 - Math.min(...raw.map((p) => p.y)),
    };
    return { xMin, xMax, yMin, yMax, zMax, scale, origin };
  }, [bulb.x_m, bulb.depth_m, crownPlan.y_m]);

  if (!geometry) return null;
  const { xMin, xMax, yMin, yMax, zMax, scale, origin } = geometry;
  const p = (x: number, y: number, z: number) => project(x, y, z, scale, origin);

  // The section is cut at y = 0 in reported coordinates (the worst point
  // along the pipe, which is where the bulb was sampled).
  const yCut = 0;
  const pipeZ = coverM + pipeOdM / 2;
  const pipeR = pipeOdM / 2;

  /*
   * A cutaway, with the quarter NEAREST the viewer removed.
   */
  const ground = [p(xMin, yMin, 0), p(xMax, yMin, 0), p(xMax, yCut, 0), p(xMin, yCut, 0)];
  const backWall = [p(xMin, yMin, 0), p(xMax, yMin, 0), p(xMax, yMin, zMax), p(xMin, yMin, zMax)];
  const sideWall = [p(xMin, yMin, 0), p(xMin, yCut, 0), p(xMin, yCut, zMax), p(xMin, yMin, zMax)];

  // Pipe silhouette: hull of the two projected end circles.
  const ring = (y: number) =>
    Array.from({ length: 48 }, (_, i) => {
      const t = (i / 48) * Math.PI * 2;
      return p(pipeR * Math.cos(t), y, pipeZ + pipeR * Math.sin(t));
    });
  const nearRing = ring(yMax);
  const pipeBody = convexHull([...nearRing, ...ring(yCut)]);

  const patchQuad = (patch: SoilPatch, y0: number, y1: number) => {
    const x0 = patch.x_m + offsetM - patch.width_x_m / 2;
    const x1 = patch.x_m + offsetM + patch.width_x_m / 2;
    return [p(x0, y0, 0), p(x1, y0, 0), p(x1, y1, 0), p(x0, y1, 0)];
  };

  // Travel arrow coordinates on ground surface (behind the cut in the visible quadrant)
  const arrowBaseX = offsetM;
  const arrowBaseY = (yMin + yCut) / 2;
  const arrowLen = Math.min(1.8, (xMax - xMin) / 4);

  const travelArrowStart = orientation === "across"
    ? p(arrowBaseX - arrowLen / 2, arrowBaseY, 0)
    : p(arrowBaseX, arrowBaseY - arrowLen / 2, 0);

  const travelArrowEnd = orientation === "across"
    ? p(arrowBaseX + arrowLen / 2, arrowBaseY, 0)
    : p(arrowBaseX, arrowBaseY + arrowLen / 2, 0);

  return (
    <div className="panel">
      <div className="model-head">
        <div>
          <p className="chart-title">Three-dimensional view</p>
          <p className="chart-sub">
            Isometric cutaway showing machine bearing areas, travel direction, pipe alignment, and stress dissipation.
          </p>
        </div>
        <label className="inline" style={{ margin: 0, whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={showCrown}
                 onChange={(e) => setShowCrown(e.target.checked)} />
          <span style={{ marginBottom: 0 }}>Crown plane</span>
        </label>
      </div>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`}
           style={{ width: "100%", height: "auto", maxHeight: 360 }}
           role="img" aria-label="Isometric view of the loads, pipe and pressure bulb">
        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <polygon points="0 0, 6 3, 0 6" fill="#b91c1c" />
          </marker>
        </defs>

        {/* soil block: far faces, then the surface behind the cut */}
        <path d={path(backWall)} fill="#ded6c6" stroke="#a89c85" strokeWidth={1} />
        <path d={path(sideWall)} fill="#d3cab8" stroke="#a89c85" strokeWidth={1} />
        <path d={path(ground)} fill="#efe9dc" stroke="#a89c85" strokeWidth={1} />

        {/* bearing areas: solid where the ground remains, ghosted where the
            block has been cut away so the load is still legible */}
        {patches.map((patch, i) => {
          const y0 = patch.y_m - patch.length_y_m / 2;
          const y1 = patch.y_m + patch.length_y_m / 2;
          const solid = y0 < yCut
            ? patchQuad(patch, y0, Math.min(y1, yCut)) : null;
          const ghost = y1 > yCut
            ? patchQuad(patch, Math.max(y0, yCut), y1) : null;
          return (
            <g key={i}>
              {solid && (
                <path d={path(solid)} fill="#c8752a" fillOpacity={0.85}
                      stroke="#7d440f" strokeWidth={1.2} />
              )}
              {ghost && (
                <path d={path(ghost)} fill="#c8752a" fillOpacity={0.32}
                      stroke="#7d440f" strokeWidth={1.2} strokeDasharray="5 3" />
              )}
            </g>
          );
        })}

        {/* Travel direction arrow on ground surface */}
        <g>
          <line
            x1={travelArrowStart.x}
            y1={travelArrowStart.y}
            x2={travelArrowEnd.x}
            y2={travelArrowEnd.y}
            stroke="#b91c1c"
            strokeWidth={2.5}
            markerEnd="url(#arrowhead)"
          />
          <text
            x={travelArrowEnd.x + (orientation === "across" ? 8 : -8)}
            y={travelArrowEnd.y - 4}
            fontSize={9.5}
            fontWeight={600}
            fill="#b91c1c"
            textAnchor={orientation === "across" ? "start" : "end"}
          >
            {orientation === "across" ? "Travel: Crossing Pipe →" : "Travel: Along Pipe →"}
          </text>
        </g>

        {/* the cut face, carrying the pressure bulb */}
        {sectionPng && (
          <g>
            <image href={sectionPng}
                   transform={imageMatrix(
                     p(xMin, yCut, 0), p(xMax, yCut, 0),
                     p(xMin, yCut, zMax), bulb.x_m.length, bulb.depth_m.length)}
                   width={bulb.x_m.length} height={bulb.depth_m.length}
                   preserveAspectRatio="none" />
            <path d={path([p(xMin, yCut, 0), p(xMax, yCut, 0),
                           p(xMax, yCut, zMax), p(xMin, yCut, zMax)])}
                  fill="none" stroke="#3a352b" strokeWidth={1.3} />
            <text x={p(xMin, yCut, 0).x - 4} y={p(xMin, yCut, 0).y - 6}
                  fontSize={9.5} fill="#3a352b" textAnchor="end">
              section, peak {bulb.peak_kpa.toFixed(0)} kPa
            </text>
          </g>
        )}

        {/* crown-level slice, revealed inside the cut-away quarter */}
        {showCrown && planPng && (
          <g opacity={0.9}>
            <image href={planPng}
                   transform={imageMatrix(
                     p(xMin, yCut, coverM), p(xMax, yCut, coverM),
                     p(xMin, yMax, coverM), crownPlan.x_m.length, revealed.length)}
                   width={crownPlan.x_m.length} height={revealed.length}
                   preserveAspectRatio="none" />
            <path d={path([p(xMin, yCut, coverM), p(xMax, yCut, coverM),
                           p(xMax, yMax, coverM), p(xMin, yMax, coverM)])}
                  fill="none" stroke="#4a4336" strokeWidth={1} strokeDasharray="4 3" />
            <text x={p(xMax, yCut, coverM).x + 6} y={p(xMax, yCut, coverM).y + 4}
                  fontSize={9.5} fill="#4a4336">
              crown {coverM.toFixed(2)} m, peak {crownPlan.peak_kpa.toFixed(0)} kPa
            </text>
          </g>
        )}

        {/* the pipe */}
        <path d={path(pipeBody)} fill="#7f9ec4" fillOpacity={0.9}
              stroke="#12315c" strokeWidth={1.3} />
        <path d={path(nearRing)} fill="#f2f6fb" stroke="#12315c" strokeWidth={1.6} />
        <text x={p(0, yMax, pipeZ).x} y={p(0, yMax, pipeZ).y + 3}
              textAnchor="middle" fontSize={9.5} fill="#12315c" fontWeight={600}>
          pipe
        </text>

        {/* axes */}
        <g stroke="#5c5344" fill="#5c5344" fontSize={10}>
          <text x={p(xMax, yMin, 0).x + 10} y={p(xMax, yMin, 0).y + 12}>
            across pipe (x) →
          </text>
          <text x={p(xMin, yMax, 0).x - 10} y={p(xMin, yMax, 0).y - 6} textAnchor="end">
            ← along pipe (y)
          </text>
          <text x={p(xMin, yMin, zMax).x - 8} y={p(xMin, yMin, zMax).y + 4}
                textAnchor="end">
            depth (z) to {zMax.toFixed(1)} m
          </text>
        </g>
      </svg>
    </div>
  );
}

