import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import GeometrySearchParameters
from engine.optimization.alternative_generator import generate_alternatives
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
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0, Mx_kNm=30.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0, Mx_kNm=42.0)],
)

GEOM = GeometrySearchParameters(
    B_min_m=1.0, B_max_m=2.6, B_step_m=0.2,
    L_min_m=1.0, L_max_m=2.6, L_step_m=0.2,
    max_LB_ratio=1.5,
)


def _generate():
    return generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GEOM, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_generates_both_valid_and_discarded():
    result = _generate()
    assert len(result.valid) > 0, "Debe encontrar al menos una alternativa viable"
    assert len(result.discarded) > 0, "Con B=1.0 m en el rango, algunas deben descartarse"
    assert result.n_geometries_evaluated == len(result.valid) + len(result.discarded)


def test_no_valid_alternative_has_a_failing_check():
    result = _generate()
    for alt in result.valid:
        # PASS o WARNING son aceptables; FAIL nunca. Un WARNING señala una
        # condición que requiere revisión del ingeniero (p. ej. punzonamiento
        # con transferencia de momento no implementada) pero no invalida.
        assert alt.candidate.overall_status is not CheckStatus.FAIL
        assert alt.candidate.discard_reasons == []
        assert alt.candidate.trace.failing_entries() == []


def test_alternatives_with_moment_get_a_real_punching_verification():
    """L1 cerrada: los momentos ya no degradan a WARNING, se verifican."""
    result = _generate()
    for alt in result.valid:
        assert alt.candidate.punching.unbalanced_moment_present is True
        assert alt.candidate.punching.moment_transfer is not None
        assert alt.candidate.punching.status is not CheckStatus.FAIL


def test_every_discarded_geometry_has_an_explicit_reason():
    result = _generate()
    for disc in result.discarded:
        assert disc.representative is not None
        assert disc.representative.discard_reasons, (
            f"La geometría {disc.B_m}x{disc.L_m} se descartó sin razón registrada"
        )


def test_ids_are_unique():
    result = _generate()
    ids = [a.id for a in result.valid] + [d.id for d in result.discarded]
    assert len(ids) == len(set(ids))


def test_discard_histogram_accounts_for_reasons():
    result = _generate()
    histogram = result.discard_reason_histogram()
    assert histogram, "Debe haber al menos un motivo de descarte registrado"
    # el motivo dominante con B pequeño y este suelo debe ser la presión de contacto
    assert any("qmax > qadm" in reason for reason in histogram)


def test_small_geometries_are_discarded_and_large_ones_accepted():
    result = _generate()
    discarded_areas = [d.B_m * d.L_m for d in result.discarded]
    valid_areas = [a.candidate.B_m * a.candidate.L_m for a in result.valid]
    # La menor área válida debe ser mayor que la menor área descartada:
    # confirma que el filtro sigue una lógica física, no aleatoria.
    assert min(valid_areas) > min(discarded_areas)


def test_metrics_are_consistent_with_geometry():
    result = _generate()
    alt = result.valid[0]
    c = alt.candidate
    assert alt.metrics.concrete_volume_m3 == pytest.approx(c.B_m * c.L_m * c.h_m)
    assert alt.metrics.footing_area_m2 == pytest.approx(c.B_m * c.L_m)
    assert alt.metrics.max_plan_dimension_m == pytest.approx(max(c.B_m, c.L_m))
    assert alt.metrics.steel_mass_kg > 0.0


def test_column_larger_than_footing_is_skipped_not_crashed():
    # B_min menor que la columna: esas geometrías deben omitirse sin excepción.
    geom = GeometrySearchParameters(
        B_min_m=0.2, B_max_m=2.4, B_step_m=0.2, L_min_m=0.2, L_max_m=2.4, L_step_m=0.2, max_LB_ratio=1.5
    )
    result = generate_alternatives(
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=geom, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    for alt in result.valid:
        assert alt.candidate.B_m > COLUMN_40x40.bx_m
    for disc in result.discarded:
        assert disc.B_m > COLUMN_40x40.bx_m
