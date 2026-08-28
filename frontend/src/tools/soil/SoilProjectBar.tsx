import { useRef, useState } from "react";
import { exportSoilAnalysis } from "../../api/client";
import type { SoilProjectSummary, SurchargeRequest } from "../../api/types";

interface Props {
  projects: SoilProjectSummary[];
  currentName: string;
  busy: boolean;
  onSave: (name: string) => void;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onImport: (payload: SurchargeRequest, name: string) => void;
  buildPayload: () => SurchargeRequest;
}

export default function SoilProjectBar({
  projects,
  currentName,
  busy,
  onSave,
  onLoad,
  onDelete,
  onImport,
  buildPayload,
}: Props) {
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [aiExport, setAiExport] = useState<
    { ok: true; json: string; md: string } | { ok: false; error: string } | null
  >(null);
  const [exporting, setExporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const effectiveName = name || currentName;

  /**
   * Writes .md and .json into the repo for an AI tool to pick up. Distinct
   * from "Export .json" above, which downloads the INPUTS for reloading here.
   * This one writes the inputs, the vehicle and the full results, with units
   * and assumptions spelled out, where an agent working the workspace finds
   * it without being handed a path.
   */
  const exportForAi = async () => {
    setExporting(true);
    setAiExport(null);
    try {
      const r = await exportSoilAnalysis(
        effectiveName.trim() || "pipe-surcharge", buildPayload());
      setAiExport(r.ok
        ? { ok: true, json: r.json_path, md: r.markdown_path }
        : { ok: false, error: r.error });
    } catch (e) {
      setAiExport({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setExporting(false);
    }
  };

  const exportJson = () => {
    const record = { name: effectiveName || "pipe-surcharge", payload: buildPayload() };
    const blob = new Blob([JSON.stringify(record, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(effectiveName || "pipe-surcharge").replace(/[^\w.-]+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = async (file: File) => {
    try {
      const text = await file.text();
      const record = JSON.parse(text);
      const payload = record.payload ?? record;
      if (!payload?.load_type || !payload?.cover) {
        throw new Error("File does not look like a saved pipe surcharge project.");
      }
      onImport(payload as SurchargeRequest, record.name ?? file.name.replace(/\.json$/i, ""));
    } catch (e) {
      alert(`Could not import that file: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="panel project-bar">
      <h2>Pipe surcharge project</h2>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <label style={{ flex: 2 }}>
          <span>Save project as</span>
          <input
            value={effectiveName}
            placeholder="e.g. Trunk Main MH12-MH13"
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={busy || !effectiveName.trim()}
          onClick={() => onSave(effectiveName.trim())}
          style={{ flex: 0, whiteSpace: "nowrap" }}
        >
          Save
        </button>
      </div>

      <div className="row" style={{ alignItems: "flex-end", marginTop: 4 }}>
        <label style={{ flex: 2 }}>
          <span>Open saved project</span>
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">
              {projects.length ? "— select saved project —" : "— none saved yet —"}
            </option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.member ? ` · ${p.member}` : ""} ({p.load_type}, {p.cover} cover) · {p.saved_at.slice(0, 10)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!selected || busy}
          onClick={() => {
            onLoad(selected);
            const p = projects.find((x) => x.id === selected);
            if (p) setName(p.name);
          }}
          style={{ flex: 0 }}
        >
          Open
        </button>
        <button
          type="button"
          disabled={!selected || busy}
          onClick={() => {
            const p = projects.find((x) => x.id === selected);
            if (p && confirm(`Delete saved project "${p.name}"? This cannot be undone.`)) {
              onDelete(selected);
              setSelected("");
            }
          }}
          style={{ flex: 0 }}
        >
          Delete
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
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

      <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
        <button type="button" onClick={exportForAi} disabled={busy || exporting}
                style={{ flex: 0, whiteSpace: "nowrap" }}>
          {exporting ? "Exporting…" : "Export for AI tool"}
        </button>
        <span className="muted" style={{ fontSize: 11.5 }}>
          Writes .md + .json into the repo, with units and assumptions spelled out.
        </span>
      </div>

      {aiExport?.ok && (
        <div className="verdict ok" style={{ marginTop: 8, display: "block" }}>
          <div style={{ fontSize: 12 }}>Written into the workspace:</div>
          <code style={{ fontSize: 11.5 }}>{aiExport.md}</code><br />
          <code style={{ fontSize: 11.5 }}>{aiExport.json}</code>
        </div>
      )}
      {aiExport && !aiExport.ok && (
        <div className="err" style={{ marginTop: 8 }}>{aiExport.error}</div>
      )}

      <p className="muted" style={{ fontSize: 11.5, marginBottom: 0 }}>
        Projects save the inputs only — results are recalculated on open, so a saved
        job never carries stale numbers.
      </p>
    </div>
  );
}
