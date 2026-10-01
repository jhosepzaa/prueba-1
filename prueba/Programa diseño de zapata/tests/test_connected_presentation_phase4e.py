"""FASE 4E — contrato de la capa de presentación de la cimentación conectada.

QUÉ SE VERIFICA
===============
Una sola cosa, desde tres ángulos: **que el estado real sobreviva al cruce de capas**.

El motor de 4D dejó cerradas dos distinciones que cuestan trabajo y que se pierden con
una facilidad desproporcionada:

1. ACEPTADA ≠ CONFORME. Una alternativa que supera todas las verificaciones
   implementadas sigue siendo NO VERIFICADA mientras TBD-C1 no tenga criterio que
   aplicar.
2. NO VERIFICADO por un TBD ≠ NO VERIFICADO por un dato que falta. El primero no lo
   puede cerrar el proyectista; el segundo sí.

Las dos viajan en `@property` del motor, y pydantic **no serializa propiedades**: basta
olvidar un campo en un DTO para que un NO VERIFICADO llegue al navegador convertido en
«una alternativa más». Estos tests existen para que ese olvido falle en CI y no en la
pantalla de un proyectista.

Se comprueban las tres capas:

* **Informe** — el bloque de estado va ANTES de la tabla, y el HTML no afirma que algo
  cumpla cuando no hay ninguna alternativa conforme.
* **API** — los siete campos exigidos viajan como campos explícitos, con `open_tbd` y
  `scope` intactos en la traza.
* **UI** — los fuentes de TypeScript consumen esos campos y no rotulan `accepted` como
  «válida».
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.reports.connected_report import (
    ESTADO_ACEPTADA,
    ESTADO_CONFORME,
    ESTADO_NO_VERIFICADA,
    ESTADO_RECHAZADA,
    build_connected_status_summary,
    render_connected_report_html,
)
from engine.results.status import CheckStatus

import tests.test_connected_search_phase4d as motor

RAIZ = Path(__file__).resolve().parent.parent
UI = RAIZ / "ui" / "src"


# =========================================================================
# Utilidades compartidas
# =========================================================================


def _combos(P: float, M: float = 0.0) -> list[dict]:
    return [
        {"name": "S1", "type": "SERVICIO", "P_kN": P, "Mx_kNm": M},
        {"name": "U1", "type": "FACTORIZADA", "P_kN": P * 1.4, "Mx_kNm": M * 1.4},
    ]


def _peticion(**cambios) -> dict:
    base = {
        "project_name": "Contrato 4E",
        "analysis_model": "ARTICULADO",
        "couple_transfer_mode": "EQUILIBRIO_EN_CIMENTACION",
        # Gancho de 90° en la zapata de lindero (2026-09-28, E.060 §15.6.2).
        "exterior": {"label": "Z1", "bx_m": 0.50, "by_m": 0.50,
                     "hook_type_x": "90", "hook_type_y": "90",
                     "combinations": _combos(850.0)},
        "interior": {"label": "Z2", "bx_m": 0.50, "by_m": 0.50,
                     "combinations": _combos(1100.0)},
        "anchor": {"edge": "X_MIN", "face_clearance_m": 0.0},
        "beam": {"b_m": 0.35, "h_m": 1.20, "d_m": 1.10,
                 "support_mode": "SIN_APOYO", "self_weight_mode": "DESPRECIADO"},
        "axis_distance_m": 6.0,
        "soil": {"qadm_kPa": 250.0, "gamma_kNm3": 18.0, "Df_m": 1.50,
                 "FS_overturning_required": 1.5, "source_notes": "contrato"},
        "search": {
            "ext_long_min_m": 2.0, "ext_long_max_m": 2.8, "ext_long_step_m": 0.4,
            "ext_transv_min_m": 2.4, "ext_transv_max_m": 2.8, "ext_transv_step_m": 0.4,
            "int_long_min_m": 2.2, "int_long_max_m": 2.6, "int_long_step_m": 0.4,
            "int_transv_min_m": 2.2, "int_transv_max_m": 2.6, "int_transv_step_m": 0.4,
            "h_min_m": 0.60, "h_max_m": 1.00, "h_step_m": 0.20,
            "same_depth_both_footings": True, "max_systems": 400,
        },
        "top_n": 3,
    }
    base.update(cambios)
    return base


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def respuesta(cliente: TestClient) -> dict:
    r = cliente.post("/api/design-connected", json=_peticion())
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def conjunto():
    """El barrido directo del motor, para contrastar contra lo que sirve la API."""
    return motor._buscar(soil=motor.SUELO_CON_FS)


def _fuente_ui(nombre: str) -> str:
    return io.open(UI / nombre, encoding="utf-8").read()


# =========================================================================
# 1. Informe — se emite, y en el orden correcto
# =========================================================================


def test_el_informe_se_emite_con_todo_NO_VERIFICADO(conjunto):
    """El caso normal de esta tipología. Negarse a emitir dejaría la herramienta
    inservible; emitir como si fuera conforme sería peor."""
    assert conjunto.accepted
    assert conjunto.accepted_and_compliant == []

    html = render_connected_report_html(conjunto)
    assert "<!doctype html>" in html
    assert CheckStatus.NOT_VERIFIED.value in html


def test_el_informe_se_emite_aunque_no_haya_ninguna_aceptada():
    """A diferencia de la combinada, «no hay nada que reportar» aquí es falso: que el
    barrido entero se cayera por despegue es justo lo que hay que leer."""
    vacio = motor._buscar(
        motor._layout(modelo=motor.AnalysisModel.CUERPO_RIGIDO, M_ext=9000.0)
    )
    assert vacio.accepted == []

    html = render_connected_report_html(vacio)
    assert "<!doctype html>" in html
    assert "DESPEGUE" in html
    assert "RECHAZAD" in html


def test_el_estado_y_los_pendientes_van_antes_de_la_tabla(conjunto):
    """Requisito de orden, no de contenido: quien lea solo la tabla tiene que haber
    pasado por el estado. Si el bloque migrara al pie, este test lo detecta."""
    html = render_connected_report_html(conjunto)

    pos_estado = html.find("Estado del análisis")
    pos_pendientes = html.find("Pendientes abiertos")
    pos_tabla = html.find("Alternativas aceptadas")

    assert pos_estado != -1 and pos_pendientes != -1 and pos_tabla != -1
    assert pos_estado < pos_tabla, "El estado quedó después de la tabla de alternativas"
    assert pos_pendientes < pos_tabla, "Los pendientes quedaron después de la tabla"


def test_el_informe_nombra_el_pendiente_que_bloquea(conjunto):
    html = render_connected_report_html(conjunto)
    assert "TBD-C1" in html
    # Y explica qué es, para no obligar a buscarlo en otro documento.
    assert "no tiene criterio normativo" in html


def test_el_informe_no_afirma_que_algo_cumpla_sin_alternativas_conformes(conjunto):
    """La regla dura. El informe puede decir «no cumple», «no declara que cumpla» o
    nombrar el motivo de rechazo NO_CUMPLE; lo que no puede es afirmarlo."""
    resumen = build_connected_status_summary(conjunto)
    assert resumen.accepted_and_compliant_count == 0
    assert resumen.can_claim_compliance is False

    assert "NO declara que ninguna cumpla" in resumen.headline
    assert ESTADO_CONFORME not in resumen.headline


def test_el_informe_no_llama_valida_a_ninguna_alternativa(conjunto):
    """«Válida» se lee como «correcta». Se comprueba sobre el HTML producido, no sobre
    el código fuente: lo que importa es lo que el usuario ve."""
    html = render_connected_report_html(conjunto)
    assert not re.search(r"\bválid", html, re.IGNORECASE)
    assert not re.search(r"\bvalid[ao]s?\b", html, re.IGNORECASE)


def test_el_informe_separa_las_cuatro_categorias(conjunto):
    html = render_connected_report_html(conjunto)
    for rotulo in (ESTADO_RECHAZADA, ESTADO_ACEPTADA, ESTADO_NO_VERIFICADA, ESTADO_CONFORME):
        assert rotulo in html, f"Falta la categoría {rotulo} en el informe"
    # Y cada una con su definición al lado, no como número suelto.
    assert "Aceptada no significa conforme" in html


def test_el_informe_marca_las_entradas_de_traza_con_pendiente(conjunto):
    """La columna que distingue un hueco normativo de un dato que falta."""
    html = render_connected_report_html(conjunto)
    assert "Pendiente</th>" in html
    assert "señala un dato que el proyectista no declaró" in html


# =========================================================================
# 2. API — los siete campos exigidos, explícitos
# =========================================================================

CAMPOS_EXIGIDOS = (
    "overall_status",
    "implemented_checks_status",
    "open_tbds",
    "accepted",
    "not_verified",
    "accepted_and_compliant",
    "rejected",
)


def test_la_respuesta_trae_los_campos_exigidos(respuesta):
    """`implemented_checks_status` vive en cada alternativa; los otros seis, en la
    raíz. Los siete tienen que estar."""
    for campo in CAMPOS_EXIGIDOS:
        if campo == "implemented_checks_status":
            assert respuesta["accepted"], "Sin alternativas no se puede comprobar"
            assert campo in respuesta["accepted"][0]
        else:
            assert campo in respuesta, f"Falta «{campo}» en la respuesta"


def test_ningun_campo_del_contrato_depende_de_una_property():
    """La trampa concreta: pydantic NO serializa `@property`. Si alguno de los campos
    del contrato se declarase como propiedad del DTO en vez de como campo, el JSON
    saldría sin él y nadie se enteraría hasta ver la pantalla."""
    from api import schemas

    campos_raiz = set(schemas.ConnectedDesignResponse.model_fields)
    campos_alt = set(schemas.ConnectedAlternativeOut.model_fields)

    for campo in CAMPOS_EXIGIDOS:
        assert campo in campos_raiz or campo in campos_alt, (
            f"«{campo}» no es un campo declarado: si es una @property, no se serializa."
        )

    # Los recuentos también, porque son lo que la UI muestra.
    for campo in ("can_claim_compliance", "headline", "accepted_count",
                  "not_verified_count", "accepted_and_compliant_count",
                  "rejected_count", "truncated", "search_note"):
        assert campo in campos_raiz


def test_el_NO_VERIFICADO_llega_intacto_al_JSON(respuesta):
    """El cruce completo: motor -> DTO -> JSON serializado."""
    crudo = json.dumps(respuesta, ensure_ascii=False)

    assert respuesta["overall_status"] == CheckStatus.NOT_VERIFIED.value
    assert respuesta["can_claim_compliance"] is False
    assert respuesta["accepted_and_compliant"] == []
    assert respuesta["accepted_and_compliant_count"] == 0
    assert respuesta["not_verified_count"] == respuesta["accepted_count"] > 0
    assert CheckStatus.NOT_VERIFIED.value in crudo


def test_cada_alternativa_lleva_sus_dos_estados_por_separado(respuesta):
    """`implemented_checks_status` PASS junto a `overall_status` NO VERIFICADO es
    exactamente la situación que no se puede colapsar en una sola etiqueta."""
    a = respuesta["accepted"][0]
    assert a["overall_status"] == CheckStatus.NOT_VERIFIED.value
    # Fase 10B: las verificaciones implementadas pueden quedar NO VERIFICADAS por la
    # estabilidad de las zapatas (E.020 art. 20.1: cargas corregidas sin composición). Lo que
    # este test protege es que el campo viaje por separado del estado global.
    assert a["implemented_checks_status"] in (CheckStatus.PASS.value, CheckStatus.NOT_VERIFIED.value)
    assert a["open_tbds"] == ["TBD-C1"]
    assert a["status_label"] == ESTADO_NO_VERIFICADA


def test_los_pendientes_llegan_nombrados_y_descritos(respuesta):
    assert respuesta["open_tbds"], "La respuesta perdió los pendientes abiertos"
    t = respuesta["open_tbds"][0]
    assert t["id"] == "TBD-C1"
    assert t["description"]
    assert t["affected_alternatives"] == respuesta["accepted_count"]


def test_la_traza_conserva_open_tbd_y_scope(respuesta):
    """Sin `open_tbd` la UI no podría distinguir un hueco normativo de un dato que
    falta; sin `scope`, mostraría el punzonamiento de una zapata bajo el rótulo de la
    otra —los ids se repiten entre las dos—."""
    assert respuesta["trace"], "La respuesta no trae traza"

    con_pendiente = [e for e in respuesta["trace"] if e.get("open_tbd")]
    assert con_pendiente, "Se perdió `open_tbd` al cruzar la API"
    assert con_pendiente[0]["open_tbd"] == "TBD-C1"
    assert con_pendiente[0]["status"] == CheckStatus.NOT_VERIFIED.value

    ambitos = {e.get("scope") for e in respuesta["trace"]}
    assert {"sistema", "zap_ext", "zap_int", "viga"} <= ambitos

    # Y la distinción: hay entradas NO VERIFICADO SIN pendiente —lo que falta es
    # información del proyecto (la composición de las cargas, E.020 art. 20.1), no un
    # criterio del motor—.
    #
    # El modelo es CUERPO_RIGIDO porque desde FORMULACION_VOLTEO (2026-09-19) es donde el
    # volcamiento de las zapatas conserva demanda: con ARTICULADO la viga recentra cada
    # componente de la carga corregida, el momento neto es nulo y la verificación se
    # declara no aplicable, de modo que no habría ninguna entrada que clasificar.
    sin_fs = TestClient(app).post(
        "/api/design-connected",
        json=_peticion(analysis_model="CUERPO_RIGIDO",
                       soil={"qadm_kPa": 250.0, "gamma_kNm3": 18.0, "Df_m": 1.50,
                             "source_notes": "sin FS"}),
    ).json()
    huerfanas = [
        e for e in sin_fs["trace"]
        if e["status"] == CheckStatus.NOT_VERIFIED.value and not e.get("open_tbd")
    ]
    assert huerfanas, (
        "Debe existir al menos una entrada NO VERIFICADO que NO sea un pendiente del motor."
    )
    assert all("overturning" in e["id"] for e in huerfanas), [e["id"] for e in huerfanas]


def test_los_rechazos_llegan_con_su_motivo(respuesta):
    assert respuesta["rejected"]
    assert respuesta["rejected_count"] == respuesta["evaluated_count"] - respuesta["accepted_count"]
    assert set(respuesta["rejections_by_reason"]) <= {
        "GEOMETRIA_IMPOSIBLE", "DESPEGUE", "CARGA_NETA_ASCENDENTE", "ENTRADA_INVALIDA", "NO_CUMPLE"
    }
    assert respuesta["rejected"][0]["reason"]


def test_la_API_no_devuelve_error_cuando_nada_esta_verificado(cliente):
    """Devolver 422 por NO VERIFICADO dejaría el endpoint inservible: es el estado
    normal de esta tipología."""
    r = cliente.post("/api/design-connected", json=_peticion())
    assert r.status_code == 200
    assert r.json()["overall_status"] == CheckStatus.NOT_VERIFIED.value


def test_la_API_responde_200_aunque_no_haya_ninguna_aceptada(cliente):
    r = cliente.post(
        "/api/design-connected",
        json=_peticion(
            analysis_model="CUERPO_RIGIDO",
            exterior={"label": "Z1", "bx_m": 0.50, "by_m": 0.50,
                      "combinations": _combos(850.0, 9000.0)},
        ),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["accepted_count"] == 0
    assert d["overall_status"] == CheckStatus.FAIL.value
    assert d["rejections_by_reason"] == {"DESPEGUE": d["rejected_count"]}
    # El titular nombra el motivo real, no «no superó las verificaciones».
    assert "DESPEGUE" in d["headline"]


def test_el_informe_de_la_API_se_sirve_siempre(cliente):
    for peticion in (
        _peticion(),
        _peticion(
            analysis_model="CUERPO_RIGIDO",
            exterior={"label": "Z1", "bx_m": 0.50, "by_m": 0.50,
                      "combinations": _combos(850.0, 9000.0)},
        ),
    ):
        r = cliente.post("/api/report-connected", json=peticion)
        assert r.status_code == 200, r.text
        assert "<!doctype html>" in r.text


def test_el_tope_y_el_peralte_compartido_cruzan_la_API(cliente):
    """Los dos parámetros que la decisión de 4D dejó editables."""
    r = cliente.post("/api/design-connected", json=_peticion(
        search={**_peticion()["search"], "max_systems": 20}
    ))
    d = r.json()
    assert d["evaluated_count"] == 20
    assert d["truncated"] is True
    assert "max_systems" in d["search_note"]

    from api import schemas
    campos = schemas.ConnectedSearchInput.model_fields
    assert campos["same_depth_both_footings"].default is False
    assert campos["max_systems"].default > 0


def test_los_DTO_no_usan_la_palabra_valida():
    """El vocabulario cerrado también rige en el esquema: un campo `valid` reaparecería
    en el JSON, en la documentación de OpenAPI y en cualquier cliente."""
    from api import schemas

    for modelo in (schemas.ConnectedDesignResponse, schemas.ConnectedAlternativeOut):
        for nombre in modelo.model_fields:
            assert "valid" not in nombre.lower(), (
                f"«{nombre}» en {modelo.__name__} usa el vocabulario prohibido."
            )


# =========================================================================
# 3. UI — el contrato se consume y no se re-rotula
# =========================================================================


def test_la_UI_declara_la_tercera_tipologia():
    app_tsx = _fuente_ui("App.tsx")
    assert "Cimentación conectada" in app_tsx
    assert '"conectada"' in app_tsx
    assert "ConnectedResultsView" in app_tsx
    assert "ConnectedInputPanel" in app_tsx


def test_la_UI_consume_los_campos_del_contrato():
    """Que el campo viaje en el JSON no sirve de nada si la vista no lo lee."""
    vista = _fuente_ui("components/ConnectedResultsView.tsx")
    for campo in (
        "overall_status", "implemented_checks_status", "open_tbds",
        "accepted", "not_verified_count", "accepted_and_compliant_count",
        "rejected", "can_claim_compliance", "status_label",
    ):
        assert campo in vista, f"La vista no consume «{campo}»"


def test_la_UI_usa_el_vocabulario_cerrado():
    vista = _fuente_ui("components/ConnectedResultsView.tsx")
    for rotulo in (ESTADO_RECHAZADA, ESTADO_ACEPTADA, ESTADO_NO_VERIFICADA, ESTADO_CONFORME):
        assert rotulo in vista, f"Falta el rótulo {rotulo}"


def test_la_UI_no_rotula_las_aceptadas_como_validas():
    """Se revisa el TEXTO VISIBLE, no el código: `invalid` o `validate` en una variable
    no engañan a nadie, pero la palabra en pantalla sí."""
    for nombre in ("components/ConnectedResultsView.tsx",
                   "components/ConnectedInputPanel.tsx"):
        fuente = _fuente_ui(nombre)
        visibles = re.findall(r">([^<>{}]+)<", fuente)
        for texto in visibles:
            assert not re.search(r"\bválid", texto, re.IGNORECASE), (
                f"«{texto.strip()}» rotula algo como válido en {nombre}"
            )


def test_la_UI_muestra_los_pendientes_de_forma_visible():
    vista = _fuente_ui("components/ConnectedResultsView.tsx")
    assert "Pendientes abiertos" in vista
    assert "open_tbd" in vista
    # Y explica que no son verificaciones fallidas.
    assert "no existen" in vista


def test_la_UI_bloquea_la_afirmacion_de_conformidad():
    vista = _fuente_ui("components/ConnectedResultsView.tsx")
    assert "!data.can_claim_compliance" in vista
    assert "no se puede presentar como conforme" in vista


def test_el_formulario_expone_el_tope_y_el_peralte_compartido():
    panel = _fuente_ui("components/ConnectedInputPanel.tsx")
    assert "max_systems" in panel
    assert "same_depth_both_footings" in panel
    # Editables: hay un handler que los escribe, no solo una lectura.
    assert "setSearch({ max_systems:" in panel
    assert "setSearch({ same_depth_both_footings:" in panel
    # Y el valor se muestra, no se oculta.
    assert "{value.search.max_systems}" in panel


def test_el_formulario_no_rellena_las_declaraciones_obligatorias():
    """Las cuatro declaraciones sin respaldo normativo arrancan vacías y bloquean el
    cálculo. Un valor por defecto sería decidir por el proyectista sin decírselo."""
    app_tsx = _fuente_ui("App.tsx")
    assert 'analysis_model: ""' in app_tsx
    assert 'couple_transfer_mode: ""' in app_tsx
    assert 'support_mode: ""' in app_tsx
    assert 'self_weight_mode: ""' in app_tsx

    panel = _fuente_ui("components/ConnectedInputPanel.tsx")
    assert "faltanDeclaraciones" in panel
    # Desde 4G la condición incluye además la combinación incompatible de D1; lo que se
    # exige aquí sigue siendo que las declaraciones que faltan bloqueen el cálculo.
    assert "disabled={running || faltanDeclaraciones" in panel


def test_el_tipo_de_traza_de_la_UI_conserva_open_tbd_y_scope():
    api_ts = _fuente_ui("lib/api.ts")
    bloque = api_ts[api_ts.index("export interface TraceEntry"):]
    bloque = bloque[: bloque.index("}")]
    assert "open_tbd" in bloque
    assert "scope" in bloque
