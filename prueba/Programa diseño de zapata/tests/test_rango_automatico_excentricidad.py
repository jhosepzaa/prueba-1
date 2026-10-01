"""El rango automático mira lo que hay que mirar (2026-09-24).

DOS CORRECCIONES, las dos medidas:

1. PRESIÓN DISPONIBLE. Estimaba `A ≈ P/qadm`. Con base BRUTA, el relleno y el concreto
   sobre la huella consumen parte de la capacidad antes de que la columna aporte nada, de
   modo que el área salía corta. Ahora se descuenta con la MISMA conversión de bases que
   usa el verificador.

2. EXCENTRICIDAD. La ignoraba por completo. El modelo de contacto por defecto exige la
   resultante dentro del núcleo central, lo que pide un lado del orden de 6·e. Con una
   columna de P = 600 kN y M = 900 kN·m (e = 1,50 m) el rango llegaba a 4,40 m y la mejor
   propuesta era de 18,39 m³; con la corrección llega a 9,90 m y la mejor es de 13,16 m³.

Sigue siendo una HEURÍSTICA de búsqueda: acota dónde mirar, no decide nada. Un rango mal
elegido solo puede hacer que no se encuentre la mejor, nunca que se acepte una mala.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.auto_search_range import (
    MAX_POINTS_PER_AXIS,
    estimate_search_range,
)

cliente = TestClient(app)


def _suelo(qadm: float = 150.0, basis: PressureBasis = PressureBasis.BRUTA) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=qadm, pressure_basis=basis, gamma_kNm3=18.0, Df_m=1.5,
        source_notes="dato de prueba",
    )


def _cargas(P: float, M: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[
            LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P, Mx_kNm=M)
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4, Mx_kNm=M * 1.4
            )
        ],
    )


# --- 1. Presión disponible -----------------------------------------------------

def test_descuenta_el_relleno_cuando_la_base_es_bruta():
    """Con Df = 1,5 m y γ = 18, el relleno se lleva 27 kPa de los 150 declarados."""
    rango = estimate_search_range(_cargas(900), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    esperada = 900.0 / (150.0 - 18.0 * 1.5)
    assert rango.estimated_area_m2 == pytest.approx(esperada, rel=1e-9)


def test_con_base_neta_no_descuenta_nada():
    """El `qadm` neto ya viene descontado: volver a restarlo sería contarlo dos veces."""
    rango = estimate_search_range(
        _cargas(900), _suelo(basis=PressureBasis.NETA), 0.4, 0.4, 0.1, 0.1, 0.05
    )
    assert rango.estimated_area_m2 == pytest.approx(900.0 / 150.0, rel=1e-9)


def test_si_el_relleno_se_come_la_capacidad_lo_dice_y_abre_el_rango():
    rango = estimate_search_range(_cargas(900), _suelo(qadm=20.0), 0.4, 0.4, 0.1, 0.1, 0.05)
    assert "presión disponible para la columna es nula" in rango.note
    assert rango.B_max_m > rango.B_min_m


# --- 2. Excentricidad ----------------------------------------------------------

def test_el_rango_alcanza_el_lado_que_pide_el_nucleo_central():
    """e = 1,50 m exige del orden de 6·e = 9,00 m para mantener la resultante dentro."""
    rango = estimate_search_range(_cargas(600, 900), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    assert rango.B_max_m >= 9.0
    assert "núcleo central" in rango.note


def test_sin_momento_la_excentricidad_no_ensancha_nada():
    con_momento = estimate_search_range(_cargas(600, 900), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    sin_momento = estimate_search_range(_cargas(600), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    assert sin_momento.B_max_m < con_momento.B_max_m
    assert "núcleo central" not in sin_momento.note


# --- 3. La malla sigue siendo manejable ----------------------------------------

def test_el_incremento_crece_con_el_rango_y_se_declara():
    rango = estimate_search_range(_cargas(600, 900), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    assert rango.B_step_m is not None and rango.B_step_m > 0.1
    assert "más gruesos que los pedidos" in rango.note
    puntos = (rango.B_max_m - rango.B_min_m) / rango.B_step_m + 1
    assert puntos <= MAX_POINTS_PER_AXIS


def test_con_rango_estrecho_se_respeta_el_incremento_pedido():
    rango = estimate_search_range(_cargas(400), _suelo(), 0.4, 0.4, 0.1, 0.1, 0.05)
    assert rango.B_step_m == pytest.approx(0.1)


# --- 4. De punta a punta -------------------------------------------------------

def test_con_excentricidad_el_optimo_ya_no_queda_contra_el_borde():
    """De punta a punta, con una excentricidad menor para que el barrido sea barato.

    El caso medido del encabezado (e = 1,50 m) se comprueba arriba sobre la heurística,
    que es donde está la corrección; repetirlo entero aquí costaba 87 s de suite para
    volver a demostrar lo mismo."""
    peticion = schemas.DesignRequest(
        soil=schemas.SoilInput(qadm_kPa=250, pressure_basis="BRUTA", gamma_kNm3=18, Df_m=1.5),
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=500, Mx_kNm=250),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=700, Mx_kNm=350),
        ],
    ).model_dump(mode="json")
    datos = cliente.post("/api/design", json=peticion).json()
    assert datos["top"], "el rango automático debe encontrar alternativas"
    assert datos["summary"]["search_boundary_note"] == "", (
        "con el rango corregido la recomendada ya no queda contra el borde"
    )
