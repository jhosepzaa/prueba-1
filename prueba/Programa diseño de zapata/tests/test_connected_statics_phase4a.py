"""FASE 4A — Estática de la zapata conectada.

QUÉ SE VERIFICA
===============
1. El equilibrio CIERRA: ΣF_v = 0 y ΣM = 0, comprobado sumando de nuevo todas las
   fuerzas, no releyendo el resultado del solver.
2. Las cargas se CONSERVAN: lo que pierde una zapata lo gana la otra.
3. La condición de rótula: el momento en la sección de corte es nulo.
4. La condición geométrica de la zapata de lindero se mantiene durante el barrido.
5. `connecting_beam_statics` NO importa ni usa `analysis/beam_diagram`.
6. El modelo de análisis es obligatorio y CUERPO_RIGIDO todavía no se resuelve.
7. Benchmark de Aragón §3.6 problema 1: se compara y se documenta la diferencia.
   NO se ajusta el motor para forzar la coincidencia.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.analysis import connected_statics
from engine.analysis.connected_statics import (
    Force,
    FreeBody,
    correct_loads,
    distribute_couple,
)
from engine.analysis.connecting_beam_statics import solve_connecting_beam
from engine.domain.column import Column
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectedElement,
    ConnectedFootingLayout,
    ConnectingBeamSpec,
    CoupleTransferMode,
    EdgeAnchor,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile

TONF_TO_KN = 9.80665
COL50 = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)

# Suelo auxiliar para la estática: el reparto solo lo usa en el modelo de cuerpo
# rígido, donde hace falta el peso propio de las zapatas.
_SUELO = SoilProfile(
    qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
    Df_m=1.50, source_notes="prueba",
)


def _huellas(layout, L1_m: float, L_transv: float = 2.60,
             int_B: float = 2.60, int_L: float = 2.60, h: float = 0.70):
    """Construye las dos huellas a partir de la longitud de la exterior."""
    return layout.footprints(L1_m, L_transv, h, int_B, int_L, h)



def _viga(
    self_weight=BeamSelfWeightMode.DESPRECIADO,
    support=BeamSupportMode.SIN_APOYO,
    **kw,
) -> ConnectingBeamSpec:
    """Los dos modos son OBLIGATORIOS en el modelo: no hay valor por defecto. Aquí se
    fijan explícitamente para que cada test diga con qué hipótesis corre."""
    base = dict(b_m=0.35, h_m=1.20, d_m=1.10)
    # Fase 9a: con EXPLICITO la cota vertical es obligatoria; HV-1 salvo que se indique.
    if self_weight is BeamSelfWeightMode.EXPLICITO:
        base["soffit_above_base_m"] = 0.0
    base.update(kw)
    return ConnectingBeamSpec(
        support_mode=support, self_weight_mode=self_weight, **base
    )


def _loads(P_serv: float, P_fact: float, Mx_serv: float = 0.0, Mx_fact: float = 0.0):
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                 P_kN=P_serv, Mx_kNm=Mx_serv)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=P_fact, Mx_kNm=Mx_fact)],
    )


def _layout(
    *, S: float = 6.0, clearance: float = 0.0, edge: str = "X_MIN",
    col_ext: Column = COL50, col_int: Column = COL50,
    loads_ext=None, loads_int=None, modelo=AnalysisModel.ARTICULADO,
    beam: ConnectingBeamSpec | None = None,
    modo_par=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
) -> ConnectedFootingLayout:
    return ConnectedFootingLayout(
        analysis_model=modelo,
        exterior=ConnectedElement(
            label="Z1", column=col_ext, loads=loads_ext or _loads(850.0, 1240.0),
            anchor=EdgeAnchor(edge=edge, face_clearance_m=clearance),
        ),
        interior=ConnectedElement(
            label="Z2", column=col_int, loads=loads_int or _loads(1100.0, 1600.0)
        ),
        beam=beam or _viga(),
        couple_transfer_mode=modo_par,
        axis_distance_m=S, longitudinal_axis="X",
    )


def _reparto(layout: ConnectedFootingLayout, L1: float, indice: int = 0):
    return distribute_couple(
        layout, _huellas(layout, L1),
        layout.exterior.loads.factored[indice], layout.interior.loads.factored[indice],
        _SUELO,
    )


# =========================================================================
# 1. Equilibrio global de fuerzas y de momentos
# =========================================================================

def test_el_cuerpo_libre_resuelve_dos_incognitas_con_dos_ecuaciones():
    """Prueba del mecanismo, con números escritos a mano y no por el motor."""
    cuerpo = FreeBody(
        description="prueba",
        known_forces=[Force(label="P", s_m=1.0, F_up_kN=-100.0)],
        unknown_1_label="R", unknown_1_s_m=2.0,
        unknown_2_label="V", unknown_2_s_m=5.0,
        moment_reference_s_m=5.0,
    )
    R, V = cuerpo.solve()
    # ΣM en s=5: (2−5)·R + (1−5)·(−100) = 0  ->  −3R + 400 = 0  ->  R = 133,33
    assert R == pytest.approx(400.0 / 3.0)
    # ΣFv: R + V − 100 = 0  ->  V = 100 − R
    assert V == pytest.approx(100.0 - 400.0 / 3.0)


def test_un_punto_de_momentos_degenerado_se_rechaza():
    """Si las dos incógnitas tienen el mismo brazo, el sistema es singular."""
    cuerpo = FreeBody(
        description="degenerado",
        known_forces=[Force(label="P", s_m=1.0, F_up_kN=-100.0)],
        unknown_1_label="A", unknown_1_s_m=3.0,
        unknown_2_label="B", unknown_2_s_m=3.0,
        moment_reference_s_m=0.0,
    )
    with pytest.raises(ValueError, match="indeterminado"):
        cuerpo.solve()


@pytest.mark.parametrize("L1", [1.60, 2.00, 2.40, 2.80, 3.20])
def test_el_equilibrio_de_fuerzas_cierra(L1):
    d = _reparto(_layout(), L1)
    assert d.residual_force_kN == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("L1", [1.60, 2.00, 2.40, 2.80, 3.20])
def test_el_equilibrio_de_momentos_cierra(L1):
    d = _reparto(_layout(), L1)
    assert d.residual_moment_kNm == pytest.approx(0.0, abs=1e-8)
    assert d.closes


def test_el_equilibrio_cierra_tambien_con_momento_de_columna():
    lay = _layout(loads_ext=_loads(850.0, 1240.0, Mx_serv=60.0, Mx_fact=90.0))
    d = _reparto(lay, 2.40)
    assert d.M_ext_kNm == pytest.approx(90.0)
    assert d.closes


def test_el_equilibrio_cierra_con_peso_propio_de_viga_declarado():
    lay = _layout(beam=_viga(self_weight=BeamSelfWeightMode.EXPLICITO))
    d = _reparto(lay, 2.40)
    assert d.beam_self_weight_kN > 0.0
    assert d.closes


def test_la_comprobacion_de_cierre_es_independiente_del_solver():
    """`residuals` vuelve a sumar TODAS las fuerzas. Si se le entrega una solución
    equivocada, debe delatarla: si no, el test de cierre no probaría nada."""
    lay = _layout()
    cuerpo = connected_statics.build_free_body(lay, 2.40, 1240.0, 0.0)
    R, V = cuerpo.solve()
    sf_mal, sm_mal = cuerpo.residuals(R * 1.01, V)
    assert abs(sf_mal) > 1.0, "Una solución errónea debe producir residuo no nulo"


# =========================================================================
# 2. Conservación de cargas
# =========================================================================

@pytest.mark.parametrize("L1", [1.60, 2.40, 3.20])
def test_lo_que_una_zapata_gana_la_otra_lo_pierde(L1):
    """ΔP es una transferencia, no una creación de carga. La suma de las cargas
    corregidas debe igualar la suma de las originales."""
    d = _reparto(_layout(), L1)
    original = d.P_ext_kN + d.P_int_kN
    corregida = d.P_ext_corrected_kN + d.P_int_corrected_kN
    assert corregida == pytest.approx(original, rel=1e-12)


def test_la_transferencia_es_exactamente_el_cortante_del_corte():
    d = _reparto(_layout(), 2.40)
    assert d.delta_P_kN == pytest.approx(-d.V_cut_kN, rel=1e-12)


def test_con_gravedad_pura_la_exterior_recibe_mas_de_lo_que_baja_su_columna():
    """Resultado clásico: la excentricidad obliga al suelo bajo la zapata de lindero
    a dar MÁS reacción que la carga de su propia columna."""
    d = _reparto(_layout(), 2.40)
    assert d.R_ext_kN > d.P_ext_kN
    assert d.delta_P_kN > 0.0
    # Y la interior actúa de CONTRAPESO: la viga tira de ella hacia arriba.
    assert d.P_int_corrected_kN < d.P_int_kN


def test_al_reducir_la_zapata_exterior_crece_la_transferencia():
    """El acoplamiento que impide optimizar las dos zapatas por separado."""
    grande = _reparto(_layout(), 3.00)
    pequena = _reparto(_layout(), 1.80)
    assert pequena.e1_m < grande.e1_m
    assert pequena.delta_P_kN < grande.delta_P_kN


def test_una_columna_centrada_no_genera_transferencia():
    """Caso límite: sin excentricidad no hay par que repartir."""
    col = COL50
    L1 = 3.00
    holgura = L1 / 2.0 - col.bx_m / 2.0  # la columna queda en el centro
    d = _reparto(_layout(clearance=holgura), L1)
    assert d.e1_m == pytest.approx(0.0, abs=1e-12)
    assert d.delta_P_kN == pytest.approx(0.0, abs=1e-9)


def test_las_combinaciones_se_reparten_una_a_una_y_no_por_envolvente():
    lay = _layout()
    corregidas = correct_loads(lay, _huellas(lay, 2.40), _SUELO)
    assert len(corregidas.distributions) == 2, "Una de servicio y una factorizada"
    assert {d.combo_name for d in corregidas.distributions} == {"S1", "U1"}
    assert len(corregidas.exterior.service) == 1
    assert len(corregidas.exterior.factored) == 1


def test_el_signo_de_la_transferencia_sigue_al_de_la_carga():
    """E.030 invierte el sismo: ΔP debe invertirse con él, y ambas ramas evaluarse.
    Se fuerza con un momento de columna que domina sobre la excentricidad.

    El signo del momento que consigue invertirla es el POSITIVO en la convención de
    E.050 art. 28.1: un Mx positivo desplaza la resultante hacia el interior y descarga
    la zapata de lindero. Una versión anterior necesitaba aquí un momento negativo,
    porque el momento entraba en el cuerpo libre sin convertir de convención."""
    lay = _layout(loads_ext=_loads(850.0, 1240.0, Mx_fact=3000.0))
    d = _reparto(lay, 2.00)
    assert d.delta_P_kN < 0.0, "Con el par invertido, la exterior queda aliviada"
    assert d.closes


def test_las_dos_ramas_del_sismo_dan_transferencias_de_signo_opuesto():
    """Lo que el artículo obliga a evaluar: no basta con una de las dos."""
    mas = _reparto(_layout(loads_ext=_loads(850.0, 1240.0, Mx_fact=3000.0)), 2.00)
    menos = _reparto(_layout(loads_ext=_loads(850.0, 1240.0, Mx_fact=-3000.0)), 2.00)
    assert mas.delta_P_kN * menos.delta_P_kN < 0.0


def test_el_momento_transversal_no_lo_toca_el_reparto():
    """La viga reparte el par EN SU DIRECCIÓN. Sobre el otro eje no dice nada."""
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        exterior=ConnectedElement(
            label="Z1", column=COL50,
            loads=LoadCaseSet(
                service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                         P_kN=850.0, My_kNm=45.0)],
                factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                          P_kN=1240.0, My_kNm=70.0)],
            ),
            anchor=EdgeAnchor(edge="X_MIN"),
        ),
        interior=ConnectedElement(label="Z2", column=COL50, loads=_loads(1100.0, 1600.0)),
        beam=_viga(),
        couple_transfer_mode=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        axis_distance_m=6.0, longitudinal_axis="X",
    )
    corregidas = correct_loads(lay, _huellas(lay, 2.40), _SUELO)
    assert corregidas.exterior.factored[0].My_kNm == pytest.approx(70.0)


# =========================================================================
# 3. La presión uniforme sale del par que la viga transmite
# =========================================================================

def test_el_par_corregido_anula_la_excentricidad_de_la_resultante():
    """Es el punto fino del modelo: entregar momento CERO no daría presión uniforme,
    porque la columna descentrada aporta P·offset por geometría."""
    from engine.soil.eccentricity import compute_total_eccentricity

    L1, B = 2.40, 2.40
    lay = _layout()
    d = _reparto(lay, L1)
    placement = lay.exterior.placement_for(B, 2.00)

    ecc = compute_total_eccentricity(
        d.P_ext_corrected_kN, 500.0, d.M_ext_corrected_kNm, 0.0,
        placement.offset_x_m, placement.offset_y_m,
    )
    assert ecc.ex_m == pytest.approx(0.0, abs=1e-9), (
        "Con el par de la viga aplicado, la resultante cae en el centroide"
    )


def test_sin_el_par_la_presion_no_seria_uniforme():
    """Control negativo: demuestra que el test anterior verifica algo."""
    from engine.soil.eccentricity import compute_total_eccentricity

    lay = _layout()
    d = _reparto(lay, 2.40)
    placement = lay.exterior.placement_for(2.40, 2.00)
    ecc = compute_total_eccentricity(
        d.P_ext_corrected_kN, 500.0, 0.0, 0.0, placement.offset_x_m, placement.offset_y_m
    )
    assert abs(ecc.ex_m) > 0.5, "Con momento nulo la excentricidad geométrica queda viva"


# =========================================================================
# 4. Condición geométrica de la zapata de lindero durante el barrido
# =========================================================================

@pytest.mark.parametrize("B", [1.60, 2.00, 2.40, 2.80, 3.60, 4.40])
def test_la_cara_de_la_columna_queda_al_ras_para_cualquier_geometria(B):
    """El requisito que `ColumnPlacement` NO podía mantener: un desplazamiento fijo
    despega la columna del lindero al crecer B."""
    anchor = EdgeAnchor(edge="X_MIN", face_clearance_m=0.0)
    placement = anchor.placement_for(COL50, B, 2.00)
    voladizo_izq, _ = placement.cantilevers_x(B)
    assert voladizo_izq == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("B", [2.00, 2.80, 3.60])
@pytest.mark.parametrize("holgura", [0.0, 0.05, 0.15])
def test_la_holgura_declarada_se_conserva_para_cualquier_geometria(B, holgura):
    anchor = EdgeAnchor(edge="X_MIN", face_clearance_m=holgura)
    voladizo_izq, _ = anchor.placement_for(COL50, B, 2.00).cantilevers_x(B)
    assert voladizo_izq == pytest.approx(holgura, abs=1e-12)


def test_el_borde_opuesto_invierte_el_signo_del_desplazamiento():
    p_min = EdgeAnchor(edge="X_MIN").placement_for(COL50, 3.00, 2.00)
    p_max = EdgeAnchor(edge="X_MAX").placement_for(COL50, 3.00, 2.00)
    assert p_min.offset_x_m == pytest.approx(-p_max.offset_x_m)


def test_un_anclaje_sobre_el_eje_Y_desplaza_en_Y():
    p = EdgeAnchor(edge="Y_MIN").placement_for(COL50, 3.00, 2.20)
    assert p.offset_x_m == 0.0
    assert p.offset_y_m == pytest.approx(-(2.20 / 2.0 - 0.25))


@pytest.mark.parametrize("B,cabe", [(0.40, False), (0.50, True), (2.40, True)])
def test_se_detecta_cuando_la_columna_no_cabe(B, cabe):
    assert EdgeAnchor(edge="X_MIN").fits_in(COL50, B, 2.00) is cabe


def test_el_borde_debe_estar_sobre_el_eje_de_la_viga():
    with pytest.raises(ValidationError, match="eje"):
        _layout(edge="Y_MIN")


def test_la_zapata_exterior_debe_declarar_su_borde():
    with pytest.raises(ValidationError, match="anchor"):
        ConnectedFootingLayout(
            analysis_model=AnalysisModel.ARTICULADO,
            exterior=ConnectedElement(label="Z1", column=COL50, loads=_loads(850.0, 1240.0)),
            interior=ConnectedElement(label="Z2", column=COL50, loads=_loads(1100.0, 1600.0)),
            beam=_viga(),
            couple_transfer_mode=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            axis_distance_m=6.0,
        )


# =========================================================================
# 5. Prohibición de reutilizar `analysis/beam_diagram.py`
# =========================================================================

_MODULOS_DE_CONECTADA = [
    "engine/analysis/connected_statics.py",
    "engine/analysis/connecting_beam_statics.py",
    "engine/foundation/connected_solver.py",
]


@pytest.mark.parametrize("ruta", _MODULOS_DE_CONECTADA)
def test_ningun_modulo_de_conectada_importa_beam_diagram(ruta):
    """`beam_diagram` modela un elemento APOYADO SOBRE EL SUELO en toda su longitud:
    deriva w0 y w1 del equilibrio de la reacción del terreno. La viga de conexión
    salva un vano sin apoyo. Usarlo daría números plausibles y equivocados."""
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                assert "beam_diagram" not in alias.name, f"{ruta} importa {alias.name}"
        elif isinstance(nodo, ast.ImportFrom):
            assert "beam_diagram" not in (nodo.module or ""), f"{ruta} importa de {nodo.module}"
            for alias in nodo.names:
                assert "beam_diagram" not in alias.name, f"{ruta} importa {alias.name}"


@pytest.mark.parametrize("ruta", _MODULOS_DE_CONECTADA)
def test_tampoco_se_menciona_build_beam_diagram(ruta):
    """Cubre el import diferido dentro de una función, que el análisis de AST de
    nivel superior no vería."""
    fuente = Path(ruta).read_text(encoding="utf-8")
    codigo = "\n".join(
        l for l in fuente.splitlines() if not l.strip().startswith("#")
    )
    assert "build_beam_diagram" not in codigo
    assert "BeamDiagram" not in codigo


def test_la_viga_de_conexion_no_tiene_carga_repartida_en_su_vano():
    """La diferencia física con `beam_diagram`, comprobada sobre el resultado: entre
    el borde de la zapata y el eje interior el cortante es CONSTANTE, porque allí no
    hay reacción del terreno."""
    lay = _layout()
    d = _reparto(lay, 2.40)
    b = solve_connecting_beam(lay, d)
    en_vano = [e for e in b.stations if e.s_m >= d.L1_m - 1e-9]
    assert len(en_vano) >= 2
    cortantes = [e.V_kN for e in en_vano]
    assert max(cortantes) == pytest.approx(min(cortantes), rel=1e-9)


# =========================================================================
# 6. Estática de la viga
# =========================================================================

def test_el_momento_en_la_rotula_es_nulo():
    """Es la condición que cierra el sistema en el modelo articulado. Si no saliera
    cero, el reparto estaría mal planteado."""
    lay = _layout()
    for L1 in (1.80, 2.40, 3.00):
        b = solve_connecting_beam(lay, _reparto(lay, L1))
        assert b.M_at_cut_kNm == pytest.approx(0.0, abs=1e-7)


def test_el_cortante_de_la_viga_es_la_transferencia():
    lay = _layout()
    d = _reparto(lay, 2.40)
    b = solve_connecting_beam(lay, d)
    assert b.V_design_kN == pytest.approx(abs(d.delta_P_kN), rel=1e-9)


def test_el_cortante_de_diseno_no_es_el_de_la_zapata():
    """Regresión de un error real: tomar el máximo sobre TODAS las secciones daba el
    cortante de la zapata —del orden de la carga de columna entera— y no el de la
    viga."""
    lay = _layout()
    d = _reparto(lay, 2.40)
    b = solve_connecting_beam(lay, d)
    assert b.V_design_kN < 0.5 * d.P_ext_kN
    assert b.s_beam_start_m == pytest.approx(d.L1_m)


def test_la_viga_trabaja_a_momento_negativo_en_su_vano():
    """Cuelga del voladizo de la zapata de lindero: tracción arriba."""
    lay = _layout()
    b = solve_connecting_beam(lay, _reparto(lay, 2.40))
    assert b.M_max_negative_kNm > 0.0
    assert b.M_max_positive_kNm == pytest.approx(0.0, abs=1e-9)


def test_el_momento_decrece_linealmente_hasta_la_rotula():
    lay = _layout()
    d = _reparto(lay, 2.40)
    b = solve_connecting_beam(lay, d)
    en_borde = next(e for e in b.stations if e.description.startswith("borde interior"))
    esperado = abs(d.delta_P_kN) * (d.s_cut_m - d.L1_m)
    assert abs(en_borde.M_kNm) == pytest.approx(esperado, rel=1e-9)


# =========================================================================
# 7. El modelo de análisis es obligatorio; CUERPO_RIGIDO sigue sin resolverse
# =========================================================================

def test_el_modelo_de_analisis_no_tiene_valor_por_defecto():
    with pytest.raises(ValidationError, match="analysis_model"):
        ConnectedFootingLayout(
            exterior=ConnectedElement(label="Z1", column=COL50, loads=_loads(850.0, 1240.0),
                                      anchor=EdgeAnchor(edge="X_MIN")),
            interior=ConnectedElement(label="Z2", column=COL50, loads=_loads(1100.0, 1600.0)),
            beam=_viga(),
            couple_transfer_mode=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            axis_distance_m=6.0,
        )


def test_el_modelo_de_cuerpo_rigido_ya_se_resuelve():
    """TBD-C2 quedó resuelto con el problema de aplicación 2 de los apuntes."""
    d = _reparto(_layout(modelo=AnalysisModel.CUERPO_RIGIDO), 2.40)
    assert d.analysis_model is AnalysisModel.CUERPO_RIGIDO
    assert d.bearing_area_m2 > 0.0 and d.bearing_inertia_m4 > 0.0
    assert d.M_cut_kNm != 0.0, "La junta transmite momento: es lo que define el modelo"


def test_las_dos_columnas_deben_declarar_las_mismas_combinaciones():
    """El reparto se resuelve combinación a combinación; sin pareja no hay reparto."""
    with pytest.raises(ValidationError, match="MISMAS combinaciones"):
        _layout(loads_int=LoadCaseSet(
            service=[LoadCombination(name="OTRA", type=LoadCombinationType.SERVICIO, P_kN=900.0)],
            factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=1300.0)],
        ))


# =========================================================================
# 8. Lo que queda declarado, no oculto
# =========================================================================

def test_la_premisa_de_presion_uniforme_viaja_en_las_hipotesis():
    d = _reparto(_layout(), 2.40)
    assert any("TBD-C1" in h for h in d.hypotheses)
    assert any("NO VERIFICADA" in h for h in d.hypotheses)


def test_el_peso_propio_de_la_viga_se_declara_en_los_tres_modos():
    """TBD-C5: las tres alternativas dejan constancia distinta. Ninguna puede pasar por
    otra, y ninguna es un valor por defecto."""
    textos = {}
    for modo in BeamSelfWeightMode:
        d = _reparto(_layout(beam=_viga(self_weight=modo)), 2.40)
        textos[modo] = " ".join(d.hypotheses)
    assert "EXPLÍCITAMENTE" in textos[BeamSelfWeightMode.EXPLICITO]
    assert "dos veces" in textos[BeamSelfWeightMode.EN_CARGAS_DE_COLUMNA]
    assert "DESPRECIADO" in textos[BeamSelfWeightMode.DESPRECIADO]
    assert len(set(textos.values())) == 3, "Los tres modos deben distinguirse en la traza"


def test_el_peso_propio_de_las_zapatas_no_entra_en_el_reparto():
    """Si entrara, `evaluate_candidate` lo contaría por segunda vez.

    Se comprueba sobre la nota de las ZAPATAS, identificada por su texto propio: la
    primera versión de este test buscaba «dos veces» en cualquier hipótesis y lo
    encontraba en la nota de la VIGA, de modo que pasaba sin verificar nada de lo que
    su nombre anuncia."""
    d = _reparto(_layout(), 2.40)
    nota = next((h for h in d.hypotheses if h.startswith("El peso propio de cada ZAPATA")), None)
    assert nota is not None, "La nota sobre el peso propio de las zapatas debe estar"
    assert "DOS VECES" in nota
    assert "self_weight.py" in nota


def test_la_estrategia_articulada_no_calcula_peso_propio_de_zapatas():
    """Control estructural acotado a la estrategia ARTICULADA. La de cuerpo rígido sí
    lo necesita —consecuencia F2— y llama al módulo compartido; la articulada no puede,
    porque su nota afirma que se agrupa y desaparece."""
    fuente = inspect.getsource(connected_statics._distribute_articulated)
    assert "compute_self_weight" not in fuente


def test_la_estrategia_rigida_reutiliza_el_modulo_de_peso_propio():
    """F2: lo necesita, y debe llamar al mismo módulo que usa el solver de zapata. Una
    segunda fórmula daría un peso distinto del que añade `evaluate_candidate`."""
    fuente = inspect.getsource(connected_statics._distribute_rigid_body)
    assert "compute_self_weight" in fuente


# =========================================================================
# 9. Benchmark Aragón §3.6 problema 1 — CON LOS DATOS REALES DEL PDF
# =========================================================================
#
# Hasta que llegó el PDF, este benchmark trabajaba sobre una geometría RECONSTRUIDA
# por ingeniería inversa a partir de Mu(−) y Vu. Esa reconstrucción era errónea en
# dos puntos, y conviene dejarlo escrito:
#
#   1. Supuso que la columna exterior no tenía momento. Sí lo tiene:
#      Mcm = 4 t·m, Mcv = 1,5 t·m, Ms = 90 t·m.
#   2. Dedujo que el libro dividía el par entre la LUZ LIBRE, porque
#      Mu(−)/Vu = 140,6/25,6 = 5,49 ≈ 5,50 m. Era una coincidencia: el libro divide
#      entre la distancia ENTRE EJES, S = 6,00 m, y el 5,49 sale de que el momento
#      de diseño está tomado a la CARA de la columna, no al eje.
#
# DATOS REALES (PDF, páginas 32 a 36):
#   Columnas 0,50 × 0,50. Columna exterior en límite de propiedad -> a = 0,25 m.
#   Zapata exterior: largo 1,40 m (longitudinal) × ancho 3,70 m × 0,60 m.
#   Zapata interior: 3,20 × 3,20 × 0,60 m.   Entre ejes S = 6,00 m.
#   Exterior: Pcm = 60, Pcv = 25, Mcm = 4, Mcv = 1,5, Ms = 90.
#   Interior: Pcm = 120, Pcv = 50.
#   sigma_adm = 1,8 kg/cm² = 18 t/m².  Peso propio = volumen × 2,4 (solo concreto).

ARAGON_P1 = dict(
    L1=1.40, B1=3.70, H1=0.60,
    L2=3.20, B2=3.20, H2=0.60,
    S=6.00, a=0.25,
    P_ext=85.0, M_ext=5.5, Ms_ext=90.0,
    P_int=170.0,
    sigma_adm=18.0,
)


def _pp(largo, ancho, alto):
    """Peso propio como lo calcula el libro: volumen de concreto por 2,4 t/m³."""
    return largo * ancho * alto * 2.4


def _metodo_del_libro(P_col, M_col, Ms=0.0):
    """Reproduce el procedimiento del PDF paso a paso, con sus propias reglas.

    Existe para poder CONTRASTAR el motor contra el libro sabiendo que lo que se
    compara es el método y no una transcripción equivocada. Este ayudante no forma
    parte del motor ni se usa en producción."""
    d = ARAGON_P1
    pp = _pp(d["L1"], d["B1"], d["H1"])
    e1 = d["L1"] / 2.0 - d["a"]
    R = P_col + pp                                  # el libro NO amplifica la reacción
    M_en_eje = M_col + pp * e1 + Ms                 # momento en el eje de la columna
    M_par = M_en_eje - R * e1
    delta_P = M_par / d["S"]                        # divide entre la distancia ENTRE EJES
    return dict(pp=pp, e1=e1, R=R, M_en_eje=M_en_eje, M_par=M_par, delta_P=delta_P)


def test_aragon_p1_se_reproduce_el_metodo_del_libro_paso_a_paso():
    """Primero hay que saber leer el libro. Si estos números no salen, cualquier
    conclusión sobre la discrepancia sería sobre una lectura equivocada."""
    r = _metodo_del_libro(ARAGON_P1["P_ext"], ARAGON_P1["M_ext"])
    assert r["pp"] == pytest.approx(7.46, abs=0.01)
    assert r["R"] == pytest.approx(92.46, abs=0.01)
    assert r["M_en_eje"] == pytest.approx(8.86, abs=0.01)
    assert abs(r["M_par"]) == pytest.approx(32.75, abs=0.02)
    assert abs(r["delta_P"]) == pytest.approx(5.45, abs=0.02)


def test_aragon_p1_la_presion_de_la_zapata_exterior_del_libro():
    d = ARAGON_P1
    r = _metodo_del_libro(d["P_ext"], d["M_ext"])
    sigma = r["R"] / (d["L1"] * d["B1"])
    assert sigma == pytest.approx(17.85, abs=0.02)
    assert sigma < d["sigma_adm"]


def test_aragon_p1_la_zapata_interior_queda_aliviada_en_gravedad():
    """Confirma el SIGNO que el motor adoptó: con gravedad pura, la zapata interior
    actúa de contrapeso y recibe MENOS carga."""
    d = ARAGON_P1
    r = _metodo_del_libro(d["P_ext"], d["M_ext"])
    pp_int = _pp(d["L2"], d["B2"], d["H2"])
    P_int = d["P_int"] + pp_int - abs(r["delta_P"])
    assert pp_int == pytest.approx(14.75, abs=0.02)
    assert P_int == pytest.approx(179.3, abs=0.05)


def test_aragon_p1_el_sismo_invierte_el_signo_de_la_transferencia():
    """CM+CV+CS carga la interior (194,29 t); CM+CV−CS la alivia (164,3 t). Ambas
    deben evaluarse: no basta la envolvente de una."""
    d = ARAGON_P1
    pp_int = _pp(d["L2"], d["B2"], d["H2"])
    mas = _metodo_del_libro(d["P_ext"], d["M_ext"], Ms=+d["Ms_ext"])
    menos = _metodo_del_libro(d["P_ext"], d["M_ext"], Ms=-d["Ms_ext"])
    assert mas["M_par"] == pytest.approx(57.25, abs=0.05)
    assert menos["M_par"] == pytest.approx(-122.75, abs=0.05)
    assert d["P_int"] + pp_int + mas["delta_P"] == pytest.approx(194.29, abs=0.05)
    assert d["P_int"] + pp_int + menos["delta_P"] == pytest.approx(164.3, abs=0.05)
    assert mas["delta_P"] * menos["delta_P"] < 0, "El signo se invierte con el sismo"


def test_aragon_p1_los_esfuerzos_de_la_viga_salen_del_reparto():
    """El libro amplifica con U = 1,25·(CM+CV+CS) y obtiene la viga directamente del
    reparto: Vu = 1,25·ΔP y Mu(−) en el eje = 1,25·M_par."""
    d = ARAGON_P1
    menos = _metodo_del_libro(d["P_ext"], d["M_ext"], Ms=-d["Ms_ext"])
    assert 1.25 * abs(menos["delta_P"]) == pytest.approx(25.6, abs=0.05)
    assert 1.25 * abs(menos["M_par"]) == pytest.approx(153.4, abs=0.1)


def test_aragon_p1_la_geometria_del_par_es_la_misma_en_los_dos_modos():
    """La excentricidad geométrica es de donde nace todo, y no depende del modo."""
    for modo in CoupleTransferMode:
        r = _reparto_aragon_p1_modo(modo)
        assert r.e1_m == pytest.approx(0.45, abs=1e-9)


# EL MOMENTO DEL LIBRO ENTRA EN EL MOTOR TAL CUAL.
#
# Esta constante existe porque durante un rato NO fue así, y la historia vale la pena.
#
# Una versión anterior necesitaba introducir el momento de los apuntes CAMBIADO DE
# SIGNO para reproducir sus tres combinaciones. Eso debía haber sido la señal: un factor
# ad hoc que hace cuadrar un benchmark casi siempre está tapando un defecto.
#
# Lo estaba. El momento de columna se inyectaba en el cuerpo libre sin convertirlo de la
# convención de E.050 art. 28.1 —«Mx positivo desplaza la resultante hacia +x»— a la del
# cuerpo libre, que suma momentos con las fuerzas positivas hacia arriba y tiene el signo
# opuesto. Con la conversión puesta, el libro se reproduce con su propio momento y los
# dos modelos de análisis responden al mismo dato en el mismo sentido.
SIGNO_MOMENTO_LIBRO = +1.0


def _reparto_aragon_p1_modo(modo, Ms: float = 0.0):
    """El mismo problema resuelto por el MOTOR, con el modo de reparto indicado."""
    d = ARAGON_P1
    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        couple_transfer_mode=modo,
        exterior=ConnectedElement(
            label="Z1", column=col,
            loads=_loads(
                d["P_ext"] * TONF_TO_KN, d["P_ext"] * TONF_TO_KN,
                Mx_serv=SIGNO_MOMENTO_LIBRO * (d["M_ext"] + Ms) * TONF_TO_KN,
                Mx_fact=SIGNO_MOMENTO_LIBRO * (d["M_ext"] + Ms) * TONF_TO_KN,
            ),
            anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=0.0),
        ),
        interior=ConnectedElement(
            label="Z2", column=col,
            loads=_loads(d["P_int"] * TONF_TO_KN, d["P_int"] * TONF_TO_KN),
        ),
        beam=_viga(),
        axis_distance_m=d["S"], longitudinal_axis="X",
    )
    return distribute_couple(
        lay, _huellas(lay, d["L1"], L_transv=d["B1"]),
        lay.exterior.loads.service[0], lay.interior.loads.service[0], _SUELO,
    )


@pytest.mark.parametrize("Ms, M_par_libro, dP_libro", [
    (0.0, -32.75, 5.45),
    (90.0, 57.25, 9.54),
    (-90.0, -122.75, 20.45),
])
def test_aragon_p1_el_modo_PAR_PURO_reproduce_el_libro(Ms, M_par_libro, dP_libro):
    """El procedimiento del libro es ahora un MODO declarable (TBD-C11), no una
    discrepancia. Con él, el motor reproduce sus tres combinaciones."""
    r = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA, Ms)
    assert r.M_couple_kNm / TONF_TO_KN == pytest.approx(M_par_libro, abs=0.02)
    assert abs(r.delta_P_kN) / TONF_TO_KN == pytest.approx(dP_libro, abs=0.02)


def test_aragon_p1_en_modo_PAR_PURO_la_reaccion_no_se_amplifica():
    """Es lo que distingue al modo: R = P, sin más, y de ahí la presión uniforme del
    libro (17,85 t/m²)."""
    d = ARAGON_P1
    r = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA)
    assert r.R_ext_kN / TONF_TO_KN == pytest.approx(d["P_ext"], rel=1e-9)
    pp = _pp(d["L1"], d["B1"], d["H1"])
    sigma = (r.R_ext_kN / TONF_TO_KN + pp) / (d["L1"] * d["B1"])
    assert sigma == pytest.approx(17.85, abs=0.02)


def test_aragon_p1_en_modo_PAR_PURO_falta_exactamente_la_rama_del_par():
    """La carga vertical NO cuadra dentro de la cimentación, y eso está declarado: lo
    que falta es exactamente la transferencia, ni más ni menos. El invariante sigue
    siendo fuerte, solo que admite ese hueco y lo mide."""
    r = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA)
    suma = r.P_ext_corrected_kN + r.P_int_corrected_kN
    assert suma == pytest.approx(r.P_ext_kN + r.P_int_kN - r.delta_P_kN, rel=1e-9)
    assert r.expected_residual_kN == pytest.approx(-r.delta_P_kN, rel=1e-12)
    assert r.conserves_load, "Falta lo previsto, de modo que el invariante se cumple"


def test_los_dos_modos_responden_al_momento_en_el_MISMO_sentido():
    """REGRESIÓN DE UN DEFECTO REAL. La primera versión del modo de par puro copiaba la
    fórmula cerrada del libro, `M_col − P·e1`, y con ella importaba SU convención de
    signos: el mismo Mx del usuario movía la transferencia en sentidos OPUESTOS según
    el modo. El benchmark no lo detectaba, porque reproducía el libro por construcción.

    Ahora el par se deriva del cuerpo libre con la misma maquinaria en los dos modos, de
    modo que el signo sale de la convención del motor y no de la fuente."""
    variaciones = {}
    for modo in CoupleTransferMode:
        bajo = _reparto_aragon_p1_modo(modo, Ms=-50.0).delta_P_kN
        alto = _reparto_aragon_p1_modo(modo, Ms=+50.0).delta_P_kN
        variaciones[modo] = alto - bajo
    valores = list(variaciones.values())
    assert valores[0] * valores[1] > 0, (
        f"Los dos modos responden al momento en sentidos opuestos: {variaciones}"
    )


def test_en_modo_par_puro_los_residuos_se_CALCULAN():
    """REGRESIÓN DE UN DEFECTO REAL. Estaban fijados a `0.0` a mano, con lo que `closes`
    no verificaba nada en ese modo. Ahora salen de sumar las fuerzas del cuerpo libre
    con el par incluido; si el par estuviera mal, el residuo de momentos lo diría."""
    r = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA)
    assert r.residual_force_kN == pytest.approx(0.0, abs=1e-9)
    assert r.residual_moment_kNm == pytest.approx(0.0, abs=1e-9)
    # Y un par falseado tiene que romper el cierre, o el test anterior no probaría nada.
    falseado = r.model_copy(update={"residual_moment_kNm": 500.0})
    assert not falseado.closes


def test_aragon_p1_los_dos_modos_dan_resultados_distintos():
    """Si coincidieran, uno de los dos estaría mal implementado. La diferencia nace de
    qué cuerpo libre se plantea, no de la aritmética."""
    equil = _reparto_aragon_p1_modo(CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION)
    puro = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA)
    assert equil.R_ext_kN > puro.R_ext_kN
    assert abs(equil.delta_P_kN) > abs(puro.delta_P_kN)


def test_aragon_p1_la_direccion_de_la_diferencia_entre_modos_esta_medida():
    """Hacia dónde se aparta cada modo del otro, que es lo que decide si importa:

      zapata exterior  EQUILIBRIO la carga MÁS  -> lado seguro
      zapata interior  EQUILIBRIO la alivia MÁS -> lado INSEGURO

    Ese segundo punto es la razón de que el modo sea declaración obligatoria y no un
    detalle de implementación."""
    equil = _reparto_aragon_p1_modo(CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION)
    puro = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA)
    assert equil.P_ext_corrected_kN > puro.P_ext_corrected_kN
    assert equil.P_int_corrected_kN < puro.P_int_corrected_kN


def test_aragon_p1_la_viga_en_modo_PAR_PURO_reproduce_el_cortante_del_libro():
    """Vu = 1,25·ΔP = 25,6 t, y Mu(−) en el eje = 1,25·M_par = 153,4 t·m."""
    from engine.analysis.connecting_beam_statics import solve_connecting_beam

    d = ARAGON_P1
    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        couple_transfer_mode=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
        exterior=ConnectedElement(
            label="Z1", column=col,
            loads=_loads(d["P_ext"] * TONF_TO_KN, d["P_ext"] * TONF_TO_KN,
                         Mx_serv=SIGNO_MOMENTO_LIBRO * (d["M_ext"] - d["Ms_ext"]) * TONF_TO_KN,
                         Mx_fact=SIGNO_MOMENTO_LIBRO * (d["M_ext"] - d["Ms_ext"]) * TONF_TO_KN),
            anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=0.0),
        ),
        interior=ConnectedElement(
            label="Z2", column=col,
            loads=_loads(d["P_int"] * TONF_TO_KN, d["P_int"] * TONF_TO_KN),
        ),
        beam=_viga(),
        axis_distance_m=d["S"], longitudinal_axis="X",
    )
    r = distribute_couple(
        lay, _huellas(lay, d["L1"], L_transv=d["B1"]),
        lay.exterior.loads.service[0], lay.interior.loads.service[0], _SUELO,
    )
    b = solve_connecting_beam(lay, r)
    assert 1.25 * b.V_design_kN / TONF_TO_KN == pytest.approx(25.6, abs=0.1)
    assert 1.25 * b.M_max_negative_kNm / TONF_TO_KN == pytest.approx(153.4, abs=0.2)


def test_aragon_p1_el_momento_a_la_cara_no_se_reproduce_y_esta_documentado():
    """DIFERENCIA QUE PERSISTE. El libro diseña con Mu(−) = 140,6 t·m a la CARA de la
    columna, reducido desde los 153,4 del eje. El motor reduce linealmente desde el eje
    y obtiene 147,0.

    La diferencia se explica: 153,4·(1 − 0,50/6,00) = 140,6 exactamente, de modo que el
    libro mide el brazo desde el LINDERO (s = 0) y no desde el eje de la columna
    (s = 0,25). Es otra convención de cuerpo libre, no un error de aritmética, y no se
    adopta en silencio: se deja medida."""
    from engine.analysis.connecting_beam_statics import solve_connecting_beam

    d = ARAGON_P1
    r = _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA, -d["Ms_ext"])
    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        couple_transfer_mode=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
        exterior=ConnectedElement(label="Z1", column=col, loads=_loads(1.0, 1.0),
                                  anchor=EdgeAnchor(edge="X_MIN")),
        interior=ConnectedElement(label="Z2", column=col, loads=_loads(1.0, 1.0)),
        beam=_viga(), axis_distance_m=d["S"], longitudinal_axis="X",
    )
    b = solve_connecting_beam(lay, r)
    del_motor = 1.25 * abs(b.M_at_exterior_column_face_kNm) / TONF_TO_KN
    assert del_motor == pytest.approx(147.0, abs=0.3)

    # La convención del libro, reconstruida: brazo desde el lindero.
    del_libro = 1.25 * abs(r.M_couple_kNm) / TONF_TO_KN * (1.0 - 0.50 / d["S"])
    assert del_libro == pytest.approx(140.6, abs=0.2)
