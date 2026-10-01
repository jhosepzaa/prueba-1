"""FASE 4B — Integración de la zapata conectada con los motores existentes.

EL RIESGO QUE ESTOS TESTS CUBREN
================================
`connected_solver` orquesta tres motores que ya existen y están congelados. La
tentación, cada vez que falta un número, es calcularlo «al paso» dentro del
orquestador: un As aquí, un Vc allá. Al cabo de unas semanas hay dos versiones de la
misma ecuación y solo una recibe las correcciones.

Estos tests fijan que el solver de conectada NO calcula nada de ingeniería. Lo
demuestran de tres maneras independientes, el mismo patrón que en la Fase 3 probó
que la zapata combinada reutiliza el motor de vigas:

  1. Interceptando las llamadas: si hubiera una copia, el espía no se dispararía.
  2. Reproduciendo el resultado dígito a dígito llamando al motor a mano.
  3. Escaneando el fuente en busca de una segunda implementación.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import engine.foundation.connected_solver as connected_solver
from engine.beam import connecting_beam as beam_module
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
from engine.foundation import depth_solver as depth_module
from engine.foundation.connected_solver import (
    SCOPE_BEAM,
    SCOPE_EXTERIOR,
    SCOPE_INTERIOR,
    SCOPE_SYSTEM,
    ConnectedFootingGeometry,
    solve_connected_footing,
)
from engine.results.status import CheckStatus

CODE = E060ConcreteCode()
COL50 = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
DEPTH = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)


def _viga(
    self_weight=BeamSelfWeightMode.DESPRECIADO,
    support=BeamSupportMode.SIN_APOYO,
) -> ConnectingBeamSpec:
    return ConnectingBeamSpec(
        b_m=0.35, h_m=1.20, d_m=1.10,
        support_mode=support, self_weight_mode=self_weight,
    )


def _soil(Df_m: float = 1.50, qadm: float = 250.0, rock: bool = False) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
        Df_m=Df_m, founded_on_rock=rock, source_notes="prueba",
    )


def _loads(P_serv: float, P_fact: float):
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P_serv)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P_fact)],
    )


def _layout(**kw) -> ConnectedFootingLayout:
    return ConnectedFootingLayout(
        analysis_model=kw.get("modelo", AnalysisModel.ARTICULADO),
        exterior=ConnectedElement(
            label="Z1", column=COL50, loads=kw.get("loads_ext", _loads(850.0, 1240.0)),
            anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=0.0),
        ),
        interior=ConnectedElement(
            label="Z2", column=COL50, loads=kw.get("loads_int", _loads(1100.0, 1600.0))
        ),
        beam=kw.get("beam", _viga()),
        couple_transfer_mode=kw.get(
            "modo_par", CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION
        ),
        axis_distance_m=kw.get("S", 6.0), longitudinal_axis="X",
    )


def _geom(**kw) -> ConnectedFootingGeometry:
    base = dict(
        exterior_B_m=3.40, exterior_L_m=2.60, exterior_h_m=0.90,
        interior_B_m=2.60, interior_L_m=2.60, interior_h_m=0.70,
    )
    base.update(kw)
    return ConnectedFootingGeometry(**base)


def _resolver(layout=None, geometry=None, soil=None):
    return solve_connected_footing(
        layout or _layout(), geometry or _geom(),
        soil=soil or _soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=__import__(
            "engine.soil.contact_pressure", fromlist=["KernCheckModel"]
        ).KernCheckModel(),
        depth_params=DEPTH,
    )


# =========================================================================
# 1. El solver llama a los motores existentes, no a copias
# =========================================================================

def test_las_dos_zapatas_pasan_por_evaluate_candidate(monkeypatch):
    llamadas: list[dict] = []
    original = connected_solver.evaluate_candidate

    def espia(**kwargs):
        llamadas.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(connected_solver, "evaluate_candidate", espia)
    _resolver()

    assert len(llamadas) == 2, "Una llamada por zapata, al motor compartido"
    assert {round(k["B_m"], 3) for k in llamadas} == {3.40, 2.60}


def test_la_viga_pasa_por_design_connecting_beam(monkeypatch):
    llamadas: list[dict] = []
    original = connected_solver.design_connecting_beam

    def espia(**kwargs):
        llamadas.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(connected_solver, "design_connecting_beam", espia)
    _resolver()

    assert len(llamadas) == 1
    assert llamadas[0]["b_m"] == pytest.approx(0.35)
    assert llamadas[0]["Mu_negative_kNm"] > 0.0


def test_los_simbolos_importados_son_los_de_los_modulos_originales():
    assert connected_solver.evaluate_candidate is depth_module.evaluate_candidate
    assert connected_solver.design_connecting_beam is beam_module.design_connecting_beam


def test_el_orquestador_no_reimplementa_ninguna_ecuacion():
    """Ninguna de estas expresiones puede aparecer en el orquestador: cada una vive
    en un motor que ya existe."""
    fuente = inspect.getsource(connected_solver)
    prohibidos = [
        "0.85",           # bloque de compresión — §10.2.7
        "sqrt",           # Vc y fr
        "0.17",           # ec. 11-3
        "0.62",           # fr de §10.5.1
        "def _flexure", "def _shear", "def _punching", "def _as_",
        "MIN_FOUNDATION_DEPTH_M =",
        "rebar", "Rebar",
    ]
    for p in prohibidos:
        assert p not in fuente, (
            f"«{p}» aparece en connected_solver: ese cálculo pertenece a un motor "
            f"existente y debe llamarse, no reescribirse."
        )


# =========================================================================
# 2. Los números coinciden con los de los motores llamados a mano
# =========================================================================

def test_la_zapata_exterior_coincide_digito_a_digito():
    """Se reconstruye la llamada con las cargas corregidas que el propio solver
    publicó y debe salir exactamente lo mismo."""
    from engine.analysis.connected_statics import correct_loads
    from engine.soil.contact_pressure import KernCheckModel

    lay, geo = _layout(), _geom()
    r = _resolver(lay, geo)

    corregidas = correct_loads(
        lay,
        lay.footprints(geo.exterior_B_m, geo.exterior_L_m, geo.exterior_h_m,
                       geo.interior_B_m, geo.interior_L_m, geo.interior_h_m),
        _soil(), MaterialConcrete(fc_MPa=21.0).unit_weight_kNm3,
    )
    esperado = depth_module.evaluate_candidate(
        B_m=geo.exterior_B_m, L_m=geo.exterior_L_m, h_m=geo.exterior_h_m,
        column=lay.exterior.column, soil=_soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=corregidas.exterior, code=CODE, contact_model=KernCheckModel(),
        depth_params=DEPTH,
        placement=lay.exterior.placement_for(geo.exterior_B_m, geo.exterior_L_m),
    )
    assert r.exterior.contact_pressure.qmax_kPa == pytest.approx(
        esperado.contact_pressure.qmax_kPa, rel=1e-12
    )
    assert r.exterior.flexure_x.Mu_kNm == pytest.approx(esperado.flexure_x.Mu_kNm, rel=1e-12)
    assert r.exterior.punching.ratio == pytest.approx(esperado.punching.ratio, rel=1e-12)
    assert r.exterior.overall_status is esperado.overall_status


def test_la_viga_coincide_digito_a_digito():
    """Se reconstruye la llamada con las solicitaciones que el propio solver publicó
    y debe salir exactamente lo mismo."""
    lay, geo = _layout(), _geom()
    r = _resolver(lay, geo)

    esperado = beam_module.design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10,
        clear_span_m=6.0 - 0.25 - 0.25,
        Mu_negative_kNm=max(b.M_max_negative_kNm for b in r.beam_statics),
        Mu_positive_kNm=max(b.M_max_positive_kNm for b in r.beam_statics),
        Vu_kN=max(b.V_design_kN for b in r.beam_statics),
        fc_MPa=21.0, fy_MPa=420.0, longitudinal_db_mm=25.4,
        sum_Pu_kN=max(c.P_ext_corrected_kN for c in r.statics
                      if c.combo_type == "FACTORIZADA"),
        seismic=beam_module.SeismicContext(qadm_kPa=250.0),
    )
    assert r.beam.As_negative_m2 == pytest.approx(esperado.As_negative_m2, rel=1e-12)
    assert r.beam.As_positive_m2 == pytest.approx(esperado.As_positive_m2, rel=1e-12)
    assert r.beam.shear.Vc_kN == pytest.approx(esperado.shear.Vc_kN, rel=1e-12)
    assert r.beam.shear.equation_substituted == esperado.shear.equation_substituted
    assert r.beam.status is esperado.status


def test_la_luz_libre_de_la_viga_es_entre_caras_de_columna():
    """§21.12.3.2 mide sobre el «espacio libre entre columnas conectadas»."""
    r = _resolver()
    assert r.beam.clear_span_m == pytest.approx(6.0 - 0.25 - 0.25)


# =========================================================================
# 3. La condición de borde se mantiene durante el barrido
# =========================================================================

@pytest.mark.parametrize("B", [2.60, 3.00, 3.40, 4.00, 4.60])
def test_la_columna_de_lindero_sigue_al_ras_para_cualquier_B(B):
    """Es la razón por la que la fase no usa un `ColumnPlacement` fijo: con B
    variable, un desplazamiento constante despegaría la columna del lindero."""
    lay = _layout()
    r = _resolver(lay, _geom(exterior_B_m=B))
    placement = lay.exterior.placement_for(B, r.geometry.exterior_L_m)
    voladizo_izq, _ = placement.cantilevers_x(B)
    assert voladizo_izq == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("B", [2.60, 3.40, 4.60])
def test_el_reparto_usa_la_dimension_longitudinal_de_la_geometria(B):
    r = _resolver(geometry=_geom(exterior_B_m=B))
    assert r.L1_m == pytest.approx(B)


def test_una_geometria_donde_la_columna_no_cabe_se_rechaza():
    with pytest.raises(ValueError, match="no cabe"):
        _resolver(geometry=_geom(exterior_B_m=0.40))


# =========================================================================
# 4. La presión bajo la zapata exterior resulta uniforme
# =========================================================================

def test_la_zapata_exterior_recibe_presion_uniforme():
    """Es la premisa del modelo articulado, y sale del motor de zapata SIN
    modificarlo: el par que la viga transmite centra la resultante."""
    r = _resolver()
    cp = r.exterior.contact_pressure
    assert cp.qmax_kPa == pytest.approx(cp.qmin_kPa, rel=1e-9)
    assert r.exterior.eccentricity_governing.ex_m == pytest.approx(0.0, abs=1e-9)


def test_la_zapata_interior_queda_aliviada_por_el_contrapeso():
    r = _resolver()
    servicio = next(d for d in r.statics if d.combo_type == "SERVICIO")
    assert servicio.P_int_corrected_kN < servicio.P_int_kN


# =========================================================================
# 5. Traza con ámbito, y el defecto latente de `by_id` cerrado
# =========================================================================

def test_la_traza_separa_los_cuatro_ambitos():
    r = _resolver()
    assert r.trace.scopes() == [SCOPE_SYSTEM, SCOPE_EXTERIOR, SCOPE_INTERIOR, SCOPE_BEAM]
    for ambito in (SCOPE_SYSTEM, SCOPE_EXTERIOR, SCOPE_INTERIOR, SCOPE_BEAM):
        assert r.trace.by_scope(ambito), f"El ámbito {ambito} no tiene entradas"


def test_by_id_sin_ambito_levanta_cuando_hay_dos_zapatas():
    """El defecto latente que la Fase 4 cierra: devolver la primera coincidencia
    mostraría el punzonamiento de una columna bajo el rótulo de la otra."""
    r = _resolver()
    with pytest.raises(ValueError, match="aparece 2 veces"):
        r.trace.by_id("punching")


def test_by_id_con_ambito_devuelve_la_entrada_correcta():
    r = _resolver()
    ext = r.trace.by_id("punching", scope=SCOPE_EXTERIOR)
    interior = r.trace.by_id("punching", scope=SCOPE_INTERIOR)
    assert ext is not None and interior is not None
    assert ext is not interior
    assert ext.result_value == pytest.approx(r.exterior.punching.ratio)
    assert interior.result_value == pytest.approx(r.interior.punching.ratio)


def test_las_entradas_del_sistema_llevan_lo_que_no_es_de_ningun_componente():
    r = _resolver()
    ids = {e.id for e in r.trace.by_scope(SCOPE_SYSTEM)}
    assert "analysis_model" in ids
    assert "uniform_pressure_premise" in ids
    assert "foundation_depth" in ids
    assert any(i.startswith("couple_") for i in ids)


def test_las_trazas_de_los_componentes_no_se_recalculan():
    """Se copian con su ámbito; los valores deben ser los mismos objetos lógicos."""
    r = _resolver()
    del_componente = r.exterior.trace.by_id("flexure_x")
    del_sistema = r.trace.by_id("flexure_x", scope=SCOPE_EXTERIOR)
    assert del_sistema.result_value == del_componente.result_value
    assert del_sistema.equation_substituted == del_componente.equation_substituted


# =========================================================================
# 6. Estados: el sistema es el peor de sus partes
# =========================================================================

def test_la_premisa_sin_verificar_impide_el_PASS_del_sistema():
    """TBD-C1 sigue abierto: mientras no haya criterio para comprobar la rigidez de
    la viga, el sistema NO puede declararse conforme."""
    r = _resolver()
    premisa = r.trace.by_id("uniform_pressure_premise", scope=SCOPE_SYSTEM)
    assert premisa.status is CheckStatus.NOT_VERIFIED
    assert r.overall_status is not CheckStatus.PASS


def test_una_zapata_en_FAIL_arrastra_al_sistema():
    r = _resolver(geometry=_geom(exterior_B_m=1.20, exterior_L_m=1.20, exterior_h_m=0.40))
    assert r.exterior.overall_status is CheckStatus.FAIL
    assert r.overall_status is CheckStatus.FAIL


def test_Df_insuficiente_descarta_el_sistema_entero():
    r = _resolver(soil=_soil(Df_m=0.50))
    assert r.trace.by_id("foundation_depth", scope=SCOPE_SYSTEM).status is CheckStatus.FAIL
    assert r.overall_status is CheckStatus.FAIL
    assert any("26.2" in m for m in r.discard_reasons)


def test_Df_se_verifica_una_sola_vez_para_las_dos_zapatas():
    """Las dos comparten profundidad: repetir la entrada duplicaría el motivo de
    descarte y confundiría el informe."""
    r = _resolver(soil=_soil(Df_m=0.50))
    entradas = [e for e in r.trace.entries if e.id == "foundation_depth"]
    assert len(entradas) == 1
    assert entradas[0].scope == SCOPE_SYSTEM


def test_los_motivos_de_descarte_dicen_de_que_componente_vienen():
    r = _resolver(geometry=_geom(exterior_B_m=1.20, exterior_L_m=1.20, exterior_h_m=0.40))
    assert r.discard_reasons
    assert all(m.startswith("[") for m in r.discard_reasons)
    assert any(m.startswith("[Z1]") for m in r.discard_reasons)


# =========================================================================
# 7. No se reutiliza `beam_diagram`, ni siquiera de forma indirecta
# =========================================================================

def test_el_solver_de_conectada_no_menciona_beam_diagram():
    fuente = Path("engine/foundation/connected_solver.py").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in fuente.splitlines() if not l.strip().startswith("#"))
    assert "beam_diagram" not in codigo
    assert "build_beam_diagram" not in codigo


def test_la_estatica_de_la_viga_viene_del_modulo_propio():
    r = _resolver()
    assert r.beam_statics, "Debe haber diagramas de viga"
    for b in r.beam_statics:
        assert any("beam_diagram" in h for h in b.hypotheses), (
            "La hipótesis que explica por qué NO se reutiliza debe viajar en el resultado"
        )


def test_solo_se_dimensiona_la_viga_con_combinaciones_factorizadas():
    """E.060 §9.2: el concreto se diseña con cargas amplificadas."""
    r = _resolver()
    assert {b.combo_type for b in r.beam_statics} == {"FACTORIZADA"}


# =========================================================================
# 8. El modelo de análisis se propaga y CUERPO_RIGIDO sigue bloqueado
# =========================================================================

def test_el_modelo_declarado_queda_registrado_en_la_traza():
    r = _resolver()
    e = r.trace.by_id("analysis_model", scope=SCOPE_SYSTEM)
    assert "ARTICULADO" in e.equation_substituted
    assert e.status is CheckStatus.INFO, "Una decisión del proyectista no aprueba ni reprueba"
    assert any("NO lo elige" in h for h in e.hypotheses)


def test_el_solver_resuelve_tambien_el_modelo_de_cuerpo_rigido():
    """4C: el orquestador no cambió para admitirlo. Recibe el mismo contrato."""
    r = _resolver(_layout(modelo=AnalysisModel.CUERPO_RIGIDO))
    assert r.statics and all(d.closes for d in r.statics)
    assert r.trace.by_id("rigid_body_premise", scope=SCOPE_SYSTEM) is not None
