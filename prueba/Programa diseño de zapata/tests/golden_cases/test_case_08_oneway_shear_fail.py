"""CASO 08 -- Falla por CORTANTE UNIDIRECCIONAL aislado.

Este caso es difícil de construir a propósito: en zapatas cuadradas con columna
pequeña, el punzonamiento casi siempre gobierna antes que el cortante en una
dirección. Para aislar la falla por cortante unidireccional se necesita:
  - columna GRANDE (aumenta bo -> mucha capacidad al punzonamiento, y aumenta el
    área crítica -> baja la demanda Vu de punzonamiento), y
  - zapata muy alargada en una dirección (voladizo largo respecto de d -> alta
    demanda de cortante como viga ancha en esa dirección).

Datos: B=6.00 m, L=3.00 m, columna 1.20x1.20, h=0.80 m, f'c=21 MPa, fy=420 MPa,
       qadm=300 kPa (BRUTA, suelo competente), gamma=18 kN/m3, Df=1.20 m
       S1 (servicio):    P=4000 kN
       U1 (factorizada): P=6000 kN

CÁLCULO A MANO (verificado, coincide con el motor):
    Fase 10A: recubrimiento contra el suelo 75 mm, E.060 §7.7.1 a) (propuesta 2019;
    este caso se calculó antes con 70 mm y se rehízo a mano con 75 mm).
    Barras seleccionadas: X = 1" (25.4 mm, capa inferior por ser el lado largo),
    Y = 5/8" (15.9 mm, capa superior). `d` es el de la capa superior:
        d = 0.80 - 0.075 - 0.0254 - 0.0159/2 = 0.69165 m
    §15.7 (EFFECTIVE_DEPTH): d=0.692 >= 0.300 -> PASS

    Presión de servicio:
      W_zapata=24x18x0.80=345.6 ; W_relleno=18x18x0.40=129.6 ; W_total=475.2 kN
      q = (4000+475.2)/18 = 248.62 kPa < 300 -> PASS (no interfiere)

    CORTANTE UNIDIRECCIONAL X (crítico):
      voladizo c_x = (6.00-1.20)/2 = 2.40 m
      w = Pu/B = 6000/6 = 1000 kN/m
      Vu = w x (c_x - d) = 1000 x (2.40-0.69165) = 1708.35 kN
      Vc = 0.17 x sqrt(21) x 3000 mm x 691.65 mm = 1616.5 kN  (ec. 11-3, bw = L = 3.0 m)
      phi*Vc = 0.85 x 1616.5 = 1374.0 kN
      Vu=1708.35 > phi*Vc=1374.0  -> FAIL (ratio 1.243)

    PUNZONAMIENTO (debe pasar, para que la falla quede aislada):
      bo = 4 x (1.20+0.69165) = 7.5666 m
      gobierna ec. 11-43: Vc = 0.33 x sqrt(21) x 7566.6 x 691.65 = 7914.3 kN
      phi*Vc = 6727.1 kN
      Vu = 6000 x (1 - 1.89165^2/18) = 4807.2 kN < 6727.1 -> PASS (ratio 0.715)

    CORTANTE UNIDIRECCIONAL Y (debe pasar):
      c_y = (3.00-1.20)/2 = 0.90 m ; Vu = (6000/3) x (0.90-0.69165) = 416.7 kN
      phi*Vc = 0.85 x 0.17 x sqrt(21) x 6000 x 691.65 = 2748.0 kN -> PASS (ratio 0.152)

RESULTADO ESPERADO: FAIL, con "Cortante unidireccional X no cumple" como ÚNICA
razón de descarte. Todas las demás verificaciones en PASS.
"""

import pytest

from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from tests.golden_cases.common import CODE, CONCRETE_21, CONTACT_MODEL, STEEL_420

COLUMN_120x120 = Column(shape="cuadrada", bx_m=1.20, by_m=1.20)
SOIL_300_BRUTA = SoilProfile(
    qadm_kPa=300.0,
    pressure_basis=PressureBasis.BRUTA,
    gamma_kNm3=18.0,
    Df_m=1.20,
    source_notes="Dato del caso golden (suelo competente) -- no proviene de un EMS real.",
)
DEPTH_PARAMS = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=4000.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=6000.0)],
)


def _candidate():
    return evaluate_candidate(
        B_m=6.0, L_m=3.0, h_m=0.80,
        column=COLUMN_120x120, soil=SOIL_300_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS,
    )


def test_case_08_oneway_shear_x_fails():
    c = _candidate()
    assert c.shear_x.Vu_kN == pytest.approx(1708.35, rel=1e-3)
    assert c.shear_x.phi_Vc_kN == pytest.approx(1374.0, rel=1e-3)
    assert c.shear_x.ratio == pytest.approx(1.243, rel=1e-2)
    assert c.shear_x.status == CheckStatus.FAIL


def test_case_08_failure_is_isolated_to_oneway_shear():
    c = _candidate()
    # Todo lo demás debe pasar: si otro check falla, el caso dejó de aislar el
    # fenómeno que pretende verificar.
    assert c.punching.status == CheckStatus.PASS
    assert c.punching.ratio == pytest.approx(0.715, rel=1e-2)
    assert c.shear_y.status == CheckStatus.PASS
    assert c.flexure_x.status == CheckStatus.PASS
    assert c.flexure_y.status == CheckStatus.PASS
    assert c.contact_pressure.qmax_kPa == pytest.approx(248.62, rel=1e-3)
    assert c.contact_pressure.qmax_kPa < SOIL_300_BRUTA.qadm_kPa
    assert c.min_depth_status == CheckStatus.PASS


def test_case_08_discard_reason_is_exactly_one_and_names_shear():
    c = _candidate()
    assert c.overall_status == CheckStatus.FAIL
    assert c.discard_reasons == ["Cortante unidireccional X no cumple."]
