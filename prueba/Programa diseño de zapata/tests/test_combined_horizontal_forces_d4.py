"""D4 — la zapata combinada ignoraba en silencio las fuerzas horizontales.

Hallado al preparar la integración global: con 4000 kN de fuerza horizontal por columna
la combinada salía PASS, sin entrada de deslizamiento, volcamiento ni limitación. La
aislada sí verifica estabilidad.

La corrección original fue conservadora y sin física nueva: con fuerza horizontal el
resultado quedaba NO VERIFICADO con una entrada `stability_not_implemented` que lo
declaraba.

ACTUALIZADO EN EL PENDIENTE 7. Esa declaración quedó SUSTITUIDA por la verificación real
(`engine/foundation/combined_stability.py`). Lo que estos tests siguen fijando es el
hallazgo de D4, que no ha caducado:

  - con fuerza horizontal la combinada NO puede salir PASS mientras falte μ, que es dato
    del proyectista (E.020 art. 22.2);
  - la fuerza horizontal no mueve ningún número del diseño por flexión ni por
    punzonamiento;
  - sin fuerza horizontal no se añade nada (el congelamiento de K1–K4 lo confirma aparte).

Lo que sí cambió: con μ declarado la combinada YA puede pronunciarse. Eso se fija en
tests/test_combined_stability_pendiente7.py.
"""

from __future__ import annotations

import pytest
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.combined_solver import solve_combined_footing
from engine.integration.typology_catalog import CATALOG
from engine.optimization.combined_generator import (
    ColumnSpec,
    CombinedSearchParameters,
    generate_combined_alternatives,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import COMBINED_CASES

CODE = E060ConcreteCode()
KERN = KernCheckModel()
BASE = COMBINED_CASES[0]


def _con_H(layout, Hx: float = 0.0, Hy: float = 0.0, solo_factorizada: bool = False):
    columnas = []
    for col in layout.columns:
        ls = col.loads
        servicio = ls.service if solo_factorizada else [
            x.model_copy(update={"Hx_kN": Hx, "Hy_kN": Hy}) for x in ls.service
        ]
        factorizadas = [x.model_copy(update={"Hx_kN": 1.4 * Hx, "Hy_kN": 1.4 * Hy}) for x in ls.factored]
        columnas.append(col.model_copy(update={"loads": ls.model_copy(
            update={"service": servicio, "factored": factorizadas})}))
    return layout.model_copy(update={"columns": columnas})


def _resolver(layout):
    return solve_combined_footing(layout, BASE.h_m, soil=BASE.soil, concrete=BASE.concrete,
                                  steel=BASE.steel, code=CODE, contact_model=KERN,
                                  top_cover=BASE.top_cover)


def test_sin_fuerza_horizontal_no_cambia_nada():
    r = _resolver(BASE.layout)
    assert r.overall_status is CheckStatus.PASS
    assert r.trace.by_id("stability_not_implemented") is None


@pytest.mark.parametrize("Hx, Hy", [(400.0, 0.0), (0.0, 250.0), (4000.0, 4000.0)])
def test_con_fuerza_horizontal_sin_mu_nunca_sale_PASS(Hx, Hy):
    """ACTUALIZADO en el pendiente 7: la verificación ya existe, pero el suelo de estos
    casos no declara μ, y μ es dato del proyectista. Sin él, NO VERIFICADO y nunca PASS."""
    r = _resolver(_con_H(BASE.layout, Hx, Hy))
    assert r.trace.by_id("stability_not_implemented") is None, "D4 quedó sustituido"
    e = r.trace.by_id("sliding")
    assert e is not None and e.status is CheckStatus.NOT_VERIFIED
    assert any("mu_friction" in p for p in r.stability.sliding.missing_parameters)
    # El hallazgo de D4 sigue en pie: nunca PASS. Lo que cambió es que con una horizontal
    # suficiente el motor YA puede pronunciarse y decir FAIL por volcamiento, en vez de
    # limitarse a «no lo sé»: el volcamiento no necesita μ.
    assert r.overall_status is not CheckStatus.PASS
    assert r.overall_status in (CheckStatus.NOT_VERIFIED, CheckStatus.FAIL)
    if r.overall_status is CheckStatus.FAIL:
        volcamientos = [r.trace.by_id(f"overturning_{eje}").status for eje in ("x", "y")]
        assert CheckStatus.FAIL in volcamientos


def test_solo_las_combinaciones_de_servicio_disparan_la_estabilidad():
    """ACTUALIZADO en el pendiente 7. Antes bastaba una factorizada porque la declaración
    D4 miraba todas las combinaciones. La verificación real usa SERVICIO (E.050 art. 17.1),
    así que una horizontal solo en la factorizada no la dispara: el estado no se degrada y
    tampoco se afirma nada sobre estabilidad."""
    r = _resolver(_con_H(BASE.layout, Hx=300.0, solo_factorizada=True))
    assert r.stability is None
    assert r.trace.by_id("sliding") is None


def test_la_entrada_no_atribuye_a_la_norma_un_factor_que_no_dice():
    """No se inventa respaldo normativo. El FS 1,50 es criterio del programa (D10-2b) y la
    referencia dice cuál es el valor de la norma y que el adoptado es más estricto."""
    e = _resolver(_con_H(BASE.layout, 500.0)).trace.by_id("sliding")
    assert "criterio del programa (D10-2b)" in e.code_reference
    assert "E.020 art. 22.1 (1,25)" in e.code_reference
    # Y la sustitución muestra la RESULTANTE de las dos columnas, no la de una: 2 x 500 kN.
    assert "H = 1000.00 kN" in e.equation_substituted


def test_la_fuerza_horizontal_no_mueve_ningun_numero():
    """La corrección añade una entrada y degrada el estado; no toca la aritmética."""
    a, b = _resolver(BASE.layout), _resolver(_con_H(BASE.layout, 800.0))
    assert a.bottom_face.As_design_m2 == b.bottom_face.As_design_m2
    assert a.contact_pressure.qmax_kPa == b.contact_pressure.qmax_kPa
    assert [p.ratio for p in a.punching] == [p.ratio for p in b.punching]


def test_el_barrido_conserva_lo_no_verificado_y_lo_rotula():
    """ACTUALIZADO en la decisión 6. Antes, el criterio PASS/INFO descartaba toda
    evaluación NO VERIFICADA, de modo que con fuerzas horizontales el barrido quedaba
    vacío: la tipología entera era inutilizable con sismo o viento. Con NO_FAIL la
    geometría se conserva CON su estado, y la nota de búsqueda advierte que aceptada no
    significa conforme. Lo que no cambia: nunca llega a PASS."""
    specs = []
    for col in _con_H(BASE.layout, 300.0).columns:
        specs.append(ColumnSpec(
            label=col.label, column=col.placement.column,
            distance_from_first_m=col.placement.offset_x_m - BASE.layout.columns[0].placement.offset_x_m,
            loads=col.loads,
        ))
    params = CombinedSearchParameters(
        length_min_m=BASE.layout.B_m, length_max_m=BASE.layout.B_m, length_step_m=0.2,
        width_min_m=BASE.layout.L_m, width_max_m=BASE.layout.L_m, width_step_m=0.2,
        h_min_m=BASE.h_m, h_max_m=BASE.h_m, h_step_m=0.05,
        first_column_edge_distance_m=BASE.layout.columns[0].placement.offset_x_m + BASE.layout.B_m / 2,
    )
    r = generate_combined_alternatives(specs, params, soil=BASE.soil, concrete=BASE.concrete,
                                       steel=BASE.steel, code=CODE, contact_model=KERN,
                                       top_cover=BASE.top_cover)
    assert r.evaluated_count >= 1
    assert len(r.valid) == 1
    assert r.valid[0].result.overall_status is CheckStatus.NOT_VERIFIED
    assert r.accepted_and_compliant == [] and len(r.not_verified) == 1
    assert "NO VERIFICADA" in r.search_note and "NO que cumpla" in r.search_note


def test_el_catalogo_registra_la_diferencia():
    ids = {k.id for k in CATALOG.known_differences}
    assert "ESTABILIDAD_COMBINADA" in ids
