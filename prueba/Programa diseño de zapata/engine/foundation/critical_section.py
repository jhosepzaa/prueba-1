"""Geometría de la sección crítica de punzonamiento — Fase 1C.

Este módulo es GEOMETRÍA PURA. No contiene ninguna ecuación de E.060: entrega las
propiedades de sección (perímetro, área encerrada, centroide, Jc) que las
ecuaciones normativas necesitan. La separación es deliberada — las propiedades de
sección son derivaciones mecánicas y deben poder auditarse sin mezclarlas con las
citas normativas, que viven en `punching_shear.py`.

BASE NORMATIVA DE LA UBICACIÓN (la única que hay)
=================================================
E.060 §11.12.1.2, verbatim:

  "La superficie crítica equivalente que deberá investigarse estará localizada de
   modo que su perímetro, bo, sea MÍNIMO, pero no necesita estar más cerca de d/2
   desde: (a) los bordes o las esquinas de las columnas, cargas concentradas, o
   áreas de reacción [...]"
  "Para columnas cuadradas o rectangulares [...] se permite utilizar secciones
   críticas equivalentes con cuatro lados rectos."

Dos lecturas importan aquí:

  1. La sección se sitúa a d/2 de las caras de la columna, y la norma exige tomar
     la de PERÍMETRO MÍNIMO. Cuando el borde de la zapata queda más cerca que d/2,
     la sección se recorta contra ese borde: el perímetro resultante es menor, de
     modo que es la que la norma manda investigar. **El truncamiento es exigencia
     normativa, no una elección de este motor.**
  2. "Cuatro lados RECTOS" se refiere a la FORMA de los lados (rectos en vez de
     seguir el redondeo de esquinas), no a que la sección deba cerrarse por los
     cuatro. Leerlo como lo segundo obligaría a contar como resistente una cara
     situada en el borde libre de la zapata, donde no hay concreto que resista.

QUÉ LADO CUENTA Y CUÁL NO — DERIVACIÓN
======================================
La sección crítica es una superficie VERTICAL de altura d. Un lado solo transmite
cortante si hay concreto a ambas caras. Un lado que cae sobre el borde de la
zapata es una superficie libre: no hay concreto más allá, luego no resiste y **no
cuenta en bo**. Los lados perpendiculares a ese borde sí existen, pero acortados:
llegan solo hasta el borde.

De ahí salen los tres casos, sin necesidad de tratarlos por separado:

    0 lados recortados -> sección cerrada de 4 lados   (columna interior)
    1 lado  recortado  -> sección abierta de 3 lados   (columna de borde)
    2 lados recortados -> sección abierta de 2 lados   (columna de esquina)

DISCONTINUIDAD EN holgura = d/2 — ES FÍSICA, NO UN ARTEFACTO
============================================================
Al pasar la holgura de d/2 a un valor infinitesimalmente menor, bo cae de golpe
en la longitud del lado que deja de contar. No es un defecto del modelo: es la
misma discontinuidad que separa las fórmulas clásicas de columna interior y de
borde. Por debajo de d/2 el lado ya no está rodeado de concreto y deja de
resistir; no hay transición gradual posible.

CONVENCIÓN DE COORDENADAS
=========================
Origen en el CENTROIDE DE LA ZAPATA. La zapata ocupa x ∈ [-B/2, B/2],
y ∈ [-L/2, L/2]. La columna está centrada en (offset_x, offset_y). Misma
convención de ejes que el resto del motor (E.050 art. 28.1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Tolerancia geométrica. Un lado cuya holgura sea EXACTAMENTE d/2 cuenta: la norma
# dice "no necesita estar más cerca de d/2", de modo que d/2 es admisible.
GEOM_TOL_M = 1e-12

ColumnPosition = Literal["interior", "borde", "esquina", "degenerada"]

# --- Clasificación de la columna: INTERPRETACIÓN DECLARADA -------------------
# E.060 §11.12.2.1(b) fija alpha_s = 40 / 30 / 20 para columna "interior", "de
# borde" y "en esquina", pero NO DEFINE qué convierte a una columna en cada cosa.
# Se adopta el criterio GEOMÉTRICO: la clasificación la da el número de lados de la
# sección crítica que quedan recortados contra el borde de la zapata.
#
# Razón: alpha_s aparece en la ec. 11-42 multiplicando d/bo, es decir en la misma
# expresión que el perímetro. Que ambos respondan a la misma geometría es la
# lectura coherente. La alternativa —clasificar por la posición de la columna en el
# pórtico, con independencia de la zapata— dejaría alpha_s y bo describiendo
# geometrías distintas dentro de una misma ecuación.
#
# Es una INTERPRETACIÓN, declarada como tal igual que la de §15.7. Si se dispusiera
# de una definición normativa explícita, mandaría ella.
ALPHA_S_CLASSIFICATION_NOTE = (
    "E.060 §11.12.2.1(b) da los valores de alpha_s (40 interior / 30 borde / 20 esquina) "
    "pero NO define qué hace que una columna sea de borde o de esquina. Este motor lo "
    "clasifica por el número de lados de la sección crítica recortados contra el borde de "
    "la zapata (0 / 1 / 2). Es una INTERPRETACIÓN declarada, no una cita: alpha_s aparece "
    "en la ec. 11-42 junto a bo, y hacer que ambos respondan a la misma geometría es la "
    "lectura coherente."
)


class CriticalFace(BaseModel):
    """Una cara de la sección crítica que SÍ transmite cortante."""

    axis: Literal["x", "y"] = Field(
        ..., description='"x" si la cara es perpendicular al eje X (su normal es X)'
    )
    at_low_edge: bool = Field(..., description="True si está del lado de menor coordenada")
    position_m: float = Field(..., description="Coordenada de la cara sobre su eje normal")
    length_m: float = Field(..., description="Longitud de la cara en planta")


class AxisProperties(BaseModel):
    """Propiedades de la sección crítica respecto de UN eje de flexión.

    `axis="x"` describe la flexión EN la dirección X, la que produce Mx según la
    convención de E.050 art. 28.1."""

    axis: Literal["x", "y"]
    b1_m: float = Field(..., description="Dimensión de la sección crítica EN la dirección del momento (ec. 13-1)")
    b2_m: float = Field(..., description="Dimensión perpendicular")
    centroid_m: float = Field(..., description="Centroide de las caras resistentes sobre este eje")
    c_low_m: float = Field(..., description="Distancia del centroide a la cara de menor coordenada")
    c_high_m: float = Field(..., description="Distancia del centroide a la cara de mayor coordenada")
    Jc_m4: float = Field(..., description="Propiedad de sección análoga al momento polar de inercia")
    is_symmetric: bool = Field(..., description="True si c_low == c_high (sección cerrada)")

    @property
    def c_max_m(self) -> float:
        """La distancia mayor: es la que produce el esfuerzo máximo, y en una
        sección truncada NO es b1/2."""
        return max(self.c_low_m, self.c_high_m)


class CriticalSection(BaseModel):
    """Sección crítica de punzonamiento, cerrada o truncada."""

    x_lo_m: float
    x_hi_m: float
    y_lo_m: float
    y_hi_m: float

    faces: list[CriticalFace]
    n_truncated_sides: int
    position: ColumnPosition

    bo_m: float = Field(..., description="Perímetro resistente: suma de las caras que cuentan")
    enclosed_area_m2: float = Field(..., description="Área en planta encerrada por la sección")
    enclosed_centroid_x_m: float = Field(..., description="Centroide del ÁREA encerrada (para la descarga del suelo)")
    enclosed_centroid_y_m: float

    axis_x: AxisProperties
    axis_y: AxisProperties

    geometry_note: str

    @property
    def is_closed(self) -> bool:
        return self.n_truncated_sides == 0


def _axis_properties(
    axis: Literal["x", "y"],
    lo: float,
    hi: float,
    lo_counts: bool,
    hi_counts: bool,
    perp_lo: float,
    perp_hi: float,
    perp_lo_counts: bool,
    perp_hi_counts: bool,
    d_m: float,
) -> AxisProperties:
    """Propiedades respecto del eje de flexión indicado.

    DERIVACIÓN DEL CENTROIDE
    ========================
    El centroide se toma sobre las CARAS RESISTENTES, ponderadas por su área
    (longitud x d). Como todas tienen el mismo espesor d, el peso es su longitud.

      - Caras PARALELAS al eje de flexión (las que se extienden de `lo` a `hi`):
        su centroide sobre este eje es el punto medio (lo+hi)/2.
      - Caras PERPENDICULARES (situadas en `lo` o en `hi`): su centroide es su
        propia posición.

    En una sección cerrada la simetría devuelve el punto medio. En una truncada el
    centroide SE DESPLAZA hacia el lado cerrado, y por eso c_low != c_high.

    DERIVACIÓN DE Jc
    ================
    E.060 §11.12.7.2 exige que el esfuerzo "varíe linealmente alrededor del
    centroide", pero NO da la expresión de Jc para ninguna geometría. Se deriva
    como propiedad de sección, sumando sobre las caras resistentes:

      - Cara PARALELA al eje (longitud Lp, espesor d), a distancia e de su propio
        centroide al centroide de la sección:
            d*Lp^3/12  +  Lp*d^3/12  +  Lp*d*e^2
        Los dos primeros términos son sus momentos propios en planta y en espesor;
        el tercero es el traslado de Steiner, que en una sección cerrada se anula.
      - Cara PERPENDICULAR al eje (longitud Lq), a distancia e del centroide:
            Lq*d*e^2
        No tiene extensión propia sobre este eje, luego solo aporta el traslado.

    Con sección cerrada y simétrica esto se reduce EXACTAMENTE a la expresión
    clásica de columna interior:
        Jc = d*b1^3/6 + b1*d^3/6 + d*b2*b1^2/2
    lo que sirve de comprobación de la derivación (ver los tests de degeneración).
    """
    b1 = hi - lo
    b2 = perp_hi - perp_lo
    mid = (lo + hi) / 2.0

    # Longitud de las caras paralelas al eje de flexión: son las perpendiculares al
    # OTRO eje, y su longitud es b1. Cuentan las que no estén recortadas.
    n_parallel = int(perp_lo_counts) + int(perp_hi_counts)
    # Caras perpendiculares a este eje: longitud b2, situadas en lo y en hi.
    perp_faces = [(lo, lo_counts), (hi, hi_counts)]

    total_len = n_parallel * b1 + sum(b2 for _, counts in perp_faces if counts)
    if total_len <= 0:
        # Ninguna cara resiste: geometría degenerada. El llamador lo detecta por bo.
        return AxisProperties(
            axis=axis, b1_m=b1, b2_m=b2, centroid_m=mid,
            c_low_m=0.0, c_high_m=0.0, Jc_m4=0.0, is_symmetric=True,
        )

    momento = n_parallel * b1 * mid + sum(b2 * pos for pos, counts in perp_faces if counts)
    centroid = momento / total_len

    Jc = 0.0
    # Caras paralelas al eje de flexión
    if n_parallel:
        e = mid - centroid
        Jc += n_parallel * (d_m * b1**3 / 12.0 + b1 * d_m**3 / 12.0 + b1 * d_m * e**2)
    # Caras perpendiculares
    for pos, counts in perp_faces:
        if counts:
            Jc += b2 * d_m * (pos - centroid) ** 2

    c_low = centroid - lo
    c_high = hi - centroid
    return AxisProperties(
        axis=axis, b1_m=b1, b2_m=b2, centroid_m=centroid,
        c_low_m=c_low, c_high_m=c_high, Jc_m4=Jc,
        is_symmetric=abs(c_low - c_high) <= GEOM_TOL_M,
    )


def build_critical_section(
    B_m: float,
    L_m: float,
    bx_m: float,
    by_m: float,
    d_m: float,
    offset_x_m: float = 0.0,
    offset_y_m: float = 0.0,
) -> CriticalSection:
    """Construye la sección crítica a d/2 de las caras de la columna, recortada
    contra los bordes de la zapata donde corresponda (E.060 §11.12.1.2).

    Coordenadas con origen en el centroide de la ZAPATA."""
    half_d = d_m / 2.0
    fx_lo, fx_hi = offset_x_m - bx_m / 2.0, offset_x_m + bx_m / 2.0  # caras de la columna
    fy_lo, fy_hi = offset_y_m - by_m / 2.0, offset_y_m + by_m / 2.0

    edge_x_lo, edge_x_hi = -B_m / 2.0, B_m / 2.0
    edge_y_lo, edge_y_hi = -L_m / 2.0, L_m / 2.0

    # Posición ideal (sin recortar) y posición efectiva (recortada contra el borde).
    ideal = {
        ("x", True): fx_lo - half_d, ("x", False): fx_hi + half_d,
        ("y", True): fy_lo - half_d, ("y", False): fy_hi + half_d,
    }
    limite = {
        ("x", True): edge_x_lo, ("x", False): edge_x_hi,
        ("y", True): edge_y_lo, ("y", False): edge_y_hi,
    }

    efectiva: dict[tuple[str, bool], float] = {}
    cuenta: dict[tuple[str, bool], bool] = {}
    for clave, ideal_pos in ideal.items():
        lim = limite[clave]
        es_lado_bajo = clave[1]
        recortado = (ideal_pos < lim - GEOM_TOL_M) if es_lado_bajo else (ideal_pos > lim + GEOM_TOL_M)
        efectiva[clave] = lim if recortado else ideal_pos
        # Una cara sobre el borde de la zapata es superficie libre: no resiste.
        cuenta[clave] = not recortado

    x_lo, x_hi = efectiva[("x", True)], efectiva[("x", False)]
    y_lo, y_hi = efectiva[("y", True)], efectiva[("y", False)]

    faces: list[CriticalFace] = []
    if cuenta[("x", True)]:
        faces.append(CriticalFace(axis="x", at_low_edge=True, position_m=x_lo, length_m=y_hi - y_lo))
    if cuenta[("x", False)]:
        faces.append(CriticalFace(axis="x", at_low_edge=False, position_m=x_hi, length_m=y_hi - y_lo))
    if cuenta[("y", True)]:
        faces.append(CriticalFace(axis="y", at_low_edge=True, position_m=y_lo, length_m=x_hi - x_lo))
    if cuenta[("y", False)]:
        faces.append(CriticalFace(axis="y", at_low_edge=False, position_m=y_hi, length_m=x_hi - x_lo))

    n_truncated = sum(1 for v in cuenta.values() if not v)
    # E.060 §11.12.2.1(b) solo clasifica columnas interiores, de borde y de esquina,
    # es decir 0, 1 o 2 lados recortados. Con 3 o 4 no hay categoría normativa ni,
    # por tanto, alpha_s aplicable. Se marca "degenerada" en vez de asignarle uno:
    # inventar el valor sería inventar normativa. Geométricamente es una zapata
    # apenas mayor que la columna, que ningún modelo de punzonamiento describe.
    position: ColumnPosition = (
        "interior" if n_truncated == 0
        else "borde" if n_truncated == 1
        else "esquina" if n_truncated == 2
        else "degenerada"
    )

    bo = sum(f.length_m for f in faces)

    ax = _axis_properties(
        "x", x_lo, x_hi, cuenta[("x", True)], cuenta[("x", False)],
        y_lo, y_hi, cuenta[("y", True)], cuenta[("y", False)], d_m,
    )
    ay = _axis_properties(
        "y", y_lo, y_hi, cuenta[("y", True)], cuenta[("y", False)],
        x_lo, x_hi, cuenta[("x", True)], cuenta[("x", False)], d_m,
    )

    recortados = [
        etiqueta
        for clave, etiqueta in (
            (("x", True), "x−"), (("x", False), "x+"), (("y", True), "y−"), (("y", False), "y+"),
        )
        if not cuenta[clave]
    ]
    nota = (
        f"Sección crítica de {len(faces)} lado(s), columna clasificada «{position}». "
        f"x ∈ [{x_lo:.4f}, {x_hi:.4f}], y ∈ [{y_lo:.4f}, {y_hi:.4f}] m respecto del centroide "
        f"de la zapata. "
        + (
            f"Lados recortados contra el borde (no resisten): {', '.join(recortados)}."
            if recortados
            else "Ningún lado recortado: la sección se cierra por los cuatro lados."
        )
    )

    return CriticalSection(
        x_lo_m=x_lo, x_hi_m=x_hi, y_lo_m=y_lo, y_hi_m=y_hi,
        faces=faces, n_truncated_sides=n_truncated, position=position,
        bo_m=bo,
        enclosed_area_m2=(x_hi - x_lo) * (y_hi - y_lo),
        enclosed_centroid_x_m=(x_lo + x_hi) / 2.0,
        enclosed_centroid_y_m=(y_lo + y_hi) / 2.0,
        axis_x=ax, axis_y=ay,
        geometry_note=nota,
    )
