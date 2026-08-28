/**
 * Drafting primitives shared by the soil drawings.
 *
 * Lifted out of SiteDrawing so VehicleDiagram can reuse them rather than
 * carry a second copy: two implementations of a dimension line drift, and
 * these drawings are meant to be read against each other.
 */

export const LOAD_FILL = "#c8752a";
export const LOAD_EDGE = "#8a4d15";
export const SOIL = "#e8e0cf";
export const PIPE = "#1f5fa8";
export const TRAVEL = "#0a7a2a";
export const DIM = "#4a4336";

/** Round a span up to a tidy number so the drawing does not jitter while typing. */
export function tidy(value: number): number {
  const steps = [1, 2, 2.5, 5, 10, 20, 25, 50];
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(value, 0.1)));
  return (steps.find((s) => s * magnitude >= value) ?? 10) * magnitude;
}

/** A double-ended horizontal dimension line with its value centred underneath. */
export function DimLine({
  x1, x2, y, label, fontSize = 9,
}: { x1: number; x2: number; y: number; label: string; fontSize?: number }) {
  const tick = 3.5;
  const mid = (x1 + x2) / 2;
  return (
    <g stroke={DIM} fill={DIM} strokeWidth={0.9}>
      <line x1={x1} y1={y} x2={x2} y2={y} />
      <line x1={x1} y1={y - tick} x2={x1} y2={y + tick} />
      <line x1={x2} y1={y - tick} x2={x2} y2={y + tick} />
      <text x={mid} y={y - 4} stroke="none" fontSize={fontSize} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

/** A double-ended vertical dimension line, value to the right of the line. */
export function VDimLine({
  x, y1, y2, label, fontSize = 9,
}: { x: number; y1: number; y2: number; label: string; fontSize?: number }) {
  const tick = 3.5;
  const mid = (y1 + y2) / 2;
  return (
    <g stroke={DIM} fill={DIM} strokeWidth={0.9}>
      <line x1={x} y1={y1} x2={x} y2={y2} />
      <line x1={x - tick} y1={y1} x2={x + tick} y2={y1} />
      <line x1={x - tick} y1={y2} x2={x + tick} y2={y2} />
      <text x={x + 6} y={mid + 3} stroke="none" fontSize={fontSize}>{label}</text>
    </g>
  );
}

/** Arrowhead-tipped line showing the direction of travel. */
export function TravelArrow({
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
export function TravelIntoPage({ x, y }: { x: number; y: number }) {
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
