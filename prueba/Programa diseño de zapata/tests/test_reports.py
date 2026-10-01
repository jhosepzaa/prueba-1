"""Fase 7 — Reporte de cálculo (sección 15 del encargo original).

Verifica que el reporte contenga las 16 secciones exigidas y que cada ecuación
declare variables, unidades, supuestos y fuente normativa. Y sobre todo: que el
reporte NO calcule nada, sino que refleje lo que el motor ya resolvió.
"""

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.search_parameters import GeometrySearchParameters
from engine.optimization.alternative_generator import generate_alternatives
from engine.optimization.ranker import rank_alternatives
from engine.reports.html_renderer import render_report_html
from engine.reports.report_builder import build_report
from engine.reports.report_model import SECTION_TITLES, status_label
from engine.results.status import CheckStatus
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)

SOIL_FULL = SOIL_150_BRUTA.model_copy(
    update={
        "mu_friction_soil_concrete": 0.45,
        "FS_sliding_required": 1.5,
        "FS_overturning_required": 1.5,
        "source_notes": "EMS ficticio de prueba",
    }
)
GEOM = GeometrySearchParameters(
    B_min_m=1.6, B_max_m=3.0, B_step_m=0.2, L_min_m=1.6, L_max_m=3.0, L_step_m=0.2, max_LB_ratio=1.6
)
PASS_CONDITIONS = ["condición 1", "condición 2"]


def _loads(**kwargs) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Mx_kNm=40.0, **kwargs)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0, Mx_kNm=56.0)],
    )


def _build(soil=SOIL_FULL, loads=None):
    loads = loads or _loads()
    result = generate_alternatives(
        column=COLUMN_40x40, soil=soil, concrete=CONCRETE_21, steel=STEEL_420,
        load_case_set=loads, code=CODE, contact_model=CONTACT_MODEL,
        geometry_params=GEOM, depth_params=DEPTH_PARAMS_DEFAULT,
    )
    ranking = rank_alternatives(result, top_n=5)
    return build_report(
        alternative=ranking.top[0].alternative, alternative_set=result,
        project_name="Proyecto de prueba", column=COLUMN_40x40, concrete=CONCRETE_21,
        steel=STEEL_420, soil=soil, load_case_set=loads, geometry_params=GEOM,
        depth_params=DEPTH_PARAMS_DEFAULT, code_name="E.060",
        min_depth_interpretation="EFFECTIVE_DEPTH", pass_conditions=PASS_CONDITIONS,
        cover_mm=70.0, elapsed_seconds=0.5, generated_at=datetime(2026, 8, 17, 10, 30),
    ), ranking.top[0].alternative, result


# ===== Las 16 secciones exigidas ======================================================

def test_sixteen_sections_are_declared():
    assert len(SECTION_TITLES) == 16
    assert SECTION_TITLES[0] == (1, "Datos del proyecto")
    assert SECTION_TITLES[-1] == (16, "Tabla comparativa")


def test_report_populates_every_section():
    report, _, _ = _build()
    assert report.project_name                 # 1
    assert report.column_rows                  # 2
    assert report.soil_rows                    # 3
    assert report.service_combinations         # 4
    assert report.factored_combinations        # 4
    assert report.hypotheses                   # 5
    assert report.geometry_rows                # 6
    assert report.trace_groups                 # 7-12
    assert report.eccentricity_rows            # 8
    assert report.rebar_tables                 # 12
    assert report.governing_combinations       # 13
    assert report.limitations                  # 13
    assert report.conclusion                   # 14
    assert report.pass_conditions == PASS_CONDITIONS
    assert report.comparison.rows              # 16


def test_html_contains_every_numbered_section():
    report, _, _ = _build()
    html = render_report_html(report)
    for number, title in SECTION_TITLES:
        # las secciones 7-12 aparecen con su título de grupo del trace
        assert title.split()[0] in html or f"{number}." in html, title


def test_html_is_self_contained():
    """Sin CSS externo, sin scripts, sin imágenes remotas: archivable tal cual."""
    html = render_report_html(_build()[0])
    assert "<style>" in html
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html.lower()


def test_html_has_print_rules():
    html = render_report_html(_build()[0])
    assert "@media print" in html
    assert "@page" in html
    assert "page-break" in html
    assert "no-print" in html  # el aviso de Ctrl+P no se imprime


# ===== Cada ecuación con variables, unidades, supuestos y fuente ========================

def test_every_equation_declares_the_four_required_elements():
    report, _, _ = _build()
    entries = [e for _, group in report.trace_groups for e in group]
    assert entries
    for e in entries:
        assert e.equation_symbolic.strip()      # variables
        assert e.equation_substituted.strip()   # sustitución numérica
        assert e.result_unit.strip()            # unidades
        assert e.code_reference.strip()         # fuente normativa


def test_html_renders_the_four_labels_for_each_equation():
    html = render_report_html(_build()[0])
    assert "Ecuación" in html
    assert "Sustitución numérica" in html
    assert "Fuente normativa" in html
    assert "Supuestos" in html


def test_trace_groups_cover_pressures_flexure_shear_punching_and_steel():
    report, _, _ = _build()
    titles = " ".join(t for t, _ in report.trace_groups).lower()
    for topic in ("presiones", "flexión", "cortante", "punzonamiento", "acero"):
        assert topic in titles, topic


# ===== El reporte refleja el motor, no lo recalcula =====================================

def test_geometry_rows_match_the_candidate():
    report, alternative, _ = _build()
    c = alternative.candidate
    values = {r.label: r.value for r in report.geometry_rows}
    assert values["Ancho B (eje X)"] == f"{c.B_m:.2f}"
    assert values["Largo L (eje Y)"] == f"{c.L_m:.2f}"
    assert values["Peralte total h"] == f"{c.h_m:.2f}"
    assert values["Peralte efectivo d"] == f"{c.d_m:.4f}"


def test_governing_combinations_come_from_the_trace():
    report, alternative, _ = _build()
    from_trace = {
        e.governing_combo for e in alternative.candidate.trace.entries if e.governing_combo
    }
    from_report = {g.combination for g in report.governing_combinations}
    assert from_report == from_trace


def test_hypotheses_are_collected_from_the_engine_not_invented():
    report, alternative, _ = _build()
    engine_texts = {
        h.strip() for e in alternative.candidate.trace.entries for h in e.hypotheses if h.strip()
    }
    for item in report.hypotheses:
        assert item.text in engine_texts


def test_discards_reflect_the_alternative_set():
    report, _, result = _build()
    total_reported = sum(d.count for d in report.discarded)
    assert total_reported >= len(result.discarded) or not result.discarded
    assert str(result.n_geometries_evaluated) in report.discard_note


def test_report_module_contains_no_engineering_formulas():
    """El constructor y el renderizador solo formatean."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "engine" / "reports"
    forbidden = [r"math\.sqrt", r"\b0\.85\b", r"\b0\.17\b", r"\b0\.0018\b", r"\bphi\s*\*"]
    offenders = []
    for path in root.glob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith(("#", '"', "'")):
                continue
            for pattern in forbidden:
                if re.search(pattern, line, re.IGNORECASE):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()[:80]}")
    assert not offenders, "Ingeniería en el módulo de reportes:\n" + "\n".join(offenders)


# ===== El estado real nunca se maquilla ================================================

def test_status_label_maps_every_state():
    """ACTUALIZADO en el pendiente 8: vocabulario único de las tres tipologías. «ACEPTADA» a
    secas desapareció —significaba PASS aquí y WARNING en la conectada— y «DESCARTADA» se
    unificó con «RECHAZADA». El mapa completo se fija en
    tests/test_status_vocabulary_pendiente8.py."""
    assert status_label(CheckStatus.PASS) == "CONFORME"
    assert status_label(CheckStatus.INFO) == "CONFORME"
    assert status_label(CheckStatus.WARNING) == "ACEPTADA CON OBSERVACIONES"
    assert status_label(CheckStatus.NOT_VERIFIED) == "NO VERIFICADA"
    assert status_label(CheckStatus.FAIL) == "RECHAZADA"


def test_not_verified_report_says_so_and_lists_what_is_pending():
    """Fuerzas horizontales sin μ ni FS -> NO VERIFICADO."""
    report, alternative, _ = _build(soil=SOIL_150_BRUTA, loads=_loads(Hx_kN=80.0))
    assert alternative.candidate.overall_status is CheckStatus.NOT_VERIFIED
    assert report.final_status is CheckStatus.NOT_VERIFIED
    assert "NO VERIFICADA" in status_label(report.final_status)
    assert "NO pudieron ejecutarse" in report.conclusion
    assert "no puede considerarse conforme" in report.conclusion
    # y nombra las verificaciones concretas que quedaron pendientes
    assert "Deslizamiento" in report.conclusion
    html = render_report_html(report)
    assert "NO VERIFICADO" in html
    assert "NO VERIFICADA" in html


def test_report_never_upgrades_the_status():
    report, alternative, _ = _build()
    assert report.final_status is alternative.candidate.overall_status


def test_limitations_table_is_always_present_in_the_html():
    html = render_report_html(_build()[0])
    assert "Limitaciones declaradas" in html
    assert "falso PASS" in html


def test_soil_report_marks_undeclared_parameters():
    report, _, _ = _build(soil=SOIL_150_BRUTA)  # sin mu ni FS
    values = {r.label: r.value for r in report.soil_rows}
    assert values["Coef. fricción suelo-concreto μ"] == "no declarado"
    assert values["FS deslizamiento adoptado"] == "no declarado"
    refs = {r.label: r.reference for r in report.soil_rows}
    assert "no lo prescribe" in refs["FS deslizamiento adoptado"]


# ===== Endpoint =========================================================================

client = TestClient(app)

REQUEST = {
    "project_name": "Prueba API",
    "combinations": [
        {"name": "S1", "type": "SERVICIO", "P_kN": 450, "Mx_kNm": 40, "My_kNm": 25,
         "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False, "includes_wind_loads": False},
        {"name": "U1", "type": "FACTORIZADA", "P_kN": 630, "Mx_kNm": 56, "My_kNm": 35,
         "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False, "includes_wind_loads": False},
    ],
    "search": {
        "B_min_m": 1.6, "B_max_m": 3.0, "B_step_m": 0.2,
        "L_min_m": 1.6, "L_max_m": 3.0, "L_step_m": 0.2, "max_LB_ratio": 1.6,
        "h_min_m": 0.40, "h_max_m": 0.80, "h_step_m": 0.05,
        "cover_override_mm": None, "hook_type_x": "ninguno", "hook_type_y": "ninguno",
    },
}


def test_report_endpoint_returns_html():
    response = client.post("/api/report", json=REQUEST)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()
    assert "Memoria de cálculo" in response.text


def test_report_endpoint_honours_the_requested_alternative():
    design = client.post("/api/design", json=REQUEST).json()
    target = design["top"][2]["id"]
    html = client.post("/api/report", json={**REQUEST, "alternative_id": target}).text
    assert target in html


def test_report_endpoint_rejects_an_unknown_alternative():
    response = client.post("/api/report", json={**REQUEST, "alternative_id": "ALT-999"})
    assert response.status_code == 404


def test_report_endpoint_rejects_empty_combinations():
    response = client.post("/api/report", json={**REQUEST, "combinations": []})
    assert response.status_code == 422


def test_report_endpoint_explains_when_nothing_is_valid():
    impossible = {
        **REQUEST,
        "soil": {
            "qadm_kPa": 31.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.2,
            "mu_friction_soil_concrete": None, "cohesion_kPa": None,
            "FS_sliding_required": None, "FS_overturning_required": None,
            "allow_temporary_increase_30pct": False, "allow_seismic_reduction_80pct": False,
            "source_notes": "",
        },
    }
    response = client.post("/api/report", json=impossible)
    assert response.status_code == 422
    assert "alternativa" in response.json()["detail"]["detail"].lower()


def test_report_html_escapes_user_supplied_text():
    """El nombre del proyecto llega del usuario: no puede inyectar HTML."""
    malicious = {**REQUEST, "project_name": "<script>alert(1)</script>"}
    html = client.post("/api/report", json=malicious).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
