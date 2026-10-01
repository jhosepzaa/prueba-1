"""CASO 07 -- Sección groseramente insuficiente: robustez del solver de flexión.

HALLAZGO DE INGENIERÍA (documentado tras intentar construir este caso):
una falla por flexión AISLADA es físicamente inalcanzable en una zapata aislada.
El techo de resistencia a flexión de una sección simplemente reforzada es

    Mn_max ~ 0.425 * f'c * b * d^2

que crece con d^2, mientras que las capacidades de cortante (0.17*sqrt(f'c)*b*d) y
de punzonamiento crecen solo con d. Para agotar el techo de flexión de una zapata
de 3.00x3.00 m con d=0.72 m haría falta Pu del orden de 68 000 kN (~6900 t sobre
una sola columna); mucho antes fallarían la capacidad portante, el punzonamiento y
el cortante unidireccional. Conclusión práctica: en zapatas, la flexión determina
la CANTIDAD DE ACERO, pero nunca es el límite que gobierna el peralte.

Por eso este caso NO pretende aislar la flexión. Lo que verifica -- y es
importante -- es la ROBUSTEZ del motor ante una sección absurda: que el solver de
flexión devuelva FAIL con una nota explícita en vez de propagar NaN en silencio o
lanzar una excepción, y que el selector de acero degrade limpiamente al recibir
ese NaN.

Datos: B=L=3.00 m, columna 0.40x0.40 (voladizo 1.30 m), h=0.20 m -> d=0.122 m,
       Pu=3000 kN. Es una zapata deliberadamente imposible.

RESULTADO ESPERADO: FAIL en prácticamente todas las verificaciones (incluida
§15.7, porque d=0.122 m < 0.300 m), con As_required = NaN señalizado como FAIL
explícito y sin excepciones no controladas.
"""

import math

from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
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

LOADS = LoadCaseSet(
    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=2200.0)],
    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=3000.0)],
)


def _candidate():
    return evaluate_candidate(
        B_m=3.0, L_m=3.0, h_m=0.20,
        column=COLUMN_40x40, soil=SOIL_150_BRUTA, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=LOADS, code=CODE, contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )


def test_case_07_flexure_solver_fails_explicitly_instead_of_returning_garbage():
    c = _candidate()
    assert c.flexure_x.status == CheckStatus.FAIL
    assert math.isnan(c.flexure_x.As_required_m2)
    assert "insuficiente" in c.flexure_x.note.lower()


def test_case_07_rebar_selector_degrades_cleanly_on_nan():
    c = _candidate()
    # El NaN no debe propagarse en silencio hasta el resultado final.
    assert c.rebar_x.status == CheckStatus.FAIL
    assert c.rebar_x.bar_designation == "N/A"
    assert c.rebar_x.n_bars == 0


def test_case_07_reports_every_failing_check_not_just_the_first():
    c = _candidate()
    assert c.overall_status == CheckStatus.FAIL
    reasons = " | ".join(c.discard_reasons)
    # El motor debe acumular TODAS las razones, no cortocircuitar en la primera:
    # esa es la base de la explicación de descartes (sección 12 del encargo).
    for expected in ("qmax > qadm", "peralte mínimo", "Flexión X", "Cortante unidireccional X", "Punzonamiento"):
        assert expected in reasons, f'Falta la razón "{expected}" en: {reasons}'


def test_case_07_does_not_raise():
    # Una zapata absurda debe producir un resultado FAIL bien formado, no una
    # excepción: el generador de alternativas recorre miles de geometrías y no
    # puede abortar por una entrada degenerada.
    c = _candidate()
    assert c.overall_status is CheckStatus.FAIL
    assert len(c.trace.entries) > 0
