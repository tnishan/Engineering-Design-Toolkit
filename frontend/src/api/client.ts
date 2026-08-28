import type {
  AxleConfig,
  AxleConfigSummary,
  AxleSpecIn,
  DesignRequest,
  DesignResponse,
  EndConditionInfo,
  LengthInput,
  Material,
  PostRequest,
  PostResponse,
  Preview,
  Project,
  ProjectSummary,
  SavedVehicle,
  SavedVehicleSummary,
  SclColumnProduct,
  SoilProject,
  SoilProjectSummary,
  SurchargeRequest,
  SoilExportResponse,
  SurchargeResponse,
  VehicleComparisonRequest,
  VehicleComparisonResponse,
  VehiclePresets,
} from "./types";



async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((d: { loc?: string[]; msg: string }) =>
            `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
          .join("; ");
      }
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const listMaterials = () => request<Material[]>("/api/beam/materials");

export const designBeam = (payload: DesignRequest) =>
  request<DesignResponse>("/api/beam/design", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listProjects = () => request<ProjectSummary[]>("/api/projects");

export const loadProject = (id: string) =>
  request<Project>(`/api/projects/${encodeURIComponent(id)}`);

export const saveProject = (name: string, payload: DesignRequest) =>
  request<ProjectSummary>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, payload }),
  });

export const deleteProject = (id: string) =>
  request<{ status: string }>(`/api/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const listEndConditions = () =>
  request<EndConditionInfo[]>("/api/post/end-conditions");

export const listSclColumnProducts = () =>
  request<SclColumnProduct[]>("/api/post/scl-products");

export const designPost = (payload: PostRequest) =>
  request<PostResponse>("/api/post/design", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const previewBeam = (payload: DesignRequest) =>
  request<Preview>("/api/beam/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const pipeSurcharge = (payload: SurchargeRequest) =>
  request<SurchargeResponse>("/api/soil/pipe-surcharge", {
    method: "POST",
    body: JSON.stringify(payload),
  });

/**
 * Writes the analysis into the repo as .md + .json for an AI tool to read.
 * The server re-runs the analysis from this payload rather than trusting
 * numbers from the browser, so an export is always a record of a real run.
 */
export const exportSoilAnalysis = (name: string, payload: SurchargeRequest) =>
  request<SoilExportResponse>("/api/soil/export", {
    method: "POST",
    body: JSON.stringify({ name, payload }),
  });

export const listVehiclePresets = async (): Promise<VehiclePresets> => {
  const data = await request<any>("/api/soil/vehicle-presets");
  if (Array.isArray(data?.vehicles)) {
    return data as VehiclePresets;
  }
  const vehicles: any[] = [];
  if (Array.isArray(data?.tracked)) {
    for (const t of data.tracked) {
      vehicles.push({
        key: t.key,
        name: t.name,
        category: "excavator",
        axles: [{
          label: "Tracks",
          load_kn: t.weight_kn,
          tires_per_side: 1,
          tire_width_m: t.track_width_m,
          tire_length_m: t.track_length_m,
          tire_pressure_kpa: null,
          dual_spacing_m: 0,
          spacing_from_previous_m: 0,
        }],
        axle_width_m: t.gauge_m,
        total_load_kn: t.weight_kn,
        source: t.source || "",
        verified: t.verified || false,
        assumptions: t.assumptions || [],
      });
    }
  }
  if (Array.isArray(data?.trucks)) {
    for (const tr of data.trucks) {
      const total = (tr.axles || []).reduce((s: number, a: any) => s + (a.load_kn || 0), 0);
      vehicles.push({
        key: tr.key,
        name: tr.name,
        category: "truck",
        axles: tr.axles || [],
        axle_width_m: tr.axle_width_m,
        total_load_kn: total,
        source: tr.source || "",
        verified: tr.verified || false,
        assumptions: tr.assumptions || [],
      });
    }
  }
  return { vehicles };
};

export const compareVehicles = (payload: VehicleComparisonRequest) =>
  request<VehicleComparisonResponse>("/api/soil/vehicle-comparison", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listSoilProjects = () => request<SoilProjectSummary[]>("/api/projects/soil");

export const loadSoilProject = (id: string) =>
  request<SoilProject>(`/api/projects/soil/${encodeURIComponent(id)}`);

export const saveSoilProject = (name: string, payload: SurchargeRequest) =>
  request<SoilProjectSummary>("/api/projects/soil", {
    method: "POST",
    body: JSON.stringify({ name, payload }),
  });

export const deleteSoilProject = (id: string) =>
  request<{ status: string }>(`/api/projects/soil/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const listAxleConfigs = () => request<AxleConfigSummary[]>("/api/soil/axle-configs");

export const loadAxleConfig = (id: string) =>
  request<AxleConfig>(`/api/soil/axle-configs/${encodeURIComponent(id)}`);

export const saveAxleConfig = (name: string, truck_axles: AxleSpecIn[], truck_axle_width: LengthInput) =>
  request<AxleConfigSummary>("/api/soil/axle-configs", {
    method: "POST",
    body: JSON.stringify({ name, truck_axles, truck_axle_width }),
  });

export const deleteAxleConfig = (id: string) =>
  request<{ status: string }>(`/api/soil/axle-configs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const listSavedVehicles = () => request<SavedVehicleSummary[]>("/api/soil/vehicles");

export const loadSavedVehicle = (id: string) =>
  request<SavedVehicle>(`/api/soil/vehicles/${encodeURIComponent(id)}`);

export const saveSavedVehicle = (name: string, vehicle: Partial<SavedVehicle>) =>
  request<SavedVehicleSummary>("/api/soil/vehicles", {
    method: "POST",
    body: JSON.stringify({ name, ...vehicle }),
  });

export const deleteSavedVehicle = (id: string) =>
  request<{ status: string }>(`/api/soil/vehicles/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });


