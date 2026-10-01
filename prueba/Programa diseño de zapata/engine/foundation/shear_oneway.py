"""Cortante unidireccional ("viga ancha"). Sección crítica a distancia d de la
cara de columna (E.060 §15.5.2, que remite a §11.1.3.1). Vc por E.060 §11.3.1.1,
ec. 11-3 (E.060 §15.5.1-15.5.2)."""

from __future__ import annotations

from pydantic import BaseModel

from engine.codes.base import IConcreteCode
from engine.foundation.flexure import (
    _campo_biaxial,
    _cortante_biaxial,
    net_pressure_field,
)
from engine.results.status import CheckStatus


class ShearOneWayResult(BaseModel):
    Vu_kN: float
    phi_Vc_kN: float
    ratio: float
    status: CheckStatus
    equation_substituted: str
    code_reference: str


def shear_force_at_d_from_face(
    P_u_column_kN: float, e_m: float, dim_along_e_m: float, cantilever_m: float, d_m: float,
    near_high_edge: bool,
    e_transverse_m: float = 0.0, dim_transverse_m: float | None = None,
) -> float:
    """Vu [kN] = fuerza resultante de la presión neta factorizada más allá de la
    sección crítica (a distancia d de la cara de columna, hacia el borde libre).
    Si d >= cantilever, la sección crítica cae dentro de la columna: Vu = 0 (caso
    fuera del alcance físico habitual, se reporta 0 en vez de un valor inválido).

    El campo lo resuelve `NetPressureField`, que distingue el contacto total del bloque
    triangular con despegue (decisión B, 2026-09-19). Antes se recortaban a cero las
    presiones negativas del campo lineal, que no equilibra la carga y subestima Vu.

    Con excentricidad transversal declarada y despegue BIAXIAL se integra el campo común
    de `unilateral_contact` sobre la franja, igual que la flexión: ver
    `moment_at_critical_section`."""
    c_shear = max(cantilever_m - d_m, 0.0)
    if c_shear == 0.0:
        return 0.0
    biaxial = _campo_biaxial(
        P_u_column_kN, e_m, dim_along_e_m, e_transverse_m, dim_transverse_m
    )
    if biaxial is not None:
        return _cortante_biaxial(biaxial, e_m, dim_along_e_m, c_shear, near_high_edge)
    campo = net_pressure_field(P_u_column_kN, e_m, dim_along_e_m)
    if near_high_edge:
        # Desde el borde de mayor presión hasta la sección crítica, en s = c_shear.
        fuerza, _ = campo.force_and_moment(0.0, c_shear, c_shear)
    else:
        fuerza, _ = campo.force_and_moment(
            dim_along_e_m - c_shear, dim_along_e_m, dim_along_e_m - c_shear
        )
    return fuerza


def check_shear_oneway(
    Vu_kN: float, fc_MPa: float, bw_m: float, d_m: float, code: IConcreteCode
) -> ShearOneWayResult:
    phi = code.phi_factors().cortante
    vc = code.one_way_shear_vc(fc_MPa, bw_m, d_m)
    phi_vc_kN = phi * vc.value
    ratio = Vu_kN / phi_vc_kN if phi_vc_kN > 0 else float("inf")
    status = CheckStatus.PASS if Vu_kN <= phi_vc_kN else CheckStatus.FAIL
    return ShearOneWayResult(
        Vu_kN=Vu_kN,
        phi_Vc_kN=phi_vc_kN,
        ratio=ratio,
        status=status,
        equation_substituted=f"phi*Vc = {phi} * {vc.value:.2f} = {phi_vc_kN:.2f} kN ; Vu = {Vu_kN:.2f} kN",
        code_reference=vc.code_reference,
    )
