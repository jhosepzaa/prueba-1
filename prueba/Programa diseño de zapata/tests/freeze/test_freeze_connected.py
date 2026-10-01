"""CONGELAMIENTO NUMÉRICO DE LA CIMENTACIÓN CONECTADA — Fase 4F.

Requisito que protege este archivo:

    LOS RESULTADOS DE LA CIMENTACIÓN CONECTADA NO DEBEN MOVERSE COMO EFECTO
    COLATERAL DE NINGÚN CAMBIO POSTERIOR.

Era la única tipología del programa sin contrato de no regresión, y la más frágil:
tres solvers acoplados —dos zapatas y una viga—, dos modelos de análisis, dos modos de
reparto del par, y una convención de momentos (E.050 art. 28.1) cuyo signo ya produjo
un defecto real que solo se detectó por auditoría manual.

BASELINE PROPIA, Y POR QUÉ
==========================
Este archivo escribe en `baseline_connected.json`, no en `baseline.json`. Los 30 casos
de las tres tipologías anteriores quedan literalmente intactos —otro archivo, otro
driver—, que es la garantía más fuerte de que 4F no puede tocarlos. Además los
contratos no son los mismos: aquí hay uno blando que allí no existe.

CUATRO CONTRATOS
================
  `numeros`          DURO. Valores de ingeniería.
  `estados`          DURO. Incluye `implemented_checks_status` y los marcadores
                     `open_tbd` de cada entrada de traza.
  `estados_blandos`  BLANDO. Solo `overall_status` del sistema. Depende de qué
                     pendientes sigan abiertos, que es estado del conocimiento
                     normativo y no del código: el día que TBD-C1 se cierre, este
                     contrato debe poder actualizarse sin arrastrar a los otros tres.
  `referencias`      BLANDO. Citas normativas, como en las otras tipologías.

Y dos secciones específicas: `rechazo` para las ternas que el motor se niega a
resolver, y `barrido` para los micro-barridos.

REGENERAR LA LÍNEA BASE
-----------------------
Solo cuando un cambio de resultado sea DELIBERADO y esté justificado:

    FREEZE_REGEN=1 py -m pytest tests/freeze -q

Regenerar sin revisar el diff anula el propósito del archivo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.connected_solver import solve_connected_footing
from engine.optimization.connected_generator import (
    _classify,
    generate_connected_alternatives,
)
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import (
    CONNECTED_CASES,
    CONNECTED_SWEEP_CASES,
    ConnectedFreezeCase,
    ConnectedSweepCase,
)
from tests.freeze.snapshot import (
    diff_snapshots,
    dumps,
    snapshot_connected,
    snapshot_connected_rejection,
    snapshot_connected_sweep,
)

BASELINE = Path(__file__).parent / "baseline_connected.json"
REGEN = os.environ.get("FREEZE_REGEN") == "1"

CODE = E060ConcreteCode()
CONTACT_MODEL = KernCheckModel()


def _solve(case: ConnectedFreezeCase):
    # `build_layout()` y no `case.layout`: un layout que el motor rechaza por validación
    # tiene que fallar AQUÍ, dentro del `try` de `_snapshot_case`, para que su negativa se
    # congele igual que un despegue o una geometría imposible.
    return solve_connected_footing(
        case.build_layout(), case.geometry,
        soil=case.soil, concrete=case.concrete, steel=case.steel,
        code=CODE, contact_model=CONTACT_MODEL, depth_params=case.depth_params,
    )


def _snapshot_case(case: ConnectedFreezeCase) -> dict:
    """Resuelve la terna, o congela la negativa si el motor se niega.

    La negativa se traduce con `_classify`, el MISMO clasificador que usa el generador
    de 4D. Escribir aquí una segunda lectura del mensaje habría permitido que el
    congelamiento y la búsqueda acabaran discrepando sobre por qué se rechaza una
    geometría."""
    try:
        resultado = _solve(case)
    except ValueError as exc:
        motivo, detalle = _classify(exc)
        return snapshot_connected_rejection(motivo.value, detalle)
    return snapshot_connected(resultado)


def _snapshot_sweep(case: ConnectedSweepCase) -> dict:
    alternativas = generate_connected_alternatives(
        case.layout, case.params,
        soil=case.soil, concrete=case.concrete, steel=case.steel,
        code=CODE, contact_model=CONTACT_MODEL, depth_params=case.depth_params,
    )
    return snapshot_connected_sweep(alternativas)


def _build_all() -> dict[str, dict]:
    actual: dict[str, dict] = {}
    for case in CONNECTED_CASES:
        actual[case.name] = _snapshot_case(case)
    for sweep in CONNECTED_SWEEP_CASES:
        actual[sweep.name] = _snapshot_sweep(sweep)
    return actual


@pytest.fixture(scope="module")
def actual() -> dict[str, dict]:
    return _build_all()


@pytest.fixture(scope="module")
def esperado() -> dict[str, dict]:
    if not BASELINE.exists():
        pytest.skip(
            "No existe baseline_connected.json; ejecutar con FREEZE_REGEN=1 para crearla."
        )
    return json.loads(BASELINE.read_text(encoding="utf-8"))


_TERNAS = [c.name for c in CONNECTED_CASES]
_BARRIDOS = [c.name for c in CONNECTED_SWEEP_CASES]
_TODOS = _TERNAS + _BARRIDOS


def _mecanismo(nombre: str) -> str:
    for case in list(CONNECTED_CASES) + list(CONNECTED_SWEEP_CASES):
        if case.name == nombre:
            return case.mechanism
    return "(desconocido)"


def test_regenerar_linea_base(actual):
    """No es una verificación: es el mecanismo de regeneración, activado por variable
    de entorno. Con FREEZE_REGEN sin definir, no hace nada."""
    if not REGEN:
        pytest.skip("Regeneración desactivada (definir FREEZE_REGEN=1 para regenerar).")
    BASELINE.write_text(dumps(actual), encoding="utf-8")


def test_la_linea_base_cubre_todos_los_casos(actual, esperado):
    faltan = sorted(set(actual) - set(esperado))
    sobran = sorted(set(esperado) - set(actual))
    assert not faltan, f"Casos sin línea base: {faltan}. Regenerar con FREEZE_REGEN=1."
    assert not sobran, f"Línea base con casos que ya no existen: {sobran}."


# =========================================================================
# Contratos duros
# =========================================================================


@pytest.mark.parametrize("nombre", _TODOS)
def test_numeros_congelados(nombre, actual, esperado):
    """CONTRATO DURO. Un fallo aquí es una regresión hasta que se demuestre lo
    contrario: algún valor de ingeniería del sistema conectado se movió."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "numeros")
    assert not lineas, (
        f"El resultado numérico de '{nombre}' cambió.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n" + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _TODOS)
def test_estados_congelados(nombre, actual, esperado):
    """CONTRATO DURO. Cubre `implemented_checks_status` —la única pregunta que no
    depende de ningún pendiente— y el estado de cada entrada de traza. Protege además
    la regla de que un WARNING no ascienda a PASS por haberse implementado otra cosa."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "estados")
    assert not lineas, (
        f"Un estado de verificación de '{nombre}' cambió.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n" + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _TERNAS)
def test_trazas_en_fallo_congeladas(nombre, actual, esperado):
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "trazas_en_fallo")
    assert not lineas, (
        f"Cambió el conjunto de verificaciones en fallo de '{nombre}':\n" + "\n".join(lineas)
    )


@pytest.mark.parametrize(
    "nombre", [c.name for c in CONNECTED_CASES if c.expects_rejection]
)
def test_las_negativas_del_motor_se_congelan(nombre, actual, esperado):
    """CONTRATO DURO. Que una terna deje de rechazarse —o pase a rechazarse por otra
    causa— es un cambio de criterio de ingeniería, no una mejora silenciosa."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "rechazo")
    assert not lineas, (
        f"Cambió la negativa del motor en '{nombre}'.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n" + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _BARRIDOS)
def test_el_espacio_de_busqueda_congelado(nombre, actual, esperado):
    """CONTRATO DURO Y ESTRECHO. Tres números: ternas evaluadas, ternas aceptadas y
    motivos de rechazo. NO se congela el orden ni el ranking — ese es el terreno de la
    estrategia de búsqueda, que puede mejorarse sin que la ingeniería cambie."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "barrido")
    assert not lineas, (
        f"Cambió el espacio de búsqueda de '{nombre}'.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n" + "\n".join(lineas)
    )


# =========================================================================
# Contratos blandos
# =========================================================================


@pytest.mark.parametrize("nombre", _TODOS)
def test_estado_global_congelado_contrato_blando(nombre, actual, esperado):
    """CONTRATO BLANDO. `overall_status` depende de qué pendientes sigan abiertos.

    Hoy todas las ternas salen NO VERIFICADO por TBD-C1. Si ese pendiente llega a
    cerrarse, TODAS cambiarán a la vez y habrá que regenerar — pero solo esta sección,
    no los números ni los estados de las verificaciones implementadas. Esa es la razón
    de que viva aparte: un cambio de estado del conocimiento normativo no debe obligar
    a regenerar en bloque un baseline que nadie revisaría entero."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "estados_blandos")
    assert not lineas, (
        f"Cambió el estado global de '{nombre}'. Si se debe al cierre de un pendiente "
        f"abierto, revísalo y regenera con FREEZE_REGEN=1:\n" + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _TERNAS)
def test_referencias_normativas_congeladas(nombre, actual, esperado):
    """CONTRATO BLANDO. Corregir una cita puede ser legítimo; por eso el mensaje pide
    revisarla en vez de darla por errónea."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "referencias")
    assert not lineas, (
        f"Cambió una referencia normativa en '{nombre}'. Si la corrección es "
        f"deliberada, revísala una por una y regenera con FREEZE_REGEN=1:\n"
        + "\n".join(lineas)
    )


# =========================================================================
# Salud del propio congelamiento
# =========================================================================


def test_la_traza_no_pierde_entradas_por_colision_de_id(actual):
    """El defecto que 4F tuvo que corregir en `snapshot.py` antes de poder congelar.

    La zapata conectada tiene cuatro ámbitos y 19 de sus entradas comparten id con otra
    —`punching` existe en las DOS zapatas—. Indexar la traza por id a secas guardaba
    solo la última de cada par: el congelamiento habría cubierto dos tercios de la traza
    creyendo cubrirla entera. Este test fija que la clave siga siendo (ámbito, id)."""
    snap = actual["Z1_articulado_equilibrio"]
    claves = [k for k in snap["referencias"]]

    assert len(claves) >= 55, (
        f"Solo {len(claves)} entradas de traza congeladas: el resultado tiene más. "
        f"Probable colisión de identificadores entre ámbitos."
    )
    for ambito in ("sistema/", "zap_ext/", "zap_int/", "viga/"):
        assert any(k.startswith(ambito) for k in claves), f"Falta el ámbito {ambito}"
    # Y el caso concreto: `punching` aparece en las dos zapatas, por separado.
    assert "zap_ext/punching" in claves
    assert "zap_int/punching" in claves


def test_el_pendiente_abierto_es_contrato_duro(actual):
    """D3. El marcador `open_tbd` va en `estados`, no en la sección blanda: que una
    entrada deje de estar marcada como pendiente significa que pasó a comprobarse, y
    eso tiene que romper el congelamiento."""
    estados = actual["Z1_articulado_equilibrio"]["estados"]
    marcadores = {k: v for k, v in estados.items() if k.endswith(".open_tbd")}

    assert marcadores, "Ningún marcador `open_tbd` llegó a la instantánea"
    assert "TBD-C1" in marcadores.values()
    assert estados["open_tbds"] == "TBD-C1"


def test_el_estado_de_las_verificaciones_implementadas_es_contrato_duro(actual):
    """D2. La pregunta que NO depende de ningún pendiente vive en el contrato duro.

    `implemented_checks_status` es el peor estado de las entradas de traza SIN `open_tbd`:
    no lo mueve ningún TBD.

    HISTORIA. Hasta la Fase 10B valía PASS en Z1 y Z3. Desde 10B el volteo de las zapatas se
    evaluaba con cargas corregidas sin composición y su cumplimiento quedaba NO VERIFICADO
    (E.020 art. 20.1; D10-3 y D10-7), que era la única entrada sin pendiente peor que
    PASS/INFO. Desde FORMULACION_VOLTEO (2026-09-19) vuelve a valer PASS, y el motivo es
    físico, no una relajación del criterio: la carga corregida de la zapata de lindero trae
    M = −P·offset, de modo que el momento neto respecto del centroide es nulo o residual y
    el volcamiento no tiene demanda que verificar. El caveat de la carga muerta solo aparece
    cuando hay un FS que afirmar, y aquí no lo hay.

    Lo que el test exige es que NO haya ninguna otra causa: toda entrada sin pendiente es
    PASS o INFO, y el resumen coincide con ese peor estado."""
    peor = {CheckStatus.PASS.value: 0, CheckStatus.INFO.value: 0, CheckStatus.WARNING.value: 1,
            CheckStatus.NOT_VERIFIED.value: 2, CheckStatus.FAIL.value: 3}
    for nombre in ("Z1_articulado_equilibrio", "Z3_cuerpo_rigido_equilibrio"):
        estados = actual[nombre]["estados"]
        assert "overall_status" not in estados, (
            "`overall_status` debe estar en `estados_blandos`, no en el contrato duro."
        )
        assert actual[nombre]["estados_blandos"]["overall_status"] == (
            CheckStatus.NOT_VERIFIED.value
        )

        sin_pendiente = {
            k: v for k, v in estados.items()
            if k.startswith("traza[") and k.endswith("].status")
            and k.replace("].status", "].open_tbd") not in estados
        }
        # Se comparan SEVERIDADES, no etiquetas: PASS e INFO empatan en severidad y
        # comparar el texto convertía un empate en un falso positivo.
        assert peor[estados["implemented_checks_status"]] == max(
            peor[v] for v in sin_pendiente.values()
        )
        # Si alguna entrada implementada es peor que PASS/INFO, solo puede ser un
        # volcamiento NO VERIFICADO por composición desconocida (E.020 art. 20.1).
        # En Z1 (ARTICULADO) ya no hay ninguna —la carga corregida queda centrada—; en
        # Z3 (CUERPO_RIGIDO) queda la excentricidad residual del reparto, y esa sí.
        no_pass = {k for k, v in sin_pendiente.items() if peor[v] > 0}  # PASS e INFO no cuentan
        assert all("/overturning_" in k for k in no_pass), no_pass
        assert all(
            v == CheckStatus.NOT_VERIFIED.value
            for k, v in sin_pendiente.items() if k in no_pass
        )
        assert bool(no_pass) == (nombre == "Z3_cuerpo_rigido_equilibrio"), (nombre, no_pass)


def test_el_dato_que_falta_no_se_marca_como_pendiente_del_motor(actual):
    """Dos casos que solo difieren en si el FS de volcamiento está declarado.

    Historia: en 4D, sin declararlo, la verificación quedaba NO VERIFICADO sin `open_tbd`
    (faltaba un dato del proyectista, no un criterio del motor). En 10B el FS no declarado
    pasó a tomar el criterio del programa. Desde FORMULACION_VOLTEO (2026-09-19) el
    volcamiento de la zapata de lindero no tiene demanda —su carga corregida trae
    M = −P·offset—, de modo que la verificación se declara NO APLICABLE en los dos casos y
    el FS requerido ya no lo fija ninguna combinación gobernante.

    Lo que se fija ahora:

    1. la verificación es inerte en los dos casos, por la misma razón física;
    2. lo ÚNICO que los distingue en ese bloque es el dato declarado: `FS_required` vale
       1,50 en Z1, que lo declara, y None en Z1b, que no. El dato viaja y no se inventa;
    3. la falta del dato sigue sin marcarse como pendiente del motor: ninguna entrada de
       estabilidad lleva `open_tbd`, y TBD-C1 es el mismo en los dos casos.

    El valor y la procedencia del FS cuando SÍ hay demanda no se fijan aquí, sino en
    `tests/test_normative_corrections_phase1a.py` y `tests/test_stability.py`, que es su
    sitio: son una regla del motor, no una foto de un caso."""
    z1, z1b = actual["Z1_articulado_equilibrio"], actual["Z1b_articulado_sin_FS_de_volcamiento"]

    # 1. Inerte en los dos, por ausencia de demanda.
    for caso in (z1, z1b):
        assert caso["numeros"]["exterior.stability.applicable"] is False
        assert caso["numeros"]["exterior.stability.overturning_x.FS_obtained"] is None
        assert caso["numeros"]["exterior.stability.overturning_x.overturning_moment_kNm"] == 0.0
        assert caso["estados"]["exterior.stability.overturning_x.status"] == CheckStatus.PASS.value

    # 2. El dato declarado es lo único que los distingue.
    claves_fs = {
        "exterior.stability.overturning_x.FS_required",
        "exterior.stability.overturning_y.FS_required",
    }
    for clave in claves_fs:
        assert z1["numeros"][clave] == 1.50
        assert z1b["numeros"][clave] is None
    distintos = {
        k for k in z1["numeros"]
        if k.startswith("exterior.stability.") and z1["numeros"][k] != z1b["numeros"].get(k)
    }
    assert distintos == claves_fs, distintos

    # 3. Ni el dato ausente ni su valor por defecto son un pendiente del motor.
    for caso in (z1, z1b):
        estados = caso["estados"]
        for k in estados:
            if k.startswith("traza[") and ("overturning" in k or "sliding" in k):
                assert not k.endswith("].open_tbd"), f"{k}: la estabilidad no es un TBD"
    assert z1["estados"]["open_tbds"] == z1b["estados"]["open_tbds"] == "TBD-C1"


def test_los_benchmarks_quedan_marcados():
    """D5. Los casos que reproducen los apuntes se identifican como tales, para que un
    fallo doble —benchmark y congelamiento— se lea como un solo problema."""
    marcados = [c for c in CONNECTED_CASES if c.benchmark]
    assert len(marcados) == 2
    for c in marcados:
        assert "CR2-93-134" in c.benchmark
        assert "asserts en" in c.benchmark, (
            "El marcador debe decir DÓNDE se afirman los valores del libro, para no "
            "duplicar esos asserts aquí."
        )


def test_cuerpo_rigido_con_par_puro_se_rechaza_por_validacion(actual):
    """Fase 5A, D1 — sustituye al test que en 4F fijaba la discrepancia.

    En 4F `Z4` se aceptaba y combinaba el campo de presión rígido de las zapatas con una
    viga de par puro articulado: dos equilibrios incompatibles en un mismo resultado. La
    decisión (a1) es rechazar la combinación, porque las dos hipótesis se excluyen.

    Se congela que se rechace, que se rechace como ENTRADA_INVALIDA —es un error de
    declaración, no una geometría imposible ni un despegue— y que no quede ningún número
    de ingeniería congelado para esa combinación."""
    z4 = actual["Z4_cuerpo_rigido_par_puro"]
    assert z4["rechazo"]["motivo"] == "ENTRADA_INVALIDA"
    assert z4["numeros"] == {}
    assert z4["estados"] == {"rechazo.motivo": "ENTRADA_INVALIDA"}

    # Y la combinación compatible del mismo modelo sigue resolviéndose.
    assert "rechazo" not in actual["Z3_cuerpo_rigido_equilibrio"]
