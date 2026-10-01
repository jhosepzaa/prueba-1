"""FootingSceneDTO — contrato ÚNICO entre el motor y la visualización.

Especificado en la arquitectura de Fase 1:
    "El motor produce un FootingSceneDTO (dimensiones, posición de columna,
     lista de barras con posición/diámetro/longitud, recubrimiento) — es el único
     contrato entre motor y visualización. El motor no sabe que existe three.js."

REGLA FUNDAMENTAL: la visualización muestra datos calculados, NUNCA los recalcula.
Por eso las POSICIONES de cada barra se resuelven aquí, del lado del motor, y no
en el visor. Este módulo no contiene ninguna ecuación de ingeniería: solo dispone
en el espacio valores que el motor ya decidió (n_bars, spacing_m, bar_diameter_m,
bar_length_m provienen íntegros de `FootingRebarGeometry`).

SISTEMA DE COORDENADAS (metros):
    X  a lo largo de B      Y  a lo largo de L      Z  vertical hacia arriba
    Origen en el CENTRO DE LA BASE de la zapata.
    Zapata:  x ∈ [-B/2, +B/2],  y ∈ [-L/2, +L/2],  z ∈ [0, h]
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.reinforcement.rebar_geometry import BarLayerGeometry, FootingRebarGeometry
from engine.results.status import CheckStatus

# Altura del tramo de columna que se dibuja emergiendo de la zapata. Es un valor
# puramente de PRESENTACIÓN (no estructural): la columna real continúa hacia
# arriba fuera del alcance de este modelo.
COLUMN_STUB_HEIGHT_M = 0.60


class Vec3(BaseModel):
    x: float
    y: float
    z: float


class BoxDTO(BaseModel):
    """Prisma recto definido por su centro y sus dimensiones."""

    center: Vec3
    size: Vec3


class BarDTO(BaseModel):
    """Una barra individual, con su posición y sus propiedades reales."""

    index: int
    direction: Literal["X", "Y"]
    layer: Literal["inferior", "superior"]
    diameter_m: float
    length_m: float
    start: Vec3
    end: Vec3
    has_hook: bool
    hook_type: str


class DimensionDTO(BaseModel):
    """Cota acotada entre dos puntos, con su etiqueta ya formateada."""

    id: str
    label: str
    start: Vec3
    end: Vec3
    plane: Literal["XY", "XZ", "YZ"]


class LayerSummaryDTO(BaseModel):
    """Resumen del armado de una dirección, tal como lo resolvió el motor."""

    direction: Literal["X", "Y"]
    layer: Literal["inferior", "superior"]
    bar_designation: str
    diameter_mm: float
    spacing_cm: float
    n_bars: int
    bar_length_m: float
    d_m: float
    label: str


class FootingSceneDTO(BaseModel):
    """Todo lo necesario para dibujar la zapata. Nada más, nada calculable."""

    alternative_id: str
    status: CheckStatus = Field(..., description="Estado real: el visor NUNCA debe presentarlo como PASS")

    # Geometría principal
    B_m: float
    L_m: float
    h_m: float
    d_m: float
    cover_m: float

    footing: BoxDTO
    column: BoxDTO
    column_bx_m: float
    column_by_m: float
    column_offset_x_m: float = 0.0
    column_offset_y_m: float = 0.0

    # Volumen delimitado por el recubrimiento (se dibuja como caja de alambre)
    cover_box: BoxDTO

    bars: list[BarDTO]
    layers: list[LayerSummaryDTO]
    dimensions: list[DimensionDTO]

    # Nota de alcance que el visor debe mostrar junto al modelo
    scope_note: str = (
        "Modelo de visualización. Las barras se dibujan rectas: los ganchos, dobleces y "
        "traslapes no se representan."
    )


def _bar_positions(n_bars: int, spacing_m: float, width_m: float) -> list[float]:
    """Coordenadas transversales de las barras, centradas en el ancho.

    Usa la separación REAL que decidió el motor y centra el grupo: la primera
    barra queda a −(n−1)·s/2 del eje y la última a +(n−1)·s/2. No se recalcula
    ninguna separación ni número de barras.
    """
    if n_bars <= 0:
        return []
    if n_bars == 1:
        return [0.0]
    spread = (n_bars - 1) * spacing_m
    # Si el grupo excediera el ancho disponible, se comprime proporcionalmente
    # para que el dibujo siga siendo legible; se trata solo de presentación y el
    # resumen por capa conserva siempre los valores reales del motor.
    usable = width_m
    if spread > usable > 0:
        spacing_m = usable / (n_bars - 1)
        spread = usable
    start = -spread / 2.0
    return [start + i * spacing_m for i in range(n_bars)]


def _bars_for_layer(layer: BarLayerGeometry, B_m: float, L_m: float) -> list[BarDTO]:
    z = layer.depth_to_bar_center_from_bottom_m
    half_length = layer.bar_length_m / 2.0

    if layer.direction == "X":
        # Corren a lo largo de X, repartidas sobre el ancho L.
        transverse = _bar_positions(layer.n_bars, layer.spacing_m, L_m - 2 * layer.side_cover_m)
        return [
            BarDTO(
                index=i, direction="X", layer=layer.layer,
                diameter_m=layer.bar_diameter_m, length_m=layer.bar_length_m,
                start=Vec3(x=-half_length, y=t, z=z),
                end=Vec3(x=half_length, y=t, z=z),
                has_hook=layer.has_hook, hook_type=layer.hook_type,
            )
            for i, t in enumerate(transverse)
        ]

    # Dirección Y: corren a lo largo de Y, repartidas sobre el ancho B.
    transverse = _bar_positions(layer.n_bars, layer.spacing_m, B_m - 2 * layer.side_cover_m)
    return [
        BarDTO(
            index=i, direction="Y", layer=layer.layer,
            diameter_m=layer.bar_diameter_m, length_m=layer.bar_length_m,
            start=Vec3(x=t, y=-half_length, z=z),
            end=Vec3(x=t, y=half_length, z=z),
            has_hook=layer.has_hook, hook_type=layer.hook_type,
        )
        for i, t in enumerate(transverse)
    ]


def _layer_summary(
    layer: BarLayerGeometry, designation: str, label: str
) -> LayerSummaryDTO:
    return LayerSummaryDTO(
        direction=layer.direction,
        layer=layer.layer,
        bar_designation=designation,
        diameter_mm=layer.bar_diameter_m * 1000.0,
        spacing_cm=layer.spacing_m * 100.0,
        n_bars=layer.n_bars,
        bar_length_m=layer.bar_length_m,
        d_m=layer.d_m,
        label=label,
    )


def _dimensions(B_m: float, L_m: float, h_m: float, bx_m: float, by_m: float) -> list[DimensionDTO]:
    offset = 0.30
    return [
        DimensionDTO(
            id="B", label=f"B = {B_m:.2f} m", plane="XY",
            start=Vec3(x=-B_m / 2, y=-L_m / 2 - offset, z=0.0),
            end=Vec3(x=B_m / 2, y=-L_m / 2 - offset, z=0.0),
        ),
        DimensionDTO(
            id="L", label=f"L = {L_m:.2f} m", plane="XY",
            start=Vec3(x=-B_m / 2 - offset, y=-L_m / 2, z=0.0),
            end=Vec3(x=-B_m / 2 - offset, y=L_m / 2, z=0.0),
        ),
        DimensionDTO(
            id="h", label=f"h = {h_m:.2f} m", plane="XZ",
            start=Vec3(x=B_m / 2 + offset, y=-L_m / 2, z=0.0),
            end=Vec3(x=B_m / 2 + offset, y=-L_m / 2, z=h_m),
        ),
        DimensionDTO(
            id="col_bx", label=f"bx = {bx_m:.2f} m", plane="XY",
            start=Vec3(x=-bx_m / 2, y=by_m / 2 + 0.10, z=h_m),
            end=Vec3(x=bx_m / 2, y=by_m / 2 + 0.10, z=h_m),
        ),
        DimensionDTO(
            id="col_by", label=f"by = {by_m:.2f} m", plane="XY",
            start=Vec3(x=bx_m / 2 + 0.10, y=-by_m / 2, z=h_m),
            end=Vec3(x=bx_m / 2 + 0.10, y=by_m / 2, z=h_m),
        ),
    ]


def build_footing_scene(
    alternative_id: str,
    status: CheckStatus,
    B_m: float,
    L_m: float,
    h_m: float,
    d_m: float,
    cover_m: float,
    column_bx_m: float,
    column_by_m: float,
    rebar_geometry: FootingRebarGeometry,
    designation_x: str,
    designation_y: str,
    label_x: str,
    label_y: str,
    # Con valor por defecto: una escena de columna concéntrica no cambia de firma.
    column_offset_x_m: float = 0.0,
    column_offset_y_m: float = 0.0,
) -> FootingSceneDTO:
    """Ensambla la escena a partir de resultados YA calculados por el motor."""
    lx, ly = rebar_geometry.layer_x, rebar_geometry.layer_y

    return FootingSceneDTO(
        alternative_id=alternative_id,
        status=status,
        B_m=B_m, L_m=L_m, h_m=h_m, d_m=d_m, cover_m=cover_m,
        footing=BoxDTO(
            center=Vec3(x=0.0, y=0.0, z=h_m / 2.0),
            size=Vec3(x=B_m, y=L_m, z=h_m),
        ),
        # La columna se dibuja DONDE ESTÁ. Con la Fase 1B puede no coincidir con el
        # centroide de la zapata, y una vista que la centrara siempre mostraría una
        # geometría distinta de la que se calculó.
        column=BoxDTO(
            center=Vec3(
                x=column_offset_x_m,
                y=column_offset_y_m,
                z=h_m + COLUMN_STUB_HEIGHT_M / 2.0,
            ),
            size=Vec3(x=column_bx_m, y=column_by_m, z=COLUMN_STUB_HEIGHT_M),
        ),
        column_bx_m=column_bx_m,
        column_by_m=column_by_m,
        column_offset_x_m=column_offset_x_m,
        column_offset_y_m=column_offset_y_m,
        cover_box=BoxDTO(
            center=Vec3(x=0.0, y=0.0, z=h_m / 2.0),
            size=Vec3(x=B_m - 2 * cover_m, y=L_m - 2 * cover_m, z=h_m - 2 * cover_m),
        ),
        bars=_bars_for_layer(lx, B_m, L_m) + _bars_for_layer(ly, B_m, L_m),
        layers=[
            _layer_summary(lx, designation_x, label_x),
            _layer_summary(ly, designation_y, label_y),
        ],
        dimensions=_dimensions(B_m, L_m, h_m, column_bx_m, column_by_m),
    )
