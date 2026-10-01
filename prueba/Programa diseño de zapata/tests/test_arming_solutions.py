import pytest
from pydantic import ValidationError

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import GeometrySearchParameters
from engine.optimization.alternative_generator import generate_alternatives
from engine.optimization.arming_ranker import (
    ArmingScoreWeights,
    rank_arming_solutions,
    render_arming_ranking_text,
)
from engine.optimization.arming_solutions import (
    generate_all_arming_solutions,
    generate_arming_solutions,
)
from engine.optimization.metrics import STEEL_DENSITY_KGM3
from engine.optimization.ranker import rank_alternatives
from engine.results.status import CheckStatus
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

COVER_M = 0.070

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Mx_kNm=35.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0, Mx_kNm=49.0)],
)
GEOM = GeometrySearchParameters(
    B_min_m=1.8, B_max_m=3.0, B_step_m=0.2, L_min_m=1.8, L_max_m=3.0, L_step_m=0.2, max_LB_ratio=1.5
)


def _alternatives():
    return generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GEOM, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def _solutions():
    return generate_all_arming_solutions(_alternatives().valid, COVER_M)


# --- Generación de soluciones combinadas -------------------------------------------

def test_generates_cartesian_product_of_direction_options():
    alt = _alternatives().valid[0]
    solutions = generate_arming_solutions(alt, COVER_M)
    expected = len(alt.candidate.rebar_options_x) * len(alt.candidate.rebar_options_y)
    assert len(solutions) == expected
    assert expected > 1, "La geometría debe ofrecer más de un armado posible"


def test_each_solution_has_unique_id_and_links_to_its_geometry():
    alt = _alternatives().valid[0]
    solutions = generate_arming_solutions(alt, COVER_M)
    ids = [s.id for s in solutions]
    assert len(ids) == len(set(ids))
    assert all(s.geometry_id == alt.id for s in solutions)


def test_all_pairs_of_options_are_represented():
    alt = _alternatives().valid[0]
    solutions = generate_arming_solutions(alt, COVER_M)
    pairs = {(s.rebar_x.label, s.rebar_y.label) for s in solutions}
    expected = {
        (x.label, y.label)
        for x in alt.candidate.rebar_options_x
        for y in alt.candidate.rebar_options_y
    }
    assert pairs == expected


def test_max_solutions_is_respected():
    alt = _alternatives().valid[0]
    limited = generate_arming_solutions(alt, COVER_M, max_solutions=3)
    assert len(limited) == 3


def test_generates_solutions_across_all_geometries():
    alt_set = _alternatives()
    solutions = generate_all_arming_solutions(alt_set.valid, COVER_M)
    assert len({s.geometry_id for s in solutions}) == len(alt_set.valid)


# --- Masa de acero ------------------------------------------------------------------

def test_steel_mass_uses_actual_selected_bars_and_straight_length():
    alt = _alternatives().valid[0]
    s = generate_arming_solutions(alt, COVER_M)[0]
    c = s.candidate
    expected_x = s.rebar_x.As_provided_m2 * (c.B_m - 2 * COVER_M) * STEEL_DENSITY_KGM3
    expected_y = s.rebar_y.As_provided_m2 * (c.L_m - 2 * COVER_M) * STEEL_DENSITY_KGM3
    assert s.metrics.steel_mass_x_kg == pytest.approx(expected_x)
    assert s.metrics.steel_mass_y_kg == pytest.approx(expected_y)
    assert s.metrics.steel_mass_kg == pytest.approx(expected_x + expected_y)


def test_steel_mass_declares_it_excludes_hooks_and_laps():
    """Limitación L4: sin longitud de desarrollo implementada, la masa es una
    cota inferior del acero real de obra. El motor debe declararlo."""
    for s in _solutions()[:20]:
        assert s.metrics.steel_mass_excludes_hooks is True


def test_different_arming_solutions_have_different_steel_mass():
    alt = _alternatives().valid[0]
    masses = {round(s.metrics.steel_mass_kg, 6) for s in generate_arming_solutions(alt, COVER_M)}
    assert len(masses) > 1, "Distintos armados deben producir distintas masas de acero"


# --- Constructibilidad y eficiencia --------------------------------------------------

def test_same_diameter_solutions_are_flagged_and_simpler():
    solutions = _solutions()
    same = [s for s in solutions if s.metrics.same_diameter_both_directions]
    different = [s for s in solutions if not s.metrics.same_diameter_both_directions]
    assert same and different
    assert all(s.metrics.n_distinct_diameters == 1 for s in same)
    assert all(s.metrics.n_distinct_diameters == 2 for s in different)
    assert min(s.metrics.constructive_complexity_index for s in same) < min(
        s.metrics.constructive_complexity_index for s in different
    )


def test_complexity_index_within_documented_range():
    for s in _solutions():
        assert 1.0 <= s.metrics.constructive_complexity_index <= 2.5


def test_utilization_and_waste_are_complementary():
    for s in _solutions()[:30]:
        assert s.metrics.mean_utilization == pytest.approx(
            (s.metrics.utilization_x + s.metrics.utilization_y) / 2
        )
        assert s.metrics.steel_waste_ratio == pytest.approx(1.0 - s.metrics.mean_utilization)
        assert 0.0 <= s.metrics.steel_waste_ratio < 1.0


def test_total_bars_is_sum_of_both_directions():
    for s in _solutions()[:20]:
        assert s.metrics.total_bars == s.rebar_x.n_bars + s.rebar_y.n_bars


# --- El armado no puede limpiar una advertencia de la geometría -----------------------

def test_arming_status_inherits_geometry_status():
    alt_set = _alternatives()
    for alt in alt_set.valid:
        for s in generate_arming_solutions(alt, COVER_M):
            assert s.status is alt.candidate.overall_status


def test_no_arming_solution_can_reach_pass_while_limitations_apply():
    for s in _solutions():
        assert s.status is not CheckStatus.PASS


# --- Clasificación ---------------------------------------------------------------------

def test_ranking_is_sorted_and_deterministic():
    solutions = _solutions()
    a = rank_arming_solutions(solutions, top_n=5)
    b = rank_arming_solutions(solutions, top_n=5)
    scores = [s.score for s in a.all_scored]
    assert scores == sorted(scores)
    assert [s.solution.id for s in a.top] == [s.solution.id for s in b.top]
    assert [s.rank for s in a.all_scored] == list(range(1, len(a.all_scored) + 1))


def test_breakdown_contributions_sum_to_score():
    result = rank_arming_solutions(_solutions())
    for item in result.all_scored:
        assert sum(b.contribution for b in item.breakdown.values()) == pytest.approx(item.score)


def test_weight_on_steel_mass_alone_picks_lightest():
    solutions = _solutions()
    result = rank_arming_solutions(
        solutions,
        ArmingScoreWeights(w_steel_mass=1.0, w_constructive_complexity=0.0, w_steel_waste=0.0, w_bar_count=0.0),
    )
    assert result.best().solution.metrics.steel_mass_kg == pytest.approx(
        min(s.metrics.steel_mass_kg for s in solutions)
    )


def test_weight_on_complexity_alone_picks_simplest():
    solutions = _solutions()
    result = rank_arming_solutions(
        solutions,
        ArmingScoreWeights(w_steel_mass=0.0, w_constructive_complexity=1.0, w_steel_waste=0.0, w_bar_count=0.0),
    )
    best = result.best().solution
    assert best.metrics.constructive_complexity_index == pytest.approx(
        min(s.metrics.constructive_complexity_index for s in solutions)
    )
    assert best.metrics.same_diameter_both_directions is True


def test_different_weights_can_pick_different_winners():
    solutions = _solutions()
    lightest = rank_arming_solutions(
        solutions, ArmingScoreWeights(w_steel_mass=1.0, w_constructive_complexity=0.0, w_steel_waste=0.0, w_bar_count=0.0)
    ).best()
    simplest = rank_arming_solutions(
        solutions, ArmingScoreWeights(w_steel_mass=0.0, w_constructive_complexity=1.0, w_steel_waste=0.0, w_bar_count=0.0)
    ).best()
    # Si coincidieran siempre, los pesos no estarían discriminando nada.
    assert lightest.solution.id != simplest.solution.id or len(solutions) == 1


def test_zero_weights_rejected():
    with pytest.raises(ValidationError):
        ArmingScoreWeights(
            w_steel_mass=0.0, w_constructive_complexity=0.0, w_steel_waste=0.0, w_bar_count=0.0
        )


def test_empty_input_returns_empty_ranking():
    result = rank_arming_solutions([])
    assert result.top == []
    assert result.n_solutions == 0


def test_render_declares_that_steel_mass_excludes_hooks_and_laps():
    result = rank_arming_solutions(_solutions(), top_n=5)
    text = render_arming_ranking_text(result)
    assert "no incluye ganchos ni traslapes" in text
    for item in result.top:
        assert item.solution.id in text


def test_arming_ranking_can_be_restricted_to_top_geometries():
    """Flujo previsto: primero se ordenan las geometrías, luego se arman solo las
    mejores -- evita generar miles de soluciones irrelevantes."""
    alt_set = _alternatives()
    top_geometries = [item.alternative for item in rank_alternatives(alt_set, top_n=3).top]
    solutions = generate_all_arming_solutions(top_geometries, COVER_M)
    result = rank_arming_solutions(solutions, top_n=5)
    assert result.n_geometries == 3
    assert result.n_solutions == sum(
        len(a.candidate.rebar_options_x) * len(a.candidate.rebar_options_y) for a in top_geometries
    )
