"""Generación de alternativas (Fase 3).

Recorre la grilla de geometrías (B, L) y, para cada una, resuelve el peralte h
mínimo viable. Conserva TODAS las geometrías evaluadas: las que producen una
alternativa válida y las que se descartan, estas últimas con la razón exacta
(sección 12 del encargo original).

SEPARACIÓN EXPLÍCITA (punto 3 de la corrección del usuario a la Fase 2):
este módulo NO ordena, NO puntúa y NO elige "la mejor". Solo genera y caracteriza
el conjunto de alternativas. El ranking ponderado es responsabilidad de la Fase 4.
Por eso `AlternativeSet.valid` se devuelve en el orden de generación (barrido de
la grilla), no en un orden de calidad.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from engine.codes.base import IConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters, GeometrySearchParameters
from engine.domain.soil import SoilProfile
from engine.foundation.depth_solver import evaluate_candidate, solve_depth
from engine.foundation.geometry_generator import (
    count_pruned_by_ratio,
    generate_geometry_candidates,
)
from engine.optimization.metrics import AlternativeMetrics, compute_metrics
from engine.results.footing_candidate import DepthTrialResult, FootingCandidate
from engine.results.status import CheckStatus


# Peraltes adicionales que se prueban por encima del mínimo viable de cada planta.
#
# Tres pasos cubren el tramo donde el acero todavía puede bajar —el cambio de diámetro
# o de separación ocurre en uno o dos incrementos— sin multiplicar el costo del barrido:
# solo se prueban en las plantas que YA tienen una alternativa válida, y se paran en
# cuanto el acero deja de mejorar. Es un límite de BÚSQUEDA, no un criterio de diseño.
EXTRA_DEPTH_STEPS = 3

# Dos diseños con la misma parrilla pueden diferir unos gramos por redondeo del peso.
# Por debajo de este umbral no se considera que el acero haya bajado.
_TOLERANCIA_ACERO_KG = 0.5


class Alternative(BaseModel):
    """Una geometría (B, L, h) que superó todas las verificaciones."""

    id: str
    candidate: FootingCandidate
    metrics: AlternativeMetrics


class DiscardedAlternative(BaseModel):
    """Una geometría (B, L) para la que ningún h del rango resultó válido."""

    id: str
    B_m: float
    L_m: float
    h_range_tried_m: tuple[float, float]
    n_depths_tried: int
    pruned_early: bool
    prune_reason: str | None
    # Candidato representativo (el último h evaluado, que es el estructuralmente
    # más favorable salvo poda) -- conserva el CalculationTrace completo para que
    # el explicador de descartes pueda detallar qué pasó y qué no.
    representative: FootingCandidate | None
    trials: list[DepthTrialResult]


class AlternativeSet(BaseModel):
    valid: list[Alternative] = Field(default_factory=list)
    discarded: list[DiscardedAlternative] = Field(default_factory=list)
    pruned_by_LB_ratio: int = Field(
        default=0,
        description=(
            "Parejas (B, L) que la relación máxima L/B dejó fuera de la malla. No se "
            "evaluaron, así que tampoco figuran entre las descartadas."
        ),
    )
    geometries_evaluated: int = Field(
        default=0,
        description=(
            "Plantas (B, L) evaluadas. Desde 2026-09-24 una misma planta puede aportar "
            "VARIAS alternativas —peraltes que no se dominan entre sí—, de modo que el "
            "número de alternativas ya no coincide con el de geometrías."
        ),
    )

    @property
    def n_geometries_evaluated(self) -> int:
        # Hasta 2026-09-24 bastaba `len(valid) + len(discarded)`, porque cada planta
        # producía como mucho una alternativa. Ahora el recuento se lleva explícito; el
        # cálculo antiguo queda de reserva para conjuntos construidos a mano en tests.
        return self.geometries_evaluated or (len(self.valid) + len(self.discarded))

    def discard_reason_histogram(self) -> dict[str, int]:
        """Cuántas geometrías fueron descartadas por cada motivo. Útil para que el
        ingeniero entienda qué está limitando la búsqueda (p. ej. "480 descartadas
        por qmax > qadm" indica que el rango de B-L es demasiado pequeño para el
        suelo disponible)."""
        histogram: dict[str, int] = {}
        for item in self.discarded:
            if item.representative is None:
                continue
            for reason in item.representative.discard_reasons:
                histogram[reason] = histogram.get(reason, 0) + 1
        return histogram


def generate_alternatives(
    column: Column,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    load_case_set: LoadCaseSet,
    code: IConcreteCode,
    contact_model,
    geometry_params: GeometrySearchParameters,
    depth_params: DepthSearchParameters,
    placement: ColumnPlacement | None = None,
) -> AlternativeSet:
    result = AlternativeSet()
    cover_m = (
        depth_params.cover_override_mm if depth_params.cover_override_mm is not None else code.cover_footing_mm()[0]
    ) / 1000.0

    valid_counter = 0
    discarded_counter = 0
    valid_geometries = 0

    for geometry in generate_geometry_candidates(geometry_params):
        # Una geometría que no puede alojar la columna no es un "descarte de
        # diseño", es una entrada geométricamente imposible: se omite en silencio.
        # Con la columna descentrada (Fase 1B) no basta comparar dimensiones: hay
        # que comprobar que la columna quepa EN SU POSICIÓN.
        if placement is not None and not placement.is_concentric:
            if not placement.fits_inside(geometry.B_m, geometry.L_m):
                continue
        elif geometry.B_m <= column.bx_m or geometry.L_m <= column.by_m:
            continue

        solved = solve_depth(
            geometry.B_m, geometry.L_m, column, soil, concrete, steel,
            load_case_set, code, contact_model, depth_params, placement,
        )

        if solved.accepted is not None:
            valid_counter += 1
            valid_geometries += 1
            metricas = compute_metrics(solved.accepted, soil.Df_m, cover_m)
            result.valid.append(
                Alternative(
                    id=f"ALT-{valid_counter:03d}",
                    candidate=solved.accepted,
                    metrics=metricas,
                )
            )
        else:
            discarded_counter += 1
            h_tried = [t.h_m for t in solved.trials]
            result.discarded.append(
                DiscardedAlternative(
                    id=f"DESC-{discarded_counter:03d}",
                    B_m=geometry.B_m,
                    L_m=geometry.L_m,
                    h_range_tried_m=(min(h_tried), max(h_tried)) if h_tried else (0.0, 0.0),
                    n_depths_tried=len(solved.trials),
                    pruned_early=solved.pruned_early,
                    prune_reason=solved.prune_reason,
                    representative=solved.last_evaluated,
                    trials=solved.trials,
                )
            )

    result.geometries_evaluated = valid_geometries + discarded_counter
    result.pruned_by_LB_ratio = count_pruned_by_ratio(geometry_params)

    # SEGUNDA PASADA: peraltes alternativos SOLO donde está el compromiso.
    #
    # Para cada planta, la primera pasada se queda con el peralte mínimo viable. Eso
    # deja fuera diseños que no están dominados —más concreto y menos acero—, y con
    # ellos el frente de Pareto de la pantalla no era el frente real.
    #
    # Refinarlas TODAS costaba el triple de tiempo y triplicaba la tabla con variantes
    # de plantas que ya estaban dominadas por otras: ruido caro. Se refinan las del
    # frente, que son exactamente las que representan el compromiso entre objetivos.
    #
    # LIMITACIÓN DECLARADA: una variante de peralte de una planta dominada podría, en
    # teoría, entrar en el frente real y aquí no se busca. Es estrategia de búsqueda,
    # como el rango automático, y se declara en lugar de disimularse.
    if result.valid:
        # Import local: `pareto` importa `Alternative` de este módulo, y hacerlo arriba
        # cerraría el ciclo.
        from engine.optimization.pareto import DEFAULT_OBJECTIVES, pareto_mask

        mascara = pareto_mask([a.metrics for a in result.valid], DEFAULT_OBJECTIVES)
        for alternativa, en_frente in zip(list(result.valid), mascara):
            if not en_frente:
                continue
            c = alternativa.candidate
            for extra in _peraltes_no_dominados(
                c.B_m, c.L_m, c.h_m, alternativa.metrics.steel_mass_kg,
                c.flexure_x, c.flexure_y,
                column, soil, concrete, steel, load_case_set, code, contact_model,
                depth_params, placement, cover_m,
            ):
                valid_counter += 1
                extra.id = f"ALT-{valid_counter:03d}"
                result.valid.append(extra)

    return result


def _gobierna_el_minimo(flexion) -> bool:
    """¿El acero de esa dirección lo fija la cuantía mínima y no la flexión?

    `As_required` es NaN cuando no hay momento que resistir: ahí manda el mínimo."""
    requerido = flexion.As_required_m2
    return math.isnan(requerido) or requerido <= flexion.As_min_m2


def _peraltes_no_dominados(
    B_m: float,
    L_m: float,
    h_minimo_m: float,
    acero_minimo_kg: float,
    aceptado_x,
    aceptado_y,
    column: Column,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    load_case_set: LoadCaseSet,
    code: IConcreteCode,
    contact_model,
    depth_params: DepthSearchParameters,
    placement: ColumnPlacement | None,
    cover_m: float,
) -> list[Alternative]:
    """Peraltes por encima del mínimo viable que NINGUNO domina.

    POR QUÉ EXISTE (2026-09-24)
    El barrido tomaba, para cada planta, el primer peralte que no falla, y ahí se
    detenía. Eso deja fuera diseños que no están dominados: en una planta de 4,20 × 4,20 m
    medida, h = 0,50 m da 8,82 m³ de concreto y 315,8 kg de acero, y h = 0,55 m da
    9,70 m³ y 278,9 kg — más concreto y un 12 % menos de acero—. Ninguna es peor que la
    otra: son puntos distintos del compromiso, y el programa presentaba un «frente de
    Pareto» que en la dirección del peralte no lo era.

    CRITERIO DE DOMINANCIA
    El volumen de concreto crece siempre con el peralte y la planta no cambia, de modo
    que un peralte mayor solo es interesante si BAJA el acero respecto de todos los ya
    conservados para esa planta. Esa es exactamente la condición de no dominancia sobre
    (concreto, acero), y se comprueba sin suponer nada más.

    Es ESTRATEGIA DE BÚSQUEDA, no ingeniería: cada peralte que se conserva se verifica
    con las mismas ecuaciones y el mismo criterio de aceptación —solo FAIL descarta— que
    el mínimo. Lo único que cambia es que ahora también se miran.
    """
    encontrados: list[Alternative] = []

    # PARADA CON FUNDAMENTO, no por ahorro a ciegas. `As_min = ρ_min·b·h` (E.060 §9.7)
    # CRECE con el peralte. Si en las dos direcciones el acero ya lo gobierna el mínimo,
    # un peralte mayor solo puede pedir MÁS acero y más concreto: está dominado con
    # seguridad y no hace falta evaluarlo. Así el barrido no paga por mirar donde se
    # sabe que no hay nada.
    if _gobierna_el_minimo(aceptado_x) and _gobierna_el_minimo(aceptado_y):
        return encontrados

    acero_tope = acero_minimo_kg
    h = round(h_minimo_m + depth_params.h_step_m, 6)

    for _ in range(EXTRA_DEPTH_STEPS):
        if h > depth_params.h_max_m + 1e-9:
            break
        candidato = evaluate_candidate(
            B_m, L_m, h, column, soil, concrete, steel, load_case_set, code,
            contact_model, depth_params, placement,
        )
        if candidato.overall_status is not CheckStatus.FAIL:
            metricas = compute_metrics(candidato, soil.Df_m, cover_m)
            if metricas.steel_mass_kg < acero_tope - _TOLERANCIA_ACERO_KG:
                acero_tope = metricas.steel_mass_kg
                encontrados.append(
                    Alternative(id="", candidate=candidato, metrics=metricas)
                )
            # A partir del peralte en que el mínimo gobierna las dos direcciones, el
            # acero solo puede crecer y el concreto también: todo lo que venga después
            # está dominado. Se para aquí por la misma razón demostrable de arriba.
            if _gobierna_el_minimo(candidato.flexure_x) and _gobierna_el_minimo(
                candidato.flexure_y
            ):
                break
        h = round(h + depth_params.h_step_m, 6)

    return encontrados
