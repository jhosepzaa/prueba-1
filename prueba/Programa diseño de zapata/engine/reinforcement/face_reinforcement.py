"""Refuerzo por CARA de la zapata — Fase 2.

POR QUÉ UN CONCEPTO NUEVO Y NO LAS «CAPAS» EXISTENTES
=====================================================
`rebar_geometry.py` llama "inferior" y "superior" a las dos capas de la parrilla
**de abajo**: ambas se miden desde el recubrimiento inferior y ambas resisten
momento positivo. Es una distinción de capas dentro de una misma cara.

Lo que la zapata combinada necesita es otra cosa: una CARA distinta, la de arriba,
que resiste el momento NEGATIVO entre columnas. Su peralte efectivo se mide desde
la fibra de abajo —que pasa a ser la comprimida— y su recubrimiento es otro. Meter
eso en la semántica de capas produciría un peralte efectivo equivocado.

Por eso aquí `face` es "inferior" o "superior" refiriéndose a la CARA de la
zapata, y el peralte se calcula desde la fibra comprimida que corresponde a cada
una.

RECUBRIMIENTO — E.060 §7.7.1
============================
La tabla de §7.7.1 no da un valor único: depende de la exposición.

  (a) Concreto vaciado contra el suelo y expuesto permanentemente a él .... 70 mm
  (b) En contacto permanente con el suelo o la intemperie:
        barras 3/4" y mayores ................................................ 50 mm
        barras 5/8" y menores ................................................ 40 mm
  (c) No expuesto a la intemperie ni en contacto con el suelo:
        losas, muros, viguetas, barras <= 1 3/8" ............................. 20 mm

La cara INFERIOR de una zapata se vacía contra el suelo: le corresponde el caso
(a), 70 mm, y así lo tenía ya el motor.

La cara SUPERIOR **no está vaciada contra el suelo**. Qué caso le aplica depende
de si queda enterrada bajo relleno —caso (b)— o dentro de un ambiente protegido
—caso (c)—. Eso es un dato de proyecto, no una constante: **lo declara el
usuario**. El motor no elige por él, y el valor adoptado queda en la traza.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.codes.peru.e060_development import development_length_table_12_1, psi_t_top_bar
from engine.reinforcement.rebar_selector import select_rebar
from engine.results.status import CheckStatus

Face = Literal["inferior", "superior"]

# --- E.060 §7.7.1, casos aplicables a la cara superior de una zapata ---------
# Los VALORES son normativos; cuál aplica es una condición de proyecto que declara
# el usuario. Las barras de reparto de la cara superior de una zapata rara vez
# superan 5/8", pero el caso se distingue igualmente para no elegir por el usuario.
TOP_COVER_OPTIONS_MM: dict[str, float] = {
    "contacto_suelo_barras_grandes": 50.0,  # §7.7.1(b), barras 3/4" y mayores
    "contacto_suelo_barras_pequenas": 40.0,  # §7.7.1(b), barras 5/8" y menores
    "no_expuesto": 20.0,  # §7.7.1(c), losas no expuestas
    "vaciado_contra_suelo": 75.0,  # §7.7.1 a), si el proyecto lo justifica
}

TopCoverCase = Literal[
    "contacto_suelo_barras_grandes",
    "contacto_suelo_barras_pequenas",
    "no_expuesto",
    "vaciado_contra_suelo",
]

TOP_COVER_REFERENCE = (
    "E.060 §7.7.1. La cara superior de una zapata NO está vaciada contra el suelo, de modo "
    "que no le aplica el caso a) de 75 mm por defecto. Cuál de los casos de la tabla "
    "corresponde depende de la exposición real —enterrada bajo relleno, caso (b); o "
    "protegida, caso (c)—, que es un dato de proyecto y lo declara el usuario."
)


class TopCoverDeclaration(BaseModel):
    """Recubrimiento de la cara superior, declarado por el usuario.

    No tiene valor por defecto silencioso: el llamador elige un caso de la tabla de
    §7.7.1 o entrega un valor propio justificado."""

    case: TopCoverCase | None = Field(
        default=None, description="Caso de la tabla de §7.7.1 que aplica a la cara superior"
    )
    explicit_mm: float | None = Field(
        default=None, gt=0, description="Valor declarado directamente, si el proyecto lo justifica"
    )

    def resolve_mm(self) -> tuple[float, str]:
        """Devuelve (recubrimiento, justificación). Falla si no se declaró nada:
        suponerlo sería exactamente lo que esta clase existe para impedir."""
        if self.explicit_mm is not None:
            return self.explicit_mm, (
                f"Recubrimiento superior de {self.explicit_mm:.0f} mm declarado directamente por "
                f"el proyectista. {TOP_COVER_REFERENCE}"
            )
        if self.case is not None:
            valor = TOP_COVER_OPTIONS_MM[self.case]
            return valor, (
                f"Recubrimiento superior de {valor:.0f} mm por el caso «{self.case}» de la tabla "
                f"de E.060 §7.7.1, declarado por el proyectista. {TOP_COVER_REFERENCE}"
            )
        raise ValueError(
            "No se ha declarado el recubrimiento de la cara superior. La tabla de E.060 §7.7.1 "
            "no da un valor único para esa cara: depende de la exposición, que es un dato de "
            "proyecto. Declare `case` o `explicit_mm`."
        )


class FaceReinforcementResult(BaseModel):
    """Armado de una cara en una dirección."""

    face: Face
    direction: Literal["X", "Y"]
    Mu_kNm: float = Field(..., description="Momento de diseño para esta cara, en valor absoluto")

    width_m: float = Field(..., description="Ancho de la sección considerada")
    h_m: float
    cover_m: float
    d_m: float = Field(..., description="Peralte efectivo desde la fibra COMPRIMIDA de esta cara")

    As_required_m2: float
    As_min_m2: float
    As_design_m2: float
    rho_provided: float

    min_governed_by: str = Field(..., description="Qué disposición gobernó el mínimo")
    code_reference: str
    note: str


def effective_depth_for_face(face: Face, h_m: float, cover_m: float, db_m: float) -> float:
    """Peralte efectivo de una cara, medido desde la fibra COMPRIMIDA.

    - Cara inferior traccionada (momento positivo): la fibra comprimida es la de
      arriba, y d = h - recubrimiento_inferior - db/2.
    - Cara superior traccionada (momento negativo): la comprimida es la de abajo, y
      d = h - recubrimiento_superior - db/2.

    La expresión resulta simétrica, pero el RECUBRIMIENTO que entra es el de la cara
    traccionada, que no es el mismo arriba que abajo. Confundirlos daría un peralte
    efectivo equivocado, que es el error que este módulo existe para impedir."""
    return h_m - cover_m - db_m / 2.0


# =========================================================================
# Acero mínimo cuando se arma en DOS CARAS — E.060 §10.5.4
# =========================================================================

# E.060 §10.5.4, verbatim:
#   "Para losas estructurales y zapatas de espesor uniforme, el acero mínimo en la
#    dirección de la luz debe ser el requerido por 9.7. Cuando el acero mínimo se
#    distribuya en las DOS CARAS de la losa, deberá cumplirse que la cuantía de
#    refuerzo en la CARA EN TRACCIÓN POR FLEXIÓN no sea menor de 0,0012. El
#    espaciamiento máximo del refuerzo no debe exceder tres veces el espesor ni de
#    400 mm."
#
# Es el anclaje normativo del acero de cara superior de la zapata combinada: la
# norma contempla explícitamente el mínimo repartido en dos caras.
RHO_MIN_TENSION_FACE_TWO_FACES = 0.0012
TWO_FACE_MIN_REFERENCE = "E.060 §10.5.4"


class TwoFaceMinimum(BaseModel):
    """Las dos exigencias de §10.5.4, resueltas por separado para poder decir cuál
    gobierna en vez de devolver un único número sin explicación."""

    As_min_total_m2: float = Field(..., description="rho de §9.7 sobre b*h: mínimo del CONJUNTO")
    As_min_tension_face_m2: float = Field(..., description="0,0012*b*h en la cara traccionada")
    rho_min_total: float
    rho_min_reference: str

    def for_face(self, is_tension_face: bool) -> tuple[float, str]:
        """Mínimo aplicable a UNA cara, con la disposición que lo gobierna.

        Una cara que no trabaja a tracción por flexión en ninguna sección no está
        cubierta por la exigencia de 0,0012 de §10.5.4; le sigue correspondiendo su
        parte del mínimo de §9.7, que este motor reparte por igual entre las dos
        caras. Ese reparto es un CRITERIO DE DISTRIBUCIÓN, no una prescripción:
        §10.5.4 fija el total y el mínimo de la cara traccionada, pero no dice cómo
        repartir el resto."""
        mitad = self.As_min_total_m2 / 2.0
        if is_tension_face:
            if self.As_min_tension_face_m2 >= mitad:
                return self.As_min_tension_face_m2, (
                    f"{TWO_FACE_MIN_REFERENCE}: rho >= 0,0012 en la cara traccionada"
                )
            return mitad, (
                f"{self.rho_min_reference}: mitad del mínimo del conjunto, que aquí supera "
                f"el 0,0012 de {TWO_FACE_MIN_REFERENCE}"
            )
        return mitad, (
            f"{self.rho_min_reference} repartido por igual entre las dos caras "
            f"(CRITERIO de distribución: §10.5.4 fija el total y el mínimo de la cara "
            f"traccionada, no cómo repartir el resto)"
        )


def two_face_minimum(
    width_m: float, h_m: float, rho_min_9_7: float, rho_min_reference: str
) -> TwoFaceMinimum:
    """Exigencias de acero mínimo de §10.5.4 para una sección armada en dos caras."""
    return TwoFaceMinimum(
        As_min_total_m2=rho_min_9_7 * width_m * h_m,
        As_min_tension_face_m2=RHO_MIN_TENSION_FACE_TWO_FACES * width_m * h_m,
        rho_min_total=rho_min_9_7,
        rho_min_reference=rho_min_reference,
    )


# E.060 §10.5.4 y §9.7.3 coinciden en el espaciamiento máximo: 3h y 400 mm.
def max_spacing_m(h_m: float) -> tuple[float, str]:
    return min(3.0 * h_m, 0.400), "E.060 §10.5.4 y §9.7.3: min(3h, 400 mm)"


# =========================================================================
# Selección de barras por cara y verificación de desarrollo
# =========================================================================


class FaceRebar(BaseModel):
    """Armado concreto de una cara: barras, separación y desarrollo verificado."""

    face: Face
    bar_designation: str
    diameter_mm: float
    spacing_m: float
    n_bars: int
    As_provided_m2: float
    As_required_m2: float

    spacing_limit_m: float
    spacing_reference: str
    spacing_ok: bool

    d_real_m: float = Field(
        ..., description="Peralte efectivo con el diámetro REALMENTE seleccionado"
    )

    ld_required_m: float = Field(..., description="Longitud de desarrollo exigida (Tabla 12.1)")
    ld_available_m: float = Field(
        ..., description="Longitud disponible desde la sección crítica hasta el extremo de la barra"
    )
    development_ok: bool
    development_note: str

    status: CheckStatus
    note: str


def select_face_rebar(
    face: Face,
    As_required_m2: float,
    width_m: float,
    h_m: float,
    cover_m: float,
    fy_MPa: float,
    fc_MPa: float,
    available_length_m: float,
) -> FaceRebar:
    """Selecciona el armado de una cara y verifica su separación máxima.

    El peralte efectivo se recalcula con el diámetro REAL seleccionado, no con el
    supuesto: es el mismo motivo por el que existe la iteración de punto fijo de
    `effective_depth.py`. Un d calculado con una barra supuesta menor que la real
    queda del lado inseguro."""
    seleccion = select_rebar(As_required_m2, width_m=width_m, h_m=h_m)
    db_m = seleccion.diameter_mm / 1000.0
    limite, ref = max_spacing_m(h_m)
    espaciamiento_ok = seleccion.spacing_m <= limite + 1e-9

    # --- Longitud de desarrollo, E.060 §15.6 -> Capítulo 12, Tabla 12.1 ---
    # psi_t depende del concreto fresco POR DEBAJO de la barra (§12.2.4, Tabla 12.2):
    # la cara inferior solo tiene su recubrimiento; la SUPERIOR tiene todo el peralte
    # de la zapata debajo, de modo que sí es "barra superior" y le corresponde
    # psi_t = 1,3. Aplicar 1,0 a la cara superior subestimaría la longitud exigida.
    concreto_debajo = cover_m if face == "inferior" else h_m - cover_m - db_m
    psi_t = psi_t_top_bar(concreto_debajo)
    ld = development_length_table_12_1(
        db_m=db_m, fy_MPa=fy_MPa, fc_MPa=fc_MPa, psi_t=psi_t, psi_e=1.0
    )
    desarrollo_ok = ld.ld_m <= available_length_m + 1e-9

    estado = seleccion.status
    if not espaciamiento_ok and estado is CheckStatus.PASS:
        estado = CheckStatus.FAIL
    if not desarrollo_ok and estado is CheckStatus.PASS:
        estado = CheckStatus.FAIL

    return FaceRebar(
        face=face,
        bar_designation=seleccion.bar_designation,
        diameter_mm=seleccion.diameter_mm,
        spacing_m=seleccion.spacing_m,
        n_bars=seleccion.n_bars,
        As_provided_m2=seleccion.As_provided_m2,
        As_required_m2=As_required_m2,
        spacing_limit_m=limite,
        spacing_reference=ref,
        spacing_ok=espaciamiento_ok,
        d_real_m=effective_depth_for_face(face, h_m, cover_m, db_m),
        ld_required_m=ld.ld_m,
        ld_available_m=available_length_m,
        development_ok=desarrollo_ok,
        development_note=(
            f"ld = {ld.ld_m * 100:.1f} cm exigida frente a {available_length_m * 100:.1f} cm "
            f"disponibles desde la sección crítica ({'CUMPLE' if desarrollo_ok else 'NO CUMPLE'}). "
            f"psi_t = {psi_t:.1f} con {concreto_debajo * 1000:.0f} mm de concreto por debajo de "
            f"la barra (E.060 §12.2.4, Tabla 12.2). {ld.equation_substituted}"
        ),
        status=estado,
        note=(
            f"{seleccion.note} Separación {seleccion.spacing_m * 100:.1f} cm frente al límite "
            f"de {limite * 100:.1f} cm ({ref})."
        ),
    )
