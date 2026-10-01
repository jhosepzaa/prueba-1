"""Generador de geometría B-L. SOLO dimensionamiento (enumerar candidatos válidos
por rango/relación L-B) -- explícitamente separado del optimizador/ranking (punto
3 del encargo original y punto 3 de la corrección de Fase 2, que en Fase 2 aún no
existe: el ranking llega en Fase 4).

No aplica ningún criterio de "mejor" candidato -- simplemente enumera todas las
combinaciones (B, L) dentro de los parámetros de búsqueda, respetando la relación
máxima L/B en cualquiera de los dos sentidos (L/B o B/L).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from engine.domain.search_parameters import GeometrySearchParameters


@dataclass(frozen=True)
class GeometryCandidate:
    B_m: float
    L_m: float


def _frange(start: float, stop: float, step: float) -> list[float]:
    values = []
    v = start
    # tolerancia numérica para no perder el último valor por redondeo de punto flotante
    while v <= stop + 1e-9:
        values.append(round(v, 6))
        v += step
    return values


def count_pruned_by_ratio(params: GeometrySearchParameters) -> int:
    """Parejas (B, L) de la malla que la relación máxima L/B deja fuera.

    POR QUÉ SE CUENTA (2026-09-24). Estas geometrías NO se generan, de modo que tampoco
    aparecen entre las descartadas: no quedaba ni rastro de que existieran. Y el límite es
    criterio del programa —`max_LB_ratio` vale 2 por omisión—, mientras que E.050 art. 23.3
    clasifica como zapata hasta L/B = 10. Para una carga muy excéntrica la solución
    razonable suele ser alargada, así que el usuario tiene que saber que ahí no se miró."""
    fuera = 0
    for B in _frange(params.B_min_m, params.B_max_m, params.B_step_m):
        for L in _frange(params.L_min_m, params.L_max_m, params.L_step_m):
            if max(B, L) / min(B, L) > params.max_LB_ratio:
                fuera += 1
    return fuera


def pruning_note(pruned: int, max_ratio: float) -> str:
    """Lo que se le dice al proyectista cuando la relación L/B dejó fuera geometrías."""
    if pruned <= 0:
        return ""
    return (
        f"{pruned} geometrías de la malla no se evaluaron porque su relación L/B supera "
        f"el máximo declarado ({max_ratio:g}). No figuran entre las descartadas porque no "
        f"llegaron a generarse. Es un parámetro de BÚSQUEDA, no un límite normativo: "
        f"E.050 art. 23.3 admite hasta L/B = 10 antes de considerar el elemento una "
        f"cimentación continua. Si la carga es muy excéntrica, la solución razonable "
        f"puede ser una zapata alargada que este límite está escondiendo."
    )


def generate_geometry_candidates(params: GeometrySearchParameters) -> Iterator[GeometryCandidate]:
    for B in _frange(params.B_min_m, params.B_max_m, params.B_step_m):
        for L in _frange(params.L_min_m, params.L_max_m, params.L_step_m):
            ratio = max(B, L) / min(B, L)
            if ratio <= params.max_LB_ratio:
                yield GeometryCandidate(B_m=B, L_m=L)
