"""CASO 04 -- Excentricidad cercana al límite del núcleo central (B/6).

B=L=1.5 m -> B/6 = 0.25 m. Se construye My tal que ex quede justo debajo y justo
encima del límite, usando el mismo P_total en ambos para aislar el efecto de la
excentricidad.
"""

import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

# P_total = 1000 (columna) + ~54 (peso propio, B=L=1.5, h=0.4) = 1054 kN
P_TOTAL_APPROX = 1054.0
B = L = 1.5
KERN_LIMIT = B / 6.0  # 0.25 m


def _loads_with_my(my: float) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=1000.0, My_kNm=my)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=1400.0, My_kNm=my * 1.4)],
    )


def test_just_inside_kern_passes_bearing_check():
    my = 0.24 * P_TOTAL_APPROX  # ex objetivo ~0.24 < 0.25
    candidate = evaluate_candidate(
        B_m=B, L_m=L, h_m=0.40,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=_loads_with_my(my), code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert candidate.contact_pressure.within_kern is True
    assert candidate.eccentricity_governing.ex_m < KERN_LIMIT


def test_just_outside_kern_is_discarded_with_explicit_reason():
    my = 0.30 * P_TOTAL_APPROX  # ex objetivo ~0.30 > 0.25
    candidate = evaluate_candidate(
        B_m=B, L_m=L, h_m=0.40,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=_loads_with_my(my), code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert candidate.contact_pressure.within_kern is False
    assert any("núcleo central" in reason for reason in candidate.discard_reasons)
