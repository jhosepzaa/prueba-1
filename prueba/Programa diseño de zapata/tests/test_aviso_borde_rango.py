"""El barrido avisa cuando la recomendada queda contra el borde del rango (2026-09-24).

Un barrido solo puede elegir entre lo que miró. Si la alternativa recomendada cae en el
límite del rango explorado, lo más probable es que fuera haya algo mejor, y el programa
no tiene forma de saberlo: lo único honesto es decirlo.

El caso que lo motivó está en el primer test: con el rango estimado automáticamente la
mejor propuesta era un 46 % más voluminosa que la que aparece al ampliar el rango.

Este aviso NO cambia ningún resultado: ni descarta, ni acepta, ni mueve un número.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.optimization.search_boundary import (
    boundary_note,
    describe_boundary,
    dimension_at_limit,
)

cliente = TestClient(app)


# --- La detección, sin pasar por el motor --------------------------------------

def test_detecta_el_limite_superior_y_el_inferior():
    arriba = dimension_at_limit("B", 4.40, 1.10, 4.40, 0.10)
    assert arriba is not None and arriba.side == "máximo"
    abajo = dimension_at_limit("B", 1.10, 1.10, 4.40, 0.10)
    assert abajo is not None and abajo.side == "mínimo"


def test_no_avisa_cuando_la_solucion_esta_dentro():
    assert dimension_at_limit("B", 2.50, 1.10, 4.40, 0.10) is None


def test_la_tolerancia_es_medio_incremento():
    """El barrido solo produce valores de la malla; «pegado» es «el último que se miró»."""
    assert dimension_at_limit("h", 0.99, 0.40, 1.00, 0.05) is not None
    assert dimension_at_limit("h", 0.90, 0.40, 1.00, 0.05) is None


def test_el_peralte_no_avisa_de_su_limite_inferior():
    """El barrido elige el peralte mínimo viable de cada planta: tocar el mínimo del
    rango es lo NORMAL. Y E.060 §15.7 le pone piso, así que «pruebe con menos» sería
    sugerir algo que la norma no admite."""
    assert dimension_at_limit("h", 0.40, 0.40, 1.00, 0.05, warn_lower=False) is None
    # El límite SUPERIOR sí se avisa: ahí puede faltar por explorar.
    assert dimension_at_limit("h", 1.00, 0.40, 1.00, 0.05, warn_lower=False) is not None


def test_sin_valor_o_sin_incremento_no_se_inventa_un_aviso():
    assert dimension_at_limit("B", None, 1.0, 4.0, 0.1) is None
    assert dimension_at_limit("B", 4.0, 1.0, 4.0, 0.0) is None


def test_sin_dimensiones_tocadas_no_hay_texto():
    assert boundary_note([]) == ""
    tocadas, texto = describe_boundary([("B", 2.5, 1.0, 4.0, 0.1)])
    assert tocadas == [] and texto == ""


def test_el_aviso_nombra_la_dimension_y_el_limite():
    _, texto = describe_boundary([("B", 4.0, 1.0, 4.0, 0.1)])
    assert "LÍMITE SUPERIOR" in texto and "B = 4.00 m" in texto
    assert "amplíe el rango" in texto.lower()


# --- A través de la API --------------------------------------------------------

def _peticion(**busqueda):
    return schemas.DesignRequest(
        soil=schemas.SoilInput(qadm_kPa=150, pressure_basis="BRUTA", gamma_kNm3=18, Df_m=1.5),
        search=schemas.SearchInput(**busqueda),
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=600, Mx_kNm=900),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=840, Mx_kNm=1260),
        ],
    ).model_dump(mode="json")


@pytest.fixture(scope="module")
def con_rango_estrecho() -> dict:
    """Un rango declarado a mano que se queda corto: el óptimo cae en su máximo.

    Hasta que se corrigió la heurística (`test_rango_automatico_excentricidad.py`), el
    rango AUTOMÁTICO caía justo en este caso. Ahora que ya no, el aviso se comprueba con
    un rango estrecho explícito, que es la situación que seguirá dándose cuando el
    proyectista acote la búsqueda a mano."""
    return cliente.post(
        "/api/design",
        json=_peticion(
            B_min_m=1.2, B_max_m=4.4, B_step_m=0.2,
            L_min_m=1.2, L_max_m=4.4, L_step_m=0.2,
            h_min_m=0.4, h_max_m=1.2, h_step_m=0.05,
        ),
    ).json()["summary"]


@pytest.fixture(scope="module")
def con_rango_amplio() -> dict:
    return cliente.post(
        "/api/design",
        json=_peticion(
            # Acotado a la zona donde está la solución: basta para que el óptimo quede
            # INTERIOR, que es lo que este test comprueba, y el barrido cuesta la décima
            # parte que explorando de 1 a 8 m.
            B_min_m=3.6, B_max_m=5.6, B_step_m=0.2,
            L_min_m=3.6, L_max_m=5.6, L_step_m=0.2,
            h_min_m=0.5, h_max_m=1.0, h_step_m=0.05,
        ),
    ).json()["summary"]


def test_un_rango_corto_avisa_de_que_se_quedo_corto(con_rango_estrecho):
    """El óptimo cae en el máximo declarado: hay que decirlo."""
    aviso = con_rango_estrecho["search_boundary_note"]
    assert aviso, "debería avisar: la recomendada cae en el máximo explorado"
    assert "LÍMITE SUPERIOR" in aviso


def test_con_rango_holgado_no_hay_aviso(con_rango_amplio):
    assert con_rango_amplio["search_boundary_note"] == ""


def test_el_aviso_no_altera_la_busqueda(con_rango_estrecho):
    """Es presentación: el barrido evalúa y acepta exactamente lo mismo que antes."""
    assert con_rango_estrecho["n_evaluated"] > 0
    assert con_rango_estrecho["n_valid"] > 0


def test_las_tres_tipologias_declaran_el_campo():
    """Paridad: una advertencia útil en una tipología lo es en las tres."""
    for modelo in (
        schemas.DesignSummaryOut,
        schemas.CombinedDesignResponse,
        schemas.ConnectedDesignResponse,
    ):
        assert "search_boundary_note" in modelo.model_fields
