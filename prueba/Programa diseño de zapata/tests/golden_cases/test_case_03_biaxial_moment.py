"""CASO 03 -- Zapata cuadrada con momento biaxial (Mx e My simultáneos).

Verifica que el motor trata correctamente la superposición de ambas
excentricidades, tanto en la presión de contacto (suma de los dos términos) como
en la flexión (cada dirección usa SU propia excentricidad, no la resultante).

Datos: B=L=2.80 m, h=0.60 m, columna 0.40x0.40, f'c=21 MPa, fy=420 MPa,
       qadm=150 kPa (BRUTA), gamma_suelo=18 kN/m3, Df=1.20 m
       S1 (servicio):    P=500 kN, Mx=80 kN·m, My=60 kN·m
       U1 (factorizada): P=700 kN, Mx=112 kN·m, My=84 kN·m

CÁLCULO A MANO (verificado, coincide con el motor con 6 cifras):
    W_zapata  = 24 x 2.8 x 2.8 x 0.60          = 112.896 kN
    W_relleno = 18 x 2.8 x 2.8 x (1.20-0.60)   =  84.672 kN
    W_total                                     = 197.568 kN
    P_total   = 500 + 197.568                   = 697.568 kN

    ex = My/P_total = 60/697.568 = 0.086013 m
    ey = Mx/P_total = 80/697.568 = 0.114684 m
    (nota: My -> ex, Mx -> ey, por la convención de ejes del motor)

    Núcleo central: B/6 = L/6 = 0.466667 m
    kern_ratio = 0.086013/0.466667 + 0.114684/0.466667 = 0.1843 + 0.2458 = 0.4301 <= 1
    => DENTRO del núcleo, sin tracciones (E.060 §15.2)

    q_avg = 697.568/7.84 = 88.976 kPa
    term_x = 6 x 0.086013/2.8 = 0.184313
    term_y = 6 x 0.114684/2.8 = 0.245751
    qmax = 88.976 x (1 + 0.184313 + 0.245751) = 127.241 kPa  < 150 -> PASS
    qmin = 88.976 x (1 - 0.184313 - 0.245751) =  50.710 kPa  > 0   -> sin tracciones

RESULTADO ESPERADO: PASS en todas las verificaciones, y Mu_y > Mu_x porque
ey > ex (la dirección Y tiene mayor excentricidad y por tanto mayor momento).
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
    service=[
        LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=500.0, My_kNm=80.0, Mx_kNm=60.0)
    ],
    factored=[
        LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=700.0, My_kNm=112.0, Mx_kNm=84.0)
    ],
)


def _candidate():
    return evaluate_candidate(
        B_m=2.8, L_m=2.8, h_m=0.60,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_case_03_self_weight_and_eccentricities():
    c = _candidate()
    assert c.self_weight.W_footing_kN == pytest.approx(112.896, rel=1e-6)
    assert c.self_weight.W_soil_backfill_kN == pytest.approx(84.672, rel=1e-6)
    assert c.self_weight.W_total_kN == pytest.approx(197.568, rel=1e-6)
    # My genera ex, Mx genera ey (convención declarada en engine/soil/eccentricity.py)
    assert c.eccentricity_governing.ex_m == pytest.approx(0.086013, rel=1e-4)
    assert c.eccentricity_governing.ey_m == pytest.approx(0.114684, rel=1e-4)


def test_case_03_biaxial_pressure_superposes_both_terms():
    c = _candidate()
    assert c.contact_pressure.within_kern is True
    assert c.contact_pressure.qavg_kPa == pytest.approx(88.976, rel=1e-4)
    assert c.contact_pressure.qmax_kPa == pytest.approx(127.241, rel=1e-4)
    assert c.contact_pressure.qmin_kPa == pytest.approx(50.710, rel=1e-4)
    # Sin tracciones: qmin estrictamente positivo (E.060 §15.2)
    assert c.contact_pressure.qmin_kPa > 0.0
    assert c.contact_pressure.qmax_kPa < SOIL_150_BRUTA.qadm_kPa


def test_case_03_each_direction_uses_its_own_eccentricity():
    c = _candidate()
    # ey > ex  =>  el momento en Y debe superar al de X. Si el motor usara la
    # excentricidad resultante o cruzara las direcciones, esto no se cumpliría.
    assert c.eccentricity_governing.ey_m > c.eccentricity_governing.ex_m
    assert c.flexure_y.Mu_kNm > c.flexure_x.Mu_kNm


def test_case_03_no_check_fails():
    c = _candidate()
    # Ninguna verificación FALLA: la geometría es adecuada.
    assert c.discard_reasons == []
    assert c.trace.failing_entries() == []
    assert c.governing_combos.contact_pressure == "S1"
    assert c.governing_combos.flexure_x == "U1"
    assert c.governing_combos.punching == "U1"


def test_case_03_punching_includes_moment_transfer():
    """L1 cerrada: con Mux/Muy != 0 la verificacion aplica E.060 §11.12.6 y ya no
    se degrada a WARNING por falta de implementacion."""
    c = _candidate()
    assert c.punching.unbalanced_moment_present is True
    assert c.punching.moment_transfer_implemented is True
    mt = c.punching.moment_transfer
    assert mt is not None
    # Ambos ejes aportan porque hay Mx y My simultaneos.
    assert mt.axis_x is not None and mt.axis_y is not None
    assert 0.0 < mt.axis_x.gamma_v < 1.0
    assert mt.amplification_factor > 1.0
    assert c.punching.status == CheckStatus.PASS
