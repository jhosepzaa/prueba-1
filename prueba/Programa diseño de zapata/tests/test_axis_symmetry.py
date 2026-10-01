"""Test de simetría de ejes -- prueba ejecutable de que la convención
B=X, L=Y, Mx->ey, My->ex es consistente en TODO el pipeline.

Ver docs/convenciones_ejes.md para la auditoría escrita.

Idea: intercambiar simultáneamente B<->L, Mx<->My y bx<->by es una ROTACIÓN de
90° del mismo problema físico. Todo resultado escalar (presiones, punzonamiento,
volúmenes) debe quedar idéntico, y todo resultado direccional debe intercambiarse.

El test también verifica el caso NEGATIVO: rotar solo la zapata y los momentos,
sin rotar la columna, produce un problema distinto y NO debe dar el mismo
resultado. Sin esa comprobación, el test podría pasar por casualidad si el motor
ignorara alguna de las dimensiones.
"""

import pytest

from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
from engine.soil.contact_pressure import FullContactModel
from engine.soil.eccentricity import compute_eccentricity
from tests.golden_cases.common import (
    CODE,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

# Geometría deliberadamente ASIMÉTRICA en todo: zapata rectangular, columna
# rectangular, y Mx != My. Si algo estuviera cruzado, el test lo detecta.
B, L = 3.20, 2.40
BX, BY = 0.30, 0.50
H = 0.60
P_SERV, MX_SERV, MY_SERV = 600.0, 90.0, 45.0
P_FACT, MX_FACT, MY_FACT = 840.0, 126.0, 63.0


def _loads(mx: float, my: float, mx_f: float, my_f: float) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P_SERV, Mx_kNm=mx, My_kNm=my)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P_FACT, Mx_kNm=mx_f, My_kNm=my_f)],
    )


def _evaluate(b: float, l: float, bx: float, by: float, mx: float, my: float, mx_f: float, my_f: float):
    return evaluate_candidate(
        B_m=b, L_m=l, h_m=H,
        column=Column(shape="rectangular", bx_m=bx, by_m=by),
        soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=_loads(mx, my, mx_f, my_f),
        code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def _original():
    return _evaluate(B, L, BX, BY, MX_SERV, MY_SERV, MX_FACT, MY_FACT)


def _rotated():
    """Rotación completa de 90°: B<->L, bx<->by, Mx<->My."""
    return _evaluate(L, B, BY, BX, MY_SERV, MX_SERV, MY_FACT, MX_FACT)


# --- Convención base --------------------------------------------------------------

def test_convencion_e050_mx_da_ex_y_my_da_ey():
    """E.050 art. 28.1: ex = Mx/Q, ey = My/Q."""
    ecc = compute_eccentricity(P_kN=500.0, Mx_kNm=100.0, My_kNm=40.0)
    assert ecc.ex_m == pytest.approx(100.0 / 500.0)  # Mx / P
    assert ecc.ey_m == pytest.approx(40.0 / 500.0)  # My / P


def test_pressure_formula_pairs_ex_with_B_and_ey_with_L():
    """ex debe dividirse entre B (dimensión X) y ey entre L (dimensión Y).
    Con B != L, cruzarlos daría un resultado distinto y detectable."""
    model = FullContactModel()
    b, l, p, ex, ey = 4.0, 2.0, 400.0, 0.20, 0.10
    r = model.compute(B_m=b, L_m=l, P_kN=p, ex_m=ex, ey_m=ey)
    q_avg = p / (b * l)
    expected_max = q_avg * (1 + 6 * ex / b + 6 * ey / l)
    assert r.qmax_kPa == pytest.approx(expected_max)
    # y NO el emparejamiento cruzado:
    crossed = q_avg * (1 + 6 * ex / l + 6 * ey / b)
    assert r.qmax_kPa != pytest.approx(crossed)


def test_kern_condition_pairs_each_eccentricity_with_its_own_dimension():
    model = FullContactModel()
    # ex = B/6 exacto, ey = 0 -> justo en el borde del núcleo
    assert model.compute(6.0, 2.0, 400.0, 1.0, 0.0).within_kern is True
    # ex ligeramente mayor -> fuera
    assert model.compute(6.0, 2.0, 400.0, 1.02, 0.0).within_kern is False
    # ey = L/6 exacto -> borde
    assert model.compute(6.0, 2.0, 400.0, 0.0, 1.0 / 3.0).within_kern is True


# --- Simetría bajo rotación de 90° -------------------------------------------------

def test_eccentricities_swap_under_rotation():
    o, r = _original(), _rotated()
    assert r.eccentricity_governing.ex_m == pytest.approx(o.eccentricity_governing.ey_m)
    assert r.eccentricity_governing.ey_m == pytest.approx(o.eccentricity_governing.ex_m)


def test_contact_pressure_is_invariant_under_rotation():
    o, r = _original(), _rotated()
    assert r.contact_pressure.qmax_kPa == pytest.approx(o.contact_pressure.qmax_kPa)
    assert r.contact_pressure.qmin_kPa == pytest.approx(o.contact_pressure.qmin_kPa)
    assert r.contact_pressure.qavg_kPa == pytest.approx(o.contact_pressure.qavg_kPa)
    assert r.contact_pressure.within_kern == o.contact_pressure.within_kern


def test_self_weight_is_invariant_under_rotation():
    o, r = _original(), _rotated()
    assert r.self_weight.W_total_kN == pytest.approx(o.self_weight.W_total_kN)


def test_flexure_swaps_directions_under_rotation():
    o, r = _original(), _rotated()
    assert r.flexure_x.Mu_kNm == pytest.approx(o.flexure_y.Mu_kNm)
    assert r.flexure_y.Mu_kNm == pytest.approx(o.flexure_x.Mu_kNm)
    assert r.flexure_x.As_design_m2 == pytest.approx(o.flexure_y.As_design_m2)
    assert r.flexure_y.As_design_m2 == pytest.approx(o.flexure_x.As_design_m2)


def test_one_way_shear_swaps_directions_under_rotation():
    o, r = _original(), _rotated()
    assert r.shear_x.Vu_kN == pytest.approx(o.shear_y.Vu_kN)
    assert r.shear_y.Vu_kN == pytest.approx(o.shear_x.Vu_kN)
    assert r.shear_x.phi_Vc_kN == pytest.approx(o.shear_y.phi_Vc_kN)


def test_punching_is_invariant_under_rotation():
    o, r = _original(), _rotated()
    assert r.punching.bo_m == pytest.approx(o.punching.bo_m)
    assert r.punching.critical_area_m2 == pytest.approx(o.punching.critical_area_m2)
    assert r.punching.Vu_kN == pytest.approx(o.punching.Vu_kN)
    assert r.punching.beta_col == pytest.approx(o.punching.beta_col)
    assert r.punching.phi_Vc_kN == pytest.approx(o.punching.phi_Vc_kN)


def test_rebar_swaps_directions_under_rotation():
    o, r = _original(), _rotated()
    assert r.rebar_x.bar_designation == o.rebar_y.bar_designation
    assert r.rebar_x.spacing_m == pytest.approx(o.rebar_y.spacing_m)
    assert r.rebar_x.As_provided_m2 == pytest.approx(o.rebar_y.As_provided_m2)


def test_overall_status_is_invariant_under_rotation():
    o, r = _original(), _rotated()
    assert r.overall_status == o.overall_status
    assert sorted(r.discard_reasons) == sorted(
        # las razones direccionales también se intercambian
        [reason.replace(" X", " @").replace(" Y", " X").replace(" @", " Y") for reason in o.discard_reasons]
    )


# --- Control negativo: una rotación INCOMPLETA no debe preservar el resultado -------

def test_incomplete_rotation_does_not_preserve_results():
    """Intercambiar B<->L y Mx<->My SIN rotar la columna es un problema físico
    distinto. Si esto diera el mismo resultado, significaría que el motor está
    ignorando las dimensiones de la columna en alguna dirección."""
    o = _original()
    partial = _evaluate(L, B, BX, BY, MY_SERV, MX_SERV, MY_FACT, MX_FACT)  # columna sin rotar
    assert partial.flexure_x.Mu_kNm != pytest.approx(o.flexure_y.Mu_kNm)


def test_asymmetric_setup_actually_produces_different_directions():
    """Garantiza que el caso de prueba no es trivialmente simétrico: si Mu_x
    fuera igual a Mu_y, los tests de intercambio pasarían sin probar nada."""
    o = _original()
    assert o.flexure_x.Mu_kNm != pytest.approx(o.flexure_y.Mu_kNm)
    assert o.shear_x.Vu_kN != pytest.approx(o.shear_y.Vu_kN)
    assert o.eccentricity_governing.ex_m != pytest.approx(o.eccentricity_governing.ey_m)
