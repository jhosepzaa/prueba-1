import math

import pytest

from engine.reinforcement.rebar_selector import select_rebar
from engine.results.status import CheckStatus


def test_select_rebar_meets_as_required():
    # As_req = 18 cm2 en un ancho de 2.0 m
    selection = select_rebar(As_required_m2=0.0018, width_m=2.0, h_m=0.5)
    assert selection.status == CheckStatus.PASS
    assert selection.As_provided_m2 >= 0.0018


def test_select_rebar_respects_max_spacing():
    selection = select_rebar(As_required_m2=0.0001, width_m=2.0, h_m=0.5)
    max_spacing = min(3 * 0.5, 0.400)
    assert selection.spacing_m <= max_spacing + 1e-9


def test_select_rebar_handles_nan_gracefully():
    selection = select_rebar(As_required_m2=float("nan"), width_m=2.0, h_m=0.5)
    assert selection.status == CheckStatus.FAIL
    assert math.isnan(selection.As_required_m2)
