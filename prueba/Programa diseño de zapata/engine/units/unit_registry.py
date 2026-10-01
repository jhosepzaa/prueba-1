"""Registro de unidades de ENTRADA.

El motor calcula siempre en SI (kN, kN·m, kPa, m, kN/m³). Este módulo permite que
el usuario declare sus datos en las unidades que use habitualmente — toneladas
fuerza, kilogramos fuerza, kg/cm², libras — y los convierte a SI en un único
punto, antes de que entren al motor.

POR QUÉ VIVE EN EL MOTOR Y NO EN LA INTERFAZ
La conversión de unidades no es ingeniería, pero sí es aritmética que puede
introducir errores. Manteniéndola aquí queda cubierta por tests y la interfaz
sigue sin calcular nada: solo declara en qué unidad viene cada dato.

FACTORES
Cada factor convierte DESDE la unidad indicada HACIA la unidad SI del motor.
Se usan las equivalencias exactas (g = 9,80665 m/s²; 1 lbf = 4,4482216152605 N;
1 in = 25,4 mm), no aproximaciones redondeadas.
"""

from __future__ import annotations

import math
from typing import Literal

G = 9.80665  # aceleración de la gravedad estándar [m/s²]
LBF_N = 4.4482216152605  # 1 libra fuerza en newtons
FT_M = 0.3048  # 1 pie en metros

# --- Fuerza -> kN ---------------------------------------------------------------
ForceUnit = Literal["kN", "tonf", "kgf", "N", "lbf", "kip"]
FORCE_TO_KN: dict[str, float] = {
    "kN": 1.0,
    "tonf": G,                 # 1 tonelada fuerza = 1000 kgf = 9.80665 kN
    "kgf": G / 1000.0,         # 0.00980665 kN
    "N": 0.001,
    "lbf": LBF_N / 1000.0,     # 0.0044482216 kN
    "kip": LBF_N,              # 1000 lbf = 4.4482216 kN
}
FORCE_LABELS: dict[str, str] = {
    "kN": "kN", "tonf": "tonf (t)", "kgf": "kgf", "N": "N", "lbf": "lbf", "kip": "kip",
}

# --- Momento -> kN·m ------------------------------------------------------------
MomentUnit = Literal["kN·m", "tonf·m", "kgf·m", "kgf·cm", "N·m", "lbf·ft", "kip·ft"]
MOMENT_TO_KNM: dict[str, float] = {
    "kN·m": 1.0,
    "tonf·m": G,
    "kgf·m": G / 1000.0,
    "kgf·cm": G / 1000.0 / 100.0,
    "N·m": 0.001,
    "lbf·ft": LBF_N * FT_M / 1000.0,
    "kip·ft": LBF_N * FT_M,
}
MOMENT_LABELS: dict[str, str] = {
    "kN·m": "kN·m", "tonf·m": "tonf·m (t·m)", "kgf·m": "kgf·m", "kgf·cm": "kgf·cm",
    "N·m": "N·m", "lbf·ft": "lbf·ft", "kip·ft": "kip·ft",
}

# --- Presión -> kPa -------------------------------------------------------------
PressureUnit = Literal["kPa", "kgf/cm²", "tonf/m²", "kgf/m²", "MPa", "psi", "ksf"]
PRESSURE_TO_KPA: dict[str, float] = {
    "kPa": 1.0,
    "kgf/cm²": G * 10.0,            # 98.0665 kPa  (muy usada en el Perú)
    "tonf/m²": G,                   # 9.80665 kPa
    "kgf/m²": G / 1000.0,
    "MPa": 1000.0,
    "psi": LBF_N / (0.0254**2) / 1000.0,     # 6.894757 kPa
    "ksf": LBF_N * 1000.0 / (FT_M**2) / 1000.0,  # 47.88026 kPa
}
PRESSURE_LABELS: dict[str, str] = {
    "kPa": "kPa", "kgf/cm²": "kgf/cm² (kg/cm²)", "tonf/m²": "tonf/m² (t/m²)",
    "kgf/m²": "kgf/m²", "MPa": "MPa", "psi": "psi", "ksf": "ksf",
}

# --- Resistencia de materiales -> MPa -------------------------------------------
StrengthUnit = Literal["MPa", "kgf/cm²", "psi", "ksi", "kPa"]
STRENGTH_TO_MPA: dict[str, float] = {
    "MPa": 1.0,
    # 1 kgf/cm² = 9,80665 N / 1e-4 m² = 98 066,5 Pa = 0,0980665 MPa.
    # (f'c = 210 kgf/cm² -> 20,59 MPa ; fy = 4200 kgf/cm² -> 411,88 MPa)
    "kgf/cm²": G / 100.0,
    "psi": LBF_N / (0.0254**2) / 1e6,
    "ksi": LBF_N * 1000.0 / (0.0254**2) / 1e6,
    "kPa": 0.001,
}
STRENGTH_LABELS: dict[str, str] = {
    "MPa": "MPa", "kgf/cm²": "kgf/cm² (kg/cm²)", "psi": "psi", "ksi": "ksi", "kPa": "kPa",
}

# --- Longitud -> m --------------------------------------------------------------
LengthUnit = Literal["m", "cm", "mm", "ft", "in"]
LENGTH_TO_M: dict[str, float] = {
    "m": 1.0, "cm": 0.01, "mm": 0.001, "ft": FT_M, "in": 0.0254,
}
LENGTH_LABELS: dict[str, str] = {
    "m": "m", "cm": "cm", "mm": "mm", "ft": "pie", "in": "pulgada",
}

# --- Peso unitario -> kN/m³ ------------------------------------------------------
UnitWeightUnit = Literal["kN/m³", "tonf/m³", "kgf/m³", "pcf"]
UNIT_WEIGHT_TO_KNM3: dict[str, float] = {
    "kN/m³": 1.0,
    "tonf/m³": G,
    "kgf/m³": G / 1000.0,
    "pcf": LBF_N / (FT_M**3) / 1000.0,  # lb/ft³ -> 0.157087 kN/m³
}
UNIT_WEIGHT_LABELS: dict[str, str] = {
    "kN/m³": "kN/m³", "tonf/m³": "tonf/m³ (t/m³)", "kgf/m³": "kgf/m³", "pcf": "lb/ft³",
}


def _convert(value: float, unit: str, table: dict[str, float], kind: str) -> float:
    try:
        return value * table[unit]
    except KeyError:
        raise ValueError(
            f'Unidad de {kind} no reconocida: "{unit}". Disponibles: {", ".join(sorted(table))}'
        ) from None


def force_to_kN(value: float, unit: str) -> float:
    return _convert(value, unit, FORCE_TO_KN, "fuerza")


def moment_to_kNm(value: float, unit: str) -> float:
    return _convert(value, unit, MOMENT_TO_KNM, "momento")


def pressure_to_kPa(value: float, unit: str) -> float:
    return _convert(value, unit, PRESSURE_TO_KPA, "presión")


def strength_to_MPa(value: float, unit: str) -> float:
    return _convert(value, unit, STRENGTH_TO_MPA, "resistencia")


def length_to_m(value: float, unit: str) -> float:
    return _convert(value, unit, LENGTH_TO_M, "longitud")


def unit_weight_to_kNm3(value: float, unit: str) -> float:
    return _convert(value, unit, UNIT_WEIGHT_TO_KNM3, "peso unitario")


# --- Registro por magnitud ------------------------------------------------------
# Una sola tabla por magnitud, y el nombre de la unidad SI en que trabaja el motor.
# Todo lo que convierta —entrada, presentación o cambio de unidad— sale de aquí.
KIND_TABLES: dict[str, dict[str, float]] = {
    "force": FORCE_TO_KN,
    "moment": MOMENT_TO_KNM,
    "pressure": PRESSURE_TO_KPA,
    "strength": STRENGTH_TO_MPA,
    "length": LENGTH_TO_M,
    "unit_weight": UNIT_WEIGHT_TO_KNM3,
}
KIND_LABELS: dict[str, dict[str, str]] = {
    "force": FORCE_LABELS,
    "moment": MOMENT_LABELS,
    "pressure": PRESSURE_LABELS,
    "strength": STRENGTH_LABELS,
    "length": LENGTH_LABELS,
    "unit_weight": UNIT_WEIGHT_LABELS,
}
SI_UNITS: dict[str, str] = {
    "force": "kN",
    "moment": "kN·m",
    "pressure": "kPa",
    "strength": "MPa",
    "length": "m",
    "unit_weight": "kN/m³",
}
KIND_NAMES: dict[str, str] = {
    "force": "fuerza",
    "moment": "momento",
    "pressure": "presión",
    "strength": "resistencia",
    "length": "longitud",
    "unit_weight": "peso unitario",
}

# Cifras significativas con que se presenta un valor convertido.
#
# POR QUÉ SE REDONDEA. Al cambiar de unidad, 21 MPa son 214,140404725... kgf/cm².
# Mostrar ese número entero es ilegible, y guardar uno distinto del que se muestra
# haría que lo calculado no fuera lo visible — exactamente lo que este programa
# evita. Se redondea a seis cifras, se muestra y se calcula ESE valor: el error
# relativo que introduce es ≤ 5·10⁻⁶ —cinco partes por millón, invisible frente a
# cualquier tolerancia de ingeniería— y la ida y vuelta entre unidades es estable
# (21 MPa → 214,14 kgf/cm² → 21 MPa).
# Es una decisión de PRESENTACIÓN declarada, no un criterio de cálculo.
DISPLAY_SIGNIFICANT_DIGITS = 6

ROUNDING_NOTE = (
    "Al cambiar de unidad el valor se convierte con el factor exacto y se redondea a "
    f"{DISPLAY_SIGNIFICANT_DIGITS} cifras significativas; se calcula con el valor que se "
    "muestra. El error relativo del redondeo es ≤ 5·10⁻⁶."
)


def _table(kind: str) -> dict[str, float]:
    try:
        return KIND_TABLES[kind]
    except KeyError:
        raise ValueError(
            f'Magnitud no reconocida: "{kind}". Disponibles: {", ".join(sorted(KIND_TABLES))}'
        ) from None


def to_si(value: float, kind: str, unit: str) -> float:
    """Del valor declarado por el usuario a la unidad SI del motor."""
    return _convert(value, unit, _table(kind), KIND_NAMES.get(kind, kind))


def from_si(value: float, kind: str, unit: str) -> float:
    """Del valor SI del motor a la unidad en que el usuario quiere verlo."""
    return value / _convert(1.0, unit, _table(kind), KIND_NAMES.get(kind, kind))


def convert(value: float, kind: str, source: str, target: str) -> float:
    """Entre dos unidades de la misma magnitud, pasando por el SI. Sin redondear."""
    if source == target:
        return value
    return from_si(to_si(value, kind, source), kind, target)


def round_significant(value: float, digits: int = DISPLAY_SIGNIFICANT_DIGITS) -> float:
    """Redondeo a cifras significativas. Ver DISPLAY_SIGNIFICANT_DIGITS."""
    if value == 0.0 or not math.isfinite(value):
        return value
    exponente = math.floor(math.log10(abs(value)))
    escala = 10.0 ** (digits - 1 - exponente)
    return round(value * escala) / escala


def convert_for_display(value: float, kind: str, source: str, target: str) -> float:
    """Conversión + redondeo declarado: lo que la interfaz muestra y envía."""
    return round_significant(convert(value, kind, source, target))


def available_units() -> dict[str, list[dict[str, object]]]:
    """Catálogo que la interfaz muestra en los desplegables.

    `to_si` acompaña a cada unidad para que la interfaz pueda ROTULAR y presentar
    resultados sin volver a declarar factores por su cuenta: la tabla sigue siendo
    única y vive aquí. La interfaz no decide ninguna equivalencia."""
    def _entries(kind: str) -> list[dict[str, object]]:
        tabla = KIND_TABLES[kind]
        return [
            {"value": k, "label": v, "to_si": tabla[k]}
            for k, v in KIND_LABELS[kind].items()
        ]

    return {kind: _entries(kind) for kind in KIND_TABLES}
