"""L1 — TRANSFERENCIA DE MOMENTO EN PUNZONAMIENTO (E.060 §11.12.7).

Módulo INDEPENDIENTE, validable con casos unitarios sin necesidad del resto del
motor.

TEXTO NORMATIVO (verificado en el PDF)
======================================
§11.12.7.1  "Cuando las cargas de gravedad, viento o sismo u otras fuerzas
             laterales produzcan transmisión de momentos no balanceados, Mu,
             entre una losa y una columna, la fracción γf·Mu debe ser transmitida
             por flexión de acuerdo con 13.5.3. El resto del momento no
             balanceado dado por γv·Mu se considera transferido por excentricidad
             del cortante alrededor del centroide de la sección crítica definida
             en 11.12.1.2, donde

                    γv = 1 − γf                                        (11-45)"

§11.12.7.2  "El esfuerzo cortante que resulta de la transferencia de momento por
             excentricidad del cortante debe suponerse que varía linealmente
             alrededor del centroide de las secciones críticas definidas en
             11.12.1.2. El máximo esfuerzo cortante debido a Vu y Mu no debe
             exceder φvn, donde:
             (a) Para elementos sin refuerzo para cortante

                    vn = Vc / (bo·d)                                   (11-46)"

Ec. 13-1    "γf = 1 / (1 + (2/3)·sqrt(b1/b2))"

donde b1 es la dimensión de la sección crítica MEDIDA EN LA DIRECCIÓN DEL
MOMENTO (es decir, del vano que genera el momento) y b2 la dimensión
perpendicular.

PROPIEDAD DE SECCIÓN Jc — ALCANCE DECLARADO
===========================================
E.060 §11.12.7.2 exige que el esfuerzo "varíe linealmente alrededor del
centroide", pero NO da la expresión de la propiedad de sección Jc. La fórmula
empleada aquí es la propiedad geométrica estándar de la sección crítica de cuatro
lados de una COLUMNA INTERIOR:

    Jc = (d·b1³)/6 + (b1·d³)/6 + (d·b2·b1²)/2

Es una DERIVACIÓN GEOMÉTRICA (momento polar de inercia de las cuatro caras del
perímetro crítico respecto a su eje centroidal), no una ecuación citada de E.060.
Se marca explícitamente como tal. Vale para columna interior con sección crítica
cerrada por los cuatro lados — el único caso del MVP (columna concéntrica).

ESFUERZO COMBINADO
==================
    vu = Vu/(bo·d)  +  γvx·Mux·cx/Jcx  +  γvy·Muy·cy/Jcy

con c = b1/2 (distancia del centroide a la cara más solicitada). La combinación
biaxial suma los dos aportes en la esquina más desfavorable: es la extensión
directa del principio de superposición lineal que exige §11.12.7.2, aplicada a
los dos ejes.

CRITERIO:   vu <= φ·vn = φ·Vc/(bo·d)
Equivalente en fuerza:  Vu_efectivo = vu·bo·d  <=  φ·Vc
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from engine.foundation.critical_section import AxisProperties, CriticalSection
from engine.results.status import CheckStatus

JC_REFERENCE = (
    "Propiedad geométrica de la sección crítica (momento polar de inercia de las cuatro caras). "
    "DERIVACIÓN estándar, no una ecuación numerada de E.060; §11.12.7.2 solo exige variación lineal."
)


class AxisMomentTransfer(BaseModel):
    axis: str = Field(..., description='"X" o "Y"')
    Mu_kNm: float
    b1_m: float = Field(..., description="Dimensión de la sección crítica en la dirección del momento")
    b2_m: float = Field(..., description="Dimensión perpendicular")
    gamma_f: float
    gamma_v: float
    Jc_m4: float
    c_m: float = Field(..., description="b1/2, distancia del centroide a la cara más solicitada")
    shear_stress_MPa: float = Field(..., description="γv·Mu·c/Jc")
    equation_substituted: str


class MomentTransferResult(BaseModel):
    applicable: bool
    bo_m: float
    d_m: float

    v_direct_MPa: float = Field(..., description="Vu/(bo·d)")
    axis_x: AxisMomentTransfer | None
    axis_y: AxisMomentTransfer | None
    v_max_MPa: float = Field(..., description="Esfuerzo combinado máximo")

    phi_vn_MPa: float = Field(..., description="φ·Vc/(bo·d)")
    ratio: float

    Vu_effective_kN: float = Field(..., description="v_max·bo·d, comparable contra φVc")
    phi_Vc_kN: float

    amplification_factor: float = Field(
        ..., description="v_max / v_direct: cuánto amplifica la transferencia de momento"
    )

    status: CheckStatus
    message: str
    equation_substituted: str
    code_reference: str


def gamma_f(b1_m: float, b2_m: float) -> float:
    """γf = 1/(1 + (2/3)·sqrt(b1/b2))  — E.060 ec. 13-1."""
    return 1.0 / (1.0 + (2.0 / 3.0) * math.sqrt(b1_m / b2_m))


def polar_moment_jc(b1_m: float, b2_m: float, d_m: float) -> float:
    """Jc de la sección crítica de cuatro lados, columna interior. Ver JC_REFERENCE."""
    return (d_m * b1_m**3) / 6.0 + (b1_m * d_m**3) / 6.0 + (d_m * b2_m * b1_m**2) / 2.0


def _axis_transfer(
    axis: str, Mu_kNm: float, b1_m: float, b2_m: float, d_m: float,
    props: AxisProperties | None = None,
) -> AxisMomentTransfer:
    """`props` aporta la geometría REAL de la sección crítica (Fase 1C). Sin él se
    supone la sección cerrada y simétrica de columna interior, que es el
    comportamiento anterior."""
    gf = gamma_f(b1_m, b2_m)
    gv = 1.0 - gf
    if props is None:
        jc = polar_moment_jc(b1_m, b2_m, d_m)
        c = b1_m / 2.0
    else:
        jc = props.Jc_m4
        # En una sección TRUNCADA el centroide se desplaza y c_low != c_high. El
        # esfuerzo máximo está en la fibra más alejada del centroide, que puede ser
        # la del lado abierto: ese material existe -- pertenece a las caras
        # paralelas, que llegan hasta el borde -- aunque allí no haya una cara
        # perpendicular que resista. Tomar b1/2 subestimaría el esfuerzo.
        c = props.c_max_m
    # Mu en kN·m -> N·mm ; Jc en m^4 -> mm^4 ; resultado en MPa
    Mu_Nmm = Mu_kNm * 1e6
    jc_mm4 = jc * 1e12
    c_mm = c * 1000.0
    stress = gv * Mu_Nmm * c_mm / jc_mm4 if jc_mm4 > 0 else 0.0
    return AxisMomentTransfer(
        axis=axis, Mu_kNm=Mu_kNm, b1_m=b1_m, b2_m=b2_m,
        gamma_f=gf, gamma_v=gv, Jc_m4=jc, c_m=c, shear_stress_MPa=stress,
        equation_substituted=(
            f"eje {axis}: b1={b1_m:.4f} m, b2={b2_m:.4f} m -> "
            f"γf = 1/(1+(2/3)·sqrt({b1_m / b2_m:.4f})) = {gf:.4f}, γv = {gv:.4f} | "
            f"Jc = {jc:.6e} m⁴, c = {c:.4f} m | "
            f"v = γv·Mu·c/Jc = {gv:.4f}·{Mu_kNm:.2f}·{c:.4f}/{jc:.6e} = {stress:.4f} MPa"
        ),
    )


def check_punching_with_moment_transfer(
    Vu_kN: float,
    Mux_kNm: float,
    Muy_kNm: float,
    bx_m: float,
    by_m: float,
    d_m: float,
    Vc_kN: float,
    phi: float,
    section: CriticalSection | None = None,
) -> MomentTransferResult:
    """Verificación completa de §11.12.7.

    Vu_kN: cortante directo de punzonamiento (Pu − qu·A_crit).
    Mux/Muy: momentos no balanceados transmitidos a la columna.
    bx/by: dimensiones de la COLUMNA. La sección crítica es (bx+d) x (by+d).
    Vc_kN: resistencia nominal del concreto por §11.12.2.1 (mínimo de las tres ec.).
    """
    if section is None:
        b_crit_x = bx_m + d_m  # dimensión de la sección crítica a lo largo de X
        b_crit_y = by_m + d_m
        bo = 2.0 * (b_crit_x + b_crit_y)
        props_x = props_y = None
    else:
        b_crit_x = section.axis_x.b1_m
        b_crit_y = section.axis_y.b1_m
        bo = section.bo_m
        props_x, props_y = section.axis_x, section.axis_y

    bo_mm = bo * 1000.0
    d_mm = d_m * 1000.0
    area_mm2 = bo_mm * d_mm

    v_direct = (Vu_kN * 1000.0) / area_mm2 if area_mm2 > 0 else 0.0
    phi_vn = (phi * Vc_kN * 1000.0) / area_mm2 if area_mm2 > 0 else 0.0

    has_moment = abs(Mux_kNm) > 1e-9 or abs(Muy_kNm) > 1e-9

    # Convención E.050 art. 28.1: Mux es el momento que desplaza la resultante a lo
    # largo de X, es decir el que flexiona en el plano X-Z. Su b1 -- la dimensión de la
    # sección crítica MEDIDA EN LA DIRECCIÓN DEL MOMENTO, según ec. 13-1 -- es por
    # tanto la dimensión a lo largo de X.
    ax_x = (
        _axis_transfer("X", abs(Mux_kNm), b_crit_x, b_crit_y, d_m, props_x)
        if abs(Mux_kNm) > 1e-9 else None
    )
    # Muy flexiona en el plano Y-Z: b1 a lo largo de Y.
    ax_y = (
        _axis_transfer("Y", abs(Muy_kNm), b_crit_y, b_crit_x, d_m, props_y)
        if abs(Muy_kNm) > 1e-9 else None
    )

    v_moment = (ax_x.shear_stress_MPa if ax_x else 0.0) + (ax_y.shear_stress_MPa if ax_y else 0.0)
    v_max = v_direct + v_moment

    ratio = v_max / phi_vn if phi_vn > 0 else float("inf")
    vu_effective_kN = v_max * area_mm2 / 1000.0
    phi_vc_kN = phi * Vc_kN
    amplification = v_max / v_direct if v_direct > 0 else 1.0

    if v_max <= phi_vn:
        status = CheckStatus.PASS
        message = (
            f"Punzonamiento con transferencia de momento CUMPLE: "
            f"vu = {v_max:.4f} MPa <= φvn = {phi_vn:.4f} MPa (ratio {ratio:.3f}). "
            f"La transferencia de momento amplifica el esfuerzo un {(amplification - 1) * 100:.1f}%."
        )
    else:
        status = CheckStatus.FAIL
        message = (
            f"PUNZONAMIENTO NO CUMPLE con transferencia de momento (§11.12.7): "
            f"vu = {v_max:.4f} MPa > φvn = {phi_vn:.4f} MPa (ratio {ratio:.3f}). "
            f"El cortante directo solo daba {v_direct:.4f} MPa; la transferencia de momento "
            f"lo amplifica un {(amplification - 1) * 100:.1f}% hasta superar la capacidad."
        )

    return MomentTransferResult(
        applicable=has_moment,
        bo_m=bo, d_m=d_m,
        v_direct_MPa=v_direct, axis_x=ax_x, axis_y=ax_y, v_max_MPa=v_max,
        phi_vn_MPa=phi_vn, ratio=ratio,
        Vu_effective_kN=vu_effective_kN, phi_Vc_kN=phi_vc_kN,
        amplification_factor=amplification,
        status=status, message=message,
        equation_substituted=(
            f"Sección crítica {b_crit_x:.4f} x {b_crit_y:.4f} m, bo={bo:.4f} m, d={d_m:.4f} m | "
            f"v_directo = Vu/(bo·d) = {Vu_kN:.2f}kN/({bo_mm:.0f}·{d_mm:.0f}) = {v_direct:.4f} MPa"
            + (f" | {ax_x.equation_substituted}" if ax_x else "")
            + (f" | {ax_y.equation_substituted}" if ax_y else "")
            + f" | vu_max = {v_direct:.4f} + {v_moment:.4f} = {v_max:.4f} MPa | "
            f"φvn = φ·Vc/(bo·d) = {phi}·{Vc_kN:.2f}kN/({bo_mm:.0f}·{d_mm:.0f}) = {phi_vn:.4f} MPa | "
            f"ratio = {ratio:.3f}"
        ),
        code_reference=(
            "E.060 §11.12.7.1 (γv, ec. 11-45), §11.12.7.2 (ec. 11-46), ec. 13-1 (γf); "
            f"Jc: {JC_REFERENCE}"
        ),
    )
