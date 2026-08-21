import type { LoadCase, LoadEcho, Reaction } from "../../api/types";

interface Props {
  lengthMm: number;
  supportsMm: number[];
  supportKinds: string[];
  loads: LoadEcho[];
  /** Empty while previewing - reactions only exist once the beam is analysed. */
  reactions: Reaction[];
  depthMm: number;
  /** Rendered bare, for embedding in the model preview panel. */
  bare?: boolean;
}

export const CASE_COLOUR: Record<LoadCase, string> = {
  D: "#6b7280",
  L: "#1f5fa8",
  S: "#0e8fa8",
  W: "#a86a00",
};

const CASE_NAME: Record<LoadCase, string> = {
  D: "Dead",
  L: "Live",
  S: "Snow",
  W: "Wind",
};

// Drawing is in an SVG user space of VB_W x VB_H; the viewBox scales it to fit.
const VB_W = 1000;
const PAD_L = 54;
const PAD_R = 54;
const BEAM_Y = 210;
const BEAM_H = 16;
const BAND_H = 34; // vertical space per stacked UDL band
const TOP_PAD = 18;

export default function BeamElevation({
  lengthMm,
  supportsMm,
  supportKinds,
  loads,
  reactions,
  depthMm,
  bare = false,
}: Props) {
  if (!lengthMm) return null;

  const usable = VB_W - PAD_L - PAD_R;
  const sx = (mm: number) => PAD_L + (mm / lengthMm) * usable;

  const udls = loads.filter((l) => l.kind === "udl");
  const points = loads.filter((l) => l.kind === "point");

  // Stack UDL bands upward from the beam, heaviest at the bottom.
  const ordered = [...udls].sort((a, b) => a.magnitude - b.magnitude);
  const bandTop = (i: number) => BEAM_Y - 26 - (i + 1) * BAND_H;
  const topOfLoads = ordered.length ? bandTop(ordered.length - 1) : BEAM_Y - 40;
  const pointHeadroom = points.length ? 58 : 0;
  const vbTop = Math.min(topOfLoads, BEAM_Y - 40 - pointHeadroom) - TOP_PAD;
  const vbBottom = reactions.length ? 330 : 268;
  const VB_H = vbBottom - vbTop;

  const maxUdl = Math.max(...udls.map((l) => Math.abs(l.magnitude)), 1e-9);
  const maxPoint = Math.max(...points.map((l) => Math.abs(l.magnitude)), 1e-9);

  const support = (x: number, kind: string, i: number) => {
    const px = sx(x);
    const y = BEAM_Y + BEAM_H;
    const w = 13;
    const h = 20;
    return (
      <g key={`sup-${i}`}>
        {kind === "fixed" ? (
          <>
            <line x1={px} y1={y - BEAM_H - 8} x2={px} y2={y + h}
                  stroke="#1a1d21" strokeWidth={3} />
            {[0, 1, 2, 3, 4].map((k) => (
              <line key={k} x1={px} y1={y - BEAM_H - 4 + k * 8}
                    x2={px - 9} y2={y - BEAM_H + 3 + k * 8}
                    stroke="#1a1d21" strokeWidth={1.4} />
            ))}
          </>
        ) : (
          <polygon points={`${px},${y} ${px - w},${y + h} ${px + w},${y + h}`}
                   fill="none" stroke="#1a1d21" strokeWidth={2} />
        )}
        {kind === "roller" && (
          <>
            <circle cx={px - 6} cy={y + h + 5} r={4.5}
                    fill="none" stroke="#1a1d21" strokeWidth={1.8} />
            <circle cx={px + 6} cy={y + h + 5} r={4.5}
                    fill="none" stroke="#1a1d21" strokeWidth={1.8} />
          </>
        )}
        {kind !== "fixed" && (
          <line x1={px - 24} y1={y + h + (kind === "roller" ? 10 : 0)}
                x2={px + 24} y2={y + h + (kind === "roller" ? 10 : 0)}
                stroke="#1a1d21" strokeWidth={2.5} />
        )}
        <text x={px} y={y + h + 26} textAnchor="middle" fontSize={12} fill="#626b76">
          {String.fromCharCode(65 + i)}
        </text>
      </g>
    );
  };

  const svg = (
      <svg
        viewBox={`0 ${vbTop} ${VB_W} ${VB_H}`}
        style={{ width: "100%", height: "auto", maxHeight: 420 }}
        role="img"
        aria-label="Beam elevation showing applied loads, supports and reactions"
      >
        {/* ---- distributed loads, stacked ---- */}
        {ordered.map((l, i) => {
          const x1 = sx(l.x_start_mm);
          const x2 = sx(l.x_end_mm);
          const colour = CASE_COLOUR[l.case] ?? "#6b7280";
          const top = bandTop(i);
          const h = 8 + 16 * (Math.abs(l.magnitude) / maxUdl);
          const base = top + BAND_H - 8;
          const nArrows = Math.max(2, Math.min(26, Math.round((x2 - x1) / 34)));
          return (
            <g key={`udl-${i}`} opacity={l.is_self_weight ? 0.55 : 1}>
              <rect x={x1} y={base - h} width={x2 - x1} height={h}
                    fill={colour} opacity={0.14} />
              <line x1={x1} y1={base - h} x2={x2} y2={base - h}
                    stroke={colour} strokeWidth={2} />
              {Array.from({ length: nArrows + 1 }, (_, k) => {
                const px = x1 + ((x2 - x1) * k) / nArrows;
                return (
                  <g key={k}>
                    <line x1={px} y1={base - h} x2={px} y2={base}
                          stroke={colour} strokeWidth={1.2} />
                    <polygon points={`${px},${base + 3} ${px - 3},${base - 3} ${px + 3},${base - 3}`}
                             fill={colour} />
                  </g>
                );
              })}
              <text x={x1 + 6} y={base - h - 5} fontSize={12.5} fill={colour}
                    fontWeight={600}>
                {CASE_NAME[l.case] ?? l.case} {Math.abs(l.magnitude).toFixed(2)} kN/m
                {l.is_self_weight ? " (self wt.)" : ""}
              </text>
            </g>
          );
        })}

        {/* ---- point loads ---- */}
        {points.map((l, i) => {
          const px = sx(l.x_start_mm);
          const colour = CASE_COLOUR[l.case] ?? "#6b7280";
          const len = 30 + 26 * (Math.abs(l.magnitude) / maxPoint);
          const top = BEAM_Y - 26 - len;
          return (
            <g key={`pt-${i}`}>
              <line x1={px} y1={top} x2={px} y2={BEAM_Y - 22}
                    stroke={colour} strokeWidth={2.4} />
              <polygon points={`${px},${BEAM_Y - 17} ${px - 5.5},${BEAM_Y - 27} ${px + 5.5},${BEAM_Y - 27}`}
                       fill={colour} />
              <text x={px} y={top - 5} textAnchor="middle" fontSize={12.5}
                    fill={colour} fontWeight={600}>
                {CASE_NAME[l.case] ?? l.case} {Math.abs(l.magnitude).toFixed(1)} kN
              </text>
            </g>
          );
        })}

        {/* ---- the beam ---- */}
        <rect x={sx(0)} y={BEAM_Y} width={sx(lengthMm) - sx(0)} height={BEAM_H}
              fill="#c8ccd2" stroke="#1a1d21" strokeWidth={1.6} />

        {supportsMm.map((x, i) => support(x, supportKinds[i] ?? "roller", i))}

        {/* ---- reactions ---- */}
        {reactions.map((r, i) => {
          const px = sx(r.x_mm);
          const y0 = BEAM_Y + BEAM_H + 62;
          const over = r.bearing_ratio > 1;
          return (
            <g key={`rx-${i}`}>
              <line x1={px} y1={y0 + 26} x2={px} y2={y0 + 2}
                    stroke={over ? "#c02020" : "#0a7a2a"} strokeWidth={2.2} />
              <polygon points={`${px},${y0 - 3} ${px - 5},${y0 + 6} ${px + 5},${y0 + 6}`}
                       fill={over ? "#c02020" : "#0a7a2a"} />
              <text x={px} y={y0 + 41} textAnchor="middle" fontSize={12.5}
                    fontWeight={700} fill={over ? "#c02020" : "#0a7a2a"}>
                {r.max_kn.toFixed(1)} kN
              </text>
              <text x={px} y={y0 + 55} textAnchor="middle" fontSize={11} fill="#626b76">
                brg {r.required_bearing_mm.toFixed(0)} mm
              </text>
            </g>
          );
        })}

        {/* ---- span dimensions ---- */}
        {supportsMm.slice(0, -1).map((a, i) => {
          const b = supportsMm[i + 1];
          const y = BEAM_Y - 6;
          const xa = sx(a);
          const xb = sx(b);
          const mid = (xa + xb) / 2;
          const m = (b - a) / 1000;
          const ft = (b - a) / 304.8;
          return (
            <g key={`dim-${i}`} stroke="#626b76" fill="#626b76">
              <line x1={xa} y1={y} x2={xb} y2={y} strokeWidth={1} />
              <line x1={xa} y1={y - 4} x2={xa} y2={y + 4} strokeWidth={1} />
              <line x1={xb} y1={y - 4} x2={xb} y2={y + 4} strokeWidth={1} />
              <rect x={mid - 52} y={y - 10} width={104} height={14}
                    fill="#ffffff" stroke="none" />
              <text x={mid} y={y + 1} textAnchor="middle" fontSize={12}
                    stroke="none" fontWeight={600}>
                {m.toFixed(3)} m ({ft.toFixed(2)} ft)
              </text>
            </g>
          );
        })}

        {/* Kept clear of the right-hand support symbol. */}
        <text x={sx(lengthMm)} y={BEAM_Y - 22} textAnchor="end"
              fontSize={11} fill="#626b76">
          section depth {depthMm.toFixed(0)} mm
        </text>
      </svg>
  );

  if (bare) return svg;

  return (
    <div className="panel">
      <p className="chart-title">Beam elevation — loads, supports and reactions</p>
      <p className="chart-sub">
        Specified (unfactored) loads. Reactions are factored envelope maxima.
      </p>
      {svg}
    </div>
  );
}
