"""¿La mejor alternativa está contra el borde del rango explorado? (2026-09-24)

POR QUÉ EXISTE
El barrido solo puede elegir entre lo que miró. Cuando la geometría recomendada cae
justo en el límite del rango —el máximo de B, de L o del peralte—, lo más probable es
que fuera del rango haya algo mejor, y el programa no tiene forma de saberlo. Hasta
ahora eso se entregaba en silencio: la alternativa se presentaba como la mejor sin
decir que el borde estaba pegado a ella.

Se midió el efecto con una columna muy excéntrica (P = 600 kN, M = 900 kN·m): con el
rango estimado automáticamente la mejor propuesta era de 18,39 m³, y ampliando el rango
a mano aparecía una de 12,56 m³ —un 32 % menos— justo al otro lado del límite.

QUÉ ES Y QUÉ NO ES
Esto NO cambia ningún resultado: no descarta, no acepta y no altera un solo número. Solo
mira dónde quedó la solución dentro de la ventana explorada y lo dice. Es la misma idea
que ya aplica el barrido de la conectada al declararse truncado.

El límite INFERIOR también se informa: si la mejor alternativa es la más pequeña que se
miró, puede haber una más económica por debajo.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DimensionAtLimit(BaseModel):
    """Una dimensión de la búsqueda que quedó pegada a su límite."""

    name: str
    value: float
    limit: float
    side: str = Field(description="«máximo» o «mínimo»")

    @property
    def is_upper(self) -> bool:
        return self.side == "máximo"


def dimension_at_limit(
    name: str,
    value: float | None,
    minimum: float | None,
    maximum: float | None,
    step: float,
    warn_lower: bool = True,
) -> DimensionAtLimit | None:
    """Devuelve la dimensión si `value` coincide con uno de sus límites.

    La tolerancia es medio incremento: el barrido solo produce valores de la malla, de
    modo que «pegado al límite» significa «es el último valor que se miró».

    `warn_lower=False` calla el aviso del límite INFERIOR. Se usa en el peralte: el
    barrido elige el mínimo viable de cada planta, de modo que tocar el mínimo del rango
    es lo NORMAL y no indica que falte explorar. Además E.060 §15.7 le pone un piso, así
    que sugerir «pruebe con menos» sería sugerir algo que la norma no admite."""
    if value is None or step <= 0:
        return None
    tolerancia = step / 2.0
    if maximum is not None and abs(value - maximum) <= tolerancia:
        return DimensionAtLimit(name=name, value=value, limit=maximum, side="máximo")
    if warn_lower and minimum is not None and abs(value - minimum) <= tolerancia:
        return DimensionAtLimit(name=name, value=value, limit=minimum, side="mínimo")
    return None


def boundary_note(dimensiones: list[DimensionAtLimit]) -> str:
    """El aviso que lee el proyectista. Cadena vacía si no hay nada que avisar."""
    if not dimensiones:
        return ""

    arriba = [d for d in dimensiones if d.is_upper]
    abajo = [d for d in dimensiones if not d.is_upper]
    partes: list[str] = []

    if arriba:
        detalle = ", ".join(f"{d.name} = {d.value:.2f} m (máximo explorado)" for d in arriba)
        partes.append(
            f"La alternativa recomendada está en el LÍMITE SUPERIOR del rango explorado: "
            f"{detalle}. El barrido no miró más allá, de modo que no puede afirmarse que "
            f"sea la mejor posible: amplíe el rango para comprobarlo."
        )
    if abajo:
        detalle = ", ".join(f"{d.name} = {d.value:.2f} m (mínimo explorado)" for d in abajo)
        partes.append(
            f"También está en el LÍMITE INFERIOR en {detalle}: por debajo podría haber "
            f"soluciones más económicas que no se evaluaron."
        )
    return " ".join(partes)


def describe_boundary(
    dimensiones: list[tuple],
) -> tuple[list[DimensionAtLimit], str]:
    """Aplica `dimension_at_limit` a varias dimensiones y arma el aviso.

    Cada elemento es `(nombre, valor, mínimo, máximo, incremento)` y, opcionalmente, un
    sexto campo `warn_lower`."""
    tocadas = [d for d in (dimension_at_limit(*args) for args in dimensiones) if d is not None]
    return tocadas, boundary_note(tocadas)
