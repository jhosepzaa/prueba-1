"""Decisión 6 — la zapata combinada acepta con criterio NO_FAIL.

QUÉ CAMBIÓ Y POR QUÉ
====================
Hasta esta decisión el barrido de la combinada solo aceptaba PASS o INFO, mientras que la
aislada y la conectada aceptan todo lo que no sea FAIL. Era la diferencia conocida
`ACEPTACION_COMBINADA`. Desde D4, con fuerzas horizontales la estabilidad de la combinada
queda NO VERIFICADA —no está implementada— en TODOS los peraltes, de modo que el criterio
PASS/INFO descartaba la tipología entera en cuanto había sismo o viento.

QUÉ NO CAMBIÓ
=============
Ninguna ecuación, hipótesis, referencia normativa ni estado de verificación. El solver es
el mismo: lo que cambia es qué alternativas sobreviven al barrido. Estos tests lo fijan:

1. el criterio es NO_FAIL y es el mismo de las otras dos tipologías;
2. sin fuerzas horizontales el barrido devuelve EXACTAMENTE lo de antes;
3. con fuerzas horizontales devuelve las mismas geometrías, NO VERIFICADAS, nunca PASS;
4. el FAIL sigue descartando;
5. aceptada no es conforme: las particiones son exactas y la presentación lo dice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.integration.typology_catalog import CATALOG, AcceptanceRule, accepts
from engine.optimization.combined_generator import (
    CombinedSearchParameters,
    generate_combined_alternatives,
)
from engine.reports.combined_report import render_combined_report_html
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from tests.test_combined_footing_phase2 import CODE, TAPA, _specs

MAT = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))
ACEPTA = (CheckStatus.PASS, CheckStatus.INFO)
POR_ID = {t.id: t for t in CATALOG.typologies}

# Barrido A de la auditoría C-V, con los recuentos medidos ANTES de la decisión 6.
SUELO = SoilProfile(qadm_kPa=147.1, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50)
PARAMS = CombinedSearchParameters(
    length_min_m=6.0, length_max_m=7.6, length_step_m=0.40,
    width_min_m=3.0, width_max_m=4.4, width_step_m=0.40,
    h_min_m=0.40, h_max_m=0.90, h_step_m=0.10,
    first_column_edge_distance_m=0.25,
)
PREVIO = dict(evaluadas=118, descartadas=117, aceptadas=[(7.2, 4.2, 0.70)])


def _con_H(specs, Hx: float):
    """Las mismas columnas con fuerza horizontal. La combinada no la usa en ningún
    número (D4): solo dispara la entrada de estabilidad no implementada."""
    return [
        s.model_copy(update={"loads": s.loads.model_copy(update={
            "service": [c.model_copy(update={"Hx_kN": Hx}) for c in s.loads.service],
            "factored": [c.model_copy(update={"Hx_kN": 1.4 * Hx}) for c in s.loads.factored],
        })})
        for s in specs
    ]


def _barrer(specs):
    return generate_combined_alternatives(
        specs, PARAMS, soil=SUELO, code=CODE, contact_model=FullContactModel(),
        top_cover=TAPA, **MAT,
    )


@pytest.fixture(scope="module")
def sin_H():
    return _barrer(_specs())


@pytest.fixture(scope="module")
def con_H():
    return _barrer(_con_H(_specs(), 300.0))


# =========================================================================
# 1. El criterio es NO_FAIL, y es el de las tres tipologías
# =========================================================================


def test_el_catalogo_y_el_codigo_declaran_NO_FAIL():
    """Refleja el test de integración: el catálogo no puede desviarse del código."""
    import inspect

    import engine.optimization.combined_generator as m

    assert "if not r.overall_status.discards:" in inspect.getsource(m.generate_combined_alternatives)
    assert POR_ID["combinada"].acceptance_rule is AcceptanceRule.NO_FAIL


def test_las_tres_tipologias_comparten_hoy_la_misma_regla():
    assert {t.acceptance_rule for t in CATALOG.typologies} == {AcceptanceRule.NO_FAIL}
    for estado in (CheckStatus.PASS, CheckStatus.INFO, CheckStatus.WARNING, CheckStatus.NOT_VERIFIED):
        assert accepts(AcceptanceRule.NO_FAIL, estado) is True
    assert accepts(AcceptanceRule.NO_FAIL, CheckStatus.FAIL) is False


def test_la_diferencia_conocida_queda_resuelta_no_borrada():
    """CLAUDE.md §16: el historial de una decisión cerrada no se borra."""
    dif = {k.id: k for k in CATALOG.known_differences}
    assert "ACEPTACION_COMBINADA" in dif, "La diferencia no se elimina del catálogo"
    assert dif["ACEPTACION_COMBINADA"].resolution is not None
    assert dif["ACEPTACION_COMBINADA"].is_open is False
    assert "NO_FAIL" in dif["ACEPTACION_COMBINADA"].resolution
    # La ambigüedad del rótulo «aceptada» alcanzó también a la combinada, y el pendiente 8
    # la cerró con el vocabulario único: la diferencia queda resuelta, no borrada.
    assert "combinada" in dif["VOCABULARIO_ACEPTADA"].typologies
    assert dif["VOCABULARIO_ACEPTADA"].resolution is not None


# =========================================================================
# 2. Sin fuerzas horizontales el barrido devuelve exactamente lo de antes
# =========================================================================


def test_sin_fuerzas_horizontales_los_recuentos_son_los_previos(sin_H):
    assert sin_H.evaluated_count == PREVIO["evaluadas"]
    assert sin_H.discarded_count == PREVIO["descartadas"]
    assert [(a.length_m, a.width_m, a.h_m) for a in sin_H.valid] == PREVIO["aceptadas"]
    assert sin_H.discard_summary.discarded_by_status == {"FAIL": PREVIO["descartadas"]}


def test_sin_fuerzas_horizontales_todo_lo_aceptado_es_conforme(sin_H):
    assert sin_H.accepted_and_compliant == sin_H.valid
    assert sin_H.not_verified == [] and sin_H.accepted_with_findings == []
    assert sin_H.status_summary() == {"PASS": 1}
    assert sin_H.search_note == "", "Sin nada que advertir, no se inventa una advertencia"


# =========================================================================
# 3. Con fuerzas horizontales: mismas geometrías, NO VERIFICADAS, nunca PASS
# =========================================================================


def test_con_fuerzas_horizontales_el_barrido_ya_no_queda_vacio(con_H):
    """Antes de la decisión 6 esto devolvía cero alternativas: el NO VERIFICADO de la
    estabilidad (D4) descartaba todas las geometrías, en todos los peraltes."""
    assert con_H.valid, "La tipología entera quedaba inutilizada con sismo o viento"
    assert len(con_H.not_verified) == len(con_H.valid)
    assert con_H.accepted_and_compliant == []
    assert con_H.status_summary() == {"NO VERIFICADO": len(con_H.valid)}


def test_la_fuerza_horizontal_no_mueve_el_peralte_elegido(sin_H, con_H):
    """Guarda contra la regresión que haría peligroso NO_FAIL: que una alternativa NO
    VERIFICADA con menos peralte desplace a una PASS más profunda. Hoy no puede ocurrir
    —la entrada de estabilidad no depende de h—, y este test lo fija."""
    assert [(a.length_m, a.width_m, a.h_m) for a in con_H.valid] == \
           [(a.length_m, a.width_m, a.h_m) for a in sin_H.valid]


def test_ninguna_aceptada_con_horizontal_alcanza_PASS(con_H):
    """ACTUALIZADO en el pendiente 7: la causa ya no es «no implementada» sino la falta de
    μ, que es dato del proyectista. El resultado observable es el mismo."""
    for a in con_H.valid:
        assert a.result.overall_status is CheckStatus.NOT_VERIFIED
        e = a.result.trace.by_id("sliding")
        assert e is not None and e.status is CheckStatus.NOT_VERIFIED


def test_la_nota_de_busqueda_dice_que_aceptada_no_es_conforme(sin_H, con_H):
    assert "NO VERIFICADA" in con_H.search_note
    assert "NO que cumpla" in con_H.search_note
    assert "estabilidad" in con_H.search_note
    assert "cumple" not in sin_H.search_note


# =========================================================================
# 4. El FAIL sigue descartando
# =========================================================================


def test_ninguna_aceptada_esta_en_FAIL(sin_H, con_H):
    for conjunto in (sin_H, con_H):
        for a in conjunto.valid:
            assert a.result.overall_status is not CheckStatus.FAIL
            assert not a.result.overall_status.discards


def test_donde_todo_falla_el_barrido_sigue_vacio():
    """Suelo insuficiente: todas las geometrías dan FAIL y NO_FAIL no rescata ninguna."""
    g = generate_combined_alternatives(
        _con_H(_specs(), 300.0),
        PARAMS.model_copy(update={"h_min_m": 0.15, "h_max_m": 0.90, "h_step_m": 0.10}),
        soil=SoilProfile(qadm_kPa=60.0, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )
    assert g.valid == []
    assert g.discarded_count == g.evaluated_count
    assert set(g.discard_summary.discarded_by_status) == {"FAIL"}


# =========================================================================
# 5. Aceptada no es conforme: particiones exactas y presentación honesta
# =========================================================================


def test_las_particiones_son_exactas_y_disjuntas(sin_H, con_H):
    for conjunto in (sin_H, con_H):
        ids = lambda xs: [a.id for a in xs]  # noqa: E731
        partes = ids(conjunto.not_verified) + ids(conjunto.accepted_with_findings) \
            + ids(conjunto.accepted_and_compliant)
        assert sorted(partes) == sorted(ids(conjunto.valid))
        assert len(partes) == len(set(partes)), "Una alternativa no puede estar en dos partes"
        assert conjunto.accepted == conjunto.valid
        assert sum(conjunto.status_summary().values()) == len(conjunto.valid)


def test_lo_conforme_excluye_lo_no_verificado(con_H):
    for a in con_H.accepted_and_compliant:
        assert a.result.overall_status in ACEPTA


def test_la_memoria_avisa_cuando_la_alternativa_no_es_conforme(sin_H, con_H):
    html = render_combined_report_html(con_H.valid[0].result, "prueba")
    assert "NO puede declararse conforme" in html
    assert "sliding" in html
    assert "NO VERIFICADO" in html
    # Y no aparece el aviso cuando la alternativa sí es conforme.
    assert "NO puede declararse conforme" not in render_combined_report_html(
        sin_H.valid[0].result, "prueba"
    )


# =========================================================================
# 6. La API transporta el desglose
# =========================================================================


def _payload(Hx: float) -> dict:
    from tests.test_api_combined_phase2 import _request

    p = _request()
    for col in p["columns"]:
        for combo in col["combinations"]:
            combo["Hx_kN"] = Hx if combo["type"] == "SERVICIO" else 1.4 * Hx
    return p


@pytest.mark.parametrize("Hx, conforme", [(0.0, True), (300.0, False)])
def test_la_API_separa_aceptada_de_conforme(Hx, conforme):
    r = TestClient(app).post("/api/design-combined", json=_payload(Hx))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["accepted_count"] >= 1
    assert d["accepted_count"] == len(d["comparison"])
    assert d["can_claim_compliance"] is conforme
    esperado = "PASS" if conforme else "NO VERIFICADO"
    assert set(d["status_summary"]) == {esperado}
    assert all(a["status"] == esperado for a in d["top"])
    assert all(fila["status"] == esperado for fila in d["comparison"])
    if conforme:
        assert d["not_verified"] == [] and d["accepted_and_compliant_count"] == d["accepted_count"]
    else:
        assert d["accepted_and_compliant"] == []
        assert d["not_verified_count"] == d["accepted_count"]
        assert "NO que cumpla" in d["search_note"]


def test_el_catalogo_servido_declara_la_capacidad_real_de_descartes():
    """Defecto encontrado de paso: la capacidad seguía en False desde antes de la Fase 2."""
    d = TestClient(app).get("/api/typologies").json()
    combinada = next(t for t in d["typologies"] if t["id"] == "combinada")
    assert combinada["acceptance_rule"] == "NO_FAIL"
    assert combinada["capabilities"]["explicacion_descartes"] is True
    assert combinada["capabilities"]["vista_3d"] is True, "Pendiente 3: ya tiene vista 3D"
