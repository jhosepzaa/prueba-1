"""Validación de rangos físicamente plausibles.

Distingue dos niveles (sección 17 del encargo — "evitar errores de conversión" y
"detectar valores físicamente improbables"):

- Imposible / matemáticamente inválido (p. ej. f'c <= 0, B <= 0): esto se rechaza
  con una excepción dura en el propio modelo Pydantic (Field(gt=0), etc.), porque
  no representa nada construible.
- Físicamente improbable pero no imposible (p. ej. f'c = 5 MPa, qadm = 5000 kPa):
  esto NO se rechaza automáticamente -- se recolecta como advertencia para que el
  ingeniero la vea y decida, porque un valor "raro" puede ser correcto en un caso
  particular y el motor no debe impedir el cálculo por eso.

Los rangos "razonables" aquí NO son límites normativos (salvo que se indique la
cita); son bandas de sentido común de la práctica local, explícitamente marcadas
como tales para no confundirlas con requisitos de E.060/E.050.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlausibilityWarning:
    field: str
    value: float
    message: str


def check_range(
    field: str, value: float, low: float, high: float, unit: str
) -> PlausibilityWarning | None:
    """Devuelve una advertencia si `value` cae fuera de [low, high]. No lanza excepción."""
    if value < low or value > high:
        return PlausibilityWarning(
            field=field,
            value=value,
            message=(
                f"{field} = {value} {unit} está fuera del rango habitual "
                f"[{low}, {high}] {unit}. No es un límite normativo, es una "
                f"banda de sentido común -- revisar el dato de entrada."
            ),
        )
    return None


# Bandas de sentido común (NO normativas) usadas por los modelos de dominio.
FC_RANGE_MPA = (17.0, 55.0)  # el mínimo 17 MPa SÍ es normativo (E.060 §9.4); el
# máximo 55 MPa es solo una banda de sentido común para concreto convencional.
FY_RANGE_MPA = (240.0, 550.0)  # el máximo 550 MPa SÍ es normativo (E.060 §9.5).
QADM_RANGE_KPA = (30.0, 1000.0)
GAMMA_SOIL_RANGE_KNM3 = (12.0, 22.0)
GAMMA_CONCRETE_RANGE_KNM3 = (22.0, 25.0)
COVER_RANGE_MM = (20.0, 100.0)
COLUMN_DIM_RANGE_M = (0.15, 2.0)
FOOTING_DIM_RANGE_M = (0.5, 15.0)
