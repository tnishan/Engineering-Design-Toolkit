import type { SectionPreview } from "../../api/types";

interface Props {
  section: SectionPreview;
}

// Beam sections are tall and narrow, so the drawing area is too - a wide
// viewBox would leave the section rendered as a sliver in the middle.
const VB_W = 300;
const VB_H = 340;
const PAD_X = 46;
const PAD_Y = 34;
const PLY_GAP = 2.5; // drawn separation so individual plies read as separate

export default function BeamSection({ section }: Props) {
  const { plies, ply_width_mm, depth_mm, width_mm } = section;

  // Fit the section into the drawing area, preserving true proportions.
  const availW = VB_W - PAD_X * 2;
  const availH = VB_H - PAD_Y * 2;
  const scale = Math.min(availW / width_mm, availH / depth_mm);
  const w = width_mm * scale;
  const h = depth_mm * scale;
  const x0 = (VB_W - w) / 2;
  const y0 = (VB_H - h) / 2;
  const plyW = w / plies;

  const dim = (
    key: string,
    x1: number, y1: number, x2: number, y2: number,
    label: string,
    side: "below" | "right" | "above",
  ) => {
    const tick = 4;
    const vertical = side === "right";
    const mid = { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
    return (
      <g key={key} stroke="#626b76" fill="#626b76" strokeWidth={1}>
        <line x1={x1} y1={y1} x2={x2} y2={y2} />
        {vertical ? (
          <>
            <line x1={x1 - tick} y1={y1} x2={x1 + tick} y2={y1} />
            <line x1={x2 - tick} y1={y2} x2={x2 + tick} y2={y2} />
            <text
              x={mid.x + 9} y={mid.y} stroke="none" fontSize={11.5}
              dominantBaseline="middle"
              transform={`rotate(-90 ${mid.x + 9} ${mid.y})`}
              textAnchor="middle"
            >
              {label}
            </text>
          </>
        ) : (
          <>
            <line x1={x1} y1={y1 - tick} x2={x1} y2={y1 + tick} />
            <line x1={x2} y1={y2 - tick} x2={x2} y2={y2 + tick} />
            <text
              x={mid.x} y={side === "below" ? mid.y + 14 : mid.y - 6}
              stroke="none" fontSize={11.5} textAnchor="middle"
            >
              {label}
            </text>
          </>
        )}
      </g>
    );
  };

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      style={{ width: "100%", height: "auto", maxHeight: 330 }}
      role="img"
      aria-label={`Cross-section: ${section.label}`}
    >
      {/* plies */}
      {Array.from({ length: plies }, (_, i) => {
        const px = x0 + i * plyW;
        const inset = plies > 1 ? PLY_GAP / 2 : 0;
        return (
          <g key={i}>
            <rect
              x={px + inset}
              y={y0}
              width={plyW - inset * 2}
              height={h}
              fill="#dfd3bd"
              stroke="#1a1d21"
              strokeWidth={1.4}
            />
            {/* grain hint, so it reads as timber rather than a plain box */}
            {[0.25, 0.5, 0.75].map((f) => (
              <line
                key={f}
                x1={px + inset + 2}
                y1={y0 + h * f}
                x2={px + plyW - inset - 2}
                y2={y0 + h * f}
                stroke="#c9b795"
                strokeWidth={0.8}
              />
            ))}
          </g>
        );
      })}

      {/* ply-width dimension on the first ply, overall width below it */}
      {plies > 1 &&
        dim("ply", x0, y0 - 16, x0 + plyW, y0 - 16,
            `${ply_width_mm.toFixed(0)}`, "above")}
      {dim("width", x0, y0 + h + 20, x0 + w, y0 + h + 20,
           `${width_mm.toFixed(0)} mm overall`, "below")}
      {dim("depth", x0 + w + 22, y0, x0 + w + 22, y0 + h,
           `${depth_mm.toFixed(0)} mm`, "right")}

      {plies > 1 && (
        <text x={x0 + plyW / 2} y={y0 + h / 2} fontSize={11.5} fill="#5a4a2a"
              textAnchor="middle" dominantBaseline="middle">
          1
        </text>
      )}
      {plies > 1 && Array.from({ length: plies - 1 }, (_, i) => (
        <text key={i} x={x0 + plyW * (i + 1.5)} y={y0 + h / 2} fontSize={11.5}
              fill="#5a4a2a" textAnchor="middle" dominantBaseline="middle">
          {i + 2}
        </text>
      ))}

      <text x={VB_W / 2} y={VB_H - 8} fontSize={12} fill="#1a1d21"
            textAnchor="middle" fontWeight={600}>
        {plies > 1 ? `${plies} plies @ ${ply_width_mm.toFixed(0)} mm` : "single member"}
      </text>
    </svg>
  );
}
