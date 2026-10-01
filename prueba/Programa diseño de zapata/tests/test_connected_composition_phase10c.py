"""Fase 10C — composición de las cargas corregidas de la zapata conectada.

En el modo por casos, la carga que recibe cada zapata tras el reparto conserva de qué casos
está hecha (superposición con el mismo reparto). Con ella la estabilidad de esas zapatas
cuenta solo la carga muerta (E.020 art. 20.1). El modo directo no cambia.

Las comprobaciones de superposición se hacen con el pipeline público: se repite el cálculo
con un solo caso cargado y se compara, sin usar la función que construye la composición.
"""

from __future__ import annotations

import pytest

from engine.analysis.connected_statics import (
    ENGINE_BEAM_WEIGHT_CASE,
    ENGINE_FOOTING_WEIGHT_CASE,
    ORIGIN_ENGINE,
    ORIGIN_EXTERIOR,
    ORIGIN_INTERIOR,
    REDISTRIBUTED_COMPOSITION_NOTE,
    correct_loads,
    distribute_couple,
    redistributed_compositions,
)
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.connected_layout import AnalysisModel, BeamSelfWeightMode, CoupleTransferMode
from engine.domain.load_cases import (
    ActionLevel,
    CombinationDefinition,
    LoadCase,
    LoadCaseKind,
    derive_load_case_set,
)
from engine.domain.loads import LoadCombinationType
from engine.foundation.connected_solver import solve_connected_footing
from engine.foundation.depth_solver import soil_actions
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import CONNECTED_CASES, GEO_REF, SOIL_CONN_250, _conn_layout

SERV, FACT = LoadCombinationType.SERVICIO, LoadCombinationType.FACTORIZADA
GAMMA_C = 24.0

MODELOS = [
    "Z1_articulado_equilibrio",                         # ARTICULADO + EQUILIBRIO
    "Z2_articulado_par_puro",                           # ARTICULADO + PAR_PURO
    "Z3_cuerpo_rigido_equilibrio",                      # CUERPO_RIGIDO
    "Z5_eje_longitudinal_Y",                            # viga sobre Y
    "Z8_peso_propio_de_viga_explicito",                 # EXPLICITO, articulado
    "Z12_aragon_p2_cuerpo_rigido",                      # rígido con otra geometría
    "Z14_cuerpo_rigido_con_momento_de_columna",         # rígido con momento
    "Z15_par_puro_con_peso_propio_de_viga_explicito",   # EXPLICITO + PAR_PURO (B*)
]


def _caso(nombre):
    return next(c for c in CONNECTED_CASES if c.name == nombre)


def _definiciones():
    return [
        CombinationDefinition(name="S1", type=SERV, factors={"CM": 1.0, "CV": 1.0, "CSx": 1.0}),
        CombinationDefinition(name="U1", type=FACT, factors={"CM": 1.4, "CV": 1.7}),
    ]


def _a_casos(loads, f_cm=0.6, f_cv=0.4, sismo=(0.0, 0.0, 0.0), H=0.0, M_trans=0.0):
    """Reparte la combinación de servicio del caso congelado en CM + CV (+ CS). Con sismo nulo
    la combinación S1 derivada es IDÉNTICA a la directa."""
    s = loads.service[0]
    P_cs, M_cs, H_cs = sismo
    casos = [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=f_cm * s.P_kN,
                 Mx_kNm=f_cm * s.Mx_kNm + M_trans, My_kNm=f_cm * s.My_kNm + M_trans, Hx_kN=H),
        LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=f_cv * s.P_kN,
                 Mx_kNm=f_cv * s.Mx_kNm, My_kNm=f_cv * s.My_kNm),
        LoadCase(name="CSx", kind=LoadCaseKind.CS, level=ActionLevel.RESISTENCIA,
                 P_kN=P_cs, Mx_kNm=M_cs, My_kNm=M_cs, Hx_kN=H_cs),
    ]
    return derive_load_case_set(casos, _definiciones())


def _layout_por_casos(lay, **kw):
    kw_int = {k: v for k, v in kw.items() if k in ("f_cm", "f_cv")}
    return lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": _a_casos(lay.exterior.loads, **kw)}),
        "interior": lay.interior.model_copy(update={"loads": _a_casos(lay.interior.loads, **kw_int)}),
    })


def _footprints(lay, g):
    return lay.footprints(g.exterior_B_m, g.exterior_L_m, g.exterior_h_m,
                          g.interior_B_m, g.interior_L_m, g.interior_h_m)


def _corregidas(lay, caso):
    return correct_loads(lay, _footprints(lay, caso.geometry), caso.soil, GAMMA_C)


def _resolver(lay, caso):
    return solve_connected_footing(
        lay, caso.geometry, soil=caso.soil, concrete=caso.concrete, steel=caso.steel,
        code=E060ConcreteCode(), contact_model=KernCheckModel(), depth_params=caso.depth_params,
    )


def _M_eje(obj, eje):
    return obj.Mx_kNm if eje == "X" else obj.My_kNm


def _M_trans(obj, eje):
    return obj.My_kNm if eje == "X" else obj.Mx_kNm


def _todas(cl):
    return [
        (cl.exterior.service + cl.exterior.factored, [d.exterior_corrected_composition for d in cl.distributions]),
        (cl.interior.service + cl.interior.factored, [d.interior_corrected_composition for d in cl.distributions]),
    ]


# =========================================================================
# 1. Las componentes suman la carga corregida (positivo)
# =========================================================================


@pytest.mark.parametrize("nombre", MODELOS)
def test_las_componentes_suman_la_carga_corregida(nombre):
    caso = _caso(nombre)
    lay = _layout_por_casos(caso.build_layout(), H=15.0, M_trans=7.0)
    eje = lay.longitudinal_axis
    cl = _corregidas(lay, caso)
    for combos, _ in _todas(cl):
        for combo in combos:
            comp = combo.composition
            assert comp is not None and comp.redistributed
            tol = 1e-9 * max(abs(combo.P_kN), 1.0)
            assert sum(c.P_kN for c in comp.components) == pytest.approx(combo.P_kN, abs=tol)
            assert sum(_M_eje(c, eje) for c in comp.components) == pytest.approx(_M_eje(combo, eje), abs=1e-8 * max(abs(_M_eje(combo, eje)), 1.0))
            assert sum(_M_trans(c, eje) for c in comp.components) == pytest.approx(_M_trans(combo, eje), abs=1e-9)
            assert sum(c.Hx_kN for c in comp.components) == pytest.approx(combo.Hx_kN, abs=1e-9)
            assert {c.origin for c in comp.components} <= {ORIGIN_EXTERIOR, ORIGIN_INTERIOR, ORIGIN_ENGINE}
    for d in cl.distributions:
        assert REDISTRIBUTED_COMPOSITION_NOTE in d.hypotheses
        assert d.exterior_corrected_composition == next(
            c for c in cl.exterior.service + cl.exterior.factored if c.name == d.combo_name
        ).composition


# =========================================================================
# 2. Superposición independiente: un caso a la vez por el pipeline público
# =========================================================================


def _solo(lay, cual):
    """Mismo layout por casos, con los valores de un único caso (el otro en cero)."""
    f = {"CM": dict(f_cm=0.6, f_cv=0.0), "CV": dict(f_cm=0.0, f_cv=0.4)}[cual]
    return _layout_por_casos(lay, **f)


@pytest.mark.parametrize("nombre", MODELOS)
def test_el_aporte_de_cada_caso_es_el_reparto_con_ese_caso_solo(nombre):
    """Aporte de CV a la carga corregida = carga corregida con solo CV cargado − cargas del
    motor. Idem CM. Las cargas del motor dependen del FACTOR CM de la definición, que no
    cambia al anular los valores de un caso."""
    caso = _caso(nombre)
    base = caso.build_layout()
    completo = _corregidas(_layout_por_casos(base), caso)
    solo = {k: _corregidas(_solo(base, k), caso) for k in ("CM", "CV")}

    for lado in ("exterior", "interior"):
        for grupo in ("service", "factored"):
            for i, combo in enumerate(getattr(getattr(completo, lado), grupo)):
                comp = combo.composition.components
                motor = sum(c.P_kN for c in comp if c.origin == ORIGIN_ENGINE)
                for k in ("CM", "CV"):
                    aporte = sum(c.P_kN for c in comp if c.case_name == k)
                    referencia = getattr(getattr(solo[k], lado), grupo)[i].P_kN - motor
                    assert aporte == pytest.approx(referencia, abs=1e-8 * max(abs(combo.P_kN), 1.0))


# =========================================================================
# 3. Peso propio de la viga y de las zapatas
# =========================================================================


@pytest.mark.parametrize("modelo,modo", [
    (AnalysisModel.ARTICULADO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
    (AnalysisModel.CUERPO_RIGIDO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
])
def test_el_peso_de_la_viga_entra_con_el_factor_cm_y_se_conserva(modelo, modo):
    """HV-2 (z_b = 0,30): W = 34,713 kN sin factor. Con reparto que conserva carga, lo que la
    componente de viga aporta a las dos zapatas suma f_CM · W: 1,0 en S1 y 1,4 en U1."""
    caso = _caso("Z8_peso_propio_de_viga_explicito")
    lay = _conn_layout(modelo=modelo, modo=modo, P_ext=850.0, P_int=1100.0,
                       peso=BeamSelfWeightMode.EXPLICITO, z_b=0.30)
    cl = correct_loads(_layout_por_casos(lay), _footprints(lay, GEO_REF), SOIL_CONN_250, GAMMA_C)
    for d in cl.distributions:
        f = 1.0 if d.combo_name == "S1" else 1.4
        ve = next(c for c in d.exterior_corrected_composition.components if c.case_name == ENGINE_BEAM_WEIGHT_CASE)
        vi = next(c for c in d.interior_corrected_composition.components if c.case_name == ENGINE_BEAM_WEIGHT_CASE)
        assert (ve.kind, ve.factor, ve.origin, ve.level) == ("CM", f, ORIGIN_ENGINE, None)
        assert ve.P_kN + vi.P_kN == pytest.approx(f * 34.713, rel=1e-9)
        assert d.beam_self_weight_kN == pytest.approx(f * 34.713, rel=1e-12)
    assert caso.soil.Df_m == SOIL_CONN_250.Df_m


def test_sin_cm_en_la_combinacion_la_viga_no_aporta():
    lay = _conn_layout(modelo=AnalysisModel.ARTICULADO, modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
                       P_ext=850.0, P_int=1100.0, peso=BeamSelfWeightMode.EXPLICITO, z_b=0.30)

    def sin_cm(loads):
        s = loads.service[0]
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=0.5 * s.P_kN),
                 LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=0.5 * s.P_kN)]
        return derive_load_case_set(casos, [
            CombinationDefinition(name="S1", type=SERV, factors={"CM": 1.0, "CV": 1.0}),
            CombinationDefinition(name="U1", type=FACT, factors={"CV": 1.7}),
        ])

    lay = lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": sin_cm(lay.exterior.loads)}),
        "interior": lay.interior.model_copy(update={"loads": sin_cm(lay.interior.loads)}),
    })
    cl = correct_loads(lay, _footprints(lay, GEO_REF), SOIL_CONN_250, GAMMA_C)
    u = next(d for d in cl.distributions if d.combo_name == "U1")
    v = [c for c in u.exterior_corrected_composition.components if c.case_name == ENGINE_BEAM_WEIGHT_CASE]
    assert len(v) == 1 and v[0].factor == 0.0 and v[0].P_kN == 0.0


def test_el_peso_de_las_zapatas_solo_aparece_en_cuerpo_rigido_y_no_crea_carga():
    """En CUERPO_RIGIDO el peso de las zapatas entra en el reparto (F2) y se redistribuye: su
    aporte neto a las dos cargas corregidas suma cero. En ARTICULADO no interviene."""
    for nombre, esperado in (("Z3_cuerpo_rigido_equilibrio", True), ("Z1_articulado_equilibrio", False)):
        caso = _caso(nombre)
        cl = _corregidas(_layout_por_casos(caso.build_layout()), caso)
        for d in cl.distributions:
            we = [c for c in d.exterior_corrected_composition.components if c.case_name == ENGINE_FOOTING_WEIGHT_CASE]
            wi = [c for c in d.interior_corrected_composition.components if c.case_name == ENGINE_FOOTING_WEIGHT_CASE]
            assert bool(we) is esperado
            if esperado:
                # D10C-1: CM con f_CM en la factorizada (1,4) y 1,0 en servicio.
                f = 1.4 if d.combo_type == FACT.value else 1.0
                assert (we[0].kind, we[0].factor) == ("CM", f)
                assert we[0].P_kN + wi[0].P_kN == pytest.approx(0.0, abs=1e-9)


def test_despreciado_no_genera_componente_de_viga():
    caso = _caso("Z1_articulado_equilibrio")
    cl = _corregidas(_layout_por_casos(caso.build_layout()), caso)
    for d in cl.distributions:
        assert not [c for c in d.exterior_corrected_composition.components if c.origin == ORIGIN_ENGINE]


# =========================================================================
# 4. Equilibrio y combinaciones: los totales no cambian respecto del modo directo
# =========================================================================


@pytest.mark.parametrize("nombre", MODELOS)
def test_las_cargas_corregidas_de_servicio_son_las_del_modo_directo(nombre):
    """S1 derivada = S1 directa (CM y CV con factor 1, sismo nulo): el reparto, el peso de la
    viga (× 1,0) y las cargas corregidas son los mismos. Solo se añade la composición."""
    caso = _caso(nombre)
    lay = caso.build_layout()
    directo = _corregidas(lay, caso)
    por_casos = _corregidas(_layout_por_casos(lay), caso)
    for dd, dc in zip(directo.distributions, por_casos.distributions):
        if dd.combo_name != "S1":
            continue
        for campo in ("P_ext_corrected_kN", "M_ext_corrected_kNm", "P_int_corrected_kN",
                      "M_int_corrected_kNm", "delta_P_kN", "R_ext_kN", "V_cut_kN", "M_cut_kNm",
                      "beam_self_weight_kN"):
            assert getattr(dc, campo) == pytest.approx(getattr(dd, campo), rel=1e-12, abs=1e-9)
        assert dc.closes and dc.conserves_load


def test_despreciado_factorizada_tambien_coincide_con_el_modo_directo():
    """Con peso DESPRECIADO nada depende del factor CM: U1 = 1,4 CM + 1,4 CV equivale a la
    U1 directa del caso (P × 1,4)."""
    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    lay = caso.build_layout()

    def u14(loads):
        s = loads.service[0]
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=0.6 * s.P_kN, Mx_kNm=0.6 * s.Mx_kNm),
                 LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=0.4 * s.P_kN, Mx_kNm=0.4 * s.Mx_kNm)]
        return derive_load_case_set(casos, [
            CombinationDefinition(name="S1", type=SERV, factors={"CM": 1.0, "CV": 1.0}),
            CombinationDefinition(name="U1", type=FACT, factors={"CM": 1.4, "CV": 1.4}),
        ])

    lay_c = lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": u14(lay.exterior.loads)}),
        "interior": lay.interior.model_copy(update={"loads": u14(lay.interior.loads)}),
    })
    for dd, dc in zip(_corregidas(lay, caso).distributions, _corregidas(lay_c, caso).distributions):
        assert dc.P_ext_corrected_kN == pytest.approx(dd.P_ext_corrected_kN, rel=1e-12)
        assert dc.P_int_corrected_kN == pytest.approx(dd.P_int_corrected_kN, rel=1e-12)


# =========================================================================
# 5. Estabilidad (E.020 art. 20.1)
# =========================================================================


@pytest.mark.parametrize("nombre", [
    "Z3_cuerpo_rigido_equilibrio", "Z14_cuerpo_rigido_con_momento_de_columna",
])
def test_la_composicion_decide_si_el_volteo_puede_afirmarse(nombre):
    """Donde el volcamiento SÍ tiene demanda, la composición decide si puede afirmarse.

    El reparto de CUERPO_RIGIDO deja una excentricidad residual en la zapata de lindero y un
    momento real en la interior, de modo que la verificación se ejecuta. Entonces:

      - modo directo: no se sabe qué parte de P es carga muerta, se usa la cota superior y el
        cumplimiento NO puede afirmarse (E.020 art. 20.1) → NO VERIFICADO;
      - por casos con toda la carga en CM: N es exacta y vale lo mismo → PASS con el MISMO FS;
      - por casos con 60 % CM: la fuerza estabilizante baja y el FS con ella.

    El escalón PASS → FAIL por composición insuficiente no se fija aquí sino en
    `tests/test_stability.py` (`test_overturning_fail`, `test_sin_fs_de_volteo_declarado_...`):
    es una regla del motor común a las tres tipologías, no algo propio de la conectada."""
    caso = _caso(nombre)
    lay = caso.build_layout()
    eje = lay.longitudinal_axis

    def volteo(r, lado):
        return getattr(getattr(r, lado).stability,
                       "overturning_x" if eje == "X" else "overturning_y")

    for lado in ("exterior", "interior"):
        directo = volteo(_resolver(lay, caso), lado)
        todo_cm = volteo(_resolver(_layout_por_casos(lay, f_cm=1.0, f_cv=0.0), caso), lado)
        parcial = volteo(_resolver(_layout_por_casos(lay, f_cm=0.6, f_cv=0.4), caso), lado)

        assert directo.status is CheckStatus.NOT_VERIFIED, lado
        assert todo_cm.status is CheckStatus.PASS, lado
        assert todo_cm.FS_obtained == pytest.approx(directo.FS_obtained, rel=1e-9), lado
        assert parcial.N_total_kN < directo.N_total_kN, lado
        assert parcial.FS_obtained < todo_cm.FS_obtained, lado


@pytest.mark.parametrize("nombre", [
    "Z1_articulado_equilibrio", "Z2_articulado_par_puro",
    "Z8_peso_propio_de_viga_explicito", "Z15_par_puro_con_peso_propio_de_viga_explicito",
    "Z13_articulado_con_momento_de_columna",
])
def test_la_viga_recentra_cada_componente_y_el_volteo_queda_sin_demanda(nombre):
    """FORMULACION_VOLTEO: por qué en estos casos el volcamiento no depende de la composición.

    La viga de conexión absorbe la excentricidad de la carga que llega, y el reparto es
    LINEAL: cada componente de la composición se recentra por separado, no solo la suma. Por
    eso `M_k + P_k·offset ≈ 0` componente a componente, las dos lecturas de la envolvente son
    nulas y la verificación se declara NO APLICABLE en los tres modos.

    Antes de FORMULACION_VOLTEO el motor leía |M| = |P·offset| como demanda y publicaba un FS
    de 1,54 a 1,94 —a un paso del mínimo— para una zapata cuya resultante está centrada. Ese
    número era falsamente conservador, y este test fija que ya no aparece."""
    caso = _caso(nombre)
    lay = caso.build_layout()
    eje = lay.longitudinal_axis
    clave = "overturning_x" if eje == "X" else "overturning_y"

    for etiqueta, layout in (
        ("directo", lay),
        ("todo_CM", _layout_por_casos(lay, f_cm=1.0, f_cv=0.0)),
        ("60/40", _layout_por_casos(lay, f_cm=0.6, f_cv=0.4)),
    ):
        o = getattr(_resolver(layout, caso).exterior.stability, clave)
        assert o.status is CheckStatus.PASS, etiqueta
        assert o.FS_obtained is None, etiqueta
        assert o.applied_moment_total_kNm == 0.0, etiqueta
        assert o.applied_moment_dead_kNm == 0.0, etiqueta
        assert "No aplicable" in o.pivot_description, etiqueta

    # Y la razón, con números: componente a componente la carga corregida está centrada.
    lay_casos = _layout_por_casos(lay, f_cm=0.6, f_cv=0.4)
    r = _resolver(lay_casos, caso)
    s1 = next(d for d in r.statics if d.combo_type == "SERVICIO")
    pl = lay_casos.exterior.placement_for(r.geometry.exterior_B_m, r.geometry.exterior_L_m)
    offset = pl.offset_x_m if eje == "X" else pl.offset_y_m
    assert offset != 0.0, "La zapata de lindero tiene la columna descentrada"
    for c in s1.exterior_corrected_composition.components:
        m_k = c.Mx_kNm if eje == "X" else c.My_kNm
        escala = abs(m_k) + abs(c.P_kN * offset)
        assert abs(m_k + c.P_kN * offset) <= 1e-9 * escala + 1e-9, (
            f"El componente {c.case_name} no queda centrado: "
            f"M = {m_k:.6f}, P·offset = {c.P_kN * offset:.6f}"
        )


def test_la_estabilizante_es_peso_propio_mas_componentes_muertas():
    """Reconstrucción: N = W_zapata + Σ P de componentes CM (columna y motor) + Σ P negativos
    de las demás.

    El caso es de CUERPO_RIGIDO porque desde FORMULACION_VOLTEO es donde la zapata de lindero
    conserva demanda de volcamiento y, con ella, una N que leer: en los modelos ARTICULADO la
    carga corregida queda centrada y la verificación no llega a ejecutarse."""
    caso = _caso("Z14_cuerpo_rigido_con_momento_de_columna")
    lay = _layout_por_casos(caso.build_layout(), f_cm=0.6, f_cv=0.4)
    r = _resolver(lay, caso)
    s1 = next(d for d in r.statics if d.combo_name == "S1")
    comp = s1.exterior_corrected_composition.components
    W = r.exterior.self_weight.W_total_kN
    N = W + sum(c.P_kN for c in comp if c.kind == "CM") + sum(c.P_kN for c in comp if c.kind != "CM" and c.P_kN < 0)
    assert r.exterior.stability.overturning_x.N_total_kN == pytest.approx(N, rel=1e-12)


def test_modo_directo_sin_composicion_sigue_no_verificado():
    """No regresión: combinaciones directas → sin composición, sin nota de 10C, NO VERIFICADO.

    El caso es de CUERPO_RIGIDO porque desde FORMULACION_VOLTEO es donde el volcamiento de la
    zapata de lindero conserva demanda: en los modelos ARTICULADO la carga corregida queda
    centrada y la verificación no llega a ejecutarse. Lo que se fija aquí es lo de siempre —sin
    composición, un cumplimiento no puede afirmarse—, sobre un caso donde hay algo que
    afirmar."""
    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    cl = _corregidas(caso.build_layout(), caso)
    for combos, comps in _todas(cl):
        assert all(c.composition is None for c in combos)
        assert all(c is None for c in comps)
    for d in cl.distributions:
        assert REDISTRIBUTED_COMPOSITION_NOTE not in d.hypotheses
    r = _resolver(caso.build_layout(), caso)
    assert r.exterior.stability.overturning_x.status is CheckStatus.NOT_VERIFIED
    assert r.interior.stability.overturning_x.status is CheckStatus.NOT_VERIFIED


# =========================================================================
# 6. Negativos
# =========================================================================


def test_modos_mezclados_entre_columnas_se_rechazan():
    caso = _caso("Z1_articulado_equilibrio")
    lay = caso.build_layout()
    mixto = lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": _a_casos(lay.exterior.loads)}),
    })
    with pytest.raises(ValueError, match="mismo modo de cargas"):
        _corregidas(mixto, caso)


def test_si_la_suma_no_cierra_se_detiene():
    """La guarda de linealidad: una carga corregida que no coincide con la suma de sus
    componentes detiene el cálculo en vez de publicar una composición falsa."""
    caso = _caso("Z1_articulado_equilibrio")
    lay = _layout_por_casos(caso.build_layout())
    fp = _footprints(lay, caso.geometry)
    ce, ci = lay.exterior.loads.service[0], lay.interior.loads.service[0]
    d = distribute_couple(lay, fp, ce, ci, caso.soil, GAMMA_C)
    alterada = d.model_copy(update={"P_ext_corrected_kN": d.P_ext_corrected_kN + 1.0})
    with pytest.raises(ValueError, match="dejó de ser"):
        redistributed_compositions(lay, fp, ce, ci, alterada, caso.soil, GAMMA_C)


# =========================================================================
# 7. D10C-1 — peso propio de las zapatas (concreto + relleno) como CM en el reparto rígido
# =========================================================================


def _rigido_a_mano(Pe, Pi, geo, a, S, Df, f, M_col, gc, gs):
    """Cuerpo rígido escrito de nuevo, sin funciones del motor. Huella exterior [0, B_e] ancho
    L_e; interior centrada en a + S. Peso de cada zapata = f·(γc·h + γs·max(Df − h, 0))·área."""
    Be, Le, he = geo.exterior_B_m, geo.exterior_L_m, geo.exterior_h_m
    Bi, Li, hi = geo.interior_B_m, geo.interior_L_m, geo.interior_h_m
    xe, xi = Be / 2.0, a + S
    Ae, Ai = Be * Le, Bi * Li
    We = f * Ae * (gc * he + gs * max(Df - he, 0.0))
    Wi = f * Ai * (gc * hi + gs * max(Df - hi, 0.0))
    A = Ae + Ai
    xc = (Ae * xe + Ai * xi) / A
    I = Le * Be ** 3 / 12 + Ae * (xe - xc) ** 2 + Li * Bi ** 3 / 12 + Ai * (xi - xc) ** 2
    cargas = [(a, Pe), (xi, Pi), (xe, We), (xi, Wi)]
    P = sum(q for _, q in cargas)
    Mc = sum(q * (x - xc) for x, q in cargas) + M_col
    Re = Ae * (P / A + Mc * (xe - xc) / I)
    Ri = Ai * (P / A + Mc * (xi - xc) / I)
    return Re - We, Ri - Wi, We, Wi


@pytest.mark.parametrize("nombre,h_int,esperado_ext", [
    # Valores del análisis D10C-1, opción A (1,4 sobre concreto y relleno).
    ("Z3_cuerpo_rigido_equilibrio", 0.60, 1476.227),
    ("Z12_aragon_p2_cuerpo_rigido", 0.90, 1519.126),
    ("Z3_cuerpo_rigido_equilibrio", None, 1476.535),   # espesores iguales: el peso no redistribuye
])
def test_peso_de_zapatas_con_fcm_contra_cuerpo_rigido_a_mano(nombre, h_int, esperado_ext):
    caso = _caso(nombre)
    geo = caso.geometry if h_int is None else caso.geometry.model_copy(update={"interior_h_m": h_int})
    lay = _layout_por_casos(caso.build_layout())
    cl = correct_loads(lay, _footprints(lay, geo), caso.soil, GAMMA_C)
    a = lay.exterior.anchor.axis_distance_to_column_center_m(lay.exterior.column)
    for d in cl.distributions:
        f = 1.4 if d.combo_type == FACT.value else 1.0
        Pe, Pi, We, Wi = _rigido_a_mano(
            d.P_ext_kN, d.P_int_kN, geo, a, lay.axis_distance_m, caso.soil.Df_m, f,
            d.M_ext_kNm + d.M_int_kNm, GAMMA_C, caso.soil.gamma_kNm3,
        )
        assert d.P_ext_corrected_kN == pytest.approx(Pe, rel=1e-12)
        assert d.P_int_corrected_kN == pytest.approx(Pi, rel=1e-12)
        assert (d.W_ext_kN, d.W_int_kN) == (pytest.approx(We, rel=1e-12), pytest.approx(Wi, rel=1e-12))
        # Sin doble factorización: el reparto conserva la carga de las columnas (DESPRECIADO).
        assert d.P_ext_corrected_kN + d.P_int_corrected_kN == pytest.approx(d.P_ext_kN + d.P_int_kN, rel=1e-12)
        if f == 1.4:
            assert d.P_ext_corrected_kN == pytest.approx(esperado_ext, abs=5e-4)


def test_la_clasificacion_cm_del_peso_de_zapatas_queda_trazada():
    from engine.analysis.connected_statics import FOOTING_WEIGHT_CM_NOTE

    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    cl = _corregidas(_layout_por_casos(caso.build_layout()), caso)
    marca = FOOTING_WEIGHT_CM_NOTE.split("{")[0]
    for d in cl.distributions:
        assert any(h.startswith(marca) for h in d.hypotheses) is (d.combo_type == FACT.value)


def test_modo_directo_el_peso_de_zapatas_sigue_sin_factor():
    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    lay = caso.build_layout()
    directo = _corregidas(lay, caso)
    por_casos = _corregidas(_layout_por_casos(lay), caso)
    u_d = next(d for d in directo.distributions if d.combo_name == "U1")
    u_c = next(d for d in por_casos.distributions if d.combo_name == "U1")
    assert u_c.W_ext_kN == pytest.approx(1.4 * u_d.W_ext_kN, rel=1e-12)
    s_d = next(d for d in directo.distributions if d.combo_name == "S1")
    s_c = next(d for d in por_casos.distributions if d.combo_name == "S1")
    assert s_c.W_ext_kN == s_d.W_ext_kN


def test_factorizada_sin_cm_anula_el_peso_de_zapatas_y_factores_distintos_se_rechazan():
    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    lay = caso.build_layout()

    def cargas(loads, fu):
        s = loads.service[0]
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=0.6 * s.P_kN),
                 LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=0.4 * s.P_kN)]
        return derive_load_case_set(casos, [
            CombinationDefinition(name="S1", type=SERV, factors={"CM": 1.0, "CV": 1.0}),
            CombinationDefinition(name="U1", type=FACT, factors=fu),
        ])

    def con(fu_ext, fu_int):
        return lay.model_copy(update={
            "exterior": lay.exterior.model_copy(update={"loads": cargas(lay.exterior.loads, fu_ext)}),
            "interior": lay.interior.model_copy(update={"loads": cargas(lay.interior.loads, fu_int)}),
        })

    u = next(d for d in _corregidas(con({"CV": 1.7}, {"CV": 1.7}), caso).distributions if d.combo_name == "U1")
    assert u.W_ext_kN == 0.0 and u.W_int_kN == 0.0
    with pytest.raises(ValueError, match="misma"):
        _corregidas(con({"CM": 1.4, "CV": 1.7}, {"CM": 1.2, "CV": 1.7}), caso)


def test_la_viga_del_cuerpo_rigido_sigue_cerrando_con_el_peso_factorizado():
    """La estática de la viga rígida toma W_ext del reparto: con el peso factorizado su campo
    de presión y su momento en el corte siguen siendo los del reparto."""
    from engine.analysis.connecting_beam_statics import solve_connecting_beam

    caso = _caso("Z3_cuerpo_rigido_equilibrio")
    geo = caso.geometry.model_copy(update={"interior_h_m": 0.60})
    lay = _layout_por_casos(caso.build_layout())
    fp = _footprints(lay, geo)
    for d in correct_loads(lay, fp, caso.soil, GAMMA_C).distributions:
        assert solve_connecting_beam(lay, d, fp).cut_moment_consistent


# =========================================================================
# 8. D10C-2 — reducción sísmica 0,8 en las presiones de suelo de cada zapata
# =========================================================================


def _sismico(nombre, f_cs, cs, directo=False):
    """Casos CM/CV/CS; S2 = CM + CV + f_cs·CS (CS a nivel de resistencia)."""
    caso = _caso(nombre)
    lay = caso.build_layout()
    P_e, M_e, P_i, M_i = cs

    def conv(loads, P_cs, M_cs):
        s = loads.service[0]
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=0.7 * s.P_kN, Mx_kNm=0.7 * s.Mx_kNm),
                 LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=0.3 * s.P_kN, Mx_kNm=0.3 * s.Mx_kNm),
                 LoadCase(name="CSx", kind=LoadCaseKind.CS, level=ActionLevel.RESISTENCIA, P_kN=P_cs, Mx_kNm=M_cs)]
        cs_ = derive_load_case_set(casos, [
            CombinationDefinition(name="S1", type=SERV, factors={"CM": 1, "CV": 1}),
            CombinationDefinition(name="S2", type=SERV, factors={"CM": 1, "CV": 1, "CSx": f_cs}),
            CombinationDefinition(name="U1", type=FACT, factors={"CM": 1.4, "CV": 1.7}),
            CombinationDefinition(name="U2", type=FACT, factors={"CM": 1.25, "CV": 1.25, "CSx": 1.0}),
        ])
        if directo:
            cs_ = cs_.model_copy(update={
                "service": [c.model_copy(update={"composition": None}) for c in cs_.service],
                "factored": [c.model_copy(update={"composition": None}) for c in cs_.factored],
            })
        return cs_

    return caso, lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": conv(lay.exterior.loads, P_e, M_e)}),
        "interior": lay.interior.model_copy(update={"loads": conv(lay.interior.loads, P_i, M_i)}),
    })


def _resolver_suelo(caso, lay, reduccion):
    suelo = caso.soil.model_copy(update={"allow_seismic_reduction_80pct": reduccion})
    return solve_connected_footing(
        lay, caso.geometry, soil=suelo, concrete=caso.concrete, steel=caso.steel,
        code=E060ConcreteCode(), contact_model=KernCheckModel(), depth_params=caso.depth_params,
    )


CS_MODERADO = (-120.0, 250.0, 120.0, 180.0)
_PRESION = ("contact_pressure", "eccentricity_governing", "traza[contact_pressure]")


def _es_de_presion(clave: str) -> bool:
    return clave.startswith(_PRESION)


@pytest.mark.parametrize("nombre,q_int_esperada", [
    ("Z1_articulado_equilibrio", 346.265),
    ("Z3_cuerpo_rigido_equilibrio", 283.380),
])
def test_presiones_por_zapata_con_reduccion_igual_a_repartir_08_cs(nombre, q_int_esperada):
    """Reducir las componentes CS de las cargas corregidas equivale a repartir 0,8·CS: las
    presiones de contacto de cada zapata son las mismas."""
    from tests.freeze.snapshot import snapshot_candidate

    caso, lay = _sismico(nombre, 1.0, CS_MODERADO)
    _, lay08 = _sismico(nombre, 0.8, CS_MODERADO)
    reducido = _resolver_suelo(caso, lay, True)
    referencia = _resolver_suelo(caso, lay08, False)
    for lado in ("exterior", "interior"):
        a = snapshot_candidate(getattr(reducido, lado))["numeros"]
        b = snapshot_candidate(getattr(referencia, lado))["numeros"]
        claves = [k for k in a if _es_de_presion(k)]
        assert claves
        for k in claves:
            assert a[k] == pytest.approx(b[k], rel=1e-9, abs=1e-9), k
    assert reducido.interior.contact_pressure.qmax_kPa == pytest.approx(q_int_esperada, abs=5e-4)
    sin = _resolver_suelo(caso, lay, False)
    assert sin.interior.contact_pressure.qmax_kPa > reducido.interior.contact_pressure.qmax_kPa


def test_la_reduccion_no_toca_estabilidad_diseno_ni_reparto():
    """Con y sin la opción de reducción: todo lo que no es presión de suelo es idéntico
    (estabilidad con fuerzas sin reducir, E.030 art. 64.2; diseño factorizado; reparto)."""
    from tests.freeze.snapshot import snapshot_candidate, snapshot_connected

    caso, lay = _sismico("Z3_cuerpo_rigido_equilibrio", 1.0, CS_MODERADO)
    con, sin = _resolver_suelo(caso, lay, True), _resolver_suelo(caso, lay, False)
    for lado in ("exterior", "interior"):
        a = snapshot_candidate(getattr(con, lado))["numeros"]
        b = snapshot_candidate(getattr(sin, lado))["numeros"]
        otras = [k for k in a if not _es_de_presion(k)]
        assert any(k.startswith("stability") for k in otras) and any(k.startswith("punching") for k in otras)
        assert {k: a[k] for k in otras} == {k: b[k] for k in otras}
    sa, sb = snapshot_connected(con), snapshot_connected(sin)
    for clave in sa["numeros"]:
        if clave.startswith(("statics", "beam_statics", "beam.")):
            assert sa["numeros"][clave] == sb["numeros"][clave], clave


def test_el_despegue_del_sistema_se_verifica_sin_reducir():
    """Con M_CS grande el sistema rígido despega con CS completo (σ_min < 0) y no con 0,8·CS.
    La reducción es solo para las presiones de cada zapata: el candidato sigue rechazado."""
    cs = (-300.0, 1600.0, 300.0, 1200.0)
    caso, lay = _sismico("Z3_cuerpo_rigido_equilibrio", 1.0, cs)
    _, lay08 = _sismico("Z3_cuerpo_rigido_equilibrio", 0.8, cs)
    s2 = lambda cl: next(d for d in cl.distributions if d.combo_name == "S2")
    assert s2(_corregidas(lay, caso)).uplift
    assert not s2(_corregidas(lay08, caso)).uplift
    with pytest.raises(ValueError, match="DESPEGUE"):
        _resolver_suelo(caso, lay, True)


def test_soil_actions_reduce_las_componentes_cs_de_la_carga_corregida():
    caso, lay = _sismico("Z1_articulado_equilibrio", 1.0, CS_MODERADO)
    s2 = next(c for c in _corregidas(lay, caso).interior.service if c.name == "S2")
    assert s2.composition.redistributed
    suelo = caso.soil.model_copy(update={"allow_seismic_reduction_80pct": True})
    notas: list[str] = []
    P, Mx, _ = soil_actions(s2, suelo, notas)
    cs_P = s2.composition.total("P_kN", {"CS"}, "RESISTENCIA")
    cs_M = s2.composition.total("Mx_kNm", {"CS"}, "RESISTENCIA")
    assert P == pytest.approx(s2.P_kN - 0.2 * cs_P, rel=1e-12)
    assert Mx == pytest.approx(s2.Mx_kNm - 0.2 * cs_M, rel=1e-12)
    assert any("D10C-2" in n for n in notas)


def test_modo_directo_la_reduccion_no_se_aplica_en_la_conectada():
    from tests.freeze.snapshot import snapshot_connected

    caso, lay = _sismico("Z1_articulado_equilibrio", 1.0, CS_MODERADO, directo=True)
    assert all(c.composition is None for c in lay.exterior.loads.service)
    con = snapshot_connected(_resolver_suelo(caso, lay, True))
    sin = snapshot_connected(_resolver_suelo(caso, lay, False))

    # Con combinaciones directas la opción solo añade la limitación INFO que ya existía (no se
    # conoce la componente sísmica); ningún número ni estado de ingeniería cambia.
    def sin_limitacion(d):
        return {k: v for k, v in d.items() if "limitation_seismic_reduction_80pct" not in k and k != "traza.orden"}

    for sec in ("numeros", "estados", "referencias"):
        assert sin_limitacion(con[sec]) == sin_limitacion(sin[sec])
    assert any("limitation_seismic_reduction_80pct" in k for k in con["estados"])


def test_una_zapata_puede_recibir_mas_carga_al_reducir_la_accion():
    """La norma reduce la ACCIÓN, no su efecto: en Z1 el sismo alivia la zapata exterior en S2,
    y con 0,8·CS esa zapata recibe más carga (786,7 → 823,6 kN)."""
    caso, lay = _sismico("Z1_articulado_equilibrio", 1.0, CS_MODERADO)
    s2 = next(c for c in _corregidas(lay, caso).exterior.service if c.name == "S2")
    suelo = caso.soil.model_copy(update={"allow_seismic_reduction_80pct": True})
    P, _, _ = soil_actions(s2, suelo, [])
    assert s2.P_kN == pytest.approx(786.667, abs=5e-4)
    assert P == pytest.approx(823.619, abs=5e-4)


# =========================================================================
# 7. Trazabilidad en el informe
# =========================================================================


def test_el_informe_muestra_la_composicion_solo_en_modo_por_casos():
    from engine.optimization.connected_generator import ConnectedAlternative, ConnectedAlternativeSet
    from engine.optimization.connected_metrics import compute_connected_metrics
    from engine.reports.connected_report import render_connected_report_html

    caso = _caso("Z8_peso_propio_de_viga_explicito")
    html = {}
    for modo, lay in (("directo", caso.build_layout()), ("casos", _layout_por_casos(caso.build_layout(), f_cm=1.0, f_cv=0.0))):
        r = _resolver(lay, caso)
        alt = ConnectedAlternative(id="A1", geometry=caso.geometry, result=r,
                                   metrics=compute_connected_metrics(r, caso.soil.Df_m, 0.075))
        conjunto = ConnectedAlternativeSet(accepted=[alt], evaluated_count=1)
        html[modo] = render_connected_report_html(conjunto)
    assert "Composición de las cargas corregidas" in html["casos"]
    assert ENGINE_BEAM_WEIGHT_CASE in html["casos"]
    assert "Composición de las cargas corregidas" not in html["directo"]
