"""Geometría de la columna que apoya sobre la zapata.

Solo rectangular/cuadrada en el MVP (columnas circulares quedan para una fase
posterior, ver limitaciones de la Fase 1). E.060 §15.3 permite, para columnas
circulares o de polígono regular, tratarlas como cuadradas de área equivalente al
ubicar secciones críticas -- eso ya deja la arquitectura preparada para ese caso
futuro sin cambiar el resto del motor.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from engine.units.validators import COLUMN_DIM_RANGE_M, PlausibilityWarning, check_range

ColumnShape = Literal["rectangular", "cuadrada"]


class Column(BaseModel):
    shape: ColumnShape
    bx_m: float = Field(..., gt=0, description="Dimensión de columna en X [m]")
    by_m: float = Field(..., gt=0, description="Dimensión de columna en Y [m]")

    @model_validator(mode="after")
    def _cuadrada_consistente(self) -> "Column":
        if self.shape == "cuadrada" and abs(self.bx_m - self.by_m) > 1e-9:
            raise ValueError(
                f"shape='cuadrada' requiere bx_m == by_m (recibido bx={self.bx_m}, by={self.by_m})."
            )
        return self

    def plausibility_warnings(self) -> list[PlausibilityWarning]:
        warnings = []
        for name, value in (("bx_m", self.bx_m), ("by_m", self.by_m)):
            w = check_range(name, value, *COLUMN_DIM_RANGE_M, "m")
            if w:
                warnings.append(w)
        return warnings
