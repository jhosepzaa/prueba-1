"""Excentricidad de la carga resultante sobre la base de la zapata.

CONVENCIÓN ADOPTADA — E.050 art. 28.1
=====================================
    ex = Mx / Q          ey = My / Q

    - La columna tiene dimensiones bx (a lo largo del eje X) y by (a lo largo de Y).
    - La zapata tiene dimensiones B (a lo largo de X) y L (a lo largo de Y).
    - **Mx** desplaza la resultante a lo largo de X -> se compara contra B.
    - **My** desplaza la resultante a lo largo de Y -> se compara contra L.

ATENCIÓN AL SIGNIFICADO DEL RÓTULO
==================================
`Mx` NO es "el momento alrededor del eje X". Es el momento que flexiona la zapata
EN la dirección X, que mecánicamente es el momento *alrededor del eje Y*. El
rótulo sigue a la norma, no al eje de giro. Es también la convención de la
bibliografía peruana: Aragón, «Concreto Armado 2» 3.4.1, titula su sección de
diseño *"Diseño por flexión Dir. X (Momentos alrededor de Y)"*.

HISTORIA — POR QUÉ ESTE ENCABEZADO ES TAN EXPLÍCITO
===================================================
Hasta la migración de convención, el motor usaba el rótulo OPUESTO (`Mx` = momento
alrededor del eje X, ex = My/P) y este mismo encabezado afirmaba —falsamente— que
"E.060 y E.050 usan Mx/My sin fijar una convención universal". E.050 art. 28.1 sí
la fija. La consecuencia era que quien tomara un Mx calculado según la norma y lo
escribiera en el campo `Mx` lo aplicaba al eje equivocado; en zapata cuadrada con
momentos iguales no se notaba. El error llegó a cometerse al transcribir el
ejercicio de Aragón para validación.

La migración fue puramente de ETIQUETA: se verificó contra el congelamiento
numérico de `tests/freeze/` que, ejecutando el motor nuevo con los momentos
intercambiados, TODOS los resultados físicos son idénticos a los previos. Ver el
informe completo en docs/convenciones_ejes.md y la guardia permanente en
tests/test_axis_convention_vs_e050.py.

Si el usuario define sus ejes de otra manera, este es el punto único del motor
donde corregirlo -- no está disperso en otros módulos.
"""

from __future__ import annotations

from pydantic import BaseModel


AXIS_CONVENTION_NOTE = (
    "Convención de momentos (E.050 art. 28.1): Mx es el momento que desplaza la "
    "resultante a lo largo del eje X — el que flexiona en la dirección de B — de modo "
    "que ex = Mx/P; My hace lo propio a lo largo de Y, ey = My/P. NO es «momento "
    "alrededor del eje X»: mecánicamente Mx es el momento alrededor del eje Y."
)


class Eccentricity(BaseModel):
    ex_m: float
    ey_m: float


def compute_total_eccentricity(
    P_column_kN: float,
    self_weight_kN: float,
    Mx_kNm: float,
    My_kNm: float,
    offset_x_m: float = 0.0,
    offset_y_m: float = 0.0,
) -> Eccentricity:
    """Excentricidad de la resultante respecto del CENTROIDE DE LA ZAPATA, cuando la
    columna puede estar descentrada (Fase 1B).

    ESTÁTICA (derivación, no cita normativa)
    ========================================
    Tomando momentos respecto del centroide de la zapata:

      - La carga de columna P actúa a distancia `offset` del centroide, de modo que
        aporta un momento P·offset ADEMÁS del momento aplicado M.
      - El peso propio y el relleno actúan SOBRE el propio centroide: aumentan la
        carga vertical pero no aportan momento.

            ex = (Mx + P_columna · offset_x) / (P_columna + W)

    Nótese la asimetría del cociente: en el numerador solo interviene la carga que
    está descentrada; en el denominador, toda la carga vertical. Confundirlas es el
    error fácil de este cálculo.

    Con offset = 0 la expresión se reduce a M/(P+W), que es exactamente el
    comportamiento anterior a la Fase 1B."""
    P_total = P_column_kN + self_weight_kN
    if P_total <= 0:
        raise ValueError(
            f"La carga vertical total debe ser positiva (compresión); recibido {P_total} kN "
            f"(columna {P_column_kN} + peso propio {self_weight_kN})."
        )
    return Eccentricity(
        ex_m=(Mx_kNm + P_column_kN * offset_x_m) / P_total,
        ey_m=(My_kNm + P_column_kN * offset_y_m) / P_total,
    )


def compute_eccentricity(P_kN: float, Mx_kNm: float, My_kNm: float) -> Eccentricity:
    if P_kN <= 0:
        raise ValueError(
            f"P_kN debe ser positivo (compresión) para calcular excentricidad; recibido {P_kN} kN. "
            "Una carga neta de tracción sobre la zapata no es un caso soportado por este modelo."
        )
    # E.050 art. 28.1: ex = Mx/Q, ey = My/Q.
    return Eccentricity(ex_m=Mx_kNm / P_kN, ey_m=My_kNm / P_kN)
