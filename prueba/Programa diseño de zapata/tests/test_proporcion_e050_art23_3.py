"""Proporción en planta — E.050 art. 23.3, común a las tres tipologías (H6, 2026-09-20).

EL HALLAZGO
===========
`docs/auditoria_paridad_tipologias.md` §H6: el artículo dice «Las zapatas y plateas
deberán tener una forma regular», sin distinguir tipología, y su tabla de formas asigna
`L ≤ 10·B` a la rectangular y a la combinada. Solo la COMBINADA lo verificaba. En la
aislada, `max_LB_ratio` es un **parámetro de búsqueda** con valor por defecto 2,0: quien
pidiera 15 recibía un cimiento corrido presentado como zapata aislada, sin que nada lo
dijera.

EL NÚMERO ES EL DEL ARTÍCULO
============================
La tabla del 23.3 dice **10**:

    Cuadrada     L = B
    Rectangular  L <= 10 B
    Continua     L > 10 B
    Combinada    L <= 10 B

El «cinco (5)» que aparece unas líneas antes es del art. **23.1** y es otra relación
—`Df/B`, profundidad sobre ancho, la que define una cimentación superficial—, que no dice
nada sobre la forma en planta. Adoptar 5 aquí sería un criterio del programa más estricto
que la norma, no una lectura del 23.3, y como tal tendría que declararse igual que los FS
de D10-2b. Hoy el motor usa el 10 del artículo.

LA LECTURA
==========
La tabla **no prohíbe, clasifica**. Por encima de `L = 10·B` el elemento deja de ser una
zapata y pasa a ser una cimentación continua, que es otra tipología con sus propios
requisitos y que este motor no modela. Por eso es FAIL: no por incumplir un número, sino
porque el resultado no sería el de una zapata. Es un límite de ALCANCE, y así se declara
en la hipótesis de la entrada.
"""

import pytest

from engine.codes.peru.e050_soils import (
    MAX_L_OVER_B,
    SHAPE_RATIO_EXCEEDED_NOTE,
    SHAPE_RATIO_READING,
    check_shape_ratio,
)
from engine.results.status import CheckStatus


# =========================================================================
# 1. La regla, reconstruida a mano
# =========================================================================


def test_el_limite_es_el_del_articulo():
    """«Rectangular L ≤ 10 B» y «Combinada L ≤ 10 B» (tabla del art. 23.3)."""
    assert MAX_L_OVER_B == 10.0


@pytest.mark.parametrize(
    "B,L,ratio,ok",
    [
        (2.00, 2.00, 1.00, True),      # cuadrada
        (3.00, 2.40, 1.25, True),
        (2.40, 3.00, 1.25, True),      # da igual cuál sea el lado mayor
        (12.00, 3.20, 3.75, True),     # la combinada más alargada del congelamiento
        (10.00, 1.00, 10.00, True),    # el límite EXACTO cumple: el artículo dice «<=»
        (10.01, 1.00, 10.01, False),
        (30.00, 1.50, 20.00, False),   # esto es un cimiento corrido
    ],
)
def test_la_proporcion_es_lado_mayor_sobre_lado_menor(B, L, ratio, ok):
    r = check_shape_ratio(B, L)
    assert r.ratio == pytest.approx(ratio)
    assert r.ok is ok
    assert r.long_side_m == max(B, L)
    assert r.short_side_m == min(B, L)


def test_la_referencia_cita_el_articulo_correcto():
    r = check_shape_ratio(3.00, 2.40)
    assert "23.3" in r.code_reference
    # Y NO el 23.1, que es Df/B y no tiene nada que ver con la forma en planta.
    assert "23.1" not in r.code_reference


def test_la_lectura_declara_que_es_un_limite_de_alcance():
    """No se presenta como exigencia numérica de la norma (CLAUDE.md §8)."""
    assert "CLASIFICA" in SHAPE_RATIO_READING
    assert "alcance" in SHAPE_RATIO_READING
    assert "continua" in SHAPE_RATIO_READING


# =========================================================================
# 2. Las tres tipologías la emiten
# =========================================================================


def test_la_aislada_emite_la_entrada_y_la_pasa():
    from tests.freeze.cases import CASES
    from tests.freeze.test_freeze_isolated import _evaluate

    caso = next(c for c in CASES if c.name == "09_rectangular_reparto_direccion_corta")
    entrada = _evaluate(caso).trace.by_id("shape_ratio")
    assert entrada is not None
    assert entrada.status is CheckStatus.PASS
    assert entrada.result_value == pytest.approx(max(caso.B_m, caso.L_m) / min(caso.B_m, caso.L_m))
    assert SHAPE_RATIO_READING in entrada.hypotheses


def test_la_combinada_sigue_emitiendola_con_la_misma_regla():
    from tests.freeze.cases import COMBINED_CASES
    from tests.freeze.test_freeze_isolated import _solve_combined

    caso = next(c for c in COMBINED_CASES if c.name == "K3_tres_columnas_desiguales")
    r = _solve_combined(caso)
    entrada = r.trace.by_id("shape_ratio")
    assert entrada is not None
    assert entrada.result_value == pytest.approx(check_shape_ratio(r.B_m, r.L_m).ratio)
    assert entrada.status is CheckStatus.PASS


def test_las_zapatas_de_la_conectada_tambien():
    """No hace falta código nuevo: sus zapatas pasan por `evaluate_candidate`. Lo que hay
    que comprobar es que efectivamente llegue, no suponerlo."""
    from tests.freeze.cases import CONNECTED_CASES
    from tests.freeze.test_freeze_connected import _solve

    caso = next(c for c in CONNECTED_CASES if not c.expects_rejection)
    r = _solve(caso)
    ids = {e.id for e in r.trace.entries}
    assert any(i.endswith("shape_ratio") or i == "shape_ratio" for i in ids), sorted(ids)


# =========================================================================
# 3. Pasarse descarta, en la aislada igual que en la combinada
# =========================================================================


def test_pasarse_del_limite_descarta_la_alternativa_aislada():
    """El caso que motivó H6: `max_LB_ratio` es de búsqueda y no protege de nada."""
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
    comun = dict(
        h_m=0.60, column=col,
        soil=SoilProfile(qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.20),
        concrete=MaterialConcrete(fc_MPa=21.0, unit_weight_kNm3=24.0),
        steel=MaterialSteel(fy_MPa=420.0, bar_type="corrugada"),
        load_case_set=cargas, code=E060ConcreteCode(), contact_model=KernCheckModel(),
        placement=ColumnPlacement(column=col),
        depth_params=DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05),
    )

    # 12,00 x 1,00 m: relación 12 > 10. Es un cimiento corrido, no una zapata.
    corrido = evaluate_candidate(B_m=12.00, L_m=1.00, **comun)
    entrada = corrido.trace.by_id("shape_ratio")
    assert entrada.status is CheckStatus.FAIL
    assert SHAPE_RATIO_EXCEEDED_NOTE in entrada.hypotheses
    assert any("23.3" in m for m in corrido.discard_reasons), corrido.discard_reasons
    assert corrido.overall_status is CheckStatus.FAIL

    # La misma área con una proporción admisible no se descarta por este motivo.
    zapata = evaluate_candidate(B_m=4.00, L_m=3.00, **comun)
    assert zapata.trace.by_id("shape_ratio").status is CheckStatus.PASS
    assert not any("23.3" in m for m in zapata.discard_reasons)


def test_el_motivo_de_descarte_nombra_la_tipologia_que_seria():
    """Diagnóstico honesto: no «incumple 23.3» sino «eso es una cimentación continua»."""
    from engine.codes.peru.e050_soils import check_shape_ratio as chk

    r = chk(30.0, 1.5)
    assert r.ok is False
    assert r.equation_substituted.startswith("30.000 / 1.500")
    assert ">" in r.equation_substituted
