import pytest

from engine.foundation.self_weight import compute_self_weight


def test_self_weight_with_backfill():
    result = compute_self_weight(
        B_m=2.0, L_m=2.0, h_m=0.5, Df_m=1.2, concrete_unit_weight_kNm3=24.0, soil_unit_weight_kNm3=18.0
    )
    assert result.W_footing_kN == pytest.approx(24.0 * 2.0 * 2.0 * 0.5)  # 48.0
    assert result.W_soil_backfill_kN == pytest.approx(18.0 * 2.0 * 2.0 * 0.7)  # 50.4
    assert result.W_total_kN == pytest.approx(98.4)


def test_self_weight_no_backfill_when_h_equals_df():
    result = compute_self_weight(
        B_m=2.0, L_m=2.0, h_m=1.2, Df_m=1.2, concrete_unit_weight_kNm3=24.0, soil_unit_weight_kNm3=18.0
    )
    assert result.W_soil_backfill_kN == 0.0
