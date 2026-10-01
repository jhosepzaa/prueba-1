"""FASE 4 — Contrato de las estrategias de análisis y cierre de 4A/4B.

POR QUÉ ESTE ARCHIVO EXISTE APARTE
==================================
Los tests de 4A y 4B verifican la estrategia ARTICULADA, que es la única
implementada. Este archivo verifica el **contrato** que cualquier estrategia debe
cumplir, incluida la de cuerpo rígido cuando se escriba.

La distinción importa. Los errores que aparecieron durante 4A/4B —signo invertido de
ΔP, momento transferido mal planteado, cortante tomado de secciones que pertenecen a
la zapata— no son errores de la estrategia articulada: son errores que CUALQUIER
estrategia puede cometer. Protegerlos con tests que solo corren la articulada
dejaría a la de cuerpo rígido sin red.

Por eso los invariantes se comprueban sobre el objeto del contrato y no dentro del
código que lo produce.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.analysis import connected_statics
from engine.analysis.connected_statics import (
    DISTRIBUTION_STRATEGIES,
    UNIFORM_PRESSURE_NOT_A_CODE_CHECK,
    CoupleDistribution,
    _checked,
    correct_loads,
    distribute_couple,
)
from engine.analysis.connecting_beam_statics import solve_connecting_beam
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
    SCOPE_SYSTEM,
    ConnectedFootingGeometry,
    solve_connected_footing,
)
from engine.results.limitations import LIMITATION_REGISTRY
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel

CODE = E060ConcreteCode()
COL50 = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
DEPTH = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)


def _viga(
    self_weight=BeamSelfWeightMode.DESPRECIADO,
    support=BeamSupportMode.SIN_APOYO,
) -> ConnectingBeamSpec:
    # Fase 9a: con EXPLICITO la cota vertical es obligatoria. Aquí se fija HV-1 (fondo de
    # la viga en la base común); los tests de 9a/9c recorren las otras cotas.
    z_b = 0.0 if self_weight is BeamSelfWeightMode.EXPLICITO else None
    return ConnectingBeamSpec(
        b_m=0.35, h_m=1.20, d_m=1.10,
        support_mode=support, self_weight_mode=self_weight, soffit_above_base_m=z_b,
    )


def _loads(P_serv: float, P_fact: float):
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P_serv)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P_fact)],
    )


def _layout(modelo=AnalysisModel.ARTICULADO, beam=None, clearance=0.0,
            modo_par=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION):
    return ConnectedFootingLayout(
        analysis_model=modelo,
        exterior=ConnectedElement(
            label="Z1", column=COL50, loads=_loads(850.0, 1240.0),
            anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=clearance),
        ),
        interior=ConnectedElement(label="Z2", column=COL50, loads=_loads(1100.0, 1600.0)),
        beam=beam or _viga(),
        couple_transfer_mode=modo_par,
        axis_distance_m=6.0, longitudinal_axis="X",
    )


def _reparto(layout=None, L1=2.40):
    lay = layout or _layout()
    fp = lay.footprints(L1, 2.60, 0.90, 2.60, 2.60, 0.70)
    suelo = SoilProfile(qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA,
                        gamma_kNm3=18.0, Df_m=1.50, source_notes="prueba")
    return distribute_couple(lay, fp, lay.exterior.loads.factored[0],
                             lay.interior.loads.factored[0], suelo)


def _resolver(layout=None, geometry=None, soil=None):
    return solve_connected_footing(
        layout or _layout(),
        geometry or ConnectedFootingGeometry(
            exterior_B_m=3.40, exterior_L_m=2.60, exterior_h_m=0.90,
            interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
        ),
        soil=soil or SoilProfile(
            qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
            Df_m=1.50, source_notes="prueba",
        ),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=KernCheckModel(), depth_params=DEPTH,
    )


# =========================================================================
# 1. Los invariantes se comprueban sobre el CONTRATO, no sobre la estrategia
# =========================================================================

def _falsear(d: CoupleDistribution, **cambios) -> CoupleDistribution:
    return d.model_copy(update=cambios)


def test_un_reparto_que_no_conserva_carga_se_rechaza():
    """Regresión del error real: ΔP se sumaba a las DOS zapatas, creando carga de la
    nada. El invariante lo delata sin importar qué estrategia lo produjo."""
    d = _reparto()
    roto = _falsear(d, P_int_corrected_kN=d.P_int_kN + d.delta_P_kN)
    assert not roto.conserves_load
    with pytest.raises(ValueError, match="no cuadra en carga vertical"):
        _checked(roto)


def test_un_reparto_que_no_cierra_en_fuerzas_se_rechaza():
    roto = _falsear(_reparto(), residual_force_kN=50.0)
    with pytest.raises(ValueError, match="no cierra"):
        _checked(roto)


def test_un_reparto_que_no_cierra_en_momentos_se_rechaza():
    roto = _falsear(_reparto(), residual_moment_kNm=500.0)
    with pytest.raises(ValueError, match="no cierra"):
        _checked(roto)


def test_el_invariante_de_conservacion_admite_el_peso_propio_de_la_viga():
    """Es lo ÚNICO que puede aumentar el total: una carga real que antes no estaba.
    El test de 4A solo cubría W = 0, de modo que la forma general no estaba fijada."""
    for modo in BeamSelfWeightMode:
        d = _reparto(_layout(beam=_viga(self_weight=modo)))
        esperado = d.beam_self_weight_kN
        obtenido = (
            d.P_ext_corrected_kN + d.P_int_corrected_kN - d.P_ext_kN - d.P_int_kN
        )
        assert obtenido == pytest.approx(esperado, abs=1e-9)
        assert d.conserves_load


def test_solo_el_modo_explicito_mete_peso_de_viga_en_el_equilibrio():
    pesos = {
        modo: _reparto(_layout(beam=_viga(self_weight=modo))).beam_self_weight_kN
        for modo in BeamSelfWeightMode
    }
    assert pesos[BeamSelfWeightMode.EXPLICITO] > 0.0
    assert pesos[BeamSelfWeightMode.EN_CARGAS_DE_COLUMNA] == 0.0
    assert pesos[BeamSelfWeightMode.DESPRECIADO] == 0.0


def test_el_verificador_de_invariantes_corre_en_el_camino_normal(monkeypatch):
    """Si `distribute_couple` no pasara por `_checked`, los invariantes serían
    decorativos."""
    llamadas = []
    original = connected_statics._checked

    def espia(d):
        llamadas.append(d)
        return original(d)

    monkeypatch.setattr(connected_statics, "_checked", espia)
    _reparto()
    assert len(llamadas) == 1


# =========================================================================
# 2. Las dos estrategias existen; la de cuerpo rígido sigue bloqueada
# =========================================================================

def test_hay_exactamente_una_estrategia_por_modelo():
    assert set(DISTRIBUTION_STRATEGIES) == set(AnalysisModel)


def test_la_estrategia_de_cuerpo_rigido_ya_resuelve():
    """Estuvo bloqueada mientras TBD-C2 seguía abierto. El problema de aplicación 2 de
    los apuntes lo resolvió y la estrategia se implementó contra esa fuente."""
    assert AnalysisModel.CUERPO_RIGIDO in DISTRIBUTION_STRATEGIES
    d = _reparto(_layout(modelo=AnalysisModel.CUERPO_RIGIDO))
    assert d.analysis_model is AnalysisModel.CUERPO_RIGIDO
    assert d.closes and d.conserves_load


def test_la_estrategia_rigida_cita_su_fuente_y_sus_hipotesis():
    """La elección del modelo no es normativa: viene declarada en el enunciado de la
    fuente, y las hipótesis que la sostienen tienen que estar donde se lean."""
    doc = connected_statics._distribute_rigid_body.__doc__
    assert "CR2-93-134" in doc, "Debe citar la fuente primaria"
    assert "para el conjunto de 2 zapatas" in doc, "Y la frase que declara el modelo"
    for marca in ("H1", "H2", "H3", "F1", "F2", "F3"):
        assert marca in doc, f"Falta la hipotesis o consecuencia {marca}"


def test_el_modulo_de_balasto_no_es_una_entrada_del_motor():
    """Resolución de TBD-C2: para un cuerpo rígido k_s se cancela en el equilibrio, de
    modo que el motor NO puede pedirlo. Se comprueba sobre los modelos de ENTRADA, que
    es donde se vería si alguien lo reintrodujera."""
    campos = set(ConnectedFootingLayout.model_fields) | set(SoilProfile.model_fields)
    for prohibido in ("subgrade", "balasto", "k_s", "ks_"):
        assert not any(prohibido in c for c in campos), (
            f"«{prohibido}» aparece como entrada: el cuerpo rígido no necesita el módulo "
            f"de balasto, porque se cancela en el equilibrio."
        )
    assert "cancela" in connected_statics._rigid_pressure.__doc__

def test_el_orquestador_resuelve_los_dos_modelos():
    for modelo in AnalysisModel:
        r = _resolver(_layout(modelo=modelo))
        assert r.statics, f"El modelo {modelo.value} debe producir reparto"


def test_el_orquestador_no_ramifica_EL_REPARTO_por_modelo():
    """El contrato existe para que el solver no tenga que saber qué estrategia resolvió
    el reparto: llama a `distribute_couple` y recibe siempre el mismo objeto.

    Lo que sí depende del modelo es la TRAZA —la premisa de rigidez cambia de forma y
    TBD-C11 solo tiene sentido en el articulado—, y eso es presentación, no cálculo."""
    import engine.foundation.connected_solver as cs

    fuente = inspect.getsource(cs)
    assert "_distribute_articulated" not in fuente
    assert "_distribute_rigid_body" not in fuente
    assert "DISTRIBUTION_STRATEGIES" not in fuente


def test_el_momento_de_junta_forma_parte_del_contrato():
    """Es el campo que distinguirá a los dos modelos. En articulado vale cero porque
    hay una rótula; se verifica, no se supone."""
    d = _reparto()
    assert d.M_cut_kNm == 0.0
    b = solve_connecting_beam(_layout(), d)
    assert b.M_cut_declared_kNm == 0.0
    assert b.cut_moment_consistent, (
        "El momento del diagrama y el declarado por el reparto deben coincidir"
    )


def test_la_estatica_de_la_viga_contrasta_el_momento_de_junta():
    """Control negativo: si el reparto declarara otro momento, la comprobación cruzada
    debe delatarlo. Es lo que hará útil este campo cuando llegue cuerpo rígido."""
    d = _reparto()
    mentiroso = _falsear(d, M_cut_kNm=500.0)
    b = solve_connecting_beam(_layout(), mentiroso)
    assert not b.cut_moment_consistent


# =========================================================================
# 3. TBD-C1 — la premisa no se convierte en verificación normativa
# =========================================================================

def test_la_premisa_sigue_NO_VERIFICADO():
    e = _resolver().trace.by_id("uniform_pressure_premise", scope=SCOPE_SYSTEM)
    assert e.status is CheckStatus.NOT_VERIFIED


def test_la_premisa_no_se_atribuye_a_ningun_articulo():
    """La premisa no puede presentarse como respaldada por ningún artículo.

    MATIZ QUE LA AUDITORÍA NORMATIVA DEL 2026-09-19 OBLIGÓ A INTRODUCIR. Hasta entonces la
    entrada decía «Sin artículo», y eso era inexacto en la otra dirección: E.060 §15.2.6
    EXIGE «evaluar[…] el comportamiento de éstas de acuerdo a su rigidez y la del conjunto
    suelo-cimentación». La pregunta SÍ es normativa; lo que no existe es el criterio con que
    responderla.

    Lo que este test sigue impidiendo es lo de siempre: que la premisa se dé por verificada
    apoyándose en un artículo. Por eso se exige a la vez que se cite §15.2.6 —para no ocultar
    que la norma lo pide— y que la entrada siga declarándose como hipótesis de modelación, sin
    norma que la respalde, en NO VERIFICADO. Citar §21.12.3.2 como si lo verificara seguiría
    siendo fabricar un requisito: ese artículo fija una dimensión mínima, no una rigidez."""
    e = _resolver().trace.by_id("uniform_pressure_premise", scope=SCOPE_SYSTEM)
    assert e.code_name.startswith("N/A"), (
        "La premisa no tiene norma que la respalde: el `code_name` no puede ser una norma."
    )
    assert e.status is CheckStatus.NOT_VERIFIED
    assert "15.2.6" in e.code_reference, (
        "Debe citarse el artículo que EXIGE evaluar la rigidez; callarlo ocultaba que la "
        "pregunta es normativa."
    )
    assert "sin prescribir método ni umbral" in e.code_reference, (
        "Y debe decirse en la misma frase que ese artículo no da criterio: si no, se lee "
        "como si la verificación estuviera respaldada."
    )
    assert any(UNIFORM_PRESSURE_NOT_A_CODE_CHECK in h for h in e.hypotheses)


def test_el_requisito_dimensional_de_la_viga_si_es_normativo_y_va_aparte():
    """§21.12.3.2 SÍ es verificable y tiene su propio PASS/FAIL, en la traza de la
    viga. Separarlos es lo que impide que el lector los confunda."""
    r = _resolver()
    dimensional = r.trace.by_id("beam_dimension", scope="viga")
    assert dimensional is not None
    assert dimensional.status in (CheckStatus.PASS, CheckStatus.FAIL)
    assert "21.12.3.2" in dimensional.code_reference
    premisa = r.trace.by_id("uniform_pressure_premise", scope=SCOPE_SYSTEM)
    assert premisa.status is CheckStatus.NOT_VERIFIED
    assert dimensional.id != premisa.id


def test_la_premisa_esta_en_el_catalogo_de_limitaciones_con_falso_pass():
    """El catálogo es lo que la API expone como «alcance». Una limitación capaz de
    producir un falso PASS que no figure ahí es invisible para el usuario."""
    lim = next(
        l for l in LIMITATION_REGISTRY if l.id == "connected_uniform_pressure_premise"
    )
    assert lim.can_cause_false_pass is True
    assert lim.enforced_by == "uniform_pressure_premise"


def test_la_premisa_impide_el_PASS_del_sistema():
    assert _resolver().overall_status is not CheckStatus.PASS


# =========================================================================
# 4. TBD-C4 / C5 — declaración obligatoria, sin valor por defecto
# =========================================================================

def test_los_dos_modos_de_la_viga_son_obligatorios():
    """Como `analysis_model`: ninguna norma los prescribe, de modo que no puede haber
    un valor por defecto que decida por el proyectista."""
    with pytest.raises(ValidationError) as exc:
        ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10)
    campos = {e["loc"][0] for e in exc.value.errors()}
    assert {"support_mode", "self_weight_mode"} <= campos


def test_declarar_apoyo_en_suelo_se_RECHAZA():
    """Decisión 5 sobre TBD-C4 (2026-09-20). Antes producía NO VERIFICADO; ahora se rechaza.

    El NO VERIFICADO decía la verdad pero entregaba, con una nota al pie, el diseño de OTRO
    problema: una viga que salva el vano sin apoyo. Ignorar el apoyo sobrestima ΔP y deja la
    zapata interior menos cargada de lo que estaría, del lado inseguro. Rechazar es la
    respuesta honesta mientras no se defina el modelo resistente del apoyo."""
    with pytest.raises(ValueError, match="APOYA_EN_SUELO"):
        _resolver(_layout(beam=_viga(support=BeamSupportMode.APOYA_EN_SUELO)))


def test_sin_apoyo_no_degrada_el_estado():
    e = _resolver().trace.by_id("beam_support_mode", scope=SCOPE_SYSTEM)
    assert e.status is CheckStatus.INFO


def test_el_riesgo_de_apoyo_en_suelo_es_sobre_la_zapata_interior():
    """La dirección del error importa: ignorar el apoyo sobrestima ΔP, y como la carga
    corregida de la interior es P_int − ΔP, la deja MENOS cargada. La exterior queda
    del lado seguro; la interior no."""
    d = _reparto()
    assert d.delta_P_kN > 0.0
    assert d.P_int_corrected_kN == pytest.approx(d.P_int_kN - d.delta_P_kN)
    assert d.P_ext_corrected_kN > d.P_ext_kN


def test_el_modo_de_peso_propio_se_registra_aunque_se_desprecie():
    """Un peso que no aparece en ninguna parte y del que la memoria no dice nada es
    indistinguible de un olvido."""
    r = _resolver(_layout(beam=_viga(self_weight=BeamSelfWeightMode.DESPRECIADO)))
    e = r.trace.by_id("beam_self_weight_mode", scope=SCOPE_SYSTEM)
    assert e is not None
    assert "DESPRECIADO" in e.equation_substituted
    assert any("omisión consciente" in h for h in e.hypotheses)


def test_el_modo_explicito_publica_el_peso_en_la_traza():
    r = _resolver(_layout(beam=_viga(self_weight=BeamSelfWeightMode.EXPLICITO)))
    e = r.trace.by_id("beam_self_weight_mode", scope=SCOPE_SYSTEM)
    assert e.result_value > 0.0
    assert e.result_unit == "kN"


def test_el_modo_en_cargas_de_columna_no_vuelve_a_sumarlo():
    r = _resolver(_layout(beam=_viga(self_weight=BeamSelfWeightMode.EN_CARGAS_DE_COLUMNA)))
    e = r.trace.by_id("beam_self_weight_mode", scope=SCOPE_SYSTEM)
    assert e.result_value == 0.0
    assert any("dos veces" in h for h in e.hypotheses)


# =========================================================================
# 5. EdgeAnchor durante TODO el barrido, a través del solver completo
# =========================================================================

# El barrido llega hasta 4.80 m y no hasta 5.00: con la distancia entre ejes de este
# layout, una zapata de lindero de 5.00 m alcanza la huella interior y el sistema deja
# de ser realizable. El caso no se pierde: lo cubre
# `test_una_zapata_de_lindero_demasiado_larga_alcanza_la_huella_interior`.
@pytest.mark.parametrize("B", [2.00, 2.60, 3.20, 3.80, 4.40, 4.80])
@pytest.mark.parametrize("holgura", [0.0, 0.10])
def test_la_condicion_de_borde_sobrevive_al_barrido_completo(B, holgura):
    """No basta comprobarlo sobre `EdgeAnchor` aislado: lo que importa es que la
    geometría que llega al motor de zapata la conserve."""
    lay = _layout(clearance=holgura)
    r = _resolver(lay, ConnectedFootingGeometry(
        exterior_B_m=B, exterior_L_m=2.60, exterior_h_m=0.90,
        interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
    ))
    placement = lay.exterior.placement_for(B, 2.60)
    izq, der = placement.cantilevers_x(B)
    assert izq == pytest.approx(holgura, abs=1e-12)
    assert izq + der + COL50.bx_m == pytest.approx(B, abs=1e-12)
    assert r.L1_m == pytest.approx(B)


def test_una_zapata_de_lindero_demasiado_larga_alcanza_la_huella_interior():
    """Límite superior del barrido de B. Con los ejes a 6.00 m y una zapata interior de
    2.60 m, la de lindero no puede pasar de 4.95 m sin invadir la huella vecina: el
    sistema se rechaza por geometría, no se resuelve con un área de apoyo inventada."""
    lay = _layout(clearance=0.0)
    with pytest.raises(ValueError, match="GEOMETRIA_IMPOSIBLE"):
        _resolver(lay, ConnectedFootingGeometry(
            exterior_B_m=5.00, exterior_L_m=2.60, exterior_h_m=0.90,
            interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
        ))


@pytest.mark.parametrize("B", [2.00, 3.20, 4.40])
def test_la_excentricidad_crece_con_B_como_exige_la_geometria(B):
    """e1 = B/2 − a. Si el desplazamiento se hubiera congelado, e1 dejaría de seguir a
    B y el reparto describiría otra estructura."""
    d = _reparto(L1=B)
    assert d.e1_m == pytest.approx(B / 2.0 - 0.25, abs=1e-12)


def test_la_presion_uniforme_se_mantiene_en_todo_el_barrido():
    """La premisa del modelo no puede depender de la geometría que salga del barrido."""
    for B in (2.60, 3.40, 4.20):
        r = _resolver(geometry=ConnectedFootingGeometry(
            exterior_B_m=B, exterior_L_m=2.60, exterior_h_m=0.90,
            interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
        ))
        cp = r.exterior.contact_pressure
        assert cp.qmax_kPa == pytest.approx(cp.qmin_kPa, rel=1e-9)


def test_el_par_transmitido_sigue_la_regla_M_igual_a_menos_P_por_offset():
    """Regresión del segundo error real: entregar momento CERO no daba presión
    uniforme, porque la columna descentrada aporta P·offset por geometría."""
    for B in (2.60, 3.40, 4.20):
        lay = _layout()
        d = _reparto(lay, L1=B)
        offset = lay.exterior.placement_for(B, 2.60).offset_x_m
        assert d.M_ext_corrected_kNm == pytest.approx(
            -d.P_ext_corrected_kN * offset, rel=1e-12
        )


# =========================================================================
# 6. Cortante de la viga: siempre fuera de las zapatas
# =========================================================================

@pytest.mark.parametrize("B", [2.00, 3.00, 4.00])
def test_las_secciones_de_diseno_de_la_viga_quedan_fuera_de_la_zapata(B):
    """Regresión del tercer error real: el cortante de diseño se tomaba de secciones
    interiores a la zapata y daba el cortante de la zapata, no el de la viga."""
    lay = _layout()
    d = _reparto(lay, L1=B)
    b = solve_connecting_beam(lay, d)
    assert b.s_beam_start_m == pytest.approx(d.L1_m)
    assert b.s_V_design_m >= d.L1_m - 1e-9
    assert b.s_M_max_negative_m >= d.L1_m - 1e-9
    assert b.V_design_kN == pytest.approx(abs(d.delta_P_kN), rel=1e-9)


def test_el_cortante_de_la_viga_es_muy_menor_que_el_de_la_zapata():
    """Comprobación de magnitud: si alguien volviera a tomarlo de la zapata, el valor
    saltaría al orden de la carga de columna."""
    d = _reparto()
    b = solve_connecting_beam(_layout(), d)
    assert b.V_design_kN < 0.4 * d.P_ext_kN


# =========================================================================
# 7. Ningún módulo de conectada usa `beam_diagram`
# =========================================================================

@pytest.mark.parametrize("ruta", [
    "engine/analysis/connected_statics.py",
    "engine/analysis/connecting_beam_statics.py",
    "engine/foundation/connected_solver.py",
    "engine/domain/connected_layout.py",
])
def test_ningun_modulo_de_conectada_usa_beam_diagram(ruta):
    codigo = "\n".join(
        l for l in Path(ruta).read_text(encoding="utf-8").splitlines()
        if not l.strip().startswith("#")
    )
    assert "build_beam_diagram" not in codigo
    assert "import beam_diagram" not in codigo
    assert "from engine.analysis.beam_diagram" not in codigo
