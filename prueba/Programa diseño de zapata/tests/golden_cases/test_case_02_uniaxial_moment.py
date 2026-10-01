"""CASO 02 -- Zapata rectangular con momento en una dirección (My != 0, Mx = 0).

Verificado a mano:
    B=2.4 L=2.0 h=0.5, W_total=118.08 kN
    S1: P=350, My=60 -> P_total=468.08, ey=My/P_total=0.1282 (dentro del núcleo, L/6=0.333)
    (convención E.050 art. 28.1: My desplaza la resultante a lo largo de Y, contra L)
    qmax = 97.52*(1+0.3846) = 135.05 kPa < qadm=150 -> PASS
    qmin = 97.52*(1-0.3846) = 60.03 kPa (positivo, confirma dentro del núcleo)
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
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=350.0, My_kNm=60.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0, My_kNm=90.0)],
)


def test_case_02_contact_pressure_within_kern():
    candidate = evaluate_candidate(
        B_m=2.4, L_m=2.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert candidate.contact_pressure.within_kern is True
    assert candidate.contact_pressure.qmax_kPa == pytest.approx(135.05, rel=1e-3)
    assert candidate.contact_pressure.qmin_kPa == pytest.approx(60.03, rel=1e-3)
    assert candidate.contact_pressure.qmax_kPa < 150.0

    # Mx genera ey (no ex): la flexión relevante es en dirección Y.
    assert candidate.eccentricity_governing.ex_m == pytest.approx(0.0)
    assert candidate.eccentricity_governing.ey_m > 0.0
