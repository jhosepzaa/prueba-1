import math

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode, MinDepthInterpretation

code = E060ConcreteCode()


def test_phi_factors():
    phi = code.phi_factors()
    assert phi.flexion == 0.90
    assert phi.cortante == 0.85


def test_fc_min():
    value, ref = code.fc_min_MPa()
    assert value == 17.0
    assert "E.060" in ref


def test_cover_footing():
    value, ref = code.cover_footing_mm()
    assert value == 75.0  # §7.7.1 a), E.060 propuesta 2019 (Fase 10A, A1)


def test_one_way_shear_vc_hand_check():
    # Vc = 0.17*sqrt(21)*2000mm*422mm (bw=2.0m, d=0.422m) -> ~657.3 kN
    result = code.one_way_shear_vc(fc_MPa=21.0, bw_m=2.0, d_m=0.422)
    expected_N = 0.17 * math.sqrt(21.0) * 2000.0 * 422.0
    assert result.value == pytest.approx(expected_N / 1000.0, rel=1e-6)
    assert result.value == pytest.approx(657.31, rel=1e-3)


def test_punching_shear_vc_governing_case():
    # Columna cuadrada (beta=1) -> ec. 11-43 (0.33*sqrt(fc)*bo*d) gobierna
    # frente a interior alpha_s=40 con bo grande. Verificado a mano: ~2098.5 kN.
    result = code.punching_shear_vc(fc_MPa=21.0, bo_m=3.288, d_m=0.422, beta_col=1.0, alpha_s=40.0)
    assert result.vc_kN == pytest.approx(2098.5, rel=2e-3)
    assert result.governing_equation == "11-43"
    assert "11-43" in result.code_reference


def test_punching_shear_vc_exposes_all_three_equations():
    result = code.punching_shear_vc(fc_MPa=21.0, bo_m=3.288, d_m=0.422, beta_col=1.0, alpha_s=40.0)
    # El valor de diseño debe ser el MENOR de las tres (E.060 §11.12.2.1).
    assert result.vc_kN == pytest.approx(min(result.vc_a_kN, result.vc_b_kN, result.vc_c_kN))
    # Con beta=1, la ec. 11-41 vale 0.51*sqrt(fc)*bo*d, mayor que 0.33*... (11-43)
    assert result.vc_a_kN > result.vc_c_kN


def test_punching_eq_11_33_governs_for_very_elongated_column():
    # La ec. 11-41 solo puede gobernar si beta > 2: 0.17*(1+2/beta) < 0.33 <=> beta > 2.06
    elongated = code.punching_shear_vc(fc_MPa=21.0, bo_m=6.0, d_m=0.50, beta_col=4.0, alpha_s=40.0)
    assert elongated.governing_equation == "11-41"


def test_punching_eq_11_34_governs_for_long_perimeter():
    # La ec. 11-42 gobierna cuando bo/d es grande (alpha_s*d/bo + 2 pequeño).
    long_perimeter = code.punching_shear_vc(fc_MPa=21.0, bo_m=40.0, d_m=0.30, beta_col=1.0, alpha_s=40.0)
    assert long_perimeter.governing_equation == "11-42"


def test_rho_min_temperature_branches():
    rho_420, _ = code.rho_min_temperature(fy_MPa=420.0, bar_type="corrugada")
    rho_280, _ = code.rho_min_temperature(fy_MPa=280.0, bar_type="corrugada")
    assert rho_420 == 0.0018
    assert rho_280 == 0.0020
    # Fase 10A (A8): §9.7.2 solo da cuantías para acero corrugado y §3.5.4.2 no admite
    # barras lisas como refuerzo de zapatas.
    with pytest.raises(ValueError, match="corrugado"):
        code.rho_min_temperature(fy_MPa=420.0, bar_type="lisa")


def test_short_direction_steel_fraction():
    result = code.short_direction_steel_fraction(beta=1.5)
    assert result.value == pytest.approx(2.0 / 2.5)


def test_min_depth_rule_default_uses_effective_depth():
    # Interpretación adoptada (ver docs/normativa/peralte_minimo_zapatas.md):
    # "altura medida sobre el refuerzo inferior" = peralte efectivo d.
    result = code.min_depth_rule(h_total_m=0.5, d_m=0.422, on_soil=True)
    assert result.value == pytest.approx(0.422)
    assert "EFFECTIVE_DEPTH" in result.code_reference


def test_min_depth_rule_configurable_to_total_depth():
    alt_code = E060ConcreteCode(min_depth_interpretation=MinDepthInterpretation.TOTAL_DEPTH)
    result = alt_code.min_depth_rule(h_total_m=0.5, d_m=0.422, on_soil=True)
    assert result.value == pytest.approx(0.5)
    assert "TOTAL_DEPTH" in result.code_reference


def test_min_depth_interpretation_changes_verdict_in_the_ambiguous_band():
    # h=0.35, d=0.272: cumple bajo TOTAL_DEPTH pero no bajo EFFECTIVE_DEPTH.
    # Esta banda es exactamente la razón por la que la interpretación importa.
    threshold = code.min_depth_threshold_m()
    default_governing = code.min_depth_rule(0.35, 0.272, on_soil=True).value
    total_governing = E060ConcreteCode(
        min_depth_interpretation=MinDepthInterpretation.TOTAL_DEPTH
    ).min_depth_rule(0.35, 0.272, on_soil=True).value
    assert default_governing < threshold  # FAIL con la interpretación adoptada
    assert total_governing >= threshold  # PASS con la alternativa


def test_min_depth_rule_rejects_pile_supported_footings():
    with pytest.raises(NotImplementedError):
        code.min_depth_rule(h_total_m=0.5, d_m=0.422, on_soil=False)
