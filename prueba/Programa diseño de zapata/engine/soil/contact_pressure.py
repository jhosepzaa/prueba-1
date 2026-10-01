"""Modelos de presión de contacto suelo-zapata, intercambiables (punto 2 de la
corrección de Fase 2: FullContact / KernCheck / EffectiveArea sin modificar el
resto del motor al agregar un modelo nuevo).

DOS MODELOS DE DISEÑO, Y CUÁL RIGE
==================================
`KernCheckModel` es el modelo POR DEFECTO y el único que usan hoy la API y todos
los casos congelados. `EffectiveAreaModel` se elige explícitamente: es una opción
del proyectista, no un cambio de comportamiento. `FullContactModel` es la pieza
interna que aplica la fórmula lineal y no decide si es válida; no debe usarse sola
para dar por bueno un diseño.

KernCheck — E.060 §15.2.3
-------------------------
  "En el cálculo de las presiones de contacto entre las zapatas y el suelo solo se
   aceptará que ocurran compresiones sobre el suelo."

La condición de núcleo central de una sección rectangular B x L es la condición
clásica de mecánica de materiales para que la distribución lineal
q = P/A ± M·c/I no genere tracciones. No es un artículo numerado aparte: se deriva
de esa prohibición. Fuera del núcleo, KernCheck no resuelve el despegue parcial y
lo dice (`within_kern = False`).

EffectiveArea — E.050 art. 28.2-28.3
------------------------------------
Sí resuelve la excentricidad alta, y con el método que la norma prescribe:
B' = B − 2|ex|, L' = L − 2|ey|, con la carga centrada sobre esa área reducida y
una presión uniforme q = Q/(B'·L'). El texto literal está transcrito en
`engine/codes/peru/e050_soils.py`, que es la única implementación del cálculo.

CRITERIO ADOPTADO: EXTIENDE AL DEL NÚCLEO, NO LO SUSTITUYE
==========================================================
El art. 28 NO releva de §15.2.3. Los dos criterios conviven, y el modelo aplica el
que corresponde a cada caso:

  - **resultante DENTRO del núcleo**: la distribución lineal es válida y su PICO es
    la presión de contacto real. Rige ese pico, exactamente igual que en KernCheck;
  - **resultante FUERA del núcleo**: la lineal deja de valer —habría tracciones— y
    rige E.050 art. 28 con su presión uniforme sobre el área efectiva.

Por qué así y no tomando siempre el art. 28: la presión uniforme sobre B'×L' es
MENOR que el pico de la distribución lineal (con excentricidad en un solo eje, 3/4
de él). Aplicarla dentro del núcleo relajaría casos que hoy se verifican con el pico,
y elegir un modelo no puede convertir un FAIL en un PASS. Con este criterio, escoger
`EffectiveArea` solo puede AÑADIR geometrías que el núcleo descartaba; ninguna de las
que ya pasaban cambia de resultado.

POR QUÉ ESTE MODELO NO PUEDE AFIRMAR CUMPLIMIENTO
=================================================
`qadm` es un DATO que declara el proyectista y que el Estudio de Mecánica de Suelos
obtiene para la zapata real, B x L. El art. 28 evalúa la capacidad sobre B' x L', y
la capacidad portante de una zapata más estrecha NO es la misma:

  - en suelo granular el término 0,5·γ·B'·Nγ baja con B', de modo que el qadm real
    del área efectiva sería MENOR que el declarado -> comparar contra el declarado
    sería OPTIMISTA;
  - en suelo cohesivo (φ = 0) la capacidad no depende de B, y si gobierna el
    asentamiento, un área menor asienta menos y el qadm sería MAYOR.

El motor no sabe cuál de los dos casos es el suyo, y `CLAUDE.md` §1 le prohíbe
suponer parámetros geotécnicos para averiguarlo. Se aplica entonces la MISMA regla
asimétrica que ya rige en la estabilidad con E.020 art. 20.1, donde la fuerza
estabilizante también se calcula con una cota superior:

  - si q > qadm declarado, el incumplimiento es VÁLIDO: con el qadm correcto del
    área efectiva incumpliría al menos tanto;
  - si q <= qadm declarado, el cumplimiento NO puede afirmarse y queda
    NO VERIFICADO.

Es la lectura conservadora, y es la que el proyecto adopta
(`docs/area_efectiva_e050_art28.md`). El proyectista la cierra declarando que su
qadm vale para las dimensiones efectivas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from engine.codes.peru.e050_soils import (
    EFFECTIVE_AREA_REFERENCE,
    effective_area_from_eccentricity,
)


EFFECTIVE_AREA_CANNOT_AFFIRM_NOTE = (
    "E.050 art. 28 evalúa la presión sobre el ÁREA EFECTIVA B'×L', pero el qadm declarado "
    "corresponde a la zapata real B×L: el Estudio de Mecánica de Suelos lo obtiene para esas "
    "dimensiones. La capacidad portante de una zapata más estrecha no es la misma —en suelo "
    "granular baja con B, y si gobierna el asentamiento sube—, y el motor no puede saber cuál "
    "es el caso sin parámetros geotécnicos que no tiene. Un INCUMPLIMIENTO calculado así es "
    "válido; un cumplimiento NO puede afirmarse y queda NO VERIFICADO. Lo cierra el proyectista "
    "declarando un qadm válido para las dimensiones efectivas."
)


class ContactPressureResult(BaseModel):
    qmax_kPa: float
    qmin_kPa: float
    qavg_kPa: float
    within_kern: bool
    model_name: str
    code_reference: str
    equation_substituted: str
    # E.050 art. 28.2-28.3. Solo las llena `EffectiveAreaModel`; en los demás modelos
    # valen None y no añaden ninguna clave al congelamiento
    # (`OPTIONAL_WHEN_NONE_FIELDS` de tests/freeze/snapshot.py).
    B_eff_m: float | None = Field(
        default=None, description="Ancho efectivo B' = B − 2|ex| (E.050 art. 28.2)"
    )
    L_eff_m: float | None = Field(
        default=None, description="Largo efectivo L' = L − 2|ey| (E.050 art. 28.2)"
    )
    qadm_declared_for_effective_area: bool | None = Field(
        default=None,
        description=(
            "Solo con área efectiva: si el proyectista declaró que su qadm vale para las "
            "dimensiones efectivas B'×L'. Sin esa declaración, un cumplimiento no puede "
            "afirmarse (ver la cabecera del módulo)."
        ),
    )

    @property
    def uses_effective_area(self) -> bool:
        return self.B_eff_m is not None

    @property
    def effective_area_governs(self) -> bool:
        """¿Gobierna el art. 28, o sigue rigiendo el pico de la distribución lineal?

        Solo gobierna fuera del núcleo central. Dentro, el modelo de área efectiva
        devuelve el mismo pico que KernCheck y no hay nada que matizar."""
        return self.uses_effective_area and not self.within_kern

    @property
    def compliance_can_be_affirmed(self) -> bool:
        """¿Puede este modelo afirmar que el diseño CUMPLE, o solo que no incumple?

        Es una propiedad derivada, no un campo: la responde el modelo por su
        construcción. Ver la regla asimétrica en la cabecera del módulo."""
        if not self.effective_area_governs:
            return True
        return bool(self.qadm_declared_for_effective_area)

    @property
    def usable(self) -> bool:
        """¿Sirve este campo de presiones para juzgar el diseño?

        Es la pregunta que hacen los solvers, y NO es la misma que `within_kern`:
        KernCheck solo es válido dentro del núcleo, mientras que EffectiveArea lo es
        mientras el área efectiva sea positiva —es decir, mientras la resultante caiga
        dentro de la huella—. `within_kern` conserva su significado geométrico literal
        en los dos modelos."""
        if not self.uses_effective_area:
            return self.within_kern
        return self.B_eff_m > 0.0 and self.L_eff_m > 0.0


def contact_pressure_equation_symbolic(result: "ContactPressureResult") -> str:
    """Ecuación simbólica de la entrada de traza, según el modelo que la produjo."""
    if result.effective_area_governs:
        return "q = Q/(B'·L') con B' = B − 2|ex| y L' = L − 2|ey|   (E.050 art. 28.2-28.3)"
    return "q = P/A · (1 ± 6ex/B ± 6ey/L), válido solo si la resultante cae en el núcleo central"


def contact_pressure_not_usable_reason(result: "ContactPressureResult") -> str:
    """Motivo de descarte cuando el campo de presiones no sirve para juzgar el diseño.

    Es una CATEGORÍA DE TEXTO GLOBAL (`CLAUDE.md` §5): la API y los informes agrupan los
    motivos por texto exacto, de modo que hay una redacción por causa y no una por caso."""
    if not result.uses_effective_area:
        return (
            "Excentricidad fuera del núcleo central: el modelo KernCheck (E.060 §15.2.3, solo "
            "compresiones) no es válido para esta combinación. El método del área efectiva de "
            "E.050 art. 28 sí la resuelve: puede elegirse el modelo EffectiveArea."
        )
    return (
        "Resultante fuera de la huella de la zapata: el área efectiva de E.050 art. 28 no es "
        "positiva (B' o L' menor o igual que cero), de modo que no existe equilibrio posible "
        "sobre esta base. Ningún modelo de presión de contacto la resuelve."
    )


class ContactPressureModel(ABC):
    name: ClassVar[str]

    @abstractmethod
    def compute(self, B_m: float, L_m: float, P_kN: float, ex_m: float, ey_m: float) -> ContactPressureResult: ...


class FullContactModel(ContactPressureModel):
    """Fórmula lineal q = P/A * (1 ± 6ex/B ± 6ey/L), sin verificar si hay
    tracciones. Es una pieza interna (mecánica de materiales estándar, no una
    cita normativa numerada) usada por KernCheckModel -- no debe usarse sola
    para dar por válido un diseño, porque no aplica la prohibición de tracciones
    del §15.2.

    Convención de ejes (igual que engine/soil/eccentricity.py): B es la
    dimensión de la zapata a lo largo de X, L a lo largo de Y. ex desplaza la
    resultante a lo largo de X -> se compara contra B; ey a lo largo de Y ->
    se compara contra L."""

    name: ClassVar[str] = "FullContact"

    def compute(self, B_m: float, L_m: float, P_kN: float, ex_m: float, ey_m: float) -> ContactPressureResult:
        A = B_m * L_m
        q_avg = P_kN / A
        term_x = 6.0 * ex_m / B_m
        term_y = 6.0 * ey_m / L_m
        q_max = q_avg * (1.0 + abs(term_x) + abs(term_y))
        q_min = q_avg * (1.0 - abs(term_x) - abs(term_y))
        kern_ratio = abs(ex_m) / (B_m / 6.0) + abs(ey_m) / (L_m / 6.0) if L_m > 0 and B_m > 0 else float("inf")
        # Tolerancia numérica: un punto exactamente en el borde del núcleo (kern_ratio==1)
        # no debe clasificarse como "fuera" por errores de redondeo de punto flotante.
        KERN_TOLERANCE = 1e-9
        return ContactPressureResult(
            qmax_kPa=q_max,
            qmin_kPa=q_min,
            qavg_kPa=q_avg,
            within_kern=kern_ratio <= 1.0 + KERN_TOLERANCE,
            model_name=self.name,
            code_reference=(
                "Mecánica de materiales estándar (no es un artículo numerado); "
                "prohibición de tracciones: E.060 §15.2.3"
            ),
            equation_substituted=(
                f"q_avg=P/A={P_kN:.1f}/{A:.3f}={q_avg:.2f} kPa | "
                f"q=q_avg*(1 ± 6ex/B ± 6ey/L) = {q_avg:.2f}*(1 ± {term_x:.4f} ± {term_y:.4f}) "
                f"-> qmax={q_max:.2f} kPa, qmin={q_min:.2f} kPa"
            ),
        )


class KernCheckModel(ContactPressureModel):
    """Modelo POR DEFECTO: aplica FullContactModel y exige que la resultante caiga
    dentro del núcleo central (solo compresiones, E.060 §15.2.3).

    Si cae fuera, este modelo no resuelve el despegue parcial —para eso está
    `EffectiveAreaModel`, que el proyectista elige— y reporta `within_kern = False`
    para que la alternativa se descarte con esa razón explícita. Es la posición
    conservadora: descarta geometrías que E.050 art. 28 admitiría, nunca al revés."""

    name: ClassVar[str] = "KernCheck"

    def __init__(self) -> None:
        self._full_contact = FullContactModel()

    def compute(self, B_m: float, L_m: float, P_kN: float, ex_m: float, ey_m: float) -> ContactPressureResult:
        result = self._full_contact.compute(B_m, L_m, P_kN, ex_m, ey_m)
        return result.model_copy(update={"model_name": self.name})


class EffectiveAreaModel(ContactPressureModel):
    """Método del área efectiva de E.050 art. 28.2-28.3 (2026-09-19).

    QUÉ CALCULA
    ===========
        B' = B − 2|ex|        L' = L − 2|ey|        q = Q / (B'·L')

    `q` es la «presión uniforme aplicada» que define el art. 28.3, y es la que se
    compara contra la presión admisible. Se devuelve en `qmax_kPa` —que es lo que los
    solvers contrastan contra qadm— y también en `qmin_kPa`, porque bajo este modelo
    el campo ES uniforme sobre el área reducida: fuera de ella la zapata no apoya.
    `qavg_kPa` conserva su significado de siempre, Q/(B·L) sobre la huella REAL, para
    que las dos lecturas puedan compararse.

    QUÉ NO CALCULA
    ==============
    No es la distribución real de contacto. El pico real de un bloque triangular con
    despegue es mayor que esta presión uniforme —4/3 en el caso de excentricidad en un
    solo eje—. El art. 28 plantea el área efectiva para la CAPACIDAD PORTANTE, y eso
    es lo que este modelo resuelve. Los esfuerzos de diseño de la zapata (flexión,
    cortante, punzonamiento) los sigue calculando el solver con su propio campo de
    presiones; este modelo no los toca.

    `within_kern` conserva su significado literal: dice si la resultante cae dentro
    del núcleo, que con este modelo ya no es condición de validez pero sigue siendo el
    dato que distingue un caso con despegue de uno sin él.

    CUÁNDO NO SIRVE
    ===============
    Si |ex| >= B/2 o |ey| >= L/2 el área efectiva no es positiva: la resultante cae
    FUERA de la huella y no hay equilibrio posible sobre esa base. El modelo devuelve
    igualmente las dimensiones calculadas —negativas o nulas— y `usable` vale False,
    para que el solver descarte con un motivo exacto en lugar de reventar.

    LA DECLARACIÓN DEL PROYECTISTA
    ==============================
    `qadm_declared_for_effective_area` es el dato con que el proyectista cierra la
    asimetría explicada en la cabecera del módulo: afirma que su qadm vale para las
    dimensiones efectivas. Por defecto es False —no declarado—, que es la lectura
    conservadora. El motor nunca lo supone."""

    name: ClassVar[str] = "EffectiveArea"

    def __init__(self, qadm_declared_for_effective_area: bool = False) -> None:
        self.qadm_declared_for_effective_area = qadm_declared_for_effective_area
        self._full_contact = FullContactModel()

    def compute(self, B_m: float, L_m: float, P_kN: float, ex_m: float, ey_m: float) -> ContactPressureResult:
        # El núcleo del método vive en engine/codes/peru/e050_soils.py y es el único
        # sitio donde se escribe B − 2|e|. Aquí no se reimplementa.
        area = effective_area_from_eccentricity(B_m, L_m, ex_m, ey_m, strict=False)
        lineal = self._full_contact.compute(B_m, L_m, P_kN, ex_m, ey_m)
        q_avg_real = P_kN / (B_m * L_m)
        area_positiva = area.B_eff_m > 0.0 and area.L_eff_m > 0.0
        # El art. 28 solo entra donde la distribución lineal deja de valer. Dentro del
        # núcleo rige su pico, que es más estricto: ver el criterio adoptado en la
        # cabecera del módulo.
        gobierna_area = area_positiva and not lineal.within_kern
        q_area = P_kN / (area.B_eff_m * area.L_eff_m) if area_positiva else q_avg_real

        if lineal.within_kern:
            q_max, q_min = lineal.qmax_kPa, lineal.qmin_kPa
            sustituida = (
                f"Resultante DENTRO del núcleo central: rige la distribución lineal y su pico, "
                f"que es el criterio más estricto. {lineal.equation_substituted} | "
                f"A título informativo, E.050 art. 28 daría B'={area.B_eff_m:.4f} m, "
                f"L'={area.L_eff_m:.4f} m y q={q_area:.2f} kPa"
            )
        elif area_positiva:
            q_max = q_min = q_area
            sustituida = (
                f"Resultante FUERA del núcleo central: la distribución lineal produciría "
                f"tracciones y no es válida (E.060 §15.2.3). Rige E.050 art. 28. | "
                f"B' = B − 2|ex| = {B_m:.3f} − 2·{abs(ex_m):.4f} = {area.B_eff_m:.4f} m | "
                f"L' = L − 2|ey| = {L_m:.3f} − 2·{abs(ey_m):.4f} = {area.L_eff_m:.4f} m | "
                f"q = Q/(B'·L') = {P_kN:.1f}/({area.B_eff_m:.4f}·{area.L_eff_m:.4f}) = "
                f"{q_area:.2f} kPa (presión uniforme del art. 28.3) | Q/(B·L) = "
                f"{q_avg_real:.2f} kPa sobre la huella real"
            )
        else:
            q_max, q_min = q_avg_real, lineal.qmin_kPa
            sustituida = (
                f"B' = {area.B_eff_m:.4f} m, L' = {area.L_eff_m:.4f} m: área efectiva NO "
                f"POSITIVA con ex={ex_m:+.4f} m y ey={ey_m:+.4f} m sobre {B_m:.3f}×{L_m:.3f} m. "
                f"La resultante cae fuera de la huella y no hay equilibrio posible sobre esta "
                f"base: E.050 art. 28 tampoco es aplicable."
            )

        return ContactPressureResult(
            qmax_kPa=q_max,
            qmin_kPa=q_min,
            qavg_kPa=q_avg_real,
            within_kern=lineal.within_kern,
            model_name=self.name,
            code_reference=EFFECTIVE_AREA_REFERENCE,
            equation_substituted=sustituida,
            B_eff_m=area.B_eff_m,
            L_eff_m=area.L_eff_m,
            qadm_declared_for_effective_area=self.qadm_declared_for_effective_area,
        )
