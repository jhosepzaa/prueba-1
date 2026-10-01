"""Pendiente 1 — esquema 2D de la zapata combinada.

Es paridad de PRESENTACIÓN: la combinada ya tenía tabla comparativa, frente de Pareto y
motivos de descarte agrupados; le faltaba el esquema. No cambia ningún criterio, ninguna
ecuación ni ningún estado.

La regla que estos tests protegen es la de `scene_dto.py`: **la visualización muestra
datos ya calculados y nunca los recalcula**. Todas las posiciones salen del motor, a
partir de la misma geometría que usó el cálculo.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.integration.typology_catalog import CATALOG
from engine.optimization.combined_generator import (
    CombinedSearchParameters,
    build_layout,
    generate_combined_alternatives,
    rank_combined_alternatives,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from engine.visualization.combined_scene import COLUMN_STUB_HEIGHT_M, build_combined_scene
from tests.test_api_combined_phase2 import _request
from tests.test_combined_footing_phase2 import CODE, TAPA, _specs

MAT = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))
BORDE = 0.25


def _barrido(**kw):
    params = CombinedSearchParameters(
        length_min_m=6.8, length_max_m=7.6, length_step_m=0.40,
        width_min_m=3.6, width_max_m=4.4, width_step_m=0.40,
        h_min_m=0.60, h_max_m=0.90, h_step_m=0.05,
        first_column_edge_distance_m=BORDE, **kw,
    )
    g = generate_combined_alternatives(
        _specs(), params,
        soil=SoilProfile(qadm_kPa=147.1, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )
    return params, g


@pytest.fixture(scope="module")
def escena():
    params, g = _barrido()
    mejor = rank_combined_alternatives(g.valid)[0].alternative
    layout = build_layout(_specs(), mejor.length_m, mejor.width_m,
                          params.first_column_edge_distance_m, params.longitudinal_direction)
    return build_combined_scene(layout, mejor), mejor, layout


# =========================================================================
# 1. La escena no recalcula: repite la geometría del cálculo
# =========================================================================


def test_la_huella_y_el_peralte_son_los_del_resultado(escena):
    sc, alt, _ = escena
    r = alt.result
    assert (sc.B_m, sc.L_m, sc.h_m) == (r.B_m, r.L_m, r.h_m)
    assert sc.longitudinal_direction == r.longitudinal_direction
    assert sc.alternative_id == alt.id
    # La caja de la zapata: centrada en la base, de tamaño B × L × h.
    assert (sc.footing.size.x, sc.footing.size.y, sc.footing.size.z) == (r.B_m, r.L_m, r.h_m)
    assert (sc.footing.center.x, sc.footing.center.y) == (0.0, 0.0)
    assert sc.footing.center.z == pytest.approx(r.h_m / 2)


def test_cada_columna_esta_donde_la_puso_el_layout(escena):
    sc, alt, layout = escena
    assert [c.label for c in sc.columns] == [c.label for c in layout.columns]
    for marca, col in zip(sc.columns, layout.columns):
        assert (marca.x_m, marca.y_m) == (col.offset_x_m, col.offset_y_m)
        assert marca.box.size.x == col.placement.column.bx_m
        assert marca.box.size.y == col.placement.column.by_m
        # El tramo que emerge es de presentación y arranca en la cara superior.
        assert marca.box.size.z == COLUMN_STUB_HEIGHT_M
        assert marca.box.center.z == pytest.approx(alt.result.h_m + COLUMN_STUB_HEIGHT_M / 2)


def test_las_cotas_reproducen_los_datos_de_entrada_de_la_busqueda(escena):
    """El voladizo inicial es la distancia al lindero declarada y la separación entre ejes
    es la del proyecto: si la escena los recalculara, no coincidirían."""
    sc, alt, _ = escena
    por_id = {d.id: d for d in sc.dimensions}
    assert f"B = {alt.result.B_m:.2f} m" == por_id["B"].label
    assert f"L = {alt.result.L_m:.2f} m" == por_id["L"].label
    assert por_id["voladizo_inicial"].label.startswith(f"{BORDE:.2f} m al eje de C1")
    separacion = _specs()[1].distance_from_first_m
    assert por_id["entre_C1_C2"].label == f"{separacion:.2f} m entre ejes"
    resto = alt.result.B_m - BORDE - separacion
    assert por_id["voladizo_final"].label == f"{resto:.2f} m al extremo"
    assert all(d.plane == "XY" for d in sc.dimensions)


def test_la_escena_no_contiene_ninguna_ecuacion():
    """Igual que `scene_dto`/`connected_scene`: sitúa en el espacio, no calcula."""
    fuente = io.open("engine/visualization/combined_scene.py", encoding="utf-8").read()
    for prohibido in ("sqrt", "phi", "0.85", "f_c", "qadm", "solve_", "check_"):
        assert prohibido not in fuente, prohibido


# =========================================================================
# 2. El esquema no presenta nada como conforme
# =========================================================================


def test_una_alternativa_conforme_no_lleva_aviso(escena):
    sc, alt, _ = escena
    assert alt.result.overall_status in (CheckStatus.PASS, CheckStatus.INFO)
    assert sc.status is alt.result.overall_status
    assert sc.status_note == ""


def test_una_alternativa_no_verificada_lleva_el_aviso():
    """Desde la decisión 6 el barrido puede entregar una NO VERIFICADA: el esquema tiene
    que decirlo, porque un dibujo limpio se lee como un diseño conforme."""
    specs = [
        s.model_copy(update={"loads": s.loads.model_copy(update={
            "service": [c.model_copy(update={"Hx_kN": 300.0}) for c in s.loads.service],
            "factored": [c.model_copy(update={"Hx_kN": 420.0}) for c in s.loads.factored],
        })})
        for s in _specs()
    ]
    params = CombinedSearchParameters(
        length_min_m=7.2, length_max_m=7.2, length_step_m=0.40,
        width_min_m=4.0, width_max_m=4.0, width_step_m=0.40,
        h_min_m=0.60, h_max_m=0.90, h_step_m=0.05,
        first_column_edge_distance_m=BORDE,
    )
    g = generate_combined_alternatives(
        specs, params,
        soil=SoilProfile(qadm_kPa=147.1, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )
    alt = g.valid[0]
    assert alt.result.overall_status is CheckStatus.NOT_VERIFIED
    sc = build_combined_scene(build_layout(specs, 7.2, 4.0, BORDE), alt)
    assert sc.status is CheckStatus.NOT_VERIFIED
    assert "NO puede presentarse como conforme" in sc.status_note
    assert "NO_FAIL" in sc.status_note


# =========================================================================
# 3. La API la entrega, y el catálogo lo declara
# =========================================================================


def test_la_api_entrega_la_escena_de_la_primera_alternativa():
    d = TestClient(app).post("/api/design-combined", json=_request()).json()
    sc = d["scene"]
    assert sc is not None
    primera = d["top"][0]
    assert sc["alternative_id"] == primera["id"]
    assert (sc["B_m"], sc["L_m"], sc["h_m"]) == (primera["length_m"], primera["width_m"], primera["h_m"])
    assert sc["status"] == primera["status"]
    assert [c["label"] for c in sc["columns"]] == [c["label"] for c in _request()["columns"]]
    assert sc["scope_note"]


def test_sin_alternativas_aceptadas_no_hay_escena():
    payload = _request()
    payload["soil"] = dict(payload["soil"], qadm_kPa=30.0)
    d = TestClient(app).post("/api/design-combined", json=payload).json()
    assert d["top"] == [] and d["scene"] is None


def test_el_catalogo_declara_el_esquema_2d():
    combinada = next(t for t in CATALOG.typologies if t.id == "combinada")
    assert combinada.capabilities["esquema_2d"] is True
    assert combinada.capabilities["vista_3d"] is True, "Pendiente 3: ya tiene vista 3D"
    dif = {k.id: k for k in CATALOG.known_differences}
    assert dif["PRESENTACION_COMBINADA"].resolution is not None
    assert "3D" in dif["PRESENTACION_COMBINADA"].resolution


def test_el_esquema_de_la_UI_solo_escala_la_escena_del_motor():
    fuente = io.open("ui/src/components/CombinedFootingDiagram.tsx", encoding="utf-8").read()
    for usado in ("scene.footing", "scene.columns", "scene.dimensions", "scene.status",
                  "scene.status_note", "scene.scope_note", "scene.longitudinal_direction"):
        assert usado in fuente, usado
    # No recalcula geometría: ni raíces, ni momentos, ni presiones.
    for prohibido in ("Math.sqrt", "qadm", "Mu", "As_"):
        assert prohibido not in fuente, prohibido
    assert "CombinedFootingDiagram" in io.open(
        "ui/src/components/CombinedResultsView.tsx", encoding="utf-8"
    ).read()
