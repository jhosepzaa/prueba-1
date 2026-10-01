"""Solver de zapata conectada — Fase 4B.

QUÉ HACE Y QUÉ NO HACE
======================
Este módulo **orquesta**. No calcula flexión, ni cortante, ni punzonamiento, ni
acero mínimo, ni selecciona barras: todo eso ya existe y se llama tal cual.

    evaluate_candidate()     -> las dos zapatas, con los artículos de zapata aislada
    design_connecting_beam() -> la viga, con §21.12.3, §10.5, §11.5 y E.030 art. 65.1
    correct_loads()          -> el reparto del par, único cálculo propio de la fase
    solve_connecting_beam()  -> los diagramas de la viga, que no son los de una zapata

Si alguna vez hiciera falta un número que ninguno de esos cuatro produce, el que
tiene que cambiar es el motor correspondiente, no este archivo.

POR QUÉ LOS MOTORES EXISTENTES NO SE ENTERAN DE NADA
====================================================
El paso de estática entrega dos `LoadCaseSet` CORREGIDOS. Con ellos,
`evaluate_candidate` recibe lo que siempre recibió y no sabe que las cargas vienen
de un sistema conectado. La presión uniforme bajo la zapata exterior tampoco
necesita un modelo de contacto nuevo: sale de que la carga corregida lleva momento
nulo en el eje longitudinal, porque ese momento ya se transfirió al par.

LA CONDICIÓN DE BORDE SE MANTIENE DURANTE EL BARRIDO
====================================================
El `ColumnPlacement` de la zapata exterior se DERIVA de `EdgeAnchor` para cada
geometría. No se guarda un desplazamiento fijo: al variar B, un desplazamiento
constante despegaría la columna del lindero y describiría otra estructura.

ESTADO DEL SISTEMA
==================
El peor de los tres componentes, más las entradas de ámbito «sistema». Una viga en
FAIL invalida el conjunto aunque ambas zapatas cumplan.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.analysis.connected_statics import (
    BEAM_SUPPORT_NOTES,
    BEAM_SELF_WEIGHT_FACTOR_DECLARED,
    BEAM_SELF_WEIGHT_FACTORING_PENDING,
    COUPLE_TRANSFER_NOTES,
    FILL_OVER_SPAN_PENDING,
    RIGID_BODY_PREMISE,
    STIFFNESS_DECLARED_NOTE,
    STIFFNESS_NOT_DECLARED_NOTE,
    UNIFORM_PRESSURE_NOT_A_CODE_CHECK,
    UPLIFT_NOT_SOLVED,
    UNIFORM_PRESSURE_PREMISE,
    BeamAxisGeometry,
    CorrectedLoads,
    CoupleDistribution,
    beam_axis_geometry,
    beam_self_weight_note,
    correct_loads,
)
from engine.analysis.connecting_beam_statics import (
    ConnectingBeamStatics,
    solve_connecting_beam,
)
from engine.beam.beam_trace import build_beam_trace
from engine.beam.connecting_beam import (
    ConnectingBeamResult,
    SeismicContext,
    design_connecting_beam,
)
from engine.codes.base import IConcreteCode
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectedFootingLayout,
    CoupleTransferMode,
    LongitudinalAxis,
    StiffnessDeclaration,
)
from engine.domain.loads import LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.calculation_trace import CalculationTrace, CalculationTraceEntry
from engine.results.footing_candidate import FootingCandidate
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import ContactPressureModel
from engine.soil.foundation_depth import check_foundation_depth

SCOPE_SYSTEM = "sistema"
SCOPE_EXTERIOR = "zap_ext"
SCOPE_INTERIOR = "zap_int"
SCOPE_BEAM = "viga"

M2_TO_CM2 = 1e4


class ConnectedFootingGeometry(BaseModel):
    """Las dos geometrías del sistema. Se pasan juntas porque están acopladas: la
    longitud de la zapata exterior decide el par, que decide la carga de la interior."""

    exterior_B_m: float = Field(..., gt=0)
    exterior_L_m: float = Field(..., gt=0)
    exterior_h_m: float = Field(..., gt=0)
    interior_B_m: float = Field(..., gt=0)
    interior_L_m: float = Field(..., gt=0)
    interior_h_m: float = Field(..., gt=0)


class ConnectedFootingResult(BaseModel):
    geometry: ConnectedFootingGeometry

    exterior: FootingCandidate
    interior: FootingCandidate
    beam: ConnectingBeamResult

    statics: list[CoupleDistribution]
    beam_statics: list[ConnectingBeamStatics]
    governing_beam_combo: str

    trace: CalculationTrace
    overall_status: CheckStatus
    discard_reasons: list[str]

    longitudinal_axis: LongitudinalAxis = Field(
        ...,
        description=(
            "Eje sobre el que corre la viga. Viaja en el resultado porque las "
            "dimensiones en planta del sistema dependen de él y el resultado se "
            "consume (métricas, informe) sin el `layout` al lado."
        ),
    )
    beam_axis: BeamAxisGeometry = Field(
        ...,
        description=(
            "Fase 9b. Posición física de la viga sobre el eje (c_e, L1, f_i, c_i) y su z_b "
            "declarada. Viaja en el resultado por la misma razón que `longitudinal_axis`: "
            "el vano libre y las métricas se calculan sin el `layout` al lado."
        ),
    )

    # -------------------------------------------------------------------
    # TRES CONCEPTOS QUE NO SON EL MISMO
    # -------------------------------------------------------------------
    # 1. `implemented_checks_status` — de lo que este motor SABE comprobar, ¿algo sale
    #    mal? Es el único de los tres que habla de verificaciones.
    # 2. `open_tbds` — ¿qué pendientes impiden pronunciarse? No son comprobaciones que
    #    fallen: son comprobaciones que no existen.
    # 3. `overall_status` — el estado que llega al informe, y que mientras haya un
    #    pendiente abierto NO puede ser PASS.
    #
    # Confundir 1 con 3 es exactamente el error que el encargo prohíbe: presentar como
    # conforme algo que depende de una funcionalidad no implementada. Confundir 3 con
    # «rechazado» es el error contrario, y dejaría la tipología inutilizable.

    @property
    def open_tbds(self) -> list[str]:
        """Pendientes abiertos que impiden verificar este sistema, p.ej. ["TBD-C1"]."""
        return self.trace.open_tbds()

    @property
    def implemented_checks_status(self) -> CheckStatus:
        """Peor estado de las verificaciones IMPLEMENTADAS, ignorando los pendientes.

        NO es «cumple»: un sistema puede tener aquí PASS y seguir siendo NO VERIFICADO
        porque TBD-C1 no tiene criterio que aplicar. Sirve para responder una pregunta
        distinta —¿hay algo mal en lo que sí se comprobó?— y para que el informe pueda
        decir las dos cosas por separado en vez de fundirlas en una sola etiqueta."""
        return CheckStatus.worst(
            [e.status for e in self.trace.entries if not e.open_tbd]
            + [self.exterior.overall_status, self.interior.overall_status, self.beam.status]
        )

    @property
    def blocked_only_by_open_tbd(self) -> bool:
        """Todo lo comprobable salió bien y lo único que queda es un pendiente abierto.

        Es la situación NORMAL de la zapata conectada hoy: mientras TBD-C1 siga abierto,
        el mejor resultado posible es este. No autoriza a informar «cumple»."""
        return bool(self.open_tbds) and not self.implemented_checks_status.discards             and self.implemented_checks_status in (CheckStatus.PASS, CheckStatus.INFO)

    @property
    def L1_m(self) -> float:
        """Longitud de la zapata exterior sobre el eje longitudinal."""
        return self.statics[0].L1_m if self.statics else 0.0

    @property
    def system_length_m(self) -> float:
        """Longitud que ocupa el sistema, del lindero al borde exterior de la zapata
        interior. Es la dimensión en planta que hay que comparar entre alternativas: la
        de una sola zapata no dice nada del conjunto."""
        if not self.statics:
            return 0.0
        d = self.statics[0]
        # La dimensión de la zapata interior QUE CORRE A LO LARGO DE LA VIGA: es
        # `interior_B_m` con la viga sobre X y `interior_L_m` con la viga sobre Y.
        # Tomar siempre B daría, en un sistema sobre Y, la dimensión transversal.
        longitudinal = (
            self.geometry.interior_B_m
            if self.longitudinal_axis == "X"
            else self.geometry.interior_L_m
        )
        return d.s_cut_m + longitudinal / 2.0

    @property
    def beam_span_m(self) -> float:
        """Vano LIBRE físico de la viga: f_i − L1, del borde de la huella exterior al
        borde de la huella interior (Fase 9b).

        Es geometría, igual en todos los modelos. Hasta 9b valía `s_corte − s_inicio` del
        tramo de diseño: s_corte − L1 en EQUILIBRIO y CUERPO_RIGIDO, y s_corte − a (la
        distancia entre ejes) en PAR_PURO. `s_corte` es la rótula, no un borde de la viga.

        Ya NO es la longitud de metrado: las métricas usan `beam_axis` completa
        (`connected_metrics.beam_volume_breakdown`)."""
        return self.beam_axis.clear_span_m


def _longitudinal_length(layout: ConnectedFootingLayout, B_m: float, L_m: float) -> float:
    """La dimensión de la zapata que corre a lo largo de la viga."""
    return B_m if layout.longitudinal_axis == "X" else L_m


# Verificaciones que pertenecen al SISTEMA y no a cada componente. Cada zapata las
# emite por su cuenta —no sabe que forma parte de un sistema—, pero repetirlas
# llenaría el informe de entradas idénticas y triplicaría el motivo de descarte de un
# dato único. Se emiten una vez en ámbito "sistema" y se filtran de los componentes.
_SYSTEM_LEVEL_IDS = frozenset({"foundation_depth"})


def _scoped(trace: CalculationTrace, source: CalculationTrace, scope: str) -> None:
    """Copia una traza ajena marcándole el ámbito. No la recalcula ni la reordena."""
    for e in source.entries:
        if e.id in _SYSTEM_LEVEL_IDS:
            continue
        trace.add(e.model_copy(update={"scope": scope}))


def _system_trace(
    layout: ConnectedFootingLayout,
    corrected: CorrectedLoads,
    beam_statics: list[ConnectingBeamStatics],
    soil: SoilProfile,
) -> tuple[CalculationTrace, list[str]]:
    """Entradas de ámbito «sistema»: lo que no pertenece a ningún componente."""
    trace = CalculationTrace()
    motivos: list[str] = []

    # Varias entradas dependen del modelo declarado: la premisa de rigidez cambia de
    # forma y TBD-C11 solo tiene sentido en el modelo articulado.
    articulado = layout.analysis_model is AnalysisModel.ARTICULADO
    par_puro = (
        articulado
        and layout.couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA
    )

    trace.add(
        CalculationTraceEntry(
            id="analysis_model",
            scope=SCOPE_SYSTEM,
            description=(
                "Modelo de análisis de la zapata conectada, declarado por el usuario."
            ),
            equation_symbolic="ARTICULADO | CUERPO_RIGIDO",
            equation_substituted=f"Modelo adoptado: {layout.analysis_model.value}",
            result_value=0.0,
            result_unit="—",
            hypotheses=[
                "Ni E.050, ni E.060, ni E.030 dicen cuál de los dos modelos corresponde. La "
                "elección depende de la magnitud de los momentos de la columna interior, y "
                "«momentos considerables» no está definido en ninguna de las tres. El "
                "programa NO lo elige: lo declara el ingeniero y queda registrado aquí.",
            ],
            code_name="N/A (criterio de modelación)",
            code_reference="Sin respaldo normativo: es una decisión del proyectista",
            status=CheckStatus.INFO,
        )
    )

    # --- E.050 art. 26.2, una sola vez para el sistema -----------------------
    # Las dos zapatas comparten Df, de modo que verificarlo por zapata lo repetiría.
    fd = check_foundation_depth(soil.Df_m, soil.founded_on_rock)
    trace.add(
        CalculationTraceEntry(
            id="foundation_depth",
            scope=SCOPE_SYSTEM,
            description="Profundidad mínima de cimentación, común a las dos zapatas",
            equation_symbolic="Df >= 0,80 m (salvo cimentación sobre roca)",
            equation_substituted=fd.equation_substituted,
            result_value=fd.Df_m,
            result_unit="m",
            hypotheses=fd.hypotheses,
            code_name="E.050",
            code_reference=fd.code_reference,
            status=fd.status,
        )
    )
    if fd.status is CheckStatus.FAIL:
        motivos.append(fd.message)

    # --- Reparto del par, combinación a combinación --------------------------
    for d in corrected.distributions:
        trace.add(
            CalculationTraceEntry(
                id=f"couple_{d.combo_name}",
                scope=SCOPE_SYSTEM,
                description=(
                    f"Reparto del par en la combinación «{d.combo_name}»: equilibrio del "
                    f"cuerpo libre {{zapata exterior + viga}} cortado en el eje de la columna "
                    f"interior."
                ),
                equation_symbolic=(
                    "ΣF_v = 0 y ΣM = 0 sobre el cuerpo libre; en el corte hay rótula, "
                    "de modo que el momento interno allí es nulo"
                ),
                equation_substituted=d.equation_substituted,
                result_value=d.delta_P_kN,
                result_unit="kN",
                hypotheses=list(d.hypotheses),
                governing_combo=d.combo_name,
                code_name="N/A (estática)",
                code_reference=(
                    "Sin artículo: E.060 §15.10 cubre zapatas que soportan MÁS DE UNA columna, "
                    "y aquí hay dos zapatas de una columna cada una. Derivación declarada."
                ),
                status=CheckStatus.INFO,
            )
        )
        if not d.closes:
            motivos.append(
                f"El equilibrio de la combinación «{d.combo_name}» no cierra: residuos "
                f"ΣFv = {d.residual_force_kN:.3e} kN, ΣM = {d.residual_moment_kNm:.3e} kN·m."
            )

    # --- La premisa de §15.2.6, y quién responde por ella --------------------
    #
    # Decisión 4 (2026-09-20). La pregunta que plantea §15.2.6 es normativa y su criterio
    # no está en ninguna fuente: el motor no puede responderla. Lo que sí puede es
    # registrar quién la responde. Sin declaración sigue en NO VERIFICADO, como siempre;
    # con ella pasa a INFO y la responsabilidad queda escrita en la traza.
    declarada = (
        layout.beam.stiffness_declaration
        is StiffnessDeclaration.DECLARADA_POR_PROYECTISTA
    )
    premisa = UNIFORM_PRESSURE_PREMISE if articulado else RIGID_BODY_PREMISE
    trace.add(
        CalculationTraceEntry(
            id="uniform_pressure_premise" if articulado else "rigid_body_premise",
            scope=SCOPE_SYSTEM,
            description=(
                "Premisa de presión uniforme bajo la zapata exterior, sostenida por la "
                "rigidez de la viga de conexión."
                if articulado
                else "Premisa de que el conjunto gira como un solo cuerpo rígido."
            ),
            equation_symbolic=(
                "E.060 §15.2.6 exige evaluar la rigidez; no prescribe criterio con que hacerlo"
            ),
            equation_substituted=(
                "Supuesto: la viga impide el giro de la zapata de lindero -> la resultante "
                "pasa por su centroide -> la presión es uniforme. Lo verificable de esa "
                "cadena es la geometría; la RIGIDEZ no la cuantifica ninguna norma. "
                + (
                    "Declaración del proyectista: el modelo adoptado satisface §15.2.6."
                    if declarada
                    else "Sin declaración del proyectista."
                )
            ),
            result_value=0.0,
            result_unit="—",
            hypotheses=(
                [premisa, STIFFNESS_DECLARED_NOTE, UNIFORM_PRESSURE_NOT_A_CODE_CHECK]
                if declarada
                else [premisa, STIFFNESS_NOT_DECLARED_NOTE, UNIFORM_PRESSURE_NOT_A_CODE_CHECK]
            ),
            code_name="N/A (hipótesis de modelación)",
            code_reference=(
                "E.060 §15.2.6 (manda evaluar la rigidez de las vigas de conexión y la del "
                "conjunto suelo-cimentación, sin prescribir método ni umbral); §21.12.3.2 "
                "verifica la DIMENSIÓN mínima de la viga y figura aparte, en la traza de la "
                "viga, con su propio PASS/FAIL"
            ),
            status=CheckStatus.INFO if declarada else CheckStatus.NOT_VERIFIED,
            open_tbd=None if declarada else "TBD-C1",
        )
    )

    # --- TBD-C11: destino de la rama cercana del par -------------------------
    # Solo tiene sentido en el modelo ARTICULADO. En cuerpo rígido el conjunto es UN
    # cuerpo y su equilibrio cierra globalmente: la pregunta no se plantea.
    trace.add(
        CalculationTraceEntry(
            id="couple_transfer_mode",
            scope=SCOPE_SYSTEM,
            description="¿Dónde va la rama cercana del par que reparte la viga?",
            equation_symbolic="EQUILIBRIO_EN_CIMENTACION | PAR_PURO_EN_ZAPATA",
            equation_substituted=(
                f"Modo declarado: {layout.couple_transfer_mode.value}"
                + (
                    ""
                    if articulado
                    else " — único modo admitido en cuerpo rígido: la cimentación "
                    "cierra su equilibrio sola por construcción, y PAR_PURO_EN_ZAPATA "
                    "se rechaza por incompatible"
                )
            ),
            result_value=(
                corrected.distributions[0].expected_residual_kN
                if corrected.distributions else 0.0
            ),
            result_unit="kN que no llegan al suelo",
            hypotheses=[
                COUPLE_TRANSFER_NOTES[layout.couple_transfer_mode] if articulado
                else (
                    "En el modelo de cuerpo rígido el conjunto se equilibra globalmente "
                    "por construcción: no hay ninguna rama del par que pueda quedar fuera "
                    "de la cimentación, y el modo declarado no interviene."
                )
            ],
            code_name="N/A (criterio de modelación)",
            code_reference="Sin respaldo normativo: E.060 no tiene artículo para la conectada",
            status=CheckStatus.NOT_VERIFIED if par_puro else CheckStatus.INFO,
            open_tbd="TBD-C11" if par_puro else None,
        )
    )
    if par_puro:
        motivos.append(
            "TBD-C11: con PAR_PURO_EN_ZAPATA la carga vertical no se cierra dentro de la "
            "cimentación. Que el pórtico recoja la rama cercana del par es una hipótesis "
            "sobre la superestructura que este motor no comprueba, y deja la zapata "
            "interior más aliviada."
        )

    # --- Modelo de cuerpo rígido: presiones y despegue -----------------------
    if not articulado:
        for d in corrected.distributions:
            trace.add(
                CalculationTraceEntry(
                    id=f"rigid_pressure_{d.combo_name}",
                    scope=SCOPE_SYSTEM,
                    description=(
                        f"Presión del conjunto como cuerpo rígido, combinación "
                        f"«{d.combo_name}»: las dos huellas tratadas como una sección."
                    ),
                    equation_symbolic="σ = P/A ± M·y/I sobre el área de apoyo",
                    equation_substituted=d.equation_substituted,
                    result_value=d.sigma_min_kPa if d.sigma_min_kPa is not None else 0.0,
                    result_unit="kPa",
                    hypotheses=list(d.hypotheses),
                    governing_combo=d.combo_name,
                    code_name="N/A (estática)",
                    code_reference=(
                        "Sin artículo. E.060 §15.2 sí prohíbe considerar tracciones, y es "
                        "lo que obliga a detectar el despegue"
                    ),
                    status=CheckStatus.FAIL if d.uplift else CheckStatus.INFO,
                )
            )
            if d.uplift:
                motivos.append(
                    f"DESPEGUE en la combinación «{d.combo_name}»: la presión mínima "
                    f"resulta {d.sigma_min_kPa:.2f} kPa. E.060 §15.2 prohíbe considerar "
                    f"tracciones y el campo lineal deja de valer; el caso exige contacto "
                    f"parcial, fuera del alcance de este motor."
                )

    # --- TBD-C5: peso propio de la viga --------------------------------------
    # Se registra SIEMPRE, incluso cuando se desprecia. Un peso que no aparece en
    # ninguna parte y del que la memoria no dice nada es indistinguible de un olvido.
    modo_pp = layout.beam.self_weight_mode
    W_viga = corrected.distributions[0].beam_self_weight_kN if corrected.distributions else 0.0
    # Fase 9a: el desglose es geométrico, idéntico en todas las combinaciones.
    bw = corrected.distributions[0].beam_self_weight_breakdown if corrected.distributions else None
    hipotesis_pp = [
        beam_self_weight_note(layout, bw),
        "El motor de zapata calcula el peso propio de cada ZAPATA por su cuenta; "
        "el de la VIGA no lo calcula nadie más. Por eso el modo es una declaración "
        "obligatoria: sin ella, el peso quedaría fuera del cálculo sin constancia.",
    ]
    motivos_pp: list[str] = []
    if bw is not None:
        sin_contacto = [
            nombre for nombre, toca in (
                (layout.exterior.label, bw.exterior_contact),
                (layout.interior.label, bw.interior_contact),
            ) if not toca
        ]
        if sin_contacto:
            motivos_pp.append(
                f"Peso propio de viga: con z_b = {bw.soffit_above_base_m:.3f} m el fondo de la "
                f"viga queda por encima de la cara superior de {', '.join(sin_contacto)}. Ese "
                f"tramo no descansa sobre la zapata y su camino de carga no es el modelado."
            )
        if bw.fill_over_span:
            hipotesis_pp.append(FILL_OVER_SPAN_PENDING)
            motivos_pp.append(
                f"Peso propio de viga: la cara superior de la viga (z_t = "
                f"{bw.top_above_base_m:.3f} m) queda bajo el nivel de desplante y el relleno "
                f"sobre ella en el vano libre no está incluido (pendiente de la Fase 9a)."
            )
    # TBD-C13 (decisión A′): el factor de CM del peso propio de la viga en las combinaciones
    # FACTORIZADAS del modo directo es un DATO DEL PROYECTISTA. Declarado, se aplica y se
    # traza. Sin declarar, el peso entra sin amplificar y la entrada queda NO VERIFICADA:
    # es la misma regla que el proyecto ya usa con μ (E.020 art. 22.2).
    sin_factorizar = [
        d for d in corrected.distributions
        if d.combo_type == "FACTORIZADA"
        and d.beam_self_weight_breakdown is not None
        and d.beam_self_weight_breakdown.load_factor is None
    ]
    if sin_factorizar:
        hipotesis_pp.append(BEAM_SELF_WEIGHT_FACTORING_PENDING)
        motivos_pp.append(
            f"Peso propio de viga: falta el factor de carga muerta para las combinaciones "
            f"factorizadas del modo directo ({', '.join(d.combo_name for d in sin_factorizar)}). "
            f"Declare `beam.self_weight_dead_load_factor` o use el modo de cargas por casos "
            f"(TBD-C13)."
        )
    elif layout.beam.self_weight_dead_load_factor is not None:
        hipotesis_pp.append(
            BEAM_SELF_WEIGHT_FACTOR_DECLARED.format(f=layout.beam.self_weight_dead_load_factor)
        )
    trace.add(
        CalculationTraceEntry(
            id="beam_self_weight_mode",
            scope=SCOPE_SYSTEM,
            description="Tratamiento del peso propio de la viga de conexión",
            equation_symbolic=(
                "EXPLICITO | EN_CARGAS_DE_COLUMNA | DESPRECIADO; con EXPLICITO "
                "W = ΔW_e + W_V + ΔW_i por geometría física"
            ),
            equation_substituted=(
                f"Modo declarado: {modo_pp.value}"
                + (f" -> W = {W_viga:.2f} kN en el equilibrio" if W_viga else " -> W = 0 en el equilibrio")
                + (
                    f" = ΔW_e {bw.exterior_increment_kN:.3f} + W_V {bw.span_kN:.3f} + ΔW_i "
                    f"{bw.interior_increment_kN:.3f} kN (z_b = {bw.soffit_above_base_m:.3f} m)"
                    if bw is not None else ""
                )
            ),
            result_value=W_viga,
            result_unit="kN",
            hypotheses=hipotesis_pp + motivos_pp,
            code_name="N/A (criterio de modelación)",
            code_reference="Sin respaldo normativo: ni E.060 ni E.050 lo prescriben",
            # NO VERIFICADO sin `open_tbd`: no falta un criterio normativo, falta
            # funcionalidad (relleno sobre el vano, viga sin contacto con una zapata).
            status=CheckStatus.NOT_VERIFIED if motivos_pp else CheckStatus.INFO,
        )
    )
    motivos.extend(motivos_pp)

    # --- TBD-C4: apoyo de la viga sobre el terreno ---------------------------
    modo_apoyo = layout.beam.support_mode
    apoya = modo_apoyo is BeamSupportMode.APOYA_EN_SUELO
    trace.add(
        CalculationTraceEntry(
            id="beam_support_mode",
            scope=SCOPE_SYSTEM,
            description="¿Transmite la viga de conexión presión al terreno?",
            equation_symbolic="SIN_APOYO | APOYA_EN_SUELO",
            equation_substituted=(
                f"Modo declarado: {modo_apoyo.value}"
                + (
                    " -> la reacción del terreno bajo la viga NO está modelada"
                    if apoya
                    else " -> el tramo entre zapatas salva el vano sin apoyo"
                )
            ),
            result_value=0.0,
            result_unit="—",
            hypotheses=[BEAM_SUPPORT_NOTES[modo_apoyo]],
            code_name="N/A (criterio de modelación)",
            code_reference="Sin respaldo normativo: depende de cómo se construya",
            status=CheckStatus.NOT_VERIFIED if apoya else CheckStatus.INFO,
            open_tbd="TBD-C4" if apoya else None,
        )
    )
    if apoya:
        motivos.append(
            "TBD-C4: se declaró que la viga apoya sobre el terreno y esa reacción no está "
            "modelada. La zapata interior puede quedar sobrestimada del lado inseguro."
        )

    # --- Diagramas de la viga ------------------------------------------------
    #
    # CONTRASTE DEL MOMENTO DE JUNTA — Fase 5A, D3
    # El diagrama de la viga se integra desde las cargas; el reparto calcula el momento
    # en el eje interior por su cuenta, sobre el mismo cuerpo. Si no coinciden, uno de
    # los dos describe otro cuerpo y la viga se estaría diseñando con esfuerzos que no
    # cumplen el equilibrio del modelo declarado.
    #
    # Hasta 5A `cut_moment_consistent` se calculaba y nadie lo leía: salía False en
    # cinco de los casos congelados sin que nada lo reflejara. Ahora decide el estado
    # de esta entrada. Se usa FAIL y no NO VERIFICADO porque no es un criterio que
    # falte: es la estática del propio motor que no cierra, y aceptar la alternativa
    # dejaría pasar una viga diseñada con esfuerzos incoherentes. Sigue el precedente
    # del cierre del reparto, unas líneas más arriba.
    #
    # No se añade una entrada nueva: la existente cambia de INFO fijo a INFO o FAIL, de
    # modo que los casos consistentes no cambian de traza.
    for bs in beam_statics:
        consistente = bs.cut_moment_consistent
        trace.add(
            CalculationTraceEntry(
                id=f"beam_statics_{bs.combo_name}",
                scope=SCOPE_SYSTEM,
                description=(
                    f"Diagramas V(s) y M(s) de la viga de conexión en la combinación "
                    f"«{bs.combo_name}», contrastados con el momento del reparto."
                ),
                equation_symbolic=(
                    "V(s) = Σ F_up a la izquierda; M(s) = Σ F_up·(s − s_i) a la izquierda; "
                    "M(s_corte) del diagrama = M_corte del reparto"
                ),
                equation_substituted=(
                    f"{bs.equation_substituted} | contraste: diagrama "
                    f"{bs.M_at_cut_kNm:.3f} kN·m frente a reparto "
                    f"{bs.M_cut_declared_kNm:.3f} kN·m -> "
                    + ("coinciden" if consistente else "NO COINCIDEN")
                ),
                result_value=bs.M_max_negative_kNm,
                result_unit="kN·m",
                hypotheses=list(bs.hypotheses),
                governing_combo=bs.combo_name,
                code_name="N/A (estática)",
                code_reference="Derivación declarada; el diseño de la sección sigue §21.12.3",
                status=CheckStatus.INFO if consistente else CheckStatus.FAIL,
            )
        )
        if not consistente:
            motivos.append(
                f"[viga] La estática de la viga no cierra en la combinación "
                f"«{bs.combo_name}»: el diagrama da {bs.M_at_cut_kNm:.3f} kN·m en el eje "
                f"de la columna interior y el reparto {bs.M_cut_declared_kNm:.3f} kN·m. "
                f"La viga no puede diseñarse con esfuerzos que no cumplen el equilibrio "
                f"del modelo declarado."
            )

    return trace, motivos


def solve_connected_footing(
    layout: ConnectedFootingLayout,
    geometry: ConnectedFootingGeometry,
    *,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    depth_params: DepthSearchParameters,
    seismic: SeismicContext | None = None,
    longitudinal_db_mm: float = 25.4,
    stirrup_diameter_mm: float = 9.525,
    n_legs: int = 2,
) -> ConnectedFootingResult:
    """Resuelve el sistema completo para una terna (exterior, viga, interior)."""
    L1 = _longitudinal_length(layout, geometry.exterior_B_m, geometry.exterior_L_m)

    anchor = layout.exterior.anchor
    if not anchor.fits_in(layout.exterior.column, geometry.exterior_B_m, geometry.exterior_L_m):
        raise ValueError(
            f"La columna {layout.exterior.label} no cabe en la zapata "
            f"{geometry.exterior_B_m:.2f} × {geometry.exterior_L_m:.2f} m manteniendo la "
            f"holgura de {anchor.face_clearance_m:.3f} m al borde {anchor.edge}."
        )

    # --- 1. Estática: el único cálculo propio de esta fase -------------------
    # F1 — el contrato lleva las DOS huellas. La estrategia articulada solo usa la
    # exterior; la de cuerpo rígido necesita ambas, porque el área de apoyo, su
    # centroide y su inercia dependen de las dos.
    footprints = layout.footprints(
        geometry.exterior_B_m, geometry.exterior_L_m, geometry.exterior_h_m,
        geometry.interior_B_m, geometry.interior_L_m, geometry.interior_h_m,
    )
    eje_viga = beam_axis_geometry(layout, footprints)
    corrected = correct_loads(
        layout, footprints, soil, concrete.unit_weight_kNm3
    )
    beam_statics = [
        solve_connecting_beam(layout, d, footprints)
        for d in corrected.distributions
        if d.combo_type == LoadCombinationType.FACTORIZADA.value
    ]
    # DESPEGUE — el cálculo se detiene aquí, y no por gusto.
    #
    # Detectarlo y seguir sería peor que no detectarlo: las cargas corregidas salen de
    # integrar un campo lineal sobre toda la huella, y cuando parte de ella se levanta
    # ese campo no describe nada. Con momentos grandes la carga corregida de una zapata
    # llega a resultar NEGATIVA y `evaluate_candidate` aborta con un error interno
    # sobre tracción, que no le dice nada al usuario.
    #
    # NO se resuelve contacto unilateral: eso es un modelo distinto y está sin definir.
    despegadas = [d for d in corrected.distributions if d.uplift]
    if despegadas:
        detalle = ", ".join(
            f"«{d.combo_name}» con σ_min = {d.sigma_min_kPa:.2f} kPa" for d in despegadas
        )
        raise ValueError(
            f"DESPEGUE en {len(despegadas)} combinación(es): {detalle}. "
            + UPLIFT_NOT_SOLVED
            + " Reduzca la excentricidad o aumente el área de apoyo."
        )

    if not beam_statics:
        raise ValueError(
            "No hay ninguna combinación FACTORIZADA: la viga se diseña con cargas "
            "amplificadas (E.060 §9.2), no de servicio."
        )

    # CARGA NETA ASCENDENTE — el mismo motivo que el despegue para detenerse aquí.
    #
    # La carga corregida de cada zapata es la que le entregan columna y viga para que el
    # suelo reaccione lo que dice la estática: R − W en cuerpo rígido, P ∓ ΔP en el
    # articulado. `evaluate_candidate` diseña con la carga FACTORIZADA de columna y sin
    # peso propio, y todo su planteamiento supone esa carga hacia abajo. Si sale nula o
    # negativa, la zapata cuelga de la viga y la losa trabaja al revés; seguir abortaría
    # dentro del solver con un error de datos que no señala la causa (y que el barrido
    # clasificaba como ENTRADA_INVALIDA). Aquí se nombra y se explica.
    ascendentes = [
        (d.combo_name, etiqueta, P)
        for d in corrected.distributions
        if d.combo_type == LoadCombinationType.FACTORIZADA.value
        for etiqueta, P in (
            (layout.exterior.label, d.P_ext_corrected_kN),
            (layout.interior.label, d.P_int_corrected_kN),
        )
        if P <= 0.0
    ]
    if ascendentes:
        detalle = ", ".join(
            f"«{combo}» en {zapata}: {P:.2f} kN" for combo, zapata, P in ascendentes
        )
        raise ValueError(
            f"CARGA_NETA_ASCENDENTE en {len(ascendentes)} caso(s): {detalle}. "
            "El suelo devuelve bajo esa zapata menos que su propio peso, de modo que la "
            "columna y la viga tienen que sostenerla: la carga neta que recibe va hacia "
            "ARRIBA. El diseño de la zapata (punzonamiento, cortante y flexión) solo está "
            "planteado para carga neta hacia abajo; con la carga invertida la losa cuelga y "
            "trabaja con la tracción arriba, y ese caso no está implementado. No es un dato "
            "mal declarado. Suele aparecer con zapatas grandes y pesadas bajo una columna "
            "poco cargada, sobre todo en 0,9·CM ± CS: reduzca esa zapata o aumente la otra."
        )

    # --- 2. Las dos zapatas, con los motores existentes ----------------------
    # El gancho es dato de CADA zapata (lo declara el proyectista; nunca se supone).
    def _con_ganchos(elemento) -> DepthSearchParameters:
        return depth_params.model_copy(update={
            "hook_type_x": elemento.hook_type_x, "hook_type_y": elemento.hook_type_y,
        })

    exterior = evaluate_candidate(
        B_m=geometry.exterior_B_m, L_m=geometry.exterior_L_m, h_m=geometry.exterior_h_m,
        column=layout.exterior.column, soil=soil, concrete=concrete, steel=steel,
        load_case_set=corrected.exterior, code=code, contact_model=contact_model,
        depth_params=_con_ganchos(layout.exterior),
        placement=layout.exterior.placement_for(geometry.exterior_B_m, geometry.exterior_L_m),
    )
    interior = evaluate_candidate(
        B_m=geometry.interior_B_m, L_m=geometry.interior_L_m, h_m=geometry.interior_h_m,
        column=layout.interior.column, soil=soil, concrete=concrete, steel=steel,
        load_case_set=corrected.interior, code=code, contact_model=contact_model,
        depth_params=_con_ganchos(layout.interior),
        placement=layout.interior.placement_for(geometry.interior_B_m, geometry.interior_L_m),
    )

    # --- 3. La viga, con el motor existente ----------------------------------
    # Gobierna la combinación de mayor momento negativo, que es la que arma la viga.
    gobernante = max(beam_statics, key=lambda b: b.M_max_negative_kNm)
    luz_libre = _clear_span(layout)
    suma_Pu = _sum_factored_axial(corrected)

    beam = design_connecting_beam(
        b_m=layout.beam.b_m, h_m=layout.beam.h_m, d_m=layout.beam.d_m,
        clear_span_m=luz_libre,
        Mu_negative_kNm=gobernante.M_max_negative_kNm,
        Mu_positive_kNm=max(b.M_max_positive_kNm for b in beam_statics),
        Vu_kN=max(b.V_design_kN for b in beam_statics),
        fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa,
        longitudinal_db_mm=longitudinal_db_mm,
        sum_Pu_kN=suma_Pu,
        seismic=seismic or SeismicContext(qadm_kPa=soil.qadm_kPa),
        stirrup_diameter_mm=stirrup_diameter_mm, n_legs=n_legs,
    )

    # --- 4. Traza del sistema, con ámbito por componente ---------------------
    trace, motivos = _system_trace(layout, corrected, beam_statics, soil)
    _scoped(trace, exterior.trace, SCOPE_EXTERIOR)
    _scoped(trace, interior.trace, SCOPE_INTERIOR)
    _scoped(trace, build_beam_trace(beam), SCOPE_BEAM)

    # El motivo de E.050 art. 26.2 ya lo emitió el ámbito de sistema: cada zapata lo
    # repite porque no sabe que forma parte de uno, y triplicarlo confundiría el
    # informe sobre cuántos problemas distintos hay.
    del_sistema = set(motivos)
    motivos += [
        f"[{layout.exterior.label}] {m}" for m in exterior.discard_reasons if m not in del_sistema
    ]
    motivos += [
        f"[{layout.interior.label}] {m}" for m in interior.discard_reasons if m not in del_sistema
    ]
    if beam.status is CheckStatus.FAIL:
        motivos += [f"[viga] {m}" for m in beam.messages if m]

    estado = CheckStatus.worst(
        [e.status for e in trace.entries]
        + [exterior.overall_status, interior.overall_status, beam.status]
    )

    return ConnectedFootingResult(
        geometry=geometry,
        exterior=exterior, interior=interior, beam=beam,
        statics=corrected.distributions,
        beam_statics=beam_statics,
        governing_beam_combo=gobernante.combo_name,
        trace=trace, overall_status=estado, discard_reasons=motivos,
        longitudinal_axis=layout.longitudinal_axis,
        beam_axis=eje_viga,
    )


def _clear_span(layout: ConnectedFootingLayout) -> float:
    """Luz LIBRE entre caras de las dos columnas — §21.12.3.2 mide sobre ella."""
    eje = layout.longitudinal_axis
    b_ext = layout.exterior.column.bx_m if eje == "X" else layout.exterior.column.by_m
    b_int = layout.interior.column.bx_m if eje == "X" else layout.interior.column.by_m
    return layout.axis_distance_m - b_ext / 2.0 - b_int / 2.0


SUM_PU_INTERPRETATION = (
    "E.030 art. 65.1 mide la fuerza axial mínima sobre «las cargas verticales amplificadas "
    "que soporta la zapata», sin precisar si son las de la columna o la reacción total que "
    "la zapata recibe una vez repartido el par. "
    "LECTURA ADOPTADA: la carga CORREGIDA de la zapata de lindero, es decir la reacción "
    "que realmente recibe una vez repartido el par. Es la mayor de las dos y por tanto la "
    "más exigente. Es una interpretación declarada, no una cita."
)


def _sum_factored_axial(corrected: CorrectedLoads) -> float:
    """ΣPu de la zapata conectada, para E.030 art. 65.1. Ver SUM_PU_INTERPRETATION."""
    factorizadas = [c.P_kN for c in corrected.exterior.factored]
    return max(factorizadas) if factorizadas else 0.0
