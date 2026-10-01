"""DTOs de la API — contrato entre el motor y la interfaz.

PRINCIPIO ARQUITECTÓNICO (sección 18 del encargo original):
    "La interfaz NO debe contener directamente las ecuaciones de ingeniería.
     El motor de cálculo debe poder ejecutarse independientemente de la interfaz."

Por eso la UI nunca calcula nada: recibe de aquí las ecuaciones YA sustituidas,
sus referencias normativas y sus estados. Estos DTOs son deliberadamente planos y
serializables, para que el frontend solo tenga que renderizarlos.

Peso de la respuesta: devolver las ~475 alternativas válidas con su trace completo
serían megabytes. Se devuelve el trace completo SOLO para el Top-N; el resto viaja
como filas compactas para la tabla comparativa.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.domain.column import ColumnShape
from engine.domain.soil import PressureBasis
from engine.optimization.connected_generator import DEFAULT_MAX_CONNECTED_SYSTEMS


# ============================ ENTRADA ============================


class LoadCombinationInput(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., description='"SERVICIO" o "FACTORIZADA"')
    P_kN: float
    # Convención E.050 art. 28.1: Mx desplaza la resultante a lo largo de X
    # (ex = Mx/Q); My a lo largo de Y. NO es "momento alrededor del eje X".
    Mx_kNm: float = 0.0
    My_kNm: float = 0.0
    Hx_kN: float = 0.0
    Hy_kN: float = 0.0
    includes_seismic_loads: bool = False
    includes_wind_loads: bool = False
    description: str = ""


class LoadCaseInput(BaseModel):
    """Fase 10B — un caso de carga sin factorizar (modo por casos).

    Tipos de E.060 §9.2: CM, CV, CVi, CS, CE, CL, CT. `level` (SERVICIO | RESISTENCIA) es
    obligatorio para CVi y CS y no se admite en los demás."""

    name: str = Field(..., min_length=1)
    kind: str = Field(..., description="CM | CV | CVi | CS | CE | CL | CT")
    level: str | None = Field(default=None, description="SERVICIO | RESISTENCIA (solo CVi y CS)")
    P_kN: float = 0.0
    Mx_kNm: float = 0.0
    My_kNm: float = 0.0
    Hx_kN: float = 0.0
    Hy_kN: float = 0.0
    description: str = ""


class CombinationDefinitionInput(BaseModel):
    """Fase 10B — una combinación como factores declarados sobre casos, por nombre."""

    name: str = Field(..., min_length=1)
    type: str = Field(..., description='"SERVICIO" o "FACTORIZADA"')
    factors: dict[str, float] = Field(..., description="nombre de caso -> factor con signo")
    description: str = ""


class ColumnInput(BaseModel):
    shape: ColumnShape = "cuadrada"
    bx_m: float = 0.40
    by_m: float = 0.40
    # Posición de la columna sobre la zapata (Fase 1B). Desplazamiento del centroide
    # de la columna respecto del centroide de la zapata, en las unidades de longitud
    # declaradas. Cero = concéntrica, que es el comportamiento por defecto.
    # Se expresa como desplazamiento y no como coordenada porque B y L varían durante
    # el barrido de geometrías: una coordenada absoluta describiría una posición
    # relativa distinta en cada candidato.
    offset_x_m: float = 0.0
    offset_y_m: float = 0.0


class MaterialsInput(BaseModel):
    fc_MPa: float = 21.0
    fy_MPa: float = 420.0
    bar_type: str = "corrugada"
    concrete_unit_weight_kNm3: float = 24.0


class SoilInput(BaseModel):
    qadm_kPa: float = 150.0
    pressure_basis: PressureBasis = PressureBasis.BRUTA
    gamma_kNm3: float = 18.0
    Df_m: float = 1.20
    mu_friction_soil_concrete: float | None = None
    cohesion_kPa: float | None = None
    FS_sliding_required: float | None = None
    FS_overturning_required: float | None = None
    allow_temporary_increase_30pct: bool = False
    allow_seismic_reduction_80pct: bool = False
    # E.050 art. 26.2: única excepción al mínimo de 0,80 m. Por defecto FALSE, que es
    # la rama estricta: el motor no supone roca, porque suponerla relajaría un
    # requisito numérico explicito de la norma.
    founded_on_rock: bool = Field(
        default=False,
        description=(
            "Declara cimentación sobre roca. Única excepción de E.050 art. 26.2 al "
            "mínimo de Df = 0,80 m. Lo declara el profesional responsable a partir del "
            "EMS; el motor nunca lo deduce."
        ),
    )
    # E.050 art. 28: método del área efectiva. Las DOS son declaraciones del
    # proyectista y las dos están apagadas por defecto, que es la lectura
    # conservadora: sin ellas rige el núcleo central, que descarta más.
    use_effective_area_e050_art28: bool = Field(
        default=False,
        description=(
            "Habilita el método del área efectiva de E.050 art. 28.2-28.3 para las "
            "combinaciones cuya resultante caiga FUERA del núcleo central. Dentro del "
            "núcleo no cambia nada: sigue rigiendo el pico de la distribución lineal, que "
            "es el criterio más estricto."
        ),
    )
    qadm_declared_for_effective_area: bool = Field(
        default=False,
        description=(
            "Declara que el qadm aportado vale para las dimensiones EFECTIVAS B'×L' y no "
            "solo para la zapata real B×L. Sin esta declaración, un cumplimiento calculado "
            "con el área efectiva queda NO VERIFICADO: la capacidad portante de una zapata "
            "más estrecha no es la misma y el motor no puede deducirla. Solo tiene efecto "
            "con `use_effective_area_e050_art28`."
        ),
    )
    source_notes: str = ""


class UnitsInput(BaseModel):
    """Unidades en que el usuario declara sus datos.

    El motor calcula siempre en SI; la conversion ocurre en una sola capa
    (engine/units/unit_registry.py), nunca en la interfaz.
    """

    force: str = "kN"
    moment: str = "kN·m"
    pressure: str = "kPa"
    strength: str = "MPa"
    length: str = "m"
    unit_weight: str = "kN/m³"


class UnitsRewriteRequest(BaseModel):
    """Petición de cambio de unidades (2026-09-23).

    La interfaz manda la petición tal como la tiene, junto con las unidades a las que
    el usuario quiere pasar, y recibe la misma petición con los números convertidos.
    El valor FÍSICO no cambia: 21 MPa se convierten en 214,14 kgf/cm², no en 210.
    """

    typology: str = Field(description="aislada | combinada | conectada | viga")
    units: UnitsInput
    request: dict = Field(description="La petición completa de esa tipología, tal cual.")


class SearchInput(BaseModel):
    # Los limites son OPCIONALES. Si se omiten, el motor estima el rango a partir
    # de la carga de servicio y la presion admisible (heuristica de busqueda).
    B_min_m: float | None = None
    B_max_m: float | None = None
    B_step_m: float = 0.1
    L_min_m: float | None = None
    L_max_m: float | None = None
    L_step_m: float = 0.1
    max_LB_ratio: float = 2.0
    h_min_m: float | None = None
    h_max_m: float | None = None
    h_step_m: float = 0.05
    cover_override_mm: float | None = None
    hook_type_x: str = "ninguno"
    hook_type_y: str = "ninguno"


class WeightsInput(BaseModel):
    w_concrete_volume: float = 0.35
    w_steel_mass: float = 0.30
    w_max_dimension: float = 0.20
    w_constructive_complexity: float = 0.15


class DesignRequest(BaseModel):
    project_name: str = "Proyecto sin nombre"
    column: ColumnInput = Field(default_factory=ColumnInput)
    materials: MaterialsInput = Field(default_factory=MaterialsInput)
    soil: SoilInput = Field(default_factory=SoilInput)
    search: SearchInput = Field(default_factory=SearchInput)
    weights: WeightsInput = Field(default_factory=WeightsInput)
    units: UnitsInput = Field(default_factory=UnitsInput)
    combinations: list[LoadCombinationInput] = Field(
        default_factory=list, description="Modo directo. Vacío si se usa el modo por casos."
    )
    # --- Fase 10B: modo de cargas por casos (aditivo) ---
    load_cases: list[LoadCaseInput] | None = None
    combination_definitions: list[CombinationDefinitionInput] | None = None
    top_n: int = 5
    min_depth_interpretation: str = "EFFECTIVE_DEPTH"


# ============================ SALIDA ============================


class TraceEntryOut(BaseModel):
    """Una ecuación del cálculo, lista para mostrar. La UI no interpreta nada."""

    id: str
    scope: str | None = Field(
        default=None,
        description=(
            'Componente al que pertenece la entrada cuando el resultado tiene varios: '
            '"sistema", "zap_ext", "zap_int", "viga". None en la zapata aislada. La '
            'unicidad es del par (scope, id), no del id: sin el ámbito, la UI mostraría '
            'el punzonamiento de una zapata bajo el rótulo de la otra.'
        ),
    )
    description: str
    equation_symbolic: str
    equation_substituted: str
    result_value: float
    result_unit: str
    hypotheses: list[str]
    governing_combo: str | None
    code_name: str
    code_reference: str
    status: str
    open_tbd: str | None = Field(
        default=None,
        description=(
            'Pendiente abierto que impide verificar esta entrada, p.ej. "TBD-C1". '
            'Presente solo cuando el estado es NO VERIFICADO PORQUE no existe criterio '
            'normativo que aplicar. Su ausencia en una entrada NO VERIFICADO significa '
            'lo contrario: el criterio existe y falta un dato que el proyectista puede '
            'declarar. La UI necesita distinguirlas para no decirle al usuario que no '
            'puede hacer nada cuando sí puede.'
        ),
    )


class RebarOptionOut(BaseModel):
    label: str
    bar_designation: str
    diameter_mm: float
    spacing_cm: float
    n_bars: int
    As_provided_cm2: float
    As_required_cm2: float
    As_min_cm2: float
    utilization: float
    governed_by: str
    ld_required_mm: float | None
    ld_available_mm: float | None
    development_ok: bool | None


class BandOut(BaseModel):
    name: str
    width_m: float
    As_required_cm2: float
    As_min_cm2: float
    topped_up: bool


class ShortDirectionOut(BaseModel):
    is_square: bool
    beta: float
    gamma_s: float
    bands: list[BandOut]
    note: str
    code_reference: str


class StabilityOut(BaseModel):
    """Estabilidad de la zapata aislada.

    Los campos de volcamiento se ampliaron en FORMULACION_VOLTEO para que la aislada
    publique lo mismo que la combinada: el FS requerido y su procedencia, la combinación
    que gobierna y cuál de las dos lecturas de la envolvente mandó. Es un cambio ADITIVO:
    ningún campo anterior cambió de nombre ni de significado."""

    sliding_status: str
    sliding_FS: float | None
    sliding_FS_required: float | None
    sliding_message: str
    sliding_governing_combo: str | None
    overturning_x_status: str
    overturning_x_FS: float | None
    overturning_y_status: str
    overturning_y_FS: float | None
    overturning_message_x: str
    overturning_message_y: str
    pivot_description: str
    missing_parameters: list[str]
    overturning_x_FS_required: float | None = None
    overturning_y_FS_required: float | None = None
    overturning_x_governing_combo: str | None = None
    overturning_y_governing_combo: str | None = None
    overturning_x_envelope_reading: str | None = Field(
        default=None,
        description='"TOTAL" o "ESTABILIZANTE": cuál de las dos lecturas de la envolvente '
                    "gobernó el momento volcador en X.",
    )
    overturning_y_envelope_reading: str | None = None
    criterion_note: str = Field(
        default="",
        description=(
            "Criterio adoptado (D10-2b), término de excentricidad de la columna y envolvente "
            "del momento volcador. Lo escribe el motor; la UI no lo reconstruye."
        ),
    )


class Vec3Out(BaseModel):
    x: float
    y: float
    z: float


class BoxOut(BaseModel):
    center: Vec3Out
    size: Vec3Out


class BarOut(BaseModel):
    index: int
    direction: str
    layer: str
    diameter_m: float
    length_m: float
    start: Vec3Out
    end: Vec3Out
    has_hook: bool
    hook_type: str


class DimensionOut(BaseModel):
    id: str
    label: str
    start: Vec3Out
    end: Vec3Out
    plane: str


class LayerSummaryOut(BaseModel):
    direction: str
    layer: str
    bar_designation: str
    diameter_mm: float
    spacing_cm: float
    n_bars: int
    bar_length_m: float
    d_m: float
    label: str


class FootingSceneOut(BaseModel):
    """Contrato único con la visualización 3D. Todo viene resuelto del motor."""

    alternative_id: str
    status: str
    B_m: float
    L_m: float
    h_m: float
    d_m: float
    cover_m: float
    footing: BoxOut
    column: BoxOut
    column_bx_m: float
    column_by_m: float
    cover_box: BoxOut
    bars: list[BarOut]
    layers: list[LayerSummaryOut]
    dimensions: list[DimensionOut]
    scope_note: str


class AlternativeDetailOut(BaseModel):
    """Alternativa del Top-N, con todo lo necesario para la vista académica."""

    id: str
    rank: int
    score: float
    status: str

    B_m: float
    L_m: float
    h_m: float
    d_m: float
    cover_mm: float

    # Métricas
    concrete_volume_m3: float
    steel_mass_kg: float
    footing_area_m2: float
    excavation_volume_m3: float
    constructive_complexity: float
    score_breakdown: dict[str, dict[str, float]]

    # Resultados de ingeniería (valores, no ecuaciones: esas van en el trace)
    self_weight_kN: float
    qmax_kPa: float
    qmin_kPa: float
    qavg_kPa: float
    within_kern: bool
    ex_m: float
    ey_m: float

    Mu_x_kNm: float
    Mu_y_kNm: float
    As_req_x_cm2: float
    As_req_y_cm2: float
    As_min_x_cm2: float
    As_min_y_cm2: float

    shear_x_ratio: float
    shear_y_ratio: float
    punching_ratio: float
    punching_governing_equation: str
    punching_bo_m: float
    punching_has_moment_transfer: bool
    punching_amplification: float | None

    rebar_x_label: str
    rebar_y_label: str
    rebar_options_x: list[RebarOptionOut]
    rebar_options_y: list[RebarOptionOut]
    short_direction: ShortDirectionOut | None
    stability: StabilityOut | None

    scene: FootingSceneOut

    governing_combos: dict[str, str]
    trace: list[TraceEntryOut]
    discard_reasons: list[str]


class ComparisonRowOut(BaseModel):
    id: str
    rank: int | None
    B_m: float
    L_m: float
    h_m: float
    d_m: float
    steel_x: str
    steel_y: str
    qmax_kPa: float
    concrete_volume_m3: float
    steel_mass_kg: float
    max_dimension_m: float
    complexity: float
    score: float | None
    status: str
    in_pareto: bool


class DiscardGroupOut(BaseModel):
    reason: str
    count: int
    example_id: str
    example_B_m: float
    example_L_m: float
    example_explanation: str


class LimitationOut(BaseModel):
    id: str
    title: str
    kind: str
    code_reference: str
    description: str
    impact: str
    can_cause_false_pass: bool
    enforced_by: str | None


class InputWarningOut(BaseModel):
    field: str
    value: float
    message: str


class DesignSummaryOut(BaseModel):
    project_name: str
    n_evaluated: int
    n_valid: int
    n_discarded: int
    pareto_size: int
    elapsed_seconds: float
    code_name: str
    min_depth_interpretation: str
    status_histogram: dict[str, int]
    search_range_note: str = ""
    pruned_by_LB_ratio: int = Field(
        default=0,
        description=(
            "Geometrías que la relación máxima L/B dejó fuera de la malla sin evaluarlas."
        ),
    )
    pruned_note: str = Field(
        default="",
        description="Explicación de la poda por relación L/B. Vacía si no podó nada.",
    )
    search_boundary_note: str = Field(
        default="",
        description=(
            "Aviso cuando la alternativa recomendada queda pegada al límite del rango "
            "explorado: el barrido no miró más allá y puede haber algo mejor fuera. "
            "Vacío si no toca ningún límite."
        ),
    )
    effective_search_range: dict[str, float] = Field(default_factory=dict)


class DesignResponse(BaseModel):
    summary: DesignSummaryOut
    top: list[AlternativeDetailOut]
    table: list[ComparisonRowOut]
    discarded: list[DiscardGroupOut]
    limitations: list[LimitationOut]
    input_warnings: list[InputWarningOut]
    pass_conditions: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    field: str | None = None


# =========================================================================
# Zapata combinada — Fase 2
# =========================================================================


class CombinedColumnInput(BaseModel):
    """Una columna del conjunto, situada por su distancia a la PRIMERA.

    Se parametriza así y no por desplazamiento respecto del centro porque durante
    el barrido la longitud varía: lo que está fijo en el problema real es la
    separación entre ejes, no la distancia al centroide."""

    label: str = "C1"
    shape: ColumnShape = "cuadrada"
    bx_m: float = 0.50
    by_m: float = 0.50
    distance_from_first_m: float = 0.0
    transverse_offset_m: float = 0.0
    combinations: list[LoadCombinationInput] = Field(default_factory=list)
    load_cases: list[LoadCaseInput] | None = Field(default=None, description="Fase 10B, modo por casos")


class TopCoverInput(BaseModel):
    """Recubrimiento de la cara superior — E.060 §7.7.1.

    Sin valor por defecto a propósito: la tabla de §7.7.1 no da uno único para esa
    cara, porque depende de la exposición, que es un dato de proyecto."""

    case: str | None = None
    explicit_mm: float | None = None


class SiteLimitsInput(BaseModel):
    """Linderos del terreno (2026-09-28): distancia libre de la CARA de la columna al
    lindero, en la unidad de longitud de la petición. `None` = sin límite por ese lado;
    0 = columna al ras. Ver `engine/domain/site_limits.py`."""

    start_clearance_m: float | None = Field(default=None, ge=0.0)
    end_clearance_m: float | None = Field(default=None, ge=0.0)
    side_neg_clearance_m: float | None = Field(default=None, ge=0.0)
    side_pos_clearance_m: float | None = Field(default=None, ge=0.0)


class CombinedSearchInput(BaseModel):
    # 2026-09-28: los rangos son OPCIONALES. Con `auto_ranges` —o si falta alguno— los
    # estima el programa (heurística de búsqueda declarada en la respuesta).
    length_min_m: float | None = None
    length_max_m: float | None = None
    length_step_m: float = 0.20
    width_min_m: float | None = None
    width_max_m: float | None = None
    width_step_m: float = 0.20
    h_min_m: float = 0.50
    h_max_m: float = 1.20
    h_step_m: float = 0.05
    # None = la posición de la zapata la decide el programa (centra la resultante de la
    # combinación permanente y respeta los linderos).
    first_column_edge_distance_m: float | None = 0.25
    longitudinal_direction: str = "X"
    auto_ranges: bool = False


class CombinedDesignRequest(BaseModel):
    project_name: str = "Zapata combinada sin nombre"
    columns: list[CombinedColumnInput]
    # Fase 10B: definiciones comunes a todas las columnas (coherencia por construcción).
    combination_definitions: list[CombinationDefinitionInput] | None = None
    materials: MaterialsInput = Field(default_factory=MaterialsInput)
    soil: SoilInput = Field(default_factory=SoilInput)
    search: CombinedSearchInput
    top_cover: TopCoverInput = Field(default_factory=TopCoverInput)
    units: UnitsInput = Field(default_factory=UnitsInput)
    top_n: int = 5
    site_limits: SiteLimitsInput | None = None


class CombinedFaceOut(BaseModel):
    face: str
    Mu_kNm: float
    x_m: float
    d_m: float
    cover_m: float
    As_design_cm2: float
    min_governed_by: str
    bar_designation: str | None = None
    spacing_m: float | None = None
    ld_required_m: float | None = None
    ld_available_m: float | None = None
    development_ok: bool | None = None
    status: str


class CombinedPunchingOut(BaseModel):
    column_label: str
    column_position: str
    critical_section_sides: int
    alpha_s: float
    ratio: float
    status: str


class CombinedStabilityCheckOut(BaseModel):
    """Una de las tres verificaciones de estabilidad de la combinada (pendiente 7)."""

    check: str = Field(..., description='"sliding", "overturning_x" u "overturning_y"')
    status: str
    FS_obtained: float | None = None
    FS_required: float | None = None
    governing_combo: str | None = None
    message: str = ""
    code_reference: str = ""
    missing_parameters: list[str] = Field(default_factory=list)
    envelope_reading: str | None = Field(
        default=None,
        description=(
            'Solo en volcamiento: "TOTAL" o "ESTABILIZANTE", cuál de las dos lecturas de la '
            "envolvente gobernó el momento volcador."
        ),
    )


class CombinedStabilityOut(BaseModel):
    """Deslizamiento y volcamiento de la zapata combinada (pendiente 7). Sustituye la
    declaración D4 de «no implementada»."""

    applicable: bool
    status: str
    checks: list[CombinedStabilityCheckOut] = Field(default_factory=list)
    criterion_note: str = Field(
        default="",
        description="Criterio adoptado (D10-2b) y envolvente del momento volcador (opción B).",
    )


class CombinedAlternativeOut(BaseModel):
    id: str
    length_m: float
    width_m: float
    h_m: float
    # 2026-09-28: dónde quedó la zapata (SI). Con posición automática cambia por planta.
    first_column_edge_distance_m: float | None = None
    transverse_shift_m: float = 0.0
    concrete_volume_m3: float
    longitudinal_direction: str
    M_positive_kNm: float
    M_negative_kNm: float
    has_top_steel: bool
    bottom_face: CombinedFaceOut
    top_face: CombinedFaceOut | None
    punching: list[CombinedPunchingOut]
    stability: CombinedStabilityOut | None = Field(
        default=None,
        description=(
            "None cuando ninguna combinación de servicio declara fuerza horizontal: entonces el "
            "momento de las columnas queda acotado por la exigencia de núcleo central."
        ),
    )
    status: str = Field(..., description="CheckStatus crudo: el que usan los criterios")
    status_label: str = Field(
        default="",
        description=(
            "Rótulo del vocabulario único (pendiente 8): CONFORME | ACEPTADA CON OBSERVACIONES "
            "| NO VERIFICADA | RECHAZADA. Es presentación; el criterio va en `status`."
        ),
    )


class CombinedComparisonRowOut(BaseModel):
    """Fila de la tabla comparativa de la combinada (integración global)."""

    id: str
    length_m: float
    width_m: float
    h_m: float
    first_column_edge_distance_m: float | None = None
    transverse_shift_m: float = 0.0
    concrete_volume_m3: float
    steel_mass_kg: float
    footing_area_m2: float
    max_plan_dimension_m: float
    score: float
    status: str = Field(..., description="CheckStatus crudo: el que usan los criterios")
    status_label: str = Field(
        default="",
        description=(
            "Rótulo del vocabulario único (pendiente 8): CONFORME | ACEPTADA CON OBSERVACIONES "
            "| NO VERIFICADA | RECHAZADA. Es presentación; el criterio va en `status`."
        ),
    )
    in_pareto: bool = Field(
        default=False,
        description="Frente no dominado por costo. No cambia el estado de la alternativa.",
    )


class CombinedDiscardExampleOut(BaseModel):
    length_m: float
    width_m: float
    h_m: float
    texts: list[str] = Field(default_factory=list)


class CombinedDiscardGroupOut(BaseModel):
    """Fase 2. Un motivo de descarte normalizado de la combinada (no cambia ningún criterio)."""

    category: str
    label: str
    aspect: str
    status: str
    count: int = Field(..., description="Geometrías descartadas con esta causa (una puede tener varias)")
    primary_count: int = Field(..., description="Geometrías cuya causa principal es esta")
    check_ids: list[str] = Field(default_factory=list, description="Entradas de traza que la producen")
    elements: list[str] = Field(default_factory=list)
    code_references: list[str] = Field(default_factory=list)
    has_written_reason: bool = Field(
        ..., description="False si el solver degradó el estado sin escribir un motivo de descarte"
    )
    example: CombinedDiscardExampleOut | None = None


class CombinedUnresolvedGroupOut(BaseModel):
    reason: str
    count: int
    example: CombinedDiscardExampleOut | None = None


class CombinedColumnMarkOut(BaseModel):
    label: str
    x_m: float
    y_m: float
    box: BoxOut


class CombinedSceneOut(BaseModel):
    """Esquema 2D de la zapata combinada (pendiente 1). Posiciones resueltas por el motor."""

    alternative_id: str
    status: str
    status_label: str = ""
    status_note: str = ""
    longitudinal_direction: str
    B_m: float
    L_m: float
    h_m: float
    footing: BoxOut
    columns: list[CombinedColumnMarkOut]
    dimensions: list[DimensionOut]
    scope_note: str


class CombinedDesignResponse(BaseModel):
    top: list[CombinedAlternativeOut]
    evaluated_count: int
    discarded_count: int
    truncated: bool
    search_note: str
    search_boundary_note: str = Field(
        default="",
        description=(
            "Aviso cuando la alternativa recomendada queda pegada al límite del rango "
            "explorado: el barrido no miró más allá y puede haber algo mejor fuera."
        ),
    )
    centering_length_m: float | None = None
    centering_note: str = ""
    axis_convention_note: str

    # --- Integración global: paridad con aislada y conectada (campos aditivos) ---
    comparison: list[CombinedComparisonRowOut] = Field(
        default_factory=list,
        description="Todas las alternativas aceptadas, en orden de costo, con marca de Pareto.",
    )
    pareto_objectives: list[str] = Field(default_factory=list)
    pareto_size: int = 0

    # --- Fase 2: motivos de descarte agrupados (aditivo) ---
    discard_groups: list[CombinedDiscardGroupOut] = Field(default_factory=list)
    discarded_by_status: dict[str, int] = Field(default_factory=dict)
    unresolved_count: int = 0
    unresolved_groups: list[CombinedUnresolvedGroupOut] = Field(default_factory=list)

    # --- Decisión 6: la combinada acepta NO_FAIL; aceptada NO es conforme (aditivo) ---
    # Mismo desglose que la conectada, para que una vista común no tenga que inferirlo.
    # Todos los recuentos son sobre las alternativas ACEPTADAS del barrido, no sobre `top`.
    accepted_count: int = Field(
        default=0, description="Alternativas que ninguna verificación implementada descarta."
    )
    status_summary: dict[str, int] = Field(
        default_factory=dict, description="Cuántas aceptadas hay en cada estado."
    )
    not_verified: list[str] = Field(
        default_factory=list,
        description=(
            "Ids de las aceptadas NO VERIFICADAS. En la combinada la causa hoy es la "
            "estabilidad no implementada con fuerzas horizontales (D4)."
        ),
    )
    accepted_with_findings: list[str] = Field(
        default_factory=list, description="Ids de las aceptadas con alguna observación (WARNING)."
    )
    accepted_and_compliant: list[str] = Field(
        default_factory=list,
        description=(
            "Ids de las aceptadas en estado PASS o INFO: las únicas presentables como "
            "conformes. Una lista vacía es información, no un fallo del barrido."
        ),
    )
    not_verified_count: int = 0
    accepted_with_findings_count: int = 0
    accepted_and_compliant_count: int = 0
    can_claim_compliance: bool = Field(
        default=False,
        description=(
            "False cuando ninguna alternativa aceptada está en PASS o INFO. La UI no debe "
            "presentar ningún resultado como conforme cuando esto es false."
        ),
    )

    # --- Pendiente 1: esquema 2D (aditivo). Paridad con aislada y conectada ---
    scene: CombinedSceneOut | None = Field(
        default=None,
        description=(
            "Esquema de la PRIMERA alternativa del ordenamiento, la misma que encabeza "
            "`top`. None cuando el barrido no acepta ninguna."
        ),
    )


# =========================================================================
# Viga de conexión — Fase 3
# =========================================================================


class BeamSeismicInput(BaseModel):
    """Datos que deciden si aplica E.030 art. 65.1 y si aplica §21.12.3.3.

    Ninguno tiene valor por defecto que dispare requisitos: si el usuario no los
    declara, el motor lo dice en vez de suponerlos."""

    soil_profile: str | None = Field(
        default=None, description="Perfil de suelo de E.030 art. 14: S0, S1, S2, S3 o S4"
    )
    seismic_zone: int | None = Field(default=None, ge=1, le=4)
    part_of_lateral_force_system: bool = Field(
        default=False,
        description=(
            "True solo si la viga recibe FLEXIÓN de columnas del sistema resistente a "
            "fuerzas laterales. Activa §21.12.3.3, que NO aplica siempre."
        ),
    )
    lateral_system: str | None = Field(
        default=None,
        description="muros_estructurales | dual_tipo_I | porticos | dual_tipo_II",
    )


class BeamDesignRequest(BaseModel):
    """Diseño de una viga de conexión. Los momentos y el cortante son de ENTRADA:
    provienen del análisis de la estructura, no los inventa este motor."""

    project_name: str = "Viga de conexión sin nombre"

    b_m: float = Field(..., gt=0, description="Ancho de la viga")
    h_m: float = Field(..., gt=0, description="Peralte total")
    d_m: float = Field(..., gt=0, description="Peralte efectivo")
    clear_span_m: float = Field(..., gt=0, description="Luz LIBRE entre caras de columna")

    Mu_negative_kNm: float = Field(..., ge=0, description="Momento último negativo, magnitud")
    Mu_positive_kNm: float = Field(..., ge=0, description="Momento último positivo, magnitud")
    Vu_kN: float = Field(..., ge=0)

    sum_Pu_kN: float = Field(
        ..., ge=0,
        description="Carga vertical amplificada de la zapata conectada; E.030 art. 65.1 "
                    "mide sobre ella la fuerza axial mínima",
    )
    longitudinal_db_mm: float = Field(
        default=25.4, gt=0, description="Diámetro de la barra longitudinal; §21.12.3.2 lo usa"
    )
    stirrup_diameter_mm: float = 9.525
    n_legs: int = Field(default=2, ge=2)
    fyt_MPa: float | None = Field(
        default=None, description="Si se omite, se toma min(fy, 420) por §11.5.2"
    )

    materials: MaterialsInput = Field(default_factory=MaterialsInput)
    soil: SoilInput = Field(default_factory=SoilInput)
    seismic: BeamSeismicInput = Field(default_factory=BeamSeismicInput)
    units: UnitsInput = Field(default_factory=UnitsInput)


class BeamMinSteelOut(BaseModel):
    As_min_10_5_1_cm2: float
    As_min_10_5_2_cm2: float
    As_min_governing_cm2: float
    governed_by: str
    Mcr_kNm: float
    fr_MPa: float
    exempt_by_10_5_3: bool
    equation_substituted: str


class BeamShearOut(BaseModel):
    Vu_kN: float
    phi: float
    Vc_kN: float
    phi_Vc_kN: float
    Vs_required_kN: float
    Vs_max_kN: float
    Vs_exceeds_limit: bool
    stirrups_required: bool
    av_min_required: bool
    av_min_exemption: str
    Av_over_s_governing_cm2_m: float
    stirrup_label: str | None = None
    spacing_cm: float | None = None
    spacing_limit_cm: float | None = None
    spacing_limit_reference: str | None = None
    status_ok: bool
    message: str
    code_reference: str


class BeamInteractionPointOut(BaseModel):
    Pn_kN: float
    Mn_kNm: float
    phi: float
    phi_Pn_kN: float
    phi_Mn_kNm: float


class BeamAxialFlexureOut(BaseModel):
    Pu_kN: float
    Mu_kNm: float
    Pn_max_kN: float
    phi_Pn_max_kN: float
    P0_tension_kN: float
    phi_Mn_at_Pu_kNm: float | None
    phi_at_Pu: float | None
    demand_ratio: float
    inside_diagram: bool
    axial_cap_ok: bool
    status_ok: bool
    message: str
    equation_substituted: str
    code_reference: str
    diagram: list[BeamInteractionPointOut] = Field(default_factory=list)


class BeamLateralRequirementsOut(BaseModel):
    applies: bool
    section: str
    system_label: str
    reason: str
    disallows_10_5_3: bool
    positive_moment_ratio_at_joint: float | None
    max_tension_ratio: float | None
    min_clear_span_over_depth: float | None
    min_width_over_depth: float | None
    not_implemented: list[str]


class BeamDesignResponse(BaseModel):
    project_name: str
    b_m: float
    h_m: float
    d_m: float
    clear_span_m: float

    status: str
    messages: list[str]

    dimension_required_mm: float
    dimension_provided_mm: float
    dimension_ok: bool
    dimension_equation: str

    Mu_negative_kNm: float
    Mu_positive_kNm: float
    As_negative_cm2: float
    As_positive_cm2: float
    min_steel_negative: BeamMinSteelOut
    min_steel_positive: BeamMinSteelOut

    shear: BeamShearOut
    confinement_limit_cm: float
    confinement_provided_cm: float | None
    confinement_governed_by: str
    confinement_ok: bool | None

    axial_required: bool
    axial_N_kN: float
    axial_trigger_note: str
    axial_flexure_negative: BeamAxialFlexureOut | None = None
    axial_flexure_positive: BeamAxialFlexureOut | None = None

    lateral_requirements: BeamLateralRequirementsOut | None = None

    trace: list[TraceEntryOut]


# =========================================================================
# Cimentación conectada — Fase 4E
# =========================================================================
#
# VOCABULARIO CERRADO. Cuatro palabras con cuatro significados que no se solapan, y
# que esta capa NO puede difuminar:
#
#   RECHAZADA     el sistema no se pudo plantear, o una verificación resultó FAIL
#   ACEPTADA      ninguna verificación IMPLEMENTADA la descarta. Nada más.
#   NO VERIFICADA aceptada, pero con un pendiente abierto que impide pronunciarse
#   CONFORME      aceptada, sin pendientes abiertos y sin observaciones
#
# La palabra «válida» no aparece en estos DTOs, y hay un test de contrato que lo
# comprueba sobre el esquema. Todo lo que la UI necesita para no mentir viaja como
# CAMPO EXPLÍCITO: las `@property` del motor no se serializan, y confiar en ellas era
# la vía directa a que un NO VERIFICADO llegara al navegador como «una alternativa más».


class ConnectedColumnInput(BaseModel):
    label: str
    shape: ColumnShape = "cuadrada"
    bx_m: float = 0.50
    by_m: float = 0.50
    # 2026-09-28 (aditivo): gancho del acero de ESTA zapata. Nunca se asume.
    hook_type_x: Literal["ninguno", "90", "180"] = "ninguno"
    hook_type_y: Literal["ninguno", "90", "180"] = "ninguno"
    combinations: list[LoadCombinationInput] = Field(default_factory=list)
    load_cases: list[LoadCaseInput] | None = Field(default=None, description="Fase 10B, modo por casos")


class EdgeAnchorInput(BaseModel):
    """Condición de lindero de la zapata exterior.

    Se declara como borde + holgura y no como desplazamiento respecto del centro
    porque lo que permanece fijo durante el barrido es la condición de borde, no la
    distancia al centroide."""

    edge: str = Field(default="X_MIN", description="X_MIN | X_MAX | Y_MIN | Y_MAX")
    face_clearance_m: float = Field(
        default=0.0, ge=0.0,
        description="Cara de la columna al borde. Cero = al ras del lindero.",
    )


class ConnectingBeamInput(BaseModel):
    b_m: float
    h_m: float
    d_m: float
    support_mode: str = Field(
        ...,
        description=(
            "TBD-C4, OBLIGATORIO y sin valor por defecto. En esta versión el único valor "
            "admitido es SIN_APOYO: APOYA_EN_SUELO se RECHAZA por validación (decisión 5, "
            "2026-09-20), porque el motor no modela la reacción del terreno bajo la viga e "
            "ignorarla deja la zapata interior del lado inseguro."
        ),
    )
    # --- TBD-C1, decisión 4 (campo aditivo) ---
    stiffness_declaration: str | None = Field(
        default=None,
        description=(
            "TBD-C1. Declaración del proyectista sobre E.060 §15.2.6: NO_EVALUADA | "
            "DECLARADA_POR_PROYECTISTA. El artículo EXIGE evaluar la rigidez de la viga de "
            "conexión y del conjunto suelo-cimentación, pero no prescribe método ni umbral, "
            "de modo que el motor no puede responderla y solo registra quién lo hace. "
            "Declararla levanta ÚNICAMENTE ese bloqueo: no convierte el resultado en "
            "conforme. Sin declarar equivale a NO_EVALUADA."
        ),
    )
    self_weight_mode: str = Field(
        ...,
        description="TBD-C5, OBLIGATORIO: EXPLICITO | EN_CARGAS_DE_COLUMNA | DESPRECIADO.",
    )
    concrete_unit_weight_kNm3: float = 24.0
    # --- Fase 9a (campo aditivo) ---
    soffit_above_base_m: float | None = Field(
        default=None,
        description=(
            "z_b: altura del FONDO de la viga sobre la base de cimentación, en la unidad de "
            "longitud de la petición. OBLIGATORIA con EXPLICITO y sin valor por defecto; no "
            "se admite con los otros dos modos."
        ),
    )
    # --- TBD-C13 A′ (campo aditivo) ---
    self_weight_dead_load_factor: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "TBD-C13. Factor de CARGA MUERTA del peso propio de la viga en las combinaciones "
            "FACTORIZADAS del MODO DIRECTO. Dato del proyectista, sin valor por defecto: el "
            "motor no puede inferirlo de una combinación ya formada. Sin él, la verificación "
            "`beam_self_weight_mode` queda NO VERIFICADA. No se usa en el modo por casos."
        ),
    )


class ConnectedSearchInput(BaseModel):
    """Rangos del barrido. Las dos zapatas se barren por separado."""

    # 2026-09-28: OPCIONALES. Con `auto_ranges` —o si falta alguno— los estima el
    # programa, comparte peralte entre las dos zapatas y ajusta el tope al tamaño de la
    # malla, para no truncar (se declara en la respuesta).
    ext_long_min_m: float | None = None
    ext_long_max_m: float | None = None
    ext_long_step_m: float = 0.20
    ext_transv_min_m: float | None = None
    ext_transv_max_m: float | None = None
    ext_transv_step_m: float = 0.20

    int_long_min_m: float | None = None
    int_long_max_m: float | None = None
    int_long_step_m: float = 0.20
    int_transv_min_m: float | None = None
    int_transv_max_m: float | None = None
    int_transv_step_m: float = 0.20
    auto_ranges: bool = False

    h_min_m: float = 0.50
    h_max_m: float = 1.20
    h_step_m: float = 0.10

    max_systems: int = Field(
        default=DEFAULT_MAX_CONNECTED_SYSTEMS, gt=0,
        description=(
            "Tope de ternas a evaluar. EDITABLE: el valor por defecto es un punto de "
            "partida, no un límite del producto. Al alcanzarlo la respuesta trae "
            "`truncated=true` y `search_note` con la advertencia — nunca en silencio."
        ),
    )
    same_depth_both_footings: bool = Field(
        default=False,
        description=(
            "Si es true, las dos zapatas comparten peralte. Es una RESTRICCIÓN del "
            "usuario y puede dejar fuera el óptimo: por eso el valor por defecto es "
            "false y el programa no lo impone."
        ),
    )


class ConnectedDesignRequest(BaseModel):
    project_name: str = "Cimentación conectada sin nombre"
    # Fase 10B: definiciones comunes a las dos columnas en el modo por casos.
    combination_definitions: list[CombinationDefinitionInput] | None = None

    analysis_model: str = Field(
        ...,
        description=(
            "OBLIGATORIO, sin valor por defecto: ARTICULADO | CUERPO_RIGIDO. Ninguna "
            "norma dice cuál corresponde; lo elige el proyectista y queda registrado."
        ),
    )
    couple_transfer_mode: str = Field(
        ...,
        description="TBD-C11, OBLIGATORIO: EQUILIBRIO_EN_CIMENTACION | PAR_PURO_EN_ZAPATA.",
    )

    exterior: ConnectedColumnInput
    interior: ConnectedColumnInput
    anchor: EdgeAnchorInput = Field(default_factory=EdgeAnchorInput)
    beam: ConnectingBeamInput
    axis_distance_m: float = Field(..., gt=0)
    longitudinal_axis: str = "X"

    materials: MaterialsInput = Field(default_factory=MaterialsInput)
    soil: SoilInput = Field(default_factory=SoilInput)
    search: ConnectedSearchInput
    units: UnitsInput = Field(default_factory=UnitsInput)
    top_n: int = 5
    # 2026-09-28: linderos del fondo y laterales (el del inicio lo da `anchor`).
    site_limits: SiteLimitsInput | None = None


class OpenTbdOut(BaseModel):
    """Un pendiente abierto. NO es una verificación que haya salido mal."""

    id: str
    description: str
    affected_alternatives: int


class ConnectedAlternativeOut(BaseModel):
    id: str
    exterior_B_m: float
    exterior_L_m: float
    exterior_h_m: float
    interior_B_m: float
    interior_L_m: float
    interior_h_m: float
    concrete_volume_m3: float
    steel_mass_kg: float
    system_length_m: float
    beam_span_m: float
    delta_P_kN: float
    score: float

    overall_status: str = Field(
        ..., description="Estado que llega al informe. Hoy, siempre NO VERIFICADO."
    )
    implemented_checks_status: str = Field(
        ...,
        description=(
            "Peor estado de las verificaciones IMPLEMENTADAS, ignorando los pendientes. "
            "NO significa «cumple»: puede ser PASS y la alternativa seguir sin poder "
            "informarse como conforme."
        ),
    )
    open_tbds: list[str] = Field(
        default_factory=list,
        description="Pendientes que impiden pronunciarse sobre esta alternativa.",
    )
    status_label: str = Field(
        ...,
        description=(
            "Rótulo del vocabulario cerrado: RECHAZADA | ACEPTADA | NO VERIFICADA | "
            "CONFORME. Lo calcula el motor, no la UI: dejar que cada cliente lo derive "
            "es como acaban divergiendo."
        ),
    )

    # --- Fase 4G: comparación entre alternativas (campos aditivos) -----------
    footing_area_m2: float = Field(default=0.0, description="Área de apoyo de las dos zapatas")
    max_plan_dimension_m: float = Field(
        default=0.0, description="Dimensión máxima en planta del sistema"
    )
    in_pareto: bool = Field(
        default=False,
        description=(
            "¿Pertenece al frente no dominado según `pareto_objectives`? Es un criterio de "
            "COSTO, no de conformidad: una alternativa del frente sigue NO VERIFICADA."
        ),
    )


class ConnectedSceneOut(BaseModel):
    """Esquema del sistema conectado (Fase 4G). Posiciones resueltas por el motor."""

    alternative_id: str
    status: str
    status_label: str
    open_tbds: list[str] = Field(default_factory=list)
    longitudinal_axis: str
    exterior_footing: BoxOut
    interior_footing: BoxOut
    beam: BoxOut
    exterior_column: BoxOut
    interior_column: BoxOut
    property_line_x_m: float
    exterior_column_axis_x_m: float
    interior_column_axis_x_m: float
    free_span_start_x_m: float
    free_span_end_x_m: float
    system_length_m: float
    dimensions: list[DimensionOut]
    scope_note: str


class ConnectedRejectionOut(BaseModel):
    exterior_B_m: float
    exterior_L_m: float
    exterior_h_m: float
    interior_B_m: float
    interior_L_m: float
    interior_h_m: float
    reason: str = Field(
        ..., description="GEOMETRIA_IMPOSIBLE | DESPEGUE | CARGA_NETA_ASCENDENTE | ENTRADA_INVALIDA | NO_CUMPLE"
    )
    detail: str = ""


class ConnectedDesignResponse(BaseModel):
    """Las cuatro categorías, cada una con su recuento propio y explícito."""

    overall_status: str = Field(
        ...,
        description=(
            "Estado del conjunto: el mejor que alcanza alguna alternativa aceptada, o "
            "FAIL si no hay ninguna."
        ),
    )
    headline: str = Field(
        ...,
        description=(
            "Titular ya redactado por el motor. Nunca afirma que algo cumpla si "
            "`accepted_and_compliant_count` es cero."
        ),
    )
    can_claim_compliance: bool = Field(
        ...,
        description=(
            "False mientras quede un pendiente abierto. La UI NO debe presentar ningún "
            "resultado como conforme cuando esto es false."
        ),
    )
    open_tbds: list[OpenTbdOut] = Field(default_factory=list)

    accepted: list[ConnectedAlternativeOut] = Field(
        default_factory=list,
        description="Las `top_n` mejores por costo. Aceptada no es conforme.",
    )
    not_verified: list[str] = Field(
        default_factory=list,
        description="Ids de las aceptadas que están NO VERIFICADAS. Hoy, todas.",
    )
    accepted_and_compliant: list[str] = Field(
        default_factory=list,
        description=(
            "Ids de las aceptadas sin pendientes ni observaciones: las únicas "
            "presentables como conformes. Vacío mientras TBD-C1 siga abierto, y que lo "
            "esté es el resultado correcto, no un fallo."
        ),
    )
    rejected: list[ConnectedRejectionOut] = Field(default_factory=list)

    evaluated_count: int = 0
    accepted_count: int = 0
    not_verified_count: int = 0
    accepted_and_compliant_count: int = 0
    accepted_with_findings_count: int = 0
    rejected_count: int = 0
    rejections_by_reason: dict[str, int] = Field(default_factory=dict)

    truncated: bool = False
    search_note: str = ""
    search_boundary_note: str = Field(
        default="",
        description=(
            "Aviso cuando la alternativa recomendada queda pegada al límite del rango "
            "explorado: el barrido no miró más allá y puede haber algo mejor fuera."
        ),
    )

    trace: list[TraceEntryOut] = Field(
        default_factory=list,
        description=(
            "Traza de la mejor alternativa por costo, con `scope` y `open_tbd`. Es lo "
            "que permite a la UI señalar qué entradas son huecos normativos y cuáles "
            "datos que el proyectista aún puede declarar."
        ),
    )

    # --- Fase 4G: paridad de presentación (campos aditivos) ------------------
    comparison: list[ConnectedAlternativeOut] = Field(
        default_factory=list,
        description=(
            "TODAS las alternativas aceptadas, en orden de costo, con la marca de Pareto. "
            "`accepted` sigue siendo el top_n."
        ),
    )
    pareto_objectives: list[str] = Field(default_factory=list)
    pareto_size: int = 0
    scene: ConnectedSceneOut | None = Field(
        default=None, description="Esquema de la mejor alternativa por costo"
    )
