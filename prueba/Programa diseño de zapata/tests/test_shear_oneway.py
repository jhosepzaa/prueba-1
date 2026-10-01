import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.shear_oneway import check_shear_oneway, shear_force_at_d_from_face
from engine.results.status import CheckStatus

code = E060ConcreteCode()


def test_shear_force_uniform_load():
    # w=280 kN/m, c_shear = 0.80-0.422=0.378 -> Vu = w*c_shear
    Vu = shear_force_at_d_from_face(
        P_u_column_kN=560.0, e_m=0.0, dim_along_e_m=2.0, cantilever_m=0.80, d_m=0.422, near_high_edge=True
    )
    assert Vu == pytest.approx(280.0 * 0.378, rel=1e-6)


def test_shear_zero_when_critical_section_beyond_edge():
    Vu = shear_force_at_d_from_face(
        P_u_column_kN=560.0, e_m=0.0, dim_along_e_m=2.0, cantilever_m=0.30, d_m=0.422, near_high_edge=True
    )
    assert Vu == 0.0


def test_check_shear_oneway_pass():
    result = check_shear_oneway(Vu_kN=105.84, fc_MPa=21.0, bw_m=2.0, d_m=0.422, code=code)
    assert result.status == CheckStatus.PASS
    assert result.ratio < 1.0


def test_check_shear_oneway_fail():
    result = check_shear_oneway(Vu_kN=900.0, fc_MPa=21.0, bw_m=2.0, d_m=0.422, code=code)
    assert result.status == CheckStatus.FAIL
    assert result.ratio > 1.0
