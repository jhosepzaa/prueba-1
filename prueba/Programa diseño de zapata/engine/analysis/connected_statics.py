"""Estática de la zapata conectada — Fase 4A.

QUÉ RESUELVE Y POR QUÉ NO ES NORMATIVO
======================================
E.060 no tiene ningún artículo para la zapata conectada: §15.10 cubre «las zapatas
que soporten más de una columna», y aquí hay dos zapatas de una columna cada una.
E.050 art. 23.2 reconoce la tipología pero no prescribe método.

De modo que el reparto del par entre las dos zapatas es **estática pura — nivel B,
derivación declarada**. No hay ninguna ecuación normativa que citar, y este módulo
no inventa ninguna: plantea el equilibrio de un cuerpo libre y lo resuelve.

POR QUÉ SE PLANTEA EL SISTEMA Y NO SE ESCRIBE LA FÓRMULA CERRADA
===============================================================
La forma cerrada clásica —R = P·S/(S − e)— es fácil de escribir y fácil de escribir
MAL: basta invertir un signo o medir una distancia desde otro origen para obtener
números plausibles y equivocados. Aquí el cuerpo libre se ENSAMBLA a partir de sus
fuerzas y el sistema se resuelve como tal. La forma cerrada existe solo en los
tests, como verificación independiente, y es ahí donde se contrasta contra el
benchmark.

CONVENCIÓN DE SIGNOS — EXPLÍCITA Y ÚNICA
========================================
Coordenada `s`: recorre el eje longitudinal del sistema. **Origen en el borde de
lindero de la zapata exterior; positiva hacia el interior.**

    s = 0        borde de lindero
    s = a        eje de la columna exterior, con a = holgura + b_col/2
    s = L1       borde interior de la zapata exterior
    s = a + S    eje de la columna interior

Fuerzas verticales: **positivas hacia ARRIBA**. Una carga de columna en compresión
es una fuerza hacia abajo sobre la zapata, de modo que entra como −P.

Momentos: **positivo el que, sobre el eje s con las verticales hacia arriba, produce
un giro antihorario**. El momento de una fuerza vertical F_up aplicada en s_i,
tomado respecto de un punto s_c, vale (s_i − s_c) · F_up.

EL PESO PROPIO DE LAS ZAPATAS NO ENTRA AQUÍ
===========================================
`evaluate_candidate` calcula el peso propio de cada zapata y el relleno sobre ella
por su cuenta. Si este módulo lo incluyera, se contaría dos veces.

Y no hace falta incluirlo: el peso propio de una zapata de espesor uniforme actúa en
su MISMO centroide que la resultante del suelo, de modo que en la ecuación de
momentos sus términos se agrupan y desaparecen. Lo que este módulo resuelve es la
resultante NETA de peso propio, que es exactamente la carga equivalente en la base
de la columna que `evaluate_candidate` espera recibir.

Esa agrupación es válida mientras el peso propio actúe en el centroide de la zapata
—espesor uniforme— y queda declarada como hipótesis en la traza.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectedFootingLayout,
    CoupleTransferMode,
    Footprints,
    check_beam_support_supported,
    check_couple_mode_compatible,
)
from engine.foundation.self_weight import compute_self_weight
from engine.domain.loads import (
    ComponentAction,
    LoadCaseSet,
    LoadCombination,
    LoadCombinationType,
    LoadComposition,
)

# Tolerancia con la que se considera cerrado un equilibrio, en kN y kN·m.
EQUILIBRIUM_TOL = 1e-6

# Nota del peso propio de las ZAPATAS. Es propia de la estrategia ARTICULADA: la
# agrupación que la justifica —resultante del suelo y peso propio actuando en el mismo
# centroide— solo vale cuando la resultante pasa por el centroide, que es justamente lo
# que impone el modelo articulado. En cuerpo rígido NO vale y el peso propio deberá
# entrar en el reparto (ver F2 en `_distribute_rigid_body`).
SELF_WEIGHT_NOTE = (
    "El peso propio de cada ZAPATA no entra en este reparto, y no por descuido: lo "
    "calcula `foundation/self_weight.py` dentro de cada solver de zapata. Incluirlo aquí "
    "lo contaría DOS VECES. Y no hace falta incluirlo: con espesor uniforme actúa en el "
    "mismo centroide que la resultante del suelo, de modo que sus términos se agrupan en "
    "la ecuación de momentos y el reparto queda planteado sobre cargas netas en la base "
    "de la columna, que es justo lo que el solver de zapata espera recibir."
)

# TBD-C1 — la premisa de presión uniforme, enunciada con precisión.
#
# QUÉ SUPONE EXACTAMENTE EL MODELO. Tres cosas encadenadas, no una:
#
#   (a) La viga impide el GIRO de la zapata de lindero.
#   (b) En consecuencia, la resultante del suelo pasa por el centroide de esa zapata.
#   (c) En consecuencia, y por ser la zapata rígida, la presión es UNIFORME.
#
# Lo que el motor calcula es (b): entrega a la zapata el par que anula la
# excentricidad. (c) se sigue de (b) más la hipótesis de zapata rígida, que es la misma
# que usa cualquier zapata aislada del motor. Quien NO tiene respaldo es (a).
#
# QUÉ DICE LA NORMA, Y QUÉ NO.
#
#   - **E.060 §15.2.6 es el artículo que MÁS CERCA queda, y conviene leerlo entero:**
#     «En terrenos de baja capacidad portante o cimentaciones sobre pilotes, deberá
#     analizarse la necesidad de conectar las zapatas mediante vigas, evaluándose en el
#     diseño el comportamiento de éstas de acuerdo a su rigidez y la del conjunto
#     suelo-cimentación.» O sea: la norma EXIGE evaluar la rigidez, y no da método ni
#     umbral con que hacerlo. No es que falte respaldo para la pregunta —la pregunta es
#     normativa—: falta el criterio con que responderla. Por eso la premisa se declara y
#     queda NO VERIFICADA en vez de darse por cumplida.
#   - E.060 §21.12.3.2 fija una DIMENSIÓN TRANSVERSAL MÍNIMA de la viga
#     (>= luz libre/20, tope 450 mm) y la separación de estribos cerrados. Es un
#     requisito dimensional, verificable, y el motor lo verifica: aparece en la traza de
#     la viga como PASS o FAIL. **No es una comprobación de rigidez.** Cumplirlo no dice
#     nada sobre si la viga impide el giro.
#   - E.060 §15.10.3 exige que la distribución de presiones «debe ser consistentes con
#     las propiedades del suelo y la estructura y con los principios establecidos de
#     mecánica de suelos», pero está escrito para zapatas COMBINADAS y losas —«zapatas
#     que soporten más de una columna»— y no alcanza a la conectada, que son dos zapatas
#     de una columna cada una.
#   - E.060 §15.2.3: «En el cálculo de las presiones de contacto entre las zapatas y el
#     suelo solo se aceptará que ocurran compresiones sobre el suelo.» Se verifica, y es
#     independiente de esto.
#   - E.050 art. 26.3, sobre plateas, deja en manos del proyectista estructural el
#     espesor y los peraltes «para garantizar la rigidez de la cimentación». Es otra
#     tipología, pero muestra el criterio de la norma: delega la rigidez, no la tasa.
#   - h ≈ L/7 de los apuntes es predimensionamiento profesional, nivel C. No puede
#     producir PASS ni FAIL.
#
# CONCLUSIÓN: no existe requisito normativo de presión uniforme ni criterio normativo
# para verificar la rigidez de la viga. La premisa (a) es una HIPÓTESIS DE MODELACIÓN
# sin respaldo citable y se mantiene NO VERIFICADA. Convertirla en una verificación
# apoyándose en §21.12.3.2 sería fabricar un requisito que la norma no contiene.
UNIFORM_PRESSURE_PREMISE = (
    "TBD-C1 — HIPÓTESIS DE MODELACIÓN NO VERIFICADA. El modelo articulado supone que la "
    "viga impide el giro de la zapata de lindero; de ahí que su resultante pase por el "
    "centroide y su presión resulte uniforme. E.060 §15.2.6 EXIGE evaluar el "
    "comportamiento de las vigas de conexión «de acuerdo a su rigidez y la del conjunto "
    "suelo-cimentación», pero no prescribe método ni umbral: la pregunta es normativa y el "
    "criterio para responderla no está en ninguna fuente del proyecto. §21.12.3.2 fija una "
    "dimensión transversal mínima de la viga —requisito dimensional que el motor sí "
    "verifica— pero no una comprobación de rigidez del conjunto, y §15.10.3 está escrito "
    "para zapatas combinadas y losas, no para la conectada. La regla h ≈ L/7 de los apuntes es "
    "práctica profesional, nivel C. Si la viga no fuera lo bastante rígida, la presión "
    "bajo la zapata de lindero dejaría de ser uniforme, su qmax sería mayor que el "
    "calculado y el resultado dejaría de ser conservador: por eso esta entrada puede "
    "producir un falso PASS y se mantiene en NO VERIFICADO."
)

STIFFNESS_DECLARED_NOTE = (
    "TBD-C1 — DECLARACIÓN DEL PROYECTISTA (decisión 4, 2026-09-20). El profesional "
    "responsable declara que el modelo adoptado para la viga de conexión y el conjunto "
    "suelo-cimentación satisface la condición de comportamiento que exige E.060 §15.2.6. "
    "EL MOTOR NO LO HA COMPROBADO y no afirma haberlo hecho: la norma exige la evaluación "
    "pero no prescribe método ni umbral, y ninguna fuente del proyecto lo suple, de modo "
    "que la pregunta solo puede responderla quien firma el diseño. Es el mismo reparto de "
    "responsabilidad con que se declaran μ, los factores de seguridad o el factor de carga "
    "muerta del peso propio de la viga. Esta declaración levanta ÚNICAMENTE este bloqueo: "
    "no convierte el resultado en conforme, y cualquier otra verificación en NO VERIFICADO "
    "o cualquier otro TBD abierto lo sigue impidiendo por su cuenta."
)

STIFFNESS_NOT_DECLARED_NOTE = (
    "TBD-C1 — NO DECLARADA. El proyectista no se ha pronunciado sobre §15.2.6, de modo que "
    "la premisa sigue siendo una hipótesis de modelación sin respaldo y la alternativa no "
    "puede presentarse como conforme. Para pronunciarse, declare "
    "`stiffness_declaration = DECLARADA_POR_PROYECTISTA` en la viga."
)

UNIFORM_PRESSURE_NOT_A_CODE_CHECK = (
    "Cumplir §21.12.3.2 NO verifica esta premisa. Son cosas distintas: aquél es un "
    "mínimo de dimensión transversal; ésta es una condición de rigidez que ninguna norma "
    "cuantifica."
)


# TBD-C5 — qué se hizo con el peso propio de la viga. Un texto por alternativa: las
# tres dan W = 0 o W > 0 en el equilibrio, pero significan cosas distintas y la traza
# tiene que poder distinguirlas.
BEAM_SELF_WEIGHT_NOTES: dict[BeamSelfWeightMode, str] = {
    BeamSelfWeightMode.EXPLICITO: (
        "TBD-C5: peso propio de la viga modelado EXPLÍCITAMENTE, {W:.2f} kN, calculado por "
        "geometría física e introducido en las ecuaciones de equilibrio. No se suma en "
        "ningún otro sitio."
    ),
    BeamSelfWeightMode.EN_CARGAS_DE_COLUMNA: (
        "TBD-C5: el usuario declara que el peso propio de la viga YA ESTÁ INCLUIDO en las "
        "cargas P de columna que entregó. El motor no lo vuelve a sumar: hacerlo lo "
        "contaría dos veces."
    ),
    BeamSelfWeightMode.DESPRECIADO: (
        "TBD-C5: peso propio de la viga DESPRECIADO por decisión declarada del "
        "proyectista. No está en el equilibrio ni en ninguna otra parte del cálculo. Es "
        "una omisión consciente, no una cobertura: ni E.060 ni E.050 dicen cómo "
        "contabilizarlo."
    ),
}

# TBD-C13 — PENDIENTE INDEPENDIENTE de 9a/9c. Solo documenta: no cambia ningún cálculo
# ni ningún estado. Ver `docs/tbd_c13_factorizacion_peso_viga.md`.
BEAM_SELF_WEIGHT_FACTORING_PENDING = (
    "TBD-C13 — FALTA UN DATO: el factor de carga muerta del peso propio de la viga en las "
    "combinaciones FACTORIZADAS del modo directo. Con peso propio EXPLICITO el peso entra con "
    "el MISMO valor en servicio y en factorizadas porque el motor no le aplica ningún factor, "
    "y no puede inferirlo: recibe la combinación ya formada y desconoce su composición. El "
    "factor de CM además CAMBIA entre combinaciones (E.060 §9.2: 1,4; 1,25; 0,9), de modo que "
    "sin factor el peso queda subestimado frente a 1,4 y sobrestimado frente a 0,9 —esto "
    "último es lo desfavorable para despegue y volcamiento—. CONSECUENCIA: puede subestimar "
    "las cargas corregidas de las dos zapatas y los esfuerzos de diseño de la viga, y por eso "
    "esta entrada queda NO VERIFICADA. SALIDAS: declarar "
    "`beam.self_weight_dead_load_factor` (decisión A′), o usar el modo de cargas POR CASOS, "
    "donde el factor sale de la composición."
)

BEAM_SELF_WEIGHT_FACTOR_DECLARED = (
    "TBD-C13 (A′) — modo directo: el proyectista declara f_CM = {f:g} para el peso propio de "
    "la viga en las combinaciones FACTORIZADAS. Es un dato del proyecto, no un valor del "
    "motor: E.060 §9.2 no fija uno único, y el motor no puede inferirlo de una combinación ya "
    "formada. Las combinaciones de SERVICIO llevan el peso real, sin factor."
)


def factoring_pending_applies(combo: LoadCombination, beam_weight_kN: float) -> bool:
    """¿Afecta TBD-C13 a esta combinación? Solo factorizadas, con peso de viga modelado y
    en el modo de combinaciones DIRECTAS. En el modo por casos la composición es conocida y
    el peso recibe el factor CM de la combinación (Fase 10B, CC-3)."""
    return (
        combo.type is LoadCombinationType.FACTORIZADA
        and beam_weight_kN > 0.0
        and combo.composition is None
    )


BEAM_WEIGHT_FACTORED_NOTE = (
    "Fase 10B (CC-3) — modo de cargas por casos: el peso propio de la viga es CARGA MUERTA "
    "(E.020 art. 2, «incluyendo su peso propio») y recibe el factor de los casos CM de esta "
    "combinación, {f:.4g}, declarado por el usuario. Si la combinación no contiene CM, el "
    "factor es 0: la combinación declarada no incluye carga muerta."
)


UPLIFT_NOT_SOLVED = (
    "DESPEGUE — LIMITACIÓN DECLARADA. El motor DETECTA que la presión resulta negativa "
    "en algún punto del área de apoyo, y ahí se detiene. NO resuelve contacto "
    "unilateral: el campo lineal σ = P/A ± M·y/I supone que toda la huella trabaja, y "
    "cuando una parte se levanta esa hipótesis deja de valer. Las resultantes bajo cada "
    "zapata quedarían mal, no solo la presión de un extremo. E.060 §15.2 prohíbe "
    "considerar tracciones. Resolverlo exigiría redistribuir sobre el área realmente "
    "comprimida, que es un modelo distinto y no está implementado."
)

RIGID_BODY_PREMISE = (
    "TBD-C1 en su forma RÍGIDA — HIPÓTESIS DE MODELACIÓN NO VERIFICADA. El modelo supone "
    "que el conjunto de las dos zapatas y la viga gira como un solo cuerpo rígido. "
    "Ninguna norma da criterio para comprobar esa rigidez: E.060 §21.12.3.2 fija una "
    "dimensión transversal mínima de la viga, no una condición de rigidez del conjunto. "
    "La hipótesis no desaparece respecto del modelo articulado: cambia de forma."
)

COUPLE_TRANSFER_NOTES_RIGID = (
    "TBD-C11 no se plantea en este modelo: el conjunto es UN cuerpo y su equilibrio "
    "vertical cierra globalmente por construcción, de modo que no hay ninguna rama del "
    "par que pueda quedar fuera de la cimentación. Por eso el único modo admitido es "
    "EQUILIBRIO_EN_CIMENTACION: PAR_PURO_EN_ZAPATA exige una reacción de lindero igual a "
    "la carga de su columna, incompatible con un campo fijado por equilibrio global, y "
    "se rechaza (Fase 5A, D1)."
)

# TBD-C11 — destino de la rama cercana del par.
COUPLE_TRANSFER_NOTES: dict[CoupleTransferMode, str] = {
    CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION: (
        "TBD-C11: la rama cercana del par la toma la propia zapata de lindero, de modo "
        "que el equilibrio vertical CIERRA sobre la cimentación sola y la suma de las "
        "cargas corregidas iguala la de las aplicadas. La reacción de esa zapata resulta "
        "amplificada sobre la carga de su columna: es la lectura más exigente para ella."
    ),
    CoupleTransferMode.PAR_PURO_EN_ZAPATA: (
        "TBD-C11 — NO VERIFICADO: la viga aplica a la zapata de lindero un PAR PURO y la "
        "rama cercana se supone absorbida por la columna y el pórtico. Es el "
        "procedimiento de los apuntes CR2-93-134 §3.6. La rama transmitida al pórtico "
        "corresponde EXCLUSIVAMENTE al par; las cargas verticales gravitacionales de la "
        "viga se transmiten mediante sus reacciones (Fase 9c, B*). CONSECUENCIA DECLARADA: "
        "la carga vertical NO se conserva dentro de la cimentación —faltan exactamente las "
        "toneladas de la rama del par—, y la zapata interior queda MÁS aliviada que si "
        "la cimentación tuviera que equilibrarse sola. Que el pórtico recoja esa rama es "
        "una hipótesis sobre la superestructura que este motor NO comprueba."
    ),
}

# TBD-C4 — si la viga apoya en el terreno.
BEAM_SUPPORT_NOTES: dict[BeamSupportMode, str] = {
    BeamSupportMode.SIN_APOYO: (
        "TBD-C4: la viga NO apoya sobre el terreno (decisión de modelación declarada). Es "
        "la hipótesis que este reparto sabe resolver."
    ),
    BeamSupportMode.APOYA_EN_SUELO: (
        "TBD-C4 — NO VERIFICADO: se declaró que la viga APOYA sobre el terreno, y este "
        "motor NO modela esa reacción. Ignorarla SOBRESTIMA ΔP; como la carga corregida "
        "de la zapata interior es P_int − ΔP, la deja MENOS cargada de lo que estaría en "
        "realidad. La zapata exterior queda del lado seguro; la interior, NO. El "
        "resultado puede ser un falso PASS de la zapata interior."
    ),
}


class Force(BaseModel):
    """Una fuerza vertical del cuerpo libre, en la convención declarada arriba."""

    label: str
    s_m: float = Field(..., description="Posición sobre el eje longitudinal [m]")
    F_up_kN: float = Field(..., description="Positiva hacia ARRIBA [kN]")

    def moment_about_kNm(self, s_c_m: float) -> float:
        return (self.s_m - s_c_m) * self.F_up_kN


class AppliedMoment(BaseModel):
    """Un momento aplicado, independiente del punto respecto del cual se tome."""

    label: str
    M_kNm: float = Field(..., description="Positivo antihorario")


def applied_moment_in_free_body(M_e050_kNm: float) -> float:
    """Convierte un momento de la convención E.050 art. 28.1 a la del cuerpo libre.

    LAS DOS CONVENCIONES NO COINCIDEN, y confundirlas fue un defecto real de la Fase 4.

    E.050 art. 28.1 define `ex = Mx/Q`: un momento POSITIVO desplaza la resultante hacia
    +x. Es la convención de todo el motor —`compute_total_eccentricity` la usa— y es la
    que el usuario introduce.

    El cuerpo libre de este módulo suma momentos como `Σ (s_i − s_c)·F_up`, con las
    fuerzas positivas hacia ARRIBA. Una carga hacia abajo en s_i aporta `−P·s_i`, de
    modo que el momento estático que sitúa la resultante es el OPUESTO de esa suma. Un
    momento aplicado positivo en esta convención desplaza la resultante hacia −x.

    Entregar `Mx` sin convertir hacía que el momento de columna AUMENTARA la reacción de
    la zapata de lindero, cuando físicamente debe reducirla: un momento que empuja la
    resultante hacia el interior descarga el borde. El modelo de cuerpo rígido, que
    plantea el momento estático directamente, hacía lo contrario, y los dos modelos
    respondían al mismo dato en sentidos opuestos.

    La comprobación independiente de que esta es la conversión correcta: con ella, los
    apuntes CR2-93-134 §3.6 problema 1 se reproducen con SU PROPIO momento, +5,5 t·m,
    sin ningún cambio de signo ad hoc."""
    return -M_e050_kNm


class FreeBody(BaseModel):
    """Cuerpo libre con dos incógnitas: una fuerza de posición conocida y otra más.

    No se resuelve con una fórmula: se arman las dos ecuaciones de equilibrio y se
    resuelve el sistema lineal 2×2 que forman."""

    description: str
    known_forces: list[Force] = Field(default_factory=list)
    applied_moments: list[AppliedMoment] = Field(default_factory=list)

    unknown_1_label: str
    unknown_1_s_m: float
    unknown_2_label: str
    unknown_2_s_m: float

    moment_reference_s_m: float = Field(
        ..., description="Punto respecto del cual se toman momentos"
    )

    def solve(self) -> tuple[float, float]:
        """Devuelve (F1_up, F2_up) resolviendo ΣF_v = 0 y ΣM = 0.

        Sistema:
            [ 1                    1                  ] [F1]   [ −ΣF_conocidas      ]
            [ (s1 − sc)            (s2 − sc)          ] [F2] = [ −ΣM_conocidos      ]
        """
        sc = self.moment_reference_s_m
        suma_F = sum(f.F_up_kN for f in self.known_forces)
        suma_M = sum(f.moment_about_kNm(sc) for f in self.known_forces)
        suma_M += sum(m.M_kNm for m in self.applied_moments)

        a11, a12 = 1.0, 1.0
        a21 = self.unknown_1_s_m - sc
        a22 = self.unknown_2_s_m - sc
        b1, b2 = -suma_F, -suma_M

        det = a11 * a22 - a12 * a21
        if abs(det) < 1e-12:
            raise ValueError(
                f"El cuerpo libre «{self.description}» es indeterminado con el punto de "
                f"momentos elegido: las dos incógnitas tienen el mismo brazo respecto de "
                f"s = {sc:.4f} m. Elija otro punto de momentos."
            )
        F1 = (b1 * a22 - a12 * b2) / det
        F2 = (a11 * b2 - b1 * a21) / det
        return F1, F2

    def residuals(self, F1_up_kN: float, F2_up_kN: float) -> tuple[float, float]:
        """(ΣF_v, ΣM) con la solución sustituida. Deben ser cero.

        Es una comprobación INDEPENDIENTE del código que resolvió el sistema: se
        vuelven a sumar todas las fuerzas, incluidas las incógnitas ya resueltas."""
        sc = self.moment_reference_s_m
        todas = list(self.known_forces) + [
            Force(label=self.unknown_1_label, s_m=self.unknown_1_s_m, F_up_kN=F1_up_kN),
            Force(label=self.unknown_2_label, s_m=self.unknown_2_s_m, F_up_kN=F2_up_kN),
        ]
        sf = sum(f.F_up_kN for f in todas)
        sm = sum(f.moment_about_kNm(sc) for f in todas) + sum(
            m.M_kNm for m in self.applied_moments
        )
        return sf, sm


# Fase 9a — pendiente declarado: el relleno SOBRE la viga en el vano libre.
FILL_OVER_SPAN_PENDING = (
    "PENDIENTE (Fase 9a) — el relleno que queda SOBRE la viga en el vano libre, entre su "
    "cara superior y el nivel de terreno, NO está incluido en el cálculo. No es peso "
    "propio de la viga: es una carga permanente de suelo que, con la viga sin apoyo en el "
    "terreno, cargaría sobre ella y llegaría a las dos zapatas. Omitirla subestima las "
    "cargas de ambas; por eso, cuando la geometría declarada deja relleno sobre la viga, "
    "la entrada queda NO VERIFICADA."
)


class BeamSelfWeightBreakdown(BaseModel):
    """Peso propio de la viga de conexión por GEOMETRÍA FÍSICA — Fase 9a.

    POR QUÉ NO SE USA `s_corte`
    ===========================
    Hasta 9a el peso se tomaba sobre [L1, s_corte]: del borde de la zapata de lindero al
    eje de la columna interior. `s_corte` es el punto de la rótula y la referencia de
    momentos del modelo, NO un límite geométrico de la viga. Ese tramo metía media zapata
    interior —cuyo concreto y relleno ya cuenta `compute_self_weight`— y la zona de la
    columna, y dejaba fuera el tramo de viga sobre la zapata de lindero.

    LA VIGA EN PLANTA
    =================
    Va de la cara interior de la columna exterior (c_e) a la cara de la columna interior
    (c_i). Las huellas la parten en tres tramos, y cada uno pertenece a un cuerpo:

        [c_e, L1]    sobre la huella exterior   ΔW_e   cuerpo: zapata exterior
        [L1,  f_i]   vano libre                 W_V    cuerpo: viga
        [f_i, c_i]   sobre la huella interior   ΔW_i   cuerpo: zapata interior

    LA VIGA EN SECCIÓN — hipótesis de cota vertical declarada
    =========================================================
    z_b es la altura del fondo de la viga sobre la base común de cimentación; z_t = z_b +
    h_v la de su cara superior. Sobre una huella de espesor h_f, el suelo de desplante Df
    define tres franjas ya contabilizadas por `compute_self_weight`:

        [0, h_f]              concreto de la zapata        γc_zapata
        [h_f, max(Df, h_f)]   relleno sobre la zapata      γs
        encima                nada                         0

    La viga solo AGREGA la diferencia de peso unitario en cada franja que ocupa:

        Δw = b·[(γc_viga − γc_zapata)·t_f + (γc_viga − γs)·t_r + γc_viga·t_a]

    En el vano libre no hay nada contabilizado bajo ni sobre la viga: W_V = b·h_v·γc·(f_i −
    L1), independiente de la cota. El relleno sobre la viga en el vano NO se incluye
    (`FILL_OVER_SPAN_PENDING`).

    VALIDEZ
    =======
    El modelo supone que la viga toca las dos zapatas: z_b ≤ h_f. Si su fondo queda por
    encima de la cara superior de una zapata, ese tramo no descansa sobre ella; el peso
    se sigue contabilizando igual, pero su camino de carga no es el modelado y la entrada
    de traza queda NO VERIFICADA (`exterior_contact`, `interior_contact`)."""

    soffit_above_base_m: float = Field(..., description="z_b: fondo de la viga sobre la base")
    top_above_base_m: float = Field(..., description="z_t = z_b + h_v")

    s_exterior_face_m: float = Field(..., description="c_e: cara interior de la columna exterior")
    s_span_start_m: float = Field(..., description="L1: fin de la huella exterior")
    s_span_end_m: float = Field(..., description="f_i: inicio de la huella interior")
    s_interior_face_m: float = Field(..., description="c_i: cara de la columna interior")

    exterior_increment_kN_per_m: float
    interior_increment_kN_per_m: float
    span_kN_per_m: float

    exterior_increment_kN: float = Field(..., description="ΔW_e, sobre [c_e, L1]")
    s_exterior_increment_m: float
    span_kN: float = Field(..., description="W_V, vano libre [L1, f_i]")
    s_span_m: float = Field(..., description="x_V")
    interior_increment_kN: float = Field(..., description="ΔW_i, sobre [f_i, c_i]")
    s_interior_increment_m: float

    exterior_contact: bool
    interior_contact: bool
    fill_over_span: bool = Field(
        ..., description="¿Queda relleno sobre la viga en el vano? NO incluido (pendiente)"
    )

    load_factor: float | None = Field(
        default=None,
        description=(
            "Factor aplicado a los tres pesos (Fase 10B): el de los casos CM de la combinación "
            "en el modo por casos. None en el modo directo, donde el peso va sin factor."
        ),
    )

    @property
    def total_kN(self) -> float:
        return self.exterior_increment_kN + self.span_kN + self.interior_increment_kN

    def scaled(self, factor: float) -> "BeamSelfWeightBreakdown":
        """Mismo desglose geométrico con los pesos multiplicados por `factor`."""
        return self.model_copy(update=dict(
            exterior_increment_kN_per_m=factor * self.exterior_increment_kN_per_m,
            interior_increment_kN_per_m=factor * self.interior_increment_kN_per_m,
            span_kN_per_m=factor * self.span_kN_per_m,
            exterior_increment_kN=factor * self.exterior_increment_kN,
            span_kN=factor * self.span_kN,
            interior_increment_kN=factor * self.interior_increment_kN,
            load_factor=factor,
        ))


def factored_beam_weight(
    bw: "BeamSelfWeightBreakdown | None",
    combo_ext: LoadCombination,
    combo_int: LoadCombination,
    direct_dead_load_factor: float | None = None,
) -> "BeamSelfWeightBreakdown | None":
    """Peso de la viga para UNA combinación (Fase 10B, CC-3; TBD-C13 A′).

    Modo por casos: recibe el factor de los casos CM de la combinación. Las dos columnas
    salen de la misma definición, de modo que sus factores CM deben coincidir.

    Modo directo (sin composición): el motor no puede inferir el factor. Si el proyectista
    lo DECLARA (`direct_dead_load_factor`), se aplica a las combinaciones FACTORIZADAS; las
    de servicio llevan el peso real, factor 1,0. Si no lo declara, el peso va sin factor y
    `load_factor` queda None, que es lo que hace que TBD-C13 degrade la entrada a NO
    VERIFICADO. Nunca se supone un factor."""
    if bw is None:
        return bw
    if combo_ext.composition is None:
        if direct_dead_load_factor is None:
            return bw
        return bw.scaled(
            direct_dead_load_factor
            if combo_ext.type is LoadCombinationType.FACTORIZADA
            else 1.0
        )
    if combo_int.composition is None:
        raise ValueError(
            f'La combinación "{combo_ext.name}" tiene composición en la columna exterior y no '
            f"en la interior: las dos columnas deben usar el mismo modo de cargas."
        )
    f_ext = combo_ext.composition.dead_load_factor
    f_int = combo_int.composition.dead_load_factor
    if f_ext != f_int:
        raise ValueError(
            f'La combinación "{combo_ext.name}" aplica a CM el factor {f_ext} en la columna '
            f"exterior y {f_int} en la interior: la definición debe ser la misma."
        )
    return bw.scaled(f_ext if f_ext is not None else 0.0)


FOOTING_WEIGHT_CM_NOTE = (
    "Peso propio de las zapatas en el reparto de CUERPO_RIGIDO (decisión D10C-1): concreto y "
    "relleno calculados por el motor se clasifican como CM (E.020 art. 2; el relleno como carga "
    "muerta, opción A). En la combinación factorizada «{combo}» de modo por casos se aplica "
    "f_CM = {f:g} al peso total, tanto en las cargas del cuerpo rígido como en la resta R − W de "
    "la carga corregida: W_ext = {we:.2f} kN y W_int = {wi:.2f} kN (sin factor {we0:.2f} y "
    "{wi0:.2f} kN). Las verificaciones factorizadas de las zapatas usan la carga neta y no "
    "vuelven a sumar W, de modo que no hay doble factorización."
)


def footing_weight_factor(combo_ext: LoadCombination, combo_int: LoadCombination) -> float:
    """Factor del peso propio de las zapatas en el reparto rígido (D10C-1).

    - Modo directo (sin composición): 1,0. No se infiere nada.
    - Combinación de SERVICIO: 1,0. El motor de zapata suma el peso propio sin factor a la
      presión de servicio; el reparto debe usar el mismo peso para que P_corr = R − W sea neta.
    - Combinación FACTORIZADA por casos: f_CM de la combinación (0 si no contiene CM, igual
      que el peso de la viga en 10B). Las dos columnas deben declarar el mismo factor."""
    ce, ci = combo_ext.composition, combo_int.composition
    if ce is None or combo_ext.type is not LoadCombinationType.FACTORIZADA:
        return 1.0
    if ci is None:
        raise ValueError(
            f'La combinación "{combo_ext.name}" tiene composición en la columna exterior y no '
            f"en la interior: las dos columnas deben usar el mismo modo de cargas."
        )
    if ce.dead_load_factor != ci.dead_load_factor:
        raise ValueError(
            f'La combinación "{combo_ext.name}" aplica a CM el factor {ce.dead_load_factor} en la '
            f"columna exterior y {ci.dead_load_factor} en la interior: la definición debe ser la misma."
        )
    return ce.dead_load_factor if ce.dead_load_factor is not None else 0.0


def _along_axis(column, axis: str) -> float:
    return column.bx_m if axis == "X" else column.by_m


def _band(z0: float, z1: float, lo: float, hi: float) -> float:
    return max(0.0, min(z1, hi) - max(z0, lo))


class BeamAxisGeometry(BaseModel):
    """Dónde está la viga de conexión, medida sobre el eje longitudinal — Fase 9b.

    Es la MISMA geometría física que usa el peso propio de 9a, extraída para que la
    compartan el peso, el vano libre publicado y las métricas:

        [c_e, L1]    viga sobre la huella exterior
        [L1,  f_i]   vano libre
        [f_i, c_i]   viga sobre la huella interior

    `s_corte` no aparece: es la rótula y la referencia de momentos del modelo, no un límite
    de la viga. Por eso esta geometría no depende del modelo de análisis ni del reparto
    del par.

    `soffit_above_base_m` es la z_b DECLARADA (solo existe con peso EXPLICITO); `None`
    cuando no se declaró. Quien la necesite sin declaración debe fijar y trazar su propia
    hipótesis: aquí no se inventa."""

    s_exterior_face_m: float = Field(..., description="c_e: cara interior de la columna exterior")
    s_span_start_m: float = Field(..., description="L1: fin de la huella exterior")
    s_span_end_m: float = Field(..., description="f_i: inicio de la huella interior")
    s_interior_face_m: float = Field(..., description="c_i: cara de la columna interior")
    soffit_above_base_m: float | None = Field(
        default=None, description="z_b declarada; None si no se declaró"
    )

    @property
    def clear_span_m(self) -> float:
        """Vano libre físico f_i − L1."""
        return max(self.s_span_end_m - self.s_span_start_m, 0.0)

    @property
    def over_exterior_m(self) -> float:
        """Longitud de viga sobre la huella exterior, L1 − c_e."""
        return max(self.s_span_start_m - self.s_exterior_face_m, 0.0)

    @property
    def over_interior_m(self) -> float:
        """Longitud de viga sobre la huella interior, c_i − f_i."""
        return max(self.s_interior_face_m - self.s_span_end_m, 0.0)

    @property
    def between_column_faces_m(self) -> float:
        """Longitud total de la viga entre caras de columna, c_i − c_e."""
        return max(self.s_interior_face_m - self.s_exterior_face_m, 0.0)


def beam_axis_geometry(layout: ConnectedFootingLayout, footprints: Footprints) -> BeamAxisGeometry:
    """c_e, L1, f_i y c_i de la viga, y su z_b declarada si existe."""
    eje = layout.longitudinal_axis
    a = layout.exterior.anchor.axis_distance_to_column_center_m(layout.exterior.column)
    s_cut = a + layout.axis_distance_m
    return BeamAxisGeometry(
        s_exterior_face_m=a + _along_axis(layout.exterior.column, eje) / 2.0,
        s_span_start_m=footprints.exterior.end_m,
        s_span_end_m=footprints.interior.start_m,
        s_interior_face_m=s_cut - _along_axis(layout.interior.column, eje) / 2.0,
        soffit_above_base_m=layout.beam.soffit_above_base_m,
    )


def _increment_per_m(
    *, b: float, z_b: float, z_t: float, h_f: float, Df: float,
    gamma_beam: float, gamma_footing: float, gamma_soil: float,
) -> float:
    techo_relleno = max(Df, h_f)
    t_f = _band(z_b, z_t, 0.0, h_f)
    t_r = _band(z_b, z_t, h_f, techo_relleno)
    t_a = max(0.0, z_t - max(z_b, techo_relleno))
    return b * (
        (gamma_beam - gamma_footing) * t_f + (gamma_beam - gamma_soil) * t_r + gamma_beam * t_a
    )


def beam_self_weight_breakdown(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    soil,
    footing_concrete_unit_weight_kNm3: float,
) -> BeamSelfWeightBreakdown | None:
    """Desglose físico del peso de la viga. `None` si no se modela (modo ≠ EXPLICITO)."""
    beam = layout.beam
    if not beam.models_self_weight:
        return None
    if soil is None:
        raise ValueError(
            "El peso propio EXPLICITO de la viga necesita el perfil de suelo: el tramo sobre "
            "cada zapata agrega solo lo que no cuentan ya su concreto y su relleno, y eso "
            "depende de Df y del peso unitario del relleno."
        )
    fe, fi = footprints.exterior, footprints.interior
    ax = beam_axis_geometry(layout, footprints)
    c_e, L1, f_i, c_i = ax.s_exterior_face_m, ax.s_span_start_m, ax.s_span_end_m, ax.s_interior_face_m

    z_b = beam.soffit_above_base_m
    z_t = z_b + beam.h_m
    g_b = beam.concrete_unit_weight_kNm3
    comunes = dict(
        b=beam.b_m, z_b=z_b, z_t=z_t, Df=soil.Df_m, gamma_beam=g_b,
        gamma_footing=footing_concrete_unit_weight_kNm3, gamma_soil=soil.gamma_kNm3,
    )
    dw_e = _increment_per_m(h_f=fe.h_m, **comunes)
    dw_i = _increment_per_m(h_f=fi.h_m, **comunes)
    w_v = beam.b_m * beam.h_m * g_b

    largo_e = max(L1 - c_e, 0.0)
    largo_v = max(f_i - L1, 0.0)
    largo_i = max(c_i - f_i, 0.0)
    tol = 1e-9
    return BeamSelfWeightBreakdown(
        soffit_above_base_m=z_b, top_above_base_m=z_t,
        s_exterior_face_m=c_e, s_span_start_m=L1, s_span_end_m=f_i, s_interior_face_m=c_i,
        exterior_increment_kN_per_m=dw_e, interior_increment_kN_per_m=dw_i, span_kN_per_m=w_v,
        exterior_increment_kN=dw_e * largo_e, s_exterior_increment_m=(c_e + L1) / 2.0,
        span_kN=w_v * largo_v, s_span_m=(L1 + f_i) / 2.0,
        interior_increment_kN=dw_i * largo_i, s_interior_increment_m=(f_i + c_i) / 2.0,
        exterior_contact=z_b <= fe.h_m + tol,
        interior_contact=z_b <= fi.h_m + tol,
        fill_over_span=z_t < soil.Df_m - tol,
    )


def beam_self_weight_note(layout: ConnectedFootingLayout, bw: BeamSelfWeightBreakdown | None) -> str:
    """Texto de TBD-C5 con el desglose, para hipótesis y traza."""
    W = bw.total_kN if bw is not None else 0.0
    texto = BEAM_SELF_WEIGHT_NOTES[layout.beam.self_weight_mode].format(W=W)
    if bw is None:
        return texto
    return (
        f"{texto} Cota declarada z_b = {bw.soffit_above_base_m:.3f} m (z_t = "
        f"{bw.top_above_base_m:.3f} m sobre la base). ΔW_e = {bw.exterior_increment_kN:.3f} kN "
        f"sobre [{bw.s_exterior_face_m:.3f}, {bw.s_span_start_m:.3f}] m; W_V = "
        f"{bw.span_kN:.3f} kN en el vano libre [{bw.s_span_start_m:.3f}, "
        f"{bw.s_span_end_m:.3f}] m; ΔW_i = {bw.interior_increment_kN:.3f} kN sobre "
        f"[{bw.s_span_end_m:.3f}, {bw.s_interior_face_m:.3f}] m. Sobre cada zapata la viga "
        f"solo agrega lo que no cuentan ya su concreto y su relleno; la zona de las columnas "
        f"no es viga."
    )


class CoupleDistribution(BaseModel):
    """Reparto resuelto para UNA combinación de carga."""

    combo_name: str
    combo_type: str
    analysis_model: AnalysisModel
    couple_transfer_mode: CoupleTransferMode = Field(
        ...,
        description=(
            "TBD-C11. Decide si la rama cercana del par la toma la zapata de lindero o "
            "el pórtico. Cambia la reacción de esa zapata y si la carga se conserva."
        ),
    )
    M_couple_kNm: float = Field(
        default=0.0,
        description=(
            "Par que la viga arranca de la zapata de lindero [kN·m]: M_col − P_col·e1. "
            "El peso propio de la ZAPATA se cancela en esta expresión. Con PAR_PURO y peso "
            "de viga EXPLICITO intervienen además las cargas de nudo de la viga (Fase 9c)."
        ),
    )

    # --- Geometría del cuerpo libre, en la coordenada s ---
    a_m: float = Field(..., description="Del lindero al eje de la columna exterior")
    L1_m: float = Field(..., description="Longitud de la zapata exterior sobre el eje")
    e1_m: float = Field(..., description="Excentricidad geométrica: L1/2 − a")
    S_m: float = Field(..., description="Distancia entre ejes de columnas")
    s_centroid_ext_m: float
    s_cut_m: float = Field(..., description="Sección de corte, en el eje de la columna interior")

    # --- Acciones de entrada ---
    P_ext_kN: float
    M_ext_kNm: float
    P_int_kN: float
    M_int_kNm: float
    beam_self_weight_kN: float = Field(
        default=0.0,
        description="Peso de la viga en el modelo: ΔW_e + W_V + ΔW_i (Fase 9a)",
    )
    beam_self_weight_breakdown: BeamSelfWeightBreakdown | None = Field(
        default=None, description="Desglose físico del peso de la viga. None si no se modela."
    )
    beam_node_reaction_kN: float | None = Field(
        default=None,
        description=(
            "N_a — reacción gravitatoria de la viga en el nudo de la columna exterior, que "
            "entra a la zapata de lindero como carga de nudo. Solo con PAR_PURO_EN_ZAPATA y "
            "peso EXPLICITO (Fase 9c, B*)."
        ),
    )

    # --- Incógnitas resueltas ---
    R_ext_kN: float = Field(
        ..., description="Resultante NETA del suelo bajo la zapata exterior [kN], hacia arriba"
    )
    V_cut_kN: float = Field(
        ..., description="Fuerza vertical en la sección de corte, positiva hacia arriba"
    )
    M_cut_kNm: float = Field(
        default=0.0,
        description=(
            "Momento interno en la sección de corte [kN·m]. **Es el campo que distingue a "
            "los dos modelos de análisis**: ARTICULADO tiene una rótula ahí y siempre "
            "devuelve 0; CUERPO_RIGIDO transmitirá momento y devolverá un valor no nulo. "
            "Forma parte del contrato para que `connecting_beam_statics` sirva a ambos sin "
            "ramificar."
        ),
    )
    delta_P_kN: float = Field(
        ...,
        description=(
            "Transferencia del sistema [kN], igual a −V_cut por acción y reacción. "
            "EXCEPCIÓN: con PAR_PURO_EN_ZAPATA es la rama del par que recoge el pórtico, "
            "−C_Z/S, y con peso de viga EXPLICITO deja de igualar −V_cut (Fase 9c). "
            "POSITIVA: la zapata EXTERIOR recibe más reacción del suelo que la carga de su "
            "propia columna, y la INTERIOR queda aliviada en la misma cantidad —actúa como "
            "contrapeso, sujetando la viga—. NEGATIVA: al revés, que es lo que ocurre "
            "cuando el sismo invierte el par."
        ),
    )

    # --- Comprobación de cierre ---
    residual_force_kN: float
    residual_moment_kNm: float

    # --- Campos propios del modelo de CUERPO RÍGIDO (nulos en el articulado) ---
    bearing_area_m2: float = Field(default=0.0)
    bearing_centroid_m: float = Field(default=0.0)
    bearing_inertia_m4: float = Field(default=0.0)
    sigma_min_kPa: float | None = Field(
        default=None,
        description=(
            "Presión mínima sobre el área de apoyo. Si resultara negativa habría "
            "DESPEGUE, y E.060 §15.2 prohíbe considerar tracciones: el campo lineal "
            "deja de valer y el caso exige contacto parcial, fuera de alcance."
        ),
    )
    sigma_max_kPa: float | None = Field(default=None)
    uplift: bool = Field(
        default=False, description="True si alguna fibra del apoyo resulta traccionada"
    )
    W_ext_kN: float = Field(default=0.0, description="Peso propio de la zapata exterior")
    W_int_kN: float = Field(default=0.0, description="Peso propio de la zapata interior")

    # --- Acciones corregidas que recibirán los motores existentes ---
    P_ext_corrected_kN: float
    M_ext_corrected_kNm: float = Field(
        ...,
        description=(
            "Par que la viga transmite a la zapata exterior [kN·m]. Es el que centra la "
            "resultante y produce la presión uniforme del modelo articulado."
        ),
    )
    P_int_corrected_kN: float
    M_int_corrected_kNm: float

    # Fase 10C: de qué casos están hechas las cargas corregidas. Solo en el modo por casos.
    exterior_corrected_composition: LoadComposition | None = Field(
        default=None, description="Composición de la carga corregida de la zapata exterior"
    )
    interior_corrected_composition: LoadComposition | None = Field(
        default=None, description="Composición de la carga corregida de la zapata interior"
    )

    equation_substituted: str
    hypotheses: list[str] = Field(default_factory=list)

    @property
    def expected_residual_kN(self) -> float:
        """Cuánta carga debe faltar, según el modo declarado.

        EQUILIBRIO_EN_CIMENTACION: cero. La cimentación cierra sola.

        PAR_PURO_EN_ZAPATA: exactamente la transferencia. La rama cercana del par se
        supone recogida por la columna y el pórtico, de modo que no llega al suelo. No
        es un error: es la hipótesis declarada. Pero tiene que faltar ESA cantidad y no
        otra, y por eso el invariante sigue siendo fuerte en los dos modos. El peso de la
        viga no falta nunca: llega a las zapatas por las reacciones de la viga (9c, B*)."""
        if (
            self.analysis_model is AnalysisModel.ARTICULADO
            and self.couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA
        ):
            return -self.delta_P_kN
        # En CUERPO_RIGIDO el conjunto se equilibra globalmente por construcción y la
        # pregunta de TBD-C11 —dónde va la rama cercana del par— ni siquiera se
        # plantea: no hay dos cuerpos, hay uno. La carga se conserva siempre.
        return 0.0

    @property
    def load_conservation_residual_kN(self) -> float:
        """Cuánta carga aparece o desaparece de más respecto de lo que el modo admite.

        ΔP es una TRANSFERENCIA: lo que una zapata deja de recibir lo recibe la otra. Lo
        único que puede aumentar el total es el peso propio de la viga, y solo cuando se
        declara EXPLICITO.

            P_ext_corr + P_int_corr = P_ext + P_int + W_viga

        Se comprueba aquí, sobre el objeto del contrato, y no dentro del código que
        resuelve el reparto. La razón es 4C: cuando exista una segunda estrategia, este
        invariante seguirá vigilándola sin que haya que acordarse de repetir la
        comprobación. Un error de signo en ΔP —que ya ocurrió una vez, sumando la
        transferencia a las DOS zapatas— se delata aquí de inmediato."""
        return (
            self.P_ext_corrected_kN
            + self.P_int_corrected_kN
            - self.P_ext_kN
            - self.P_int_kN
            - self.beam_self_weight_kN
            - self.expected_residual_kN
        )

    @property
    def conserves_load(self) -> bool:
        escala = max(abs(self.P_ext_kN) + abs(self.P_int_kN), 1.0)
        return abs(self.load_conservation_residual_kN) <= EQUILIBRIUM_TOL * escala

    @property
    def closes(self) -> bool:
        """Los TRES invariantes del contrato: ΣF_v = 0, ΣM = 0 y conservación de carga.

        Cualquier estrategia de análisis —articulada, de cuerpo rígido o la que venga—
        debe satisfacerlos. No son propiedades del método de resolución: son propiedades
        de la física que el método debe respetar."""
        escala = max(abs(self.P_ext_kN) + abs(self.P_int_kN), 1.0)
        return (
            abs(self.residual_force_kN) <= EQUILIBRIUM_TOL * escala
            and abs(self.residual_moment_kNm) <= EQUILIBRIUM_TOL * escala * max(self.S_m, 1.0)
            and self.conserves_load
        )


def build_free_body(
    layout: ConnectedFootingLayout,
    L1_m: float,
    P_ext_kN: float,
    M_ext_kNm: float,
    beam_weight: BeamSelfWeightBreakdown | None = None,
) -> FreeBody:
    """Arma el cuerpo libre {zapata exterior + viga}, cortado en el eje interior.

    Las dos incógnitas son la resultante neta del suelo bajo la zapata exterior y la
    fuerza vertical en la sección de corte. La condición que cierra el sistema en el
    modelo ARTICULADO es que en esa sección el momento es nulo: por eso se toman
    momentos justamente allí, y el término de la rótula desaparece.

    PESO DE LA VIGA (Fase 9a). Entran ΔW_e —tramo de viga sobre la huella exterior— y
    W_V —vano libre—, cada uno en su centroide. ΔW_i NO: descansa sobre la zapata
    interior y pertenece a ese cuerpo, aunque quede a la izquierda de la rótula."""
    if layout.beam.models_self_weight and beam_weight is None:
        raise ValueError(
            "Con peso propio de viga EXPLICITO el cuerpo libre necesita el desglose físico "
            "del peso (`beam_self_weight_breakdown`): depende de las huellas y del suelo."
        )
    a = layout.exterior.anchor.axis_distance_to_column_center_m(layout.exterior.column)
    s_cut = a + layout.axis_distance_m
    s_centroide = L1_m / 2.0

    conocidas = [
        Force(label=f"Carga de la columna {layout.exterior.label}", s_m=a, F_up_kN=-P_ext_kN),
    ]
    if beam_weight is not None:
        if beam_weight.exterior_increment_kN > 0.0:
            conocidas.append(Force(
                label="Peso de la viga sobre la huella exterior (ΔW_e)",
                s_m=beam_weight.s_exterior_increment_m,
                F_up_kN=-beam_weight.exterior_increment_kN,
            ))
        if beam_weight.span_kN > 0.0:
            conocidas.append(Force(
                label="Peso de la viga en el vano libre (W_V)",
                s_m=beam_weight.s_span_m, F_up_kN=-beam_weight.span_kN,
            ))

    momentos = []
    if M_ext_kNm != 0.0:
        momentos.append(
            AppliedMoment(
                label=f"Momento de la columna {layout.exterior.label}",
                M_kNm=applied_moment_in_free_body(M_ext_kNm),
            )
        )

    return FreeBody(
        description=f"{layout.exterior.label} + viga, cortado en el eje de {layout.interior.label}",
        known_forces=conocidas,
        applied_moments=momentos,
        unknown_1_label="Resultante neta del suelo bajo la zapata exterior",
        unknown_1_s_m=s_centroide,
        unknown_2_label="Fuerza vertical en la sección de corte",
        unknown_2_s_m=s_cut,
        # Momentos EN el corte: en el modelo articulado allí hay una rótula y el
        # momento interno es nulo, de modo que no aparece en la ecuación.
        moment_reference_s_m=s_cut,
    )


def _distribute_articulated(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    combo_ext: LoadCombination,
    combo_int: LoadCombination,
    soil,
    concrete_unit_weight_kNm3: float,
) -> CoupleDistribution:
    """ESTRATEGIA ARTICULADO.

    Hipótesis que la definen, y que ninguna norma impone —las elige el proyectista al
    declarar el modelo—:

      H1  La unión viga-zapata interior es una RÓTULA: no transmite momento. Es lo que
          cierra el sistema y hace que `M_cut_kNm` valga cero.
      H2  La viga es lo bastante rígida para impedir el giro de la zapata de lindero,
          de modo que su presión de contacto resulta UNIFORME. Es TBD-C1, sin criterio
          de verificación disponible.
      H3  El peso propio de cada zapata actúa en su centroide —espesor uniforme—, lo
          que permite plantear el reparto sobre cargas netas de peso propio.

    De las dos huellas solo usa la EXTERIOR: su cuerpo libre no mira a la interior.
    Recibe las dos porque la firma es común a todas las estrategias —el modelo de
    cuerpo rígido sí necesita ambas— y así el orquestador no tiene que saber cuál
    corrió. `soil` y el peso unitario del concreto tampoco le hacen falta: el peso
    propio de las zapatas se agrupa y desaparece de sus ecuaciones."""
    L1_m = footprints.exterior.length_m
    if combo_ext.name != combo_int.name:
        raise ValueError(
            f"El reparto se resuelve combinación a combinación: «{combo_ext.name}» y "
            f"«{combo_int.name}» no son la misma."
        )

    eje = layout.longitudinal_axis
    M_ext = combo_ext.Mx_kNm if eje == "X" else combo_ext.My_kNm
    M_int = combo_int.Mx_kNm if eje == "X" else combo_int.My_kNm

    a = layout.exterior.anchor.axis_distance_to_column_center_m(layout.exterior.column)
    e1 = L1_m / 2.0 - a
    S = layout.axis_distance_m
    s_cut = a + S
    bw = beam_self_weight_breakdown(layout, footprints, soil, concrete_unit_weight_kNm3)
    bw = factored_beam_weight(bw, combo_ext, combo_int, layout.beam.self_weight_dead_load_factor)
    W_viga = bw.total_kN if bw is not None else 0.0
    N_a: float | None = None

    if layout.couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA:
        # PAR PURO. La condición que define el modo es que la viga no aplique fuerza
        # vertical neta a la zapata de lindero: su reacción vale exactamente la carga
        # de su columna. Con eso, el cuerpo libre {zapata exterior} queda con UNA sola
        # incógnita —el par que la viga le aplica— y una sola ecuación, ΣM = 0.
        #
        # EL PAR SE DERIVA, NO SE ESCRIBE. La versión anterior copiaba la fórmula
        # cerrada del libro, `M_col − P·e1`, y con ella importaba SU convención de
        # signos: el mismo Mx del usuario movía la transferencia en sentidos OPUESTOS
        # según el modo. Aquí el momento se suma con la misma maquinaria y la misma
        # convención que usa el modo de equilibrio, de modo que el signo sale solo.
        #
        # El peso propio de la ZAPATA no aparece: actúa en el centroide, igual que la
        # reacción del suelo, y su momento respecto de ese punto es nulo.
        #
        # PESO DE LA VIGA — Fase 9c, formulación B*. Dos cuerpos unidos en el nudo `a`:
        #
        #   Z (zapata)  −P_ext y −N_a en a, −ΔW_e en x_e, R_ext uniforme, par C_Z
        #   V (viga)    +N_a y +F_p en a, −W_V en x_V, +V_I en s_corte, par −C_Z
        #
        # El equilibrio deja UNA indeterminación: cómo se reparte en el nudo la fuerza
        # de la viga entre la zapata (N_a) y el pórtico (F_p). El modo la fija así: al
        # pórtico va SOLO la rama del par, F_p = −C_Z/S; la gravedad de la viga llega por
        # sus reacciones, N_a = W_V·(s_corte − x_V)/S a la zapata y el resto a la rótula.
        # El peso del vano NO se suma globalmente a P_ext.
        R_ext = combo_ext.P_kN
        if bw is not None:
            N_a = bw.span_kN * (s_cut - bw.s_span_m) / S
            R_ext = combo_ext.P_kN + N_a + bw.exterior_increment_kN
        s_centroide = L1_m / 2.0
        fuerzas_zapata = [
            Force(
                label=f"Carga de la columna {layout.exterior.label}",
                s_m=a, F_up_kN=-combo_ext.P_kN,
            ),
            Force(
                label="Reacción neta del suelo, uniforme, en el centroide",
                s_m=s_centroide, F_up_kN=R_ext,
            ),
        ]
        if bw is not None:
            fuerzas_zapata += [
                Force(label="Reacción gravitatoria de la viga en el nudo (N_a)",
                      s_m=a, F_up_kN=-N_a),
                Force(label="Peso de la viga sobre la huella exterior (ΔW_e)",
                      s_m=bw.s_exterior_increment_m, F_up_kN=-bw.exterior_increment_kN),
            ]
        suma_M = sum(
            f.moment_about_kNm(s_centroide) for f in fuerzas_zapata
        ) + applied_moment_in_free_body(M_ext)
        M_par = -suma_M
        delta_P = -M_par / S
        if bw is None:
            V_cut = -delta_P
        else:
            # (V-F): N_a + F_p + V_I = W_V, con F_p = ΔP.
            V_cut = bw.span_kN - N_a - delta_P

        # RESIDUOS CALCULADOS, no afirmados. Con el par incluido, el cuerpo libre de
        # la zapata cierra exactamente en fuerzas y en momentos; si alguna vez dejara
        # de hacerlo, estos números lo dirían. Ponerlos a cero a mano dejaba `closes`
        # sin verificar nada en este modo.
        res_F = sum(f.F_up_kN for f in fuerzas_zapata)
        res_M = suma_M + M_par
        if bw is not None:
            # Y el de la VIGA, que con peso deja de ser trivial. Momentos sobre `a`.
            res_F_v = N_a + delta_P + V_cut - bw.span_kN
            res_M_v = S * V_cut - bw.span_kN * (bw.s_span_m - a) - M_par
            res_F = max((res_F, res_F_v), key=abs)
            res_M = max((res_M, res_M_v), key=abs)
        cuerpo = None
    else:
        # La cimentación se equilibra sola: ΣFv = 0 y ΣM = 0 sobre el cuerpo libre.
        cuerpo = build_free_body(layout, L1_m, combo_ext.P_kN, M_ext, bw)
        R_ext, V_cut = cuerpo.solve()
        res_F, res_M = cuerpo.residuals(R_ext, V_cut)
        # Acción y reacción: el cuerpo libre recibe V_cut de la zapata interior, de
        # modo que la zapata interior recibe −V_cut del sistema.
        delta_P = -V_cut
        # El par equivalente, para poder compararlo entre modos. Se obtiene del mismo
        # modo que arriba: momentos sobre el centroide de la zapata de lindero.
        M_par = -delta_P * S

    # --- Acciones CORREGIDAS que reciben los motores existentes ---
    #
    # Exterior. La carga es la resultante neta resuelta. El momento NO es cero, y
    # aquí está el punto fino del modelo: la viga transmite a la zapata de lindero un
    # PAR, y ese par es una acción real sobre ella. Es justamente el par que centra
    # la resultante y produce la presión uniforme que el modelo articulado supone.
    #
    # El motor de zapata aislada compone la excentricidad como
    #     ex = (M + P_columna · offset) / (P_columna + W)          [Fase 1B]
    # de modo que la columna descentrada aporta un momento P·offset POR GEOMETRÍA.
    # Entregar momento nulo NO daría presión uniforme: daría la de una zapata de
    # lindero sin viga, que es un problema distinto. El par que hay que entregar es
    # el que anula esa excentricidad geométrica:
    #
    #     M_corr = − P_corr · offset,   con offset = signo_borde · e1
    #
    # Con él, ex = 0 y la presión resulta uniforme SIN necesidad de un modelo de
    # contacto nuevo y sin tocar una línea del motor de zapata.
    signo_borde = layout.exterior.anchor.offset_sign()
    offset_ext = signo_borde * e1
    P_ext_corr = R_ext
    M_ext_corr = -R_ext * offset_ext
    # Interior. Es un CONTRAPESO: la viga tira de ella hacia arriba y su reacción del
    # suelo DISMINUYE en la misma cantidad en que aumenta la de la exterior. Sumarle
    # ΔP en vez de restarlo crearía carga de la nada —la suma de las dos cargas
    # corregidas dejaría de igualar la suma de las originales— y dejaría la zapata
    # interior sobredimensionada y la premisa de contrapeso sin verificar.
    #
    # Su momento propio se conserva: la rótula no lo transmite al sistema, de modo que
    # la zapata interior lo recibe entero y se verifica como una aislada con momento.
    #
    # Se escribe con V_cut —la fuerza que la viga entrega en la rótula— y no con ΔP: son
    # la misma cosa salvo en PAR_PURO con peso de viga, donde ΔP es la rama del par y la
    # rótula recibe además la parte del peso que le toca (9c). ΔW_i descansa sobre la
    # zapata interior y va directo a ella (9a).
    P_int_corr = combo_int.P_kN + V_cut
    if bw is not None:
        P_int_corr += bw.interior_increment_kN
    M_int_corr = M_int

    hipotesis = [
        COUPLE_TRANSFER_NOTES[layout.couple_transfer_mode],
        SELF_WEIGHT_NOTE,
        UNIFORM_PRESSURE_PREMISE,
        f"La viga transmite a la zapata exterior un par de {M_ext_corr:.2f} kN·m. No es un "
        f"artificio de cálculo: es la acción que impide el giro y, con ella, la "
        f"excentricidad de la resultante resulta nula y la presión uniforme.",
    ]
    hipotesis.append(beam_self_weight_note(layout, bw))
    if bw is not None and bw.fill_over_span:
        hipotesis.append(FILL_OVER_SPAN_PENDING)
    if factoring_pending_applies(combo_ext, W_viga):
        hipotesis.append(BEAM_SELF_WEIGHT_FACTORING_PENDING)
    if bw is not None and bw.load_factor is not None:
        hipotesis.append(BEAM_WEIGHT_FACTORED_NOTE.format(f=bw.load_factor))
    hipotesis.append(BEAM_SUPPORT_NOTES[layout.beam.support_mode])

    if cuerpo is not None:
        texto_cuerpo = (
            f"ΣM en s = {cuerpo.moment_reference_s_m:.4f} m (rótula, M interno = 0) y ΣFv = 0 "
        )
    elif bw is None:
        texto_cuerpo = "par puro: R_ext = P_col y ΣM = 0 sobre el centroide de la zapata "
    else:
        texto_cuerpo = (
            f"par puro (B*): N_a = W_V·(s_corte − x_V)/S = {bw.span_kN:.3f}·"
            f"({s_cut:.4f} − {bw.s_span_m:.4f})/{S:.4f} = {N_a:.3f} kN; R_ext = P_col + N_a + "
            f"ΔW_e = {combo_ext.P_kN:.3f} + {N_a:.3f} + {bw.exterior_increment_kN:.3f} y ΣM = 0 "
            f"sobre el centroide; al pórtico solo la rama del par, ΔP = −C_Z/S "
        )
    sustituida = (
        f"a = {a:.4f} m · L1 = {L1_m:.4f} m · e1 = L1/2 − a = {e1:.4f} m · "
        f"S = {layout.axis_distance_m:.4f} m | "
        + texto_cuerpo
        + f"-> R_ext = {R_ext:.3f} kN, V_corte = {V_cut:.3f} kN | "
        f"par transmitido a la zapata exterior = {M_ext_corr:.3f} kN·m "
        f"(centra la resultante: offset = {offset_ext:+.4f} m) | "
        + (f"ΔP = −V_corte = {delta_P:.3f} kN " if N_a is None else f"ΔP = −C_Z/S = {delta_P:.3f} kN ")
        + f"({'la exterior recibe más reacción y la interior queda aliviada' if delta_P > 0 else 'la exterior queda aliviada y la interior recibe más'}) | "
        f"residuos ΣFv = {res_F:.3e} kN, ΣM = {res_M:.3e} kN·m"
    )

    return CoupleDistribution(
        combo_name=combo_ext.name,
        combo_type=combo_ext.type.value,
        analysis_model=layout.analysis_model,
        a_m=a, L1_m=L1_m, e1_m=e1, S_m=layout.axis_distance_m,
        s_centroid_ext_m=L1_m / 2.0, s_cut_m=a + S,
        P_ext_kN=combo_ext.P_kN, M_ext_kNm=M_ext,
        P_int_kN=combo_int.P_kN, M_int_kNm=M_int,
        beam_self_weight_kN=W_viga,
        beam_self_weight_breakdown=bw,
        beam_node_reaction_kN=N_a,
        couple_transfer_mode=layout.couple_transfer_mode,
        M_couple_kNm=M_par,
        R_ext_kN=R_ext, V_cut_kN=V_cut, delta_P_kN=delta_P,
        # Rótula: el momento interno en el corte es CERO por definición del modelo
        # articulado. No es un resultado del cálculo, es la condición que lo cierra.
        M_cut_kNm=0.0,
        residual_force_kN=res_F, residual_moment_kNm=res_M,
        P_ext_corrected_kN=P_ext_corr, M_ext_corrected_kNm=M_ext_corr,
        P_int_corrected_kN=P_int_corr, M_int_corrected_kNm=M_int_corr,
        equation_substituted=sustituida,
        hypotheses=hipotesis,
    )


def _rigid_pressure(
    footprints: Footprints, P_total_kN: float, M_about_origin_kNm: float
) -> tuple[float, float, float, float]:
    """Campo lineal de presión sobre el área de apoyo. Devuelve (p0, p1, x_c, e).

    p(s) = p0 + p1·(s − x_c), en kPa.

    POR QUÉ NO HACE FALTA EL MÓDULO DE BALASTO
    ==========================================
    Para un cuerpo rígido el campo de desplazamientos es w(s) = w0 + θ·s, de modo que
    con Winkler p(s) = k_s·w0 + (k_s·θ)·s. Las incógnitas que fijan la presión son los
    PRODUCTOS k_s·w0 y k_s·θ, y ambos quedan determinados por ΣF = 0 y ΣM = 0 sobre
    magnitudes puramente geométricas. **k_s se cancela idénticamente.**

    Comprobado además por discretización numérica en resortes con k_s entre 5 000 y
    500 000 kN/m³: presiones y resultantes coinciden a doce cifras. Lo único que cambia
    con k_s es el asentamiento, que no interviene en el diseño. Es la resolución de
    TBD-C2, y coincide con el procedimiento de los apuntes CR2-93-134 §3.6 problema 2,
    que aplica σ = P/A ± M·y/I sobre las dos huellas tratadas como una sección."""
    A = footprints.total_area_m2
    x_c = footprints.centroid_m
    I = footprints.inertia_m4
    x_R = M_about_origin_kNm / P_total_kN
    e = x_R - x_c
    M_c = P_total_kN * e
    return P_total_kN / A, M_c / I, x_c, e


def _integrate_footprint(f, p0: float, p1: float, x_c: float) -> tuple[float, float]:
    """(resultante [kN], su posición s [m]) de la presión lineal sobre una huella.

    Integración EXACTA de un trapecio, no muestreada: la presión es lineal y su
    resultante y su centro se conocen en forma cerrada."""
    a, b, w = f.start_m, f.end_m, f.width_m
    # p(s) = p0 + p1·(s − x_c)
    L = b - a
    R = w * (p0 * L + p1 * ((b - x_c) ** 2 - (a - x_c) ** 2) / 2.0)
    if abs(R) < 1e-12:
        return 0.0, f.centroid_m
    mom = w * (
        p0 * (b**2 - a**2) / 2.0
        + p1 * (
            (b**3 - a**3) / 3.0 - x_c * (b**2 - a**2) / 2.0
        )
    )
    return R, mom / R


def _rigid_body_loads(
    *, a: float, x_col_int: float, P_ext: float, P_int: float,
    fe, fi, W_ext: float, W_int: float, beam: BeamSelfWeightBreakdown | None,
) -> list[tuple[float, float]]:
    """Cargas verticales del conjunto rígido: (posición s, magnitud hacia ABAJO).

    UNA SOLA DEFINICIÓN. La usan el reparto (`_distribute_rigid_body`) y la estática de
    la viga (`rigid_pressure_field`). Antes de 5A la viga no la usaba en absoluto:
    tomaba una presión uniforme y un `R_ext` bruto. Definir aquí qué cargas actúan y
    dónde, y no en dos sitios, impide que reparto y viga vuelvan a describir cuerpos
    distintos. El orden de la lista es el de siempre: las sumas en coma flotante que se
    hacen sobre ella no cambian ni un bit respecto de la versión anterior.

    Peso de la viga (Fase 9a): ΔW_e, W_V y ΔW_i, cada uno en su centroide y en ese
    orden. ΔW_i va SIEMPRE último: `_distribute_rigid_body` lo excluye del cuerpo a la
    izquierda del corte, porque pertenece a la zapata interior."""
    cargas = [
        (a, P_ext), (x_col_int, P_int),
        (fe.centroid_m, W_ext), (fi.centroid_m, W_int),
    ]
    if beam is not None:
        for s, W in (
            (beam.s_exterior_increment_m, beam.exterior_increment_kN),
            (beam.s_span_m, beam.span_kN),
            (beam.s_interior_increment_m, beam.interior_increment_kN),
        ):
            if W > 0.0:
                cargas.append((s, W))
    return cargas


def _rigid_resultant(
    cargas: list[tuple[float, float]], M_ext: float, M_int: float
) -> tuple[float, float]:
    """(P total, momento estático respecto de s = 0) del conjunto rígido.

    Los momentos de columna entran con la convención de E.050 art. 28.1 —desplazan la
    resultante hacia +x—, sumados directamente al momento estático, como hace el
    problema 2 de los apuntes CR2-93-134: «0.4 (95) + 6.9 (180) + 4.88 (25.27) + 6 − 6.5
    = X (300.27)»."""
    P_total = sum(P for _, P in cargas)
    M_origen = sum(x * P for x, P in cargas) + M_ext + M_int
    return P_total, M_origen


def rigid_pressure_field(
    layout: ConnectedFootingLayout, footprints: Footprints, d: "CoupleDistribution"
) -> tuple[float, float, float]:
    """Campo de presión del cuerpo rígido para un reparto ya resuelto: (p₀, p₁, x_c).

    p(s) = p₀ + p₁·(s − x_c)   [kPa]

    Lo necesita la estática de la viga (defecto D3, mecanismo M1): la reacción del
    terreno bajo la zapata de lindero NO es uniforme en este modelo, y la viga tiene que
    cargarse con la presión real. Se reconstruye desde los datos del propio reparto con
    las MISMAS cargas (`_rigid_body_loads`) y la MISMA solución de sección
    (`_rigid_pressure`), de modo que es el campo del reparto y no una aproximación.

    Solo tiene sentido en CUERPO_RIGIDO; en el modelo articulado la presión es uniforme
    por hipótesis y no hay campo compuesto que reconstruir."""
    if d.analysis_model is not AnalysisModel.CUERPO_RIGIDO:
        raise ValueError(
            "El campo de presión compuesto solo existe en el modelo CUERPO_RIGIDO: en el "
            "articulado la presión bajo la zapata de lindero es uniforme por hipótesis."
        )
    fe, fi = footprints.exterior, footprints.interior
    cargas = _rigid_body_loads(
        a=d.a_m, x_col_int=d.s_cut_m, P_ext=d.P_ext_kN, P_int=d.P_int_kN,
        fe=fe, fi=fi, W_ext=d.W_ext_kN, W_int=d.W_int_kN,
        beam=d.beam_self_weight_breakdown,
    )
    P_total, M_origen = _rigid_resultant(cargas, d.M_ext_kNm, d.M_int_kNm)
    p0, p1, x_c, _ = _rigid_pressure(footprints, P_total, M_origen)
    return p0, p1, x_c


def _distribute_rigid_body(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    combo_ext: LoadCombination,
    combo_int: LoadCombination,
    soil,
    concrete_unit_weight_kNm3: float,
) -> CoupleDistribution:
    """ESTRATEGIA CUERPO_RIGIDO — apuntes CR2-93-134 §3.6, problema de aplicación 2.

        «Solución simplificada del problema asumiendo zapata rígida y comportamiento
         elástico lineal del suelo. El modelo de análisis será el de un cuerpo rígido
         para el conjunto de 2 zapatas y la viga de conexión pues la viga lleva
         esfuerzos de la zapata izquierda a la zapata derecha y viceversa.»

    HIPÓTESIS QUE LA DEFINEN, y que ninguna norma impone:

      H1  El conjunto {zapata exterior + viga + zapata interior} gira como UN SOLO
          cuerpo rígido. La unión transmite momento en ambos sentidos.
      H2  El suelo responde linealmente, con módulo de balasto UNIFORME bajo las dos
          huellas. Su valor no hace falta: se cancela (ver `_rigid_pressure`).
      H3  El peso propio de cada zapata actúa en su propio centroide.

    DIFERENCIAS CON LA ESTRATEGIA ARTICULADA, que son las consecuencias F1, F2 y F3 de
    la auditoría de Fase 4:

      F1  Necesita las DOS huellas, no solo la longitud de la de lindero.
      F2  El peso propio de las zapatas SÍ entra en el reparto. En el modelo articulado
          se agrupaba y desaparecía porque la resultante del suelo pasaba por el
          centroide de la zapata; aquí NO pasa, y sus momentos dejan de cancelarse.
      F3  La presión puede resultar negativa en un extremo. E.060 §15.2 prohíbe
          considerar tracciones, de modo que el despegue se detecta y se declara.
    """
    if combo_ext.name != combo_int.name:
        raise ValueError(
            f"El reparto se resuelve combinación a combinación: «{combo_ext.name}» y "
            f"«{combo_int.name}» no son la misma."
        )

    eje = layout.longitudinal_axis
    M_ext = combo_ext.Mx_kNm if eje == "X" else combo_ext.My_kNm
    M_int = combo_int.Mx_kNm if eje == "X" else combo_int.My_kNm

    fe, fi = footprints.exterior, footprints.interior
    a = layout.exterior.anchor.axis_distance_to_column_center_m(layout.exterior.column)
    S = layout.axis_distance_m
    x_col_int = a + S

    # --- F2: el peso propio entra, y sale del MISMO módulo que usa el solver ---
    W_ext = compute_self_weight(
        B_m=fe.width_m, L_m=fe.length_m, h_m=fe.h_m, Df_m=soil.Df_m,
        concrete_unit_weight_kNm3=concrete_unit_weight_kNm3,
        soil_unit_weight_kNm3=soil.gamma_kNm3,
    ).W_total_kN
    W_int = compute_self_weight(
        B_m=fi.width_m, L_m=fi.length_m, h_m=fi.h_m, Df_m=soil.Df_m,
        concrete_unit_weight_kNm3=concrete_unit_weight_kNm3,
        soil_unit_weight_kNm3=soil.gamma_kNm3,
    ).W_total_kN
    # D10C-1: CM con f_CM en la combinación factorizada por casos; 1,0 en el resto. El MISMO
    # W factorizado entra en las cargas del cuerpo rígido y en la resta R − W de abajo.
    f_zapatas = footing_weight_factor(combo_ext, combo_int)
    W_ext_sin_factor, W_int_sin_factor = W_ext, W_int
    W_ext, W_int = f_zapatas * W_ext, f_zapatas * W_int
    bw = beam_self_weight_breakdown(layout, footprints, soil, concrete_unit_weight_kNm3)
    bw = factored_beam_weight(bw, combo_ext, combo_int, layout.beam.self_weight_dead_load_factor)
    W_viga = bw.total_kN if bw is not None else 0.0

    # --- Equilibrio global del cuerpo rígido ---------------------------------
    cargas = _rigid_body_loads(
        a=a, x_col_int=x_col_int, P_ext=combo_ext.P_kN, P_int=combo_int.P_kN,
        fe=fe, fi=fi, W_ext=W_ext, W_int=W_int, beam=bw,
    )
    P_total, M_origen = _rigid_resultant(cargas, M_ext, M_int)

    p0, p1, x_c, e = _rigid_pressure(footprints, P_total, M_origen)

    def presion(s: float) -> float:
        return p0 + p1 * (s - x_c)

    extremos = [presion(x) for x in (fe.start_m, fe.end_m, fi.start_m, fi.end_m)]
    sigma_min, sigma_max = min(extremos), max(extremos)
    hay_despegue = sigma_min < -1e-9

    R_ext, x_R_ext = _integrate_footprint(fe, p0, p1, x_c)
    R_int, x_R_int = _integrate_footprint(fi, p0, p1, x_c)

    # --- Acciones corregidas -------------------------------------------------
    # `evaluate_candidate` añade el peso propio por su cuenta, de modo que recibe la
    # carga NETA. Y compone la excentricidad como ex = (M + P·offset)/(P + W): el
    # momento que hay que entregarle es el que reproduce la excentricidad REAL de la
    # resultante respecto del centroide de su zapata.
    P_ext_corr = R_ext - W_ext
    P_int_corr = R_int - W_int
    offset_ext = layout.exterior.anchor.offset_sign() * (fe.length_m / 2.0 - a)
    e_res_ext = x_R_ext - fe.centroid_m
    e_res_int = x_R_int - fi.centroid_m
    signo = layout.exterior.anchor.offset_sign()
    M_ext_corr = signo * (e_res_ext * R_ext) - P_ext_corr * offset_ext
    M_int_corr = signo * (e_res_int * R_int)

    delta_P = P_ext_corr - combo_ext.P_kN

    # --- M y V internos en el eje de la columna interior ---------------------
    # Todo lo que queda a la IZQUIERDA de la sección de corte.
    # ΔW_i queda a la izquierda del eje pero descansa sobre la zapata interior: no es
    # de este cuerpo (9a). `_rigid_body_loads` lo pone último.
    cuerpo_izq = cargas[:-1] if bw is not None and bw.interior_increment_kN > 0.0 else cargas
    izq = [(x, -P) for x, P in cuerpo_izq if x < x_col_int - 1e-12]
    R_izq, x_izq = _integrate_footprint(
        fe, p0, p1, x_c
    )
    V_cut = -(R_izq + sum(P for _, P in izq))
    M_cut = R_izq * (x_col_int - x_izq) + sum(P * (x_col_int - x) for x, P in izq) + M_ext

    hipotesis = [
        COUPLE_TRANSFER_NOTES_RIGID,
        RIGID_BODY_PREMISE,
        f"Peso propio de las zapatas INCLUIDO en el reparto: {W_ext:.2f} kN la exterior "
        f"y {W_int:.2f} kN la interior. En el modelo articulado se agrupaba y "
        f"desaparecía; aquí la resultante no pasa por el centroide de cada zapata y sus "
        f"momentos ya no se cancelan.",
        beam_self_weight_note(layout, bw),
        BEAM_SUPPORT_NOTES[layout.beam.support_mode],
    ]
    if bw is not None and bw.fill_over_span:
        hipotesis.append(FILL_OVER_SPAN_PENDING)
    if factoring_pending_applies(combo_ext, W_viga):
        hipotesis.append(BEAM_SELF_WEIGHT_FACTORING_PENDING)
    if bw is not None and bw.load_factor is not None:
        hipotesis.append(BEAM_WEIGHT_FACTORED_NOTE.format(f=bw.load_factor))
    if combo_ext.composition is not None and combo_ext.type is LoadCombinationType.FACTORIZADA:
        hipotesis.append(FOOTING_WEIGHT_CM_NOTE.format(
            combo=combo_ext.name, f=f_zapatas, we=W_ext, wi=W_int,
            we0=W_ext_sin_factor, wi0=W_int_sin_factor,
        ))
    if hay_despegue:
        hipotesis.append(
            f"DESPEGUE: la presión mínima resulta {sigma_min:.2f} kPa, negativa. "
            + UPLIFT_NOT_SOLVED
        )

    sustituida = (
        f"A = {footprints.total_area_m2:.4f} m² · x_c = {x_c:.4f} m · "
        f"I = {footprints.inertia_m4:.4f} m⁴ | "
        f"P = {P_total:.2f} kN en x_R = {M_origen/P_total:.4f} m -> e = {e:+.4f} m | "
        f"σ = P/A ± M·y/I -> [{sigma_min:.2f}, {sigma_max:.2f}] kPa | "
        f"R_ext = {R_ext:.2f} kN en s = {x_R_ext:.4f} m · "
        f"R_int = {R_int:.2f} kN en s = {x_R_int:.4f} m"
    )

    return CoupleDistribution(
        combo_name=combo_ext.name, combo_type=combo_ext.type.value,
        analysis_model=layout.analysis_model,
        couple_transfer_mode=layout.couple_transfer_mode,
        M_couple_kNm=M_ext - combo_ext.P_kN * (fe.length_m / 2.0 - a),
        a_m=a, L1_m=fe.length_m, e1_m=fe.length_m / 2.0 - a, S_m=S,
        s_centroid_ext_m=fe.centroid_m, s_cut_m=x_col_int,
        P_ext_kN=combo_ext.P_kN, M_ext_kNm=M_ext,
        P_int_kN=combo_int.P_kN, M_int_kNm=M_int,
        beam_self_weight_kN=W_viga,
        beam_self_weight_breakdown=bw,
        R_ext_kN=R_ext, V_cut_kN=V_cut, M_cut_kNm=M_cut, delta_P_kN=delta_P,
        residual_force_kN=0.0, residual_moment_kNm=0.0,
        bearing_area_m2=footprints.total_area_m2,
        bearing_centroid_m=x_c, bearing_inertia_m4=footprints.inertia_m4,
        sigma_min_kPa=sigma_min, sigma_max_kPa=sigma_max, uplift=hay_despegue,
        W_ext_kN=W_ext, W_int_kN=W_int,
        P_ext_corrected_kN=P_ext_corr, M_ext_corrected_kNm=M_ext_corr,
        P_int_corrected_kN=P_int_corr, M_int_corrected_kNm=M_int_corr,
        equation_substituted=sustituida, hypotheses=hipotesis,
    )


# Las dos estrategias, resueltas por el modelo declarado. El registro existe para que
# añadir o cambiar una no obligue a tocar el orquestador: `connected_solver` llama a
# `distribute_couple` y no sabe cuál corrió.
DISTRIBUTION_STRATEGIES = {
    AnalysisModel.ARTICULADO: _distribute_articulated,
    AnalysisModel.CUERPO_RIGIDO: _distribute_rigid_body,
}


def _checked(d: CoupleDistribution) -> CoupleDistribution:
    """Verifica los invariantes del CONTRATO, no los de una estrategia concreta.

    Se aplica a la salida de cualquier estrategia. Es deliberado: los tres invariantes
    —suma de fuerzas nula, suma de momentos nula y conservación de carga— son
    propiedades de la física, no del método, y comprobarlos aquí significa que una
    estrategia nueva no puede saltárselos por olvido."""
    if not d.conserves_load:
        raise ValueError(
            f"El reparto de la combinación «{d.combo_name}» no cuadra en carga vertical: "
            f"sobran o faltan {d.load_conservation_residual_kN:+.6f} kN respecto de lo que "
            f"el modo «{d.couple_transfer_mode.value}» admite "
            f"({d.expected_residual_kN:+.3f} kN). Lo único que puede aumentar el total es "
            f"el peso propio de la viga cuando se declara EXPLICITO, y lo único que puede "
            f"faltar es la rama del par que el pórtico recoge cuando se declara "
            f"PAR_PURO_EN_ZAPATA. Un signo invertido produce exactamente este error."
        )
    if not d.closes:
        raise ValueError(
            f"El equilibrio de la combinación «{d.combo_name}» no cierra: residuos "
            f"SFv = {d.residual_force_kN:.3e} kN, SM = {d.residual_moment_kNm:.3e} kN·m."
        )
    return d


def distribute_couple(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    combo_ext: LoadCombination,
    combo_int: LoadCombination,
    soil,
    concrete_unit_weight_kNm3: float = 24.0,
) -> CoupleDistribution:
    """Resuelve el reparto para una combinación, con la estrategia del modelo declarado.

    Es el único punto de entrada. El orquestador no conoce las estrategias ni ramifica
    por modelo: recibe siempre el mismo `CoupleDistribution`, y los invariantes se
    comprueban sobre él."""
    # D1. El validador del layout ya lo rechaza, pero `model_copy(update=…)` no lo
    # ejecuta: sin esta guarda la combinación incompatible volvería a entrar por ahí.
    check_couple_mode_compatible(layout.analysis_model, layout.couple_transfer_mode)
    check_beam_support_supported(layout.beam.support_mode)
    estrategia = DISTRIBUTION_STRATEGIES[layout.analysis_model]
    return _checked(
        estrategia(layout, footprints, combo_ext, combo_int, soil, concrete_unit_weight_kNm3)
    )


# =========================================================================
# Fase 10C — composición de las cargas corregidas, por superposición
# =========================================================================

ENGINE_BEAM_WEIGHT_CASE = "peso propio de la viga"
ENGINE_FOOTING_WEIGHT_CASE = "peso propio de las zapatas (reparto del cuerpo rígido)"
ORIGIN_EXTERIOR = "columna exterior"
ORIGIN_INTERIOR = "columna interior"
ORIGIN_ENGINE = "motor"

REDISTRIBUTED_COMPOSITION_NOTE = (
    "Composición de las cargas corregidas (Fase 10C): el reparto es lineal en las cargas de "
    "las columnas y en las cargas que genera el motor, de modo que cada caso aporta a cada "
    "zapata lo que el MISMO reparto produce con ese caso solo (superposición). El aporte "
    "conserva el tipo, el nivel y el factor del caso que lo origina; el peso propio de la "
    "viga es CM con el factor CM de la combinación (E.020 art. 2); en CUERPO_RIGIDO, el "
    "reparto del peso propio de las zapatas (concreto y relleno) es CM con f_CM en las "
    "combinaciones factorizadas y 1,0 en las de servicio (D10C-1). Las componentes suman "
    "exactamente la carga corregida."
)


def _synthetic_combo(
    base: LoadCombination, P_kN: float, M_kNm: float, axis: str, dead_load_factor: float | None
) -> LoadCombination:
    """Combinación auxiliar con solo P y el momento del eje, y el factor CM indicado. Sirve
    para evaluar el reparto con una sola fuente de carga."""
    campos = {
        "P_kN": P_kN, "Mx_kNm": 0.0, "My_kNm": 0.0, "Hx_kN": 0.0, "Hy_kN": 0.0,
        "composition": LoadComposition(components=[], dead_load_factor=dead_load_factor),
    }
    campos["Mx_kNm" if axis == "X" else "My_kNm"] = M_kNm
    return base.model_copy(update=campos)


def _corrected_actions(d: CoupleDistribution) -> tuple[float, float, float, float]:
    return (d.P_ext_corrected_kN, d.M_ext_corrected_kNm, d.P_int_corrected_kN, d.M_int_corrected_kNm)


def _component(
    *, case_name: str, kind: str, level: str | None, factor: float, origin: str,
    P: float, M_axis: float, M_transverse: float, Hx: float, Hy: float, axis: str,
) -> ComponentAction:
    return ComponentAction(
        case_name=case_name, kind=kind, level=level, factor=factor, origin=origin,
        P_kN=P,
        Mx_kNm=M_axis if axis == "X" else M_transverse,
        My_kNm=M_transverse if axis == "X" else M_axis,
        Hx_kN=Hx, Hy_kN=Hy,
    )


def redistributed_compositions(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    combo_ext: LoadCombination,
    combo_int: LoadCombination,
    d: CoupleDistribution,
    soil,
    concrete_unit_weight_kNm3: float = 24.0,
) -> tuple[LoadComposition | None, LoadComposition | None]:
    """Composición de las dos cargas corregidas de UNA combinación (Fase 10C).

    Modo directo (sin composición en las columnas): (None, None). No se infiere nada.

    Modo por casos: el reparto de las tres estrategias es AFÍN en (P_ext, M_ext, P_int,
    M_int) más las cargas que genera el motor —peso de la viga y, en CUERPO_RIGIDO, peso de
    las zapatas—. Se evalúa el MISMO `distribute_couple` —no se reescriben sus ecuaciones—:

        base      columnas en cero: peso de la viga (× factor CM) + peso de las zapatas
        sin viga  columnas en cero y factor CM nulo: solo peso de las zapatas
        unitarias base + 1 kN (o 1 kN·m) en cada entrada, menos base: coeficientes

    y cada caso aporta coeficientes · (P, M del eje) del caso. El momento transversal y las
    fuerzas horizontales no pasan por el reparto (`_corrected_combo` los conserva): cada zapata
    recibe los de su propia columna. La suma se contrasta con la carga corregida; si no
    cerrara, el reparto dejó de ser lineal y se detiene."""
    ce, ci = combo_ext.composition, combo_int.composition
    if ce is None and ci is None:
        return None, None
    if ce is None or ci is None:
        raise ValueError(
            f'La combinación "{combo_ext.name}" tiene composición en una sola columna: las dos '
            f"columnas deben usar el mismo modo de cargas."
        )
    eje = layout.longitudinal_axis
    f_cm = ce.dead_load_factor

    def reparto(Pe, Me, Pi, Mi, lay=layout):
        dd = distribute_couple(
            lay, footprints,
            _synthetic_combo(combo_ext, Pe, Me, eje, f_cm),
            _synthetic_combo(combo_int, Pi, Mi, eje, f_cm),
            soil, concrete_unit_weight_kNm3,
        )
        return _corrected_actions(dd)

    def resta(x, y):
        return tuple(a - b for a, b in zip(x, y))

    # Punto de referencia con carga NO nula. Con la carga del motor anulada (combinación sin CM,
    # D10C-1) un reparto con columnas en cero dejaría el cuerpo rígido sin carga. Al ser afín,
    # op(x) = c0 + J·x: J sale de incrementos alrededor de x0 y c0 = op(x0) − J·x0.
    P_ref = max(abs(d.P_ext_kN) + abs(d.P_int_kN), 1.0)
    M_ref = P_ref * max(d.S_m, 1.0)
    x0 = {"Pe": P_ref, "Me": 0.0, "Pi": P_ref, "Mi": 0.0}
    paso = {"Pe": P_ref, "Me": M_ref, "Pi": P_ref, "Mi": M_ref}
    en_x0 = reparto(**x0)
    coef = {}
    for k in ("Pe", "Me", "Pi", "Mi"):
        x = dict(x0)
        x[k] += paso[k]
        coef[k] = tuple(v / paso[k] for v in resta(reparto(**x), en_x0))

    def constante(op_x0):
        return tuple(op_x0[i] - sum(coef[k][i] * x0[k] for k in x0) for i in range(4))

    base = constante(en_x0)
    # Sin viga: el mismo layout con el peso de la viga despreciado. No se usa un factor CM
    # nulo porque desde D10C-1 ese factor también escala el peso de las zapatas.
    if layout.beam.models_self_weight:
        sin_peso_viga = layout.model_copy(update={"beam": layout.beam.model_copy(update={
            "self_weight_mode": BeamSelfWeightMode.DESPRECIADO, "soffit_above_base_m": None,
        })})
        sin_viga = constante(reparto(**x0, lay=sin_peso_viga))
    else:
        sin_viga = base

    comp_ext: list[ComponentAction] = []
    comp_int: list[ComponentAction] = []
    for origen, comp, kP, kM in ((ORIGIN_EXTERIOR, ce, "Pe", "Me"), (ORIGIN_INTERIOR, ci, "Pi", "Mi")):
        propia_ext = origen == ORIGIN_EXTERIOR
        for c in comp.components:
            M_eje = c.Mx_kNm if eje == "X" else c.My_kNm
            M_trans = c.My_kNm if eje == "X" else c.Mx_kNm
            aporte = tuple(coef[kP][i] * c.P_kN + coef[kM][i] * M_eje for i in range(4))
            comunes = dict(case_name=c.case_name, kind=c.kind, level=c.level, factor=c.factor,
                           origin=origen, axis=eje)
            comp_ext.append(_component(
                P=aporte[0], M_axis=aporte[1],
                M_transverse=M_trans if propia_ext else 0.0,
                Hx=c.Hx_kN if propia_ext else 0.0, Hy=c.Hy_kN if propia_ext else 0.0, **comunes,
            ))
            comp_int.append(_component(
                P=aporte[2], M_axis=aporte[3],
                M_transverse=0.0 if propia_ext else M_trans,
                Hx=0.0 if propia_ext else c.Hx_kN, Hy=0.0 if propia_ext else c.Hy_kN, **comunes,
            ))

    motor = []
    if layout.beam.models_self_weight:
        motor.append((ENGINE_BEAM_WEIGHT_CASE, f_cm if f_cm is not None else 0.0, resta(base, sin_viga)))
    if layout.analysis_model is AnalysisModel.CUERPO_RIGIDO:
        motor.append((ENGINE_FOOTING_WEIGHT_CASE, footing_weight_factor(combo_ext, combo_int), sin_viga))
    for nombre, factor, aporte in motor:
        comunes = dict(case_name=nombre, kind="CM", level=None, factor=factor, origin=ORIGIN_ENGINE,
                       M_transverse=0.0, Hx=0.0, Hy=0.0, axis=eje)
        comp_ext.append(_component(P=aporte[0], M_axis=aporte[1], **comunes))
        comp_int.append(_component(P=aporte[2], M_axis=aporte[3], **comunes))

    total = _corrected_actions(d)
    escala = max(abs(d.P_ext_kN) + abs(d.P_int_kN) + abs(d.beam_self_weight_kN)
                 + abs(d.W_ext_kN) + abs(d.W_int_kN), 1.0)
    suma = (
        sum(c.P_kN for c in comp_ext), sum((c.Mx_kNm if eje == "X" else c.My_kNm) for c in comp_ext),
        sum(c.P_kN for c in comp_int), sum((c.Mx_kNm if eje == "X" else c.My_kNm) for c in comp_int),
    )
    for nombre, t, s_ in zip(("P_ext", "M_ext", "P_int", "M_int"), total, suma):
        if abs(t - s_) > EQUILIBRIUM_TOL * escala * max(d.S_m, 1.0):
            raise ValueError(
                f'Composición de la carga corregida "{combo_ext.name}": las componentes suman '
                f"{s_:.6f} y la carga corregida {nombre} vale {t:.6f}. El reparto dejó de ser "
                f"lineal y la superposición no es válida."
            )
    return (
        LoadComposition(components=comp_ext, dead_load_factor=f_cm, redistributed=True),
        LoadComposition(components=comp_int, dead_load_factor=ci.dead_load_factor, redistributed=True),
    )


class CorrectedLoads(BaseModel):
    """Los dos `LoadCaseSet` corregidos, listos para los motores existentes."""

    exterior: LoadCaseSet
    interior: LoadCaseSet
    distributions: list[CoupleDistribution]

    def by_combo(self, name: str) -> CoupleDistribution | None:
        for d in self.distributions:
            if d.combo_name == name:
                return d
        return None


def _corrected_combo(
    base: LoadCombination, P_kN: float, M_kNm: float, axis: Literal["X", "Y"], suffix: str,
    composition: LoadComposition | None = None,
) -> LoadCombination:
    """Copia la combinación cambiando solo P y el momento del eje longitudinal.

    El momento del eje TRANSVERSAL se conserva intacto: la viga reparte el par en su
    propia dirección y no dice nada sobre la otra."""
    campos = {"P_kN": P_kN, "description": (base.description + " " + suffix).strip()}
    campos["Mx_kNm" if axis == "X" else "My_kNm"] = M_kNm
    # La composición de la columna NO se copia: la carga corregida incluye la transferencia
    # de la viga y su peso. Fase 10C: en el modo por casos se adjunta la composición de la
    # carga CORREGIDA (`redistributed_compositions`), cuyas componentes sí suman P y M. En el
    # modo directo queda None y no se infiere nada.
    campos["composition"] = composition
    return base.model_copy(update=campos)


def correct_loads(
    layout: ConnectedFootingLayout,
    footprints: Footprints,
    soil,
    concrete_unit_weight_kNm3: float = 24.0,
) -> CorrectedLoads:
    """Resuelve el reparto de TODAS las combinaciones y devuelve las cargas corregidas.

    Con esto, los motores existentes de zapata se llaman sin modificar ni una línea:
    reciben un `LoadCaseSet` normal y no saben que vienen de un sistema conectado."""
    ext_por_nombre = {
        c.name: c for c in layout.exterior.loads.service + layout.exterior.loads.factored
    }
    int_por_nombre = {
        c.name: c for c in layout.interior.loads.service + layout.interior.loads.factored
    }

    distribuciones: list[CoupleDistribution] = []
    ext_serv, ext_fact, int_serv, int_fact = [], [], [], []

    for grupo_ext, grupo_int, destino_ext, destino_int in (
        (layout.exterior.loads.service, layout.interior.loads.service, ext_serv, int_serv),
        (layout.exterior.loads.factored, layout.interior.loads.factored, ext_fact, int_fact),
    ):
        for combo_ext in grupo_ext:
            combo_int = next(c for c in grupo_int if c.name == combo_ext.name)
            d = distribute_couple(
                layout, footprints, combo_ext, combo_int, soil, concrete_unit_weight_kNm3
            )
            comp_ext, comp_int = redistributed_compositions(
                layout, footprints, combo_ext, combo_int, d, soil, concrete_unit_weight_kNm3
            )
            if comp_ext is not None:
                d = d.model_copy(update={
                    "exterior_corrected_composition": comp_ext,
                    "interior_corrected_composition": comp_int,
                    "hypotheses": d.hypotheses + [REDISTRIBUTED_COMPOSITION_NOTE],
                })
            distribuciones.append(d)
            destino_ext.append(
                _corrected_combo(
                    combo_ext, d.P_ext_corrected_kN, d.M_ext_corrected_kNm,
                    layout.longitudinal_axis,
                    "[carga corregida por el reparto: momento transferido al par]",
                    comp_ext,
                )
            )
            destino_int.append(
                _corrected_combo(
                    combo_int, d.P_int_corrected_kN, d.M_int_corrected_kNm,
                    layout.longitudinal_axis,
                    f"[carga corregida por el reparto: −ΔP = {-d.delta_P_kN:+.1f} kN]",
                    comp_int,
                )
            )

    # Silencia el linter sobre los diccionarios auxiliares, que documentan la
    # correspondencia exigida por el validador del layout.
    assert set(ext_por_nombre) == set(int_por_nombre)

    return CorrectedLoads(
        exterior=LoadCaseSet(service=ext_serv, factored=ext_fact),
        interior=LoadCaseSet(service=int_serv, factored=int_fact),
        distributions=distribuciones,
    )
