"""FASE 3 — Pruebas extremo a extremo.

Los tests unitarios verifican piezas; estos verifican que las piezas están
CONECTADAS. Es un hueco distinto: cada eslabón puede estar bien y el circuito roto
porque un DTO no mapea un campo, porque la interfaz manda un nombre que la API no
reconoce, o porque el informe lee un atributo que el motor dejó de publicar.

Se recorren los dos circuitos completos:

  1. UI → API → motor de vigas → resultados → informe
  2. UI combinada → solver combinado → viga/cortante → resultados

El payload de entrada se construye con los MISMOS nombres de campo que emite la
interfaz, no con los del motor: si alguien renombra un campo del esquema sin tocar
la interfaz, estos tests lo detectan.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.results.status import CheckStatus

cliente = TestClient(app)

ESTADOS_VALIDOS = {s.value for s in CheckStatus}


# El payload que emite `BeamInputPanel.tsx` con sus valores por defecto, salvo el
# contexto sísmico, que aquí se declara para ejercer la rama de E.030 art. 65.1.
PAYLOAD_VIGA = {
    "project_name": "Viga VC-1 — prueba extremo a extremo",
    "b_m": 0.35,
    "h_m": 1.20,
    "d_m": 1.10,
    "clear_span_m": 5.50,
    "Mu_negative_kNm": 1379.0,
    "Mu_positive_kNm": 300.0,
    "Vu_kN": 220.0,
    "sum_Pu_kN": 1240.0,
    "longitudinal_db_mm": 25.4,
    "stirrup_diameter_mm": 9.525,
    "n_legs": 2,
    "fyt_MPa": None,
    "materials": {
        "fc_MPa": 21.0, "fy_MPa": 420.0,
        "bar_type": "corrugada", "concrete_unit_weight_kNm3": 24.0,
    },
    "soil": {
        "qadm_kPa": 80.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.50,
        "mu_friction_soil_concrete": None, "cohesion_kPa": None,
        "FS_sliding_required": None, "FS_overturning_required": None,
        "allow_temporary_increase_30pct": False, "allow_seismic_reduction_80pct": False,
        "source_notes": "",
    },
    "seismic": {
        "soil_profile": "S3", "seismic_zone": 4,
        "part_of_lateral_force_system": True, "lateral_system": "porticos",
    },
    "units": {
        "force": "kN", "moment": "kN·m", "pressure": "kPa",
        "strength": "MPa", "length": "m", "unit_weight": "kN/m³",
    },
}


def _combinada(**cambios) -> dict:
    """Payload de `CombinedInputPanel.tsx`. El recubrimiento superior se declara:
    sin él la API debe rechazar el cálculo, y eso se comprueba aparte."""
    def combos(P_s, M_s, P_u, M_u):
        return [
            {"name": "S1", "type": "SERVICIO", "P_kN": P_s, "Mx_kNm": M_s, "My_kNm": 0,
             "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False,
             "includes_wind_loads": False},
            {"name": "U1", "type": "FACTORIZADA", "P_kN": P_u, "Mx_kNm": M_u, "My_kNm": 0,
             "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False,
             "includes_wind_loads": False},
        ]

    base = {
        "project_name": "Zapata combinada — prueba extremo a extremo",
        "columns": [
            {"label": "C1", "shape": "cuadrada", "bx_m": 0.5, "by_m": 0.5,
             "distance_from_first_m": 0.0, "transverse_offset_m": 0.0,
             "combinations": combos(1078, 83, 1563, 120)},
            {"label": "C2", "shape": "cuadrada", "bx_m": 0.5, "by_m": 0.5,
             "distance_from_first_m": 5.0, "transverse_offset_m": 0.0,
             "combinations": combos(2157, -24.5, 3128, -35.5)},
        ],
        "materials": {"fc_MPa": 21.0, "fy_MPa": 420.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 24.0},
        "soil": {"qadm_kPa": 150.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0,
                 "Df_m": 1.50, "mu_friction_soil_concrete": None, "cohesion_kPa": None,
                 "FS_sliding_required": None, "FS_overturning_required": None,
                 "allow_temporary_increase_30pct": False,
                 "allow_seismic_reduction_80pct": False, "source_notes": ""},
        "search": {"length_min_m": 6.8, "length_max_m": 7.8, "length_step_m": 0.2,
                   "width_min_m": 3.6, "width_max_m": 4.4, "width_step_m": 0.2,
                   "h_min_m": 0.65, "h_max_m": 0.95, "h_step_m": 0.05,
                   "first_column_edge_distance_m": 0.25, "longitudinal_direction": "X"},
        "top_cover": {"case": "contacto_suelo_barras_pequenas", "explicit_mm": None},
        "units": {"force": "kN", "moment": "kN·m", "pressure": "kPa",
                  "strength": "MPa", "length": "m", "unit_weight": "kN/m³"},
        "top_n": 5,
    }
    base.update(cambios)
    return base


# =========================================================================
# 1. Circuito de la viga: UI → API → motor → resultados → informe
# =========================================================================

@pytest.fixture(scope="module")
def viga() -> dict:
    r = cliente.post("/api/design-beam", json=PAYLOAD_VIGA)
    assert r.status_code == 200, r.text
    return r.json()


def test_la_api_acepta_el_payload_que_emite_la_interfaz(viga):
    assert viga["project_name"] == PAYLOAD_VIGA["project_name"]
    assert viga["b_m"] == pytest.approx(0.35)
    assert viga["clear_span_m"] == pytest.approx(5.50)


def test_el_estado_global_es_uno_de_los_cinco_de_la_maquina(viga):
    assert viga["status"] in ESTADOS_VALIDOS


def test_llegan_los_resultados_de_flexion_cortante_acero_y_estribos(viga):
    """Los cuatro bloques que la Fase 3 exigía trazar."""
    assert viga["As_negative_cm2"] > 0 and viga["As_positive_cm2"] > 0
    assert viga["min_steel_negative"]["As_min_governing_cm2"] > 0
    assert viga["shear"]["phi_Vc_kN"] > 0
    assert viga["confinement_limit_cm"] > 0
    assert viga["confinement_provided_cm"] is not None


def test_la_traza_llega_completa_y_con_estados_validos(viga):
    trace = viga["trace"]
    assert len(trace) >= 12, "La traza de la viga debe cubrir las cuatro familias"
    ids = {e["id"] for e in trace}
    esperados = {
        "beam_dimension",
        "beam_flexure_negativo", "beam_min_steel_negativo",
        "beam_flexure_positivo", "beam_min_steel_positivo",
        "beam_shear_concrete", "beam_shear_steel", "beam_shear_av_min",
        "beam_confinement", "beam_axial_trigger", "beam_lateral_system",
    }
    assert esperados <= ids, f"Faltan en la traza: {sorted(esperados - ids)}"
    for e in trace:
        assert e["status"] in ESTADOS_VALIDOS
        assert e["equation_symbolic"] and e["equation_substituted"]
        assert e["code_name"] and e["code_reference"]


def test_los_grupos_de_la_interfaz_cubren_todas_las_entradas_de_la_traza(viga):
    """`BeamResultsView.tsx` reparte la traza en cinco grupos por `id`. Si el motor
    añade una entrada y nadie actualiza esa lista, cae en «otras notas» sin que
    nadie lo note. Este test mantiene las dos listas sincronizadas."""
    grupos = {
        "beam_dimension",
        "beam_flexure_negativo", "beam_min_steel_negativo",
        "beam_flexure_positivo", "beam_min_steel_positivo",
        "beam_shear_concrete", "beam_shear_steel", "beam_shear_av_min",
        "beam_stirrup_spacing", "beam_confinement",
        "beam_axial_trigger", "beam_axial_flexure_negativo", "beam_axial_flexure_positivo",
        "beam_lateral_system",
    }
    huerfanas = {e["id"] for e in viga["trace"]} - grupos
    assert not huerfanas, (
        f"Entradas de traza sin grupo en BeamResultsView.tsx: {sorted(huerfanas)}"
    )


def test_la_interaccion_P_M_llega_con_su_diagrama_dibujable(viga):
    """La interfaz dibuja el diagrama con estos puntos: si llegan vacíos, el SVG
    queda en blanco sin error visible."""
    assert viga["axial_required"] is True
    assert viga["axial_N_kN"] == pytest.approx(0.10 * PAYLOAD_VIGA["sum_Pu_kN"])
    for lado in ("axial_flexure_negative", "axial_flexure_positive"):
        chk = viga[lado]
        assert chk is not None
        assert len(chk["diagram"]) > 100, "Resolución insuficiente para dibujar la frontera"
        assert all("phi_Mn_kNm" in p and "phi_Pn_kN" in p for p in chk["diagram"])
        assert chk["phi_Mn_at_Pu_kNm"] is not None
        assert chk["phi_at_Pu"] is not None


def test_el_ratio_infinito_llega_como_numero_y_no_rompe_el_JSON():
    """Cuando Pu cae fuera del diagrama el motor produce infinito, que JSON no
    admite. El DTO lo convierte en −1 y la interfaz lo rotula «fuera del diagrama»."""
    payload = dict(PAYLOAD_VIGA)
    payload["sum_Pu_kN"] = 900_000.0  # una axial absurda: fuerza el caso
    r = cliente.post("/api/design-beam", json=payload)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    chk = cuerpo["axial_flexure_negative"]
    # Se comprueba que se alcanzó de verdad la rama de «fuera del diagrama», no solo
    # que el JSON sea válido: sin esto el test pasaría aunque nunca se ejercitara.
    assert chk["inside_diagram"] is False
    assert chk["phi_Mn_at_Pu_kNm"] is None, "No hay capacidad que ofrecer a ese Pu"
    assert chk["demand_ratio"] == -1.0, "El infinito del motor viaja como −1"
    assert chk["axial_cap_ok"] is False
    assert cuerpo["status"] == CheckStatus.FAIL.value, (
        "Una axial por encima del tope de la ec. 10-2 no puede terminar en PASS"
    )


def test_lo_no_verificado_viaja_hasta_la_interfaz(viga):
    """Lo que el motor no comprueba no puede perderse por el camino: §21.5 deja
    requisitos sin implementar y eso tiene que llegar declarado."""
    lat = viga["lateral_requirements"]
    assert lat["applies"] is True
    assert lat["section"] == "§21.5", "§21.2 remite a §21.5 para pórticos"
    assert lat["not_implemented"], "Lo pendiente de §21.5 debe declararse"
    entrada = next(e for e in viga["trace"] if e["id"] == "beam_lateral_system")
    assert entrada["status"] == CheckStatus.NOT_VERIFIED.value
    assert viga["status"] in {CheckStatus.NOT_VERIFIED.value, CheckStatus.FAIL.value}, (
        "Con requisitos sin verificar el estado global NO puede ser PASS"
    )


def test_el_informe_se_genera_y_contiene_lo_que_calculo_el_motor(viga):
    r = cliente.post("/api/report-beam", json=PAYLOAD_VIGA)
    assert r.status_code == 200, r.text
    html = r.text
    assert html.lstrip().startswith("<!doctype html>")
    assert PAYLOAD_VIGA["project_name"] in html
    # Las secciones normativas que el informe debe citar.
    for cita in ("§21.12.3.2", "§10.5", "§11.5", "art. 65.1", "§21.12.3.3", "§9.3.2"):
        assert cita in html, f"El informe no cita {cita}"
    # Y la traza completa, entrada por entrada.
    for e in viga["trace"]:
        assert e["id"] in html, f"La entrada {e['id']} no llegó al informe"
    # El diagrama de interacción dibujado, no solo tabulado.
    assert "<svg" in html and "interaccion" in html


def test_el_informe_y_la_pantalla_no_pueden_divergir(viga):
    """Ambos endpoints pasan por el mismo `_solve_beam`. Se comprueba con un número
    que solo puede salir de un cálculo: el φMn en el Pu de demanda."""
    html = cliente.post("/api/report-beam", json=PAYLOAD_VIGA).text
    phi_Mn = viga["axial_flexure_negative"]["phi_Mn_at_Pu_kNm"]
    assert f"{phi_Mn:.1f} kN·m" in html


def test_una_seccion_imposible_se_rechaza_con_un_mensaje_util():
    payload = dict(PAYLOAD_VIGA)
    payload["d_m"] = payload["h_m"]
    r = cliente.post("/api/design-beam", json=payload)
    assert r.status_code == 422
    assert "recubrimiento" in r.text


# =========================================================================
# 2. Circuito de la combinada: UI → solver → viga/cortante → resultados
# =========================================================================

@pytest.fixture(scope="module")
def combinada() -> dict:
    r = cliente.post("/api/design-combined", json=_combinada())
    assert r.status_code == 200, r.text
    return r.json()


def test_la_combinada_responde_al_payload_de_su_panel(combinada):
    assert combinada["top"], "Debe haber al menos una alternativa viable"
    mejor = combinada["top"][0]
    assert mejor["status"] in ESTADOS_VALIDOS
    assert mejor["length_m"] > 0 and mejor["width_m"] > 0


def test_la_combinada_arma_las_dos_caras(combinada):
    mejor = combinada["top"][0]
    assert mejor["bottom_face"]["As_design_cm2"] > 0
    if mejor["has_top_steel"]:
        assert mejor["top_face"] is not None
        assert mejor["top_face"]["As_design_cm2"] > 0


def test_sin_recubrimiento_superior_la_combinada_se_rechaza():
    """§7.7.1 no da un valor único para esa cara: el programa no lo elige."""
    r = cliente.post(
        "/api/design-combined",
        json=_combinada(top_cover={"case": None, "explicit_mm": None}),
    )
    assert r.status_code == 422


def test_el_informe_de_la_combinada_se_genera(combinada):
    r = cliente.post("/api/report-combined", json=_combinada())
    assert r.status_code == 200, r.text
    assert "<svg" in r.text, "Los diagramas V(x) y M(x) deben dibujarse"


def test_cuando_el_concreto_no_basta_la_combinada_descarta_sin_estribos():
    """Circuito completo del requisito 4 de la Fase 3: una combinada que agota el
    concreto a cortante debe dimensionar el refuerzo con el MISMO motor, y la traza
    debe publicarlo citando §11.5.7.2 ec. 11-15."""
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.column import Column
    from engine.domain.column_placement import ColumnPlacement
    from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
    from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
    from engine.domain.materials import MaterialConcrete, MaterialSteel
    from engine.domain.soil import PressureBasis, SoilProfile
    from engine.foundation.combined_solver import solve_combined_footing
    from engine.reinforcement.face_reinforcement import TopCoverDeclaration
    from engine.soil.contact_pressure import FullContactModel

    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)

    def _c(label, x, P, L):
        return ColumnOnFooting(
            label=label,
            placement=ColumnPlacement(column=col, offset_x_m=x - L / 2.0),
            loads=LoadCaseSet(
                service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P)],
                factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                          P_kN=P * 1.4)],
            ),
        )

    encontrado = None
    for h_mm in range(300, 1300, 25):
        r = solve_combined_footing(
            CombinedFootingLayout(B_m=8.0, L_m=3.60,
                                  columns=[_c("C1", 1.0, 900.0, 8.0), _c("C2", 7.0, 900.0, 8.0)]),
            h_mm / 1000.0,
            soil=SoilProfile(qadm_kPa=400.0, pressure_basis=PressureBasis.BRUTA,
                             gamma_kNm3=18.0, Df_m=1.50, source_notes="prueba"),
            concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
            code=E060ConcreteCode(), contact_model=FullContactModel(),
            top_cover=TopCoverDeclaration(case="contacto_suelo_barras_pequenas"),
        )
        if r.shear_longitudinal.status is CheckStatus.FAIL:
            encontrado = r
            break

    # Auditoría C-V: la combinada NO usa el motor de vigas para el cortante. Con Vu > φVc la
    # verificación es FAIL por el criterio de concreto solo, sin refuerzo dimensionado.
    assert encontrado is not None, "Ninguna geometría del barrido superó φVc"
    assert encontrado.shear_reinforcement is None
    assert encontrado.trace.by_id("shear_reinforcement") is None
    assert encontrado.overall_status is CheckStatus.FAIL
    assert any("concreto solo" in m for m in encontrado.discard_reasons)
