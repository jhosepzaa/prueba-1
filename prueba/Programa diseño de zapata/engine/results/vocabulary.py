"""Vocabulario ÚNICO de estados de alternativa — pendiente 8.

POR QUÉ EXISTE
==============
La máquina de verificación es una sola (`CheckStatus`), pero cada tipología rotulaba su
resultado a su manera, y la misma palabra significaba cosas distintas:

    «ACEPTADA» = PASS o INFO en la zapata aislada
    «ACEPTADA» = WARNING, es decir «con reservas», en la conectada

Además «DESCARTADA» y «RECHAZADA» eran dos nombres del mismo estado. Era la diferencia
conocida `VOCABULARIO_ACEPTADA`: una vista común que mostrara el rótulo sin decir de qué
tipología viene haría pasar una conectada con observaciones por una aislada que cumple.

QUÉ RESUELVE Y QUÉ NO TOCA
==========================
Desaparece la palabra ambigua. El vocabulario queda en cuatro términos, uno por desenlace:

| Estado interno                        | Rótulo                     |
|---------------------------------------|----------------------------|
| PASS o INFO, sin pendiente abierto     | CONFORME                   |
| PASS o INFO, con pendiente abierto     | NO VERIFICADA              |
| WARNING                                | ACEPTADA CON OBSERVACIONES |
| NO VERIFICADO                          | NO VERIFICADA              |
| FAIL                                   | RECHAZADA                  |

**Esto es rotulado y nada más.** No cambia ningún `CheckStatus`, ninguna regla de
aceptación, ningún número ni ningún criterio. La semántica interna se mantiene intacta y
sigue siendo la que manda: `accepted` —sobrevive al barrido— no es lo mismo que
`accepted_and_compliant` —PASS o INFO— ni que «verificada». El rótulo es la lectura humana
de esa semántica, no su sustituto.

Un pendiente abierto (`open_tbds`) impide llegar a CONFORME aunque todo lo implementado
pase: es la regla que la conectada ya aplicaba y que aquí se generaliza.
"""

from __future__ import annotations

from typing import Literal

from engine.results.status import CheckStatus

ESTADO_CONFORME = "CONFORME"
ESTADO_CON_OBSERVACIONES = "ACEPTADA CON OBSERVACIONES"
ESTADO_NO_VERIFICADA = "NO VERIFICADA"
ESTADO_RECHAZADA = "RECHAZADA"

StatusLabel = Literal[
    "CONFORME", "ACEPTADA CON OBSERVACIONES", "NO VERIFICADA", "RECHAZADA"
]

#: El vocabulario cerrado, en orden de mejor a peor desenlace.
STATUS_VOCABULARY: list[str] = [
    ESTADO_CONFORME, ESTADO_CON_OBSERVACIONES, ESTADO_NO_VERIFICADA, ESTADO_RECHAZADA,
]

_POR_ESTADO: dict[CheckStatus, str] = {
    CheckStatus.PASS: ESTADO_CONFORME,
    CheckStatus.INFO: ESTADO_CONFORME,
    CheckStatus.WARNING: ESTADO_CON_OBSERVACIONES,
    CheckStatus.NOT_VERIFIED: ESTADO_NO_VERIFICADA,
    CheckStatus.FAIL: ESTADO_RECHAZADA,
}

VOCABULARY_NOTE = (
    "Vocabulario único de las tres tipologías (pendiente 8): CONFORME, ACEPTADA CON "
    "OBSERVACIONES, NO VERIFICADA y RECHAZADA. Es el rótulo del estado, no un criterio: "
    "«aceptada» a secas ya no se usa, porque significaba PASS en una tipología y WARNING en "
    "otra. Un pendiente abierto impide CONFORME aunque todo lo implementado pase."
)


def status_label(status: CheckStatus, open_tbds: "list[str] | tuple[str, ...]" = ()) -> StatusLabel:
    """Rótulo de una alternativa a partir de su estado y de sus pendientes abiertos.

    Un pendiente abierto degrada CONFORME a NO VERIFICADA: el motor no puede demostrar la
    conformidad aunque todo lo implementado haya pasado. Nunca al revés —un FAIL sigue
    siendo RECHAZADA con pendientes o sin ellos—."""
    etiqueta = _POR_ESTADO[status]
    if open_tbds and etiqueta == ESTADO_CONFORME:
        return ESTADO_NO_VERIFICADA
    return etiqueta  # type: ignore[return-value]


# Equivalencias con los rótulos anteriores, para que quien lea un informe antiguo sepa
# traducir. No se usan en el código: son documentación ejecutable del cambio.
LEGACY_EQUIVALENCE: dict[str, str] = {
    "ACEPTADA (aislada, PASS/INFO)": ESTADO_CONFORME,
    "ACEPTADA (conectada, WARNING)": ESTADO_CON_OBSERVACIONES,
    "DESCARTADA (aislada)": ESTADO_RECHAZADA,
    "RECHAZADA (conectada)": ESTADO_RECHAZADA,
    "NO VERIFICADA": ESTADO_NO_VERIFICADA,
    "CONFORME (conectada)": ESTADO_CONFORME,
}
