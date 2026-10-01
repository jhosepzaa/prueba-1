"""API de zapata combinada — Fase 2."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


def _combo(P: float, M: float, tipo: str) -> dict:
    return {
        "name": "S1" if tipo == "SERVICIO" else "U1", "type": tipo,
        "P_kN": P, "Mx_kNm": M, "My_kNm": 0.0, "Hx_kN": 0.0, "Hy_kN": 0.0,
        "includes_seismic_loads": False, "includes_wind_loads": False,
    }


def _request(**overrides) -> dict:
    base = {
        "columns": [
            {"label": "C1", "shape": "cuadrada", "bx_m": 0.50, "by_m": 0.50,
             "distance_from_first_m": 0.0,
             "combinations": [_combo(1078.0, 83.0, "SERVICIO"), _combo(1563.0, 120.0, "FACTORIZADA")]},
            {"label": "C2", "shape": "cuadrada", "bx_m": 0.50, "by_m": 0.50,
             "distance_from_first_m": 5.0,
             "combinations": [_combo(2157.0, -24.5, "SERVICIO"), _combo(3128.0, -35.5, "FACTORIZADA")]},
        ],
        "materials": {"fc_MPa": 21.0, "fy_MPa": 420.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 24.0},
        "soil": {"qadm_kPa": 147.1, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.50,
                 "mu_friction_soil_concrete": None, "cohesion_kPa": None,
                 "FS_sliding_required": None, "FS_overturning_required": None,
                 "allow_temporary_increase_30pct": False, "allow_seismic_reduction_80pct": False,
                 "source_notes": ""},
        "search": {"length_min_m": 6.8, "length_max_m": 7.8, "length_step_m": 0.20,
                   "width_min_m": 3.6, "width_max_m": 4.4, "width_step_m": 0.20,
                   "h_min_m": 0.65, "h_max_m": 0.95, "h_step_m": 0.05,
                   "first_column_edge_distance_m": 0.25},
        "top_cover": {"case": "contacto_suelo_barras_pequenas"},
    }
    base.update(overrides)
    return base


def _design(payload: dict) -> dict:
    r = client.post("/api/design-combined", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_devuelve_alternativas_ordenadas_por_el_mismo_criterio_que_la_aislada():
    """ACTUALIZADO: antes ordenaba por volumen de concreto a secas. Ahora usa el
    núcleo de puntuación compartido con la zapata aislada —normalización min-max y
    suma ponderada—, para que las dos tipologías no acaben con criterios distintos.
    El volumen sigue pesando, pero ya no es lo único."""
    d = _design(_request())
    assert d["top"], "Debe encontrar alternativas viables"
    assert len(d["top"]) >= 2

    # El orden debe ser estable entre llamadas: si no lo fuera, «la mejor» cambiaría
    # de una ejecución a otra.
    otra = _design(_request())
    assert [a["id"] for a in d["top"]] == [a["id"] for a in otra["top"]]


def test_cada_alternativa_trae_el_armado_de_ambas_caras():
    a = _design(_request())["top"][0]
    assert a["bottom_face"]["bar_designation"]
    if a["has_top_steel"]:
        assert a["top_face"]["bar_designation"]
        assert a["top_face"]["face"] == "superior"


def test_la_longitud_de_desarrollo_viene_verificada_no_nula():
    """Un campo nulo aparentaría una comprobación no hecha."""
    a = _design(_request())["top"][0]
    for cara in ("bottom_face", "top_face"):
        if a[cara] is None:
            continue
        assert a[cara]["ld_required_m"] is not None
        assert a[cara]["development_ok"] is not None


def test_el_punzonamiento_viene_por_columna_con_su_clasificacion():
    a = _design(_request())["top"][0]
    assert len(a["punching"]) == 2
    porc = {p["column_label"]: p for p in a["punching"]}
    assert porc["C1"]["column_position"] == "borde", "Está al ras del lindero"
    assert porc["C1"]["alpha_s"] == 30.0
    assert porc["C2"]["column_position"] == "interior"
    assert porc["C2"]["alpha_s"] == 40.0


def test_ofrece_la_longitud_que_centra_la_resultante_como_ayuda():
    d = _design(_request())
    assert d["centering_length_m"] == pytest_approx(7.20, 0.02)
    assert "CRITERIO DE PREDIMENSIONAMIENTO" in d["centering_note"]


def pytest_approx(valor: float, tol: float):
    import pytest
    return pytest.approx(valor, abs=tol)


def test_declara_la_convencion_de_ejes():
    d = _design(_request())
    assert "E.050 art. 28.1" in d["axis_convention_note"]


def test_omitir_el_recubrimiento_superior_es_error_no_un_valor_por_defecto():
    """La tabla de §7.7.1 no da un valor único para esa cara."""
    r = client.post("/api/design-combined", json=_request(top_cover={}))
    assert r.status_code == 422
    assert "no da un valor único" in str(r.json())


def test_una_sola_columna_se_rechaza_indicando_el_endpoint_correcto():
    payload = _request()
    r = client.post("/api/design-combined", json={**payload, "columns": payload["columns"][:1]})
    assert r.status_code == 422
    assert "/api/design" in str(r.json())


# =========================================================================
# Memoria de cálculo
# =========================================================================

def _report(payload: dict):
    return client.post("/api/report-combined", json=payload)


def test_la_memoria_se_genera_y_es_html_autocontenido():
    r = _report(_request())
    assert r.status_code == 200, r.text
    html = r.text
    assert html.lstrip().startswith("<!doctype html>")
    # Autocontenido: nada que traer de fuera.
    assert "http://" not in html and "https://" not in html


def test_la_memoria_cita_las_secciones_normativas_del_analisis():
    html = _report(_request()).text
    for seccion in ("§15.4.1", "§15.10.1", "§15.10.2", "§10.5.4", "§7.7.1"):
        assert seccion in html, f"Falta la cita de {seccion}"


def test_la_memoria_dibuja_los_diagramas_a_partir_de_lo_calculado():
    """El informe visualiza; no recalcula. Es la misma regla del modelo 3D."""
    html = _report(_request()).text
    assert "<svg" in html and "polygon" in html
    assert "Cortante V(x)" in html and "Momento M(x)" in html


def test_la_memoria_distingue_lo_normativo_de_lo_que_es_criterio():
    html = _report(_request()).text
    # El ancho de franja es criterio de Aragón, no norma.
    assert "Criterio de modelación, no norma" in html or "criterio de modelación" in html.lower()
    # Y la clasificación de columna para alpha_s es interpretación declarada.
    assert "interpretación declarada" in html


def test_la_memoria_muestra_el_armado_de_ambas_caras():
    html = _report(_request()).text
    assert "Inferior (M positivo)" in html
    assert "Superior (M negativo)" in html


def test_sin_alternativa_viable_la_memoria_lo_dice_en_vez_de_fallar():
    """Rango imposible: qadm ridículamente bajo."""
    payload = _request()
    payload["soil"] = {**payload["soil"], "qadm_kPa": 5.0}
    r = _report(payload)
    assert r.status_code == 422
    assert "ninguna alternativa viable" in str(r.json()).lower()


# =========================================================================
# Integración global: tabla comparativa y frente de Pareto (campos aditivos)
# =========================================================================


def test_la_combinada_entrega_tabla_comparativa_y_pareto():
    from engine.optimization.pareto import DEFAULT_OBJECTIVES

    d = _design(_request())
    comp = d["comparison"]
    assert len(comp) >= len(d["top"]) >= 1
    assert [a["id"] for a in d["top"]] == [a["id"] for a in comp[: len(d["top"])]]
    puntuaciones = [a["score"] for a in comp]
    assert puntuaciones == sorted(puntuaciones)
    assert d["pareto_objectives"] == list(DEFAULT_OBJECTIVES)
    assert d["pareto_size"] == sum(a["in_pareto"] for a in comp) >= 1

    # Definición de dominancia, comprobada fuera del código que la implementa.
    def vec(a):
        return (a["concrete_volume_m3"], a["steel_mass_kg"], a["max_plan_dimension_m"])

    for a in comp:
        dominada = any(
            all(x <= y + 1e-12 for x, y in zip(vec(b), vec(a)))
            and any(x < y - 1e-12 for x, y in zip(vec(b), vec(a)))
            for b in comp if b is not a
        )
        assert a["in_pareto"] is (not dominada)
