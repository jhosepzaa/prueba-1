"""Linderos del terreno y búsqueda automática — combinada y conectada (2026-09-28).

Lo que se protege:
  - Sin linderos y con la posición declarada, NADA cambia (misma geometría, mismo layout).
  - La posición automática centra la resultante de la combinación permanente y se recorta
    contra los linderos; con la columna al lindero, la zapata queda al ras.
  - Una planta que no cabe en el terreno no se evalúa, y se dice.
  - Los linderos laterales de la combinada corren la zapata; en la conectada limitan el
    ancho (las zapatas se modelan centradas sobre su columna).
  - Los rangos automáticos son una heurística declarada que CUBRE soluciones conocidas.
Las comprobaciones de posición se hacen a mano, sin llamar a la función probada.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.site_limits import SiteLimits
from engine.optimization.combined_generator import (
    ColumnSpec,
    auto_first_column_edge_distance,
    auto_transverse_shift,
    build_layout,
)

S, F = LoadCombinationType.SERVICIO, LoadCombinationType.FACTORIZADA


def _cargas(P: float, M: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=S, P_kN=P, Mx_kNm=M)],
        factored=[LoadCombination(name="U1", type=F, P_kN=1.4 * P, Mx_kNm=1.4 * M)],
    )


def _specs(P1=800.0, P2=1200.0, d=5.0, b=0.50):
    col = Column(shape="cuadrada", bx_m=b, by_m=b)
    return [
        ColumnSpec(label="C1", column=col, distance_from_first_m=0.0, loads=_cargas(P1)),
        ColumnSpec(label="C2", column=col, distance_from_first_m=d, loads=_cargas(P2)),
    ]


# --- 1. Posición longitudinal -----------------------------------------------------

def test_sin_linderos_centra_la_resultante():
    specs = _specs()
    L = 7.0
    x_R = (800 * 0 + 1200 * 5.0) / 2000.0          # 3,0 m desde C1
    a_mano = -(x_R - L / 2.0)                       # el extremo queda a 0,5 m detrás de C1
    assert auto_first_column_edge_distance(specs, L, "X", None) == pytest.approx(a_mano)


def test_con_la_columna_al_lindero_la_zapata_queda_al_ras():
    specs = _specs()
    lim = SiteLimits(start_clearance_m=0.0)
    # Centrar pediría 0,5 m detrás de C1, pero el lindero está en su cara (0,25 m).
    assert auto_first_column_edge_distance(specs, 7.0, "X", lim) == pytest.approx(0.25)


def test_el_lindero_del_fondo_empuja_la_zapata_hacia_atras():
    specs = _specs(P1=200.0, P2=2000.0)     # resultante cerca de C2: centrar la llevaría hacia delante
    L = 6.0
    # Sin lindero, lo más adelante posible sin destapar C1: extremo en su cara (0,25).
    assert auto_first_column_edge_distance(specs, L, "X", None) == pytest.approx(0.25)
    lim = SiteLimits(end_clearance_m=0.10)
    fin_permitido = 5.0 + 0.25 + 0.10       # cara de C2 + holgura
    a_mano = -(fin_permitido - L)           # extremo inicial = fin − L → 0,65 detrás de C1
    assert auto_first_column_edge_distance(specs, L, "X", lim) == pytest.approx(a_mano)


def test_si_no_cabe_entre_linderos_no_hay_posicion():
    specs = _specs()
    lim = SiteLimits(start_clearance_m=0.0, end_clearance_m=0.0)
    # Entre linderos caben 5,0 + 0,25 + 0,25 = 5,5 m: una zapata de 6 m no cabe.
    assert auto_first_column_edge_distance(specs, 6.0, "X", lim) is None
    assert auto_first_column_edge_distance(specs, 5.5, "X", lim) == pytest.approx(0.25)


# --- 2. Posición lateral -----------------------------------------------------------

def test_sin_linderos_laterales_no_se_corre_nada():
    assert auto_transverse_shift(_specs(), 3.0, "X", None) == 0.0
    assert auto_transverse_shift(_specs(), 3.0, "X", SiteLimits(start_clearance_m=0.0)) == 0.0


def test_el_lindero_lateral_corre_el_eje_de_la_zapata():
    lim = SiteLimits(side_neg_clearance_m=0.0)       # columnas al ras del lindero lateral −
    W = 3.0
    # Borde − de la zapata en la cara de las columnas (−0,25): eje en −0,25 + W/2.
    assert auto_transverse_shift(_specs(), W, "X", lim) == pytest.approx(-0.25 + W / 2.0)


def test_build_layout_sin_corrimiento_es_el_de_siempre():
    specs = _specs()
    a = build_layout(specs, 7.0, 3.0, 0.5, "X")
    b = build_layout(specs, 7.0, 3.0, 0.5, "X", transverse_shift_m=0.0)
    assert a.model_dump() == b.model_dump()
    c = build_layout(specs, 7.0, 3.0, 0.5, "X", transverse_shift_m=1.25)
    assert c.columns[0].placement.offset_y_m == pytest.approx(-1.25)


# --- 3. API de la combinada ---------------------------------------------------------

def _combinada(**cambios) -> dict:
    col = lambda lab, d, P: {"label": lab, "shape": "cuadrada", "bx_m": 0.5, "by_m": 0.5,
                              "distance_from_first_m": d,
                              "combinations": [{"name": "S1", "type": "SERVICIO", "P_kN": P},
                                               {"name": "U1", "type": "FACTORIZADA", "P_kN": 1.4 * P}]}
    base = {
        "columns": [col("C1", 0.0, 800.0), col("C2", 5.0, 1200.0)],
        "soil": {"qadm_kPa": 250.0, "gamma_kNm3": 18.0, "Df_m": 1.5},
        "search": {"auto_ranges": True, "first_column_edge_distance_m": None},
        "top_cover": {"case": "contacto_suelo_barras_pequenas"},
    }
    base.update(cambios)
    return base


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app)


def test_la_combinada_calcula_sin_que_el_usuario_de_rangos_ni_posicion(cliente):
    r = cliente.post("/api/design-combined", json=_combinada())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["top"], "la búsqueda automática encuentra alternativas"
    assert "estimado por el programa" in j["search_note"]
    assert "Posición de la zapata elegida por el programa" in j["search_note"]


def test_la_combinada_respeta_el_lindero_inicial(cliente):
    r = cliente.post("/api/design-combined", json=_combinada(site_limits={"start_clearance_m": 0.0}))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["top"]
    for a in j["comparison"]:
        # El extremo nunca pasa del lindero: a lo sumo, media columna detrás del eje de C1.
        assert a["first_column_edge_distance_m"] <= 0.25 + 1e-9
    assert "Linderos declarados" in j["search_note"]


def test_la_escena_de_la_combinada_usa_la_posicion_calculada(cliente):
    j = cliente.post("/api/design-combined", json=_combinada(site_limits={"start_clearance_m": 0.0})).json()
    mejor = j["top"][0]
    escena = j["scene"]
    borde_inicial = -mejor["length_m"] / 2.0
    c1 = next(c for c in escena["columns"] if c["label"] == "C1")
    assert c1["x_m"] - borde_inicial == pytest.approx(mejor["first_column_edge_distance_m"])


# --- 4. Conectada -------------------------------------------------------------------

def test_el_lindero_lateral_limita_el_ancho_de_la_conectada():
    from engine.optimization.connected_generator import ConnectedSearchParameters, recortar_por_linderos
    from tests.test_connected_search_phase4d import _layout, _params

    base = _params()
    p = base.model_copy(update={"ext_transv_max_m": 4.0, "int_transv_max_m": 4.0, "int_long_max_m": 4.0,
                                "site_limits": SiteLimits(side_pos_clearance_m=0.60, end_clearance_m=0.40)})
    recortado, nota = recortar_por_linderos(ConnectedSearchParameters(**p.model_dump()), _layout())
    assert recortado.ext_transv_max_m == pytest.approx(0.50 + 2 * 0.60)
    assert recortado.int_transv_max_m == pytest.approx(0.50 + 2 * 0.60)
    assert recortado.int_long_max_m == pytest.approx(0.50 + 2 * 0.40)
    assert "centradas sobre su columna" in nota


def test_la_conectada_calcula_con_busqueda_automatica(cliente):
    from tests.test_connected_presentation_phase4e import _peticion

    peticion = _peticion()
    peticion["search"] = {"auto_ranges": True}
    r = cliente.post("/api/design-connected", json=peticion)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["accepted_count"] > 0
    assert not j["truncated"], "la búsqueda automática ajusta el tope a su malla"
    assert "estimado por el programa" in j["search_note"]


def test_los_rangos_automaticos_cubren_la_solucion_de_aragon_p2():
    """La heurística no decide nada, pero tiene que MIRAR donde está la solución: la
    CONN-076 del problema 2 de Aragón (exterior 2,80 × 5,40, interior 6,00 × 2,80, h 1,25)
    tiene que caer dentro del rango que el programa estima solo."""
    from api import schemas
    from api.server import _build_connected_layout
    from api import mapping
    from engine.optimization.auto_search import estimate_connected_search
    from tests.test_carga_neta_ascendente_conectada import _peticion

    req = schemas.ConnectedDesignRequest(**_peticion(2.8, 5.4, 6.0, 2.8, 1.25))
    layout = _build_connected_layout(req)
    soil = mapping.build_soil(req.soil, req.units)
    rangos, nota = estimate_connected_search(layout, soil, None, 4000)
    for eje, v in (("ext_long", 2.8), ("ext_transv", 5.4), ("int_long", 6.0), ("int_transv", 2.8), ("h", 1.25)):
        assert rangos[f"{eje}_min_m"] - 1e-9 <= v <= rangos[f"{eje}_max_m"] + 1e-9, (eje, rangos)
    assert "Heurística de búsqueda" in nota
