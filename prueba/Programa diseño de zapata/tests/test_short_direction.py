"""E.060 §15.4.4 y ec. 15-1 -- distribución del refuerzo en dirección corta."""

import pytest

from engine.reinforcement.short_direction import distribute_short_direction

RHO_MIN = 0.0018
H = 0.50


def test_square_footing_degrades_to_uniform():
    d = distribute_short_direction(As_total_m2=0.0020, long_side_m=2.0, short_side_m=2.0, h_m=H, rho_min=RHO_MIN)
    assert d.is_square is True
    assert d.beta == pytest.approx(1.0)
    assert d.gamma_s == pytest.approx(1.0)  # 2/(1+1)
    assert len(d.bands) == 1
    assert d.bands[0].width_m == pytest.approx(2.0)


def test_gamma_s_matches_equation_15_1():
    d = distribute_short_direction(0.0030, long_side_m=3.0, short_side_m=2.0, h_m=H, rho_min=RHO_MIN)
    beta = 3.0 / 2.0
    assert d.beta == pytest.approx(beta)
    assert d.gamma_s == pytest.approx(2.0 / (beta + 1.0))  # 0.8


def test_central_band_width_equals_short_side():
    d = distribute_short_direction(0.0030, long_side_m=4.0, short_side_m=2.0, h_m=H, rho_min=RHO_MIN)
    central = d.bands[0]
    outer = d.bands[1]
    assert central.width_m == pytest.approx(2.0)  # = lado corto
    assert outer.width_m == pytest.approx(2.0)  # = 4.0 - 2.0
    assert central.width_m + outer.width_m == pytest.approx(4.0)


def test_central_band_gets_gamma_s_fraction_when_flexure_governs():
    # As_total muy superior al mínimo -> el reparto puro de §15.4.4 no se altera
    As_total = 0.0200
    d = distribute_short_direction(As_total, long_side_m=4.0, short_side_m=2.0, h_m=H, rho_min=RHO_MIN)
    gamma_s = 2.0 / (4.0 / 2.0 + 1.0)  # 0.6667
    assert d.bands[0].As_required_m2 == pytest.approx(gamma_s * As_total)
    assert d.bands[1].As_required_m2 == pytest.approx((1 - gamma_s) * As_total)
    assert not d.bands[0].topped_up
    assert not d.bands[1].topped_up


def test_outer_bands_are_topped_up_when_minimum_governs():
    """HALLAZGO documentado: si As_total está gobernado por la cuantía mínima,
    el reparto de §15.4.4 deja las franjas exteriores por debajo de ese mínimo.
    El motor las eleva y lo declara."""
    B_long, L_short = 4.0, 2.0
    As_total = RHO_MIN * B_long * H  # gobernado por el mínimo
    d = distribute_short_direction(As_total, B_long, L_short, H, RHO_MIN)

    gamma_s = 2.0 / (B_long / L_short + 1.0)
    outer_raw = (1 - gamma_s) * As_total
    outer_min = RHO_MIN * (B_long - L_short) * H

    assert outer_raw < outer_min  # confirma el hallazgo
    assert d.bands[1].topped_up is True
    assert d.bands[1].As_required_m2 == pytest.approx(outer_min)
    assert "mínima" in d.note


def test_central_band_never_needs_topping_up():
    # Demostrado algebraicamente: el cociente de la franja central es 2B/(B+L) >= 1
    for B_long, L_short in [(2.5, 2.0), (4.0, 2.0), (6.0, 2.0), (3.0, 2.9)]:
        As_total = RHO_MIN * B_long * H
        d = distribute_short_direction(As_total, B_long, L_short, H, RHO_MIN)
        assert d.bands[0].topped_up is False, f"B={B_long}, L={L_short}"


def test_total_after_distribution_never_less_than_input():
    As_total = RHO_MIN * 4.0 * H
    d = distribute_short_direction(As_total, 4.0, 2.0, H, RHO_MIN)
    assert d.As_total_after_distribution_m2 >= As_total - 1e-12


def test_no_band_falls_below_its_own_minimum():
    for B_long, L_short in [(2.0, 2.0), (3.0, 2.0), (5.0, 2.5), (4.0, 3.9)]:
        As_total = RHO_MIN * B_long * H
        d = distribute_short_direction(As_total, B_long, L_short, H, RHO_MIN)
        for band in d.bands:
            assert band.As_required_m2 >= band.As_min_m2 - 1e-12


def test_rejects_swapped_sides():
    with pytest.raises(ValueError, match="debe ser >="):
        distribute_short_direction(0.002, long_side_m=2.0, short_side_m=3.0, h_m=H, rho_min=RHO_MIN)
