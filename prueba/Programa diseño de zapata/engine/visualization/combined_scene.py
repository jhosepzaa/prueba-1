"""CombinedSceneDTO — contrato entre el motor y el esquema de la zapata combinada.

Misma regla que `scene_dto.py` y `connected_scene.py`: la visualización muestra datos ya
calculados y **nunca** los recalcula. Todas las posiciones se resuelven aquí, del lado del
motor, a partir de la geometría que el propio solver usó. Este módulo **no contiene
ninguna ecuación de ingeniería**: coloca en el espacio valores que el motor ya decidió.

SISTEMA DE COORDENADAS (metros) — el mismo de `scene_dto.py`:
    X  a lo largo de B      Y  a lo largo de L      Z  vertical hacia arriba
    Origen en el CENTRO DE LA BASE de la zapata, que es el origen de los
    `ColumnPlacement.offset_x_m / offset_y_m` del layout.

Es el sistema local de la zapata, no el del proyecto: la dirección longitudinal —aquella
en la que se separan las columnas— viaja en el DTO (`longitudinal_direction`) para que el
visor pueda rotular la planta sin deducirla.

LO QUE NO SE DIBUJA, Y SE DECLARA
=================================
- El armado. El motor resuelve las posiciones de barra de la zapata aislada
  (`FootingRebarGeometry`), no las de la combinada.
- El relleno sobre la zapata y la profundidad de cimentación: el alzado se dibuja desde la
  base de la zapata, no desde el nivel de terreno.
- El tramo de columna que emerge es de presentación (`COLUMN_STUB_HEIGHT_M`), no un dato
  estructural.

ESTADO
======
El estado real de la alternativa viaja con la escena. Desde la decisión 6 la combinada
acepta con criterio NO_FAIL, de modo que una alternativa dibujada puede estar NO
VERIFICADA: un esquema limpio no puede leerse como un diseño conforme.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.domain.combined_layout import CombinedFootingLayout
from engine.optimization.combined_generator import CombinedAlternative
from engine.results.status import CheckStatus
from engine.results.vocabulary import status_label
from engine.visualization.scene_dto import COLUMN_STUB_HEIGHT_M, BoxDTO, DimensionDTO, Vec3

COMBINED_SCOPE_NOTE = (
    "Esquema de la zapata combinada dibujado con la geometría que usó el cálculo: huella, "
    "peralte y posición de cada columna. No representa el armado ni el relleno sobre la "
    "zapata, y el tramo de columna que emerge es una convención de dibujo."
)

STATUS_NOTE_NOT_COMPLIANT = (
    "Esta alternativa NO puede presentarse como conforme: sobrevive al barrido porque "
    "ninguna verificación implementada la descarta (criterio NO_FAIL), no porque cumpla."
)


class ColumnMarkDTO(BaseModel):
    """Eje de una columna sobre la planta, ya situado."""

    label: str
    x_m: float
    y_m: float
    box: BoxDTO


class CombinedSceneDTO(BaseModel):
    """Todo lo necesario para dibujar la zapata combinada. Nada más, nada calculable."""

    alternative_id: str
    status: CheckStatus = Field(..., description="Estado real. El visor no lo presenta como PASS.")
    status_label: str = Field(
        default="", description="Rótulo del vocabulario único (pendiente 8)"
    )
    status_note: str = Field(
        default="",
        description="Vacío si la alternativa es PASS o INFO; si no, por qué no es conforme.",
    )
    longitudinal_direction: str = Field(..., description='"X" o "Y": en la que se separan las columnas')

    B_m: float
    L_m: float
    h_m: float
    footing: BoxDTO
    columns: list[ColumnMarkDTO]

    dimensions: list[DimensionDTO]
    scope_note: str = COMBINED_SCOPE_NOTE


def build_combined_scene(
    layout: CombinedFootingLayout, alternative: CombinedAlternative
) -> CombinedSceneDTO:
    """Ensambla la escena a partir de la geometría y del resultado ya calculados."""
    r = alternative.result
    B, L, h = r.B_m, r.L_m, r.h_m
    eje = r.longitudinal_direction
    largo = B if eje == "X" else L

    columnas = [
        ColumnMarkDTO(
            label=col.label,
            x_m=col.offset_x_m,
            y_m=col.offset_y_m,
            box=BoxDTO(
                center=Vec3(x=col.offset_x_m, y=col.offset_y_m, z=h + COLUMN_STUB_HEIGHT_M / 2.0),
                size=Vec3(
                    x=col.placement.column.bx_m,
                    y=col.placement.column.by_m,
                    z=COLUMN_STUB_HEIGHT_M,
                ),
            ),
        )
        for col in layout.columns
    ]

    # Posición de cada columna medida desde el extremo inicial de la dirección
    # longitudinal, que es como se parametriza la búsqueda (distancia al lindero).
    def s(col: ColumnMarkDTO) -> float:
        return (col.x_m if eje == "X" else col.y_m) + largo / 2.0

    ordenadas = sorted(columnas, key=s)
    off = 0.40
    y_cota = -L / 2.0 - off
    x_cota = -B / 2.0 - off

    dims = [
        DimensionDTO(id="B", label=f"B = {B:.2f} m", plane="XY",
                     start=Vec3(x=-B / 2, y=y_cota, z=0.0), end=Vec3(x=B / 2, y=y_cota, z=0.0)),
        DimensionDTO(id="L", label=f"L = {L:.2f} m", plane="XY",
                     start=Vec3(x=x_cota, y=-L / 2, z=0.0), end=Vec3(x=x_cota, y=L / 2, z=0.0)),
    ]

    # Voladizos y separaciones entre ejes, a lo largo de la dirección longitudinal.
    def cota_long(id_: str, etiqueta: str, s0: float, s1: float, fila: float) -> DimensionDTO:
        a, b = s0 - largo / 2.0, s1 - largo / 2.0
        if eje == "X":
            return DimensionDTO(id=id_, label=etiqueta, plane="XY",
                                start=Vec3(x=a, y=fila, z=0.0), end=Vec3(x=b, y=fila, z=0.0))
        return DimensionDTO(id=id_, label=etiqueta, plane="XY",
                            start=Vec3(x=fila, y=a, z=0.0), end=Vec3(x=fila, y=b, z=0.0))

    fila = (y_cota - off) if eje == "X" else (x_cota - off)
    primera, ultima = s(ordenadas[0]), s(ordenadas[-1])
    dims.append(cota_long("voladizo_inicial", f"{primera:.2f} m al eje de {ordenadas[0].label}",
                          0.0, primera, fila))
    for a, b in zip(ordenadas, ordenadas[1:]):
        dims.append(cota_long(f"entre_{a.label}_{b.label}",
                              f"{s(b) - s(a):.2f} m entre ejes", s(a), s(b), fila))
    dims.append(cota_long("voladizo_final", f"{largo - ultima:.2f} m al extremo",
                          ultima, largo, fila))

    return CombinedSceneDTO(
        alternative_id=alternative.id,
        status=r.overall_status,
        status_label=status_label(r.overall_status),
        status_note=(
            "" if r.overall_status in (CheckStatus.PASS, CheckStatus.INFO)
            else STATUS_NOTE_NOT_COMPLIANT
        ),
        longitudinal_direction=eje,
        B_m=B, L_m=L, h_m=h,
        footing=BoxDTO(center=Vec3(x=0.0, y=0.0, z=h / 2.0), size=Vec3(x=B, y=L, z=h)),
        columns=columnas,
        dimensions=dims,
    )
