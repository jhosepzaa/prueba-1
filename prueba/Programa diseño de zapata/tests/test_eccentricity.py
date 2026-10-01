import pytest

from engine.soil.eccentricity import compute_eccentricity


def test_no_moment_gives_zero_eccentricity():
    ecc = compute_eccentricity(P_kN=400.0, Mx_kNm=0.0, My_kNm=0.0)
    assert ecc.ex_m == 0.0
    assert ecc.ey_m == 0.0


def test_convencion_e050_mx_mueve_ex_y_my_mueve_ey():
    """E.050 art. 28.1: ex = Mx/Q, ey = My/Q."""
    ecc = compute_eccentricity(P_kN=100.0, Mx_kNm=20.0, My_kNm=10.0)
    assert ecc.ex_m == pytest.approx(0.20)  # Mx / P
    assert ecc.ey_m == pytest.approx(0.10)  # My / P


def test_rejects_non_positive_axial_load():
    with pytest.raises(ValueError):
        compute_eccentricity(P_kN=0.0, Mx_kNm=1.0, My_kNm=1.0)
