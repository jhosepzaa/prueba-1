"""FASE 4D — Búsqueda y optimización de la zapata conectada.

QUÉ SE VERIFICA
===============
1. El generador NO calcula física: la delega entera en `solve_connected_footing`.
2. El despegue RECHAZA el candidato y la búsqueda continúa. No es una excepción que
   detenga el barrido.
3. Solo FAIL descarta. Exigir PASS rechazaría todo mientras TBD-C1 siga abierto, y esa
   distinción es la que decide si la tipología es utilizable.
4. El acoplamiento de la terna se respeta: la geometría de la interior influye en el
   resultado, y por eso no se puede optimizar cada zapata por separado.
5. La pareja de peralte elegida es la más barata de las que cumplen, no la primera del
   orden de iteración.
6. El tope de ternas se declara cuando se alcanza.
7. La puntuación reutiliza el mismo núcleo que las otras dos tipologías.
"""

from __future__ import annotations

import inspect

import pytest

import engine.optimization.connected_generator as generador
from engine.codes.peru.e060_concrete import E060ConcreteCode
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
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation import connected_solver as solver_module
from engine.optimization.connected_generator import (
    MAX_CONNECTED_SYSTEMS,
    ConnectedSearchParameters,
    RejectionReason,
    generate_connected_alternatives,
    rank_connected_alternatives,
)
from engine.optimization.connected_metrics import compute_connected_metrics
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel

COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
CODE = E060ConcreteCode()
CONC = MaterialConcrete(fc_MPa=21.0)
STEEL = MaterialSteel(fy_MPa=420.0)
SUELO = SoilProfile(qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA,
                    gamma_kNm3=18.0, Df_m=1.50, source_notes="prueba")

# El mismo suelo con el FS de volcamiento DECLARADO. Sirve para aislar TBD-C1: sin
# declararlo, la zapata de lindero sale NO VERIFICADO por DOS motivos distintos —el
# pendiente del motor y un dato que el proyectista no aportó— y no se podría comprobar
# que se distinguen. Ver `test_faltar_un_dato_no_es_lo_mismo_que_un_TBD_abierto`.
SUELO_CON_FS = SUELO.model_copy(update={"FS_overturning_required": 1.5})
DEPTH = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)


def _cargas(P: float, M: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                 P_kN=P, Mx_kNm=M)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=P * 1.4, Mx_kNm=M * 1.4)],
    )


def _layout(modelo=AnalysisModel.ARTICULADO, M_ext: float = 0.0):
    return ConnectedFootingLayout(
        analysis_model=modelo,
        couple_transfer_mode=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        # Gancho de 90° en la zapata de lindero (2026-09-28): con E.060 §15.6.2 la barra
        # recta no se ancla hacia el lindero en el ancho de una columna de 0,50 m. En las
        # dos direcciones, para que girar la viga de X a Y no cambie el problema.
        exterior=ConnectedElement(label="Z1", column=COL, loads=_cargas(850.0, M_ext),
                                  anchor=EdgeAnchor(edge="X_MIN"),
                                  hook_type_x="90", hook_type_y="90"),
        interior=ConnectedElement(label="Z2", column=COL, loads=_cargas(1100.0)),
        beam=ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10,
                                support_mode=BeamSupportMode.SIN_APOYO,
                                self_weight_mode=BeamSelfWeightMode.DESPRECIADO),
        axis_distance_m=6.0, longitudinal_axis="X",
    )


def _params(**kw) -> ConnectedSearchParameters:
    base = dict(
        ext_long_min_m=2.0, ext_long_max_m=2.8, ext_long_step_m=0.4,
        ext_transv_min_m=2.4, ext_transv_max_m=2.8, ext_transv_step_m=0.4,
        int_long_min_m=2.2, int_long_max_m=2.6, int_long_step_m=0.4,
        int_transv_min_m=2.2, int_transv_max_m=2.6, int_transv_step_m=0.4,
        h_min_m=0.60, h_max_m=1.00, h_step_m=0.20,
        same_depth_both_footings=True,
    )
    base.update(kw)
    return ConnectedSearchParameters(**base)


def _buscar(layout=None, params=None, soil=None):
    return generate_connected_alternatives(
        layout or _layout(), params or _params(),
        soil=soil or SUELO, concrete=CONC, steel=STEEL, code=CODE,
        contact_model=KernCheckModel(), depth_params=DEPTH,
    )


# =========================================================================
# 1. El generador NO calcula física
# =========================================================================

def test_el_generador_no_reimplementa_ninguna_ecuacion():
    fuente = inspect.getsource(generador)
    prohibidos = ["0.85", "sqrt", "0.17", "0.62", "compute_self_weight",
                  "moment_about_kNm", "distribute_couple", "rebar", "Rebar"]
    for p in prohibidos:
        assert p not in fuente, (
            f"«{p}» aparece en el generador: 4D es estrategia de búsqueda, la física "
            f"vive en los solvers."
        )


def test_cada_candidato_pasa_por_el_solver_de_conectada(monkeypatch):
    llamadas = []
    original = generador.solve_connected_footing

    def espia(*a, **kw):
        llamadas.append(kw.get("depth_params"))
        return original(*a, **kw)

    monkeypatch.setattr(generador, "solve_connected_footing", espia)
    r = _buscar()
    assert len(llamadas) == r.evaluated_count


def test_el_simbolo_importado_es_el_del_solver_original():
    assert generador.solve_connected_footing is solver_module.solve_connected_footing


def test_la_puntuacion_reutiliza_el_nucleo_comun():
    """Ninguna aritmética de puntuación propia: `score_metric_sets` opera sobre las
    métricas y no sabe qué tipología las produjo."""
    fuente = inspect.getsource(generador.rank_connected_alternatives)
    assert "score_metric_sets" in fuente
    assert "min(" not in fuente and "max(" not in fuente


# =========================================================================
# 2. Despegue: candidato RECHAZADO, búsqueda que continúa
# =========================================================================

def test_el_despegue_rechaza_el_candidato_y_no_detiene_la_busqueda():
    """LA DECISIÓN DE 4D. El solver no puede producir un resultado con despegue y por
    eso se niega; en un barrido esa negativa no puede propagarse y parar la
    exploración de las demás geometrías."""
    r = _buscar(_layout(modelo=AnalysisModel.CUERPO_RIGIDO, M_ext=9000.0))
    assert r.evaluated_count > 1, "La búsqueda recorrió el espacio entero"
    assert r.rejections_by_reason().get(RejectionReason.DESPEGUE.value, 0) > 0
    assert len(r.rejected) == r.evaluated_count


def test_el_rechazo_por_despegue_guarda_el_motivo_y_la_geometria():
    r = _buscar(_layout(modelo=AnalysisModel.CUERPO_RIGIDO, M_ext=9000.0))
    caso = next(x for x in r.rejected if x.reason is RejectionReason.DESPEGUE)
    assert caso.geometry.exterior_B_m > 0
    assert "DESPEGUE" in caso.detail
    assert "contacto" in caso.detail, "Debe decir que no se resuelve contacto unilateral"


def test_una_geometria_imposible_tambien_se_rechaza_sin_parar():
    """La columna no cabe: no es un descarte de diseño, es una entrada sin sentido
    físico. Tampoco puede detener el barrido."""
    r = _buscar(params=_params(ext_long_min_m=0.30, ext_long_max_m=0.30,
                               ext_transv_min_m=0.30, ext_transv_max_m=0.30))
    assert r.evaluated_count > 0
    assert r.rejections_by_reason().get(RejectionReason.GEOMETRIA_IMPOSIBLE.value, 0) > 0


def test_los_motivos_de_rechazo_se_agrupan():
    r = _buscar()
    conteo = r.rejections_by_reason()
    assert sum(conteo.values()) == len(r.rejected)
    assert all(motivo in {m.value for m in RejectionReason} for motivo in conteo)


# =========================================================================
# 3. El criterio de aceptación: solo FAIL descarta
# =========================================================================

def test_se_aceptan_alternativas_en_NO_VERIFICADO():
    """Es lo que hace utilizable la tipología. La premisa de rigidez de TBD-C1 no tiene
    criterio normativo de verificación, de modo que el sistema NUNCA alcanza PASS:
    exigirlo rechazaría todas las alternativas sin excepción."""
    r = _buscar()
    assert r.accepted, "Debe haber alternativas aceptadas"
    assert all(a.overall_status is CheckStatus.NOT_VERIFIED for a in r.accepted)


def test_ninguna_alternativa_aceptada_esta_en_FAIL():
    r = _buscar()
    assert all(not a.overall_status.discards for a in r.accepted)


def test_el_criterio_usa_la_maquina_de_estados_y_no_una_lista_propia():
    """`status.discards` dice que solo FAIL descarta. Si el generador comparase contra
    una lista de estados escrita a mano, divergiría de la máquina en cuanto ésta
    cambie."""
    # `_evaluar_planta` es quien juzga cada candidato y `_acumular` quien lo incorpora;
    # `generate_connected_alternatives` solo recorre y reparte (2026-09-24). El criterio
    # se comprueba donde se aplica. Fuera de ellas, `CheckStatus.PASS` sí aparece: en
    # `accepted_and_compliant`, que es una PARTICIÓN del resultado y no el criterio de
    # aceptación (CLAUDE.md §5).
    decisión = inspect.getsource(generador._evaluar_planta) + inspect.getsource(
        generador._acumular
    )
    assert ".discards" in decisión
    assert "CheckStatus.PASS" not in decisión


def test_lo_NO_VERIFICADO_no_se_presenta_como_conforme():
    """El estado viaja en el resultado y el módulo lo dice por escrito. Aceptar no es
    aprobar."""
    r = _buscar()
    assert "Aceptada no es" in generador.ConnectedAlternativeSet.model_fields[
        "accepted"
    ].description
    assert r.accepted[0].result.overall_status is CheckStatus.NOT_VERIFIED


def test_el_conjunto_no_usa_la_palabra_valida_para_lo_no_verificado():
    """La palabra «válida» sugiere «correcta». Ninguna alternativa de esta tipología
    puede declararse correcta mientras TBD-C1 siga abierto, así que el campo no se
    llama así y no debe volver a llamarse así."""
    assert "valid" not in generador.ConnectedAlternativeSet.model_fields
    assert "accepted" in generador.ConnectedAlternativeSet.model_fields


# =========================================================================
# 4. El acoplamiento de la terna
# =========================================================================

def test_la_geometria_de_la_zapata_interior_influye_en_el_resultado():
    """Si no influyera, se podrían optimizar por separado y toda la estrategia de 4D
    sobraría."""
    estrecho = _buscar(params=_params(int_transv_min_m=2.2, int_transv_max_m=2.2))
    ancho = _buscar(params=_params(int_transv_min_m=3.4, int_transv_max_m=3.4))
    assert estrecho.accepted and ancho.accepted
    assert estrecho.accepted[0].concrete_volume_m3 != pytest.approx(
        ancho.accepted[0].concrete_volume_m3, rel=1e-6
    )


def test_alargar_la_zapata_de_lindero_aumenta_la_transferencia():
    """El acoplamiento que impide la optimización por separado, comprobado sobre las
    alternativas que el barrido dio por válidas y no sobre la estática aislada.

    Se agrupan por longitud de la zapata de lindero en vez de comparar dos barridos
    fijos: una longitud concreta puede no dejar ninguna alternativa viable, y el test
    estaría midiendo eso en vez del acoplamiento."""
    r = _buscar()
    por_longitud: dict[float, float] = {}
    for a in r.accepted:
        L1 = a.result.statics[0].L1_m
        por_longitud.setdefault(L1, a.result.statics[0].delta_P_kN)

    assert len(por_longitud) >= 2, "Hacen falta al menos dos longitudes viables"
    longitudes = sorted(por_longitud)
    transferencias = [por_longitud[L] for L in longitudes]
    assert transferencias == sorted(transferencias), (
        f"ΔP debe crecer con la longitud de la zapata de lindero: {por_longitud}"
    )


def test_la_terna_completa_viaja_en_cada_alternativa():
    a = _buscar().accepted[0]
    assert a.result.exterior is not None
    assert a.result.interior is not None
    assert a.result.beam is not None
    assert a.result.statics


# =========================================================================
# 5. El peralte elegido es el más barato que cumple
# =========================================================================

def test_las_parejas_de_peralte_van_ordenadas_por_volumen_creciente():
    parejas = generador._depth_pairs(_params(same_depth_both_footings=False))
    sumas = [a + b for a, b in parejas]
    assert sumas == sorted(sumas)


def test_con_mismo_peralte_declarado_solo_se_prueban_parejas_iguales():
    parejas = generador._depth_pairs(_params(same_depth_both_footings=True))
    assert all(a == b for a, b in parejas)


def test_sin_esa_restriccion_se_prueban_parejas_distintas():
    parejas = generador._depth_pairs(_params(same_depth_both_footings=False))
    assert any(a != b for a, b in parejas)
    assert len(parejas) == 3 * 3


def test_el_peralte_elegido_es_el_menor_que_cumple_para_esa_planta():
    """Se resuelve a mano la misma planta con cada peralte y se comprueba que el
    generador eligió el primero que no falla."""
    from engine.foundation.connected_solver import (
        ConnectedFootingGeometry, solve_connected_footing,
    )

    r = _buscar(params=_params(ext_long_min_m=2.0, ext_long_max_m=2.0,
                               ext_transv_min_m=2.4, ext_transv_max_m=2.4,
                               int_long_min_m=2.2, int_long_max_m=2.2,
                               int_transv_min_m=2.2, int_transv_max_m=2.2))
    assert r.accepted
    elegido = r.accepted[0].geometry.exterior_h_m

    lay = _layout()
    for h in (0.60, 0.80, 1.00):
        if h >= elegido:
            break
        geo = ConnectedFootingGeometry(
            exterior_B_m=2.0, exterior_L_m=2.4, exterior_h_m=h,
            interior_B_m=2.2, interior_L_m=2.2, interior_h_m=h,
        )
        try:
            previo = solve_connected_footing(
                lay, geo, soil=SUELO, concrete=CONC, steel=STEEL, code=CODE,
                contact_model=KernCheckModel(), depth_params=DEPTH,
            )
        except ValueError:
            continue
        assert previo.overall_status.discards, (
            f"h = {h} no falla: el generador debió elegirlo antes que {elegido}"
        )


# =========================================================================
# 6. El tope se declara
# =========================================================================

def test_un_rango_desmedido_se_trunca_y_lo_dice():
    r = _buscar(params=_params(
        ext_long_min_m=1.5, ext_long_max_m=4.0, ext_long_step_m=0.1,
        ext_transv_min_m=1.5, ext_transv_max_m=4.0, ext_transv_step_m=0.1,
        int_long_min_m=1.5, int_long_max_m=4.0, int_long_step_m=0.1,
        int_transv_min_m=1.5, int_transv_max_m=4.0, int_transv_step_m=0.1,
    ))
    assert r.truncated
    assert "NO es una búsqueda exhaustiva" in r.search_note
    assert r.evaluated_count <= MAX_CONNECTED_SYSTEMS


def test_un_rango_acotado_no_se_trunca():
    r = _buscar()
    assert not r.truncated
    assert r.search_note == ""


def test_un_rango_invertido_se_rechaza_en_la_entrada():
    with pytest.raises(ValueError, match="invertido"):
        _params(ext_long_min_m=3.0, ext_long_max_m=2.0)


# =========================================================================
# 7. Métricas y ordenamiento
# =========================================================================

def test_las_metricas_suman_las_dos_zapatas_y_la_viga():
    from engine.optimization.metrics import compute_metrics

    a = _buscar().accepted[0]
    cover = CODE.cover_footing_mm()[0] / 1000.0
    m_ext = compute_metrics(a.result.exterior, SUELO.Df_m, cover)
    m_int = compute_metrics(a.result.interior, SUELO.Df_m, cover)
    assert a.metrics.concrete_volume_m3 > m_ext.concrete_volume_m3 + m_int.concrete_volume_m3
    assert a.metrics.footing_area_m2 == pytest.approx(
        m_ext.footing_area_m2 + m_int.footing_area_m2
    )


def test_el_volumen_de_la_viga_no_se_cuenta_dos_veces_ni_se_omite():
    """Fase 9b. La parte de la viga dentro de cada zapata ya está en el volumen de esa
    zapata; la que sobresale no la cuenta nadie más. Se reconstruye a mano con z_b = 0
    (la búsqueda no declara la cota) desde las huellas y las columnas."""
    a = _buscar().accepted[0]
    assert generador.compute_connected_metrics is compute_connected_metrics
    from engine.optimization.connected_metrics import _beam_concrete_m3

    r = a.result
    ax = r.beam_axis
    b, h = r.beam.b_m, r.beam.h_m
    t_e = min(h, r.geometry.exterior_h_m)
    t_i = min(h, r.geometry.interior_h_m)
    esperado = (
        b * h * (ax.s_span_end_m - ax.s_span_start_m)
        + b * (h - t_e) * (ax.s_span_start_m - ax.s_exterior_face_m)
        + b * (h - t_i) * (ax.s_interior_face_m - ax.s_span_end_m)
    )
    assert _beam_concrete_m3(r) == pytest.approx(esperado)
    assert r.beam_span_m == pytest.approx(ax.s_span_end_m - ax.s_span_start_m)
    assert r.beam_span_m < r.statics[0].S_m, "El vano libre es menor que la distancia entre ejes"


def test_la_penalizacion_heuristica_de_la_viga_no_altera_el_ranking():
    """`BEAM_COMPLEXITY_PENALTY` está en cero DELIBERADAMENTE: una constante sin
    fundamento no puede decidir cuál alternativa se recomienda. El test fija esa
    decisión, no la implementación: si algún día se le da un valor justificable,
    tendrá que ser una decisión explícita que pase por aquí."""
    from engine.optimization.connected_metrics import BEAM_COMPLEXITY_PENALTY

    assert BEAM_COMPLEXITY_PENALTY == 0.0

    aceptadas = _buscar().accepted
    orden_en_cero = [s.alternative.id for s in rank_connected_alternatives(aceptadas)]

    # Y además: el término es el mismo para todas las alternativas —todas llevan viga—,
    # de modo que ni siquiera con un valor grande podría mover el orden. Se comprueba
    # de verdad, recalculando las métricas con la constante parcheada.
    import engine.optimization.connected_metrics as cm

    original = cm.BEAM_COMPLEXITY_PENALTY
    try:
        cm.BEAM_COMPLEXITY_PENALTY = 7.5
        recalculadas = [
            a.model_copy(update={
                "metrics": cm.compute_connected_metrics(
                    a.result, SUELO.Df_m, CODE.cover_footing_mm()[0] / 1000.0
                )
            })
            for a in aceptadas
        ]
    finally:
        cm.BEAM_COMPLEXITY_PENALTY = original

    desplazamientos = {
        round(n.metrics.constructive_complexity_index
              - v.metrics.constructive_complexity_index, 9)
        for v, n in zip(aceptadas, recalculadas)
    }
    assert desplazamientos == {7.5}, (
        f"La penalización no afecta por igual a todas las alternativas: {desplazamientos}"
    )
    assert orden_en_cero == [
        s.alternative.id for s in rank_connected_alternatives(recalculadas)
    ]


def test_el_ordenamiento_es_determinista():
    aceptadas = _buscar().accepted
    primero = [s.alternative.id for s in rank_connected_alternatives(aceptadas)]
    segundo = [s.alternative.id for s in rank_connected_alternatives(aceptadas)]
    assert primero == segundo


def test_la_mejor_alternativa_no_es_la_de_mayor_volumen():
    """Todas las métricas son costos: menor puntuación es mejor."""
    aceptadas = _buscar().accepted
    orden = rank_connected_alternatives(aceptadas)
    assert orden[0].score <= orden[-1].score
    assert orden[0].alternative.concrete_volume_m3 <= max(
        a.concrete_volume_m3 for a in aceptadas
    )


def test_las_alternativas_se_numeran_de_forma_estable():
    r = _buscar()
    ids = [a.id for a in r.accepted]
    assert ids == sorted(ids)
    assert ids[0] == "CONN-001"


# =========================================================================
# 8. Lo que el barrido NO decide
# =========================================================================

def test_el_modelo_de_analisis_no_se_optimiza():
    """Es una declaración del proyectista, no un parámetro a buscar. El generador lo
    toma del layout y no lo toca."""
    for modelo in AnalysisModel:
        r = _buscar(_layout(modelo=modelo))
        assert all(
            a.result.statics[0].analysis_model is modelo for a in r.accepted
        ), f"El barrido cambió el modelo declarado ({modelo})"


def test_el_modo_de_reparto_del_par_tampoco_se_optimiza():
    for modo in CoupleTransferMode:
        lay = _layout().model_copy(update={"couple_transfer_mode": modo})
        r = _buscar(lay)
        assert all(
            a.result.statics[0].couple_transfer_mode is modo for a in r.accepted
        )


def test_el_generador_no_admite_parametros_de_la_viga():
    """La sección de la viga es dato del proyectista: h ≈ L/7 es predimensionamiento
    nivel C y no puede convertirse en un eje de optimización sin que alguien lo
    decida."""
    campos = set(ConnectedSearchParameters.model_fields)
    assert not any("beam" in c or "viga" in c for c in campos)


# =========================================================================
# 9. Huellas que se solapan — defecto detectado al cerrar 4D
# =========================================================================

def test_las_huellas_no_pueden_solaparse():
    """`Footprints` publica área, inercia y `width_at` suponiendo dos rectángulos
    DISJUNTOS. Con solape los tres salen mal y en el sentido peligroso: más área y más
    inercia de la real, luego MENOS presión. Tiene que cortarse en la geometría."""
    from engine.domain.connected_layout import Footprint, Footprints

    with pytest.raises(ValueError, match="GEOMETRIA_IMPOSIBLE"):
        Footprints(
            exterior=Footprint(length_m=3.60, width_m=2.40, h_m=0.80, start_m=0.0),
            interior=Footprint(length_m=2.40, width_m=2.40, h_m=0.80, start_m=3.05),
        )


def test_las_huellas_que_solo_se_tocan_tambien_se_rechazan():
    """Vano libre nulo: no hay viga de conexión que salvar nada, y la tipología deja de
    ser la que resuelve este motor."""
    from engine.domain.connected_layout import Footprint, Footprints

    with pytest.raises(ValueError, match="GEOMETRIA_IMPOSIBLE"):
        Footprints(
            exterior=Footprint(length_m=3.00, width_m=2.40, h_m=0.80, start_m=0.0),
            interior=Footprint(length_m=2.40, width_m=2.40, h_m=0.80, start_m=3.00),
        )


def test_las_huellas_separadas_siguen_siendo_validas():
    """Control positivo: el validador no puede estar rechazando el caso normal."""
    from engine.domain.connected_layout import Footprint, Footprints

    fp = Footprints(
        exterior=Footprint(length_m=2.00, width_m=2.40, h_m=0.80, start_m=0.0),
        interior=Footprint(length_m=2.40, width_m=2.40, h_m=0.80, start_m=4.80),
    )
    assert fp.total_area_m2 == pytest.approx(2.00 * 2.40 + 2.40 * 2.40)
    assert fp.width_at(3.0) == 0.0  # el vano no aporta apoyo


def test_el_solape_es_un_rechazo_de_busqueda_y_no_detiene_el_barrido():
    """Con las columnas muy juntas TODA la malla solapa. El barrido tiene que
    terminar, contabilizar los rechazos como GEOMETRIA_IMPOSIBLE —no como una entrada
    inválida cualquiera— y no dejar escapar la excepción."""
    lay = _layout().model_copy(update={"axis_distance_m": 2.20})
    params = _params(ext_long_min_m=3.0, ext_long_max_m=3.4, ext_long_step_m=0.2,
                     int_long_min_m=3.0, int_long_max_m=3.4, int_long_step_m=0.2)

    r = _buscar(lay, params)

    assert r.accepted == []
    assert r.rejections_by_reason() == {RejectionReason.GEOMETRIA_IMPOSIBLE.value:
                                        len(r.rejected)}
    assert r.evaluated_count == len(r.rejected)


def test_el_solape_no_llega_disfrazado_de_carga_negativa():
    """Antes del arreglo, un sistema con huellas solapadas seguía adelante y reventaba
    aguas abajo con «la carga vertical total debe ser positiva»: un síntoma que no
    señala a la causa y que el barrido clasificaba como ENTRADA_INVALIDA."""
    lay = _layout().model_copy(update={"axis_distance_m": 2.20})
    params = _params(ext_long_min_m=3.2, ext_long_max_m=3.2,
                     int_long_min_m=3.2, int_long_max_m=3.2)

    r = _buscar(lay, params)

    assert RejectionReason.ENTRADA_INVALIDA.value not in r.rejections_by_reason()
    assert all("carga vertical" not in x.detail for x in r.rejected)


# =========================================================================
# 10. La dimensión en planta del sistema depende del eje de la viga
# =========================================================================

def test_la_longitud_del_sistema_usa_la_dimension_sobre_el_eje_de_la_viga():
    """`system_length_m` alimenta `max_plan_dimension_m`, que es una de las métricas de
    ordenamiento. Tomar siempre `interior_B_m` daba, en un sistema sobre Y, la
    dimensión TRANSVERSAL de la zapata interior: un número que no es la longitud del
    sistema y que altera el orden entre alternativas."""
    lay_x = _layout()
    lay_y = lay_x.model_copy(update={
        "longitudinal_axis": "Y",
        "exterior": lay_x.exterior.model_copy(
            update={"anchor": EdgeAnchor(edge="Y_MIN")}),
    })

    r_x = _buscar(lay_x, _params())
    r_y = _buscar(lay_y, _params())
    assert r_x.accepted and r_y.accepted

    # Mismo sistema girado 90°: la longitud del conjunto no puede depender del giro.
    a_x = r_x.accepted[0]
    a_y = r_y.accepted[0]
    assert a_x.result.longitudinal_axis == "X"
    assert a_y.result.longitudinal_axis == "Y"
    assert a_y.result.system_length_m == pytest.approx(a_x.result.system_length_m)


def test_la_longitud_del_sistema_crece_con_la_zapata_interior():
    """Control de dirección: alargar la zapata interior sobre el eje de la viga tiene
    que alargar el sistema, en los dos ejes."""
    for eje, borde in (("X", "X_MIN"), ("Y", "Y_MIN")):
        lay = _layout()
        lay = lay.model_copy(update={
            "longitudinal_axis": eje,
            "exterior": lay.exterior.model_copy(
                update={"anchor": EdgeAnchor(edge=borde)}),
        })
        r = _buscar(lay, _params())
        largos = {}
        for a in r.accepted:
            g = a.geometry
            longitudinal = g.interior_B_m if eje == "X" else g.interior_L_m
            largos.setdefault(longitudinal, set()).add(
                round(a.result.system_length_m, 6)
            )
        claves = sorted(largos)
        assert len(claves) >= 2, f"El barrido no varió la dimensión longitudinal ({eje})"
        for corta, larga in zip(claves, claves[1:]):
            assert min(largos[larga]) > min(largos[corta]), (
                f"Alargar la zapata interior no alargó el sistema sobre {eje}"
            )


# =========================================================================
# 11. Los tres conceptos no se confunden
# =========================================================================

def test_aceptada_no_significa_conforme():
    """El caso que el encargo prohíbe presentar mal: todas las aceptadas superan las
    verificaciones implementadas Y SIN EMBARGO ninguna es un diseño conforme, porque
    TBD-C1 no tiene criterio que aplicar."""
    r = _buscar(soil=SUELO_CON_FS)

    assert r.accepted, "El barrido debe aceptar alternativas"
    # Ninguna verificación implementada las descarta...
    assert all(not a.implemented_checks_status.discards for a in r.accepted)
    # ...y aun así ninguna puede informarse como conforme.
    assert r.accepted_and_compliant == []
    assert len(r.not_verified) == len(r.accepted)


def test_el_pendiente_que_bloquea_se_nombra():
    """No basta con decir NO VERIFICADO: hay que decir POR QUÉ, o el usuario no puede
    saber qué haría falta para cerrarlo."""
    r = _buscar()
    assert r.open_tbds() == ["TBD-C1"]
    assert all("TBD-C1" in a.open_tbds for a in r.accepted)


def test_el_pendiente_de_la_premisa_no_es_una_verificacion_fallida():
    """La entrada de TBD-C1 está en NO VERIFICADO, pero no es una comprobación que
    salga mal: es una comprobación que no existe. Si se contara como fallida, el
    programa estaría informando un problema de diseño donde hay un hueco normativo."""
    r = _buscar(soil=SUELO_CON_FS)
    a = r.accepted[0]

    premisa = next(e for e in a.result.trace.entries if e.open_tbd == "TBD-C1")
    assert premisa.status is CheckStatus.NOT_VERIFIED
    assert premisa.code_name.startswith("N/A")
    assert premisa not in a.result.trace.failing_entries()

    # Y al excluirla, lo que queda no es un fallo. Fase 10B: puede quedar NO VERIFICADO por
    # la estabilidad de las zapatas (E.020 art. 20.1 con cargas corregidas sin composición),
    # que es falta de información, no un pendiente del motor ni un FAIL.
    assert not a.result.trace.status_of_implemented_checks().discards


def test_TBD_C11_se_declara_aparte_de_TBD_C1():
    """Dos pendientes distintos no pueden fundirse en una sola etiqueta: cerrar uno no
    cierra el otro, y el informe tiene que poder decirlo."""
    lay = _layout().model_copy(
        update={"couple_transfer_mode": CoupleTransferMode.PAR_PURO_EN_ZAPATA}
    )
    r = _buscar(lay)
    assert r.accepted
    assert set(r.open_tbds()) == {"TBD-C1", "TBD-C11"}


def test_rechazada_y_no_verificada_no_se_mezclan():
    """Un candidato rechazado no aparece entre las aceptadas bajo ningún estado, y una
    aceptada no aparece entre los rechazos aunque esté NO VERIFICADO."""
    r = _buscar()
    ids_rechazados = {
        (x.geometry.exterior_B_m, x.geometry.exterior_L_m, x.geometry.exterior_h_m,
         x.geometry.interior_B_m, x.geometry.interior_L_m, x.geometry.interior_h_m)
        for x in r.rejected
    }
    ids_aceptados = {
        (a.geometry.exterior_B_m, a.geometry.exterior_L_m, a.geometry.exterior_h_m,
         a.geometry.interior_B_m, a.geometry.interior_L_m, a.geometry.interior_h_m)
        for a in r.accepted
    }
    assert not (ids_rechazados & ids_aceptados)


def test_el_resumen_de_estados_no_esconde_el_NO_VERIFICADO():
    """Lo que el informe debe mostrar en vez de «N alternativas encontradas»."""
    r = _buscar()
    assert r.status_summary() == {CheckStatus.NOT_VERIFIED.value: len(r.accepted)}


# =========================================================================
# 12. El tope es configurable y nunca silencioso
# =========================================================================

def test_el_tope_lo_fija_el_usuario():
    """No es un límite del producto: es un parámetro. Bajarlo tiene que recortar el
    barrido de verdad, no solo cambiar el mensaje."""
    r = _buscar(params=_params(max_systems=20))
    assert r.evaluated_count == 20
    assert r.truncated


def test_subir_el_tope_amplia_la_busqueda():
    """Control positivo del anterior: si el tope no gobernara, subirlo no cambiaría
    nada y el primer test pasaría por accidente."""
    bajo = _buscar(params=_params(max_systems=20))
    alto = _buscar(params=_params(max_systems=400))
    assert alto.evaluated_count > bajo.evaluated_count
    assert len(alto.accepted) >= len(bajo.accepted)


def test_el_truncamiento_nunca_es_silencioso():
    r = _buscar(params=_params(max_systems=20))
    assert r.truncated
    assert "NO es una búsqueda exhaustiva" in r.search_note
    assert "max_systems" in r.search_note


def test_un_barrido_completo_no_se_marca_truncado():
    r = _buscar(params=_params(max_systems=10_000))
    assert not r.truncated
    assert r.search_note == ""


def test_el_valor_por_defecto_no_es_un_limite_del_producto():
    """El default existe para no colgar la interfaz, no para imponer un tamaño de
    búsqueda: el campo tiene que ser editable y el default, solo un punto de partida."""
    campo = ConnectedSearchParameters.model_fields["max_systems"]
    assert campo.default == generador.DEFAULT_MAX_CONNECTED_SYSTEMS
    assert _params().max_systems == generador.DEFAULT_MAX_CONNECTED_SYSTEMS
    assert _params(max_systems=99).max_systems == 99


def test_el_mismo_peralte_no_se_impone_por_defecto():
    """Igualar peraltes es una práctica constructiva, no un supuesto del programa."""
    assert ConnectedSearchParameters.model_fields[
        "same_depth_both_footings"
    ].default is False


def test_faltar_un_dato_no_es_lo_mismo_que_un_TBD_abierto():
    """Hay DOS maneras de acabar en NO VERIFICADO y no se pueden confundir:

    * un pendiente del motor (TBD-C1): no existe criterio normativo que aplicar, y el
      proyectista no puede cerrarlo aportando datos;
    * un dato no declarado (el FS de volcamiento de E.050 art. 17.1): el criterio
      existe, falta el valor, y el proyectista SÍ lo cierra declarándolo.

    Decirle al usuario «NO VERIFICADO» sin distinguirlas le oculta que una de las dos
    está en su mano.

    El modelo es CUERPO_RIGIDO porque desde FORMULACION_VOLTEO (2026-09-19) es donde el
    volcamiento de la zapata de lindero conserva demanda: con ARTICULADO la viga recentra
    cada componente de la carga corregida —M = −P·offset— y la verificación se declara no
    aplicable, de modo que no habría nada que clasificar."""
    rigido = _layout(modelo=AnalysisModel.CUERPO_RIGIDO)
    sin_fs = _buscar(layout=rigido, soil=SUELO).accepted[0]
    con_fs = _buscar(layout=rigido, soil=SUELO_CON_FS).accepted[0]

    # Fase 10B: sin FS declarado rige E.020 art. 21 (1,5), de modo que ya no falta ese dato.
    # Lo que impide afirmar el volcamiento es la composición de las cargas corregidas
    # (E.020 art. 20.1): información que no está, NO un pendiente del motor.
    volc_sin = sin_fs.result.exterior.trace.by_id("overturning_x")
    volc_con = con_fs.result.exterior.trace.by_id("overturning_x")
    assert volc_sin.status is CheckStatus.NOT_VERIFIED
    assert volc_con.status is CheckStatus.NOT_VERIFIED
    for volc in (volc_sin, volc_con):
        assert volc.open_tbd is None, (
            "Una verificación que no puede afirmarse por falta de información no es un "
            "pendiente del motor: marcarla como TBD haría creer que el usuario no puede resolverla."
        )

    # ...y NO cierra TBD-C1: la alternativa sigue sin poder informarse como conforme.
    assert con_fs.open_tbds == ["TBD-C1"]
    assert con_fs.overall_status is CheckStatus.NOT_VERIFIED
    assert _buscar(layout=rigido, soil=SUELO_CON_FS).accepted_and_compliant == []
