"""FASE 4G — paridad de presentación de la cimentación conectada.

Tres piezas, ninguna con física propia:

1. Frente de Pareto: el MISMO núcleo de dominancia para las tres tipologías.
2. `ConnectedSceneDTO`: posiciones del esquema resueltas por el motor desde las huellas
   que usó el cálculo; la UI no recalcula nada.
3. API: tabla comparativa con todas las aceptadas, marca de Pareto y escena, como campos
   ADITIVOS (el contrato de 4E no cambia).

Y una regla de 4E que 4G no puede romper: estar en el frente o dibujarse no convierte
nada en CONFORME.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.optimization.pareto import (
    DEFAULT_OBJECTIVES,
    METRIC_OBJECTIVES,
    PARETO_OBJECTIVES,
    pareto_mask,
)
from engine.reports.connected_report import ESTADO_CONFORME
from engine.visualization.connected_scene import build_connected_scene
import tests.test_connected_search_phase4d as busqueda
from tests.test_connected_presentation_phase4e import _combos, _peticion

UI = Path(__file__).resolve().parent.parent / "ui" / "src"


def _domina(a, b, objetivos):
    va = [METRIC_OBJECTIVES[o](a) for o in objetivos]
    vb = [METRIC_OBJECTIVES[o](b) for o in objetivos]
    return all(x <= y + 1e-12 for x, y in zip(va, vb)) and any(x < y - 1e-12 for x, y in zip(va, vb))


# =========================================================================
# 1. Pareto
# =========================================================================


@pytest.fixture(scope="module")
def conectadas():
    return busqueda._buscar(soil=busqueda.SUELO_CON_FS)


def test_el_frente_de_la_conectada_cumple_la_definicion_de_dominancia(conectadas):
    """Comprobación independiente de la definición, no del código: ningún miembro del
    frente está dominado y todo excluido lo domina alguien."""
    metricas = [a.metrics for a in conectadas.accepted]
    mascara = pareto_mask(metricas)
    assert any(mascara)
    for i, (m, dentro) in enumerate(zip(metricas, mascara)):
        dominado = any(_domina(o, m, DEFAULT_OBJECTIVES) for j, o in enumerate(metricas) if j != i)
        assert dentro is (not dominado)


def test_los_objetivos_publicos_no_cambian():
    assert set(PARETO_OBJECTIVES) == set(METRIC_OBJECTIVES)
    assert DEFAULT_OBJECTIVES == ("volumen_concreto", "masa_acero", "dimension_maxima")


def test_pareto_rechaza_objetivos_desconocidos():
    with pytest.raises(ValueError, match="no reconocido"):
        pareto_mask([], ("inventado",))


# =========================================================================
# 2. Escena del sistema
# =========================================================================


def _escena(layout, alt):
    return build_connected_scene(layout, alt)


def test_la_escena_usa_las_huellas_del_calculo(conectadas):
    lay = busqueda._layout()
    alt = conectadas.accepted[0]
    sc = _escena(lay, alt)
    g = alt.geometry
    fp = lay.footprints(g.exterior_B_m, g.exterior_L_m, g.exterior_h_m,
                        g.interior_B_m, g.interior_L_m, g.interior_h_m)

    def extremos(box):
        return (box.center.x - box.size.x / 2, box.center.x + box.size.x / 2)

    assert extremos(sc.exterior_footing) == pytest.approx((fp.exterior.start_m, fp.exterior.end_m))
    assert extremos(sc.interior_footing) == pytest.approx((fp.interior.start_m, fp.interior.end_m))
    assert extremos(sc.beam) == pytest.approx((fp.exterior.end_m, fp.interior.start_m))
    assert sc.exterior_footing.size.y == pytest.approx(fp.exterior.width_m)
    assert sc.interior_footing.size.z == pytest.approx(fp.interior.h_m)
    assert sc.beam.size.y == pytest.approx(lay.beam.b_m)
    assert sc.property_line_x_m == 0.0 and extremos(sc.exterior_footing)[0] == 0.0


def test_la_escena_coincide_con_las_magnitudes_del_resultado(conectadas):
    lay = busqueda._layout()
    alt = conectadas.accepted[0]
    sc = _escena(lay, alt)
    d = alt.result.statics[0]
    assert sc.exterior_column_axis_x_m == pytest.approx(d.a_m)
    assert sc.interior_column_axis_x_m == pytest.approx(d.s_cut_m)
    assert sc.system_length_m == pytest.approx(alt.result.system_length_m)
    assert sc.exterior_column.center.x == pytest.approx(d.a_m)


def test_la_escena_no_presenta_nada_como_conforme(conectadas):
    lay = busqueda._layout()
    sc = _escena(lay, conectadas.accepted[0])
    assert sc.status_label != ESTADO_CONFORME
    assert sc.open_tbds == ["TBD-C1"]
    assert "armado" in sc.scope_note and "convención de dibujo" in sc.scope_note


def test_la_escena_con_viga_sobre_Y_usa_la_dimension_longitudinal():
    """Con la viga sobre Y, la longitud de cada zapata a lo largo de la viga es su L."""
    lay_y = busqueda._layout().model_copy(update={
        "longitudinal_axis": "Y",
        "exterior": busqueda._layout().exterior.model_copy(
            update={"anchor": busqueda.EdgeAnchor(edge="Y_MIN")}),
    })
    r = busqueda._buscar(lay_y, soil=busqueda.SUELO_CON_FS)
    alt = r.accepted[0]
    sc = _escena(lay_y, alt)
    g = alt.geometry
    assert sc.longitudinal_axis == "Y"
    assert sc.exterior_footing.size.x == pytest.approx(g.exterior_L_m)
    assert sc.exterior_footing.size.y == pytest.approx(g.exterior_B_m)
    assert sc.system_length_m == pytest.approx(alt.result.system_length_m)


# =========================================================================
# 3. API
# =========================================================================


@pytest.fixture(scope="module")
def respuesta():
    r = TestClient(app).post("/api/design-connected", json=_peticion())
    assert r.status_code == 200, r.text
    return r.json()


def test_la_comparacion_contiene_todas_las_aceptadas_en_orden_de_costo(respuesta):
    comp = respuesta["comparison"]
    assert len(comp) == respuesta["accepted_count"]
    puntuaciones = [a["score"] for a in comp]
    assert puntuaciones == sorted(puntuaciones)
    assert [a["id"] for a in respuesta["accepted"]] == [a["id"] for a in comp[: len(respuesta["accepted"])]]


def test_la_marca_de_pareto_es_coherente(respuesta):
    comp = respuesta["comparison"]
    assert respuesta["pareto_objectives"] == list(DEFAULT_OBJECTIVES)
    assert respuesta["pareto_size"] == sum(a["in_pareto"] for a in comp) >= 1
    for a in comp:
        if a["in_pareto"]:
            assert a["status_label"] != ESTADO_CONFORME
            assert a["overall_status"] == "NO VERIFICADO"


def test_la_escena_de_la_api_es_la_de_la_mejor_alternativa(respuesta):
    sc = respuesta["scene"]
    assert sc is not None
    assert sc["alternative_id"] == respuesta["comparison"][0]["id"]
    assert sc["open_tbds"] == ["TBD-C1"]
    assert sc["free_span_end_x_m"] > sc["free_span_start_x_m"]


def test_sin_aceptadas_no_hay_escena_ni_comparacion():
    r = TestClient(app).post("/api/design-connected", json=_peticion(
        analysis_model="CUERPO_RIGIDO",
        exterior={"label": "Z1", "bx_m": 0.50, "by_m": 0.50, "combinations": _combos(850.0, 9000.0)},
    ))
    d = r.json()
    assert r.status_code == 200
    assert d["comparison"] == [] and d["scene"] is None and d["pareto_size"] == 0


def test_los_campos_de_4E_siguen_intactos(respuesta):
    for campo in ("overall_status", "headline", "can_claim_compliance", "open_tbds",
                  "accepted", "not_verified", "accepted_and_compliant", "rejected", "trace"):
        assert campo in respuesta


# =========================================================================
# 4. Memoria y UI
# =========================================================================


def test_la_memoria_marca_el_frente_sin_cambiar_el_estado(conectadas):
    from engine.reports.connected_report import render_connected_report_html

    html = render_connected_report_html(conectadas)
    assert "<th>Pareto</th>" in html
    assert "◆" in html
    assert "no cambia el estado" in html
    assert "CONFORME" not in html.split("Alternativas aceptadas", 1)[1].split("Sistemas rechazados", 1)[0].replace(
        "CONFORMES", "")


def _ui(nombre: str) -> str:
    return (UI / nombre).read_text(encoding="utf-8")


def test_el_esquema_de_la_UI_solo_escala_la_escena_del_motor():
    """No recalcula geometría: no toca huellas, cargas ni longitudes de zapata; lee
    cajas y cotas ya situadas."""
    fuente = _ui("components/ConnectedSystemDiagram.tsx")
    for prohibido in ("exterior_B_m", "interior_B_m", "axis_distance_m", "footprints", "P_kN"):
        assert prohibido not in fuente, prohibido
    for usado in ("scene.exterior_footing", "scene.beam", "scene.dimensions", "scene.status_label",
                  "scene.open_tbds", "scene.scope_note"):
        assert usado in fuente, usado


def test_la_vista_de_resultados_usa_comparacion_pareto_y_escena():
    fuente = _ui("components/ConnectedResultsView.tsx")
    for usado in ("data.comparison", "in_pareto", "data.pareto_size", "data.scene",
                  "<ConnectedSystemDiagram"):
        assert usado in fuente, usado
    assert "pertenecer al frente no cambia el estado" in fuente


def test_el_formulario_impide_cuerpo_rigido_con_par_puro():
    """D1 en la presentación: la opción incompatible queda deshabilitada y el cálculo
    bloqueado. La regla es la del motor; el servidor sigue siendo la autoridad."""
    panel = _ui("components/ConnectedInputPanel.tsx")
    api_ts = _ui("lib/api.ts")
    assert "export function coupleModeCompatible" in api_ts
    assert 'analysisModel === "CUERPO_RIGIDO" && coupleMode === "PAR_PURO_EN_ZAPATA"' in api_ts
    assert "combinacionIncompatible" in panel
    assert "disabled={running || faltanDeclaraciones || combinacionIncompatible}" in panel


def test_la_regla_de_la_UI_coincide_con_la_del_motor():
    """La copia de la regla en TypeScript no puede divergir de la del motor: se
    comprueban las cuatro combinaciones contra `check_couple_mode_compatible`."""
    from engine.domain.connected_layout import (
        AnalysisModel, CoupleTransferMode, check_couple_mode_compatible,
    )

    api_ts = _ui("lib/api.ts")
    incompatible_ts = ('CUERPO_RIGIDO', 'PAR_PURO_EN_ZAPATA')
    for modelo in AnalysisModel:
        for modo in CoupleTransferMode:
            try:
                check_couple_mode_compatible(modelo, modo)
                motor_ok = True
            except ValueError:
                motor_ok = False
            ts_ok = (modelo.value, modo.value) != incompatible_ts
            assert motor_ok == ts_ok, (modelo, modo)
    assert all(v in api_ts for v in incompatible_ts)
