import { useEffect, useRef, useState } from "react";
import { deleteAxleConfig, listAxleConfigs, loadAxleConfig, saveAxleConfig } from "../../api/client";
import type { AxleConfigSummary, AxleSpecIn } from "../../api/types";

export interface AxleRow {
  label: string;
  loadKn: number;
  tiresPerSide: 1 | 2;
  tireWidth: string;
  tireLength: string;       // empty -> derive from pressure instead
  tirePressureKpa: string;  // empty -> tireLength is used directly
  dualSpacing: string;
  spacingFromPrevious: string;
}

export function blankAxleRow(n: number): AxleRow {
  return {
    label: `Axle ${n}`,
    loadKn: 100,
    tiresPerSide: 1,
    tireWidth: "300",
    tireLength: "250",
    tirePressureKpa: "",
    dualSpacing: "0",
    spacingFromPrevious: n === 1 ? "0" : "4 m",
  };
}

export function axleRowsToRequest(rows: AxleRow[]): AxleSpecIn[] {
  return rows.map((r) => ({
    label: r.label,
    load_kn: r.loadKn,
    tires_per_side: r.tiresPerSide,
    tire_width: r.tireWidth,
    tire_length: r.tireLength.trim() === "" ? null : r.tireLength,
    tire_pressure_kpa: r.tirePressureKpa.trim() === "" ? null : Number(r.tirePressureKpa),
    dual_spacing: r.dualSpacing,
    spacing_from_previous: r.spacingFromPrevious,
  }));
}

export function axleSpecsToRows(specs: AxleSpecIn[]): AxleRow[] {
  return specs.map((a, i) => ({
    label: a.label || `Axle ${i + 1}`,
    loadKn: a.load_kn,
    tiresPerSide: (a.tires_per_side as 1 | 2) || 1,
    tireWidth: typeof a.tire_width === "number" ? `${a.tire_width}` : String(a.tire_width || "300"),
    tireLength: a.tire_length != null ? String(a.tire_length) : "",
    tirePressureKpa: a.tire_pressure_kpa != null ? String(a.tire_pressure_kpa) : "",
    dualSpacing: typeof a.dual_spacing === "number" ? `${a.dual_spacing}` : String(a.dual_spacing || "0"),
    spacingFromPrevious: typeof a.spacing_from_previous === "number" ? `${a.spacing_from_previous}` : String(a.spacing_from_previous || "0"),
  }));
}

interface Props {
  open: boolean;
  axles: AxleRow[];
  axleWidth: string;
  onChange: (axles: AxleRow[], axleWidth: string) => void;
  onClose: () => void;
}

export default function AxleEditor({ open, axles, axleWidth, onChange, onClose }: Props) {
  const [configs, setConfigs] = useState<AxleConfigSummary[]>([]);
  const [selectedConfig, setSelectedConfig] = useState("");
  const [configName, setConfigName] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      listAxleConfigs().then(setConfigs).catch(() => setConfigs([]));
    }
  }, [open]);

  if (!open) return null;

  const updateRow = (i: number, patch: Partial<AxleRow>) => {
    onChange(axles.map((r, j) => (j === i ? { ...r, ...patch } : r)), axleWidth);
  };
  const addRow = () => onChange([...axles, blankAxleRow(axles.length + 1)], axleWidth);
  const removeRow = (i: number) => onChange(axles.filter((_, j) => j !== i), axleWidth);

  const handleSaveConfig = async () => {
    if (!configName.trim()) return;
    setBusy(true);
    try {
      const summary = await saveAxleConfig(configName.trim(), axleRowsToRequest(axles), axleWidth);
      const updated = await listAxleConfigs();
      setConfigs(updated);
      setSelectedConfig(summary.id);
    } catch (e) {
      alert(`Error saving axle configuration: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const handleLoadConfig = async (id: string) => {
    if (!id) return;
    setBusy(true);
    try {
      const conf = await loadAxleConfig(id);
      const loadedRows = axleSpecsToRows(conf.truck_axles);
      const loadedWidth = typeof conf.truck_axle_width === "number" ? `${conf.truck_axle_width} m` : String(conf.truck_axle_width);
      onChange(loadedRows, loadedWidth);
      setConfigName(conf.name);
    } catch (e) {
      alert(`Error loading axle configuration: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteConfig = async (id: string) => {
    if (!id) return;
    const c = configs.find((x) => x.id === id);
    if (!c || !confirm(`Delete saved axle configuration "${c.name}"?`)) return;
    setBusy(true);
    try {
      await deleteAxleConfig(id);
      const updated = await listAxleConfigs();
      setConfigs(updated);
      setSelectedConfig("");
    } catch (e) {
      alert(`Error deleting axle configuration: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const exportJson = () => {
    const record = {
      name: configName || "axle-config",
      truck_axle_width: axleWidth,
      truck_axles: axleRowsToRequest(axles),
    };
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(configName || "axle-config").replace(/[^\w.-]+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = async (file: File) => {
    try {
      const text = await file.text();
      const record = JSON.parse(text);
      if (!record.truck_axles || !Array.isArray(record.truck_axles)) {
        throw new Error("File does not contain valid truck_axles array.");
      }
      const loadedRows = axleSpecsToRows(record.truck_axles);
      const loadedWidth = record.truck_axle_width ? String(record.truck_axle_width) : axleWidth;
      onChange(loadedRows, loadedWidth);
      if (record.name) setConfigName(record.name);
    } catch (e) {
      alert(`Could not import file: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 style={{ margin: 0 }}>Axle configuration</h2>
          <button type="button" className="link" onClick={onClose}>Close ✕</button>
        </div>

        {/* Saved Axle Configs Management */}
        <div style={{ background: "#f8fafc", padding: "10px 14px", borderRadius: 6, border: "1px solid #e2e8f0", marginBottom: 14 }}>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <label style={{ flex: 2 }}>
              <span>Save current configuration as</span>
              <input
                value={configName}
                placeholder="e.g. 5-Axle Mobile Crane 60t"
                onChange={(e) => setConfigName(e.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy || !configName.trim()}
              onClick={handleSaveConfig}
              style={{ flex: 0, whiteSpace: "nowrap" }}
            >
              Save config
            </button>
          </div>

          <div className="row" style={{ alignItems: "flex-end", marginTop: 6 }}>
            <label style={{ flex: 2 }}>
              <span>Load saved configuration</span>
              <select value={selectedConfig} onChange={(e) => setSelectedConfig(e.target.value)}>
                <option value="">
                  {configs.length ? "— select saved axle layout —" : "— no saved layouts —"}
                </option>
                {configs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.axle_count} axles · {c.total_load_kn} kN total)
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={!selectedConfig || busy}
              onClick={() => handleLoadConfig(selectedConfig)}
              style={{ flex: 0 }}
            >
              Load
            </button>
            <button
              type="button"
              disabled={!selectedConfig || busy}
              onClick={() => handleDeleteConfig(selectedConfig)}
              style={{ flex: 0 }}
            >
              Delete
            </button>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button type="button" className="link" onClick={exportJson}>
              Export .json
            </button>
            <button type="button" className="link" onClick={() => fileRef.current?.click()}>
              Import .json
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importJson(f);
                e.target.value = "";
              }}
            />
          </div>
        </div>

        <label style={{ maxWidth: 280 }}><span>Axle (track) width — left/right wheel centres</span>
          <input value={axleWidth} onChange={(e) => onChange(axles, e.target.value)} />
        </label>

        <div style={{ overflowX: "auto" }}>
          <table className="axle-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Load (kN)</th>
                <th>Tyres/side</th>
                <th>Tyre width</th>
                <th>Contact length</th>
                <th>or pressure (kPa)</th>
                <th>Dual spacing</th>
                <th>Spacing from previous</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {axles.map((r, i) => (
                <tr key={i}>
                  <td><input value={r.label}
                             onChange={(e) => updateRow(i, { label: e.target.value })} /></td>
                  <td><input type="number" step="1" value={r.loadKn}
                             onChange={(e) => updateRow(i, { loadKn: Number(e.target.value) })} /></td>
                  <td>
                    <select value={r.tiresPerSide}
                            onChange={(e) => updateRow(i, {
                              tiresPerSide: Number(e.target.value) as 1 | 2,
                            })}>
                      <option value={1}>1 (single)</option>
                      <option value={2}>2 (dual)</option>
                    </select>
                  </td>
                  <td><input value={r.tireWidth}
                             onChange={(e) => updateRow(i, { tireWidth: e.target.value })} /></td>
                  <td><input value={r.tireLength} placeholder="e.g. 250"
                             onChange={(e) => updateRow(i, { tireLength: e.target.value })} /></td>
                  <td><input value={r.tirePressureKpa} placeholder="e.g. 700"
                             onChange={(e) => updateRow(i, { tirePressureKpa: e.target.value })} /></td>
                  <td>
                    <input value={r.dualSpacing} disabled={r.tiresPerSide === 1}
                           onChange={(e) => updateRow(i, { dualSpacing: e.target.value })} />
                  </td>
                  <td>
                    <input value={r.spacingFromPrevious} disabled={i === 0}
                           onChange={(e) => updateRow(i, { spacingFromPrevious: e.target.value })} />
                  </td>
                  <td>
                    <button type="button" className="link" onClick={() => removeRow(i)}>×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="link" onClick={addRow}>+ add axle</button>

        <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
          Give either a contact length or a tyre pressure per axle (not both — length
          wins if both are filled in). Pressure derives the contact patch from
          area = load ÷ pressure, a standard pavement-engineering approximation.
          Spacing from previous is measured from the axle immediately ahead; the first
          axle has none.
        </p>
      </div>
    </div>
  );
}
