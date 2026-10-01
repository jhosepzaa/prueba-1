"""Carga neta ascendente sobre una zapata de la conectada (2026-09-28).

Defecto: en cuerpo rígido, cuando el suelo devuelve bajo una zapata MENOS que el peso de
la propia zapata, la carga corregida R − W sale negativa: columna y viga tienen que
sostenerla. El diseño de la zapata solo está planteado para carga neta hacia abajo, y el
solver abortaba con «La carga vertical total debe ser positiva», que el barrido
clasificaba como ENTRADA_INVALIDA —«un dato mal declarado»— cuando los datos eran
correctos. Ahora se detecta antes, se nombra CARGA_NETA_ASCENDENTE y se explica.

Caso real: Apuntes CR2-93-134 §3.6, problema 2, con el sismo a nivel de servicio (E.060
§9.2.3, ec. 9-4b) y una zapata exterior ancha. En 0,9·CM + 1,25·CS la columna exterior
lleva 38 t y la zapata pesa más de lo que el suelo le devuelve.

No cambia ningún baseline: ningún caso congelado caía en este supuesto (el único
ENTRADA_INVALIDA congelado, Z4, es un error de declaración y lo sigue siendo).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.optimization.connected_generator import RejectionReason, _classify

CASOS = {
    "exterior": [("CM", 70.0, 4.0), ("CV", 25.0, 2.0), ("CS", -20.0, 140.0)],
    "interior": [("CM", 130.0, -4.5), ("CV", 50.0, -2.0), ("CS", 20.0, 150.0)],
}
COMBINACIONES = [
    ("S1", "SERVICIO", {"CM": 1.0, "CV": 1.0}),
    ("S2", "SERVICIO", {"CM": 1.0, "CV": 1.0, "CS": 1.0}),
    ("S3", "SERVICIO", {"CM": 1.0, "CV": 1.0, "CS": -1.0}),
    ("U1", "FACTORIZADA", {"CM": 1.4, "CV": 1.7}),
    ("U4", "FACTORIZADA", {"CM": 0.9, "CS": 1.25}),
    ("U5", "FACTORIZADA", {"CM": 0.9, "CS": -1.25}),
]


def _columna(cual: str, label: str) -> dict:
    return {
        "label": label, "shape": "rectangular", "bx_m": 0.80, "by_m": 0.25, "combinations": [],
        "load_cases": [
            {"name": n, "kind": n, "level": "SERVICIO" if n == "CS" else None, "P_kN": P, "Mx_kNm": M}
            for n, P, M in CASOS[cual]
        ],
    }


def _peticion(ext_long: float, ext_transv: float, int_long: float, int_transv: float, h: float) -> dict:
    def fijo(pref: str, v: float) -> dict:
        return {f"{pref}_min_m": v, f"{pref}_max_m": v, f"{pref}_step_m": 0.1}

    return {
        "project_name": "Aragón P2 — carga neta ascendente",
        "analysis_model": "CUERPO_RIGIDO",
        "couple_transfer_mode": "EQUILIBRIO_EN_CIMENTACION",
        "combination_definitions": [{"name": n, "type": t, "factors": f} for n, t, f in COMBINACIONES],
        "exterior": _columna("exterior", "C1"),
        "interior": _columna("interior", "C2"),
        "anchor": {"edge": "X_MIN", "face_clearance_m": 0.0},
        "beam": {"b_m": 0.35, "h_m": 1.20, "d_m": 1.10, "support_mode": "SIN_APOYO",
                 "self_weight_mode": "DESPRECIADO", "concrete_unit_weight_kNm3": 2.4},
        "axis_distance_m": 6.50,
        "longitudinal_axis": "X",
        "materials": {"fc_MPa": 210.0, "fy_MPa": 4200.0, "bar_type": "corrugada",
                      "concrete_unit_weight_kNm3": 2.4},
        "soil": {"qadm_kPa": 1.75, "gamma_kNm3": 1.8, "Df_m": 1.50,
                 "allow_temporary_increase_30pct": True},
        "search": {**fijo("ext_long", ext_long), **fijo("ext_transv", ext_transv),
                   **fijo("int_long", int_long), **fijo("int_transv", int_transv),
                   **fijo("h", h), "max_systems": 5, "same_depth_both_footings": True},
        "units": {"force": "tonf", "moment": "tonf·m", "pressure": "kgf/cm²",
                  "strength": "kgf/cm²", "length": "m", "unit_weight": "tonf/m³"},
        "top_n": 1,
    }


@pytest.fixture(scope="module")
def rechazo() -> dict:
    r = TestClient(app).post("/api/design-connected", json=_peticion(2.3, 6.0, 3.3, 6.7, 1.0))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["accepted_count"] == 0
    return j


def test_se_clasifica_como_carga_neta_ascendente_y_no_como_entrada_invalida(rechazo):
    assert rechazo["rejections_by_reason"] == {"CARGA_NETA_ASCENDENTE": 1}
    assert rechazo["rejected"][0]["reason"] == "CARGA_NETA_ASCENDENTE"


def test_el_detalle_nombra_combinacion_zapata_y_carga(rechazo):
    detalle = rechazo["rejected"][0]["detail"]
    assert "U4" in detalle and "C1" in detalle
    assert "kN" in detalle
    assert "ARRIBA" in detalle, "explica el sentido de la carga"
    # La API recorta el detalle; la explicación física llega en su primera parte.
    assert "menos que su propio peso" in detalle and "hacia abajo" in detalle
    assert "carga vertical total debe ser positiva" not in detalle, "ya no llega al solver"


def test_el_titular_del_informe_explica_el_motivo(rechazo):
    assert "CARGA_NETA_ASCENDENTE" in rechazo["headline"]
    assert "ENTRADA_INVALIDA" not in rechazo["headline"]


def test_el_clasificador_distingue_los_motivos():
    assert _classify(ValueError("CARGA_NETA_ASCENDENTE en 1 caso(s)"))[0] is RejectionReason.CARGA_NETA_ASCENDENTE
    assert _classify(ValueError("DESPEGUE en 1 combinación(es)"))[0] is RejectionReason.DESPEGUE
    # Lo que de verdad es un dato mal declarado sigue siendo ENTRADA_INVALIDA.
    assert _classify(ValueError("No hay ninguna combinación FACTORIZADA"))[0] is RejectionReason.ENTRADA_INVALIDA


def test_una_geometria_sin_carga_invertida_no_se_ve_afectada():
    """La geometría que el barrido acepta (CONN-076 del problema) no toca la detección."""
    r = TestClient(app).post("/api/design-connected", json=_peticion(2.8, 5.4, 6.0, 2.8, 1.25))
    assert r.status_code == 200, r.text
    j = r.json()
    assert "CARGA_NETA_ASCENDENTE" not in j["rejections_by_reason"]
