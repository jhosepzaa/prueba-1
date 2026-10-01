"""Profundidad mínima de cimentación -- E.050 art. 26.2.

TEXTO NORMATIVO (verificado en el PDF de E.050, art. 26.2)
=========================================================
"La profundidad de cimentación es definida por el PR y está condicionada por la
 estratigrafía del suelo, a cambios de volumen por humedecimiento-secado,
 hielo-deshielo o condiciones particulares de uso de la estructura, **no siendo
 menor de 0,80 metros en cualquier tipo de cimentación de elementos portantes o
 no portantes no arriostrados lateralmente**. En el caso de cimentación sobre
 roca, el PR define la profundidad de cimentación, pudiendo en este caso ser
 menor a 0,80 metros."

ALCANCE DE LA VERIFICACIÓN
==========================
La zapata de una columna es cimentación de un elemento portante, de modo que el
mínimo le aplica. La única excepción del artículo es la cimentación sobre roca,
y esa condición **la declara el usuario** (`SoilProfile.founded_on_rock`): el
motor no la deduce de ningún otro dato.

Este es un requisito sobre un DATO DE ENTRADA, no sobre una geometría calculada.
Ninguna combinación de B, L o h puede corregirlo: si Df es insuficiente, todas
las alternativas resultan igualmente inadmisibles y el motivo es el mismo. Por
eso se evalúa una vez por candidato y produce FAIL, no advertencia -- es una
exigencia numérica explícita de la norma, no una interpretación.

Lo que este módulo NO verifica: las demás condiciones que el art. 26.2 pone en
manos del PR (estratigrafía, cambios de volumen, condiciones de uso). Son juicio
profesional sobre datos que el motor no posee.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.results.status import CheckStatus

# E.050 art. 26.2. Valor normativo literal, no una heurística.
MIN_FOUNDATION_DEPTH_M = 0.80

CODE_REFERENCE = "E.050 art. 26.2"

# Lo que el artículo pone en manos del PR y el motor NO comprueba. Vivía solo en el
# docstring de este módulo, que el usuario del programa no lee: la auditoría de trazas
# (2026-09-19) lo encontró como la entrada más repetida sin ninguna hipótesis declarada.
# Un «Df = 1,50 ≥ 0,80 → PASS» a secas se lee como «la profundidad está verificada», y no
# lo está: solo lo está el mínimo numérico.
SCOPE_NOTES: tuple[str, ...] = (
    "E.050 art. 26.2 condiciona además la profundidad a la estratigrafía del suelo, a los "
    "cambios de volumen por humedecimiento-secado o hielo-deshielo y a las condiciones "
    "particulares de uso. Eso es juicio del profesional responsable sobre datos que el motor "
    "no posee: aquí solo se comprueba el mínimo numérico de 0,80 m.",
    "Df es un DATO DE ENTRADA: ninguna combinación de B, L o h puede corregirlo.",
)


class FoundationDepthResult(BaseModel):
    Df_m: float
    Df_min_required_m: float | None
    founded_on_rock: bool
    status: CheckStatus
    message: str
    equation_substituted: str
    code_reference: str

    @property
    def hypotheses(self) -> list[str]:
        """Lo que hay que declarar en la traza. Una sola fuente para las tres tipologías:
        antes cada solver armaba su lista y las tres omitían el alcance del artículo."""
        rock = (
            ["Cimentación sobre roca declarada por el usuario (E.050 art. 26.2, única excepción)."]
            if self.founded_on_rock
            else []
        )
        return rock + list(SCOPE_NOTES)


def check_foundation_depth(Df_m: float, founded_on_rock: bool) -> FoundationDepthResult:
    if founded_on_rock:
        return FoundationDepthResult(
            Df_m=Df_m,
            Df_min_required_m=None,
            founded_on_rock=True,
            status=CheckStatus.INFO,
            message=(
                f"Profundidad de cimentación no sujeta al mínimo de {MIN_FOUNDATION_DEPTH_M:.2f} m: "
                "se ha declarado cimentación sobre roca, único caso en que E.050 art. 26.2 permite "
                "un valor menor, quedando la profundidad a criterio del profesional responsable."
            ),
            equation_substituted=(
                f"Df = {Df_m:.3f} m | cimentación sobre roca declarada -> "
                "mínimo de 0,80 m no aplicable (E.050 art. 26.2)"
            ),
            code_reference=CODE_REFERENCE,
        )

    cumple = Df_m >= MIN_FOUNDATION_DEPTH_M - 1e-9
    return FoundationDepthResult(
        Df_m=Df_m,
        Df_min_required_m=MIN_FOUNDATION_DEPTH_M,
        founded_on_rock=False,
        status=CheckStatus.PASS if cumple else CheckStatus.FAIL,
        message=(
            f"Profundidad de cimentación Df = {Df_m:.3f} m >= {MIN_FOUNDATION_DEPTH_M:.2f} m."
            if cumple
            else (
                f"PROFUNDIDAD DE CIMENTACIÓN INSUFICIENTE: Df = {Df_m:.3f} m es menor que el "
                f"mínimo de {MIN_FOUNDATION_DEPTH_M:.2f} m que exige E.050 art. 26.2. Ninguna "
                "geometría de zapata corrige esto: hay que aumentar Df. Si la cimentación se "
                "apoya sobre roca, declárelo (founded_on_rock) -- es la única excepción del "
                "artículo."
            )
        ),
        equation_substituted=(
            f"Df = {Df_m:.3f} m {'>=' if cumple else '<'} Df_min = {MIN_FOUNDATION_DEPTH_M:.2f} m"
        ),
        code_reference=CODE_REFERENCE,
    )
