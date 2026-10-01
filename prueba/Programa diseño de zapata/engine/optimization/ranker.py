"""Ranking de alternativas y selección de las N mejores (secciones 10 y 11).

Este es el ÚNICO módulo del motor que decide "cuál es mejor". El generador de
alternativas (Fase 3) y el solver de peralte (Fase 2) deliberadamente no lo hacen
-- la separación dimensionamiento / optimización que exigió el usuario.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.optimization.alternative_generator import AlternativeSet
from engine.optimization.pareto import DEFAULT_OBJECTIVES, ParetoResult, pareto_front
from engine.optimization.scoring import ScoredAlternative, ScoreWeights, score_alternatives
from engine.results.status import CheckStatus


class RankingResult(BaseModel):
    top: list[ScoredAlternative]
    all_scored: list[ScoredAlternative]
    pareto: ParetoResult
    weights: ScoreWeights
    n_with_warnings: int

    def best(self) -> ScoredAlternative | None:
        return self.top[0] if self.top else None


def rank_alternatives(
    alternative_set: AlternativeSet,
    weights: ScoreWeights | None = None,
    top_n: int = 5,
    pareto_objectives: tuple[str, ...] = DEFAULT_OBJECTIVES,
) -> RankingResult:
    weights = weights or ScoreWeights()
    scored = score_alternatives(alternative_set.valid, weights)

    # Orden: menor score primero. Ante empate exacto, se desempata por volumen de
    # concreto y luego por id, para que el resultado sea determinista.
    scored.sort(key=lambda s: (s.score, s.alternative.metrics.concrete_volume_m3, s.alternative.id))
    for position, item in enumerate(scored, start=1):
        item.rank = position

    return RankingResult(
        top=scored[:top_n],
        all_scored=scored,
        pareto=pareto_front(alternative_set.valid, pareto_objectives),
        weights=weights,
        n_with_warnings=sum(
            1 for a in alternative_set.valid if a.candidate.overall_status is CheckStatus.WARNING
        ),
    )


def render_ranking_text(result: RankingResult, limit: int | None = None) -> str:
    rows = result.top if limit is None else result.top[:limit]
    header = (
        f"{'#':<3} {'ID':<9} {'B[m]':>5} {'L[m]':>5} {'h[m]':>5} "
        f"{'V.conc':>7} {'Acero':>8} {'Dmax':>6} {'Compl':>6} {'SCORE':>7} {'Estado':<8}"
    )
    lines = [header, "-" * len(header)]
    for item in rows:
        c = item.alternative.candidate
        m = item.alternative.metrics
        lines.append(
            f"{item.rank:<3} {item.alternative.id:<9} {c.B_m:>5.2f} {c.L_m:>5.2f} {c.h_m:>5.2f} "
            f"{m.concrete_volume_m3:>7.3f} {m.steel_mass_kg:>8.1f} {m.max_plan_dimension_m:>6.2f} "
            f"{m.constructive_complexity_index:>6.2f} {item.score:>7.4f} {c.overall_status.value:<8}"
        )
    if result.n_with_warnings:
        lines.append("")
        lines.append(
            f"NOTA: {result.n_with_warnings} de {len(result.all_scored)} alternativas válidas "
            f"tienen al menos un WARNING (revisar antes de adoptar)."
        )
    return "\n".join(lines)
