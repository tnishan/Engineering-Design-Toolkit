// Mirrors backend/api/schemas/beam.py. Keep the two in step.

export type LoadCase = "D" | "L" | "S" | "W";
export type LengthInput = string | number;

export interface LoadInput {
  case: LoadCase;
  kind: "udl" | "point";
  area_load_kpa?: number | null;
  tributary?: LengthInput | null;
  line_load_kn_m?: number | null;
  p_kn?: number | null;
  x?: LengthInput | null;
  x_start?: LengthInput | null;
  x_end?: LengthInput | null;
}

export interface ConditionsInput {
  service: "dry" | "wet";
  treatment: "none" | "preservative" | "incised";
  system: "none" | "case1" | "case2";
  laterally_supported: boolean;
  bearing_length: LengthInput;
  bearing_at_end: boolean;
}

export interface SectionInput {
  ply_width: LengthInput;
  depth: LengthInput;
  plies: number;
}

export interface CustomMaterialInput {
  name: string;
  fb_mpa: number;
  fv_mpa: number;
  fcp_mpa: number;
  e_mpa: number;
  g_mpa?: number | null;
  source: string;
  depth_ref?: LengthInput | null;
  depth_exponent?: number | null;
}

export interface DesignRequest {
  spans: LengthInput[];
  supports: ("pin" | "roller" | "fixed" | "free")[];
  material_key: string;
  custom_material?: CustomMaterialInput | null;
  section?: SectionInput | null;
  max_plies?: number;
  loads: LoadInput[];
  conditions: ConditionsInput;
  deflection_limits: { live_ratio: number; total_ratio: number; creep_factor: number };
  include_wind: boolean;
  include_self_weight: boolean;
  project: string;
  member: string;
  engineer: string;
}

export interface Factor {
  symbol: string;
  value: number;
  clause: string;
  description: string;
}

export interface Check {
  check: string;
  label: string;
  demand: number;
  resistance: number;
  units: string;
  ratio: number;
  status: "PASS" | "FAIL";
  combo_label: string;
  clause: string;
  formula: string;
  substitution: string;
  location_mm: number | null;
  note: string;
  factors: Factor[];
}

export interface Peak {
  label: string;
  x_mm: number;
  value: number;
  units: string;
  combo: string;
}

export interface SpanLimit {
  name: string;
  x_start_mm: number;
  x_end_mm: number;
  reference_length_mm: number;
  live_limit_mm: number;
  total_limit_mm: number;
}

export interface Reaction {
  x_mm: number;
  support_kind: string;
  max_kn: number;
  governing_combo: string;
  required_bearing_mm: number;
  bearing_ratio: number;
}

export interface LoadEcho {
  case: LoadCase;
  kind: "udl" | "point";
  magnitude: number;
  units: string;
  x_start_mm: number;
  x_end_mm: number;
  label: string;
  is_self_weight: boolean;
}

export interface Diagrams {
  x_mm: number[];
  shear_min_kn: number[];
  shear_max_kn: number[];
  moment_min_knm: number[];
  moment_max_knm: number[];
  deflection_live_mm: number[];
  deflection_total_mm: number[];
  governing_shear_combo: string;
  governing_moment_combo: string;
  peaks: Peak[];
}

export interface Alternative {
  label: string;
  plies: number;
  width_mm: number;
  depth_mm: number;
  max_ratio: number;
  governing_check: string;
}

export interface DesignResponse {
  passed: boolean;
  max_ratio: number;
  section_label: string;
  material_name: string;
  material_source: string;
  material_verified: boolean;
  plies: number;
  width_mm: number;
  depth_mm: number;
  checks: Check[];
  warnings: string[];
  diagrams: Diagrams;
  reactions: Reaction[];
  loads: LoadEcho[];
  span_limits: SpanLimit[];
  span_positions_mm: number[];
  length_mm: number;
  self_weight_kn_m: number;
  combos_considered: string[];
  alternatives: Alternative[];
  report_html: string;
}

export interface Material {
  key: string;
  name: string;
  family: string;
  verified: boolean;
  source: string;
  fb_mpa: number;
  fv_mpa: number;
  fcp_mpa: number;
  e_mpa: number;
  available_widths_mm: number[];
  available_depths_mm: number[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  saved_at: string;
  member: string;
  material_key: string;
  spans: string[];
}

export interface Project extends ProjectSummary {
  payload: DesignRequest;
}

// ---- Post / column design ----

export type EndCondition =
  | "pinned-pinned" | "fixed-pinned" | "fixed-fixed" | "fixed-free" | "fixed-fixed-sway";

export interface EndConditionInfo {
  key: EndCondition;
  ke: number;
  description: string;
}

export interface SclColumnSize {
  index: number;
  label: string;
  width_mm: number;
  depth_mm: number;
}

export interface SclColumnProduct {
  key: string;
  name: string;
  source: string;
  sizes: SclColumnSize[];
}

export interface PostRequest {
  length: LengthInput;
  axial_kn: Record<string, number>;
  material_key: string;
  section?: SectionInput | null;
  scl_product?: string | null;
  scl_size_index?: number;
  scl_bearing?: "column_base" | "wood_plate";
  conditions: ConditionsInput;
  end_condition_d: EndCondition;
  end_condition_b: EndCondition;
  unbraced_d?: LengthInput | null;
  unbraced_b?: LengthInput | null;
  include_wind: boolean;
  project: string;
  member: string;
  engineer: string;
}

export interface PostResponse {
  passed: boolean;
  max_ratio: number;
  label: string;
  material_name: string;
  material_source: string;
  material_verified: boolean;
  method: string;
  width_mm: number;
  depth_mm: number;
  plies: number;
  area_mm2: number;
  slenderness: number;
  slenderness_axis: string;
  demand_kn: number;
  resistance_kn: number;
  governing_combo: string;
  independent_ply_resistance_kn: number | null;
  checks: Check[];
  warnings: string[];
  capacity_curve: { length_mm: number; resistance_kn: number }[];
  report_html: string;
}

export interface SectionPreview {
  label: string;
  ply_width_mm: number;
  depth_mm: number;
  plies: number;
  width_mm: number;
  area_mm2: number;
  section_modulus_mm3: number;
  inertia_mm4: number;
  self_weight_kn_m: number;
  material_name: string;
  material_verified: boolean;
}

export interface Preview {
  ok: boolean;
  error: string;
  length_mm: number;
  span_positions_mm: number[];
  supports: string[];
  loads: LoadEcho[];
  section: SectionPreview | null;
  description: string;
  total_load_kn: number;
}

// ---- Soil: buried pipe surcharge ----

export type Orientation = "along" | "across";
export type SoilLoadType = "tracked" | "wheels" | "truck" | "custom";

export interface AxleSpecIn {
  label: string;
  load_kn: number;
  tires_per_side: 1 | 2;
  tire_width: LengthInput;
  tire_length?: LengthInput | null;
  tire_pressure_kpa?: number | null;
  dual_spacing: LengthInput;
  spacing_from_previous: LengthInput;
}

export interface TrackedMachineIn {
  weight_kn: number;
  track_length: LengthInput;
  track_width: LengthInput;
  gauge: LengthInput;
}

export interface WheelGroupIn {
  wheel_load_kn: number;
  patch_along_travel: LengthInput;
  patch_across_travel: LengthInput;
  axle_width: LengthInput;
  dual_spacing: LengthInput;
  axle_count: number;
  axle_spacing: LengthInput;
}

export interface CustomPatchIn {
  label: string;
  x: LengthInput;
  y: LengthInput;
  width_x: LengthInput;
  length_y: LengthInput;
  total_kn: number;
}

export interface CustomPointIn {
  label: string;
  x: LengthInput;
  y: LengthInput;
  load_kn: number;
}

export interface SurchargeRequest {
  load_type: SoilLoadType;
  tracked?: TrackedMachineIn | null;
  wheels?: WheelGroupIn | null;
  truck_axles: AxleSpecIn[];
  truck_axle_width: LengthInput;
  custom_patches: CustomPatchIn[];
  custom_points: CustomPointIn[];
  orientation: Orientation;
  cover: LengthInput;
  pipe_od: LengthInput;
  machine_offset: LengthInput;
  soil_unit_weight_kn_m3: number;
  poisson_ratio: number;
  dla_mode: "none" | "manual" | "aashto_depth";
  dla: number;
  spread_preset: "aashto_granular" | "aashto_other" | "custom" | "none";
  spread_factor: number;
  project: string;
  member: string;
  engineer: string;
  /**
   * Which built-in preset the axle figures came from, if any. Ignored by the
   * analysis — it exists so the preset's source, verified flag and assumptions
   * reach the report and the export, which the bare axle numbers cannot carry.
   */
  vehicle_preset_key?: string;
  vehicle_name?: string;
}

export interface SoilMethod {
  key: string;
  name: string;
  pressure_kpa: number;
  basis: string;
  verified: boolean;
  note: string;
  formula: string;
  substitution: string;
  terms: SoilTerm[];
  terms_sum_to_total: boolean;
}

export interface SoilPatch {
  label: string;
  x_m: number;
  y_m: number;
  width_x_m: number;
  length_y_m: number;
  total_kn: number;
  pressure_kpa: number;
}

export interface SoilPoint {
  label: string;
  x_m: number;
  y_m: number;
  load_kn: number;
}

export interface SoilIsoline {
  level_kpa: number;
  segments: number[][][];
}

export interface SoilBulb {
  x_m: number[];
  depth_m: number[];
  grid_kpa: number[][];
  peak_kpa: number;
  isolines: SoilIsoline[];
}

export interface SoilCrownPlan {
  x_m: number[];
  y_m: number[];
  grid_kpa: number[][];
  peak_kpa: number;
}

export interface SoilTerm {
  label: string;
  detail: string;
  value_kpa: number;
}

// ---- Vehicle presets and comparison ----

export interface AxlePreset {
  label: string;
  load_kn: number;
  tires_per_side: number;
  tire_width_m: number;
  tire_length_m: number | null;
  tire_pressure_kpa: number | null;
  dual_spacing_m: number;
  spacing_from_previous_m: number;
}

export interface VehiclePresetEntry {
  key: string;
  name: string;
  category: string;
  axles: AxlePreset[];
  axle_width_m: number;
  total_load_kn: number;
  source: string;
  verified: boolean;
  assumptions: string[];
}

export interface VehiclePresets {
  vehicles: VehiclePresetEntry[];
}


export interface VehicleSpec {
  label: string;
  load_type: "tracked" | "wheels" | "truck";
  preset_key?: string | null;
  orientation: Orientation;
  tracked?: TrackedMachineIn | null;
  wheels?: WheelGroupIn | null;
  truck_axles: AxleSpecIn[];
  truck_axle_width: LengthInput;
}

export interface VehicleComparisonRequest {
  vehicles: VehicleSpec[];
  cover: LengthInput;
  pipe_od: LengthInput;
  soil_unit_weight_kn_m3: number;
  poisson_ratio: number;
  dla_mode: "none" | "manual" | "aashto_depth";
  dla: number;
  spread_preset: "aashto_granular" | "aashto_other" | "custom" | "none";
  spread_factor: number;
}

export interface AxleDetail {
  label: string;
  load_kn: number;
  tires_per_side: number;
  /** Tyre/track width across travel, metres. */
  width_m: number;
  /** Ground contact length along travel, metres. */
  length_m: number;
  /** Centre-to-centre distance from the previous axle line (0 for the first). */
  spacing_m: number;
}

export interface VehicleResult {
  ok: boolean;
  error: string;
  label: string;
  load_type: string;
  orientation: string;
  description: string;
  total_load_kn: number;
  live_pressure_kpa: number;
  worst_offset_m: number;
  worst_offset_pressure_kpa: number;
  axle_count?: number;
  axle_width_m?: number;
  wheelbase_m?: number;
  dimensions_summary?: string;
  critical_axle?: string;
  critical_axle_contribution_kpa?: number;
  axles?: AxleDetail[];
}

export interface VehicleComparisonResponse {
  ok: boolean;
  error: string;
  results: VehicleResult[];
}

export interface OrientationComparison {
  orientation: Orientation;
  label: string;
  is_current: boolean;
  pressure_at_offset_kpa: number;
  worst_offset_m: number;
  worst_pressure_kpa: number;
}

/** One depth station carrying a series per method, keyed by method name. */
export type SoilDepthRow = Record<string, number>;

export interface SoilProfilePoint {
  depth_m: number | null;
  offset_m: number | null;
  pressure_kpa: number;
}

/** One axle line of the machine, in the machine's own travel frame. */
export interface VehicleAxle {
  index: number;
  label: string;
  load_kn: number;
  wheel_load_kn: number;
  tires_per_side: number;
  tire_width_m: number;
  contact_length_m: number;
  /**
   * The contact length was backed out of an assumed inflation pressure rather
   * than stated. Where that is true, contact_pressure_kpa just echoes the
   * assumption back — the CL-625 reports exactly 700 kPa on every axle for
   * this reason — so the diagram must label it as assumed, never as measured.
   */
  contact_length_is_derived: boolean;
  tire_pressure_kpa: number | null;
  /** null on a single tyre: there is no dual spacing, which is not a zero. */
  dual_spacing_m: number | null;
  /** null on the first axle: nothing precedes it. */
  spacing_from_previous_m: number | null;
  position_u_m: number;
  position_u_centred_m: number;
  contact_area_m2: number;
  axle_contact_area_m2: number;
  contact_pressure_kpa: number;
}

/** One contact patch positioned in the travel frame. */
export interface VehicleContact {
  /** Identical to the matching SoilPatch.label, so the two can be joined. */
  label: string;
  axle_index: number;
  side: "left" | "right";
  tyre_index: number;
  u_m: number;
  v_m: number;
  length_u_m: number;
  width_v_m: number;
  load_kn: number;
  pressure_kpa: number;
}

/**
 * The machine in its own frame: u along travel, v across it, u = 0 at the
 * wheelbase midpoint. Deliberately independent of pipe orientation so the
 * drawing checks the vehicle rather than restating the analysis.
 */
export interface VehicleGeometry {
  frame: string;
  travel_axis_note: string;
  orientation: Orientation;
  plan_mapping: string;
  load_type: SoilLoadType;
  is_tracked: boolean;
  contact_noun: string;
  axle_count: number;
  wheelbase_m: number;
  gauge_m: number;
  overall_width_m: number;
  overall_length_m: number;
  total_load_kn: number;
  contact_patch_count: number;
  total_contact_area_m2: number;
  mean_contact_pressure_kpa: number;
  axles: VehicleAxle[];
  contacts: VehicleContact[];
}

export interface SurchargeResponse {
  ok: boolean;
  error: string;
  cover_m: number;
  pipe_od_m: number;
  machine_offset_m: number;
  load_description: string;
  total_load_kn: number;
  dla: number;
  dla_basis: string;
  methods: SoilMethod[];
  live_pressure_kpa: number;
  average_over_pipe_kpa: number;
  load_per_m_kn_m: number;
  worst_offset_m: number;
  worst_offset_pressure_kpa: number;
  offset_is_worst: boolean;
  soil_pressure_kpa: number;
  live_to_dead_ratio: number;
  patches: SoilPatch[];
  points: SoilPoint[];
  axles: AxleDetail[];
  /** null for custom rectangle loads, which are not a vehicle. */
  vehicle: VehicleGeometry | null;
  depth_profile: SoilDepthRow[];
  offset_profile: SoilProfilePoint[];
  bulb: SoilBulb;
  crown_plan: SoilCrownPlan;
  orientations: OrientationComparison[];
  warnings: string[];
  report_html: string;
}

export interface SoilProjectSummary {
  id: string;
  name: string;
  saved_at: string;
  member: string;
  load_type: string;
  cover: string;
}

export interface SoilProject extends SoilProjectSummary {
  payload: SurchargeRequest;
}

export interface AxleConfigSummary {
  id: string;
  name: string;
  saved_at: string;
  axle_count: number;
  total_load_kn: number;
}

export interface AxleConfig extends AxleConfigSummary {
  truck_axles: AxleSpecIn[];
  truck_axle_width: LengthInput;
}

export interface SoilExportResponse {
  ok: boolean;
  error: string;
  /** Repo-relative, so it can be handed straight to an agent. */
  json_path: string;
  markdown_path: string;
  markdown: string;
  data: Record<string, unknown>;
}

export interface SavedVehicleSummary {
  id: string;
  name: string;
  saved_at: string;
  load_type: SoilLoadType;
  total_load_kn: number;
}

export interface SavedVehicle extends SavedVehicleSummary {
  load_type: SoilLoadType;
  tracked?: TrackedMachineIn | null;
  wheels?: WheelGroupIn | null;
  truck_axles: AxleSpecIn[];
  truck_axle_width: LengthInput;
}


