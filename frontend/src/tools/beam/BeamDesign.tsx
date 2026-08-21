import { useCallback, useEffect, useState } from "react";
import {
  deleteProject,
  designBeam,
  listMaterials,
  listProjects,
  loadProject,
  previewBeam,
  saveProject,
} from "../../api/client";
import type {
  DesignRequest,
  DesignResponse,
  Material,
  Preview,
  ProjectSummary,
} from "../../api/types";
import Diagrams from "./Diagrams";
import InputForm, { type FormState } from "./InputForm";
import ModelPreview from "./ModelPreview";
import ProjectBar from "./ProjectBar";
import ResultsSummary from "./ResultsSummary";
import type { PostSeed } from "../post/PostDesign";

interface Props {
  onDesignPostFor: (seed: PostSeed) => void;
}

const INITIAL: FormState = {
  project: "",
  member: "B1",
  engineer: "",
  spans: ["18 ft", "12 ft"],
  supports: ["pin", "roller", "roller"],
  materialKey: "LVL-2.0E-Microllam",
  autoSize: false,
  plyWidth: '1.75"',
  depth: '14"',
  plies: 2,
  maxPlies: 6,
  loads: [
    { case: "D", kind: "udl", area_load_kpa: 0.5, tributary: "12 ft" },
    { case: "S", kind: "udl", area_load_kpa: 2.16, tributary: "12 ft" },
  ],
  conditions: {
    service: "dry",
    treatment: "none",
    system: "none",
    laterally_supported: true,
    bearing_length: "140",
    bearing_at_end: false,
  },
  liveRatio: 360,
  totalRatio: 240,
  creepFactor: 1,
  includeWind: false,
  includeSelfWeight: true,
};

function toRequest(s: FormState): DesignRequest {
  return {
    spans: s.spans,
    supports: s.supports,
    material_key: s.materialKey,
    section: s.autoSize
      ? null
      : { ply_width: s.plyWidth, depth: s.depth, plies: s.plies },
    max_plies: s.maxPlies,
    loads: s.loads.filter((l) =>
      l.kind === "point"
        ? l.p_kn != null && l.x != null && String(l.x) !== ""
        : l.area_load_kpa != null || l.line_load_kn_m != null,
    ),
    conditions: s.conditions,
    deflection_limits: {
      live_ratio: s.liveRatio,
      total_ratio: s.totalRatio,
      creep_factor: s.creepFactor,
    },
    include_wind: s.includeWind,
    include_self_weight: s.includeSelfWeight,
    project: s.project,
    member: s.member,
    engineer: s.engineer,
  };
}

/** Rebuild editable form state from a saved request payload. */
function fromRequest(r: DesignRequest): FormState {
  return {
    project: r.project ?? "",
    member: r.member ?? "",
    engineer: r.engineer ?? "",
    spans: r.spans.map(String),
    supports: r.supports,
    materialKey: r.material_key,
    autoSize: !r.section,
    plyWidth: String(r.section?.ply_width ?? '1.75"'),
    depth: String(r.section?.depth ?? '14"'),
    plies: r.section?.plies ?? 2,
    maxPlies: r.max_plies ?? 6,
    loads: r.loads ?? [],
    conditions: r.conditions ?? INITIAL.conditions,
    liveRatio: r.deflection_limits?.live_ratio ?? 360,
    totalRatio: r.deflection_limits?.total_ratio ?? 240,
    creepFactor: r.deflection_limits?.creep_factor ?? 1,
    includeWind: r.include_wind ?? false,
    includeSelfWeight: r.include_self_weight ?? true,
  };
}

export default function BeamDesign({ onDesignPostFor }: Props) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [result, setResult] = useState<DesignResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The last preview that parsed. Kept while the engineer is mid-keystroke so a
  // half-typed span shows a message instead of blanking the drawing.
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // Inputs edited since the last successful run: results on screen are stale.
  const [stale, setStale] = useState(false);

  const refreshProjects = useCallback(() => {
    listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    listMaterials().then(setMaterials).catch((e) => setError(String(e.message ?? e)));
    refreshProjects();
  }, [refreshProjects]);

  // Redraw the model shortly after typing stops. The parse runs on the server
  // so the drawing can never disagree with what the design will analyse.
  useEffect(() => {
    const id = setTimeout(() => {
      previewBeam(toRequest(form))
        .then((p) => {
          if (p.ok) {
            setPreview(p);
            setPreviewError(null);
          } else {
            setPreviewError(p.error);
          }
        })
        .catch(() => { /* keep the last good drawing */ });
    }, 250);
    return () => clearTimeout(id);
  }, [form]);

  const runDesign = async (state: FormState = form) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await designBeam(toRequest(state)));
      setStale(false);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const flash = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice(null), 4000);
  };

  const handleSave = async (name: string) => {
    try {
      await saveProject(name, toRequest(form));
      refreshProjects();
      flash(`Saved “${name}”.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleLoad = async (id: string) => {
    try {
      const project = await loadProject(id);
      const state = fromRequest(project.payload);
      setForm(state);
      flash(`Opened “${project.name}”.`);
      await runDesign(state);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id);
      refreshProjects();
      flash("Project deleted.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleImport = (payload: DesignRequest, name: string) => {
    const state = fromRequest(payload);
    setForm(state);
    flash(`Imported “${name}”. Press Design beam to run it.`);
  };

  const openReport = () => {
    if (!result) return;
    const blob = new Blob([result.report_html], { type: "text/html" });
    window.open(URL.createObjectURL(blob), "_blank");
  };

  return (
    <div className="app">
      <div>
        <ProjectBar
          projects={projects}
          currentName={form.project || form.member}
          busy={busy}
          onSave={handleSave}
          onLoad={handleLoad}
          onDelete={handleDelete}
          onImport={handleImport}
          buildPayload={() => toRequest(form)}
        />
        <InputForm
          state={form}
          materials={materials}
          busy={busy}
          onChange={(next) => { setForm(next); if (result) setStale(true); }}
          onSubmit={() => runDesign()}
        />
      </div>
      <div>
        {notice && <div className="notice">{notice}</div>}
        {error && <div className="err">{error}</div>}

        <ModelPreview
          preview={preview}
          error={previewError}
          reactions={result && !stale ? result.reactions : []}
          stale={stale}
        />

        {!result && !error && (
          <div className="panel">
            <h2>Results</h2>
            <p className="muted">
              Press <b>Design beam</b> to run every NBC 2020 load combination, check
              bending, shear, bearing and deflection to CSA O86-19, and produce a
              printable calculation report.
            </p>
          </div>
        )}
        {result && (
          <>
            <ResultsSummary
              result={result}
              onOpenReport={openReport}
              onDesignPostFor={onDesignPostFor}
              loads={result.loads}
            />
            <Diagrams
              diagrams={result.diagrams}
              supportsAtMm={result.span_positions_mm}
              spanLimits={result.span_limits}
            />
          </>
        )}
      </div>
    </div>
  );
}
