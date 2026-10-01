"""Fase 10B — contrato de cargas por casos (alternativa C).

Referencias escritas a mano. Cubre los invariantes del análisis
(`docs/analisis_contrato_cargas.md` §4):
  I1 linealidad · I2 equivalencia con el modo directo · I4 cargas internas con el factor
  CM · I5 coherencia entre columnas · I6 componente sísmica aislable, y la estabilidad
  con solo carga muerta (E.020 art. 20.1).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.analysis.connected_statics import BEAM_SELF_WEIGHT_FACTORING_PENDING
from engine.domain.connected_layout import AnalysisModel, BeamSelfWeightMode, CoupleTransferMode
from engine.domain.load_cases import (
    ActionLevel,
    CombinationDefinition,
    LoadCase,
    LoadCaseKind,
    derive_combination,
    derive_load_case_set,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.connected_solver import solve_connected_footing
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from tests.freeze.cases import CONCRETE_21, CONNECTED_CASES, GEO_REF, SOIL_CONN_250, STEEL_420, _conn_layout
from tests.freeze.snapshot import snapshot_candidate, snapshot_connected
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
)

SERV, FACT = LoadCombinationType.SERVICIO, LoadCombinationType.FACTORIZADA
S, U = "S1", "U1"


def _casos_basicos():
    return [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=300.0, Mx_kNm=20.0),
        LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=120.0, Mx_kNm=10.0),
        LoadCase(name="CSx", kind=LoadCaseKind.CS, level=ActionLevel.RESISTENCIA,
                 P_kN=40.0, Mx_kNm=90.0, Hx_kN=60.0),
    ]


# =========================================================================
# 1. Declaración y validación
# =========================================================================


def test_sismo_y_viento_exigen_nivel():
    with pytest.raises(ValueError, match="nivel"):
        LoadCase(name="CS", kind=LoadCaseKind.CS, P_kN=1.0)
    with pytest.raises(ValueError, match="nivel"):
        LoadCase(name="W", kind=LoadCaseKind.CVi, P_kN=1.0)


def test_los_demas_tipos_no_admiten_nivel():
    with pytest.raises(ValueError, match="solo se declara"):
        LoadCase(name="CM", kind=LoadCaseKind.CM, level=ActionLevel.SERVICIO, P_kN=1.0)


def test_una_combinacion_no_puede_usar_casos_no_declarados():
    with pytest.raises(ValueError, match="no declarados"):
        derive_combination(_casos_basicos(), CombinationDefinition(name=U, type=FACT, factors={"CM": 1.4, "CT": 1.0}))


def test_factores_distintos_en_casos_cm_se_rechazan():
    casos = _casos_basicos() + [LoadCase(name="CM2", kind=LoadCaseKind.CM, P_kN=10.0)]
    with pytest.raises(ValueError, match="único factor de CM"):
        derive_combination(casos, CombinationDefinition(name=U, type=FACT, factors={"CM": 1.4, "CM2": 1.25}))


# =========================================================================
# 2. I1 — linealidad y banderas derivadas
# =========================================================================


def test_la_combinacion_es_la_suma_factorizada_de_los_casos():
    c = derive_combination(
        _casos_basicos(),
        CombinationDefinition(name="U2", type=FACT, factors={"CM": 1.25, "CV": 1.25, "CSx": -1.0}),
    )
    assert c.P_kN == pytest.approx(1.25 * 300 + 1.25 * 120 - 40)
    assert c.Mx_kNm == pytest.approx(1.25 * 20 + 1.25 * 10 - 90)
    assert c.Hx_kN == pytest.approx(-60.0)
    assert c.includes_seismic_loads and not c.includes_wind_loads
    assert c.composition.dead_load_factor == pytest.approx(1.25)
    assert c.composition.total("P_kN", {"CS"}, "RESISTENCIA") == pytest.approx(-40.0)


def test_sin_cm_el_factor_de_carga_muerta_no_existe():
    c = derive_combination(_casos_basicos(), CombinationDefinition(name="X", type=SERV, factors={"CV": 1.0}))
    assert c.composition.dead_load_factor is None
    assert not c.includes_seismic_loads


# =========================================================================
# 3. I2 — equivalencia bit a bit con el modo directo
# =========================================================================


def _equivalentes_aislada():
    casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=300.0),
             LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=150.0)]
    por_casos = derive_load_case_set(casos, [
        CombinationDefinition(name=S, type=SERV, factors={"CM": 1.0, "CV": 1.0}),
        CombinationDefinition(name=U, type=FACT, factors={"CM": 1.4, "CV": 1.7}),
    ])
    directo = LoadCaseSet(
        service=[LoadCombination(name=S, type=SERV, P_kN=300.0 + 150.0)],
        factored=[LoadCombination(name=U, type=FACT, P_kN=1.4 * 300.0 + 1.7 * 150.0)],
    )
    return por_casos, directo


def _aislada(loads, soil=SOIL_150_BRUTA):
    return evaluate_candidate(B_m=2.2, L_m=2.2, h_m=0.50, column=COLUMN_40x40, soil=soil,
                              concrete=CONCRETE_21, steel=STEEL_420, load_case_set=loads, code=CODE,
                              contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT)


def test_aislada_derivar_o_escribir_a_mano_da_lo_mismo():
    """Sin momentos ni fuerzas horizontales (la estabilidad no aplica) y sin reducción
    sísmica, la composición no interviene: el resultado es idéntico."""
    por_casos, directo = _equivalentes_aislada()
    assert snapshot_candidate(_aislada(por_casos)) == snapshot_candidate(_aislada(directo))


def test_conectada_con_peso_despreciado_derivar_o_escribir_a_mano_da_lo_mismo():
    caso = next(c for c in CONNECTED_CASES if c.name == "Z1_articulado_equilibrio")
    lay = caso.build_layout()

    def a_casos(loads: LoadCaseSet) -> LoadCaseSet:
        s, u = loads.service[0], loads.factored[0]
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=s.P_kN, Mx_kNm=s.Mx_kNm)]
        f = u.P_kN / s.P_kN
        assert u.Mx_kNm == pytest.approx(f * s.Mx_kNm)
        return derive_load_case_set(casos, [
            CombinationDefinition(name=s.name, type=SERV, factors={"CM": 1.0}),
            CombinationDefinition(name=u.name, type=FACT, factors={"CM": f}),
        ])

    lay_casos = lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": a_casos(lay.exterior.loads)}),
        "interior": lay.interior.model_copy(update={"loads": a_casos(lay.interior.loads)}),
    })
    kw = dict(soil=caso.soil, concrete=caso.concrete, steel=caso.steel, code=CODE,
              contact_model=CONTACT_MODEL, depth_params=caso.depth_params)
    por_casos = snapshot_connected(solve_connected_footing(lay_casos, caso.geometry, **kw))
    directo = snapshot_connected(solve_connected_footing(lay, caso.geometry, **kw))

    # Fase 10C: las cargas corregidas conservan su composición y la estabilidad la lee. Todo
    # lo demás —reparto, cargas, diseño, referencias— es idéntico.
    #
    # Desde FORMULACION_VOLTEO (2026-09-19) las ÚNICAS diferencias son las claves de
    # composición, que son nuevas. El volteo de la zapata de lindero de Z1 ya no distingue los
    # dos modos porque no tiene demanda que verificar: la carga corregida trae M = −P·offset y
    # la resultante está centrada. Que la composición SÍ mueva el volteo cuando hay demanda se
    # fija en `tests/test_connected_composition_phase10c.py`, sobre los casos de CUERPO_RIGIDO.
    assert por_casos["referencias"] == directo["referencias"]
    assert por_casos["estados_blandos"] == directo["estados_blandos"]
    nuevas = {k for k in por_casos["numeros"] if "composition" in k}
    assert nuevas and not any("composition" in k for k in directo["numeros"])
    assert {k: v for k, v in por_casos["numeros"].items() if k not in nuevas} == directo["numeros"]
    distintos = {k for k in directo["estados"] if directo["estados"][k] != por_casos["estados"].get(k)}
    assert distintos == set(), distintos
    assert all(directo["estados"][k] == CheckStatus.NOT_VERIFIED.value for k in distintos)
    assert all(por_casos["estados"][k] == CheckStatus.PASS.value for k in distintos)


# =========================================================================
# 4. I4 — el peso de la viga recibe el factor CM de cada combinación (cierra TBD-C13)
# =========================================================================


def _conectada_por_casos(fm_serv=1.0, fm_fact=1.4, incluir_cm_en_u=True):
    lay = _conn_layout(modelo=AnalysisModel.ARTICULADO, modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
                       P_ext=850.0, P_int=1100.0, peso=BeamSelfWeightMode.EXPLICITO, z_b=0.30)

    def cargas(P):
        casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=P)]
        fu = {"CM": fm_fact} if incluir_cm_en_u else {"CV": 1.7}
        if not incluir_cm_en_u:
            casos.append(LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=P))
        defs = [CombinationDefinition(name=S, type=SERV, factors={"CM": fm_serv} | ({"CV": 0.0} if not incluir_cm_en_u else {})),
                CombinationDefinition(name=U, type=FACT, factors=fu)]
        return derive_load_case_set(casos, defs)

    lay = lay.model_copy(update={
        "exterior": lay.exterior.model_copy(update={"loads": cargas(850.0)}),
        "interior": lay.interior.model_copy(update={"loads": cargas(1100.0)}),
    })
    return solve_connected_footing(lay, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21, steel=STEEL_420,
                                   code=CODE, contact_model=CONTACT_MODEL,
                                   depth_params=next(c for c in CONNECTED_CASES if c.name.startswith("Z8")).depth_params)


def test_el_peso_de_la_viga_recibe_el_factor_cm():
    r = _conectada_por_casos()
    peso = {d.combo_name: d.beam_self_weight_kN for d in r.statics}
    # HV-2 (z_b = 0,30): 34,713 kN sin factor (docs/fase9ac_peso_propio_viga.md).
    assert peso[S] == pytest.approx(34.713, rel=1e-12)
    assert peso[U] == pytest.approx(1.4 * 34.713, rel=1e-12)
    for d in r.statics:
        assert BEAM_SELF_WEIGHT_FACTORING_PENDING not in d.hypotheses
        assert d.beam_self_weight_breakdown.load_factor == pytest.approx(1.0 if d.combo_name == S else 1.4)
        assert d.closes
    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert BEAM_SELF_WEIGHT_FACTORING_PENDING not in e.hypotheses


def test_sin_cm_en_la_combinacion_el_peso_de_la_viga_no_entra():
    r = _conectada_por_casos(incluir_cm_en_u=False)
    u = next(d for d in r.statics if d.combo_name == U)
    assert u.beam_self_weight_kN == 0.0
    assert u.beam_self_weight_breakdown.load_factor == 0.0


# =========================================================================
# 5. I6 — reducción sísmica al 80 % para el suelo (E.030 art. 29, E.060 §15.2.5)
# =========================================================================


def _sismica(nivel: ActionLevel, reduccion: bool):
    casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=400.0),
             LoadCase(name="CS", kind=LoadCaseKind.CS, level=nivel, P_kN=100.0, Mx_kNm=150.0)]
    loads = derive_load_case_set(casos, [
        CombinationDefinition(name=S, type=SERV, factors={"CM": 1.0, "CS": 1.0}),
        CombinationDefinition(name=U, type=FACT, factors={"CM": 1.25, "CS": 1.0}),
    ])
    soil = SOIL_150_BRUTA.model_copy(update={"allow_seismic_reduction_80pct": reduccion})
    return _aislada(loads, soil)


def test_la_reduccion_solo_toca_el_sismo_a_nivel_de_resistencia():
    """q con P = 400 + 0,8·100 y Mx = 0,8·150 frente a P = 500 y Mx = 150."""
    con = _sismica(ActionLevel.RESISTENCIA, True)
    sin = _sismica(ActionLevel.RESISTENCIA, False)
    servicio = _sismica(ActionLevel.SERVICIO, True)
    assert con.contact_pressure.qmax_kPa < sin.contact_pressure.qmax_kPa
    assert servicio.contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-12)
    A, W = 2.2 * 2.2, con.self_weight.W_total_kN
    P, M = 400.0 + 0.8 * 100.0, 0.8 * 150.0
    q_mano = (P + W) / A * (1 + 6 * (M / (P + W)) / 2.2)
    assert con.contact_pressure.qmax_kPa == pytest.approx(q_mano, rel=1e-9)


def test_con_combinaciones_directas_no_hay_reduccion():
    directo = LoadCaseSet(
        service=[LoadCombination(name=S, type=SERV, P_kN=500.0, Mx_kNm=150.0, includes_seismic_loads=True)],
        factored=[LoadCombination(name=U, type=FACT, P_kN=600.0, Mx_kNm=150.0, includes_seismic_loads=True)],
    )
    soil = SOIL_150_BRUTA.model_copy(update={"allow_seismic_reduction_80pct": True})
    sin = _sismica(ActionLevel.RESISTENCIA, False)
    assert _aislada(directo, soil).contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-12)


# =========================================================================
# 6. API — modo por casos
# =========================================================================

_BUSQUEDA = {"B_min_m": 1.8, "B_max_m": 2.6, "B_step_m": 0.2, "L_min_m": 1.8, "L_max_m": 2.6, "L_step_m": 0.2,
             "max_LB_ratio": 1.6, "h_min_m": 0.50, "h_max_m": 0.70, "h_step_m": 0.10,
             "cover_override_mm": None, "hook_type_x": "ninguno", "hook_type_y": "ninguno"}
_SUELO = {"qadm_kPa": 150.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.2,
          "mu_friction_soil_concrete": 0.45, "cohesion_kPa": None, "FS_sliding_required": None,
          "FS_overturning_required": None, "allow_temporary_increase_30pct": False,
          "allow_seismic_reduction_80pct": False, "source_notes": ""}
_CASOS = [{"name": "CM", "kind": "CM", "P_kN": 300.0},
          {"name": "CV", "kind": "CV", "P_kN": 100.0, "Hx_kN": 30.0}]
_DEFS = [{"name": "S1", "type": "SERVICIO", "factors": {"CM": 1.0, "CV": 1.0}},
         {"name": "U1", "type": "FACTORIZADA", "factors": {"CM": 1.4, "CV": 1.7}}]


def test_api_modo_por_casos_permite_demostrar_la_estabilidad():
    r = TestClient(app).post("/api/design", json={"load_cases": _CASOS, "combination_definitions": _DEFS,
                                                  "search": _BUSQUEDA, "soil": _SUELO})
    assert r.status_code == 200, r.text
    alt = r.json()["top"][0]
    assert alt["stability"]["sliding_status"] == "PASS"


def test_api_no_admite_los_dos_modos_a_la_vez():
    combos = [{"name": "S1", "type": "SERVICIO", "P_kN": 400.0}, {"name": "U1", "type": "FACTORIZADA", "P_kN": 600.0}]
    r = TestClient(app).post("/api/design", json={"combinations": combos, "load_cases": _CASOS,
                                                  "combination_definitions": _DEFS, "search": _BUSQUEDA})
    assert r.status_code == 422


def test_api_casos_sin_definiciones_se_rechazan():
    r = TestClient(app).post("/api/design", json={"load_cases": _CASOS, "search": _BUSQUEDA})
    assert r.status_code == 422


# =========================================================================
# 7. API — combinada y conectada en modo por casos (I5: definiciones comunes)
# =========================================================================


def _casos_columna(P: float, M: float = 0.0) -> list[dict]:
    return [{"name": "CM", "kind": "CM", "P_kN": P, "Mx_kNm": M}]


_DEFS_CM = [{"name": "S1", "type": "SERVICIO", "factors": {"CM": 1.0}},
            {"name": "U1", "type": "FACTORIZADA", "factors": {"CM": 1.45}}]


def test_api_combinada_por_casos_equivale_a_combinaciones_directas():
    from tests.test_api_combined_phase2 import _request as peticion_combinada

    directa = peticion_combinada()
    por_casos = peticion_combinada()
    for col, (P, M) in zip(por_casos["columns"], ((1078.0, 83.0), (2157.0, -24.5))):
        col["combinations"] = []
        col["load_cases"] = _casos_columna(P, M)
    # Las directas del test de origen son U = 1,45·S salvo redondeo: se reescriben exactas.
    for col, (P, M) in zip(directa["columns"], ((1078.0, 83.0), (2157.0, -24.5))):
        col["combinations"] = [
            {"name": "S1", "type": "SERVICIO", "P_kN": P, "Mx_kNm": M},
            {"name": "U1", "type": "FACTORIZADA", "P_kN": 1.45 * P, "Mx_kNm": 1.45 * M},
        ]
    por_casos["combination_definitions"] = _DEFS_CM
    cliente = TestClient(app)
    a = cliente.post("/api/design-combined", json=directa)
    b = cliente.post("/api/design-combined", json=por_casos)
    assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
    assert [x["id"] for x in a.json()["top"]] == [x["id"] for x in b.json()["top"]]


def test_api_conectada_por_casos_responde():
    from tests.test_connected_presentation_phase4e import _peticion

    p = _peticion()
    p["exterior"]["combinations"] = []
    p["interior"]["combinations"] = []
    p["exterior"]["load_cases"] = _casos_columna(850.0)
    p["interior"]["load_cases"] = _casos_columna(1100.0)
    p["combination_definitions"] = [{"name": "S1", "type": "SERVICIO", "factors": {"CM": 1.0}},
                                    {"name": "U1", "type": "FACTORIZADA", "factors": {"CM": 1.4}}]
    r = TestClient(app).post("/api/design-connected", json=p)
    assert r.status_code == 200, r.text
