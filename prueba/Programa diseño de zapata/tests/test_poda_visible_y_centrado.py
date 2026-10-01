"""Dos silencios del generador de propuestas, resueltos (2026-09-24).

1. LA PODA POR L/B ERA INVISIBLE. Las geometrías con L/B por encima del máximo no se
   generan, de modo que tampoco aparecían entre las descartadas: no quedaba ni rastro de
   que existieran. Y el límite es criterio del programa —2 por omisión—, mientras que
   E.050 art. 23.3 clasifica como zapata hasta L/B = 10. Ahora se cuentan y se explican.
   No se cambia el valor por defecto: eso es decisión del proyectista.

2. LA LONGITUD DE CENTRADO DE LA COMBINADA usaba `service[0]`, la primera combinación de
   la lista, fuera cual fuera. Ahora se elige la primera SIN sismo ni viento y se dice
   cuál es, porque centrar es un criterio de estado PERMANENTE: el sismo se invierte y no
   puede centrarse en los dos sentidos a la vez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.domain.search_parameters import GeometrySearchParameters
from engine.foundation.geometry_generator import (
    count_pruned_by_ratio,
    generate_geometry_candidates,
    pruning_note,
)

cliente = TestClient(app)


# --- 1. La poda por L/B --------------------------------------------------------

def _malla(max_ratio: float) -> GeometrySearchParameters:
    return GeometrySearchParameters(
        B_min_m=1.0, B_max_m=6.0, B_step_m=0.5,
        L_min_m=1.0, L_max_m=6.0, L_step_m=0.5,
        max_LB_ratio=max_ratio,
    )


def test_lo_podado_mas_lo_generado_es_la_malla_entera():
    params = _malla(2.0)
    generadas = sum(1 for _ in generate_geometry_candidates(params))
    assert generadas + count_pruned_by_ratio(params) == 11 * 11


def test_con_el_limite_de_la_norma_apenas_se_poda():
    """E.050 art. 23.3 admite hasta L/B = 10: en esta malla no deja fuera casi nada."""
    assert count_pruned_by_ratio(_malla(10.0)) < count_pruned_by_ratio(_malla(2.0))


def test_sin_poda_no_hay_nota():
    assert pruning_note(0, 2.0) == ""


def test_la_nota_dice_cuantas_y_que_el_limite_no_es_normativo():
    nota = pruning_note(40, 2.0)
    assert "40 geometrías" in nota
    assert "no figuran entre las descartadas" in nota.lower()
    assert "art. 23.3" in nota and "L/B = 10" in nota


def test_la_api_informa_de_la_poda():
    peticion = schemas.DesignRequest(
        search=schemas.SearchInput(
            B_min_m=1.0, B_max_m=6.0, B_step_m=0.5,
            L_min_m=1.0, L_max_m=6.0, L_step_m=0.5,
        ),
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=800),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=1120),
        ],
    ).model_dump(mode="json")
    resumen = cliente.post("/api/design", json=peticion).json()["summary"]
    assert resumen["pruned_by_LB_ratio"] == 40
    assert "no se evaluaron" in resumen["pruned_note"]


# --- 2. El centrado de la combinada --------------------------------------------

def _columna(label: str, distancia: float, P_grav: float, P_sismo: float):
    return schemas.CombinedColumnInput(
        label=label, shape="cuadrada", bx_m=0.5, by_m=0.5,
        distance_from_first_m=distancia,
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=P_grav),
            schemas.LoadCombinationInput(
                name="S2", type="SERVICIO", P_kN=P_sismo, includes_seismic_loads=True
            ),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=P_grav * 1.4),
        ],
    )


@pytest.fixture(scope="module")
def respuesta() -> dict:
    peticion = schemas.CombinedDesignRequest(
        columns=[_columna("C1", 0.0, 800, 400), _columna("C2", 5.0, 800, 1400)],
        search=schemas.CombinedSearchInput(
            length_min_m=6.0, length_max_m=8.0, length_step_m=0.2,
            width_min_m=2.0, width_max_m=3.0, width_step_m=0.2,
            h_min_m=0.5, h_max_m=0.9, h_step_m=0.05,
            first_column_edge_distance_m=0.25,
        ),
        top_cover=schemas.TopCoverInput(case="no_expuesto"),
    ).model_dump(mode="json")
    return cliente.post("/api/design-combined", json=peticion).json()


def test_el_centrado_usa_la_combinacion_sin_sismo(respuesta):
    """Con cargas simétricas en gravedad, la resultante cae en el centro del vano."""
    assert respuesta["centering_note"].startswith("[S1]")
    # x_R = 2,50 m desde la primera columna + 0,25 de voladizo → L = 5,50 m
    assert respuesta["centering_length_m"] == pytest.approx(5.50, rel=1e-6)


def test_el_centrado_declara_cuanto_se_mueve_con_el_sismo(respuesta):
    nota = respuesta["centering_note"]
    assert "longitud de centrado va de" in nota
    assert "no puede centrarse en los dos sentidos" in nota


def test_el_centrado_sigue_siendo_predimensionamiento(respuesta):
    """No es criterio normativo, y la nota lo dice: lo exigido se verifica después."""
    assert "CRITERIO DE PREDIMENSIONAMIENTO" in respuesta["centering_note"]
