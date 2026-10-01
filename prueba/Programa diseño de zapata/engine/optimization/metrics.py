"""Métricas descriptivas de una alternativa válida.

ALCANCE (Fase 3): estas son propiedades MEDIBLES de una alternativa -- volumen de
concreto, masa de acero, dimensiones. NO hay aquí ninguna función de puntuación ni
pesos: la combinación ponderada de estas métricas es responsabilidad del
optimizador (Fase 4), deliberadamente separada del dimensionamiento (punto 3 de la
corrección del usuario a la Fase 2).

Las métricas también alimentan la tabla comparativa (sección 11 del encargo
original), que es una vista de datos, no un ranking.

Ningún valor de este módulo proviene de E.060 o E.050: son geometría y densidad
de materiales.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.results.footing_candidate import FootingCandidate

# Densidad del acero de refuerzo [kg/m3]. Constante física del material, no un
# valor normativo.
STEEL_DENSITY_KGM3 = 7850.0

# Separaciones consideradas "habituales en obra" para la heurística de
# constructibilidad. Criterio de práctica constructiva, NO normativo.
COMMON_SPACINGS_M = {0.10, 0.15, 0.20, 0.25, 0.30}


class AlternativeMetrics(BaseModel):
    concrete_volume_m3: float = Field(..., description="B * L * h")
    steel_mass_kg: float = Field(..., description="Masa de la parrilla inferior en ambas direcciones")
    footing_area_m2: float
    max_plan_dimension_m: float
    excavation_volume_m3: float = Field(..., description="B * L * Df -- volumen de excavación aproximado")

    # Ingredientes crudos de constructibilidad, expuestos por separado para que el
    # optimizador de la Fase 4 pueda ponderarlos como prefiera.
    n_distinct_bar_diameters: int
    uses_common_spacings: bool
    constructive_complexity_index: float = Field(
        ...,
        description=(
            "HEURÍSTICA, no normativa ni derivada de ingeniería estructural: "
            "n_diámetros_distintos + 0.5 si alguna separación no es habitual + h[m]. "
            "Menor = más simple de construir. Documentada para poder ajustarse."
        ),
    )


def compute_metrics(candidate: FootingCandidate, Df_m: float, cover_m: float) -> AlternativeMetrics:
    concrete_volume = candidate.B_m * candidate.L_m * candidate.h_m

    # Barras en dirección X: repartidas sobre el ancho L, corren a lo largo de B.
    # Barras en dirección Y: repartidas sobre el ancho B, corren a lo largo de L.
    bar_length_x = max(candidate.B_m - 2.0 * cover_m, 0.0)
    bar_length_y = max(candidate.L_m - 2.0 * cover_m, 0.0)
    steel_volume = (
        candidate.rebar_x.As_provided_m2 * bar_length_x + candidate.rebar_y.As_provided_m2 * bar_length_y
    )
    steel_mass = steel_volume * STEEL_DENSITY_KGM3

    n_diameters = len({candidate.rebar_x.bar_designation, candidate.rebar_y.bar_designation})
    spacings_common = (
        round(candidate.rebar_x.spacing_m, 4) in COMMON_SPACINGS_M
        and round(candidate.rebar_y.spacing_m, 4) in COMMON_SPACINGS_M
    )
    complexity = n_diameters + (0.0 if spacings_common else 0.5) + candidate.h_m

    return AlternativeMetrics(
        concrete_volume_m3=concrete_volume,
        steel_mass_kg=steel_mass,
        footing_area_m2=candidate.B_m * candidate.L_m,
        max_plan_dimension_m=max(candidate.B_m, candidate.L_m),
        excavation_volume_m3=candidate.B_m * candidate.L_m * Df_m,
        n_distinct_bar_diameters=n_diameters,
        uses_common_spacings=spacings_common,
        constructive_complexity_index=complexity,
    )
