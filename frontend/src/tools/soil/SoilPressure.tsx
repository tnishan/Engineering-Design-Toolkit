import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { listVehiclePresets, pipeSurcharge } from "../../api/client";
import type {
  Orientation,
  SoilLoadType,
  SurchargeRequest,
  SurchargeResponse,
  VehiclePresets,
  VehicleSpec,
} from "../../api/types";
import AxleEditor, { axleRowsToRequest, blankAxleRow, type AxleRow } from "./AxleEditor";
import Iso3D from "./Iso3D";
import PressureBulb from "./PressureBulb";
import SiteDrawing from "./SiteDrawing";
import VehicleComparison from "./VehicleComparison";

interface Form {
  project: string;
  member: string;
  engineer: string;
  loadType: SoilLoadType;
  orientation: Orientation;
  // tracked
  weightKn: number;
  trackLength: string;
  trackWidth: string;
  gauge: string;
  // wheels
  wheelLoadKn: number;
  patchAlong: string;
  patchAcross: string;
  axleWidth: string;
  dualSpacing: string;
  axleCount: number;
  axleSpacing: string;
  // truck / multi-axle
  truckAxles: AxleRow[];
  truckAxleWidth: string;
  truckPreset: string;
  // pipe / ground
  cover: string;
  pipeOd: string;
  offset: string;
  unitWeight: number;
  poisson: number;
  dlaMode: "none" | "manual" | "aashto_depth";
  dla: number;
  spreadPreset: "aashto_granular" | "aashto_other" | "custom" | "none";
  spreadFactor: number;
}

const INITIAL: Form = {
  project: "",
  member: "Pipe crossing",
  engineer: "",
  loadType: "tracked",
  orientation: "across",
  weightKn: 200,
  trackLength: "3.2 m",
  trackWidth: "600",
  gauge: "2.2 m",
  wheelLoadKn: 70,
  patchAlong: "250",
  patchAcross: "510",
  axleWidth: "1.8 m",
  dualSpacing: "350",
  axleCount: 2,
  axleSpacing: "1.2 m",
  truckAxles: [blankAxleRow(1)],
  truckAxleWidth: "1.8 m",
  truckPreset: "custom",
  cover: "1.0 m",
  pipeOd: "600",
  offset: "0",
  unitWeight: 20,
  poisson: 0,
  dlaMode: "manual",
  dla: 1.3,
  spreadPreset: "aashto_granular",
  spreadFactor: 1.15,
};

function toRequest(f: Form): SurchargeRequest {
  return {
    load_type: f.loadType,
    tracked: f.loadType === "tracked" ? {
      weight_kn: f.weightKn,
      track_length: f.trackLength,
      track_width: f.trackWidth,
      gauge: f.gauge,
    } : null,
    wheels: f.loadType === "wheels" ? {
      wheel_load_kn: f.wheelLoadKn,
      patch_along_travel: f.patchAlong,
      patch_across_travel: f.patchAcross,
      axle_width: f.axleWidth,
      dual_spacing: f.dualSpacing,
      axle_count: f.axleCount,
      axle_spacing: f.axleSpacing,
    } : null,
    truck_axles: f.loadType === "truck" ? axleRowsToRequest(f.truckAxles) : [],
    truck_axle_width: f.truckAxleWidth,
    custom_patches: [],
    custom_points: [],
    orientation: f.orientation,
    cover: f.cover,
    pipe_od: f.pipeOd,
    machine_offset: f.offset,
    soil_unit_weight_kn_m3: f.unitWeight,
    poisson_ratio: f.poisson,
    dla_mode: f.dlaMode,
    dla: f.dla,
    spread_preset: f.spreadPreset,
    spread_factor: f.spreadFactor,
    project: f.project,
    member: f.member,
    engineer: f.engineer,
  };
}

// The point-load idealisation is left out here on purpose: it is singular at
// the surface and can run into the hundreds of kPa at shallow cover, which
// squashes every other curve into an unreadable band at the bottom of the
// chart. It still appears in the method comparison table above.
const METHOD_SERIES = [
  { key: "boussinesq", label: "Boussinesq", colour: "#1f5fa8", dash: undefined },
  { key: "westergaard", label: "Westergaard", colour: "#0e8fa8", dash: "6 3" },
  { key: "spread_2to1", label: "2:1 spread (merged)", colour: "#a86a00", dash: "3 3" },
  { key: "spread_superposed", label: "2:1 spread (summed)", colour: "#8a5fb0", dash: "1 3" },
  { key: "code_spread", label: "Code spread", colour: "#6b7280", dash: "2 3" },
];

/** Convert a preset truck's axle list (metres/kN) into editable form rows. */
function presetToAxleRows(preset: NonNullable<VehiclePresets["trucks"][number]>): AxleRow[] {
  return preset.axles.map((a) => ({
    label: a.label,
    loadKn: a.load_kn,
    tiresPerSide: a.tires_per_side as 1 | 2,
    tireWidth: `${(a.tire_width_m * 1000).toFixed(0)} mm`,
    tireLength: a.tire_length_m != null ? `${(a.tire_length_m * 1000).toFixed(0)} mm` : "",
    tirePressureKpa: a.tire_pressure_kpa != null ? String(a.tire_pressure_kpa) : "",
    dualSpacing: `${(a.dual_spacing_m * 1000).toFixed(0)} mm`,
    spacingFromPrevious: `${(a.spacing_from_previous_m * 1000).toFixed(0)} mm`,
  }));
}

export default function SoilPressure() {
  const [form, setForm] = useState<Form>(INITIAL);
  const [result, setResult] = useState<SurchargeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [presets, setPresets] = useState<VehiclePresets | null>(null);
  const [axleEditorOpen, setAxleEditorOpen] = useState(false);

  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  useEffect(() => {
    listVehiclePresets().then(setPresets).catch(() => setPresets(null));
  }, []);

  const applyTruckPreset = (key: string) => {
    if (key === "custom") {
      set({ truckPreset: key });
      return;
    }
    const preset = presets?.trucks.find((t) => t.key === key);
    if (!preset) return;
    set({
      truckPreset: key,
      truckAxles: presetToAxleRows(preset),
      truckAxleWidth: `${(preset.axle_width_m * 1000).toFixed(0)} mm`,
    });
  };

  // The analysis is a few milliseconds, so it just runs as you type.
  useEffect(() => {
    const id = setTimeout(() => {
      pipeSurcharge(toRequest(form))
        .then((r) => {
          if (r.ok) {
            setResult(r);
            setError(null);
          } else {
            setError(r.error);
          }
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 220);
    return () => clearTimeout(id);
  }, [form]);

  const openReport = () => {
    if (!result) return;
    const blob = new Blob([result.report_html], { type: "text/html" });
    window.open(URL.createObjectURL(blob), "_blank");
  };

  const currentVehicleSpec: VehicleSpec = form.loadType === "custom"
    ? {
        // Custom rectangles have no reusable "vehicle" shape for comparison;
        // fall back to a zero-axle truck so the request is at least well-formed
        // and the comparison endpoint reports a clear per-vehicle error.
        label: "Current configuration", load_type: "truck", orientation: form.orientation,
        truck_axles: [], truck_axle_width: form.truckAxleWidth,
      }
    : {
        label: "Current configuration",
        load_type: form.loadType,
        orientation: form.orientation,
        tracked: form.loadType === "tracked" ? {
          weight_kn: form.weightKn, track_length: form.trackLength,
          track_width: form.trackWidth, gauge: form.gauge,
        } : null,
        wheels: form.loadType === "wheels" ? {
          wheel_load_kn: form.wheelLoadKn, patch_along_travel: form.patchAlong,
          patch_across_travel: form.patchAcross, axle_width: form.axleWidth,
          dual_spacing: form.dualSpacing, axle_count: form.axleCount,
          axle_spacing: form.axleSpacing,
        } : null,
        truck_axles: form.loadType === "truck" ? axleRowsToRequest(form.truckAxles) : [],
        truck_axle_width: form.truckAxleWidth,
      };

  const depthData = result?.depth_profile ?? [];
  const offsetData = result?.offset_profile.map((p) => ({
    offset: p.offset_m, pressure: p.pressure_kpa,
  })) ?? [];

  return (
    <div className="app">
      <div>
        <div className="panel">
          <h2>Project</h2>
          <label><span>Project</span>
            <input value={form.project} onChange={(e) => set({ project: e.target.value })} />
          </label>
          <div className="row">
            <label><span>Element</span>
              <input value={form.member} onChange={(e) => set({ member: e.target.value })} />
            </label>
            <label><span>Engineer</span>
              <input value={form.engineer} onChange={(e) => set({ engineer: e.target.value })} />
            </label>
          </div>
        </div>

        <div className="panel">
          <h2>Surface load</h2>
          <div className="row" style={{ marginBottom: 10 }}>
            <button type="button" className={form.loadType === "tracked" ? "seg on" : "seg"}
                    onClick={() => set({ loadType: "tracked" })}>Tracked plant</button>
            <button type="button" className={form.loadType === "wheels" ? "seg on" : "seg"}
                    onClick={() => set({ loadType: "wheels" })}>Wheel loads</button>
            <button type="button" className={form.loadType === "truck" ? "seg on" : "seg"}
                    onClick={() => set({ loadType: "truck" })}>Truck (multi-axle)</button>
          </div>

          {form.loadType === "truck" ? (
            <>
              <label><span>Vehicle</span>
                <select value={form.truckPreset}
                        onChange={(e) => applyTruckPreset(e.target.value)}>
                  <option value="custom">Custom axle configuration</option>
                  {(presets?.trucks ?? []).map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.name}{!t.verified ? " (unverified transcription)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <div className="row" style={{ alignItems: "center" }}>
                <p className="muted" style={{ fontSize: 11.5, margin: 0 }}>
                  {form.truckAxles.length} axle(s), {form.truckAxles.reduce((s, a) => s + a.loadKn, 0).toFixed(0)} kN
                  total, {form.truckAxleWidth} track.
                </p>
                <button type="button" onClick={() => setAxleEditorOpen(true)}
                        style={{ flex: 0, whiteSpace: "nowrap" }}>
                  Edit axle configuration…
                </button>
              </div>
              {form.truckPreset !== "custom" && (() => {
                const preset = presets?.trucks.find((t) => t.key === form.truckPreset);
                return preset && !preset.verified ? (
                  <div className="warn">
                    <b>Unverified transcription.</b> {preset.source}
                    {preset.assumptions.map((a, i) => <div key={i}>• {a}</div>)}
                  </div>
                ) : null;
              })()}
              <AxleEditor
                open={axleEditorOpen}
                axles={form.truckAxles}
                axleWidth={form.truckAxleWidth}
                onChange={(axles, axleWidth) => set({
                  truckAxles: axles, truckAxleWidth: axleWidth, truckPreset: "custom",
                })}
                onClose={() => setAxleEditorOpen(false)}
              />
            </>
          ) : form.loadType === "tracked" ? (
            <>
              <label><span>Operating weight (kN)</span>
                <input type="number" step="1" value={form.weightKn}
                       onChange={(e) => set({ weightKn: Number(e.target.value) })} />
              </label>
              <div className="row">
                <label><span>Track contact length</span>
                  <input value={form.trackLength}
                         onChange={(e) => set({ trackLength: e.target.value })} />
                </label>
                <label><span>Shoe width</span>
                  <input value={form.trackWidth}
                         onChange={(e) => set({ trackWidth: e.target.value })} />
                </label>
                <label><span>Track gauge</span>
                  <input value={form.gauge} onChange={(e) => set({ gauge: e.target.value })} />
                </label>
              </div>
              <p className="muted" style={{ fontSize: 11.5 }}>
                Take these from the machine's data sheet. Weight is split evenly between
                the tracks — slewing the upper structure shifts load onto one side and is
                not modelled.
              </p>
            </>
          ) : (
            <>
              <div className="row">
                <label><span>Load per tyre (kN)</span>
                  <input type="number" step="1" value={form.wheelLoadKn}
                         onChange={(e) => set({ wheelLoadKn: Number(e.target.value) })} />
                </label>
                <label><span>Axles</span>
                  <input type="number" min={1} max={6} value={form.axleCount}
                         onChange={(e) => set({ axleCount: Number(e.target.value) })} />
                </label>
              </div>
              <div className="row">
                <label><span>Patch across travel</span>
                  <input value={form.patchAcross}
                         onChange={(e) => set({ patchAcross: e.target.value })} />
                </label>
                <label><span>Patch along travel</span>
                  <input value={form.patchAlong}
                         onChange={(e) => set({ patchAlong: e.target.value })} />
                </label>
              </div>
              <div className="row">
                <label><span>Axle width</span>
                  <input value={form.axleWidth}
                         onChange={(e) => set({ axleWidth: e.target.value })} />
                </label>
                <label><span>Dual spacing (0 = single)</span>
                  <input value={form.dualSpacing}
                         onChange={(e) => set({ dualSpacing: e.target.value })} />
                </label>
                <label><span>Axle spacing</span>
                  <input value={form.axleSpacing}
                         onChange={(e) => set({ axleSpacing: e.target.value })} />
                </label>
              </div>
            </>
          )}

          <label style={{ marginTop: 6 }}><span>Direction of travel</span>
            <select value={form.orientation}
                    onChange={(e) => set({ orientation: e.target.value as Orientation })}>
              <option value="across">Crossing the pipe (at right angles)</option>
              <option value="along">Tracking along the pipe (parallel)</option>
            </select>
          </label>
          <p className="muted" style={{ fontSize: 11.5 }}>
            This matters a lot. Crossing puts the long track axis over the pipe;
            tracking along it can leave the pipe in the gap between the tracks.
          </p>
        </div>

        <div className="panel">
          <h2>Pipe and ground</h2>
          <div className="row">
            <label><span>Depth of cover to crown</span>
              <input value={form.cover} onChange={(e) => set({ cover: e.target.value })} />
            </label>
            <label><span>Pipe outside diameter</span>
              <input value={form.pipeOd} onChange={(e) => set({ pipeOd: e.target.value })} />
            </label>
          </div>
          <div className="row">
            <label><span>Machine offset from pipe centreline</span>
              <input value={form.offset} onChange={(e) => set({ offset: e.target.value })} />
            </label>
            <label><span>Soil unit weight (kN/m³)</span>
              <input type="number" step="0.5" value={form.unitWeight}
                     onChange={(e) => set({ unitWeight: Number(e.target.value) })} />
            </label>
            <label><span>Poisson's ratio (Westergaard)</span>
              <input type="number" step="0.05" min={0} max={0.45} value={form.poisson}
                     onChange={(e) => set({ poisson: Number(e.target.value) })} />
            </label>
          </div>
          {result && !result.offset_is_worst && (
            <button type="button" className="link"
                    onClick={() => set({ offset: `${result.worst_offset_m.toFixed(2)} m` })}>
              Move machine to the worst position ({result.worst_offset_m >= 0 ? "+" : ""}
              {result.worst_offset_m.toFixed(2)} m)
            </button>
          )}
        </div>

        <div className="panel">
          <h2>Allowances and comparison</h2>
          <label><span>Dynamic load allowance</span>
            <select value={form.dlaMode}
                    onChange={(e) => set({ dlaMode: e.target.value as Form["dlaMode"] })}>
              <option value="none">None — stationary or slowly tracking</option>
              <option value="manual">Enter a multiplier</option>
              <option value="aashto_depth">Depth-reduced impact (AASHTO form, unverified)</option>
            </select>
          </label>
          {form.dlaMode === "manual" && (
            <label><span>Multiplier</span>
              <input type="number" step="0.05" min={1} max={2.5} value={form.dla}
                     onChange={(e) => set({ dla: Number(e.target.value) })} />
            </label>
          )}

          <label><span>Load-spread comparison</span>
            <select value={form.spreadPreset}
                    onChange={(e) => set({
                      spreadPreset: e.target.value as Form["spreadPreset"],
                    })}>
              <option value="aashto_granular">AASHTO, select granular (1.15) — unverified</option>
              <option value="aashto_other">AASHTO, other backfill (1.0) — unverified</option>
              <option value="custom">Enter my own factor (e.g. from CSA S6)</option>
              <option value="none">Omit</option>
            </select>
          </label>
          {form.spreadPreset === "custom" && (
            <label><span>Distribution factor</span>
              <input type="number" step="0.05" min={0} max={3} value={form.spreadFactor}
                     onChange={(e) => set({ spreadFactor: Number(e.target.value) })} />
            </label>
          )}
          <p className="muted" style={{ fontSize: 11.5 }}>
            No CSA S6 values are built in — enter your own from the code.
          </p>
        </div>
      </div>

      <div>
        {error && <div className="err">{error}</div>}

        {result && (
          <>
            <div className="verdict ok" style={{ background: "#eef4fb", borderColor: "var(--accent)", color: "var(--accent)" }}>
              <div>
                <div className="big">{result.live_pressure_kpa.toFixed(1)} kPa</div>
                <div className="sub">
                  Free-field vertical stress at the pipe crown, {result.cover_m.toFixed(2)} m cover
                  <br />
                  {result.load_per_m_kn_m.toFixed(1)} kN per metre of pipe ·{" "}
                  {result.live_to_dead_ratio.toFixed(2)}× the soil overburden of{" "}
                  {result.soil_pressure_kpa.toFixed(1)} kPa
                </div>
              </div>
              <button onClick={openReport}>Open calc report</button>
            </div>

            {!result.offset_is_worst && (
              <div className="warn">
                <b>This is not the worst machine position.</b> Moving to{" "}
                {result.worst_offset_m >= 0 ? "+" : ""}{result.worst_offset_m.toFixed(2)} m
                raises the crown stress to{" "}
                <b>{result.worst_offset_pressure_kpa.toFixed(1)} kPa</b>
                {result.live_pressure_kpa > 0.01 && (
                  <> ({(result.worst_offset_pressure_kpa / result.live_pressure_kpa).toFixed(1)}× higher)</>
                )}.
              </div>
            )}

            <div className="panel">
              <h2>Method comparison at crown level</h2>
              <table>
                <thead>
                  <tr><th>Method</th><th className="num">Crown pressure</th><th>Basis</th></tr>
                </thead>
                <tbody>
                  {result.methods.map((m) => (
                    <tr key={m.key}
                        style={m.key === "boussinesq" ? { background: "#eef4fb" } : undefined}>
                      <td>
                        <b>{m.name}</b>
                        {!m.verified && <span className="fail" style={{ fontSize: 11 }}> (unverified)</span>}
                      </td>
                      <td className="num"><b>{m.pressure_kpa.toFixed(1)}</b> kPa</td>
                      <td className="muted" style={{ fontSize: 11.5 }}>
                        {m.basis}{m.note && <><br />{m.note}</>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3>Supporting calculations</h3>
              {result.methods.map((m) => (
                <details className="check-detail" key={m.key}>
                  <summary>
                    {m.name} — {m.pressure_kpa.toFixed(1)} kPa
                  </summary>
                  <div className="formula">{m.formula}</div>
                  <table>
                    <thead>
                      <tr>
                        <th>{m.terms_sum_to_total ? "Contribution" : "Candidate area"}</th>
                        <th>Working</th>
                        <th className="num">σ<sub>z</sub></th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.terms.map((t, i) => (
                        <tr key={i}>
                          <td>{t.label}</td>
                          <td className="muted" style={{ fontSize: 11.5 }}>{t.detail}</td>
                          <td className="num">{t.value_kpa.toFixed(2)} kPa</td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={2}>
                          <b>{m.terms_sum_to_total
                            ? "Sum of contributions"
                            : "Governing (largest) area"}</b>
                        </td>
                        <td className="num"><b>{m.pressure_kpa.toFixed(2)} kPa</b></td>
                      </tr>
                    </tbody>
                  </table>
                  <p className="muted" style={{ fontSize: 11.5 }}>{m.substitution}</p>
                </details>
              ))}

              <table style={{ marginTop: 10 }}>
                <tbody>
                  <tr><th style={{ width: "48%" }}>Surface load</th>
                      <td className="muted">{result.load_description}</td></tr>
                  <tr><th>Dynamic load allowance</th>
                      <td>{result.dla.toFixed(2)} — <span className="muted">{result.dla_basis}</span></td></tr>
                  <tr><th>Average pressure across the pipe</th>
                      <td className="num">{result.average_over_pipe_kpa.toFixed(1)} kPa</td></tr>
                  <tr><th>Vertical load per metre of pipe</th>
                      <td className="num">{result.load_per_m_kn_m.toFixed(2)} kN/m</td></tr>
                </tbody>
              </table>
            </div>

            <div className="panel">
              <h2>Direction of travel</h2>
              <table>
                <thead>
                  <tr>
                    <th>Machine heading</th>
                    <th className="num">At this offset</th>
                    <th className="num">Worst offset</th>
                    <th className="num">Worst case</th>
                  </tr>
                </thead>
                <tbody>
                  {result.orientations.map((o) => (
                    <tr key={o.orientation}
                        style={o.is_current ? { background: "#eef4fb" } : undefined}>
                      <td>
                        <b>{o.label}</b>
                        {o.is_current && <span className="muted"> — selected</span>}
                      </td>
                      <td className="num">{o.pressure_at_offset_kpa.toFixed(1)} kPa</td>
                      <td className="num">
                        {o.worst_offset_m >= 0 ? "+" : ""}{o.worst_offset_m.toFixed(2)} m
                      </td>
                      <td className="num"><b>{o.worst_pressure_kpa.toFixed(1)}</b> kPa</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted" style={{ fontSize: 11.5, marginBottom: 0 }}>
                Both headings are computed every time so you can see which one governs.
                Crossing puts the long track axis over the pipe; tracking along it can
                leave the pipe in the gap between the tracks, which is why the two
                columns on the right can differ so much from the one on the left.
              </p>
            </div>

            <VehicleComparison
              currentVehicle={currentVehicleSpec}
              cover={form.cover}
              pipeOd={form.pipeOd}
              unitWeight={form.unitWeight}
              poisson={form.poisson}
              dlaMode={form.dlaMode}
              dla={form.dla}
              spreadPreset={form.spreadPreset}
              spreadFactor={form.spreadFactor}
            />

            <Iso3D
              bulb={result.bulb}
              crownPlan={result.crown_plan}
              patches={result.patches}
              offsetM={result.machine_offset_m}
              coverM={result.cover_m}
              pipeOdM={result.pipe_od_m}
            />

            <PressureBulb
              bulb={result.bulb}
              patches={result.patches}
              offsetM={result.machine_offset_m}
              coverM={result.cover_m}
              pipeOdM={result.pipe_od_m}
            />

            <SiteDrawing
              patches={result.patches}
              points={result.points}
              coverM={result.cover_m}
              pipeOdM={result.pipe_od_m}
              offsetM={result.machine_offset_m}
              worstOffsetM={result.worst_offset_m}
              offsetIsWorst={result.offset_is_worst}
              orientation={form.orientation}
            />

            <div className="charts">
              <div className="panel">
                <p className="chart-title">Pressure against depth — every method</p>
                <p className="chart-sub">
                  Directly beneath the machine at its current offset. The point-load
                  idealisation is left off this chart — it can be an order of magnitude
                  higher at shallow cover and would swamp the scale; see the table above.
                </p>
                <ResponsiveContainer width="100%" height={190}>
                  <LineChart data={depthData} margin={{ top: 16, right: 26, bottom: 20, left: 4 }}>
                    <CartesianGrid stroke="#e6e9ed" />
                    <XAxis dataKey="depth_m" type="number" tick={{ fontSize: 11 }}
                           domain={["dataMin", "dataMax"]}
                           tickFormatter={(v: number) => v.toFixed(1)}
                           label={{ value: "Depth below surface (m)",
                                    position: "insideBottom", offset: -12,
                                    style: { fontSize: 11 } }} />
                    <YAxis width={68} tick={{ fontSize: 11 }}
                           label={{ value: "Vertical stress (kPa)", angle: -90,
                                    position: "insideLeft", style: { fontSize: 11 } }} />
                    <Tooltip formatter={(v: number, n: string) => [`${v.toFixed(1)} kPa`, n]}
                             labelFormatter={(v: number) => `${Number(v).toFixed(2)} m deep`}
                             contentStyle={{ fontSize: 12 }} />
                    <Legend verticalAlign="top" height={24}
                            wrapperStyle={{ fontSize: 11 }} />
                    {METHOD_SERIES.filter((m) => depthData.length
                        && m.key in depthData[0]).map((m) => (
                      <Line key={m.key} type="monotone" dataKey={m.key}
                            name={m.label} stroke={m.colour}
                            strokeWidth={m.key === "boussinesq" ? 2.4 : 1.6}
                            strokeDasharray={m.dash} dot={false}
                            isAnimationActive={false} />
                    ))}
                    <ReferenceLine x={result.cover_m} stroke="#c02020" strokeDasharray="5 4"
                                   label={{ value: "crown", position: "insideTopRight",
                                            fontSize: 11, fill: "#c02020" }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="panel">
                <p className="chart-title">Pressure against machine position</p>
                <p className="chart-sub">
                  Crown stress as the machine moves across the pipe. Zero is centred on
                  the pipe.
                </p>
                <ResponsiveContainer width="100%" height={190}>
                  <LineChart data={offsetData} margin={{ top: 16, right: 26, bottom: 20, left: 4 }}>
                    <CartesianGrid stroke="#e6e9ed" />
                    <XAxis dataKey="offset" type="number" tick={{ fontSize: 11 }}
                           domain={["dataMin", "dataMax"]}
                           tickFormatter={(v: number) => v.toFixed(1)}
                           label={{ value: "Machine offset from pipe centreline (m)",
                                    position: "insideBottom", offset: -12,
                                    style: { fontSize: 11 } }} />
                    <YAxis width={68} tick={{ fontSize: 11 }}
                           label={{ value: "Crown stress (kPa)", angle: -90,
                                    position: "insideLeft", style: { fontSize: 11 } }} />
                    <Tooltip formatter={(v: number) => [`${v.toFixed(1)} kPa`, "Crown stress"]}
                             labelFormatter={(v: number) => `offset ${Number(v).toFixed(2)} m`}
                             contentStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="pressure" stroke="#1f5fa8" strokeWidth={2}
                          dot={false} isAnimationActive={false} />
                    <ReferenceDot x={result.worst_offset_m} y={result.worst_offset_pressure_kpa}
                                  r={5} fill="#c02020" stroke="#fff" strokeWidth={1.5}
                                  label={{ value: `worst ${result.worst_offset_pressure_kpa.toFixed(1)} kPa`,
                                           position: "top", fontSize: 11, fill: "#c02020",
                                           fontWeight: 700 }} />
                    <ReferenceDot x={result.machine_offset_m} y={result.live_pressure_kpa}
                                  r={4} fill="#0a7a2a" stroke="#fff" strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <h2>Limitations</h2>
              {result.warnings.map((w, i) => <div className="warn" key={i}>{w}</div>)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
