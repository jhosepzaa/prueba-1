"""El barrido de la conectada repartido entre procesos (2026-09-24).

LO QUE HAY QUE DEMOSTRAR no es que vaya más rápido, sino que da EXACTAMENTE lo mismo.
Un barrido que reparte trabajo puede cambiar sin querer:
  - qué candidatos se evalúan, porque dentro de cada planta el recorrido se detiene en la
    primera pareja de peralte aceptada;
  - cuántos, porque el tope se aplica candidato a candidato;
  - los identificadores `CONN-xxx`, que se asignan por orden de aparición.

Estos tests comparan los dos caminos campo por campo sobre el mismo problema, incluido el
caso en que el tope corta el barrido por la mitad.
"""

from __future__ import annotations

import pytest

from api import mapping, schemas
from api.server import _build_connected_layout
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.search_parameters import DepthSearchParameters
from engine.optimization.connected_generator import (
    ConnectedSearchParameters,
    _reparte,
    _tamano_de_lote,
    generate_connected_alternatives,
)


def _columna(label: str, P: float, gancho: str = "ninguno") -> schemas.ConnectedColumnInput:
    return schemas.ConnectedColumnInput(
        label=label, shape="cuadrada", bx_m=0.5, by_m=0.5,
        hook_type_x=gancho, hook_type_y=gancho,
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=P),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=P * 1.4),
        ],
    )


def _montaje(tope: int, paso: float = 0.4):
    """Un problema pequeño pero con aceptaciones y rechazos mezclados."""
    peticion = schemas.ConnectedDesignRequest(
        analysis_model="ARTICULADO",
        couple_transfer_mode="EQUILIBRIO_EN_CIMENTACION",
        # Gancho de 90° en la zapata de lindero (2026-09-28, E.060 §15.6.2).
        exterior=_columna("Z1", 350, gancho="90"), interior=_columna("Z2", 500),
        axis_distance_m=6.0,
        soil=schemas.SoilInput(qadm_kPa=250, gamma_kNm3=18, Df_m=1.5),
        beam=schemas.ConnectingBeamInput(
            b_m=0.35, h_m=1.2, d_m=1.1,
            support_mode="SIN_APOYO", self_weight_mode="DESPRECIADO",
        ),
        search=schemas.ConnectedSearchInput(
            ext_long_min_m=1.8, ext_long_max_m=3.0, ext_long_step_m=paso,
            ext_transv_min_m=1.8, ext_transv_max_m=3.0, ext_transv_step_m=paso,
            int_long_min_m=1.8, int_long_max_m=3.0, int_long_step_m=paso,
            int_transv_min_m=1.8, int_transv_max_m=3.0, int_transv_step_m=paso,
            h_min_m=0.6, h_max_m=0.9, h_step_m=0.05, max_systems=tope,
        ),
    )
    u = peticion.units
    s = peticion.search
    params = ConnectedSearchParameters(
        ext_long_min_m=s.ext_long_min_m, ext_long_max_m=s.ext_long_max_m,
        ext_long_step_m=s.ext_long_step_m,
        ext_transv_min_m=s.ext_transv_min_m, ext_transv_max_m=s.ext_transv_max_m,
        ext_transv_step_m=s.ext_transv_step_m,
        int_long_min_m=s.int_long_min_m, int_long_max_m=s.int_long_max_m,
        int_long_step_m=s.int_long_step_m,
        int_transv_min_m=s.int_transv_min_m, int_transv_max_m=s.int_transv_max_m,
        int_transv_step_m=s.int_transv_step_m,
        h_min_m=s.h_min_m, h_max_m=s.h_max_m, h_step_m=s.h_step_m,
        max_systems=s.max_systems,
        same_depth_both_footings=s.same_depth_both_footings,
    )
    kw = dict(
        soil=mapping.build_soil(peticion.soil, u),
        concrete=mapping.build_materials(peticion.materials, u)[0],
        steel=mapping.build_materials(peticion.materials, u)[1],
        code=E060ConcreteCode(),
        contact_model=mapping.contact_model_for(peticion.soil),
        depth_params=DepthSearchParameters(
            h_min_m=s.h_min_m, h_max_m=s.h_max_m, h_step_m=s.h_step_m
        ),
    )
    return _build_connected_layout(peticion), params, kw


@pytest.mark.parametrize("tope", [500, 37])
def test_los_dos_caminos_dan_el_mismo_barrido(tope):
    """Con tope holgado y con tope que corta a mitad de una planta."""
    layout, params, kw = _montaje(tope)

    secuencial = generate_connected_alternatives(layout, params, workers=1, **kw)
    paralelo = generate_connected_alternatives(layout, params, workers=4, **kw)

    assert secuencial.evaluated_count == paralelo.evaluated_count
    assert secuencial.truncated == paralelo.truncated
    assert [a.id for a in secuencial.accepted] == [a.id for a in paralelo.accepted]
    assert secuencial.model_dump() == paralelo.model_dump()


def test_el_barrido_de_prueba_mezcla_aceptaciones_y_rechazos():
    """Si todo se rechazara, la comparación no probaría gran cosa."""
    layout, params, kw = _montaje(500)
    r = generate_connected_alternatives(layout, params, workers=1, **kw)
    assert r.accepted, "el caso de prueba debería aceptar alguna terna"
    assert r.rejected, "el caso de prueba debería rechazar alguna terna"


def test_con_tope_pequeno_no_se_evalua_ni_un_candidato_de_mas():
    layout, params, kw = _montaje(37)
    for procesos in (1, 4):
        r = generate_connected_alternatives(layout, params, workers=procesos, **kw)
        assert r.evaluated_count == 37
        assert r.truncated


def test_un_barrido_pequeno_no_arranca_procesos():
    """Repartir cuesta medio segundo: por debajo del umbral no compensa."""
    assert _reparte(None, candidatos=50, plantas=20) == 1
    assert _reparte(None, candidatos=5000, plantas=200) > 1
    assert _reparte(1, candidatos=5000, plantas=200) == 1, "workers=1 fuerza el secuencial"
    assert _reparte(None, candidatos=5000, plantas=1) == 1, "una sola planta no se reparte"


def test_el_tamano_de_lote_se_mantiene_en_rango():
    assert _tamano_de_lote(1, 8) == 1
    assert _tamano_de_lote(10_000, 8) == 16
    assert 1 <= _tamano_de_lote(100, 8) <= 16
