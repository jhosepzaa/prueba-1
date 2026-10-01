"""FASE 2 — Solver de zapata combinada.

QUÉ SE VERIFICA
===============
1. El modelo de datos rechaza lo que no describe una estructura real.
2. La dirección longitudinal se decide por la SEPARACIÓN de las columnas, no por
   cuál dimensión de la zapata sea mayor.
3. El acero superior es una CARA distinta, con su recubrimiento y su peralte
   efectivo propios — no una capa de la parrilla de abajo.
4. El recubrimiento superior no se supone: hay que declararlo.
5. El acero mínimo de dos caras sigue §10.5.4, y el reparto del resto queda
   marcado como criterio.
6. El punzonamiento por columna reutiliza la Fase 1C, incluida la clasificación
   de borde para la columna de límite de propiedad.
7. E.050 art. 23.3: L <= 10 B.
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import (
    TRANSVERSE_STRIP_NOTE,
    solve_combined_footing,
)
from engine.reinforcement.face_reinforcement import (
    RHO_MIN_TENSION_FACE_TWO_FACES,
    TopCoverDeclaration,
    two_face_minimum,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel

CODE = E060ConcreteCode()
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
B_LONG, L_ANCHO, H = 8.0, 3.60, 0.80
TAPA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")


def _col(label: str, x_desde_extremo: float, P: float, M: float = 0.0, L_total: float = B_LONG):
    return ColumnOnFooting(
        label=label,
        placement=ColumnPlacement(column=COL, offset_x_m=x_desde_extremo - L_total / 2.0),
        loads=LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P, Mx_kNm=M)],
            factored=[
                LoadCombination(
                    name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4, Mx_kNm=M * 1.4
                )
            ],
        ),
    )


def _layout(**kw) -> CombinedFootingLayout:
    return CombinedFootingLayout(
        B_m=kw.get("B", B_LONG), L_m=kw.get("L", L_ANCHO),
        columns=kw.get("columns", [_col("C1", 1.0, 900.0), _col("C2", 7.0, 900.0)]),
    )


def _resolver(layout=None, h=H, tapa=TAPA, qadm=400.0):
    return solve_combined_footing(
        layout or _layout(), h,
        soil=SoilProfile(
            qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50,
            source_notes="prueba",
        ),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(), top_cover=tapa,
    )


# =========================================================================
# 1. Modelo de datos
# =========================================================================

def test_hacen_falta_al_menos_dos_columnas():
    with pytest.raises(ValueError):
        CombinedFootingLayout(B_m=8.0, L_m=3.0, columns=[_col("C1", 4.0, 900.0)])


def test_las_etiquetas_deben_ser_unicas():
    with pytest.raises(ValueError, match="únicas"):
        _layout(columns=[_col("C1", 1.0, 900.0), _col("C1", 7.0, 900.0)])


def test_dos_columnas_en_la_misma_posicion_es_un_error():
    with pytest.raises(ValueError, match="misma posición"):
        _layout(columns=[_col("C1", 4.0, 900.0), _col("C2", 4.0, 900.0)])


def test_una_columna_fuera_de_la_zapata_es_un_error():
    with pytest.raises(ValueError, match="no cabe dentro"):
        _layout(columns=[_col("C1", 1.0, 900.0), _col("C2", 9.5, 900.0)])


def test_todas_las_columnas_deben_declarar_las_mismas_combinaciones():
    """Una combinación que exista en una columna y no en otra no describe ningún
    estado de carga del conjunto."""
    c2 = _col("C2", 7.0, 900.0)
    c2.loads.factored[0].name = "OTRA"
    with pytest.raises(ValueError, match="mismas combinaciones"):
        _layout(columns=[_col("C1", 1.0, 900.0), c2])


# =========================================================================
# 2. Dirección longitudinal
# =========================================================================

def test_la_direccion_longitudinal_la_da_la_separacion_no_la_dimension_mayor():
    """Zapata MÁS ANCHA que larga, con las columnas alineadas a lo largo del lado
    CORTO. La dirección de análisis debe seguir a las columnas."""
    ancha = CombinedFootingLayout(
        B_m=3.0, L_m=9.0,
        columns=[
            ColumnOnFooting(
                label=f"C{i}", placement=ColumnPlacement(column=COL, offset_x_m=dx),
                loads=LoadCaseSet(
                    service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=800.0)],
                    factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=1120.0)],
                ),
            )
            for i, dx in ((1, -1.0), (2, 1.0))
        ],
    )
    # Las columnas están separadas en X aunque L (9,0) sea mucho mayor que B (3,0).
    assert ancha.longitudinal_direction == "X"
    assert ancha.longitudinal_length_m == pytest.approx(3.0)


def test_la_posicion_longitudinal_se_mide_desde_el_extremo():
    lay = _layout()
    assert lay.longitudinal_position_m(lay.columns[0]) == pytest.approx(1.0)
    assert lay.longitudinal_position_m(lay.columns[1]) == pytest.approx(7.0)


# =========================================================================
# 3. Cara superior: concepto propio, no una capa de la parrilla inferior
# =========================================================================

def test_el_peralte_de_la_cara_superior_usa_su_propio_recubrimiento():
    """Es el error que este concepto existe para impedir: si la cara superior
    heredara el recubrimiento de 75 mm de la inferior, su peralte efectivo saldría
    equivocado."""
    r = _resolver()
    assert r.d_top_m != pytest.approx(r.d_bottom_m)
    # 40 mm arriba frente a 75 abajo -> la cara superior tiene MÁS peralte efectivo.
    assert r.d_top_m > r.d_bottom_m
    assert r.d_top_m == pytest.approx(H - 0.040 - 0.008)
    assert r.d_bottom_m == pytest.approx(H - 0.075 - 0.008)


def test_hay_acero_superior_cuando_el_diagrama_da_momento_negativo():
    r = _resolver()
    assert r.diagram.has_negative_moment
    assert r.top_face is not None
    assert r.top_face.face == "superior"
    assert r.top_face.As_design_m2 > 0


def test_sin_momento_negativo_no_se_disena_acero_superior_por_flexion():
    """Voladizos largos: el momento negativo se anula. La traza debe decir que la
    cara superior no trabaja a flexión, sin callar que §9.7 sigue aplicando."""
    lay = _layout(columns=[_col("C1", 2.0, 900.0), _col("C2", 6.0, 900.0)])
    r = _resolver(lay)
    assert not r.diagram.has_negative_moment
    assert r.top_face is None
    entrada = r.trace.by_id("flexure_top")
    assert entrada.status is CheckStatus.INFO
    assert "§9.7" in " ".join(entrada.hypotheses)


# =========================================================================
# 4. El recubrimiento superior se declara, no se supone
# =========================================================================

def test_no_declarar_el_recubrimiento_superior_es_un_error():
    with pytest.raises(ValueError, match="no da un valor único"):
        _resolver(tapa=TopCoverDeclaration())


@pytest.mark.parametrize(
    "caso, mm",
    [
        ("contacto_suelo_barras_pequenas", 40.0),
        ("contacto_suelo_barras_grandes", 50.0),
        ("no_expuesto", 20.0),
        ("vaciado_contra_suelo", 75.0),
    ],
)
def test_cada_caso_de_la_tabla_de_7_7_1_da_su_valor(caso, mm):
    r = _resolver(tapa=TopCoverDeclaration(case=caso))
    assert r.d_top_m == pytest.approx(H - mm / 1000.0 - 0.008)


def test_el_recubrimiento_adoptado_queda_en_la_traza():
    entrada = _resolver().trace.by_id("top_cover")
    assert entrada is not None
    assert "§7.7.1" in entrada.code_reference
    assert "declarado por el proyectista" in " ".join(entrada.hypotheses)


def test_un_valor_explicito_manda_sobre_el_caso():
    r = _resolver(tapa=TopCoverDeclaration(case="no_expuesto", explicit_mm=55.0))
    assert r.d_top_m == pytest.approx(H - 0.055 - 0.008)


# =========================================================================
# 5. Acero mínimo de dos caras — §10.5.4
# =========================================================================

def test_el_minimo_de_la_cara_traccionada_es_el_de_10_5_4():
    assert RHO_MIN_TENSION_FACE_TWO_FACES == 0.0012
    m = two_face_minimum(3.60, 0.80, 0.0018, "E.060 §9.7")
    assert m.As_min_tension_face_m2 == pytest.approx(0.0012 * 3.60 * 0.80)
    assert m.As_min_total_m2 == pytest.approx(0.0018 * 3.60 * 0.80)


def test_el_reparto_del_resto_esta_marcado_como_criterio():
    """§10.5.4 fija el total y el mínimo de la cara traccionada, pero no dice cómo
    repartir el resto. Repartirlo por igual es decisión de este motor y debe leerse
    como tal."""
    m = two_face_minimum(3.60, 0.80, 0.0018, "E.060 §9.7")
    _, ref = m.for_face(is_tension_face=False)
    assert "CRITERIO" in ref


def test_el_minimo_gobierna_cuando_la_flexion_pide_menos():
    r = _resolver()
    cara = r.bottom_face
    if cara.As_required_m2 < cara.As_min_m2:
        assert cara.As_design_m2 == pytest.approx(cara.As_min_m2)
        assert "10.5.4" in cara.min_governed_by or "9.7" in cara.min_governed_by


# =========================================================================
# 6. Punzonamiento por columna — reutiliza la Fase 1C
# =========================================================================

def test_hay_una_verificacion_de_punzonamiento_por_columna():
    r = _resolver()
    assert len(r.punching) == 2
    for col in r.trace.entries:
        pass
    assert r.trace.by_id("punching_C1") is not None
    assert r.trace.by_id("punching_C2") is not None


def test_la_columna_en_limite_de_propiedad_se_clasifica_de_borde():
    """Es la integración con la Fase 1C: la columna al ras del borde debe dar
    sección crítica de 3 lados, sin que el solver de combinada haga nada especial."""
    al_ras = COL.bx_m / 2.0
    lay = _layout(columns=[_col("C1", al_ras, 900.0), _col("C2", 6.5, 1800.0)])
    r = _resolver(lay)
    borde = r.punching[0]
    assert borde.column_position == "borde"
    assert borde.critical_section_sides == 3
    assert borde.alpha_s == 30.0


# =========================================================================
# 7. E.050 art. 23.3 — proporción
# =========================================================================

def test_una_proporcion_admisible_pasa():
    r = _resolver()
    assert r.shape_ok
    assert r.trace.by_id("shape_ratio").status is CheckStatus.PASS


def test_una_proporcion_mayor_que_diez_se_descarta():
    """Por encima de 10 la propia E.050 la clasifica como cimentación continua."""
    lay = _layout(B=12.0, L=1.0, columns=[_col("C1", 1.5, 500.0, L_total=12.0),
                                          _col("C2", 10.5, 500.0, L_total=12.0)])
    r = _resolver(lay)
    assert not r.shape_ok
    assert r.trace.by_id("shape_ratio").status is CheckStatus.FAIL
    assert any("continua" in m for m in r.discard_reasons)


# =========================================================================
# 8. Franjas transversales — criterio declarado
# =========================================================================

def test_hay_una_franja_transversal_por_columna_y_su_ancho_es_criterio():
    r = _resolver()
    assert len(r.transverse_strips) == 2
    for s in r.transverse_strips:
        assert "CRITERIO DE MODELACIÓN" in s.criterion_note
        assert "NO una exigencia normativa" in s.criterion_note


def test_el_ancho_de_franja_es_columna_mas_medio_peralte_a_cada_lado():
    r = _resolver()
    esperado = COL.by_m + 2.0 * 0.5 * r.d_bottom_m
    assert r.transverse_strips[0].strip_width_m == pytest.approx(esperado)


def test_la_traza_de_la_franja_declara_que_el_ancho_no_es_normativo():
    entrada = _resolver().trace.by_id("transverse_strip_C1")
    assert "CRITERIO" in entrada.code_reference
    assert TRANSVERSE_STRIP_NOTE in entrada.hypotheses


# =========================================================================
# 9. Coherencia general
# =========================================================================

def test_el_cortante_sale_del_diagrama_y_no_de_una_formula_de_voladizo():
    r = _resolver()
    assert r.shear_longitudinal.Vu_kN == pytest.approx(r.diagram.V_max_abs_kN)
    entrada = r.trace.by_id("shear_longitudinal")
    assert "no es monótono" in " ".join(entrada.hypotheses)


def test_la_traza_declara_el_metodo_del_diagrama_y_su_base_normativa():
    entrada = _resolver().trace.by_id("beam_diagram")
    assert "§15.4.1" in entrada.code_reference
    assert "§15.10.1" in entrada.code_reference
    assert any("linealidad" in h or "lineal" in h for h in entrada.hypotheses)


def test_la_presion_de_contacto_usa_la_resultante_de_todas_las_columnas():
    """Con dos columnas iguales y simétricas la resultante cae en el centroide y la
    presión sale uniforme."""
    r = _resolver()
    assert r.contact_pressure.qmax_kPa == pytest.approx(r.contact_pressure.qmin_kPa, rel=1e-6)


def test_cargas_asimetricas_inclinan_la_presion():
    lay = _layout(columns=[_col("C1", 1.0, 500.0), _col("C2", 7.0, 1500.0)])
    r = _resolver(lay)
    assert r.contact_pressure.qmax_kPa > r.contact_pressure.qmin_kPa


# =========================================================================
# 10. Benchmark: Aragón «Concreto Armado 2» §3.5
# =========================================================================

TONF_TO_KN = 9.80665


def _aragon_3_5():
    """Zapata combinada 7,20 x 3,80 x 0,80 m, dos columnas 50x50, la primera en
    límite de propiedad. Datos del libro."""
    Lz, Bz = 7.20, 3.80

    def mk(lbl, x, Pcm, Pcv, M):
        return ColumnOnFooting(
            label=lbl,
            placement=ColumnPlacement(column=COL, offset_x_m=x - Lz / 2.0),
            loads=LoadCaseSet(
                service=[LoadCombination(
                    name="CM+CV", type=LoadCombinationType.SERVICIO,
                    P_kN=(Pcm + Pcv) * TONF_TO_KN, Mx_kNm=M * TONF_TO_KN)],
                factored=[LoadCombination(
                    name="1.4CM+1.7CV", type=LoadCombinationType.FACTORIZADA,
                    P_kN=(1.4 * Pcm + 1.7 * Pcv) * TONF_TO_KN, Mx_kNm=M * 1.5 * TONF_TO_KN)],
            ),
        )

    return CombinedFootingLayout(
        B_m=Lz, L_m=Bz,
        columns=[mk("C1", 0.25, 80, 30, 8.5), mk("C2", 5.25, 160, 60, -2.5)],
    )


def test_aragon_3_5_reproduce_la_resultante_del_libro():
    """El libro sitúa la resultante en x = 3,60 m con
        0,25(110) + 5,25(220) + 8,5 − 2,5 = X(330)
    incluyendo los momentos aplicados."""
    lay = _aragon_3_5()
    esperado = (110 * 0.25 + 220 * 5.25 + 8.5 - 2.5) / 330
    assert esperado == pytest.approx(3.60, abs=0.01)

    P = sum(c.loads.service[0].P_kN for c in lay.columns)
    M = sum(
        c.loads.service[0].Mx_kNm + c.loads.service[0].P_kN * c.offset_x_m for c in lay.columns
    )
    x_desde_extremo = lay.longitudinal_length_m / 2.0 + M / P
    assert x_desde_extremo == pytest.approx(esperado, rel=1e-6)


def test_aragon_3_5_la_columna_de_lindero_se_resuelve_como_de_borde():
    r = _resolver(_aragon_3_5(), h=0.80, qadm=1.5 * 98.0665)
    c1 = next(p for p, c in zip(r.punching, r.trace.entries) if True)
    assert r.punching[0].column_position == "borde"
    assert r.punching[1].column_position == "interior"


def test_aragon_3_5_la_diferencia_de_presion_es_solo_el_peso_propio():
    """El libro estima el peso propio como el 10% de (CM+CV) —33 t— y NO incluye el
    relleno de suelo sobre la zapata. El motor calcula 53,6 t de concreto más 35,2 t
    de relleno. La diferencia de presión debe explicarse íntegramente por eso: si
    saliera otra cosa, habría un error de modelo, no de metodología."""
    r = _resolver(_aragon_3_5(), h=0.80, qadm=1.5 * 98.0665)
    q_motor = r.contact_pressure.qmax_kPa / 98.0665
    q_libro = 363.0 / (7.20 * 3.80) / 10.0  # t/m2 -> kg/cm2

    P_columnas = 330.0
    pp_libro = 33.0
    pp_motor = (7.20 * 3.80 * 0.80 * 24.0 + (1.50 - 0.80) * 7.20 * 3.80 * 18.0) / TONF_TO_KN
    esperado = q_libro * (P_columnas + pp_motor) / (P_columnas + pp_libro)
    assert q_motor == pytest.approx(esperado, rel=0.01)


def test_aragon_3_5_produce_momento_negativo_y_por_tanto_acero_superior():
    """Es la razón de ser de la zapata combinada frente a dos aisladas."""
    r = _resolver(_aragon_3_5(), h=0.80, qadm=1.5 * 98.0665)
    assert r.diagram.has_negative_moment
    assert r.top_face is not None
    assert r.top_face.Mu_kNm > r.bottom_face.Mu_kNm, (
        "En esta geometría el momento negativo supera al positivo, que es lo que hace "
        "indispensable la cara superior."
    )


# =========================================================================
# 11. Predimensionamiento y generación de alternativas
# =========================================================================

from engine.analysis.beam_diagram import length_to_center_resultant  # noqa: E402
from engine.optimization.combined_generator import (  # noqa: E402
    ColumnSpec,
    CombinedSearchParameters,
    build_layout,
    generate_combined_alternatives,
)


def test_la_longitud_que_centra_la_resultante_reproduce_la_de_aragon():
    """El libro adopta L = 7,20 m para que el centroide coincida con la resultante."""
    r = length_to_center_resultant(
        column_positions_m=[0.0, 5.0],
        column_loads_kN=[110.0, 220.0],
        column_moments_kNm=[8.5, -2.5],
        start_offset_m=0.25,
    )
    assert r.length_m == pytest.approx(7.20, abs=0.01)
    assert r.feasible


def test_centrar_la_resultante_esta_marcado_como_criterio_no_como_norma():
    """Ni E.060 ni E.050 obligan a centrar la resultante: lo que exigen es que no
    haya tracciones y que la presión no supere la admisible."""
    r = length_to_center_resultant([0.0, 6.0], [1000.0, 1000.0], start_offset_m=0.25)
    assert "CRITERIO DE PREDIMENSIONAMIENTO" in r.note
    assert "obligan a centrar" in r.note
    assert "§15.2" in r.note, "Debe decir qué SÍ exige la norma, no solo qué no exige"


def test_con_cargas_simetricas_la_longitud_sale_simetrica():
    r = length_to_center_resultant([0.0, 6.0], [1000.0, 1000.0], start_offset_m=0.25)
    assert r.length_m == pytest.approx(2 * (3.0 + 0.25))


def test_una_disposicion_que_no_permite_centrar_se_declara_infactible():
    """Si casi toda la carga está en la primera columna, la longitud que centraría la
    resultante no llega a cubrir la última."""
    r = length_to_center_resultant([0.0, 10.0], [10000.0, 100.0], start_offset_m=0.25)
    assert not r.feasible
    assert "no alcanza a cubrir" in r.note


def _specs():
    return [
        ColumnSpec(label="C1", column=COL, distance_from_first_m=0.0,
                   loads=_col("C1", 1.0, 1078.0, 83.0).loads),
        ColumnSpec(label="C2", column=COL, distance_from_first_m=5.0,
                   loads=_col("C2", 6.0, 2157.0, -24.5).loads),
    ]


def test_el_barrido_ancla_la_primera_columna_al_borde():
    """Es lo que la Fase 1B dejó pendiente: al variar la longitud, la cara de la
    primera columna debe seguir al ras del lindero, no desplazarse con el centro."""
    for L in (6.8, 7.2, 7.6):
        lay = build_layout(_specs(), length_m=L, width_m=3.8,
                           first_column_edge_distance_m=0.25)
        # La posición de C1 desde el extremo debe ser SIEMPRE 0,25 m.
        assert lay.longitudinal_position_m(lay.columns[0]) == pytest.approx(0.25)
        # Y la separación entre ejes debe mantenerse.
        sep = lay.longitudinal_position_m(lay.columns[1]) - lay.longitudinal_position_m(lay.columns[0])
        assert sep == pytest.approx(5.0)


def test_el_generador_encuentra_alternativas_y_las_ordena_por_volumen():
    r = generate_combined_alternatives(
        _specs(),
        CombinedSearchParameters(
            length_min_m=6.8, length_max_m=7.6, length_step_m=0.20,
            width_min_m=3.6, width_max_m=4.4, width_step_m=0.20,
            h_min_m=0.65, h_max_m=0.90, h_step_m=0.05,
            first_column_edge_distance_m=0.25,
        ),
        soil=SoilProfile(qadm_kPa=1.5 * 98.0665, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA,
    )
    assert r.valid, "Debe encontrar al menos una alternativa viable"
    assert r.evaluated_count > 0
    assert not r.truncated
    # Todas deben clasificar C1 como columna de borde: está al ras del lindero.
    for alt in r.valid:
        assert alt.result.punching[0].column_position == "borde"


def test_un_rango_desmesurado_se_trunca_y_lo_declara():
    """Truncar en silencio haría que «la mejor alternativa» no lo fuera."""
    r = generate_combined_alternatives(
        _specs(),
        CombinedSearchParameters(
            length_min_m=6.0, length_max_m=12.0, length_step_m=0.05,
            width_min_m=3.0, width_max_m=6.0, width_step_m=0.05,
            h_min_m=0.50, h_max_m=1.50, h_step_m=0.05,
            first_column_edge_distance_m=0.25,
        ),
        soil=SoilProfile(qadm_kPa=1.5 * 98.0665, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA,
    )
    assert r.truncated
    assert "NO es una búsqueda exhaustiva" in r.search_note


# =========================================================================
# 12. Armado de las caras
# =========================================================================

def test_cada_cara_recibe_armado_real_no_solo_area():
    r = _resolver()
    assert r.bottom_face.rebar is not None
    assert r.bottom_face.rebar.n_bars > 0
    assert r.bottom_face.rebar.As_provided_m2 >= r.bottom_face.As_design_m2 * 0.99
    if r.top_face is not None:
        assert r.top_face.rebar is not None
        assert r.top_face.rebar.face == "superior"


def test_el_peralte_real_se_recalcula_con_la_barra_seleccionada():
    """Igual que en la zapata aislada: un d calculado con una barra supuesta menor
    que la real queda del lado inseguro."""
    r = _resolver()
    rb = r.bottom_face.rebar
    assert rb.d_real_m == pytest.approx(H - r.bottom_face.cover_m - rb.diameter_mm / 2000.0)


def test_la_separacion_maxima_se_verifica_contra_10_5_4():
    r = _resolver()
    for cara in (r.bottom_face, r.top_face):
        if cara is None:
            continue
        assert cara.rebar.spacing_limit_m == pytest.approx(min(3 * H, 0.400))
        assert "§10.5.4" in cara.rebar.spacing_reference


def test_la_cara_superior_exige_mas_longitud_de_desarrollo_que_la_inferior():
    """E.060 §12.2.4, Tabla 12.2: una barra con 300 mm o más de concreto fresco por
    DEBAJO es «barra superior» y le corresponde psi_t = 1,3. La cara superior de una
    zapata tiene todo el peralte debajo; la inferior, solo su recubrimiento.
    Aplicarle 1,0 a la cara superior subestimaría la longitud exigida."""
    r = _resolver()
    assert r.top_face is not None
    assert r.top_face.rebar.ld_required_m > r.bottom_face.rebar.ld_required_m
    assert "psi_t = 1.3" in r.top_face.rebar.development_note
    assert "psi_t = 1.0" in r.bottom_face.rebar.development_note


def test_el_desarrollo_se_verifica_y_no_queda_en_none():
    """Un campo siempre nulo aparentaría una comprobación no hecha."""
    r = _resolver()
    for cara in (r.bottom_face, r.top_face):
        if cara is None:
            continue
        assert cara.rebar.ld_required_m > 0
        assert cara.rebar.ld_available_m >= 0
        assert isinstance(cara.rebar.development_ok, bool)


def test_un_desarrollo_insuficiente_descarta_con_motivo():
    """Zapata corta: la sección crítica queda tan cerca del extremo que no hay
    longitud para desarrollar la barra."""
    lay = _layout(B=3.2, L=2.0, columns=[_col("C1", 0.30, 400.0, L_total=3.2),
                                         _col("C2", 2.90, 400.0, L_total=3.2)])
    r = _resolver(lay, h=0.45)
    caras = [c for c in (r.bottom_face, r.top_face) if c is not None and c.rebar is not None]
    if any(not c.rebar.development_ok for c in caras):
        assert any("longitud de desarrollo insuficiente" in m for m in r.discard_reasons)


def test_las_franjas_transversales_tambien_traen_armado_real():
    """Devolver solo el área dejaba el diseño a medias: la franja se arma igual que
    cualquier otra sección."""
    r = _resolver()
    for franja in r.transverse_strips:
        assert franja.rebar is not None
        assert franja.rebar.n_bars > 0
        assert franja.rebar.ld_required_m > 0
        assert isinstance(franja.rebar.development_ok, bool)


def test_el_desarrollo_de_la_franja_se_mide_sobre_su_voladizo():
    """La barra transversal arranca en la cara de la columna y llega al borde: lo
    disponible es el voladizo menos el recubrimiento lateral."""
    r = _resolver()
    f = r.transverse_strips[0]
    assert f.rebar.ld_available_m == pytest.approx(
        max(f.cantilever_m - r.bottom_face.cover_m, 0.0)
    )


# =========================================================================
# 13. Puntuación y ordenamiento
# =========================================================================

from engine.optimization.combined_generator import rank_combined_alternatives  # noqa: E402
from engine.optimization.metrics import AlternativeMetrics  # noqa: E402
from engine.optimization.scoring import ScoreWeights, score_metric_sets  # noqa: E402


def test_la_combinada_produce_las_mismas_metricas_que_la_aislada():
    """Mantener el tipo es lo que permite reutilizar scoring, pareto y ranker sin
    tocarlos: el optimizador nunca necesitó conocer la tipología."""
    r = _resolver()
    from engine.optimization.combined_metrics import compute_combined_metrics

    m = compute_combined_metrics(r, Df_m=1.50)
    assert isinstance(m, AlternativeMetrics)
    assert m.concrete_volume_m3 == pytest.approx(r.B_m * r.L_m * r.h_m)
    assert m.steel_mass_kg > 0


def test_armar_dos_caras_penaliza_la_complejidad_constructiva():
    """Es heurística declarada, no ingeniería estructural: armar arriba y abajo es
    constructivamente más costoso que armar solo abajo."""
    from engine.optimization.combined_metrics import compute_combined_metrics

    con_sup = compute_combined_metrics(_resolver(), Df_m=1.50)
    sin_sup_layout = _layout(columns=[_col("C1", 2.0, 900.0), _col("C2", 6.0, 900.0)])
    sin_sup = compute_combined_metrics(_resolver(sin_sup_layout), Df_m=1.50)
    assert sin_sup.constructive_complexity_index < con_sup.constructive_complexity_index


def test_el_nucleo_de_puntuacion_es_el_mismo_para_ambas_tipologias():
    """Si divergieran, dos tipologías se ordenarían con criterios distintos sin que
    nadie lo notara."""
    from engine.optimization.combined_metrics import compute_combined_metrics

    metricas = [compute_combined_metrics(_resolver(), Df_m=1.50)]
    puntuadas = score_metric_sets(metricas, ScoreWeights())
    assert len(puntuadas) == 1
    score, desglose = puntuadas[0]
    assert set(desglose) == {
        "volumen_concreto", "masa_acero", "dimension_maxima", "complejidad_constructiva"
    }
    # Con una sola alternativa la normalización min-max da 0 en todo.
    assert score == pytest.approx(0.0)


def test_el_ordenamiento_es_determinista():
    """Dos alternativas con la misma puntuación deben salir siempre igual."""
    r = generate_combined_alternatives(
        _specs(),
        CombinedSearchParameters(
            length_min_m=6.8, length_max_m=7.6, length_step_m=0.20,
            width_min_m=3.6, width_max_m=4.4, width_step_m=0.20,
            h_min_m=0.65, h_max_m=0.90, h_step_m=0.05,
            first_column_edge_distance_m=0.25,
        ),
        soil=SoilProfile(qadm_kPa=1.5 * 98.0665, pressure_basis=PressureBasis.BRUTA,
                         gamma_kNm3=18.0, Df_m=1.50),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA,
    )
    a = [s.alternative.id for s in rank_combined_alternatives(r.valid)]
    b = [s.alternative.id for s in rank_combined_alternatives(r.valid)]
    assert a == b
    puntuaciones = [s.score for s in rank_combined_alternatives(r.valid)]
    assert puntuaciones == sorted(puntuaciones), "Menor puntuación primero"


# =========================================================================
# 14. Cortante longitudinal — criterio de concreto solo (auditoría C-V)
# =========================================================================
#
# Hasta la auditoría C-V estos tests afirmaban que la combinada «proponía estribos en vez de
# descartarse». No era así: la entrada del concreto seguía en FAIL y la geometría se descartaba.
# Los estribos se retiraron; el comportamiento se fija en tests/test_combined_shear_concrete_only_cv.py.

def test_sin_fail_de_cortante_no_hay_refuerzo_ni_motivo():
    r = _resolver()
    assert r.shear_longitudinal.status is not CheckStatus.FAIL
    assert r.shear_reinforcement is None
    assert not any(m.startswith("Cortante longitudinal:") for m in r.discard_reasons)


def test_con_cortante_alto_se_descarta_por_el_criterio_de_concreto_solo():
    """Vu > φVc → FAIL (criterio del programa). No es una prohibición de E.060, que admite
    Vn = Vc + Vs (§11.12.1.1, §11.1): el refuerzo de cortante no está implementado."""
    lay = _layout(B=9.0, L=2.2, columns=[_col("C1", 1.0, 2600.0, L_total=9.0),
                                         _col("C2", 8.0, 2600.0, L_total=9.0)])
    r = _resolver(lay, h=0.55, qadm=900.0)
    assert r.shear_longitudinal.status is CheckStatus.FAIL
    assert r.overall_status is CheckStatus.FAIL
    assert r.shear_reinforcement is None
    assert r.trace.by_id("shear_reinforcement") is None
    assert any(m.startswith("Cortante longitudinal:") and "concreto solo" in m for m in r.discard_reasons)
