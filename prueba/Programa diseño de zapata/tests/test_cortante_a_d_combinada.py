"""Cortante longitudinal de la combinada a d de la cara — E.060 §15.5.2 y §11.1.3.1 (2026-09-29).

Decisión del proyectista: el cortante unidireccional longitudinal se toma a d de la cara de
cada columna, no como máx |V| de todo el diagrama (que era el criterio conservador del
programa, `docs/auditoria_cv_cortante_longitudinal_combinada.md`). Se protege:

  1. el valor, contra una reconstrucción a mano (Wight 15-5, validado por StructurePoint);
  2. los tres casos de borde: voladizo más corto que d, columna entre la cara y la
     sección (§11.1.3 c) y presión negativa (se conserva el criterio anterior);
  3. la PROPIEDAD que justifica el criterio: con presión no negativa, ningún punto fuera de
     las zonas cubiertas por §11.1.3.1 tiene más |V| que el de diseño.
"""
from __future__ import annotations

import random

import pytest

from engine.analysis.beam_diagram import PointLoad, _shear, build_beam_diagram, critical_one_way_shear

KIP, FT = 4.448222, 0.3048


def _carga(label, x, P, w, M=0.0):
    return PointLoad(label=label, position_m=x, P_kN=P, width_m=w, M_kNm=M)


# --- 1. Contra el ejemplo publicado ---------------------------------------------------

def test_wight_15_5_a_mano():
    """25 ft 4 in; exterior 480 k a 8 in del extremo (16 in de ancho); interior 720 k a
    20 ft 8 in (24 in). d = 36,5 in. A mano, en kip y ft: w = 1200/25,333; la sección a d a
    la izquierda de la cara de la interior está en x = 20,667 − 1 − 3,042 = 16,625 ft y
    V = w·x − 480 = 307,5 k."""
    L = (25 + 4 / 12) * FT
    dia = build_beam_diagram(L, 8 * FT, [
        _carga("EXT", 8 / 12 * FT, 480 * KIP, 16 / 12 * FT),
        _carga("INT", (20 + 8 / 12) * FT, 720 * KIP, 2 * FT),
    ])
    d = 36.5 / 12 * FT
    c = critical_one_way_shear(dia, d)
    w = 1200 / (25 + 4 / 12)
    a_mano = (w * (20 + 8 / 12 - 1 - 36.5 / 12) - 480) * KIP
    assert c.Vu_kN == pytest.approx(a_mano, rel=1e-9)
    assert c.Vu_kN == pytest.approx(307.5 * KIP, rel=2e-3)
    assert (c.column_label, c.side, c.at_face) == ("INT", "izquierda", False)
    assert c.Vu_kN < dia.V_max_abs_kN, "a d de la cara es menor que el máximo del diagrama"


# --- 2. Casos de borde ------------------------------------------------------------------

def test_voladizo_mas_corto_que_d_no_tiene_seccion():
    """Columna exterior al ras (voladizo 0) e interior con voladizo de 0,30 m < d = 0,60 m:
    solo cuentan las secciones del tramo entre columnas."""
    L = 6.0
    dia = build_beam_diagram(L, 2.0, [_carga("A", 0.25, 1000, 0.5), _carga("B", 5.45, 1000, 0.5)])
    c = critical_one_way_shear(dia, 0.60)
    assert c.x_m is not None
    assert 0.5 < c.x_m < 5.2, "la sección que gobierna está en el tramo entre columnas"


def test_columna_entre_la_cara_y_la_seccion_obliga_a_tomar_la_cara():
    """Dos columnas con 0,30 m libres entre caras y d = 0,60 m: la sección a d de una cae
    detrás de la otra, luego §11.1.3 (c) no se cumple y ese lado se toma en la cara."""
    dia = build_beam_diagram(4.0, 2.0, [_carga("A", 1.5, 1200, 0.5), _carga("B", 2.3, 800, 0.5)])
    c = critical_one_way_shear(dia, 0.60)
    V_cara_der_A = abs(_shear(1.75, dia.w_start_kNm, dia.w_end_kNm, 4.0, dia.loads))
    V_cara_izq_B = abs(_shear(2.05, dia.w_start_kNm, dia.w_end_kNm, 4.0, dia.loads))
    assert c.Vu_kN >= max(V_cara_der_A, V_cara_izq_B) - 1e-9
    assert c.at_face or c.Vu_kN > max(V_cara_der_A, V_cara_izq_B)


def test_con_presion_negativa_se_conserva_el_maximo_del_diagrama():
    dia = build_beam_diagram(3.0, 2.0, [_carga("A", 0.2, 1000, 0.4, M=600.0), _carga("B", 2.6, 100, 0.4)])
    assert min(dia.w_start_kNm, dia.w_end_kNm) < 0
    c = critical_one_way_shear(dia, 0.5)
    assert c.method == "maximo_del_diagrama"
    assert c.Vu_kN == dia.V_max_abs_kN


# --- 3. La propiedad que justifica el criterio ------------------------------------------

def _zonas_excluidas(cargas, d):
    """Huellas de columna y la franja [cara, cara ± d] de cada lado: lo que §11.1.3.1
    permite diseñar con el cortante de la sección a d."""
    zonas = []
    for ld in cargas:
        izq, der = ld.position_m - ld.width_m / 2, ld.position_m + ld.width_m / 2
        zonas += [(izq - d, der + d)]
    return zonas


@pytest.mark.parametrize("semilla", range(40))
def test_ningun_punto_fuera_de_las_zonas_supera_el_cortante_de_diseno(semilla):
    rnd = random.Random(semilla)
    L = rnd.uniform(4.0, 10.0)
    n = rnd.choice((2, 3))
    xs = sorted(rnd.uniform(0.3, L - 0.3) for _ in range(n))
    cargas = [_carga(f"C{i}", x, rnd.uniform(300, 2000), rnd.uniform(0.3, 0.7)) for i, x in enumerate(xs)]
    # separar las columnas lo suficiente para que no se solapen
    for a, b in zip(cargas, cargas[1:]):
        if b.position_m - a.position_m < (a.width_m + b.width_m) / 2 + 0.05:
            return
    dia = build_beam_diagram(L, 2.0, cargas)
    if min(dia.w_start_kNm, dia.w_end_kNm) < 0:
        return  # fuera del núcleo: rige el criterio anterior, probado aparte
    d = rnd.uniform(0.3, 1.2)
    c = critical_one_way_shear(dia, d)
    zonas = _zonas_excluidas(cargas, d)
    # con una columna entre la cara y su sección, esa franja se evalúa en la cara (más
    # exigente): la comprobación sigue valiendo con las franjas completas
    for k in range(2001):
        x = L * k / 2000
        if any(a - 1e-9 <= x <= b + 1e-9 for a, b in zonas):
            continue
        V = abs(_shear(x, dia.w_start_kNm, dia.w_end_kNm, L, cargas))
        assert V <= c.Vu_kN + 1e-6, (semilla, x, V, c.Vu_kN)
