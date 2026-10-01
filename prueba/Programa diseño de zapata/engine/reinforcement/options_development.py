"""Verificación de longitud de desarrollo para CADA opción de armado.

DEFECTO QUE CORRIGE ESTE MÓDULO (auditoría integral)
====================================================
`check_development_length` se ejecutaba una sola vez, sobre la barra elegida por
`select_rebar`. Pero `generate_rebar_alternatives` ofrece varios diámetros, y las
soluciones de armado (`arming_solutions`) los combinan libremente.

Medido en un caso real: de 16 soluciones de armado generadas para una geometría,
**12 usaban un diámetro cuya longitud de desarrollo nunca se verificó**. Como ld
crece linealmente con db, una opción de 3/4" puede no desarrollarse donde una de
1/2" sí lo hace -- y se estaba ofreciendo como válida.

SOLUCIÓN
========
Cada `RebarAlternative` se verifica con su propio diámetro y separación, y las que
no pueden desarrollarse quedan marcadas (`development_ok=False`) y se EXCLUYEN de
la lista de opciones ofrecidas. Así ninguna solución de armado puede construirse
sobre una barra no desarrollable.
"""

from __future__ import annotations

from engine.reinforcement.development_check import check_development_length
from engine.reinforcement.rebar_alternatives import RebarAlternative
from engine.reinforcement.rebar_geometry import BarLayerGeometry


def verify_options_development(
    options: list[RebarAlternative],
    reference_layer: BarLayerGeometry,
    fy_MPa: float,
    fc_MPa: float,
) -> tuple[list[RebarAlternative], list[RebarAlternative]]:
    """Verifica cada opción con SU diámetro y separación.

    `reference_layer` aporta la geometría común de la capa (voladizo, recubrimiento,
    dirección); de cada opción se toman db y s, que son los que cambian.

    Devuelve (opciones_desarrollables, opciones_descartadas).
    """
    ok: list[RebarAlternative] = []
    rejected: list[RebarAlternative] = []

    for option in options:
        db = option.diameter_mm / 1000.0
        layer_for_option = reference_layer.model_copy(
            update={
                "bar_diameter_m": db,
                "spacing_m": option.spacing_m,
                "n_bars": option.n_bars,
                "clear_spacing_m": max(option.spacing_m - db, 0.0),
            }
        )
        result = check_development_length(layer_for_option, fy_MPa, fc_MPa)
        updated = option.model_copy(
            update={
                "ld_required_m": result.ld_required_m,
                "ld_available_m": result.ld_available_m,
                "development_ok": result.deficit_m <= 1e-9,
                "development_message": result.message,
            }
        )
        (ok if updated.development_ok else rejected).append(updated)

    return ok, rejected
