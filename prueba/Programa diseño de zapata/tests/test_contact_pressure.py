import pytest

from engine.soil.contact_pressure import FullContactModel, KernCheckModel


def test_concentric_load_gives_uniform_pressure():
    model = FullContactModel()
    result = model.compute(B_m=2.0, L_m=2.0, P_kN=400.0, ex_m=0.0, ey_m=0.0)
    assert result.qmax_kPa == pytest.approx(100.0)
    assert result.qmin_kPa == pytest.approx(100.0)
    assert result.qavg_kPa == pytest.approx(100.0)
    assert result.within_kern is True


def test_uniaxial_within_kern():
    # B=2, ex=0.2 (< B/6=0.333) -> dentro del núcleo
    model = FullContactModel()
    result = model.compute(B_m=2.0, L_m=2.0, P_kN=400.0, ex_m=0.2, ey_m=0.0)
    q_avg = 400.0 / 4.0
    term = 6.0 * 0.2 / 2.0
    assert result.qmax_kPa == pytest.approx(q_avg * (1 + term))
    assert result.qmin_kPa == pytest.approx(q_avg * (1 - term))
    assert result.within_kern is True


def test_uniaxial_outside_kern_flagged():
    # ex=0.5 > B/6=0.333 -> fuera del núcleo (qmin sería negativo)
    model = FullContactModel()
    result = model.compute(B_m=2.0, L_m=2.0, P_kN=400.0, ex_m=0.5, ey_m=0.0)
    assert result.within_kern is False
    assert result.qmin_kPa < 0


def test_kern_check_model_delegates_to_full_contact():
    kern = KernCheckModel()
    full = FullContactModel()
    r_kern = kern.compute(2.0, 2.0, 400.0, 0.1, 0.05)
    r_full = full.compute(2.0, 2.0, 400.0, 0.1, 0.05)
    assert r_kern.qmax_kPa == pytest.approx(r_full.qmax_kPa)
    assert r_kern.model_name == "KernCheck"


def test_kern_boundary_exact_sixth():
    # ex = B/6 exacto -> qmin debe ser 0 (borde del núcleo), within_kern True
    model = FullContactModel()
    result = model.compute(B_m=1.2, L_m=1.2, P_kN=300.0, ex_m=0.2, ey_m=0.0)  # B/6 = 0.2
    assert result.qmin_kPa == pytest.approx(0.0, abs=1e-6)
    assert result.within_kern is True
