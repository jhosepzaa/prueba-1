"""Materiales: concreto y acero.

Los límites normativos citados (f'c >= 17 MPa, fy <= 550 MPa) provienen de
E.060 §9.4 y §9.5 respectivamente (ver docs/normativa/referencias_e060_e050.md).
El peso unitario del concreto NO es un valor normativo: es un supuesto de
ingeniería habitual, explícito y editable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from engine.units.validators import (
    FC_RANGE_MPA,
    FY_RANGE_MPA,
    GAMMA_CONCRETE_RANGE_KNM3,
    PlausibilityWarning,
    check_range,
)

BarType = Literal["corrugada", "lisa"]

# Supuesto de ingeniería (NO normativo): peso unitario típico del concreto armado
# en la práctica peruana (~2400 kgf/m3). Editable por el usuario en cada proyecto.
DEFAULT_CONCRETE_UNIT_WEIGHT_KNM3 = 24.0

# Constante física universal (no normativa): módulo de elasticidad del acero.
STEEL_ES_MPA = 200_000.0


class MaterialConcrete(BaseModel):
    fc_MPa: float = Field(..., gt=0, description="f'c, resistencia especificada a compresión [MPa]")
    unit_weight_kNm3: float = Field(
        default=DEFAULT_CONCRETE_UNIT_WEIGHT_KNM3,
        gt=0,
        description="Peso unitario del concreto armado [kN/m3] -- supuesto de ingeniería, no normativo",
    )

    @field_validator("fc_MPa")
    @classmethod
    def _fc_min_normativo(cls, v: float) -> float:
        # E.060 §9.4: "Para el concreto estructural, f'c no debe ser inferior a 17 MPa"
        if v < 17.0:
            raise ValueError(
                f"f'c = {v} MPa es menor que el mínimo normativo de 17 MPa (E.060 §9.4)."
            )
        return v

    def plausibility_warnings(self) -> list[PlausibilityWarning]:
        warnings: list[PlausibilityWarning] = []
        w = check_range("fc_MPa", self.fc_MPa, *FC_RANGE_MPA, "MPa")
        if w:
            warnings.append(w)
        w = check_range(
            "unit_weight_kNm3", self.unit_weight_kNm3, *GAMMA_CONCRETE_RANGE_KNM3, "kN/m3"
        )
        if w:
            warnings.append(w)
        return warnings


class MaterialSteel(BaseModel):
    fy_MPa: float = Field(..., gt=0, description="fy, esfuerzo de fluencia del acero [MPa]")
    bar_type: BarType = Field(default="corrugada")
    Es_MPa: float = Field(default=STEEL_ES_MPA, gt=0)

    @field_validator("bar_type")
    @classmethod
    def _solo_corrugadas(cls, v: str) -> str:
        # E.060 §3.5.1: "El refuerzo debe ser corrugado, excepto en los casos indicados en
        # 3.5.4". §3.5.4.2 admite barras lisas solo en espirales, preesfuerzo y refuerzo por
        # cambios volumétricos de losas nervadas (<= 1/4"). Ninguno es refuerzo de zapatas
        # ni de vigas de conexión, y §9.7.2 exige acero corrugado (Fase 10A, A8).
        if v != "corrugada":
            raise ValueError(
                "ENTRADA_INVALIDA: E.060 §3.5.1 y §3.5.4.2 no admiten barras lisas como "
                "refuerzo de zapatas ni de vigas de conexión; §9.7.2 exige acero corrugado."
            )
        return v

    @field_validator("fy_MPa")
    @classmethod
    def _fy_max_normativo(cls, v: float) -> float:
        # E.060 §9.5: "Los valores de fy ... no deben exceder de 550 MPa"
        if v > 550.0:
            raise ValueError(
                f"fy = {v} MPa excede el máximo normativo de 550 MPa (E.060 §9.5)."
            )
        return v

    def plausibility_warnings(self) -> list[PlausibilityWarning]:
        w = check_range("fy_MPa", self.fy_MPa, *FY_RANGE_MPA, "MPa")
        return [w] if w else []
