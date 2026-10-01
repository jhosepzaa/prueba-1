"""Fase 6 — FootingSceneDTO y su contrato con la visualización 3D.

Los cinco puntos exigidos:
  1. el DTO contiene todos los datos necesarios;
  2. cambiar de alternativa cambia correctamente la geometría;
  3. diámetro y número de barras corresponden al resultado real del motor;
  4. la UI no contiene cálculos de ingeniería;
  5. una alternativa WARNING / NO VERIFICADO / FAIL se representa como tal,
     nunca convertida visualmente en PASS.
"""

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from engine.visualization.scene_dto import COLUMN_STUB_HEIGHT_M, build_footing_scene
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
    update={"mu_friction_soil_concrete": 0.45, "FS_sliding_required": 1.5, "FS_overturning_required": 1.5}
)
COVER = 0.070


def _candidate(B=2.6, L=2.2, h=0.50, soil=SOIL_FULL, loads=None):
    loads = loads or LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    return evaluate_candidate(
        B_m=B, L_m=L, h_m=h, column=COLUMN_40x40, soil=soil, concrete=CONCRETE_21,
        steel=STEEL_420, load_case_set=loads, code=CODE, contact_model=CONTACT_MODEL,
        depth_params=DEPTH_PARAMS_DEFAULT,
    )


def _scene(candidate, alt_id="ALT-001"):
    return build_footing_scene(
        alternative_id=alt_id, status=candidate.overall_status,
        B_m=candidate.B_m, L_m=candidate.L_m, h_m=candidate.h_m, d_m=candidate.d_m,
        cover_m=COVER, column_bx_m=COLUMN_40x40.bx_m, column_by_m=COLUMN_40x40.by_m,
        rebar_geometry=candidate.rebar_geometry,
        designation_x=candidate.rebar_x.bar_designation,
        designation_y=candidate.rebar_y.bar_designation,
        label_x=f"{candidate.rebar_x.bar_designation} @ {candidate.rebar_x.spacing_m * 100:.1f} cm",
        label_y=f"{candidate.rebar_y.bar_designation} @ {candidate.rebar_y.spacing_m * 100:.1f} cm",
    )


# ===== 1. El DTO contiene todos los datos necesarios =================================

def test_scene_carries_every_required_field():
    s = _scene(_candidate())
    assert s.alternative_id
    assert s.B_m > 0 and s.L_m > 0 and s.h_m > 0 and s.d_m > 0
    assert s.cover_m > 0
    assert s.column_bx_m > 0 and s.column_by_m > 0
    assert s.footing and s.column and s.cover_box
    assert s.bars, "Sin barras no hay nada que visualizar"
    assert len(s.layers) == 2, "Deben describirse las dos direcciones de armado"
    assert s.dimensions, "Deben venir las cotas principales"
    assert s.scope_note


def test_footing_box_matches_the_declared_geometry():
    s = _scene(_candidate())
    assert s.footing.size.x == pytest.approx(s.B_m)
    assert s.footing.size.y == pytest.approx(s.L_m)
    assert s.footing.size.z == pytest.approx(s.h_m)
    # base en z=0, centro a media altura
    assert s.footing.center.z == pytest.approx(s.h_m / 2)
    assert s.footing.center.x == pytest.approx(0.0)


def test_column_sits_on_top_of_the_footing():
    s = _scene(_candidate())
    assert s.column.size.x == pytest.approx(s.column_bx_m)
    assert s.column.size.y == pytest.approx(s.column_by_m)
    assert s.column.center.z == pytest.approx(s.h_m + COLUMN_STUB_HEIGHT_M / 2)


def test_cover_box_is_inset_by_the_cover_on_every_face():
    s = _scene(_candidate())
    assert s.cover_box.size.x == pytest.approx(s.B_m - 2 * s.cover_m)
    assert s.cover_box.size.y == pytest.approx(s.L_m - 2 * s.cover_m)
    assert s.cover_box.size.z == pytest.approx(s.h_m - 2 * s.cover_m)


def test_dimensions_cover_B_L_h_and_the_column():
    s = _scene(_candidate())
    ids = {d.id for d in s.dimensions}
    assert {"B", "L", "h", "col_bx", "col_by"}.issubset(ids)
    for d in s.dimensions:
        assert d.label.strip()
        assert d.start != d.end


def test_every_bar_has_position_diameter_and_length():
    s = _scene(_candidate())
    for bar in s.bars:
        assert bar.diameter_m > 0
        assert bar.length_m > 0
        assert bar.direction in {"X", "Y"}
        assert bar.layer in {"inferior", "superior"}
        # la barra tiene extensión real en su dirección
        axis = abs(bar.end.x - bar.start.x) if bar.direction == "X" else abs(bar.end.y - bar.start.y)
        assert axis == pytest.approx(bar.length_m)


# ===== 2. Cambiar de alternativa cambia correctamente la geometría ====================

def test_different_alternatives_produce_different_scenes():
    a = _scene(_candidate(B=2.0, L=2.0, h=0.45), "ALT-001")
    b = _scene(_candidate(B=3.0, L=2.4, h=0.60), "ALT-002")

    assert a.alternative_id != b.alternative_id
    assert a.B_m != b.B_m and a.L_m != b.L_m and a.h_m != b.h_m
    assert a.footing.size.x != pytest.approx(b.footing.size.x)
    assert a.footing.size.z != pytest.approx(b.footing.size.z)
    assert a.column.center.z != pytest.approx(b.column.center.z)
    assert a.cover_box.size.x != pytest.approx(b.cover_box.size.x)


def test_bigger_footing_yields_longer_bars():
    small = _scene(_candidate(B=2.0, L=2.0))
    big = _scene(_candidate(B=3.4, L=3.0))
    small_x = [b for b in small.bars if b.direction == "X"][0]
    big_x = [b for b in big.bars if b.direction == "X"][0]
    assert big_x.length_m > small_x.length_m


def test_dimension_labels_follow_the_selected_alternative():
    a = _scene(_candidate(B=2.0, L=2.0, h=0.45))
    b = _scene(_candidate(B=3.0, L=2.4, h=0.60))
    label_a = next(d.label for d in a.dimensions if d.id == "B")
    label_b = next(d.label for d in b.dimensions if d.id == "B")
    assert "2.00" in label_a
    assert "3.00" in label_b


def test_bars_stay_inside_the_footing_for_every_geometry():
    for B, L, h in [(1.8, 1.8, 0.45), (2.6, 2.2, 0.50), (3.4, 2.0, 0.70)]:
        s = _scene(_candidate(B=B, L=L, h=h))
        for bar in s.bars:
            for point in (bar.start, bar.end):
                assert abs(point.x) <= B / 2 + 1e-9
                assert abs(point.y) <= L / 2 + 1e-9
                assert 0 <= point.z <= h + 1e-9


# ===== 3. Diámetro y número de barras = resultado real del motor ======================

def test_bar_count_matches_the_engine_exactly():
    c = _candidate()
    s = _scene(c)
    n_x = len([b for b in s.bars if b.direction == "X"])
    n_y = len([b for b in s.bars if b.direction == "Y"])
    assert n_x == c.rebar_geometry.layer_x.n_bars
    assert n_y == c.rebar_geometry.layer_y.n_bars
    assert n_x == c.rebar_x.n_bars
    assert n_y == c.rebar_y.n_bars


def test_bar_diameter_matches_the_engine_exactly():
    c = _candidate()
    s = _scene(c)
    for bar in s.bars:
        expected = (
            c.rebar_x.diameter_mm if bar.direction == "X" else c.rebar_y.diameter_mm
        ) / 1000.0
        assert bar.diameter_m == pytest.approx(expected)


def test_bar_length_matches_the_engine_geometry():
    c = _candidate()
    s = _scene(c)
    for bar in s.bars:
        layer = c.rebar_geometry.layer_x if bar.direction == "X" else c.rebar_geometry.layer_y
        assert bar.length_m == pytest.approx(layer.bar_length_m)


def test_layer_summary_reproduces_the_engine_values():
    c = _candidate()
    s = _scene(c)
    by_dir = {l.direction: l for l in s.layers}
    assert by_dir["X"].n_bars == c.rebar_x.n_bars
    assert by_dir["X"].diameter_mm == pytest.approx(c.rebar_x.diameter_mm)
    assert by_dir["X"].spacing_cm == pytest.approx(c.rebar_x.spacing_m * 100)
    assert by_dir["Y"].n_bars == c.rebar_y.n_bars
    assert by_dir["Y"].spacing_cm == pytest.approx(c.rebar_y.spacing_m * 100)


def test_two_layers_are_drawn_at_their_real_depths():
    """La parrilla tiene dos capas a distinta profundidad; el 3D debe reflejarlo."""
    c = _candidate()
    s = _scene(c)
    z_x = {round(b.start.z, 6) for b in s.bars if b.direction == "X"}
    z_y = {round(b.start.z, 6) for b in s.bars if b.direction == "Y"}
    assert len(z_x) == 1 and len(z_y) == 1
    assert z_x != z_y, "Las dos capas no pueden dibujarse a la misma altura"
    assert z_x.pop() == pytest.approx(c.rebar_geometry.layer_x.depth_to_bar_center_from_bottom_m)
    assert z_y.pop() == pytest.approx(c.rebar_geometry.layer_y.depth_to_bar_center_from_bottom_m)


def test_layer_summary_reports_the_real_effective_depth_per_layer():
    c = _candidate()
    s = _scene(c)
    by_dir = {l.direction: l for l in s.layers}
    assert by_dir["X"].d_m == pytest.approx(c.rebar_geometry.layer_x.d_m)
    assert by_dir["Y"].d_m == pytest.approx(c.rebar_geometry.layer_y.d_m)
    assert by_dir["X"].d_m != pytest.approx(by_dir["Y"].d_m)


def test_scene_reaches_the_ui_through_the_api_with_the_same_numbers():
    client = TestClient(app)
    response = client.post("/api/design", json={
        "combinations": [
            {"name": "S1", "type": "SERVICIO", "P_kN": 450, "Mx_kNm": 0, "My_kNm": 0,
             "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False, "includes_wind_loads": False},
            {"name": "U1", "type": "FACTORIZADA", "P_kN": 630, "Mx_kNm": 0, "My_kNm": 0,
             "Hx_kN": 0, "Hy_kN": 0, "includes_seismic_loads": False, "includes_wind_loads": False},
        ],
        "search": {
            "B_min_m": 1.6, "B_max_m": 3.0, "B_step_m": 0.2,
            "L_min_m": 1.6, "L_max_m": 3.0, "L_step_m": 0.2, "max_LB_ratio": 1.6,
            "h_min_m": 0.40, "h_max_m": 0.80, "h_step_m": 0.05,
            "cover_override_mm": None, "hook_type_x": "ninguno", "hook_type_y": "ninguno",
        },
    })
    assert response.status_code == 200
    alt = response.json()["top"][0]
    scene = alt["scene"]

    assert scene["alternative_id"] == alt["id"]
    assert scene["B_m"] == pytest.approx(alt["B_m"])
    assert scene["h_m"] == pytest.approx(alt["h_m"])
    assert scene["d_m"] == pytest.approx(alt["d_m"])
    assert scene["cover_m"] * 1000 == pytest.approx(alt["cover_mm"])
    # el armado dibujado es el que la ficha declara
    labels = {l["direction"]: l["label"] for l in scene["layers"]}
    assert labels["X"] == alt["rebar_x_label"]
    assert labels["Y"] == alt["rebar_y_label"]
    # y hay tantas barras como declara cada capa
    for layer in scene["layers"]:
        drawn = len([b for b in scene["bars"] if b["direction"] == layer["direction"]])
        assert drawn == layer["n_bars"]


# ===== 4. La UI no contiene cálculos de ingeniería ====================================

UI_SRC = pathlib.Path(__file__).resolve().parent.parent / "ui" / "src"

# Patrones que delatarían ingeniería embebida en el frontend.
FORBIDDEN_PATTERNS = [
    r"Math\.sqrt\s*\(",          # raíz cuadrada -> Vc, ld, gamma_f...
    r"\b0\.85\b",                # bloque de compresión / phi cortante
    r"\b0\.17\b", r"\b0\.33\b", r"\b0\.083\b",  # coeficientes de cortante
    r"\b0\.0018\b", r"\b0\.0020\b", r"\b0\.0025\b",  # cuantías mínimas
    r"\b0\.24\b",                # ganchos §12.5.2
    r"gamma_?[fv]\s*=",          # cálculo de gamma_f / gamma_v
    r"\bphi\s*\*",               # aplicación de phi
]

# Solo se permiten líneas que MUESTRAN texto normativo, nunca que calculen.
# (Un allowlist laxo — p. ej. incluir "*" — volvería el test inútil: casi toda
# línea con una multiplicación quedaría exenta.)
ALLOWED_SUBSTRINGS = ("code_reference", "equation_")

# Propiedades de RENDER de three.js que usan números en el mismo rango que algunos
# coeficientes normativos (p. ej. roughness={0.85}). No son ingeniería: describen
# cómo se ve un material, no cómo resiste. Se excluyen explícitamente para que el
# test no produzca falsos positivos y siga siendo útil.
RENDERING_PROPERTIES = (
    "roughness", "metalness", "opacity", "intensity", "lineWidth",
    "distanceFactor", "fov", "dpr", "fadeDistance", "cellSize", "sectionSize",
)


def _ui_source_files() -> list[pathlib.Path]:
    return [p for p in UI_SRC.rglob("*") if p.suffix in {".ts", ".tsx"}]


def test_ui_has_no_engineering_formulas():
    offenders: list[str] = []
    for path in _ui_source_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            if any(prop in line for prop in RENDERING_PROPERTIES):
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, line) and not any(a in line for a in ALLOWED_SUBSTRINGS):
                    offenders.append(f"{path.name}:{lineno}: {stripped[:90]}")
    assert not offenders, "Ingeniería embebida en la UI:\n" + "\n".join(offenders)


def test_3d_viewer_only_reads_dto_fields_for_geometry():
    """El visor no puede derivar posiciones de barras: deben venir del DTO."""
    source = (UI_SRC / "components" / "FootingScene3D.tsx").read_text(encoding="utf-8")
    # usa las posiciones tal como llegan
    assert "bar.start" in source and "bar.end" in source
    assert "bar.diameter_m" in source and "bar.length_m" in source
    # no reparte barras ni deriva separaciones
    assert "spacing_m *" not in source
    assert "n_bars" not in source.split("<table>")[0], "El visor no debe iterar n_bars para posicionar"


def test_bar_positions_are_computed_in_the_engine_not_in_the_ui():
    """Prueba estructural: el DTO ya trae las coordenadas resueltas."""
    s = _scene(_candidate())
    for bar in s.bars:
        assert isinstance(bar.start.x, float)
        assert isinstance(bar.start.y, float)
        assert isinstance(bar.start.z, float)


# ===== 5. WARNING / NO VERIFICADO / FAIL nunca se visualizan como PASS =================

def test_scene_status_is_the_real_candidate_status():
    c = _candidate()
    s = _scene(c)
    assert s.status is c.overall_status


def test_not_verified_alternative_keeps_its_status_in_the_scene():
    """Fuerzas horizontales sin μ ni FS -> NO VERIFICADO."""
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Hx_kN=90.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0)],
    )
    c = _candidate(soil=SOIL_150_BRUTA, loads=loads)
    assert c.overall_status is CheckStatus.NOT_VERIFIED
    s = _scene(c)
    assert s.status is CheckStatus.NOT_VERIFIED
    assert s.status is not CheckStatus.PASS


def test_failing_alternative_keeps_its_status_in_the_scene():
    c = _candidate(B=1.0, L=1.0)  # presión de contacto excedida
    assert c.overall_status is CheckStatus.FAIL
    s = _scene(c)
    assert s.status is CheckStatus.FAIL
    assert s.status is not CheckStatus.PASS


def test_scene_never_upgrades_a_status():
    """Recorre los cinco estados posibles: el DTO nunca mejora ninguno."""
    for status in CheckStatus:
        c = _candidate()
        s = build_footing_scene(
            alternative_id="X", status=status,
            B_m=c.B_m, L_m=c.L_m, h_m=c.h_m, d_m=c.d_m, cover_m=COVER,
            column_bx_m=0.4, column_by_m=0.4, rebar_geometry=c.rebar_geometry,
            designation_x="1/2\"", designation_y="1/2\"", label_x="a", label_y="b",
        )
        assert s.status is status


def test_viewer_renders_the_status_badge_without_normalising_it():
    source = (UI_SRC / "components" / "FootingScene3D.tsx").read_text(encoding="utf-8")
    assert "scene.status" in source
    # el visor no puede sustituir el estado por PASS ni ocultarlo
    assert '"PASS"' not in source
    assert "status ===" not in source


def test_scope_note_declares_that_hooks_are_not_drawn():
    s = _scene(_candidate())
    assert "gancho" in s.scope_note.lower()
    assert "recta" in s.scope_note.lower()
