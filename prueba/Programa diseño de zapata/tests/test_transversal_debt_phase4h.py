"""FASE 4H — deuda transversal.

1. `TraceView` indexaba la traza por `id`: en un resultado con varios componentes los ids
   se repiten (`punching` en las dos zapatas) y la vista mostraba una zapata bajo el
   rótulo de otra. La clave es ahora (ámbito, id), como `trace_key` del motor.
2. `/api/report-connected` repetía el barrido completo que acababa de hacer
   `/api/design-connected` con la misma petición. Ahora se sirve desde una caché acotada.
3. La hipótesis de α_s del punzonamiento decía siempre «columna interior», también con
   α_s = 30 en una zapata de lindero.

Ninguno cambia un número del motor: el congelamiento lo confirma aparte.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.server as server
from api.server import app
from tests.freeze.cases import CASES, CONNECTED_CASES
from tests.freeze.test_freeze_connected import _solve as _solve_conectada
from tests.freeze.test_freeze_isolated import _evaluate
from tests.test_connected_presentation_phase4e import _peticion

UI = Path(__file__).resolve().parent.parent / "ui" / "src"


# =========================================================================
# 1. TraceView
# =========================================================================


def test_traceview_agrupa_por_ambito_e_id():
    fuente = (UI / "components" / "TraceView.tsx").read_text(encoding="utf-8")
    assert "new Map(shown.map((e) => [e.id, e]))" not in fuente, (
        "El índice por id a secas pierde entradas repetidas entre ámbitos."
    )
    assert "new Map<string, TraceEntry[]>()" in fuente
    assert "export function traceKey" in fuente
    assert "key={e.id}" not in fuente
    assert fuente.count("key={traceKey(e)}") == 2


# =========================================================================
# 2. Caché del barrido de la conectada
# =========================================================================


@pytest.fixture
def contador(monkeypatch):
    server._connected_cache.clear()
    llamadas = {"n": 0}
    original = server._compute_connected_search

    def contar(request):
        llamadas["n"] += 1
        return original(request)

    monkeypatch.setattr(server, "_compute_connected_search", contar)
    yield llamadas
    server._connected_cache.clear()


def test_el_informe_reutiliza_el_barrido_del_diseno(contador):
    cliente = TestClient(app)
    peticion = _peticion()
    assert cliente.post("/api/design-connected", json=peticion).status_code == 200
    assert contador["n"] == 1
    r = cliente.post("/api/report-connected", json=dict(peticion, alternative_id=None))
    assert r.status_code == 200
    assert contador["n"] == 1, "el informe volvió a ejecutar el barrido completo"


def test_otra_peticion_es_otro_calculo(contador):
    cliente = TestClient(app)
    cliente.post("/api/design-connected", json=_peticion())
    otra = _peticion()
    otra["axis_distance_m"] = 6.2
    cliente.post("/api/design-connected", json=otra)
    assert contador["n"] == 2


def test_los_errores_no_se_guardan_en_la_cache(contador):
    cliente = TestClient(app)
    mala = _peticion(analysis_model="CUERPO_RIGIDO", couple_transfer_mode="PAR_PURO_EN_ZAPATA")
    assert cliente.post("/api/design-connected", json=mala).status_code == 422
    assert cliente.post("/api/design-connected", json=mala).status_code == 422
    assert len(server._connected_cache) == 0


def test_la_cache_esta_acotada(contador):
    cliente = TestClient(app)
    for i in range(server._CONNECTED_CACHE_SIZE + 2):
        p = _peticion()
        p["axis_distance_m"] = 6.0 + 0.1 * i
        cliente.post("/api/design-connected", json=p)
    assert len(server._connected_cache) == server._CONNECTED_CACHE_SIZE


def test_la_respuesta_desde_cache_es_identica(contador):
    cliente = TestClient(app)
    a = cliente.post("/api/design-connected", json=_peticion()).json()
    b = cliente.post("/api/design-connected", json=_peticion()).json()
    assert contador["n"] == 1
    assert a == b


# =========================================================================
# 3. Nota de α_s según la clasificación real
# =========================================================================


def _nota_alpha(trace, scope=None):
    entrada = trace.by_id("punching", scope=scope) if scope else trace.by_id("punching")
    return next(h for h in entrada.hypotheses if h.startswith("alpha_s"))


def test_la_zapata_de_lindero_ya_no_se_describe_como_columna_interior():
    c = next(x for x in CONNECTED_CASES if x.name == "Z11_aragon_p1_articulado")
    r = _solve_conectada(c)
    nota_ext = _nota_alpha(r.trace, "zap_ext")
    assert r.exterior.punching.column_position == "borde"
    assert "columna de borde" in nota_ext and "alpha_s=30" in nota_ext
    assert "columna interior" not in nota_ext
    assert "columna interior" in _nota_alpha(r.trace, "zap_int")


def test_la_aislada_concentrica_sigue_siendo_interior():
    r = _evaluate(CASES[0])
    nota = _nota_alpha(r.trace)
    assert r.punching.column_position == "interior"
    assert "columna interior" in nota and "alpha_s=40" in nota


def test_la_nota_sigue_la_clasificacion_en_todos_los_casos_congelados():
    for c in CASES:
        r = _evaluate(c)
        pos = r.punching.column_position
        nota = _nota_alpha(r.trace)
        esperado = "columna interior" if pos == "interior" else f"columna de {pos}"
        assert esperado in nota, (c.name, pos, nota)
