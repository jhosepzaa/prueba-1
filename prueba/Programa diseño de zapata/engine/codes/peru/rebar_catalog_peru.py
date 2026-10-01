"""Catálogo comercial de barras de refuerzo corrugadas en Perú.

IMPORTANTE: esto NO es una disposición normativa. Es un catálogo de fabricación
(diámetros y áreas nominales estandarizados a nivel nacional por productores como
Aceros Arequipa / Siderperú, ampliamente uniformes en toda la industria peruana).
Se trata como dato maestro, no como cita de E.060/E.050 -- ver punto 5 de las
preguntas planteadas en la ficha normativa (aceptado por el usuario).
"""

from __future__ import annotations

from typing import NamedTuple


class RebarSize(NamedTuple):
    designation: str  # p.ej. '1/2"'
    diameter_mm: float
    area_mm2: float


# Áreas nominales estándar (mm2) para barras corrugadas de grado 60, catálogo
# comercial peruano habitual.
REBAR_CATALOG: list[RebarSize] = [
    RebarSize('3/8"', 9.5, 71.0),
    RebarSize('1/2"', 12.7, 129.0),
    RebarSize('5/8"', 15.9, 199.0),
    RebarSize('3/4"', 19.1, 284.0),
    RebarSize('1"', 25.4, 510.0),
    RebarSize('1 3/8"', 34.9, 956.0),
]


def rebar_by_designation(designation: str) -> RebarSize:
    for bar in REBAR_CATALOG:
        if bar.designation == designation:
            return bar
    raise ValueError(f'Diámetro "{designation}" no está en el catálogo comercial definido.')
