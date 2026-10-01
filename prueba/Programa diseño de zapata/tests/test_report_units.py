"""La memoria de cálculo escrita en las unidades del proyectista (2026-09-23).

Lo que se comprueba:
  1. que el número que aparece en la memoria es el CONVERTIDO, no el SI con otro
     rótulo —que es el defecto que tenía la interfaz antes de este trabajo—;
  2. que sin declarar unidades la memoria sale exactamente como salía antes;
  3. que la traza se mantiene en SI y la memoria lo DICE, porque es una limitación
     deliberada (`engine/reports/report_units.py`).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.reports.report_units import ReportUnits

cliente = TestClient(app)

PERUANAS = schemas.UnitsInput(
    force="tonf", moment="tonf·m", pressure="kgf/cm²",
    strength="kgf/cm²", length="m", unit_weight="tonf/m³",
)


# --- El formateador ------------------------------------------------------------

def test_por_omision_son_las_unidades_si_del_motor():
    u = ReportUnits()
    assert u.es_si
    assert u.fmt(21.0, "strength", 1) == "21.0"
    assert u.con(150.0, "pressure", 1) == "150.0 kPa"


def test_convierte_con_los_factores_del_registro():
    u = ReportUnits.from_input(PERUANAS)
    assert not u.es_si
    # 21 MPa = 214,14 kgf/cm²; 150 kPa = 1,53 kgf/cm²; 800 kN = 81,58 tonf
    assert u.fmt(21.0, "strength", 2) == "214.14"
    assert u.fmt(150.0, "pressure", 2) == "1.53"
    assert u.fmt(800.0, "force", 2) == "81.58"


def test_un_valor_ausente_se_escribe_como_raya():
    u = ReportUnits.from_input(PERUANAS)
    assert u.fmt(None, "pressure") == "—"
    assert u.con(None, "force") == "—"


def test_la_nota_declara_siempre_que_la_traza_va_en_si():
    assert "TRAZA" in ReportUnits().note().upper()
    assert "TRAZA" in ReportUnits.from_input(PERUANAS).note().upper()


def test_la_nota_enumera_las_unidades_declaradas():
    nota = ReportUnits.from_input(PERUANAS).note()
    assert "tonf" in nota and "kgf/cm²" in nota


# --- La memoria de la zapata aislada -------------------------------------------

def _peticion_aislada(
    units: schemas.UnitsInput, qadm: float, fc: float, fy: float, P: float, gamma: float
):
    return schemas.DesignRequest(
        project_name="unidades",
        materials=schemas.MaterialsInput(fc_MPa=fc, fy_MPa=fy),
        soil=schemas.SoilInput(qadm_kPa=qadm, gamma_kNm3=gamma, Df_m=1.5),
        units=units,
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=P),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=P * 1.4),
        ],
    ).model_dump(mode="json")


def _memoria(peticion: dict) -> str:
    diseño = cliente.post("/api/design", json=peticion)
    assert diseño.status_code == 200, diseño.text
    peticion = {**peticion, "alternative_id": diseño.json()["top"][0]["id"]}
    memoria = cliente.post("/api/report", json=peticion)
    assert memoria.status_code == 200, memoria.text
    return memoria.text


def _fila(html: str, etiqueta: str) -> str:
    m = re.search(rf"{re.escape(etiqueta)}</td>(.{{0,160}})", html, re.S)
    assert m, f"No aparece la fila «{etiqueta}» en la memoria"
    return m.group(1)


@pytest.fixture(scope="module")
def memoria_peruana() -> str:
    # El mismo problema físico que `memoria_si`, escrito en unidades peruanas.
    return _memoria(
        _peticion_aislada(PERUANAS, qadm=1.5, fc=210.0, fy=4200.0, P=81.58, gamma=1.8)
    )


@pytest.fixture(scope="module")
def memoria_si() -> str:
    return _memoria(
        _peticion_aislada(
            schemas.UnitsInput(), qadm=147.1, fc=20.6, fy=411.9, P=800.0, gamma=17.65
        )
    )


def test_la_memoria_escribe_los_datos_en_las_unidades_declaradas(memoria_peruana):
    suelo = _fila(memoria_peruana, "Presión admisible")
    assert "1.50" in suelo and "kgf/cm" in suelo
    materiales = _fila(memoria_peruana, "f&#x27;c") if "f&#x27;c" in memoria_peruana else _fila(memoria_peruana, "f'c")
    # La memoria escribe f'c con un decimal: «210.0», el valor que declaró el usuario.
    assert "210.0" in materiales and "kgf/cm" in materiales


def test_la_memoria_en_si_sigue_escribiendo_en_si(memoria_si):
    suelo = _fila(memoria_si, "Presión admisible")
    assert "147.10" in suelo and "kPa" in suelo


def test_la_memoria_declara_sus_unidades_y_la_traza_en_si(memoria_peruana):
    assert "Unidades declaradas" in memoria_peruana
    assert "TRAZA DE CÁLCULO" in memoria_peruana


def test_la_traza_conserva_las_unidades_si(memoria_peruana):
    """La sustitución numérica es el registro del cálculo; reescribirla lo falsearía."""
    assert "kPa" in memoria_peruana, "la traza debería seguir citando kPa"


def test_la_cabecera_de_combinaciones_lleva_la_unidad_elegida(memoria_peruana):
    assert "P (tonf" in memoria_peruana
    assert "Mx (tonf" in memoria_peruana


def test_la_carga_aparece_convertida_y_no_en_kN(memoria_peruana):
    """81,58 tonf se escriben 81,6 — no 800, que sería el número en kN."""
    assert re.search(r">81\.6<", memoria_peruana)
