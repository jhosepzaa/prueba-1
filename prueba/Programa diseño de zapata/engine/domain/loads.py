"""Combinaciones de carga -- separación obligatoria SERVICIO / FACTORIZADA.

Arquitectura exigida por el usuario (punto 9 de la corrección de Fase 2):

    LOAD CASES
    ├── SERVICIO     (S1, S2, ...)   -> usadas para geometría B-L y presión de contacto
    │                                    (E.060 §15.2, E.050 art.17.1)
    └── FACTORIZADA  (U1, U2, ...)   -> usadas para diseño estructural
                                         (E.060 §15.2: "cargas amplificadas")

El motor NO deriva combinaciones factorizadas a partir de CM/CV/CS (E.060 §9.2 se
documenta como referencia, pero el MVP no la ejecuta -- ver punto 8 de la
corrección: el usuario entrega P, Mx, My ya combinados por combinación).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class LoadCombinationType(str, Enum):
    SERVICIO = "SERVICIO"
    FACTORIZADA = "FACTORIZADA"


class ComponentAction(BaseModel):
    """Aporte YA FACTORIZADO de un caso de carga a una combinación (Fase 10B)."""

    case_name: str
    kind: str = Field(..., description="Tipo de caso de E.060 §9.2: CM, CV, CVi, CS, CE, CL, CT")
    level: str | None = Field(default=None, description="SERVICIO | RESISTENCIA, solo CVi y CS")
    factor: float
    P_kN: float
    Mx_kNm: float
    My_kNm: float
    Hx_kN: float
    Hy_kN: float
    origin: str | None = Field(
        default=None,
        description=(
            "Fase 10C. De dónde viene el aporte en una carga CORREGIDA por el reparto de la "
            "conectada: columna exterior, columna interior o carga generada por el motor. "
            "None en las combinaciones de una columna."
        ),
    )


class LoadComposition(BaseModel):
    """De qué casos está hecha una combinación. Solo existe en el modo por casos."""

    components: list[ComponentAction]
    redistributed: bool = Field(
        default=False,
        description=(
            "Fase 10C. True si la composición es la de una carga CORREGIDA por el reparto de la "
            "conectada, obtenida por superposición. Los consumidores que no están validados para "
            "cargas redistribuidas la tratan como ausente (hoy, la reducción sísmica al 80 %)."
        ),
    )
    dead_load_factor: float | None = Field(
        default=None,
        description=(
            "Factor común de los casos CM en esta combinación. Es el que reciben las cargas "
            "muertas que genera el motor (peso propio de la viga: E.020 art. 2). None si la "
            "combinación no contiene CM."
        ),
    )

    def total(self, attr: str, kinds: set[str] | None = None, level: str | None = None) -> float:
        """Suma de un atributo sobre los componentes filtrados por tipo y nivel."""
        s = 0.0
        for c in self.components:
            if kinds is not None and c.kind not in kinds:
                continue
            if level is not None and c.level != level:
                continue
            s += getattr(c, attr)
        return s


class LoadCombination(BaseModel):
    name: str = Field(..., min_length=1, description='Identificador, p.ej. "S1", "U2"')
    type: LoadCombinationType
    P_kN: float = Field(..., description="Carga axial en la base de la columna [kN], compresión positiva")
    # CONVENCIÓN E.050 art. 28.1 -- ver engine/soil/eccentricity.py.
    # OJO: no es "momento alrededor del eje X". Es el momento que flexiona EN la
    # dirección X, que mecánicamente es el momento alrededor del eje Y.
    Mx_kNm: float = Field(default=0.0, description="Momento que desplaza la resultante a lo largo del eje X (E.050 art. 28.1: ex = Mx/Q) [kN·m]")
    My_kNm: float = Field(default=0.0, description="Momento que desplaza la resultante a lo largo del eje Y (E.050 art. 28.1: ey = My/Q) [kN·m]")
    Hx_kN: float = Field(default=0.0, description="Fuerza horizontal en X [kN] (no usada en checks del MVP)")
    Hy_kN: float = Field(default=0.0, description="Fuerza horizontal en Y [kN] (no usada en checks del MVP)")
    description: str = Field(default="")

    # Banderas para las disposiciones opcionales de E.060 §15.2 -- necesarias
    # porque el motor no descompone la combinación en CM/CV/CS (punto 8: el
    # usuario entrega P,Mx,My ya combinados), así que debe declarar él mismo si
    # la combinación incluye estas acciones.
    includes_seismic_loads: bool = Field(default=False)
    includes_wind_loads: bool = Field(default=False)

    # Fase 10B — solo en el modo por casos (`engine/domain/load_cases.py`). None en el modo
    # de combinaciones directas, que no cambia.
    composition: LoadComposition | None = Field(default=None)


class LoadCaseSet(BaseModel):
    service: list[LoadCombination] = Field(default_factory=list)
    factored: list[LoadCombination] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validar_tipos_y_unicidad(self) -> "LoadCaseSet":
        for combo in self.service:
            if combo.type is not LoadCombinationType.SERVICIO:
                raise ValueError(
                    f'La combinación "{combo.name}" está en la lista `service` pero '
                    f"su type es {combo.type}, no SERVICIO."
                )
        for combo in self.factored:
            if combo.type is not LoadCombinationType.FACTORIZADA:
                raise ValueError(
                    f'La combinación "{combo.name}" está en la lista `factored` pero '
                    f"su type es {combo.type}, no FACTORIZADA."
                )
        if not self.service:
            raise ValueError("Debe existir al menos una combinación de SERVICIO.")
        if not self.factored:
            raise ValueError("Debe existir al menos una combinación FACTORIZADA.")

        names = [c.name for c in (*self.service, *self.factored)]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"Nombres de combinación duplicados: {sorted(dupes)}")
        return self
