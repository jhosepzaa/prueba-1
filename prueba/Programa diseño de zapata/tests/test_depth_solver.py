from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import solve_depth
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

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0)],
)


def test_solve_depth_finds_minimum_viable_h_and_keeps_full_history():
    result = solve_depth(
        B_m=2.0, L_m=2.0,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert result.accepted is not None
    # El solver acepta PASS o WARNING; solo FAIL descarta.
    assert result.accepted.overall_status is not CheckStatus.FAIL
    assert result.accepted.trace.failing_entries() == []
    assert len(result.trials) >= 1
    # todos los h antes del aceptado deben haber FALLADO (si no, el solver se
    # habría detenido antes)
    for trial in result.trials[:-1]:
        assert trial.overall_status is CheckStatus.FAIL
    assert result.trials[-1].h_m == result.accepted.h_m
    # el h aceptado nunca debe superar h_max
    assert result.accepted.h_m <= DEPTH_PARAMS_DEFAULT.h_max_m + 1e-9


def test_solve_depth_returns_none_accepted_when_infeasible():
    # zapata demasiado pequeña: ninguna h en el rango hará que la presión de
    # contacto cumpla (falla geotécnica, no estructural)
    result = solve_depth(
        B_m=1.0, L_m=1.0,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert result.accepted is None
    assert all(t.overall_status != CheckStatus.PASS for t in result.trials)
