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
    for (const t of presets?.trucks ?? []) {
      out.push({
        key: t.key, label: t.name,
        spec: {
          label: t.name, load_type: "truck", preset_key: t.key, orientation,
          truck_axles: [], truck_axle_width: "1.8 m",
        },
      });
    }
    for (const t of presets?.tracked ?? []) {
      out.push({
        key: t.key, label: t.name,
        spec: {
          label: t.name, load_type: "tracked", preset_key: t.key, orientation,
          truck_axles: [], truck_axle_width: "1.8 m",
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
        <table style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>Vehicle</th><th className="num">Total load</th>
              <th className="num">Worst crown stress</th><th style={{ width: 110 }}>Relative</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={i}>
                <td>
                  {r.ok ? <b>{r.label}</b> : <span className="fail">{r.label} — {r.error}</span>}
                  {r.ok && <div className="muted" style={{ fontSize: 11 }}>{r.description}</div>}
                </td>
                <td className="num">{r.ok ? `${r.total_load_kn.toFixed(0)} kN` : "—"}</td>
                <td className="num">
                  {r.ok ? <b>{r.worst_offset_pressure_kpa.toFixed(1)} kPa</b> : "—"}
                </td>
                <td>
                  {r.ok && (
                    <div className="bar">
                      <i style={{ width: `${peak ? (r.worst_offset_pressure_kpa / peak) * 100 : 0}%` }} />
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
