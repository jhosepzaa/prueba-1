"""Modelo de resultados de una alternativa (B, L, h) evaluada.

Conserva TODO lo exigido en el punto 4 de la corrección de Fase 2: entradas
utilizadas, combinación gobernante (por check, no una sola global), geometría,
presión de contacto, excentricidades, momentos, cortantes, punzonamiento, As
requerido/proporcionado, verificaciones, estado PASS/FAIL/WARNING, razones de
descarte, CalculationTrace, hipótesis y referencia normativa (estas dos últimas
viven dentro de cada CalculationTraceEntry, no repetidas aquí)."""

from __future__ import annotations

from pydantic import BaseModel

from engine.foundation.flexure import FlexureResult
from engine.foundation.punching_shear import PunchingShearResult
from engine.foundation.self_weight import SelfWeightResult
from engine.foundation.shear_oneway import ShearOneWayResult
from engine.reinforcement.development_check import DevelopmentCheckResult
from engine.reinforcement.rebar_alternatives import RebarAlternative
from engine.reinforcement.rebar_geometry import FootingRebarGeometry
from engine.reinforcement.rebar_selector import RebarSelection
from engine.reinforcement.short_direction import ShortDirectionDistribution
from engine.results.calculation_trace import CalculationTrace
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import ContactPressureResult
from engine.soil.eccentricity import Eccentricity
from engine.soil.stability import StabilityResult


class GoverningCombos(BaseModel):
    """Combinación de carga que gobierna cada verificación, de forma
    independiente (punto 5 de la corrección de Fase 2)."""

    contact_pressure: str
    flexure_x: str
    flexure_y: str
    shear_x: str
    shear_y: str
    punching: str


class DepthTrialResult(BaseModel):
    """Un valor de h probado dentro de la iteración del solver (punto 9 del plan
    de tareas: conservar todos los h evaluados, no solo el que pasó)."""

    h_m: float
    d_m: float
    overall_status: CheckStatus
    discard_reasons: list[str]


class FootingCandidate(BaseModel):
    B_m: float
    L_m: float
    h_m: float
    d_m: float

    self_weight: SelfWeightResult
    eccentricity_governing: Eccentricity
    contact_pressure: ContactPressureResult
    min_depth_status: CheckStatus

    flexure_x: FlexureResult
    flexure_y: FlexureResult
    shear_x: ShearOneWayResult
    shear_y: ShearOneWayResult
    punching: PunchingShearResult

    rebar_x: RebarSelection
    rebar_y: RebarSelection

    # Fase 4: varias opciones de armado por dirección y reparto de §15.4.4.
    rebar_options_x: list[RebarAlternative] = []
    rebar_options_y: list[RebarAlternative] = []
    short_direction: ShortDirectionDistribution | None = None

    # L4 y L3
    rebar_geometry: FootingRebarGeometry | None = None
    development_x: DevelopmentCheckResult | None = None
    development_y: DevelopmentCheckResult | None = None
    stability: StabilityResult | None = None

    governing_combos: GoverningCombos

    overall_status: CheckStatus
    discard_reasons: list[str]
    trace: CalculationTrace

    depth_trials: list[DepthTrialResult] = []
