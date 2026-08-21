import type { AxleSpecIn } from "../../api/types";

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

interface Props {
  open: boolean;
  axles: AxleRow[];
  axleWidth: string;
  onChange: (axles: AxleRow[], axleWidth: string) => void;
  onClose: () => void;
}

export default function AxleEditor({ open, axles, axleWidth, onChange, onClose }: Props) {
  if (!open) return null;

  const updateRow = (i: number, patch: Partial<AxleRow>) => {
    onChange(axles.map((r, j) => (j === i ? { ...r, ...patch } : r)), axleWidth);
  };
  const addRow = () => onChange([...axles, blankAxleRow(axles.length + 1)], axleWidth);
  const removeRow = (i: number) => onChange(axles.filter((_, j) => j !== i), axleWidth);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 style={{ margin: 0 }}>Axle configuration</h2>
          <button type="button" className="link" onClick={onClose}>Close ✕</button>
        </div>

        <label style={{ maxWidth: 260 }}><span>Axle (track) width — left/right wheel centres</span>
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
