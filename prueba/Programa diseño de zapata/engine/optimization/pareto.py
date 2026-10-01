"""Frente de Pareto (mejora #5 propuesta en la Fase 1, punto 7 del usuario).

Motivación: el score ponderado comprime varios objetivos en un solo número, y ese
número depende de pesos que el ingeniero eligió con criterio subjetivo. El frente
de Pareto muestra el compromiso REAL antes de aplicar cualquier peso: qué
alternativas no pueden mejorarse en un objetivo sin empeorar otro.

Una alternativa A DOMINA a B si A es al menos tan buena en todos los objetivos y
estrictamente mejor en al menos uno. El frente es el conjunto no dominado.

Todos los objetivos aquí se MINIMIZAN (volumen, acero, dimensión, complejidad).
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from engine.optimization.alternative_generator import Alternative
from engine.optimization.metrics import AlternativeMetrics

# Objetivos disponibles, todos a minimizar, definidos sobre las MÉTRICAS.
#
# Fase 4G. Se definen sobre `AlternativeMetrics` y no sobre `Alternative` porque las tres
# tipologías producen ese mismo tipo de métricas: así el frente de la zapata conectada
# sale del MISMO criterio de dominancia que el de la aislada, sin una segunda versión.
METRIC_OBJECTIVES: dict[str, Callable[[AlternativeMetrics], float]] = {
    "volumen_concreto": lambda m: m.concrete_volume_m3,
    "masa_acero": lambda m: m.steel_mass_kg,
    "dimension_maxima": lambda m: m.max_plan_dimension_m,
    "complejidad_constructiva": lambda m: m.constructive_complexity_index,
    "area": lambda m: m.footing_area_m2,
    "excavacion": lambda m: m.excavation_volume_m3,
}

# Contrato anterior, intacto: los mismos objetivos, leídos desde la alternativa aislada.
PARETO_OBJECTIVES: dict[str, Callable[[Alternative], float]] = {
    name: (lambda f: (lambda a: f(a.metrics)))(fn) for name, fn in METRIC_OBJECTIVES.items()
}

DEFAULT_OBJECTIVES = ("volumen_concreto", "masa_acero", "dimension_maxima")


class ParetoResult(BaseModel):
    objectives: list[str]
    front: list[Alternative]
    dominated_count: int

    @property
    def front_size(self) -> int:
        return len(self.front)


def _dominates(a_values: list[float], b_values: list[float]) -> bool:
    """¿`a` domina a `b`? (todos <= y al menos uno <)"""
    not_worse = all(a <= b + 1e-12 for a, b in zip(a_values, b_values))
    strictly_better = any(a < b - 1e-12 for a, b in zip(a_values, b_values))
    return not_worse and strictly_better


def _check_objectives(objectives: tuple[str, ...]) -> None:
    for name in objectives:
        if name not in METRIC_OBJECTIVES:
            raise ValueError(
                f'Objetivo "{name}" no reconocido. Disponibles: {sorted(METRIC_OBJECTIVES)}'
            )


def pareto_mask(
    metrics: list[AlternativeMetrics], objectives: tuple[str, ...] = DEFAULT_OBJECTIVES
) -> list[bool]:
    """¿Pertenece cada conjunto de métricas al frente no dominado?

    Núcleo único de la dominancia, para cualquier tipología. `pareto_front` lo usa, de
    modo que la aislada conserva exactamente su frente."""
    _check_objectives(objectives)
    vectors = [[METRIC_OBJECTIVES[name](m) for name in objectives] for m in metrics]
    return [
        not any(_dominates(other, candidate) for j, other in enumerate(vectors) if j != i)
        for i, candidate in enumerate(vectors)
    ]


def pareto_front(
    alternatives: list[Alternative], objectives: tuple[str, ...] = DEFAULT_OBJECTIVES
) -> ParetoResult:
    _check_objectives(objectives)
    if not alternatives:
        return ParetoResult(objectives=list(objectives), front=[], dominated_count=0)

    mask = pareto_mask([a.metrics for a in alternatives], objectives)
    front = [a for a, in_front in zip(alternatives, mask) if in_front]

    return ParetoResult(
        objectives=list(objectives), front=front, dominated_count=len(alternatives) - len(front)
    )
