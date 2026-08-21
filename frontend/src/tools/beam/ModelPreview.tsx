import type { Preview, Reaction } from "../../api/types";
import BeamElevation from "./BeamElevation";
import BeamSection from "./BeamSection";

interface Props {
  /** The last preview that parsed successfully. */
  preview: Preview | null;
  /** Set while the current inputs cannot be parsed; the drawing stays put. */
  error: string | null;
  /** Present once the beam has been analysed; drawn on the elevation. */
  reactions: Reaction[];
  stale: boolean;
}

export default function ModelPreview({ preview, error, reactions, stale }: Props) {
  if (!preview) {
    return (
      <div className="panel">
        <h2>Beam model</h2>
        <p className="muted">Building the drawing…</p>
      </div>
    );
  }

  const s = preview.section;

  return (
    <div className="panel model-preview">
      <div className="model-head">
        <div>
          <h2 style={{ margin: 0 }}>Beam model</h2>
          <p className="chart-sub" style={{ margin: "2px 0 0" }}>
            Updates as you type. {reactions.length
              ? "Reactions shown are factored envelope maxima."
              : "Press Design beam to add reactions and check the section."}
          </p>
        </div>
        {stale && <span className="stale-chip">inputs changed — re-run to update results</span>}
      </div>

      {error && (
        <div className="err" style={{ margin: "8px 0" }}>
          {error} — showing the last valid model.
        </div>
      )}

      {preview.ok && (
        <>
          <div className="model-grid">
            <div className="model-elevation">
              <p className="mini-title">Elevation</p>
              <BeamElevation
                bare
                lengthMm={preview.length_mm}
                supportsMm={preview.span_positions_mm}
                supportKinds={preview.supports}
                loads={preview.loads}
                reactions={reactions}
                depthMm={s?.depth_mm ?? 0}
              />
            </div>
            <div className="model-section">
              <p className="mini-title">Section</p>
              {s ? (
                <BeamSection section={s} />
              ) : (
                <div className="auto-size-note">
                  <b>Auto-sizing</b>
                  <span>Section chosen on design</span>
                </div>
              )}
            </div>
          </div>

          <div className="model-desc">
            <p>{preview.description}</p>
            <p className="muted">
              Total applied load on the member:{" "}
              <b>{preview.total_load_kn.toFixed(1)} kN</b> specified
              {preview.span_positions_mm.length > 1 && (
                <> over {(preview.length_mm / 1000).toFixed(3)} m
                  ({(preview.length_mm / 304.8).toFixed(2)} ft) in{" "}
                  {preview.span_positions_mm.length - 1} span
                  {preview.span_positions_mm.length > 2 ? "s" : ""}</>
              )}.
            </p>
            {s && !s.material_verified && (
              <p className="muted">
                Material properties for {s.material_name} are an unverified
                transcription — confirm against CSA O86 before use.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
