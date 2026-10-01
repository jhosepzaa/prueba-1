"""PUNZONAMIENTO (cortante en dos direcciones) -- E.060 §11.12.

AUDITORÍA COMPLETA DE LA IMPLEMENTACIÓN
=======================================
Cada elemento del cálculo, con su fundamento y su estado real:

1. UBICACIÓN DE LA SECCIÓN CRÍTICA -- a d/2 de las caras de la columna
   E.060 §11.12.1.2: la superficie crítica "estará localizada de modo que su
   perímetro, bo, sea mínimo, pero no necesita estar más cerca de d/2 desde
   (a) los bordes o las esquinas de las columnas...".
   §11.12.1.2 además permite: "Para columnas cuadradas o rectangulares [...] se
   permite utilizar secciones críticas equivalentes con cuatro lados rectos."
   IMPLEMENTADO: rectángulo de (bx + d) x (by + d), es decir d/2 hacia afuera de
   cada una de las cuatro caras.

2. PERÍMETRO CRÍTICO bo
   bo = 2*(bx + d) + 2*(by + d)
   IMPLEMENTADO en `critical_perimeter()`.

3. ÁREA ENCERRADA POR LA SECCIÓN CRÍTICA
   A_crit = (bx + d) * (by + d)
   IMPLEMENTADO en `critical_enclosed_area()`. Es el área cuya reacción del suelo
   NO produce cortante en la sección crítica (queda "dentro" del cono de falla).

4. EFECTO DE q (reacción del suelo) SOBRE Vu
   Vu = Pu_columna - qu * A_crit
   El término restado es la reacción del suelo bajo el área encerrada, que
   descarga la sección crítica.
   IMPLEMENTADO. Y es EXACTO -- no una aproximación -- para el caso del MVP
   (columna concéntrica), por lo siguiente:
       La presión factorizada varía linealmente:
           q(x,y) = q_avg * (1 + 12*ex*x/B^2 + 12*ey*y/L^2),  x,y desde el centro
       El área crítica es un rectángulo CENTRADO en ese mismo origen, luego
           ∫x dA = 0  y  ∫y dA = 0   sobre esa área
       de modo que  ∫q dA = q_avg * A_crit  exactamente, cualquiera sea la
       excentricidad. Usar la presión promedio NO introduce error en la
       RESULTANTE Vu.
   ADVERTENCIA: esto vale para la resultante. Lo que la excentricidad sí altera
   es la DISTRIBUCIÓN del esfuerzo cortante alrededor del perímetro, y eso es
   precisamente lo que cubre §11.12.7 -- ver punto 10.

5. Vc -- resistencia nominal del concreto
   E.060 §11.12.2.1: Vc es el MENOR entre las ecuaciones 11-41, 11-42 y 11-43.
   IMPLEMENTADO en E060ConcreteCode.punching_shear_vc(), que devuelve las tres
   evaluadas por separado más la gobernante (ver PunchingVcResult).

6. φVc -- resistencia de diseño
   φ = 0.85 para "cortante y torsión" (E.060 §9.3.2).
   IMPLEMENTADO. Criterio: PASS si Vu <= φVc (ec. 11-1: φVn >= Vu, con Vs = 0
   porque no se coloca refuerzo de cortante en zapatas en este MVP).

7. β (beta) -- relación de lados de la COLUMNA
   E.060 §11.12.2.1(a): "beta es la relación del lado largo al lado corto de la
   sección de la columna". β = max(bx,by)/min(bx,by) >= 1.
   IMPLEMENTADO. Nota: β solo puede hacer gobernar la ec. 11-41 si β > 2.

8. αs (alpha_s) -- posición de la columna
   E.060 §11.12.2.1(b): "alpha_s es 40 para columnas interiores, 30 para columnas
   de borde, y 20 para columnas en esquina".
   IMPLEMENTADO con αs = 40 y JUSTIFICACIÓN: en una zapata aislada con columna
   concéntrica, la zapata se extiende por los cuatro lados de la columna, de modo
   que la sección crítica se cierra completamente -- es el caso "interior". Los
   valores 30 y 20 corresponden a conexiones losa-columna donde la sección crítica
   queda truncada por un borde libre, situación que NO ocurre en el MVP (columna
   siempre centrada). El parámetro es configurable para zapatas excéntricas o de
   lindero en una fase posterior.

9. VALIDACIÓN GEOMÉTRICA -- la sección crítica debe caber en la zapata
   Si d/2 excede el voladizo, el perímetro crítico se saldría del concreto y el
   modelo de cono truncado cerrado deja de ser válido.
   IMPLEMENTADO como verificación explícita (devuelve FAIL con razón propia en vez
   de producir un número sin significado físico).

10. TRANSFERENCIA DE MOMENTO -- **IMPLEMENTADO (L1 cerrada)**
    E.060 §11.12.7 exige que, cuando se transmite un momento no balanceado Mu
    entre el elemento y la columna, la fracción γv*Mu (con γv = 1 - γf, ec. 11-45)
    se transfiera por EXCENTRICIDAD DEL CORTANTE, generando un esfuerzo cortante
    que "varía linealmente alrededor del centroide de las secciones críticas"
    (§11.12.7.2), y que el máximo combinado por Vu y Mu no exceda φvn = φVc/(bo*d)
    (ec. 11-46).
    IMPLEMENTADO en engine/foundation/punching_moment_transfer.py:
      - γf por E.060 ec. 13-1: γf = 1/(1 + (2/3)*sqrt(b1/b2)); γv = 1 - γf
      - Jc del perímetro crítico (derivación geométrica, ver JC_REFERENCE)
      - esfuerzo combinado vu = Vu/(bo*d) + γvx*Mux*cx/Jcx + γvy*Muy*cy/Jcy
      - criterio vu <= φ*Vc/(bo*d)
    Cuando hay momento no balanceado, **este criterio SUSTITUYE** al de la
    resultante sola: no se usa la aproximación de presión uniforme.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from engine.codes.base import IConcreteCode
from engine.foundation.punching_moment_transfer import (
    MomentTransferResult,
    check_punching_with_moment_transfer,
)
from engine.foundation.critical_section import (
    ALPHA_S_CLASSIFICATION_NOTE,
    CriticalSection,
    build_critical_section,
)
from engine.results.status import CheckStatus

# E.060 §11.12.2.1(b). Ver punto 8 de la auditoría para la justificación de 40.
ALPHA_S_INTERIOR = 40.0
ALPHA_S_EDGE = 30.0
ALPHA_S_CORNER = 20.0

# Correspondencia entre la clasificación geométrica de la sección crítica y el
# alpha_s de §11.12.2.1(b). Los VALORES son normativos; la clasificación que los
# selecciona es la interpretación declarada en ALPHA_S_CLASSIFICATION_NOTE.
ALPHA_S_BY_POSITION = {
    "interior": ALPHA_S_INTERIOR,
    "borde": ALPHA_S_EDGE,
    "esquina": ALPHA_S_CORNER,
}

# L1 CERRADA: §11.12.7 implementado en engine/foundation/punching_moment_transfer.py
MOMENT_TRANSFER_IMPLEMENTED_NOTE = "Punzonamiento con transferencia de momento: IMPLEMENTADO (E.060 §11.12.7)"


class PunchingFailureCause(str, Enum):
    """Por qué FALLA el punzonamiento — Fase 5B, defecto D2.

    Se fija en `check_punching_shear`, en la MISMA rama que decide el estado. Antes de
    5B la causa se infería después, en `depth_solver`, a partir de
    `critical_section_fits`, que significa «la sección crítica se cierra por los cuatro
    lados» y es `False` en TODA columna de borde o esquina. Una zapata de lindero que
    fallaba por §11.12.7 —sección de 3 lados perfectamente formada, α_s = 30— se
    reportaba como «la sección crítica no cabe».

    Son las únicas tres ramas de fallo del motor: el punzonamiento no emite WARNING ni
    NO VERIFICADO."""

    SECCION_CRITICA_DEGENERADA = "SECCION_CRITICA_DEGENERADA"
    """La sección crítica queda recortada por 3 o 4 lados (o su perímetro es nulo). Es
    la única causa GEOMÉTRICA: E.060 §11.12.2.1(b) no tiene categoría ni α_s para ese
    caso y el motor no verifica nada. Una sección de borde (1 lado recortado) o de
    esquina (2) NO es esto: es una sección utilizable."""

    CAPACIDAD_CORTANTE_DIRECTO = "CAPACIDAD_CORTANTE_DIRECTO"
    """Sección utilizable, sin momento no balanceado, y Vu > φVc."""

    CAPACIDAD_TRANSFERENCIA_MOMENTO = "CAPACIDAD_TRANSFERENCIA_MOMENTO"
    """Sección utilizable, con momento no balanceado, y el esfuerzo combinado de
    E.060 §11.12.7 supera φvn (vu,máx > φvn)."""


# Textos de `discard_reasons`. SON LAS CATEGORÍAS GLOBALES DE DESCARTE: el informe y la
# API agrupan las alternativas descartadas por el texto EXACTO. Por eso son constantes,
# sin valores numéricos —un mensaje con MPa crearía una categoría por alternativa— y
# conservan literalmente los textos anteriores a la Fase 5B. Lo que cambia es CUÁNDO se
# emite cada uno, no el conjunto ni su redacción.
PUNCHING_DISCARD_DEGENERATE = (
    "Sección crítica de punzonamiento no cabe en la zapata (d/2 excede el voladizo disponible)."
)
PUNCHING_DISCARD_CAPACITY = "Punzonamiento no cumple."

PUNCHING_FAILURE_DESCRIPTIONS: dict[PunchingFailureCause, str] = {
    PunchingFailureCause.SECCION_CRITICA_DEGENERADA: (
        "sección crítica degenerada: recortada por 3 o 4 lados, sin categoría en "
        "E.060 §11.12.2.1(b); no hay verificación posible"
    ),
    PunchingFailureCause.CAPACIDAD_CORTANTE_DIRECTO: (
        "capacidad insuficiente por cortante directo: Vu > φVc"
    ),
    PunchingFailureCause.CAPACIDAD_TRANSFERENCIA_MOMENTO: (
        "capacidad insuficiente con transferencia de momento (E.060 §11.12.7): "
        "vu,máx > φvn"
    ),
}


class PunchingShearResult(BaseModel):
    # --- Geometría de la sección crítica ---
    bo_m: float = Field(..., description="Perímetro crítico a d/2 de las caras de columna")
    critical_area_m2: float = Field(..., description="Área encerrada por la sección crítica")
    critical_offset_m: float = Field(..., description="d/2 -- distancia desde la cara de columna")
    critical_section_fits: bool = Field(..., description="¿La sección crítica se cierra por los cuatro lados?")
    column_position: str = Field(
        default="interior",
        description='Clasificación geométrica: "interior", "borde", "esquina" o "degenerada"',
    )
    critical_section_sides: int = Field(
        default=4, description="Número de caras de la sección crítica que transmiten cortante"
    )

    # --- Demanda ---
    Vu_kN: float
    qu_avg_kPa: float = Field(..., description="Presión factorizada promedio bajo la zapata")
    soil_relief_kN: float = Field(..., description="qu * A_crit -- reacción que descarga la sección crítica")

    # --- Resistencia (las tres ecuaciones, no solo la gobernante) ---
    #
    # OJO CON EL NOMBRE DE ESTOS TRES CAMPOS: dicen 11-33/34/35, que era la numeración de
    # una edición anterior de E.060. En la edición designada por el usuario
    # (`docs/normativa/fuentes/`), las tres ecuaciones de §11.12.2.1 son **11-41, 11-42 y
    # 11-43**, y así es como se citan en `governing_equation`, en la traza, en la memoria
    # y en `engine/codes/peru/e060_concrete.py`. Lo que se calcula es correcto; lo que
    # está anticuado es el nombre del campo.
    #
    # No se renombra porque estas claves están en los contratos congelados
    # (`tests/freeze/baseline.json` y `baseline_connected.json`, 53 apariciones) y
    # cambiarlas obligaría a regenerar baselines por un motivo cosmético, que es
    # exactamente lo que CLAUDE.md §11 no permite hacer a la ligera. Anotado como
    # pendiente en `docs/estado_proyecto.md`.
    Vc_kN: float
    Vc_eq_11_33_kN: float  # ec. 11-41 — término de β (forma de la columna)
    Vc_eq_11_34_kN: float  # ec. 11-42 — término de α_s (posición de la columna)
    Vc_eq_11_35_kN: float  # ec. 11-43 — techo constante
    governing_equation: str
    beta_col: float
    alpha_s: float
    phi: float
    phi_Vc_kN: float

    ratio: float
    status: CheckStatus

    # --- Alcance real de la verificación ---
    moment_transfer_implemented: bool = Field(
        default=True, description="§11.12.7 implementado (L1 cerrada)"
    )
    moment_transfer: MomentTransferResult | None = Field(
        default=None, description="Detalle de §11.12.7 cuando hay momento no balanceado"
    )
    unbalanced_moment_present: bool = Field(
        ..., description="¿La combinación gobernante transmite momento a la columna?"
    )
    completeness_note: str

    equation_substituted: str
    code_reference: str

    failure_cause: PunchingFailureCause | None = Field(
        default=None,
        description=(
            "Causa del FAIL, fijada en la misma rama que el estado. None si no falla. "
            "Es lo que decide el mensaje de descarte; `critical_section_fits` no."
        ),
    )

    @property
    def critical_section_usable(self) -> bool:
        """¿Existe una sección crítica sobre la que se pueda verificar?

        NO es `critical_section_fits`. Una sección de borde (3 lados) o de esquina (2)
        no se cierra por los cuatro lados y sin embargo es perfectamente utilizable:
        tiene su perímetro, su α_s y su Jc. Solo la sección degenerada no lo es."""
        return self.column_position != "degenerada" and self.bo_m > 0.0

    @model_validator(mode="after")
    def _causa_coherente_con_estado(self) -> "PunchingShearResult":
        falla = self.status is CheckStatus.FAIL
        if falla and self.failure_cause is None:
            raise ValueError(
                "Un punzonamiento en FAIL debe declarar su `failure_cause`: sin ella, el "
                "mensaje de descarte tendría que volver a inferirse de la geometría."
            )
        if not falla and self.failure_cause is not None:
            raise ValueError(
                f"`failure_cause` = {self.failure_cause.value} con estado "
                f"{self.status.value}: solo un FAIL tiene causa de fallo."
            )
        return self


def punching_discard_reason(result: PunchingShearResult) -> str:
    """Motivo de descarte de un punzonamiento en FAIL, decidido por su causa explícita.

    Devuelve uno de los DOS textos existentes, literalmente, de modo que las categorías
    de descarte y su número no cambian: la sección degenerada conserva «no cabe» y los
    dos fallos de capacidad —cortante directo y §11.12.7— comparten «no cumple». Los
    valores que explican el fallo viajan en la traza, no en el texto que agrupa."""
    if result.failure_cause is None:
        raise ValueError("El punzonamiento no está en FAIL: no tiene motivo de descarte.")
    if result.failure_cause is PunchingFailureCause.SECCION_CRITICA_DEGENERADA:
        return PUNCHING_DISCARD_DEGENERATE
    return PUNCHING_DISCARD_CAPACITY


def critical_perimeter(bx_m: float, by_m: float, d_m: float) -> float:
    """bo = 2*(bx+d) + 2*(by+d). Sección crítica a d/2 de cada cara (E.060 §11.12.1.2)."""
    return 2.0 * (bx_m + d_m) + 2.0 * (by_m + d_m)


def critical_enclosed_area(bx_m: float, by_m: float, d_m: float) -> float:
    """A_crit = (bx+d)*(by+d). Área cuya reacción del suelo no carga la sección crítica."""
    return (bx_m + d_m) * (by_m + d_m)


def critical_section_fits_in_footing(
    B_m: float, L_m: float, bx_m: float, by_m: float, d_m: float,
    offset_x_m: float = 0.0, offset_y_m: float = 0.0,
) -> bool:
    """La sección crítica se extiende d/2 más allá de cada cara de la columna;
    debe quedar dentro de la planta de la zapata para que el modelo de cono
    truncado CERRADO tenga sentido físico.

    Con la columna descentrada (Fase 1B) la condición deja de ser simétrica: hay
    que comprobar las cuatro holguras por separado, no solo que la suma quepa. Con
    offset = 0 la expresión se reduce a la anterior."""
    cx, cy = B_m / 2.0 + offset_x_m, L_m / 2.0 + offset_y_m
    holguras = (
        cx - bx_m / 2.0,          # borde x = 0
        B_m - cx - bx_m / 2.0,    # borde x = B
        cy - by_m / 2.0,          # borde y = 0
        L_m - cy - by_m / 2.0,    # borde y = L
    )
    return min(holguras) >= d_m / 2.0 - 1e-12


def punching_demand(
    P_u_column_kN: float, B_m: float, L_m: float, bx_m: float, by_m: float, d_m: float,
    offset_x_m: float = 0.0, offset_y_m: float = 0.0,
    ex_m: float = 0.0, ey_m: float = 0.0,
    section: "CriticalSection | None" = None,
    field_P_u_kN: float | None = None,
) -> float:
    """Vu = Pu - (reacción del suelo encerrada por la sección crítica).

    COLUMNA CONCÉNTRICA
    ===================
    Basta la presión media: el área crítica está centrada en el mismo origen que la
    distribución lineal, luego integral(x dA) = 0 y la media da la resultante EXACTA.
    Ver punto 4 de la auditoría en el encabezado del módulo.

    COLUMNA DESCENTRADA (Fase 1B)
    =============================
    Ese argumento se cae: el área crítica ya no está centrada en el origen de la
    distribución, y hay que integrar de verdad.

    CÓMO SE INTEGRA (2026-09-20)
    ============================
    Por CUADRATURA del campo real de presión de diseño sobre el rectángulo encerrado:

        Vu = Pu − ∫∫(A_crit) q(x, y) dA

    `q(x, y)` lo da `engine/foundation/unilateral_contact.py`, el MISMO campo con que se
    calculan la flexión y el cortante. No hay una segunda representación del contacto de
    diseño, y no hay simplificación del alivio: la integral se recorta contra la zona
    comprimida y es exacta sobre el campo.

    QUÉ SUSTITUYE. Hasta aquí se usaba la forma cerrada del campo LINEAL,

        ∫ q dA = q_avg · A_crit · (1 + 12·ex·ax/B² + 12·ey·ay/L²)

    —la presión en el centroide del área encerrada por su área—, que es exacta mientras
    la distribución sea lineal, es decir **solo dentro del núcleo central**. Fuera de él
    el campo lineal no existe: parte de la huella no apoya. Se midió el error y era del
    lado INSEGURO —el alivio lineal salía mayor que el real y Vu quedaba subestimado hasta
    un 1,4 %—, de modo que no bastaba con declararlo.

    Dentro del núcleo la integral reproduce la forma cerrada, porque el campo se reduce
    término a término al lineal: ninguna geometría sin despegue cambia de resultado. Está
    comprobado caso a caso en `tests/test_punzonamiento_campo_real.py`.

    EL CAMPO ES EL UNILATERAL, Y ES COMÚN (decisión del proyectista, 2026-09-20)
    ===========================================================================
    `engine/foundation/unilateral_contact.py` resuelve `q⁺ = max(a + b·u + c·v, 0)` por
    equilibrio —`∫q⁺ = Pu`, `∫x·q⁺ = Pu·ex`, `∫y·q⁺ = Pu·ey`— y es el MISMO campo con que
    se calculan la flexión y el cortante unidireccional. Sustituye a la superposición de
    los dos campos 1-D, que con excentricidad biaxial no resolvía el contacto sino que lo
    describía: su parte positiva entregaba 1,61·Pu en el régimen de
    `17_columna_de_esquina`, y daba aquí un alivio de 397,5 kN donde el exacto es 836,5.

    La integral sobre el rectángulo encerrado es EXACTA: se recorta contra la zona
    comprimida y se evalúan los momentos del polígono en forma cerrada.

    DOS CARGAS DISTINTAS: `P_u_column_kN` Y `field_P_u_kN`
    =====================================================
    `P_u_column_kN` es la carga que PUNZONA, la de la columna que se está verificando.
    `field_P_u_kN` es la que produce el CAMPO de presiones bajo la zapata, junto con
    `ex_m` y `ey_m`.

    En la zapata aislada son la misma y `field_P_u_kN` se omite. En la COMBINADA no: el
    campo lo produce la resultante de TODAS las columnas. Pasar la carga de una sola con
    su excentricidad respecto del centroide describe una zapata que no existe, y estaba
    midiendo mal el alivio —en K1, dos columnas iguales y simétricas sin momento, el campo
    real es uniforme y el alivio vale 129,60 kN; con la carga de una sola columna salían
    174,14 kN, es decir un Vu SUBESTIMADO—.
    """
    from engine.foundation.unilateral_contact import (
        ContactFieldImpossible,
        solve_unilateral_contact,
    )

    P_field = P_u_column_kN if field_P_u_kN is None else field_P_u_kN
    # El rectángulo ENCERRADO por la sección crítica. Con sección cerrada es el de la
    # columna más d/2 a cada lado; con sección TRUNCADA, el recorte contra el borde de la
    # zapata lo desplaza y lo acorta, y la integral tiene que hacerse sobre el recortado.
    if section is None:
        semi_x = (bx_m + d_m) / 2.0
        semi_y = (by_m + d_m) / 2.0
        x_lo, x_hi = offset_x_m - semi_x, offset_x_m + semi_x
        y_lo, y_hi = offset_y_m - semi_y, offset_y_m + semi_y
    else:
        x_lo, x_hi = section.x_lo_m, section.x_hi_m
        y_lo, y_hi = section.y_lo_m, section.y_hi_m

    try:
        campo = solve_unilateral_contact(P_field, B_m, L_m, ex_m, ey_m)
    except ContactFieldImpossible:
        # La resultante de diseño cae fuera de la huella: no hay campo que integrar. Se
        # devuelve la carga entera, sin alivio, que es el mismo criterio con que
        # `NetPressureField` trata `e >= dim/2`. La geometría ya está descartada por la
        # presión de contacto; lo que no puede pasar es que el punzonamiento reviente.
        return P_u_column_kN
    alivio = campo.force_over_rectangle(x_lo, x_hi, y_lo, y_hi)
    return max(P_u_column_kN - max(alivio, 0.0), 0.0)


def _degenerate_result(
    section: CriticalSection, B_m: float, L_m: float, bx_m: float, by_m: float,
    d_m: float, P_u_column_kN: float, phi: float, beta_col: float,
    field_P_u_kN: float | None = None,
) -> PunchingShearResult:
    """Sección crítica recortada por TRES O CUATRO lados.

    E.060 §11.12.2.1(b) solo da alpha_s para columna interior, de borde y de esquina
    —0, 1 o 2 lados recortados—. Con 3 o 4 no hay categoría normativa, y asignarle un
    valor sería inventar normativa. Geométricamente corresponde a una zapata apenas
    mayor que la columna, que ningún modelo de punzonamiento describe.

    Se devuelve FAIL con el motivo, no un número: un resultado numérico aquí
    aparentaría una verificación que no se ha hecho."""
    return PunchingShearResult(
        bo_m=section.bo_m,
        critical_area_m2=section.enclosed_area_m2,
        critical_offset_m=d_m / 2.0,
        critical_section_fits=False,
        column_position=section.position,
        critical_section_sides=len(section.faces),
        Vu_kN=P_u_column_kN,
        # Diagnóstico, no cálculo: la presión media bajo la ZAPATA, que en la combinada
        # la produce la resultante de todas las columnas y no la que se está verificando.
        qu_avg_kPa=(P_u_column_kN if field_P_u_kN is None else field_P_u_kN) / (B_m * L_m),
        soil_relief_kN=0.0,
        Vc_kN=0.0, Vc_eq_11_33_kN=0.0, Vc_eq_11_34_kN=0.0, Vc_eq_11_35_kN=0.0,
        governing_equation="no aplicable",
        beta_col=beta_col, alpha_s=0.0, phi=phi, phi_Vc_kN=0.0,
        ratio=float("inf"),
        moment_transfer_implemented=True,
        unbalanced_moment_present=False,
        completeness_note=(
            f"GEOMETRÍA FUERA DE ALCANCE: la sección crítica queda recortada por "
            f"{section.n_truncated_sides} de sus 4 lados. E.060 §11.12.2.1(b) solo clasifica "
            f"columnas interiores (0 lados recortados), de borde (1) y de esquina (2); para "
            f"3 o 4 no prescribe alpha_s y este motor NO le inventa uno. En la práctica "
            f"significa que la zapata ({B_m:.3f} x {L_m:.3f} m) es apenas mayor que la columna "
            f"({bx_m:.3f} x {by_m:.3f} m) frente al peralte efectivo d = {d_m:.3f} m. "
            f"Aumente la zapata o reduzca el peralte."
        ),
        status=CheckStatus.FAIL,
        failure_cause=PunchingFailureCause.SECCION_CRITICA_DEGENERADA,
        equation_substituted=section.geometry_note,
        code_reference="E.060 §11.12.1.2 y §11.12.2.1(b) (sin categoría aplicable)",
    )


def check_punching_shear(
    P_u_column_kN: float,
    B_m: float,
    L_m: float,
    bx_m: float,
    by_m: float,
    d_m: float,
    fc_MPa: float,
    code: IConcreteCode,
    Mux_kNm: float = 0.0,
    Muy_kNm: float = 0.0,
    alpha_s: float | None = None,
    offset_x_m: float = 0.0,
    offset_y_m: float = 0.0,
    ex_m: float = 0.0,
    ey_m: float = 0.0,
    field_P_u_kN: float | None = None,
) -> PunchingShearResult:
    """`field_P_u_kN` es la carga que produce el CAMPO de presiones bajo la zapata, que
    en la combinada NO es la de la columna que punzona: ver `punching_demand`. Omitirlo
    equivale a declarar que son la misma, que es el caso de la zapata aislada."""
    phi = code.phi_factors().cortante
    section = build_critical_section(B_m, L_m, bx_m, by_m, d_m, offset_x_m, offset_y_m)
    bo = section.bo_m
    area_crit = section.enclosed_area_m2
    fits = section.is_closed
    beta_col = max(bx_m, by_m) / min(bx_m, by_m)

    # alpha_s por CLASIFICACIÓN GEOMÉTRICA (interpretación declarada; ver
    # ALPHA_S_CLASSIFICATION_NOTE). Un alpha_s pasado explícitamente por el llamador
    # manda sobre la clasificación automática.
    if section.position == "degenerada" or section.bo_m <= 0.0:
        return _degenerate_result(
            section, B_m, L_m, bx_m, by_m, d_m, P_u_column_kN, phi, beta_col,
            field_P_u_kN=field_P_u_kN,
        )
    alpha_s_geom = ALPHA_S_BY_POSITION[section.position]
    # `alpha_s=None` -- el caso normal -- deja que lo decida la geometría; un valor
    # explícito lo declara el llamador y manda sobre la clasificación automática.
    alpha_s_used = alpha_s_geom if alpha_s is None else alpha_s

    vc = code.punching_shear_vc(fc_MPa, bo, d_m, beta_col, alpha_s_used)
    phi_vc_kN = phi * vc.vc_kN

    qu_avg = (P_u_column_kN if field_P_u_kN is None else field_P_u_kN) / (B_m * L_m)
    vu = punching_demand(
        P_u_column_kN, B_m, L_m, bx_m, by_m, d_m,
        offset_x_m=offset_x_m, offset_y_m=offset_y_m, ex_m=ex_m, ey_m=ey_m,
        section=section, field_P_u_kN=field_P_u_kN,
    )
    soil_relief = P_u_column_kN - vu
    ratio = vu / phi_vc_kN if phi_vc_kN > 0 else float("inf")

    has_moment = abs(Mux_kNm) > 1e-9 or abs(Muy_kNm) > 1e-9

    # L1 IMPLEMENTADO: si hay momento no balanceado, la verificación gobernante
    # es la de §11.12.7 (esfuerzo combinado), no la de la resultante sola.
    # Ya no se exige `fits`: con la Fase 1C la sección truncada tiene su propio Jc y
    # sus propias distancias al centroide, de modo que §11.12.7 se aplica igual.
    moment_transfer: MomentTransferResult | None = None
    if has_moment:
        moment_transfer = check_punching_with_moment_transfer(
            Vu_kN=vu, Mux_kNm=Mux_kNm, Muy_kNm=Muy_kNm,
            bx_m=bx_m, by_m=by_m, d_m=d_m, Vc_kN=vc.vc_kN, phi=phi,
            section=section,
        )

    # Orden de precedencia de estados:
    #  1) geometría inválida -> FAIL (el resultado numérico no significaría nada)
    #  2) con momento: gobierna §11.12.7 (esfuerzo combinado)
    #  3) sin momento: basta la resultante
    # La sección truncada YA NO es motivo de fallo: desde la Fase 1C tiene su propio
    # perímetro, su alpha_s, su centroide y su Jc. Lo único que se declara es CÓMO se
    # clasificó, porque de esa clasificación depende alpha_s y es una interpretación.
    truncada = not section.is_closed
    # La causa del fallo se fija AQUÍ, en la misma rama que el estado (Fase 5B, D2). La
    # sección truncada de borde o esquina no aparece en ninguna: no es causa de fallo.
    causa: PunchingFailureCause | None = None
    if moment_transfer is not None:
        status = moment_transfer.status
        if status is CheckStatus.FAIL:
            causa = PunchingFailureCause.CAPACIDAD_TRANSFERENCIA_MOMENTO
        completeness = (
            f"Verificación COMPLETA incluyendo transferencia de momento (E.060 §11.12.7). "
            f"{moment_transfer.message}"
        )
    elif vu > phi_vc_kN:
        status = CheckStatus.FAIL
        causa = PunchingFailureCause.CAPACIDAD_CORTANTE_DIRECTO
        completeness = f"Vu={vu:.2f} kN excede phi*Vc={phi_vc_kN:.2f} kN."
    else:
        status = CheckStatus.PASS
        completeness = (
            "Verificación completa: la combinación gobernante no transmite momento a la columna, "
            "por lo que §11.12.7 no es aplicable."
        )

    if truncada:
        completeness = (
            f"{completeness} SECCIÓN CRÍTICA TRUNCADA: {section.geometry_note} "
            f"alpha_s = {alpha_s_used:.0f} por clasificación «{section.position}». "
            f"{ALPHA_S_CLASSIFICATION_NOTE}"
        )

    return PunchingShearResult(
        bo_m=bo,
        column_position=section.position,
        critical_section_sides=len(section.faces),
        critical_area_m2=area_crit,
        critical_offset_m=d_m / 2.0,
        critical_section_fits=fits,
        Vu_kN=vu,
        qu_avg_kPa=qu_avg,
        soil_relief_kN=soil_relief,
        Vc_kN=vc.vc_kN,
        Vc_eq_11_33_kN=vc.vc_a_kN,
        Vc_eq_11_34_kN=vc.vc_b_kN,
        Vc_eq_11_35_kN=vc.vc_c_kN,
        governing_equation=vc.governing_equation,
        beta_col=beta_col,
        alpha_s=alpha_s_used,
        phi=phi,
        phi_Vc_kN=phi_vc_kN,
        ratio=ratio,
        status=status,
        failure_cause=causa,
        unbalanced_moment_present=has_moment,
        moment_transfer=moment_transfer,
        completeness_note=completeness,
        equation_substituted=(
            f"Sección crítica a d/2={d_m / 2:.3f} m de las caras: ({bx_m + d_m:.3f} x {by_m + d_m:.3f}) m, "
            f"bo={bo:.3f} m, A_crit={area_crit:.4f} m2 | "
            f"qu_avg={qu_avg:.2f} kPa, alivio del suelo={soil_relief:.2f} kN | "
            f"Vu={P_u_column_kN:.2f}-{soil_relief:.2f}={vu:.2f} kN | "
            f"beta={beta_col:.2f}, alpha_s={alpha_s_used:.0f} | {vc.equation_substituted} | "
            f"phi*Vc={phi}*{vc.vc_kN:.2f}={phi_vc_kN:.2f} kN | ratio={ratio:.3f}"
            # El desarrollo completo de §11.12.7 (γf, γv, Jc, esfuerzo combinado) debe
            # quedar en el trace, no solo su conclusión: es lo que hace auditable la
            # verificación de transferencia de momento.
            + (f" || §11.12.7: {moment_transfer.equation_substituted}" if moment_transfer else "")
            + f" | {completeness}"
        ),
        code_reference=(
            f"{vc.code_reference}; sección crítica §11.12.1.2; phi §9.3.2"
            + ("; transferencia de momento §11.12.7 (ec. 11-45, 11-46, 13-1)" if moment_transfer else "")
        ),
    )
