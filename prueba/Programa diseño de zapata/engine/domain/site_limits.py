"""Límites del terreno: dónde están los linderos respecto de las columnas (2026-09-28).

QUÉ DECLARA EL PROYECTISTA
==========================
La distancia libre de la CARA de la columna al lindero, en cada sentido. Es lo que se
mide en obra y lo que exige el plano de la propiedad; `None` quiere decir que por ese lado
no hay límite. Cero es una columna al ras del lindero.

  start_clearance_m     cara de la PRIMERA columna → lindero del extremo inicial
                        (en la conectada lo cubre `EdgeAnchor`: la zapata de lindero)
  end_clearance_m       cara de la ÚLTIMA columna (o de la interior) → lindero del extremo final
  side_neg_clearance_m  cara lateral de las columnas → lindero lateral del lado negativo
  side_pos_clearance_m  cara lateral de las columnas → lindero lateral del lado positivo

«Longitudinal» es la dirección en que se alinean las columnas (la de la viga en la
conectada); «lateral» es la perpendicular. Con varias columnas, la cara lateral que cuenta
es la más próxima a cada lindero.

QUÉ NO ES
=========
No es un criterio de diseño ni un dato normativo: es la geometría de la propiedad. La
zapata no puede salir de ella. Cómo se COLOCA la zapata dentro de esos límites lo decide
cada generador, y lo declara como heurística de búsqueda.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SiteLimits(BaseModel):
    start_clearance_m: float | None = Field(
        default=None, ge=0.0,
        description="Cara de la primera columna al lindero del extremo inicial [m]. None = libre.",
    )
    end_clearance_m: float | None = Field(
        default=None, ge=0.0,
        description="Cara de la última columna al lindero del extremo final [m]. None = libre.",
    )
    side_neg_clearance_m: float | None = Field(
        default=None, ge=0.0,
        description="Cara lateral de las columnas al lindero del lado negativo [m]. None = libre.",
    )
    side_pos_clearance_m: float | None = Field(
        default=None, ge=0.0,
        description="Cara lateral de las columnas al lindero del lado positivo [m]. None = libre.",
    )

    @property
    def has_side_limits(self) -> bool:
        return self.side_neg_clearance_m is not None or self.side_pos_clearance_m is not None

    def describe(self) -> str:
        """Texto para la traza y el informe."""
        partes = []
        for etiqueta, valor in (
            ("inicio", self.start_clearance_m), ("fin", self.end_clearance_m),
            ("lateral −", self.side_neg_clearance_m), ("lateral +", self.side_pos_clearance_m),
        ):
            partes.append(f"{etiqueta}: {'libre' if valor is None else f'{valor:.3f} m de la cara'}")
        return "Linderos declarados — " + "; ".join(partes) + "."
