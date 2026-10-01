"""Tests de la capa API.

Verifican el contrato con la interfaz y, sobre todo, el requisito arquitectónico:
la UI no puede necesitar calcular nada — todo lo que muestra debe venir resuelto.
"""

import pytest
from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)

BASE_COMBOS = [
    {
        "name": "S1", "type": "SERVICIO", "P_kN": 450.0, "Mx_kNm": 40.0, "My_kNm": 25.0,
        "Hx_kN": 0.0, "Hy_kN": 0.0, "includes_seismic_loads": False, "includes_wind_loads": False,
    },
    {
        "name": "U1", "type": "FACTORIZADA", "P_kN": 630.0, "Mx_kNm": 56.0, "My_kNm": 35.0,
        "Hx_kN": 0.0, "Hy_kN": 0.0, "includes_seismic_loads": False, "includes_wind_loads": False,
    },
]

COARSE_SEARCH = {
    "B_min_m": 1.6, "B_max_m": 3.0, "B_step_m": 0.2,
    "L_min_m": 1.6, "L_max_m": 3.0, "L_step_m": 0.2,
    "max_LB_ratio": 1.6, "h_min_m": 0.40, "h_max_m": 0.80, "h_step_m": 0.05,
    "cover_override_mm": None, "hook_type_x": "ninguno", "hook_type_y": "ninguno",
}


def _request(**overrides) -> dict:
    payload = {"combinations": BASE_COMBOS, "search": COARSE_SEARCH}
    payload.update(overrides)
    return payload


def _design(**overrides):
    response = client.post("/api/design", json=_request(**overrides))
    assert response.status_code == 200, response.text
    return response.json()


# --- endpoints básicos ---------------------------------------------------------------

def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_reference_exposes_catalog_and_limitations():
    data = client.get("/api/reference").json()
    assert len(data["rebar_catalog"]) == 6
    # 6 del alcance de zapata aislada + 3 propias de la zapata conectada (Fase 4) + el
    # relleno sobre la viga en el vano, pendiente declarado de la Fase 9a, + la estabilidad de
    # las zapatas de la conectada con solo carga muerta (Fase 10B) + el factor de CM del peso
    # propio de la viga en modo directo (TBD-C13 A').
    #
    # Fueron 13 durante un día: el 2026-09-19 se añadió la del punzonamiento con contacto
    # parcial, y el 2026-09-20 la decisión 1 la retiró al implementar el contacto unilateral
    # por equilibrio (`docs/freeze_contacto_unilateral.md` §1.6). Una limitación se retira
    # cuando se RESUELVE el hueco, no cuando molesta.
    assert len(data["limitations"]) == 12
    assert data["pass_conditions"]
    # el FS de referencia se expone marcado como propio de muros de contención
    assert data["fs_reference"]["static"] == 1.50
    assert "MUROS DE CONTENCIÓN" in data["fs_reference"]["note"]


# --- diseño completo -------------------------------------------------------------------

def test_design_returns_a_complete_response():
    data = _design()
    assert data["summary"]["n_evaluated"] > 0
    assert data["top"], "Debe devolver al menos una alternativa"
    assert data["table"]
    assert data["limitations"]
    assert data["pass_conditions"]


def test_top_alternatives_carry_the_full_trace():
    """La vista académica depende de que cada alternativa traiga su memoria."""
    alt = _design()["top"][0]
    assert len(alt["trace"]) >= 15
    for entry in alt["trace"]:
        assert entry["equation_symbolic"]
        assert entry["equation_substituted"]
        assert entry["code_reference"]
        assert entry["status"] in {"PASS", "INFO", "WARNING", "NO VERIFICADO", "FAIL"}


def test_ui_never_needs_to_compute_a_ratio_or_a_conversion():
    """Todo lo que la interfaz muestra llega ya calculado y en unidades de
    presentación (cm², cm, mm)."""
    alt = _design()["top"][0]
    for key in (
        "shear_x_ratio", "shear_y_ratio", "punching_ratio",
        "As_req_x_cm2", "As_min_x_cm2", "qmax_kPa", "score",
        "concrete_volume_m3", "steel_mass_kg",
    ):
        assert isinstance(alt[key], (int, float)), key
    for option in alt["rebar_options_x"]:
        assert option["spacing_cm"] > 0
        assert option["As_provided_cm2"] > 0
        assert option["label"]


def test_score_breakdown_is_auditable():
    alt = _design()["top"][0]
    total = sum(b["contribution"] for b in alt["score_breakdown"].values())
    assert total == pytest.approx(alt["score"], rel=1e-9)


def test_governing_combination_is_reported_per_check():
    alt = _design()["top"][0]
    combos = alt["governing_combos"]
    assert combos["contact_pressure"] == "S1"
    assert combos["flexure_x"] == "U1"
    assert combos["punching"] == "U1"


def test_discarded_groups_include_a_worked_example():
    data = _design()
    if data["discarded"]:
        group = data["discarded"][0]
        assert group["count"] >= 1
        assert group["example_explanation"]
        assert "CUMPLE" in group["example_explanation"]


def test_pareto_flag_is_present_in_the_table():
    data = _design()
    marked = [r for r in data["table"] if r["in_pareto"]]
    assert len(marked) == data["summary"]["pareto_size"]


# --- estabilidad a través de la API ------------------------------------------------------

def test_horizontal_forces_without_parameters_yield_not_verified():
    combos = [dict(BASE_COMBOS[0], Hx_kN=80.0), BASE_COMBOS[1]]
    data = _design(combinations=combos)
    alt = data["top"][0]
    assert alt["stability"]["sliding_status"] == "NO VERIFICADO"
    assert alt["stability"]["missing_parameters"]
    assert alt["status"] != "PASS"


def test_supplying_stability_parameters_allows_pass():
    combos = [dict(BASE_COMBOS[0], Hx_kN=40.0), BASE_COMBOS[1]]
    soil = {
        "qadm_kPa": 150.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.2,
        "mu_friction_soil_concrete": 0.45, "cohesion_kPa": None,
        "FS_sliding_required": 1.5, "FS_overturning_required": 1.5,
        "allow_temporary_increase_30pct": False, "allow_seismic_reduction_80pct": False,
        "source_notes": "",
    }
    alt = _design(combinations=combos, soil=soil)["top"][0]
    # Fase 10B: con combinaciones directas el FS se calcula, pero un cumplimiento no puede
    # afirmarse (E.020 art. 20.1). El PASS con el modo por casos lo cubre
    # tests/test_load_cases_phase10b.py.
    assert alt["stability"]["sliding_status"] == "NO VERIFICADO"
    assert alt["stability"]["sliding_FS"] is not None


def test_moment_transfer_is_reported():
    alt = _design()["top"][0]
    assert alt["punching_has_moment_transfer"] is True
    assert alt["punching_amplification"] > 1.0


# --- validación de entradas ---------------------------------------------------------------

def test_normative_validation_error_reaches_the_client_with_its_article():
    response = client.post(
        "/api/design",
        json=_request(materials={
            "fc_MPa": 10.0, "fy_MPa": 420.0, "bar_type": "corrugada",
            "concrete_unit_weight_kNm3": 24.0,
        }),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "17 MPa" in detail["detail"]
    assert "§9.4" in detail["detail"]
    assert detail["field"] == "fc_MPa"


def test_empty_combinations_rejected():
    response = client.post("/api/design", json={"combinations": []})
    assert response.status_code == 422


def test_missing_service_combination_rejected():
    only_factored = [BASE_COMBOS[1]]
    response = client.post("/api/design", json=_request(combinations=only_factored))
    assert response.status_code == 422


def test_oversized_search_grid_is_rejected_before_running():
    huge = dict(COARSE_SEARCH, B_min_m=0.5, B_max_m=20.0, B_step_m=0.05,
                L_min_m=0.5, L_max_m=20.0, L_step_m=0.05)
    response = client.post("/api/design", json=_request(search=huge))
    assert response.status_code == 422
    assert "geometrías" in response.json()["detail"]


def test_min_depth_interpretation_is_configurable_through_the_api():
    effective = _design(min_depth_interpretation="EFFECTIVE_DEPTH")
    total = _design(min_depth_interpretation="TOTAL_DEPTH")
    assert effective["summary"]["min_depth_interpretation"] == "EFFECTIVE_DEPTH"
    assert total["summary"]["min_depth_interpretation"] == "TOTAL_DEPTH"


def test_weights_change_the_winner_through_the_api():
    volume_only = _design(weights={
        "w_concrete_volume": 1.0, "w_steel_mass": 0.0,
        "w_max_dimension": 0.0, "w_constructive_complexity": 0.0,
    })
    steel_only = _design(weights={
        "w_concrete_volume": 0.0, "w_steel_mass": 1.0,
        "w_max_dimension": 0.0, "w_constructive_complexity": 0.0,
    })
    best_volume = min(r["concrete_volume_m3"] for r in volume_only["table"])
    best_steel = min(r["steel_mass_kg"] for r in steel_only["table"])
    assert volume_only["top"][0]["concrete_volume_m3"] == pytest.approx(best_volume)
    assert steel_only["top"][0]["steel_mass_kg"] == pytest.approx(best_steel)
