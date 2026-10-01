"""L1 — Transferencia de momento en punzonamiento (E.060 §11.12.7).

Módulo independiente: estos tests no requieren el resto del motor.
"""

import math

import pytest

from engine.foundation.punching_moment_transfer import (
    check_punching_with_moment_transfer,
    gamma_f,
    polar_moment_jc,
)
from engine.results.status import CheckStatus

# Caso base: columna 0.40x0.40, d=0.422, Vc=2098.5 kN (ec. 11-43), phi=0.85
BX = BY = 0.40
D = 0.422
VC = 2098.5
PHI = 0.85


def _check(Vu=400.0, Mux=0.0, Muy=0.0, bx=BX, by=BY, d=D, Vc=VC):
    return check_punching_with_moment_transfer(Vu, Mux, Muy, bx, by, d, Vc, PHI)


# --- gamma_f / gamma_v (ec. 13-1 y 11-45) -------------------------------------------

def test_gamma_f_equation_13_1():
    b1, b2 = 0.822, 0.822
    assert gamma_f(b1, b2) == pytest.approx(1.0 / (1.0 + (2.0 / 3.0) * math.sqrt(b1 / b2)))


def test_gamma_f_for_square_critical_section_is_0_6():
    # b1 = b2 -> gamma_f = 1/(1+2/3) = 0.6 ; gamma_v = 0.4
    assert gamma_f(0.822, 0.822) == pytest.approx(0.6)


def test_gamma_v_complements_gamma_f():
    r = _check(Mux=100.0)
    assert r.axis_x.gamma_v == pytest.approx(1.0 - r.axis_x.gamma_f)
    assert r.axis_x.gamma_v == pytest.approx(0.4)


def test_elongated_critical_section_lowers_gamma_f():
    # b1 mayor que b2 -> mayor raiz -> menor gamma_f -> mayor gamma_v
    assert gamma_f(2.0, 1.0) < gamma_f(1.0, 1.0)


# --- Jc ------------------------------------------------------------------------------

def test_jc_matches_the_documented_expression():
    b1, b2, d = 0.822, 0.822, 0.422
    expected = (d * b1**3) / 6 + (b1 * d**3) / 6 + (d * b2 * b1**2) / 2
    assert polar_moment_jc(b1, b2, d) == pytest.approx(expected)


def test_jc_grows_with_the_critical_section():
    assert polar_moment_jc(1.2, 1.2, 0.5) > polar_moment_jc(0.8, 0.8, 0.5)


# --- CASO: Mx = My = 0 ----------------------------------------------------------------

def test_no_moment_means_no_amplification():
    r = _check(Vu=400.0)
    assert r.applicable is False
    assert r.axis_x is None and r.axis_y is None
    assert r.v_max_MPa == pytest.approx(r.v_direct_MPa)
    assert r.amplification_factor == pytest.approx(1.0)
    assert r.status is CheckStatus.PASS


# --- CASO: solo Mx / solo My ------------------------------------------------------------

def test_only_mx_activates_only_one_axis():
    r = _check(Mux=120.0)
    assert r.axis_x is not None
    assert r.axis_y is None
    assert r.v_max_MPa > r.v_direct_MPa


def test_only_my_activates_only_the_other_axis():
    r = _check(Muy=120.0)
    assert r.axis_x is None
    assert r.axis_y is not None
    assert r.v_max_MPa > r.v_direct_MPa


def test_symmetric_column_gives_same_stress_for_mx_or_my():
    """Columna cuadrada: un momento de igual magnitud en cualquier eje produce el
    mismo esfuerzo adicional."""
    only_x = _check(Mux=120.0)
    only_y = _check(Muy=120.0)
    assert only_x.v_max_MPa == pytest.approx(only_y.v_max_MPa)


def test_rectangular_column_breaks_that_symmetry():
    only_x = _check(Mux=120.0, bx=0.30, by=0.70)
    only_y = _check(Muy=120.0, bx=0.30, by=0.70)
    assert only_x.v_max_MPa != pytest.approx(only_y.v_max_MPa)


# --- CASO: Mx + My (biaxial) --------------------------------------------------------------

def test_biaxial_sums_both_contributions():
    only_x = _check(Mux=120.0)
    only_y = _check(Muy=90.0)
    both = _check(Mux=120.0, Muy=90.0)
    extra_x = only_x.v_max_MPa - only_x.v_direct_MPa
    extra_y = only_y.v_max_MPa - only_y.v_direct_MPa
    assert both.v_max_MPa == pytest.approx(both.v_direct_MPa + extra_x + extra_y)
    assert both.axis_x is not None and both.axis_y is not None


def test_biaxial_is_worse_than_either_alone():
    both = _check(Mux=120.0, Muy=90.0)
    assert both.v_max_MPa > _check(Mux=120.0).v_max_MPa
    assert both.v_max_MPa > _check(Muy=90.0).v_max_MPa


def test_sign_of_moment_does_not_matter():
    assert _check(Mux=120.0).v_max_MPa == pytest.approx(_check(Mux=-120.0).v_max_MPa)


# --- CASO: cercano al límite y falla por transferencia de momento ---------------------------

def test_case_near_the_limit():
    """Mu ajustado para dejar el ratio apenas por debajo de 1.0 (~0.97)."""
    r = _check(Vu=1500.0, Mux=168.0)
    assert 0.95 < r.ratio < 1.0
    assert r.status is CheckStatus.PASS


def test_just_over_the_limit_flips_to_fail():
    """Un incremento pequeño del momento cruza el límite: confirma que el
    criterio es sensible y no un umbral holgado."""
    apenas_ok = _check(Vu=1500.0, Mux=168.0)
    apenas_no = _check(Vu=1500.0, Mux=260.0)
    assert apenas_ok.status is CheckStatus.PASS
    assert apenas_no.status is CheckStatus.FAIL
    assert apenas_no.ratio > 1.0


def test_fails_because_of_moment_transfer_although_direct_shear_alone_would_pass():
    """EL CASO CLAVE: sin §11.12.7 este diseño parecería aceptable."""
    Vu = 1700.0
    sin_momento = _check(Vu=Vu)
    assert sin_momento.status is CheckStatus.PASS  # la resultante sola cumple

    con_momento = _check(Vu=Vu, Mux=450.0)
    assert con_momento.status is CheckStatus.FAIL
    assert con_momento.ratio > 1.0
    assert con_momento.v_direct_MPa < con_momento.phi_vn_MPa  # el directo cumplía
    assert con_momento.v_max_MPa > con_momento.phi_vn_MPa  # el combinado no
    assert "amplifica" in con_momento.message


def test_amplification_factor_is_reported():
    r = _check(Vu=1000.0, Mux=200.0)
    assert r.amplification_factor > 1.0
    assert r.amplification_factor == pytest.approx(r.v_max_MPa / r.v_direct_MPa)


# --- Trazabilidad -------------------------------------------------------------------------

def test_result_documents_every_required_element():
    r = _check(Vu=1000.0, Mux=200.0, Muy=150.0)
    text = r.equation_substituted
    for token in ("γf", "γv", "Jc", "v_directo", "vu_max", "φvn"):
        assert token in text, token
    assert "11.12.7" in r.code_reference
    assert "13-1" in r.code_reference
    assert "DERIVACIÓN" in r.code_reference  # Jc marcado como derivación, no cita


def test_effective_shear_force_is_comparable_to_phi_vc():
    r = _check(Vu=1000.0)
    assert r.Vu_effective_kN == pytest.approx(1000.0, rel=1e-6)
    assert r.phi_Vc_kN == pytest.approx(PHI * VC)
