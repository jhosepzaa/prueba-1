"""Cimentación superficial — E.050 art. 23.1, común a las tres tipologías (H7, 2026-09-20).

EL HALLAZGO
===========
`docs/auditoria_paridad_tipologias.md` §H7: **nadie** comprobaba que la cimentación siguiera
siendo superficial. Todo el capítulo bajo el que trabaja este motor —presiones admisibles,
profundidad mínima, tipologías— está escrito para cimentaciones superficiales, y el art.
23.2 las enumera: zapatas aisladas, conectadas y combinadas, cimientos corridos y plateas.
Son exactamente las que el motor resuelve. Si la relación se pasa, el elemento deja de ser
una de ellas y todo lo demás deja de aplicar.

EL TEXTO
========
    «23.1. Son aquellas en las cuales la relación Profundidad / ancho (Dƒ/ B) es menor o
    igual a cinco (5), siendo Dƒ la profundidad de la cimentación y B el ancho o diámetro
    de la misma.»

Es una **definición**, no un requisito de resistencia. Y el «cinco (5)» es de ESTE artículo:
no confundirlo con el `L ≤ 10 B` del 23.3, que es la forma en planta (H6). Van seguidos en
la norma y es fácil mezclarlos.

QUÉ ES «B»
==========
El lado MENOR. El artículo dice «el ancho o diámetro de la misma»; tomar el lado mayor daría
una relación más pequeña y dejaría pasar geometrías que el artículo excluye. Es además la
dimensión que gobierna los mecanismos por los que la distinción existe —el bulbo de
presiones y el confinamiento—.

POR QUÉ FAIL Y NO NO VERIFICADO
===============================
Decisión del proyectista (2026-09-20). El programa diseña cimentaciones superficiales, y
admitir una entrada físicamente fuera del alcance del modelo —aunque se rotule NO
VERIFICADO— deja abierta la puerta a que alguien la use. Se declara como **condición de
aplicabilidad**: no es que la norma lo prohíba, es que el modelo deja de describir el
problema. Misma lectura de alcance que el 23.3 en H6.
"""

import pytest

from engine.codes.peru.e050_soils import (
    MAX_DF_OVER_B,
    SHALLOW_FOUNDATION_EXCEEDED_NOTE,
    SHALLOW_FOUNDATION_READING,
    check_shallow_foundation,
)
from engine.results.status import CheckStatus


# =========================================================================
# 1. La regla, reconstruida a mano
# =========================================================================


def test_el_limite_es_el_del_articulo():
    """«menor o igual a cinco (5)» (art. 23.1)."""
    assert MAX_DF_OVER_B == 5.0


@pytest.mark.parametrize(
    "Df,B,L,ratio,ok",
    [
        (1.20, 3.00, 2.40, 0.50, True),     # Df/B = 1,20/2,40
        (1.20, 2.40, 3.00, 0.50, True),     # da igual cuál sea el lado menor
        (5.00, 1.00, 4.00, 5.00, True),     # el límite EXACTO cumple: «menor o igual»
        (5.01, 1.00, 4.00, 5.01, False),
        (12.00, 1.50, 8.00, 8.00, False),   # esto es una cimentación profunda
    ],
)
def test_la_relacion_usa_el_lado_MENOR(Df, B, L, ratio, ok):
    r = check_shallow_foundation(Df, B, L)
    assert r.ratio == pytest.approx(ratio)
    assert r.ok is ok
    assert r.width_m == min(B, L)


def test_tomar_el_lado_mayor_seria_mas_permisivo():
    """La razón de elegir el menor, con números: una zapata alargada pasaría el filtro.

    Df = 6,00 m sobre 1,00 × 8,00 m. Con el lado menor la relación es 6,00 y no cumple;
    con el mayor sería 0,75 y pasaría sin que nadie lo mirara."""
    r = check_shallow_foundation(6.00, 1.00, 8.00)
    assert r.ratio == pytest.approx(6.00)
    assert r.ok is False
    assert 6.00 / 8.00 < MAX_DF_OVER_B  # lo que habría salido con el lado mayor


def test_la_referencia_cita_el_articulo_correcto():
    r = check_shallow_foundation(1.20, 3.00, 2.40)
    assert "23.1" in r.code_reference
    # Y NO el 23.3, que es la forma en planta y lleva el 10.
    assert "23.3" not in r.code_reference


def test_la_lectura_declara_que_es_una_condicion_de_aplicabilidad():
    """No se presenta como exigencia numérica de la norma (CLAUDE.md §8): el artículo
    DEFINE, no prohíbe."""
    assert "CONDICIÓN DE APLICABILIDAD" in SHALLOW_FOUNDATION_READING
    assert "DEFINE" in SHALLOW_FOUNDATION_READING
    assert "PROFUNDA" in SHALLOW_FOUNDATION_READING
    assert "no es que la norma lo prohíba" in SHALLOW_FOUNDATION_READING.lower()


# =========================================================================
# 2. Las tres tipologías la emiten
# =========================================================================


def test_la_aislada_emite_la_entrada_y_la_pasa():
    from tests.freeze.cases import CASES
    from tests.freeze.test_freeze_isolated import _evaluate

    caso = next(c for c in CASES if c.name == "09_rectangular_reparto_direccion_corta")
    entrada = _evaluate(caso).trace.by_id("shallow_foundation")
    assert entrada is not None
    assert entrada.status is CheckStatus.PASS
    esperado = caso.soil.Df_m / min(caso.B_m, caso.L_m)
    assert entrada.result_value == pytest.approx(esperado)
    assert SHALLOW_FOUNDATION_READING in entrada.hypotheses


def test_la_combinada_tambien():
    from tests.freeze.cases import COMBINED_CASES
    from tests.freeze.test_freeze_isolated import _solve_combined

    caso = COMBINED_CASES[0]
    r = _solve_combined(caso)
    entrada = r.trace.by_id("shallow_foundation")
    assert entrada is not None
    assert entrada.result_value == pytest.approx(
        check_shallow_foundation(caso.soil.Df_m, r.B_m, r.L_m).ratio
    )


def test_las_zapatas_de_la_conectada_tambien():
    from tests.freeze.cases import CONNECTED_CASES
    from tests.freeze.test_freeze_connected import _solve

    caso = next(c for c in CONNECTED_CASES if not c.expects_rejection)
    ids = {e.id for e in _solve(caso).trace.entries}
    assert "shallow_foundation" in ids


def test_ningun_caso_congelado_falla_por_este_motivo():
    """La entrada es aditiva: se añadió a 36 casos y ninguno cambió de estado."""
    from tests.freeze.cases import CASES
    from tests.freeze.test_freeze_isolated import _evaluate

    for caso in CASES:
        entrada = _evaluate(caso).trace.by_id("shallow_foundation")
        assert entrada.status is CheckStatus.PASS, caso.name


# =========================================================================
# 3. Pasarse descarta
# =========================================================================


def test_pasarse_del_limite_descarta_la_alternativa_aislada():
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.column import Column
    from engine.domain.column_placement import ColumnPlacement
    from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
    from engine.domain.materials import MaterialConcrete, MaterialSteel
    from engine.domain.search_parameters import DepthSearchParameters
    from engine.domain.soil import PressureBasis, SoilProfile
    from engine.foundation.depth_solver import evaluate_candidate
    from engine.soil.contact_pressure import KernCheckModel

    col = Column(shape="cuadrada", bx_m=0.40, by_m=0.40)
    cargas = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=500.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=700.0)],
    )

    def _evaluar(Df: float):
        return evaluate_candidate(
            B_m=2.00, L_m=2.00, h_m=0.60, column=col,
            soil=SoilProfile(qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA,
                             gamma_kNm3=18.0, Df_m=Df),
            concrete=MaterialConcrete(fc_MPa=21.0, unit_weight_kNm3=24.0),
            steel=MaterialSteel(fy_MPa=420.0, bar_type="corrugada"),
            load_case_set=cargas, code=E060ConcreteCode(), contact_model=KernCheckModel(),
            placement=ColumnPlacement(column=col),
            depth_params=DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05),
        )

    # Df = 12,00 m sobre B = 2,00 m: relación 6 > 5. Es una cimentación profunda.
    profunda = _evaluar(12.00)
    entrada = profunda.trace.by_id("shallow_foundation")
    assert entrada.status is CheckStatus.FAIL
    assert SHALLOW_FOUNDATION_EXCEEDED_NOTE in entrada.hypotheses
    assert any("23.1" in m for m in profunda.discard_reasons), profunda.discard_reasons
    assert profunda.overall_status is CheckStatus.FAIL

    # La misma zapata a profundidad razonable no se descarta por este motivo.
    superficial = _evaluar(1.50)
    assert superficial.trace.by_id("shallow_foundation").status is CheckStatus.PASS
    assert not any("23.1" in m for m in superficial.discard_reasons)


def test_el_motivo_de_descarte_dice_que_seria_una_cimentacion_profunda():
    """Diagnóstico honesto: no «incumple 23.1» sino «eso es una cimentación profunda»."""
    r = check_shallow_foundation(12.00, 2.00, 2.00)
    assert r.ok is False
    assert r.equation_substituted.startswith("Df/B = 12.000 / 2.000")
    assert ">" in r.equation_substituted
