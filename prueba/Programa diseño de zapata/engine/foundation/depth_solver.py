"""Orquestador de la Fase 2: para una geometría (B, L) dada, itera h y, para cada
h, ejecuta el pipeline completo (punto 4 de la corrección de Fase 2):

    B,L -> h candidato -> peso propio -> carga total de servicio -> presión de
    contacto -> flexión -> cortante -> punzonamiento -> cumplimiento

En cada iteración se recalcula TODO desde el peso propio -- nunca se reutiliza un
resultado calculado para un h distinto.

El solver encuentra el primer h que cumple TODAS las verificaciones (h mínimo
viable para esa B,L); NO decide si esa B,L es la mejor alternativa global -- eso
es responsabilidad del optimizador de una fase posterior (punto 3 de la
corrección de Fase 2).
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.codes.base import IConcreteCode
from engine.codes.peru.e050_soils import (
    SHALLOW_FOUNDATION_EXCEEDED_NOTE,
    SHALLOW_FOUNDATION_READING,
    SHAPE_RATIO_EXCEEDED_NOTE,
    SHAPE_RATIO_READING,
    check_shallow_foundation,
    check_shape_ratio,
)
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement, concentric
from engine.domain.loads import LoadCaseSet, LoadCombination
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.effective_depth import resolve_effective_depth
from engine.foundation.flexure import design_flexure, moment_at_critical_section
from engine.foundation.punching_shear import (
    PUNCHING_FAILURE_DESCRIPTIONS,
    check_punching_shear,
    punching_discard_reason,
)
from engine.foundation.self_weight import compute_self_weight
from engine.foundation.shear_oneway import check_shear_oneway, shear_force_at_d_from_face
from engine.reinforcement.development_check import check_development_length
from engine.reinforcement.rebar_alternatives import generate_rebar_alternatives
from engine.reinforcement.options_development import verify_options_development
from engine.reinforcement.rebar_geometry import build_rebar_geometry
from engine.reinforcement.rebar_selector import select_rebar
from engine.reinforcement.short_direction import distribute_short_direction
from engine.results.calculation_trace import CalculationTrace, CalculationTraceEntry
from engine.results.footing_candidate import DepthTrialResult, FootingCandidate, GoverningCombos
from engine.results.limitations import collect_applicable_limitations
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import (
    EFFECTIVE_AREA_CANNOT_AFFIRM_NOTE,
    ContactPressureModel,
    ContactPressureResult,
    contact_pressure_equation_symbolic,
    contact_pressure_not_usable_reason,
)
from engine.soil.foundation_depth import check_foundation_depth
from engine.soil.eccentricity import (
    AXIS_CONVENTION_NOTE,
    compute_eccentricity,
    compute_total_eccentricity,
)
from engine.soil.stability import (
    E030_OVERTURNING_INTERPRETATION,
    E030_UNREDUCED_NOTE,
    ECCENTRICITY_TERM_NOTE,
    ENVELOPE_NOTE,
    check_stability,
)
from engine.soil.pressure_basis import STANDARD_PRACTICE_REFERENCE, convert_pressure


TEMPORARY_INCREASE_FACTOR = 1.30  # E.060 §15.2.4


def effective_qadm(soil: SoilProfile, combo: LoadCombination, hypotheses: list[str]) -> float:
    """Presión admisible con que se juzga ESTA combinación.

    Aplica, si el proyectista lo habilitó, el incremento del 30 % de **E.060 §15.2.4**:
    «Se podrá considerar un incremento del 30% en el valor de la presión admisible del suelo
    para los estados de cargas en los que intervengan cargas temporales, tales como sismo o
    viento». Es potestativo —«se podrá»—, y por eso `allow_temporary_increase_30pct` es una
    declaración del usuario, apagada por defecto.

    El artículo habla de la PRESIÓN ADMISIBLE DEL SUELO, no de una tipología: rige igual en
    la aislada, en las zapatas de la conectada y en la combinada. Esta es la ÚNICA
    implementación; no duplicarla.

    Deja constancia explícita en `hypotheses` cuando se aplica —nunca en silencio— y también
    cuando la reducción sísmica del 80 % se pidió y no pudo aplicarse."""
    qadm = soil.qadm_kPa
    if soil.allow_temporary_increase_30pct and (combo.includes_seismic_loads or combo.includes_wind_loads):
        qadm *= TEMPORARY_INCREASE_FACTOR
        hypotheses.append(
            f'Incremento del 30% en qadm aplicado a la combinación "{combo.name}" '
            "(E.060 §15.2.4) por incluir cargas sísmicas/viento."
        )
    if seismic_reduction_unavailable(soil, combo):
        hypotheses.append(seismic_reduction_unavailable_note(combo.name))

    return qadm


SEISMIC_REDUCTION_FACTOR = 0.8  # E.030 art. 29 y 62.2; E.060 §15.2.5


def seismic_reduction_unavailable(soil: SoilProfile, combo: LoadCombination) -> bool:
    """True cuando el usuario pidió la reducción del 80 % pero la combinación no trae
    composición: en modo directo no se sabe qué parte es sísmica y no puede aplicarse."""
    return bool(
        soil.allow_seismic_reduction_80pct
        and combo.includes_seismic_loads
        and combo.composition is None
    )


def seismic_reduction_unavailable_note(combo_name: str) -> str:
    """Aviso único para las tres tipologías. No duplicar esta redacción."""
    return (
        f'Reducción sísmica al 80% (E.060 §15.2.5, E.030 art. 29) NO aplicada a "{combo_name}": '
        "requiere conocer la componente sísmica, y con combinaciones directas no se conoce. "
        "Se procede sin la reducción -- resultado del lado conservador. El modo de cargas "
        "por casos la permite."
    )


def soil_actions(combo: LoadCombination, soil: SoilProfile, hypotheses: list[str]) -> tuple[float, float, float]:
    """(P, Mx, My) de servicio con que se verifica el SUELO (Fase 10B, CC-4).

    Si el usuario activa la reducción y la composición es conocida, la componente sísmica
    declarada A NIVEL DE RESISTENCIA se multiplica por 0,8: E.030 art. 29 («Cuando se
    realicen verificaciones por esfuerzos admisibles, las fuerzas sísmicas obtenidas con esta
    Norma Técnica se multiplican por 0,8») y E.060 §15.2.5, que la justifica porque E.030 las
    da a nivel de resistencia. Un sismo declarado A NIVEL DE SERVICIO no se vuelve a reducir.

    Interpretación declarada: E.020 art. 19 usa 0,70·E, pero se declara subsidiaria («excepto
    en los casos indicados en las normas propias de los diversos materiales»); rigen E.030 y
    E.060. La estabilidad NO usa esta reducción (E.030 art. 64.2)."""
    P, Mx, My = combo.P_kN, combo.Mx_kNm, combo.My_kNm
    comp = combo.composition
    # D10C-2: también las cargas CORREGIDAS de la conectada (composición redistribuida). Por
    # linealidad del reparto, reducir sus componentes CS equivale a repartir 0,8·CS. Solo para
    # las presiones de suelo de cada zapata: la estabilidad, el despegue del sistema y el diseño
    # factorizado no pasan por aquí.
    if not (soil.allow_seismic_reduction_80pct and comp is not None and combo.includes_seismic_loads):
        return P, Mx, My
    quita = 1.0 - SEISMIC_REDUCTION_FACTOR
    dP = quita * comp.total("P_kN", {"CS"}, "RESISTENCIA")
    dMx = quita * comp.total("Mx_kNm", {"CS"}, "RESISTENCIA")
    dMy = quita * comp.total("My_kNm", {"CS"}, "RESISTENCIA")
    servicio = [c.case_name for c in comp.components if c.kind == "CS" and c.level == "SERVICIO"]
    hypotheses.append(
        f'Reducción sísmica al 80% aplicada a "{combo.name}" para el suelo (E.030 art. 29, '
        f"E.060 §15.2.5): componente CS a nivel de resistencia ΔP = −{dP:.2f} kN, "
        f"ΔMx = −{dMx:.2f} kN·m, ΔMy = −{dMy:.2f} kN·m."
        + (f" Casos CS a nivel de servicio sin reducir: {servicio}." if servicio else "")
        + (" Carga corregida por el reparto de la conectada: la reducción se aplica a las "
           "componentes CS de su composición (D10C-2); la estabilidad y el despegue del sistema "
           "se verifican sin reducir." if comp.redistributed else "")
    )
    return P - dP, Mx - dMx, My - dMy


def _evaluate_contact_pressure(
    B_m: float,
    L_m: float,
    self_weight_total_kN: float,
    soil: SoilProfile,
    load_case_set: LoadCaseSet,
    contact_model: ContactPressureModel,
    placement: ColumnPlacement,
) -> tuple[ContactPressureResult, str, CheckStatus, list[str]]:
    worst_ratio = -1.0
    worst_result: ContactPressureResult | None = None
    worst_combo_name = ""
    worst_hypotheses: list[str] = []

    for combo in load_case_set.service:
        hyps: list[str] = []
        P_s, Mx_s, My_s = soil_actions(combo, soil, hyps)
        P_total = P_s + self_weight_total_kN
        # El peso propio actúa sobre el centroide de la zapata: suma carga vertical
        # pero no momento. Solo la carga de columna está descentrada.
        ecc = compute_total_eccentricity(
            P_s, self_weight_total_kN, Mx_s, My_s,
            placement.offset_x_m, placement.offset_y_m,
        )
        result = contact_model.compute(B_m, L_m, P_total, ecc.ex_m, ecc.ey_m)

        qadm_used = effective_qadm(soil, combo, hyps)
        qmax_in_qadm_basis = convert_pressure(
            result.qmax_kPa, PressureBasis.BRUTA, soil.pressure_basis, soil.gamma_kNm3, soil.Df_m
        )
        # `usable` y no `within_kern`: con el modelo de área efectiva (E.050 art. 28) una
        # resultante fuera del núcleo SÍ tiene un campo de presiones válido. Ver
        # `engine/soil/contact_pressure.py`.
        ratio = float("inf") if not result.usable else qmax_in_qadm_basis / qadm_used

        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_result = result
            worst_combo_name = combo.name
            worst_hypotheses = hyps

    assert worst_result is not None
    if worst_ratio > 1.0:
        status = CheckStatus.FAIL
    elif not worst_result.compliance_can_be_affirmed:
        # E.050 art. 28 evalúa sobre el área efectiva y el qadm declarado corresponde a la
        # zapata real: un incumplimiento es válido, un cumplimiento no puede afirmarse. Es
        # la misma regla asimétrica de E.020 art. 20.1 en la estabilidad.
        status = CheckStatus.NOT_VERIFIED
        worst_hypotheses = worst_hypotheses + [EFFECTIVE_AREA_CANNOT_AFFIRM_NOTE]
    else:
        status = CheckStatus.PASS
    return worst_result, worst_combo_name, status, worst_hypotheses


class _DirectionalDemand(BaseModel):
    moment_combo_name: str
    Mu_kNm: float
    moment_cantilever_m: float
    moment_side: str
    shear_combo_name: str
    Vu_kN: float
    shear_cantilever_m: float
    shear_side: str


def _worst_directional_demand(
    load_case_set: LoadCaseSet,
    dim_along_e_m: float,
    cantilevers_m: tuple[float, float],
    d_m: float,
    ecc_selector,
    transverse_ecc_selector=None,
    dim_transverse_m: float | None = None,
) -> _DirectionalDemand:
    """ecc_selector(combo) -> excentricidad CON SIGNO [m] a lo largo de la dirección
    analizada, usando SOLO la carga factorizada de columna (sin peso propio --
    ver justificación en engine/foundation/flexure.py).

    `cantilevers_m` = (voladizo del lado de menor coordenada, voladizo del lado de
    mayor coordenada). Con columna concéntrica ambos son iguales.

    LOS DOS LADOS SE EVALÚAN SIEMPRE (Fase 1B)
    ==========================================
    Antes se evaluaba únicamente el voladizo del lado de MAYOR presión, lo cual es
    correcto mientras los dos voladizos midan lo mismo. Con la columna descentrada
    deja de serlo: el voladizo largo puede caer del lado de MENOR presión y aun así
    gobernar, porque el momento crece con el cuadrado de la longitud y solo
    linealmente con la presión. Evaluar un solo lado subestimaría Mu.

    El signo de la excentricidad decide qué borde tiene la presión alta: con e >= 0
    es el borde de mayor coordenada; con e < 0, el de menor.

    La combinación gobernante de Mu y la de Vu se determinan de forma INDEPENDIENTE
    (punto 5 de la corrección de Fase 2)."""
    c_at_low_coord, c_at_high_coord = cantilevers_m
    best_Mu, best_Mu_combo, best_Mu_cant, best_Mu_side = -1.0, "", 0.0, ""
    best_Vu, best_Vu_combo, best_Vu_cant, best_Vu_side = -1.0, "", 0.0, ""

    for combo in load_case_set.factored:
        e = ecc_selector(combo)
        # La excentricidad PERPENDICULAR. Con despegue biaxial la presión deja de ser
        # uniforme a lo ancho de la franja y el voladizo ya no se puede integrar como un
        # problema 1-D: se usa el campo común. Ver `flexure._campo_biaxial`.
        e_t = 0.0 if transverse_ecc_selector is None else transverse_ecc_selector(combo)
        # (voladizo, está_en_el_borde_de_presión_alta, etiqueta)
        if e >= 0:
            lados = ((c_at_high_coord, True, "mayor coordenada"), (c_at_low_coord, False, "menor coordenada"))
        else:
            lados = ((c_at_low_coord, True, "menor coordenada"), (c_at_high_coord, False, "mayor coordenada"))

        for cant, en_borde_alto, etiqueta in lados:
            if cant <= 0:
                continue
            Mu = moment_at_critical_section(
                combo.P_kN, abs(e), dim_along_e_m, cant, near_high_edge=en_borde_alto,
                e_transverse_m=e_t, dim_transverse_m=dim_transverse_m,
            )
            Vu = shear_force_at_d_from_face(
                combo.P_kN, abs(e), dim_along_e_m, cant, d_m, near_high_edge=en_borde_alto,
                e_transverse_m=e_t, dim_transverse_m=dim_transverse_m,
            )
            if Mu > best_Mu:
                best_Mu, best_Mu_combo, best_Mu_cant, best_Mu_side = Mu, combo.name, cant, etiqueta
            if Vu > best_Vu:
                best_Vu, best_Vu_combo, best_Vu_cant, best_Vu_side = Vu, combo.name, cant, etiqueta

    return _DirectionalDemand(
        moment_combo_name=best_Mu_combo, Mu_kNm=best_Mu,
        moment_cantilever_m=best_Mu_cant, moment_side=best_Mu_side,
        shear_combo_name=best_Vu_combo, Vu_kN=best_Vu,
        shear_cantilever_m=best_Vu_cant, shear_side=best_Vu_side,
    )


def evaluate_candidate(
    B_m: float,
    L_m: float,
    h_m: float,
    column: Column,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    load_case_set: LoadCaseSet,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    depth_params: DepthSearchParameters,
    placement: ColumnPlacement | None = None,
) -> FootingCandidate:
    """`placement` describe DÓNDE se apoya la columna sobre la zapata (Fase 1B).
    Omitirlo equivale a columna concéntrica, que es el comportamiento anterior:
    ninguna llamada existente cambia de resultado."""
    if placement is None:
        placement = concentric(column)
    elif placement.column is not column and placement.column != column:
        raise ValueError(
            "El `column` recibido y el `placement.column` describen columnas distintas. "
            "Entregue uno solo, o hágalos coincidir."
        )

    trace = CalculationTrace()
    discard_reasons: list[str] = []

    cover_mm = depth_params.cover_override_mm if depth_params.cover_override_mm is not None else code.cover_footing_mm()[0]
    cover_m = cover_mm / 1000.0
    d_m = resolve_effective_depth(
        h_m=h_m, cover_m=cover_m,
        assumed_db_m=depth_params.assumed_bar_diameter_mm / 1000.0,
        B_m=B_m, L_m=L_m, column=column, soil=soil, concrete=concrete, steel=steel,
        load_case_set=load_case_set, code=code, placement=placement,
    )

    self_weight = compute_self_weight(B_m, L_m, h_m, soil.Df_m, concrete.unit_weight_kNm3, soil.gamma_kNm3)
    trace.add(
        CalculationTraceEntry(
            id="self_weight",
            description="Peso propio de la zapata y del relleno de suelo sobre ella",
            equation_symbolic="W = gamma_concreto*B*L*h + gamma_suelo*B*L*max(Df-h,0)",
            equation_substituted=(
                f"W = {concrete.unit_weight_kNm3}*{B_m}*{L_m}*{h_m} + {soil.gamma_kNm3}*{B_m}*{L_m}*"
                f"max({soil.Df_m}-{h_m},0) = {self_weight.W_total_kN:.2f} kN"
            ),
            result_value=self_weight.W_total_kN,
            result_unit="kN",
            hypotheses=["Peso propio recalculado para este h específico (no reutilizado de otra iteración)."],
            code_name="N/A",
            code_reference="N/A (geometría + peso unitario, no es una ecuación normativa numerada)",
            status=CheckStatus.PASS,
        )
    )

    # --- Presión de contacto (combinaciones de SERVICIO) ---
    contact_result, contact_combo, contact_status, contact_hyps = _evaluate_contact_pressure(
        B_m, L_m, self_weight.W_total_kN, soil, load_case_set, contact_model, placement
    )
    if not contact_result.usable:
        discard_reasons.append(contact_pressure_not_usable_reason(contact_result))
    elif contact_status is CheckStatus.FAIL:
        discard_reasons.append(f'qmax > qadm en la combinación de servicio gobernante "{contact_combo}".')
    trace.add(
        CalculationTraceEntry(
            id="contact_pressure",
            description=(
                f"Presión de contacto máxima suelo-zapata (modelo {contact_result.model_name})"
            ),
            equation_symbolic=contact_pressure_equation_symbolic(contact_result),
            equation_substituted=contact_result.equation_substituted,
            result_value=contact_result.qmax_kPa,
            result_unit="kPa",
            hypotheses=contact_hyps + [f"within_kern={contact_result.within_kern}", AXIS_CONVENTION_NOTE],
            governing_combo=contact_combo,
            code_name="E.060",
            code_reference=contact_result.code_reference,
            status=contact_status if contact_result.usable else CheckStatus.FAIL,
        )
    )

    contact_combo_obj = next(c for c in load_case_set.service if c.name == contact_combo)
    # Las mismas acciones con que se verificó el suelo (reducción sísmica incluida, Fase 10B).
    P_rep, Mx_rep, My_rep = soil_actions(contact_combo_obj, soil, [])
    ecc_for_report = compute_total_eccentricity(
        P_rep, self_weight.W_total_kN, Mx_rep, My_rep,
        placement.offset_x_m, placement.offset_y_m,
    )

    # --- Posición de la columna sobre la zapata (Fase 1B) ---
    # Se registra SIEMPRE, también cuando es concéntrica: que la traza no mencione
    # la posición obligaría al lector a suponerla, y una zapata descentrada leída
    # como centrada es un error difícil de detectar en un informe.
    holgura_min = placement.min_clearance_m(B_m, L_m)
    cx0, cxB = placement.cantilevers_x(B_m)
    cy0, cyL = placement.cantilevers_y(L_m)
    perimetro_cerrado = holgura_min >= d_m / 2.0 - 1e-12
    trace.add(
        CalculationTraceEntry(
            id="column_placement",
            description="Posición de la columna sobre la zapata",
            equation_symbolic="voladizo = dim/2 ± offset − b/2 ; holgura_mín ≥ d/2 para perímetro cerrado",
            equation_substituted=(
                f"offset = ({placement.offset_x_m:+.4f}, {placement.offset_y_m:+.4f}) m | "
                f"voladizos X = ({cx0:.4f}, {cxB:.4f}) m, Y = ({cy0:.4f}, {cyL:.4f}) m | "
                f"holgura mínima = {holgura_min:.4f} m frente a d/2 = {d_m / 2:.4f} m"
            ),
            result_value=holgura_min,
            result_unit="m",
            hypotheses=(
                ["Columna concéntrica: los dos voladizos de cada dirección son iguales."]
                if placement.is_concentric
                else [
                    "Columna DESCENTRADA: la excentricidad geométrica se suma a la de carga "
                    "(ex = (Mx + P·offset_x)/(P+W)) y los voladizos de cada dirección son "
                    "distintos, por lo que ambos lados se evalúan y gobierna el peor.",
                    (
                        "Perímetro de punzonamiento CERRADO por los cuatro lados."
                        if perimetro_cerrado
                        else "Holgura menor que d/2: el perímetro se truncaría, caso fuera del "
                             "alcance de esta fase (ver punzonamiento)."
                    ),
                ]
            ),
            code_name="E.060",
            code_reference="§11.12.1.2 (sección crítica a d/2 de las caras de la columna)",
            status=CheckStatus.INFO,
        )
    )

    # --- Profundidad mínima de cimentación (E.050 art. 26.2) ---
    # Requisito sobre un DATO DE ENTRADA: no depende de B, L ni h. Se evalúa aquí
    # para que aparezca en la traza de cada alternativa con su propio estado.
    foundation_depth = check_foundation_depth(soil.Df_m, soil.founded_on_rock)
    trace.add(
        CalculationTraceEntry(
            id="foundation_depth",
            description="Profundidad mínima de cimentación",
            equation_symbolic="Df >= 0,80 m (salvo cimentación sobre roca)",
            equation_substituted=foundation_depth.equation_substituted,
            result_value=foundation_depth.Df_m,
            result_unit="m",
            hypotheses=foundation_depth.hypotheses,
            code_name="E.050",
            code_reference=foundation_depth.code_reference,
            status=foundation_depth.status,
        )
    )
    if foundation_depth.status is CheckStatus.FAIL:
        discard_reasons.append(foundation_depth.message)

    # --- Peralte mínimo (E.060 §15.7, interpretación documentada y configurable) ---
    min_depth_eq = code.min_depth_rule(h_m, d_m, on_soil=True)
    threshold = code.min_depth_threshold_m()
    min_depth_status = CheckStatus.PASS if min_depth_eq.value >= threshold - 1e-9 else CheckStatus.FAIL
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
                "(razonada, no una certeza normativa; configurable en E060ConcreteCode)."
            ],
            code_name="E.060",
            code_reference=min_depth_eq.code_reference,
            status=min_depth_status,
        )
    )
    if min_depth_status is CheckStatus.FAIL:
        discard_reasons.append(
            f"No cumple peralte mínimo E.060 §15.7 (magnitud gobernante {min_depth_eq.value:.3f} m < {threshold:.3f} m)."
        )

    # --- E.050 art. 23.1: la cimentación sigue siendo SUPERFICIAL (H7) -------
    superficial = check_shallow_foundation(soil.Df_m, B_m, L_m)
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
        discard_reasons.append(
            f"Df/B = {superficial.ratio:.2f} > {superficial.limit:.0f}: E.050 art. 23.1 "
            f"define esa cimentación como PROFUNDA, fuera del alcance del programa."
        )

    # --- E.050 art. 23.3: proporción en planta (H6, 2026-09-20) --------------
    # El artículo habla de «Las zapatas y plateas», sin distinguir tipología, y hasta aquí
    # solo la combinada lo verificaba. `max_LB_ratio` es un parámetro de BÚSQUEDA: quien
    # pidiera 15 recibía un cimiento corrido presentado como zapata aislada.
    forma = check_shape_ratio(B_m, L_m)
    trace.add(
        CalculationTraceEntry(
            id="shape_ratio",
            description="Proporción en planta de la zapata",
            equation_symbolic="lado mayor / lado menor <= 10",
            equation_substituted=forma.equation_substituted,
            result_value=forma.ratio,
            result_unit="—",
            hypotheses=[SHAPE_RATIO_READING]
            + ([] if forma.ok else [SHAPE_RATIO_EXCEEDED_NOTE]),
            code_name="E.050",
            code_reference=forma.code_reference,
            status=CheckStatus.PASS if forma.ok else CheckStatus.FAIL,
        )
    )
    if not forma.ok:
        discard_reasons.append(
            f"Proporción {forma.ratio:.2f} > {forma.limit:.0f}: E.050 art. 23.3 clasifica esa "
            f"forma como cimentación continua, no como zapata."
        )

    # --- Flexión, cortante (direcciones X e Y) y punzonamiento (combinaciones FACTORIZADAS) ---
    cants_x = placement.cantilevers_x(B_m)
    cants_y = placement.cantilevers_y(L_m)
    # Un voladizo NULO es válido y frecuente: es la zapata de lindero, con la cara de
    # la columna al ras del borde. Simplemente no hay voladizo que flexionar de ese
    # lado, y el diseño lo gobierna el otro. Lo que no puede admitirse es un voladizo
    # NEGATIVO —la columna sobresaldría de la zapata— ni que AMBOS lados de una
    # dirección sean nulos, porque entonces no hay sección que diseñar.
    if min(*cants_x, *cants_y) < -1e-12:
        raise ValueError(
            f"La columna (bx={column.bx_m}, by={column.by_m}) desplazada "
            f"({placement.offset_x_m:+.3f}, {placement.offset_y_m:+.3f}) m SOBRESALE de la "
            f"zapata (B={B_m}, L={L_m}): voladizos X={cants_x}, Y={cants_y}."
        )
    if max(cants_x) <= 1e-12 or max(cants_y) <= 1e-12:
        raise ValueError(
            f"La zapata (B={B_m}, L={L_m}) no tiene voladizo en alguna dirección frente a la "
            f"columna (bx={column.bx_m}, by={column.by_m}): voladizos X={cants_x}, Y={cants_y}. "
            f"No hay sección de flexión que diseñar."
        )

    def _ecc(c):
        return compute_total_eccentricity(
            c.P_kN, 0.0, c.Mx_kNm, c.My_kNm, placement.offset_x_m, placement.offset_y_m
        )

    demand_x = _worst_directional_demand(
        load_case_set, dim_along_e_m=B_m, cantilevers_m=cants_x, d_m=d_m,
        ecc_selector=lambda c: _ecc(c).ex_m,
        transverse_ecc_selector=lambda c: _ecc(c).ey_m, dim_transverse_m=L_m,
    )
    demand_y = _worst_directional_demand(
        load_case_set, dim_along_e_m=L_m, cantilevers_m=cants_y, d_m=d_m,
        ecc_selector=lambda c: _ecc(c).ey_m,
        transverse_ecc_selector=lambda c: _ecc(c).ex_m, dim_transverse_m=B_m,
    )

    flexure_x = design_flexure(demand_x.Mu_kNm, b_m=L_m, h_m=h_m, d_m=d_m,
                                cantilever_m=demand_x.moment_cantilever_m,
                                fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa, bar_type=steel.bar_type, code=code)
    flexure_y = design_flexure(demand_y.Mu_kNm, b_m=B_m, h_m=h_m, d_m=d_m,
                                cantilever_m=demand_y.moment_cantilever_m,
                                fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa, bar_type=steel.bar_type, code=code)
    shear_x = check_shear_oneway(demand_x.Vu_kN, concrete.fc_MPa, bw_m=L_m, d_m=d_m, code=code)
    shear_y = check_shear_oneway(demand_y.Vu_kN, concrete.fc_MPa, bw_m=B_m, d_m=d_m, code=code)

    # Combinación gobernante de punzonamiento, determinada de forma independiente
    # (punto 5 de la corrección de Fase 2). Vu = Pu*(1 - A_crit/A) es monótona
    # creciente en Pu, así que la combinación de mayor Pu es la que gobierna la
    # RESULTANTE. Los momentos de esa combinación se pasan al check para que
    # pueda declarar si la verificación queda incompleta por §11.12.7.
    governing_punching_combo = max(load_case_set.factored, key=lambda c: c.P_kN)
    ecc_punching = compute_total_eccentricity(
        governing_punching_combo.P_kN, 0.0,
        governing_punching_combo.Mx_kNm, governing_punching_combo.My_kNm,
        placement.offset_x_m, placement.offset_y_m,
    )
    punching_result = check_punching_shear(
        P_u_column_kN=governing_punching_combo.P_kN,
        B_m=B_m, L_m=L_m, bx_m=column.bx_m, by_m=column.by_m, d_m=d_m,
        fc_MPa=concrete.fc_MPa, code=code,
        Mux_kNm=governing_punching_combo.Mx_kNm, Muy_kNm=governing_punching_combo.My_kNm,
        offset_x_m=placement.offset_x_m, offset_y_m=placement.offset_y_m,
        ex_m=ecc_punching.ex_m, ey_m=ecc_punching.ey_m,
    )
    punching_combo_name = governing_punching_combo.name

    for check_id, res, direction_label in (
        ("flexure_x", flexure_x, "X"), ("flexure_y", flexure_y, "Y"),
    ):
        trace.add(
            CalculationTraceEntry(
                id=check_id,
                description=f"Diseño a flexión, dirección {direction_label} (cara de columna)",
                equation_symbolic="As = (0.85 f'c b / fy) * (d - sqrt(d^2 - 2*Mu/(phi*0.85*f'c*b)))",
                equation_substituted=f"Mu={res.Mu_kNm:.2f} kN*m -> As_req={res.As_required_m2*1e4:.2f} cm2, As_min={res.As_min_m2*1e4:.2f} cm2 -> As_diseño={res.As_design_m2*1e4:.2f} cm2 ({res.note})",
                result_value=res.As_design_m2,
                result_unit="m2",
                hypotheses=[res.note],
                governing_combo=demand_x.moment_combo_name if direction_label == "X" else demand_y.moment_combo_name,
                code_name="E.060",
                code_reference=f"§15.4.2 sección crítica, §10.2 hipótesis de diseño, §9.3.2 phi=0.90, As_min: {res.rho_min_reference}",
                status=res.status,
            )
        )
        if res.status is CheckStatus.FAIL:
            discard_reasons.append(f"Flexión {direction_label} no cumple.")

    for check_id, res, direction_label in (
        ("shear_x", shear_x, "X"), ("shear_y", shear_y, "Y"),
    ):
        demanda = demand_x if direction_label == "X" else demand_y
        trace.add(
            CalculationTraceEntry(
                id=check_id,
                description=f"Cortante unidireccional, dirección {direction_label} (a d de la cara de columna)",
                equation_symbolic="phi*Vc = phi*0.17*sqrt(f'c)*bw*d ; PASS si Vu <= phi*Vc",
                equation_substituted=res.equation_substituted,
                result_value=res.ratio,
                result_unit="adimensional (Vu/phiVc)",
                # Una entrada que puede degradar el estado tiene que decir DE DÓNDE sale su
                # demanda: con qué voladizo y por qué lado. Sin eso, un FAIL de cortante no
                # se puede reconstruir desde la traza (auditoría de integridad).
                hypotheses=[
                    f"Sección crítica a d = {d_m:.3f} m de la cara de columna; la referencia "
                    f"normativa de esta entrada es la que gobierna. Voladizo de diseño "
                    f"{demanda.shear_cantilever_m:.3f} m por el lado {demanda.shear_side}, "
                    f"con la combinación {demanda.shear_combo_name}.",
                    "La resistencia es la del CONCRETO SOLO: en zapatas no se dimensiona "
                    "refuerzo de cortante (E.060 §11.5.6.1(a) exime del mínimo).",
                ],
                governing_combo=demand_x.shear_combo_name if direction_label == "X" else demand_y.shear_combo_name,
                code_name="E.060",
                code_reference=res.code_reference,
                status=res.status,
            )
        )
        if res.status is CheckStatus.FAIL:
            discard_reasons.append(f"Cortante unidireccional {direction_label} no cumple.")

    trace.add(
        CalculationTraceEntry(
            id="punching",
            description="Punzonamiento alrededor de la columna",
            equation_symbolic="Vu = Pu - qu*A_crit ; phi*Vc = phi*min(ec.11-41,11-42,11-43) ; PASS si Vu <= phi*Vc",
            equation_substituted=punching_result.equation_substituted,
            result_value=punching_result.ratio,
            result_unit="adimensional (Vu/phiVc)",
            hypotheses=[
                _alpha_s_note(punching_result),
                punching_result.completeness_note,
                AXIS_CONVENTION_NOTE,
            ]
            + (
                [
                    f"Causa del fallo: {punching_result.failure_cause.value} — "
                    f"{PUNCHING_FAILURE_DESCRIPTIONS[punching_result.failure_cause]}."
                ]
                if punching_result.failure_cause is not None
                else []
            ),
            governing_combo=punching_combo_name,
            code_name="E.060",
            code_reference=punching_result.code_reference,
            status=punching_result.status,
        )
    )

    if punching_result.status is CheckStatus.FAIL:
        # Fase 5B, D2. El mensaje lo decide la CAUSA explícita del fallo, fijada en
        # `check_punching_shear` junto al estado. Antes se decidía con
        # `critical_section_fits`, que es False en toda columna de borde o esquina: una
        # zapata de lindero que fallaba por §11.12.7 se reportaba como «no cabe».
        discard_reasons.append(punching_discard_reason(punching_result))

    rebar_x = select_rebar(flexure_x.As_design_m2, width_m=L_m, h_m=h_m)
    rebar_y = select_rebar(flexure_y.As_design_m2, width_m=B_m, h_m=h_m)

    # Alternativas de armado (Fase 4) y distribución en dirección corta (§15.4.4).
    rho_min, _ = code.rho_min_temperature(steel.fy_MPa, steel.bar_type)
    rebar_options_x_raw = generate_rebar_alternatives(
        flexure_x.As_required_m2, flexure_x.As_min_m2, width_m=L_m, h_m=h_m
    )
    rebar_options_y_raw = generate_rebar_alternatives(
        flexure_y.As_required_m2, flexure_y.As_min_m2, width_m=B_m, h_m=h_m
    )

    # La "dirección corta" de §15.4.4 es la paralela al lado corto de la zapata;
    # su acero se reparte a lo ancho del lado largo.
    if B_m >= L_m:
        short_dir_As = flexure_y.As_design_m2  # barras paralelas a Y (lado corto = L)
        short_dir_label = "Y"
    else:
        short_dir_As = flexure_x.As_design_m2
        short_dir_label = "X"
    short_distribution = distribute_short_direction(
        As_total_m2=short_dir_As,
        long_side_m=max(B_m, L_m),
        short_side_m=min(B_m, L_m),
        h_m=h_m,
        rho_min=rho_min,
    )
    trace.add(
        CalculationTraceEntry(
            id="short_direction_distribution",
            description=f"Distribución del refuerzo en la dirección corta ({short_dir_label})",
            equation_symbolic="gamma_s = 2/(beta+1) ; As_franja_central = gamma_s*As_total",
            equation_substituted=(
                f"beta={short_distribution.beta:.4f} -> gamma_s={short_distribution.gamma_s:.4f} | "
                + " | ".join(
                    f"{b.name}: ancho={b.width_m:.2f} m, As={b.As_required_m2 * 1e4:.2f} cm2"
                    + (" (elevado al mínimo §9.7)" if b.topped_up else "")
                    for b in short_distribution.bands
                )
            ),
            result_value=short_distribution.gamma_s,
            result_unit="adimensional",
            hypotheses=[short_distribution.note],
            code_name="E.060",
            code_reference=short_distribution.code_reference,
            status=CheckStatus.PASS,
        )
    )
    for check_id, rebar, direction_label in (("rebar_x", rebar_x, "X"), ("rebar_y", rebar_y, "Y")):
        trace.add(
            CalculationTraceEntry(
                id=check_id,
                description=f"Selección preliminar de acero, dirección {direction_label}",
                equation_symbolic="n_barras = floor(ancho/separación)+1 ; As_prov = n_barras * area_barra",
                equation_substituted=f"{rebar.bar_designation} @ {rebar.spacing_m*100:.1f} cm -> {rebar.n_bars} barras, As_prov={rebar.As_provided_m2*1e4:.2f} cm2 (req {rebar.As_required_m2*1e4:.2f} cm2)",
                result_value=rebar.As_provided_m2,
                result_unit="m2",
                hypotheses=[rebar.note],
                code_name="E.060",
                code_reference="§7.6.1 (separación mínima), §9.7.3 (separación máxima)",
                status=rebar.status,
            )
        )
        if rebar.status is CheckStatus.FAIL:
            discard_reasons.append(f"No se encontró combinación de acero práctica que cumpla As requerido en dirección {direction_label}.")

    # --- L4: geometría real de barras y desarrollo del refuerzo ----------------
    rebar_geometry = build_rebar_geometry(
        B_m=B_m, L_m=L_m, h_m=h_m, bx_m=column.bx_m, by_m=column.by_m, cover_m=cover_m,
        db_x_m=rebar_x.diameter_mm / 1000.0, db_y_m=rebar_y.diameter_mm / 1000.0,
        n_bars_x=rebar_x.n_bars, n_bars_y=rebar_y.n_bars,
        spacing_x_m=rebar_x.spacing_m, spacing_y_m=rebar_y.spacing_m,
        d_used_by_engine_m=d_m,
        hook_x=depth_params.hook_type_x, hook_y=depth_params.hook_type_y,
        # Los voladizos REALES: con la columna descentrada (zapata de lindero) el tramo
        # de desarrollo hacia el lado corto es el ancho de la columna (E.060 §15.6.2).
        cantilevers_x_m=placement.cantilevers_x(B_m),
        cantilevers_y_m=placement.cantilevers_y(L_m),
        # §15.6.2 se verifica en la cara cuyo momento gobierna cada dirección.
        governing_face_x=demand_x.moment_side or None,
        governing_face_y=demand_y.moment_side or None,
    )
    development_x = check_development_length(rebar_geometry.layer_x, steel.fy_MPa, concrete.fc_MPa)
    development_y = check_development_length(rebar_geometry.layer_y, steel.fy_MPa, concrete.fc_MPa)

    # Cada OPCIÓN de armado tiene su propio diámetro y por tanto su propia ld:
    # verificar solo la barra de `select_rebar` dejaría opciones no desarrollables
    # circulando hacia las soluciones de armado (defecto de la auditoría integral).
    rebar_options_x, rejected_options_x = verify_options_development(
        rebar_options_x_raw, rebar_geometry.layer_x, steel.fy_MPa, concrete.fc_MPa
    )
    rebar_options_y, rejected_options_y = verify_options_development(
        rebar_options_y_raw, rebar_geometry.layer_y, steel.fy_MPa, concrete.fc_MPa
    )
    for direction, kept, rejected in (
        ("X", rebar_options_x, rejected_options_x),
        ("Y", rebar_options_y, rejected_options_y),
    ):
        trace.add(
            CalculationTraceEntry(
                id=f"rebar_options_development_{direction.lower()}",
                description=f"Desarrollo verificado en cada opción de armado, dirección {direction}",
                equation_symbolic="ld(db_i) <= ld_disponible para cada opción i",
                equation_substituted=(
                    "aceptadas: "
                    + (", ".join(f"{o.label} (ld={o.ld_required_m * 1000:.0f} mm)" for o in kept) or "ninguna")
                    + " | descartadas por desarrollo: "
                    + (
                        ", ".join(
                            f"{o.label} (ld={o.ld_required_m * 1000:.0f} mm > {o.ld_available_m * 1000:.0f} mm)"
                            for o in rejected
                        )
                        or "ninguna"
                    )
                ),
                result_value=float(len(kept)),
                result_unit="opciones desarrollables",
                hypotheses=[
                    "Cada diámetro se verifica con su propia ld: no se extrapola desde la barra "
                    "seleccionada por select_rebar."
                ],
                code_name="E.060",
                code_reference="§15.6 → Cap. 12",
                status=CheckStatus.PASS if kept else CheckStatus.FAIL,
            )
        )
        if not kept:
            discard_reasons.append(
                f"Ninguna opción de armado en dirección {direction} puede desarrollarse en la "
                f"longitud disponible."
            )
    for check_id, dev in (("development_x", development_x), ("development_y", development_y)):
        trace.add(
            CalculationTraceEntry(
                id=check_id,
                description=f"Longitud de desarrollo del refuerzo, dirección {dev.direction} (capa {dev.layer})",
                equation_symbolic=dev.straight_result.equation_symbolic + "  ;  PASS si ld <= disponible",
                equation_substituted=dev.equation_substituted,
                result_value=dev.utilization,
                result_unit="adimensional (ld_req/ld_disp)",
                hypotheses=[
                    dev.message,
                    f"Ganchos: {'declarados por el usuario (' + dev.hook_type + '°)' if dev.uses_hook else 'NO se asume ningún gancho'}.",
                    rebar_geometry.d_discrepancy_note,
                ],
                code_name="E.060",
                code_reference=dev.code_reference,
                status=dev.status,
            )
        )
        if dev.status is CheckStatus.FAIL:
            discard_reasons.append(
                f"Longitud de desarrollo insuficiente en dirección {dev.direction}: "
                f"faltan {dev.deficit_m * 1000:.0f} mm."
            )

    # --- L3: estabilidad (deslizamiento y volcamiento) --------------------------
    stability = check_stability(
        load_case_set, soil, self_weight.W_total_kN, B_m, L_m, h_m, placement
    )
    for check_id, res, label in (
        ("sliding", stability.sliding, "Deslizamiento"),
        ("overturning_x", stability.overturning_x, "Volcamiento eje X"),
        ("overturning_y", stability.overturning_y, "Volcamiento eje Y"),
    ):
        trace.add(
            CalculationTraceEntry(
                id=check_id,
                description=f"Estabilidad — {label}",
                equation_symbolic=(
                    "FS = (μ·N + c·A) / H" if check_id == "sliding" else "FS = M_estabilizador / M_volcador"
                ),
                equation_substituted=res.equation_substituted,
                result_value=res.FS_obtained if res.FS_obtained is not None else 0.0,
                result_unit="FS",
                hypotheses=[res.message]
                + ([f"Parámetros faltantes: {', '.join(res.missing_parameters)}"] if res.missing_parameters else [])
                + ([res.pivot_description] if hasattr(res, "pivot_description") else [])
                # Cuando el criterio de volteo lo aporta E.030 art. 64.2 y no el
                # proyectista, la interpretación que lo lleva del nivel "estructura"
                # al nivel "zapata" queda declarada, no dada por supuesta.
                + (
                    [E030_OVERTURNING_INTERPRETATION, E030_UNREDUCED_NOTE]
                    if "E.030 art. 64.2" in res.code_reference
                    else []
                )
                # FORMULACION_VOLTEO: el término P·offset es estática y la envolvente es
                # criterio del programa. Se declaran por separado para que no se lean como
                # una sola cosa ni como exigencia normativa.
                + ([ECCENTRICITY_TERM_NOTE, ENVELOPE_NOTE] if check_id != "sliding" else []),
                governing_combo=res.governing_combo,
                code_name="E.030" if "E.030" in res.code_reference else "E.050",
                code_reference=res.code_reference,
                status=res.status,
            )
        )
        if res.status is CheckStatus.FAIL:
            discard_reasons.append(f"{label} no cumple.")

    # --- Limitaciones del motor relevantes para ESTE cálculo -------------------
    # Se emiten al final para que ninguna quede silenciada: si una limitación
    # relevante pudiera hacer pasar por válido un diseño inseguro, degrada el
    # estado global. Ver engine/results/limitations.py.
    for applicable in collect_applicable_limitations(load_case_set, soil):
        lim = applicable.limitation
        if lim.enforced_by is not None:
            continue  # ya la refleja el check nombrado; no se duplica la advertencia
        trace.add(
            CalculationTraceEntry(
                id=f"limitation_{lim.id}",
                description=f"LIMITACIÓN DEL MOTOR — {lim.title} [{lim.kind.value}]",
                equation_symbolic="(sin ecuación: verificación no implementada)",
                equation_substituted=applicable.reason_relevant,
                result_value=0.0,
                result_unit="N/A",
                hypotheses=[lim.description, f"IMPACTO: {lim.impact}"],
                code_name="E.060/E.050",
                code_reference=lim.code_reference,
                status=applicable.status,
            )
        )

    overall_status = CheckStatus.worst([e.status for e in trace.entries])

    return FootingCandidate(
        B_m=B_m, L_m=L_m, h_m=h_m, d_m=d_m,
        self_weight=self_weight,
        eccentricity_governing=ecc_for_report,
        contact_pressure=contact_result,
        min_depth_status=min_depth_status,
        flexure_x=flexure_x, flexure_y=flexure_y,
        shear_x=shear_x, shear_y=shear_y,
        punching=punching_result,
        rebar_x=rebar_x, rebar_y=rebar_y,
        rebar_options_x=rebar_options_x, rebar_options_y=rebar_options_y,
        short_direction=short_distribution,
        rebar_geometry=rebar_geometry,
        development_x=development_x, development_y=development_y,
        stability=stability,
        governing_combos=GoverningCombos(
            contact_pressure=contact_combo,
            flexure_x=demand_x.moment_combo_name, flexure_y=demand_y.moment_combo_name,
            shear_x=demand_x.shear_combo_name, shear_y=demand_y.shear_combo_name,
            punching=punching_combo_name,
        ),
        overall_status=overall_status,
        discard_reasons=discard_reasons,
        trace=trace,
    )


class DepthSolverResult(BaseModel):
    B_m: float
    L_m: float
    trials: list[DepthTrialResult]
    accepted: FootingCandidate | None
    last_evaluated: FootingCandidate | None = None
    pruned_early: bool = False
    prune_reason: str | None = None


def _bearing_is_hopeless(candidate: FootingCandidate, qadm_kPa: float) -> bool:
    """¿Aumentar h puede llegar a salvar la presión de contacto de esta geometría?

    NO, cuando la resultante ya cae dentro del núcleo y aun así qmax > qadm:

        qmax = P_total/A + 6*M/(A*B)

    El segundo término no depende de P_total, y P_total crece monótonamente con h
    (dW/dh = B*L*(gamma_concreto - gamma_suelo) > 0 mientras h < Df, y
    dW/dh = B*L*gamma_concreto > 0 cuando h >= Df; siempre positivo porque el
    concreto pesa más que el suelo). Por lo tanto qmax solo puede empeorar.

    SÍ puede salvarse, en cambio, cuando la falla es por estar FUERA del núcleo:
    ahí e = M/P_total sí disminuye al crecer P_total, de modo que un h mayor puede
    devolver la resultante al núcleo. Ese caso NO se poda.
    """
    return candidate.contact_pressure.within_kern and candidate.contact_pressure.qmax_kPa > qadm_kPa


def solve_depth(
    B_m: float,
    L_m: float,
    column: Column,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    load_case_set: LoadCaseSet,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    depth_params: DepthSearchParameters,
    placement: ColumnPlacement | None = None,
) -> DepthSolverResult:
    """Prueba h desde h_min hasta h_max en pasos de h_step; se detiene en el
    primer h que resulta PASS. Devuelve también el historial completo de h
    probados y el último candidato evaluado (necesario para explicar el descarte
    cuando ningún h cumple)."""
    trials: list[DepthTrialResult] = []
    accepted: FootingCandidate | None = None
    last_evaluated: FootingCandidate | None = None
    pruned_early = False
    prune_reason: str | None = None

    h = depth_params.h_min_m
    while h <= depth_params.h_max_m + 1e-9:
        candidate = evaluate_candidate(
            B_m, L_m, round(h, 6), column, soil, concrete, steel, load_case_set, code, contact_model,
            depth_params, placement,
        )
        last_evaluated = candidate
        trials.append(
            DepthTrialResult(
                h_m=candidate.h_m, d_m=candidate.d_m,
                overall_status=candidate.overall_status,
                discard_reasons=candidate.discard_reasons,
            )
        )
        # Un WARNING NO invalida el diseño: señala una condición que requiere
        # revisión del ingeniero (definición acordada de los tres estados). Solo
        # FAIL descarta. De lo contrario, una verificación incompleta como el
        # punzonamiento con transferencia de momento (§11.12.7, no implementado)
        # impediría aceptar cualquier alternativa con momentos.
        if candidate.overall_status is not CheckStatus.FAIL:
            accepted = candidate
            break
        if _bearing_is_hopeless(candidate, soil.qadm_kPa):
            pruned_early = True
            prune_reason = (
                f"Búsqueda de h interrumpida en h={candidate.h_m:.2f} m: la presión de contacto ya "
                f"excede qadm con la resultante dentro del núcleo, y un h mayor solo agrega peso "
                f"propio (qmax aumenta monótonamente con h). Ningún h del rango puede cumplir."
            )
            break
        h += depth_params.h_step_m

    if accepted is not None:
        accepted.depth_trials = trials
    return DepthSolverResult(
        B_m=B_m, L_m=L_m, trials=trials, accepted=accepted,
        last_evaluated=last_evaluated, pruned_early=pruned_early, prune_reason=prune_reason,
    )


def _alpha_s_note(punching_result) -> str:
    """Nota de α_s según la clasificación REAL de la sección crítica — Fase 4H.

    Antes decía siempre «columna interior», también en zapatas de lindero con α_s = 30.
    Es texto de traza: no interviene en ningún cálculo ni en el congelamiento."""
    pos = punching_result.column_position
    alpha = punching_result.alpha_s
    if pos == "interior":
        return (
            f"alpha_s={alpha:.0f} (columna interior: la sección crítica se cierra por los "
            f"cuatro lados)."
        )
    if pos in ("borde", "esquina"):
        recortados = 4 - punching_result.critical_section_sides
        return (
            f"alpha_s={alpha:.0f} (columna de {pos}: la sección crítica queda recortada por "
            f"{recortados} lado(s) y conserva {punching_result.critical_section_sides}; "
            f"clasificación declarada, E.060 §11.12.2.1(b))."
        )
    return (
        "alpha_s no aplicable (sección crítica degenerada: recortada por 3 o 4 lados, sin "
        "categoría en E.060 §11.12.2.1(b))."
    )
