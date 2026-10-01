"""Selección preliminar de acero: diámetro y separación constructiva a partir del
As de diseño. Diseño "preliminar" (Fase 2) -- la generación de VARIAS alternativas
de armado y su comparación pertenece a la Fase 3/optimización, fuera de este
alcance.

Límites normativos usados:
- Separación libre mínima entre barras paralelas: max(db, 25 mm) -- E.060 §7.6.1.
- Separación máxima del refuerzo de retracción/temperatura: min(3h, 400 mm) --
  E.060 §9.7.3 (aplicable porque el As de zapatas se rige por §9.7, ver
  docs/normativa/as_min_zapatas.md).
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from engine.codes.peru.rebar_catalog_peru import REBAR_CATALOG, RebarSize
from engine.results.status import CheckStatus

# Separaciones constructivas prácticas habituales (m) -- no normativo, catálogo
# de la práctica constructiva peruana. Se usa para redondear la separación
# calculada a un valor "colocable" en obra.
PRACTICAL_SPACINGS_M = [0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.275, 0.30]


class RebarSelection(BaseModel):
    bar_designation: str
    diameter_mm: float
    spacing_m: float
    n_bars: int
    As_provided_m2: float
    As_required_m2: float
    status: CheckStatus
    note: str


def _max_spacing_m(h_m: float) -> float:
    return min(3.0 * h_m, 0.400)  # E.060 §9.7.3


def _min_spacing_m(diameter_mm: float) -> float:
    clear_min_mm = max(diameter_mm, 25.0)  # E.060 §7.6.1
    return (clear_min_mm + diameter_mm) / 1000.0


def select_rebar(As_required_m2: float, width_m: float, h_m: float) -> RebarSelection:
    """Recorre el catálogo de menor a mayor diámetro y elige la primera
    combinación diámetro-separación que sea constructiva (separación dentro de
    [s_min, s_max]) y provea As >= As_required, con la separación redondeada
    hacia abajo al valor práctico más cercano (para no quedar corto de acero)."""
    if math.isnan(As_required_m2):
        return RebarSelection(
            bar_designation="N/A",
            diameter_mm=0.0,
            spacing_m=0.0,
            n_bars=0,
            As_provided_m2=0.0,
            As_required_m2=float("nan"),
            status=CheckStatus.FAIL,
            note="No se puede seleccionar acero: el diseño a flexión no convergió (sección insuficiente, ver check de flexión).",
        )
    if As_required_m2 <= 0:
        As_required_m2 = 0.0

    best: RebarSelection | None = None
    for bar in REBAR_CATALOG:
        bar_area_m2 = bar.area_mm2 / 1_000_000.0
        s_max = _max_spacing_m(h_m)
        s_min = _min_spacing_m(bar.diameter_mm)

        if As_required_m2 <= 0.0:
            s_needed = s_max
        else:
            s_needed = bar_area_m2 * width_m / As_required_m2

        s_practical = _round_down_to_practical(min(s_needed, s_max))
        if s_practical < s_min:
            continue  # este diámetro necesitaría una separación menor que la mínima permitida -> probar uno mayor
        if s_practical > s_max:
            s_practical = s_max

        n_bars = max(math.floor(width_m / s_practical) + 1, 2)
        As_provided_m2 = n_bars * bar_area_m2

        if As_provided_m2 >= As_required_m2:
            status = CheckStatus.PASS
            note = "Cumple As requerido con separación constructiva."
        else:
            status = CheckStatus.FAIL
            note = "Ni siquiera al límite de separación mínima se alcanza As requerido con este diámetro."

        candidate = RebarSelection(
            bar_designation=bar.designation,
            diameter_mm=bar.diameter_mm,
            spacing_m=s_practical,
            n_bars=n_bars,
            As_provided_m2=As_provided_m2,
            As_required_m2=As_required_m2,
            status=status,
            note=note,
        )
        if status is CheckStatus.PASS:
            return candidate
        best = candidate  # conserva el último intento por si ningún diámetro del catálogo alcanza

    assert best is not None
    return best


def _round_down_to_practical(spacing_m: float) -> float:
    candidates = [s for s in PRACTICAL_SPACINGS_M if s <= spacing_m]
    if not candidates:
        return min(PRACTICAL_SPACINGS_M)
    return max(candidates)
