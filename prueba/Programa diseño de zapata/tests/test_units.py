from engine.units.si_units import kn_to_n, m_to_mm, mm_to_m, n_to_kn


def test_length_roundtrip():
    assert m_to_mm(1.5) == 1500.0
    assert mm_to_m(1500.0) == 1.5


def test_force_roundtrip():
    assert kn_to_n(2.0) == 2000.0
    assert n_to_kn(2000.0) == 2.0
