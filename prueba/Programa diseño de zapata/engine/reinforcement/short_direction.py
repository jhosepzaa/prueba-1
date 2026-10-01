"""Distribución del refuerzo en la DIRECCIÓN CORTA de zapatas rectangulares
-- E.060 §15.4.4, ecuación 15-1.

TEXTO NORMATIVO (verificado en el PDF):
    "El refuerzo en la dirección larga debe distribuirse uniformemente en el ancho
     total de la zapata.
     Para el refuerzo en la dirección corta, una porción del refuerzo total,
     gamma_s*As, debe distribuirse en forma uniforme sobre una franja (centrada
     con respecto al eje de la columna o pedestal) cuyo ancho sea igual a la
     longitud del lado corto de la zapata. El resto del refuerzo requerido en la
     dirección corta, (1 - gamma_s)*As, debe distribuirse uniformemente en las
     zonas que queden fuera de la franja central de la zapata.

         gamma_s = 2 / (beta + 1)                                    (15-1)

     donde beta es la relación del lado largo al lado corto de la zapata."

TERMINOLOGÍA (para evitar la confusión habitual):
    "Dirección corta" = la dirección PARALELA al lado corto de la zapata. Las
    barras de esa dirección se reparten a lo ancho del LADO LARGO. La franja
    central tiene un ancho igual al LADO CORTO.

    Ejemplo con B=4.0 m (largo, eje X) y L=2.0 m (corto, eje Y):
      - dirección larga  = X: barras paralelas a X, repartidas sobre el ancho L=2.0
                              -> uniforme (§15.4.4.1)
      - dirección corta  = Y: barras paralelas a Y, repartidas sobre el ancho B=4.0
                              -> franja central de ancho 2.0 m con gamma_s*As,
                                 y dos franjas exteriores de 1.0 m con el resto

    Para zapata cuadrada, beta = 1 -> gamma_s = 1 -> toda el área en la "franja
    central", que coincide con el ancho total: se degrada correctamente al caso
    uniforme.

HALLAZGO -- INTERACCIÓN NO RESUELTA POR LA NORMA
================================================
Cuando el acero total está gobernado por la cuantía mínima de §9.7
(As_total = rho_min * B_largo * h), repartirlo según §15.4.4 deja a las franjas
EXTERIORES por debajo de esa misma cuantía mínima. Demostración:

    (1 - gamma_s) = (beta - 1)/(beta + 1) = (B - L)/(B + L)
    As_exterior   = (B-L)/(B+L) * rho_min * B * h
    As_min exigido en el ancho exterior (B-L):  rho_min * (B-L) * h
    cociente = B/(B+L)  <  1     -> las franjas exteriores quedan cortas

(En cambio la franja central siempre cumple: su cociente es 2B/(B+L) >= 1.)

E.060 no resuelve explícitamente esta interacción entre §15.4.4 y §9.7. DECISIÓN
DE INGENIERÍA ADOPTADA (conservadora, marcada como tal en el CalculationTrace):
se eleva el acero de cada franja hasta su propio mínimo de §9.7 cuando el reparto
de §15.4.4 lo dejaría por debajo. Nunca se coloca menos que rho_min*ancho*h en
ninguna franja. El acero total resultante puede superar ligeramente al calculado
por §15.4.4 puro; esa diferencia queda registrada en `topped_up`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RebarBand(BaseModel):
    name: str
    width_m: float
    As_required_m2: float = Field(..., description="Acero asignado a esta franja tras el reparto")
    As_min_m2: float = Field(..., description="Mínimo de §9.7 aplicado al ancho de esta franja")
    topped_up: bool = Field(..., description="¿Se elevó al mínimo por la interacción §15.4.4 / §9.7?")


class ShortDirectionDistribution(BaseModel):
    is_square: bool
    beta: float
    gamma_s: float
    long_side_m: float
    short_side_m: float
    bands: list[RebarBand]
    As_total_after_distribution_m2: float
    code_reference: str
    note: str


def distribute_short_direction(
    As_total_m2: float,
    long_side_m: float,
    short_side_m: float,
    h_m: float,
    rho_min: float,
) -> ShortDirectionDistribution:
    """Reparte `As_total_m2` (acero de la dirección corta, sobre el ancho
    `long_side_m`) según E.060 §15.4.4, elevando cada franja a su mínimo de §9.7
    cuando corresponda.
    """
    if short_side_m > long_side_m:
        raise ValueError(
            f"long_side_m ({long_side_m}) debe ser >= short_side_m ({short_side_m}); "
            "el llamador debe ordenar los lados antes de invocar esta función."
        )

    beta = long_side_m / short_side_m
    gamma_s = 2.0 / (beta + 1.0)
    is_square = abs(long_side_m - short_side_m) < 1e-9

    if is_square:
        band_min = rho_min * long_side_m * h_m
        as_band = max(As_total_m2, band_min)
        bands = [
            RebarBand(
                name="uniforme (zapata cuadrada, gamma_s = 1)",
                width_m=long_side_m,
                As_required_m2=as_band,
                As_min_m2=band_min,
                topped_up=as_band > As_total_m2 + 1e-12,
            )
        ]
        note = "Zapata cuadrada: beta = 1 y gamma_s = 1, el reparto degrada al caso uniforme."
    else:
        central_width = short_side_m
        outer_width_total = long_side_m - short_side_m

        as_central_raw = gamma_s * As_total_m2
        as_outer_raw = (1.0 - gamma_s) * As_total_m2

        central_min = rho_min * central_width * h_m
        outer_min = rho_min * outer_width_total * h_m

        as_central = max(as_central_raw, central_min)
        as_outer = max(as_outer_raw, outer_min)

        bands = [
            RebarBand(
                name="franja central (ancho = lado corto)",
                width_m=central_width,
                As_required_m2=as_central,
                As_min_m2=central_min,
                topped_up=as_central > as_central_raw + 1e-12,
            ),
            RebarBand(
                name="franjas exteriores (suma de ambos lados)",
                width_m=outer_width_total,
                As_required_m2=as_outer,
                As_min_m2=outer_min,
                topped_up=as_outer > as_outer_raw + 1e-12,
            ),
        ]
        note = (
            f"Reparto §15.4.4: gamma_s={gamma_s:.4f} del acero en la franja central de "
            f"{central_width:.2f} m; el resto en {outer_width_total:.2f} m exteriores."
        )
        if bands[1].topped_up:
            note += (
                " Las franjas exteriores se elevaron a la cuantía mínima de §9.7 "
                "(interacción no resuelta por la norma -- decisión conservadora, ver módulo)."
            )

    return ShortDirectionDistribution(
        is_square=is_square,
        beta=beta,
        gamma_s=gamma_s,
        long_side_m=long_side_m,
        short_side_m=short_side_m,
        bands=bands,
        As_total_after_distribution_m2=sum(b.As_required_m2 for b in bands),
        code_reference="E.060 §15.4.4 y ec. 15-1; mínimos por §9.7 vía §10.6",
        note=note,
    )
