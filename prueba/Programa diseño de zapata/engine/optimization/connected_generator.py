"""Búsqueda y optimización de la zapata conectada — Fase 4D.

NADA DE ESTE MÓDULO ES NORMATIVO. Es estrategia de búsqueda, y no calcula ni una sola
ecuación de ingeniería: cada candidato se resuelve llamando a `solve_connected_footing`,
que a su vez llama a los motores de zapata y de viga. Aquí solo se decide QUÉ geometrías
se prueban y CÓMO se ordenan las que sobreviven.

LA UNIDAD DE COMPARACIÓN ES LA TERNA, NO CADA ZAPATA
====================================================
En una zapata conectada no se puede optimizar cada zapata por separado y unir los
ganadores. Reducir la zapata de lindero aumenta su excentricidad, lo que aumenta la
transferencia, lo que cambia la carga de la interior. La alternativa es el conjunto
{zapata exterior, viga, zapata interior} y su espacio de búsqueda es el producto
cartesiano de las dos geometrías.

Ese producto crece rápido, y por eso el barrido lleva un tope explícito y declara cuándo
lo alcanza. Un resultado truncado NO es una búsqueda exhaustiva y el usuario tiene que
saberlo.

CÓMO SE ELIGE EL PERALTE
========================
Para cada pareja de plantas se prueban las parejas de peralte ORDENADAS POR VOLUMEN DE
CONCRETO CRECIENTE, y se toma la primera que no falla. Así la pareja elegida es la más
barata de las que cumplen para esa planta, y no la primera que aparezca en un bucle
anidado —que dependería del orden de iteración y no de ningún criterio—.

TRES CONCEPTOS DISTINTOS, TRES NOMBRES DISTINTOS
================================================
Este módulo no usa la palabra «válida» para nada, y es deliberado. Hay tres situaciones
que se parecen lo justo para confundirse, y confundirlas es el error que el encargo
prohíbe expresamente:

1. **RECHAZADA** — `ConnectedAlternativeSet.rejected`. El sistema no se pudo plantear
   (geometría imposible, despegue, entrada inválida) o alguna verificación salió FAIL.
   No es candidata a nada.

2. **ACEPTADA** — `ConnectedAlternativeSet.accepted`. Sobrevivió el barrido: ninguna de
   las verificaciones IMPLEMENTADAS la descarta. Eso es todo lo que significa. NO
   significa que cumpla.

3. **NO VERIFICADA** — `ConnectedAlternativeSet.not_verified`, un subconjunto de las
   aceptadas. El motor no puede pronunciarse porque hay un pendiente abierto: TBD-C1 —la
   premisa de rigidez— no tiene criterio normativo que aplicar. Hoy **todas** las
   aceptadas están aquí, y seguirán estándolo mientras TBD-C1 no se cierre.

El criterio de aceptación es por tanto «no FAIL» y no «PASS»: la zapata conectada no
puede alcanzar PASS mientras TBD-C1 siga abierto, de modo que exigirlo rechazaría todas
las alternativas sin excepción. Pero aceptar no es aprobar. `accepted_and_compliant`
existe para dejarlo explícito: hoy devuelve la lista vacía, y eso es información, no un
fallo.
"""

from __future__ import annotations

import atexit
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from enum import Enum
from itertools import islice
from typing import Iterator

from pydantic import BaseModel, Field, model_validator

from engine.codes.base import IConcreteCode
from engine.domain.connected_layout import ConnectedFootingLayout
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.site_limits import SiteLimits
from engine.domain.soil import SoilProfile
from engine.foundation.connected_solver import (
    ConnectedFootingGeometry,
    ConnectedFootingResult,
    solve_connected_footing,
)
from engine.optimization.connected_metrics import compute_connected_metrics
from engine.optimization.metrics import AlternativeMetrics
from engine.optimization.scoring import ScoreWeights
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import ContactPressureModel

# Tope de ternas por barrido POR DEFECTO. No es un límite del producto: es el valor
# inicial de `ConnectedSearchParameters.max_systems`, que el usuario sube o baja.
#
# Más bajo que el de la combinada porque cada terna cuesta tres solvers en vez de uno.
# Sea cual sea el valor, alcanzarlo marca `truncated=True` y emite la advertencia: un
# barrido truncado en silencio es un óptimo que no lo es.
DEFAULT_MAX_CONNECTED_SYSTEMS = 1500

# Alias histórico. Se conserva para no romper a quien lo importe, pero el valor que
# manda es `params.max_systems`.
MAX_CONNECTED_SYSTEMS = DEFAULT_MAX_CONNECTED_SYSTEMS


class RejectionReason(str, Enum):
    """Por qué se rechazó un candidato. No son estados de la máquina de verificación:
    son motivos de BÚSQUEDA, y por eso viven aquí y no en `results/status.py`."""

    GEOMETRIA_IMPOSIBLE = "GEOMETRIA_IMPOSIBLE"
    """La columna no cabe en la zapata manteniendo su holgura al lindero. No es un
    descarte de diseño: es una geometría sin sentido físico."""

    DESPEGUE = "DESPEGUE"
    """El modelo de cuerpo rígido da presión negativa en parte del apoyo. El campo
    lineal deja de describir el problema y el motor no resuelve contacto unilateral
    (TBD-C12). El candidato se RECHAZA; la búsqueda continúa."""

    CARGA_NETA_ASCENDENTE = "CARGA_NETA_ASCENDENTE"
    """En alguna combinación FACTORIZADA el suelo devuelve bajo una zapata MENOS que el
    peso de la propia zapata: la carga neta que le llega de la columna y la viga resulta
    hacia ARRIBA (la viga la sostiene). El diseño de cada zapata —punzonamiento, cortante,
    flexión, todos con la losa empujada hacia arriba por el suelo— solo está planteado
    para carga neta hacia abajo; con la carga invertida la losa cuelga y trabaja con la
    tracción arriba. Es un estado físico del candidato, no un dato mal declarado: hasta
    2026-09-28 se clasificaba como ENTRADA_INVALIDA. El candidato se RECHAZA; la búsqueda
    continúa."""

    ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
    """Cualquier otra condición que impide siquiera plantear el sistema, como no
    declarar ninguna combinación factorizada."""

    NO_CUMPLE = "NO_CUMPLE"
    """El sistema se resolvió entero y alguna verificación resultó FAIL."""


class RejectedSystem(BaseModel):
    """Un candidato rechazado, con el motivo y lo suficiente para entenderlo.

    Se guardan los rechazos y no solo su número: en una tipología donde el espacio de
    búsqueda es un producto cartesiano, saber POR QUÉ se cayó cada rama es lo que
    permite al usuario mover los rangos con criterio en vez de a ciegas."""

    geometry: ConnectedFootingGeometry
    reason: RejectionReason
    detail: str = ""


class ConnectedAlternative(BaseModel):
    id: str
    geometry: ConnectedFootingGeometry
    result: ConnectedFootingResult
    # Mismo tipo que la aislada y la combinada: es lo que permite reutilizar `scoring`,
    # `pareto` y `ranker` sin tocarlos.
    metrics: AlternativeMetrics

    @property
    def overall_status(self) -> CheckStatus:
        """El estado que llega al informe. Hoy, siempre NO VERIFICADO."""
        return self.result.overall_status

    @property
    def implemented_checks_status(self) -> CheckStatus:
        """De lo que el motor sabe comprobar, el peor resultado. NO es «cumple»."""
        return self.result.implemented_checks_status

    @property
    def open_tbds(self) -> list[str]:
        """Pendientes que impiden pronunciarse sobre esta alternativa."""
        return self.result.open_tbds

    @property
    def is_not_verified(self) -> bool:
        return self.overall_status is CheckStatus.NOT_VERIFIED

    @property
    def concrete_volume_m3(self) -> float:
        return self.metrics.concrete_volume_m3


class ConnectedAlternativeSet(BaseModel):
    """Resultado de un barrido. Ver la nota de cabecera sobre los TRES conceptos.

    El campo se llama `accepted` y no `valid` a propósito: «válida» sugiere «correcta»,
    y ninguna alternativa de esta tipología puede declararse correcta mientras TBD-C1
    siga abierto."""

    accepted: list[ConnectedAlternative] = Field(
        default_factory=list,
        description=(
            "Sistemas que ninguna verificación IMPLEMENTADA descarta. Aceptada no es "
            "conforme: consúltese `overall_status` de cada una."
        ),
    )
    rejected: list[RejectedSystem] = Field(default_factory=list)
    evaluated_count: int = 0
    truncated: bool = False
    search_note: str = ""
    # 2026-09-28: los rangos EFECTIVOS del barrido, en SI y ya recortados por los linderos
    # (o estimados por el programa). El aviso de borde tiene que compararse con esto, no
    # con lo que trajo la petición.
    search_ranges_m: dict[str, float] = Field(default_factory=dict)

    # -- Las tres particiones, explícitas ---------------------------------

    @property
    def not_verified(self) -> list[ConnectedAlternative]:
        """Aceptadas sobre las que el motor NO puede pronunciarse, por un pendiente
        abierto. Hoy son todas: TBD-C1 no tiene criterio normativo que aplicar."""
        return [a for a in self.accepted if a.open_tbds]

    @property
    def accepted_and_compliant(self) -> list[ConnectedAlternative]:
        """Aceptadas SIN ningún pendiente abierto: las únicas que podrían informarse
        como conformes.

        Mientras TBD-C1 siga abierto esta lista está vacía por construcción, y que lo
        esté es el resultado correcto —no un fallo del barrido—."""
        return [a for a in self.accepted if not a.open_tbds and not a.overall_status.discards
                and a.overall_status in (CheckStatus.PASS, CheckStatus.INFO)]

    @property
    def accepted_with_findings(self) -> list[ConnectedAlternative]:
        """Aceptadas en las que algo de lo IMPLEMENTADO salió con reserva (WARNING).
        Se separan de las que solo están bloqueadas por un pendiente: no es lo mismo
        «no puedo pronunciarme» que «sí me pronuncio, y con reservas»."""
        return [a for a in self.accepted
                if a.implemented_checks_status is CheckStatus.WARNING]

    def open_tbds(self) -> list[str]:
        """Pendientes que bloquean el conjunto del barrido, sin repetir."""
        vistos: list[str] = []
        for a in self.accepted:
            for t in a.open_tbds:
                if t not in vistos:
                    vistos.append(t)
        return vistos

    def status_summary(self) -> dict[str, int]:
        """Cuántas aceptadas hay en cada estado. Lo que el informe tiene que mostrar
        en vez de un simple recuento de «alternativas encontradas»."""
        conteo: dict[str, int] = {}
        for a in self.accepted:
            clave = a.overall_status.value
            conteo[clave] = conteo.get(clave, 0) + 1
        return conteo

    def rejections_by_reason(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for r in self.rejected:
            conteo[r.reason.value] = conteo.get(r.reason.value, 0) + 1
        return conteo


class ConnectedSearchParameters(BaseModel):
    """Rango de geometrías a explorar, para las DOS zapatas.

    La zapata de lindero y la interior se barren por separado porque sus rangos útiles
    son distintos: la exterior quiere ser corta en la dirección de la viga —para reducir
    la excentricidad— y ancha en la transversal, y la interior no tiene esa restricción."""

    ext_long_min_m: float = Field(..., gt=0, description="Longitud sobre el eje de la viga")
    ext_long_max_m: float = Field(..., gt=0)
    ext_long_step_m: float = Field(default=0.20, gt=0)
    ext_transv_min_m: float = Field(..., gt=0)
    ext_transv_max_m: float = Field(..., gt=0)
    ext_transv_step_m: float = Field(default=0.20, gt=0)

    int_long_min_m: float = Field(..., gt=0)
    int_long_max_m: float = Field(..., gt=0)
    int_long_step_m: float = Field(default=0.20, gt=0)
    int_transv_min_m: float = Field(..., gt=0)
    int_transv_max_m: float = Field(..., gt=0)
    int_transv_step_m: float = Field(default=0.20, gt=0)

    h_min_m: float = Field(default=0.50, gt=0)
    h_max_m: float = Field(default=1.20, gt=0)
    h_step_m: float = Field(default=0.10, gt=0)

    max_systems: int = Field(
        default=DEFAULT_MAX_CONNECTED_SYSTEMS,
        gt=0,
        description=(
            "Tope de ternas a evaluar en este barrido. Configurable: el valor por "
            "defecto es un punto de partida, no un límite del producto. Al alcanzarlo "
            "el resultado queda marcado `truncated=True` y con advertencia; el tope "
            "nunca se aplica en silencio."
        ),
    )

    site_limits: SiteLimits | None = Field(
        default=None,
        description=(
            "Linderos del terreno (2026-09-28). El del extremo inicial lo fija la zapata de "
            "lindero (`EdgeAnchor`); aquí cuentan el del fondo y los laterales, que RECORTAN "
            "el barrido. None = sin límites (comportamiento anterior)."
        ),
    )

    same_depth_both_footings: bool = Field(
        default=False,
        description=(
            "Si es True, las dos zapatas comparten peralte. Reduce el espacio de "
            "búsqueda de n² a n parejas y responde a una práctica constructiva "
            "habitual, pero es una RESTRICCIÓN del usuario: puede dejar fuera el "
            "óptimo. No se activa por defecto."
        ),
    )

    @model_validator(mode="after")
    def _rangos_coherentes(self) -> "ConnectedSearchParameters":
        for lo, hi, nombre in (
            (self.ext_long_min_m, self.ext_long_max_m, "ext_long"),
            (self.ext_transv_min_m, self.ext_transv_max_m, "ext_transv"),
            (self.int_long_min_m, self.int_long_max_m, "int_long"),
            (self.int_transv_min_m, self.int_transv_max_m, "int_transv"),
            (self.h_min_m, self.h_max_m, "h"),
        ):
            if hi < lo:
                raise ValueError(f"Rango {nombre} invertido: {lo} > {hi}.")
        return self


def _frange(lo: float, hi: float, step: float) -> list[float]:
    valores, x = [], lo
    while x <= hi + 1e-9:
        valores.append(round(x, 6))
        x += step
    return valores


def _depth_pairs(params: ConnectedSearchParameters) -> list[tuple[float, float]]:
    """Parejas de peralte ORDENADAS POR LA SUMA, que es proporcional al volumen de
    concreto a igualdad de planta. La primera que cumpla es la más barata de las que
    cumplen; un bucle anidado daría la primera del ORDEN DE ITERACIÓN, que no es un
    criterio."""
    alturas = _frange(params.h_min_m, params.h_max_m, params.h_step_m)
    if params.same_depth_both_footings:
        parejas = [(h, h) for h in alturas]
    else:
        parejas = [(a, b) for a in alturas for b in alturas]
    return sorted(parejas, key=lambda p: (p[0] + p[1], p[0], p[1]))


def recortar_por_linderos(
    params: "ConnectedSearchParameters", layout: ConnectedFootingLayout
) -> tuple["ConnectedSearchParameters", str]:
    """Recorta los rangos para que ninguna zapata salga del terreno.

    Las dos zapatas se modelan centradas lateralmente sobre su columna (el cuerpo libre de
    la conectada es plano, a lo largo de la viga): un lindero lateral limita su ancho a la
    columna más dos veces la holgura menor. Correrlas lateralmente exigiría un modelo con
    torsión en la viga y reparto biaxial en el cuerpo rígido, que no está implementado.
    La zapata interior va centrada sobre su columna también a lo largo de la viga: el
    lindero del fondo limita su largo del mismo modo. El del extremo inicial lo fija
    `EdgeAnchor` y aquí no se repite."""
    lim = params.site_limits
    if lim is None:
        return params, ""
    X = layout.longitudinal_axis == "X"

    def dims(el) -> tuple[float, float]:
        return (el.column.bx_m, el.column.by_m) if X else (el.column.by_m, el.column.bx_m)

    (_, et_col), (il_col, it_col) = dims(layout.exterior), dims(layout.interior)
    cambios: dict[str, float] = {}
    partes: list[str] = []
    laterales = [v for v in (lim.side_neg_clearance_m, lim.side_pos_clearance_m) if v is not None]
    if laterales:
        menor = min(laterales)
        cambios["ext_transv_max_m"] = min(params.ext_transv_max_m, et_col + 2.0 * menor)
        cambios["int_transv_max_m"] = min(params.int_transv_max_m, it_col + 2.0 * menor)
        partes.append(
            f"ancho de cada zapata ≤ columna + 2·{menor:.3f} m (linderos laterales; las "
            f"zapatas de la conectada se modelan centradas sobre su columna)"
        )
    if lim.end_clearance_m is not None:
        cambios["int_long_max_m"] = min(params.int_long_max_m, il_col + 2.0 * lim.end_clearance_m)
        partes.append(f"largo de la interior ≤ columna + 2·{lim.end_clearance_m:.3f} m (lindero del fondo)")
    if not cambios:
        return params, ""
    recortados = params.model_copy(update=cambios)
    vacio = any(
        getattr(recortados, f"{k}_max_m") < getattr(recortados, f"{k}_min_m") - 1e-9
        for k in ("ext_transv", "int_transv", "int_long")
    )
    nota = "Linderos del terreno: " + "; ".join(partes) + "."
    if vacio:
        nota += (" Con esos linderos ningún tamaño del rango cabe en el terreno: no se evaluó "
                 "ninguna terna. Revise los linderos o el rango.")
    return recortados, nota


def _classify(exc: ValueError) -> tuple[RejectionReason, str]:
    """Traduce la negativa del solver a un motivo de búsqueda.

    El solver lanza `ValueError` cuando no puede siquiera plantear el sistema. Aquí esa
    negativa se convierte en un candidato RECHAZADO: en un barrido, una geometría
    inviable no puede detener la exploración de las demás."""
    texto = str(exc)
    if "DESPEGUE" in texto:
        return RejectionReason.DESPEGUE, texto
    if "CARGA_NETA_ASCENDENTE" in texto:
        return RejectionReason.CARGA_NETA_ASCENDENTE, texto
    if "GEOMETRIA_IMPOSIBLE" in texto or "no cabe" in texto:
        return RejectionReason.GEOMETRIA_IMPOSIBLE, texto
    return RejectionReason.ENTRADA_INVALIDA, texto


# --- Reparto del barrido entre varios procesos (2026-09-24) --------------------
#
# El barrido es la parte cara del programa: 1500 ternas tardaban 7,6 s en un solo
# núcleo, y el tope se alcanzaba antes de agotar el rango, de modo que el resultado se
# entregaba TRUNCADO. Repartirlo no es solo esperar menos: permite subir el tope y que
# la búsqueda deje de presentarse como no exhaustiva.
#
# QUÉ GARANTIZA QUE EL RESULTADO NO CAMBIE
# La unidad de reparto es la PLANTA (las cuatro dimensiones en planta), no el candidato
# suelto, porque dentro de una planta el barrido tiene una parada que depende del
# resultado: se prueban las parejas de peralte de menor a mayor volumen y se detiene en
# la primera aceptada. Cada proceso reproduce esa parada dentro de su planta, y el padre
# junta las plantas EN EL ORDEN del barrido, aplicando el tope candidato a candidato
# igual que el recorrido secuencial. Mismos candidatos evaluados, mismos rechazos, mismos
# identificadores `CONN-xxx`. Lo comprueba `tests/test_barrido_paralelo_conectada.py`,
# que exige igualdad EXACTA entre los dos caminos, y el congelamiento.
#
# El motor es determinista y no guarda estado entre candidatos, así que un proceso
# aparte calcula exactamente lo mismo.

_UMBRAL_PARALELO = 400  # candidatos; por debajo, arrancar procesos cuesta más de lo que ahorra
_MAX_PROCESOS = 8

# Procesos reutilizados entre barridos. Arrancarlos cuesta medio segundo en Windows —un
# 16 % de un barrido típico— y no hay razón para pagarlo en cada cálculo: son procesos
# sin estado, que reciben con cada tarea todo lo que necesitan.
_POOL: ProcessPoolExecutor | None = None
_POOL_TAMANO = 0


def _pool(procesos: int) -> ProcessPoolExecutor:
    global _POOL, _POOL_TAMANO
    roto = _POOL is not None and getattr(_POOL, "_broken", False)
    if _POOL is None or roto or _POOL_TAMANO != procesos:
        if _POOL is not None:
            _POOL.shutdown(wait=False, cancel_futures=True)
        _POOL = ProcessPoolExecutor(max_workers=procesos)
        _POOL_TAMANO = procesos
    return _POOL


def cerrar_procesos() -> None:
    """Cierra los procesos del barrido. Se llama al terminar; también sirve en tests."""
    global _POOL, _POOL_TAMANO
    if _POOL is not None:
        _POOL.shutdown(wait=False, cancel_futures=True)
        _POOL, _POOL_TAMANO = None, 0


atexit.register(cerrar_procesos)


def _evaluar_lote_en_trabajador(
    contexto: dict, lote: list[list[ConnectedFootingGeometry]]
) -> list[list[tuple]]:
    """Varias plantas por tarea.

    El tamaño de la tarea importa: cuando una planta acepta en su primer candidato dura
    unos 4 ms, y con una tarea por planta el ir y venir entre procesos cuesta más que el
    cálculo. Agrupándolas, el reparto se amortiza.

    El contexto viaja con cada tarea —unos 3 KB— en vez de instalarse al arrancar el
    proceso: es lo que permite reutilizar los mismos procesos entre barridos distintos,
    que es de donde sale la mayor parte del ahorro."""
    return [_evaluar_planta(geos, contexto) for geos in lote]


def _evaluar_planta(geos: list[ConnectedFootingGeometry], ctx: dict) -> list[tuple]:
    """Las parejas de peralte de UNA planta, hasta la primera aceptada.

    Devuelve un resultado por candidato evaluado, en orden: `("RECHAZADO", geo, motivo,
    detalle)` o `("ACEPTADO", geo, resultado, None)`. No asigna identificadores ni aplica
    el tope: eso es del recorrido, que es quien conoce el orden global."""
    salida: list[tuple] = []
    for geo in geos:
        try:
            r = solve_connected_footing(
                ctx["layout"], geo, soil=ctx["soil"], concrete=ctx["concrete"],
                steel=ctx["steel"], code=ctx["code"], contact_model=ctx["contact_model"],
                depth_params=ctx["depth_params"], **ctx["solver_kwargs"],
            )
        except ValueError as exc:
            motivo, detalle = _classify(exc)
            salida.append(("RECHAZADO", geo, motivo, detalle))
            continue

        # Solo FAIL descarta, y por eso el campo se llama `accepted` y no `valid`. Ver la
        # nota de cabecera: exigir PASS rechazaría TODAS las alternativas mientras TBD-C1
        # siga abierto.
        if r.overall_status.discards:
            salida.append(
                ("RECHAZADO", geo, RejectionReason.NO_CUMPLE, "; ".join(r.discard_reasons[:3]))
            )
            continue

        salida.append(("ACEPTADO", geo, r, None))
        # Pareja de peralte más barata que cumple para esta planta: las parejas vienen
        # ordenadas por volumen creciente.
        break
    return salida


def _plantas(
    layout: ConnectedFootingLayout, params: ConnectedSearchParameters
) -> "Iterator[list[ConnectedFootingGeometry]]":
    """Las geometrías del barrido, agrupadas por planta y en el orden del recorrido."""
    ext_long = _frange(params.ext_long_min_m, params.ext_long_max_m, params.ext_long_step_m)
    ext_transv = _frange(
        params.ext_transv_min_m, params.ext_transv_max_m, params.ext_transv_step_m
    )
    int_long = _frange(params.int_long_min_m, params.int_long_max_m, params.int_long_step_m)
    int_transv = _frange(
        params.int_transv_min_m, params.int_transv_max_m, params.int_transv_step_m
    )
    parejas_h = _depth_pairs(params)
    longitudinal = layout.longitudinal_axis == "X"

    for e_l in ext_long:
        for e_t in ext_transv:
            for i_l in int_long:
                for i_t in int_transv:
                    yield [
                        ConnectedFootingGeometry(
                            exterior_B_m=e_l if longitudinal else e_t,
                            exterior_L_m=e_t if longitudinal else e_l,
                            exterior_h_m=h_e,
                            interior_B_m=i_l if longitudinal else i_t,
                            interior_L_m=i_t if longitudinal else i_l,
                            interior_h_m=h_i,
                        )
                        for h_e, h_i in parejas_h
                    ]


def generate_connected_alternatives(
    layout: ConnectedFootingLayout,
    params: ConnectedSearchParameters,
    *,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    code: IConcreteCode,
    contact_model: ContactPressureModel,
    depth_params: DepthSearchParameters,
    workers: int | None = None,
    **solver_kwargs,
) -> ConnectedAlternativeSet:
    """Barre las dos plantas y las parejas de peralte, y devuelve lo que no falla.

    `layout` fija lo que NO se barre: las columnas, sus cargas, la distancia entre ejes,
    la viga y —lo más importante— el modelo de análisis y el modo de reparto del par,
    que son declaraciones del proyectista y no parámetros a optimizar.

    `workers` reparte el barrido entre procesos: `None` lo decide por tamaño, `1` fuerza
    el recorrido secuencial. El resultado es el MISMO en los dos casos (ver la nota de
    arriba); solo cambia cuánto tarda."""
    resultado = ConnectedAlternativeSet()
    params, nota_linderos = recortar_por_linderos(params, layout)
    resultado.search_ranges_m = {
        k: v for k, v in params.model_dump().items() if k.endswith("_m") and isinstance(v, float)
    }

    ext_long = _frange(params.ext_long_min_m, params.ext_long_max_m, params.ext_long_step_m)
    ext_transv = _frange(
        params.ext_transv_min_m, params.ext_transv_max_m, params.ext_transv_step_m
    )
    int_long = _frange(params.int_long_min_m, params.int_long_max_m, params.int_long_step_m)
    int_transv = _frange(
        params.int_transv_min_m, params.int_transv_max_m, params.int_transv_step_m
    )
    parejas_h = _depth_pairs(params)

    tope = params.max_systems
    total = (
        len(ext_long) * len(ext_transv) * len(int_long) * len(int_transv) * len(parejas_h)
    )
    if total > tope:
        resultado.truncated = True
        resultado.search_note = (
            f"El rango solicitado genera {total} ternas, por encima del tope declarado "
            f"de {tope}. Se exploró solo hasta el tope: el resultado NO es una búsqueda "
            f"exhaustiva y puede no contener el óptimo. Suba `max_systems`, acote los "
            f"rangos, aumente los pasos, o declare el mismo peralte para las dos zapatas."
        )

    if nota_linderos:
        resultado.search_note = (resultado.search_note + " " + nota_linderos).strip()

    contexto = {
        "layout": layout, "soil": soil, "concrete": concrete, "steel": steel,
        "code": code, "contact_model": contact_model, "depth_params": depth_params,
        "solver_kwargs": solver_kwargs,
    }

    # Las plantas se generan PEREZOSAMENTE. Materializarlas todas costaba construir
    # decenas de miles de geometrías que el barrido no llega a mirar: cada planta se
    # detiene en su primera pareja de peralte aceptada, y el tope corta mucho antes de
    # agotar el rango. Cada planta evalúa al menos un candidato, así que `tope` plantas
    # es cota suficiente.
    plantas_totales = len(ext_long) * len(ext_transv) * len(int_long) * len(int_transv)
    generador = islice(_plantas(layout, params), tope)
    en_paralelo = _reparte(workers, min(total, tope), min(plantas_totales, tope))

    if en_paralelo > 1:
        try:
            pool = _pool(en_paralelo)
            # VENTANA DESLIZANTE, no un `map` de todo el barrido. El tope suele caer mucho
            # antes de agotar las plantas, y despacharlas todas de golpe hace que los
            # procesos sigan calculando geometrías que nadie va a leer: la primera versión
            # de esto calculaba un 73 % de más y se comía la ganancia. Con la ventana se
            # mantienen los procesos ocupados y se pasa del tope como mucho en lo que
            # quepa en ella.
            #
            # Los resultados se CONSUMEN EN ORDEN de barrido: es lo que mantiene idénticos
            # los identificadores, los recuentos y la lista de rechazos.
            ventana = en_paralelo + 2
            lote = _tamano_de_lote(min(plantas_totales, tope), en_paralelo)
            pendientes: deque = deque()
            while True:
                while len(pendientes) < ventana:
                    siguiente = list(islice(generador, lote))
                    if not siguiente:
                        break
                    pendientes.append(
                        pool.submit(_evaluar_lote_en_trabajador, contexto, siguiente)
                    )
                if not pendientes:
                    break
                for salida in pendientes.popleft().result():
                    if _acumular(resultado, salida, soil, code, tope):
                        for futuro in pendientes:
                            futuro.cancel()
                        return resultado
            return resultado
        except (OSError, BrokenProcessPool):
            # Sin recursos para crear procesos, o un proceso caído: se sigue por el camino
            # secuencial, que da el mismo resultado. Un barrido no se pierde por no poder
            # paralelizar.
            cerrar_procesos()
            resultado = ConnectedAlternativeSet(
                truncated=resultado.truncated, search_note=resultado.search_note,
                search_ranges_m=resultado.search_ranges_m,
            )
            generador = islice(_plantas(layout, params), tope)

    for geos in generador:
        if _acumular(resultado, _evaluar_planta(geos, contexto), soil, code, tope):
            return resultado

    return resultado


def _tamano_de_lote(plantas: int, procesos: int) -> int:
    """Plantas por tarea: bastantes para amortizar el reparto, pocas para no calcular de
    más cuando el tope cae pronto."""
    return max(1, min(16, plantas // (procesos * 4) or 1))


def _reparte(workers: int | None, candidatos: int, plantas: int) -> int:
    """Cuántos procesos usar. Por debajo del umbral, uno: arrancarlos cuesta."""
    if workers is not None:
        return max(1, min(workers, plantas))
    if candidatos < _UMBRAL_PARALELO or plantas < 2:
        return 1
    return max(1, min(_MAX_PROCESOS, (os.cpu_count() or 1) - 1, plantas))


def _acumular(
    resultado: ConnectedAlternativeSet,
    salida: list[tuple],
    soil: SoilProfile,
    code: IConcreteCode,
    tope: int,
) -> bool:
    """Incorpora los candidatos de una planta. Devuelve True si se alcanzó el tope.

    El tope se comprueba ANTES de contar cada candidato, igual que en el recorrido
    secuencial: `evaluated_count` nunca lo supera."""
    for estado, geo, a, b in salida:
        if resultado.evaluated_count >= tope:
            resultado.truncated = True
            return True
        resultado.evaluated_count += 1
        if estado == "RECHAZADO":
            resultado.rejected.append(RejectedSystem(geometry=geo, reason=a, detail=b))
            continue
        resultado.accepted.append(
            ConnectedAlternative(
                id=f"CONN-{len(resultado.accepted) + 1:03d}", geometry=geo, result=a,
                metrics=compute_connected_metrics(
                    a, soil.Df_m, code.cover_footing_mm()[0] / 1000.0
                ),
            )
        )
    return False


# =========================================================================
# Puntuación y ordenamiento
# =========================================================================


class ScoredConnectedAlternative(BaseModel):
    alternative: ConnectedAlternative
    score: float = Field(..., description="Menor es mejor: todas las métricas son costos")
    breakdown: dict


def rank_connected_alternatives(
    alternatives: list[ConnectedAlternative], weights: ScoreWeights | None = None
) -> list[ScoredConnectedAlternative]:
    """Ordena ALTERNATIVAS ACEPTADAS por costo, con el mismo núcleo que las otras dos
    tipologías.

    El orden es por costo y nada más. NO significa recomendación: la primera de la
    lista sigue siendo NO VERIFICADO como todas las demás, y quien la presente tiene
    que decirlo. Ordenar no aprueba.

    No hay aquí ninguna aritmética de puntuación: `score_metric_sets` opera sobre las
    métricas y no sabe qué tipología las produjo. Duplicarla habría sido la vía directa a
    que las tres tipologías acabaran puntuando con criterios distintos sin que nadie lo
    note."""
    from engine.optimization.scoring import score_metric_sets

    puntuadas = score_metric_sets([a.metrics for a in alternatives], weights)
    resultado = [
        ScoredConnectedAlternative(alternative=a, score=score, breakdown=breakdown)
        for a, (score, breakdown) in zip(alternatives, puntuadas)
    ]
    # Desempate por id: dos alternativas con la misma puntuación deben salir siempre en
    # el mismo orden.
    return sorted(resultado, key=lambda s: (s.score, s.alternative.id))
