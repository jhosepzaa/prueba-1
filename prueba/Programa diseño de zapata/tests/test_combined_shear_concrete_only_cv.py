"""C-V — cortante longitudinal de la zapata combinada: criterio de CONCRETO SOLO.

Tras la auditoría C-V se retiró el dimensionamiento de estribos que el solver hacía después de un
FAIL de `shear_longitudinal`: no intervenía en ninguna decisión (la entrada del concreto seguía en
FAIL) y sugería que el motor contaba con Vs. Estos tests fijan:

1. los estribos no intervienen en la aceptación actual;
2. C-V conserva exactamente sus resultados (valores medidos ANTES del cambio);
3. no aparecen falsos PASS por Vs.

`Vu > φVc → FAIL` es el criterio del programa, no una prohibición de E.060 (§11.12.1.1 remite a
§11.1–11.5, Vn = Vc + Vs; §11.12.3 admite refuerzo de cortante). Ver
docs/auditoria_cv_cortante_longitudinal_combinada.md.
"""

from __future__ import annotations

import math

import pytest

from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import CONCRETE_ONLY_SHEAR_CRITERION, solve_combined_footing
from engine.optimization.combined_generator import (
    CombinedSearchParameters,
    _frange,
    build_layout,
    generate_combined_alternatives,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from tests.test_combined_footing_phase2 import CODE, TAPA, _specs

FC = 21.0
MAT = dict(concrete=MaterialConcrete(fc_MPa=FC), steel=MaterialSteel(fy_MPa=420.0))
ACEPTA = (CheckStatus.PASS, CheckStatus.INFO)

# Barridos de la auditoría y valores medidos con el motor ANTES de retirar los estribos.
BARRIDOS = {
    #      q [kPa], h_min, h_paso -> evaluadas, descartadas, con cortante FAIL, aceptadas (L, B, h)
    "A": ((147.1, 0.40, 0.10), (118, 117, 94, [(7.2, 4.2, 0.70)])),
    "B": ((147.1, 0.30, 0.05), (256, 255, 214, [(7.2, 4.2, 0.70)])),
    "C": ((60.0, 0.15, 0.10), (160, 160, 140, [])),
}


def _suelo(q):
    return SoilProfile(qadm_kPa=q, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50)


def _resultados(q, h_min, h_paso):
    for L in _frange(6.0, 7.6, 0.40):
        for B in _frange(3.0, 4.4, 0.40):
            for h in _frange(h_min, 0.90, h_paso):
                r = solve_combined_footing(build_layout(_specs(), L, B, 0.25), h, soil=_suelo(q),
                                           code=CODE, contact_model=FullContactModel(),
                                           top_cover=TAPA, **MAT)
                yield (L, B, h), r


@pytest.fixture(scope="module")
def barridos():
    return {k: list(_resultados(*params)) for k, (params, _) in BARRIDOS.items()}


# =========================================================================
# 1. Los estribos no intervienen en la aceptación
# =========================================================================


def test_no_se_dimensionan_estribos_ni_hay_entrada_de_refuerzo(barridos):
    for resultados in barridos.values():
        for _, r in resultados:
            assert r.shear_reinforcement is None
            assert all(e.id != "shear_reinforcement" for e in r.trace.entries)


def test_la_aceptacion_depende_solo_de_las_verificaciones_de_la_traza(barridos):
    for resultados in barridos.values():
        for _, r in resultados:
            aceptada = r.overall_status in ACEPTA
            assert aceptada == all(e.status in ACEPTA for e in r.trace.entries)
            if r.shear_longitudinal.status is CheckStatus.FAIL:
                assert not aceptada


def test_el_fail_de_concreto_solo_queda_explicito_y_trazado(barridos):
    for resultados in barridos.values():
        for _, r in resultados:
            e = r.trace.by_id("shear_longitudinal")
            assert CONCRETE_ONLY_SHEAR_CRITERION in e.hypotheses
            registros = [x for x in r.discard_records if x.check_id == "shear_longitudinal"]
            if r.shear_longitudinal.status is CheckStatus.FAIL:
                assert [x.aspect for x in registros] == ["concreto_solo"]
                assert "concreto solo" in registros[0].text
                assert registros[0].text.startswith("Cortante longitudinal:")
            else:
                assert registros == []
    # El texto no convierte el criterio en una prohibición de la norma, y desde la
    # decisión 6 (2026-09-20) tampoco en una verificación completa de E.060: dice que el
    # aporte de estribos queda FUERA DEL ALCANCE, que el criterio es más estricto y que
    # ampliarlo es una decisión nueva. Lo detalla `test_decisiones_conectada_2026_09_20`.
    assert "Vn = Vc + Vs" in CONCRETE_ONLY_SHEAR_CRITERION
    assert "NO ES UNA VERIFICACIÓN COMPLETA DEL MODELO DE CORTANTE DE E.060" in (
        CONCRETE_ONLY_SHEAR_CRITERION
    )
    assert "Criterio del programa" in CONCRETE_ONLY_SHEAR_CRITERION
    assert "Vn = Vc + Vs" in CONCRETE_ONLY_SHEAR_CRITERION


# =========================================================================
# 2. C-V conserva exactamente sus resultados
# =========================================================================


def test_la_verificacion_es_vu_contra_phi_vc_del_concreto_a_mano(barridos):
    """φVc = 0,85·0,17·√f'c·b·d con b = ancho transversal y d = d inferior (E.060 §11.3.1.1)."""
    for resultados in barridos.values():
        for _, r in resultados:
            s = r.shear_longitudinal
            b = r.L_m if r.longitudinal_direction == "X" else r.B_m
            phi_vc = 0.85 * 0.17 * math.sqrt(FC) * (b * 1000.0) * (r.d_bottom_m * 1000.0) / 1000.0
            assert s.phi_Vc_kN == pytest.approx(phi_vc, rel=1e-12)
            assert s.Vu_kN == pytest.approx(r.diagram.V_max_abs_kN, rel=1e-12)
            assert (s.status is CheckStatus.FAIL) == (s.Vu_kN > s.phi_Vc_kN)


@pytest.mark.parametrize("clave", sorted(BARRIDOS))
def test_recuentos_y_aceptadas_iguales_a_los_previos(barridos, clave):
    (q, h_min, h_paso), (evaluadas, descartadas, con_fail, aceptadas) = BARRIDOS[clave]
    assert sum(1 for _, r in barridos[clave] if r.shear_longitudinal.status is CheckStatus.FAIL) == con_fail
    g = generate_combined_alternatives(
        _specs(),
        CombinedSearchParameters(length_min_m=6.0, length_max_m=7.6, length_step_m=0.40,
                                 width_min_m=3.0, width_max_m=4.4, width_step_m=0.40,
                                 h_min_m=h_min, h_max_m=0.90, h_step_m=h_paso,
                                 first_column_edge_distance_m=0.25),
        soil=_suelo(q), code=CODE, contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )
    assert (g.evaluated_count, g.discarded_count) == (evaluadas, descartadas)
    assert [(a.length_m, a.width_m, a.h_m) for a in g.valid] == aceptadas


# =========================================================================
# 3. Sin falsos PASS por Vs
# =========================================================================


def test_la_geometria_que_solo_falla_por_cortante_sigue_descartada():
    """Caso de la auditoría: L×B = 7,2 × 4,2 m, h = 0,65 m. Solo `shear_longitudinal` falla
    (Vu = 1634,4 kN > φVc = 1576,9 kN) y un Vs de 67,6 kN «cumpliría». Con el criterio de
    concreto solo sigue en FAIL, y la planta se acepta recién con h = 0,70 m."""
    (q, _, _), _ = BARRIDOS["B"]
    r = solve_combined_footing(build_layout(_specs(), 7.2, 4.2, 0.25), 0.65, soil=_suelo(q),
                               code=CODE, contact_model=FullContactModel(), top_cover=TAPA, **MAT)
    degradadas = {e.id for e in r.trace.entries if e.status not in ACEPTA}
    assert degradadas == {"shear_longitudinal"}
    assert r.shear_longitudinal.Vu_kN == pytest.approx(1634.391660237, rel=1e-9)
    assert r.shear_longitudinal.phi_Vc_kN == pytest.approx(1576.920662315, rel=1e-9)
    assert r.overall_status is CheckStatus.FAIL
    assert r.shear_reinforcement is None


def test_ningun_resultado_aceptado_tiene_vu_mayor_que_phi_vc(barridos):
    aceptadas = 0
    for resultados in barridos.values():
        for _, r in resultados:
            if r.overall_status in ACEPTA:
                aceptadas += 1
                assert r.shear_longitudinal.Vu_kN <= r.shear_longitudinal.phi_Vc_kN
    assert aceptadas > 0
