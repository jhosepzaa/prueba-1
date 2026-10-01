"""Resolución del PERALTE EFECTIVO `d` usado por flexión, cortante y punzonamiento.

DEFECTO QUE CORRIGE ESTE MÓDULO (auditoría integral)
====================================================
El motor calculaba `d` con un diámetro de barra ASUMIDO (16 mm por defecto) y lo
usaba tal cual para las tres verificaciones de resistencia. Dos errores en uno:

  1. La barra realmente seleccionada casi nunca coincide con la asumida.
  2. Una parrilla tiene DOS CAPAS: las barras de una dirección se apoyan sobre las
     de la otra, de modo que la capa superior tiene un `d` menor.

Medido en un caso real: el motor usaba d = 422 mm mientras la capa superior real
tenía d = 410.9 mm. Las capacidades de esa dirección quedaban SOBREESTIMADAS un
2.7% y el candidato aun así se reportaba PASS. Es exactamente un falso PASS.

SOLUCIÓN ADOPTADA
=================
Se resuelve `d` por PUNTO FIJO antes de las verificaciones definitivas:

  1. Se parte de un `d` sembrado con el diámetro asumido.
  2. Se hace un diseño preliminar de flexión y se selecciona la barra real.
  3. Se recalcula el `d` de la CAPA SUPERIOR con los diámetros reales:
         d_superior = h − recubrimiento − db_inferior − db_superior/2
  4. Si cambió, se repite (máximo `MAX_ITERATIONS` pasadas).
  5. Si el diámetro no se estabiliza, se toma el MAYOR diámetro visto, que da el
     `d` más pequeño: siempre del lado conservador.

Se adopta el `d` de la capa superior para AMBAS direcciones. Es ligeramente
conservador para la capa inferior (por db, ~13-16 mm), y garantiza que ninguna
capacidad quede sobreestimada. La geometría real por capa se sigue reportando en
`FootingRebarGeometry` para que el ingeniero vea ambos valores.
"""

from __future__ import annotations

from engine.codes.base import IConcreteCode
from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import SoilProfile

MAX_ITERATIONS = 4
TOLERANCE_M = 1e-4


def upper_layer_depth(h_m: float, cover_m: float, db_bottom_m: float, db_top_m: float) -> float:
    """d de la capa superior de la parrilla: la más desfavorable de las dos."""
    return h_m - cover_m - db_bottom_m - db_top_m / 2.0


def resolve_effective_depth(
    h_m: float,
    cover_m: float,
    assumed_db_m: float,
    B_m: float,
    L_m: float,
    column: Column,
    soil: SoilProfile,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    load_case_set: LoadCaseSet,
    code: IConcreteCode,
    placement: "ColumnPlacement | None" = None,
) -> float:
    """Devuelve el `d` conservador (capa superior) con los diámetros que el diseño
    realmente selecciona. Importación diferida para evitar un ciclo de imports con
    depth_solver."""
    from engine.foundation.flexure import design_flexure, moment_at_critical_section
    from engine.reinforcement.rebar_selector import select_rebar
    from engine.domain.column_placement import concentric
    from engine.soil.eccentricity import compute_total_eccentricity

    # La estimación preliminar debe usar la MISMA geometría que el diseño real: si
    # aquí se supusiera la columna centrada, el diámetro estimado saldría de un
    # momento menor que el verdadero y el `d` resultante sería mayor que el real,
    # es decir del lado inseguro.
    if placement is None:
        placement = concentric(column)
    cants_x = placement.cantilevers_x(B_m)
    cants_y = placement.cantilevers_y(L_m)
    cant_x = max(cants_x)
    cant_y = max(cants_y)

    d = upper_layer_depth(h_m, cover_m, assumed_db_m, assumed_db_m)
    largest_db_seen = assumed_db_m

    for _ in range(MAX_ITERATIONS):
        if d <= 0:
            return d  # geometría degenerada; el llamador lo detectará

        # Diseño preliminar con el d actual, solo para conocer el diámetro real.
        mu_x = max(
            moment_at_critical_section(
                c.P_kN,
                abs(compute_total_eccentricity(
                    c.P_kN, 0.0, c.Mx_kNm, c.My_kNm, placement.offset_x_m, placement.offset_y_m
                ).ex_m),
                B_m, cant, True,
            )
            for c in load_case_set.factored
            for cant in cants_x
            if cant > 0
        )
        mu_y = max(
            moment_at_critical_section(
                c.P_kN,
                abs(compute_total_eccentricity(
                    c.P_kN, 0.0, c.Mx_kNm, c.My_kNm, placement.offset_x_m, placement.offset_y_m
                ).ey_m),
                L_m, cant, True,
            )
            for c in load_case_set.factored
            for cant in cants_y
            if cant > 0
        )
        fx = design_flexure(mu_x, L_m, h_m, d, cant_x, concrete.fc_MPa, steel.fy_MPa, steel.bar_type, code)
        fy = design_flexure(mu_y, B_m, h_m, d, cant_y, concrete.fc_MPa, steel.fy_MPa, steel.bar_type, code)
        bar_x = select_rebar(fx.As_design_m2, width_m=L_m, h_m=h_m)
        bar_y = select_rebar(fy.As_design_m2, width_m=B_m, h_m=h_m)

        db_x = bar_x.diameter_mm / 1000.0
        db_y = bar_y.diameter_mm / 1000.0
        largest_db_seen = max(largest_db_seen, db_x, db_y)

        d_new = upper_layer_depth(h_m, cover_m, db_x, db_y)
        if abs(d_new - d) <= TOLERANCE_M:
            return d_new
        d = d_new

    # No convergió: se adopta el mayor diámetro visto -> el d más pequeño posible.
    return upper_layer_depth(h_m, cover_m, largest_db_seen, largest_db_seen)
