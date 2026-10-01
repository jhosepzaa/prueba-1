"""FASE DE ARMADO: soluciones de acero constructibles, combinadas y clasificables.

Hueco que cierra este módulo
----------------------------
`reinforcement/rebar_alternatives.py` genera varias opciones (diámetro, separación)
POR DIRECCIÓN, pero cada geometría producía una sola solución de armado y esas
opciones no participaban en ninguna clasificación.

Aquí se combinan las opciones de la dirección X con las de la dirección Y para
formar SOLUCIONES DE ARMADO completas y distintas, cada una con su propia masa de
acero real, su eficiencia y su complejidad constructiva, de modo que puedan
compararse y ordenarse.

    Geometría ALT-031 (B=2.00, L=2.50, h=0.40)
      ├── ARM-031-A:  X: 1/2" @ 17.5 cm   Y: 1/2" @ 17.5 cm   (mismo diámetro)
      ├── ARM-031-B:  X: 1/2" @ 17.5 cm   Y: 5/8" @ 25.0 cm
      ├── ARM-031-C:  X: 5/8" @ 25.0 cm   Y: 1/2" @ 17.5 cm
      └── ...

MASA DE ACERO -- ALCANCE DECLARADO
----------------------------------
Se calcula con la longitud recta de las barras (dimensión de la zapata menos dos
recubrimientos). **NO incluye ganchos, dobleces ni traslapes.** La verificación de
longitud de desarrollo (L4) ya está implementada y determina SI se requiere un
gancho, pero el cómputo de la longitud adicional del doblez no está incorporado a
la masa. Por lo tanto la masa reportada sigue siendo una COTA INFERIOR del acero
real de obra, declarada en `steel_mass_excludes_hooks`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.optimization.alternative_generator import Alternative
from engine.optimization.metrics import COMMON_SPACINGS_M, STEEL_DENSITY_KGM3
from engine.reinforcement.rebar_alternatives import RebarAlternative
from engine.results.footing_candidate import FootingCandidate
from engine.results.status import CheckStatus


class ArmingMetrics(BaseModel):
    steel_mass_kg: float = Field(..., description="Masa total de la parrilla inferior (sin ganchos ni traslapes)")
    steel_mass_x_kg: float
    steel_mass_y_kg: float
    steel_mass_excludes_hooks: bool = Field(
        default=True,
        description="Siempre True: la masa usa longitud recta, sin ganchos ni traslapes",
    )

    total_bars: int
    n_distinct_diameters: int
    same_diameter_both_directions: bool
    uses_common_spacings: bool

    utilization_x: float = Field(..., description="As_diseño / As_provisto en X (1.0 = sin desperdicio)")
    utilization_y: float
    mean_utilization: float
    steel_waste_ratio: float = Field(..., description="1 - utilización media: fracción de acero excedente")

    constructive_complexity_index: float = Field(
        ...,
        description=(
            "HEURÍSTICA (no normativa): 1 si ambas direcciones usan el mismo diámetro, 2 si usan "
            "dos diámetros distintos; +0.5 si alguna separación no es de las habituales en obra. "
            "Rango 1.0 (más simple) a 2.5."
        ),
    )


class ArmingSolution(BaseModel):
    id: str
    geometry_id: str
    candidate: FootingCandidate
    rebar_x: RebarAlternative
    rebar_y: RebarAlternative
    metrics: ArmingMetrics
    status: CheckStatus

    @property
    def label(self) -> str:
        return f"X: {self.rebar_x.label}  |  Y: {self.rebar_y.label}"


def _bar_mass_kg(rebar: RebarAlternative, bar_length_m: float) -> float:
    """La sección `As_provided_m2` es el área TOTAL de todas las barras de esa
    dirección; multiplicada por la longitud recta da el volumen de acero."""
    return rebar.As_provided_m2 * max(bar_length_m, 0.0) * STEEL_DENSITY_KGM3


def compute_arming_metrics(
    candidate: FootingCandidate, rebar_x: RebarAlternative, rebar_y: RebarAlternative, cover_m: float
) -> ArmingMetrics:
    # Barras de X corren a lo largo de B; barras de Y a lo largo de L.
    length_x = candidate.B_m - 2.0 * cover_m
    length_y = candidate.L_m - 2.0 * cover_m

    mass_x = _bar_mass_kg(rebar_x, length_x)
    mass_y = _bar_mass_kg(rebar_y, length_y)

    same_diameter = rebar_x.bar_designation == rebar_y.bar_designation
    n_diameters = 1 if same_diameter else 2
    common_spacings = (
        round(rebar_x.spacing_m, 4) in COMMON_SPACINGS_M and round(rebar_y.spacing_m, 4) in COMMON_SPACINGS_M
    )
    complexity = n_diameters + (0.0 if common_spacings else 0.5)

    mean_utilization = (rebar_x.utilization + rebar_y.utilization) / 2.0

    return ArmingMetrics(
        steel_mass_kg=mass_x + mass_y,
        steel_mass_x_kg=mass_x,
        steel_mass_y_kg=mass_y,
        total_bars=rebar_x.n_bars + rebar_y.n_bars,
        n_distinct_diameters=n_diameters,
        same_diameter_both_directions=same_diameter,
        uses_common_spacings=common_spacings,
        utilization_x=rebar_x.utilization,
        utilization_y=rebar_y.utilization,
        mean_utilization=mean_utilization,
        steel_waste_ratio=1.0 - mean_utilization,
        constructive_complexity_index=complexity,
    )


def generate_arming_solutions(
    alternative: Alternative, cover_m: float, max_solutions: int | None = None
) -> list[ArmingSolution]:
    """Producto cartesiano de las opciones de armado en X e Y de una geometría.

    El estado de cada solución hereda el de la geometría: si la geometría llevaba
    WARNING (p. ej. por punzonamiento con momento, o por el anclaje no
    implementado), todas sus soluciones de armado lo llevan también. Un armado
    válido NO puede "limpiar" una advertencia de la geometría que lo soporta.
    """
    candidate = alternative.candidate
    options_x = candidate.rebar_options_x
    options_y = candidate.rebar_options_y
    if not options_x or not options_y:
        return []

    suffix = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    geometry_number = alternative.id.split("-")[-1]

    solutions: list[ArmingSolution] = []
    for rx in options_x:
        for ry in options_y:
            index = len(solutions)
            if max_solutions is not None and index >= max_solutions:
                return solutions
            letter = suffix[index] if index < len(suffix) else f"#{index}"
            solutions.append(
                ArmingSolution(
                    id=f"ARM-{geometry_number}-{letter}",
                    geometry_id=alternative.id,
                    candidate=candidate,
                    rebar_x=rx,
                    rebar_y=ry,
                    metrics=compute_arming_metrics(candidate, rx, ry, cover_m),
                    status=candidate.overall_status,
                )
            )
    return solutions


def generate_all_arming_solutions(
    alternatives: list[Alternative], cover_m: float, max_per_geometry: int | None = None
) -> list[ArmingSolution]:
    result: list[ArmingSolution] = []
    for alternative in alternatives:
        result.extend(generate_arming_solutions(alternative, cover_m, max_per_geometry))
    return result
