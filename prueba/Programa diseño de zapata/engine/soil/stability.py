"""L3 — ESTABILIDAD: DESLIZAMIENTO Y VOLCAMIENTO.

ESTADO NORMATIVO — FASE 10B (docs/normativa/transcripcion_cargas.md §4)
=====================================================================
E.020 cap. 6 (Estabilidad), fuente designada del proyecto:
  - Art. 20.1 — «La estabilidad requerida será suministrada SÓLO POR LAS CARGAS MUERTAS
               más la acción de los anclajes permanentes que se provean.»
  - Art. 20.2 — El peso de la tierra sobre las zapatas puede considerarse carga muerta.
  - Art. 21   — Volteo: coeficiente de seguridad mínimo 1,5 («la edificación o cualquiera
               de sus partes»).
  - Art. 22.1 — Deslizamiento: coeficiente de seguridad mínimo 1,25.
  - Art. 22.2 — Los coeficientes de fricción los establece el proyectista.
E.030 art. 64.2 — Volteo sísmico: FS >= 1,2 con las fuerzas SIN la reducción del art. 29.

CRITERIO ADOPTADO (D10-2b, decisión del proyecto — NO es exigencia textual de la norma):
  - FS de volteo: 1,50 en TODA combinación, incluida la sísmica.
  - FS de deslizamiento: 1,50.
  - Un FS declarado por el proyectista sustituye siempre al adoptado.
  - μ: SIEMPRE del proyectista (E.020 art. 22.2). Sin μ -> NO VERIFICADO.

  Qué dicen las fuentes y qué adopta el programa:

  | Verificación            | Valor en la fuente                | Valor adoptado | Relación      |
  |-------------------------|-----------------------------------|----------------|---------------|
  | Volteo, sin sismo       | 1,50 (E.020 art. 21)              | 1,50           | coincide      |
  | Volteo, con sismo       | 1,20 (E.030 art. 64.2)            | 1,50           | MÁS ESTRICTO  |
  | Deslizamiento           | 1,25 (E.020 art. 22.1)            | 1,50           | MÁS ESTRICTO  |

  Donde el criterio adoptado difiere de la fuente, la traza lo dice con esas palabras: el
  programa exige más de lo que la norma pide, y eso no convierte 1,50 en el valor
  normativo. Detalle en docs/d10_2b_fs_volteo_sismico.md.

E.050 art. 39.13.6 (1,50 / 1,25) sigue citándose solo como referencia de MUROS.

FUERZA ESTABILIZANTE (E.020 art. 20.1)
======================================
  Modo por casos (composición conocida):
      N = P_CM + Σ min(P_otros, 0) + peso propio (zapata y relleno, E.020 art. 20.2)
  Las cargas no muertas NO estabilizan; si restan carga vertical, sí desestabilizan.

  Modo de combinaciones directas (composición desconocida):
      se calcula con N = P + peso propio, que es COTA SUPERIOR de la N anterior.
      - Si aun así NO cumple, el FAIL es válido: con la N correcta cumpliría menos.
      - Si cumple, NO puede afirmarse: queda NO VERIFICADO (E.020 art. 20.1).

CARGAS UTILIZADAS
=================
Combinaciones de SERVICIO (sin amplificar), coherente con E.050 art. 17.1
("Para el cálculo del factor de seguridad de cimentaciones: se utilizan como
cargas aplicadas a la cimentación, las Cargas de Servicio").

VOLCAMIENTO — DOCUMENTACIÓN DEL MODELO
======================================
- PUNTO DE GIRO ADOPTADO: la arista inferior de la zapata del lado hacia el que
  actúa la resultante horizontal (borde de la base, no el centro). Para el eje X
  es la arista situada a B/2 del centro; para Y, a L/2.
- MOMENTOS ESTABILIZADORES: el peso total vertical de servicio (carga axial de
  columna + peso propio de la zapata + peso del relleno de suelo sobre ella)
  actuando con brazo B/2 (o L/2) respecto a esa arista.
      M_estab = N_total · B/2
- MOMENTOS VOLCADORES: el momento aplicado en la base más el momento que produce
  la fuerza horizontal por su brazo respecto al nivel de la base.
      M_volc = max(|M_total|, |M_estabilizante|) + |H| · h
  con
      M_total         = M + P·offset
      M_estabilizante = Σ_estab (M_k + P_k·offset)   (mismo conjunto que N, art. 20.1)

  EL TÉRMINO `P·offset` (FORMULACION_VOLTEO, aprobada 2026-09-19)
  --------------------------------------------------------------
  Es ESTÁTICA, no una hipótesis nueva. Tomando momentos en la arista, el brazo real
  de la carga de columna es dim/2 − offset, de modo que

      M_estab_real = (P + W)·dim/2 − P·offset

  y pasar ese término al miembro volcador da |M + P·offset|. Con `offset = 0` se
  reduce a |M|, que es la formulación anterior.

  Omitirlo hacía la zapata aislada INCOHERENTE CONSIGO MISMA: la presión de contacto
  ya usaba ex = (M + P·offset)/(P + W) (`engine/soil/eccentricity.py`) mientras el
  volcamiento usaba |M|. El error iba en las dos direcciones —inseguro en la zapata
  de lindero sin momento, falsamente conservador en la zapata exterior de la
  conectada, donde el reparto centra la resultante—. Diagnóstico y ejemplos
  numéricos en `docs/formulacion_volteo_analisis.md`; impacto sobre los casos
  congelados en `docs/freeze_formulacion_volteo.md`.

  A QUÉ MIEMBRO VA EL TÉRMINO — CONVENCIÓN ADOPTADA, NO IDENTIDAD ALGEBRAICA
  -------------------------------------------------------------------------
  `P·offset` se lleva al miembro VOLCADOR y el estabilizador se mantiene en `N·dim/2`.
  NO es lo mismo que acortar el brazo de la carga:

      adoptada:       FS = N·(dim/2) / (|M + P·offset| + |H|·h)
      brazo acortado: FS = (N·dim/2 − P·offset) / (|M| + |H|·h)

  Un cociente no es invariante al pasar un término de un miembro al otro, y las dos
  escrituras dan números distintos. Se adopta la primera por tres razones:

    1. es la MÁS ESTRICTA siempre que la otra dé FS > 1, que es el caso normal;
    2. es la única coherente con la presión de contacto, que reduce la MISMA resultante
       con `ex = (M + P·offset)/(P + W)`;
    3. con `H = 0` da `FS = dim/(2·e)`, de donde sale la relación «resultante en el
       núcleo central ⇒ FS ≥ 3» que el alcance de la combinada invoca.

  Es una HIPÓTESIS DE MODELACIÓN declarada, no una exigencia normativa: ninguna fuente
  del proyecto prescribe cómo plantear el volcamiento de una zapata. Comprobado con
  números en `tests/test_formulacion_volteo.py`.

  LA ENVOLVENTE es en cambio un CRITERIO DEL PROGRAMA (opción B, pendiente 7): ver
  `ENVELOPE_NOTE`. No es exigencia normativa.

  Las tres tipologías comparten esta formulación desde FORMULACION_VOLTEO: el
  ayudante es `axis_moments_kNm`, y `engine/foundation/combined_stability.py` lo
  llama por cada columna antes de sumar la resultante.
  BRAZO ADOPTADO: se toma `h` (peralte de la zapata), es decir, se supone que la
  fuerza horizontal se transmite en la BASE DE LA COLUMNA (cara superior de la
  zapata) y actúa con ese brazo hasta la base de la cimentación. Es un supuesto
  explícito: si el usuario define H en otro nivel, el brazo cambia.
- CRITERIO: FS_volcamiento = M_estab / M_volc >= FS_requerido (declarado por el usuario).
- El empuje pasivo del suelo NO se considera (del lado conservador).

DESLIZAMIENTO
=============
- Resultante horizontal: H = sqrt(Hx² + Hy²)
- Fuerza normal: N = carga axial de servicio + peso propio + relleno
- Resistencia por fricción: F = μ · N
- Cohesión: se suma c·A SOLO si el usuario proporciona la cohesión. No se asume.
- Empuje pasivo: NO considerado (conservador).
- FS_deslizamiento = F / H >= FS_requerido (declarado por el usuario).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet, LoadCombination
from engine.domain.soil import SoilProfile
from engine.results.status import CheckStatus

# Valores de E.050 art. 39.13.6, aplicables a MUROS DE CONTENCIÓN.
# Se exponen SOLO como referencia documentada para que el ingeniero decida si los
# adopta; el motor NUNCA los aplica por su cuenta.
FS_REFERENCE_RETAINING_WALL_STATIC = 1.50
FS_REFERENCE_RETAINING_WALL_PSEUDOSTATIC = 1.25
FS_REFERENCE_NOTE = (
    "E.050 art. 39.13.6 prescribe FS 1,50 (estático) y 1,25 (pseudo-dinámico) por volteo y "
    "deslizamiento PARA MUROS DE CONTENCIÓN. E.050 no prescribe un FS equivalente para zapatas "
    "aisladas; adoptarlo es decisión del ingeniero proyectista."
)

# --- Volcamiento sísmico: E.030 art. 64 -------------------------------------------
# Art. 64.1: "Toda estructura y su cimentación deben diseñarse para resistir el momento
# de volteo que produce un sismo".
# Art. 64.2: "El factor de seguridad calculado con las fuerzas que se obtienen en el
# análisis estructural, SIN considerar la reducción establecida en el artículo 29,
# debe ser mayor o igual que 1,2".
E030_FS_OVERTURNING_SEISMIC = 1.20  # valor de la NORMA; el programa adopta 1,50 (D10-2b)

E030_OVERTURNING_INTERPRETATION = (
    "E.030 art. 64 habla de «toda estructura y su cimentación». Aplicarlo al volcamiento "
    "de una zapata aislada respecto de su propia arista es una INTERPRETACIÓN razonada, "
    "no una lectura literal: la norma no distingue el nivel al que se comprueba. Se "
    "declara aquí igual que la interpretación de §15.7. El proyectista puede sustituirla "
    "declarando FS_overturning_required."
)

E030_UNREDUCED_NOTE = (
    "Art. 64.2 exige calcular el FS sin la reducción del art. 29 (factor 0,8). El motor "
    "nunca aplica esa reducción a las cargas —queda registrada como no implementada y del "
    "lado conservador—, de modo que las combinaciones de servicio empleadas aquí ya están "
    "sin reducir."
)


# --- E.020 cap. 6 (Fase 10B) ---------------------------------------------------------
E020_FS_OVERTURNING = 1.50  # E.020 art. 21
E020_FS_SLIDING = 1.25  # E.020 art. 22.1; valor de la NORMA, el programa adopta 1,50 (D10-2b)


# --- D10-2b: factores de seguridad ADOPTADOS por el proyecto --------------------------
# Decisión del usuario (2026-09-18). No son los valores de la norma en dos de los tres
# casos: son un criterio de diseño del programa, más estricto. Se nombran así para que
# nadie los confunda con una cita normativa.
PROGRAM_FS_OVERTURNING = 1.50
PROGRAM_FS_OVERTURNING_SEISMIC = 1.50
PROGRAM_FS_SLIDING = 1.50

D10_2B_ADOPTED_NOTE = (
    "CRITERIO DE DISEÑO ADOPTADO POR EL PROYECTO (D10-2b), no exigencia textual de la norma: "
    "el programa exige FS >= 1,50 al volteo —incluido el volteo con acción sísmica— y FS >= 1,50 "
    "al deslizamiento. Valores identificados en las fuentes: E.020 art. 21 pide 1,50 al volteo "
    "(coincide); E.030 art. 64.2 pide 1,20 al volteo sísmico y E.020 art. 22.1 pide 1,25 al "
    "deslizamiento (en ambos el criterio adoptado es MÁS ESTRICTO que la norma). Un FS declarado "
    "por el proyectista sustituye siempre al adoptado."
)

# Etiquetas de procedencia del FS. La cadena viaja a la traza, de modo que al leerla se
# distingue un valor normativo de uno adoptado.
FS_SOURCE_DECLARED = "declarado por el proyectista"
FS_SOURCE_PROGRAM_OVERTURNING = (
    "criterio del programa D10-2b: 1,50 (coincide con E.020 art. 21)"
)
FS_SOURCE_PROGRAM_OVERTURNING_SEISMIC = (
    "criterio del programa D10-2b: 1,50, MÁS ESTRICTO que E.030 art. 64.2, que exige 1,20"
)
FS_SOURCE_PROGRAM_SLIDING = (
    "criterio del programa D10-2b: 1,50, MÁS ESTRICTO que E.020 art. 22.1, que exige 1,25"
)

E020_DEAD_LOAD_ONLY_NOTE = (
    "E.020 art. 20.1: la estabilidad la suministran SOLO las cargas muertas. Con combinaciones "
    "directas no se conoce qué parte de P es carga muerta; el FS se calculó con la carga total "
    "de servicio, que es una cota superior de la estabilizante. Un FAIL así calculado es válido; "
    "un cumplimiento no puede afirmarse y queda NO VERIFICADO. Use el modo de cargas por casos."
)


def _fs_overturning_required(
    combo: LoadCombination, declared: float | None
) -> tuple[float | None, str]:
    """FS exigido a ESTA combinación, con la procedencia del criterio.

    Prioridad: lo declarado por el proyectista manda siempre. En su ausencia rige el
    criterio adoptado en D10-2b —1,50 con y sin sismo—, que en el caso sísmico es más
    estricto que E.030 art. 64.2. La cadena devuelta lo dice; no se presenta 1,50 como
    exigencia textual de la norma."""
    if declared is not None:
        return declared, FS_SOURCE_DECLARED
    if combo.includes_seismic_loads:
        return PROGRAM_FS_OVERTURNING_SEISMIC, FS_SOURCE_PROGRAM_OVERTURNING_SEISMIC
    return PROGRAM_FS_OVERTURNING, FS_SOURCE_PROGRAM_OVERTURNING


def _fs_sliding_required(declared: float | None) -> tuple[float, str]:
    if declared is not None:
        return declared, FS_SOURCE_DECLARED
    return PROGRAM_FS_SLIDING, FS_SOURCE_PROGRAM_SLIDING


ECCENTRICITY_TERM_NOTE = (
    "El momento volcador incluye el término P·offset de la columna descentrada "
    "(FORMULACION_VOLTEO): es el mismo término que la presión de contacto ya usaba en "
    "ex = (M + P·offset)/(P + W), de modo que las dos verificaciones reducen la resultante "
    "igual. CONVENCIÓN ADOPTADA: el término se lleva al miembro volcador y el estabilizador "
    "se mantiene en N·dim/2; no equivale a acortar el brazo de la carga —un cociente no es "
    "invariante al cambiar un término de miembro— y es la escritura más estricta de las dos. "
    "Es una hipótesis de modelación declarada, no una exigencia normativa. Con la columna "
    "centrada el término es nulo y la formulación se reduce a |M|."
)

ENVELOPE_NOTE = (
    "CRITERIO DEL PROGRAMA (pendiente 7, opción B): el momento volcador se toma como la "
    "ENVOLVENTE de dos lecturas —con la carga total y con solo la parte estabilizante "
    "(E.020 art. 20.1)—, porque la excentricidad de una carga no muerta puede reducir el "
    "momento total y enmascarar el volcamiento. No es una exigencia normativa: E.020 "
    "art. 20.1 dice qué estabiliza, no cómo tratar la excentricidad de lo demás."
)


MOMENT_NOISE_REL_TOL = 1e-9
"""Tolerancia RELATIVA con la que un momento cancelado se declara nulo.

`M + P·offset` es una DIFERENCIA de dos magnitudes grandes. Cuando la columna descentrada
está equilibrada —la zapata exterior de la conectada, cuya carga corregida trae
M = −P·offset— el resultado exacto es cero, pero en coma flotante queda un residuo del
orden de 1e-13 kN·m. Sin tolerancia ese residuo convierte «no hay volcamiento» en un
FS de 1e16, que es basura en la traza y además hace que dos casos idénticos se lean
distinto según de qué lado caiga el último bit.

CLAUDE.md §10 ya fija el criterio para la estática de la viga: «un residuo de 1e-13 no es
demanda». Esto es lo mismo, aplicado al momento de volcamiento.

La tolerancia es RELATIVA a la escala de los términos que se cancelan —|M| + |P·offset|—,
no absoluta: es la precisión con la que la diferencia PUEDE formarse. 1e-9 está siete
órdenes por encima del ruido de la doble precisión (~1e-16) y muchos órdenes por debajo
de cualquier momento con significado de ingeniería, de modo que no puede silenciar una
demanda real."""


def denoise_moment_kNm(value: float, scale: float) -> float:
    """Cero si `value` está por debajo del ruido de cancelación de su propia escala."""
    return 0.0 if abs(value) <= MOMENT_NOISE_REL_TOL * scale else value


def axis_moments_kNm(
    combo: LoadCombination, offset_m: float, axis: str
) -> tuple[float, float]:
    """(M_total, M_estabilizante) de UNA carga respecto del centro de la base [kN·m].

    Los dos CON SIGNO, en el convenio de `engine/soil/eccentricity.py`:

        M_total         = M + P·offset
        M_estabilizante = Σ_estab (M_k + P_k·offset)

    El conjunto `estab` es EXACTAMENTE el de `stabilizing_axial_kN` —los CM más los
    aportes no muertos que restan carga vertical, E.020 art. 20.1—, de modo que N y su
    momento son coherentes entre sí. Sin composición no se sabe qué parte es muerta y
    las dos lecturas coinciden.

    Es la ÚNICA fuente del término `P·offset` en el motor: la usan la zapata aislada,
    las zapatas de la conectada y, columna a columna, la combinada."""
    m_col = combo.Mx_kNm if axis == "X" else combo.My_kNm
    total = denoise_moment_kNm(
        m_col + combo.P_kN * offset_m, abs(m_col) + abs(combo.P_kN * offset_m)
    )
    comp = combo.composition
    if comp is None:
        return total, total
    estabilizante = escala = 0.0
    for c in comp.components:
        if c.kind == "CM" or c.P_kN < 0.0:
            m_k = c.Mx_kNm if axis == "X" else c.My_kNm
            estabilizante += m_k + c.P_kN * offset_m
            escala += abs(m_k) + abs(c.P_kN * offset_m)
    return total, denoise_moment_kNm(estabilizante, escala)


def stabilizing_axial_kN(combo: LoadCombination, self_weight_kN: float) -> tuple[float, bool]:
    """(N estabilizante, ¿es exacta?) según E.020 art. 20.1.

    Con composición: carga muerta más los aportes no muertos que RESTAN carga vertical.
    Sin composición: la carga total, que es cota superior (no exacta)."""
    comp = combo.composition
    if comp is None:
        return combo.P_kN + self_weight_kN, False
    n = self_weight_kN
    for c in comp.components:
        if c.kind == "CM":
            n += c.P_kN
        elif c.P_kN < 0.0:
            n += c.P_kN
    return n, True


class SlidingResult(BaseModel):
    H_resultant_kN: float
    Hx_kN: float
    Hy_kN: float
    N_total_kN: float
    mu_used: float | None
    friction_resistance_kN: float | None
    cohesion_resistance_kN: float | None
    total_resistance_kN: float | None
    FS_obtained: float | None
    FS_required: float | None
    governing_combo: str | None
    status: CheckStatus
    message: str
    missing_parameters: list[str] = Field(default_factory=list)
    equation_substituted: str
    code_reference: str


class OverturningResult(BaseModel):
    """Volcamiento respecto de una arista. Común a las tres tipologías desde
    FORMULACION_VOLTEO: `applied_moment_kNm` es ya la ENVOLVENTE de las dos lecturas,
    y las dos se publican para que el criterio pueda comprobarse con números y no
    leyendo la prosa."""

    axis: str = Field(..., description='"X" o "Y": eje respecto al cual se evalúa el volcamiento')
    pivot_description: str
    N_total_kN: float
    stabilizing_moment_kNm: float
    applied_moment_kNm: float
    applied_moment_total_kNm: float = Field(
        default=0.0, description="|M| con la carga TOTAL de la combinación, incluido P·offset"
    )
    applied_moment_dead_kNm: float = Field(
        default=0.0,
        description="|M| con solo la parte estabilizante (E.020 art. 20.1), incluido P·offset",
    )
    envelope_reading: str = Field(
        default="TOTAL", description='"TOTAL" o "ESTABILIZANTE": cuál de las dos lecturas gobernó'
    )
    horizontal_force_kN: float
    horizontal_lever_arm_m: float
    overturning_moment_kNm: float
    FS_obtained: float | None
    FS_required: float | None
    governing_combo: str | None
    status: CheckStatus
    message: str
    missing_parameters: list[str] = Field(default_factory=list)
    equation_substituted: str
    code_reference: str


class StabilityResult(BaseModel):
    sliding: SlidingResult
    overturning_x: OverturningResult
    overturning_y: OverturningResult
    applicable: bool = Field(..., description="False si ninguna combinación tiene fuerzas horizontales ni momentos")

    @property
    def status(self) -> CheckStatus:
        return CheckStatus.worst(
            [self.sliding.status, self.overturning_x.status, self.overturning_y.status]
        )


def _has_horizontal(combo: LoadCombination) -> bool:
    return abs(combo.Hx_kN) > 1e-9 or abs(combo.Hy_kN) > 1e-9


def check_sliding(
    load_case_set: LoadCaseSet, soil: SoilProfile, self_weight_kN: float, footing_area_m2: float
) -> SlidingResult:
    combos = [c for c in load_case_set.service if _has_horizontal(c)]

    if not combos:
        return SlidingResult(
            H_resultant_kN=0.0, Hx_kN=0.0, Hy_kN=0.0, N_total_kN=0.0,
            mu_used=None, friction_resistance_kN=None, cohesion_resistance_kN=None,
            total_resistance_kN=None, FS_obtained=None, FS_required=soil.FS_sliding_required,
            governing_combo=None, status=CheckStatus.PASS,
            message="No aplicable: ninguna combinación de servicio declara fuerzas horizontales.",
            equation_substituted="Hx = Hy = 0 en todas las combinaciones de servicio.",
            code_reference="E.050 art. 17.1 (cargas de servicio)",
        )

    missing: list[str] = []
    if soil.mu_friction_soil_concrete is None:
        missing.append("mu_friction_soil_concrete (coeficiente de fricción suelo-concreto, E.020 art. 22.2)")
    fs_required, fs_source = _fs_sliding_required(soil.FS_sliding_required)

    # Combinación gobernante: la de MENOR FS, es decir mayor H respecto de su N.
    # Sin mu no puede calcularse FS; se usa la de mayor H/N como gobernante.
    def _ratio(c: LoadCombination) -> float:
        n = stabilizing_axial_kN(c, self_weight_kN)[0]
        h = (c.Hx_kN**2 + c.Hy_kN**2) ** 0.5
        return h / n if n > 0 else float("inf")

    governing = max(combos, key=_ratio)
    H = (governing.Hx_kN**2 + governing.Hy_kN**2) ** 0.5
    N, n_exacta = stabilizing_axial_kN(governing, self_weight_kN)

    if missing:
        return SlidingResult(
            H_resultant_kN=H, Hx_kN=governing.Hx_kN, Hy_kN=governing.Hy_kN, N_total_kN=N,
            mu_used=None, friction_resistance_kN=None, cohesion_resistance_kN=None,
            total_resistance_kN=None, FS_obtained=None, FS_required=fs_required,
            governing_combo=governing.name, status=CheckStatus.NOT_VERIFIED,
            message=(
                f"DESLIZAMIENTO NO VERIFICADO: falta(n) {', '.join(missing)}. "
                f"La combinación {governing.name} aplica H={H:.1f} kN sobre N={N:.1f} kN. "
                f"No se asume ningún valor. {FS_REFERENCE_NOTE}"
            ),
            missing_parameters=missing,
            equation_substituted=f"H={H:.2f} kN, N={N:.2f} kN; falta {', '.join(missing)}",
            code_reference=(
                "E.050 art. 17.1; E.020 art. 22.2 (μ del proyectista); FS 1,50: criterio del "
                "programa (D10-2b), más estricto que E.020 art. 22.1 (1,25)"
            ),
        )

    mu = soil.mu_friction_soil_concrete
    friction = mu * N
    cohesion_res = soil.cohesion_kPa * footing_area_m2 if soil.cohesion_kPa is not None else 0.0
    total_resistance = friction + cohesion_res
    fs = total_resistance / H if H > 0 else float("inf")

    if fs >= fs_required and not n_exacta:
        status = CheckStatus.NOT_VERIFIED
        message = (
            f"DESLIZAMIENTO NO VERIFICADO: FS = {fs:.2f} >= {fs_required:.2f} ({fs_source}) con la "
            f"carga total de la combinación {governing.name}. {E020_DEAD_LOAD_ONLY_NOTE}"
        )
    elif fs >= fs_required:
        status = CheckStatus.PASS
        message = (
            f"Deslizamiento cumple: FS = {fs:.2f} >= {fs_required:.2f} ({fs_source}), con solo la "
            f"carga muerta como estabilizante (E.020 art. 20.1), combinación {governing.name}."
        )
    else:
        status = CheckStatus.FAIL
        message = (
            f"DESLIZAMIENTO NO CUMPLE: FS = {fs:.2f} < {fs_required:.2f} requerido "
            f"(combinación {governing.name}). Resistencia {total_resistance:.1f} kN frente a "
            f"H = {H:.1f} kN. Faltan {(H * fs_required - total_resistance):.1f} kN de resistencia."
        )

    return SlidingResult(
        H_resultant_kN=H, Hx_kN=governing.Hx_kN, Hy_kN=governing.Hy_kN, N_total_kN=N,
        mu_used=mu, friction_resistance_kN=friction,
        cohesion_resistance_kN=cohesion_res if soil.cohesion_kPa is not None else None,
        total_resistance_kN=total_resistance, FS_obtained=fs, FS_required=fs_required,
        governing_combo=governing.name, status=status, message=message,
        equation_substituted=(
            f"H = sqrt({governing.Hx_kN:.1f}² + {governing.Hy_kN:.1f}²) = {H:.2f} kN | "
            + (f"N = CM + no muertas desfavorables + peso propio = {N:.2f} kN (E.020 art. 20.1) | "
               if n_exacta else f"N = {governing.P_kN:.1f} + {self_weight_kN:.1f} = {N:.2f} kN (cota superior) | ")
            + f"F_fricción = μ·N = {mu:.3f}·{N:.2f} = {friction:.2f} kN"
            + (f" | F_cohesión = c·A = {soil.cohesion_kPa:.1f}·{footing_area_m2:.3f} = {cohesion_res:.2f} kN"
               if soil.cohesion_kPa is not None else " | cohesión no proporcionada: no se considera")
            + f" | FS = {total_resistance:.2f}/{H:.2f} = {fs:.3f} (requerido {fs_required:.2f})"
        ),
        code_reference=(
            "E.050 art. 17.1 (cargas de servicio); E.020 art. 20.1 (solo carga muerta); "
            + (
                "FS adoptado por el proyectista" if fs_source == FS_SOURCE_DECLARED
                else "FS 1,50: criterio del programa (D10-2b), más estricto que E.020 art. 22.1 (1,25)"
            )
        ),
    )


def _check_overturning_axis(
    load_case_set: LoadCaseSet,
    soil: SoilProfile,
    self_weight_kN: float,
    dimension_m: float,
    h_m: float,
    axis: str,
    offset_m: float = 0.0,
) -> OverturningResult:
    """axis='X': vuelco alrededor de la arista perpendicular a X, es decir el vuelco
    EN LA DIRECCIÓN X. Lo gobierna Mx -- que según E.050 art. 28.1 es el momento que
    desplaza la resultante a lo largo de X -- la excentricidad de la columna sobre ese
    mismo eje y la fuerza horizontal Hx.

    `offset_m` es el desplazamiento de la columna respecto del centroide de la zapata en
    este eje (`ColumnPlacement`). Con la columna centrada vale 0 y la formulación se
    reduce a la anterior a FORMULACION_VOLTEO."""
    fs_required = soil.FS_overturning_required

    def _partes(c: LoadCombination) -> tuple[float, float, float]:
        """(|M_total|, |M_estabilizante|, |H|) en este eje."""
        total, estab = axis_moments_kNm(c, offset_m, axis)
        h_force = c.Hx_kN if axis == "X" else c.Hy_kN
        return abs(total), abs(estab), abs(h_force)

    def _aplica(c: LoadCombination) -> bool:
        m_total, m_dead, h_force = _partes(c)
        return max(m_total, m_dead) > 0.0 or h_force > 0.0

    relevant = [c for c in load_case_set.service if _aplica(c)]
    if not relevant:
        return OverturningResult(
            axis=axis,
            pivot_description="No aplicable",
            N_total_kN=0.0, stabilizing_moment_kNm=0.0, applied_moment_kNm=0.0,
            horizontal_force_kN=0.0, horizontal_lever_arm_m=0.0, overturning_moment_kNm=0.0,
            FS_obtained=None, FS_required=fs_required, governing_combo=None,
            status=CheckStatus.PASS,
            message=(
                f"No aplicable en el eje {axis}: la resultante no produce momento ni fuerza "
                f"horizontal en esa dirección."
            ),
            equation_substituted=(
                f"M + P·offset = 0 y H = 0 en todas las combinaciones de servicio "
                f"(offset_{axis.lower()} = {offset_m:+.4f} m)."
            ),
            code_reference="E.050 art. 17.1",
            applied_moment_total_kNm=0.0, applied_moment_dead_kNm=0.0, envelope_reading="TOTAL",
        )

    pivot = (
        f"Arista inferior de la zapata perpendicular al eje {axis}, a {dimension_m / 2:.3f} m "
        f"del centro (borde de la base). Empuje pasivo no considerado."
    )

    def _valores(c: LoadCombination):
        m_total, m_dead, h_force = _partes(c)
        # ENVOLVENTE (opción B): la peor de las dos lecturas. Ver ENVELOPE_NOTE.
        m_aplicado = max(m_total, m_dead)
        lectura = "TOTAL" if m_total >= m_dead else "ESTABILIZANTE"
        n, exacta = stabilizing_axial_kN(c, self_weight_kN)
        m_stab = n * dimension_m / 2.0
        m_over = m_aplicado + h_force * h_m
        fs = m_stab / m_over if m_over > 0 else float("inf")
        return m_total, m_dead, m_aplicado, lectura, h_force, n, exacta, m_stab, m_over, fs

    def _fs(c: LoadCombination) -> float:
        return _valores(c)[9]

    # La combinación gobernante NO puede elegirse solo por el FS más bajo: distintas
    # combinaciones pueden tener criterios distintos (o ninguno). Se separan en las que
    # tienen criterio aplicable y las que no, y gobierna la de peor desenlace.
    declared = soil.FS_overturning_required
    con_criterio = [c for c in relevant if _fs_overturning_required(c, declared)[0] is not None]
    sin_criterio = [c for c in relevant if _fs_overturning_required(c, declared)[0] is None]

    peor_con_criterio = (
        min(con_criterio, key=lambda c: _fs(c) / _fs_overturning_required(c, declared)[0])
        if con_criterio
        else None
    )
    peor_sin_criterio = min(sin_criterio, key=_fs) if sin_criterio else None

    # Una combinación que INCUMPLE su criterio manda sobre una que no puede juzgarse;
    # y una que no puede juzgarse manda sobre las que cumplen. Nunca al revés: un PASS
    # no debe tapar un NO VERIFICADO.
    if peor_con_criterio is not None and _fs(peor_con_criterio) < _fs_overturning_required(
        peor_con_criterio, declared
    )[0]:
        governing = peor_con_criterio
    elif peor_sin_criterio is not None:
        governing = peor_sin_criterio
    else:
        governing = peor_con_criterio

    assert governing is not None
    fs_required, fs_source = _fs_overturning_required(governing, declared)
    (
        m_total, m_dead, m_applied, lectura, h_force, N, n_exacta, m_stab, m_over, fs
    ) = _valores(governing)

    envolvente = (
        f"envolvente |M|: total {m_total:.2f} / estabilizante {m_dead:.2f} "
        f"→ {m_applied:.2f} kN·m ({lectura})"
    )
    excentricidad = (
        f"M_total = M + P·offset con offset_{axis.lower()} = {offset_m:+.4f} m"
        if offset_m != 0.0
        else "columna centrada en este eje: P·offset = 0"
    )

    if fs_required is None:
        return OverturningResult(
            axis=axis, pivot_description=pivot, N_total_kN=N,
            stabilizing_moment_kNm=m_stab, applied_moment_kNm=m_applied,
            horizontal_force_kN=h_force, horizontal_lever_arm_m=h_m,
            overturning_moment_kNm=m_over, FS_obtained=fs, FS_required=None,
            governing_combo=governing.name, status=CheckStatus.NOT_VERIFIED,
            message=(
                f"VOLCAMIENTO EJE {axis} NO VERIFICADO: falta FS_overturning_required "
                f"(factor de seguridad al volcamiento adoptado). El FS calculado es {fs:.2f}, "
                f"pero sin criterio declarado no puede juzgarse. {FS_REFERENCE_NOTE}"
            ),
            missing_parameters=["FS_overturning_required"],
            equation_substituted=(
                f"M_estab = N·{axis.lower()}/2 = {N:.2f}·{dimension_m / 2:.3f} = {m_stab:.2f} kN·m | "
                f"{excentricidad} | {envolvente} | "
                f"M_volc = {m_applied:.2f} + {h_force:.2f}·{h_m:.3f} = {m_over:.2f} kN·m | "
                f"FS = {fs:.3f} (sin criterio declarado)"
            ),
            code_reference="E.050 art. 17.1; FS no prescrito para zapatas aisladas",
            applied_moment_total_kNm=m_total, applied_moment_dead_kNm=m_dead,
            envelope_reading=lectura,
        )

    if fs >= fs_required and not n_exacta:
        status = CheckStatus.NOT_VERIFIED
        message = (
            f"VOLCAMIENTO EJE {axis} NO VERIFICADO: FS = {fs:.2f} >= {fs_required:.2f} "
            f"({fs_source}) con la carga total de la combinación {governing.name}. "
            f"{E020_DEAD_LOAD_ONLY_NOTE}"
        )
    elif fs >= fs_required:
        status = CheckStatus.PASS
        message = (
            f"Volcamiento eje {axis} cumple: FS = {fs:.2f} >= {fs_required:.2f} "
            f"({fs_source}, combinación {governing.name}), con solo la carga muerta como "
            f"estabilizante (E.020 art. 20.1) y la lectura {lectura} de la envolvente."
        )
    else:
        status = CheckStatus.FAIL
        message = (
            f"VOLCAMIENTO EJE {axis} NO CUMPLE: FS = {fs:.2f} < {fs_required:.2f} requerido "
            f"({fs_source}, combinación {governing.name}). M_estabilizador = {m_stab:.1f} kN·m "
            f"frente a M_volcador = {m_over:.1f} kN·m (lectura {lectura} de la envolvente)."
        )

    return OverturningResult(
        axis=axis, pivot_description=pivot, N_total_kN=N,
        stabilizing_moment_kNm=m_stab, applied_moment_kNm=m_applied,
        horizontal_force_kN=h_force, horizontal_lever_arm_m=h_m,
        overturning_moment_kNm=m_over, FS_obtained=fs, FS_required=fs_required,
        governing_combo=governing.name, status=status, message=message,
        equation_substituted=(
            f"Punto de giro: {pivot} | "
            f"M_estab = N·dim/2 = {N:.1f}·{dimension_m / 2:.3f} = {m_stab:.2f} kN·m "
            + ("(N: carga muerta y no muertas desfavorables, E.020 art. 20.1) | "
               if n_exacta else f"(N = {governing.P_kN:.1f}+{self_weight_kN:.1f}, cota superior) | ")
            + f"{excentricidad} | {envolvente} | "
            f"M_volc = |M| + |H|·h = {m_applied:.2f} + {h_force:.2f}·{h_m:.3f} = {m_over:.2f} kN·m | "
            f"FS = {fs:.3f} (requerido {fs_required:.2f}, {fs_source})"
        ),
        code_reference=(
            "E.050 art. 17.1 (cargas de servicio); E.020 art. 20.1 (solo carga muerta); "
            + (
                "FS 1,50: criterio del programa (D10-2b), más estricto que E.030 art. 64.2 "
                "(1,20 por volteo sísmico)"
                if fs_source == FS_SOURCE_PROGRAM_OVERTURNING_SEISMIC
                else "FS 1,50: criterio del programa (D10-2b), coincide con E.020 art. 21"
                if fs_source == FS_SOURCE_PROGRAM_OVERTURNING
                else "FS adoptado por el proyectista"
            )
        ),
        applied_moment_total_kNm=m_total, applied_moment_dead_kNm=m_dead,
        envelope_reading=lectura,
    )


def check_stability(
    load_case_set: LoadCaseSet,
    soil: SoilProfile,
    self_weight_kN: float,
    B_m: float,
    L_m: float,
    h_m: float,
    placement: "ColumnPlacement | None" = None,
) -> StabilityResult:
    """`placement` describe dónde se apoya la columna sobre la zapata. Su excentricidad
    entra en el momento volcador (FORMULACION_VOLTEO); omitirlo equivale a declarar la
    columna centrada, que es el caso por defecto."""
    area = B_m * L_m
    offset_x = placement.offset_x_m if placement is not None else 0.0
    offset_y = placement.offset_y_m if placement is not None else 0.0
    sliding = check_sliding(load_case_set, soil, self_weight_kN, area)
    over_x = _check_overturning_axis(
        load_case_set, soil, self_weight_kN, B_m, h_m, "X", offset_x
    )
    over_y = _check_overturning_axis(
        load_case_set, soil, self_weight_kN, L_m, h_m, "Y", offset_y
    )
    applicable = any(
        _has_horizontal(c)
        or max(abs(v) for v in axis_moments_kNm(c, offset_x, "X")) > 1e-9
        or max(abs(v) for v in axis_moments_kNm(c, offset_y, "Y")) > 1e-9
        for c in load_case_set.service
    )
    return StabilityResult(
        sliding=sliding, overturning_x=over_x, overturning_y=over_y, applicable=applicable
    )
