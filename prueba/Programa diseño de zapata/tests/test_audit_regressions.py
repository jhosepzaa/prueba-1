"""Regresiones de los defectos encontrados en las auditorías.

Cada test aquí corresponde a un falso PASS real que el motor produjo y que fue
corregido. Existen para que no vuelvan a aparecer.
"""

import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.foundation.effective_depth import resolve_effective_depth, upper_layer_depth
from engine.optimization.alternative_generator import Alternative, generate_alternatives
from engine.optimization.arming_solutions import generate_arming_solutions
from engine.optimization.discard_explainer import explain_candidate
from engine.optimization.metrics import compute_metrics
from engine.results.status import CheckStatus
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

SOIL_FULL = SOIL_150_BRUTA.model_copy(
    update={"mu_friction_soil_concrete": 0.45, "FS_sliding_required": 1.5, "FS_overturning_required": 1.5}
)
LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
)


def _candidate(B=2.6, L=2.6, h=0.50, soil=SOIL_FULL, loads=LOADS):
    return evaluate_candidate(
        B_m=B, L_m=L, h_m=h, column=COLUMN_40x40, soil=soil,
        concrete=CONCRETE_21, steel=STEEL_420, load_case_set=loads,
        code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


# === REGRESIÓN 1: d sobreestimado producía capacidades infladas y PASS ==============

def test_engine_d_never_exceeds_the_real_worst_layer_depth():
    """DEFECTO: el motor usaba d con un diámetro ASUMIDO (16 mm) y un solo valor
    para ambas capas. Medido: d_motor=422 mm contra d_real_superior=410.9 mm,
    con el candidato reportado como PASS."""
    for B, L, h in [(2.0, 2.0, 0.40), (2.6, 2.6, 0.50), (3.0, 2.0, 0.60), (4.0, 2.5, 0.80)]:
        c = _candidate(B=B, L=L, h=h)
        worst_real = min(c.rebar_geometry.layer_x.d_m, c.rebar_geometry.layer_y.d_m)
        assert c.d_m <= worst_real + 1e-9, (
            f"B={B} L={L} h={h}: d={c.d_m:.4f} sobreestima el d real {worst_real:.4f}"
        )


def test_discrepancy_note_never_reports_overestimation():
    for B, L, h in [(2.0, 2.0, 0.40), (2.6, 2.6, 0.50), (3.5, 2.0, 0.70)]:
        c = _candidate(B=B, L=L, h=h)
        assert "SOBREESTIMADAS" not in c.rebar_geometry.d_discrepancy_note


def test_effective_depth_uses_upper_layer_formula():
    d = upper_layer_depth(h_m=0.50, cover_m=0.070, db_bottom_m=0.0127, db_top_m=0.0127)
    assert d == pytest.approx(0.50 - 0.070 - 0.0127 - 0.00635)


def test_effective_depth_resolution_converges_to_actual_bars():
    d = resolve_effective_depth(
        h_m=0.50, cover_m=CODE.cover_footing_mm()[0] / 1000.0, assumed_db_m=0.016, B_m=2.6, L_m=2.6,
        column=COLUMN_40x40, soil=SOIL_FULL, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE,
    )
    c = _candidate()
    assert d == pytest.approx(c.d_m)
    # y corresponde a barras reales del catálogo, no a la asumida de 16 mm
    assert d != pytest.approx(0.50 - CODE.cover_footing_mm()[0] / 1000.0 - 0.008)


def test_assumed_diameter_no_longer_changes_the_result():
    """Si el `d` se resuelve por punto fijo, el diámetro sembrado es irrelevante."""
    base = DEPTH_PARAMS_DEFAULT
    seeded_small = base.model_copy(update={"assumed_bar_diameter_mm": 9.5})
    seeded_large = base.model_copy(update={"assumed_bar_diameter_mm": 34.9})
    common = dict(
        B_m=2.6, L_m=2.6, h_m=0.50, column=COLUMN_40x40, soil=SOIL_FULL,
        concrete=CONCRETE_21, steel=STEEL_420, load_case_set=LOADS,
        code=CODE, contact_model=CONTACT_MODEL,
    )
    a = evaluate_candidate(**common, depth_params=seeded_small)
    b = evaluate_candidate(**common, depth_params=seeded_large)
    assert a.d_m == pytest.approx(b.d_m)


# === REGRESIÓN 2: opciones de armado con desarrollo sin verificar ====================

def test_every_offered_rebar_option_has_its_own_development_verified():
    """DEFECTO: `check_development_length` corría solo sobre la barra de
    `select_rebar`. Medido: 12 de 16 soluciones de armado usaban un diámetro
    cuya ld nunca se verificó."""
    c = _candidate()
    for options in (c.rebar_options_x, c.rebar_options_y):
        assert options, "Debe haber al menos una opción desarrollable"
        for option in options:
            assert option.development_ok is True
            assert option.ld_required_m is not None
            assert option.ld_available_m is not None
            assert option.ld_required_m <= option.ld_available_m + 1e-9


def test_development_length_scales_with_the_option_diameter():
    c = _candidate(B=3.2, L=3.2)
    options = sorted(c.rebar_options_x, key=lambda o: o.diameter_mm)
    if len(options) >= 2:
        lds = [o.ld_required_m for o in options]
        assert lds == sorted(lds), "ld debe crecer con el diámetro"


def test_no_arming_solution_is_built_on_an_undevelopable_bar():
    c = _candidate()
    alt = Alternative(id="ALT-001", candidate=c, metrics=compute_metrics(c, SOIL_FULL.Df_m, 0.070))
    for solution in generate_arming_solutions(alt, 0.070):
        assert solution.rebar_x.development_ok is True
        assert solution.rebar_y.development_ok is True


def test_options_are_filtered_when_large_bars_cannot_develop():
    """En una zapata de voladizo corto, los diámetros grandes deben quedar fuera."""
    small = _candidate(B=1.6, L=1.6, h=0.45)
    large = _candidate(B=3.6, L=3.6, h=0.45)
    max_db_small = max((o.diameter_mm for o in small.rebar_options_x), default=0)
    max_db_large = max((o.diameter_mm for o in large.rebar_options_x), default=0)
    assert max_db_small <= max_db_large


def test_trace_records_which_options_were_rejected_by_development():
    c = _candidate()
    entry = c.trace.by_id("rebar_options_development_x")
    assert entry is not None
    assert "aceptadas" in entry.equation_substituted
    assert "descartadas por desarrollo" in entry.equation_substituted


# === REGRESIÓN 3: WARNING rotulado como DESCARTADA ===================================

def test_non_failing_candidate_is_never_labelled_discarded():
    c = _candidate()
    text = explain_candidate(c, "ALT-001").to_text()
    assert "-- DESCARTADA" not in text


# === REGRESIÓN 4: fuerzas horizontales con PASS silencioso ===========================

def test_horizontal_forces_are_never_silently_ignored():
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Hx_kN=90.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0, Hx_kN=126.0)],
    )
    sin_params = _candidate(soil=SOIL_150_BRUTA, loads=loads)
    assert sin_params.stability.sliding.status is CheckStatus.NOT_VERIFIED
    assert sin_params.overall_status is not CheckStatus.PASS

    con_params = _candidate(soil=SOIL_FULL, loads=loads)
    # Fase 10B: el FS se calcula (H no se ignora), pero con combinaciones directas un
    # cumplimiento no puede afirmarse (E.020 art. 20.1).
    assert con_params.stability.sliding.FS_obtained is not None
    assert con_params.stability.sliding.status is not CheckStatus.PASS
    assert con_params.stability.sliding.H_resultant_kN == pytest.approx(90.0)


# === Coherencia global del pipeline ===================================================

def test_generator_produces_only_developable_solutions_end_to_end():
    from engine.domain.search_parameters import GeometrySearchParameters

    result = generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_FULL, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GeometrySearchParameters(
            B_min_m=1.4, B_max_m=3.0, B_step_m=0.4, L_min_m=1.4, L_max_m=3.0, L_step_m=0.4, max_LB_ratio=1.6
        ),
        depth_params=DEPTH_PARAMS_DEFAULT,
    )
    assert result.valid
    for alt in result.valid:
        c = alt.candidate
        assert c.d_m <= min(c.rebar_geometry.layer_x.d_m, c.rebar_geometry.layer_y.d_m) + 1e-9
        assert all(o.development_ok for o in c.rebar_options_x)
        assert all(o.development_ok for o in c.rebar_options_y)
        assert c.overall_status is not CheckStatus.FAIL
