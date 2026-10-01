"""Zapata que soporta más de una columna — Fase 2.

BASE NORMATIVA
==============
E.060 §15.10.1, verbatim:

  "Las zapatas que soporten MÁS DE UNA COLUMNA, pedestal o muro (zapatas
   combinadas y losas de cimentación) deben diseñarse para resistir las cargas
   amplificadas y las reacciones inducidas, de acuerdo con los requisitos de
   diseño apropiados de esta Norma."

E.050 art. 23.2 reconoce la zapata combinada como cimentación superficial, y su
art. 23.3 fija la proporción **L ≤ 10·B**: por encima de esa relación la norma la
clasifica como cimentación continua, que es otra tipología.

QUÉ ES «LONGITUDINAL» Y QUÉ «TRANSVERSAL»
=========================================
La dirección LONGITUDINAL es aquella a lo largo de la cual las columnas están
separadas: es la que se analiza como viga y donde aparece el momento negativo. La
TRANSVERSAL es la perpendicular, donde cada columna trabaja sobre una franja.

Se determina por la SEPARACIÓN de las columnas, no por qué dimensión sea mayor:
una zapata puede ser más ancha que larga y aun así tener las columnas alineadas a
lo largo del lado corto. Con una sola columna no hay separación y el caso degenera
en la zapata aislada, que tiene su propio solver.

CONVENCIÓN DE EJES
==================
La del resto del motor (E.050 art. 28.1): X es la dirección de B, Y la de L.
Las posiciones de columna son desplazamientos respecto del centroide de la zapata,
igual que en `ColumnPlacement`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet

Direction = Literal["X", "Y"]

# E.050 art. 23.3 se verifica desde H6 (2026-09-20) en LAS TRES tipologías, con una sola
# implementación: `engine.codes.peru.e050_soils.check_shape_ratio`. Aquí no queda ninguna
# constante propia: duplicarla fue lo que permitió que la aislada no mirara el artículo.


class ColumnOnFooting(BaseModel):
    """Una columna sobre la zapata combinada, con sus propias cargas.

    Reutiliza `LoadCaseSet` sin cambios: la separación entre combinaciones de
    SERVICIO y FACTORIZADAS, que es un requisito del proyecto desde la Fase 2
    original, se mantiene columna por columna."""

    label: str = Field(..., min_length=1, description='Identificador, p.ej. "C1"')
    placement: ColumnPlacement
    loads: LoadCaseSet

    @property
    def offset_x_m(self) -> float:
        return self.placement.offset_x_m

    @property
    def offset_y_m(self) -> float:
        return self.placement.offset_y_m


class CombinedFootingLayout(BaseModel):
    """Geometría y columnas de una zapata combinada."""

    B_m: float = Field(..., gt=0, description="Dimensión a lo largo de X")
    L_m: float = Field(..., gt=0, description="Dimensión a lo largo de Y")
    columns: list[ColumnOnFooting] = Field(..., min_length=2)

    @model_validator(mode="after")
    def _validar(self) -> "CombinedFootingLayout":
        etiquetas = [c.label for c in self.columns]
        if len(set(etiquetas)) != len(etiquetas):
            raise ValueError(f"Las etiquetas de columna deben ser únicas; recibidas {etiquetas}.")

        for c in self.columns:
            if not c.placement.fits_inside(self.B_m, self.L_m):
                raise ValueError(
                    f"La columna «{c.label}» no cabe dentro de la zapata "
                    f"({self.B_m} x {self.L_m} m) en su posición "
                    f"({c.offset_x_m:+.3f}, {c.offset_y_m:+.3f}) m."
                )

        # Dos columnas en la misma posición no describen ninguna estructura real.
        for i, a in enumerate(self.columns):
            for b in self.columns[i + 1 :]:
                if (
                    abs(a.offset_x_m - b.offset_x_m) < 1e-9
                    and abs(a.offset_y_m - b.offset_y_m) < 1e-9
                ):
                    raise ValueError(
                        f"Las columnas «{a.label}» y «{b.label}» están en la misma posición."
                    )

        # Todas las columnas deben declarar las mismas combinaciones: una combinación
        # que exista en una columna y no en otra no describe un estado de carga.
        nombres = [
            {c.name for c in col.loads.service} | {c.name for c in col.loads.factored}
            for col in self.columns
        ]
        if any(n != nombres[0] for n in nombres[1:]):
            faltantes = set().union(*nombres) - set.intersection(*nombres)
            raise ValueError(
                f"Todas las columnas deben declarar las mismas combinaciones de carga. "
                f"No están en todas: {sorted(faltantes)}."
            )
        return self

    # --- Dirección de análisis ---------------------------------------------

    @property
    def longitudinal_direction(self) -> Direction:
        """La dirección en la que las columnas están separadas.

        Se decide por la SEPARACIÓN, no por cuál dimensión de la zapata sea mayor:
        las columnas pueden estar alineadas a lo largo del lado corto."""
        spread_x = max(c.offset_x_m for c in self.columns) - min(c.offset_x_m for c in self.columns)
        spread_y = max(c.offset_y_m for c in self.columns) - min(c.offset_y_m for c in self.columns)
        return "X" if spread_x >= spread_y else "Y"

    @property
    def longitudinal_length_m(self) -> float:
        return self.B_m if self.longitudinal_direction == "X" else self.L_m

    @property
    def transverse_width_m(self) -> float:
        return self.L_m if self.longitudinal_direction == "X" else self.B_m

    def longitudinal_position_m(self, column: ColumnOnFooting) -> float:
        """Posición de la columna sobre el eje longitudinal, medida desde el extremo
        de menor coordenada (que es el origen que usa `beam_diagram`)."""
        if self.longitudinal_direction == "X":
            return self.longitudinal_length_m / 2.0 + column.offset_x_m
        return self.longitudinal_length_m / 2.0 + column.offset_y_m

    def column_width_along(self, column: ColumnOnFooting, direction: Direction) -> float:
        col = column.placement.column
        return col.bx_m if direction == "X" else col.by_m

    @property
    def combination_names(self) -> list[str]:
        primera = self.columns[0].loads
        return [c.name for c in primera.service] + [c.name for c in primera.factored]

    def shape_ratio(self) -> float:
        """L/B con L el lado mayor: es como E.050 art. 23.3 expresa la proporción."""
        largo, corto = max(self.B_m, self.L_m), min(self.B_m, self.L_m)
        return largo / corto
