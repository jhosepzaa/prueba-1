"""Pendiente 7 — estabilidad de la zapata combinada: deslizamiento y volcamiento.

QUÉ SUSTITUYE
=============
La declaración D4: con fuerza horizontal la combinada quedaba NO VERIFICADA con la entrada
`stability_not_implemented`, porque la verificación no existía para esta tipología. Ahora
existe. Análisis y decisión en `docs/pendiente7_estabilidad_combinada.md`.

QUÉ FIJA ESTE ARCHIVO
=====================
1. la resultante de varias columnas, reconstruida A MANO sin llamar al código que prueba;
2. la envolvente aprobada (opción B): se toma la peor de las dos lecturas del momento;
3. el criterio adoptado en D10-2b: FS 1,50 al deslizamiento y al volteo, también con sismo,
   sin atribuirle ese valor a la norma;
4. μ es dato del proyectista: sin μ, NO VERIFICADO y nunca PASS;
5. sin fuerza horizontal no se añade nada, y los casos congelados no se mueven;
6. la zapata aislada NO se toca (decisión del usuario).
"""

from __future__ import annotations

import math

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.load_cases import (
    ActionLevel,
    CombinationDefinition,
    LoadCase,
    LoadCaseKind,
    derive_load_case_set,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.combined_stability import (
    check_combined_stability,
    resultants,
)
from engine.foundation.self_weight import compute_self_weight
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from engine.soil.stability import (
    E020_FS_SLIDING,
    E030_FS_OVERTURNING_SEISMIC,
    PROGRAM_FS_OVERTURNING,
    PROGRAM_FS_OVERTURNING_SEISMIC,
    PROGRAM_FS_SLIDING,
)

CODE = E060ConcreteCode()
TAPA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")
MAT = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)

B, L, H = 8.0, 3.60, 0.80
GAMMA, DF = 18.0, 1.50


def _suelo(q=400.0, mu=None, c=None, fs_d=None, fs_v=None):
    return SoilProfile(
        qadm_kPa=q, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=GAMMA, Df_m=DF,
        mu_friction_soil_concrete=mu, cohesion_kPa=c,
        FS_sliding_required=fs_d, FS_overturning_required=fs_v,
    )


def _directo(P, Mx=0.0, Hx=0.0, Hy=0.0, sismo=False) -> LoadCaseSet:
    """Modo DIRECTO: combinaciones ya formadas, sin composición."""
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P,
                                 Mx_kNm=Mx, Hx_kN=Hx, Hy_kN=Hy, includes_seismic_loads=sismo)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4,
                                  Mx_kNm=Mx * 1.4, Hx_kN=Hx * 1.4, Hy_kN=Hy * 1.4,
                                  includes_seismic_loads=sismo)],
    )


def _por_casos(P_cm, P_cv, Mx_cm=0.0, Mx_cv=0.0, Hx_cm=0.0, Hx_cv=0.0) -> LoadCaseSet:
    """Modo POR CASOS: el motor conoce qué parte es carga muerta."""
    casos = [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=P_cm, Mx_kNm=Mx_cm, Hx_kN=Hx_cm),
        LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=P_cv, Mx_kNm=Mx_cv, Hx_kN=Hx_cv),
    ]
    return derive_load_case_set(casos, [
        CombinationDefinition(name="S1", type=LoadCombinationType.SERVICIO,
                              factors={"CM": 1.0, "CV": 1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA,
                              factors={"CM": 1.4, "CV": 1.7}),
    ])


def _layout(cargas: list[LoadCaseSet], posiciones=(1.0, 7.0), B_m=B, L_m=L) -> CombinedFootingLayout:
    return CombinedFootingLayout(
        B_m=B_m, L_m=L_m,
        columns=[
            ColumnOnFooting(
                label=f"C{i + 1}",
                placement=ColumnPlacement(column=COL, offset_x_m=x - B_m / 2.0),
                loads=cs,
            )
            for i, (x, cs) in enumerate(zip(posiciones, cargas))
        ],
    )


def _W(B_m=B, L_m=L, h=H) -> float:
    return compute_self_weight(B_m, L_m, h, DF, MAT["concrete"].unit_weight_kNm3, GAMMA).W_total_kN


def _estabilidad(layout, soil, h=H):
    return check_combined_stability(layout, soil, _W(layout.B_m, layout.L_m, h),
                                    layout.B_m, layout.L_m, h)


# =========================================================================
# 1. La resultante, reconstruida a mano
# =========================================================================


def test_la_resultante_es_la_suma_con_el_momento_de_la_excentricidad():
    """Reconstrucción independiente: M = Σ (M_i + P_i·offset_i), H = Σ H_i."""
    lay = _layout([_directo(900.0, Mx=40.0, Hx=50.0), _directo(1200.0, Mx=-15.0, Hx=30.0)])
    r = resultants(lay)[0]

    off1, off2 = 1.0 - B / 2.0, 7.0 - B / 2.0
    assert r.P_total_kN == pytest.approx(2100.0)
    assert r.Mx_total_kNm == pytest.approx(40.0 + 900.0 * off1 - 15.0 + 1200.0 * off2)
    assert r.Hx_kN == pytest.approx(80.0)
    assert r.Hy_kN == 0.0
    # Modo directo: no se sabe qué parte es muerta, así que las dos lecturas coinciden.
    assert r.exact_dead_load is False
    assert r.Mx_stabilizing_kNm == pytest.approx(r.Mx_total_kNm)
    assert r.N_stabilizing_kN == pytest.approx(r.P_total_kN)


def test_el_fs_de_deslizamiento_se_reconstruye_a_mano():
    lay = _layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0, Hy=40.0)])
    soil = _suelo(mu=0.45)
    st = _estabilidad(lay, soil)

    H_res = math.hypot(80.0, 40.0)
    N = 2100.0 + _W()
    fs = 0.45 * N / H_res
    assert st.sliding.H_resultant_kN == pytest.approx(H_res, rel=1e-12)
    assert st.sliding.N_total_kN == pytest.approx(N, rel=1e-12)
    assert st.sliding.FS_obtained == pytest.approx(fs, rel=1e-12)
    assert st.sliding.cohesion_resistance_kN is None, "Sin cohesión declarada no se inventa"


def test_el_fs_de_volcamiento_se_reconstruye_a_mano():
    lay = _layout([_directo(900.0, Mx=40.0, Hx=50.0), _directo(1200.0, Mx=-15.0, Hx=30.0)])
    st = _estabilidad(lay, _suelo(mu=0.45))

    off1, off2 = 1.0 - B / 2.0, 7.0 - B / 2.0
    Mx = 40.0 + 900.0 * off1 - 15.0 + 1200.0 * off2
    N = 2100.0 + _W()
    m_estab = N * B / 2.0
    m_volc = abs(Mx) + 80.0 * H
    assert st.overturning_x.stabilizing_moment_kNm == pytest.approx(m_estab, rel=1e-12)
    assert st.overturning_x.overturning_moment_kNm == pytest.approx(m_volc, rel=1e-12)
    assert st.overturning_x.FS_obtained == pytest.approx(m_estab / m_volc, rel=1e-12)


def test_duplicar_la_fuerza_horizontal_divide_el_fs_por_dos():
    soil = _suelo(mu=0.45)
    a = _estabilidad(_layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0)]), soil)
    b = _estabilidad(_layout([_directo(900.0, Hx=100.0), _directo(1200.0, Hx=60.0)]), soil)
    assert b.sliding.FS_obtained == pytest.approx(a.sliding.FS_obtained / 2.0, rel=1e-12)


def test_dos_columnas_simetricas_dejan_la_resultante_centrada():
    """Invariante: con cargas iguales y simétricas el momento de las excentricidades se
    cancela y solo queda el que produce la fuerza horizontal."""
    lay = _layout([_directo(900.0, Hx=40.0), _directo(900.0, Hx=40.0)], posiciones=(1.0, 7.0))
    st = _estabilidad(lay, _suelo(mu=0.5))
    N = 1800.0 + _W()
    assert st.overturning_x.applied_moment_total_kNm == pytest.approx(0.0, abs=1e-9)
    assert st.overturning_x.overturning_moment_kNm == pytest.approx(80.0 * H, rel=1e-12)
    assert st.overturning_x.FS_obtained == pytest.approx((N * B / 2.0) / (80.0 * H), rel=1e-12)


# =========================================================================
# 2. La envolvente (opción B)
# =========================================================================


def test_sin_composicion_las_dos_lecturas_coinciden():
    st = _estabilidad(_layout([_directo(900.0, Mx=40.0, Hx=50.0), _directo(1200.0, Hx=30.0)]),
                      _suelo(mu=0.45))
    o = st.overturning_x
    assert o.applied_moment_total_kNm == pytest.approx(o.applied_moment_dead_kNm)
    assert o.envelope_reading == "TOTAL"


def test_una_carga_viva_excentrica_favorable_no_puede_enmascarar_el_volcamiento():
    """EL CASO QUE JUSTIFICA LA OPCIÓN B. La carga viva está sobre la columna del lado
    opuesto a la excentricidad de la muerta, de modo que REDUCE |M_total|. Si el momento
    volcador se leyera solo con la carga total, el volcamiento saldría mejor de lo que es.
    La envolvente toma la lectura estabilizante, que es la peor."""
    # C1 al borde con toda la carga muerta; C2 al otro extremo con carga viva dominante.
    lay = _layout([_por_casos(P_cm=900.0, P_cv=0.0, Hx_cm=60.0),
                   _por_casos(P_cm=100.0, P_cv=800.0)])
    st = _estabilidad(lay, _suelo(mu=0.45))
    o = st.overturning_x

    off1, off2 = 1.0 - B / 2.0, 7.0 - B / 2.0
    m_total = 900.0 * off1 + (100.0 + 800.0) * off2
    m_muerta = 900.0 * off1 + 100.0 * off2
    assert o.applied_moment_total_kNm == pytest.approx(abs(m_total), rel=1e-12)
    assert o.applied_moment_dead_kNm == pytest.approx(abs(m_muerta), rel=1e-12)
    assert abs(m_muerta) > abs(m_total), "El escenario debe ser el que justifica la envolvente"
    assert o.envelope_reading == "ESTABILIZANTE"
    assert o.applied_moment_kNm == pytest.approx(abs(m_muerta), rel=1e-12)

    # Y el FS resultante es MENOR que el que daría la lectura total.
    N = 1000.0 + _W()
    fs_envolvente = (N * B / 2.0) / (abs(m_muerta) + 60.0 * H)
    fs_solo_total = (N * B / 2.0) / (abs(m_total) + 60.0 * H)
    assert o.FS_obtained == pytest.approx(fs_envolvente, rel=1e-12)
    assert fs_envolvente < fs_solo_total


def test_la_carga_estabilizante_es_solo_la_muerta():
    """E.020 art. 20.1, tal como ya lo implementa `stabilizing_axial_kN`."""
    lay = _layout([_por_casos(P_cm=900.0, P_cv=400.0, Hx_cm=60.0),
                   _por_casos(P_cm=600.0, P_cv=300.0)])
    r = resultants(lay)[0]
    assert r.exact_dead_load is True
    assert r.P_total_kN == pytest.approx(2200.0)
    assert r.N_stabilizing_kN == pytest.approx(1500.0), "Solo CM"


# =========================================================================
# 3. El criterio de D10-2b, sin atribuírselo a la norma
# =========================================================================


def test_el_fs_exigido_es_el_adoptado_por_el_proyecto():
    st = _estabilidad(_layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0)]),
                      _suelo(mu=0.45))
    assert st.sliding.FS_required == pytest.approx(1.50) == PROGRAM_FS_SLIDING
    assert st.overturning_x.FS_required == pytest.approx(1.50) == PROGRAM_FS_OVERTURNING
    assert "criterio del programa (D10-2b)" in st.sliding.code_reference
    assert "E.020 art. 22.1 (1,25)" in st.sliding.code_reference
    assert "más estricto" in st.sliding.code_reference
    # Los valores de la norma se conservan; el adoptado no los sobrescribe.
    assert (E020_FS_SLIDING, E030_FS_OVERTURNING_SEISMIC) == (1.25, 1.20)


def test_con_sismo_el_fs_sigue_siendo_1_50_y_la_referencia_no_lo_llama_normativo():
    lay = _layout([_directo(900.0, Hx=50.0, sismo=True), _directo(1200.0, Hx=30.0, sismo=True)])
    st = _estabilidad(lay, _suelo(mu=0.45))
    assert st.overturning_x.FS_required == pytest.approx(1.50) == PROGRAM_FS_OVERTURNING_SEISMIC
    ref = st.overturning_x.code_reference
    assert "criterio del programa (D10-2b)" in ref
    assert "E.030 art. 64.2" in ref and "1,20" in ref and "más estricto" in ref


def test_un_fs_declarado_por_el_proyectista_manda_sobre_el_adoptado():
    lay = _layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0)])
    st = _estabilidad(lay, _suelo(mu=0.45, fs_d=2.0, fs_v=1.8))
    assert st.sliding.FS_required == pytest.approx(2.0)
    assert st.overturning_x.FS_required == pytest.approx(1.8)
    assert "proyectista" in st.sliding.code_reference


# =========================================================================
# 4. μ es dato del proyectista
# =========================================================================


def test_sin_mu_el_deslizamiento_queda_no_verificado_y_nunca_pass():
    st = _estabilidad(_layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0)]), _suelo())
    assert st.sliding.status is CheckStatus.NOT_VERIFIED
    assert st.sliding.mu_used is None
    assert st.sliding.FS_obtained is None
    assert st.sliding.friction_resistance_kN is None
    assert any("mu_friction" in p for p in st.sliding.missing_parameters)
    assert st.status is not CheckStatus.PASS


def test_en_modo_directo_un_cumplimiento_no_puede_afirmarse():
    """E.020 art. 20.1: sin composición no se sabe qué parte de P es carga muerta. Un FS
    que cumple con la carga total no demuestra nada; un FAIL sí es válido."""
    st = _estabilidad(_layout([_directo(900.0, Hx=20.0), _directo(1200.0, Hx=10.0)]),
                      _suelo(mu=0.60))
    assert st.sliding.FS_obtained >= st.sliding.FS_required
    assert st.sliding.status is CheckStatus.NOT_VERIFIED
    assert "E.020 art. 20.1" in st.sliding.message


def test_en_modo_por_casos_un_cumplimiento_si_puede_afirmarse():
    lay = _layout([_por_casos(P_cm=900.0, P_cv=100.0, Hx_cm=20.0),
                   _por_casos(P_cm=1200.0, P_cv=100.0, Hx_cm=10.0)])
    st = _estabilidad(lay, _suelo(mu=0.60))
    assert st.sliding.status is CheckStatus.PASS
    assert st.overturning_x.status is CheckStatus.PASS


def test_un_eje_sin_momento_ni_fuerza_no_se_verifica_con_un_fs_infinito():
    """Con las columnas sobre el eje transversal, la resultante no produce momento ni
    fuerza en Y: el FS sería infinito y no significaría nada. Se declara no aplicable,
    igual que en la zapata aislada."""
    st = _estabilidad(_layout([_directo(900.0, Hx=50.0), _directo(1200.0, Hx=30.0)]),
                      _suelo(mu=0.45))
    assert st.overturning_y.FS_obtained is None
    assert st.overturning_y.status is CheckStatus.PASS
    assert "No aplicable" in st.overturning_y.message
    # El eje que sí tiene acción se verifica con normalidad.
    assert st.overturning_x.FS_obtained is not None


def test_un_deslizamiento_insuficiente_es_FAIL():
    st = _estabilidad(_layout([_por_casos(P_cm=300.0, P_cv=0.0, Hx_cm=400.0),
                               _por_casos(P_cm=300.0, P_cv=0.0)]), _suelo(mu=0.30))
    assert st.sliding.status is CheckStatus.FAIL
    assert st.sliding.FS_obtained < st.sliding.FS_required


# =========================================================================
# 5. Integración en el solver: sustituye D4 y no toca los casos sin H
# =========================================================================


def _resolver(cargas, soil, h=H):
    return solve_combined_footing(_layout(cargas), h, soil=soil, code=CODE,
                                  contact_model=FullContactModel(), top_cover=TAPA, **MAT)


def test_sin_fuerza_horizontal_no_se_anade_ninguna_entrada():
    """Los casos congelados K1-K4 no declaran H: esta es la razón por la que no se mueven."""
    r = _resolver([_directo(900.0), _directo(900.0)], _suelo())
    assert r.stability is None
    ids = {e.id for e in r.trace.entries}
    assert ids.isdisjoint({"sliding", "overturning_x", "overturning_y"})
    assert "stability_not_implemented" not in ids
    assert r.overall_status is CheckStatus.PASS


def test_la_entrada_de_no_implementada_desaparece_y_la_sustituyen_tres():
    r = _resolver([_directo(900.0, Hx=50.0), _directo(900.0, Hx=30.0)], _suelo(mu=0.45))
    ids = [e.id for e in r.trace.entries]
    assert "stability_not_implemented" not in ids, "D4 queda sustituido por la verificación"
    assert {"sliding", "overturning_x", "overturning_y"} <= set(ids)
    assert r.stability is not None and r.stability.applicable


def test_con_fuerza_horizontal_y_mu_el_resultado_ya_puede_ser_PASS():
    """Antes de este pendiente, cualquier H dejaba la combinada NO VERIFICADA."""
    lay = _layout([_por_casos(P_cm=900.0, P_cv=100.0, Hx_cm=20.0),
                   _por_casos(P_cm=900.0, P_cv=100.0, Hx_cm=10.0)])
    r = solve_combined_footing(lay, H, soil=_suelo(mu=0.60), code=CODE,
                               contact_model=FullContactModel(), top_cover=TAPA, **MAT)
    for cid in ("sliding", "overturning_x", "overturning_y"):
        assert r.trace.by_id(cid).status is CheckStatus.PASS
    assert r.overall_status is CheckStatus.PASS


def test_un_fallo_de_estabilidad_descarta_con_motivo_escrito():
    r = _resolver([_por_casos(P_cm=300.0, P_cv=0.0, Hx_cm=400.0),
                   _por_casos(P_cm=300.0, P_cv=0.0)], _suelo(mu=0.30))
    assert r.trace.by_id("sliding").status is CheckStatus.FAIL
    assert r.overall_status is CheckStatus.FAIL
    registros = [x for x in r.discard_records if x.check_id == "sliding"]
    assert len(registros) == 1 and registros[0].aspect == "no_cumple"
    assert registros[0].text in r.discard_reasons
    assert "Deslizamiento" in registros[0].text


def test_la_traza_declara_la_envolvente_y_el_criterio_adoptado():
    r = _resolver([_directo(900.0, Hx=50.0), _directo(900.0, Hx=30.0)], _suelo(mu=0.45))
    e = r.trace.by_id("overturning_x")
    texto = " ".join(e.hypotheses)
    assert "ENVOLVENTE" in texto
    assert "CRITERIO DE DISEÑO ADOPTADO POR EL PROYECTO (D10-2b)" in texto
    assert "núcleo central" in texto, "El alcance queda declarado"
    assert "envolvente |M|" in e.equation_substituted


# =========================================================================
# 6. La formulación es COMÚN con la aislada (FORMULACION_VOLTEO)
# =========================================================================


def test_la_combinada_no_reimplementa_el_termino_de_excentricidad():
    """FORMULACION_VOLTEO (aprobada 2026-09-19) sustituyó a la decisión anterior, que
    mantenía la aislada sin `P·offset` ni envolvente.

    Lo que este test fija ahora es lo contrario de lo que fijaba: que hay UNA sola
    implementación del término y que la combinada la usa en vez de repetirla. Si alguien
    vuelve a escribir `P * offset` a mano en este módulo, las dos tipologías pueden
    divergir en silencio, que es exactamente el defecto que FORMULACION_VOLTEO cerró."""
    import inspect

    import engine.foundation.combined_stability as comb
    import engine.soil.stability as m

    # El término vive en el ayudante común, y la combinada lo llama.
    assert "offset_m" in inspect.getsource(m.axis_moments_kNm)
    assert "axis_moments_kNm" in inspect.getsource(comb.resultants)
    assert "stabilizing_axial_kN" in inspect.getsource(comb.resultants)

    # Y no lo reimplementa: ninguna multiplicación por el offset a mano.
    fuente_comb = inspect.getsource(comb)
    for expresion in ("P_kN * ox", "P_kN * oy", "P_kN*ox", "P_kN*oy"):
        assert expresion not in fuente_comb, f"La combinada reimplementa el término: {expresion}"

    # La aislada usa la MISMA formulación: término de excentricidad y envolvente.
    fuente_aislada = inspect.getsource(m._check_overturning_axis)
    assert "offset_m" in fuente_aislada
    assert "envolvente" in fuente_aislada.lower()

    # Y el modelo de resultado es uno solo, no dos.
    assert "envelope_reading" in m.OverturningResult.model_fields
    assert comb.CombinedOverturningResult is m.OverturningResult
