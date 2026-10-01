"""Fase 2 — motivos de descarte de la zapata combinada: únicos, deterministas y trazables.

No cambia ningún criterio: los textos de `discard_reasons` y su orden son los de siempre; se
añade de qué verificación viene cada uno y un resumen agrupado del barrido. Los recuentos se
reconstruyen aquí con un barrido propio (sin usar el acumulador que se prueba).
"""

from __future__ import annotations

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.optimization.combined_discards import (
    OTHER_CATEGORY,
    category_of,
    diagnose_combined_discard,
)
from engine.optimization.combined_generator import (
    CombinedSearchParameters,
    _frange,
    build_layout,
    generate_combined_alternatives,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from tests.freeze.cases import COMBINED_CASES
from tests.freeze.test_freeze_isolated import _solve_combined
from tests.test_combined_footing_phase2 import CODE, TAPA, _specs

SEVERIDAD = {"FAIL": 3, "NO VERIFICADO": 2, "WARNING": 1, "INFO": 0, "PASS": 0}
MATERIALES = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))


def _suelo(q=1.5 * 98.0665):
    return SoilProfile(qadm_kPa=q, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50)


def _params(h_min=0.40, h_step=0.10):
    return CombinedSearchParameters(
        length_min_m=6.0, length_max_m=7.6, length_step_m=0.40,
        width_min_m=3.0, width_max_m=4.4, width_step_m=0.40,
        h_min_m=h_min, h_max_m=0.90, h_step_m=h_step,
        first_column_edge_distance_m=0.25,
    )


def _barrer(params, suelo):
    return generate_combined_alternatives(
        _specs(), params, soil=suelo, code=CODE, contact_model=FullContactModel(),
        top_cover=TAPA, **MATERIALES,
    )


def _barrido_manual(params, suelo):
    """Mismo recorrido que el generador, escrito aparte: (descartadas, aceptadas, no resueltas)."""
    descartadas, aceptadas, no_resueltas = [], 0, 0
    for L in _frange(params.length_min_m, params.length_max_m, params.length_step_m):
        for B in _frange(params.width_min_m, params.width_max_m, params.width_step_m):
            for h in _frange(params.h_min_m, params.h_max_m, params.h_step_m):
                try:
                    lay = build_layout(_specs(), L, B, params.first_column_edge_distance_m)
                except ValueError:
                    continue
                try:
                    r = solve_combined_footing(lay, h, soil=suelo, code=CODE,
                                               contact_model=FullContactModel(), top_cover=TAPA, **MATERIALES)
                except ValueError:
                    no_resueltas += 1
                    continue
                # Decisión 6: el criterio es NO_FAIL, igual que en el generador.
                if not r.overall_status.discards:
                    aceptadas += 1
                    break
                descartadas.append(((L, B, h), r))
    return descartadas, aceptadas, no_resueltas


@pytest.fixture(scope="module")
def barrido():
    params, suelo = _params(), _suelo()
    return params, suelo, _barrer(params, suelo), _barrido_manual(params, suelo)


# =========================================================================
# 1. Registro por motivo: alineado con discard_reasons y trazable
# =========================================================================


def _dirigidos():
    """Escenarios que activan cada motivo que los barridos normales no tocan."""
    res = []
    # Proporción > 10 (E.050 art. 23.3) y Df < 0,80 m (E.050 art. 26.2).
    lay = build_layout(_specs(), 7.6, 0.70, 0.25)
    res.append(solve_combined_footing(lay, 0.60, soil=_suelo(), code=CODE,
                                      contact_model=FullContactModel(), top_cover=TAPA, **MATERIALES))
    poco = SoilProfile(qadm_kPa=400.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=0.50)
    res.append(solve_combined_footing(build_layout(_specs(), 7.2, 4.0, 0.25), 0.80, soil=poco, code=CODE,
                                      contact_model=FullContactModel(), top_cover=TAPA, **MATERIALES))
    # Secciones delgadas: flexión, desarrollo, cortante y franjas.
    descartadas, _, _ = _barrido_manual(_params(h_min=0.15, h_step=0.10), _suelo(60.0))
    res += [r for _, r in descartadas]
    return res


@pytest.fixture(scope="module")
def dirigidos():
    return _dirigidos()


def _resultados_a_revisar(barrido, dirigidos=()):
    _, _, _, (descartadas, _, _) = barrido
    return [r for _, r in descartadas] + [_solve_combined(c) for c in COMBINED_CASES] + list(dirigidos)


# Prefijo estable del texto → verificación de traza que debe registrarlo. Escrito aparte del
# solver: si un motivo se registra contra otra verificación, esto lo detecta.
PREFIJOS = [
    ("Proporción ", "shape_ratio"),
    ("Presión de contacto:", "contact_pressure"),
    ("Flexión longitudinal, cara ", "flexure_"),
    ("Cara ", "flexure_"),
    ("Cortante longitudinal:", "shear_longitudinal"),
    # Auditoría de paridad (H2, 2026-09-19): §11.12.1.1 en la combinada.
    ("Cortante transversal:", "shear_transversal"),
    ("Franja transversal de ", "transverse_strip_"),
    ("Punzonamiento en ", "punching_"),
    ("PROFUNDIDAD DE CIMENTACIÓN", "foundation_depth"),
    # Auditoría de paridad (2026-09-19): §15.7 en la combinada.
    ("No cumple peralte mínimo", "min_depth"),
]


def test_el_texto_y_la_verificacion_registrada_son_coherentes(barrido, dirigidos):
    for r in _resultados_a_revisar(barrido, dirigidos):
        for x in r.discard_records:
            esperado = next(v for k, v in PREFIJOS if x.text.startswith(k))
            assert x.check_id.startswith(esperado), (x.text, x.check_id)


def test_todos_los_puntos_de_descarte_quedan_cubiertos(barrido, dirigidos):
    vistos = {(x.check_id.rstrip("0123456789").split("_C")[0] if x.check_id.startswith(("punching_", "transverse_strip_")) else x.check_id, x.aspect)
              for r in _resultados_a_revisar(barrido, dirigidos) for x in r.discard_records}
    for requerido in [
        ("shape_ratio", "proporcion_mayor_que_10"),
        ("foundation_depth", "profundidad_insuficiente"),
        ("contact_pressure", "presion_admisible"),
        ("flexure_bottom", "seccion"),
        ("shear_longitudinal", "concreto_solo"),
        ("transverse_strip", "seccion"),
        ("transverse_strip", "longitud_desarrollo"),
        ("punching", "CAPACIDAD_TRANSFERENCIA_MOMENTO"),
        ("min_depth", "peralte_minimo"),
        ("shear_transversal", "concreto_solo"),
    ]:
        assert requerido in vistos, (requerido, sorted(vistos))


def test_cada_motivo_tiene_su_registro_en_el_mismo_orden_y_con_el_mismo_texto(barrido, dirigidos):
    for r in _resultados_a_revisar(barrido, dirigidos):
        assert [x.text for x in r.discard_records] == r.discard_reasons


def test_cada_registro_apunta_a_una_entrada_de_traza_con_categoria_conocida(barrido, dirigidos):
    for r in _resultados_a_revisar(barrido, dirigidos):
        ids = {e.id for e in r.trace.entries}
        for x in r.discard_records:
            assert x.check_id in ids, x
            assert category_of(x.check_id) != OTHER_CATEGORY, x.check_id


# =========================================================================
# 2. Diagnóstico por alternativa
# =========================================================================


def test_toda_entrada_degradada_produce_una_causa_y_las_causas_son_unicas(barrido, dirigidos):
    for r in _resultados_a_revisar(barrido, dirigidos):
        d = diagnose_combined_discard(r)
        claves = [c.key for c in d.causes]
        assert len(claves) == len(set(claves))
        degradadas = {e.id for e in r.trace.entries if SEVERIDAD[e.status.value] > 0}
        assert degradadas <= {c.check_id for c in d.causes}
        # Todos los textos originales están en alguna causa, y ninguno se inventa.
        textos = [t for c in d.causes for t in c.texts]
        assert set(textos) == set(r.discard_reasons)
        assert all(len(c.texts) == len(set(c.texts)) for c in d.causes)


def test_la_causa_principal_es_la_primera_de_mayor_severidad_en_orden_de_traza(barrido):
    _, _, _, (descartadas, _, _) = barrido
    assert descartadas
    for _, r in descartadas:
        d = diagnose_combined_discard(r)
        peor = max(SEVERIDAD[e.status.value] for e in r.trace.entries)
        primera = next(e for e in r.trace.entries if SEVERIDAD[e.status.value] == peor)
        assert d.primary.check_id == primera.id
        assert SEVERIDAD[d.primary.status] == peor
        sev = [SEVERIDAD[c.status] for c in d.causes]
        assert sev == sorted(sev, reverse=True)


def test_el_punzonamiento_conserva_su_causa_fisica(barrido):
    """El aspecto de un descarte por punzonamiento es la causa física del motor (Fase 5B)."""
    _, _, _, (descartadas, _, _) = barrido
    etiquetas = [sp.label for sp in _specs()]
    vistos = 0
    for _, r in descartadas:
        por_columna = dict(zip(etiquetas, r.punching))
        for c in diagnose_combined_discard(r).causes:
            if c.category == "PUNZONAMIENTO" and c.texts:
                causa = por_columna[c.element].failure_cause
                assert c.aspect == (causa.value if causa is not None else "no_cumple")
                assert c.check_id == f"punching_{c.element}"
                vistos += 1
    assert vistos > 0


# =========================================================================
# 3. Resumen del barrido: recuentos, invariantes y determinismo
# =========================================================================


def test_los_criterios_y_recuentos_no_cambian(barrido):
    _, _, r, (descartadas, aceptadas, no_resueltas) = barrido
    assert r.discarded_count == len(descartadas)
    assert len(r.valid) == aceptadas
    assert r.unresolved_count == no_resueltas
    assert r.evaluated_count == len(r.valid) + r.discarded_count + r.unresolved_count


def test_los_recuentos_por_grupo_coinciden_con_una_reconstruccion_independiente(barrido):
    _, _, r, (descartadas, _, _) = barrido
    esperado, principal = Counter(), Counter()
    por_estado = Counter()
    for _, res in descartadas:
        d = diagnose_combined_discard(res)
        por_estado[d.status] += 1
        for clave in {(c.category, c.aspect, c.status) for c in d.causes}:
            esperado[clave] += 1
        principal[(d.primary.category, d.primary.aspect, d.primary.status)] += 1
    s = r.discard_summary
    assert {(g.category, g.aspect, g.status): g.count for g in s.groups} == dict(esperado)
    assert {(g.category, g.aspect, g.status): g.primary_count for g in s.groups if g.primary_count} == dict(principal)
    assert sum(g.primary_count for g in s.groups) == r.discarded_count
    assert s.discarded_by_status == dict(sorted(por_estado.items()))
    assert all(g.count <= r.discarded_count for g in s.groups)


def test_el_resumen_es_determinista_y_ordenado(barrido):
    params, suelo, r, _ = barrido
    otra = _barrer(params, suelo)
    assert otra.discard_summary == r.discard_summary
    claves = [(-g.count, -g.primary_count, g.category, g.aspect, g.status) for g in r.discard_summary.groups]
    assert claves == sorted(claves)
    for g in r.discard_summary.groups:
        assert g.check_ids == sorted(g.check_ids) and g.elements == sorted(g.elements)
        assert g.example is not None


def test_el_cortante_de_concreto_solo_tiene_motivo_escrito(barrido):
    """Hallazgo de la Fase 2, resuelto en la auditoría C-V: el FAIL del cortante longitudinal
    (criterio de concreto solo) ya no queda sin motivo escrito."""
    _, _, r, _ = barrido
    g = next(g for g in r.discard_summary.groups if g.category == "CORTANTE_LONGITUDINAL")
    assert (g.aspect, g.check_ids, g.has_written_reason) == ("concreto_solo", ["shear_longitudinal"], True)
    assert "concreto solo" in g.example.texts[0]
    assert not any(g.category == "CORTANTE_LONGITUDINAL" and g.aspect == "no_cumple"
                   for g in r.discard_summary.groups)


def test_una_entrada_no_verificada_sin_texto_se_agrupa_sin_inventar_motivo():
    """ACTUALIZADO en la decisión 6. El propósito es el mismo: una entrada que degrada el
    estado SIN motivo escrito —aquí la estabilidad no implementada con fuerzas
    horizontales— debe aparecer en el resumen con su estado real y `has_written_reason`
    en False, sin que nadie le invente un texto.

    Lo que cambió es cómo se llega a ella: con NO_FAIL una geometría solo NO VERIFICADA ya
    no se descarta, así que el escenario necesita además un FAIL. Se usa un suelo
    insuficiente, que hace fallar la presión de contacto sin tocar la estabilidad."""
    from tests.test_combined_horizontal_forces_d4 import BASE, KERN, _con_H
    from engine.optimization.combined_generator import ColumnSpec

    specs = [
        ColumnSpec(label=col.label, column=col.placement.column,
                   distance_from_first_m=col.placement.offset_x_m - BASE.layout.columns[0].placement.offset_x_m,
                   loads=col.loads)
        for col in _con_H(BASE.layout, 300.0).columns
    ]
    params = CombinedSearchParameters(
        length_min_m=BASE.layout.B_m, length_max_m=BASE.layout.B_m, length_step_m=0.2,
        width_min_m=BASE.layout.L_m, width_max_m=BASE.layout.L_m, width_step_m=0.2,
        h_min_m=BASE.h_m, h_max_m=BASE.h_m, h_step_m=0.05,
        first_column_edge_distance_m=BASE.layout.columns[0].placement.offset_x_m + BASE.layout.B_m / 2,
    )
    r = generate_combined_alternatives(specs, params, soil=_suelo(80.0), concrete=BASE.concrete,
                                       steel=BASE.steel, code=CODE, contact_model=KERN, top_cover=BASE.top_cover)
    assert r.valid == [] and r.discarded_count == r.evaluated_count
    g = next(g for g in r.discard_summary.groups if g.category == "ESTABILIDAD")
    assert (g.aspect, g.status, g.has_written_reason) == ("no_verificado", "NO VERIFICADO", False)
    # Dos entradas degradan sin texto: el deslizamiento porque falta μ y el volcamiento
    # porque en modo directo no se conoce la carga muerta (E.020 art. 20.1).
    assert g.check_ids == ["overturning_x", "sliding"]
    assert g.example.texts == [], "No se inventa un motivo donde el solver no escribió ninguno"
    # La geometría se descarta por el FAIL, no por la entrada NO VERIFICADA.
    assert r.discard_summary.discarded_by_status == {"FAIL": r.discarded_count}
    assert any(g.category == "PRESION_CONTACTO" and g.status == "FAIL"
               for g in r.discard_summary.groups)


def test_las_geometrias_no_resueltas_se_cuentan_y_agrupan():
    params, suelo = _params(h_min=0.05, h_step=0.05), _suelo()
    r = _barrer(params, suelo)
    assert r.unresolved_count > 0
    assert sum(u.count for u in r.discard_summary.unresolved) == r.unresolved_count
    assert r.discard_summary.unresolved[0].reason == "Peralte insuficiente"
    assert r.evaluated_count == len(r.valid) + r.discarded_count + r.unresolved_count


# =========================================================================
# 4. API (aditiva)
# =========================================================================


def test_la_api_publica_los_grupos_sin_cambiar_los_campos_existentes():
    from tests.test_api_combined_phase2 import _request

    d = TestClient(app).post("/api/design-combined", json=_request()).json()
    for campo in ("top", "evaluated_count", "discarded_count", "truncated", "search_note", "comparison"):
        assert campo in d
    grupos = d["discard_groups"]
    assert grupos
    assert sum(g["primary_count"] for g in grupos) == d["discarded_count"]
    assert sum(d["discarded_by_status"].values()) == d["discarded_count"]
    assert d["evaluated_count"] == len(d["comparison"]) + d["discarded_count"] + d["unresolved_count"]
    for g in grupos:
        assert set(g) >= {"category", "label", "aspect", "status", "count", "primary_count",
                          "check_ids", "elements", "code_references", "has_written_reason", "example"}
