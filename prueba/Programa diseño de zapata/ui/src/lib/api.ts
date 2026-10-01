/**
 * Cliente de la API y tipos del contrato.
 *
 * REGLA ARQUITECTÓNICA: este archivo — y toda la UI — NO contiene ecuaciones de
 * ingeniería. Las fórmulas, sus sustituciones numéricas y sus referencias
 * normativas llegan ya resueltas desde el motor y aquí solo se tipan y muestran.
 */

export type CheckStatus = "PASS" | "INFO" | "WARNING" | "NO VERIFICADO" | "FAIL";

export interface TraceEntry {
  id: string;
  description: string;
  equation_symbolic: string;
  equation_substituted: string;
  result_value: number;
  result_unit: string;
  hypotheses: string[];
  governing_combo: string | null;
  code_name: string;
  code_reference: string;
  status: CheckStatus;
  /**
   * Componente al que pertenece la entrada cuando el resultado tiene varios:
   * "sistema" | "zap_ext" | "zap_int" | "viga". null en la zapata aislada.
   */
  scope?: string | null;
  /**
   * Pendiente abierto que impide verificar esta entrada, p.ej. "TBD-C1".
   *
   * Solo aparece cuando el estado es NO VERIFICADO PORQUE no existe criterio normativo
   * que aplicar. Su AUSENCIA en una entrada NO VERIFICADO significa lo contrario: el
   * criterio existe y falta un dato que el proyectista sí puede declarar. Confundirlas
   * le diría al usuario que no puede hacer nada cuando sí puede.
   */
  open_tbd?: string | null;
}

export interface RebarOption {
  label: string;
  bar_designation: string;
  diameter_mm: number;
  spacing_cm: number;
  n_bars: number;
  As_provided_cm2: number;
  As_required_cm2: number;
  As_min_cm2: number;
  utilization: number;
  governed_by: string;
  ld_required_mm: number | null;
  ld_available_mm: number | null;
  development_ok: boolean | null;
}

export interface Band {
  name: string;
  width_m: number;
  As_required_cm2: number;
  As_min_cm2: number;
  topped_up: boolean;
}

export interface ShortDirection {
  is_square: boolean;
  beta: number;
  gamma_s: number;
  bands: Band[];
  note: string;
  code_reference: string;
}

export interface Stability {
  sliding_status: CheckStatus;
  sliding_FS: number | null;
  sliding_FS_required: number | null;
  sliding_message: string;
  sliding_governing_combo: string | null;
  overturning_x_status: CheckStatus;
  overturning_x_FS: number | null;
  overturning_y_status: CheckStatus;
  overturning_y_FS: number | null;
  overturning_message_x: string;
  overturning_message_y: string;
  pivot_description: string;
  missing_parameters: string[];
  // FORMULACION_VOLTEO: paridad con la combinada. Opcionales porque el contrato es
  // aditivo y una respuesta anterior puede no traerlos.
  overturning_x_FS_required?: number | null;
  overturning_y_FS_required?: number | null;
  overturning_x_governing_combo?: string | null;
  overturning_y_governing_combo?: string | null;
  overturning_x_envelope_reading?: string | null;
  overturning_y_envelope_reading?: string | null;
  criterion_note?: string;
}

export interface Vec3 { x: number; y: number; z: number; }
export interface BoxOut { center: Vec3; size: Vec3; }

export interface BarOut {
  index: number;
  direction: "X" | "Y";
  layer: "inferior" | "superior";
  diameter_m: number;
  length_m: number;
  start: Vec3;
  end: Vec3;
  has_hook: boolean;
  hook_type: string;
}

export interface DimensionOut {
  id: string;
  label: string;
  start: Vec3;
  end: Vec3;
  plane: "XY" | "XZ" | "YZ";
}

export interface LayerSummaryOut {
  direction: "X" | "Y";
  layer: "inferior" | "superior";
  bar_designation: string;
  diameter_mm: number;
  spacing_cm: number;
  n_bars: number;
  bar_length_m: number;
  d_m: number;
  label: string;
}

/** Contrato unico con la visualizacion 3D. Todo llega resuelto del motor. */
export interface FootingSceneOut {
  alternative_id: string;
  status: CheckStatus;
  B_m: number;
  L_m: number;
  h_m: number;
  d_m: number;
  cover_m: number;
  footing: BoxOut;
  column: BoxOut;
  column_bx_m: number;
  column_by_m: number;
  cover_box: BoxOut;
  bars: BarOut[];
  layers: LayerSummaryOut[];
  dimensions: DimensionOut[];
  scope_note: string;
}

export interface AlternativeDetail {
  id: string;
  rank: number;
  score: number;
  status: CheckStatus;
  B_m: number;
  L_m: number;
  h_m: number;
  d_m: number;
  cover_mm: number;
  concrete_volume_m3: number;
  steel_mass_kg: number;
  footing_area_m2: number;
  excavation_volume_m3: number;
  constructive_complexity: number;
  score_breakdown: Record<string, { raw: number; normalized: number; weight: number; contribution: number }>;
  self_weight_kN: number;
  qmax_kPa: number;
  qmin_kPa: number;
  qavg_kPa: number;
  within_kern: boolean;
  ex_m: number;
  ey_m: number;
  Mu_x_kNm: number;
  Mu_y_kNm: number;
  As_req_x_cm2: number;
  As_req_y_cm2: number;
  As_min_x_cm2: number;
  As_min_y_cm2: number;
  shear_x_ratio: number;
  shear_y_ratio: number;
  punching_ratio: number;
  punching_governing_equation: string;
  punching_bo_m: number;
  punching_has_moment_transfer: boolean;
  punching_amplification: number | null;
  rebar_x_label: string;
  rebar_y_label: string;
  rebar_options_x: RebarOption[];
  rebar_options_y: RebarOption[];
  short_direction: ShortDirection | null;
  stability: Stability | null;
  scene: FootingSceneOut;
  governing_combos: Record<string, string>;
  trace: TraceEntry[];
  discard_reasons: string[];
}

export interface ComparisonRow {
  id: string;
  rank: number | null;
  B_m: number;
  L_m: number;
  h_m: number;
  d_m: number;
  steel_x: string;
  steel_y: string;
  qmax_kPa: number;
  concrete_volume_m3: number;
  steel_mass_kg: number;
  max_dimension_m: number;
  complexity: number;
  score: number | null;
  status: CheckStatus;
  in_pareto: boolean;
}

export interface DiscardGroup {
  reason: string;
  count: number;
  example_id: string;
  example_B_m: number;
  example_L_m: number;
  example_explanation: string;
}

export interface Limitation {
  id: string;
  title: string;
  kind: string;
  code_reference: string;
  description: string;
  impact: string;
  can_cause_false_pass: boolean;
  enforced_by: string | null;
}

export interface InputWarning {
  field: string;
  value: number;
  message: string;
}

export interface DesignSummary {
  project_name: string;
  n_evaluated: number;
  n_valid: number;
  n_discarded: number;
  pareto_size: number;
  elapsed_seconds: number;
  code_name: string;
  min_depth_interpretation: string;
  status_histogram: Record<string, number>;
  search_range_note: string;
  /** Geometrías que la relación L/B dejó fuera de la malla, y su explicación. */
  pruned_by_LB_ratio?: number;
  pruned_note?: string;
  /** Aviso cuando la recomendada queda pegada al límite del rango explorado. */
  search_boundary_note?: string;
  effective_search_range: Record<string, number>;
}

export interface DesignResponse {
  summary: DesignSummary;
  top: AlternativeDetail[];
  table: ComparisonRow[];
  discarded: DiscardGroup[];
  limitations: Limitation[];
  input_warnings: InputWarning[];
  pass_conditions: string[];
}

/** Fase 10B — caso de carga sin factorizar (modo por casos). */
export interface LoadCaseInput {
  name: string;
  /** CM | CV | CVi | CS | CE | CL | CT (E.060 §9.2) */
  kind: string;
  /** SERVICIO | RESISTENCIA, solo para CVi y CS */
  level: string | null;
  P_kN: number;
  Mx_kNm: number;
  My_kNm: number;
  Hx_kN: number;
  Hy_kN: number;
  description?: string;
}

/** Fase 10B — combinación como factores declarados sobre casos, por nombre. */
export interface CombinationDefinitionInput {
  name: string;
  type: "SERVICIO" | "FACTORIZADA";
  factors: Record<string, number>;
  description?: string;
}

export interface LoadCombinationInput {
  name: string;
  type: "SERVICIO" | "FACTORIZADA";
  P_kN: number;
  Mx_kNm: number;
  My_kNm: number;
  Hx_kN: number;
  Hy_kN: number;
  includes_seismic_loads: boolean;
  includes_wind_loads: boolean;
}

/**
 * Bloques de entrada compartidos por las tres tipologias. Se extraen aqui porque
 * zapata aislada, combinada y viga de conexion declaran EXACTAMENTE los mismos
 * materiales, suelo y unidades: duplicar la forma abriria la puerta a que una
 * tipologia acepte un campo que otra ignora en silencio.
 */
export interface MaterialsInput {
  fc_MPa: number;
  fy_MPa: number;
  bar_type: string;
  concrete_unit_weight_kNm3: number;
}

export interface SoilInput {
  qadm_kPa: number;
  pressure_basis: "BRUTA" | "NETA";
  gamma_kNm3: number;
  Df_m: number;
  mu_friction_soil_concrete: number | null;
  cohesion_kPa: number | null;
  FS_sliding_required: number | null;
  FS_overturning_required: number | null;
  /** E.050 art. 21 — por defecto APAGADO, debe declararlo el usuario. */
  allow_temporary_increase_30pct: boolean;
  /** E.030 art. 29 — por defecto APAGADO, debe declararlo el usuario. */
  allow_seismic_reduction_80pct: boolean;
  /** E.050 art. 26.2 — única excepción al mínimo de Df = 0,80 m. */
  founded_on_rock: boolean;
  /** E.050 art. 28 — método del área efectiva. Por defecto APAGADO. */
  use_effective_area_e050_art28: boolean;
  /** Declara que el qadm vale para las dimensiones efectivas B'×L'. */
  qadm_declared_for_effective_area: boolean;
  source_notes: string;
}

/** Unidades en que vienen los datos. La conversion la hace el motor. */
export interface UnitsInput {
  force: string;
  moment: string;
  pressure: string;
  strength: string;
  length: string;
  unit_weight: string;
}

export interface DesignRequest {
  project_name: string;
  column: { shape: string; bx_m: number; by_m: number; offset_x_m?: number; offset_y_m?: number };
  materials: MaterialsInput;
  soil: SoilInput;
  search: {
    /** null = el motor estima el limite automaticamente */
    B_min_m: number | null; B_max_m: number | null; B_step_m: number;
    L_min_m: number | null; L_max_m: number | null; L_step_m: number;
    max_LB_ratio: number;
    h_min_m: number | null; h_max_m: number | null; h_step_m: number;
    cover_override_mm: number | null;
    hook_type_x: string; hook_type_y: string;
  };
  units: UnitsInput;
  weights: {
    w_concrete_volume: number; w_steel_mass: number;
    w_max_dimension: number; w_constructive_complexity: number;
  };
  combinations: LoadCombinationInput[];
  load_cases?: LoadCaseInput[] | null;
  combination_definitions?: CombinationDefinitionInput[] | null;
  top_n: number;
  min_depth_interpretation: string;
}

export interface UnitOption {
  value: string;
  label: string;
  /**
   * Factor hacia la unidad SI del motor, tal como lo declara
   * `engine/units/unit_registry.py`. La interfaz lo usa para PRESENTAR resultados;
   * no declara ninguna equivalencia propia.
   */
  to_si: number;
}

export interface ReferenceData {
  rebar_catalog: { designation: string; diameter_mm: number; area_mm2: number }[];
  units: Record<string, UnitOption[]>;
  limitations: Limitation[];
  pass_conditions: string[];
  fs_reference: { static: number; pseudostatic: number; note: string };
  code_notes: Record<string, string>;
  /** Regla de redondeo declarada al convertir de unidad. */
  rounding_note?: string;
}

/** Tipologías que aceptan un bloque de unidades. */
export type Tipologia = "aislada" | "combinada" | "conectada" | "viga";

const BASE = "/api";

export async function fetchReference(): Promise<ReferenceData> {
  const res = await fetch(`${BASE}/reference`);
  if (!res.ok) throw new Error("No se pudo cargar la información de referencia.");
  return res.json();
}

/**
 * Cambia las unidades de una peticion SIN cambiar el valor fisico de sus datos.
 *
 * La conversion la hace el motor: la interfaz manda la peticion tal como la tiene y
 * recibe los mismos datos expresados en otras unidades (21 MPa -> 214.14 kgf/cm2).
 * Si el servidor no responde, se devuelve la peticion intacta y el llamador avisa:
 * cambiar el rotulo sin convertir el numero cambiaria el dato en silencio.
 */
export async function rewriteUnits<T extends { units: UnitsInput }>(
  typology: Tipologia,
  request: T,
  units: UnitsInput,
): Promise<T> {
  const res = await fetch(`${BASE}/units/rewrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ typology, units, request }),
  });
  if (!res.ok) {
    throw new Error(
      "No se pudieron convertir los datos a las nuevas unidades. Se mantienen las anteriores.",
    );
  }
  const data = await res.json();
  return data.request as T;
}

export async function runDesign(request: DesignRequest): Promise<DesignResponse> {
  const res = await fetch(`${BASE}/design`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    let message = `Error ${res.status}`;
    try {
      const body = await res.json();
      const d = body.detail;
      message = typeof d === "string" ? d : d?.detail ?? JSON.stringify(d);
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

/**
 * Abre la memoria de cálculo en una pestaña nueva. El HTML llega renderizado
 * desde el motor; la UI no compone ninguna parte del documento.
 */
export async function openReport(request: DesignRequest, alternativeId?: string): Promise<void> {
  const res = await fetch(`${BASE}/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, alternative_id: alternativeId ?? null }),
  });
  if (!res.ok) {
    let message = `Error ${res.status}`;
    try {
      const body = await res.json();
      const d = body.detail;
      message = typeof d === "string" ? d : d?.detail ?? JSON.stringify(d);
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(message);
  }
  const html = await res.text();
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    throw new Error(
      "El navegador bloqueó la ventana emergente. Permita las ventanas emergentes para ver la memoria."
    );
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const STATUS_ORDER: CheckStatus[] = ["PASS", "INFO", "WARNING", "NO VERIFICADO", "FAIL"];

// =========================================================================
// Zapata combinada — Fase 2
// =========================================================================

export interface CombinedColumnInput {
  label: string;
  shape: string;
  bx_m: number;
  by_m: number;
  distance_from_first_m: number;
  transverse_offset_m: number;
  combinations: LoadCombinationInput[];
  load_cases?: LoadCaseInput[] | null;
}

/** Linderos del terreno: distancia libre de la CARA de la columna al lindero. null = libre. */
export interface SiteLimitsInput {
  start_clearance_m?: number | null;
  end_clearance_m?: number | null;
  side_neg_clearance_m?: number | null;
  side_pos_clearance_m?: number | null;
}

export interface CombinedSearchInput {
  length_min_m: number | null;
  length_max_m: number | null;
  length_step_m: number;
  width_min_m: number | null;
  width_max_m: number | null;
  width_step_m: number;
  h_min_m: number;
  h_max_m: number;
  h_step_m: number;
  /** null = la posición la decide el programa (centra la resultante y respeta linderos). */
  first_column_edge_distance_m: number | null;
  longitudinal_direction: string;
  /** true = el programa estima los rangos; los de arriba se ignoran. */
  auto_ranges?: boolean;
}

export interface TopCoverInput {
  case: string | null;
  explicit_mm: number | null;
}

export interface CombinedDesignRequest {
  project_name: string;
  columns: CombinedColumnInput[];
  combination_definitions?: CombinationDefinitionInput[] | null;
  materials: MaterialsInput;
  soil: SoilInput;
  search: CombinedSearchInput;
  top_cover: TopCoverInput;
  units: UnitsInput;
  top_n: number;
  site_limits?: SiteLimitsInput | null;
}

export interface CombinedFaceOut {
  face: string;
  Mu_kNm: number;
  x_m: number;
  d_m: number;
  cover_m: number;
  As_design_cm2: number;
  min_governed_by: string;
  bar_designation: string | null;
  spacing_m: number | null;
  ld_required_m: number | null;
  ld_available_m: number | null;
  development_ok: boolean | null;
  status: string;
}

export interface CombinedPunchingOut {
  column_label: string;
  column_position: string;
  critical_section_sides: number;
  alpha_s: number;
  ratio: number;
  status: string;
}

export interface CombinedAlternativeOut {
  id: string;
  length_m: number;
  width_m: number;
  h_m: number;
  concrete_volume_m3: number;
  longitudinal_direction: string;
  M_positive_kNm: number;
  M_negative_kNm: number;
  has_top_steel: boolean;
  bottom_face: CombinedFaceOut;
  top_face: CombinedFaceOut | null;
  punching: CombinedPunchingOut[];
  stability?: CombinedStabilityOut | null;
  status: string;
}

export interface CombinedStabilityCheckOut {
  check: string;
  status: string;
  FS_obtained: number | null;
  FS_required: number | null;
  governing_combo: string | null;
  message: string;
  code_reference: string;
  missing_parameters: string[];
  envelope_reading: string | null;
}

export interface CombinedStabilityOut {
  applicable: boolean;
  status: string;
  checks: CombinedStabilityCheckOut[];
  criterion_note: string;
}

export interface CombinedComparisonRowOut {
  id: string;
  length_m: number;
  width_m: number;
  h_m: number;
  concrete_volume_m3: number;
  steel_mass_kg: number;
  footing_area_m2: number;
  max_plan_dimension_m: number;
  score: number;
  status: CheckStatus;
  /** Frente no dominado por costo; no cambia el estado. */
  in_pareto: boolean;
}

/** Fase 2 — motivo de descarte normalizado de la combinada. */
export interface CombinedDiscardExampleOut {
  length_m: number;
  width_m: number;
  h_m: number;
  texts: string[];
}

export interface CombinedDiscardGroupOut {
  category: string;
  label: string;
  aspect: string;
  status: CheckStatus;
  /** Geometrías descartadas con esta causa (una geometría puede tener varias). */
  count: number;
  /** Geometrías cuya causa principal es esta. */
  primary_count: number;
  check_ids: string[];
  elements: string[];
  code_references: string[];
  /** false: la traza degradó el estado sin que el solver escribiera un motivo. */
  has_written_reason: boolean;
  example: CombinedDiscardExampleOut | null;
}

export interface CombinedUnresolvedGroupOut {
  reason: string;
  count: number;
  example: CombinedDiscardExampleOut | null;
}

export interface CombinedDesignResponse {
  top: CombinedAlternativeOut[];
  evaluated_count: number;
  discarded_count: number;
  truncated: boolean;
  search_note: string;
  /** Aviso cuando la recomendada queda pegada al límite del rango explorado. */
  search_boundary_note?: string;
  centering_length_m: number | null;
  centering_note: string;
  axis_convention_note: string;
  // --- Integración global ---
  comparison?: CombinedComparisonRowOut[];
  pareto_objectives?: string[];
  pareto_size?: number;
  // --- Fase 2: motivos de descarte agrupados ---
  discard_groups?: CombinedDiscardGroupOut[];
  discarded_by_status?: Record<string, number>;
  unresolved_count?: number;
  unresolved_groups?: CombinedUnresolvedGroupOut[];
  // --- Decisión 6: la combinada acepta NO_FAIL; aceptada NO es conforme ---
  accepted_count?: number;
  status_summary?: Record<string, number>;
  not_verified?: string[];
  accepted_with_findings?: string[];
  accepted_and_compliant?: string[];
  not_verified_count?: number;
  accepted_with_findings_count?: number;
  accepted_and_compliant_count?: number;
  can_claim_compliance?: boolean;
  // --- Pendiente 1: esquema 2D ---
  scene?: CombinedSceneOut | null;
}

export interface CombinedColumnMarkOut {
  label: string;
  x_m: number;
  y_m: number;
  box: BoxOut;
}

export interface CombinedSceneOut {
  alternative_id: string;
  status: string;
  /** Rótulo del vocabulario único (pendiente 8). */
  status_label: string;
  status_note: string;
  longitudinal_direction: string;
  B_m: number;
  L_m: number;
  h_m: number;
  footing: BoxOut;
  columns: CombinedColumnMarkOut[];
  dimensions: DimensionOut[];
  scope_note: string;
}

export async function runCombinedDesign(
  request: CombinedDesignRequest
): Promise<CombinedDesignResponse> {
  const res = await fetch(`${BASE}/design-combined`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? `Error ${res.status}`);
  }
  return res.json();
}

export async function openCombinedReport(
  request: CombinedDesignRequest,
  alternativeId?: string
): Promise<void> {
  const res = await fetch(`${BASE}/report-combined`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, alternative_id: alternativeId ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? `Error ${res.status}`);
  }
  const html = await res.text();
  const win = window.open("", "_blank");
  if (win) {
    win.document.write(html);
    win.document.close();
  }
}

// =========================================================================
// Viga de conexión — Fase 3
// =========================================================================

export type LateralSystem =
  | "muros_estructurales"
  | "dual_tipo_I"
  | "porticos"
  | "dual_tipo_II";

export interface BeamSeismicInput {
  soil_profile: string | null;
  seismic_zone: number | null;
  part_of_lateral_force_system: boolean;
  lateral_system: LateralSystem | null;
}

export interface BeamDesignRequest {
  project_name: string;
  b_m: number;
  h_m: number;
  d_m: number;
  clear_span_m: number;
  Mu_negative_kNm: number;
  Mu_positive_kNm: number;
  Vu_kN: number;
  sum_Pu_kN: number;
  longitudinal_db_mm: number;
  stirrup_diameter_mm: number;
  n_legs: number;
  fyt_MPa: number | null;
  materials: MaterialsInput;
  soil: SoilInput;
  seismic: BeamSeismicInput;
  units: UnitsInput;
}

export interface BeamMinSteelOut {
  As_min_10_5_1_cm2: number;
  As_min_10_5_2_cm2: number;
  As_min_governing_cm2: number;
  governed_by: string;
  Mcr_kNm: number;
  fr_MPa: number;
  exempt_by_10_5_3: boolean;
  equation_substituted: string;
}

export interface BeamShearOut {
  Vu_kN: number;
  phi: number;
  Vc_kN: number;
  phi_Vc_kN: number;
  Vs_required_kN: number;
  Vs_max_kN: number;
  Vs_exceeds_limit: boolean;
  stirrups_required: boolean;
  av_min_required: boolean;
  av_min_exemption: string;
  Av_over_s_governing_cm2_m: number;
  stirrup_label: string | null;
  spacing_cm: number | null;
  spacing_limit_cm: number | null;
  spacing_limit_reference: string | null;
  status_ok: boolean;
  message: string;
  code_reference: string;
}

export interface BeamInteractionPoint {
  Pn_kN: number;
  Mn_kNm: number;
  phi: number;
  phi_Pn_kN: number;
  phi_Mn_kNm: number;
}

export interface BeamAxialFlexureOut {
  Pu_kN: number;
  Mu_kNm: number;
  Pn_max_kN: number;
  phi_Pn_max_kN: number;
  P0_tension_kN: number;
  phi_Mn_at_Pu_kNm: number | null;
  phi_at_Pu: number | null;
  /** −1 cuando el motor devolvió infinito: el punto cae fuera del diagrama. */
  demand_ratio: number;
  inside_diagram: boolean;
  axial_cap_ok: boolean;
  status_ok: boolean;
  message: string;
  equation_substituted: string;
  code_reference: string;
  diagram: BeamInteractionPoint[];
}

export interface BeamLateralRequirementsOut {
  applies: boolean;
  section: string;
  system_label: string;
  reason: string;
  disallows_10_5_3: boolean;
  positive_moment_ratio_at_joint: number | null;
  max_tension_ratio: number | null;
  min_clear_span_over_depth: number | null;
  min_width_over_depth: number | null;
  not_implemented: string[];
}

export interface BeamDesignResponse {
  project_name: string;
  b_m: number;
  h_m: number;
  d_m: number;
  clear_span_m: number;
  status: CheckStatus;
  messages: string[];
  dimension_required_mm: number;
  dimension_provided_mm: number;
  dimension_ok: boolean;
  dimension_equation: string;
  Mu_negative_kNm: number;
  Mu_positive_kNm: number;
  As_negative_cm2: number;
  As_positive_cm2: number;
  min_steel_negative: BeamMinSteelOut;
  min_steel_positive: BeamMinSteelOut;
  shear: BeamShearOut;
  confinement_limit_cm: number;
  confinement_provided_cm: number | null;
  confinement_governed_by: string;
  confinement_ok: boolean | null;
  axial_required: boolean;
  axial_N_kN: number;
  axial_trigger_note: string;
  axial_flexure_negative: BeamAxialFlexureOut | null;
  axial_flexure_positive: BeamAxialFlexureOut | null;
  lateral_requirements: BeamLateralRequirementsOut | null;
  trace: TraceEntry[];
}

export async function runBeamDesign(
  request: BeamDesignRequest
): Promise<BeamDesignResponse> {
  const res = await fetch(`${BASE}/design-beam`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? body?.detail ?? `Error ${res.status}`);
  }
  return res.json();
}

export async function openBeamReport(request: BeamDesignRequest): Promise<void> {
  const res = await fetch(`${BASE}/report-beam`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? `Error ${res.status}`);
  }
  const html = await res.text();
  const win = window.open("", "_blank");
  if (win) {
    win.document.write(html);
    win.document.close();
  }
}

// =========================================================================
// Cimentación conectada — Fase 4E
// =========================================================================
//
// VOCABULARIO ÚNICO de las tres tipologías (pendiente 8). Cuatro rótulos con cuatro
// significados que no se solapan:
//
//   RECHAZADA                   una verificación resultó FAIL, o el sistema no se pudo
//                               plantear. No es candidata.
//   NO VERIFICADA               sobrevive al barrido, pero hay un pendiente abierto o una
//                               verificación que el motor no puede demostrar
//   ACEPTADA CON OBSERVACIONES  el motor sí se pronuncia, y con reservas (WARNING)
//   CONFORME                    sin pendientes abiertos y sin observaciones
//
// «ACEPTADA» a secas ya NO se usa: significaba PASS en la aislada y WARNING en la
// conectada, y una vista común las habría confundido.
//
// La palabra «válida» NO se usa para `accepted`, ni aquí ni en los componentes: se lee
// como «correcta», y ninguna alternativa de esta tipología puede declararse correcta
// mientras TBD-C1 siga abierto.
//
// Todos los rótulos y estados llegan del servidor como CAMPOS. La UI no los deriva: si
// cada cliente calculara el suyo, acabarían divergiendo y alguno diría «cumple».

export type StatusLabel =
  | "CONFORME"
  | "ACEPTADA CON OBSERVACIONES"
  | "NO VERIFICADA"
  | "RECHAZADA";

/** @deprecated Alias del vocabulario único; se conserva por los importadores. */
export type ConnectedStatusLabel = StatusLabel;

export interface ConnectedColumnInput {
  label: string;
  shape?: "cuadrada" | "rectangular" | "circular";
  bx_m: number;
  by_m: number;
  /** Gancho del acero de ESTA zapata (2026-09-28). Nunca se asume: por defecto, barra recta. */
  hook_type_x?: "ninguno" | "90" | "180";
  hook_type_y?: "ninguno" | "90" | "180";
  combinations: LoadCombinationInput[];
  load_cases?: LoadCaseInput[] | null;
}

export interface EdgeAnchorInput {
  edge: string;
  face_clearance_m: number;
}

export interface ConnectingBeamInput {
  b_m: number;
  h_m: number;
  d_m: number;
  /**
   * TBD-C4, obligatorio. Desde 2026-09-20 el único valor admitido es SIN_APOYO:
   * APOYA_EN_SUELO se rechaza en el motor (decisión 5), porque ignorar la reacción del
   * terreno bajo la viga deja la zapata interior del lado inseguro.
   */
  support_mode: string;
  /**
   * TBD-C1 (decisión 4). Declaración del proyectista sobre E.060 §15.2.6:
   * NO_EVALUADA | DECLARADA_POR_PROYECTISTA. Sin declarar equivale a NO_EVALUADA y la
   * premisa queda NO VERIFICADA. Declararla levanta ESE bloqueo y ningún otro.
   */
  stiffness_declaration?: string | null;
  /** TBD-C5, obligatorio: EXPLICITO | EN_CARGAS_DE_COLUMNA | DESPRECIADO */
  self_weight_mode: string;
  concrete_unit_weight_kNm3?: number;
  /** Fase 9a — z_b: fondo de la viga sobre la base. Obligatoria SOLO con EXPLICITO. */
  soffit_above_base_m?: number | null;
  /**
   * TBD-C13. Factor de carga muerta del peso propio de la viga en las combinaciones
   * FACTORIZADAS del modo directo. Dato del proyectista, sin valor por defecto: sin él la
   * verificacion `beam_self_weight_mode` queda NO VERIFICADA.
   */
  self_weight_dead_load_factor?: number | null;
}

export interface ConnectedSearchInput {
  ext_long_min_m: number;
  ext_long_max_m: number;
  ext_long_step_m: number;
  ext_transv_min_m: number;
  ext_transv_max_m: number;
  ext_transv_step_m: number;
  int_long_min_m: number;
  int_long_max_m: number;
  int_long_step_m: number;
  int_transv_min_m: number;
  int_transv_max_m: number;
  int_transv_step_m: number;
  h_min_m: number;
  h_max_m: number;
  h_step_m: number;
  /** Editable. El valor por defecto es un punto de partida, no un límite del producto. */
  max_systems: number;
  /** Restricción del usuario; por defecto false — el programa no la impone. */
  same_depth_both_footings: boolean;
  /** true = el programa estima los rangos (y comparte el peralte); los manuales se ignoran. */
  auto_ranges?: boolean;
}

export interface ConnectedDesignRequest {
  project_name: string;
  combination_definitions?: CombinationDefinitionInput[] | null;
  /** Obligatorio, sin valor por defecto: ARTICULADO | CUERPO_RIGIDO */
  analysis_model: string;
  /** TBD-C11, obligatorio: EQUILIBRIO_EN_CIMENTACION | PAR_PURO_EN_ZAPATA */
  couple_transfer_mode: string;
  exterior: ConnectedColumnInput;
  interior: ConnectedColumnInput;
  anchor: EdgeAnchorInput;
  beam: ConnectingBeamInput;
  axis_distance_m: number;
  longitudinal_axis: string;
  materials: MaterialsInput;
  soil: SoilInput;
  search: ConnectedSearchInput;
  units: UnitsInput;
  top_n: number;
  /** Linderos del fondo y laterales; el del inicio es `anchor`. */
  site_limits?: SiteLimitsInput | null;
}

export interface OpenTbd {
  id: string;
  description: string;
  affected_alternatives: number;
}

export interface ConnectedAlternativeOut {
  id: string;
  exterior_B_m: number;
  exterior_L_m: number;
  exterior_h_m: number;
  interior_B_m: number;
  interior_L_m: number;
  interior_h_m: number;
  concrete_volume_m3: number;
  steel_mass_kg: number;
  system_length_m: number;
  beam_span_m: number;
  delta_P_kN: number;
  score: number;
  /** Estado que llega al informe. Hoy, siempre NO VERIFICADO. */
  overall_status: CheckStatus;
  /** De lo IMPLEMENTADO, el peor resultado. NO significa «cumple». */
  implemented_checks_status: CheckStatus;
  open_tbds: string[];
  status_label: ConnectedStatusLabel;
  // --- Fase 4G ---
  footing_area_m2?: number;
  max_plan_dimension_m?: number;
  /** Frente no dominado por COSTO. No es conformidad: sigue NO VERIFICADA. */
  in_pareto?: boolean;
}

/** Esquema del sistema conectado. Posiciones resueltas por el motor (Fase 4G). */
export interface ConnectedSceneOut {
  alternative_id: string;
  status: CheckStatus;
  status_label: ConnectedStatusLabel;
  open_tbds: string[];
  longitudinal_axis: string;
  exterior_footing: BoxOut;
  interior_footing: BoxOut;
  beam: BoxOut;
  exterior_column: BoxOut;
  interior_column: BoxOut;
  property_line_x_m: number;
  exterior_column_axis_x_m: number;
  interior_column_axis_x_m: number;
  free_span_start_x_m: number;
  free_span_end_x_m: number;
  system_length_m: number;
  dimensions: DimensionOut[];
  scope_note: string;
}

export interface ConnectedRejectionOut {
  exterior_B_m: number;
  exterior_L_m: number;
  exterior_h_m: number;
  interior_B_m: number;
  interior_L_m: number;
  interior_h_m: number;
  reason: string;
  detail: string;
}

export interface ConnectedDesignResponse {
  overall_status: CheckStatus;
  headline: string;
  /** False mientras quede un pendiente abierto. La UI no puede presentar nada como conforme. */
  can_claim_compliance: boolean;
  open_tbds: OpenTbd[];
  accepted: ConnectedAlternativeOut[];
  not_verified: string[];
  accepted_and_compliant: string[];
  rejected: ConnectedRejectionOut[];
  evaluated_count: number;
  accepted_count: number;
  not_verified_count: number;
  accepted_and_compliant_count: number;
  accepted_with_findings_count: number;
  rejected_count: number;
  rejections_by_reason: Record<string, number>;
  truncated: boolean;
  search_note: string;
  /** Aviso cuando la recomendada queda pegada al límite del rango explorado. */
  search_boundary_note?: string;
  trace: TraceEntry[];
  // --- Fase 4G ---
  /** Todas las aceptadas, en orden de costo. `accepted` sigue siendo el top_n. */
  comparison?: ConnectedAlternativeOut[];
  pareto_objectives?: string[];
  pareto_size?: number;
  scene?: ConnectedSceneOut | null;
}

/**
 * Compatibilidad modelo × reparto del par (Fase 5A, D1). Es la MISMA regla que aplica
 * el motor; aquí solo sirve para no dejar enviar una combinación que el servidor va a
 * rechazar. El servidor sigue siendo la autoridad: si esta copia divergiera, la
 * respuesta 422 lo mostraría.
 */
export function coupleModeCompatible(analysisModel: string, coupleMode: string): boolean {
  return !(analysisModel === "CUERPO_RIGIDO" && coupleMode === "PAR_PURO_EN_ZAPATA");
}

export async function runConnectedDesign(
  request: ConnectedDesignRequest
): Promise<ConnectedDesignResponse> {
  const res = await fetch(`${BASE}/design-connected`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? `Error ${res.status}`);
  }
  return res.json();
}

export async function openConnectedReport(
  request: ConnectedDesignRequest,
  alternativeId?: string
): Promise<void> {
  const res = await fetch(`${BASE}/report-connected`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, alternative_id: alternativeId ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail?.detail ?? `Error ${res.status}`);
  }
  const html = await res.text();
  const win = window.open("", "_blank");
  if (win) {
    win.document.write(html);
    win.document.close();
  }
}
