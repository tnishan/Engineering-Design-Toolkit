import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  deleteSavedVehicle,
  deleteSoilProject,
  listSavedVehicles,
  listSoilProjects,
  listVehiclePresets,
  loadSavedVehicle,
  loadSoilProject,
  pipeSurcharge,
  saveSavedVehicle,
  saveSoilProject,
} from "../../api/client";
import type {
  Orientation,
  SavedVehicleSummary,
  SoilProjectSummary,
  SurchargeRequest,
  SurchargeResponse,
  VehiclePresets,
  VehicleSpec,
} from "../../api/types";
import AxleEditor, { axleRowsToRequest, axleSpecsToRows, blankAxleRow, type AxleRow } from "./AxleEditor";
import Iso3D from "./Iso3D";
import MethodDiagram from "./MethodDiagrams";
import PressureBulb from "./PressureBulb";
import SiteDrawing from "./SiteDrawing";
import SoilProjectBar from "./SoilProjectBar";
import VehicleComparison from "./VehicleComparison";
import VehicleDiagram from "./VehicleDiagram";

interface Form {
  project: string;
  member: string;
  engineer: string;
  orientation: Orientation;
  // unified axle-based vehicle model
  truckAxles: AxleRow[];
  truckAxleWidth: string;
  vehiclePreset: string;
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
  orientation: "across",
  truckAxles: [{
    label: "Tracks",
    loadKn: 220,
    tiresPerSide: 1 as 1 | 2,
    tireWidth: "762 mm",
    tireLength: "4470 mm",
    tirePressureKpa: "",
    dualSpacing: "0",
    spacingFromPrevious: "0",
  }],
  truckAxleWidth: "2.41 m",
  vehiclePreset: "cat_320",
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
    load_type: "truck",
    tracked: null,
    wheels: null,
    truck_axles: axleRowsToRequest(f.truckAxles),
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
    // Carries the preset's provenance (source, verified, assumptions) to the
    // server. The axle figures alone arrive as bare numbers, so without this
    // neither the report nor the export can say where they came from or that
    // they are an unconfirmed transcription. "custom" and saved user vehicles
    // are not built-in presets, so they claim no provenance.
    vehicle_preset_key:
      f.vehiclePreset === "custom" || f.vehiclePreset.startsWith("user_")
        ? "" : f.vehiclePreset,
  };
}

const METHOD_SERIES = [
  { key: "boussinesq", label: "Boussinesq", colour: "#1f5fa8", dash: undefined },
  { key: "westergaard", label: "Westergaard", colour: "#0e8fa8", dash: "6 3" },
  { key: "spread_2to1", label: "2:1 spread (merged)", colour: "#a86a00", dash: "3 3" },
  { key: "spread_superposed", label: "2:1 spread (summed)", colour: "#8a5fb0", dash: "1 3" },
  { key: "code_spread", label: "Code spread", colour: "#6b7280", dash: "2 3" },
];

function presetToAxleRows(preset: { axles: { label: string; load_kn: number; tires_per_side: number; tire_width_m: number; tire_length_m: number | null; tire_pressure_kpa: number | null; dual_spacing_m: number; spacing_from_previous_m: number }[] }): AxleRow[] {
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
  const [savedVehicles, setSavedVehicles] = useState<SavedVehicleSummary[]>([]);
  const [axleEditorOpen, setAxleEditorOpen] = useState(false);
  const [saveVehicleModalOpen, setSaveVehicleModalOpen] = useState(false);
  const [saveVehicleName, setSaveVehicleName] = useState("");

  const [projects, setProjects] = useState<SoilProjectSummary[]>([]);
  const [projectBusy, setProjectBusy] = useState(false);

  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  const refreshProjects = () => {
    listSoilProjects().then(setProjects).catch(() => setProjects([]));
  };

  const refreshSavedVehiclesList = () => {
    listSavedVehicles().then(setSavedVehicles).catch(() => setSavedVehicles([]));
  };

  useEffect(() => {
    listVehiclePresets().then(setPresets).catch(() => setPresets(null));
    refreshProjects();
    refreshSavedVehiclesList();
  }, []);

  const handleSelectVehiclePreset = async (key: string) => {
    if (key === "custom") {
      set({ vehiclePreset: "custom" });
      return;
    }

    // Check built-in presets (unified — all have axles)
    const builtinPreset = presets?.vehicles?.find((v) => v.key === key);
    if (builtinPreset) {
      set({
        vehiclePreset: key,
        truckAxles: presetToAxleRows(builtinPreset),
        truckAxleWidth: `${(builtinPreset.axle_width_m * 1000).toFixed(0)} mm`,
      });
      return;
    }

    // Check user-saved vehicles from database
    if (key.startsWith("user_")) {
      const vid = key.replace(/^user_/, "");
      try {
        const sv = await loadSavedVehicle(vid);
        set({
          vehiclePreset: key,
          truckAxles: sv.truck_axles && sv.truck_axles.length ? axleSpecsToRows(sv.truck_axles) : form.truckAxles,
          truckAxleWidth: typeof sv.truck_axle_width === "number" ? `${sv.truck_axle_width}` : String(sv.truck_axle_width ?? form.truckAxleWidth),
        });
      } catch (e) {
        alert(`Could not load saved vehicle: ${e instanceof Error ? e.message : e}`);
      }
    }
  };

  const handleSaveCurrentVehicleToDb = async () => {
    if (!saveVehicleName.trim()) return;
    try {
      const payload = {
        load_type: "truck" as const,
        tracked: null,
        wheels: null,
        truck_axles: axleRowsToRequest(form.truckAxles),
        truck_axle_width: form.truckAxleWidth,
      };
      await saveSavedVehicle(saveVehicleName.trim(), payload);
      refreshSavedVehiclesList();
      setSaveVehicleModalOpen(false);
      setSaveVehicleName("");
    } catch (e) {
      alert(`Could not save vehicle: ${e instanceof Error ? e.message : e}`);
    }
  };


  const handleDeleteCurrentSavedVehicle = async () => {
    if (!form.vehiclePreset.startsWith("user_")) return;
    const vid = form.vehiclePreset.replace(/^user_/, "");
    if (!confirm("Delete this custom vehicle from the database?")) return;
    try {
      await deleteSavedVehicle(vid);
      refreshSavedVehiclesList();
      set({ vehiclePreset: "custom" });
    } catch (e) {
      alert(`Could not delete vehicle: ${e instanceof Error ? e.message : e}`);
    }
  };

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

  const handleSaveProject = async (name: string) => {
    setProjectBusy(true);
    try {
      set({ project: name });
      const req = toRequest({ ...form, project: name });
      await saveSoilProject(name, req);
      refreshProjects();
    } catch (e) {
      alert(`Could not save project: ${e instanceof Error ? e.message : e}`);
    } finally {
      setProjectBusy(false);
    }
  };

  const extractAxleConfig = (p: any): { axles: AxleRow[]; axleWidth: string } => {
    if (p.truck_axles && p.truck_axles.length > 0) {
      return {
        axles: axleSpecsToRows(p.truck_axles),
        axleWidth: typeof p.truck_axle_width === "number" ? `${p.truck_axle_width} m` : String(p.truck_axle_width ?? "1.8 m"),
      };
    }
    if (p.tracked) {
      return {
        axles: [{
          label: "Tracks",
          loadKn: p.tracked.weight_kn,
          tiresPerSide: 1,
          tireWidth: typeof p.tracked.track_width === "number" ? `${p.tracked.track_width * 1000} mm` : String(p.tracked.track_width),
          tireLength: typeof p.tracked.track_length === "number" ? `${p.tracked.track_length * 1000} mm` : String(p.tracked.track_length),
          tirePressureKpa: "",
          dualSpacing: "0",
          spacingFromPrevious: "0",
        }],
        axleWidth: typeof p.tracked.gauge === "number" ? `${p.tracked.gauge} m` : String(p.tracked.gauge ?? "2.4 m"),
      };
    }
    if (p.wheels) {
      const w = p.wheels;
      const count = w.axle_count || 1;
      const dual = (typeof w.dual_spacing === "number" ? w.dual_spacing : Number.parseFloat(w.dual_spacing || "0")) > 0;
      const tps = dual ? 2 : 1;
      const loadPerAxle = w.wheel_load_kn * 2 * tps;
      return {
        axles: Array.from({ length: count }, (_, i) => ({
          label: `Axle ${i + 1}`,
          loadKn: loadPerAxle,
          tiresPerSide: tps as 1 | 2,
          tireWidth: typeof w.patch_across_travel === "number" ? `${w.patch_across_travel * 1000} mm` : String(w.patch_across_travel),
          tireLength: typeof w.patch_along_travel === "number" ? `${w.patch_along_travel * 1000} mm` : String(w.patch_along_travel),
          tirePressureKpa: "",
          dualSpacing: typeof w.dual_spacing === "number" ? `${w.dual_spacing * 1000} mm` : String(w.dual_spacing || "0"),
          spacingFromPrevious: i === 0 ? "0" : (typeof w.axle_spacing === "number" ? `${w.axle_spacing * 1000} mm` : String(w.axle_spacing || "1.2 m")),
        })),
        axleWidth: typeof w.axle_width === "number" ? `${w.axle_width} m` : String(w.axle_width ?? "1.8 m"),
      };
    }
    return {
      axles: [blankAxleRow(1)],
      axleWidth: "1.8 m",
    };
  };

  const handleLoadProject = async (id: string) => {
    setProjectBusy(true);
    try {
      const proj = await loadSoilProject(id);
      const p = proj.payload;
      const { axles, axleWidth } = extractAxleConfig(p);
      setForm({
        project: p.project || proj.name,
        member: p.member || "Pipe crossing",
        engineer: p.engineer || "",
        orientation: p.orientation || "across",
        truckAxles: axles,
        truckAxleWidth: axleWidth,
        vehiclePreset: "custom",
        cover: typeof p.cover === "number" ? `${p.cover}` : String(p.cover ?? "1.0 m"),
        pipeOd: typeof p.pipe_od === "number" ? `${p.pipe_od}` : String(p.pipe_od ?? "600"),
        offset: typeof p.machine_offset === "number" ? `${p.machine_offset}` : String(p.machine_offset ?? "0"),
        unitWeight: p.soil_unit_weight_kn_m3 ?? 20,
        poisson: p.poisson_ratio ?? 0,
        dlaMode: p.dla_mode || "manual",
        dla: p.dla ?? 1.3,
        spreadPreset: p.spread_preset || "aashto_granular",
        spreadFactor: p.spread_factor ?? 1.15,
      });
    } catch (e) {
      alert(`Could not load project: ${e instanceof Error ? e.message : e}`);
    } finally {
      setProjectBusy(false);
    }
  };

  const handleDeleteProject = async (id: string) => {
    setProjectBusy(true);
    try {
      await deleteSoilProject(id);
      refreshProjects();
    } catch (e) {
      alert(`Could not delete project: ${e instanceof Error ? e.message : e}`);
    } finally {
      setProjectBusy(false);
    }
  };

  const handleImportProject = (payload: SurchargeRequest, name: string) => {
    const { axles, axleWidth } = extractAxleConfig(payload);
    setForm({
      project: name || payload.project || "Imported Project",
      member: payload.member || "Pipe crossing",
      engineer: payload.engineer || "",
      orientation: payload.orientation || "across",
      truckAxles: axles,
      truckAxleWidth: axleWidth,
      vehiclePreset: "custom",
      cover: typeof payload.cover === "number" ? `${payload.cover}` : String(payload.cover ?? "1.0 m"),
      pipeOd: typeof payload.pipe_od === "number" ? `${payload.pipe_od}` : String(payload.pipe_od ?? "600"),
      offset: typeof payload.machine_offset === "number" ? `${payload.machine_offset}` : String(payload.machine_offset ?? "0"),
      unitWeight: payload.soil_unit_weight_kn_m3 ?? 20,
      poisson: payload.poisson_ratio ?? 0,
      dlaMode: payload.dla_mode || "manual",
      dla: payload.dla ?? 1.3,
      spreadPreset: payload.spread_preset || "aashto_granular",
      spreadFactor: payload.spread_factor ?? 1.15,
    });
  };

  const currentVehicleSpec: VehicleSpec = {
    label: "Current configuration",
    load_type: "truck",
    orientation: form.orientation,
    truck_axles: axleRowsToRequest(form.truckAxles),
    truck_axle_width: form.truckAxleWidth,
  };

  const depthData = result?.depth_profile ?? [];
  const offsetData = result?.offset_profile.map((p) => ({
    offset: p.offset_m, pressure: p.pressure_kpa,
  })) ?? [];

  const totalAxleLoadKn = form.truckAxles.reduce((s, a) => s + (Number(a.loadKn) || 0), 0);

  const excavatorPresets = (presets?.vehicles ?? []).filter((v) => v.category === "excavator");
  const truckPresets = (presets?.vehicles ?? []).filter((v) => v.category !== "excavator");

  return (
    <div className="app">
      <div>
        <SoilProjectBar
          projects={projects}
          currentName={form.project}
          busy={projectBusy}
          onSave={handleSaveProject}
          onLoad={handleLoadProject}
          onDelete={handleDeleteProject}
          onImport={handleImportProject}
          buildPayload={() => toRequest(form)}
        />

        <div className="panel">
          <h2>Project metadata</h2>
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
          <h2>Surface load & Vehicle presets</h2>

          {/* Unified Vehicle Preset Dropdown */}
          <label><span>Vehicle / Equipment Database</span>
            <select
              value={form.vehiclePreset}
              onChange={(e) => handleSelectVehiclePreset(e.target.value)}
            >
              {excavatorPresets.length > 0 && (
                <optgroup label="Excavators & Tracked Plant (Single Axle / Dual Track)">
                  {excavatorPresets.map((v) => (
                    <option key={v.key} value={v.key}>
                      {v.name} ({v.total_load_kn.toFixed(0)} kN)
                    </option>
                  ))}
                </optgroup>
              )}
              {truckPresets.length > 0 && (
                <optgroup label="Trucks & Multi-Axle Vehicles">
                  {truckPresets.map((v) => (
                    <option key={v.key} value={v.key}>
                      {v.name} ({v.axles.length} axles, {v.total_load_kn.toFixed(0)} kN)
                    </option>
                  ))}
                </optgroup>
              )}
              {savedVehicles.length > 0 && (
                <optgroup label="User Saved Vehicles (Database)">
                  {savedVehicles.map((sv) => (
                    <option key={sv.id} value={`user_${sv.id}`}>
                      {sv.name} ({sv.total_load_kn} kN total)
                    </option>
                  ))}
                </optgroup>
              )}
              <option value="custom">Custom vehicle / manual axle configuration</option>
            </select>
          </label>

          <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
            <button
              type="button"
              className="link"
              onClick={() => {
                setSaveVehicleName(form.project || "Custom Vehicle");
                setSaveVehicleModalOpen(true);
              }}
            >
              + Save current vehicle layout to database...
            </button>
            {form.vehiclePreset.startsWith("user_") && (
              <button type="button" className="link" onClick={handleDeleteCurrentSavedVehicle} style={{ color: "#c02020" }}>
                Delete this vehicle
              </button>
            )}
          </div>

          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px", marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>
                  {form.truckAxles.length === 1 && form.truckAxles[0].label.toLowerCase().includes("track")
                    ? "Tracked Machine (2 Tracks)"
                    : `${form.truckAxles.length} Axle Line(s)`}
                </div>
                <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                  Total load: <b>{totalAxleLoadKn.toFixed(0)} kN</b> · Track / gauge width: <b>{form.truckAxleWidth}</b>
                </div>
              </div>
              <button
                type="button"
                className="primary"
                style={{ width: "auto", fontSize: 12, padding: "6px 12px" }}
                onClick={() => setAxleEditorOpen(true)}
              >
                Edit axle & track details…
              </button>
            </div>
          </div>

          <AxleEditor
            open={axleEditorOpen}
            axles={form.truckAxles}
            axleWidth={form.truckAxleWidth}
            onChange={(axles, axleWidth) => set({
              truckAxles: axles, truckAxleWidth: axleWidth, vehiclePreset: "custom",
            })}
            onClose={() => setAxleEditorOpen(false)}
          />

          <label style={{ marginTop: 6 }}><span>Direction of travel</span>
            <select value={form.orientation}
                    onChange={(e) => set({ orientation: e.target.value as Orientation })}>
              <option value="across">Crossing the pipe (at right angles)</option>
              <option value="along">Tracking along the pipe (parallel)</option>
            </select>
          </label>
          <p className="muted" style={{ fontSize: 11.5 }}>
            Crossing puts the long track or wheelbase axis over the pipe;
            tracking along it can leave the pipe in the gap between the tracks or wheels.
          </p>
        </div>


        {/* Modal to Save Vehicle Layout to Database */}
        {saveVehicleModalOpen && (
          <div className="modal-backdrop" onClick={() => setSaveVehicleModalOpen(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
              <div className="modal-head">
                <h2 style={{ margin: 0 }}>Save Vehicle to Database</h2>
                <button type="button" className="link" onClick={() => setSaveVehicleModalOpen(false)}>✕</button>
              </div>
              <label>
                <span>Vehicle Name / Model</span>
                <input
                  value={saveVehicleName}
                  placeholder="e.g. CAT 330D Excavator or 50t Crane"
                  onChange={(e) => setSaveVehicleName(e.target.value)}
                />
              </label>
              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 12 }}>
                <button type="button" onClick={() => setSaveVehicleModalOpen(false)}>Cancel</button>
                <button type="button" className="primary" style={{ width: "auto" }} onClick={handleSaveCurrentVehicleToDb}>
                  Save Vehicle
                </button>
              </div>
            </div>
          </div>
        )}

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

            {/* Ahead of every number it feeds: confirm the machine is right
                before reading any pressure computed from it. */}
            {result.vehicle && <VehicleDiagram vehicle={result.vehicle} />}

            {/* Arrangement relative to the pipe (Section, Plan, and Schedule) */}
            <SiteDrawing
              patches={result.patches}
              points={result.points}
              coverM={result.cover_m}
              pipeOdM={result.pipe_od_m}
              offsetM={result.machine_offset_m}
              worstOffsetM={result.worst_offset_m}
              offsetIsWorst={result.offset_is_worst}
              orientation={form.orientation}
              vehicle={result.vehicle}
              onOffsetChange={(m) => set({ offset: `${m >= 0 ? "+" : ""}${m.toFixed(2)} m` })}
            />

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

              <h3 style={{ marginTop: 18, marginBottom: 8 }}>Supporting calculations & Visual Diagrams</h3>
              {result.methods.map((m) => (
                <details className="check-detail" key={m.key} open={m.key === "boussinesq"}>
                  <summary style={{ fontWeight: 600 }}>
                    {m.name} — {m.pressure_kpa.toFixed(1)} kPa
                  </summary>

                  {/* SVG Method Diagram */}
                  <MethodDiagram methodKey={m.key} coverM={result.cover_m} spreadFactor={form.spreadFactor} />

                  <div style={{ marginTop: 8, marginBottom: 8, fontSize: 12 }}>
                    <p style={{ margin: "4px 0" }}><b>Physical Basis:</b> {m.basis}</p>
                    {m.note && <p style={{ margin: "4px 0", color: "#475569" }}><b>Note:</b> {m.note}</p>}
                  </div>

                  <div className="formula" style={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 12, background: "#f1f5f9", padding: "8px 12px", borderRadius: 4, margin: "8px 0" }}>
                    {m.formula}
                  </div>

                  <table>
                    <thead>
                      <tr>
                        <th>{m.terms_sum_to_total ? "Contribution / Patch" : "Candidate area"}</th>
                        <th>Working & Parameters</th>
                        <th className="num">σ<sub>z</sub></th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.terms.map((t, i) => (
                        <tr key={i}>
                          <td><b>{t.label}</b></td>
                          <td className="muted" style={{ fontSize: 11.5 }}>{t.detail}</td>
                          <td className="num">{t.value_kpa.toFixed(2)} kPa</td>
                        </tr>
                      ))}
                      <tr style={{ background: "#f8fafc" }}>
                        <td colSpan={2}>
                          <b>{m.terms_sum_to_total
                            ? "Sum of contributions (including DLA multiplier)"
                            : "Governing (largest) pressure (including DLA multiplier)"}</b>
                        </td>
                        <td className="num"><b>{m.pressure_kpa.toFixed(2)} kPa</b></td>
                      </tr>
                    </tbody>
                  </table>
                  <p className="muted" style={{ fontSize: 11.5, marginTop: 8, fontStyle: "italic" }}>
                    <b>Step-by-step substitution:</b> {m.substitution}
                  </p>
                </details>
              ))}

              <table style={{ marginTop: 16 }}>
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
              orientation={form.orientation}
            />

            <PressureBulb
              bulb={result.bulb}
              patches={result.patches}
              offsetM={result.machine_offset_m}
              coverM={result.cover_m}
              pipeOdM={result.pipe_od_m}
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
                    <Tooltip formatter={(v: any, n: any) => [`${Number(v ?? 0).toFixed(1)} kPa`, String(n)]}
                             labelFormatter={(v: any) => `${Number(v ?? 0).toFixed(2)} m deep`}
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
                    <Tooltip formatter={(v: any) => [`${Number(v ?? 0).toFixed(1)} kPa`, "Crown stress"]}
                             labelFormatter={(v: any) => `offset ${Number(v ?? 0).toFixed(2)} m`}
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
