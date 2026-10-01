"""L4 — Longitud de desarrollo y anclaje (E.060 §15.6 → Cap. 12)."""

import math

import pytest

from engine.codes.peru.e060_development import (
    MIN_LD_M,
    PSI_T_PSI_E_CAP,
    development_length_eq_12_1,
    development_length_table_12_1,
    hook_development_length,
    psi_s_bar_size,
    psi_t_top_bar,
    simplified_conditions_met,
)
from engine.reinforcement.development_check import check_development_length
from engine.reinforcement.rebar_geometry import build_rebar_geometry
from engine.results.status import CheckStatus


def _layer(B=3.0, L=3.0, h=0.60, bx=0.40, by=0.40, cover=0.070, db=0.0159, s=0.20, hook="ninguno"):
    geom = build_rebar_geometry(
        B_m=B, L_m=L, h_m=h, bx_m=bx, by_m=by, cover_m=cover,
        db_x_m=db, db_y_m=db, n_bars_x=15, n_bars_y=15,
        spacing_x_m=s, spacing_y_m=s, d_used_by_engine_m=h - cover - db / 2,
        hook_x=hook, hook_y=hook,
    )
    return geom.layer_x


# --- Factores de la Tabla 12.2 -------------------------------------------------------

def test_psi_t_bottom_bars_of_a_footing_are_never_top_bars():
    # 70 mm de recubrimiento << 300 mm de concreto fresco debajo
    assert psi_t_top_bar(0.078) == 1.0


def test_psi_t_top_bar_threshold_is_300mm():
    assert psi_t_top_bar(0.299) == 1.0
    assert psi_t_top_bar(0.300) == 1.3


def test_psi_s_depends_on_bar_size():
    assert psi_s_bar_size(0.0127) == 0.8  # 1/2"
    assert psi_s_bar_size(0.01905) == 0.8  # 3/4" exacto
    assert psi_s_bar_size(0.0254) == 1.0  # 1"


# --- Tabla 12.1 vs ec. 12-1 -----------------------------------------------------------

def test_simplified_conditions_two_alternative_paths():
    db = 0.016
    # (a) sep>=db y rec>=db y estribos minimos
    assert simplified_conditions_met(0.02, 0.070, db, has_min_stirrups=True) is True
    # (b) sep>=2db y rec>=db, sin estribos
    assert simplified_conditions_met(0.035, 0.070, db, has_min_stirrups=False) is True
    # ninguna: sep < 2db y sin estribos
    assert simplified_conditions_met(0.02, 0.070, db, has_min_stirrups=False) is False


def test_table_12_1_small_bar_coefficient_is_2_6():
    db, fy, fc = 0.0159, 420.0, 21.0
    r = development_length_table_12_1(db, fy, fc, psi_t=1.0, psi_e=1.0)
    expected = (fy * 1.0 / (2.6 * 1.0 * math.sqrt(fc))) * db
    assert r.ld_before_minimum_m == pytest.approx(expected)
    assert r.method == "Tabla 12.1"


def test_table_12_1_large_bar_coefficient_is_2_1():
    db, fy, fc = 0.0254, 420.0, 21.0
    r = development_length_table_12_1(db, fy, fc, psi_t=1.0, psi_e=1.0)
    expected = (fy * 1.0 / (2.1 * 1.0 * math.sqrt(fc))) * db
    assert r.ld_before_minimum_m == pytest.approx(expected)


def test_minimum_300mm_governs_for_small_bars_in_strong_concrete():
    # 3/8" con f'c=35 MPa: ld = 420/(2.6·sqrt(35))·9.5 = 259.4 mm < 300 mm -> gobierna el mínimo.
    # (Con f'c=21 daría 334.9 mm y el mínimo NO gobernaría.)
    r = development_length_table_12_1(0.0095, 420.0, 35.0, psi_t=1.0, psi_e=1.0)
    assert r.ld_before_minimum_m == pytest.approx(0.2594, rel=1e-3)
    assert r.ld_before_minimum_m < MIN_LD_M
    assert r.ld_m == pytest.approx(MIN_LD_M)
    assert r.governed_by_minimum is True


def test_minimum_does_not_govern_when_ld_exceeds_300mm():
    r = development_length_table_12_1(0.0095, 420.0, 21.0, psi_t=1.0, psi_e=1.0)
    assert r.ld_before_minimum_m == pytest.approx(0.3349, rel=1e-3)
    assert r.governed_by_minimum is False
    assert r.ld_m == pytest.approx(r.ld_before_minimum_m)


def test_eq_12_1_caps_cb_ktr_ratio_at_2_5():
    r = development_length_eq_12_1(
        db_m=0.0127, fy_MPa=420.0, fc_MPa=21.0, cb_m=0.20,  # cb/db enorme
        psi_t=1.0, psi_e=1.0, psi_s=0.8,
    )
    assert r.cb_ktr_capped is True
    assert r.cb_plus_ktr_over_db == pytest.approx(2.5)


def test_psi_t_psi_e_product_is_capped_at_1_7():
    r = development_length_table_12_1(0.0159, 420.0, 21.0, psi_t=1.3, psi_e=1.5)
    assert r.psi_t_psi_e_capped is True
    expected = (420.0 * PSI_T_PSI_E_CAP / (2.6 * math.sqrt(21.0))) * 0.0159
    assert r.ld_before_minimum_m == pytest.approx(expected)


def test_sqrt_fc_is_capped_at_7_3():
    """Fase 10A (A7). §12.1.3 de la E.060 designada: 7,3 MPa (posible errata declarada)."""
    r = development_length_table_12_1(0.0159, 420.0, 100.0, psi_t=1.0, psi_e=1.0)  # sqrt=10
    assert r.sqrt_fc_capped is True
    assert r.sqrt_fc_used_MPa == pytest.approx(7.3)


# --- CASOS PEDIDOS: suficiente / insuficiente -----------------------------------------

def test_bar_with_sufficient_development():
    layer = _layer(B=3.0, bx=0.40)  # voladizo 1.30 -> disponible 1.23 m
    r = check_development_length(layer, fy_MPa=420.0, fc_MPa=21.0)
    assert r.status is CheckStatus.PASS
    assert r.deficit_m < 0
    assert "suficiente" in r.message.lower()


def test_bar_without_sufficient_development_fails_with_exact_deficit():
    # Zapata pequeña + barra grande -> disponible corto
    layer = _layer(B=1.2, bx=0.40, db=0.0254, s=0.15)  # voladizo 0.40 -> disponible 0.33 m
    r = check_development_length(layer, fy_MPa=420.0, fc_MPa=21.0)
    assert r.status is CheckStatus.FAIL
    assert r.deficit_m > 0
    assert r.ld_required_m > r.ld_available_m
    assert "FALTAN" in r.message
    assert f"{r.deficit_m * 1000:.0f} mm" in r.message


# --- CASOS PEDIDOS: sensibilidad a los parámetros --------------------------------------

def test_larger_diameter_requires_more_development():
    small = check_development_length(_layer(db=0.0127), 420.0, 21.0)
    large = check_development_length(_layer(db=0.0254), 420.0, 21.0)
    assert large.ld_required_m > small.ld_required_m


def test_larger_cover_changes_the_result():
    """El recubrimiento entra por dos vías opuestas: aumenta cb (reduce ld por
    ec. 12-1) pero reduce la longitud disponible. Ambas deben verse."""
    low = check_development_length(_layer(cover=0.050), 420.0, 21.0)
    high = check_development_length(_layer(cover=0.100), 420.0, 21.0)
    assert high.ld_available_m < low.ld_available_m
    assert high.cover_m > low.cover_m


def test_higher_fc_reduces_required_development():
    weak = check_development_length(_layer(), 420.0, 21.0)
    strong = check_development_length(_layer(), 420.0, 35.0)
    assert strong.ld_required_m < weak.ld_required_m


def test_higher_fy_increases_required_development():
    fy420 = check_development_length(_layer(), 420.0, 21.0)
    fy520 = check_development_length(_layer(), 520.0, 21.0)
    assert fy520.ld_required_m > fy420.ld_required_m


def test_tighter_spacing_increases_required_development_via_cb():
    """Separación menor reduce cb (= min(rec+db/2, s/2)) y por ec. 12-1 alarga ld."""
    wide = check_development_length(_layer(s=0.30, db=0.0254), 420.0, 21.0)
    tight = check_development_length(_layer(s=0.06, db=0.0254), 420.0, 21.0)
    assert tight.cb_m < wide.cb_m
    assert tight.ld_required_m >= wide.ld_required_m


# --- Ganchos: nunca se asumen ----------------------------------------------------------

def test_hooks_are_never_assumed():
    layer = _layer()
    assert layer.has_hook is False
    r = check_development_length(layer, 420.0, 21.0)
    assert r.uses_hook is False
    assert r.hook_result is None
    assert "no se asume" in r.message.lower() or "sin gancho" in r.message.lower()


def test_declared_hook_is_used_and_shortens_the_requirement():
    straight = check_development_length(_layer(B=1.2, bx=0.40, db=0.0254), 420.0, 21.0)
    hooked = check_development_length(_layer(B=1.2, bx=0.40, db=0.0254, hook="90"), 420.0, 21.0)
    assert hooked.uses_hook is True
    assert hooked.hook_result is not None
    assert hooked.ld_required_m < straight.ld_required_m


def test_hook_equation_matches_12_5_2():
    db, fy, fc = 0.0254, 420.0, 21.0
    r = hook_development_length(db, fy, fc, "90")
    expected = 0.24 * 1.0 * 1.0 * fy / math.sqrt(fc) * db
    assert r.ldg_before_minimum_m == pytest.approx(expected)


def test_hook_minimum_is_max_of_8db_and_150mm():
    """Fase 10A (A4). §12.5.1: «no debe ser menor que 8 db ni 150 mm»: rigen ambos."""
    r = hook_development_length(0.0095, 420.0, 21.0, "90")  # 8db = 76 mm
    assert r.minimum_m == pytest.approx(0.150)
    grande = hook_development_length(0.0254, 420.0, 21.0, "90")  # 8db = 203 mm
    assert grande.minimum_m == pytest.approx(8 * 0.0254)


def test_hook_reduction_factors_only_when_declared():
    base = hook_development_length(0.0254, 420.0, 21.0, "90")
    reduced = hook_development_length(0.0254, 420.0, 21.0, "90", side_cover_ok_for_0_7=True)
    assert reduced.reduction_factor == pytest.approx(0.7)
    assert base.reduction_factor == pytest.approx(1.0)


def test_hook_rejects_none_type():
    with pytest.raises(ValueError):
        hook_development_length(0.0159, 420.0, 21.0, "ninguno")


# --- Geometría de barras: los defectos que reveló la auditoría --------------------------

def test_two_layers_have_different_effective_depths():
    geom = build_rebar_geometry(
        B_m=3.0, L_m=2.0, h_m=0.60, bx_m=0.4, by_m=0.4, cover_m=0.070,
        db_x_m=0.0159, db_y_m=0.0159, n_bars_x=10, n_bars_y=10,
        spacing_x_m=0.20, spacing_y_m=0.20, d_used_by_engine_m=0.522,
    )
    assert geom.layer_x.d_m > geom.layer_y.d_m  # X es la capa inferior (lado largo)
    assert geom.bottom_layer_direction == "X"
    assert geom.layer_x.d_m - geom.layer_y.d_m == pytest.approx(0.0159)


def test_bottom_layer_is_the_long_side_direction():
    geom = build_rebar_geometry(
        B_m=2.0, L_m=3.0, h_m=0.60, bx_m=0.4, by_m=0.4, cover_m=0.070,
        db_x_m=0.0159, db_y_m=0.0159, n_bars_x=10, n_bars_y=10,
        spacing_x_m=0.20, spacing_y_m=0.20, d_used_by_engine_m=0.522,
    )
    assert geom.bottom_layer_direction == "Y"
    assert geom.layer_y.d_m > geom.layer_x.d_m


def test_d_discrepancy_is_reported():
    geom = build_rebar_geometry(
        B_m=3.0, L_m=3.0, h_m=0.50, bx_m=0.4, by_m=0.4, cover_m=0.070,
        db_x_m=0.0127, db_y_m=0.0127, n_bars_x=10, n_bars_y=10,
        spacing_x_m=0.20, spacing_y_m=0.20, d_used_by_engine_m=0.422,  # asumido con db=16mm
    )
    assert "SOBREESTIMADAS" in geom.d_discrepancy_note


def test_available_length_is_cantilever_minus_side_cover():
    layer = _layer(B=3.0, bx=0.40, cover=0.070)
    assert layer.cantilever_m == pytest.approx(1.30)
    assert layer.available_development_length_m == pytest.approx(1.23)


def test_bar_length_is_span_minus_two_covers():
    layer = _layer(B=3.0, cover=0.070)
    assert layer.bar_length_m == pytest.approx(3.0 - 0.14)


def test_clear_spacing_is_spacing_minus_diameter():
    layer = _layer(s=0.20, db=0.0159)
    assert layer.clear_spacing_m == pytest.approx(0.20 - 0.0159)
