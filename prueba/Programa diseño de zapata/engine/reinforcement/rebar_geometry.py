"""GEOMETRÍA REAL DE LAS BARRAS -- información que el motor no modelaba.

Diagnóstico que motiva este módulo (auditoría del armado):

  1. `d` se calculaba con un diámetro ASUMIDO (16 mm por defecto), no con la
     barra realmente seleccionada.
  2. Se usaba UN SOLO `d` para ambas direcciones, pero una parrilla tiene dos
     capas: las barras de una dirección se apoyan sobre las de la otra, de modo
     que d_capa_superior < d_capa_inferior en (db_inf + db_sup)/2.
     Medido en un caso real: 12.7 mm de diferencia, y el `d` del motor resultaba
     11.1 mm MAYOR que el real de la capa superior -> del lado INSEGURO.
  3. No existía longitud de barra, posición de extremos, ni longitud disponible
     para desarrollo.

Este módulo aporta esa geometría. Convención de capas adoptada (decisión de
ingeniería explícita, no normativa): **la capa inferior es la de la dirección
del lado LARGO de la zapata**, porque es la que recibe el mayor momento por
tener el voladizo más largo y conviene darle el mayor peralte efectivo. Para
zapata cuadrada la elección es indiferente y se toma X como capa inferior.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["X", "Y"]
LayerPosition = Literal["inferior", "superior"]


class BarLayerGeometry(BaseModel):
    direction: Direction
    layer: LayerPosition

    bar_diameter_m: float
    n_bars: int
    spacing_m: float

    # --- Peralte efectivo REAL de esta capa ---
    d_m: float = Field(..., description="Desde la fibra superior de concreto al centroide de ESTA capa")

    # --- Posición de las barras ---
    bottom_cover_m: float = Field(..., description="Recubrimiento libre bajo la capa inferior")
    depth_to_bar_center_from_bottom_m: float = Field(
        ..., description="Altura del centroide de la capa medida desde la cara inferior de la zapata"
    )
    side_cover_m: float = Field(..., description="Recubrimiento lateral en los extremos de la barra")

    # --- Longitud de la barra ---
    span_dimension_m: float = Field(..., description="Dimensión de la zapata que la barra recorre")
    bar_length_m: float = Field(..., description="Longitud recta = dimensión - 2*recubrimiento lateral")

    # --- Separaciones libres (necesarias para cb y para los factores de §12.2) ---
    clear_spacing_m: float = Field(..., description="Separación libre entre barras = s - db")

    # --- Sección crítica de flexión y longitud disponible para desarrollo ---
    cantilever_m: float = Field(
        ...,
        description=(
            "Voladizo libre de la cara de columna que gobierna el desarrollo: de esa cara al "
            "borde de la zapata. Con columna concéntrica, (dimensión − columna)/2."
        ),
    )
    available_development_length_m: float = Field(
        ...,
        description=(
            "Longitud recta disponible para desarrollar la barra A CADA LADO de la sección "
            "crítica (E.060 §15.6.2): el menor entre el tramo hacia el borde libre "
            "(voladizo − recubrimiento) y el tramo hacia el otro lado, a través de la "
            "columna (columna + voladizo opuesto − recubrimiento). Con columna concéntrica "
            "gobierna siempre el primero."
        ),
    )
    through_column_length_m: float | None = Field(
        default=None,
        description=(
            "Tramo hacia el lado opuesto a través de la columna, SOLO cuando es el que "
            "gobierna la longitud disponible (columna descentrada: p. ej. zapata de lindero). "
            "None si gobierna el tramo hacia el borde libre."
        ),
    )

    # --- Terminación ---
    has_hook: bool = Field(default=False, description="Nunca se asume: solo True si el usuario lo indica")
    hook_type: Literal["ninguno", "90", "180"] = Field(default="ninguno")


class FootingRebarGeometry(BaseModel):
    layer_x: BarLayerGeometry
    layer_y: BarLayerGeometry
    bottom_layer_direction: Direction
    d_used_by_engine_m: float = Field(..., description="El d único que usaron flexión/cortante/punzonamiento")
    d_discrepancy_note: str


# Un voladizo por debajo de esto es una cara de columna al ras del borde: no hay
# losa en voladizo, ni momento, ni sección crítica que desarrollar desde ella.
_SIN_VOLADIZO_M = 1e-9


GoverningFace = Literal["menor coordenada", "mayor coordenada"]


def development_length_available(
    cantilevers_m: tuple[float, float],
    column_dim_m: float,
    cover_m: float,
    governing_face: GoverningFace | None = None,
) -> tuple[float, float, float | None]:
    """Longitud recta disponible para desarrollar la barra, E.060 §15.6.2 y §15.6.3.

    §15.6.3 sitúa la sección crítica de desarrollo en los planos de §15.4.2, la CARA de
    la columna; §15.6.2 exige desarrollar la tracción «a cada lado de dicha sección».
    En la cara que se verifica hay, pues, dos tramos:

      - hacia el borde libre:          voladizo_i − recubrimiento
      - hacia el otro lado, a través de la columna:
                                       columna + voladizo_opuesto − recubrimiento

    y la barra dispone del MENOR de los dos. Gobierna la cara más desfavorable.

    Con la columna concéntrica los dos voladizos son iguales y el tramo a través de la
    columna es siempre el mayor: el resultado es voladizo − recubrimiento, exactamente
    lo que el motor calculaba antes. Solo cambia con la columna descentrada, y ahí
    importa: en la zapata de lindero el lado del lindero no tiene voladizo y la barra
    solo cuenta, hacia ese lado, con el ancho de la columna.

    QUÉ CARA SE VERIFICA (decisión del proyectista, 2026-09-28)
    ===========================================================
    La cara cuyo momento GOBIERNA el diseño de esa dirección (`governing_face`, la que
    `depth_solver` ya identifica al buscar el Mu mayor). Es la sección donde la barra
    trabaja a la tracción de diseño. La cara opuesta, con la columna descentrada, suele
    tener un voladizo corto y una tracción casi nula; exigirle la ld completa a fy la
    haría gobernar por un artificio (holgura de 0,15 m al lindero: 0,075 m disponibles).
    Es una hipótesis de modelación declarada, no un texto de la norma.

    Sin `governing_face` —por ejemplo, si ninguna combinación produjo momento— se
    verifica toda cara con voladizo, que es la lectura más estricta.

    Una cara al ras del borde (voladizo nulo) no es sección crítica: no tiene losa en
    voladizo que la flexione. Si NINGUNA cara tiene voladizo, se conserva el resultado
    anterior (cero disponible).

    Hipótesis de modelación que no cambia: la demanda es la ld completa de la barra a fy,
    sin reducirla por la tensión calculada en la sección.

    Devuelve (voladizo libre de la cara que gobierna, longitud disponible, tramo a través
    de la columna si es el que gobierna o None).
    """
    c_lo, c_hi = cantilevers_m
    todas = {"menor coordenada": (c_lo, c_hi), "mayor coordenada": (c_hi, c_lo)}
    candidatas = [todas[governing_face]] if governing_face in todas else list(todas.values())
    caras = [(c, otro) for c, otro in candidatas if c > _SIN_VOLADIZO_M]
    if not caras:
        c = min(c_lo, c_hi)
        return c, max(c - cover_m, 0.0), None

    mejor: tuple[float, float, float | None] | None = None
    for c, otro in caras:
        hacia_borde = max(c - cover_m, 0.0)
        a_traves = max(column_dim_m + otro - cover_m, 0.0)
        disponible = min(hacia_borde, a_traves)
        tramo = a_traves if a_traves < hacia_borde else None
        if mejor is None or disponible < mejor[1]:
            mejor = (c, disponible, tramo)
    return mejor


def build_rebar_geometry(
    B_m: float,
    L_m: float,
    h_m: float,
    bx_m: float,
    by_m: float,
    cover_m: float,
    db_x_m: float,
    db_y_m: float,
    n_bars_x: int,
    n_bars_y: int,
    spacing_x_m: float,
    spacing_y_m: float,
    d_used_by_engine_m: float,
    hook_x: Literal["ninguno", "90", "180"] = "ninguno",
    hook_y: Literal["ninguno", "90", "180"] = "ninguno",
    cantilevers_x_m: tuple[float, float] | None = None,
    cantilevers_y_m: tuple[float, float] | None = None,
    governing_face_x: GoverningFace | None = None,
    governing_face_y: GoverningFace | None = None,
) -> FootingRebarGeometry:
    """Construye la geometría real de ambas capas.

    Nomenclatura: las barras de la dirección X corren a lo largo de B y se
    reparten sobre el ancho L; las de la dirección Y corren a lo largo de L y se
    reparten sobre el ancho B.

    `cantilevers_x_m` / `cantilevers_y_m`: (voladizo del lado de menor coordenada,
    voladizo del lado de mayor coordenada), como los da `ColumnPlacement`. Sin ellos la
    columna se toma concéntrica, que era el único caso que este módulo contemplaba.
    `governing_face_x` / `governing_face_y`: la cara cuyo momento gobierna esa dirección
    (ver `development_length_available`).
    """
    # La capa inferior es la de la dirección del lado largo (ver docstring).
    bottom_direction: Direction = "X" if B_m >= L_m else "Y"

    if bottom_direction == "X":
        db_bottom, db_top = db_x_m, db_y_m
    else:
        db_bottom, db_top = db_y_m, db_x_m

    # Centroides medidos desde la cara inferior de la zapata:
    z_bottom_layer = cover_m + db_bottom / 2.0
    z_top_layer = cover_m + db_bottom + db_top / 2.0

    d_bottom = h_m - z_bottom_layer
    d_top = h_m - z_top_layer

    def _layer(
        direction: Direction, db: float, n: int, s: float, span: float,
        voladizos: tuple[float, float], columna: float, cara: GoverningFace | None,
    ) -> BarLayerGeometry:
        is_bottom = direction == bottom_direction
        cantilever, available, through = development_length_available(
            voladizos, columna, cover_m, cara
        )
        return BarLayerGeometry(
            direction=direction,
            layer="inferior" if is_bottom else "superior",
            bar_diameter_m=db,
            n_bars=n,
            spacing_m=s,
            d_m=d_bottom if is_bottom else d_top,
            bottom_cover_m=cover_m,
            depth_to_bar_center_from_bottom_m=z_bottom_layer if is_bottom else z_top_layer,
            side_cover_m=cover_m,
            span_dimension_m=span,
            bar_length_m=max(span - 2.0 * cover_m, 0.0),
            clear_spacing_m=max(s - db, 0.0),
            cantilever_m=cantilever,
            available_development_length_m=available,
            through_column_length_m=through,
            has_hook=(hook_x if direction == "X" else hook_y) != "ninguno",
            hook_type=hook_x if direction == "X" else hook_y,
        )

    concentrico_x = ((B_m - bx_m) / 2.0,) * 2
    concentrico_y = ((L_m - by_m) / 2.0,) * 2
    layer_x = _layer("X", db_x_m, n_bars_x, spacing_x_m, span=B_m,
                     voladizos=cantilevers_x_m or concentrico_x, columna=bx_m,
                     cara=governing_face_x)
    layer_y = _layer("Y", db_y_m, n_bars_y, spacing_y_m, span=L_m,
                     voladizos=cantilevers_y_m or concentrico_y, columna=by_m,
                     cara=governing_face_y)

    worst_real_d = min(layer_x.d_m, layer_y.d_m)
    delta_mm = (d_used_by_engine_m - worst_real_d) * 1000.0
    if delta_mm > 0.5:
        note = (
            f"El d usado en flexión/cortante/punzonamiento ({d_used_by_engine_m * 1000:.1f} mm) "
            f"es {delta_mm:.1f} mm MAYOR que el d real de la capa superior "
            f"({worst_real_d * 1000:.1f} mm): las capacidades de esa dirección están "
            f"SOBREESTIMADAS en aproximadamente {delta_mm / worst_real_d / 10:.1f}%."
        )
    elif delta_mm < -0.5:
        note = (
            f"El d usado ({d_used_by_engine_m * 1000:.1f} mm) es {-delta_mm:.1f} mm MENOR que el "
            f"d real más desfavorable ({worst_real_d * 1000:.1f} mm): resultado conservador."
        )
    else:
        note = "El d usado coincide con el d real de la capa más desfavorable."

    return FootingRebarGeometry(
        layer_x=layer_x,
        layer_y=layer_y,
        bottom_layer_direction=bottom_direction,
        d_used_by_engine_m=d_used_by_engine_m,
        d_discrepancy_note=note,
    )
