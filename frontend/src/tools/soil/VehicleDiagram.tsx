import { useState } from "react";
import type { VehicleGeometry } from "../../api/types";
import { DimLine, VDimLine, LOAD_EDGE, LOAD_FILL, TRAVEL, DIM } from "./drawing";

/**
 * The check-your-input drawing: the machine on its own, in the style of the
 * manufacturer axle sheets this data was transcribed from.
 *
 * Drawn in the vehicle's own frame (travel left to right), NOT relative to the
 * pipe. That is the whole point — this answers "did I enter this truck
 * correctly?", which has nothing to do with which way it crosses the pipe. The
 * pipe-relative picture is SiteDrawing's job.
 */

interface Props {
  vehicle: VehicleGeometry;
}

const GROUND = "#5c5344";

/** Elevation and plan both use one px/metre so proportions stay honest. */
function scaleFor(spanM: number, pxAvailable: number): number {
  return pxAvailable / Math.max(spanM, 0.001);
}

export default function VehicleDiagram({ vehicle }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const { axles, contacts, is_tracked: tracked, contact_noun: noun } = vehicle;
  if (!axles.length) return null;

  // A tracked machine is one axle line at u = 0, so there is no wheelbase to
  // dimension. Fall back to the contact length so the drawing still spans
  // something real rather than collapsing to a point.
  const spanM = Math.max(vehicle.wheelbase_m, vehicle.overall_length_m, 0.5);

  // =====================================================================
  // Elevation — side view, travel left to right, axle loads called out
  // above the machine and the spacing chain dimensioned below it.
  // =====================================================================
  const EW = 720;
  const EH = 300;
  const eMargin = 56;
  const eScale = scaleFor(spanM * 1.08, EW - eMargin * 2);
  const groundY = 176;
  const ex = (u: number) => EW / 2 + u * eScale;

  const wheelR = Math.max(9, Math.min(26, (spanM * eScale) / (axles.length * 5)));

  const elevation = (
    <svg viewBox={`0 0 ${EW} ${EH}`} style={{ width: "100%", height: "auto" }}
         role="img" aria-label="Vehicle elevation with axle loads and spacings">
      {/* Ground line */}
      <line x1={16} y1={groundY} x2={EW - 16} y2={groundY} stroke={GROUND} strokeWidth={2} />

      {/* Direction of travel */}
      <g stroke={TRAVEL} fill={TRAVEL}>
        <line x1={EW - 150} y1={22} x2={EW - 46} y2={22} strokeWidth={1.8} />
        <polygon points={`${EW - 38},22 ${EW - 50},17.5 ${EW - 50},26.5`} />
        <text x={EW - 154} y={26} stroke="none" fontSize={10} fontWeight={600}
              textAnchor="end">direction of travel</text>
      </g>

      {/* Chassis line, so the axles read as one machine rather than loose wheels */}
      {!tracked && axles.length > 1 && (
        <line x1={ex(axles[0].position_u_centred_m)} y1={groundY - wheelR * 2 - 6}
              x2={ex(axles[axles.length - 1].position_u_centred_m)}
              y2={groundY - wheelR * 2 - 6}
              stroke={LOAD_EDGE} strokeWidth={3} strokeLinecap="round" />
      )}

      {axles.map((a) => {
        const x = ex(a.position_u_centred_m);
        const halfLen = Math.max((a.contact_length_m * eScale) / 2, 3);
        const isHovered = hoveredIdx === a.index;

        return (
          <g
            key={a.index}
            onMouseEnter={() => setHoveredIdx(a.index)}
            onMouseLeave={() => setHoveredIdx(null)}
            style={{ cursor: "pointer" }}
          >
            {tracked ? (
              /* A track bears over its whole length, so draw the footprint. */
              <rect x={x - halfLen} y={groundY - 26} width={halfLen * 2} height={26}
                    rx={6} fill={isHovered ? "#fbbf24" : LOAD_FILL} stroke={isHovered ? "#b45309" : LOAD_EDGE} strokeWidth={isHovered ? 2.4 : 1.6} />
            ) : (
              <>
                <circle cx={x} cy={groundY - wheelR} r={wheelR}
                        fill={isHovered ? "#fbbf24" : LOAD_FILL} stroke={isHovered ? "#b45309" : LOAD_EDGE} strokeWidth={isHovered ? 2.4 : 1.8} />
                <circle cx={x} cy={groundY - wheelR} r={wheelR * 0.38}
                        fill="#fff" stroke={isHovered ? "#b45309" : LOAD_EDGE} strokeWidth={1.2} />
              </>
            )}

            {/* Load arrow and callout: kN is the number to check, so it leads. */}
            <line x1={x} y1={groundY - wheelR * 2 - 46} x2={x} y2={groundY - wheelR * 2 - 16}
                  stroke={isHovered ? "#b45309" : LOAD_EDGE} strokeWidth={isHovered ? 2.4 : 1.8} />
            <polygon
              points={`${x},${groundY - wheelR * 2 - 10} ${x - 4.2},${groundY - wheelR * 2 - 18} ${x + 4.2},${groundY - wheelR * 2 - 18}`}
              fill={isHovered ? "#b45309" : LOAD_EDGE} />
            <text x={x} y={groundY - wheelR * 2 - 52} textAnchor="middle" fontSize={12}
                  fontWeight={700} fill={isHovered ? "#b45309" : LOAD_EDGE}>
              {a.load_kn.toFixed(0)} kN
            </text>
            <text x={x} y={groundY - wheelR * 2 - 65} textAnchor="middle" fontSize={9.5}
                  fill={isHovered ? "#1e293b" : DIM} fontWeight={isHovered ? 700 : 400}>
              {a.label}
            </text>

            {/* Per-wheel load: what actually presses on the ground. */}
            <text x={x} y={groundY + 15} textAnchor="middle" fontSize={9} fill={isHovered ? "#1e293b" : DIM} fontWeight={isHovered ? 600 : 400}>
              {a.wheel_load_kn.toFixed(1)} kN/{noun}
              {a.tires_per_side === 2 ? " ×2" : ""}
            </text>
          </g>
        );
      })}

      {/* Spacing chain between consecutive axles. */}
      {axles.slice(1).map((a, i) => (
        <DimLine key={a.index}
                 x1={ex(axles[i].position_u_centred_m)}
                 x2={ex(a.position_u_centred_m)}
                 y={groundY + 44}
                 label={`${a.spacing_from_previous_m!.toFixed(2)} m`} />
      ))}

      {/* Overall dimension: wheelbase for a truck, contact length for tracks. */}
      {tracked ? (
        <DimLine x1={ex(-vehicle.overall_length_m / 2)} x2={ex(vehicle.overall_length_m / 2)}
                 y={groundY + 76} fontSize={11}
                 label={`track contact length ${vehicle.overall_length_m.toFixed(2)} m`} />
      ) : axles.length > 1 ? (
        <DimLine x1={ex(axles[0].position_u_centred_m)}
                 x2={ex(axles[axles.length - 1].position_u_centred_m)}
                 y={groundY + 76} fontSize={11}
                 label={`wheelbase ${vehicle.wheelbase_m.toFixed(2)} m`} />
      ) : null}

      <text x={16} y={EH - 8} fontSize={10} fill={DIM}>
        Total {vehicle.total_load_kn.toFixed(0)} kN over {vehicle.axle_count}{" "}
        {tracked ? "track set" : `axle line${vehicle.axle_count > 1 ? "s" : ""}`}
      </text>
    </svg>
  );

  // =====================================================================
  // Plan — looking down on the machine. Gauge across, dual spacing where
  // the axle runs duals, contact patch size on each footprint.
  // =====================================================================
  const PW = 720;
  const PH = 300;
  const pMargin = 96;
  const widthSpan = Math.max(vehicle.overall_width_m * 1.5, 1);
  // One scale for BOTH axes, whichever is the binding constraint, so a
  // 3.2 x 0.6 m track renders at 3.2:0.6 instead of being stretched to fit.
  const pScale = Math.min(
    scaleFor(spanM * 1.05, PW - pMargin * 2),
    scaleFor(widthSpan, PH - 96),
  );
  const pux = (u: number) => PW / 2 + u * pScale;
  const pvy = (v: number) => PH / 2 + v * pScale;

  const dualAxles = axles.filter((a) => a.dual_spacing_m !== null);
  const rearMost = axles[axles.length - 1];

  const plan = (
    <svg viewBox={`0 0 ${PW} ${PH}`} style={{ width: "100%", height: "auto" }}
         role="img" aria-label="Vehicle plan with gauge and dual tyre spacing">
      {/* Vehicle centreline */}
      <line x1={30} y1={pvy(0)} x2={PW - 30} y2={pvy(0)} stroke={DIM}
            strokeDasharray="7 4" strokeWidth={1} />
      <text x={34} y={pvy(0) - 6} fontSize={9.5} fill={DIM}>vehicle centreline</text>

      <g stroke={TRAVEL} fill={TRAVEL}>
        <line x1={PW - 150} y1={20} x2={PW - 46} y2={20} strokeWidth={1.8} />
        <polygon points={`${PW - 38},20 ${PW - 50},15.5 ${PW - 50},24.5`} />
        <text x={PW - 154} y={24} stroke="none" fontSize={10} fontWeight={600}
              textAnchor="end">direction of travel</text>
      </g>

      {contacts.map((c, i) => {
        const w = Math.max(c.length_u_m * pScale, 2.5);
        const h = Math.max(c.width_v_m * pScale, 2.5);
        return (
          <g key={i}>
            <rect x={pux(c.u_m) - w / 2} y={pvy(c.v_m) - h / 2} width={w} height={h}
                  fill={LOAD_FILL} fillOpacity={0.6} stroke={LOAD_EDGE} strokeWidth={1.3} />
            {/* Contact size only where the footprint is big enough to hold it. */}
            {w > 30 && h > 11 && (
              <text x={pux(c.u_m)} y={pvy(c.v_m) + 3} textAnchor="middle" fontSize={8}
                    fill={LOAD_EDGE} fontWeight={600}>
                {(c.length_u_m * 1000).toFixed(0)}×{(c.width_v_m * 1000).toFixed(0)}
              </text>
            )}
          </g>
        );
      })}

      {/* Gauge: wheel-line to wheel-line, dimensioned off the rearmost axle. */}
      <VDimLine x={pux(rearMost.position_u_centred_m) + 34}
                y1={pvy(-vehicle.gauge_m / 2)} y2={pvy(vehicle.gauge_m / 2)}
                fontSize={11}
                label={`gauge ${vehicle.gauge_m.toFixed(2)} m`} />

      {/* Dual spacing, drawn only on the axles that actually run duals. */}
      {dualAxles.map((a) => {
        const v0 = vehicle.gauge_m / 2 - a.dual_spacing_m! / 2;
        const v1 = vehicle.gauge_m / 2 + a.dual_spacing_m! / 2;
        return (
          <VDimLine key={a.index} x={pux(a.position_u_centred_m) - 30}
                    y1={pvy(v0)} y2={pvy(v1)}
                    label={`${(a.dual_spacing_m! * 1000).toFixed(0)}`} />
        );
      })}

      <text x={16} y={PH - 8} fontSize={10} fill={DIM}>
        {noun} footprints in mm{dualAxles.length
          ? `; dual spacing shown on ${dualAxles.length} of ${axles.length} axle lines`
          : ""}
      </text>
    </svg>
  );

  // The contact pressure is only a real number when the contact length was a
  // stated dimension. Where it was derived from an assumed inflation pressure
  // it just echoes that assumption back, so it must not be shown as a result.
  const anyDerived = axles.some((a) => a.contact_length_is_derived);

  return (
    <div className="panel">
      <p className="chart-title">Vehicle configuration — check your input</p>
      <p className="chart-sub">
        The machine on its own, drawn to true scale, independent of which way it
        crosses the pipe. Check the axle loads, spacings and{" "}
        {noun} sizes against the manufacturer sheet before trusting any pressure below.
      </p>

      <div className="soil-views">
        <div>
          <p className="mini-title">Elevation — travel left to right</p>
          {elevation}
        </div>
        <div>
          <p className="mini-title">Plan — looking down</p>
          {plan}
        </div>
      </div>

      <table style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th>Axle line</th>
            <th className="num">Axle load</th>
            <th className="num">Per {noun}</th>
            <th className="num">{noun === "track" ? "Tracks" : "Tyres"}/side</th>
            <th className="num">Width</th>
            <th className="num">Contact length</th>
            <th className="num">Dual spacing</th>
            <th className="num">Spacing from previous</th>
          </tr>
        </thead>
        <tbody>
          {axles.map((a) => {
            const isHovered = hoveredIdx === a.index;
            return (
              <tr
                key={a.index}
                onMouseEnter={() => setHoveredIdx(a.index)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{
                  background: isHovered ? "#fef3c7" : undefined,
                  cursor: "pointer",
                  transition: "background 0.15s ease",
                }}
              >
                <td><b>{a.label}</b></td>
                <td className="num"><b>{a.load_kn.toFixed(1)} kN</b></td>
                <td className="num">{a.wheel_load_kn.toFixed(1)} kN</td>
                <td className="num">{a.tires_per_side}</td>
                <td className="num">{(a.tire_width_m * 1000).toFixed(0)} mm</td>
                <td className="num">
                  {(a.contact_length_m * 1000).toFixed(0)} mm
                  {a.contact_length_is_derived && (
                    <span className="muted" title={
                      `Not a stated dimension: computed from an assumed ${
                        a.tire_pressure_kpa?.toFixed(0) ?? "?"} kPa inflation pressure.`
                    }> *</span>
                  )}
                </td>
                <td className="num">
                  {a.dual_spacing_m === null ? "—" : `${(a.dual_spacing_m * 1000).toFixed(0)} mm`}
                </td>
                <td className="num">
                  {a.spacing_from_previous_m === null
                    ? "—" : `${a.spacing_from_previous_m.toFixed(2)} m`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {anyDerived && (
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          * Contact length was computed from an assumed tyre inflation pressure,
          not read off a sheet. Contact pressure on those axles therefore just
          returns the assumed pressure and is not independent evidence — confirm
          the {noun} size against the machine on site.
        </p>
      )}
    </div>
  );
}
