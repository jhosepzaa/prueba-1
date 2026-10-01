import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.flexure import design_flexure, moment_at_critical_section
from engine.results.status import CheckStatus

code = E060ConcreteCode()


def test_moment_uniform_load_matches_beam_formula():
    # Carga uniforme (e=0): M = w*c^2/2, w = Pu/dim
    Pu, dim, c = 560.0, 2.0, 0.80
    w = Pu / dim
    expected = w * c**2 / 2.0
    M = moment_at_critical_section(Pu, e_m=0.0, dim_along_e_m=dim, cantilever_m=c, near_high_edge=True)
    assert M == pytest.approx(expected)
    assert M == pytest.approx(89.6, rel=1e-6)


def test_moment_triangular_zero_at_edge():
    # e tal que q0=0 exactamente en el borde analizado (near_high_edge=False):
    # q0 = (P/dim)*(1-6e/dim) = 0  =>  e = dim/6
    Pu, dim, c = 400.0, 2.0, 0.5
    e = dim / 6.0
    M = moment_at_critical_section(Pu, e_m=e, dim_along_e_m=dim, cantilever_m=c, near_high_edge=False)
    # M = c^2/6 * (2*q_edge + q_face), q_edge=0 -> M = c^2/6 * q_face
    q_face = (Pu / dim) * (1 - 6 * e / dim) + ((Pu / dim) * (1 + 6 * e / dim) - (Pu / dim) * (1 - 6 * e / dim)) * (c / dim)
    expected = c**2 / 6.0 * q_face
    assert M == pytest.approx(expected)


def test_design_flexure_governed_by_as_min():
    # Caso golden 1: Mu=89.6 kN*m, b=L=2.0m, h=0.5m, d=0.422m, fc=21, fy=420
    result = design_flexure(
        Mu_kNm=89.6, b_m=2.0, h_m=0.5, d_m=0.422, cantilever_m=0.80,
        fc_MPa=21.0, fy_MPa=420.0, bar_type="corrugada", code=code,
    )
    assert result.As_required_m2 == pytest.approx(565e-6, rel=2e-2)  # ~5.65 cm2
    assert result.As_min_m2 == pytest.approx(0.0018 * 2.0 * 0.5)  # 18 cm2
    assert result.As_design_m2 == pytest.approx(result.As_min_m2)
    assert result.status == CheckStatus.PASS


def test_design_flexure_fails_when_section_too_thin():
    # h muy pequeño -> discriminante negativo -> FAIL explícito, no NaN silencioso
    result = design_flexure(
        Mu_kNm=500.0, b_m=1.0, h_m=0.15, d_m=0.05, cantilever_m=0.80,
        fc_MPa=21.0, fy_MPa=420.0, bar_type="corrugada", code=code,
    )
    assert result.status == CheckStatus.FAIL
    assert "insuficiente" in result.note.lower()
