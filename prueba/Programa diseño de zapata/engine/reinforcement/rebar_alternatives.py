"""Generación de MÚLTIPLES alternativas de armado (sección 9 del encargo).

A diferencia de `rebar_selector.select_rebar` (Fase 2, que devolvía una sola
solución), aquí se generan varias combinaciones diámetro-separación válidas y
constructibles para que el ingeniero compare:

    Alternativa A:  1/2" @ 20 cm
    Alternativa B:  5/8" @ 25 cm
    Alternativa C:  3/8" @ 12.5 cm
    ...

Límites normativos aplicados:
  - Separación libre mínima entre barras paralelas: max(db, 25 mm)  -- E.060 §7.6.1
  - Separación máxima del refuerzo:                 min(3h, 400 mm) -- E.060 §9.7.3
    (aplicable porque el As de zapatas se rige por §9.7; ver
     docs/normativa/as_min_zapatas.md)
  - As mínimo:                                      §9.7 vía §10.6

El criterio de "no sobrearmar" (`MAX_OVERPROVISION_RATIO`) NO es normativo: es un
filtro de eficiencia de materiales para descartar soluciones que cumplen pero
desperdician acero.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from engine.codes.peru.rebar_catalog_peru import REBAR_CATALOG
from engine.results.status import CheckStatus

# Separaciones constructivas (múltiplos manejables en obra). Práctica
# constructiva peruana, NO normativa.
PRACTICAL_SPACINGS_M = [0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.30, 0.35, 0.40]

# Una solución que provee más de este múltiplo del acero requerido se considera
# antieconómica y se descarta de las alternativas ofrecidas. Criterio de
# eficiencia, no normativo.
MAX_OVERPROVISION_RATIO = 1.60


class RebarAlternative(BaseModel):
    bar_designation: str
    diameter_mm: float
    spacing_m: float
    n_bars: int
    width_m: float

    As_required_m2: float
    As_min_m2: float
    As_provided_m2: float
    utilization: float = Field(..., description="As_requerido / As_provisto -- cercano a 1.0 es eficiente")
    overprovision: float = Field(..., description="As_provisto / As_requerido")

    spacing_min_allowed_m: float
    spacing_max_allowed_m: float
    spacing_ok: bool

    governed_by: str = Field(..., description='"flexión" o "cuantía mínima §9.7"')

    # L4 por opción: cada diámetro tiene su propia longitud de desarrollo, así que
    # NO basta con verificar la barra elegida por `select_rebar`.
    ld_required_m: float | None = Field(
        default=None, description="Longitud de desarrollo requerida para ESTE diámetro"
    )
    ld_available_m: float | None = None
    development_ok: bool | None = Field(
        default=None, description="None = todavía no verificada; False = no puede desarrollarse"
    )
    development_message: str = ""

    status: CheckStatus
    note: str

    @property
    def label(self) -> str:
        return f"{self.bar_designation} @ {self.spacing_m * 100:.1f} cm"


def min_clear_spacing_m(diameter_mm: float) -> float:
    """Separación entre EJES mínima = separación libre mínima + db.
    Separación libre mínima = max(db, 25 mm) -- E.060 §7.6.1."""
    return (max(diameter_mm, 25.0) + diameter_mm) / 1000.0


def max_spacing_m(h_m: float) -> float:
    """min(3h, 400 mm) -- E.060 §9.7.3."""
    return min(3.0 * h_m, 0.400)


def _round_down_to_practical(spacing_m: float) -> float | None:
    candidates = [s for s in PRACTICAL_SPACINGS_M if s <= spacing_m + 1e-9]
    return max(candidates) if candidates else None


def generate_rebar_alternatives(
    As_required_m2: float,
    As_min_m2: float,
    width_m: float,
    h_m: float,
    max_alternatives: int = 4,
) -> list[RebarAlternative]:
    """Devuelve alternativas de armado ordenadas de menor a mayor diámetro.

    `As_required_m2` es el acero por análisis de flexión; `As_min_m2` el mínimo de
    §9.7. El acero de diseño es el mayor de ambos.
    """
    if math.isnan(As_required_m2):
        return []

    As_design = max(As_required_m2, As_min_m2)
    governed_by = "flexión" if As_required_m2 >= As_min_m2 else "cuantía mínima §9.7"
    if As_design <= 0:
        return []

    s_max = max_spacing_m(h_m)
    alternatives: list[RebarAlternative] = []

    for bar in REBAR_CATALOG:
        bar_area_m2 = bar.area_mm2 / 1_000_000.0
        s_min = min_clear_spacing_m(bar.diameter_mm)
        if s_min > s_max:
            continue  # este diámetro no admite ninguna separación válida

        # Separación teórica que provee exactamente As_design sobre `width_m`
        s_needed = bar_area_m2 * width_m / As_design
        s_practical = _round_down_to_practical(min(s_needed, s_max))
        if s_practical is None or s_practical < s_min:
            continue  # requeriría barras más juntas de lo permitido

        n_bars = max(math.floor(width_m / s_practical) + 1, 2)
        As_provided = n_bars * bar_area_m2
        if As_provided < As_design:
            continue

        overprovision = As_provided / As_design
        if overprovision > MAX_OVERPROVISION_RATIO:
            continue  # cumple pero desperdicia acero

        alternatives.append(
            RebarAlternative(
                bar_designation=bar.designation,
                diameter_mm=bar.diameter_mm,
                spacing_m=s_practical,
                n_bars=n_bars,
                width_m=width_m,
                As_required_m2=As_required_m2,
                As_min_m2=As_min_m2,
                As_provided_m2=As_provided,
                utilization=As_design / As_provided,
                overprovision=overprovision,
                spacing_min_allowed_m=s_min,
                spacing_max_allowed_m=s_max,
                spacing_ok=s_min <= s_practical <= s_max,
                governed_by=governed_by,
                status=CheckStatus.PASS,
                note=f"As_diseño gobernado por {governed_by}.",
            )
        )
        if len(alternatives) >= max_alternatives:
            break

    return alternatives
