"""Perfil de suelo.

`pressure_basis` obliga a declarar explícitamente si `qadm_kPa` es una presión
ADMISIBLE BRUTA o NETA (sección 4 del encargo original: "no confundas capacidad
portante última con admisible" y "el programa debe identificar claramente qué tipo
de presión está ingresando el usuario"). La relación bruta/neta se resuelve en
`engine/soil/pressure_basis.py`, no aquí -- este modelo solo declara el dato.

`allow_temporary_increase_30pct` y `allow_seismic_reduction_80pct` corresponden a
las dos disposiciones OPCIONALES de E.060 §15.2 ("se podrá considerar..."). Ambas
quedan en `False` por defecto (decisión validada explícitamente por el usuario en
esta fase). Si se activan, deben registrarse como hipótesis en el CalculationTrace
de cada verificación de presión de contacto -- no se aplican en silencio.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from engine.units.validators import (
    GAMMA_SOIL_RANGE_KNM3,
    QADM_RANGE_KPA,
    PlausibilityWarning,
    check_range,
)


class PressureBasis(str, Enum):
    BRUTA = "BRUTA"
    NETA = "NETA"


class SoilProfile(BaseModel):
    qadm_kPa: float = Field(..., gt=0, description="Presión admisible del suelo [kPa]")
    pressure_basis: PressureBasis = Field(
        ..., description="Declara si qadm_kPa es BRUTA o NETA -- obligatorio, sin default"
    )
    gamma_kNm3: float = Field(..., gt=0, description="Peso unitario del suelo [kN/m3]")
    Df_m: float = Field(..., gt=0, description="Profundidad de cimentación [m]")

    water_table_depth_m: float | None = Field(
        default=None, description="Profundidad del nivel freático desde superficie [m]"
    )
    phi_deg: float | None = Field(default=None, description="Ángulo de fricción interna [grados]")
    cohesion_kPa: float | None = Field(default=None, description="Cohesión del suelo [kPa]")
    mu_friction_soil_concrete: float | None = Field(
        default=None, description="Coeficiente de fricción suelo-concreto"
    )
    FS_used: float | None = Field(
        default=None, description="Factor de seguridad usado en el EMS para obtener qadm (si se conoce)"
    )

    # --- L3: estabilidad. E.050 NO prescribe FS de deslizamiento/volcamiento para
    # zapatas aisladas (art. 39.13.6 solo cubre muros de contención). Por eso estos
    # valores NO tienen default: sin ellos, el check queda NO VERIFICADO.
    FS_sliding_required: float | None = Field(
        default=None,
        description=(
            "FS al deslizamiento adoptado por el proyectista. Sin valor -> deslizamiento "
            "NO VERIFICADO. No se asume ningún valor."
        ),
    )
    FS_overturning_required: float | None = Field(
        default=None,
        description=(
            "FS al volcamiento adoptado por el proyectista. Sin valor -> volcamiento "
            "NO VERIFICADO. No se asume ningún valor."
        ),
    )
    source_notes: str = Field(
        default="", description="Referencia al estudio de mecánica de suelos (EMS) de origen"
    )

    # E.060 §15.2 -- disposiciones opcionales, default apagado (validado con el usuario).
    allow_temporary_increase_30pct: bool = Field(default=False)
    allow_seismic_reduction_80pct: bool = Field(default=False)

    # E.050 art. 26.2 exige Df >= 0,80 m y admite una sola excepción: "En el caso de
    # cimentación sobre roca, el PR define la profundidad de cimentación, pudiendo en
    # este caso ser menor a 0,80 metros". El default False es la rama ESTRICTA: no
    # supone roca, que es la condición que relaja el requisito.
    founded_on_rock: bool = Field(
        default=False,
        description=(
            "Declara que la cimentación se apoya sobre roca. Única excepción de E.050 "
            "art. 26.2 al mínimo de 0,80 m. Debe declararlo el profesional responsable "
            "a partir del EMS; el motor nunca lo deduce."
        ),
    )

    def plausibility_warnings(self) -> list[PlausibilityWarning]:
        warnings = []
        w = check_range("qadm_kPa", self.qadm_kPa, *QADM_RANGE_KPA, "kPa")
        if w:
            warnings.append(w)
        w = check_range("gamma_kNm3", self.gamma_kNm3, *GAMMA_SOIL_RANGE_KNM3, "kN/m3")
        if w:
            warnings.append(w)
        return warnings
