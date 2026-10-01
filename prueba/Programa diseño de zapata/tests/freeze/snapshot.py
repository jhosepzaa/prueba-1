"""Serialización canónica de un resultado del motor, para congelarlo.

El congelamiento separa deliberadamente **tres contratos distintos**, porque no
tienen la misma rigidez:

  `numeros`     Los valores de ingeniería. Contrato duro: no deben cambiar nunca
                como efecto de una generalización. Si cambian, hay una regresión.

  `estados`     Los PASS / WARNING / FAIL / NOT_VERIFIED de cada verificación y
                de cada entrada de traza. Contrato duro por la misma razón.

  `referencias` Los `code_reference` de cada entrada de traza. Contrato **blando**:
                puede cambiar deliberadamente al corregir una cita, y ese cambio
                debe revisarse uno por uno, no bloquearse.

La prosa (mensajes, ecuaciones sustituidas, notas) queda fuera a propósito:
reescribir un mensaje no es cambiar un resultado, y congelarla produciría
falsos positivos que acabarían por hacer que se ignore el congelamiento entero.

Redondeo: 9 cifras significativas. Suficiente para detectar cualquier cambio con
significado de ingeniería -- se trabaja con 4 o 5 cifras -- y tolerante al ruido
de último bit que puede introducir un reordenamiento de operaciones en coma
flotante que no altera la física.
"""

from __future__ import annotations

import json
import math
from enum import Enum
from typing import Any

from pydantic import BaseModel

SIGNIFICANT_DIGITS = 9

# Campos de prosa: se excluyen del congelamiento numérico (ver docstring).
PROSE_FIELDS = frozenset({
    "message", "equation_substituted", "equation_symbolic", "note", "description",
    "pivot_description", "completeness_note", "source_notes", "hypotheses",
    "rho_min_reference", "model_name", "governing_combo", "name",
    "missing_parameters", "discard_reasons", "code_reference",
})

# Colecciones intermedias que se excluyen por VOLUMEN, no por ser prosa.
#
# Se indexan por (modelo, campo) y NO solo por nombre: `diagram` existe tanto en el
# diagrama de interacción de la viga como en el de cortante y momento de la zapata
# combinada, y el segundo SÍ debe congelarse. Excluir por nombre a secas le habría
# quitado cobertura a la combinada sin que nadie lo notara.
#
# Los ~200 puntos del diagrama de interacción añadirían miles de números que nadie
# revisaría en un diff, y no hacen falta: lo que se LEE del diagrama
# —`capacity_at_Pu`, `demand_ratio`, `inside_diagram`— sí queda congelado, de modo
# que un cambio de resolución o de la frontera se detecta igual, en la magnitud que
# tiene significado de ingeniería.
BULK_FIELDS = frozenset({("AxialFlexureCheck", "diagram")})

# Campos de DIAGNÓSTICO que no forman parte del contrato numérico ni de estados.
#
# `PunchingShearResult.failure_cause` (Fase 5B, D2) clasifica POR QUÉ falla un
# punzonamiento. No altera ningún número ni el estado del chequeo —ambos siguen
# congelados—, y existe en todos los resultados de las cuatro tipologías: recorrerlo
# añadiría una clave nueva a los 48 casos y obligaría a regenerar los dos baselines por un
# cambio que no es de ingeniería. Se excluye aquí, por (modelo, campo), y se protege con
# tests dedicados en `tests/test_punching_failure_cause_phase5b.py`, que recorren además
# todos los casos congelados comprobando que la causa es coherente con su estado.
DIAGNOSTIC_FIELDS = frozenset({
    ("PunchingShearResult", "failure_cause"),
    # FORMULACION_VOLTEO: las DOS lecturas de la envolvente del momento volcador. La que
    # gobierna ya está congelada en `applied_moment_kNm` —que es su máximo— y en
    # `overturning_moment_kNm`; estas dos son el desglose que explica cuál mandó.
    # Recorrerlas añadiría cuatro claves a cada caso de zapata aislada por un campo que no
    # cambia ningún resultado. Se protegen con `tests/test_formulacion_volteo.py`, que
    # recorre todos los casos congelados comprobando
    # `applied_moment_kNm == max(total, estabilizante)` y la coherencia de
    # `envelope_reading`.
    ("OverturningResult", "applied_moment_total_kNm"),
    ("OverturningResult", "applied_moment_dead_kNm"),
    # Fase 9b: posición de la viga sobre el eje (c_e, L1, f_i, c_i, z_b declarada). Es la
    # geometría de la que salen `beam_span_m` —que SÍ se congela, abajo, en
    # `snapshot_connected`— y las métricas, que no se congelan. Recorrerla añadiría cinco
    # claves a cada caso conectado sin información nueva: L1 y f_i ya se congelan a través
    # de las dimensiones de la geometría y de `beam_span_m`. Se protege con
    # `tests/test_beam_span_metrics_phase9b.py`.
    ("ConnectedFootingResult", "beam_axis"),
    # Fase 2: de qué verificación viene cada motivo de descarte de la combinada. Es
    # presentación: los textos (`discard_reasons`) siguen fuera por prosa y su número
    # (`n_descartes`) y los estados de la traza siguen congelados. Se protege con
    # `tests/test_combined_discards_phase2.py`.
    ("CombinedFootingResult", "discard_records"),
})

# Campos de ingeniería que SOLO EXISTEN en algunos casos y valen `None` en el resto.
#
# Fase 9a/9c: el desglose físico del peso de la viga y la reacción de nudo N_a existen
# únicamente con peso propio EXPLICITO (y N_a, además, con PAR_PURO_EN_ZAPATA). Cuando
# existen SÍ son contrato duro y se congelan enteros. Cuando valen `None` se omiten, por
# la misma razón que el marcador `open_tbd` de la traza se emite condicionalmente: si se
# recorrieran siempre, cada caso conectado ganaría claves `None` y el baseline entero
# cambiaría por un campo que en ellos no significa nada.
OPTIONAL_WHEN_NONE_FIELDS = frozenset({
    ("CoupleDistribution", "beam_self_weight_breakdown"),
    ("CoupleDistribution", "beam_node_reaction_kN"),
    # Fase 10B: factor del peso de la viga, solo en el modo de cargas por casos.
    ("BeamSelfWeightBreakdown", "load_factor"),
    # Fase 10C: composición de las cargas corregidas de la conectada, solo en modo por casos.
    ("CoupleDistribution", "exterior_corrected_composition"),
    ("CoupleDistribution", "interior_corrected_composition"),
    # Pendiente 7: estabilidad de la combinada, solo cuando hay fuerza horizontal. Los casos
    # congelados K1-K4 no la declaran, de modo que el campo es None y no añade ninguna clave.
    # Se protege con `tests/test_combined_stability_pendiente7.py`.
    ("CombinedFootingResult", "stability"),
    # E.050 art. 28: dimensiones del área efectiva y la declaración del proyectista sobre el
    # qadm. Solo las llena `EffectiveAreaModel`, que es una elección del proyectista; con el
    # modelo por defecto valen None. Cuando existen SÍ son contrato duro y se congelan
    # enteras. Se protegen con `tests/test_area_efectiva_e050_art28.py`.
    ("ContactPressureResult", "B_eff_m"),
    ("ContactPressureResult", "L_eff_m"),
    ("ContactPressureResult", "qadm_declared_for_effective_area"),
    # E.060 §15.6.2 (2026-09-28): tramo de desarrollo a través de la columna. Solo existe
    # cuando GOBIERNA la longitud disponible, es decir con la columna descentrada; con la
    # columna concéntrica vale None y no añade ninguna clave. Cuando existe SÍ es contrato
    # duro. Se protege con `tests/test_desarrollo_columna_descentrada.py`.
    ("BarLayerGeometry", "through_column_length_m"),
})


def round_sig(x: float, digits: int = SIGNIFICANT_DIGITS) -> float | str:
    """Redondea a `digits` cifras significativas. Los no finitos se serializan
    como texto porque JSON no admite Infinity ni NaN de forma portable."""
    if isinstance(x, bool):
        return x
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0.0:
        return 0.0
    return round(x, -int(math.floor(math.log10(abs(x)))) + (digits - 1))


def _walk(value: Any, path: str, numeros: dict, estados: dict) -> None:
    """Recorre el modelo acumulando valores en `numeros` y `estados` por ruta.

    La traza se excluye aquí y se serializa aparte, indexada por `id` y no por
    posición: insertar una verificación nueva desplazaría todos los índices
    posteriores y produciría un falso positivo en cada entrada siguiente. Un
    congelamiento que grita por un cambio que no ocurrió acaba por ignorarse.
    """
    if isinstance(value, BaseModel):
        modelo = type(value).__name__
        for key, sub in value.__dict__.items():
            if key in PROSE_FIELDS or key == "trace":
                continue
            if (modelo, key) in BULK_FIELDS or (modelo, key) in DIAGNOSTIC_FIELDS:
                continue
            if sub is None and (modelo, key) in OPTIONAL_WHEN_NONE_FIELDS:
                continue
            _walk(sub, f"{path}.{key}" if path else key, numeros, estados)
    elif isinstance(value, dict):
        for key in sorted(value, key=str):
            _walk(value[key], f"{path}[{key}]", numeros, estados)
    elif isinstance(value, (list, tuple)):
        for i, sub in enumerate(value):
            _walk(sub, f"{path}[{i}]", numeros, estados)
    elif isinstance(value, Enum):
        estados[path] = value.value
    elif isinstance(value, bool):
        numeros[path] = value
    elif isinstance(value, (int, float)):
        numeros[path] = round_sig(float(value))
    elif value is None:
        numeros[path] = None
    # Cualquier otro str queda fuera: es prosa que no llegó a PROSE_FIELDS.


def trace_key(entry: Any) -> str:
    """Clave de una entrada de traza dentro de la instantánea.

    LA UNICIDAD REAL ES DEL PAR (scope, id), NO DEL id. Mientras las tres primeras
    tipologías tuvieron un solo componente, todas sus entradas llevaron `scope=None` y
    el id bastó. La zapata conectada tiene cuatro ámbitos —sistema, zap_ext, zap_int,
    viga— y 19 de sus 59 entradas comparten id con otra: `punching` existe en las DOS
    zapatas. Indexar por id a secas habría guardado solo la última de cada par y el
    congelamiento habría cubierto la mitad de la traza sin que nada lo delatara.

    Con `scope=None` devuelve el id tal cual, de modo que las instantáneas de la
    aislada, la combinada y la viga NO cambian ni un byte."""
    scope = getattr(entry, "scope", None)
    return entry.id if scope is None else f"{scope}/{entry.id}"


def snapshot_candidate(candidate: Any, trace: Any = None) -> dict[str, Any]:
    """Instantánea canónica de un resultado del motor.

    `trace` se admite por separado para los motores que la producen aparte del
    resultado —la viga de conexión— en vez de llevarla dentro. Si se omite, se busca
    como atributo, que es el caso de la zapata aislada y de la combinada."""
    numeros: dict[str, Any] = {}
    estados: dict[str, Any] = {}
    _walk(candidate, "", numeros, estados)

    if trace is None:
        trace = getattr(candidate, "trace", None)
    referencias: dict[str, str] = {}
    if trace is not None:
        for entry in trace.entries:
            # Indexado por (ámbito, id), nunca por posición: ver docstring de `_walk`.
            clave = trace_key(entry)
            referencias[clave] = entry.code_reference
            numeros[f"traza[{clave}].result_value"] = round_sig(float(entry.result_value))
            numeros[f"traza[{clave}].result_unit_len"] = len(entry.result_unit)
            estados[f"traza[{clave}].status"] = entry.status.value
            # CONTRATO DURO, y SOLO cuando existe. Que una entrada deje de estar marcada
            # como pendiente abierto es un cambio de significado tan fuerte como un
            # cambio de estado: pasaría de «no hay criterio que aplicar» a «se comprobó».
            #
            # Se emite condicionalmente y no siempre para que las instantáneas donde
            # ningún pendiente existe —las tres tipologías anteriores— queden intactas.
            # La PRESENCIA de la clave es en sí misma la aserción: si el marcador
            # desaparece, `diff_snapshots` lo reporta como campo desaparecido.
            if getattr(entry, "open_tbd", None):
                estados[f"traza[{clave}].open_tbd"] = entry.open_tbd
        # El ORDEN de la traza sí es contrato: es el orden en que se lee el informe.
        numeros["traza.orden"] = "|".join(trace_key(e) for e in trace.entries)

    descartes = sorted(trace_key(e) for e in trace.failing_entries()) if trace is not None else []

    return {
        "numeros": dict(sorted(numeros.items())),
        "estados": dict(sorted(estados.items())),
        "referencias": dict(sorted(referencias.items())),
        "trazas_en_fallo": descartes,
        "n_descartes": len(getattr(candidate, "discard_reasons", []) or []),
    }



# =========================================================================
# Cimentación conectada — Fase 4F
# =========================================================================
#
# UN CUARTO CONTRATO, Y POR QUÉ HACE FALTA
# ========================================
# Las tres tipologías anteriores viven con tres contratos: `numeros` y `estados`
# duros, `referencias` blando. La conectada necesita uno más, `estados_blandos`, por
# una razón concreta y no por comodidad.
#
# Mientras TBD-C1 siga abierto, TODAS las alternativas de esta tipología salen
# NO VERIFICADO. El día que ese pendiente se cierre —si se cierra—, el
# `overall_status` de todos los casos conectados cambiará a la vez. Con contrato duro
# eso obligaría a regenerar el baseline entero en bloque, que es exactamente la
# situación en la que una regeneración deja de revisarse: mucho ruido, ninguna señal.
#
# La distinción se traza así:
#
#   `implemented_checks_status`  DURO. Responde «de lo que el motor sabe comprobar,
#                                ¿algo sale mal?». No depende de ningún pendiente, y
#                                si se mueve es una regresión de ingeniería.
#
#   `overall_status`             BLANDO. Responde «¿puede el motor pronunciarse?».
#                                Depende de los pendientes abiertos, que son estado
#                                del conocimiento normativo y no del código.
#
# Lo que NO se ablanda es el marcador `open_tbd` de cada entrada ni el estado de la
# entrada de la premisa: el día que TBD-C1 se cierre, esos SÍ deben romper el
# congelamiento y forzar una revisión deliberada. La diferencia es que romperán en las
# dos o tres claves donde el cambio tiene significado, no en las catorce donde solo es
# contaminación aguas abajo.

SOFT_STATE_PATHS = frozenset({"overall_status"})
"""Claves de `estados` que pasan a contrato BLANDO en la conectada.

Solo el estado del SISTEMA. `exterior.overall_status` e `interior.overall_status` se
quedan duros a propósito: dependen de las verificaciones de cada zapata, no de TBD-C1,
que es una entrada de ámbito `sistema`."""


def snapshot_connected(result: Any) -> dict[str, Any]:
    """Instantánea de una terna resuelta de cimentación conectada.

    Reutiliza `snapshot_candidate` entera —misma aritmética de redondeo, mismos campos
    de prosa excluidos, mismas claves de traza— y después separa los dos contratos de
    estado. Reimplementarla habría sido la vía directa a que las cuatro tipologías
    acabaran congelándose con criterios distintos."""
    snap = snapshot_candidate(result)

    estados = snap["estados"]
    blandos = {k: estados.pop(k) for k in sorted(SOFT_STATE_PATHS) if k in estados}

    # CONTRATO DURO. Es una `@property` del motor, así que `_walk` no la ve: hay que
    # añadirla a mano. Sin ella, el congelamiento de la conectada no cubriría la única
    # pregunta que no depende de un pendiente abierto.
    estados["implemented_checks_status"] = result.implemented_checks_status.value

    # Las dos magnitudes derivadas que el resultado publica, por la misma razón: son
    # propiedades y `_walk` no las recorre.
    #
    # No son adorno. `system_length_m` alimenta `max_plan_dimension_m`, una de las
    # métricas con las que se ORDENAN las alternativas, y tomar siempre la dimensión en
    # X —ignorando el eje longitudinal declarado— fue un defecto real de 4D. Sin
    # congelarlas, invertir ese eje vuelve a pasar inadvertido: comprobado por mutación.
    numeros = snap["numeros"]
    numeros["system_length_m"] = round_sig(float(result.system_length_m))
    numeros["beam_span_m"] = round_sig(float(result.beam_span_m))
    snap["numeros"] = dict(sorted(numeros.items()))

    # También duro: qué pendientes bloquean la terna, y en qué orden los declara el
    # motor. `open_tbds` es propiedad, igual que la anterior.
    estados["open_tbds"] = "|".join(result.open_tbds)

    snap["estados"] = dict(sorted(estados.items()))
    snap["estados_blandos"] = blandos
    return snap


def snapshot_connected_rejection(reason: str, detail: str) -> dict[str, Any]:
    """Instantánea de una terna que el motor SE NIEGA a resolver.

    Un despegue o una geometría imposible no producen resultado: producen una negativa.
    Congelar la negativa es congelar una decisión de ingeniería —esta geometría no se
    resuelve, y por este motivo— tan digna de contrato como un número.

    Del detalle se guarda solo el MOTIVO, no el mensaje: el texto es prosa y reescribirlo
    no cambia la decisión. Lo que no puede cambiar en silencio es que la terna deje de
    rechazarse, o que pase a rechazarse por otra causa."""
    return {
        "numeros": {},
        "estados": {"rechazo.motivo": reason},
        "referencias": {},
        "trazas_en_fallo": [],
        "estados_blandos": {},
        "rechazo": {"motivo": reason, "detalle_len": len(detail)},
    }


def snapshot_connected_sweep(alternatives: Any) -> dict[str, Any]:
    """Instantánea de un MICRO-BARRIDO. Contrato deliberadamente estrecho.

    Se congelan tres cosas y solo tres: cuántas ternas se evaluaron, cuántas se
    aceptaron y por qué se rechazaron las demás. Esos tres números describen el ESPACIO
    DE BÚSQUEDA y la física que lo filtra, que es lo que no debe moverse.

    NO se congela el orden, ni el ranking, ni los identificadores de las alternativas.
    Ese es el terreno de la estrategia de búsqueda, que puede mejorarse legítimamente
    —afinar el orden de las parejas de peralte, cambiar los pesos de la puntuación— sin
    que la ingeniería cambie. Atarlo aquí haría que cada mejora rompiera todos los casos
    de barrido, y a la tercera vez nadie leería el diff."""
    return {
        "numeros": {},
        "estados": {},
        "referencias": {},
        "trazas_en_fallo": [],
        "estados_blandos": {},
        "barrido": {
            "evaluated_count": alternatives.evaluated_count,
            "accepted_count": len(alternatives.accepted),
            "rejections_by_reason": dict(sorted(alternatives.rejections_by_reason().items())),
        },
    }

def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def diff_snapshots(esperado: dict, obtenido: dict, seccion: str) -> list[str]:
    """Diferencias legibles entre dos secciones de instantánea."""
    e, o = esperado.get(seccion, {}), obtenido.get(seccion, {})
    if isinstance(e, list) or isinstance(o, list):
        return [] if e == o else [f"{seccion}: {e!r} -> {o!r}"]
    lineas = []
    for clave in sorted(set(e) | set(o)):
        if clave not in e:
            lineas.append(f"  + {clave} = {o[clave]!r}  (campo nuevo)")
        elif clave not in o:
            lineas.append(f"  - {clave} = {e[clave]!r}  (campo desaparecido)")
        elif e[clave] != o[clave]:
            lineas.append(f"  ~ {clave}: {e[clave]!r} -> {o[clave]!r}")
    return lineas
