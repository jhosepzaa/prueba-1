"""Columnas rectangulares y distintas entre sí en los paneles de entrada (2026-09-28).

Defecto: el panel de la conectada no tenía selector de forma. Toda columna viajaba como
«cuadrada» y, al escribir un `by` distinto de `bx`, el motor la rechazaba con razón
(`engine/domain/column.py`: una «cuadrada» exige bx == by). Además, escribir `bx`
sobrescribía `by`, de modo que una columna rectangular no se podía declarar. Aislada y
combinada tenían selector, pero con «Cuadrada» elegida escribir un `by` distinto daba el
mismo error.

La forma no interviene en ningún cálculo —solo se valida y se imprime—, así que el arreglo
es de interfaz: la forma sigue a las dimensiones (`ui/src/lib/columna.ts`). El motor no
cambia y su validación se conserva.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from fastapi.testclient import TestClient

from api.server import app
from tests.test_connected_presentation_phase4e import _combos, _peticion

UI = Path(__file__).resolve().parent.parent / "ui" / "src"
PANELES = ("InputPanel.tsx", "CombinedInputPanel.tsx", "ConnectedInputPanel.tsx")


def _fuente(ruta: Path) -> str:
    return io.open(ruta, encoding="utf-8").read()


# -------------------------------------------------------------------------
# 1. El motor: la validación sigue en pie y la conectada admite columnas distintas
# -------------------------------------------------------------------------


def test_una_cuadrada_con_lados_distintos_sigue_rechazandose():
    """El rótulo tiene que decir la verdad: el arreglo NO relaja el motor."""
    r = TestClient(app).post("/api/design-connected", json=_peticion(
        exterior={"label": "Z1", "shape": "cuadrada", "bx_m": 0.30, "by_m": 0.60,
                  "combinations": _combos(850.0)}))
    assert r.status_code == 422
    assert "cuadrada" in r.text


def test_la_conectada_calcula_con_columnas_rectangulares_y_distintas():
    # La de lindero lleva gancho (E.060 §15.6.2): hacia el lindero la barra solo tiene el
    # ancho de la columna para anclarse.
    ext = (0.60, 0.35)
    inte = (0.45, 0.70)
    r = TestClient(app).post("/api/design-connected", json=_peticion(
        exterior={"label": "Z1", "shape": "rectangular", "bx_m": ext[0], "by_m": ext[1],
                  "hook_type_x": "90", "hook_type_y": "90",
                  "combinations": _combos(850.0)},
        interior={"label": "Z2", "shape": "rectangular", "bx_m": inte[0], "by_m": inte[1],
                  "combinations": _combos(1100.0)}))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["accepted_count"] > 0
    escena = j["scene"]
    assert (escena["exterior_column"]["size"]["x"], escena["exterior_column"]["size"]["y"]) == ext
    assert (escena["interior_column"]["size"]["x"], escena["interior_column"]["size"]["y"]) == inte


# -------------------------------------------------------------------------
# 2. La interfaz: la forma sigue a las dimensiones en los tres paneles
# -------------------------------------------------------------------------


def test_los_tres_paneles_usan_la_regla_comun_de_forma():
    for nombre in PANELES:
        fuente = _fuente(UI / "components" / nombre)
        assert 'from "../lib/columna"' in fuente, nombre
        assert "conDimension(" in fuente and "conForma(" in fuente, nombre


def test_ningun_panel_escribe_bx_sobre_by_ni_al_reves():
    """Escribir una dimensión no puede tocar la otra: así se perdía la columna rectangular."""
    patron = re.compile(r"\{\s*bx_m:\s*\w+\s*,\s*by_m:\s*\w+\s*\}")
    for nombre in PANELES:
        assert not patron.search(_fuente(UI / "components" / nombre)), nombre


def test_la_conectada_tiene_selector_de_forma():
    fuente = _fuente(UI / "components" / "ConnectedInputPanel.tsx")
    assert '<option value="rectangular">Rectangular</option>' in fuente


def test_la_regla_de_forma_pasa_a_rectangular_si_los_lados_difieren():
    """Contrato textual de `columna.ts`: la tolerancia y el paso a «rectangular»."""
    fuente = _fuente(UI / "lib" / "columna.ts")
    assert 'Math.abs(bx_m - by_m) > 1e-9 ? "rectangular"' in fuente
    assert 'shape === "cuadrada" ? c.bx_m : c.by_m' in fuente


# -------------------------------------------------------------------------
# 3. Datos que llegan de fuera de los paneles (2026-09-28, segunda parte)
# -------------------------------------------------------------------------
# Lo recordado por el navegador y los proyectos guardados pudieron escribirse antes del
# arreglo, con «cuadrada» y 0,80 × 0,35. Ningún panel los corregía hasta volver a editar
# esa medida, y el cálculo seguía fallando.


def test_la_forma_se_corrige_al_recuperar_al_abrir_y_al_calcular():
    proyecto = _fuente(UI / "lib" / "project.ts")
    assert "normalizarColumnas(JSON.parse(guardado)" in proyecto, "memoria del navegador"
    assert "normalizarColumnas(datos.peticion)" in proyecto, "archivo de proyecto"
    app_tsx = _fuente(UI / "App.tsx")
    for envio in ("runDesign(normalizarColumnas(request))",
                  "runCombinedDesign(normalizarColumnas(combRequest))",
                  "runConnectedDesign(normalizarColumnas(connRequest))"):
        assert envio in app_tsx, envio


def test_la_normalizacion_cubre_las_tres_tipologias_y_solo_toca_la_forma():
    fuente = _fuente(UI / "lib" / "columna.ts")
    cuerpo = fuente[fuente.index("export function normalizarColumnas"):]
    for clave in ('"column"', '"exterior"', '"interior"', "p.columns"):
        assert clave in cuerpo, clave
    # Se corrige el rótulo, nunca una dimensión escrita por el usuario.
    assert 'shape: "rectangular"' in cuerpo
    assert "bx_m:" not in cuerpo and "by_m:" not in cuerpo


def test_lo_recordado_se_lee_en_el_estado_inicial_y_no_en_un_efecto():
    """Un efecto de montaje corre dos veces en modo estricto: el segundo leía el ejemplo
    que `recordar` acababa de escribir y se perdía lo guardado."""
    app_tsx = _fuente(UI / "App.tsx")
    for t in ("aislada", "combinada", "conectada", "viga"):
        assert f'recuperar<' in app_tsx and f'("{t}") ??' in app_tsx, t
    assert "const guardadaConn = recuperar" not in app_tsx
