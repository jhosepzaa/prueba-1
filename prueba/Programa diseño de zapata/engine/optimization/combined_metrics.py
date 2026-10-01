"""Métricas de una zapata combinada — Fase 2.

Devuelve el MISMO tipo `AlternativeMetrics` que la zapata aislada. No es una
casualidad ni un atajo: el optimizador —`scoring`, `pareto`, `ranker`— trabaja
sobre métricas y no sabe qué tipo de zapata las produjo. Manteniendo el tipo, toda
esa maquinaria se reutiliza sin tocar una línea, que es exactamente lo que la
auditoría de Fase 0 anticipó al clasificarla como «reutilización directa».

Ningún valor de este módulo proviene de E.060 o E.050: son geometría y densidad de
materiales, igual que en `metrics.py`.
"""

from __future__ import annotations

from engine.foundation.combined_solver import CombinedFootingResult
from engine.optimization.metrics import (
    COMMON_SPACINGS_M,
    STEEL_DENSITY_KGM3,
    AlternativeMetrics,
)


def _steel_mass_kg(result: CombinedFootingResult) -> float:
    """Masa de acero de las dos caras longitudinales más las franjas transversales.

    Las barras longitudinales recorren la longitud de la zapata; las de cada franja
    recorren su ancho. Se descuenta el recubrimiento en ambos extremos, igual que
    hace `metrics.py` para la zapata aislada."""
    largo = result.B_m if result.longitudinal_direction == "X" else result.L_m
    ancho = result.L_m if result.longitudinal_direction == "X" else result.B_m
    volumen = 0.0

    for cara in (result.bottom_face, result.top_face):
        if cara is None or cara.rebar is None:
            continue
        longitud_barra = max(largo - 2.0 * cara.cover_m, 0.0)
        volumen += cara.rebar.As_provided_m2 * longitud_barra

    for franja in result.transverse_strips:
        if franja.rebar is None:
            continue
        longitud_barra = max(ancho - 2.0 * result.bottom_face.cover_m, 0.0)
        volumen += franja.rebar.As_provided_m2 * longitud_barra

    return volumen * STEEL_DENSITY_KGM3


def compute_combined_metrics(
    result: CombinedFootingResult, Df_m: float
) -> AlternativeMetrics:
    """Métricas comparables de una alternativa de zapata combinada."""
    area = result.B_m * result.L_m
    diametros = {
        cara.rebar.bar_designation
        for cara in (result.bottom_face, result.top_face)
        if cara is not None and cara.rebar is not None
    } | {
        f.rebar.bar_designation for f in result.transverse_strips if f.rebar is not None
    }
    separaciones = [
        cara.rebar.spacing_m
        for cara in (result.bottom_face, result.top_face)
        if cara is not None and cara.rebar is not None
    ] + [f.rebar.spacing_m for f in result.transverse_strips if f.rebar is not None]
    comunes = bool(separaciones) and all(
        round(s, 4) in COMMON_SPACINGS_M for s in separaciones
    )

    # Misma heurística declarada que en la zapata aislada, más un término por la
    # SEGUNDA CARA: armar arriba y abajo es constructivamente más costoso que armar
    # solo abajo. Sigue siendo HEURÍSTICA, no ingeniería estructural ni norma.
    complejidad = (
        len(diametros)
        + (0.0 if comunes else 0.5)
        + result.h_m
        + (0.5 if result.top_face is not None else 0.0)
    )

    return AlternativeMetrics(
        concrete_volume_m3=area * result.h_m,
        steel_mass_kg=_steel_mass_kg(result),
        footing_area_m2=area,
        max_plan_dimension_m=max(result.B_m, result.L_m),
        excavation_volume_m3=area * Df_m,
        n_distinct_bar_diameters=len(diametros),
        uses_common_spacings=comunes,
        constructive_complexity_index=complejidad,
    )
