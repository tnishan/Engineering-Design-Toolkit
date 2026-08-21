import { useRef, useState } from "react";
import type { DesignRequest, ProjectSummary } from "../../api/types";

interface Props {
  projects: ProjectSummary[];
  currentName: string;
  busy: boolean;
  onSave: (name: string) => void;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onImport: (payload: DesignRequest, name: string) => void;
  buildPayload: () => DesignRequest;
}

export default function ProjectBar({
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
  const fileRef = useRef<HTMLInputElement>(null);

  const effectiveName = name || currentName;

  const exportJson = () => {
    const record = { name: effectiveName || "beam", payload: buildPayload() };
    const blob = new Blob([JSON.stringify(record, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(effectiveName || "beam").replace(/[^\w.-]+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = async (file: File) => {
    try {
      const text = await file.text();
      const record = JSON.parse(text);
      const payload = record.payload ?? record;
      if (!payload?.spans || !payload?.supports) {
        throw new Error("File does not look like a saved beam project.");
      }
      onImport(payload as DesignRequest, record.name ?? file.name.replace(/\.json$/i, ""));
    } catch (e) {
      alert(`Could not import that file: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="panel project-bar">
      <h2>Project file</h2>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <label style={{ flex: 2 }}>
          <span>Save as</span>
          <input
            value={effectiveName}
            placeholder="e.g. Smith Residence B1"
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
              {projects.length ? "— select —" : "— none saved yet —"}
            </option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.member ? ` · ${p.member}` : ""} · {p.saved_at.slice(0, 10)}
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
            if (p && confirm(`Delete saved project “${p.name}”? This cannot be undone.`)) {
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
      <p className="muted" style={{ fontSize: 11.5, marginBottom: 0 }}>
        Projects save the inputs only — results are recalculated on open, so a saved
        job never carries stale numbers.
      </p>
    </div>
  );
}
