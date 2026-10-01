"""Pendiente 8 — vocabulario ÚNICO de estados de alternativa.

EL PROBLEMA QUE CIERRA
======================
La misma palabra significaba cosas distintas: «ACEPTADA» era PASS/INFO en la zapata
aislada y WARNING —«con reservas»— en la conectada. Y «DESCARTADA» / «RECHAZADA» eran dos
nombres del mismo estado. Una vista común habría hecho pasar una conectada con
observaciones por una aislada que cumple.

QUÉ FIJA ESTE ARCHIVO
=====================
1. hay UNA sola fuente del rótulo y los tres productores la usan;
2. el mapa estado → rótulo es exacto, y la palabra ambigua ya no existe;
3. un pendiente abierto impide CONFORME;
4. **la semántica interna NO cambia**: `accepted`, `not_verified` y
   `accepted_and_compliant` siguen significando lo mismo y contando lo mismo;
5. la API entrega el estado crudo Y el rótulo, sin que la UI derive ninguno.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.integration.typology_catalog import CATALOG
from engine.optimization.discard_explainer import Explanation
from engine.reports.connected_report import (
    ESTADO_ACEPTADA,
    ESTADO_CONFORME,
    ESTADO_NO_VERIFICADA,
    ESTADO_RECHAZADA,
    alternative_label,
)
from engine.reports.report_model import status_label as label_aislada
from engine.results.status import CheckStatus
from engine.results.vocabulary import (
    LEGACY_EQUIVALENCE,
    STATUS_VOCABULARY,
    status_label,
)

ESPERADO = {
    CheckStatus.PASS: "CONFORME",
    CheckStatus.INFO: "CONFORME",
    CheckStatus.WARNING: "ACEPTADA CON OBSERVACIONES",
    CheckStatus.NOT_VERIFIED: "NO VERIFICADA",
    CheckStatus.FAIL: "RECHAZADA",
}


# =========================================================================
# 1. Una sola fuente, tres consumidores
# =========================================================================


@pytest.mark.parametrize("estado", list(CheckStatus))
def test_el_mapa_de_estado_a_rotulo_es_exacto(estado):
    assert status_label(estado) == ESPERADO[estado]


@pytest.mark.parametrize("estado", list(CheckStatus))
def test_la_aislada_usa_el_mismo_rotulo_que_la_fuente(estado):
    assert label_aislada(estado) == status_label(estado)


@pytest.mark.parametrize("estado", list(CheckStatus))
def test_la_explicacion_de_descartes_usa_el_mismo_rotulo(estado):
    """Era la tercera copia del mapa: `discard_explainer` tenía el suyo."""
    e = Explanation(alternative_id="A-1", B_m=2.0, L_m=2.0, h_m=0.5, verdict=estado,
                    failed=[], warnings=[], not_verified=[], passed=[], informative=[])
    assert e.to_text().splitlines()[0] == f"A-1 -- {status_label(estado)}"


def test_la_conectada_usa_el_mismo_rotulo():
    """`alternative_label` decide con el estado y los pendientes abiertos, igual que la
    fuente. Se comprueba con dobles, sin depender de un barrido."""

    class _Alt:
        def __init__(self, estado, tbds=()):
            self.overall_status = estado
            self.open_tbds = list(tbds)

    for estado in CheckStatus:
        assert alternative_label(_Alt(estado)) == status_label(estado)
        assert alternative_label(_Alt(estado, ("TBD-C1",))) == status_label(estado, ["TBD-C1"])


def test_las_constantes_de_la_conectada_apuntan_al_vocabulario_unico():
    assert {ESTADO_CONFORME, ESTADO_ACEPTADA, ESTADO_NO_VERIFICADA, ESTADO_RECHAZADA} == set(
        STATUS_VOCABULARY
    )
    assert ESTADO_ACEPTADA == "ACEPTADA CON OBSERVACIONES", "El rótulo ambiguo se renombró"


# =========================================================================
# 2. La palabra ambigua desapareció
# =========================================================================


def test_aceptada_a_secas_ya_no_es_un_rotulo():
    assert "ACEPTADA" not in STATUS_VOCABULARY
    assert all(status_label(e) != "ACEPTADA" for e in CheckStatus)


def test_descartada_y_rechazada_dejan_de_ser_dos_nombres_del_mismo_estado():
    assert "DESCARTADA" not in STATUS_VOCABULARY
    assert status_label(CheckStatus.FAIL) == "RECHAZADA"


def test_el_vocabulario_tiene_cuatro_terminos_en_orden_de_desenlace():
    assert STATUS_VOCABULARY == [
        "CONFORME", "ACEPTADA CON OBSERVACIONES", "NO VERIFICADA", "RECHAZADA",
    ]
    assert len(set(STATUS_VOCABULARY)) == 4


def test_se_conserva_la_equivalencia_con_los_rotulos_anteriores():
    """CLAUDE.md §16: quien lea un informe anterior tiene que poder traducirlo."""
    assert LEGACY_EQUIVALENCE["ACEPTADA (aislada, PASS/INFO)"] == "CONFORME"
    assert LEGACY_EQUIVALENCE["ACEPTADA (conectada, WARNING)"] == "ACEPTADA CON OBSERVACIONES"
    assert LEGACY_EQUIVALENCE["DESCARTADA (aislada)"] == "RECHAZADA"
    assert set(LEGACY_EQUIVALENCE.values()) <= set(STATUS_VOCABULARY)


# =========================================================================
# 3. Un pendiente abierto impide CONFORME
# =========================================================================


def test_un_pendiente_abierto_degrada_conforme_a_no_verificada():
    for estado in (CheckStatus.PASS, CheckStatus.INFO):
        assert status_label(estado) == "CONFORME"
        assert status_label(estado, ["TBD-C1"]) == "NO VERIFICADA"


def test_un_pendiente_abierto_nunca_mejora_un_rotulo():
    for estado in CheckStatus:
        sin, con = status_label(estado), status_label(estado, ["TBD-C1"])
        if sin != "CONFORME":
            assert con == sin, "Solo CONFORME puede degradarse"
    assert status_label(CheckStatus.FAIL, ["TBD-C1"]) == "RECHAZADA"


# =========================================================================
# 4. La semántica interna NO cambia
# =========================================================================


def test_las_particiones_de_la_combinada_siguen_significando_lo_mismo():
    """`accepted` ≠ `not_verified` ≠ `accepted_and_compliant`: el rótulo es otra cosa."""
    from engine.optimization.combined_generator import CombinedAlternativeSet

    for nombre in ("accepted", "not_verified", "accepted_with_findings", "accepted_and_compliant"):
        assert isinstance(getattr(CombinedAlternativeSet, nombre), property)
    fuente = io.open("engine/optimization/combined_generator.py", encoding="utf-8").read()
    assert "CheckStatus.PASS, CheckStatus.INFO" in fuente, "La partición conforme sigue siendo PASS/INFO"
    assert "not r.overall_status.discards" in fuente, "La aceptación sigue siendo NO_FAIL"


def test_el_criterio_de_aceptacion_no_depende_del_rotulo():
    from engine.integration.typology_catalog import AcceptanceRule, accepts

    assert accepts(AcceptanceRule.NO_FAIL, CheckStatus.WARNING) is True
    assert accepts(AcceptanceRule.NO_FAIL, CheckStatus.FAIL) is False
    fuente = io.open("engine/results/vocabulary.py", encoding="utf-8").read()
    for prohibido in ("accepts(", "AcceptanceRule", "discards"):
        assert prohibido not in fuente, f"El vocabulario no decide nada: {prohibido}"


# =========================================================================
# 5. Catálogo y API
# =========================================================================


def test_las_tres_tipologias_declaran_el_mismo_vocabulario():
    vocabularios = [t.status_vocabulary for t in CATALOG.typologies]
    assert all(v == STATUS_VOCABULARY for v in vocabularios)
    dif = {k.id: k for k in CATALOG.known_differences}
    assert dif["VOCABULARIO_ACEPTADA"].resolution is not None
    assert dif["VOCABULARIO_ACEPTADA"].is_open is False


def test_la_api_entrega_estado_crudo_y_rotulo_por_separado():
    from tests.test_api_combined_phase2 import _request

    d = TestClient(app).post("/api/design-combined", json=_request()).json()
    a = d["top"][0]
    assert a["status"] == "PASS", "El criterio sigue viajando como CheckStatus"
    assert a["status_label"] == "CONFORME", "El rótulo es del vocabulario único"
    assert d["comparison"][0]["status_label"] in STATUS_VOCABULARY
    assert d["scene"]["status_label"] == a["status_label"]


def test_la_ui_no_deriva_el_rotulo():
    """El rótulo llega del servidor; si cada cliente calculara el suyo acabarían
    divergiendo, y el que divergiría es el que dice si algo cumple."""
    api_ts = io.open("ui/src/lib/api.ts", encoding="utf-8").read()
    assert '"ACEPTADA CON OBSERVACIONES"' in api_ts
    assert '\n  | "ACEPTADA"\n' not in api_ts, "El rótulo ambiguo ya no está en el contrato"
    vista = io.open("ui/src/components/ConnectedResultsView.tsx", encoding="utf-8").read()
    assert "status_label" in vista
    assert '"ACEPTADA CON OBSERVACIONES": "warn"' in vista
