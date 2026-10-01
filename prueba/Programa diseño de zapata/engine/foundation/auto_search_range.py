"""Rango de búsqueda automático cuando el usuario no declara B, L o h.

QUÉ ES Y QUÉ NO ES
Esto es una HEURÍSTICA DE BÚSQUEDA: acota dónde mirar, no decide nada de diseño.
Toda geometría que caiga en el rango se verifica exactamente igual que si el
usuario la hubiera escrito a mano — mismas ecuaciones, mismos criterios, mismos
descartes. Si el rango automático resultara mal elegido, el efecto sería no
encontrar alternativas (visible de inmediato), nunca aceptar una inválida.

No proviene de ninguna norma y así se declara en el CalculationTrace del cálculo.

CRITERIO
El área necesaria en planta se estima con el equilibrio más elemental:

    A ≈ P_servicio_máx / q_admisible

que ignora el peso propio y la excentricidad — por eso es solo un punto de
partida. A partir del lado equivalente Beq = √A se abre un rango generoso:

    mínimo  = 0,60 · Beq   (permite encontrar soluciones más compactas de lo estimado)
    máximo  = 2,20 · Beq   (permite crecer si la excentricidad o el peso propio lo exigen)

acotado por límites de sentido común y redondeado al incremento de búsqueda.
El peralte arranca del mínimo constructivo y se extiende hasta una fracción del
lado, que es donde el punzonamiento deja de gobernar en la práctica.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from engine.domain.loads import LoadCaseSet
from engine.domain.soil import PressureBasis, SoilProfile
from engine.soil.pressure_basis import convert_pressure

# Cotas de sentido común (m). No normativas: evitan mallas absurdas.
B_ABSOLUTE_MIN_M = 0.60
B_ABSOLUTE_MAX_M = 12.00
H_ABSOLUTE_MIN_M = 0.40
H_ABSOLUTE_MAX_M = 2.50

LOWER_FACTOR = 0.60
UPPER_FACTOR = 2.20

# Puntos por eje que la malla automática no supera. Con el rango ampliado por la
# excentricidad, mantener un incremento fino generaba decenas de miles de geometrías y el
# servidor rechazaba la petición. Cuando el rango es ancho, el incremento se agranda y se
# dice: vale más explorar todo el rango con paso grueso que la mitad con paso fino.
MAX_POINTS_PER_AXIS = 45
STEP_LADDER_M = (0.05, 0.10, 0.20, 0.25, 0.50)


class AutoRange(BaseModel):
    B_min_m: float
    B_max_m: float
    L_min_m: float
    L_max_m: float
    h_min_m: float
    h_max_m: float
    B_step_m: float | None = None
    L_step_m: float | None = None
    estimated_area_m2: float
    equivalent_side_m: float
    note: str


def _mayor_excentricidad(load_case_set: LoadCaseSet) -> float:
    """La mayor excentricidad de servicio, `e = M/P` (E.050 art. 28.1), en cualquier eje.

    Es la que obliga a crecer en planta para mantener la resultante dentro del núcleo.
    Se mira el SERVICIO porque es el que dimensiona la planta (E.060 §15.2)."""
    peor = 0.0
    for combo in load_case_set.service:
        if combo.P_kN <= 0:
            continue
        peor = max(peor, abs(combo.Mx_kNm) / combo.P_kN, abs(combo.My_kNm) / combo.P_kN)
    return peor


def _paso_para_el_rango(minimo: float, maximo: float, paso_pedido: float) -> float:
    """El incremento más fino de la escala que mantiene la malla manejable."""
    for paso in STEP_LADDER_M:
        if paso < paso_pedido:
            continue
        if (maximo - minimo) / paso + 1 <= MAX_POINTS_PER_AXIS:
            return paso
    return max(paso_pedido, (maximo - minimo) / (MAX_POINTS_PER_AXIS - 1))


def _round_down(value: float, step: float) -> float:
    return math.floor(value / step) * step


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step) * step


def estimate_search_range(
    load_case_set: LoadCaseSet,
    soil: SoilProfile,
    column_bx_m: float,
    column_by_m: float,
    B_step_m: float,
    L_step_m: float,
    h_step_m: float,
) -> AutoRange:
    """Estima un rango de búsqueda a partir de la carga de servicio y qadm."""
    p_max = max((c.P_kN for c in load_case_set.service), default=0.0)
    if p_max <= 0 or soil.qadm_kPa <= 0:
        # Sin datos utilizables se abre un rango amplio en vez de adivinar.
        return AutoRange(
            B_min_m=1.0, B_max_m=4.0, L_min_m=1.0, L_max_m=4.0,
            h_min_m=H_ABSOLUTE_MIN_M, h_max_m=1.20,
            estimated_area_m2=0.0, equivalent_side_m=0.0,
            note=(
                "Rango por defecto: no se pudo estimar el área necesaria porque falta la "
                "carga de servicio o la presión admisible."
            ),
        )

    # PRESIÓN DISPONIBLE, no `qadm` a secas (2026-09-24). Con base BRUTA, el peso del
    # relleno y del concreto sobre la huella consume parte de la capacidad antes de que
    # la columna aporte nada: comparar P/A contra `qadm` sobrestima lo que hay. Se lleva
    # `qadm` a base NETA con la MISMA conversión que usa el verificador
    # (`engine/soil/pressure_basis.convert_pressure`), no con una fórmula propia.
    q_disponible = convert_pressure(
        soil.qadm_kPa, soil.pressure_basis, PressureBasis.NETA, soil.gamma_kNm3, soil.Df_m
    )
    if q_disponible <= 0:
        # El relleno se come toda la capacidad: no hay nada que estimar y abrir un rango
        # amplio es más honesto que dividir por un número sin sentido.
        return AutoRange(
            B_min_m=1.0, B_max_m=B_ABSOLUTE_MAX_M, L_min_m=1.0, L_max_m=B_ABSOLUTE_MAX_M,
            h_min_m=H_ABSOLUTE_MIN_M, h_max_m=1.20,
            estimated_area_m2=0.0, equivalent_side_m=0.0,
            note=(
                f"Rango amplio: con q_adm = {soil.qadm_kPa:.1f} kPa en base "
                f"{soil.pressure_basis.value} y un relleno de {soil.gamma_kNm3:.1f} kN/m³ "
                f"sobre {soil.Df_m:.2f} m, la presión disponible para la columna es nula "
                f"o negativa. Ninguna zapata de este rango cumplirá: revise el dato del EMS."
            ),
        )

    area = p_max / q_disponible
    side = math.sqrt(area)

    lower = max(_round_down(side * LOWER_FACTOR, B_step_m), B_ABSOLUTE_MIN_M)
    upper = min(_round_up(side * UPPER_FACTOR, B_step_m), B_ABSOLUTE_MAX_M)

    # EXCENTRICIDAD (2026-09-24). El modelo de contacto por defecto exige la resultante
    # dentro del núcleo central (E.060 §15.2.3), y en un rectángulo eso pide un lado de
    # al menos 6·e en el eje donde actúa el momento. Estimar solo con P/q dejaba el
    # límite superior por debajo de cualquier geometría admisible: medido, el barrido
    # entregaba como mejor una zapata un 46 % más voluminosa que la que existía justo
    # fuera del rango. El margen del 10 % evita que el único candidato quede exactamente
    # sobre el límite del núcleo.
    e_max = _mayor_excentricidad(load_case_set)
    if e_max > 0:
        upper = min(max(upper, _round_up(6.0 * e_max * 1.10, B_step_m)), B_ABSOLUTE_MAX_M)

    # La zapata debe poder alojar la columna con algo de voladizo a cada lado.
    min_for_column = _round_up(max(column_bx_m, column_by_m) + 4 * B_step_m, B_step_m)
    lower = max(lower, min_for_column)
    upper = max(upper, lower + 4 * B_step_m)

    h_upper = min(_round_up(upper * 0.30, h_step_m), H_ABSOLUTE_MAX_M)
    h_upper = max(h_upper, H_ABSOLUTE_MIN_M + 4 * h_step_m)

    paso = _paso_para_el_rango(lower, upper, B_step_m)

    return AutoRange(
        B_min_m=lower, B_max_m=upper,
        L_min_m=lower, L_max_m=upper,
        B_step_m=paso, L_step_m=paso,
        h_min_m=H_ABSOLUTE_MIN_M, h_max_m=h_upper,
        estimated_area_m2=area, equivalent_side_m=side,
        note=(
            f"Rango estimado automáticamente: A ≈ P/q_disponible = {p_max:.1f}/"
            f"{q_disponible:.1f} = {area:.3f} m² → lado equivalente {side:.2f} m"
            + (
                f"; con e = {e_max:.2f} m el núcleo central exige un lado del orden de "
                f"6·e = {6.0 * e_max:.2f} m"
                if e_max > 0
                else ""
            )
            + f". Se explora de {lower:.2f} a {upper:.2f} m"
            + (f" con incrementos de {paso:.2f} m, más gruesos que los pedidos para que "
               f"la malla siga siendo manejable" if paso > B_step_m + 1e-9 else "")
            + f". La presión disponible "
            f"descuenta el relleno sobre la huella (base {soil.pressure_basis.value}). "
            f"Heurística de búsqueda, no criterio de diseño: cada geometría del rango se "
            f"verifica con los mismos criterios normativos."
        ),
    )
