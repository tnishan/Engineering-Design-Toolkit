import type { DesignResponse, LoadEcho } from "../../api/types";
import type { PostSeed } from "../post/PostDesign";

interface Props {
  result: DesignResponse;
  onOpenReport: () => void;
  onDesignPostFor: (seed: PostSeed) => void;
  loads: LoadEcho[];
}

/**
 * Split a factored envelope reaction back into specified dead and snow parts.
 *
 * The reaction is reported factored, but a post is designed from specified
 * loads. Apportioning by the share each case contributes to the total applied
 * load reproduces the unfactored pair closely enough to seed the post form,
 * which the engineer then confirms.
 */
function splitReaction(reactionKn: number, loads: LoadEcho[]) {
  const byCase = (c: string) =>
    loads.filter((l) => l.case === c)
         .reduce((sum, l) => sum + Math.abs(l.magnitude), 0);
  const dead = byCase("D");
  const snow = byCase("S") + byCase("L");
  const factored = 1.25 * dead + 1.5 * snow;
  if (factored <= 0) return { D: 0, S: 0 };
  const scale = reactionKn / factored;
  return { D: +(dead * scale).toFixed(2), S: +(snow * scale).toFixed(2) };
}

export default function ResultsSummary({ result, onOpenReport, onDesignPostFor, loads }: Props) {
  const governing = result.checks.reduce(
    (worst, c) => (c.ratio > worst.ratio ? c : worst),
    result.checks[0],
  );

  return (
    <>
      <div className={`verdict ${result.passed ? "ok" : "no"}`}>
        <div>
          <div className="big">{result.passed ? "PASS" : "FAIL"}</div>
          <div className="sub">
            {result.section_label}
            <br />
            Governing: {governing?.label} at ratio {result.max_ratio.toFixed(3)}
          </div>
        </div>
        <button onClick={onOpenReport}>Open calc report</button>
      </div>

      {!result.material_verified && (
        <div className="warn">
          <b>Unverified material properties.</b> {result.material_source}. Check every
          value against a licensed copy of CSA O86-19 before using this output.
        </div>
      )}
      {result.warnings.map((w, i) => (
        <div className="warn" key={i}>{w}</div>
      ))}

      <div className="panel">
        <h2>Design checks</h2>
        <table>
          <thead>
            <tr>
              <th>Check</th>
              <th>Combination</th>
              <th className="num">Demand</th>
              <th className="num">Resistance</th>
              <th className="num">Ratio</th>
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

        <h3>Formulas and factors</h3>
        {result.checks.map((c, i) => (
          <details className="check-detail" key={i}>
            <summary>
              {c.label} — {c.clause} — <span className={c.status === "PASS" ? "pass" : "fail"}>{c.status}</span>
            </summary>
            <div className="formula">{c.formula}{"\n"}{c.substitution}</div>
            {c.factors.length > 0 && (
              <table>
                <thead>
                  <tr><th>Factor</th><th className="num">Value</th><th>Clause</th><th>Basis</th></tr>
                </thead>
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

      <div className="panel">
        <h2>Reactions and bearing</h2>
        <table>
          <thead>
            <tr>
              <th>Support</th>
              <th>Type</th>
              <th className="num">Max reaction</th>
              <th>Governing</th>
              <th className="num">Bearing needed</th>
              <th className="num">Ratio</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {result.reactions.map((r, i) => (
              <tr key={i}>
                <td><b>{String.fromCharCode(65 + i)}</b> at {(r.x_mm / 1000).toFixed(3)} m</td>
                <td className="muted">{r.support_kind}</td>
                <td className="num">{r.max_kn.toFixed(2)} kN</td>
                <td className="muted">{r.governing_combo}</td>
                <td className="num">{r.required_bearing_mm.toFixed(0)} mm</td>
                <td className={`num ${r.bearing_ratio > 1 ? "fail" : "pass"}`}>
                  {r.bearing_ratio.toFixed(3)}
                </td>
                <td>
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      const { D, S } = splitReaction(r.max_kn, loads);
                      onDesignPostFor({
                        member: `Post at ${String.fromCharCode(65 + i)}`,
                        axialD: D,
                        axialS: S,
                        note:
                          `Seeded from support ${String.fromCharCode(65 + i)}: ` +
                          `${r.max_kn.toFixed(1)} kN factored (${r.governing_combo}), ` +
                          `split into D = ${D} kN and S = ${S} kN by load share. ` +
                          "Confirm the split before relying on it.",
                      });
                    }}
                  >
                    Design post →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ fontSize: 12 }}>
          “Bearing needed” is the length required at that support for the beam width
          shown. Self weight included: {result.self_weight_kn_m.toFixed(3)} kN/m.
          Combinations analysed: {result.combos_considered.join(" · ")}
        </p>
      </div>

      {result.alternatives.length > 0 && (
        <div className="panel">
          <h2>Sections that work</h2>
          <table>
            <thead>
              <tr><th>Section</th><th className="num">Plies</th>
                  <th className="num">Governing ratio</th><th>Governed by</th></tr>
            </thead>
            <tbody>
              {result.alternatives.map((a, i) => (
                <tr key={i}>
                  <td>{a.label}</td>
                  <td className="num">{a.plies}</td>
                  <td className="num">{a.max_ratio.toFixed(3)}</td>
                  <td className="muted">{a.governing_check}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
