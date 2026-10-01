"""Acero mínimo por flexión en VIGAS — E.060 §10.5.

POR QUÉ NO SIRVE EL MÍNIMO DE ZAPATAS
=====================================
El motor ya calcula un As mínimo para zapatas, pero por otra vía: §10.5.1 **excluye
expresamente a zapatas y losas macizas** de la exigencia basada en el momento de
agrietamiento, y por eso el motor las lleva a §9.7 a través de §10.6.

Una viga NO está excluida. Le corresponde el mínimo de §10.5, que es otra cosa y da
otro número. Reutilizar la función de zapatas aquí —tentador, porque existe y
funciona— produciría un mínimo que no corresponde. Es el riesgo R9 de la auditoría
de Fase 0.

TEXTO NORMATIVO (verificado en el PDF de E.060)
===============================================
§10.5.1  "En cualquier sección de un elemento estructural - EXCEPTO EN ZAPATAS Y
          LOSAS MACIZAS - sometido a flexión, donde por el análisis se requiera
          refuerzo de acero en tracción, el área de acero que se proporcione será
          la necesaria para que la resistencia de diseño de la sección sea por lo
          menos 1,2 veces el momento de agrietamiento de la sección bruta Mcr
          (Mn >= 1,2 Mcr), donde:

              Mcr = fr·Ig / Yt        fr = 0,62·sqrt(f'c)"

§10.5.2  "El área mínima de refuerzo por tracción de las secciones rectangulares y
          de las secciones T con el ala en compresión, no será menor de:

              As_min = (0,22·sqrt(f'c) / fy)·bw·d          (10-3)"

§10.5.3  "Para LOSAS MACIZAS Y LOSAS NERVADAS que cumplan con 8.12, no es necesario
          satisfacer los requisitos de 10.5.1 y 10.5.2, si en cada sección del
          elemento, el área de acero en tracción proporcionada es al menos un tercio
          superior a la requerida por el análisis."   (E.060, propuesta 2019)

CÓMO SE COMBINAN
================
§10.5.1 y §10.5.2 son dos exigencias SIMULTÁNEAS, no alternativas: la norma pide
ambas y gobierna la mayor.

FASE 10A — la exención del tercio NO alcanza a vigas. La edición anterior de E.060
la formulaba para cualquier elemento; la propuesta 2019, fuente designada del
proyecto, la restringe a losas macizas y nervadas. Una viga de conexión no es losa:
rige siempre el mínimo completo de §10.5.1/§10.5.2. El campo `exempt_by_10_5_3` se
conserva por contrato y vale siempre False.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

# E.060 §10.5.1: módulo de rotura del concreto para el momento de agrietamiento.
FR_COEFFICIENT = 0.62
# E.060 §10.5.1: factor sobre Mcr.
MCR_FACTOR = 1.2
# E.060 §10.5.2, ec. 10-3.
AS_MIN_COEFFICIENT = 0.22
# E.060 §10.5.3: exención por exceso de armado. Solo losas (propuesta 2019): no se
# aplica a vigas. Se conserva la constante como referencia documental.
EXCESS_FACTOR = 4.0 / 3.0


class BeamMinimumSteel(BaseModel):
    """Las dos exigencias de §10.5 resueltas por separado, para poder decir cuál
    gobierna en vez de devolver un número sin explicación."""

    As_min_10_5_1_m2: float = Field(..., description="El que hace Mn >= 1,2·Mcr")
    As_min_10_5_2_m2: float = Field(..., description="Ec. 10-3: (0,22·sqrt(f'c)/fy)·bw·d")
    Mcr_kNm: float
    fr_MPa: float

    As_required_by_analysis_m2: float
    exempt_by_10_5_3: bool = Field(
        ..., description="True si el As proporcionado supera en 1/3 al requerido por análisis"
    )

    As_min_governing_m2: float
    governed_by: str
    equation_substituted: str


def cracking_moment_kNm(fc_MPa: float, b_m: float, h_m: float) -> tuple[float, float]:
    """Mcr = fr·Ig/Yt para sección rectangular bruta. Devuelve (Mcr, fr).

    Ig = b·h³/12 y Yt = h/2 son propiedades de la SECCIÓN BRUTA, sin descontar el
    acero: así lo dice §10.5.1 al hablar de «momento de agrietamiento de la sección
    bruta»."""
    fr_MPa = FR_COEFFICIENT * math.sqrt(fc_MPa)
    Ig_m4 = b_m * h_m**3 / 12.0
    Yt_m = h_m / 2.0
    # fr en MPa = MN/m²; el resultado sale en MN·m y se pasa a kN·m.
    Mcr_kNm = fr_MPa * Ig_m4 / Yt_m * 1000.0
    return Mcr_kNm, fr_MPa


def _as_for_moment(Mu_kNm: float, b_m: float, d_m: float, fc_MPa: float, fy_MPa: float, phi: float) -> float:
    """As necesario para que la sección resista Mu, con bloque rectangular de §10.2.

    Es la misma ecuación cuadrática que resuelve `foundation/flexure.py`; se repite
    aquí en forma reducida porque lo que hace falta es solo el área, sin el modelo
    de resultado de zapata."""
    if Mu_kNm <= 0:
        return 0.0
    b_mm, d_mm = b_m * 1000.0, d_m * 1000.0
    Mn_Nmm = (Mu_kNm * 1e6) / phi
    a = 1.0
    bq = -1.7 * fc_MPa * b_mm * d_mm
    cq = 1.7 * fc_MPa * b_mm * Mn_Nmm
    disc = bq * bq - 4 * a * cq
    if disc < 0:
        return float("nan")
    T_N = (-bq - math.sqrt(disc)) / (2 * a)
    return (T_N / fy_MPa) / 1e6


def beam_minimum_steel(
    b_m: float,
    h_m: float,
    d_m: float,
    fc_MPa: float,
    fy_MPa: float,
    As_required_by_analysis_m2: float,
    phi_flexure: float = 0.90,
) -> BeamMinimumSteel:
    """Acero mínimo por flexión de una viga, según §10.5.

    `As_required_by_analysis_m2` es el que pide el momento de diseño; hace falta
    para poder aplicar la exención de §10.5.3."""
    Mcr, fr = cracking_moment_kNm(fc_MPa, b_m, h_m)

    # §10.5.1: el As que hace Mn >= 1,2·Mcr. Se resuelve pidiendo a la sección un
    # momento de diseño equivalente phi·1,2·Mcr.
    As_10_5_1 = _as_for_moment(MCR_FACTOR * Mcr * phi_flexure, b_m, d_m, fc_MPa, fy_MPa, phi_flexure)

    # §10.5.2, ec. 10-3.
    As_10_5_2 = (AS_MIN_COEFFICIENT * math.sqrt(fc_MPa) / fy_MPa) * b_m * d_m

    # §10.5.3 (propuesta 2019) solo exime a losas macizas y nervadas: una viga no puede
    # acogerse a la exención del tercio. Rige siempre el mayor de §10.5.1 y §10.5.2.
    exento = False

    if As_10_5_1 >= As_10_5_2:
        gobierna, motivo = As_10_5_1, "E.060 §10.5.1: Mn >= 1,2·Mcr"
    else:
        gobierna, motivo = As_10_5_2, "E.060 §10.5.2, ec. 10-3"

    return BeamMinimumSteel(
        As_min_10_5_1_m2=As_10_5_1,
        As_min_10_5_2_m2=As_10_5_2,
        Mcr_kNm=Mcr,
        fr_MPa=fr,
        As_required_by_analysis_m2=As_required_by_analysis_m2,
        exempt_by_10_5_3=exento,
        As_min_governing_m2=gobierna,
        governed_by=motivo,
        equation_substituted=(
            f"fr = 0,62·sqrt({fc_MPa:.1f}) = {fr:.3f} MPa | "
            f"Mcr = fr·Ig/Yt = {Mcr:.2f} kN·m -> As(1,2·Mcr) = {As_10_5_1 * 1e4:.2f} cm² | "
            f"ec. 10-3: (0,22·sqrt({fc_MPa:.1f})/{fy_MPa:.0f})·{b_m:.3f}·{d_m:.3f} = "
            f"{As_10_5_2 * 1e4:.2f} cm² | gobierna {gobierna * 1e4:.2f} cm² ({motivo})"
        ),
    )
