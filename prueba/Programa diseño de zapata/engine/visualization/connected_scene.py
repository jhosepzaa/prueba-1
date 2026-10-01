"""ConnectedSceneDTO — contrato entre el motor y la vista del sistema conectado (Fase 4G).

Misma regla que `scene_dto.py`: la visualización muestra datos ya calculados y NUNCA los
recalcula. Todas las posiciones se resuelven aquí, del lado del motor, a partir de las
huellas que el propio solver usó (`ConnectedFootingLayout.footprints`) y del resultado
de la estática. Este módulo no contiene ninguna ecuación de ingeniería.

SISTEMA DE COORDENADAS (metros), el MISMO del reparto del par:
    X  a lo largo de la viga (coordenada `s`), origen en el LINDERO, positivo hacia el
       interior
    Y  transversal, centrado en la línea de ejes de las dos columnas
    Z  vertical hacia arriba, origen en la base de las zapatas

Con la viga declarada sobre el eje Y del proyecto, X de la escena sigue siendo la
dirección de la viga: la escena se dibuja en el sistema local del problema, y las
dimensiones B y L se asignan con la misma regla que usa el solver.

LO QUE NO SE DIBUJA, Y SE DECLARA
=================================
- El armado: sus posiciones no se resuelven para el sistema conectado.
- La cota vertical de la viga respecto de las zapatas: el motor no la calcula. La viga se
  apoya en la base común por convención de dibujo, no por un dato de diseño.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.domain.connected_layout import ConnectedFootingLayout
from engine.optimization.connected_generator import ConnectedAlternative
from engine.reports.connected_report import alternative_label
from engine.results.status import CheckStatus
from engine.visualization.scene_dto import COLUMN_STUB_HEIGHT_M, BoxDTO, DimensionDTO, Vec3

CONNECTED_SCOPE_NOTE = (
    "Esquema del sistema conectado dibujado con las huellas y distancias que usó el "
    "cálculo. No representa el armado. La posición vertical de la viga respecto de las "
    "zapatas es una convención de dibujo: el motor no la calcula."
)


class ConnectedSceneDTO(BaseModel):
    """Todo lo necesario para dibujar el sistema. Nada más, nada calculable."""

    alternative_id: str
    status: CheckStatus = Field(..., description="Estado real. El visor no lo presenta como PASS.")
    status_label: str = Field(..., description="Rótulo del vocabulario cerrado, del motor")
    open_tbds: list[str] = Field(default_factory=list)
    longitudinal_axis: str

    exterior_footing: BoxDTO
    interior_footing: BoxDTO
    beam: BoxDTO
    exterior_column: BoxDTO
    interior_column: BoxDTO

    property_line_x_m: float = 0.0
    exterior_column_axis_x_m: float
    interior_column_axis_x_m: float
    free_span_start_x_m: float
    free_span_end_x_m: float
    system_length_m: float

    dimensions: list[DimensionDTO]
    scope_note: str = CONNECTED_SCOPE_NOTE


def _box(x0: float, x1: float, width: float, z0: float, height: float) -> BoxDTO:
    return BoxDTO(
        center=Vec3(x=(x0 + x1) / 2.0, y=0.0, z=z0 + height / 2.0),
        size=Vec3(x=x1 - x0, y=width, z=height),
    )


def build_connected_scene(
    layout: ConnectedFootingLayout, alternative: ConnectedAlternative
) -> ConnectedSceneDTO:
    """Ensambla la escena a partir de la geometría y del resultado ya calculados."""
    g = alternative.geometry
    fp = layout.footprints(
        g.exterior_B_m, g.exterior_L_m, g.exterior_h_m,
        g.interior_B_m, g.interior_L_m, g.interior_h_m,
    )
    fe, fi = fp.exterior, fp.interior
    eje_x = layout.longitudinal_axis == "X"

    def a_lo_largo(col) -> tuple[float, float]:
        """(dimensión a lo largo de la viga, dimensión transversal) de una columna."""
        return (col.bx_m, col.by_m) if eje_x else (col.by_m, col.bx_m)

    a = layout.exterior.anchor.axis_distance_to_column_center_m(layout.exterior.column)
    x_int = a + layout.axis_distance_m
    ce_s, ce_t = a_lo_largo(layout.exterior.column)
    ci_s, ci_t = a_lo_largo(layout.interior.column)

    def columna(x: float, s: float, t: float, h: float) -> BoxDTO:
        return BoxDTO(
            center=Vec3(x=x, y=0.0, z=h + COLUMN_STUB_HEIGHT_M / 2.0),
            size=Vec3(x=s, y=t, z=COLUMN_STUB_HEIGHT_M),
        )

    off = 0.40
    y_cota = -max(fe.width_m, fi.width_m) / 2.0 - off
    dims = [
        DimensionDTO(id="L1", label=f"zapata de lindero = {fe.length_m:.2f} m", plane="XY",
                     start=Vec3(x=fe.start_m, y=y_cota, z=0.0), end=Vec3(x=fe.end_m, y=y_cota, z=0.0)),
        DimensionDTO(id="S", label=f"entre ejes = {layout.axis_distance_m:.2f} m", plane="XY",
                     start=Vec3(x=a, y=y_cota - off, z=0.0), end=Vec3(x=x_int, y=y_cota - off, z=0.0)),
        DimensionDTO(id="vano", label=f"vano libre = {fi.start_m - fe.end_m:.2f} m", plane="XY",
                     start=Vec3(x=fe.end_m, y=y_cota, z=0.0), end=Vec3(x=fi.start_m, y=y_cota, z=0.0)),
        DimensionDTO(id="L2", label=f"zapata interior = {fi.length_m:.2f} m", plane="XY",
                     start=Vec3(x=fi.start_m, y=y_cota, z=0.0), end=Vec3(x=fi.end_m, y=y_cota, z=0.0)),
        DimensionDTO(id="B1", label=f"{fe.width_m:.2f} m", plane="XY",
                     start=Vec3(x=fe.start_m - off, y=-fe.width_m / 2, z=0.0),
                     end=Vec3(x=fe.start_m - off, y=fe.width_m / 2, z=0.0)),
        DimensionDTO(id="B2", label=f"{fi.width_m:.2f} m", plane="XY",
                     start=Vec3(x=fi.end_m + off, y=-fi.width_m / 2, z=0.0),
                     end=Vec3(x=fi.end_m + off, y=fi.width_m / 2, z=0.0)),
    ]

    return ConnectedSceneDTO(
        alternative_id=alternative.id,
        status=alternative.overall_status,
        status_label=alternative_label(alternative),
        open_tbds=list(alternative.open_tbds),
        longitudinal_axis=layout.longitudinal_axis,
        exterior_footing=_box(fe.start_m, fe.end_m, fe.width_m, 0.0, fe.h_m),
        interior_footing=_box(fi.start_m, fi.end_m, fi.width_m, 0.0, fi.h_m),
        beam=_box(fe.end_m, fi.start_m, layout.beam.b_m, 0.0, layout.beam.h_m),
        exterior_column=columna(a, ce_s, ce_t, fe.h_m),
        interior_column=columna(x_int, ci_s, ci_t, fi.h_m),
        exterior_column_axis_x_m=a,
        interior_column_axis_x_m=x_int,
        free_span_start_x_m=fe.end_m,
        free_span_end_x_m=fi.start_m,
        system_length_m=fi.end_m - fe.start_m,
        dimensions=dims,
    )
