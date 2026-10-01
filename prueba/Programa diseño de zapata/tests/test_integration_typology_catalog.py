"""Integración global — el catálogo de tipologías no puede desviarse del código.

El catálogo describe cómo se comporta cada tipología. Si describiera algo que el código
no hace, sería peor que no tenerlo: una vista común construida sobre él presentaría como
equivalentes resultados obtenidos con criterios distintos. Estos tests lo contrastan
contra el código real.
"""

from __future__ import annotations

import inspect
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.integration.typology_catalog import CATALOG, AcceptanceRule, accepts
from engine.results.status import CheckStatus

POR_ID = {t.id: t for t in CATALOG.typologies}


def test_las_tres_tipologias_estan_catalogadas():
    assert set(POR_ID) == {"aislada", "combinada", "conectada"}


def test_los_endpoints_del_catalogo_existen():
    rutas = {r.path for r in app.routes}
    for t in CATALOG.typologies:
        assert t.design_endpoint in rutas, t.design_endpoint
        assert t.report_endpoint in rutas, t.report_endpoint


def test_la_API_sirve_el_catalogo():
    r = TestClient(app).get("/api/typologies")
    assert r.status_code == 200
    d = r.json()
    assert {t["id"] for t in d["typologies"]} == set(POR_ID)
    assert {k["id"] for k in d["known_differences"]} >= {"ACEPTACION_COMBINADA", "VOCABULARIO_ACEPTADA"}


# --- Criterio de aceptación --------------------------------------------------


@pytest.mark.parametrize("estado, no_fail, pass_info", [
    (CheckStatus.PASS, True, True),
    (CheckStatus.INFO, True, True),
    (CheckStatus.WARNING, True, False),
    (CheckStatus.NOT_VERIFIED, True, False),
    (CheckStatus.FAIL, False, False),
])
def test_tabla_de_verdad_de_las_reglas(estado, no_fail, pass_info):
    assert accepts(AcceptanceRule.NO_FAIL, estado) is no_fail
    assert accepts(AcceptanceRule.PASS_OR_INFO, estado) is pass_info


def test_la_regla_de_la_aislada_es_la_del_codigo():
    import engine.foundation.depth_solver as m

    assert "if candidate.overall_status is not CheckStatus.FAIL:" in inspect.getsource(m.solve_depth)
    assert POR_ID["aislada"].acceptance_rule is AcceptanceRule.NO_FAIL


def test_la_regla_de_la_combinada_es_la_del_codigo():
    """ACTUALIZADO en la decisión 6: la combinada se alineó con NO_FAIL. El guardián sigue
    cumpliendo su función —el criterio del código y el del catálogo no pueden divergir—,
    ahora sobre la regla nueva. Detalle en tests/test_combined_acceptance_no_fail_d6.py."""
    import engine.optimization.combined_generator as m

    fuente = inspect.getsource(m.generate_combined_alternatives)
    assert "if not r.overall_status.discards:" in fuente
    assert POR_ID["combinada"].acceptance_rule is AcceptanceRule.NO_FAIL
    # La diferencia no se borra: queda registrada como resuelta (CLAUDE.md §16).
    dif = {k.id: k for k in CATALOG.known_differences}
    assert dif["ACEPTACION_COMBINADA"].resolution is not None
    assert dif["ACEPTACION_COMBINADA"].is_open is False


def test_la_regla_de_la_conectada_es_la_del_codigo():
    import engine.optimization.connected_generator as m

    # La decisión vive en `_evaluar_planta`, que es lo que ejecuta cada candidato —sea en
    # este proceso o en uno de los que reparten el barrido (2026-09-24)—.
    assert "if r.overall_status.discards:" in inspect.getsource(m._evaluar_planta)
    assert POR_ID["conectada"].acceptance_rule is AcceptanceRule.NO_FAIL


# --- Vocabulario y pendientes -------------------------------------------------


def test_el_vocabulario_de_la_aislada_es_el_del_informe():
    from engine.reports.report_model import StatusLabel

    assert POR_ID["aislada"].status_vocabulary == list(get_args(StatusLabel))


def test_el_vocabulario_de_la_conectada_es_el_cerrado():
    from engine.reports.connected_report import (
        ESTADO_ACEPTADA, ESTADO_CONFORME, ESTADO_NO_VERIFICADA, ESTADO_RECHAZADA,
    )

    assert set(POR_ID["conectada"].status_vocabulary) == {
        ESTADO_RECHAZADA, ESTADO_ACEPTADA, ESTADO_NO_VERIFICADA, ESTADO_CONFORME,
    }


def test_los_pendientes_de_la_conectada_son_los_que_describe_el_informe():
    from engine.reports.connected_report import TBD_DESCRIPTIONS

    assert set(POR_ID["conectada"].open_tbds) == set(TBD_DESCRIPTIONS)


# --- Capacidades contra los DTO reales ---------------------------------------


def test_las_capacidades_declaradas_existen_en_las_respuestas():
    aislada = POR_ID["aislada"].capabilities
    assert aislada["tabla_comparativa"] == ("table" in schemas.DesignResponse.model_fields)
    assert aislada["frente_pareto"] == ("in_pareto" in schemas.ComparisonRowOut.model_fields)

    combinada = POR_ID["combinada"].capabilities
    campos_comb = schemas.CombinedDesignResponse.model_fields
    assert combinada["tabla_comparativa"] == ("comparison" in campos_comb)
    assert combinada["frente_pareto"] == ("in_pareto" in schemas.CombinedComparisonRowOut.model_fields)
    assert combinada["esquema_2d"] == ("scene" in campos_comb), "Pendiente 1: la combinada ya tiene esquema"

    conectada = POR_ID["conectada"].capabilities
    campos_con = schemas.ConnectedDesignResponse.model_fields
    assert conectada["tabla_comparativa"] == ("comparison" in campos_con)
    assert conectada["frente_pareto"] == ("pareto_size" in campos_con)
    assert conectada["esquema_2d"] == ("scene" in campos_con)
