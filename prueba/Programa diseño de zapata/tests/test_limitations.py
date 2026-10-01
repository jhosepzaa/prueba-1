"""Registro de limitaciones y MÁQUINA DE ESTADOS.

Verifica la corrección solicitada por el usuario:

    "No quiero que WARNING se convierta automáticamente en PASS simplemente
     porque se implementó otra limitación."
"""

import pytest

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.limitations import (
    LIMITATION_REGISTRY,
    LimitationKind,
    collect_applicable_limitations,
    limitation_by_id,
)
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

EXPECTED_LIMITATION_IDS = {
    "punching_moment_transfer",
    "seismic_reduction_80pct",
    "horizontal_forces",
    "development_length",
    "circular_columns",
    "min_depth_interpretation",
}

# Limitaciones de la zapata AISLADA que quedan fuera del invariante de abajo.
#
# VACÍO, y esa es la afirmación: la zapata aislada no tiene ninguna limitación declarada
# capaz de producir un falso PASS.
#
# Tuvo una durante un día. El bloque triangular (2026-09-19) destapó que el alivio del
# punzonamiento salía del campo lineal, que fuera del núcleo no existe; se declaró como
# `punching_partial_contact`, luego se estrechó a `punching_biaxial_uplift`, y el
# 2026-09-20 la decisión 1 la CERRÓ implementando el contacto unilateral por equilibrio.
# Al resolverse el hueco, la declaración dejó de tener objeto y se retiró.
#
# El conjunto se conserva vacío a propósito, no se borra: el invariante de abajo lo
# consulta, y volver a tener que llenarlo debe costar una línea y una justificación.
DESPEGUE_BIAXIAL_IDS: set[str] = set()

SOIL_WITH_STABILITY_PARAMS = SOIL_150_BRUTA.model_copy(
    update={"mu_friction_soil_concrete": 0.45, "FS_sliding_required": 1.5, "FS_overturning_required": 1.5}
)


def _evaluate(loads: LoadCaseSet, soil=SOIL_150_BRUTA, B=2.4, L=2.4, h=0.50):
    return evaluate_candidate(
        B_m=B, L_m=L, h_m=h,
        column=COLUMN_40x40, soil=soil, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=loads, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def _loads(**kwargs) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0, **kwargs)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0, **kwargs)],
    )


# --- Registro ---------------------------------------------------------------------

# Limitaciones propias de la zapata conectada (Fase 4). Se listan aparte porque el
# conjunto original describía el alcance de la zapata AISLADA y conviene que siga
# leyéndose como tal.
CONNECTED_LIMITATION_IDS = {
    "connected_uniform_pressure_premise",
    "connected_beam_bearing_on_soil",
    "connected_uplift_partial_contact",
    # Fase 9a: pendiente declarado del peso propio EXPLICITO de la viga.
    "connected_beam_fill_over_span",
    # Fase 10B.
    "connected_footing_stability_composition",
    # TBD-C13 (A'): factor de CM del peso propio de la viga en modo directo.
    "connected_beam_weight_factoring",
}


def test_registry_covers_all_declared_limitations():
    assert {lim.id for lim in LIMITATION_REGISTRY} == (
        EXPECTED_LIMITATION_IDS | CONNECTED_LIMITATION_IDS
    )


def test_every_limitation_declares_reference_and_impact():
    for lim in LIMITATION_REGISTRY:
        assert lim.code_reference.strip()
        assert lim.impact.strip()
        assert lim.description.strip()
        assert isinstance(lim.kind, LimitationKind)


def test_l1_l3_l4_are_now_implemented():
    for lid, enforcer in (
        ("punching_moment_transfer", "punching"),
        ("horizontal_forces", "stability"),
        ("development_length", "development"),
    ):
        lim = limitation_by_id(lid)
        assert lim.kind is LimitationKind.IMPLEMENTED, lid
        assert lim.enforced_by == enforcer
        assert lim.can_cause_false_pass is False


def test_ninguna_limitacion_de_zapata_aislada_puede_producir_un_falso_pass():
    """Tras cerrar L1, L3 y L4, ninguna limitación del alcance de la zapata AISLADA
    puede hacer pasar por válido un diseño inseguro: las restantes solo vuelven el
    resultado más conservador o se rechazan en validación de entrada.

    Este test conserva el invariante original. Lo que cambió en la Fase 4 es que
    aparecieron limitaciones NUEVAS, propias de la zapata conectada, que sí pueden
    producir un falso PASS —y por eso están declaradas como tales—. Convertirlas en
    `False` para que este test siguiera pasando habría sido ocultar exactamente lo que
    el catálogo existe para mostrar."""
    for lim in LIMITATION_REGISTRY:
        if lim.id in CONNECTED_LIMITATION_IDS or lim.id in DESPEGUE_BIAXIAL_IDS:
            continue
        assert lim.can_cause_false_pass is False, lim.id


def test_la_zapata_aislada_no_tiene_dispensas_pendientes():
    """El conjunto de dispensas está vacío, y se comprueba que lo esté.

    Una lista de excepciones que nadie poda deja de ser una lista. Cuando
    `punching_biaxial_uplift` se retiró (decisión 1, 2026-09-20), lo que quedó no fue una
    entrada obsoleta sino un conjunto vacío: la aislada no declara ninguna limitación con
    capacidad de producir un falso PASS."""
    assert DESPEGUE_BIAXIAL_IDS == set()


def test_toda_limitacion_que_puede_producir_falso_pass_esta_neutralizada():
    """EL INVARIANTE QUE DE VERDAD IMPORTA, y que sustituye al anterior como regla
    general: una limitación capaz de producir un falso PASS no puede quedarse en el
    catálogo como advertencia y nada más. Tiene que haber una verificación concreta
    que la haga visible en el resultado.

    `enforced_by` nombra esa verificación. Sin ella, el usuario leería «PASS» en un
    diseño que el propio programa sabe que no puede juzgar."""
    for lim in LIMITATION_REGISTRY:
        if not lim.can_cause_false_pass:
            continue
        assert lim.enforced_by, (
            f"«{lim.id}» puede producir un falso PASS y no declara qué verificación lo "
            f"impide. Una limitación así no puede quedar solo como nota."
        )


def test_min_depth_is_still_an_adopted_interpretation_not_a_certainty():
    lim = limitation_by_id("min_depth_interpretation")
    assert lim.kind is LimitationKind.INTERPRETATION_ADOPTED
    assert "NO una certeza normativa" in lim.description
    assert "Parametrizada" in lim.description


def test_unknown_limitation_id_raises():
    with pytest.raises(KeyError):
        limitation_by_id("no_existe")


# --- MÁQUINA DE ESTADOS -------------------------------------------------------------

def test_pass_is_reachable_when_nothing_relevant_is_pending():
    """L4 resuelta + L3 no aplicable + L1 no aplicable -> PASS alcanzable."""
    candidate = _evaluate(_loads())
    assert candidate.trace.failing_entries() == []
    assert candidate.overall_status is CheckStatus.PASS


def test_pass_is_not_automatic_missing_stability_params_block_it():
    """Aunque L3 esté implementada, si faltan μ y los FS el check queda
    NO VERIFICADO y el estado global NO puede ser PASS."""
    candidate = _evaluate(_loads(Hx_kN=80.0))
    assert candidate.stability.sliding.status is CheckStatus.NOT_VERIFIED
    assert candidate.stability.sliding.missing_parameters
    assert candidate.overall_status is CheckStatus.NOT_VERIFIED
    assert candidate.overall_status is not CheckStatus.PASS


def _por_casos(**kwargs) -> LoadCaseSet:
    """Modo por casos (Fase 10B): la composición permite demostrar la estabilidad."""
    from engine.domain.load_cases import CombinationDefinition, LoadCase, LoadCaseKind, derive_load_case_set

    casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=300.0, **kwargs),
             LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=100.0)]
    return derive_load_case_set(casos, [
        CombinationDefinition(name="S1", type=LoadCombinationType.SERVICIO, factors={"CM": 1.0, "CV": 1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA, factors={"CM": 1.4, "CV": 1.4}),
    ])


def test_supplying_the_missing_parameters_restores_pass():
    """Con μ declarado y la composición conocida (modo por casos), la estabilidad puede
    demostrarse y el resultado vuelve a PASS. Con combinaciones directas no: E.020 art.
    20.1 exige separar la carga muerta."""
    candidate = _evaluate(_por_casos(Hx_kN=40.0), soil=SOIL_WITH_STABILITY_PARAMS)
    assert candidate.stability.sliding.status is CheckStatus.PASS
    assert candidate.overall_status is CheckStatus.PASS
    directo = _evaluate(_loads(Hx_kN=40.0), soil=SOIL_WITH_STABILITY_PARAMS)
    assert directo.stability.sliding.status is CheckStatus.NOT_VERIFIED


def test_moments_alone_no_longer_downgrade_the_result():
    """Antes, cualquier momento producía WARNING por §11.12.6 no implementado.
    Ahora la verificación es real: si cumple, es PASS."""
    candidate = _evaluate(_por_casos(Mx_kNm=40.0), soil=SOIL_WITH_STABILITY_PARAMS)
    assert candidate.punching.moment_transfer is not None
    assert candidate.punching.status is CheckStatus.PASS
    assert candidate.overall_status is CheckStatus.PASS


def test_info_status_does_not_escalate_the_overall_status():
    """Una limitación puramente conservadora (reducción sísmica no aplicada) se
    emite como INFO y NO impide PASS."""
    soil = SOIL_WITH_STABILITY_PARAMS.model_copy(update={"allow_seismic_reduction_80pct": True})
    loads = LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=400.0, includes_seismic_loads=True
            )
        ],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=560.0)],
    )
    candidate = _evaluate(loads, soil=soil)
    entry = candidate.trace.by_id("limitation_seismic_reduction_80pct")
    assert entry is not None
    assert entry.status is CheckStatus.INFO
    assert candidate.overall_status is CheckStatus.PASS


def test_real_resistance_failure_still_gives_fail():
    candidate = _evaluate(_loads(), B=1.0, L=1.0)  # presión de contacto excedida
    assert candidate.overall_status is CheckStatus.FAIL
    assert candidate.trace.failing_entries()


# --- Severidad y agregación ----------------------------------------------------------

def test_severity_ordering():
    assert CheckStatus.PASS.severity == CheckStatus.INFO.severity == 0
    assert CheckStatus.INFO.severity < CheckStatus.WARNING.severity
    assert CheckStatus.WARNING.severity < CheckStatus.NOT_VERIFIED.severity
    assert CheckStatus.NOT_VERIFIED.severity < CheckStatus.FAIL.severity


def test_only_fail_discards():
    assert CheckStatus.FAIL.discards is True
    for status in (CheckStatus.PASS, CheckStatus.INFO, CheckStatus.WARNING, CheckStatus.NOT_VERIFIED):
        assert status.discards is False


def test_warning_and_not_verified_block_pass_but_info_does_not():
    assert CheckStatus.WARNING.blocks_pass is True
    assert CheckStatus.NOT_VERIFIED.blocks_pass is True
    assert CheckStatus.INFO.blocks_pass is False
    assert CheckStatus.PASS.blocks_pass is False


def test_worst_collapses_info_to_pass():
    assert CheckStatus.worst([CheckStatus.PASS, CheckStatus.INFO]) is CheckStatus.PASS
    assert CheckStatus.worst([CheckStatus.INFO, CheckStatus.INFO]) is CheckStatus.PASS


def test_worst_respects_severity():
    assert CheckStatus.worst([CheckStatus.PASS, CheckStatus.WARNING]) is CheckStatus.WARNING
    assert CheckStatus.worst([CheckStatus.WARNING, CheckStatus.NOT_VERIFIED]) is CheckStatus.NOT_VERIFIED
    assert CheckStatus.worst([CheckStatus.NOT_VERIFIED, CheckStatus.FAIL]) is CheckStatus.FAIL
    assert CheckStatus.worst([]) is CheckStatus.NOT_VERIFIED


def test_collect_is_deterministic():
    loads = _loads(Hx_kN=30.0)
    a = collect_applicable_limitations(loads, SOIL_150_BRUTA)
    b = collect_applicable_limitations(loads, SOIL_150_BRUTA)
    assert [x.limitation.id for x in a] == [x.limitation.id for x in b]
