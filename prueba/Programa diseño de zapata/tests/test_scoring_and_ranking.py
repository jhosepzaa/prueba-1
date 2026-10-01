import pytest
from pydantic import ValidationError

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import GeometrySearchParameters
from engine.optimization.alternative_generator import generate_alternatives
from engine.optimization.pareto import PARETO_OBJECTIVES, pareto_front
from engine.optimization.ranker import rank_alternatives, render_ranking_text
from engine.optimization.scoring import ScoreWeights, score_alternatives
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0)],
)
GEOM = GeometrySearchParameters(
    B_min_m=1.4, B_max_m=3.0, B_step_m=0.2, L_min_m=1.4, L_max_m=3.0, L_step_m=0.2, max_LB_ratio=1.6
)


def _alternatives():
    return generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GEOM, depth_params=DEPTH_PARAMS_DEFAULT,
    )


# --- Pesos -----------------------------------------------------------------------

def test_default_weights_are_valid_and_positive():
    w = ScoreWeights()
    assert w.total() > 0
    assert w.w_monetary_cost is None  # no hay base de precios en el MVP


def test_monetary_cost_weight_is_rejected_until_price_base_exists():
    with pytest.raises(ValidationError, match="base de precios"):
        ScoreWeights(w_monetary_cost=0.5)


def test_all_zero_weights_rejected():
    with pytest.raises(ValidationError):
        ScoreWeights(
            w_concrete_volume=0.0, w_steel_mass=0.0, w_max_dimension=0.0, w_constructive_complexity=0.0
        )


# --- Normalización y score --------------------------------------------------------

def test_scores_are_bounded_in_unit_interval():
    scored = score_alternatives(_alternatives().valid)
    for s in scored:
        assert 0.0 <= s.score <= 1.0 + 1e-12


def test_breakdown_contributions_sum_to_score():
    scored = score_alternatives(_alternatives().valid)
    for s in scored:
        total = sum(b.contribution for b in s.breakdown.values())
        assert total == pytest.approx(s.score)


def test_breakdown_exposes_raw_values_for_auditability():
    scored = score_alternatives(_alternatives().valid)
    s = scored[0]
    assert s.breakdown["volumen_concreto"].raw_value == pytest.approx(
        s.alternative.metrics.concrete_volume_m3
    )
    assert s.breakdown["masa_acero"].raw_value == pytest.approx(s.alternative.metrics.steel_mass_kg)


def test_normalized_weights_sum_to_one():
    scored = score_alternatives(_alternatives().valid)
    weights_sum = sum(b.weight for b in scored[0].breakdown.values())
    assert weights_sum == pytest.approx(1.0)


def test_identical_metric_across_pool_does_not_divide_by_zero():
    alts = _alternatives().valid[:1]  # un solo elemento -> min == max en todo
    scored = score_alternatives(alts)
    assert scored[0].score == pytest.approx(0.0)


def test_empty_pool_returns_empty():
    assert score_alternatives([]) == []


# --- El peso cambia el resultado ---------------------------------------------------

def test_weights_actually_change_the_winner():
    """Si los pesos no cambiaran nada, la función de puntuación sería decorativa."""
    alt_set = _alternatives()
    only_volume = rank_alternatives(
        alt_set,
        ScoreWeights(w_concrete_volume=1.0, w_steel_mass=0.0, w_max_dimension=0.0, w_constructive_complexity=0.0),
    )
    only_steel = rank_alternatives(
        alt_set,
        ScoreWeights(w_concrete_volume=0.0, w_steel_mass=1.0, w_max_dimension=0.0, w_constructive_complexity=0.0),
    )
    # el mínimo de cada criterio debe coincidir con el ganador bajo ese criterio
    assert only_volume.best().alternative.metrics.concrete_volume_m3 == pytest.approx(
        min(a.metrics.concrete_volume_m3 for a in alt_set.valid)
    )
    assert only_steel.best().alternative.metrics.steel_mass_kg == pytest.approx(
        min(a.metrics.steel_mass_kg for a in alt_set.valid)
    )


def test_balanced_weights_need_not_pick_the_smallest_footing():
    """El usuario pidió explícitamente que el programa NO se limite a encontrar
    'la zapata más pequeña'. Con pesos equilibrados, el ganador puede diferir del
    de volumen mínimo -- este test documenta ese comportamiento sin exigirlo."""
    alt_set = _alternatives()
    balanced = rank_alternatives(alt_set)
    smallest = min(alt_set.valid, key=lambda a: a.metrics.concrete_volume_m3)
    # No se afirma desigualdad (depende del pool); se afirma que el score
    # equilibrado considera efectivamente más de una métrica.
    winner = balanced.best()
    nonzero_metrics = [k for k, b in winner.breakdown.items() if b.weight > 0]
    assert len(nonzero_metrics) >= 3
    assert smallest is not None


# --- Ranking ------------------------------------------------------------------------

def test_ranking_is_sorted_and_ranks_are_sequential():
    result = rank_alternatives(_alternatives(), top_n=5)
    scores = [s.score for s in result.all_scored]
    assert scores == sorted(scores)
    assert [s.rank for s in result.all_scored] == list(range(1, len(result.all_scored) + 1))


def test_top_n_respected():
    result = rank_alternatives(_alternatives(), top_n=5)
    assert len(result.top) <= 5
    assert result.top[0].rank == 1


def test_ranking_is_deterministic():
    a = rank_alternatives(_alternatives(), top_n=5)
    b = rank_alternatives(_alternatives(), top_n=5)
    assert [s.alternative.id for s in a.top] == [s.alternative.id for s in b.top]


def test_render_ranking_text_includes_top_rows():
    result = rank_alternatives(_alternatives(), top_n=5)
    text = render_ranking_text(result)
    assert "SCORE" in text
    for item in result.top:
        assert item.alternative.id in text


# --- Pareto ---------------------------------------------------------------------------

def test_pareto_front_is_non_empty_subset():
    alts = _alternatives().valid
    result = pareto_front(alts)
    assert 0 < result.front_size <= len(alts)
    front_ids = {a.id for a in result.front}
    assert front_ids.issubset({a.id for a in alts})
    assert result.dominated_count == len(alts) - result.front_size


def test_no_front_member_is_dominated_by_any_other_alternative():
    alts = _alternatives().valid
    result = pareto_front(alts)
    objectives = [PARETO_OBJECTIVES[name] for name in result.objectives]
    for member in result.front:
        member_values = [f(member) for f in objectives]
        for other in alts:
            if other.id == member.id:
                continue
            other_values = [f(other) for f in objectives]
            not_worse = all(o <= m + 1e-12 for o, m in zip(other_values, member_values))
            strictly_better = any(o < m - 1e-12 for o, m in zip(other_values, member_values))
            assert not (not_worse and strictly_better), f"{member.id} dominada por {other.id}"


def test_single_objective_front_contains_the_minimum():
    alts = _alternatives().valid
    result = pareto_front(alts, objectives=("volumen_concreto",))
    best_volume = min(a.metrics.concrete_volume_m3 for a in alts)
    assert any(a.metrics.concrete_volume_m3 == pytest.approx(best_volume) for a in result.front)


def test_unknown_objective_rejected():
    with pytest.raises(ValueError, match="no reconocido"):
        pareto_front(_alternatives().valid, objectives=("costo_monetario",))


def test_ranking_reports_how_many_alternatives_carry_warnings():
    result = rank_alternatives(_alternatives())
    assert result.n_with_warnings >= 0
    assert result.n_with_warnings <= len(result.all_scored)
