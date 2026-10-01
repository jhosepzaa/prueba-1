import pytest

from engine.reinforcement.rebar_alternatives import (
    MAX_OVERPROVISION_RATIO,
    generate_rebar_alternatives,
    max_spacing_m,
    min_clear_spacing_m,
)
from engine.results.status import CheckStatus


def test_min_spacing_uses_max_of_db_and_25mm():
    # E.060 §7.6.6: separación libre mínima = db, pero no menor de 25 mm
    assert min_clear_spacing_m(9.5) == pytest.approx((25.0 + 9.5) / 1000.0)  # gobierna 25 mm
    assert min_clear_spacing_m(34.9) == pytest.approx((34.9 + 34.9) / 1000.0)  # gobierna db


def test_max_spacing_is_min_of_3h_and_400mm():
    assert max_spacing_m(h_m=0.10) == pytest.approx(0.30)  # gobierna 3h
    assert max_spacing_m(h_m=0.60) == pytest.approx(0.40)  # gobierna 400 mm


def test_generates_several_distinct_alternatives():
    options = generate_rebar_alternatives(
        As_required_m2=0.0018, As_min_m2=0.0012, width_m=2.0, h_m=0.50
    )
    assert len(options) >= 2
    labels = [o.label for o in options]
    assert len(labels) == len(set(labels))


def test_every_alternative_meets_as_design_and_spacing_limits():
    options = generate_rebar_alternatives(
        As_required_m2=0.0018, As_min_m2=0.0012, width_m=2.0, h_m=0.50
    )
    As_design = max(0.0018, 0.0012)
    for o in options:
        assert o.As_provided_m2 >= As_design
        assert o.spacing_min_allowed_m <= o.spacing_m <= o.spacing_max_allowed_m
        assert o.spacing_ok is True
        assert o.status is CheckStatus.PASS


def test_alternatives_are_not_wasteful():
    options = generate_rebar_alternatives(
        As_required_m2=0.0018, As_min_m2=0.0012, width_m=2.0, h_m=0.50
    )
    for o in options:
        assert o.overprovision <= MAX_OVERPROVISION_RATIO


def test_reports_whether_minimum_or_flexure_governs():
    by_flexure = generate_rebar_alternatives(0.0030, 0.0012, width_m=2.0, h_m=0.50)
    by_minimum = generate_rebar_alternatives(0.0005, 0.0018, width_m=2.0, h_m=0.50)
    assert all(o.governed_by == "flexión" for o in by_flexure)
    assert all(o.governed_by == "cuantía mínima §9.7" for o in by_minimum)
    # cuando gobierna el mínimo, el As de diseño es el mínimo
    assert all(o.As_provided_m2 >= 0.0018 for o in by_minimum)


def test_alternatives_ordered_by_increasing_diameter():
    options = generate_rebar_alternatives(0.0018, 0.0012, width_m=2.0, h_m=0.50)
    diameters = [o.diameter_mm for o in options]
    assert diameters == sorted(diameters)


def test_larger_bars_use_wider_spacing():
    options = generate_rebar_alternatives(0.0018, 0.0012, width_m=2.0, h_m=0.50)
    if len(options) >= 2:
        # a mayor diámetro, para el mismo As, la separación no puede reducirse
        assert options[-1].spacing_m >= options[0].spacing_m


def test_nan_input_returns_no_alternatives():
    assert generate_rebar_alternatives(float("nan"), 0.0012, 2.0, 0.5) == []


def test_utilization_is_consistent_with_overprovision():
    options = generate_rebar_alternatives(0.0018, 0.0012, width_m=2.0, h_m=0.50)
    for o in options:
        assert o.utilization == pytest.approx(1.0 / o.overprovision)
        assert 0.0 < o.utilization <= 1.0
