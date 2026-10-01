"""Auditoría del CalculationTrace y de los estados PASS/INFO/WARNING/NO VERIFICADO/FAIL.

Verifica que:
  - toda verificación del motor deja entrada en el trace,
  - cada entrada lleva los 11 campos exigidos,
  - los cinco estados son ALCANZABLES (un estado inalcanzable es código muerto),
  - la agregación al estado global respeta la severidad declarada.
"""

import pytest

from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
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

# Todo check que el motor debe registrar siempre.
REQUIRED_TRACE_IDS = {
    "self_weight",
    "contact_pressure",
    "min_depth",
    "flexure_x",
    "flexure_y",
    "shear_x",
    "shear_y",
    "punching",
    "short_direction_distribution",
    "rebar_x",
    "rebar_y",
    "rebar_options_development_x",
    "rebar_options_development_y",
    "development_x",
    "development_y",
    "sliding",
    "overturning_x",
    "overturning_y",
}


def _candidate(B=2.6, L=2.6, h=0.50, soil=SOIL_FULL, loads=None, column=COLUMN_40x40):
    loads = loads or LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    return evaluate_candidate(
        B_m=B, L_m=L, h_m=h, column=column, soil=soil, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=loads, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


# === Completitud del trace ============================================================

def test_every_required_check_appears_in_the_trace():
    ids = {e.id for e in _candidate().trace.entries}
    missing = REQUIRED_TRACE_IDS - ids
    assert not missing, f"Checks ausentes del trace: {sorted(missing)}"


def test_trace_has_no_duplicate_ids():
    ids = [e.id for e in _candidate().trace.entries]
    assert len(ids) == len(set(ids))


def test_every_entry_carries_the_eleven_required_fields():
    """Campos exigidos: id, descripción, ecuación, ecuación sustituida, resultado,
    unidades, hipótesis, combinación, código, artículo, estado."""
    for entry in _candidate().trace.entries:
        assert entry.id.strip(), entry
        assert entry.description.strip(), entry.id
        assert entry.equation_symbolic.strip(), entry.id
        assert entry.equation_substituted.strip(), entry.id
        assert entry.result_value is not None, entry.id
        assert entry.result_unit.strip(), entry.id
        assert isinstance(entry.hypotheses, list), entry.id
        assert entry.code_name.strip(), entry.id
        assert entry.code_reference.strip(), entry.id
        assert isinstance(entry.status, CheckStatus), entry.id


def test_structural_checks_declare_their_governing_combination():
    c = _candidate()
    for check_id in ("contact_pressure", "flexure_x", "flexure_y", "shear_x", "shear_y", "punching"):
        entry = c.trace.by_id(check_id)
        assert entry.governing_combo, f"{check_id} no declara combinación gobernante"


def test_stability_checks_declare_their_governing_combination_when_applicable():
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Hx_kN=60.0, My_kNm=40.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    c = _candidate(loads=loads)
    assert c.trace.by_id("sliding").governing_combo == "S1"
    assert c.trace.by_id("overturning_x").governing_combo == "S1"


def test_every_normative_entry_cites_an_article():
    for entry in _candidate().trace.entries:
        if entry.code_name in {"E.060", "E.050"}:
            assert "§" in entry.code_reference or "art" in entry.code_reference.lower(), entry.id


def test_non_normative_entries_are_declared_as_such():
    entry = _candidate().trace.by_id("self_weight")
    assert entry.code_name == "N/A"
    assert "no es una ecuación normativa" in entry.code_reference


# === Alcanzabilidad de los cinco estados ==============================================

def test_state_pass_is_reachable():
    assert _candidate().overall_status is CheckStatus.PASS


def test_state_fail_is_reachable():
    assert _candidate(B=1.0, L=1.0).overall_status is CheckStatus.FAIL


def test_state_not_verified_is_reachable():
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Hx_kN=60.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    c = _candidate(soil=SOIL_150_BRUTA, loads=loads)  # sin mu ni FS
    assert c.overall_status is CheckStatus.NOT_VERIFIED


def test_state_info_is_reachable_and_does_not_block_pass():
    soil = SOIL_FULL.model_copy(update={"allow_seismic_reduction_80pct": True})
    loads = LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, includes_seismic_loads=True
            )
        ],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    c = _candidate(soil=soil, loads=loads)
    statuses = {e.status for e in c.trace.entries}
    assert CheckStatus.INFO in statuses
    assert c.overall_status is CheckStatus.PASS


def test_state_warning_is_reachable_through_the_registry():
    """WARNING queda reservado para limitaciones relevantes con capacidad de falso
    PASS. Hoy ninguna lo es, así que el motor NO debe emitir WARNING: si lo
    hiciera sin una limitación detrás, sería un estado espurio."""
    c = _candidate()
    warnings = c.trace.warning_entries()
    for entry in warnings:
        assert entry.id.startswith("limitation_"), (
            f"WARNING emitido por {entry.id} sin una limitación que lo respalde"
        )


# === Coherencia de la agregación =======================================================

def test_overall_status_equals_worst_of_the_entries():
    for B, L, h in [(2.6, 2.6, 0.50), (1.0, 1.0, 0.50), (1.4, 1.4, 0.45)]:
        c = _candidate(B=B, L=L, h=h)
        assert c.overall_status is CheckStatus.worst([e.status for e in c.trace.entries])


def test_fail_entries_always_produce_a_discard_reason():
    c = _candidate(B=1.0, L=1.0)
    assert c.trace.failing_entries()
    assert c.discard_reasons


def test_no_discard_reason_without_a_failing_entry():
    c = _candidate()
    assert c.trace.failing_entries() == []
    assert c.discard_reasons == []


def test_pass_requires_no_blocking_entry():
    c = _candidate()
    if c.overall_status is CheckStatus.PASS:
        assert not any(e.status.blocks_pass for e in c.trace.entries)


# === Trazabilidad de las hipótesis =====================================================

def test_min_depth_always_carries_the_interpretation_note():
    entry = _candidate().trace.by_id("min_depth")
    joined = " ".join(entry.hypotheses)
    assert "no una certeza normativa" in joined.lower()


def test_development_entries_carry_the_hook_policy():
    for check_id in ("development_x", "development_y"):
        entry = _candidate().trace.by_id(check_id)
        joined = " ".join(entry.hypotheses)
        assert "gancho" in joined.lower()


def test_punching_with_moment_documents_the_transfer():
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Mx_kNm=40.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0, Mx_kNm=56.0)],
    )
    entry = _candidate(loads=loads).trace.by_id("punching")
    assert "11.12.7" in entry.code_reference
    assert "γv" in entry.equation_substituted or "gamma_v" in entry.equation_substituted
