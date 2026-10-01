"""Peraltes alternativos en el frente de Pareto (2026-09-24).

EL PROBLEMA. El barrido tomaba, para cada planta, el primer peralte que no falla y ahí
se detenía. Un peralte mayor gasta más concreto pero puede necesitar menos acero, de modo
que ninguno de los dos domina al otro: son puntos distintos del compromiso. Al no
generarlos, el «frente de Pareto» que veía el proyectista no era el frente.

Medido en el caso de estos tests: el frente pasa de 2 a 3 puntos, y el que aparece
—misma planta, 5 cm más de peralte— gasta un 10 % más de concreto y un 12 % menos de
acero.

LO QUE NO SE HACE, y por qué está bien. Solo se refinan las alternativas del frente:
refinar todas triplicaba el tiempo del barrido y llenaba la tabla de variantes de plantas
ya dominadas. Queda declarado que la variante de una planta dominada podría, en teoría,
pertenecer al frente real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import schemas
from api.server import app
from engine.optimization import alternative_generator as generador

cliente = TestClient(app)


def _peticion() -> dict:
    return schemas.DesignRequest(
        soil=schemas.SoilInput(qadm_kPa=150, pressure_basis="BRUTA", gamma_kNm3=18, Df_m=1.5),
        search=schemas.SearchInput(
            B_min_m=3.6, B_max_m=4.6, B_step_m=0.2,
            L_min_m=3.6, L_max_m=4.6, L_step_m=0.2,
            h_min_m=0.45, h_max_m=1.0, h_step_m=0.05,
        ),
        combinations=[
            schemas.LoadCombinationInput(name="S1", type="SERVICIO", P_kN=900, Mx_kNm=180),
            schemas.LoadCombinationInput(name="U1", type="FACTORIZADA", P_kN=1260, Mx_kNm=252),
        ],
    ).model_dump(mode="json")


def _tabla() -> list[dict]:
    return cliente.post("/api/design", json=_peticion()).json()["table"]


@pytest.fixture(scope="module")
def tabla() -> list[dict]:
    return _tabla()


def test_el_frente_incluye_una_variante_de_peralte(tabla):
    """Dos alternativas con la MISMA planta y distinto peralte, ambas en el frente."""
    frente = [f for f in tabla if f["in_pareto"]]
    plantas = [(round(f["B_m"], 3), round(f["L_m"], 3)) for f in frente]
    repetida = [p for p in plantas if plantas.count(p) > 1]
    assert repetida, (
        "el frente debería contener una planta con dos peraltes: es el compromiso "
        f"concreto/acero que esta mejora expone. Frente: {frente}"
    )


def test_la_variante_gasta_mas_concreto_y_menos_acero(tabla):
    frente = sorted(
        (f for f in tabla if f["in_pareto"]), key=lambda f: f["concrete_volume_m3"]
    )
    por_planta: dict[tuple, list[dict]] = {}
    for f in frente:
        por_planta.setdefault((round(f["B_m"], 3), round(f["L_m"], 3)), []).append(f)
    pares = [v for v in por_planta.values() if len(v) > 1]
    assert pares, "no hay ninguna planta con dos peraltes en el frente"
    for bajo, alto in ((v[0], v[1]) for v in pares):
        assert alto["h_m"] > bajo["h_m"]
        assert alto["concrete_volume_m3"] > bajo["concrete_volume_m3"]
        assert alto["steel_mass_kg"] < bajo["steel_mass_kg"]


def test_sin_refinar_el_frente_es_mas_pobre(monkeypatch):
    """La comprobación honesta: con el comportamiento anterior, ese punto no existe."""
    monkeypatch.setattr(generador, "EXTRA_DEPTH_STEPS", 0)
    antes = [f for f in _tabla() if f["in_pareto"]]
    monkeypatch.undo()
    despues = [f for f in _tabla() if f["in_pareto"]]
    assert len(despues) > len(antes)


def test_las_variantes_pasan_las_mismas_verificaciones(tabla):
    """No se relaja nada: una variante que fallara no entraría, igual que cualquier otra."""
    assert all(f["status"] != "FAIL" for f in tabla)


def test_el_recuento_de_geometrias_no_cuenta_alternativas(tabla):
    """Una planta puede aportar varias alternativas, así que los dos números difieren.

    `n_evaluated` son PLANTAS (B, L); `n_valid`, alternativas. Antes coincidían porque
    cada planta daba como mucho una; ahora el recuento de plantas se lleva explícito."""
    resumen = cliente.post("/api/design", json=_peticion()).json()["summary"]
    plantas_validas = len({(round(f["B_m"], 3), round(f["L_m"], 3)) for f in tabla})
    assert resumen["n_evaluated"] == plantas_validas + resumen["n_discarded"]
    assert resumen["n_valid"] > plantas_validas, "alguna planta aporta más de un peralte"


# --- La parada demostrable -----------------------------------------------------

class _Flexion:
    def __init__(self, requerido: float, minimo: float):
        self.As_required_m2 = requerido
        self.As_min_m2 = minimo


def test_si_manda_la_cuantia_minima_no_se_buscan_peraltes_mayores():
    """`As_min = ρ_min·b·h` CRECE con el peralte: más canto solo puede pedir más acero."""
    assert generador._gobierna_el_minimo(_Flexion(1e-4, 2e-4)) is True
    assert generador._gobierna_el_minimo(_Flexion(3e-4, 2e-4)) is False


def test_sin_momento_manda_el_minimo():
    """Sin flexión que resistir, `As_required` es NaN y el mínimo es quien fija el acero."""
    assert generador._gobierna_el_minimo(_Flexion(float("nan"), 2e-4)) is True
