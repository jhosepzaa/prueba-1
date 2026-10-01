"""Soluciones ANALÍTICAS independientes del motor.

Estas funciones resuelven las mismas magnitudes que el motor, pero por caminos
distintos: integración numérica del campo de presiones y búsqueda por bisección.
Son deliberadamente ineficientes y directas — su valor está en no compartir NADA
de la implementación que validan.

Ninguna proviene de bibliografía: todas se derivan de equilibrio y de la
definición del bloque de compresión, de modo que pueden escribirse sin consultar
ningún libro.
"""

from __future__ import annotations

import math

N_STEPS = 20_000  # resolución de la integración numérica


def pressure_per_unit_length(P_kN: float, e_m: float, dim_m: float, x_m: float) -> float:
    """Presión factorizada por unidad de longitud a la coordenada x, medida desde
    el CENTRO de la zapata, ya integrada sobre el ancho perpendicular.

        w(x) = (P/dim) · (1 + 12·e·x/dim²)

    En x = ±dim/2 esto vale (P/dim)·(1 ± 6e/dim), que es la distribución lineal
    clásica. Derivada de equilibrio: ∫w dx = P y ∫w·x dx = P·e.
    """
    return (P_kN / dim_m) * (1.0 + 12.0 * e_m * x_m / dim_m**2)


def moment_by_integration(P_kN: float, e_m: float, dim_m: float, cantilever_m: float) -> float:
    """Momento en la cara de columna, por integración numérica del voladizo del
    lado de MAYOR presión. Independiente de la fórmula trapezoidal del motor."""
    x_edge = dim_m / 2.0
    x_face = x_edge - cantilever_m
    total = 0.0
    step = cantilever_m / N_STEPS
    for i in range(N_STEPS):
        x = x_face + (i + 0.5) * step
        w = pressure_per_unit_length(P_kN, e_m, dim_m, x)
        total += max(w, 0.0) * (x - x_face) * step
    return total


def shear_by_integration(
    P_kN: float, e_m: float, dim_m: float, cantilever_m: float, d_m: float
) -> float:
    """Cortante en la sección crítica situada a d de la cara, por integración."""
    x_edge = dim_m / 2.0
    x_crit = x_edge - (cantilever_m - d_m)
    if x_crit >= x_edge:
        return 0.0
    total = 0.0
    length = x_edge - x_crit
    step = length / N_STEPS
    for i in range(N_STEPS):
        x = x_crit + (i + 0.5) * step
        total += max(pressure_per_unit_length(P_kN, e_m, dim_m, x), 0.0) * step
    return total


def biaxial_pressure(
    P_kN: float, B_m: float, L_m: float, ex_m: float, ey_m: float, x_m: float, y_m: float
) -> float:
    """Campo de presiones biaxial, con x,y medidos desde el centro."""
    q_avg = P_kN / (B_m * L_m)
    return q_avg * (1.0 + 12.0 * ex_m * x_m / B_m**2 + 12.0 * ey_m * y_m / L_m**2)


def total_reaction_by_integration(
    P_kN: float, B_m: float, L_m: float, ex_m: float, ey_m: float, n: int = 400
) -> tuple[float, float, float]:
    """Integra el campo de presiones sobre toda la base.

    Devuelve (fuerza_total, momento_respecto_a_X, momento_respecto_a_Y). Por
    equilibrio deben valer (P, P·ey, P·ex).
    """
    dx, dy = B_m / n, L_m / n
    area = dx * dy
    force = 0.0
    mx = 0.0
    my = 0.0
    for i in range(n):
        x = -B_m / 2 + (i + 0.5) * dx
        for j in range(n):
            y = -L_m / 2 + (j + 0.5) * dy
            q = biaxial_pressure(P_kN, B_m, L_m, ex_m, ey_m, x, y)
            force += q * area
            my += q * x * area
            mx += q * y * area
    return force, mx, my


def punching_shear_by_integration(
    P_u_kN: float, B_m: float, L_m: float, bx_m: float, by_m: float, d_m: float, n: int = 600
) -> float:
    """Vu de punzonamiento integrando la presión FUERA del perímetro crítico.

    El motor lo calcula como Pu − qu_prom·A_crit. Aquí se integra celda a celda
    la zona exterior, que es un camino completamente distinto.
    """
    half_x = (bx_m + d_m) / 2.0
    half_y = (by_m + d_m) / 2.0
    qu = P_u_kN / (B_m * L_m)
    dx, dy = B_m / n, L_m / n
    area = dx * dy
    outside = 0.0
    for i in range(n):
        x = -B_m / 2 + (i + 0.5) * dx
        for j in range(n):
            y = -L_m / 2 + (j + 0.5) * dy
            if abs(x) > half_x or abs(y) > half_y:
                outside += qu * area
    return outside


def steel_area_by_bisection(
    Mu_kNm: float, b_m: float, d_m: float, fc_MPa: float, fy_MPa: float, phi: float = 0.90
) -> float:
    """As por BISECCIÓN sobre la ecuación de equilibrio de la sección.

    Se busca As tal que φ·Mn = Mu, con
        a  = As·fy / (0.85·f'c·b)          (equilibrio de fuerzas)
        Mn = As·fy·(d − a/2)               (equilibrio de momentos)

    El motor resuelve la misma ecuación en forma cerrada (cuadrática). Que ambos
    coincidan verifica que la forma cerrada está bien despejada.
    """
    b_mm = b_m * 1000.0
    d_mm = d_m * 1000.0
    Mn_target = (Mu_kNm / phi) * 1e6  # kN·m -> N·mm

    def moment_for(as_mm2: float) -> float:
        a = as_mm2 * fy_MPa / (0.85 * fc_MPa * b_mm)
        return as_mm2 * fy_MPa * (d_mm - a / 2.0)

    lo, hi = 0.0, 0.85 * fc_MPa * b_mm * d_mm / fy_MPa  # As con a = d (techo físico)
    if moment_for(hi) < Mn_target:
        return float("nan")  # sección insuficiente
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if moment_for(mid) < Mn_target:
            lo = mid
        else:
            hi = mid
    return ((lo + hi) / 2.0) / 1e6  # mm² -> m²


def one_way_shear_capacity(fc_MPa: float, bw_m: float, d_m: float) -> float:
    """φVc por la expresión de E.060 ec. 11-3, escrita aquí de forma
    independiente para contrastar unidades y conversiones."""
    return 0.85 * 0.17 * math.sqrt(fc_MPa) * (bw_m * 1000.0) * (d_m * 1000.0) / 1000.0


def kern_limit_check(B_m: float, L_m: float, ex_m: float, ey_m: float) -> bool:
    """Condición de núcleo central por su definición geométrica."""
    return abs(ex_m) / (B_m / 6.0) + abs(ey_m) / (L_m / 6.0) <= 1.0 + 1e-9
