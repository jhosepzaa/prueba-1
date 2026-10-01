"""Parámetros de búsqueda para la generación de geometría B-L y la iteración de h.

Puramente definidos por el usuario del programa -- no hay valores normativos aquí.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GeometrySearchParameters(BaseModel):
    B_min_m: float = Field(..., gt=0)
    B_max_m: float = Field(..., gt=0)
    B_step_m: float = Field(..., gt=0)
    L_min_m: float = Field(..., gt=0)
    L_max_m: float = Field(..., gt=0)
    L_step_m: float = Field(..., gt=0)
    max_LB_ratio: float = Field(default=2.0, gt=1.0)

    @model_validator(mode="after")
    def _rangos_consistentes(self) -> "GeometrySearchParameters":
        if self.B_max_m < self.B_min_m:
            raise ValueError("B_max_m debe ser >= B_min_m")
        if self.L_max_m < self.L_min_m:
            raise ValueError("L_max_m debe ser >= L_min_m")
        return self


class DepthSearchParameters(BaseModel):
    h_min_m: float = Field(..., gt=0)
    h_max_m: float = Field(..., gt=0)
    h_step_m: float = Field(..., gt=0)
    assumed_bar_diameter_mm: float = Field(
        default=16.0,
        gt=0,
        description=(
            "Diámetro de barra asumido para estimar d antes de diseñar el acero "
            "(d = h - recubrimiento - db/2). Supuesto de ingeniería editable, no normativo."
        ),
    )
    hook_type_x: Literal["ninguno", "90", "180"] = Field(
        default="ninguno",
        description="Gancho declarado en dirección X. NUNCA se asume: por defecto no hay gancho.",
    )
    hook_type_y: Literal["ninguno", "90", "180"] = Field(
        default="ninguno",
        description="Gancho declarado en dirección Y. NUNCA se asume: por defecto no hay gancho.",
    )
    cover_override_mm: float | None = Field(
        default=None,
        description="Recubrimiento a usar en vez del valor por defecto de E.060 §7.7.1 a) (75 mm).",
    )

    @model_validator(mode="after")
    def _rangos_consistentes(self) -> "DepthSearchParameters":
        if self.h_max_m < self.h_min_m:
            raise ValueError("h_max_m debe ser >= h_min_m")
        return self
