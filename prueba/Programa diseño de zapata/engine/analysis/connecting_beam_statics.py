"""Estática de la viga de conexión — Fase 4A.

POR QUÉ ESTE MÓDULO EXISTE Y NO SE REUTILIZA `analysis/beam_diagram.py`
======================================================================
`beam_diagram.py` se llama «beam» y produce V(x) y M(x), de modo que parece el
candidato obvio. No lo es, y usarlo daría números plausibles y equivocados.

`beam_diagram` modela un elemento que APOYA SOBRE EL SUELO EN TODA SU LONGITUD: sus
w₀ y w₁ salen de exigir que la resultante de la presión iguale la suma de cargas de
columna y esté aplicada en el mismo punto. Es el modelo correcto para una zapata
combinada, donde la reacción del terreno es la única fuerza que equilibra.

La viga de conexión es otra cosa. Solo hay reacción del terreno bajo la ZAPATA
EXTERIOR —de s = 0 a s = L1—; del borde de esa zapata hasta el eje de la columna
interior la viga salva un vano sin apoyo. El diagrama tiene dos regiones con leyes
distintas, y la segunda no tiene carga distribuida en absoluto. Forzar el modelo de
`beam_diagram` sobre esta geometría es un error de física, no de estilo.

QUÉ MODELA ESTE MÓDULO
======================
La misma coordenada `s` y la misma convención de signos de `connected_statics.py`:
origen en el borde de lindero, positiva hacia el interior, fuerzas positivas hacia
arriba.

    Región 1 — 0 ≤ s ≤ L1   Carga neta repartida hacia arriba bajo la zapata
                            exterior, más la carga puntual y el momento de la columna
                            exterior en s = a. Su FORMA depende del modelo:
                              ARTICULADO     w₁ = R_ext / L1, uniforme (R_ext neto).
                              CUERPO_RIGIDO  q(s) = B·p(s) − W_ext/L1, trapecial, con
                                             p(s) el campo real del conjunto rígido.
    Región 2 — L1 ≤ s ≤ s_c Sin reacción del terreno. Cortante constante.

Convención de esfuerzos internos: se toma la porción IZQUIERDA de la sección.

    V(s) = Σ  F_up  a la izquierda de s
    M(s) = Σ  F_up · (s − s_i)  a la izquierda de s    (positivo = tracción abajo)

Con esa convención, el momento de la viga de conexión sale NEGATIVO en el tramo
central —tracción arriba—, que es lo que corresponde a una viga que cuelga del
voladizo de la zapata de lindero.

LO QUE NO MODELA
================
El peso propio de la viga solo entra cuando `self_weight_mode` vale EXPLICITO. La
reacción del terreno bajo la viga NO se modela ni siquiera cuando el usuario declara
APOYA_EN_SUELO: eso queda como hipótesis NO VERIFICADA, no como cálculo.

PESO PROPIO DE LA VIGA — FASE 9a
================================
Se carga como lo describe `BeamSelfWeightBreakdown`, repartido sobre su tramo físico:
ΔW_e sobre [c_e, L1] y W_V sobre el vano libre [L1, f_i]. ΔW_i NO carga la viga:
descansa sobre la zapata interior. Con PAR_PURO_EN_ZAPATA la viga es un cuerpo propio
entre el nudo `a` y la rótula, y solo lleva W_V (ΔW_e es de la zapata de lindero).
Hasta 9a el peso se repartía sobre [L1, s_corte], con `s_corte` como límite de peso.

EL MOMENTO EN LA SECCIÓN DE CORTE SE CONTRASTA, NO SE SUPONE
===========================================================
El diagrama se integra desde las CARGAS, y su valor en `s_corte` se compara con
`CoupleDistribution.M_cut_kNm`, que el reparto calcula por su cuenta sobre el mismo
cuerpo {huella exterior + cargas a la izquierda del eje interior}. En ARTICULADO eso
verifica la rótula (`M = 0`); en CUERPO_RIGIDO, que el diagrama y el reparto describen
el mismo campo. `cut_moment_consistent` es el resultado, y desde la Fase 5A deja de ser
un dato ignorado: el orquestador lo convierte en estado.

FASE 5A — DEFECTO D3
====================
Hasta 5A este módulo era un solver ARTICULADO en sus dos ramas:

  M1  En cuerpo rígido usaba `w = R_ext/L1` uniforme con un `R_ext` BRUTO —que incluye
      el peso propio de la zapata— y nunca descontaba ese peso. La presión real es
      trapecial. Mu⁻ salía hasta un 21 % por defecto y aparecía un Mu⁺ inexistente.
  M2  El momento de columna de E.050 art. 28.1 no entraba en el diagrama, en ningún
      modelo. El error era exactamente −M_col, con el signo del momento.
  M3  Con PAR_PURO_EN_ZAPATA aplicaba el cuerpo libre de par puro articulado aunque el
      modelo fuera rígido. Desaparece al rechazarse la combinación (D1).

Ver `docs/fase5a_estatica_viga.md`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.analysis.connected_statics import CoupleDistribution, rigid_pressure_field
from engine.domain.connected_layout import (
    AnalysisModel,
    ConnectedFootingLayout,
    CoupleTransferMode,
    Footprints,
    check_couple_mode_compatible,
)

# Muestreo para localizar extremos que no caen en una sección notable.
_SAMPLES = 400


class BeamStationResult(BaseModel):
    """Un punto notable del diagrama."""

    s_m: float
    V_kN: float
    M_kNm: float
    description: str


class ConnectingBeamStatics(BaseModel):
    """Diagramas V(s) y M(s) de la viga de conexión para UNA combinación."""

    combo_name: str
    combo_type: str

    a_m: float
    L1_m: float
    s_cut_m: float
    w_up_kNm: float = Field(
        ..., description="Carga neta repartida hacia arriba bajo la zapata exterior [kN/m]"
    )

    stations: list[BeamStationResult] = Field(default_factory=list)

    M_max_positive_kNm: float = Field(
        ..., ge=0.0, description="Máximo momento con tracción ABAJO, en magnitud"
    )
    M_max_negative_kNm: float = Field(
        ..., ge=0.0, description="Máximo momento con tracción ARRIBA, en magnitud"
    )
    s_M_max_positive_m: float
    s_M_max_negative_m: float

    V_design_kN: float = Field(
        ..., ge=0.0, description="Cortante de diseño de la viga, en magnitud"
    )
    s_V_design_m: float

    M_at_cut_kNm: float = Field(
        ..., description="Momento en la sección de corte, calculado desde el diagrama"
    )
    M_cut_declared_kNm: float = Field(
        ...,
        description=(
            "Momento en la junta según el reparto. ARTICULADO declara 0 —rótula—; "
            "CUERPO_RIGIDO declarará un valor no nulo."
        ),
    )
    cut_moment_consistent: bool = Field(
        ...,
        description=(
            "¿Coincide el momento que sale del diagrama con el que declaró el reparto? Es "
            "una comprobación CRUZADA entre dos cálculos independientes: si discrepan, uno "
            "de los dos está mal planteado. En el modelo articulado equivale a verificar "
            "que la rótula es realmente una rótula."
        ),
    )
    M_at_exterior_column_face_kNm: float = Field(
        ...,
        description=(
            "Momento en la cara interior de la columna exterior. Es la sección donde los "
            "apuntes toman el momento negativo de la viga; se reporta para poder contrastar."
        ),
    )
    s_beam_start_m: float = Field(
        ..., description="Inicio del tramo que se diseña como VIGA: borde interior de la zapata"
    )

    equation_substituted: str
    hypotheses: list[str] = Field(default_factory=list)


BeamLoads = tuple[tuple[float, float, float], ...]
"""Cargas uniformes hacia ABAJO sobre la viga: (W total [kN], s inicial, s final)."""


def beam_self_weight_loads(distribution: CoupleDistribution, *, include_exterior: bool) -> BeamLoads:
    """Tramos de peso propio que cargan el cuerpo de la viga (Fase 9a).

    `include_exterior`: ΔW_e es parte del cuerpo {zapata exterior + viga} en los modelos
    que lo plantean así (ARTICULADO + EQUILIBRIO y CUERPO_RIGIDO), pero no del cuerpo
    viga de PAR_PURO, donde pertenece a la zapata de lindero. ΔW_i nunca."""
    bw = distribution.beam_self_weight_breakdown
    if bw is None:
        return ()
    cargas = []
    if include_exterior and bw.exterior_increment_kN > 0.0:
        cargas.append((bw.exterior_increment_kN, bw.s_exterior_face_m, bw.s_span_start_m))
    if bw.span_kN > 0.0:
        cargas.append((bw.span_kN, bw.s_span_start_m, bw.s_span_end_m))
    return tuple(cargas)


def _uniform_left(s: float, beam_loads: BeamLoads) -> tuple[float, float]:
    """(carga a la izquierda de s, su momento respecto de s) de las cargas uniformes."""
    carga_total, momento = 0.0, 0.0
    for W, s0, s1 in beam_loads:
        if W > 0.0 and s > s0:
            largo = max(s1 - s0, 1e-12)
            tramo = max(min(s, s1) - s0, 0.0)
            carga = W * tramo / largo
            carga_total += carga
            momento += carga * (s - (s0 + tramo / 2.0))
    return carga_total, momento


def statics_tolerance(distribution: CoupleDistribution) -> float:
    """Tolerancia de cierre de la estática de la viga [kN·m].

    Es la MISMA con la que se contrasta el momento de la junta (`cut_moment_consistent`):
    por debajo de ella un momento no se distingue de cero dentro de este cálculo."""
    return 1e-6 * max(abs(distribution.P_ext_kN) * max(distribution.S_m, 1.0), 1.0)


def design_extreme(M_kNm: float, tolerance_kNm: float) -> float:
    """Magnitud de diseño de un extremo de momento, sin ruido de coma flotante.

    Fase 9a. En la rótula el momento vale cero POR DEFINICIÓN del modelo, pero sale de
    sumar términos grandes y queda en ±1e-13. Tomar ese residuo como demanda cambiaba
    decisiones de diseño: un Mu⁺ de 3,8e-13 kN·m activaba la exención de E.060 §10.5.3
    —acero colocado ≥ 4/3 del requerido— y el acero mínimo positivo de la viga pasaba de
    9,24 cm² a cero, solo porque el residuo había cambiado de signo. Por debajo de la
    tolerancia de cierre de la propia estática, el extremo es cero."""
    valor = max(M_kNm, 0.0)
    return valor if valor > tolerance_kNm else 0.0


def _shear(s: float, *, w_up: float, L1: float, a: float, P_ext: float,
           beam_loads: BeamLoads = (), M_col: float = 0.0) -> float:
    """V(s) por suma de fuerzas a la izquierda, positivas hacia arriba.

    `M_col` se acepta y no se usa: un par concentrado no altera el cortante. Está en la
    firma para que `_shear` y `_moment` reciban exactamente las mismas acciones."""
    v = w_up * min(max(s, 0.0), L1)
    if s > a:
        v -= P_ext
    for W, s0, s1 in beam_loads:
        if W > 0.0 and s > s0:
            tramo = max(min(s, s1) - s0, 0.0)
            largo = max(s1 - s0, 1e-12)
            v -= W * tramo / largo
    return v


def _moment(s: float, *, w_up: float, L1: float, a: float, P_ext: float,
            beam_loads: BeamLoads = (), M_col: float = 0.0) -> float:
    """M(s) = Σ F_up · (s − s_i) a la izquierda de la sección, más el momento de columna.

    MOMENTO DE COLUMNA — Fase 5A, D3/M2
    ===================================
    Con la convención del cuerpo libre (`Σ (s_i − s)·F_up + M_app = 0`) y la de esta
    viga (`M = Σ F_up·(s − s_i)`), el par aplicado entra como `−M_app`. Y
    `applied_moment_in_free_body` da `M_app = −M_E050`. Luego:

        M_viga(s) = Σ F_up·(s − s_i) + M_E050          para s > a

    Antes de 5A este término faltaba —el docstring anterior decía que «se superpone
    después», y no se superponía—. Con él, la rótula del modelo articulado cierra
    (`M(s_corte) = 0`) también cuando la columna transmite momento.

    En `s = a` exacto se toma el límite por la izquierda, igual que para la carga
    puntual. El tramo que se diseña empieza en L1 > a y no depende de esa elección."""
    x = min(max(s, 0.0), L1)
    # Resultante de la carga repartida en [0, x], aplicada en x/2.
    m = w_up * x * (s - x / 2.0)
    if s > a:
        m -= P_ext * (s - a)
        if M_col != 0.0:
            m += M_col
    for W, s0, s1 in beam_loads:
        if W > 0.0 and s > s0:
            largo = max(s1 - s0, 1e-12)
            tramo = max(min(s, s1) - s0, 0.0)
            carga = W * tramo / largo
            centro = s0 + tramo / 2.0
            m -= carga * (s - centro)
    return m


def _solve_pure_couple(
    layout: ConnectedFootingLayout, distribution: CoupleDistribution
) -> ConnectingBeamStatics:
    """Diagramas cuando la rama cercana del par la recoge el pórtico (TBD-C11).

    Aquí la viga NO nace del diagrama de la zapata. La zapata de lindero tiene
    reacción igual a la carga de su columna —presión uniforme, sin resultante neta que
    trasladar—, de modo que el diagrama del apartado anterior daría cortante nulo en el
    vano, que es falso.

    Lo que carga a la viga es el PAR. Como cuerpo libre, la viga va del eje de la
    columna exterior al de la interior, con el par M_par aplicado en el extremo
    exterior y momento nulo en el interior (la rótula del modelo articulado). De ahí:

        V = M_par / S           constante en todo el vano
        M(s) = M_par · (1 − (s − a)/S)     lineal, de M_par a cero

    Es el procedimiento de los apuntes CR2-93-134 §3.6 problema 1, y reproduce sus
    valores: con M_par = 122,75 t·m y S = 6,00 m sale V = 20,45 t, que amplificado por
    1,25 da los 25,6 t del libro, y el momento en el eje de la columna exterior
    amplificado da 153,4 t·m.

    LO QUE NO SE REPRODUCE. El libro diseña con el momento a la CARA de la columna,
    140,6 t·m, reducido desde los 153,4 del eje. Esa reducción sale de la presión de la
    zapata sobre ese tramo y su valor exacto está en una figura que el PDF no expone
    como texto. Este módulo reporta el momento en el eje y, aparte, el de la cara según
    su propia reducción lineal; la diferencia queda declarada, no ajustada.

    PESO PROPIO DE LA VIGA — Fase 9c, B*
    ====================================
    Con peso EXPLICITO la viga es un tramo apoyado en el nudo `a` y en la rótula, cargado
    además con W_V sobre el vano libre. Se superpone su gravedad:

        V(s) = −M_par/S + N_a − W_izq(s)
        M(s) = M_par·(1 − (s − a)/S) + N_a·(s − a) − M_izq(s)

    con N_a = W_V·(s_corte − x_V)/S la reacción del nudo, que el reparto ya calculó. El
    momento sigue siendo nulo en la rótula por construcción de N_a; se contrasta igual.
    Sin peso las fórmulas son exactamente las de antes."""
    a = distribution.a_m
    S = distribution.S_m
    s_cut = distribution.s_cut_m
    M_par = distribution.M_couple_kNm
    V = -M_par / S
    bw = distribution.beam_self_weight_breakdown
    cargas_viga = beam_self_weight_loads(distribution, include_exterior=False)
    N_a = distribution.beam_node_reaction_kN or 0.0

    b_col = (
        layout.exterior.column.bx_m
        if layout.longitudinal_axis == "X"
        else layout.exterior.column.by_m
    )
    cara = a + b_col / 2.0

    def M(s: float) -> float:
        m = M_par * (1.0 - (s - a) / S)
        if bw is not None:
            _, momento_izq = _uniform_left(s, cargas_viga)
            m += N_a * (s - a) - momento_izq
        return m

    def V_en(s: float) -> float:
        if bw is None:
            return V
        carga_izq, _ = _uniform_left(s, cargas_viga)
        return V + N_a - carga_izq

    notables = [
        (a, "eje de la columna exterior — par aplicado"),
        (cara, "cara interior de la columna exterior"),
        (s_cut, "sección de corte — eje de la columna interior"),
    ]
    if bw is not None:
        notables += [
            (bw.s_span_start_m, "borde interior de la zapata exterior — inicio del vano libre"),
            (bw.s_span_end_m, "borde de la zapata interior — fin del vano libre"),
        ]
        notables.sort()
    estaciones = [
        BeamStationResult(s_m=x, V_kN=V_en(x), M_kNm=M(x), description=d) for x, d in notables
    ]

    M_en_eje = M(a)
    M_neg = max(-min(M_en_eje, M(s_cut)), 0.0)
    M_pos = max(max(M_en_eje, M(s_cut)), 0.0)
    s_pos = a if M_pos else s_cut
    s_neg = a if M_neg else s_cut
    V_dis, s_V = abs(V), a
    if bw is not None:
        # Con gravedad el momento deja de ser lineal: los extremos se buscan en el tramo.
        muestras = [a + (s_cut - a) * i / _SAMPLES for i in range(_SAMPLES + 1)]
        puntos = [(s, M(s)) for s in muestras] + [(e.s_m, e.M_kNm) for e in estaciones]
        s_max, M_max = max(puntos, key=lambda p: p[1])
        s_min, M_min = min(puntos, key=lambda p: p[1])
        M_pos, s_pos = max(M_max, 0.0), s_max
        M_neg, s_neg = max(-M_min, 0.0), s_min
        s_V, V_con_signo = max(((s, V_en(s)) for s in muestras), key=lambda p: abs(p[1]))
        V_dis = abs(V_con_signo)

    return ConnectingBeamStatics(
        combo_name=distribution.combo_name,
        combo_type=distribution.combo_type,
        a_m=a, L1_m=distribution.L1_m, s_cut_m=s_cut,
        w_up_kNm=0.0,
        stations=estaciones,
        M_max_positive_kNm=design_extreme(M_pos, statics_tolerance(distribution)),
        M_max_negative_kNm=design_extreme(M_neg, statics_tolerance(distribution)),
        s_M_max_positive_m=s_pos,
        s_M_max_negative_m=s_neg,
        V_design_kN=V_dis, s_V_design_m=s_V,
        M_at_cut_kNm=M(s_cut),
        M_cut_declared_kNm=distribution.M_cut_kNm,
        cut_moment_consistent=abs(M(s_cut) - distribution.M_cut_kNm)
        <= 1e-6 * max(abs(distribution.P_ext_kN) * max(S, 1.0), 1.0),
        M_at_exterior_column_face_kNm=M(cara),
        s_beam_start_m=a,
        equation_substituted=(
            f"par M = {M_par:.3f} kN·m aplicado en s = {a:.4f} m; S = {S:.4f} m | "
            f"V = M/S = {V:.3f} kN constante en el vano | "
            f"M lineal de {M_en_eje:.2f} kN·m en el eje a {M(s_cut):.2f} kN·m en el corte | "
            f"M en la cara de la columna = {M(cara):.2f} kN·m"
            + (
                f" | peso de la viga (B*): W_V = {bw.span_kN:.3f} kN sobre "
                f"[{bw.s_span_start_m:.3f}, {bw.s_span_end_m:.3f}] m, N_a = {N_a:.3f} kN en el "
                f"nudo; V = M/S + N_a − W_izq(s), M lineal + gravedad de tramo apoyado a–s_corte "
                f"| V diseño = {V_dis:.2f} kN en s = {s_V:.3f} m"
                if bw is not None else ""
            )
        ),
        hypotheses=[
            "TBD-C11 = PAR_PURO_EN_ZAPATA: la viga se resuelve como cuerpo libre cargado "
            "por el par, no a partir del diagrama de la zapata. Con reacción igual a la "
            "carga de columna, aquel diagrama daría cortante nulo en el vano.",
            "Fase 9c, B*: la rama transmitida al pórtico corresponde exclusivamente al par; "
            "las cargas verticales gravitacionales de la viga se transmiten mediante sus "
            "reacciones —en el nudo de la columna exterior y en la rótula—.",
            "El momento del libro se toma a la CARA de la columna exterior; su reducción "
            "desde el eje depende de la presión de la zapata sobre ese tramo, que está en "
            "una figura del PDF y no se reproduce. Se reporta la reducción lineal propia.",
            "No se reutiliza `analysis/beam_diagram.py`: ese módulo supone un elemento "
            "apoyado sobre el suelo en toda su longitud y aquí eso es falso.",
        ],
    )


def _solve_rigid_body(
    layout: ConnectedFootingLayout,
    distribution: CoupleDistribution,
    footprints: Footprints,
) -> ConnectingBeamStatics:
    """Diagramas de la viga en el modelo CUERPO_RIGIDO — Fase 5A, D3/M1.

    CUERPO LIBRE
    ============
    Porción a la izquierda de la sección `s`:

      0 ≤ s ≤ L1   Reacción REAL del terreno bajo la zapata exterior, menos su peso
                   propio. Ni una ni otro son uniformes en su efecto: la presión es
                   trapecial y el peso actúa repartido sobre la huella.
      s = a        Carga de la columna exterior hacia abajo y su momento E.050.
      L1 < s       Sin terreno (salvo peso propio de viga EXPLICITO, repartido).

    ECUACIONES
    ==========
        p(s)  = p₀ + p₁·(s − x_c)                    campo del conjunto rígido
        q(s)  = B·p(s) − W_ext/L1                    carga NETA por metro

        Q(x)  = ∫₀ˣ q dt  = B·[p₀·x + p₁·((x − x_c)² − x_c²)/2] − (W_ext/L1)·x
        Qₛ(x) = ∫₀ˣ t·q dt = B·[p₀·x²/2 + p₁·(x³/3 − x_c·x²/2)] − (W_ext/L1)·x²/2

        V(s) = Q(x) − P_ext·H(s − a)
        M(s) = s·Q(x) − Qₛ(x) − P_ext·(s − a)·H(s − a) + M_E050·H(s − a)
                                                             con x = min(s, L1)

    POR QUÉ ES UNA COMPROBACIÓN INDEPENDIENTE
    =========================================
    El campo (p₀, p₁, x_c) es el del reparto: mismas cargas, misma solución de sección.
    Pero la integración usa las primitivas de arriba, no la resultante y el centroide de
    trapecio de `_integrate_footprint`. Si `M(s_corte)` coincide con el `M_cut_kNm` que
    el reparto calculó, lo que coincide son dos integraciones distintas del mismo campo.

    TRAMO DE DISEÑO: EL VANO LIBRE [L1, s_fin]
    ==========================================
    `s_fin` es el borde de la huella interior. Más allá, el cuerpo está sobre la zapata
    interior y su presión real no pertenece a la viga: prolongar el diagrama hasta
    `s_corte` con carga nula ya no sería el campo de presión real, y en Z14 fabricaba un
    Mu⁺ que no existe. El diagrama SÍ se evalúa hasta `s_corte`, pero solo para el
    contraste con el reparto, que define `M_cut` sobre ese mismo cuerpo."""
    d = distribution
    fe, fi = footprints.exterior, footprints.interior
    a = d.a_m
    L1 = fe.length_m
    s_cut = d.s_cut_m
    s_fin = fi.start_m
    P_ext = d.P_ext_kN
    M_col = d.M_ext_kNm
    B = fe.width_m
    W_ext = d.W_ext_kN
    w_pp = W_ext / L1 if L1 > 0 else 0.0
    cargas_viga = beam_self_weight_loads(d, include_exterior=True)

    p0, p1, x_c = rigid_pressure_field(layout, footprints, d)

    def Q(x: float) -> float:
        return B * (p0 * x + p1 * ((x - x_c) ** 2 - x_c**2) / 2.0) - w_pp * x

    def Qs(x: float) -> float:
        return (
            B * (p0 * x * x / 2.0 + p1 * (x**3 / 3.0 - x_c * x * x / 2.0))
            - w_pp * x * x / 2.0
        )

    def V(s: float) -> float:
        x = min(max(s, 0.0), L1)
        v = Q(x)
        if s > a:
            v -= P_ext
        carga_izq, _ = _uniform_left(s, cargas_viga)
        return v - carga_izq if cargas_viga else v

    def M(s: float) -> float:
        x = min(max(s, 0.0), L1)
        m = s * Q(x) - Qs(x)
        if s > a:
            m -= P_ext * (s - a)
            if M_col != 0.0:
                m += M_col
        _, momento_izq = _uniform_left(s, cargas_viga)
        return m - momento_izq if cargas_viga else m

    # --- Secciones notables --------------------------------------------------
    b_col = (
        layout.exterior.column.bx_m
        if layout.longitudinal_axis == "X"
        else layout.exterior.column.by_m
    )
    cara_interior = a + b_col / 2.0

    notables: list[tuple[float, str]] = [
        (0.0, "borde de lindero"),
        (a, "eje de la columna exterior"),
        (cara_interior, "cara interior de la columna exterior"),
        (L1, "borde interior de la zapata exterior — inicio del vano libre"),
        (s_fin, "borde de la zapata interior — fin del vano libre"),
        (s_cut, "sección de corte — eje de la columna interior"),
    ]
    # V = 0 dentro de la huella exterior. Con carga trapecial V es cuadrática en s:
    # se localiza por bisección, no con la fórmula del caso uniforme.
    s_izq = a + 1e-9 * max(L1, 1.0)
    if s_izq < L1 and V(s_izq) * V(L1) < 0.0:
        lo, hi = s_izq, L1
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if V(lo) * V(mid) <= 0.0:
                hi = mid
            else:
                lo = mid
        notables.append((0.5 * (lo + hi), "cortante nulo — extremo de momento"))

    vistos: list[float] = []
    estaciones: list[BeamStationResult] = []
    for s, desc in sorted(notables):
        if any(abs(s - v) < 1e-9 for v in vistos):
            continue
        vistos.append(s)
        estaciones.append(BeamStationResult(s_m=s, V_kN=V(s), M_kNm=M(s), description=desc))

    # --- Extremos sobre el VANO LIBRE ----------------------------------------
    muestras = [L1 + (s_fin - L1) * i / _SAMPLES for i in range(_SAMPLES + 1)]
    puntos = [(s, M(s)) for s in muestras] + [
        (e.s_m, e.M_kNm) for e in estaciones if L1 - 1e-9 <= e.s_m <= s_fin + 1e-9
    ]
    s_pos, M_pos = max(puntos, key=lambda p: p[1])
    s_neg, M_neg = min(puntos, key=lambda p: p[1])

    candidatos_V = [(s, V(s)) for s in muestras]
    s_V, V_dis = max(candidatos_V, key=lambda p: abs(p[1]))

    M_corte = M(s_cut)
    tolerancia = 1e-6 * max(abs(P_ext) * max(d.S_m, 1.0), 1.0)
    consistente = abs(M_corte - d.M_cut_kNm) <= tolerancia
    w_media = Q(L1) / L1 if L1 > 0 else 0.0

    return ConnectingBeamStatics(
        combo_name=d.combo_name,
        combo_type=d.combo_type,
        a_m=a, L1_m=L1, s_cut_m=s_cut, w_up_kNm=w_media,
        stations=estaciones,
        M_max_positive_kNm=design_extreme(M_pos, statics_tolerance(d)),
        M_max_negative_kNm=design_extreme(-M_neg, statics_tolerance(d)),
        s_M_max_positive_m=s_pos, s_M_max_negative_m=s_neg,
        V_design_kN=abs(V_dis), s_V_design_m=s_V,
        M_at_cut_kNm=M_corte,
        M_cut_declared_kNm=d.M_cut_kNm,
        cut_moment_consistent=consistente,
        M_at_exterior_column_face_kNm=M(cara_interior),
        s_beam_start_m=L1,
        equation_substituted=(
            f"p(s) = {p0:.3f} + ({p1:+.4f})·(s − {x_c:.4f}) kPa · B = {B:.3f} m · "
            f"q(s) = B·p(s) − W_ext/L1, W_ext = {W_ext:.2f} kN en L1 = {L1:.4f} m "
            f"(media neta {w_media:.3f} kN/m) · M_col = {M_col:.2f} kN·m en s = {a:.4f} m | "
            f"vano libre {L1:.3f} ≤ s ≤ {s_fin:.3f} m: "
            f"M⁻ = {max(-M_neg, 0.0):.2f} kN·m en s = {s_neg:.3f} m · "
            f"M⁺ = {max(M_pos, 0.0):.2f} kN·m en s = {s_pos:.3f} m · "
            f"V = {abs(V_dis):.2f} kN | "
            f"contraste en s = {s_cut:.3f} m: diagrama {M_corte:.3f} frente a reparto "
            f"{d.M_cut_kNm:.3f} kN·m ({'coinciden' if consistente else 'NO COINCIDEN'})"
        ),
        hypotheses=[
            "CUERPO_RIGIDO: la viga se carga con el campo de presión REAL del conjunto "
            "rígido —trapecial— y con la carga NETA, descontando el peso propio de la "
            "zapata exterior. Hasta la Fase 5A se usaba una presión uniforme con la "
            "reacción bruta (defecto D3, mecanismo M1).",
            "El momento de columna de E.050 art. 28.1 entra en el diagrama como "
            "+M_col para s > a (defecto D3, mecanismo M2).",
            f"Los valores de DISEÑO se toman sobre el vano libre {L1:.3f} ≤ s ≤ "
            f"{s_fin:.3f} m. Más allá, el cuerpo está sobre la zapata interior, cuya "
            f"presión real no pertenece a la viga.",
            "El diagrama se prolonga hasta el eje de la columna interior solo para "
            "contrastarlo con el momento que el reparto calculó sobre ese mismo cuerpo: "
            "son dos integraciones distintas del mismo campo.",
            "No se reutiliza `analysis/beam_diagram.py`: ese módulo supone un elemento "
            "apoyado sobre el suelo en toda su longitud y aquí eso es falso.",
            "El cortante de diseño NO se reduce a «d de la cara»: E.060 §11.1.3.1 condiciona "
            "esa reducción a que la reacción introduzca compresión en la zona de apoyo, y el "
            "vano libre no está apoyado.",
        ],
    )


def solve_connecting_beam(
    layout: ConnectedFootingLayout,
    distribution: CoupleDistribution,
    footprints: Footprints | None = None,
) -> ConnectingBeamStatics:
    """Diagramas de la viga a partir del reparto ya resuelto.

    No recalcula el reparto: lo recibe. Si este módulo volviera a plantear el
    equilibrio habría dos versiones de la misma estática.

    QUÉ CUERPO LIBRE DESCRIBE A LA VIGA
    ===================================
    Lo deciden el modelo de análisis y, en el articulado, el modo de reparto del par:

      ARTICULADO + PAR_PURO_EN_ZAPATA    cuerpo libre cargado por el par (Aragón P1)
      ARTICULADO + EQUILIBRIO            presión neta uniforme bajo la zapata exterior
      CUERPO_RIGIDO (+ EQUILIBRIO)       campo de presión real del conjunto rígido

    `CUERPO_RIGIDO + PAR_PURO_EN_ZAPATA` no llega aquí: es una combinación incompatible
    y se rechaza (Fase 5A, D1). Se vuelve a comprobar a la entrada porque este módulo
    puede recibir un reparto construido a mano o un layout variado con `model_copy`.

    `footprints` es obligatorio en CUERPO_RIGIDO: la presión real depende de las dos
    huellas —área, centroide e inercia de la sección compuesta— y del ancho de la
    exterior. En el articulado no se usa."""
    check_couple_mode_compatible(distribution.analysis_model, distribution.couple_transfer_mode)

    if distribution.couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA:
        return _solve_pure_couple(layout, distribution)

    if distribution.analysis_model is AnalysisModel.CUERPO_RIGIDO:
        if footprints is None:
            raise ValueError(
                "La estática de la viga en CUERPO_RIGIDO necesita las huellas: la presión "
                "real bajo la zapata de lindero depende de la sección compuesta de las "
                "dos. Sin ellas solo podría suponerse uniforme, que es el defecto D3/M1."
            )
        return _solve_rigid_body(layout, distribution, footprints)

    a = distribution.a_m
    L1 = distribution.L1_m
    s_cut = distribution.s_cut_m
    P_ext = distribution.P_ext_kN
    w_up = distribution.R_ext_kN / L1 if L1 > 0 else 0.0

    bw = distribution.beam_self_weight_breakdown
    cargas_viga = beam_self_weight_loads(distribution, include_exterior=True)

    # M_col: el momento de columna E.050 entra en el diagrama (Fase 5A, D3/M2).
    kw = dict(w_up=w_up, L1=L1, a=a, P_ext=P_ext, beam_loads=cargas_viga,
              M_col=distribution.M_ext_kNm)

    # --- Secciones notables --------------------------------------------------
    b_col = (
        layout.exterior.column.bx_m
        if layout.longitudinal_axis == "X"
        else layout.exterior.column.by_m
    )
    cara_interior = a + b_col / 2.0

    notables: list[tuple[float, str]] = [
        (0.0, "borde de lindero"),
        (a, "eje de la columna exterior"),
        (cara_interior, "cara interior de la columna exterior"),
        (L1, "borde interior de la zapata exterior"),
        (s_cut, "sección de corte — eje de la columna interior"),
    ]
    if bw is not None:
        # Fin del vano libre: donde termina la carga W_V (Fase 9a).
        notables.append((bw.s_span_end_m, "borde de la zapata interior — fin del vano libre"))
    # V = 0 dentro del tramo con carga repartida: w·s = P_ext -> s = P_ext/w.
    if w_up > 1e-12 and bw is None:
        s_v0 = P_ext / w_up
        if a < s_v0 < L1:
            notables.append((s_v0, "cortante nulo — extremo de momento"))
    elif bw is not None:
        # Con ΔW_e repartido sobre [c_e, L1] la fórmula cerrada deja de valer: bisección,
        # igual que en el modelo rígido.
        s_izq = a + 1e-9 * max(L1, 1.0)
        if s_izq < L1 and _shear(s_izq, **kw) * _shear(L1, **kw) < 0.0:
            lo, hi = s_izq, L1
            for _ in range(100):
                mid = 0.5 * (lo + hi)
                if _shear(lo, **kw) * _shear(mid, **kw) <= 0.0:
                    hi = mid
                else:
                    lo = mid
            notables.append((0.5 * (lo + hi), "cortante nulo — extremo de momento"))

    vistos: list[float] = []
    estaciones: list[BeamStationResult] = []
    for s, desc in sorted(notables):
        if any(abs(s - v) < 1e-9 for v in vistos):
            continue
        vistos.append(s)
        estaciones.append(
            BeamStationResult(s_m=s, V_kN=_shear(s, **kw), M_kNm=_moment(s, **kw), description=desc)
        )

    # --- Extremos, SOBRE EL TRAMO QUE SE DISEÑA COMO VIGA --------------------
    # El tramo 0 ≤ s ≤ L1 es la ZAPATA exterior, y sus esfuerzos internos los
    # verifica `evaluate_candidate` con los artículos de zapata (§15.4, §15.5,
    # §11.12). Tomar de ahí el cortante de diseño de la viga daría el cortante de la
    # zapata —del orden de la carga de columna entera— y no el de la viga.
    #
    # Lo que se diseña como viga es el tramo entre el borde interior de la zapata
    # exterior y el eje de la columna interior.
    s_ini_viga = L1
    muestras = [
        s_ini_viga + (s_cut - s_ini_viga) * i / _SAMPLES for i in range(_SAMPLES + 1)
    ] if s_cut > s_ini_viga else [s_cut]
    puntos = [(s, _moment(s, **kw)) for s in muestras] + [
        (e.s_m, e.M_kNm) for e in estaciones if e.s_m >= s_ini_viga - 1e-9
    ]

    s_pos, M_pos = max(puntos, key=lambda p: p[1])
    s_neg, M_neg = min(puntos, key=lambda p: p[1])

    # Cortante de diseño: el mayor en magnitud SOBRE EL TRAMO DE VIGA. No se toma a
    # «d de la cara» como en una zapata: §11.1.3.1 condiciona esa reducción a que la
    # reacción introduzca compresión en la zona de apoyo, y este tramo no está
    # apoyado.
    candidatos_V = [(s, _shear(s, **kw)) for s in muestras]
    s_V, V_dis = max(candidatos_V, key=lambda p: abs(p[1]))

    return ConnectingBeamStatics(
        combo_name=distribution.combo_name,
        combo_type=distribution.combo_type,
        a_m=a, L1_m=L1, s_cut_m=s_cut, w_up_kNm=w_up,
        stations=estaciones,
        M_max_positive_kNm=design_extreme(M_pos, statics_tolerance(distribution)),
        M_max_negative_kNm=design_extreme(-M_neg, statics_tolerance(distribution)),
        s_M_max_positive_m=s_pos, s_M_max_negative_m=s_neg,
        V_design_kN=abs(V_dis), s_V_design_m=s_V,
        M_at_cut_kNm=_moment(s_cut, **kw),
        M_cut_declared_kNm=distribution.M_cut_kNm,
        cut_moment_consistent=abs(_moment(s_cut, **kw) - distribution.M_cut_kNm)
        <= 1e-6 * max(abs(distribution.P_ext_kN) * max(distribution.S_m, 1.0), 1.0),
        M_at_exterior_column_face_kNm=_moment(cara_interior, **kw),
        s_beam_start_m=s_ini_viga,
        equation_substituted=(
            f"w = R_ext/L1 = {distribution.R_ext_kN:.3f}/{L1:.4f} = {w_up:.3f} kN/m en "
            f"0 ≤ s ≤ {L1:.4f} m; sin reacción del terreno entre {L1:.4f} y {s_cut:.4f} m | "
            f"M⁻ = {max(-M_neg, 0.0):.2f} kN·m en s = {s_neg:.3f} m · "
            f"M⁺ = {max(M_pos, 0.0):.2f} kN·m en s = {s_pos:.3f} m · "
            f"V = {abs(V_dis):.2f} kN en s = {s_V:.3f} m"
        ),
        hypotheses=[
            "El momento en la junta se CONTRASTA contra el que declaró el reparto, en vez "
            "de suponerlo nulo: así este módulo no queda atado al modelo articulado y la "
            "condición de rótula pasa a estar verificada, no supuesta.",
            "El momento de columna de E.050 art. 28.1 entra en el diagrama como +M_col "
            "para s > a. Hasta la Fase 5A faltaba, y la rótula no cerraba cuando la "
            "columna transmitía momento (defecto D3, mecanismo M2).",
            f"Los valores de DISEÑO de la viga se toman sobre el tramo "
            f"{s_ini_viga:.3f} ≤ s ≤ {s_cut:.3f} m. El tramo 0 ≤ s ≤ {L1:.3f} m es la "
            f"ZAPATA exterior y sus esfuerzos los verifica el motor de zapata con §15.4, "
            f"§15.5 y §11.12.",
            "La reacción del terreno existe solo bajo la zapata exterior. El tramo entre el "
            "borde de esa zapata y el eje de la columna interior salva un vano sin apoyo.",
            "No se reutiliza `analysis/beam_diagram.py`: ese módulo supone un elemento "
            "apoyado sobre el suelo en toda su longitud y aquí eso es falso.",
            "El cortante de diseño NO se reduce a «d de la cara»: E.060 §11.1.3.1 condiciona "
            "esa reducción a que la reacción introduzca compresión en la zona de apoyo, y el "
            "tramo central de esta viga no está apoyado.",
        ],
    )
