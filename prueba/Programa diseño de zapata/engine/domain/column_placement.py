"""Posición de la columna sobre la zapata — Fase 1B.

POR QUÉ UN TIPO NUEVO Y NO UN CAMPO EN `Column`
===============================================
`Column` describe la SECCIÓN de la columna (bx, by, forma). Su posición sobre la
zapata no es una propiedad de la columna: es una propiedad de la relación entre
columna y zapata. Meterla dentro de `Column` obligaría a tocar todas las firmas
que hoy reciben un `Column` —y con ellas los tests que las cubren—, que es
exactamente lo que el congelamiento de la Fase 1A existe para impedir.

Envolver cuesta menos y no rompe nada: `Column` no cambia ni una línea.

POR QUÉ LA POSICIÓN ES UN DESPLAZAMIENTO Y NO UNA COORDENADA ABSOLUTA
=====================================================================
Durante el barrido de geometrías B y L VARÍAN candidato a candidato. Una
coordenada absoluta ("la columna está en x = 1,50 m") significaría una posición
relativa distinta en cada candidato, lo que no describe ningún problema real. El
desplazamiento respecto del centroide de la zapata sí es estable bajo el barrido.

ALCANCE DESDE LA FASE 1C
========================
Cualquier holgura al borde es admisible, incluida la NULA — la cara de la columna
al ras del lindero. Cuando la holgura baja de d/2, la sección crítica de
punzonamiento se trunca y `engine/foundation/critical_section.py` la resuelve con
su propio perímetro, alpha_s, centroide y Jc.

LIMITACIÓN QUE SIGUE ABIERTA — ANCLAJE A UN BORDE DURANTE EL BARRIDO
====================================================================
La posición se expresa como desplazamiento respecto del CENTRO. Para una zapata
de lindero lo que en realidad está fijo es la distancia de la cara de la columna
al borde, normalmente cero. Con B fija ambas descripciones son equivalentes, pero
durante el BARRIDO de geometrías no lo son: al crecer B, un desplazamiento
constante deja de mantener la cara al ras. Quien busque geometrías para una
zapata de lindero debe ajustar el desplazamiento a cada B, o fijar B.

CONVENCIÓN DE EJES
==================
La misma del resto del motor (E.050 art. 28.1, ver `engine/soil/eccentricity.py`):
X es la dirección de B, Y la dirección de L. Un desplazamiento positivo en X mueve
la columna hacia el borde de mayor x.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from engine.domain.column import Column


class ColumnPlacement(BaseModel):
    """Una columna y dónde se apoya sobre la zapata.

    Con `offset_x_m = offset_y_m = 0` describe el caso concéntrico, que es el
    comportamiento anterior a la Fase 1B. Ése es el valor por defecto, de modo
    que el caso de una columna centrada no paga ningún precio por la existencia
    de las descentradas."""

    column: Column
    offset_x_m: float = Field(
        default=0.0,
        description=(
            "Desplazamiento del centroide de la columna respecto del centroide de la "
            "zapata, a lo largo del eje X (dirección de B) [m]. Positivo hacia el borde "
            "de mayor x."
        ),
    )
    offset_y_m: float = Field(
        default=0.0,
        description=(
            "Desplazamiento del centroide de la columna respecto del centroide de la "
            "zapata, a lo largo del eje Y (dirección de L) [m]."
        ),
    )

    @property
    def is_concentric(self) -> bool:
        return abs(self.offset_x_m) < 1e-12 and abs(self.offset_y_m) < 1e-12

    # --- Geometría derivada -------------------------------------------------
    # Todas devuelven medidas respecto de los BORDES de la zapata, que es lo que
    # necesitan los voladizos y las holguras. El origen se toma en el borde de
    # menor coordenada de cada eje.

    def center_x_m(self, B_m: float) -> float:
        return B_m / 2.0 + self.offset_x_m

    def center_y_m(self, L_m: float) -> float:
        return L_m / 2.0 + self.offset_y_m

    def cantilevers_x(self, B_m: float) -> tuple[float, float]:
        """(voladizo del lado x=0, voladizo del lado x=B). Iguales si es concéntrica."""
        cx = self.center_x_m(B_m)
        return cx - self.column.bx_m / 2.0, B_m - cx - self.column.bx_m / 2.0

    def cantilevers_y(self, L_m: float) -> tuple[float, float]:
        cy = self.center_y_m(L_m)
        return cy - self.column.by_m / 2.0, L_m - cy - self.column.by_m / 2.0

    def min_clearance_m(self, B_m: float, L_m: float) -> float:
        """La menor distancia de una cara de la columna al borde de la zapata.

        Es la magnitud que decide si la sección crítica de punzonamiento se cierra
        por los cuatro lados: si esta holgura es menor que d/2, el perímetro se
        trunca y el modelo cerrado deja de aplicar (E.060 §11.12.1.2)."""
        return min(*self.cantilevers_x(B_m), *self.cantilevers_y(L_m))

    def fits_inside(self, B_m: float, L_m: float) -> bool:
        """La columna debe estar dentro de la planta de la zapata.

        Holgura NULA es válida: es la zapata de lindero, con la cara de la columna al
        ras del borde. Solo se rechaza una holgura negativa, que significa que la
        columna sobresale del concreto."""
        return self.min_clearance_m(B_m, L_m) >= -1e-12

    @model_validator(mode="after")
    def _offsets_finitos(self) -> "ColumnPlacement":
        for nombre, valor in (("offset_x_m", self.offset_x_m), ("offset_y_m", self.offset_y_m)):
            if valor != valor or abs(valor) == float("inf"):
                raise ValueError(f"{nombre} debe ser un número finito; recibido {valor}.")
        return self


def concentric(column: Column) -> ColumnPlacement:
    """Atajo para el caso por defecto. Existe para que los llamadores no tengan
    que escribir dos ceros y para que el caso concéntrico se lea como tal."""
    return ColumnPlacement(column=column)
