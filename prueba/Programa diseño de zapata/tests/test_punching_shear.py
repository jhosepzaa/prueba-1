"""Auditoría del módulo de punzonamiento -- ver el encabezado de
engine/foundation/punching_shear.py para la documentación completa de cada
elemento verificado aquí."""

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.punching_shear import (
    ALPHA_S_CORNER,
    ALPHA_S_EDGE,
    ALPHA_S_INTERIOR,
    check_punching_shear,
    critical_enclosed_area,
    critical_perimeter,
    critical_section_fits_in_footing,
    punching_demand,
)
from engine.results.status import CheckStatus

code = E060ConcreteCode()


# --- 1 y 2. Ubicación a d/2 y perímetro crítico ---------------------------------

def test_critical_perimeter_is_offset_by_half_d_from_each_face():
    bx, by, d = 0.40, 0.40, 0.422
    bo = critical_perimeter(bx, by, d)
    # Lados de la sección crítica: bx + 2*(d/2) = bx + d
    assert bo == pytest.approx(2 * (bx + d) + 2 * (by + d))
    assert bo == pytest.approx(4 * (0.40 + 0.422))  # 3.288 m


def test_critical_perimeter_grows_with_d():
    assert critical_perimeter(0.4, 0.4, 0.5) > critical_perimeter(0.4, 0.4, 0.3)


def test_rectangular_column_perimeter_uses_both_dimensions():
    bo = critical_perimeter(bx_m=0.30, by_m=0.60, d_m=0.40)
    assert bo == pytest.approx(2 * 0.70 + 2 * 1.00)


# --- 3. Área encerrada ----------------------------------------------------------

def test_critical_enclosed_area():
    assert critical_enclosed_area(0.40, 0.40, 0.422) == pytest.approx(0.822**2)
    assert critical_enclosed_area(0.30, 0.60, 0.40) == pytest.approx(0.70 * 1.00)


# --- 4. Efecto de q y cálculo de Vu ---------------------------------------------

def test_vu_subtracts_soil_reaction_under_critical_area():
    Pu, B, L, bx, by, d = 560.0, 2.0, 2.0, 0.40, 0.40, 0.422
    qu = Pu / (B * L)
    expected = Pu - qu * (bx + d) * (by + d)
    assert punching_demand(Pu, B, L, bx, by, d) == pytest.approx(expected)


def test_vu_is_never_negative():
    # Zapata apenas mayor que la sección crítica -> el alivio del suelo tiende a Pu
    assert punching_demand(500.0, 1.0, 1.0, 0.4, 0.4, 0.55) >= 0.0


def test_soil_relief_is_reported_explicitly():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.qu_avg_kPa == pytest.approx(560.0 / 4.0)
    assert result.soil_relief_kN == pytest.approx(result.qu_avg_kPa * result.critical_area_m2)
    assert result.Vu_kN == pytest.approx(560.0 - result.soil_relief_kN)


# --- 5, 6. Vc, las tres ecuaciones, y phi*Vc ------------------------------------

def test_vc_reports_all_three_equations_and_the_governing_one():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.Vc_kN == pytest.approx(
        min(result.Vc_eq_11_33_kN, result.Vc_eq_11_34_kN, result.Vc_eq_11_35_kN)
    )
    assert result.governing_equation in {"11-41", "11-42", "11-43"}


def test_phi_is_085_for_shear():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.phi == 0.85  # E.060 §9.4
    assert result.phi_Vc_kN == pytest.approx(0.85 * result.Vc_kN)


# --- 7. beta ---------------------------------------------------------------------

def test_beta_is_long_over_short_side_of_the_column():
    result = check_punching_shear(560.0, 3.0, 3.0, 0.30, 0.60, 0.422, 21.0, code)
    assert result.beta_col == pytest.approx(2.0)


def test_beta_is_one_for_square_column():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.beta_col == pytest.approx(1.0)


# --- 8. alpha_s -------------------------------------------------------------------

def test_alpha_s_defaults_to_interior_column():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.alpha_s == ALPHA_S_INTERIOR == 40.0


def test_alpha_s_is_configurable_and_lower_values_reduce_capacity():
    base = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, alpha_s=ALPHA_S_INTERIOR)
    edge = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, alpha_s=ALPHA_S_EDGE)
    corner = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, alpha_s=ALPHA_S_CORNER)
    # alpha_s solo entra en la ec. 11-42; nunca puede AUMENTAR la capacidad al bajar.
    assert edge.Vc_eq_11_34_kN < base.Vc_eq_11_34_kN
    assert corner.Vc_eq_11_34_kN < edge.Vc_eq_11_34_kN
    assert corner.Vc_kN <= base.Vc_kN


# --- 9. Validación geométrica de la sección crítica --------------------------------

def test_critical_section_must_fit_inside_the_footing():
    # d/2 = 0.35 > voladizo 0.30 -> la sección crítica se sale de la zapata
    assert critical_section_fits_in_footing(B_m=1.0, L_m=1.0, bx_m=0.4, by_m=0.4, d_m=0.70) is False
    assert critical_section_fits_in_footing(B_m=2.0, L_m=2.0, bx_m=0.4, by_m=0.4, d_m=0.42) is True


def test_oversized_d_fails_with_geometric_reason_not_a_meaningless_number():
    """Zapata 1,0x1,0 m con columna 0,40 y d=0,70: la sección crítica se recorta por
    los CUATRO lados. E.060 §11.12.2.1(b) solo clasifica 0, 1 o 2 lados recortados,
    así que no hay alpha_s aplicable y el motor no le inventa uno."""
    result = check_punching_shear(560.0, 1.0, 1.0, 0.40, 0.40, 0.70, 21.0, code)
    assert result.critical_section_fits is False
    assert result.column_position == "degenerada"
    assert result.status == CheckStatus.FAIL
    # El motivo debe ser geométrico y decir qué hacer, no un número sin sentido.
    assert "GEOMETRÍA FUERA DE ALCANCE" in result.completeness_note
    assert "no prescribe alpha_s" in result.completeness_note
    assert "Aumente la zapata" in result.completeness_note
    # Y no debe presentar una resistencia calculada: no se calculó ninguna.
    assert result.phi_Vc_kN == 0.0


# --- 10. Transferencia de momento: IMPLEMENTADO (L1 cerrada) ------------------------

def test_moment_transfer_is_declared_implemented():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    assert result.moment_transfer_implemented is True


def test_without_moment_no_transfer_object_and_check_can_pass():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, Mux_kNm=0.0, Muy_kNm=0.0)
    assert result.unbalanced_moment_present is False
    assert result.moment_transfer is None
    assert result.status == CheckStatus.PASS
    assert "no transmite momento" in result.completeness_note


def test_with_moment_the_check_uses_11_12_6_and_can_still_pass():
    result = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, Mux_kNm=80.0)
    assert result.unbalanced_moment_present is True
    assert result.moment_transfer is not None
    assert result.status == CheckStatus.PASS
    assert "COMPLETA" in result.completeness_note
    assert "11.12.7" in result.code_reference


def test_moment_amplifies_the_shear_stress():
    sin_m = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code)
    con_m = check_punching_shear(560.0, 2.0, 2.0, 0.40, 0.40, 0.422, 21.0, code, Mux_kNm=80.0, Muy_kNm=50.0)
    # La RESULTANTE Vu no cambia (integral exacta sobre area centrada)...
    assert con_m.Vu_kN == pytest.approx(sin_m.Vu_kN)
    # ...pero el esfuerzo maximo si aumenta por la transferencia de momento.
    assert con_m.moment_transfer.amplification_factor > 1.0
    assert con_m.moment_transfer.v_max_MPa > con_m.moment_transfer.v_direct_MPa
