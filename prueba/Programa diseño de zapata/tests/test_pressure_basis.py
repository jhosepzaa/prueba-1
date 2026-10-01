import pytest

from engine.domain.soil import PressureBasis
from engine.soil.pressure_basis import convert_pressure


def test_bruta_to_neta():
    q_neta = convert_pressure(150.0, PressureBasis.BRUTA, PressureBasis.NETA, gamma_kNm3=18.0, Df_m=1.2)
    assert q_neta == pytest.approx(150.0 - 18.0 * 1.2)  # 128.4


def test_neta_to_bruta_roundtrip():
    q_bruta = convert_pressure(128.4, PressureBasis.NETA, PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.2)
    assert q_bruta == pytest.approx(150.0)


def test_same_basis_is_noop():
    assert convert_pressure(100.0, PressureBasis.BRUTA, PressureBasis.BRUTA, 18.0, 1.2) == 100.0
