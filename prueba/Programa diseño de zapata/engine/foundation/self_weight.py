"""Peso propio de la zapata y peso del relleno de suelo sobre la zapata.

No es una ecuación normativa (es geometría + peso unitario), por eso no lleva
cita de artículo -- se marca "N/A" en el CalculationTrace cuando corresponda.

Depende de B, L, h (candidato), por lo que debe recalcularse en cada iteración
de h (punto 4 de la corrección de Fase 2) -- nunca se congela un valor de peso
propio calculado para un h distinto del que se está evaluando.
"""

from __future__ import annotations

from pydantic import BaseModel


class SelfWeightResult(BaseModel):
    W_footing_kN: float
    W_soil_backfill_kN: float
    W_total_kN: float


def compute_self_weight(
    B_m: float,
    L_m: float,
    h_m: float,
    Df_m: float,
    concrete_unit_weight_kNm3: float,
    soil_unit_weight_kNm3: float,
) -> SelfWeightResult:
    """W_footing = gamma_concreto * B * L * h.
    W_relleno = gamma_suelo * B * L * (Df - h), solo si Df > h (relleno sobre la
    zapata); si Df <= h, no hay relleno sobre la zapata y este término es 0.
    """
    W_footing = concrete_unit_weight_kNm3 * B_m * L_m * h_m
    backfill_thickness = max(Df_m - h_m, 0.0)
    W_soil = soil_unit_weight_kNm3 * B_m * L_m * backfill_thickness
    return SelfWeightResult(
        W_footing_kN=W_footing,
        W_soil_backfill_kN=W_soil,
        W_total_kN=W_footing + W_soil,
    )
