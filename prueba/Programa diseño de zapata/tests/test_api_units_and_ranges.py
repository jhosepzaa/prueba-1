"""Unidades de entrada y rangos de búsqueda opcionales, a través de la API."""

import pytest
from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)

SEARCH_AUTO = {
    "B_step_m": 0.1, "L_step_m": 0.1, "h_step_m": 0.05, "max_LB_ratio": 2.0,
    "cover_override_mm": None, "hook_type_x": "ninguno", "hook_type_y": "ninguno",
}
SEARCH_MANUAL = {
    **SEARCH_AUTO,
    "B_min_m": 1.6, "B_max_m": 3.0, "L_min_m": 1.6, "L_max_m": 3.0,
    "h_min_m": 0.40, "h_max_m": 0.80, "B_step_m": 0.2, "L_step_m": 0.2,
}


def _soil(qadm: float, gamma: float) -> dict:
    return {
        "qadm_kPa": qadm, "pressure_basis": "BRUTA", "gamma_kNm3": gamma, "Df_m": 1.2,
        "mu_friction_soil_concrete": None, "cohesion_kPa": None,
        "FS_sliding_required": None, "FS_overturning_required": None,
        "allow_temporary_increase_30pct": False, "allow_seismic_reduction_80pct": False,
        "source_notes": "",
    }


def _combos(p_serv: float, m_serv: float, p_fact: float, m_fact: float) -> list[dict]:
    return [
        {"name": "S1", "type": "SERVICIO", "P_kN": p_serv, "Mx_kNm": m_serv, "My_kNm": 0.0,
         "Hx_kN": 0.0, "Hy_kN": 0.0, "includes_seismic_loads": False, "includes_wind_loads": False},
        {"name": "U1", "type": "FACTORIZADA", "P_kN": p_fact, "Mx_kNm": m_fact, "My_kNm": 0.0,
         "Hx_kN": 0.0, "Hy_kN": 0.0, "includes_seismic_loads": False, "includes_wind_loads": False},
    ]


def _design(payload: dict) -> dict:
    response = client.post("/api/design", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# --- Catálogo de unidades ------------------------------------------------------------

def test_reference_exposes_the_unit_catalog():
    units = client.get("/api/reference").json()["units"]
    assert {"force", "moment", "pressure", "strength", "length", "unit_weight"} <= set(units)
    force_values = {o["value"] for o in units["force"]}
    assert {"kN", "tonf", "kgf", "lbf", "kip"} <= force_values
    pressure_values = {o["value"] for o in units["pressure"]}
    assert {"kPa", "kgf/cm²", "tonf/m²"} <= pressure_values


# --- Equivalencia entre sistemas de unidades -------------------------------------------

def test_tonf_input_gives_the_same_result_as_the_equivalent_kN_input():
    """450 kN ≈ 45.89 tonf; 150 kPa ≈ 1.5299 kgf/cm². Deben dar la misma zapata."""
    si = _design({
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "soil": _soil(150.0, 18.0),
        "materials": {"fc_MPa": 21.0, "fy_MPa": 420.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 24.0},
        "search": SEARCH_MANUAL,
    })
    metric = _design({
        "units": {"force": "tonf", "moment": "tonf·m", "pressure": "kgf/cm²",
                  "strength": "kgf/cm²", "length": "m", "unit_weight": "tonf/m³"},
        "combinations": _combos(450.0 / 9.80665, 40.0 / 9.80665, 630.0 / 9.80665, 56.0 / 9.80665),
        "soil": _soil(150.0 / 98.0665, 18.0 / 9.80665),
        "materials": {"fc_MPa": 21.0 / 0.0980665, "fy_MPa": 420.0 / 0.0980665,
                      "bar_type": "corrugada", "concrete_unit_weight_kNm3": 24.0 / 9.80665},
        "search": SEARCH_MANUAL,
    })
    a, b = si["top"][0], metric["top"][0]
    assert (a["B_m"], a["L_m"], a["h_m"]) == (b["B_m"], b["L_m"], b["h_m"])
    assert a["qmax_kPa"] == pytest.approx(b["qmax_kPa"], rel=1e-4)
    assert a["As_req_x_cm2"] == pytest.approx(b["As_req_x_cm2"], rel=1e-3)


def test_imperial_input_is_accepted():
    data = _design({
        "units": {"force": "kip", "moment": "kip·ft", "pressure": "ksf",
                  "strength": "psi", "length": "ft", "unit_weight": "pcf"},
        "combinations": _combos(101.2, 29.5, 141.6, 41.3),
        "column": {"shape": "cuadrada", "bx_m": 1.31, "by_m": 1.31},
        "materials": {"fc_MPa": 3000.0, "fy_MPa": 60000.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 150.0},
        "soil": {**_soil(3.13, 115.0), "Df_m": 3.94},
        "search": {**SEARCH_AUTO, "B_step_m": 0.33, "L_step_m": 0.33, "h_step_m": 0.16},
    })
    assert data["top"], "Debe encontrar alternativas con entrada imperial"
    # Los resultados siempre salen en SI, independientemente de la entrada.
    assert 0.5 < data["top"][0]["B_m"] < 12.0


def test_kgf_cm2_steel_grade_60_is_not_rejected():
    """Regresión: un factor equivocado hacía que fy = 4200 kgf/cm² diera 4118 MPa
    y la validación normativa lo rechazara."""
    response = client.post("/api/design", json={
        "units": {"force": "kN", "moment": "kN·m", "pressure": "kPa",
                  "strength": "kgf/cm²", "length": "m", "unit_weight": "kN/m³"},
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "materials": {"fc_MPa": 210.0, "fy_MPa": 4200.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 24.0},
        "soil": _soil(150.0, 18.0),
        "search": SEARCH_MANUAL,
    })
    assert response.status_code == 200, response.text


def test_unknown_unit_is_rejected_with_a_clear_message():
    response = client.post("/api/design", json={
        "units": {"force": "quintales", "moment": "kN·m", "pressure": "kPa",
                  "strength": "MPa", "length": "m", "unit_weight": "kN/m³"},
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "soil": _soil(150.0, 18.0),
        "search": SEARCH_MANUAL,
    })
    assert response.status_code == 422
    assert "no reconocida" in response.json()["detail"]["detail"]


# --- Rangos opcionales -----------------------------------------------------------------

def test_omitting_all_limits_triggers_the_automatic_range():
    data = _design({
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "soil": _soil(150.0, 18.0),
        "search": SEARCH_AUTO,
    })
    summary = data["summary"]
    assert summary["search_range_note"], "Debe informar que el rango fue estimado"
    nota = summary["search_range_note"]
    # Desde 2026-09-24 la estimación parte de la presión DISPONIBLE —descontando el
    # relleno sobre la huella cuando la base es bruta— y no de `qadm` a secas, y tiene en
    # cuenta la excentricidad. La nota tiene que decir las dos cosas.
    assert "P/q_disponible" in nota
    assert "presión disponible" in nota.lower()
    assert "no criterio de diseño" in nota
    rng = summary["effective_search_range"]
    assert rng["B_max_m"] > rng["B_min_m"] > 0
    assert data["top"], "El rango automático debe encontrar alternativas"


def test_declaring_all_limits_does_not_trigger_the_automatic_range():
    data = _design({
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "soil": _soil(150.0, 18.0),
        "search": SEARCH_MANUAL,
    })
    assert data["summary"]["search_range_note"] == ""
    rng = data["summary"]["effective_search_range"]
    assert rng["B_min_m"] == pytest.approx(1.6)
    assert rng["B_max_m"] == pytest.approx(3.0)


def test_partial_limits_are_completed_automatically():
    """Se declara solo B_min: el resto lo estima el motor."""
    data = _design({
        "combinations": _combos(450.0, 40.0, 630.0, 56.0),
        "soil": _soil(150.0, 18.0),
        "search": {**SEARCH_AUTO, "B_min_m": 2.0},
    })
    rng = data["summary"]["effective_search_range"]
    assert rng["B_min_m"] == pytest.approx(2.0)  # respeta lo declarado
    assert rng["B_max_m"] > 2.0  # completa lo omitido
    assert data["summary"]["search_range_note"]


def test_automatic_range_scales_with_the_load():
    light = _design({
        "combinations": _combos(200.0, 0.0, 280.0, 0.0),
        "soil": _soil(150.0, 18.0), "search": SEARCH_AUTO,
    })["summary"]["effective_search_range"]
    heavy = _design({
        "combinations": _combos(2000.0, 0.0, 2800.0, 0.0),
        "soil": _soil(150.0, 18.0), "search": SEARCH_AUTO,
    })["summary"]["effective_search_range"]
    assert heavy["B_max_m"] > light["B_max_m"]


def test_automatic_range_scales_with_the_soil_capacity():
    weak = _design({
        "combinations": _combos(450.0, 0.0, 630.0, 0.0),
        "soil": _soil(80.0, 18.0), "search": SEARCH_AUTO,
    })["summary"]["effective_search_range"]
    strong = _design({
        "combinations": _combos(450.0, 0.0, 630.0, 0.0),
        "soil": _soil(400.0, 18.0), "search": SEARCH_AUTO,
    })["summary"]["effective_search_range"]
    assert weak["B_max_m"] > strong["B_max_m"]


def test_automatic_range_always_fits_the_column():
    data = _design({
        "combinations": _combos(450.0, 0.0, 630.0, 0.0),
        "column": {"shape": "cuadrada", "bx_m": 1.20, "by_m": 1.20},
        "soil": _soil(400.0, 18.0), "search": SEARCH_AUTO,
    })
    assert data["summary"]["effective_search_range"]["B_min_m"] > 1.20
