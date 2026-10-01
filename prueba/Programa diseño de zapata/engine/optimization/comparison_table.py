"""Tabla comparativa de alternativas (sección 11 del encargo original).

ALCANCE: esto es una VISTA DE DATOS sobre el conjunto generado, no un ranking de
calidad. Permite ordenar por UNA métrica objetiva a la vez (volumen de concreto,
masa de acero, área, dimensión máxima...), que es una operación de presentación.

La función de puntuación ponderada (Score = w1*costo + w2*volumen + ...) NO está
aquí: pertenece a la Fase 4, y se mantiene separada a propósito para no confundir
"ordenar por una columna" con "decidir cuál es la mejor alternativa".
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from engine.optimization.alternative_generator import Alternative, AlternativeSet


class ComparisonRow(BaseModel):
    id: str
    B_m: float
    L_m: float
    h_m: float
    d_m: float
    steel_x: str
    steel_y: str
    qmax_kPa: float
    qadm_governing_combo: str
    concrete_volume_m3: float
    steel_mass_kg: float
    max_plan_dimension_m: float
    constructive_complexity_index: float
    status: str


# Claves de ordenamiento disponibles. Todas son métricas objetivas medibles, no
# puntuaciones compuestas.
SORT_KEYS: dict[str, Callable[[ComparisonRow], float]] = {
    "volumen_concreto": lambda r: r.concrete_volume_m3,
    "masa_acero": lambda r: r.steel_mass_kg,
    "dimension_maxima": lambda r: r.max_plan_dimension_m,
    "area": lambda r: r.B_m * r.L_m,
    "peralte": lambda r: r.h_m,
    "complejidad_constructiva": lambda r: r.constructive_complexity_index,
}


def _row(alternative: Alternative) -> ComparisonRow:
    c = alternative.candidate
    m = alternative.metrics
    return ComparisonRow(
        id=alternative.id,
        B_m=c.B_m,
        L_m=c.L_m,
        h_m=c.h_m,
        d_m=c.d_m,
        steel_x=f'{c.rebar_x.bar_designation} @ {c.rebar_x.spacing_m * 100:.1f} cm',
        steel_y=f'{c.rebar_y.bar_designation} @ {c.rebar_y.spacing_m * 100:.1f} cm',
        qmax_kPa=c.contact_pressure.qmax_kPa,
        qadm_governing_combo=c.governing_combos.contact_pressure,
        concrete_volume_m3=m.concrete_volume_m3,
        steel_mass_kg=m.steel_mass_kg,
        max_plan_dimension_m=m.max_plan_dimension_m,
        constructive_complexity_index=m.constructive_complexity_index,
        status=c.overall_status.value,
    )


def build_comparison_table(
    alternative_set: AlternativeSet, sort_by: str | None = None, descending: bool = False
) -> list[ComparisonRow]:
    rows = [_row(a) for a in alternative_set.valid]
    if sort_by is not None:
        if sort_by not in SORT_KEYS:
            raise ValueError(
                f'Criterio de ordenamiento "{sort_by}" no reconocido. Disponibles: {sorted(SORT_KEYS)}'
            )
        rows.sort(key=SORT_KEYS[sort_by], reverse=descending)
    return rows


def render_table_text(rows: list[ComparisonRow], limit: int | None = None) -> str:
    shown = rows[:limit] if limit is not None else rows
    header = (
        f"{'ID':<9} {'B[m]':>5} {'L[m]':>5} {'h[m]':>5} {'Acero X':<16} {'Acero Y':<16} "
        f"{'qmax[kPa]':>9} {'V.conc[m3]':>10} {'Acero[kg]':>9} {'Compl.':>7}"
    )
    lines = [header, "-" * len(header)]
    for r in shown:
        lines.append(
            f"{r.id:<9} {r.B_m:>5.2f} {r.L_m:>5.2f} {r.h_m:>5.2f} {r.steel_x:<16} {r.steel_y:<16} "
            f"{r.qmax_kPa:>9.1f} {r.concrete_volume_m3:>10.3f} {r.steel_mass_kg:>9.1f} "
            f"{r.constructive_complexity_index:>7.2f}"
        )
    if limit is not None and len(rows) > limit:
        lines.append(f"... ({len(rows) - limit} alternativas más)")
    return "\n".join(lines)
