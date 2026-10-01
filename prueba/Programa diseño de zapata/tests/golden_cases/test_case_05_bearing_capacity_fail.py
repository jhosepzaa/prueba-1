"""CASO 05 -- Falla por capacidad portante (zapata deliberadamente subdimensionada).

B=L=1.0 m, mismas cargas de servicio del caso 01 (P=400 kN) -> q_avg muy por
encima de qadm=150 kPa. Verificado a mano:
    W_total = 24*1*1*0.5 + 18*1*1*0.7 = 12 + 12.6 = 24.6 kN
    P_total = 424.6 kN ; A = 1.0 m2 -> q = 424.6 kPa >> 150 kPa
"""

import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
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


def test_case_05_fails_bearing_pressure():
    candidate = evaluate_candidate(
        B_m=1.0, L_m=1.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert candidate.contact_pressure.qmax_kPa == pytest.approx(424.6, rel=1e-3)
    assert candidate.overall_status == CheckStatus.FAIL
    assert any("qmax > qadm" in reason for reason in candidate.discard_reasons)
