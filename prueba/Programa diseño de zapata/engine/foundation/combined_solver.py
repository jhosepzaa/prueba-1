"""Solver de zapata combinada — Fase 2.

E.060 §15.10.1 remite a "los requisitos de diseño apropiados de esta Norma". Este
módulo COMPONE esos requisitos; no introduce ecuaciones propias:

  - Momento en cualquier sección .......... §15.4.1, vía `analysis/beam_diagram.py`
  - Diseño de la sección a flexión ........ §10.2, vía `foundation/flexure.py`
  - Acero mínimo repartido en dos caras ... §10.5.4, vía `reinforcement/face_reinforcement.py`
  - Cortante unidireccional ............... ec. 11-3, vía `foundation/shear_oneway.py`
  - Punzonamiento por columna ............. §11.12, vía `foundation/punching_shear.py` (Fase 1C)
  - Presión de contacto ................... §15.2, vía `soil/contact_pressure.py`
  - Proporción de la zapata ............... E.050 art. 23.3

§15.10.2 prohíbe el Método Directo del Capítulo 13; no se usa.

LO QUE ES CRITERIO Y NO NORMA
=============================
El ancho de la franja transversal bajo cada columna. §15.4.4 reparte el acero de
la dirección corta de una zapata RECTANGULAR AISLADA, y no fija ancho de franja
para una zapata de varias columnas; §15.4 no lo cubre. El ancho «ancho de columna
más d/2 a cada lado» proviene de los apuntes de Aragón y se aplica **como criterio
de modelación declarado**, nunca como exigencia normativa.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.analysis.beam_diagram import (
    BeamDiagram,
    PointLoad,
    build_beam_diagram,
    critical_one_way_shear,
)
from engine.beam.beam_shear import BeamShearResult
from engine.foundation.depth_solver import (
    effective_qadm,
    seismic_reduction_unavailable,
    seismic_reduction_unavailable_note,
    soil_actions,
)
from engine.foundation.combined_stability import (
    HYPOTHESES as STABILITY_HYPOTHESES,
    SEISMIC_HYPOTHESES as STABILITY_SEISMIC_HYPOTHESES,
    CombinedStabilityResult,
    check_combined_stability,
)
from engine.codes.base import IConcreteCode
from engine.codes.peru.e050_soils import (
    SHALLOW_FOUNDATION_EXCEEDED_NOTE,
    SHALLOW_FOUNDATION_READING,
    SHAPE_RATIO_EXCEEDED_NOTE,
    SHAPE_RATIO_READING,
    check_shallow_foundation,
    check_shape_ratio,
)
from engine.domain.combined_layout import (
    ColumnOnFooting,
    CombinedFootingLayout,
)
from engine.domain.loads import LoadCombination
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.flexure import design_flexure
from engine.foundation.punching_shear import (
    PUNCHING_FAILURE_DESCRIPTIONS,
    PunchingShearResult,
    check_punching_shear,
)
from engine.foundation.self_weight import compute_self_weight
from engine.soil.contact_pressure import (
    EFFECTIVE_AREA_CANNOT_AFFIRM_NOTE,
    contact_pressure_equation_symbolic,
)
from engine.foundation.shear_oneway import (
    ShearOneWayResult,
    check_shear_oneway,
    shear_force_at_d_from_face,
)
from engine.reinforcement.face_reinforcement import (
    TWO_FACE_MIN_REFERENCE,
    FaceRebar,
    TopCoverDeclaration,
    select_face_rebar,
    two_face_minimum,
)
from engine.results.calculation_trace import CalculationTrace, CalculationTraceEntry
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import ContactPressureModel, ContactPressureResult
from engine.soil.eccentricity import AXIS_CONVENTION_NOTE, compute_total_eccentricity
from engine.soil.foundation_depth import check_foundation_depth
from engine.soil.pressure_basis import convert_pressure

# CRITERIO DE MODELACIÓN, no norma. Ver el encabezado del módulo.
#
# C-V — CERRADA el 2026-09-20 (decisión 6). El criterio adoptado es el que ya estaba, y lo
# que se cierra es su ESTATUTO: deja de ser un pendiente ambiguo y pasa a ser un límite de
# alcance declarado. `Vn = Vc + Vs` no se implementa como parche; admitirlo es una decisión
# de ingeniería nueva, con sus tres preguntas normativas previas sin resolver (ramas y
# separación transversal, alcance de §11.12.3 y sección crítica de §15.5.2).
#
# Lo que esto obliga a decir, y que la nota de abajo dice: el resultado NO es una
# verificación completa del modelo de cortante de E.060. Es más estricto que la norma, de
# modo que ninguna geometría se acepta por error —solo se pierden algunas por exceso de
# rigor—, pero presentarlo como «cumple E.060 §11» sería afirmar de más.
CONCRETE_ONLY_SHEAR_CRITERION = (
    "Criterio del programa (C-V), CERRADO el 2026-09-20: el cortante longitudinal de la zapata "
    "combinada se verifica con la resistencia del CONCRETO SOLO; si Vu > φVc la verificación es "
    "FAIL. NO ES UNA VERIFICACIÓN COMPLETA DEL MODELO DE CORTANTE DE E.060: la norma admite "
    "Vn = Vc + Vs —§11.12.1.1 remite a §11.1–11.5 y §11.12.3 admite refuerzo de cortante en "
    "zapatas—, y el aporte de estribos queda FUERA DEL ALCANCE de esta versión. El criterio es "
    "más estricto que la norma: puede descartar geometrías que E.060 admitiría con refuerzo, "
    "pero no puede aceptar ninguna que no cumpla. Ampliarlo a Vn = Vc + Vs es una decisión de "
    "ingeniería abierta, no un pendiente de implementación "
    "(docs/auditoria_cv_cortante_longitudinal_combinada.md)."
)

ENVELOPE_DESIGN_NOTE = (
    "ENVOLVENTE DE COMBINACIONES. Cada efecto longitudinal se diseña para SU combinación "
    "factorizada más desfavorable, que puede no ser la misma: el momento positivo (cara "
    "inferior), el negativo (cara superior) y el cortante se toman cada uno de la "
    "combinación que lo hace máximo. E.060 §9.2 da la resistencia requerida «como mínimo» "
    "para cada combinación, y §9.1 exige φRn ≥ Ru en todas; tomar los tres efectos de una "
    "sola combinación puede dejar sin cubrir el que gobierna otra."
)

TRANSVERSE_SHEAR_NOTE = (
    "CORTANTE UNIDIRECCIONAL TRANSVERSAL. E.060 §15.5.1 remite al §11.12, y §11.12.1.1 "
    "describe el comportamiento COMO VIGA ANCHA: «Cada sección crítica que debe "
    "investigarse se extiende en un plano a través del ancho total del elemento». Por eso "
    "el ancho resistente es la LONGITUD COMPLETA de la zapata en ese plano —no el ancho de "
    "la franja transversal, que es un criterio de reparto del acero y no una sección "
    "resistente— y Vu se obtiene integrando la presión sobre toda el área que queda fuera "
    "de la sección crítica. La sección crítica está a d de la cara de la columna "
    "(§15.5.2, que remite a las secciones de §15.4.2)."
)

TRANSVERSE_SHEAR_PRESSURE_NOTE = (
    "La presión es la NETA FACTORIZADA de la resultante de todas las columnas, reducida al "
    "centroide de la zapata con el término P_i·offset_i de cada carga descentrada: la misma "
    "reducción que usa la presión de contacto. No se usa la presión de franja "
    "P_columna/(ancho_franja·dim), que es un criterio de reparto tomado de los apuntes y no "
    "describe el campo real bajo el plano crítico."
)

TRANSVERSE_SHEAR_SECTION_NOTE = (
    "Con varias columnas, el plano crítico que gobierna es el que deja MÁS área fuera de "
    "él, es decir el de la columna con el voladizo transversal mayor. Se evalúan los dos "
    "lados de cada columna y todas las combinaciones factorizadas, y manda el peor Vu."
)

TRANSVERSE_STRIP_EXTENSION_FACTOR = 0.5
TRANSVERSE_STRIP_NOTE = (
    "Ancho de la franja transversal = ancho de columna + d/2 a cada lado. Es un CRITERIO DE "
    "MODELACIÓN tomado de los apuntes de Aragón, «Concreto Armado 2» §3.5, NO una exigencia "
    "normativa: E.060 §15.4 no fija ancho de franja para zapatas de varias columnas, y §15.4.4 "
    "solo cubre el reparto en la dirección corta de una zapata rectangular AISLADA."
)


class FaceDesign(BaseModel):
    """Diseño a flexión de una cara en la dirección longitudinal."""

    face: str
    Mu_kNm: float
    x_m: float = Field(..., description="Sección donde actúa el momento de diseño")
    width_m: float
    d_m: float
    cover_m: float
    As_required_m2: float
    As_min_m2: float
    As_design_m2: float
    min_governed_by: str
    rebar: "FaceRebar | None" = None
    status: CheckStatus
    note: str


class CombinedDiscardRecord(BaseModel):
    """Fase 2. Qué verificación produjo un motivo de descarte de la combinada.

    Va alineado 1:1 con `discard_reasons` (mismo orden). El texto no cambia: es la categoría
    global que agrupan la API, los informes y los golden cases. Aquí se añade lo que el texto
    no dice de forma estable: la entrada de traza, el elemento (cara o columna) y el aspecto
    concreto que falló. Todos los campos son texto: no alteran el congelamiento."""

    check_id: str = Field(..., description="id de la entrada de traza que motiva el descarte")
    aspect: str = Field(..., description="aspecto concreto: seccion, longitud_desarrollo, ...")
    element: str | None = Field(default=None, description="cara o columna afectada")
    text: str = Field(..., description="el motivo de descarte, idéntico a discard_reasons")


class TransverseStrip(BaseModel):
    """Franja transversal bajo una columna."""

    column_label: str
    strip_width_m: float
    cantilever_m: float
    Mu_kNm: float
    As_required_m2: float
    As_min_m2: float
    As_design_m2: float
    rebar: "FaceRebar | None" = None
    status: CheckStatus
    criterion_note: str


class CombinedFootingResult(BaseModel):
    B_m: float
    L_m: float
    h_m: float
    d_bottom_m: float
    d_top_m: float
    longitudinal_direction: str

    shape_ratio: float
    shape_ok: bool

    contact_pressure: ContactPressureResult
    contact_combo: str
    diagram: BeamDiagram
    diagram_combo: str

    bottom_face: FaceDesign
    top_face: FaceDesign | None = Field(
        default=None, description="None si el diagrama no produce momento negativo"
    )
    transverse_strips: list[TransverseStrip]
    shear_longitudinal: ShearOneWayResult
    shear_reinforcement: "BeamShearResult | None" = Field(
        default=None,
        description=(
            "SIEMPRE None (C-V). La combinada verifica el cortante longitudinal con el concreto "
            "solo y no dimensiona refuerzo de cortante. El campo se conserva por compatibilidad "
            "del contrato; ver CONCRETE_ONLY_SHEAR_CRITERION."
        ),
    )
    punching: list[PunchingShearResult]
    stability: "CombinedStabilityResult | None" = Field(
        default=None,
        description=(
            "Pendiente 7: deslizamiento y volcamiento de la zapata combinada. None cuando "
            "ninguna combinación de servicio declara fuerza horizontal; entonces el momento de "
            "las columnas queda acotado por la exigencia de núcleo central de la presión de "
            "contacto y no se añade ninguna entrada."
        ),
    )

    overall_status: CheckStatus
    discard_reasons: list[str]
    discard_records: list[CombinedDiscardRecord] = Field(
        default_factory=list,
        description="Fase 2: verificación, aspecto y elemento de cada motivo de discard_reasons",
    )
    trace: CalculationTrace


def _combo_by_name(col: ColumnOnFooting, name: str, factored: bool) -> LoadCombination | None:
    fuente = col.loads.factored if factored else col.loads.service
    for c in fuente:
        if c.name == name:
            return c
    return None


def _diagram_for(
    layout: CombinedFootingLayout, combo_name: str, factored: bool
) -> BeamDiagram | None:
    """Diagrama de una combinación concreta. Devuelve None si la combinación no
    existe como factorizada/servicio en las columnas."""
    direccion = layout.longitudinal_direction
    cargas: list[PointLoad] = []
    for col in layout.columns:
        combo = _combo_by_name(col, combo_name, factored)
        if combo is None:
            return None
        # El momento que flexiona EN la dirección analizada: Mx si es X, My si es Y
        # (convención E.050 art. 28.1).
        M = combo.Mx_kNm if direccion == "X" else combo.My_kNm
        cargas.append(
            PointLoad(
                label=col.label,
                position_m=layout.longitudinal_position_m(col),
                P_kN=combo.P_kN,
                M_kNm=M,
                width_m=layout.column_width_along(col, direccion),
            )
        )
    return build_beam_diagram(
        layout.longitudinal_length_m, layout.transverse_width_m, cargas
    )


def solve_combined_footing(
    layout: CombinedFootingLayout,
    h_m: float,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    top_cover: TopCoverDeclaration,
    assumed_bar_diameter_mm: float = 16.0,
) -> CombinedFootingResult:
    """Verifica una zapata combinada de geometría dada.

    `top_cover` es obligatorio y sin valor por defecto: la tabla de E.060 §7.7.1 no
    da un recubrimiento único para la cara superior."""
    trace = CalculationTrace()
    discard_reasons: list[str] = []
    discard_records: list[CombinedDiscardRecord] = []

    def descartar(check_id: str, aspect: str, element: str | None, texto: str) -> None:
        """Añade el motivo (texto sin cambios) y registra de qué verificación viene."""
        discard_reasons.append(texto)
        discard_records.append(
            CombinedDiscardRecord(check_id=check_id, aspect=aspect, element=element, text=texto)
        )

    B, L = layout.B_m, layout.L_m
    cover_bottom_m = code.cover_footing_mm()[0] / 1000.0
    cover_top_mm, cover_top_note = top_cover.resolve_mm()
    cover_top_m = cover_top_mm / 1000.0
    db = assumed_bar_diameter_mm / 1000.0

    d_bottom = h_m - cover_bottom_m - db / 2.0
    d_top = h_m - cover_top_m - db / 2.0
    if d_bottom <= 0 or d_top <= 0:
        raise ValueError(
            f"Peralte insuficiente: h={h_m} m no admite recubrimientos de "
            f"{cover_bottom_m * 1000:.0f}/{cover_top_mm:.0f} mm."
        )

    trace.add(
        CalculationTraceEntry(
            id="top_cover",
            description="Recubrimiento de la cara superior",
            equation_symbolic="d_superior = h − recubrimiento_superior − db/2",
            equation_substituted=(
                f"h={h_m:.3f} − {cover_top_m:.3f} − {db / 2:.4f} = {d_top:.4f} m "
                f"(cara inferior: d={d_bottom:.4f} m con recubrimiento {cover_bottom_m:.3f} m)"
            ),
            result_value=cover_top_mm,
            result_unit="mm",
            hypotheses=[cover_top_note],
            code_name="E.060",
            code_reference="§7.7.1",
            status=CheckStatus.INFO,
        )
    )

    # --- E.050 art. 23.1: la cimentación sigue siendo SUPERFICIAL (H7) -------
    superficial = check_shallow_foundation(soil.Df_m, B, L)
    trace.add(
        CalculationTraceEntry(
            id="shallow_foundation",
            description="Cimentación superficial: relación profundidad / ancho",
            equation_symbolic="Df / B <= 5",
            equation_substituted=superficial.equation_substituted,
            result_value=superficial.ratio,
            result_unit="—",
            hypotheses=[SHALLOW_FOUNDATION_READING]
            + ([] if superficial.ok else [SHALLOW_FOUNDATION_EXCEEDED_NOTE]),
            code_name="E.050",
            code_reference=superficial.code_reference,
            status=CheckStatus.PASS if superficial.ok else CheckStatus.FAIL,
        )
    )
    if not superficial.ok:
        descartar(
            "shallow_foundation", "cimentacion_profunda", None,
            f"Df/B = {superficial.ratio:.2f} > {superficial.limit:.0f}: E.050 art. 23.1 "
            f"define esa cimentación como PROFUNDA, fuera del alcance del programa.",
        )

    # --- E.050 art. 23.3: proporción en planta -------------------------------
    # Desde H6 (2026-09-20) la regla es la misma en las tres tipologías y vive en
    # `engine.codes.peru.e050_soils`. Aquí solo se traza.
    forma = check_shape_ratio(B, L)
    ratio, shape_ok = forma.ratio, forma.ok
    trace.add(
        CalculationTraceEntry(
            id="shape_ratio",
            description="Proporción de la zapata combinada",
            equation_symbolic="lado mayor / lado menor <= 10",
            equation_substituted=forma.equation_substituted,
            result_value=ratio,
            result_unit="—",
            hypotheses=[SHAPE_RATIO_READING]
            + ([] if shape_ok else [SHAPE_RATIO_EXCEEDED_NOTE]),
            code_name="E.050",
            code_reference=forma.code_reference,
            status=CheckStatus.PASS if shape_ok else CheckStatus.FAIL,
        )
    )
    if not shape_ok:
        descartar(
            "shape_ratio", "proporcion_mayor_que_10", None,
            f"Proporción {ratio:.2f} > 10: E.050 art. 23.3 clasifica esa forma como cimentación "
            f"continua, no como zapata combinada."
        )

    # --- Profundidad mínima de cimentación (E.050 art. 26.2) ----------------
    fd = check_foundation_depth(soil.Df_m, soil.founded_on_rock)
    trace.add(
        CalculationTraceEntry(
            id="foundation_depth", description="Profundidad mínima de cimentación",
            equation_symbolic="Df >= 0,80 m (salvo cimentación sobre roca)",
            equation_substituted=fd.equation_substituted,
            result_value=fd.Df_m, result_unit="m",
            hypotheses=fd.hypotheses,
            code_name="E.050", code_reference=fd.code_reference, status=fd.status,
        )
    )
    if fd.status is CheckStatus.FAIL:
        descartar("foundation_depth", "profundidad_insuficiente", None, fd.message)

    # --- Peralte mínimo (E.060 §15.7) ---------------------------------------
    #
    # AUDITORÍA DE PARIDAD (2026-09-19). La combinada no verificaba §15.7 y la aislada sí.
    # No es una diferencia defendible: §15.7 habla de «las zapatas» sin distinguir tipología
    # —«La altura de las zapatas, medida sobre el refuerzo inferior no debe ser menor de
    # 300 mm para zapatas apoyadas sobre el suelo»— y §15.10.1 manda diseñar las que
    # soportan más de una columna «de acuerdo con los requisitos de diseño apropiados de
    # esta Norma». El hueco producía CONFORME en una zapata combinada de h = 0,20 m con
    # cargas bajas, que la aislada habría descartado.
    #
    # No se decide nada nuevo: se aplica el MISMO criterio y la MISMA implementación que la
    # aislada —`code.min_depth_rule`, con la interpretación documentada en
    # docs/normativa/peralte_minimo_zapatas.md y parametrizada en E060ConcreteCode—. La
    # magnitud gobernante es `d_bottom`, el peralte sobre el refuerzo INFERIOR, que es el
    # que nombra el artículo.
    min_depth_eq = code.min_depth_rule(h_m, d_bottom, on_soil=True)
    min_depth_threshold = code.min_depth_threshold_m()
    min_depth_status = (
        CheckStatus.PASS if min_depth_eq.value >= min_depth_threshold - 1e-9 else CheckStatus.FAIL
    )
    trace.add(
        CalculationTraceEntry(
            id="min_depth",
            description="Peralte mínimo de zapatas apoyadas sobre el suelo",
            equation_symbolic=min_depth_eq.equation_symbolic,
            equation_substituted=min_depth_eq.equation_substituted,
            result_value=min_depth_eq.value,
            result_unit=min_depth_eq.unit,
            hypotheses=[
                "Interpretación de §15.7 documentada en docs/normativa/peralte_minimo_zapatas.md "
                "(razonada, no una certeza normativa; configurable en E060ConcreteCode).",
                "§15.7 no distingue tipología y §15.10.1 remite a los requisitos de esta Norma: "
                "se aplica a la zapata combinada el mismo criterio que a la aislada.",
            ],
            code_name="E.060",
            code_reference=min_depth_eq.code_reference,
            status=min_depth_status,
        )
    )
    if min_depth_status is CheckStatus.FAIL:
        descartar(
            "min_depth", "peralte_minimo", None,
            f"No cumple peralte mínimo E.060 §15.7 (magnitud gobernante "
            f"{min_depth_eq.value:.3f} m < {min_depth_threshold:.3f} m).",
        )

    # --- Presión de contacto: resultante de TODAS las columnas (servicio) ----
    #
    # REDUCCIÓN SÍSMICA AL 80 %. Se aplica con el MISMO operador que la zapata aislada y las
    # zapatas de la conectada: `depth_solver.soil_actions`, que es la única implementación
    # del criterio (E.030 art. 29, E.060 §15.2.5). Aquí no se reescribe nada de él.
    #
    # Alcance, idéntico al de la conectada (D10C-2): SOLO las presiones de suelo, SOLO con
    # composición —modo por casos— y SOLO sobre la componente CS declarada a nivel de
    # RESISTENCIA. No toca la estabilidad (E.030 art. 64.2 lo prohíbe expresamente), ni el
    # diagrama factorizado, ni el modo directo, donde no se sabe qué parte es sísmica.
    #
    # Por qué el término de excentricidad también usa la carga reducida: el reparto de la
    # resultante es lineal, de modo que reducir la componente CS de cada columna equivale a
    # repartir 0,8·CS. Es el mismo argumento de linealidad de D10C-2.
    self_weight = compute_self_weight(B, L, h_m, soil.Df_m, concrete.unit_weight_kNm3, soil.gamma_kNm3)
    peor_ratio, peor_res, peor_combo, peor_hip, peor_qadm = -1.0, None, "", [], soil.qadm_kPa
    for nombre in {c.name for c in layout.columns[0].loads.service}:
        P_col = 0.0
        Mx_tot = 0.0
        My_tot = 0.0
        hip: list[str] = []
        # E.060 §15.2.4 habla de «estados de cargas en los que intervengan cargas
        # temporales»: basta con que la combinación declare sismo o viento en alguna
        # columna para que el estado de carga sea temporal.
        temporal = None
        for col in layout.columns:
            combo = _combo_by_name(col, nombre, factored=False)
            if combo is None:
                continue
            temporal = combo if temporal is None else temporal.model_copy(update={
                "includes_seismic_loads": temporal.includes_seismic_loads or combo.includes_seismic_loads,
                "includes_wind_loads": temporal.includes_wind_loads or combo.includes_wind_loads,
            })
            # Las hipótesis se etiquetan con la columna de la que salen: la reducción se
            # evalúa combinación por combinación y columna por columna.
            hip_col: list[str] = []
            P_s, Mx_s, My_s = soil_actions(combo, soil, hip_col)
            if seismic_reduction_unavailable(soil, combo):
                hip_col.append(seismic_reduction_unavailable_note(combo.name))
            hip += [f"[{col.label}] {t}" for t in hip_col]
            P_col += P_s
            # Momento respecto del centroide de la zapata: el aplicado más el que
            # produce la carga por estar descentrada.
            Mx_tot += Mx_s + P_s * col.offset_x_m
            My_tot += My_s + P_s * col.offset_y_m
        P_total = P_col + self_weight.W_total_kN
        ecc = compute_total_eccentricity(P_col, self_weight.W_total_kN, Mx_tot, My_tot)
        # Ojo: los offsets ya están dentro de Mx_tot/My_tot, así que aquí van a cero.
        res = contact_model.compute(B, L, P_total, ecc.ex_m, ecc.ey_m)
        q_base = convert_pressure(
            res.qmax_kPa, PressureBasis.BRUTA, soil.pressure_basis, soil.gamma_kNm3, soil.Df_m
        )
        # PARIDAD (auditoría del incremento del 30 %). E.060 §15.2.4 habla de la presión
        # admisible DEL SUELO, no de una tipología: si el proyectista lo habilita, rige aquí
        # igual que en la aislada y en la conectada. Mismo operador, `effective_qadm`; la
        # combinada no lo reimplementa. Está apagado por defecto: sin habilitarlo, `qadm`
        # es el declarado y nada cambia.
        qadm_usada = effective_qadm(soil, temporal, hip) if temporal is not None else soil.qadm_kPa
        # `usable` y no `within_kern`: con el modelo de área efectiva (E.050 art. 28) una
        # resultante fuera del núcleo sí tiene un campo de presiones válido. Con el modelo
        # por defecto las dos preguntas coinciden.
        r = float("inf") if not res.usable else q_base / qadm_usada
        if r > peor_ratio:
            peor_ratio, peor_res, peor_combo, peor_hip = r, res, nombre, hip
            peor_qadm = qadm_usada

    assert peor_res is not None
    if peor_ratio > 1.0 or not peor_res.usable:
        contact_status = CheckStatus.FAIL
    elif not peor_res.compliance_can_be_affirmed:
        # E.050 art. 28 evalúa sobre el área efectiva y el qadm declarado corresponde a la
        # zapata real: un incumplimiento es válido, un cumplimiento no puede afirmarse.
        contact_status = CheckStatus.NOT_VERIFIED
        peor_hip = peor_hip + [EFFECTIVE_AREA_CANNOT_AFFIRM_NOTE]
    else:
        contact_status = CheckStatus.PASS
    trace.add(
        CalculationTraceEntry(
            id="contact_pressure",
            description=(
                f"Presión de contacto bajo la zapata combinada (modelo {peor_res.model_name})"
            ),
            equation_symbolic=(
                contact_pressure_equation_symbolic(peor_res)
                + ", con P y M de TODAS las columnas"
            ),
            equation_substituted=peor_res.equation_substituted,
            result_value=peor_res.qmax_kPa, result_unit="kPa",
            hypotheses=[f"within_kern={peor_res.within_kern}", AXIS_CONVENTION_NOTE] + peor_hip,
            governing_combo=peor_combo,
            code_name="E.060", code_reference=peor_res.code_reference, status=contact_status,
        )
    )
    if contact_status is CheckStatus.FAIL:
        descartar(
            "contact_pressure",
            (
                "presion_admisible_y_nucleo" if peor_ratio > 1.0 and not peor_res.usable
                else "resultante_fuera_del_nucleo" if not peor_res.usable
                else "presion_admisible"
            ),
            None,
            f"Presión de contacto: qmax={peor_res.qmax_kPa:.1f} kPa frente a qadm={peor_qadm:.1f} kPa"
            + ("" if peor_res.usable else " y resultante fuera del núcleo central (§15.2.3)")
        )

    # --- Estabilidad: deslizamiento y volcamiento (pendiente 7) --------------
    #
    # Sustituye la declaración D4, que dejaba NO VERIFICADO todo lo que trajera fuerza
    # horizontal porque la verificación no existía para esta tipología. Ahora existe:
    # `engine/foundation/combined_stability.py` reduce las columnas a una resultante —la
    # misma reducción que usa la presión de contacto— y aplica el criterio de
    # `engine/soil/stability.py`, que sigue siendo la única fuente de los FS, del trato de
    # μ y de la regla de carga muerta (E.020 art. 20.1).
    #
    # Sin fuerza horizontal no se añade nada: el momento de las columnas queda acotado por
    # la exigencia de resultante dentro del núcleo central (e ≤ dim/6 ⇒ FS ≥ 3).
    stability = check_combined_stability(layout, soil, self_weight.W_total_kN, B, L, h_m)
    if stability.applicable:
        for check_id, res, etiqueta in (
            ("sliding", stability.sliding, "Deslizamiento"),
            ("overturning_x", stability.overturning_x, "Volcamiento eje X"),
            ("overturning_y", stability.overturning_y, "Volcamiento eje Y"),
        ):
            trace.add(
                CalculationTraceEntry(
                    id=check_id,
                    description=f"Estabilidad de la zapata combinada — {etiqueta}",
                    equation_symbolic=(
                        "FS = (μ·N + c·A) / H" if check_id == "sliding"
                        else "FS = M_estabilizador / M_volcador, con M_volcador envolvente"
                    ),
                    equation_substituted=res.equation_substituted,
                    result_value=res.FS_obtained if res.FS_obtained is not None else 0.0,
                    result_unit="FS",
                    hypotheses=[res.message]
                    + ([f"Parámetros faltantes: {', '.join(res.missing_parameters)}"]
                       if res.missing_parameters else [])
                    + list(STABILITY_HYPOTHESES)
                    + (list(STABILITY_SEISMIC_HYPOTHESES)
                       if "E.030 art. 64.2" in res.code_reference else []),
                    governing_combo=res.governing_combo,
                    code_name="E.030" if "E.030" in res.code_reference else "E.050",
                    code_reference=res.code_reference,
                    status=res.status,
                )
            )
            if res.status is CheckStatus.FAIL:
                descartar(
                    check_id,
                    "no_cumple",
                    None if check_id == "sliding" else res.axis,
                    f"{etiqueta}: FS = {res.FS_obtained:.2f} < {res.FS_required:.2f} requerido "
                    f"(combinación {res.governing_combo}).",
                )
    else:
        stability = None

    # --- Diagrama longitudinal con la combinación FACTORIZADA gobernante -----
    # ENVOLVENTE (2026-09-22). Cada efecto se diseña para SU combinación más
    # desfavorable: M+ para la cara inferior, M- para la superior y |V| para el cortante.
    # Hasta esta fecha se elegía UNA combinación —la de mayor |M| de cualquier signo— y
    # se tomaban de su diagrama los tres efectos; eso no es una envolvente, y con varias
    # combinaciones podía dejar sin cubrir el efecto que gobierna otra. Lo destapó la
    # validación con Aragón CR2 §3.5: el cortante lo gobierna 1,4CM+1,7CV y el momento
    # 1,25(CM+CV-CS). `docs/validacion_aragon_3_5_combinada.md`.
    #
    # Con una sola combinación factorizada los tres coinciden con ella: por eso ningún caso
    # congelado —todos con una— se mueve, y por eso el congelamiento no lo detectaba.
    diagramas: dict[str, "BeamDiagram"] = {}
    for nombre in sorted({c.name for c in layout.columns[0].loads.factored}):
        dia = _diagram_for(layout, nombre, factored=True)
        if dia is not None:
            diagramas[nombre] = dia
    if not diagramas:
        raise ValueError("No hay ninguna combinación factorizada común a todas las columnas.")

    def _gobernante(clave) -> tuple[str, "BeamDiagram"]:
        nombre = max(diagramas, key=lambda n: (clave(diagramas[n]), n))
        return nombre, diagramas[nombre]

    # El diagrama que se MUESTRA sigue siendo el de mayor |M|: es el contrato de
    # `diagram` y `diagram_combo`. El diseño ya no sale solo de él.
    mejor_nombre, mejor_dia = _gobernante(
        lambda d: max(d.M_max_positive_kNm, d.M_max_negative_kNm)
    )
    nombre_pos, dia_pos = _gobernante(lambda d: d.M_max_positive_kNm)
    nombre_neg, dia_neg = _gobernante(lambda d: d.M_max_negative_kNm)
    # Cortante a d de la cara (decisión del proyectista, 2026-09-29): E.060 §15.5.2 y
    # §11.1.3.1. Hasta esta fecha se tomaba máx |V| de todo el diagrama, conservador y
    # distinto de la norma (docs/auditoria_cv_cortante_longitudinal_combinada.md). La
    # combinación gobernante es la de mayor cortante EN LAS SECCIONES CRÍTICAS.
    cortes = {n: critical_one_way_shear(dia, d_bottom) for n, dia in diagramas.items()}
    nombre_V = max(cortes, key=lambda n: (cortes[n].Vu_kN, n))
    corte_V = cortes[nombre_V]

    trace.add(
        CalculationTraceEntry(
            id="beam_diagram",
            description="Diagramas de cortante y momento a lo largo de la zapata",
            equation_symbolic="M(x) por estática sobre el área a un lado del plano vertical",
            equation_substituted=(
                f"dirección {layout.longitudinal_direction}, L={layout.longitudinal_length_m:.3f} m | "
                f"w0={mejor_dia.w_start_kNm:.2f}, w1={mejor_dia.w_end_kNm:.2f} kN/m | "
                f"M+ = {mejor_dia.M_max_positive_kNm:.2f} kN·m en x={mejor_dia.x_M_max_positive_m:.3f} | "
                f"M− = {mejor_dia.M_max_negative_kNm:.2f} kN·m en x={mejor_dia.x_M_max_negative_m:.3f}"
            ),
            result_value=mejor_dia.M_max_negative_kNm, result_unit="kN·m",
            hypotheses=mejor_dia.hypotheses,
            governing_combo=mejor_nombre,
            code_name="E.060", code_reference="§15.4.1 (momento en cualquier sección) y §15.10.1",
            status=CheckStatus.INFO,
        )
    )

    # --- Flexión longitudinal: cara inferior y, si procede, cara superior ----
    ancho = layout.transverse_width_m
    rho_min, rho_ref = code.rho_min_temperature(steel.fy_MPa, steel.bar_type)
    minimos = two_face_minimum(ancho, h_m, rho_min, rho_ref)
    hay_negativo = dia_neg.has_negative_moment

    def _cara(face: str, Mu: float, x: float, d: float, cover: float, traccionada: bool) -> FaceDesign:
        As_min, gobierna = minimos.for_face(traccionada)
        res = design_flexure(
            Mu, b_m=ancho, h_m=h_m, d_m=d, cantilever_m=0.0,
            fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa, bar_type=steel.bar_type, code=code,
        )
        As_req = res.As_required_m2 if res.As_required_m2 == res.As_required_m2 else float("nan")
        As_dis = max(As_req, As_min) if As_req == As_req else float("nan")
        return FaceDesign(
            face=face, Mu_kNm=Mu, x_m=x, width_m=ancho, d_m=d, cover_m=cover,
            As_required_m2=As_req, As_min_m2=As_min, As_design_m2=As_dis,
            min_governed_by=gobierna, status=res.status,
            note=(
                f"As por flexión = {As_req * 1e4:.2f} cm², mínimo = {As_min * 1e4:.2f} cm² "
                f"({gobierna}) -> diseño {As_dis * 1e4:.2f} cm²"
            ),
        )

    bottom = _cara(
        "inferior", dia_pos.M_max_positive_kNm, dia_pos.x_M_max_positive_m,
        d_bottom, cover_bottom_m, traccionada=True,
    )
    top = (
        _cara(
            "superior", dia_neg.M_max_negative_kNm, dia_neg.x_M_max_negative_m,
            d_top, cover_top_m, traccionada=True,
        )
        if hay_negativo
        else None
    )
    combo_de_cara = {"inferior": nombre_pos, "superior": nombre_neg}

    # --- Armado real de cada cara ------------------------------------------
    for cara, cover in ((bottom, cover_bottom_m), (top, cover_top_m)):
        if cara is None or cara.As_design_m2 != cara.As_design_m2:
            continue
        # Longitud disponible para desarrollar la barra: desde la sección crítica
        # hasta el extremo MÁS CERCANO de la zapata, descontando el recubrimiento
        # lateral. Se toma el lado corto porque es el que limita.
        Ltot = layout.longitudinal_length_m
        disponible = max(
            min(cara.x_m, Ltot - cara.x_m) - cover_bottom_m, 0.0
        )
        cara.rebar = select_face_rebar(
            cara.face, cara.As_design_m2, width_m=ancho, h_m=h_m, cover_m=cover,
            fy_MPa=steel.fy_MPa, fc_MPa=concrete.fc_MPa, available_length_m=disponible,
        )

    for etiqueta, cara in (("flexure_bottom", bottom), ("flexure_top", top)):
        if cara is None:
            continue
        trace.add(
            CalculationTraceEntry(
                id=etiqueta,
                description=f"Flexión longitudinal, cara {cara.face}",
                equation_symbolic="As = f(Mu, b, d, f'c, fy) con bloque 0,85f'c",
                equation_substituted=cara.note,
                result_value=cara.As_design_m2 * 1e4, result_unit="cm²",
                hypotheses=[
                    f"Peralte efectivo {cara.d_m:.4f} m medido desde la fibra comprimida de "
                    f"esta cara, con recubrimiento {cara.cover_m:.3f} m.",
                    f"Mínimo de dos caras: {TWO_FACE_MIN_REFERENCE}.",
                ]
                + ([cara.rebar.note] if cara.rebar else [])
                + ([cara.rebar.development_note] if cara.rebar else [])
                + [ENVELOPE_DESIGN_NOTE],
                governing_combo=combo_de_cara[cara.face],
                code_name="E.060",
                code_reference=f"§10.2 y §15.4.1; mínimo por {cara.min_governed_by}",
                # El estado incluye ya la longitud de desarrollo y la separación máxima:
                # `select_face_rebar` degrada a FAIL si alguna no cumple.
                status=cara.rebar.status if cara.rebar is not None else cara.status,
            )
        )
        if cara.status is CheckStatus.FAIL:
            descartar(etiqueta, "seccion", cara.face,
                      f"Flexión longitudinal, cara {cara.face}: sección insuficiente.")
        if cara.rebar is not None and not cara.rebar.development_ok:
            descartar(
                etiqueta, "longitud_desarrollo", cara.face,
                f"Cara {cara.face}: longitud de desarrollo insuficiente "
                f"({cara.rebar.ld_required_m * 100:.1f} cm exigidos frente a "
                f"{cara.rebar.ld_available_m * 100:.1f} cm disponibles, E.060 §15.6 y Cap. 12)."
            )
        if cara.rebar is not None and not cara.rebar.spacing_ok:
            descartar(
                etiqueta, "separacion", cara.face,
                f"Cara {cara.face}: separación {cara.rebar.spacing_m * 100:.1f} cm supera el "
                f"límite de {cara.rebar.spacing_limit_m * 100:.1f} cm ({cara.rebar.spacing_reference})."
            )

    if not hay_negativo:
        trace.add(
            CalculationTraceEntry(
                id="flexure_top",
                description="Flexión longitudinal, cara superior",
                equation_symbolic="—",
                equation_substituted=(
                    "El diagrama no produce momento negativo en ninguna sección: la cara "
                    "superior no trabaja a tracción por flexión."
                ),
                result_value=0.0, result_unit="kN·m",
                hypotheses=[
                    "No se diseña acero superior POR FLEXIÓN. El refuerzo por cambios "
                    "volumétricos de §9.7 sigue siendo exigible con independencia de esto."
                ],
                code_name="E.060", code_reference="§15.4.1", status=CheckStatus.INFO,
            )
        )

    # --- Cortante unidireccional longitudinal --------------------------------
    shear = check_shear_oneway(
        corte_V.Vu_kN, concrete.fc_MPa, bw_m=ancho, d_m=d_bottom, code=code
    )
    trace.add(
        CalculationTraceEntry(
            id="shear_longitudinal",
            description="Cortante unidireccional en la dirección longitudinal",
            equation_symbolic="Vc = 0,17·sqrt(f'c)·bw·d",
            equation_substituted=shear.equation_substituted,
            result_value=shear.Vu_kN, result_unit="kN",
            hypotheses=[
                "Vu tomado del diagrama, no de una fórmula de voladizo: en una zapata de "
                "varias columnas el cortante no es monótono.",
                corte_V.note,
                "Sección crítica a d de la cara de cada columna, a cada lado (E.060 §15.5.2 y "
                "§11.1.3.1, decisión del proyectista 2026-09-29). Interpretación: la zapata es "
                "una viga invertida —la columna es el apoyo y la presión del suelo, la carga—, "
                "de modo que se cumplen (a) y (b) de §11.1.3; si otra columna queda entre la "
                "cara y la sección, no se cumple (c) y ese lado se toma en la cara. Con presión "
                "no negativa, V es monótono entre cargas y el máximo fuera de esas zonas está "
                "en las propias secciones críticas.",
                "E.060 §11.5.6.1(a) exime a losas y zapatas del refuerzo mínimo de cortante.",
                CONCRETE_ONLY_SHEAR_CRITERION,
                ENVELOPE_DESIGN_NOTE,
            ],
            governing_combo=nombre_V,
            code_name="E.060", code_reference=shear.code_reference, status=shear.status,
        )
    )
    # C-V. Criterio del programa: concreto solo. Vu > φVc deja la entrada en FAIL y la geometría
    # se descarta. Hasta la auditoría C-V aquí se dimensionaban estribos (check_beam_shear con
    # 2 ramas sobre todo el ancho) que NO intervenían en la aceptación: la entrada del concreto
    # seguía en FAIL. Se retiraron para no sugerir que el motor cuenta con Vs. Implementar
    # Vn = Vc + Vs es una decisión pendiente (ramas y separación transversal, alcance de
    # §11.12.3, sección crítica de §15.5.2); ver docs/auditoria_cv_cortante_longitudinal_combinada.md.
    stirrups = None
    if shear.status is CheckStatus.FAIL:
        descartar(
            "shear_longitudinal", "concreto_solo", None,
            f"Cortante longitudinal: Vu = {shear.Vu_kN:.1f} kN > φVc = {shear.phi_Vc_kN:.1f} kN "
            f"(criterio del programa: resistencia del concreto solo; el refuerzo de cortante no "
            f"está implementado en la zapata combinada)."
        )

    # --- Franjas transversales (CRITERIO de modelación) ----------------------
    transversal = "Y" if layout.longitudinal_direction == "X" else "X"
    dim_transversal = L if transversal == "Y" else B
    tiras: list[TransverseStrip] = []
    for col in layout.columns:
        combo = max(
            (c for c in col.loads.factored), key=lambda c: c.P_kN, default=None
        )
        if combo is None:
            continue
        b_col = layout.column_width_along(col, transversal)
        ancho_franja = min(b_col + 2.0 * TRANSVERSE_STRIP_EXTENSION_FACTOR * d_bottom, dim_transversal)
        off = col.offset_y_m if transversal == "Y" else col.offset_x_m
        cants = (dim_transversal / 2.0 + off - b_col / 2.0, dim_transversal / 2.0 - off - b_col / 2.0)
        voladizo = max(cants)
        # Presión bajo la franja: la carga de la columna repartida sobre su franja.
        q_franja = combo.P_kN / (ancho_franja * dim_transversal)
        Mu = q_franja * ancho_franja * voladizo**2 / 2.0
        res = design_flexure(
            Mu, b_m=ancho_franja, h_m=h_m, d_m=d_bottom, cantilever_m=voladizo,
            fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa, bar_type=steel.bar_type, code=code,
        )
        # Armado de la franja. La barra transversal arranca en la cara de la columna
        # y llega hasta el borde: la longitud disponible es el voladizo menos el
        # recubrimiento lateral.
        armado_franja = (
            select_face_rebar(
                "inferior", res.As_design_m2, width_m=ancho_franja, h_m=h_m,
                cover_m=cover_bottom_m, fy_MPa=steel.fy_MPa, fc_MPa=concrete.fc_MPa,
                available_length_m=max(voladizo - cover_bottom_m, 0.0),
            )
            if res.As_design_m2 == res.As_design_m2
            else None
        )
        estado_franja = armado_franja.status if armado_franja else res.status
        tiras.append(
            TransverseStrip(
                column_label=col.label, strip_width_m=ancho_franja, cantilever_m=voladizo,
                Mu_kNm=Mu, As_required_m2=res.As_required_m2, As_min_m2=res.As_min_m2,
                As_design_m2=res.As_design_m2, rebar=armado_franja, status=estado_franja,
                criterion_note=TRANSVERSE_STRIP_NOTE,
            )
        )
        trace.add(
            CalculationTraceEntry(
                id=f"transverse_strip_{col.label}",
                description=f"Franja transversal bajo la columna {col.label}",
                equation_symbolic="Mu = q·b_franja·c²/2 sobre el voladizo transversal",
                equation_substituted=(
                    f"ancho de franja {ancho_franja:.4f} m, voladizo {voladizo:.4f} m, "
                    f"Mu={Mu:.2f} kN·m -> As={res.As_design_m2 * 1e4:.2f} cm²"
                ),
                result_value=res.As_design_m2 * 1e4, result_unit="cm²",
                hypotheses=[TRANSVERSE_STRIP_NOTE]
                + ([armado_franja.note, armado_franja.development_note] if armado_franja else []),
                governing_combo=combo.name,
                code_name="E.060", code_reference="§10.2 (diseño de la sección); ancho de franja: CRITERIO",
                status=estado_franja,
            )
        )
        if estado_franja is CheckStatus.FAIL:
            motivo, aspecto = "sección insuficiente", "seccion"
            if armado_franja is not None and not armado_franja.development_ok:
                aspecto = "longitud_desarrollo"
                motivo = (
                    f"longitud de desarrollo insuficiente "
                    f"({armado_franja.ld_required_m * 100:.1f} cm exigidos frente a "
                    f"{armado_franja.ld_available_m * 100:.1f} cm disponibles)"
                )
            elif armado_franja is not None and not armado_franja.spacing_ok:
                motivo, aspecto = "separación por encima del límite de §10.5.4", "separacion"
            descartar(f"transverse_strip_{col.label}", aspecto, col.label,
                      f"Franja transversal de {col.label}: {motivo}.")

    # --- Cortante unidireccional TRANSVERSAL (E.060 §15.5.1 -> §11.12.1.1) ---
    #
    # AUDITORÍA DE PARIDAD (hallazgo H2, 2026-09-19). La combinada verificaba el cortante
    # LONGITUDINAL y no el transversal; la aislada verifica los dos. §11.12.1.1 exige
    # investigar el plano que atraviesa el ancho TOTAL, sin distinguir dirección.
    #
    # Criterio aprobado por el usuario: sección crítica a d de la cara de la columna,
    # b_w = longitud completa de la zapata en ese plano, y Vu integrando la presión de
    # contacto sobre el área que queda fuera. Ver las tres notas de arriba.
    peor_vu, peor_vu_combo, peor_vu_col, peor_vu_c = 0.0, "", "", 0.0
    # Solo las FACTORIZADAS: el cortante es diseño por resistencia (E.060 §15.2.1).
    for nombre in [c.name for c in layout.columns[0].loads.factored]:
        P_u = 0.0
        M_transv = 0.0
        for col in layout.columns:
            combo = _combo_by_name(col, nombre, factored=True)
            if combo is None:
                continue
            m_col = combo.My_kNm if transversal == "Y" else combo.Mx_kNm
            off_col = col.offset_y_m if transversal == "Y" else col.offset_x_m
            P_u += combo.P_kN
            M_transv += m_col + combo.P_kN * off_col
        if P_u <= 0.0:
            continue
        e_transv = M_transv / P_u
        for col in layout.columns:
            b_col = layout.column_width_along(col, transversal)
            off = col.offset_y_m if transversal == "Y" else col.offset_x_m
            # (voladizo, ¿está del lado de mayor presión?)
            lados = (
                (dim_transversal / 2.0 - off - b_col / 2.0, e_transv >= 0.0),
                (dim_transversal / 2.0 + off - b_col / 2.0, e_transv < 0.0),
            )
            for voladizo, en_borde_alto in lados:
                if voladizo <= 0.0:
                    continue
                vu = shear_force_at_d_from_face(
                    P_u, abs(e_transv), dim_transversal, voladizo, d_bottom,
                    near_high_edge=en_borde_alto,
                )
                if vu > peor_vu:
                    peor_vu, peor_vu_combo = vu, nombre
                    peor_vu_col, peor_vu_c = col.label, voladizo

    shear_t = check_shear_oneway(
        peor_vu, concrete.fc_MPa, bw_m=layout.longitudinal_length_m, d_m=d_bottom, code=code
    )
    trace.add(
        CalculationTraceEntry(
            id="shear_transversal",
            description="Cortante unidireccional transversal (viga ancha)",
            equation_symbolic="Vu <= φVc, con la sección crítica a d de la cara y b_w = longitud total",
            equation_substituted=(
                f"Voladizo transversal gobernante {peor_vu_c:.4f} m en {peor_vu_col or '—'} "
                f"(combinación {peor_vu_combo or '—'}), sección crítica a d = {d_bottom:.4f} m "
                f"de la cara | b_w = {layout.longitudinal_length_m:.3f} m | "
                f"{shear_t.equation_substituted}"
            ),
            result_value=shear_t.Vu_kN, result_unit="kN",
            hypotheses=[
                TRANSVERSE_SHEAR_NOTE,
                TRANSVERSE_SHEAR_PRESSURE_NOTE,
                TRANSVERSE_SHEAR_SECTION_NOTE,
                "E.060 §11.5.6.1(a) exime a losas y zapatas del refuerzo mínimo de cortante.",
            ],
            governing_combo=peor_vu_combo or None,
            code_name="E.060",
            code_reference=f"§15.5.1 y §15.5.2 -> §11.12.1.1; Vc por {shear_t.code_reference}",
            status=shear_t.status,
        )
    )
    if shear_t.status is CheckStatus.FAIL:
        descartar(
            "shear_transversal", "concreto_solo", peor_vu_col or None,
            f"Cortante transversal: Vu = {shear_t.Vu_kN:.1f} kN > φVc = {shear_t.phi_Vc_kN:.1f} kN "
            f"(criterio del programa: resistencia del concreto solo; el refuerzo de cortante "
            f"no está implementado en la combinada)."
        )

    # --- Punzonamiento por columna (motor de la Fase 1C) --------------------
    # EL CAMPO LO PRODUCE LA RESULTANTE DE TODAS LAS COLUMNAS (2026-09-20).
    #
    # Hasta aquí se pasaba, por cada columna, su propia carga y su excentricidad respecto
    # del centroide de la zapata. Eso describe una zapata que no existe: en K1 —dos
    # columnas iguales y simétricas, sin momento— el campo real es UNIFORME y el alivio
    # bajo el área crítica vale 129,60 kN, mientras que con la carga de una sola columna
    # salían 174,14 kN. Vu quedaba SUBESTIMADO.
    #
    # La carga que punzona sigue siendo la de la columna; lo que cambia es el campo.
    resultantes_factorizadas: dict[str, tuple[float, float, float]] = {}
    for nombre in [c.name for c in layout.columns[0].loads.factored]:
        P_res = Mx_res = My_res = 0.0
        for col in layout.columns:
            k = _combo_by_name(col, nombre, factored=True)
            if k is None:
                continue
            P_res += k.P_kN
            Mx_res += k.Mx_kNm + k.P_kN * col.offset_x_m
            My_res += k.My_kNm + k.P_kN * col.offset_y_m
        if P_res > 0.0:
            resultantes_factorizadas[nombre] = (P_res, Mx_res / P_res, My_res / P_res)

    punzonamientos: list[PunchingShearResult] = []
    for col in layout.columns:
        combo = max((c for c in col.loads.factored), key=lambda c: c.P_kN, default=None)
        if combo is None:
            continue
        P_campo, ex_campo, ey_campo = resultantes_factorizadas.get(
            combo.name, (combo.P_kN, 0.0, 0.0)
        )
        r = check_punching_shear(
            P_u_column_kN=combo.P_kN, field_P_u_kN=P_campo, B_m=B, L_m=L,
            bx_m=col.placement.column.bx_m, by_m=col.placement.column.by_m, d_m=d_bottom,
            fc_MPa=concrete.fc_MPa, code=code,
            Mux_kNm=combo.Mx_kNm, Muy_kNm=combo.My_kNm,
            offset_x_m=col.offset_x_m, offset_y_m=col.offset_y_m,
            ex_m=ex_campo, ey_m=ey_campo,
        )
        punzonamientos.append(r)
        trace.add(
            CalculationTraceEntry(
                id=f"punching_{col.label}",
                description=f"Punzonamiento alrededor de la columna {col.label}",
                equation_symbolic="Vu <= φVc, con Vc = mín(11-41, 11-42, 11-43)",
                equation_substituted=r.equation_substituted,
                result_value=r.ratio, result_unit="—",
                hypotheses=[r.completeness_note, AXIS_CONVENTION_NOTE]
                + (
                    [
                        f"Causa del fallo: {r.failure_cause.value} — "
                        f"{PUNCHING_FAILURE_DESCRIPTIONS[r.failure_cause]}."
                    ]
                    if r.failure_cause is not None
                    else []
                ),
                governing_combo=combo.name,
                code_name="E.060", code_reference=r.code_reference, status=r.status,
            )
        )
        if r.status is CheckStatus.FAIL:
            # Fase 5B, D2. El texto NO cambia: es la categoría de descarte de la combinada
            # y el informe agrupa por él. La causa del fallo viaja en `r.failure_cause`
            # y en la hipótesis de la traza, igual que en la aislada y la conectada.
            descartar(
                f"punching_{col.label}",
                r.failure_cause.value if r.failure_cause is not None else "no_cumple",
                col.label,
                f"Punzonamiento en {col.label} no cumple.",
            )

    return CombinedFootingResult(
        B_m=B, L_m=L, h_m=h_m, d_bottom_m=d_bottom, d_top_m=d_top,
        longitudinal_direction=layout.longitudinal_direction,
        shape_ratio=ratio, shape_ok=shape_ok,
        contact_pressure=peor_res, contact_combo=peor_combo,
        diagram=mejor_dia, diagram_combo=mejor_nombre,
        bottom_face=bottom, top_face=top,
        transverse_strips=tiras, shear_longitudinal=shear,
        shear_reinforcement=stirrups, punching=punzonamientos,
        stability=stability,
        overall_status=trace.overall_status(),
        discard_reasons=discard_reasons, discard_records=discard_records, trace=trace,
    )


FaceDesign.model_rebuild()
TransverseStrip.model_rebuild()
CombinedFootingResult.model_rebuild()
