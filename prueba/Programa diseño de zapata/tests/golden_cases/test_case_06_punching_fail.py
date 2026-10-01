"""CASO 06 -- Falla por PUNZONAMIENTO aislado.

Columna pequeña sobre zapata compacta y suelo competente: el perímetro crítico bo
es corto, de modo que el punzonamiento se agota mientras la presión de contacto,
el cortante unidireccional y la flexión siguen cumpliendo.

Datos: B=L=1.60 m, columna 0.40x0.40, h=0.40 m, f'c=21 MPa, fy=420 MPa,
       qadm=500 kPa (BRUTA, suelo muy competente), gamma=18 kN/m3, Df=1.20 m
       S1 (servicio):    P=1150 kN
       U1 (factorizada): P=1700 kN     (relación 1.48, coherente con 1.4CM+1.7CV)

CÁLCULO A MANO (verificado, coincide con el motor):
    Fase 10A: recubrimiento contra el suelo 75 mm, E.060 §7.7.1 a) (propuesta 2019;
    este caso se calculó antes con 70 mm y se rehízo a mano con 75 mm).
    Barra seleccionada 1/2" (12.7 mm) en ambas direcciones. `d` corresponde a la
    CAPA SUPERIOR de la parrilla (criterio conservador del motor):
        d = 0.40 - 0.075 - 0.0127 - 0.0127/2 = 0.30595 m
    §15.7 (EFFECTIVE_DEPTH): d=0.306 >= 0.300 -> PASS (por poco)

    Presión de servicio:
      W = 24x2.56x0.40 + 18x2.56x0.80 = 24.576 + 36.864 = 61.44 kN
      q = (1150+61.44)/2.56 = 473.22 kPa < 500 -> PASS

    PUNZONAMIENTO (crítico):
      bo = 4 x (0.40+0.30595) = 2.8238 m
      gobierna ec. 11-43: Vc = 0.33 x sqrt(21) x 2823.8 x 305.95 = 1306.5 kN
      phi*Vc = 0.85 x 1306.5 = 1110.5 kN
      A_crit = 0.70595^2 = 0.49836 m^2
      Vu = 1700 x (1 - 0.49836/2.56) = 1369.1 kN > 1110.5 -> FAIL (ratio 1.233)

    CORTANTE UNIDIRECCIONAL (debe pasar):
      c = (1.60-0.40)/2 = 0.60 m ; c_shear = 0.60-0.30595 = 0.29405 m
      Vu = (1700/1.6) x 0.29405 = 312.4 kN
      phi*Vc = 0.85 x 0.17 x sqrt(21) x 1600 x 305.95 = 324.2 kN -> PASS (ratio 0.964)

    FLEXIÓN (debe pasar):
      Mu = (1700/1.6) x 0.60^2/2 = 191.25 kN·m
      As_req = 17.25 cm2 > As_min = 0.0018x1.60x0.40 = 11.52 cm2 -> gobierna flexión
      Armado: 1/2" @ 12.5 cm -> PASS

RESULTADO ESPERADO: FAIL, con "Punzonamiento no cumple." como ÚNICA razón.
"""

import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    STEEL_420,
)

SOIL_500_BRUTA = SoilProfile(
    qadm_kPa=500.0,
    pressure_basis=PressureBasis.BRUTA,
    gamma_kNm3=18.0,
    Df_m=1.20,
    source_notes="Dato del caso golden (suelo muy competente) -- no proviene de un EMS real.",
)

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=1150.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=1700.0)],
)


def _candidate():
    return evaluate_candidate(
        B_m=1.6, L_m=1.6, h_m=0.40,
        column=COLUMN_40x40, soil=SOIL_500_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_case_06_punching_fails():
    c = _candidate()
    assert c.punching.bo_m == pytest.approx(2.8238, rel=1e-4)
    assert c.punching.Vu_kN == pytest.approx(1369.1, rel=1e-3)
    assert c.punching.phi_Vc_kN == pytest.approx(1110.5, rel=1e-3)
    assert c.punching.ratio == pytest.approx(1.233, rel=1e-2)
    assert c.punching.status == CheckStatus.FAIL


def test_case_06_failure_is_isolated_to_punching():
    c = _candidate()
    assert c.contact_pressure.qmax_kPa == pytest.approx(473.22, rel=1e-3)
    assert c.contact_pressure.qmax_kPa < SOIL_500_BRUTA.qadm_kPa
    assert c.shear_x.status == CheckStatus.PASS
    assert c.shear_y.status == CheckStatus.PASS
    assert c.flexure_x.status == CheckStatus.PASS
    assert c.flexure_y.status == CheckStatus.PASS
    assert c.rebar_x.status == CheckStatus.PASS
    assert c.min_depth_status == CheckStatus.PASS


def test_case_06_flexure_governed_by_analysis_not_minimum():
    c = _candidate()
    # As requerido por flexión supera al mínimo de §9.7: confirma que este caso
    # ejercita la ecuación de diseño y no solo la cuantía mínima.
    assert c.flexure_x.As_required_m2 == pytest.approx(17.25e-4, rel=1e-2)
    assert c.flexure_x.As_required_m2 > c.flexure_x.As_min_m2


def test_case_06_discard_reason_is_exactly_one_and_names_punching():
    c = _candidate()
    assert c.overall_status == CheckStatus.FAIL
    assert c.discard_reasons == ["Punzonamiento no cumple."]
