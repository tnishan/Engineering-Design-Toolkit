import type {
  DesignRequest,
  DesignResponse,
  EndConditionInfo,
  Material,
  PostRequest,
  PostResponse,
  Preview,
  Project,
  ProjectSummary,
  SclColumnProduct,
  SurchargeRequest,
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

export const listVehiclePresets = () =>
  request<VehiclePresets>("/api/soil/vehicle-presets");

export const compareVehicles = (payload: VehicleComparisonRequest) =>
  request<VehicleComparisonResponse>("/api/soil/vehicle-comparison", {
    method: "POST",
    body: JSON.stringify(payload),
  });
