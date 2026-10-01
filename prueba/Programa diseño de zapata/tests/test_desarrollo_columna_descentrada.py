"""Desarrollo del refuerzo con la columna descentrada — E.060 §15.6.2 (2026-09-28).

Defecto: `build_rebar_geometry` tomaba el voladizo como (B − bx)/2, es decir, la columna
CENTRADA, aunque `depth_solver` ya conocía su posición real. En la zapata de lindero eso
no describe nada: el voladizo libre mide B − bx y, hacia el lindero, la barra solo tiene
el ancho de la columna para anclarse.

Texto normativo (docs/normativa/texto/e.060-concreto-armado-sencico.txt):
  §15.6.2  «La tracción o compresión calculadas en el refuerzo en cada sección debe
           desarrollarse a cada lado de dicha sección»
  §15.6.3  secciones críticas en los planos de §15.4.2 (la cara de la columna)

Decisión del proyectista (2026-09-28): se verifica la cara cuyo momento GOBIERNA la
dirección; en ella, el menor de los dos tramos:
    hacia el borde libre:                    voladizo − recubrimiento
    hacia el otro lado, a través de la columna: columna + voladizo opuesto − recubrimiento
Ganchos en la conectada: no por ahora.

Las reconstrucciones de este archivo se escriben a mano, sin llamar a la función probada.
"""
from __future__ import annotations

import pytest

from engine.reinforcement.rebar_geometry import build_rebar_geometry, development_length_available

COVER = 0.075


def _geo(B, L, bx, by, **kw):
    return build_rebar_geometry(
        B_m=B, L_m=L, h_m=0.60, bx_m=bx, by_m=by, cover_m=COVER,
        db_x_m=0.0159, db_y_m=0.0159, n_bars_x=10, n_bars_y=10,
        spacing_x_m=0.20, spacing_y_m=0.20, d_used_by_engine_m=0.50, **kw,
    )


# --- 1. Con la columna centrada no cambia nada -------------------------------------

@pytest.mark.parametrize("B, L, bx, by", [(2.0, 2.0, 0.4, 0.4), (3.0, 2.2, 0.5, 0.3), (1.2, 1.2, 0.6, 0.6)])
def test_concentrica_da_exactamente_lo_de_antes(B, L, bx, by):
    antes_x, antes_y = max((B - bx) / 2 - COVER, 0.0), max((L - by) / 2 - COVER, 0.0)
    for kw in ({}, {"cantilevers_x_m": ((B - bx) / 2,) * 2, "cantilevers_y_m": ((L - by) / 2,) * 2,
                    "governing_face_x": "mayor coordenada", "governing_face_y": "menor coordenada"}):
        g = _geo(B, L, bx, by, **kw)
        assert g.layer_x.available_development_length_m == antes_x
        assert g.layer_y.available_development_length_m == antes_y
        assert g.layer_x.through_column_length_m is None
        assert g.layer_y.through_column_length_m is None


# --- 2. Zapata de lindero: el tramo hacia el lindero es el ancho de la columna -------

def test_lindero_gobierna_el_tramo_a_traves_de_la_columna():
    B, bx = 2.0, 0.5                     # columna al ras del borde x = 0
    c_lo, c_hi = 0.0, B - bx
    disponible_a_mano = min(c_hi - COVER, bx + c_lo - COVER)      # = 0,425
    g = _geo(B, 2.0, bx, 0.5, cantilevers_x_m=(c_lo, c_hi), governing_face_x="mayor coordenada")
    assert g.layer_x.available_development_length_m == pytest.approx(disponible_a_mano)
    assert g.layer_x.available_development_length_m == pytest.approx(0.425)
    assert g.layer_x.cantilever_m == pytest.approx(1.5)
    assert g.layer_x.through_column_length_m == pytest.approx(0.425)
    # La regla anterior daba (2,0 − 0,5)/2 − 0,075 = 0,675: sobrestimaba el anclaje.
    assert g.layer_x.available_development_length_m < (B - bx) / 2 - COVER


def test_sin_indicar_la_cara_se_verifican_todas_las_que_tienen_voladizo():
    """Lectura más estricta, para cuando no hubo momento con que elegir la cara."""
    c, disp, tramo = development_length_available((0.15, 1.35), 0.5, COVER)
    assert disp == pytest.approx(0.15 - COVER), "gobierna el voladizo corto hacia su borde"
    assert c == pytest.approx(0.15) and tramo is None


def test_la_cara_que_gobierna_evita_el_artificio_del_voladizo_corto():
    """Holgura de 0,15 m al lindero (caso congelado Z6): con la cara que gobierna la
    flexión, el voladizo largo, dispone de min(1,35 − 0,075; 0,5 + 0,15 − 0,075)."""
    c, disp, tramo = development_length_available((0.15, 1.35), 0.5, COVER, "mayor coordenada")
    assert disp == pytest.approx(min(1.35 - COVER, 0.5 + 0.15 - COVER))
    assert disp == pytest.approx(0.575)
    assert c == pytest.approx(1.35) and tramo == pytest.approx(0.575)


def test_cara_al_ras_no_es_seccion_critica():
    """Si la cara que gobierna fuera una sin voladizo, no hay nada que desarrollar desde
    ella y se cae a la regla sin cara: nunca se inventa una longitud."""
    c, disp, _ = development_length_available((0.0, 0.0), 0.5, COVER, "mayor coordenada")
    assert c == 0.0 and disp == 0.0


def test_voladizo_largo_con_columna_ancha_no_cambia():
    """Descentrada pero con columna ancha: el tramo a través de la columna es mayor que el
    del voladizo, y gobierna este último, como antes."""
    c, disp, tramo = development_length_available((0.4, 1.0), 1.2, COVER, "mayor coordenada")
    assert disp == pytest.approx(1.0 - COVER) and tramo is None


# --- 3. De extremo a extremo: el solver pasa la posición real ------------------------

def test_el_solver_de_la_aislada_usa_la_posicion_real_de_la_columna():
    from tests.freeze.cases import CASES
    from tests.freeze.test_freeze_isolated import _evaluate

    caso = next(c for c in CASES if c.name == "16_columna_de_borde")
    cand = _evaluate(caso)
    capa = cand.rebar_geometry.layer_x
    bx = caso.placement.column.bx_m
    c_lo, c_hi = caso.placement.cantilevers_x(caso.B_m)
    # A mano: cara que gobierna = la del voladizo largo; tramo a través de la columna.
    largo, corto = max(c_lo, c_hi), min(c_lo, c_hi)
    a_mano = min(largo - capa.side_cover_m, bx + corto - capa.side_cover_m)
    assert capa.available_development_length_m == pytest.approx(a_mano)
    assert capa.through_column_length_m == pytest.approx(bx + corto - capa.side_cover_m)
