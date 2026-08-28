import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { designPost, listEndConditions, listMaterials, listSclColumnProducts } from "../../api/client";
import type {
  ConditionsInput,
  EndCondition,
  EndConditionInfo,
  Material,
  PostRequest,
  PostResponse,
  SclColumnProduct,
} from "../../api/types";

export interface PostSeed {
  member: string;
  axialD: number;
  axialS: number;
  note: string;
}

interface Props {
  seed: PostSeed | null;
  onSeedConsumed: () => void;
}

interface PostForm {
  project: string;
  member: string;
  engineer: string;
  length: string;
  axialD: number;
  axialL: number;
  axialS: number;
  family: "sawn" | "scl";
  materialKey: string;
  plyWidth: string;
  depth: string;
  plies: number;
  sclProduct: string;
  sclSizeIndex: number;
  sclBearing: "column_base" | "wood_plate";
  endD: EndCondition;
  endB: EndCondition;
  unbracedD: string;
  unbracedB: string;
  conditions: ConditionsInput;
}

const INITIAL: PostForm = {
  project: "",
  member: "P1",
  engineer: "",
  length: "9 ft",
  axialD: 7,
  axialL: 0,
  axialS: 30,
  family: "sawn",
  materialKey: "SPF-No1No2",
  plyWidth: "38",
  depth: "140",
  plies: 3,
  sclProduct: "PSL-1.8E-Column",
  sclSizeIndex: 0,
  sclBearing: "column_base",
  endD: "pinned-pinned",
  endB: "pinned-pinned",
  unbracedD: "",
  unbracedB: "",
  conditions: {
    service: "dry",
    treatment: "none",
    system: "none",
    laterally_supported: true,
    bearing_length: "89",
    bearing_at_end: false,
  },
};

function toRequest(f: PostForm): PostRequest {
  const scl = f.family === "scl";
  return {
    length: f.length,
    axial_kn: { D: f.axialD, L: f.axialL, S: f.axialS },
    material_key: f.materialKey,
    section: scl ? null : { ply_width: f.plyWidth, depth: f.depth, plies: f.plies },
    scl_product: scl ? f.sclProduct : null,
    scl_size_index: f.sclSizeIndex,
    scl_bearing: f.sclBearing,
    conditions: f.conditions,
    end_condition_d: f.endD,
    end_condition_b: f.endB,
    unbraced_d: f.unbracedD || null,
    unbraced_b: f.unbracedB || null,
    include_wind: false,
    project: f.project,
    member: f.member,
    engineer: f.engineer,
  };
}

export default function PostDesign({ seed, onSeedConsumed }: Props) {
  const [form, setForm] = useState<PostForm>(INITIAL);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [products, setProducts] = useState<SclColumnProduct[]>([]);
  const [ends, setEnds] = useState<EndConditionInfo[]>([]);
  const [result, setResult] = useState<PostResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seedNote, setSeedNote] = useState<string | null>(null);

  const set = (patch: Partial<PostForm>) => setForm({ ...form, ...patch });

  useEffect(() => {
    listMaterials().then((m) => setMaterials(m.filter((x) => x.family === "sawn")));
    listSclColumnProducts().then(setProducts).catch(() => setProducts([]));
    listEndConditions().then(setEnds).catch(() => setEnds([]));
  }, []);

  useEffect(() => {
    if (!seed) return;
    setForm((f) => ({
      ...f,
      member: seed.member,
      axialD: seed.axialD,
      axialS: seed.axialS,
      axialL: 0,
    }));
    setSeedNote(seed.note);
    setResult(null);
    onSeedConsumed();
  }, [seed, onSeedConsumed]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await designPost(toRequest(form)));
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openReport = () => {
    if (!result) return;
    const blob = new Blob([result.report_html], { type: "text/html" });
    window.open(URL.createObjectURL(blob), "_blank");
  };

  const product = products.find((p) => p.key === form.sclProduct);
  const curve = result?.capacity_curve.map((p) => ({
    length: p.length_mm / 1000,
    resistance: p.resistance_kn,
  })) ?? [];

  return (
    <div className="app">
      <div>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className="panel">
            <h2>Project</h2>
            <label><span>Project</span>
              <input value={form.project} onChange={(e) => set({ project: e.target.value })} />
            </label>
            <div className="row">
              <label><span>Member mark</span>
                <input value={form.member} onChange={(e) => set({ member: e.target.value })} />
              </label>
              <label><span>Engineer</span>
                <input value={form.engineer} onChange={(e) => set({ engineer: e.target.value })} />
              </label>
            </div>
          </div>

          <div className="panel">
            <h2>Geometry</h2>
            <label><span>Unbraced length</span>
              <input value={form.length} onChange={(e) => set({ length: e.target.value })} />
            </label>
            <div className="row">
              <label><span>End condition — depth axis</span>
                <select value={form.endD}
                        onChange={(e) => set({ endD: e.target.value as EndCondition })}>
                  {ends.map((e) => (
                    <option key={e.key} value={e.key}>{e.description} (Kₑ {e.ke})</option>
                  ))}
                </select>
              </label>
            </div>
            <label><span>End condition — width axis</span>
              <select value={form.endB}
                      onChange={(e) => set({ endB: e.target.value as EndCondition })}>
                {ends.map((e) => (
                  <option key={e.key} value={e.key}>{e.description} (Kₑ {e.ke})</option>
                ))}
              </select>
            </label>
            <div className="row">
              <label><span>Braced length, depth axis</span>
                <input placeholder="full length" value={form.unbracedD}
                       onChange={(e) => set({ unbracedD: e.target.value })} />
              </label>
              <label><span>Braced length, width axis</span>
                <input placeholder="full length" value={form.unbracedB}
                       onChange={(e) => set({ unbracedB: e.target.value })} />
              </label>
            </div>
            <p className="muted" style={{ fontSize: 11.5 }}>
              Leave braced lengths blank to use the full length. Bracing the weak axis at
              mid-height is usually the cheapest way to gain capacity.
            </p>
          </div>

          <div className="panel">
            <h2>Axial loads (specified)</h2>
            {seedNote && <div className="notice" style={{ marginBottom: 10 }}>{seedNote}</div>}
            <div className="row">
              <label><span>Dead D (kN)</span>
                <input type="number" step="0.1" value={form.axialD}
                       onChange={(e) => set({ axialD: Number(e.target.value) })} />
              </label>
              <label><span>Live L (kN)</span>
                <input type="number" step="0.1" value={form.axialL}
                       onChange={(e) => set({ axialL: Number(e.target.value) })} />
              </label>
              <label><span>Snow S (kN)</span>
                <input type="number" step="0.1" value={form.axialS}
                       onChange={(e) => set({ axialS: Number(e.target.value) })} />
              </label>
            </div>
          </div>

          <div className="panel">
            <h2>Section</h2>
            <div className="row" style={{ marginBottom: 10 }}>
              <button type="button"
                      className={form.family === "sawn" ? "seg on" : "seg"}
                      onClick={() => set({ family: "sawn" })}>
                Sawn lumber
              </button>
              <button type="button"
                      className={form.family === "scl" ? "seg on" : "seg"}
                      onClick={() => set({ family: "scl" })}>
                SCL column
              </button>
            </div>

            {form.family === "sawn" ? (
              <>
                <label><span>Material</span>
                  <select value={form.materialKey}
                          onChange={(e) => set({ materialKey: e.target.value })}>
                    {materials.map((m) => (
                      <option key={m.key} value={m.key}>{m.name}</option>
                    ))}
                  </select>
                </label>
                <div className="row">
                  <label><span>Ply width</span>
                    <input value={form.plyWidth}
                           onChange={(e) => set({ plyWidth: e.target.value })} />
                  </label>
                  <label><span>Depth</span>
                    <select value={form.depth} onChange={(e) => set({ depth: e.target.value })}>
                      {[["89", "2x4"], ["140", "2x6"], ["184", "2x8"],
                        ["235", "2x10"], ["286", "2x12"]].map(([v, l]) => (
                        <option key={v} value={v}>{l} ({v} mm)</option>
                      ))}
                    </select>
                  </label>
                  <label><span>Plies</span>
                    <input type="number" min={1} max={8} value={form.plies}
                           onChange={(e) => set({ plies: Number(e.target.value) })} />
                  </label>
                </div>
              </>
            ) : (
              <>
                <label><span>Product</span>
                  <select value={form.sclProduct}
                          onChange={(e) => set({ sclProduct: e.target.value, sclSizeIndex: 0 })}>
                    {products.map((p) => (
                      <option key={p.key} value={p.key}>{p.name}</option>
                    ))}
                  </select>
                </label>
                <div className="row">
                  <label><span>Size</span>
                    <select value={form.sclSizeIndex}
                            onChange={(e) => set({ sclSizeIndex: Number(e.target.value) })}>
                      {(product?.sizes ?? []).map((s) => (
                        <option key={s.index} value={s.index}>{s.label}</option>
                      ))}
                    </select>
                  </label>
                  <label><span>Bearing at end</span>
                    <select value={form.sclBearing}
                            onChange={(e) => set({
                              sclBearing: e.target.value as "column_base" | "wood_plate",
                            })}>
                      <option value="column_base">On column base</option>
                      <option value="wood_plate">On wood plate</option>
                    </select>
                  </label>
                </div>
                <p className="muted" style={{ fontSize: 11.5 }}>
                  SCL capacities are read from the manufacturer's published table, not
                  computed — see the note with the result.
                </p>
              </>
            )}
          </div>

          <div className="panel">
            <h2>Conditions</h2>
            <div className="row">
              <label><span>Service</span>
                <select value={form.conditions.service}
                        onChange={(e) => set({ conditions: { ...form.conditions,
                          service: e.target.value as "dry" | "wet" } })}>
                  <option value="dry">Dry</option><option value="wet">Wet</option>
                </select>
              </label>
              <label><span>Treatment</span>
                <select value={form.conditions.treatment}
                        onChange={(e) => set({ conditions: { ...form.conditions,
                          treatment: e.target.value as ConditionsInput["treatment"] } })}>
                  <option value="none">None</option>
                  <option value="preservative">Preservative</option>
                  <option value="incised">Incised</option>
                </select>
              </label>
            </div>
          </div>

          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Analysing…" : "Design post"}
          </button>
        </form>
      </div>

      <div>
        {error && <div className="err">{error}</div>}
        {!result && !error && (
          <div className="panel">
            <h2>Results</h2>
            <p className="muted">
              Enter the post on the left and press <b>Design post</b>. Sawn lumber is
              designed to CSA O86-19 Cl. 6.5.6; SCL columns are read from the Trus Joist
              published resistance tables.
            </p>
          </div>
        )}
        {result && (
          <>
            <div className={`verdict ${result.passed ? "ok" : "no"}`}>
              <div>
                <div className="big">{result.passed ? "PASS" : "FAIL"}</div>
                <div className="sub">
                  {result.label}
                  <br />
                  {result.demand_kn.toFixed(1)} kN applied vs {result.resistance_kn.toFixed(1)} kN
                  resistance · ratio {result.max_ratio.toFixed(3)} · {result.governing_combo}
                </div>
              </div>
              <button onClick={openReport}>Open calc report</button>
            </div>

            {/* The backend already emits a specific unverified-material warning,
                so no separate banner is needed here. */}
            {result.warnings.map((w, i) => <div className="warn" key={i}>{w}</div>)}

            <div className="panel">
              <h2>Design checks</h2>
              <table>
                <thead>
                  <tr>
                    <th>Check</th><th>Combination</th><th className="num">Demand</th>
                    <th className="num">Resistance</th><th className="num">Ratio</th>
                    <th style={{ width: 110 }}>Utilisation</th>
                  </tr>
                </thead>
                <tbody>
                  {result.checks.map((c, i) => (
                    <tr key={i}>
                      <td>{c.label}</td>
                      <td className="muted">{c.combo_label}</td>
                      <td className="num">{c.demand.toFixed(2)} {c.units}</td>
                      <td className="num">{c.resistance.toFixed(2)} {c.units}</td>
                      <td className={`num ${c.status === "PASS" ? "pass" : "fail"}`}>
                        {c.ratio.toFixed(3)}
                      </td>
                      <td>
                        <div className={`bar ${c.ratio > 1 ? "over" : ""}`}>
                          <i style={{ width: `${Math.min(c.ratio, 1) * 100}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <table style={{ marginTop: 10 }}>
                <tbody>
                  <tr><th style={{ width: "36%" }}>Design basis</th><td>{result.method}</td></tr>
                  <tr><th>Slenderness ratio C<sub>c</sub></th>
                      <td>{result.slenderness.toFixed(1)} about the {result.slenderness_axis} axis
                          {result.slenderness > 40 && " — approaching the limit of 50"}</td></tr>
                  <tr><th>Gross area</th>
                      <td>{(result.area_mm2 / 1000).toFixed(1)} × 10³ mm²
                          ({result.width_mm.toFixed(0)} × {result.depth_mm.toFixed(0)} mm)</td></tr>
                  {result.independent_ply_resistance_kn !== null && (
                    <tr><th>If plies unfastened</th>
                        <td>{result.independent_ply_resistance_kn.toFixed(1)} kN</td></tr>
                  )}
                </tbody>
              </table>

              {result.checks.map((c, i) => (
                <details className="check-detail" key={i}>
                  <summary>{c.label} — {c.clause}</summary>
                  <div className="formula">{c.formula}{"\n"}{c.substitution}</div>
                  {c.factors.length > 0 && (
                    <table>
                      <thead><tr><th>Factor</th><th className="num">Value</th>
                                 <th>Clause</th><th>Basis</th></tr></thead>
                      <tbody>
                        {c.factors.map((f, j) => (
                          <tr key={j}>
                            <td>{f.symbol}</td>
                            <td className="num">{f.value.toFixed(3)}</td>
                            <td className="muted">{f.clause}</td>
                            <td className="muted">{f.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {c.note && <p className="muted">{c.note}</p>}
                </details>
              ))}
            </div>

            {curve.length > 0 && (
              <div className="panel">
                <p className="chart-title">Capacity against unbraced length</p>
                <p className="chart-sub">
                  Shows how much you gain by shortening or bracing this post. The marker is
                  the design point.
                </p>
                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={curve} margin={{ top: 16, right: 26, bottom: 20, left: 4 }}>
                    <CartesianGrid stroke="#e6e9ed" />
                    <XAxis dataKey="length" type="number" tick={{ fontSize: 11 }}
                           domain={["dataMin", "dataMax"]}
                           tickFormatter={(v: number) => v.toFixed(1)}
                           label={{ value: "Unbraced length (m)", position: "insideBottom",
                                    offset: -12, style: { fontSize: 11 } }} />
                    <YAxis tick={{ fontSize: 11 }} width={68}
                           label={{ value: "Pr (kN)", angle: -90, position: "insideLeft",
                                    style: { fontSize: 11 } }} />
                    <Tooltip formatter={(v: any) => [`${Number(v ?? 0).toFixed(1)} kN`, "Resistance"]}
                             labelFormatter={(v: any) => `${Number(v ?? 0).toFixed(2)} m`}
                             contentStyle={{ fontSize: 12 }} />

                    <ReferenceLine y={result.demand_kn} stroke="#c02020" strokeDasharray="5 4"
                                   label={{ value: `demand ${result.demand_kn.toFixed(1)} kN`,
                                            position: "insideTopRight", fontSize: 11,
                                            fill: "#c02020" }} />
                    <Line type="monotone" dataKey="resistance" stroke="#1f5fa8"
                          strokeWidth={2} dot={false} isAnimationActive={false} />
                    <ReferenceDot
                      x={curve.reduce((best, p) =>
                        Math.abs(p.resistance - result.resistance_kn)
                          < Math.abs(best.resistance - result.resistance_kn) ? p : best,
                        curve[0]).length}
                      y={result.resistance_kn}
                      r={5} fill="#0a7a2a" stroke="#fff" strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
