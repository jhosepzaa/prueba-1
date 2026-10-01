"""Pendiente 4 — los informes no sustituyen en silencio una `alternative_id` (CLAUDE.md §14).

Antes, `/api/report-combined` buscaba el id solo entre las `top_n` mostradas y, si no lo
encontraba, reportaba `top[0]`: el usuario recibía la memoria de OTRA zapata sin aviso.
`/api/report-connected` hacía lo mismo con la mejor clasificada.

Ahora:
- el id se busca entre TODAS las aceptadas de la búsqueda;
- un id inexistente responde 422 con el motivo;
- sin id, se reporta la primera del ordenamiento (comportamiento documentado).
"""

import pytest
from fastapi.testclient import TestClient

from api.server import app
from tests.test_api_combined_phase2 import _request as _combinada
from tests.test_connected_presentation_phase4e import _peticion as _conectada

cliente = TestClient(app)


# =========================================================================
# Combinada
# =========================================================================


@pytest.fixture(scope="module")
def diseno_combinado():
    peticion = dict(_combinada(), top_n=1)
    r = cliente.post("/api/design-combined", json=peticion)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["top"]) == 1
    assert len(d["comparison"]) > 1, "el caso debe tener aceptadas fuera de top_n"
    return peticion, d


def test_combinada_id_inexistente_da_422(diseno_combinado):
    peticion, _ = diseno_combinado
    r = cliente.post("/api/report-combined", json=dict(peticion, alternative_id="NO-EXISTE"))
    assert r.status_code == 422
    assert "NO-EXISTE" in r.text and "aceptadas" in r.text


def test_combinada_id_fuera_de_top_n_se_reporta_esa_alternativa(diseno_combinado):
    peticion, d = diseno_combinado
    ultima = d["comparison"][-1]["id"]
    assert ultima != d["top"][0]["id"]
    r = cliente.post("/api/report-combined", json=dict(peticion, alternative_id=ultima))
    assert r.status_code == 200, r.text
    assert f"alternativa {ultima}" in r.text
    assert f"alternativa {d['top'][0]['id']}" not in r.text


def test_combinada_sin_id_reporta_la_primera(diseno_combinado):
    peticion, d = diseno_combinado
    r = cliente.post("/api/report-combined", json=dict(peticion, alternative_id=None))
    assert r.status_code == 200, r.text
    assert f"alternativa {d['top'][0]['id']}" in r.text


# =========================================================================
# Conectada
# =========================================================================


@pytest.fixture(scope="module")
def diseno_conectado():
    peticion = _conectada()
    r = cliente.post("/api/design-connected", json=peticion)
    assert r.status_code == 200, r.text
    return peticion, r.json()


def _ids_conectada(d: dict) -> list[str]:
    return [a["id"] for a in d["accepted"]]


def test_conectada_id_inexistente_da_422(diseno_conectado):
    peticion, _ = diseno_conectado
    r = cliente.post("/api/report-connected", json=dict(peticion, alternative_id="NO-EXISTE"))
    assert r.status_code == 422
    assert "NO-EXISTE" in r.text and "aceptadas" in r.text


def test_conectada_id_existente_detalla_esa_alternativa(diseno_conectado):
    peticion, d = diseno_conectado
    ids = _ids_conectada(d)
    assert ids
    elegido = ids[-1]
    r = cliente.post("/api/report-connected", json=dict(peticion, alternative_id=elegido))
    assert r.status_code == 200, r.text
    assert f"Memoria de la alternativa {elegido}" in r.text


def test_conectada_sin_id_se_sirve(diseno_conectado):
    peticion, _ = diseno_conectado
    r = cliente.post("/api/report-connected", json=dict(peticion, alternative_id=None))
    assert r.status_code == 200, r.text
