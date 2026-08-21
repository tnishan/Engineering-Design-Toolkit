import type { Orientation, SoilPatch, SoilPoint } from "../../api/types";

interface Props {
  patches: SoilPatch[];
  points: SoilPoint[];
  coverM: number;
  pipeOdM: number;
  offsetM: number;
  worstOffsetM: number;
  offsetIsWorst: boolean;
  orientation: Orientation;
}

const LOAD_FILL = "#c8752a";
const LOAD_EDGE = "#8a4d15";
const SOIL = "#e8e0cf";
const PIPE = "#1f5fa8";
const TRAVEL = "#0a7a2a";

/** Round a span up to a tidy number so the drawing does not jitter while typing. */
function tidy(value: number): number {
  const steps = [1, 2, 2.5, 5, 10, 20, 25, 50];
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(value, 0.1)));
  return (steps.find((s) => s * magnitude >= value) ?? 10) * magnitude;
}

/** A double-ended horizontal dimension line with its value centred underneath. */
function DimLine({
  x1, x2, y, label,
}: { x1: number; x2: number; y: number; label: string }) {
  const tick = 3.5;
  const mid = (x1 + x2) / 2;
  return (
    <g stroke="#4a4336" fill="#4a4336" strokeWidth={0.9}>
      <line x1={x1} y1={y} x2={x2} y2={y} />
      <line x1={x1} y1={y - tick} x2={x1} y2={y + tick} />
      <line x1={x2} y1={y - tick} x2={x2} y2={y + tick} />
      <text x={mid} y={y - 4} stroke="none" fontSize={9} textAnchor="middle">{label}</text>
    </g>
  );
}

/** Arrowhead-tipped line showing the direction of travel. */
function TravelArrow({
  x1, y1, x2, y2, label,
}: { x1: number; y1: number; x2: number; y2: number; label: string }) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const back = 8;
  const spread = 3.6;
  const bx = x2 - back * Math.cos(angle);
  const by = y2 - back * Math.sin(angle);
  const wx = -Math.sin(angle) * spread;
  const wy = Math.cos(angle) * spread;
  return (
    <g stroke={TRAVEL} fill={TRAVEL}>
      <line x1={x1} y1={y1} x2={bx} y2={by} strokeWidth={1.8} />
      <polygon points={`${x2},${y2} ${bx + wx},${by + wy} ${bx - wx},${by - wy}`} />
      <text x={(x1 + x2) / 2} y={Math.min(y1, y2) - 6} stroke="none" fontSize={10}
            fontWeight={600} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

/** Perpendicular-to-the-page travel symbol (circle-dot), drafting convention. */
function TravelIntoPage({ x, y }: { x: number; y: number }) {
  return (
    <g stroke={TRAVEL} fill="none">
      <circle cx={x} cy={y} r={9} strokeWidth={1.6} />
      <circle cx={x} cy={y} r={2.2} fill={TRAVEL} />
      <text x={x + 15} y={y + 4} stroke="none" fill={TRAVEL} fontSize={10} fontWeight={600}>
        travel (out of section)
      </text>
    </g>
  );
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
}: Props) {
  if (!patches.length && !points.length) return null;

  const xs = patches.flatMap((p) => [
    p.x_m + offsetM - p.width_x_m / 2,
    p.x_m + offsetM + p.width_x_m / 2,
  ]).concat(points.map((p) => p.x_m + offsetM));
  const halfX = tidy(Math.max(...xs.map(Math.abs), pipeOdM, 1) * 1.25);

  // =====================================================================
  // Section: looking along the pipe. x across, z down. A single px/metre
  // scale is used for BOTH axes so the pipe renders as a true circle and a
  // load's drawn width is genuinely proportioned against the depth scale.
  // =====================================================================
  const SW = 720;
  const SH = 340;
  const groundY = 92;
  const depthShown = tidy(Math.max(coverM + pipeOdM, 1) * 1.45);
  const sectionScale = Math.min(
    (SW / 2 - 40) / halfX,
    (SH - groundY - 34) / depthShown,
  );
  const sx = (m: number) => SW / 2 + m * sectionScale;
  const sz = (m: number) => groundY + m * sectionScale;

  const pipeCy = sz(coverM + pipeOdM / 2);
  const pipeR = Math.max(3, (pipeOdM * sectionScale) / 2);

  const section = (
    <svg viewBox={`0 0 ${SW} ${SH}`}
         style={{ width: "100%", height: "auto", maxHeight: 260 }}
         role="img" aria-label="Section through the pipe and surface loads">
      <rect x={0} y={groundY} width={SW} height={SH - groundY} fill={SOIL} />
      <line x1={0} y1={groundY} x2={SW} y2={groundY} stroke="#5c5344" strokeWidth={2} />

      {orientation === "across" ? (
        <TravelArrow x1={sx(0) - 60} y1={22} x2={sx(0) + 60} y2={22}
                     label="direction of travel" />
      ) : (
        <TravelIntoPage x={sx(0) - 80} y={22} />
      )}

      {/* loads bearing on the surface */}
      {patches.map((p, i) => {
        const x0 = sx(p.x_m + offsetM - p.width_x_m / 2);
        const x1 = sx(p.x_m + offsetM + p.width_x_m / 2);
        const h = 17;
        return (
          <g key={i}>
            <rect x={x0} y={groundY - h} width={Math.max(x1 - x0, 2)} height={h}
                  fill={LOAD_FILL} stroke={LOAD_EDGE} strokeWidth={1.4} />
            {[0.2, 0.5, 0.8].map((f) => {
              const px = x0 + (x1 - x0) * f;
              return (
                <g key={f}>
                  <line x1={px} y1={groundY - h - 15} x2={px} y2={groundY - h - 3}
                        stroke={LOAD_EDGE} strokeWidth={1.3} />
                  <polygon
                    points={`${px},${groundY - h} ${px - 3.2},${groundY - h - 5} ${px + 3.2},${groundY - h - 5}`}
                    fill={LOAD_EDGE} />
                </g>
              );
            })}
            <text x={(x0 + x1) / 2} y={groundY - h - 21} textAnchor="middle"
                  fontSize={11} fill={LOAD_EDGE} fontWeight={600}>
              {p.pressure_kpa.toFixed(0)} kPa
            </text>
            <DimLine x1={x0} x2={x1} y={groundY + 14}
                     label={`${(p.width_x_m * 1000).toFixed(0)} mm`} />
          </g>
        );
      })}
      {points.map((p, i) => {
        const px = sx(p.x_m + offsetM);
        return (
          <g key={`pt-${i}`}>
            <line x1={px} y1={groundY - 42} x2={px} y2={groundY - 4}
                  stroke={LOAD_EDGE} strokeWidth={2.4} />
            <polygon points={`${px},${groundY} ${px - 5},${groundY - 8} ${px + 5},${groundY - 8}`}
                     fill={LOAD_EDGE} />
            <text x={px} y={groundY - 47} textAnchor="middle" fontSize={11}
                  fill={LOAD_EDGE} fontWeight={600}>{p.load_kn.toFixed(0)} kN</text>
          </g>
        );
      })}

      {/* pipe */}
      <circle cx={sx(0)} cy={pipeCy} r={pipeR} fill="#fff" stroke={PIPE} strokeWidth={2.4} />
      <line x1={sx(0)} y1={pipeCy - pipeR - 8} x2={sx(0)} y2={pipeCy + pipeR + 8}
            stroke={PIPE} strokeDasharray="5 3" strokeWidth={1} />

      {/* cover dimension */}
      <g stroke="#4a4336" fill="#4a4336" strokeWidth={1}>
        <line x1={sx(0) + pipeR + 34} y1={groundY} x2={sx(0) + pipeR + 34} y2={sz(coverM)} />
        <line x1={sx(0) + pipeR + 28} y1={groundY} x2={sx(0) + pipeR + 40} y2={groundY} />
        <line x1={sx(0) + pipeR + 28} y1={sz(coverM)} x2={sx(0) + pipeR + 40} y2={sz(coverM)} />
        <text x={sx(0) + pipeR + 46} y={(groundY + sz(coverM)) / 2 + 4}
              stroke="none" fontSize={11.5} fontWeight={600}>
          cover {coverM.toFixed(2)} m
        </text>
      </g>
      <text x={sx(0)} y={pipeCy + pipeR + 22} textAnchor="middle" fontSize={11} fill={PIPE}>
        OD {(pipeOdM * 1000).toFixed(0)} mm
      </text>

      {/* worst-position marker */}
      {!offsetIsWorst && (
        <g>
          <line x1={sx(worstOffsetM)} y1={groundY - 4} x2={sx(worstOffsetM)} y2={groundY + 26}
                stroke="#c02020" strokeWidth={1.6} strokeDasharray="4 3" />
          <text x={sx(worstOffsetM)} y={groundY + 38} textAnchor="middle"
                fontSize={10.5} fill="#c02020" fontWeight={700}>
            worst at {worstOffsetM >= 0 ? "+" : ""}{worstOffsetM.toFixed(2)} m
          </text>
        </g>
      )}
    </svg>
  );

  // =====================================================================
  // Plan: pipe runs left-right (y), x is across the page vertically. A
  // single px/metre scale is used for both axes so a track's true 3.2 x
  // 0.6 m footprint actually renders at a 3.2:0.6 ratio rather than being
  // stretched to whatever the two axes independently had room for.
  // =====================================================================
  const PW = 720;
  const PH = 260;
  const ys = patches.flatMap((p) => [
    p.y_m - p.length_y_m / 2, p.y_m + p.length_y_m / 2,
  ]).concat(points.map((p) => p.y_m));
  const halfY = tidy(Math.max(...ys.map(Math.abs), 1) * 1.3);
  const planScale = Math.min((PW / 2 - 34) / halfY, (PH / 2 - 38) / halfX);
  const px_ = (m: number) => PW / 2 + m * planScale;
  const py_ = (m: number) => PH / 2 - m * planScale;

  const plan = (
    <svg viewBox={`0 0 ${PW} ${PH}`}
         style={{ width: "100%", height: "auto", maxHeight: 260 }}
         role="img" aria-label="Plan of the surface loads relative to the pipe">
      <rect x={0} y={0} width={PW} height={PH} fill={SOIL} opacity={0.45} />
      {/* pipe band */}
      <rect x={0} y={py_(pipeOdM / 2)} width={PW} height={py_(-pipeOdM / 2) - py_(pipeOdM / 2)}
            fill={PIPE} opacity={0.16} />
      <line x1={0} y1={py_(0)} x2={PW} y2={py_(0)} stroke={PIPE}
            strokeWidth={1.6} strokeDasharray="7 4" />
      <text x={8} y={py_(0) - 7} fontSize={11} fill={PIPE} fontWeight={600}>
        pipe centreline
      </text>

      {orientation === "along" ? (
        <TravelArrow x1={PW - 90} y1={20} x2={PW - 30} y2={20} label="direction of travel" />
      ) : (
        <TravelArrow x1={PW - 60} y1={36} x2={PW - 60} y2={82} label="travel" />
      )}

      {patches.map((p, i) => {
        const x0 = px_(p.y_m - p.length_y_m / 2);
        const x1 = px_(p.y_m + p.length_y_m / 2);
        const y0 = py_(p.x_m + offsetM + p.width_x_m / 2);
        const y1 = py_(p.x_m + offsetM - p.width_x_m / 2);
        const cx = (x0 + x1) / 2;
        const cy = (y0 + y1) / 2;
        return (
          <g key={i}>
            <rect x={Math.min(x0, x1)} y={Math.min(y0, y1)}
                  width={Math.max(Math.abs(x1 - x0), 2)}
                  height={Math.max(Math.abs(y1 - y0), 2)}
                  fill={LOAD_FILL} fillOpacity={0.55} stroke={LOAD_EDGE} strokeWidth={1.4} />
            <text x={cx} y={cy + 3} textAnchor="middle" fontSize={8.5} fill={LOAD_EDGE}
                  fontWeight={600}>
              {(p.length_y_m * 1000).toFixed(0)}×{(p.width_x_m * 1000).toFixed(0)}
            </text>
          </g>
        );
      })}
      {points.map((p, i) => (
        <circle key={i} cx={px_(p.y_m)} cy={py_(p.x_m + offsetM)} r={5}
                fill={LOAD_FILL} stroke={LOAD_EDGE} strokeWidth={1.4} />
      ))}

      <text x={PW - 8} y={PH - 8} textAnchor="end" fontSize={10.5} fill="#5c5344">
        pipe runs left–right; across-pipe offset is vertical
      </text>
    </svg>
  );

  return (
    <div className="panel">
      <p className="chart-title">Arrangement</p>
      <p className="chart-sub">
        Drawn to true scale — a footprint's shape on screen matches its real
        proportions. Contact pressures and mm dimensions are shown on each
        bearing area.
      </p>
      <div className="soil-views">
        <div>
          <p className="mini-title">Section — looking along the pipe</p>
          {section}
        </div>
        <div>
          <p className="mini-title">Plan</p>
          {plan}
        </div>
      </div>
    </div>
  );
}
