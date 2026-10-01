"""Auditoría final de la Fase 4 — los invariantes que la revisión pidió fijar.

POR QUÉ ESTE ARCHIVO
====================
La auditoría encontró tres defectos que los tests existentes no detectaban, y los tres
tenían la misma forma: **una afirmación escrita a mano donde debía haber un resultado
derivado**. Un valor copiado de la fuente, unos residuos puestos a cero, una detección
que no detenía nada.

Los tests de este archivo atacan esa forma concreta. Cada uno intenta ROMPER el motor
de la manera que el defecto correspondiente permitía, y falla si el motor no se defiende.
"""

from __future__ import annotations

import inspect

import pytest

from engine.analysis import connected_statics
from engine.analysis.connected_statics import distribute_couple
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
from engine.foundation.connected_solver import (
    ConnectedFootingGeometry,
    solve_connected_footing,
)
from engine.foundation.self_weight import compute_self_weight
from engine.results.limitations import LIMITATION_REGISTRY
from engine.soil.contact_pressure import KernCheckModel

TON = 9.80665
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
CONC = MaterialConcrete(fc_MPa=21.0)
SUELO = SoilProfile(qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA,
                    gamma_kNm3=18.0, Df_m=1.50, source_notes="prueba")
DEPTH = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)
GEO = ConnectedFootingGeometry(
    exterior_B_m=3.40, exterior_L_m=2.60, exterior_h_m=0.90,
    interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
)


def _cargas(P: float, M: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                 P_kN=P, Mx_kNm=M)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=P * 1.4, Mx_kNm=M * 1.4)],
    )


def _layout(modelo=AnalysisModel.ARTICULADO,
            modo_par=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            M_ext: float = 0.0,
            self_weight=BeamSelfWeightMode.DESPRECIADO):
    return ConnectedFootingLayout(
        analysis_model=modelo, couple_transfer_mode=modo_par,
        exterior=ConnectedElement(label="Z1", column=COL, loads=_cargas(850.0, M_ext),
                                  anchor=EdgeAnchor(edge="X_MIN")),
        interior=ConnectedElement(label="Z2", column=COL, loads=_cargas(1100.0)),
        beam=ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10,
                                support_mode=BeamSupportMode.SIN_APOYO,
                                self_weight_mode=self_weight),
        axis_distance_m=6.0, longitudinal_axis="X",
    )


def _reparto(lay, geo=GEO):
    fp = lay.footprints(geo.exterior_B_m, geo.exterior_L_m, geo.exterior_h_m,
                        geo.interior_B_m, geo.interior_L_m, geo.interior_h_m)
    return distribute_couple(lay, fp, lay.exterior.loads.service[0],
                             lay.interior.loads.service[0], SUELO,
                             CONC.unit_weight_kNm3)


def _resolver(lay, geo=GEO):
    return solve_connected_footing(
        lay, geo, soil=SUELO, concrete=CONC, steel=MaterialSteel(fy_MPa=420.0),
        code=E060ConcreteCode(), contact_model=KernCheckModel(), depth_params=DEPTH,
    )


# =========================================================================
# 1. COUPLE TRANSFER MODE — obligatorio, sin default oculto
# =========================================================================

def test_ningun_modelo_de_entrada_tiene_default_para_el_modo_del_par():
    """Un default aquí significaría que el programa elige por el proyectista un cuerpo
    libre que ninguna norma arbitra."""
    campo = ConnectedFootingLayout.model_fields["couple_transfer_mode"]
    assert campo.is_required()
    assert campo.default is not None or campo.is_required()


def test_el_contrato_tambien_exige_el_modo():
    """Si `CoupleDistribution` lo tuviera opcional, un reparto podría viajar sin decir
    con qué cuerpo libre se resolvió."""
    assert connected_statics.CoupleDistribution.model_fields[
        "couple_transfer_mode"
    ].is_required()


def test_equilibrio_produce_residuo_de_carga_nulo():
    d = _reparto(_layout(modo_par=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION))
    assert d.expected_residual_kN == 0.0
    assert d.P_ext_corrected_kN + d.P_int_corrected_kN == pytest.approx(
        d.P_ext_kN + d.P_int_kN, rel=1e-12
    )


def test_par_puro_produce_residuo_exactamente_menos_delta_P():
    d = _reparto(_layout(modo_par=CoupleTransferMode.PAR_PURO_EN_ZAPATA))
    assert d.expected_residual_kN == pytest.approx(-d.delta_P_kN, rel=1e-12)
    falta = (d.P_ext_kN + d.P_int_kN) - (d.P_ext_corrected_kN + d.P_int_corrected_kN)
    assert falta == pytest.approx(d.delta_P_kN, rel=1e-9)


# =========================================================================
# 2. El par SALE de la formulación, no de una condición artificial
# =========================================================================

def test_el_par_puro_no_escribe_ninguna_formula_cerrada():
    """El defecto que esta auditoría encontró: la versión anterior copiaba
    `M_col − P·e1` de los apuntes y con ella importaba su convención de signos.
    El par tiene que salir de sumar momentos con la maquinaria del motor."""
    fuente = inspect.getsource(connected_statics._distribute_articulated)
    assert "moment_about_kNm" in fuente, (
        "El par debe derivarse sumando momentos, no escribiendo la fórmula"
    )
    assert "M_ext - combo_ext.P_kN * e1" not in fuente


def test_los_residuos_del_par_puro_no_estan_fijados_a_mano():
    """Estaban puestos a `0.0`, con lo que `closes` no verificaba nada en ese modo."""
    fuente = inspect.getsource(connected_statics._distribute_articulated)
    assert "res_F = res_M = 0.0" not in fuente
    d = _reparto(_layout(modo_par=CoupleTransferMode.PAR_PURO_EN_ZAPATA, M_ext=90.0))
    assert d.residual_force_kN == pytest.approx(0.0, abs=1e-9)
    assert d.residual_moment_kNm == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("modelo", list(AnalysisModel))
def test_un_signo_invertido_en_delta_P_rompe_el_invariante(modelo):
    """La prueba de que el invariante de conservación sirve: se le da la vuelta al
    signo y tiene que delatarlo, en los dos modelos."""
    d = _reparto(_layout(modelo=modelo))
    roto = d.model_copy(update={"P_int_corrected_kN": d.P_int_kN + d.delta_P_kN})
    assert not roto.conserves_load
    with pytest.raises(ValueError, match="no cuadra en carga vertical"):
        connected_statics._checked(roto)


def test_un_par_invertido_rompe_el_equilibrio_de_momentos():
    """Y la prueba de que el residuo de momentos sirve: con el par cambiado de signo,
    el cuerpo libre deja de cerrar."""
    d = _reparto(_layout(modo_par=CoupleTransferMode.PAR_PURO_EN_ZAPATA, M_ext=90.0))
    roto = d.model_copy(update={"residual_moment_kNm": -2.0 * d.M_couple_kNm})
    assert not roto.closes


def test_los_dos_modos_responden_al_momento_en_el_mismo_sentido():
    """EL DEFECTO CENTRAL DE ESTA AUDITORÍA. El mismo Mx del usuario movía la
    transferencia en sentidos opuestos según el modo, porque uno seguía la convención
    del motor y el otro la del libro. El benchmark no lo veía: reproducía la fuente por
    construcción."""
    variacion = {}
    for modo in CoupleTransferMode:
        bajo = _reparto(_layout(modo_par=modo, M_ext=-500.0)).delta_P_kN
        alto = _reparto(_layout(modo_par=modo, M_ext=+500.0)).delta_P_kN
        variacion[modo] = alto - bajo
    valores = list(variacion.values())
    assert valores[0] * valores[1] > 0, f"Sentidos opuestos: {variacion}"


def test_el_modelo_rigido_responde_al_momento_en_el_mismo_sentido_que_el_articulado():
    """EL DEFECTO MÁS SERIO QUE ENCONTRÓ ESTA AUDITORÍA, y la razón de que este test
    compare la REACCIÓN y no la transferencia: `delta_P` se define distinto en cada
    modelo, pero R_ext es la misma magnitud física en los dos.

    El momento de columna se inyectaba en el cuerpo libre sin convertirlo de la
    convención de E.050 art. 28.1 a la del cuerpo libre. El resultado: un mismo Mx
    AUMENTABA la reacción de la zapata de lindero en un modelo y la REDUCÍA en el otro.
    Físicamente solo puede reducirla: el momento empuja la resultante hacia el interior
    y descarga el borde."""
    def variacion(modelo):
        bajo = _reparto(_layout(modelo=modelo, M_ext=-500.0)).R_ext_kN
        alto = _reparto(_layout(modelo=modelo, M_ext=+500.0)).R_ext_kN
        return alto - bajo

    v_art = variacion(AnalysisModel.ARTICULADO)
    v_rig = variacion(AnalysisModel.CUERPO_RIGIDO)
    assert v_art * v_rig > 0, f"Sentidos opuestos: articulado {v_art}, rígido {v_rig}"
    assert v_art < 0, (
        "Un momento que desplaza la resultante hacia el interior DESCARGA la zapata de "
        "lindero. Si la cargara, el signo de la convención estaría invertido."
    )


def test_la_conversion_de_convencion_esta_en_un_solo_sitio():
    """Es una conversión fácil de olvidar en una llamada nueva. Tenerla con nombre y en
    un sitio es lo que impide que vuelva a divergir entre estrategias."""
    assert hasattr(connected_statics, "applied_moment_in_free_body")
    assert connected_statics.applied_moment_in_free_body(7.0) == -7.0


def test_par_puro_sigue_siendo_NO_VERIFICADO():
    """Que el pórtico recoja la rama cercana es una hipótesis sobre la superestructura
    que este motor no comprueba."""
    from engine.foundation.connected_solver import SCOPE_SYSTEM
    from engine.results.status import CheckStatus

    r = _resolver(_layout(modo_par=CoupleTransferMode.PAR_PURO_EN_ZAPATA))
    e = r.trace.by_id("couple_transfer_mode", scope=SCOPE_SYSTEM)
    assert e.status is CheckStatus.NOT_VERIFIED
    assert any("TBD-C11" in m for m in r.discard_reasons)


# =========================================================================
# 3. PESO PROPIO — ni una vez de más, ni una de menos
# =========================================================================

@pytest.mark.parametrize("modelo", list(AnalysisModel))
def test_el_peso_propio_no_se_cuenta_dos_veces(modelo):
    """EL TEST QUE LA AUDITORÍA PIDIÓ. Recorre el flujo entero y compara lo que llega
    al suelo con lo aplicado. Si el reparto sumara el peso propio Y el solver de zapata
    volviera a sumarlo, este número se pasaría exactamente en un peso propio."""
    r = _resolver(_layout(modelo=modelo))

    al_suelo = (
        r.exterior.contact_pressure.qavg_kPa * GEO.exterior_B_m * GEO.exterior_L_m
        + r.interior.contact_pressure.qavg_kPa * GEO.interior_B_m * GEO.interior_L_m
    )
    d = next(x for x in r.statics if x.combo_type == "SERVICIO")
    aplicado = (
        d.P_ext_kN + d.P_int_kN
        + r.exterior.self_weight.W_total_kN + r.interior.self_weight.W_total_kN
    )
    assert al_suelo == pytest.approx(aplicado, rel=1e-9), (
        f"Descuadre de {al_suelo - aplicado:+.3f} kN. Pesos propios: "
        f"{r.exterior.self_weight.W_total_kN:.3f} y {r.interior.self_weight.W_total_kN:.3f}."
    )


@pytest.mark.parametrize("modelo", list(AnalysisModel))
def test_el_peso_propio_del_reparto_es_el_del_modulo_compartido(modelo):
    """Si la estática usara su propia fórmula, el peso que reparte no sería el que
    después añade `evaluate_candidate` y el sistema no cerraría."""
    r = _resolver(_layout(modelo=modelo))
    d = next(x for x in r.statics if x.combo_type == "SERVICIO")
    if modelo is AnalysisModel.ARTICULADO:
        assert d.W_ext_kN == 0.0, "En articulado se agrupa y no entra en el reparto"
        return
    esperado_ext = compute_self_weight(
        GEO.exterior_B_m, GEO.exterior_L_m, GEO.exterior_h_m, SUELO.Df_m,
        CONC.unit_weight_kNm3, SUELO.gamma_kNm3,
    ).W_total_kN
    assert d.W_ext_kN == pytest.approx(esperado_ext, rel=1e-12)
    assert d.W_ext_kN == pytest.approx(r.exterior.self_weight.W_total_kN, rel=1e-12)


def test_la_carga_corregida_es_neta_para_que_el_solver_la_complete():
    r = _resolver(_layout(modelo=AnalysisModel.CUERPO_RIGIDO))
    d = next(x for x in r.statics if x.combo_type == "SERVICIO")
    assert d.P_ext_corrected_kN == pytest.approx(d.R_ext_kN - d.W_ext_kN, rel=1e-12)


def test_solo_existe_una_formula_de_peso_propio_en_todo_el_motor():
    import pathlib

    otros = []
    for ruta in pathlib.Path("engine").rglob("*.py"):
        if ruta.name == "self_weight.py":
            continue
        texto = ruta.read_text(encoding="utf-8")
        if "W_footing" in texto or "concrete_unit_weight_kNm3 *" in texto:
            otros.append(str(ruta))
    assert not otros, f"Segunda fórmula de peso propio en: {otros}"


# =========================================================================
# 4. DESPEGUE — detección, no resolución
# =========================================================================

def _layout_con_despegue():
    lay = _layout(modelo=AnalysisModel.CUERPO_RIGIDO, M_ext=-1400.0 * TON)
    return lay


def test_el_despegue_se_detecta():
    d = _reparto(_layout_con_despegue(),
                 ConnectedFootingGeometry(
                     exterior_B_m=2.60, exterior_L_m=2.60, exterior_h_m=0.60,
                     interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.60))
    assert d.uplift
    assert d.sigma_min_kPa < 0.0


def test_el_despegue_DETIENE_el_calculo():
    """DEFECTO QUE ESTA AUDITORÍA CORRIGIÓ. Antes se detectaba y se seguía adelante: las
    cargas corregidas salen de integrar un campo lineal sobre toda la huella, y con
    parte de ella levantada ese campo no describe nada. Con momentos grandes la carga
    corregida llegaba a resultar negativa y el solver de zapata abortaba con un error
    interno sobre tracción, que no le dice nada al usuario."""
    with pytest.raises(ValueError, match="DESPEGUE"):
        _resolver(_layout_con_despegue(),
                  ConnectedFootingGeometry(
                      exterior_B_m=2.60, exterior_L_m=2.60, exterior_h_m=0.60,
                      interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.60))


def test_el_mensaje_de_despegue_dice_que_NO_se_resuelve_contacto_unilateral():
    """La distinción que la auditoría pidió explicitar: detectar σ_min < 0 no es
    resolver contacto unilateral, y el usuario tiene que saber cuál de las dos cosas
    hace el programa."""
    with pytest.raises(ValueError) as exc:
        _resolver(_layout_con_despegue(),
                  ConnectedFootingGeometry(
                      exterior_B_m=2.60, exterior_L_m=2.60, exterior_h_m=0.60,
                      interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.60))
    texto = str(exc.value)
    assert "NO resuelve contacto" in texto
    assert "15.2" in texto


def test_el_despegue_esta_declarado_como_limitacion():
    lim = next(l for l in LIMITATION_REGISTRY if l.id == "connected_uplift_partial_contact")
    assert "no está implementado" in lim.description
    assert lim.can_cause_false_pass is False, (
        "No puede producir un falso PASS: interrumpe en vez de entregar números inválidos"
    )


def test_sin_despegue_el_calculo_sigue_su_curso():
    r = _resolver(_layout(modelo=AnalysisModel.CUERPO_RIGIDO))
    assert all(not d.uplift for d in r.statics)


# =========================================================================
# 5. k_s — no es entrada, ni oculta ni visible
# =========================================================================

def _presiones_con(qadm: float, gamma: float, Df: float, h: float = 0.0):
    lay = _layout(modelo=AnalysisModel.CUERPO_RIGIDO)
    h_ext = h or GEO.exterior_h_m
    h_int = h or GEO.interior_h_m
    fp = lay.footprints(GEO.exterior_B_m, GEO.exterior_L_m, h_ext,
                        GEO.interior_B_m, GEO.interior_L_m, h_int)
    suelo = SoilProfile(qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA,
                        gamma_kNm3=gamma, Df_m=Df, source_notes="x")
    d = distribute_couple(lay, fp, lay.exterior.loads.service[0],
                          lay.interior.loads.service[0], suelo, CONC.unit_weight_kNm3)
    return d.sigma_min_kPa, d.sigma_max_kPa


def test_variar_qadm_no_altera_las_presiones_de_contacto():
    """Confirmación de TBD-C2 sobre el resultado y no sobre la teoría. qadm es la única
    propiedad del suelo que describe su CAPACIDAD y no una carga: si el análisis
    dependiera de algo parecido a una rigidez, qadm sería el candidato. No la mueve."""
    assert _presiones_con(250.0, 18.0, 1.50) == pytest.approx(
        _presiones_con(900.0, 18.0, 1.50), rel=1e-12
    )


def test_variar_gamma_SI_altera_las_presiones_y_no_es_una_contradiccion():
    """Control positivo, para que el test anterior no se lea como «nada del suelo
    influye». γ sí influye, pero no como rigidez: pesa el RELLENO sobre las zapatas, que
    es carga vertical real. Si γ no moviera nada, faltaría ese peso."""
    base = _presiones_con(250.0, 18.0, 1.50)
    pesado = _presiones_con(250.0, 22.0, 1.50)
    assert pesado[1] > base[1], "Más relleno, más presión"


def test_sin_relleno_gamma_deja_de_influir():
    """Y la confirmación de que el efecto de γ es SOLO el relleno: con Df igual al
    peralte no hay relleno sobre ninguna zapata y γ deja de importar."""
    assert _presiones_con(250.0, 18.0, 0.60, h=0.60) == pytest.approx(
        _presiones_con(250.0, 22.0, 0.60, h=0.60), rel=1e-12
    )


def test_ninguna_entrada_del_motor_pide_el_modulo_de_balasto():
    campos = (
        set(ConnectedFootingLayout.model_fields)
        | set(SoilProfile.model_fields)
        | set(ConnectingBeamSpec.model_fields)
    )
    for prohibido in ("balasto", "subgrade", "k_s", "ks_", "winkler"):
        assert not any(prohibido in c.lower() for c in campos)


# =========================================================================
# 6. ORQUESTADOR — conoce el modelo para la traza, no para el reparto
# =========================================================================

def test_el_orquestador_no_conoce_las_estrategias_de_reparto():
    import engine.foundation.connected_solver as cs

    fuente = inspect.getsource(cs)
    for prohibido in ("_distribute_articulated", "_distribute_rigid_body",
                      "DISTRIBUTION_STRATEGIES"):
        assert prohibido not in fuente


def test_el_orquestador_si_conoce_el_modelo_para_la_premisa_fisica():
    """Y debe: la premisa de rigidez cambia de forma entre modelos, y TBD-C11 solo
    tiene sentido en el articulado. Eso es memoria de cálculo, no cálculo."""
    from engine.foundation.connected_solver import SCOPE_SYSTEM

    art = _resolver(_layout(modelo=AnalysisModel.ARTICULADO))
    rig = _resolver(_layout(modelo=AnalysisModel.CUERPO_RIGIDO))
    assert art.trace.by_id("uniform_pressure_premise", scope=SCOPE_SYSTEM) is not None
    assert rig.trace.by_id("rigid_body_premise", scope=SCOPE_SYSTEM) is not None
    assert art.trace.by_id("rigid_body_premise", scope=SCOPE_SYSTEM) is None
