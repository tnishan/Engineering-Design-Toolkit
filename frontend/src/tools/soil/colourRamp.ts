/**
 * Shared colour ramp for stress fields, and the canvas encoder that turns a
 * grid into a single PNG.
 *
 * The encoder exists because drawing one SVG rect per grid cell cost 7,600
 * nodes and 1.2 MB of markup per redraw. One image element is 45x smaller and
 * the browser's own smoothing when it is scaled up reads better than
 * hard-edged cells.
 */

/** Blue -> green -> amber -> red, interpolated in RGB. */
export const STOPS: [number, [number, number, number]][] = [
  [0.0, [244, 247, 251]],
  [0.15, [186, 212, 236]],
  [0.35, [126, 178, 197]],
  [0.55, [163, 197, 138]],
  [0.75, [232, 197, 106]],
  [0.9, [222, 138, 77]],
  [1.0, [192, 60, 40]],
];

export function rampRgb(t: number): [number, number, number] {
  const v = Math.max(0, Math.min(1, t));
  for (let i = 1; i < STOPS.length; i += 1) {
    const [p1, c1] = STOPS[i];
    const [p0, c0] = STOPS[i - 1];
    if (v <= p1) {
      const f = (v - p0) / (p1 - p0 || 1);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * f),
        Math.round(c0[1] + (c1[1] - c0[1]) * f),
        Math.round(c0[2] + (c1[2] - c0[2]) * f),
      ];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

/**
 * Encode a [row][col] grid as a PNG data URI, one pixel per sample.
 *
 * ``fadeBelow`` makes low values transparent instead of near-white. A solid
 * cut face wants the default (opaque); a slice floating inside the model must
 * fade out, or it paints an opaque white sheet over everything behind it.
 */
export function fieldToPng(grid: number[][], peak: number, fadeBelow = 0): string {
  if (!grid?.length || !grid[0]?.length) return "";
  const h = grid.length;
  const w = grid[0].length;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const image = ctx.createImageData(w, h);
  for (let i = 0; i < h; i += 1) {
    for (let j = 0; j < w; j += 1) {
      const t = peak > 0 ? grid[i][j] / peak : 0;
      const [r, g, b] = rampRgb(t);
      const k = (i * w + j) * 4;
      image.data[k] = r;
      image.data[k + 1] = g;
      image.data[k + 2] = b;
      image.data[k + 3] = fadeBelow > 0
        ? Math.round(255 * Math.max(0, Math.min(1, t / fadeBelow)))
        : 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL();
}
