"""Métricas de un sistema de zapata conectada — Fase 4D.

Devuelve el MISMO tipo `AlternativeMetrics` que la zapata aislada y la combinada. El
optimizador —`scoring`, `pareto`, `ranker`— trabaja sobre métricas y no sabe qué
tipología las produjo; manteniendo el tipo, toda esa maquinaria se reutiliza sin tocar
una línea.

QUÉ SUMA Y QUÉ NO
=================
El sistema son TRES elementos: dos zapatas y una viga. Las métricas de las zapatas se
obtienen llamando a `compute_metrics`, el mismo módulo que usa la zapata aislada —no se
reescribe su aritmética—, y a eso se le añade la viga.

La VIGA no es una zapata y no cabe en `compute_metrics`. Su aportación se calcula aquí,
con la misma densidad de acero.

GEOMETRÍA DE LA VIGA — Fase 9b
==============================
Cada zapata cuenta su prisma completo B·L·h. La viga es el prisma b × h entre caras de
columna [c_e, c_i], con fondo a z_b sobre la base común. Una misma región física no puede
ser zapata y viga a la vez:

    ℓ_e = L1 − c_e      ℓ_v = f_i − L1      ℓ_i = c_i − f_i
    t_j = max(0, min(z_b + h, h_j) − max(z_b, 0))      parte de la sección DENTRO de la zapata j

    V_vano   = b·h·ℓ_v                       viga
    V_dentro = b·t_j·ℓ_j                     zapata j (ya está en B·L·h; no se suma)
    V_sobre  = b·(h − t_j)·ℓ_j               viga
    V_viga   = V_vano + V_sobre,e + V_sobre,i

    invariante: V_viga + V_dentro,e + V_dentro,i = b·h·(c_i − c_e)

Si z_b no está declarada se adopta z_b = 0 (`BEAM_METRIC_SOFFIT_HYPOTHESIS`): con esa cota
la viga ocupa la mayor altura posible dentro de las zapatas, de modo que el volumen que se
le atribuye es el MÍNIMO compatible con la geometría. Es hipótesis de la métrica: no toca
la estática ni el peso propio, que solo usan z_b declarada.

Acero longitudinal: (As⁻ + As⁺)·(c_i − c_e). Sin anclajes ni estribos.

Ningún valor de este módulo proviene de E.060 o E.050: son geometría y densidad de
materiales.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.foundation.connected_solver import ConnectedFootingResult
from engine.optimization.metrics import (
    COMMON_SPACINGS_M,
    STEEL_DENSITY_KGM3,
    AlternativeMetrics,
    compute_metrics,
)

# Penalización de constructibilidad por la viga de conexión. EN CERO, DELIBERADAMENTE.
#
# La idea —una viga con estribos cerrados y acero en dos caras cuesta más de ejecutar
# que la parrilla de una zapata— es razonable, pero no hay nada que fije el valor. Con
# 1.0 el número no salía de ningún sitio y sin embargo movía el ORDEN entre alternativas
# a través de `constructive_complexity_index`: una heurística sin fundamento decidiendo
# cuál se recomienda.
#
# En cero no altera el orden. Además, todas las alternativas del sistema llevan viga, de
# modo que una constante igual para todas tampoco aportaría información: solo desplazaría
# el índice en bloque. Si algún día existe un criterio justificable —un ratio de costo
# medido, no una impresión— este es el punto donde entra.
BEAM_COMPLEXITY_PENALTY = 0.0

# Cota del fondo de la viga que usa la MÉTRICA cuando el usuario no declaró z_b.
BEAM_METRIC_DEFAULT_SOFFIT_M = 0.0

BEAM_METRIC_SOFFIT_HYPOTHESIS = (
    "Métrica de volumen de la viga: z_b no está declarada; se adopta z_b = 0 (fondo de la "
    "viga en la base común de cimentación). Con esa cota la viga ocupa la mayor altura "
    "posible dentro de las zapatas, de modo que el volumen atribuido a la viga es el mínimo "
    "compatible con la geometría. Es una hipótesis de la métrica: no interviene en la "
    "estática, las cargas ni el diseño."
)

BEAM_METRIC_STEEL_HYPOTHESIS = (
    "Métrica de acero de la viga: As⁻ + As⁺ en toda la longitud entre caras de columna "
    "(c_i − c_e). No incluye anclajes ni estribos: subestima el acero de la viga y no debe "
    "usarse como metrado."
)


def _overlap(z0: float, z1: float, lo: float, hi: float) -> float:
    return max(0.0, min(z1, hi) - max(z0, lo))


class BeamVolumeBreakdown(BaseModel):
    """Desglose geométrico de la viga para las métricas (Fase 9b). Ver la cabecera."""

    soffit_above_base_m: float = Field(..., description="z_b usada por la métrica")
    soffit_declared: bool = Field(..., description="True si z_b la declaró el usuario")
    span_m3: float = Field(..., description="V_vano = b·h·(f_i − L1)")
    exterior_inside_m3: float = Field(..., description="dentro de la zapata exterior: es zapata")
    exterior_above_m3: float = Field(..., description="sobresale de la zapata exterior: es viga")
    interior_inside_m3: float = Field(..., description="dentro de la zapata interior: es zapata")
    interior_above_m3: float = Field(..., description="sobresale de la zapata interior: es viga")
    steel_length_m: float = Field(..., description="c_i − c_e")
    hypotheses: list[str] = Field(default_factory=list)

    @property
    def total_m3(self) -> float:
        """Volumen atribuible a la viga."""
        return self.span_m3 + self.exterior_above_m3 + self.interior_above_m3


def beam_volume_breakdown(result: ConnectedFootingResult) -> BeamVolumeBreakdown:
    """Reparte el prisma de la viga entre vano libre, zapatas y lo que sobresale."""
    ax = result.beam_axis
    b, h = result.beam.b_m, result.beam.h_m
    declarada = ax.soffit_above_base_m is not None
    z_b = ax.soffit_above_base_m if declarada else BEAM_METRIC_DEFAULT_SOFFIT_M
    z_t = z_b + h
    t_e = _overlap(z_b, z_t, 0.0, result.geometry.exterior_h_m)
    t_i = _overlap(z_b, z_t, 0.0, result.geometry.interior_h_m)
    hipotesis = [] if declarada else [BEAM_METRIC_SOFFIT_HYPOTHESIS]
    hipotesis.append(BEAM_METRIC_STEEL_HYPOTHESIS)
    return BeamVolumeBreakdown(
        soffit_above_base_m=z_b,
        soffit_declared=declarada,
        span_m3=b * h * ax.clear_span_m,
        exterior_inside_m3=b * t_e * ax.over_exterior_m,
        exterior_above_m3=b * (h - t_e) * ax.over_exterior_m,
        interior_inside_m3=b * t_i * ax.over_interior_m,
        interior_above_m3=b * (h - t_i) * ax.over_interior_m,
        steel_length_m=ax.between_column_faces_m,
        hypotheses=hipotesis,
    )


def _beam_concrete_m3(result: ConnectedFootingResult) -> float:
    """Volumen atribuible a la viga: vano libre + lo que sobresale sobre cada zapata.

    La parte de la viga dentro de cada zapata ya está en el prisma B·L·h de esa zapata;
    contarla otra vez sería doble conteo. La parte por encima de la zapata no la cuenta
    nadie más: omitirla sería el error contrario."""
    return beam_volume_breakdown(result).total_m3


def _beam_steel_kg(result: ConnectedFootingResult) -> float:
    """Acero longitudinal de las dos caras de la viga, entre caras de columna.

    Las barras de la viga no son las parrillas de las zapatas: recorren también el tramo
    sobre cada huella, así que no hay doble conteo. Los estribos y los anclajes NO se
    suman (`BEAM_METRIC_STEEL_HYPOTHESIS`): subestima el acero de la viga; no es metrado."""
    area_total = result.beam.As_negative_m2 + result.beam.As_positive_m2
    return area_total * beam_volume_breakdown(result).steel_length_m * STEEL_DENSITY_KGM3


def compute_connected_metrics(
    result: ConnectedFootingResult, Df_m: float, cover_m: float
) -> AlternativeMetrics:
    """Métricas comparables de una alternativa de zapata conectada.

    `cover_m` es el recubrimiento de las zapatas, el mismo dato que recibe
    `compute_metrics` para la aislada."""
    m_ext = compute_metrics(result.exterior, Df_m, cover_m)
    m_int = compute_metrics(result.interior, Df_m, cover_m)

    designaciones = {
        result.exterior.rebar_x.bar_designation,
        result.exterior.rebar_y.bar_designation,
        result.interior.rebar_x.bar_designation,
        result.interior.rebar_y.bar_designation,
    }
    separaciones = [
        result.exterior.rebar_x.spacing_m, result.exterior.rebar_y.spacing_m,
        result.interior.rebar_x.spacing_m, result.interior.rebar_y.spacing_m,
    ]
    if result.beam.confinement.spacing_provided_m is not None:
        separaciones.append(result.beam.confinement.spacing_provided_m)

    comunes = bool(separaciones) and all(
        round(s, 4) in COMMON_SPACINGS_M for s in separaciones
    )

    complejidad = (
        len(designaciones)
        + (0.0 if comunes else 0.5)
        + max(result.geometry.exterior_h_m, result.geometry.interior_h_m)
        + BEAM_COMPLEXITY_PENALTY  # 0.0: ver la nota de la constante
    )

    return AlternativeMetrics(
        concrete_volume_m3=(
            m_ext.concrete_volume_m3 + m_int.concrete_volume_m3 + _beam_concrete_m3(result)
        ),
        steel_mass_kg=m_ext.steel_mass_kg + m_int.steel_mass_kg + _beam_steel_kg(result),
        footing_area_m2=m_ext.footing_area_m2 + m_int.footing_area_m2,
        # La dimensión máxima en planta del SISTEMA: lo que ocupa de lindero a lindero.
        max_plan_dimension_m=max(
            result.system_length_m,
            result.geometry.exterior_L_m,
            result.geometry.interior_L_m,
        ),
        excavation_volume_m3=m_ext.excavation_volume_m3 + m_int.excavation_volume_m3,
        n_distinct_bar_diameters=len(designaciones),
        uses_common_spacings=comunes,
        constructive_complexity_index=complejidad,
    )
