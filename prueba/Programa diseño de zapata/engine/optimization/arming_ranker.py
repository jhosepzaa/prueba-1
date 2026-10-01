"""Clasificación de soluciones de armado.

Criterios (todos a minimizar), configurables e independientes de los pesos que
ordenan la GEOMETRÍA -- son decisiones distintas: elegir la zapata y elegir cómo
armarla no responden al mismo compromiso.

    Score = w_acero        * masa_de_acero_normalizada
          + w_complejidad  * complejidad_constructiva_normalizada
          + w_desperdicio  * desperdicio_de_acero_normalizado
          + w_n_barras     * número_de_barras_normalizado

Ninguno es normativo: son criterios de proyecto.

La normalización min-max se hace DENTRO del conjunto que se está clasificando,
igual que en `scoring.py`, para que los pesos sean comparables entre sí.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from engine.optimization.arming_solutions import ArmingSolution
from engine.optimization.scoring import MetricBreakdown
from engine.results.status import CheckStatus


class ArmingScoreWeights(BaseModel):
    w_steel_mass: float = Field(default=0.45, ge=0.0)
    w_constructive_complexity: float = Field(default=0.25, ge=0.0)
    w_steel_waste: float = Field(default=0.20, ge=0.0)
    w_bar_count: float = Field(default=0.10, ge=0.0)

    @model_validator(mode="after")
    def _at_least_one_positive(self) -> "ArmingScoreWeights":
        if self.total() <= 0:
            raise ValueError("Al menos un peso debe ser mayor que cero.")
        return self

    def total(self) -> float:
        return self.w_steel_mass + self.w_constructive_complexity + self.w_steel_waste + self.w_bar_count


class ScoredArmingSolution(BaseModel):
    solution: ArmingSolution
    score: float
    breakdown: dict[str, MetricBreakdown]
    rank: int = 0


class ArmingRankingResult(BaseModel):
    top: list[ScoredArmingSolution]
    all_scored: list[ScoredArmingSolution]
    weights: ArmingScoreWeights
    n_solutions: int
    n_geometries: int

    def best(self) -> ScoredArmingSolution | None:
        return self.top[0] if self.top else None


_ARMING_METRICS: dict[str, tuple] = {
    "masa_acero": (lambda s: s.metrics.steel_mass_kg, "w_steel_mass"),
    "complejidad_constructiva": (lambda s: s.metrics.constructive_complexity_index, "w_constructive_complexity"),
    "desperdicio_acero": (lambda s: s.metrics.steel_waste_ratio, "w_steel_waste"),
    "numero_barras": (lambda s: float(s.metrics.total_bars), "w_bar_count"),
}


def _normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def rank_arming_solutions(
    solutions: list[ArmingSolution], weights: ArmingScoreWeights | None = None, top_n: int = 5
) -> ArmingRankingResult:
    weights = weights or ArmingScoreWeights()
    if not solutions:
        return ArmingRankingResult(
            top=[], all_scored=[], weights=weights, n_solutions=0, n_geometries=0
        )

    weight_total = weights.total()
    raw_by_metric: dict[str, list[float]] = {}
    norm_by_metric: dict[str, list[float]] = {}
    for name, (extractor, _) in _ARMING_METRICS.items():
        raw = [extractor(s) for s in solutions]
        raw_by_metric[name] = raw
        norm_by_metric[name] = _normalize(raw)

    scored: list[ScoredArmingSolution] = []
    for i, solution in enumerate(solutions):
        breakdown: dict[str, MetricBreakdown] = {}
        score = 0.0
        for name, (_, weight_attr) in _ARMING_METRICS.items():
            w = getattr(weights, weight_attr) / weight_total
            normalized = norm_by_metric[name][i]
            contribution = w * normalized
            score += contribution
            breakdown[name] = MetricBreakdown(
                raw_value=raw_by_metric[name][i], normalized=normalized, weight=w, contribution=contribution
            )
        scored.append(ScoredArmingSolution(solution=solution, score=score, breakdown=breakdown))

    scored.sort(key=lambda s: (s.score, s.solution.metrics.steel_mass_kg, s.solution.id))
    for position, item in enumerate(scored, start=1):
        item.rank = position

    return ArmingRankingResult(
        top=scored[:top_n],
        all_scored=scored,
        weights=weights,
        n_solutions=len(solutions),
        n_geometries=len({s.geometry_id for s in solutions}),
    )


def render_arming_ranking_text(result: ArmingRankingResult, limit: int | None = None) -> str:
    rows = result.top if limit is None else result.top[:limit]
    header = (
        f"{'#':<3} {'ID':<14} {'Geom':<9} {'B x L x h':<18} {'Acero X':<17} {'Acero Y':<17} "
        f"{'kg':>7} {'Barras':>6} {'Uso':>5} {'Compl':>6} {'SCORE':>7} {'Estado':<8}"
    )
    lines = [header, "-" * len(header)]
    for item in rows:
        s = item.solution
        c = s.candidate
        geom = f"{c.B_m:.2f}x{c.L_m:.2f}x{c.h_m:.2f}"
        lines.append(
            f"{item.rank:<3} {s.id:<14} {s.geometry_id:<9} {geom:<18} "
            f"{s.rebar_x.label:<17} {s.rebar_y.label:<17} "
            f"{s.metrics.steel_mass_kg:>7.1f} {s.metrics.total_bars:>6d} "
            f"{s.metrics.mean_utilization:>5.2f} {s.metrics.constructive_complexity_index:>6.2f} "
            f"{item.score:>7.4f} {s.status.value:<8}"
        )
    lines.append("")
    lines.append(
        f"{result.n_solutions} soluciones de armado sobre {result.n_geometries} geometrías. "
        f"Masa de acero calculada con longitud RECTA: no incluye ganchos ni traslapes."
    )
    return "\n".join(lines)
