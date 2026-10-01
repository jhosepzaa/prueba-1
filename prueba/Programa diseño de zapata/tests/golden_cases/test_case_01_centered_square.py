"""CASO 01 -- Zapata cuadrada con carga axial centrada (Mx=My=0).

Verificado a mano (ver conversación de desarrollo / cálculo adjunto):
    B=L=2.0 m, h=0.50 m, d=0.422 m
    W_total = 98.4 kN
    P_servicio_total = 400+98.4 = 498.4 kN -> q_avg = qmax = qmin = 124.6 kPa
    qadm = 150 kPa (BRUTA) -> ratio = 0.83, PASS
    Pu=560 kN (columna, sin peso propio) -> Mu_x=Mu_y=89.6 kN*m
    As_min = 18 cm2 (gobierna sobre As_req~5.65cm2) en ambas direcciones
    Cortante y punzonamiento con amplio margen (ratios ~0.19 y ~0.26)
Resultado esperado: PASS en todas las verificaciones.
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


def test_case_01_no_check_fails():
    candidate = evaluate_candidate(
        B_m=2.0, L_m=2.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    # Ninguna verificación de ingeniería falla.
    assert candidate.discard_reasons == []
    assert candidate.trace.failing_entries() == []
    # Con L4 cerrada y sin fuerzas horizontales ni momentos, PASS es alcanzable.
    assert candidate.overall_status == CheckStatus.PASS
    # Y la longitud de desarrollo es ahora una verificación REAL, no una advertencia.
    assert candidate.development_x.status == CheckStatus.PASS
    assert candidate.development_x.ld_required_m <= candidate.development_x.ld_available_m

    assert candidate.self_weight.W_total_kN == pytest.approx(98.4, rel=1e-3)
    assert candidate.contact_pressure.qmax_kPa == pytest.approx(124.6, rel=1e-3)
    assert candidate.contact_pressure.within_kern is True

    assert candidate.flexure_x.As_design_m2 == pytest.approx(0.0018, rel=1e-3)
    assert candidate.flexure_y.As_design_m2 == pytest.approx(0.0018, rel=1e-3)
    assert candidate.flexure_x.status == CheckStatus.PASS
    assert candidate.flexure_y.status == CheckStatus.PASS

    assert candidate.shear_x.status == CheckStatus.PASS
    assert candidate.shear_y.status == CheckStatus.PASS
    assert candidate.punching.status == CheckStatus.PASS

    assert candidate.governing_combos.contact_pressure == "S1"
    assert candidate.governing_combos.flexure_x == "U1"
    assert candidate.governing_combos.punching == "U1"
