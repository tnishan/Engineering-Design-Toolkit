import { useMemo } from "react";
import type { SoilBulb, SoilPatch } from "../../api/types";
import { STOPS, fieldToPng } from "./colourRamp";

interface Props {
  bulb: SoilBulb;
  patches: SoilPatch[];
  offsetM: number;
  coverM: number;
  pipeOdM: number;
}

const VB_W = 760;
const VB_H = 330;
const PAD_L = 58;
const PAD_R = 96; // room for the colour scale
const PAD_T = 34;
const PAD_B = 40;

export default function PressureBulb({
  bulb, patches, offsetM, coverM, pipeOdM,
}: Props) {
  const { x_m: xs, depth_m: zs, grid_kpa: grid, peak_kpa: peak, isolines } = bulb;

  /**
   * The stress field goes onto a canvas at one pixel per sample and is
   * embedded as a single image. Drawing it as one SVG rect per cell instead
   * cost 7,600 nodes and 1.2 MB of markup per redraw, which the browser had
   * to re-diff on every keystroke. The browser's own smoothing when the
   * image is scaled up also reads better than hard-edged cells.
   */
  const imageHref = useMemo(() => fieldToPng(grid, peak), [grid, peak]);

  if (!xs?.length || !zs?.length || !grid?.length) return null;

  const xMin = xs[0];
  const xMax = xs[xs.length - 1];
  const zMin = zs[0];
  const zMax = zs[zs.length - 1];

  const plotW = VB_W - PAD_L - PAD_R;
  const plotH = VB_H - PAD_T - PAD_B;
  const px = (m: number) => PAD_L + ((m - xMin) / (xMax - xMin)) * plotW;
  const pz = (m: number) => PAD_T + (m / zMax) * plotH;

  const surfaceY = pz(0);
  const pipeCy = pz(coverM + pipeOdM / 2);
  const pipeR = Math.max(2.5, (pz(pipeOdM) - pz(0)) / 2);

  // One path per contour level rather than one element per segment.
  const contourPaths = isolines.map((line) => ({
    level: line.level_kpa,
    d: line.segments
      .map((s) => `M${px(s[0][0]).toFixed(1)},${pz(s[0][1]).toFixed(1)}`
                + `L${px(s[1][0]).toFixed(1)},${pz(s[1][1]).toFixed(1)}`)
      .join(""),
    label: line.segments.length
      ? line.segments[Math.floor(line.segments.length / 2)][0]
      : null,
  }));

  return (
    <div className="panel">
      <p className="chart-title">Pressure bulb through the section</p>
      <p className="chart-sub">
        Boussinesq vertical stress on the plane through the worst point along the
        pipe. Contours are in kPa; the circle is the pipe.
      </p>
      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} style={{ width: "100%", height: "auto", maxHeight: 330 }}
           role="img" aria-label="Contours of vertical stress beneath the surface load">
        {/* stress field */}
        {imageHref && (
          <image
            href={imageHref}
            x={PAD_L}
            y={pz(zMin)}
            width={plotW}
            height={pz(zMax) - pz(zMin)}
            preserveAspectRatio="none"
          />
        )}

        {/* contour lines */}
        {contourPaths.map((c) => (
          <g key={c.level}>
            <path d={c.d} fill="none" stroke="#2b2b2b"
                  strokeWidth={0.9} strokeOpacity={0.55} />
            {c.label && (
              <text x={px(c.label[0]) + 4} y={pz(c.label[1]) - 3}
                    fontSize={10} fill="#2b2b2b" fontWeight={600}>
                {c.level}
              </text>
            )}
          </g>
        ))}

        {/* ground surface and the bearing areas */}
        <line x1={PAD_L} y1={surfaceY} x2={VB_W - PAD_R} y2={surfaceY}
              stroke="#3a352b" strokeWidth={2} />
        {patches.map((p, i) => {
          const a = px(p.x_m + offsetM - p.width_x_m / 2);
          const b = px(p.x_m + offsetM + p.width_x_m / 2);
          if (b < PAD_L || a > VB_W - PAD_R) return null;
          return (
            <rect key={i} x={Math.max(a, PAD_L)} y={surfaceY - 13}
                  width={Math.max(Math.min(b, VB_W - PAD_R) - Math.max(a, PAD_L), 2)}
                  height={13} fill="#c8752a" stroke="#8a4d15" strokeWidth={1.2} />
          );
        })}

        {/* pipe */}
        <circle cx={px(0)} cy={pipeCy} r={pipeR}
                fill="#fff" fillOpacity={0.3} stroke="#12315c" strokeWidth={2.4} />

        {/* axes */}
        <g stroke="#5c5344" fill="#5c5344" fontSize={10.5}>
          <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={VB_H - PAD_B} strokeWidth={1} />
          {[0, 0.25, 0.5, 0.75, 1].map((f) => {
            const d = f * zMax;
            return (
              <g key={f}>
                <line x1={PAD_L - 4} y1={pz(d)} x2={PAD_L} y2={pz(d)} strokeWidth={1} />
                <text x={PAD_L - 7} y={pz(d) + 3.5} textAnchor="end" stroke="none">
                  {d.toFixed(1)}
                </text>
              </g>
            );
          })}
          <text x={16} y={(PAD_T + VB_H - PAD_B) / 2} stroke="none" fontSize={11}
                textAnchor="middle" transform={`rotate(-90 16 ${(PAD_T + VB_H - PAD_B) / 2})`}>
            Depth (m)
          </text>
          {[xMin, xMin / 2, 0, xMax / 2, xMax].map((m, i) => (
            <g key={i}>
              <line x1={px(m)} y1={VB_H - PAD_B} x2={px(m)} y2={VB_H - PAD_B + 4}
                    strokeWidth={1} />
              <text x={px(m)} y={VB_H - PAD_B + 16} textAnchor="middle" stroke="none">
                {m.toFixed(1)}
              </text>
            </g>
          ))}
          <text x={(PAD_L + VB_W - PAD_R) / 2} y={VB_H - 6} textAnchor="middle"
                stroke="none" fontSize={11}>
            Distance from pipe centreline (m)
          </text>
        </g>

        {/* colour scale */}
        <g>
          <defs>
            <linearGradient id="bulbScale" x1="0" y1="1" x2="0" y2="0">
              {STOPS.map(([p, c]) => (
                <stop key={p} offset={`${p * 100}%`} stopColor={`rgb(${c.join(",")})`} />
              ))}
            </linearGradient>
          </defs>
          <rect x={VB_W - PAD_R + 20} y={PAD_T} width={16} height={plotH}
                fill="url(#bulbScale)" stroke="#8a8578" strokeWidth={0.8} />
          <text x={VB_W - PAD_R + 42} y={PAD_T + 4} fontSize={10.5} fill="#5c5344">
            {peak.toFixed(0)}
          </text>
          <text x={VB_W - PAD_R + 42} y={VB_H - PAD_B} fontSize={10.5} fill="#5c5344">
            0
          </text>
          <text x={VB_W - PAD_R + 28} y={PAD_T - 14} fontSize={10.5} fill="#5c5344"
                textAnchor="middle">
            kPa
          </text>
        </g>
      </svg>
    </div>
  );
}
