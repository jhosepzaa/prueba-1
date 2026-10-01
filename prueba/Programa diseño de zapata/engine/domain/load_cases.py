"""Contrato de cargas por CASOS — Fase 10B (alternativa C del análisis del contrato).

POR QUÉ EXISTE
==============
El contrato original recibe combinaciones ya formadas: P, M y H de cada combinación.
Con él el motor no sabe qué parte de una combinación es carga muerta, viva o de sismo, y
eso bloquea tres cosas que la norma sí distingue:

  - factorizar las cargas que genera el propio motor —el peso de la viga— con el factor
    de la carga muerta de CADA combinación (TBD-C13);
  - reducir al 80 % SOLO la componente sísmica en las verificaciones del suelo
    (E.030 art. 29 y 62.2; E.060 §15.2.5);
  - contar SOLO la carga muerta como estabilizante (E.020 art. 20.1).

Este módulo añade un SEGUNDO modo de entrada, que produce exactamente los mismos
`LoadCombination` que consume el resto del motor, con su composición adjunta. El modo
directo sigue existiendo y no cambia (invariante I2 del análisis).

TEXTO NORMATIVO (docs/normativa/transcripcion_cargas.md)
========================================================
Tipos de caso — E.060 §9.2 (propuesta 2019):
    CM   carga muerta                          §9.2.1
    CV   carga viva                            §9.2.1  (impacto, nieve y granizo: §9.2.7-8)
    CVi  viento — a nivel de SERVICIO o de RESISTENCIA      §9.2.2
    CS   sismo  — a nivel de RESISTENCIA o de SERVICIO      §9.2.3
    CE   peso y empuje lateral de los suelos, agua del suelo §9.2.5
    CL   peso y presión de líquidos             §9.2.6
    CT   asentamientos, flujo plástico, retracción, temperatura §9.2.9

El nivel de CVi y CS es dato: la norma da ecuaciones distintas para cada nivel (9-2 frente a
9-2a, 9-4 frente a 9-4a). E.020 art. 2: la carga muerta incluye el peso propio.

LO QUE ESTE MÓDULO NO HACE
==========================
No genera combinaciones. Los factores de cada combinación los DECLARA el usuario (invariante
I7): el motor no incorpora las ecuaciones de §9.2 como plantilla. Solo comprueba la
linealidad, la coherencia entre columnas y la consistencia de la declaración.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from engine.domain.loads import (
    ComponentAction,
    LoadCaseSet,
    LoadCombination,
    LoadCombinationType,
    LoadComposition,
)


class LoadCaseKind(str, Enum):
    """Tipos de caso de E.060 §9.2."""

    CM = "CM"
    CV = "CV"
    CVi = "CVi"
    CS = "CS"
    CE = "CE"
    CL = "CL"
    CT = "CT"


class ActionLevel(str, Enum):
    """Nivel al que se entrega una acción de viento o sismo (E.060 §9.2.2, §9.2.3)."""

    SERVICIO = "SERVICIO"
    RESISTENCIA = "RESISTENCIA"


LEVELED_KINDS = frozenset({LoadCaseKind.CVi, LoadCaseKind.CS})


class LoadCase(BaseModel):
    """Un caso de carga de UNA columna, sin factorizar."""

    name: str = Field(..., min_length=1, description='Identificador, p.ej. "CM", "CSx"')
    kind: LoadCaseKind
    level: ActionLevel | None = Field(
        default=None,
        description="Obligatorio para CVi y CS, prohibido en los demás (E.060 §9.2.2-9.2.3)",
    )
    P_kN: float = 0.0
    Mx_kNm: float = Field(default=0.0, description="Convención E.050 art. 28.1: ex = Mx/Q")
    My_kNm: float = Field(default=0.0, description="Convención E.050 art. 28.1: ey = My/Q")
    Hx_kN: float = 0.0
    Hy_kN: float = 0.0
    description: str = ""

    @model_validator(mode="after")
    def _nivel_coherente(self) -> "LoadCase":
        if self.kind in LEVELED_KINDS and self.level is None:
            raise ValueError(
                f'El caso "{self.name}" es {self.kind.value}: E.060 §9.2 da ecuaciones distintas '
                f"según la acción esté a nivel de servicio o de resistencia. Declare `level`."
            )
        if self.kind not in LEVELED_KINDS and self.level is not None:
            raise ValueError(
                f'El caso "{self.name}" es {self.kind.value}: el nivel solo se declara para '
                f"viento (CVi) y sismo (CS)."
            )
        return self


class CombinationDefinition(BaseModel):
    """Una combinación como factores sobre casos, declarados por el usuario.

    `factors` va de NOMBRE de caso a factor con signo. Permite, por ejemplo,
    {"CM": 1.25, "CV": 1.25, "CSx": -1.0} para el sismo en sentido negativo."""

    name: str = Field(..., min_length=1)
    type: LoadCombinationType
    factors: dict[str, float] = Field(..., min_length=1)
    description: str = ""


def _componente(caso: LoadCase, factor: float) -> ComponentAction:
    return ComponentAction(
        case_name=caso.name, kind=caso.kind.value,
        level=caso.level.value if caso.level is not None else None, factor=factor,
        P_kN=factor * caso.P_kN, Mx_kNm=factor * caso.Mx_kNm, My_kNm=factor * caso.My_kNm,
        Hx_kN=factor * caso.Hx_kN, Hy_kN=factor * caso.Hy_kN,
    )


def derive_combination(cases: list[LoadCase], definition: CombinationDefinition) -> LoadCombination:
    """Una combinación de una columna. Invariante I1: cada acción es Σ factor·caso."""
    por_nombre = {c.name: c for c in cases}
    faltan = sorted(set(definition.factors) - set(por_nombre))
    if faltan:
        raise ValueError(
            f'La combinación "{definition.name}" usa casos no declarados en esta columna: '
            f"{faltan}. Declárelos, aunque valgan cero."
        )
    componentes = [_componente(por_nombre[n], f) for n, f in definition.factors.items()]

    # Factor de la carga muerta de ESTA combinación, para las cargas que genera el motor.
    # Si hay varios casos CM deben compartir factor: la carga muerta interna no pertenece a
    # ninguno en particular y no hay forma legítima de elegir entre factores distintos.
    factores_cm = {c.factor for c in componentes if c.kind == LoadCaseKind.CM.value}
    if len(factores_cm) > 1:
        raise ValueError(
            f'La combinación "{definition.name}" aplica factores distintos a sus casos CM '
            f"({sorted(factores_cm)}). El motor asigna a la carga muerta el peso propio que "
            f"genera, y necesita un único factor de CM por combinación."
        )
    dead_factor = factores_cm.pop() if factores_cm else None

    def suma(attr: str) -> float:
        total = 0.0
        for c in componentes:
            total += getattr(c, attr)
        return total

    sismo = any(c.kind == LoadCaseKind.CS.value and c.factor != 0.0 for c in componentes)
    viento = any(c.kind == LoadCaseKind.CVi.value and c.factor != 0.0 for c in componentes)
    return LoadCombination(
        name=definition.name, type=definition.type,
        P_kN=suma("P_kN"), Mx_kNm=suma("Mx_kNm"), My_kNm=suma("My_kNm"),
        Hx_kN=suma("Hx_kN"), Hy_kN=suma("Hy_kN"),
        description=definition.description,
        includes_seismic_loads=sismo, includes_wind_loads=viento,
        composition=LoadComposition(components=componentes, dead_load_factor=dead_factor),
    )


def derive_load_case_set(cases: list[LoadCase], definitions: list[CombinationDefinition]) -> LoadCaseSet:
    """Todas las combinaciones de una columna. Las listas SERVICIO/FACTORIZADA salen del
    `type` declarado; `LoadCaseSet` exige al menos una de cada."""
    nombres = [c.name for c in cases]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise ValueError(f"Casos de carga con nombre repetido: {repetidos}.")
    combos = [derive_combination(cases, d) for d in definitions]
    return LoadCaseSet(
        service=[c for c in combos if c.type is LoadCombinationType.SERVICIO],
        factored=[c for c in combos if c.type is LoadCombinationType.FACTORIZADA],
    )
