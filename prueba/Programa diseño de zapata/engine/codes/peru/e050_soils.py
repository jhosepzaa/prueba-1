"""Datos y fórmulas de E.050 (Perú).

`qadm` es un dato de entrada directo del usuario: el motor no lo calcula a partir
de parámetros geotécnicos, porque `CLAUDE.md` §1 prohíbe inventarlos. Los factores
de seguridad frente a falla por corte (Art. 21) quedan aquí documentados para una
fase posterior y NO se invocan.

Lo que sí se usa desde la Fase de área efectiva (2026-09-19) es
`effective_area_from_eccentricity`, el núcleo del método del art. 28, que
`engine/soil/contact_pressure.py::EffectiveAreaModel` llama directamente. Es la
ÚNICA implementación del método; el modelo de contacto no lo reescribe.

TEXTO NORMATIVO (verificado en el PDF de E.050, art. 28)
========================================================
  28.1. "En el caso de cimentaciones superficiales que transmiten al terreno una
        carga vertical Q y dos momentos Mx y My que actúan simultáneamente según
        los ejes x e y respectivamente, el sistema formado por estas tres
        solicitaciones es estáticamente equivalente a una carga vertical
        excéntrica de valor Q, ubicada en el punto (ex, ey) [...]"
  28.2. "El ancho (B) o largo (L), se corrige por excentricidad reduciéndolo en
        dos veces la excentricidad para ubicar la carga en el centro de gravedad
        del «área efectiva = B'L'»"
  28.3. "El centro de gravedad del «área efectiva» coincide con la posición de la
        carga excéntrica y sigue el contorno más próximo de la base real con la
        mayor precisión posible. Su forma es rectangular, aún en el caso de
        cimentaciones circulares."

La Figura 5 de la norma remite a NAVFAC DM 7: es el método del área efectiva de
Meyerhof.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field

CODE_NAME = "E.050"

# E.050 Art.21 -- factores de seguridad mínimos frente a falla por corte.
FS_CARGAS_ESTATICAS = 3.0
FS_SISMO_O_VIENTO = 2.5
FS_REFERENCE = "E.050 Art.21"


class EffectiveAreaResult(NamedTuple):
    B_eff_m: float
    L_eff_m: float
    ex_m: float
    ey_m: float
    code_reference: str


EFFECTIVE_AREA_REFERENCE = "E.050 art. 28.2-28.3"


def effective_area_from_eccentricity(
    B_m: float, L_m: float, ex_m: float, ey_m: float, strict: bool = True
) -> EffectiveAreaResult:
    """Núcleo del método del área efectiva (E.050 art. 28.2-28.3), a partir de la
    excentricidad ya reducida.

        B' = B - 2·|ex|          L' = L - 2·|ey|

    Convención de ejes, la del resto del motor (E.050 art. 28.1): B es la dimensión
    a lo largo de X y `ex` desplaza la resultante a lo largo de X. Por eso `ex`
    corrige B y `ey` corrige L.

    Se recibe la excentricidad y NO los momentos porque el motor ya la calcula en un
    solo sitio —`engine/soil/eccentricity.py::compute_total_eccentricity`, que además
    incluye el término P·offset de la columna descentrada—. Volver a derivarla aquí
    desde M/Q sería una segunda implementación de la misma reducción.

Con `strict` (por defecto) lanza ValueError si el área efectiva no es positiva: la
    resultante cae fuera de la huella y no existe equilibrio posible sobre esa base.
    Con `strict=False` devuelve igualmente las dimensiones, que serán nulas o
    negativas, para que el llamador pueda REPORTAR la condición en vez de reventar.
    En ninguno de los dos casos se inventa un área."""
    B_eff = B_m - 2.0 * abs(ex_m)
    L_eff = L_m - 2.0 * abs(ey_m)
    if strict and (B_eff <= 0 or L_eff <= 0):
        raise ValueError(
            f"Área efectiva no positiva (B'={B_eff:.3f} m, L'={L_eff:.3f} m): "
            "la excentricidad excede la mitad de la dimensión correspondiente."
        )
    return EffectiveAreaResult(
        B_eff_m=B_eff, L_eff_m=L_eff, ex_m=ex_m, ey_m=ey_m,
        code_reference=EFFECTIVE_AREA_REFERENCE,
    )


def effective_area_meyerhof(B_m: float, L_m: float, M1_kNm: float, M2_kNm: float, Q_kN: float) -> EffectiveAreaResult:
    """El mismo método a partir de los momentos: e1 = M1/Q corrige L, e2 = M2/Q corrige B.

    Es una envoltura de `effective_area_from_eccentricity`, no una segunda
    implementación. Se conserva porque es la forma en que el art. 28.1 plantea el
    problema —carga vertical y dos momentos— y sirve para contrastarlo a mano."""
    if Q_kN <= 0:
        raise ValueError("Q_kN debe ser positivo (carga de compresión) para el método de área efectiva.")
    return effective_area_from_eccentricity(B_m, L_m, ex_m=M2_kNm / Q_kN, ey_m=M1_kNm / Q_kN)


# =========================================================================
# E.050 art. 23.3 -- proporción en planta
# =========================================================================

# La tabla de formas del art. 23.3 asigna:
#
#     Cuadrada     L = B
#     Rectangular  L <= 10 B
#     Continua     L > 10 B
#     Combinada    L <= 10 B
#
# El 10 es el número del artículo. El «cinco (5)» que aparece cerca pertenece al
# art. 23.1 y es otra relación —profundidad sobre ancho, Df/B—, que no dice nada
# sobre la forma en planta.
MAX_L_OVER_B = 10.0

SHAPE_RATIO_REFERENCE = "E.050 art. 23.3 (tabla de formas: L <= 10 B)"

SHAPE_RATIO_READING = (
    "LECTURA ADOPTADA de E.050 art. 23.3: su tabla de formas no prohíbe nada, CLASIFICA. "
    "Por encima de L = 10·B el elemento deja de ser una zapata rectangular y pasa a ser "
    "una cimentación continua, que es otra tipología con sus propios requisitos y que "
    "este motor no modela. Por eso se trata como límite de alcance y no como una "
    "exigencia numérica de la norma."
)

SHAPE_RATIO_EXCEEDED_NOTE = (
    "Esta geometría queda por encima del límite: el resultado no sería el de una zapata."
)


class ShapeRatioResult(BaseModel):
    """Proporción en planta de una zapata, contra el límite del art. 23.3."""

    ratio: float = Field(..., description="lado mayor / lado menor")
    limit: float = Field(..., description="Límite adoptado")
    ok: bool
    long_side_m: float
    short_side_m: float
    equation_substituted: str
    code_reference: str = SHAPE_RATIO_REFERENCE


def check_shape_ratio(B_m: float, L_m: float, limit: float = MAX_L_OVER_B) -> ShapeRatioResult:
    """Proporción en planta, COMÚN A LAS TRES TIPOLOGÍAS (H6, 2026-09-20).

    El art. 23.3 habla de «Las zapatas y plateas», sin distinguir tipología. Hasta aquí
    solo la combinada lo verificaba, de modo que un usuario podía pedir `max_LB_ratio = 15`
    en la aislada y recibir un cimiento corrido presentado como zapata aislada. Es la misma
    pérdida de paridad que ya había costado la estabilidad de la combinada, el incremento
    del 30 % y el peralte mínimo de §15.7 (CLAUDE.md §13).

    Se mide `lado mayor / lado menor`, que es como el artículo expresa la proporción, sin
    importar cuál de los dos sea B."""
    mayor, menor = max(B_m, L_m), min(B_m, L_m)
    ratio = mayor / menor
    ok = ratio <= limit + 1e-9
    return ShapeRatioResult(
        ratio=ratio, limit=limit, ok=ok, long_side_m=mayor, short_side_m=menor,
        equation_substituted=(
            f"{mayor:.3f} / {menor:.3f} = {ratio:.3f} {'<=' if ok else '>'} {limit:.0f}"
        ),
    )


# =========================================================================
# E.050 art. 23.1 -- cimentación SUPERFICIAL
# =========================================================================

# Literal del artículo:
#
#   «23.1. Son aquellas en las cuales la relación Profundidad / ancho (Df/B) es menor o
#   igual a cinco (5), siendo Df la profundidad de la cimentación y B el ancho o diámetro
#   de la misma.»
#
# Es una DEFINICIÓN, no un requisito de resistencia: dice qué es una cimentación
# superficial. El art. 23.2 enumera las que lo son —zapatas aisladas, conectadas y
# combinadas, cimientos corridos y plateas—, que son exactamente las tipologías de este
# programa.
MAX_DF_OVER_B = 5.0

SHALLOW_FOUNDATION_REFERENCE = "E.050 art. 23.1 (cimentación superficial: Df/B <= 5)"

SHALLOW_FOUNDATION_READING = (
    "CONDICIÓN DE APLICABILIDAD del programa, decidida el 2026-09-20. E.050 art. 23.1 "
    "DEFINE la cimentación superficial por Df/B <= 5, y el art. 23.2 enumera como tales "
    "las tipologías que este motor resuelve. Por encima de esa relación el elemento es una "
    "cimentación PROFUNDA, gobernada por otros mecanismos —fricción lateral, capacidad de "
    "punta, asentamientos de otra naturaleza— que este motor no modela y cuyo capítulo no "
    "aplica. No es que la norma lo prohíba: es que el modelo deja de describir el problema."
)

SHALLOW_FOUNDATION_EXCEEDED_NOTE = (
    "Esta geometría queda fuera del alcance del programa: con Df/B > 5 el diseño tendría "
    "que hacerse como cimentación profunda."
)


class ShallowFoundationResult(BaseModel):
    """Relación profundidad / ancho, contra el límite del art. 23.1."""

    ratio: float = Field(..., description="Df / B, con B el ancho (lado MENOR)")
    limit: float = Field(..., description="Límite del art. 23.1")
    ok: bool
    Df_m: float
    width_m: float = Field(..., description="El lado MENOR en planta, que es el «ancho»")
    equation_substituted: str
    code_reference: str = SHALLOW_FOUNDATION_REFERENCE


def check_shallow_foundation(
    Df_m: float, B_m: float, L_m: float, limit: float = MAX_DF_OVER_B
) -> ShallowFoundationResult:
    """`Df/B <= 5`, COMÚN A LAS TRES TIPOLOGÍAS (H7, 2026-09-20).

    QUÉ ES «B». El artículo dice «el ancho o diámetro de la misma». En una zapata
    rectangular el ancho es el lado MENOR: tomar el mayor daría una relación más pequeña y
    dejaría pasar geometrías que el artículo excluye. Se elige el lado menor porque es la
    lectura estricta y porque es la dimensión que gobierna los mecanismos por los que la
    distinción existe —el bulbo de presiones y el confinamiento—.

    POR QUÉ FAIL Y NO NO VERIFICADO. Decisión del proyectista: el programa diseña
    cimentaciones superficiales, y admitir una entrada físicamente fuera del alcance del
    modelo —aunque se rotule NO VERIFICADO— deja abierta la puerta a que alguien la use.
    Es la misma lectura de alcance que la proporción del art. 23.3."""
    ancho = min(B_m, L_m)
    ratio = Df_m / ancho
    ok = ratio <= limit + 1e-9
    return ShallowFoundationResult(
        ratio=ratio, limit=limit, ok=ok, Df_m=Df_m, width_m=ancho,
        equation_substituted=(
            f"Df/B = {Df_m:.3f} / {ancho:.3f} = {ratio:.3f} {'<=' if ok else '>'} {limit:.0f}"
        ),
    )
