from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
from engine.optimization.discard_explainer import explain_candidate
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

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0)],
)


def _failing_candidate():
    # zapata 1.0x1.0: falla por presión de contacto (caso golden 05)
    return evaluate_candidate(
        B_m=1.0, L_m=1.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def _passing_candidate():
    return evaluate_candidate(
        B_m=2.0, L_m=2.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_explanation_separates_failed_and_passed_checks():
    explanation = explain_candidate(_failing_candidate(), "DESC-001")
    assert explanation.verdict is CheckStatus.FAIL
    failed_ids = {o.check_id for o in explanation.failed}
    passed_ids = {o.check_id for o in explanation.passed}

    assert "contact_pressure" in failed_ids
    # los checks estructurales sí deben pasar en esta geometría
    assert "punching" in passed_ids
    assert failed_ids.isdisjoint(passed_ids)


def test_explanation_covers_every_trace_entry():
    """La partición en cubos debe ser EXHAUSTIVA.

    Se comparan identificadores y no solo cantidades: dos errores que se compensen
    —una verificación perdida y otra duplicada— darían el mismo total y pasarían
    inadvertidos. Lo que más importa que no desaparezca es un NO VERIFICADO."""
    candidate = _failing_candidate()
    explanation = explain_candidate(candidate, "DESC-001")

    en_cubos = [
        o.check_id
        for grupo in (
            explanation.failed, explanation.warnings, explanation.not_verified,
            explanation.passed, explanation.informative,
        )
        for o in grupo
    ]
    en_traza = [e.id for e in candidate.trace.entries]

    assert sorted(en_cubos) == sorted(en_traza), (
        f"Verificaciones perdidas: {sorted(set(en_traza) - set(en_cubos))} | "
        f"duplicadas o inventadas: {sorted(set(en_cubos) - set(en_traza))}"
    )
    assert len(en_cubos) == len(en_traza), "Alguna verificación aparece en más de un cubo"


def test_ningun_estado_puede_desaparecer_de_la_explicacion():
    """Regresión: los cubos filtraban solo PASS/WARNING/FAIL, de modo que INFO y
    NO VERIFICADO se perdían en silencio."""
    from engine.results.status import CheckStatus

    candidate = _failing_candidate()
    explanation = explain_candidate(candidate, "DESC-001")
    cubo_de = {
        CheckStatus.FAIL: explanation.failed,
        CheckStatus.WARNING: explanation.warnings,
        CheckStatus.NOT_VERIFIED: explanation.not_verified,
        CheckStatus.PASS: explanation.passed,
        CheckStatus.INFO: explanation.informative,
    }
    for entrada in candidate.trace.entries:
        cubo = cubo_de[entrada.status]
        assert any(o.check_id == entrada.id for o in cubo), (
            f"La verificación «{entrada.id}» con estado {entrada.status.value} no aparece "
            f"en su cubo correspondiente."
        )


def test_explanation_carries_governing_combo_and_code_reference():
    explanation = explain_candidate(_failing_candidate(), "DESC-001")
    contact = next(o for o in explanation.failed if o.check_id == "contact_pressure")
    assert contact.governing_combo == "S1"
    assert "E.060" in contact.code_reference


def test_code_reference_is_not_duplicated():
    explanation = explain_candidate(_passing_candidate(), "ALT-001")
    shear = next(o for o in explanation.passed if o.check_id == "shear_x")
    assert shear.code_reference.count("E.060") == 1, shear.code_reference
    weight = next(o for o in explanation.passed if o.check_id == "self_weight")
    assert not weight.code_reference.startswith("N/A N/A")


def test_valid_candidate_reports_no_failures():
    explanation = explain_candidate(_passing_candidate(), "ALT-001")
    assert explanation.failed == []
    assert explanation.verdict is not CheckStatus.FAIL


def test_non_failing_candidate_is_never_labelled_as_discarded():
    """Una alternativa que no falla ninguna verificacion no puede rotularse como rechazada,
    sea su estado PASS o WARNING.

    ACTUALIZADO en el pendiente 8: el rotulo de descarte se llama ahora RECHAZADA en las
    tres tipologias, y el de PASS es CONFORME."""
    explanation = explain_candidate(_passing_candidate(), "ALT-001")
    assert explanation.verdict is not CheckStatus.FAIL
    text = explanation.to_text()
    assert "-- RECHAZADA" not in text
    assert "-- DESCARTADA" not in text
    assert ("CONFORME" in text) or ("ACEPTADA CON OBSERVACIONES" in text)
