"""Diagramas de cortante y momento a lo largo de una zapata — Fase 2.

BASE NORMATIVA
==============
E.060 §15.4.1, verbatim:

  "El momento flector en CUALQUIER SECCIÓN de una zapata debe determinarse pasando
   un plano vertical a través de la zapata, y calculando el momento de las fuerzas
   que actúan sobre el área total de la zapata que quede a un lado de dicho plano
   vertical."

Ésta es la regla GENERAL y es exactamente lo que hace este módulo. Conviene notar
que §15.4.2 —el que fija la sección crítica en la cara de la columna— está
acotado explícitamente a "una zapata AISLADA"; para una zapata que soporta más de
una columna manda §15.10.1, que remite a "los requisitos de diseño apropiados de
esta Norma", y el apropiado para el momento es §15.4.1.

Por eso el cálculo de M(x) por estática **no es una derivación**: es la aplicación
directa de §15.4.1. Lo que sí es derivación es la forma cerrada de las integrales,
que se escribe abajo.

E.060 §15.10.2 prohíbe expresamente usar el Método Directo de Diseño del
Capítulo 13 en zapatas combinadas. Este módulo no lo usa.

E.060 §15.10.3 exige que la distribución de presiones sea "consistente con las
propiedades del suelo y la estructura y con los principios establecidos de
mecánica de suelos". La hipótesis adoptada —zapata rígida, distribución lineal—
se declara como tal en el resultado; no se da por supuesta.

MODELO
======
La zapata se toma como cuerpo rígido en equilibrio bajo:

  - la reacción del suelo, distribuida linealmente y dirigida HACIA ARRIBA;
  - las cargas de columna, puntuales y dirigidas HACIA ABAJO.

El peso propio NO interviene: está equilibrado por una reacción igual y opuesta
directamente debajo, de modo que no produce cortante ni momento netos. Es el
mismo criterio que ya aplica el motor en la flexión de zapata aislada.

FORMA CERRADA (derivación)
==========================
Con la carga repartida ascendente w(x) = w0 + (w1 - w0)·x/L y cargas puntuales
P_i en x_i, midiendo x desde el extremo de menor coordenada:

    V(x) = w0·x + (w1 - w0)·x²/(2L)  -  Σ_{x_i ≤ x} P_i

    M(x) = w0·x²/2 + (w1 - w0)·x³/(6L)  -  Σ_{x_i ≤ x} P_i·(x - x_i)

Los extremos de M están donde V = 0. En cada intervalo entre cargas puntuales,
V(x) = 0 es una ecuación de segundo grado que se resuelve exactamente: muestrear
y quedarse con el máximo daría un valor sistemáticamente por debajo del real.

SIGNOS
======
M positivo = tracción en la CARA INFERIOR (voladizos).
M negativo = tracción en la CARA SUPERIOR (entre columnas).
Es la convención habitual de vigas y determina qué cara se arma.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

# Tolerancia para considerar que dos posiciones coinciden o que un valor es nulo.
TOL_M = 1e-9


class PointLoad(BaseModel):
    """Una carga de columna sobre el eje analizado."""

    label: str
    position_m: float = Field(..., description="Posición del eje de la columna, medida desde x=0")
    P_kN: float = Field(..., description="Carga vertical descendente [kN]")
    M_kNm: float = Field(
        default=0.0,
        description=(
            "Momento aplicado por la columna en la dirección analizada [kN·m]. Positivo "
            "desplaza la resultante hacia +x, igual que en E.050 art. 28.1."
        ),
    )
    width_m: float = Field(..., description="Dimensión de la columna en la dirección analizada")


class DiagramPoint(BaseModel):
    x_m: float
    V_kN: float
    M_kNm: float
    description: str


class BeamDiagram(BaseModel):
    """Diagramas de una zapata analizada longitudinalmente."""

    length_m: float
    width_m: float
    w_start_kNm: float = Field(..., description="Carga repartida ascendente en x=0 [kN/m]")
    w_end_kNm: float = Field(..., description="Carga repartida ascendente en x=L [kN/m]")
    loads: list[PointLoad]

    critical_points: list[DiagramPoint]
    M_max_positive_kNm: float = Field(..., description="Momento positivo máximo (tracción abajo)")
    M_max_negative_kNm: float = Field(..., description="Momento negativo máximo, en valor absoluto")
    x_M_max_positive_m: float
    x_M_max_negative_m: float
    V_max_abs_kN: float

    equilibrium_residual_kN: float = Field(
        ..., description="Suma de fuerzas verticales; debe ser ~0 si el modelo cierra"
    )
    hypotheses: list[str]

    @property
    def has_negative_moment(self) -> bool:
        """Si es True hace falta acero en la CARA SUPERIOR."""
        return self.M_max_negative_kNm > TOL_M


def _shear(x: float, w0: float, w1: float, L: float, loads: list[PointLoad]) -> float:
    v = w0 * x + (w1 - w0) * x * x / (2.0 * L)
    for load in loads:
        if load.position_m <= x + TOL_M:
            v -= load.P_kN
    return v


def _moment(x: float, w0: float, w1: float, L: float, loads: list[PointLoad]) -> float:
    m = w0 * x * x / 2.0 + (w1 - w0) * x**3 / (6.0 * L)
    for load in loads:
        if load.position_m <= x + TOL_M:
            m -= load.P_kN * (x - load.position_m)
            # Un momento aplicado no produce cortante, pero SALTA el diagrama de
            # momentos al pasar por su punto de aplicación.
            #
            # EL SIGNO DEL SALTO (corregido el 2026-09-22, validación Aragón CR2 §3.5)
            # ========================================================================
            # M > 0 corre la carga hacia +x (E.050 art. 28.1), que es como lo usa el campo
            # de presiones de este mismo módulo: `x_R = (Σ Pᵢxᵢ + Σ Mᵢ)/Σ Pᵢ`. Equivale a
            # Pᵢ aplicada en `xᵢ + Mᵢ/Pᵢ`, cuya contribución al momento flector —positivo,
            # tracción abajo— es `−Pᵢ·(x − xᵢ) + Mᵢ`. De ahí el `+=`.
            #
            # Estuvo en `−=` desde la Fase 2, y el diagrama NO cerraba: con `−=` el
            # extremo libre vale `M(L) = −2·Σ Mᵢ` en vez de cero. El control de equilibrio
            # era solo de FUERZA, y un par mal signado no produce residuo de fuerza. Con
            # momentos de columna el acero SUPERIOR de la combinada salía subestimado, del
            # lado inseguro. `docs/validacion_aragon_3_5_combinada.md`.
            m += load.M_kNm
    return m


def _zero_shear_points(w0: float, w1: float, L: float, loads: list[PointLoad]) -> list[float]:
    """Puntos donde V = 0, resueltos EXACTAMENTE intervalo por intervalo.

    En cada tramo entre cargas puntuales, V(x) = a·x² + b·x + c con
        a = (w1 - w0)/(2L),  b = w0,  c = -Σ P_i acumulada hasta el tramo.
    Muestrear en vez de resolver daría un momento máximo sistemáticamente menor
    que el real, es decir del lado inseguro."""
    fronteras = sorted({0.0, L} | {ld.position_m for ld in loads})
    puntos: list[float] = []

    for izq, der in zip(fronteras, fronteras[1:]):
        if der - izq < TOL_M:
            continue
        interior = (izq + der) / 2.0
        acumulado = sum(ld.P_kN for ld in loads if ld.position_m <= interior + TOL_M)
        a = (w1 - w0) / (2.0 * L)
        b = w0
        c = -acumulado

        if abs(a) < TOL_M:
            if abs(b) > TOL_M:
                raices = [-c / b]
            else:
                raices = []
        else:
            disc = b * b - 4.0 * a * c
            raices = [] if disc < 0 else [
                (-b + math.sqrt(disc)) / (2.0 * a),
                (-b - math.sqrt(disc)) / (2.0 * a),
            ]

        for r in raices:
            if izq - TOL_M <= r <= der + TOL_M:
                puntos.append(min(max(r, izq), der))
    return puntos


def build_beam_diagram(
    length_m: float,
    width_m: float,
    loads: list[PointLoad],
    hypotheses: list[str] | None = None,
) -> BeamDiagram:
    """Diagramas V(x) y M(x) de una zapata bajo N cargas de columna.

    La distribución de presiones se obtiene del EQUILIBRIO: su resultante debe
    igualar la suma de cargas y estar aplicada en el mismo punto. De ahí salen w0 y
    w1 sin necesidad de suponer nada más que la linealidad."""
    if length_m <= 0 or width_m <= 0:
        raise ValueError(f"Dimensiones inválidas: length={length_m}, width={width_m}.")
    if not loads:
        raise ValueError("Se requiere al menos una carga de columna.")
    for ld in loads:
        if not (-TOL_M <= ld.position_m <= length_m + TOL_M):
            raise ValueError(
                f"La columna «{ld.label}» está en x={ld.position_m} m, fuera de la zapata "
                f"(0 a {length_m} m)."
            )

    P_total = sum(ld.P_kN for ld in loads)
    if P_total <= 0:
        raise ValueError(f"La carga vertical total debe ser positiva; recibido {P_total} kN.")

    # Posición de la resultante. Los momentos aplicados por las columnas la desplazan
    # aunque no aporten carga vertical: tomando momentos respecto de x=0,
    #     x_R = (Σ P_i·x_i + Σ M_i) / Σ P_i
    x_resultante = (
        sum(ld.P_kN * ld.position_m for ld in loads) + sum(ld.M_kNm for ld in loads)
    ) / P_total

    # La reacción del suelo debe tener la misma resultante y el mismo punto de
    # aplicación. Para una distribución lineal w(x) = w0 + (w1-w0)x/L:
    #     ∫w dx = (w0 + w1)/2 · L = P_total
    #     ∫w·x dx / P_total = x_resultante
    # De la segunda: (w0/2 + (w1-w0)/3)·L² = P_total·x_resultante
    # Resolviendo el sistema:
    #     w0 = (2·P_total/L)·(2 - 3·x_resultante/L)
    #     w1 = (2·P_total/L)·(3·x_resultante/L - 1)
    k = 2.0 * P_total / length_m
    r = x_resultante / length_m
    w0 = k * (2.0 - 3.0 * r)
    w1 = k * (3.0 * r - 1.0)

    hips = list(hypotheses or [])
    hips.append(
        "Zapata rígida con distribución lineal de presiones (E.060 §15.10.3 exige que la "
        "distribución sea consistente con el suelo y la estructura; la linealidad es la "
        "hipótesis adoptada y queda declarada, no supuesta en silencio)."
    )
    hips.append(
        "El peso propio no interviene en los diagramas: está equilibrado por una reacción "
        "igual y opuesta directamente debajo, de modo que no produce cortante ni momento netos."
    )
    if w0 < -TOL_M or w1 < -TOL_M:
        hips.append(
            f"ATENCIÓN: la distribución lineal da presión NEGATIVA en un extremo "
            f"(w0={w0:.2f}, w1={w1:.2f} kN/m). El suelo no resiste tracción (E.060 §15.2): "
            f"la resultante cae fuera del núcleo central y este modelo deja de ser válido."
        )

    # --- Secciones críticas: caras de columna, ejes, extremos y V=0 ---
    candidatos: list[tuple[float, str]] = [(0.0, "extremo x=0"), (length_m, f"extremo x={length_m:.3f}")]
    for ld in loads:
        candidatos.append((ld.position_m, f"eje de {ld.label}"))
        for signo, lado in ((-1.0, "izquierda"), (1.0, "derecha")):
            x = ld.position_m + signo * ld.width_m / 2.0
            if -TOL_M <= x <= length_m + TOL_M:
                candidatos.append((min(max(x, 0.0), length_m), f"cara {lado} de {ld.label}"))
    for x in _zero_shear_points(w0, w1, length_m, loads):
        candidatos.append((x, "cortante nulo (extremo de M)"))

    vistos: dict[float, str] = {}
    for x, desc in candidatos:
        clave = round(x, 9)
        if clave not in vistos:
            vistos[clave] = desc

    puntos = [
        DiagramPoint(
            x_m=x,
            V_kN=_shear(x, w0, w1, length_m, loads),
            M_kNm=_moment(x, w0, w1, length_m, loads),
            description=vistos[x],
        )
        for x in sorted(vistos)
    ]

    # CIERRE DE MOMENTOS (2026-09-22). El extremo libre x = L no tiene momento: si el
    # diagrama no llega ahí a cero, el campo de presiones y las cargas describen cuerpos
    # distintos y ningún momento de diseño que salga de él significa nada. Hasta esta fecha
    # solo se comprobaba el cierre de FUERZA, y un par con el signo equivocado lo pasaba
    # intacto: dejó el extremo en −2·Σ Mᵢ durante toda la vida del módulo sin que nada lo
    # detectara. Se exige aquí, para cualquier entrada, y no solo en los tests.
    escala = sum(abs(ld.P_kN) * length_m + abs(ld.M_kNm) for ld in loads)
    cierre = _moment(length_m, w0, w1, length_m, loads)
    if abs(cierre) > 1e-9 * max(escala, 1.0):
        raise ArithmeticError(
            f"El diagrama de momentos no cierra: M(L) = {cierre:.6g} kN·m en el extremo libre, "
            f"donde el equilibrio exige cero. El campo de presiones y las cargas aplicadas "
            f"no describen el mismo cuerpo."
        )

    momentos = [(p.M_kNm, p.x_m) for p in puntos]
    m_pos, x_pos = max(momentos, key=lambda t: t[0])
    m_neg, x_neg = min(momentos, key=lambda t: t[0])

    return BeamDiagram(
        length_m=length_m, width_m=width_m,
        w_start_kNm=w0, w_end_kNm=w1, loads=loads,
        critical_points=puntos,
        M_max_positive_kNm=max(m_pos, 0.0),
        x_M_max_positive_m=x_pos,
        M_max_negative_kNm=max(-m_neg, 0.0),
        x_M_max_negative_m=x_neg,
        V_max_abs_kN=max(abs(p.V_kN) for p in puntos),
        equilibrium_residual_kN=(w0 + w1) / 2.0 * length_m - P_total,
        hypotheses=hips,
    )


# =========================================================================
# Cortante unidireccional de diseño: a d de la cara (E.060 §15.5.2, §11.1.3.1)
# =========================================================================


class CriticalShear(BaseModel):
    """Cortante de diseño a lo largo de la zapata y la sección que lo da."""

    Vu_kN: float = Field(..., description="|V| de diseño [kN]")
    x_m: float | None = Field(default=None, description="Posición de la sección que gobierna")
    column_label: str | None = None
    side: str | None = Field(default=None, description='"izquierda" | "derecha" de la columna')
    at_face: bool = Field(
        default=False,
        description="True si la sección se tomó en la CARA porque no se cumple §11.1.3 (c)",
    )
    method: str = Field(..., description='"a_d_de_la_cara" | "maximo_del_diagrama"')
    note: str


def critical_one_way_shear(diagram: BeamDiagram, d_m: float) -> CriticalShear:
    """Cortante unidireccional de diseño de una zapata de varias columnas.

    NORMA (docs/normativa/texto/e.060-concreto-armado-sencico.txt)
    ================================================================
    - §15.5.2: la sección crítica de cortante se mide desde las secciones de §15.4.2, es
      decir, desde la CARA de la columna.
    - §11.12.1.1: el comportamiento como viga se diseña con 11.1 a 11.5.
    - §11.1.3 y §11.1.3.1: se permite diseñar las secciones entre la cara y la distancia d
      con el Vu calculado a d, si (a) la reacción del apoyo introduce compresión en las zonas
      extremas, (b) las cargas están aplicadas en o cerca de la cara superior y (c) no hay
      cargas concentradas entre la cara y la sección crítica.

    LECTURA PARA UNA ZAPATA (interpretación, la misma que el motor ya usa en la aislada y en
    el cortante transversal de la combinada): es una viga INVERTIDA. La columna es el apoyo y
    comprime la zona de la cara (a); la presión del suelo es la carga y actúa sobre la cara
    opuesta a la del apoyo, que en la viga invertida es la «superior» (b). La condición (c)
    sí puede fallar: si otra columna queda entre la cara y la sección a d, en ese lado la
    sección se toma en la CARA.

    POR QUÉ BASTAN ESAS SECCIONES. Con presión w(x) ≥ 0 en toda la zapata, V(x) no decrece
    entre dos cargas de columna (dV/dx = w ≥ 0). Entre dos secciones críticas consecutivas,
    y en el voladizo hacia un extremo libre, |V| alcanza su máximo en las propias secciones
    críticas. Lo que queda entre la cara y su sección a d lo cubre §11.1.3.1. Por eso el
    máximo de |V| en las secciones críticas es el cortante de diseño de toda la zapata.

    Si la sección a d cae fuera de la zapata, el voladizo es más corto que d: no hay sección
    que verificar en ese lado (el mismo criterio que `shear_force_at_d_from_face` en la
    aislada).

    Si la presión lineal sale NEGATIVA en algún extremo, la monotonía no vale (y la
    geometría ya está fuera del núcleo central). Se conserva entonces el criterio anterior,
    máx |V| de todo el diagrama, que es el conservador.
    """
    if diagram.w_start_kNm < -TOL_M or diagram.w_end_kNm < -TOL_M:
        return CriticalShear(
            Vu_kN=diagram.V_max_abs_kN, method="maximo_del_diagrama",
            note=(
                "Presión lineal negativa en un extremo: no se puede reducir el cortante a la "
                "sección a d (V no es monótono). Se toma máx |V| del diagrama, conservador."
            ),
        )
    L = diagram.length_m
    w0, w1 = diagram.w_start_kNm, diagram.w_end_kNm
    cargas = diagram.loads

    def hay_otra_entre(i: int, a: float, b: float) -> bool:
        lo, hi = min(a, b), max(a, b)
        for j, ld in enumerate(cargas):
            if j == i:
                continue
            izq, der = ld.position_m - ld.width_m / 2.0, ld.position_m + ld.width_m / 2.0
            if der > lo + TOL_M and izq < hi - TOL_M:
                return True
        return False

    mejor: CriticalShear | None = None
    for i, ld in enumerate(cargas):
        for signo, lado in ((-1.0, "izquierda"), (1.0, "derecha")):
            cara = ld.position_m + signo * ld.width_m / 2.0
            seccion = cara + signo * d_m
            if hay_otra_entre(i, cara, min(max(seccion, 0.0), L)):
                x, en_cara = min(max(cara, 0.0), L), True
            elif seccion < -TOL_M or seccion > L + TOL_M:
                continue  # voladizo más corto que d: no hay sección que verificar
            else:
                x, en_cara = seccion, False
            V = abs(_shear(x, w0, w1, L, cargas))
            if mejor is None or V > mejor.Vu_kN + 1e-12:
                mejor = CriticalShear(
                    Vu_kN=V, x_m=x, column_label=ld.label, side=lado, at_face=en_cara,
                    method="a_d_de_la_cara",
                    note=(
                        f"Sección crítica {'en la CARA' if en_cara else f'a d = {d_m:.3f} m de la cara'} "
                        f"{lado} de {ld.label}, x = {x:.3f} m: |V| = {V:.2f} kN"
                        + (" (otra columna entre la cara y la sección a d: §11.1.3 (c) no se cumple)"
                           if en_cara else " (E.060 §15.5.2 y §11.1.3.1)")
                        + f". Máx |V| del diagrama, que ya no se usa para diseñar: {diagram.V_max_abs_kN:.2f} kN."
                    ),
                )
    if mejor is None:
        return CriticalShear(
            Vu_kN=0.0, method="a_d_de_la_cara",
            note="Todos los voladizos son más cortos que d y no hay tramos entre columnas: no hay sección crítica.",
        )
    return mejor


# =========================================================================
# Predimensionamiento: longitud que centra la resultante
# =========================================================================


class CenteringLength(BaseModel):
    """Longitud que hace coincidir el centroide de la zapata con la resultante.

    ES UN CRITERIO DE PREDIMENSIONAMIENTO, NO UNA EXIGENCIA
    =======================================================
    Ninguna disposición de E.060 ni de E.050 obliga a centrar la resultante. Lo que
    la norma exige es que no haya tracciones en el suelo (E.060 §15.2) y que la
    presión no supere la admisible; centrar la resultante es una forma cómoda de
    conseguir ambas cosas —deja presión uniforme— y es lo que hace la práctica
    habitual, pero no es la única solución válida.

    Se ofrece como AYUDA de predimensionamiento. El resultado debe verificarse
    igual que cualquier otra geometría."""

    length_m: float = Field(..., description="Longitud que centra la resultante")
    resultant_from_first_column_m: float = Field(
        ..., description="Distancia de la resultante a la primera columna"
    )
    first_column_offset_m: float = Field(
        ..., description="Distancia del extremo de la zapata al eje de la primera columna"
    )
    feasible: bool = Field(
        ..., description="False si la longitud resultante no alcanza a cubrir las columnas"
    )
    note: str


def length_to_center_resultant(
    column_positions_m: list[float],
    column_loads_kN: list[float],
    column_moments_kNm: list[float] | None = None,
    start_offset_m: float = 0.0,
) -> CenteringLength:
    """Longitud L tal que el centroide de la zapata caiga sobre la resultante.

    `column_positions_m` se mide desde el eje de la PRIMERA columna;
    `start_offset_m` es cuánto sobresale la zapata más allá de esa columna — para
    una columna de límite de propiedad vale la mitad de su ancho, porque la cara
    queda al ras.

    Con la resultante a distancia `x_R` del extremo de la zapata, centrarla exige
    L = 2·x_R. De ahí sale directamente la longitud."""
    if len(column_positions_m) != len(column_loads_kN):
        raise ValueError("Deben coincidir el número de posiciones y de cargas.")
    momentos = column_moments_kNm or [0.0] * len(column_loads_kN)
    P_total = sum(column_loads_kN)
    if P_total <= 0:
        raise ValueError(f"La carga total debe ser positiva; recibido {P_total} kN.")

    x_R_desde_primera = (
        sum(P * x for P, x in zip(column_loads_kN, column_positions_m)) + sum(momentos)
    ) / P_total
    x_R_desde_extremo = x_R_desde_primera + start_offset_m
    L = 2.0 * x_R_desde_extremo

    # La zapata debe llegar, al menos, hasta la última columna.
    alcance_necesario = start_offset_m + max(column_positions_m)
    factible = L >= alcance_necesario - TOL_M

    return CenteringLength(
        length_m=L,
        resultant_from_first_column_m=x_R_desde_primera,
        first_column_offset_m=start_offset_m,
        feasible=factible,
        note=(
            f"L = 2·{x_R_desde_extremo:.4f} = {L:.4f} m centra la resultante y deja presión "
            f"uniforme. CRITERIO DE PREDIMENSIONAMIENTO: ni E.060 ni E.050 obligan a centrar "
            f"la resultante; lo que exigen es ausencia de tracciones (§15.2) y presión dentro "
            f"de la admisible. La geometría propuesta debe verificarse igual que cualquier otra."
            + ("" if factible else
               f" ATENCIÓN: L = {L:.3f} m no alcanza a cubrir hasta la última columna, que "
               f"requiere al menos {alcance_necesario:.3f} m. La resultante no puede centrarse "
               f"con esta disposición de cargas.")
        ),
    )
