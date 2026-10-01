"""Unidades en que se ESCRIBE la memoria de cálculo (2026-09-23).

El motor calcula siempre en SI. Esto solo decide en qué unidad aparece cada número
en el documento, usando los factores del registro único
(`engine/units/unit_registry.py`): aquí no hay ninguna equivalencia nueva.

QUÉ NO SE CONVIERTE, Y POR QUÉ
La TRAZA se emite siempre en SI. No es una tabla de resultados: es el registro del
cálculo tal como el motor lo hizo, con su ecuación simbólica, su sustitución numérica
y su unidad. Reescribir los números de una sustitución dejaría un texto que ya no es
el cálculo que se ejecutó, y además `tests/freeze` congela esos valores como contrato
(CLAUDE.md §11). La memoria lo dice en lugar de disimularlo.

Tampoco se convierten las magnitudes que el usuario no elige —volumen (m³), área de
acero (cm²), masa (kg), diámetros y recubrimientos (mm)—: son unidades de obra y no
hay desplegable que las cambie.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from engine.units.unit_registry import (
    KIND_TABLES,
    ROUNDING_NOTE,
    SI_UNITS,
    convert,
)

TRACE_IN_SI_NOTE = (
    "Los cuadros de esta memoria se expresan en las unidades declaradas por el "
    "proyectista. La TRAZA DE CÁLCULO conserva las unidades SI del motor (kN, kN·m, "
    "kPa, MPa, m): es el registro del cálculo tal como se ejecutó, no una tabla de "
    "resultados, y reescribir sus sustituciones numéricas daría un texto que ya no "
    "sería ese cálculo. Volúmenes (m³), áreas de acero (cm²), masas (kg) y diámetros "
    "(mm) se mantienen en su unidad de obra."
)


class ReportUnits(BaseModel):
    """Unidades de presentación de la memoria. Por omisión, las SI del motor."""

    force: str = SI_UNITS["force"]
    moment: str = SI_UNITS["moment"]
    pressure: str = SI_UNITS["pressure"]
    strength: str = SI_UNITS["strength"]
    length: str = SI_UNITS["length"]
    unit_weight: str = SI_UNITS["unit_weight"]

    @classmethod
    def from_input(cls, units) -> "ReportUnits":
        """Desde el bloque `units` de una petición de la API (duck typing)."""
        if units is None:
            return cls()
        return cls(
            force=units.force, moment=units.moment, pressure=units.pressure,
            strength=units.strength, length=units.length, unit_weight=units.unit_weight,
        )

    @property
    def es_si(self) -> bool:
        return all(getattr(self, k) == v for k, v in SI_UNITS.items())

    def label(self, kind: str) -> str:
        """Rótulo de la unidad elegida para esa magnitud."""
        return getattr(self, kind)

    def value(self, si_value: float, kind: str) -> float:
        """El valor SI expresado en la unidad elegida. Sin formatear."""
        return convert(si_value, kind, SI_UNITS[kind], getattr(self, kind))

    def _decimals(self, kind: str, requested: int) -> int:
        """Decimales de la unidad elegida. Solo se ajustan en LONGITUD.

        Los decimales que pide quien llama están pensados para metros. En centímetros o
        milímetros sobran cifras —2,50 m escritos «250.00 cm» fingen una precisión de
        centésima de milímetro—, así que se descuenta un decimal por orden de magnitud;
        la precisión ABSOLUTA no cambia y el milímetro sigue estando.

        En las demás magnitudes no se toca: recortar un decimal en kgf/cm² convertiría
        un f'c declarado de 211,5 en «212», y un dato del proyectista se escribe como
        lo escribió el proyectista."""
        if kind != "length":
            return requested
        factor = KIND_TABLES[kind][self.length]
        if factor >= 1.0:
            return requested
        return max(0, requested + round(math.log10(factor)))

    def fmt(self, si_value: float | None, kind: str, decimals: int = 2) -> str:
        """El número ya escrito, sin unidad. `None` se escribe como «—»."""
        if si_value is None:
            return "—"
        return f"{self.value(si_value, kind):.{self._decimals(kind, decimals)}f}"

    def con(self, si_value: float | None, kind: str, decimals: int = 2) -> str:
        """El número con su unidad detrás."""
        if si_value is None:
            return "—"
        return f"{self.fmt(si_value, kind, decimals)} {self.label(kind)}"

    def note(self) -> str:
        """Lo que la memoria declara sobre sus propias unidades."""
        if self.es_si:
            return TRACE_IN_SI_NOTE
        declaradas = ", ".join(
            f"{self.label(k)}" for k in ("force", "moment", "pressure", "strength", "length")
        )
        return f"Unidades declaradas: {declaradas}. {TRACE_IN_SI_NOTE} {ROUNDING_NOTE}"
