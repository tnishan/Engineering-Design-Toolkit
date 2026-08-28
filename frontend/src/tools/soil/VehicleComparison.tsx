import { useEffect, useMemo, useState } from "react";
import { compareVehicles, listVehiclePresets } from "../../api/client";
import type {
  Orientation,
  VehicleComparisonRequest,
  VehicleResult,
  VehicleSpec,
  VehiclePresets,
} from "../../api/types";

interface Props {
  /** The vehicle currently configured in the main form, as a ready spec. */
  currentVehicle: VehicleSpec;
  cover: string;
  pipeOd: string;
  unitWeight: number;
  poisson: number;
  dlaMode: "none" | "manual" | "aashto_depth";
  dla: number;
  spreadPreset: "aashto_granular" | "aashto_other" | "custom" | "none";
  spreadFactor: number;
}

export default function VehicleComparison({
  currentVehicle, cover, pipeOd, unitWeight, poisson, dlaMode, dla,
  spreadPreset, spreadFactor,
}: Props) {
  const [presets, setPresets] = useState<VehiclePresets | null>(null);
  const [selected, setSelected] = useState<Set<string>>(
    new Set(["current", "cl625", "cat_320"]),
  );
  const [orientation, setOrientation] = useState<Orientation>("across");
  const [results, setResults] = useState<VehicleResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listVehiclePresets().then(setPresets).catch(() => setPresets(null));
  }, []);

  const options = useMemo(() => {
    const out: { key: string; label: string; spec: VehicleSpec }[] = [
      { key: "current", label: "Current configuration (from the form)", spec: currentVehicle },
    ];
    for (const v of presets?.vehicles ?? []) {
      out.push({
        key: v.key,
        label: `${v.name} (${v.total_load_kn.toFixed(0)} kN)`,
        spec: {
          label: v.name,
          load_type: "truck",
          preset_key: v.key,
          orientation,
          truck_axles: [],
          truck_axle_width: "1.8 m",
        },
      });
    }
    return out;
  }, [presets, currentVehicle, orientation]);

  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    setSelected(next);
  };

  const run = async () => {
    const vehicles = options.filter((o) => selected.has(o.key)).map((o) => o.spec);
    if (!vehicles.length) return;
    setBusy(true);
    setError(null);
    try {
      const payload: VehicleComparisonRequest = {
        vehicles, cover, pipe_od: pipeOd, soil_unit_weight_kn_m3: unitWeight,
        poisson_ratio: poisson, dla_mode: dlaMode, dla,
        spread_preset: spreadPreset, spread_factor: spreadFactor,
      };
      const r = await compareVehicles(payload);
      if (r.ok) setResults(r.results); else setError(r.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sorted = results
    ? [...results].sort((a, b) => b.worst_offset_pressure_kpa - a.worst_offset_pressure_kpa)
    : null;
  const peak = sorted?.[0]?.worst_offset_pressure_kpa ?? 0;

  return (
    <div className="panel">
      <h2>Compare vehicles</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
        Worst-case crown pressure for each vehicle at this cover and pipe, one lane,
        one vehicle at a time (not two vehicles present together).
      </p>

      <div className="row" style={{ flexWrap: "wrap", gap: "6px 14px", marginBottom: 8 }}>
        {options.map((o) => (
          <label key={o.key} className="inline" style={{ margin: 0 }}>
            <input type="checkbox" checked={selected.has(o.key)}
                   onChange={() => toggle(o.key)} />
            <span style={{ marginBottom: 0 }}>{o.label}</span>
          </label>
        ))}
      </div>

      <div className="row" style={{ alignItems: "flex-end" }}>
        <label style={{ maxWidth: 260 }}><span>Preset vehicles travel</span>
          <select value={orientation} onChange={(e) => setOrientation(e.target.value as Orientation)}>
            <option value="across">Crossing the pipe</option>
            <option value="along">Tracking along the pipe</option>
          </select>
        </label>
        <button type="button" onClick={run} disabled={busy || !selected.size}
                style={{ flex: 0, whiteSpace: "nowrap" }}>
          {busy ? "Comparing…" : "Compare"}
        </button>
      </div>

      {error && <div className="err" style={{ marginTop: 10 }}>{error}</div>}

      {sorted && (
        <div style={{ marginTop: 14 }}>
          {/* Top Governing Plant Callout */}
          {sorted[0]?.ok && (
            <div style={{
              background: "#f0fdf4",
              border: "1px solid #86efac",
              borderRadius: 6,
              padding: "10px 14px",
              marginBottom: 14,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
            }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#166534", letterSpacing: 0.5 }}>
                  Governing Plant on Site
                </span>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#14532d", marginTop: 2 }}>
                  {sorted[0].label} — {sorted[0].worst_offset_pressure_kpa.toFixed(1)} kPa peak crown stress
                </div>
                <div style={{ fontSize: 12, color: "#166534", marginTop: 2 }}>
                  Critical axis: <b>{sorted[0].critical_axle || "Governing axle"}</b> {sorted[0].critical_axle_contribution_kpa ? `(${sorted[0].critical_axle_contribution_kpa.toFixed(1)} kPa contribution)` : ""} at {sorted[0].worst_offset_m >= 0 ? "+" : ""}{sorted[0].worst_offset_m.toFixed(2)} m offset
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: "#15803d" }}>
                  {sorted[0].worst_offset_pressure_kpa.toFixed(1)} kPa
                </div>
                <div style={{ fontSize: 11, color: "#166534" }}>
                  {sorted[0].total_load_kn.toFixed(0)} kN total load
                </div>
              </div>
            </div>
          )}

          {/* Detailed Configuration & Governing Axis Table */}
          <h3 style={{ fontSize: 13, marginBottom: 6, color: "#334155" }}>
            Plant Dimensions, Axle Layout & Critical Load Axis
          </h3>
          <table>
            <thead>
              <tr>
                <th>Vehicle & Configuration</th>
                <th>Tires / Tracks & Gauge</th>
                <th className="num">Total Load</th>
                <th>Critical Governing Axle</th>
                <th className="num">Worst Stress</th>
                <th style={{ width: 90 }}>Relative</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={i} style={i === 0 ? { background: "#f8fafc" } : undefined}>
                  <td>
                    {r.ok ? (
                      <>
                        <b style={{ color: i === 0 ? "#1e40af" : "inherit" }}>{r.label}</b>
                        <div className="muted" style={{ fontSize: 11 }}>
                          {r.orientation === "across" ? "Crossing pipe (transverse)" : "Tracking along pipe (parallel)"}
                        </div>
                      </>
                    ) : (
                      <span className="fail">{r.label} — {r.error}</span>
                    )}
                  </td>
                  <td>
                    {r.ok ? (
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 500 }}>
                          {r.dimensions_summary || `${r.axle_count || 1} axle(s)`}
                        </div>
                        {r.axle_width_m ? (
                          <div className="muted" style={{ fontSize: 11 }}>
                            Track gauge: {r.axle_width_m.toFixed(2)} m
                          </div>
                        ) : null}
                      </div>
                    ) : "—"}
                  </td>
                  <td className="num">
                    {r.ok ? <b>{r.total_load_kn.toFixed(0)} kN</b> : "—"}
                  </td>
                  <td>
                    {r.ok ? (
                      <div>
                        <b style={{ color: "#b91c1c" }}>{r.critical_axle || "Combined"}</b>
                        {r.critical_axle_contribution_kpa ? (
                          <div className="muted" style={{ fontSize: 11 }}>
                            {r.critical_axle_contribution_kpa.toFixed(1)} kPa peak
                          </div>
                        ) : null}
                      </div>
                    ) : "—"}
                  </td>
                  <td className="num">
                    {r.ok ? (
                      <div>
                        <b style={{ fontSize: 13 }}>{r.worst_offset_pressure_kpa.toFixed(1)} kPa</b>
                        <div className="muted" style={{ fontSize: 11 }}>
                          @ {r.worst_offset_m >= 0 ? "+" : ""}{r.worst_offset_m.toFixed(2)} m
                        </div>
                      </div>
                    ) : "—"}
                  </td>
                  <td>
                    {r.ok && (
                      <div className="bar" title={`${peak ? ((r.worst_offset_pressure_kpa / peak) * 100).toFixed(0) : 0}% of governing`}>
                        <i style={{
                          width: `${peak ? (r.worst_offset_pressure_kpa / peak) * 100 : 0}%`,
                          background: i === 0 ? "#dc2626" : "var(--accent)",
                        }} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Per-axle/tyre loads and dimensions for every vehicle compared. */}
          {sorted.filter((r) => r.ok && r.axles?.length).map((r, i) => (
            <details className="check-detail" key={i}>
              <summary>{r.label} — tyre/track loads and dimensions ({r.axles!.length} axle line{r.axles!.length > 1 ? "s" : ""})</summary>
              <table>
                <thead>
                  <tr>
                    <th>Axle line</th>
                    <th className="num">Load</th>
                    <th className="num">Tyres/side</th>
                    <th className="num">Width</th>
                    <th className="num">Contact length</th>
                    <th className="num">Spacing from previous</th>
                  </tr>
                </thead>
                <tbody>
                  {r.axles!.map((a, j) => (
                    <tr key={j}>
                      <td>{a.label}</td>
                      <td className="num">{a.load_kn.toFixed(1)} kN</td>
                      <td className="num">{a.tires_per_side}</td>
                      <td className="num">{(a.width_m * 1000).toFixed(0)} mm</td>
                      <td className="num">{(a.length_m * 1000).toFixed(0)} mm</td>
                      <td className="num">{j === 0 ? "—" : `${a.spacing_m.toFixed(2)} m`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
