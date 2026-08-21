import { Fragment } from "react";
import type { ConditionsInput, LoadCase, LoadInput, Material } from "../../api/types";

export interface FormState {
  project: string;
  member: string;
  engineer: string;
  spans: string[];
  supports: ("pin" | "roller" | "fixed" | "free")[];
  materialKey: string;
  autoSize: boolean;
  plyWidth: string;
  depth: string;
  plies: number;
  maxPlies: number;
  loads: LoadInput[];
  conditions: ConditionsInput;
  liveRatio: number;
  totalRatio: number;
  creepFactor: number;
  includeWind: boolean;
  includeSelfWeight: boolean;
}

interface Props {
  state: FormState;
  materials: Material[];
  busy: boolean;
  onChange: (next: FormState) => void;
  onSubmit: () => void;
}

const IN = 25.4;
const fmtIn = (mm: number) => `${(mm / IN).toFixed(3).replace(/\.?0+$/, "")}"`;

export default function InputForm({ state, materials, busy, onChange, onSubmit }: Props) {
  const set = (patch: Partial<FormState>) => onChange({ ...state, ...patch });
  const material = materials.find((m) => m.key === state.materialKey);
  const isScl = material?.family === "scl";

  const setSpanCount = (n: number) => {
    const spans = [...state.spans];
    const supports = [...state.supports];
    while (spans.length < n) spans.push("10 ft");
    while (spans.length > n) spans.pop();
    while (supports.length < n + 1) supports.push("roller");
    while (supports.length > n + 1) supports.pop();
    set({ spans, supports });
  };

  const updateLoad = (i: number, patch: Partial<LoadInput>) => {
    const loads = state.loads.map((l, j) => (j === i ? { ...l, ...patch } : l));
    set({ loads });
  };

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
    >
      <div className="panel">
        <h2>Project</h2>
        <label><span>Project</span>
          <input value={state.project} onChange={(e) => set({ project: e.target.value })} />
        </label>
        <div className="row">
          <label><span>Member mark</span>
            <input value={state.member} onChange={(e) => set({ member: e.target.value })} />
          </label>
          <label><span>Engineer</span>
            <input value={state.engineer} onChange={(e) => set({ engineer: e.target.value })} />
          </label>
        </div>
      </div>

      <div className="panel">
        <h2>Geometry</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
          Enter lengths any way you like: <code>18 ft</code>, <code>12'-6"</code>,
          <code> 5.5 m</code>, <code>235</code> (mm). All calculations run in SI.
        </p>
        <label><span>Number of spans</span>
          <select value={state.spans.length}
                  onChange={(e) => setSpanCount(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {state.spans.map((s, i) => (
          <label key={i}><span>Span {i + 1}</span>
            <input value={s} onChange={(e) => {
              const spans = [...state.spans];
              spans[i] = e.target.value;
              set({ spans });
            }} />
          </label>
        ))}
        <div className="row">
          {state.supports.map((sup, i) => (
            <label key={i}><span>Support {i + 1}</span>
              <select value={sup} onChange={(e) => {
                const supports = [...state.supports];
                supports[i] = e.target.value as FormState["supports"][number];
                set({ supports });
              }}>
                <option value="pin">Pin</option>
                <option value="roller">Roller</option>
                <option value="fixed">Fixed</option>
              </select>
            </label>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Material and section</h2>
        <label><span>Material</span>
          <select value={state.materialKey}
                  onChange={(e) => {
                    const m = materials.find((x) => x.key === e.target.value);
                    const patch: Partial<FormState> = { materialKey: e.target.value };
                    if (m?.family === "scl" && m.available_widths_mm.length) {
                      patch.plyWidth = fmtIn(m.available_widths_mm[0]);
                      patch.depth = fmtIn(m.available_depths_mm[0]);
                    } else if (m?.family === "sawn") {
                      patch.plyWidth = "38";
                      patch.depth = "235";
                    }
                    set(patch);
                  }}>
            <optgroup label="Structural composite lumber (Weyerhaeuser TJ-9500)">
              {materials.filter((m) => m.family === "scl").map((m) => (
                <option key={m.key} value={m.key}>{m.name}</option>
              ))}
            </optgroup>
            <optgroup label="Sawn lumber (CSA O86 — unverified transcription)">
              {materials.filter((m) => m.family === "sawn").map((m) => (
                <option key={m.key} value={m.key}>{m.name}</option>
              ))}
            </optgroup>
          </select>
        </label>
        {material && !material.verified && (
          <div className="warn">
            Properties for this material are transcribed and unverified. Confirm against
            CSA O86 before use.
          </div>
        )}

        <div className="inline">
          <input type="checkbox" id="autoSize" checked={state.autoSize}
                 onChange={(e) => set({ autoSize: e.target.checked })} />
          <label htmlFor="autoSize" style={{ margin: 0 }}>
            Find the lightest section that works
          </label>
        </div>

        {state.autoSize ? (
          <label><span>Maximum plies to consider</span>
            <input type="number" min={1} max={12} value={state.maxPlies}
                   onChange={(e) => set({ maxPlies: Number(e.target.value) })} />
          </label>
        ) : (
          <div className="row">
            <label><span>Ply width</span>
              {isScl && material!.available_widths_mm.length > 1 ? (
                <select value={state.plyWidth}
                        onChange={(e) => set({ plyWidth: e.target.value })}>
                  {material!.available_widths_mm.map((w) => (
                    <option key={w} value={fmtIn(w)}>{fmtIn(w)}</option>
                  ))}
                </select>
              ) : (
                <input value={state.plyWidth}
                       onChange={(e) => set({ plyWidth: e.target.value })} />
              )}
            </label>
            <label><span>Depth</span>
              {isScl ? (
                <select value={state.depth} onChange={(e) => set({ depth: e.target.value })}>
                  {material!.available_depths_mm.map((d) => (
                    <option key={d} value={fmtIn(d)}>{fmtIn(d)}</option>
                  ))}
                </select>
              ) : (
                <select value={state.depth} onChange={(e) => set({ depth: e.target.value })}>
                  {[["89", "2x4"], ["140", "2x6"], ["184", "2x8"],
                    ["235", "2x10"], ["286", "2x12"], ["337", "2x14"]].map(([v, l]) => (
                    <option key={v} value={v}>{l} ({v} mm)</option>
                  ))}
                </select>
              )}
            </label>
            <label><span>Plies</span>
              <input type="number" min={1} max={12} value={state.plies}
                     onChange={(e) => set({ plies: Number(e.target.value) })} />
            </label>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Loads (specified / unfactored)</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
          UDLs are entered as an area load over a tributary width (kPa × m = kN/m).
          Point loads act at a single location along the beam — e.g. a girder
          truss or another beam framing in.
        </p>
        <table className="loads-table">
          <thead>
            <tr>
              <th>Case</th><th>Kind</th><th>Magnitude</th><th>Where</th><th></th>
            </tr>
          </thead>
          <tbody>
            {state.loads.map((l, i) => (
              <Fragment key={i}>
              <tr>
                <td style={{ width: 56 }}>
                  <select value={l.case}
                          onChange={(e) => updateLoad(i, { case: e.target.value as LoadCase })}>
                    {["D", "L", "S", "W"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td style={{ width: 68 }}>
                  <select
                    value={l.kind}
                    onChange={(e) => {
                      const kind = e.target.value as "udl" | "point";
                      // Switching kind clears the fields the other kind used,
                      // so a stale tributary can't silently ride along as an x.
                      updateLoad(i, kind === "point"
                        ? { kind, area_load_kpa: null, tributary: null, p_kn: 0, x: "" }
                        : { kind, p_kn: null, x: null, area_load_kpa: 0, tributary: "12 ft" });
                    }}
                  >
                    <option value="udl">UDL</option>
                    <option value="point">Point</option>
                  </select>
                </td>
                {l.kind === "point" ? (
                  <>
                    <td>
                      <input type="number" step="0.01" placeholder="kN"
                             value={l.p_kn ?? ""}
                             onChange={(e) => updateLoad(i, {
                               p_kn: e.target.value === "" ? null : Number(e.target.value),
                             })} />
                    </td>
                    <td>
                      <input placeholder="e.g. 6 ft" value={String(l.x ?? "")}
                             onChange={(e) => updateLoad(i, { x: e.target.value })} />
                    </td>
                  </>
                ) : (
                  <>
                    <td>
                      <input type="number" step="0.01" placeholder="kPa"
                             value={l.area_load_kpa ?? ""}
                             onChange={(e) => updateLoad(i, {
                               area_load_kpa: e.target.value === "" ? null : Number(e.target.value),
                             })} />
                    </td>
                    <td>
                      <input placeholder="12 ft (tributary)" value={String(l.tributary ?? "")}
                             onChange={(e) => updateLoad(i, { tributary: e.target.value })} />
                    </td>
                  </>
                )}
                <td style={{ width: 26 }}>
                  <button type="button" className="link"
                          onClick={() => set({ loads: state.loads.filter((_, j) => j !== i) })}>
                    ×
                  </button>
                </td>
              </tr>
              {l.kind === "udl" && (
                <tr>
                  <td />
                  <td colSpan={2} className="muted" style={{ paddingTop: 0 }}>
                    <label className="inline" style={{ margin: "2px 0" }}>
                      <input type="checkbox" checked={l.x_start != null || l.x_end != null}
                             onChange={(e) => updateLoad(i, e.target.checked
                               ? { x_start: "0", x_end: "" }
                               : { x_start: null, x_end: null })} />
                      <span style={{ marginBottom: 0 }}>only over part of the beam</span>
                    </label>
                    {(l.x_start != null || l.x_end != null) && (
                      <div className="row" style={{ marginTop: 4 }}>
                        <input placeholder="start, e.g. 0 or 3 ft" value={String(l.x_start ?? "")}
                               onChange={(e) => updateLoad(i, { x_start: e.target.value })} />
                        <input placeholder="end, e.g. 9 ft" value={String(l.x_end ?? "")}
                               onChange={(e) => updateLoad(i, { x_end: e.target.value })} />
                      </div>
                    )}
                  </td>
                  <td />
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ gap: 16 }}>
          <button type="button" className="link"
                  onClick={() => set({
                    loads: [...state.loads,
                            { case: "L", kind: "udl", area_load_kpa: 1.9, tributary: "12 ft" }],
                  })}>
            + add UDL
          </button>
          <button type="button" className="link"
                  onClick={() => set({
                    loads: [...state.loads,
                            { case: "L", kind: "point", p_kn: 5, x: "6 ft" }],
                  })}>
            + add point load
          </button>
        </div>
        <div className="inline" style={{ marginTop: 8 }}>
          <input type="checkbox" id="sw" checked={state.includeSelfWeight}
                 onChange={(e) => set({ includeSelfWeight: e.target.checked })} />
          <label htmlFor="sw" style={{ margin: 0 }}>Add beam self weight to dead load</label>
        </div>
        <div className="inline">
          <input type="checkbox" id="wind" checked={state.includeWind}
                 onChange={(e) => set({ includeWind: e.target.checked })} />
          <label htmlFor="wind" style={{ margin: 0 }}>Include wind combinations</label>
        </div>
      </div>

      <div className="panel">
        <h2>Conditions</h2>
        <div className="row">
          <label><span>Service</span>
            <select value={state.conditions.service}
                    onChange={(e) => set({ conditions: { ...state.conditions,
                      service: e.target.value as "dry" | "wet" } })}>
              <option value="dry">Dry</option><option value="wet">Wet</option>
            </select>
          </label>
          <label><span>Treatment</span>
            <select value={state.conditions.treatment}
                    onChange={(e) => set({ conditions: { ...state.conditions,
                      treatment: e.target.value as ConditionsInput["treatment"] } })}>
              <option value="none">None</option>
              <option value="preservative">Preservative</option>
              <option value="incised">Incised</option>
            </select>
          </label>
        </div>
        <label><span>Bearing length at supports</span>
          <input value={String(state.conditions.bearing_length)}
                 onChange={(e) => set({ conditions: { ...state.conditions,
                   bearing_length: e.target.value } })} />
        </label>
        <div className="inline">
          <input type="checkbox" id="lat" checked={state.conditions.laterally_supported}
                 onChange={(e) => set({ conditions: { ...state.conditions,
                   laterally_supported: e.target.checked } })} />
          <label htmlFor="lat" style={{ margin: 0 }}>
            Compression edge laterally restrained
          </label>
        </div>
        <div className="row">
          <label><span>Live deflection limit L/</span>
            <input type="number" value={state.liveRatio}
                   onChange={(e) => set({ liveRatio: Number(e.target.value) })} />
          </label>
          <label><span>Total deflection limit L/</span>
            <input type="number" value={state.totalRatio}
                   onChange={(e) => set({ totalRatio: Number(e.target.value) })} />
          </label>
          <label><span>Creep factor</span>
            <input type="number" step="0.5" min={1} max={3} value={state.creepFactor}
                   onChange={(e) => set({ creepFactor: Number(e.target.value) })} />
          </label>
        </div>
      </div>

      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Analysing…" : "Design beam"}
      </button>
    </form>
  );
}
