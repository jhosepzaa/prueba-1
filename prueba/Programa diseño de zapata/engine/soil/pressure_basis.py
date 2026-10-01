"""Conversión BRUTA <-> NETA de presión sobre el suelo (punto 3 de la corrección
de Fase 2: módulo explícito e independiente, no implícito dentro del cálculo de
presión de contacto).

ESTADO NORMATIVO: en los artículos de E.050 revisados (Art.17, 20-22, ver
docs/normativa/referencias_e060_e050.md) no se encontró una ecuación numerada que
defina la conversión bruta<->neta con una fórmula única y explícita. La relación
usada aquí:

    q_neta = q_bruta - gamma_suelo * Df

es la práctica geotécnica estándar (convención Terzaghi/Peck: la presión NETA es
el incremento de esfuerzo en el suelo respecto de la condición previa a la
excavación, es decir, se descuenta la sobrecarga de suelo gamma*Df que existía
antes de construir la cimentación). Se marca explícitamente como
"N/A (práctica estándar)" en el CalculationTrace, no como cita de E.050.

Uso previsto: la presión APLICADA por la zapata siempre se calcula primero en
términos BRUTOS (carga total de servicio entre área = statics directa, sin
ambigüedad). Este módulo la convierte a la base (BRUTA o NETA) que el usuario
declaró para qadm_kPa, de modo que la comparación final sea siempre
"manzanas contra manzanas".
"""

from __future__ import annotations

from engine.domain.soil import PressureBasis

STANDARD_PRACTICE_REFERENCE = "N/A (práctica geotécnica estándar, no es un artículo numerado de E.050)"


def convert_pressure(
    q_kPa: float, from_basis: PressureBasis, to_basis: PressureBasis, gamma_kNm3: float, Df_m: float
) -> float:
    """Convierte una presión entre base BRUTA y NETA."""
    if from_basis == to_basis:
        return q_kPa
    overburden = gamma_kNm3 * Df_m
    if from_basis == PressureBasis.BRUTA and to_basis == PressureBasis.NETA:
        return q_kPa - overburden
    if from_basis == PressureBasis.NETA and to_basis == PressureBasis.BRUTA:
        return q_kPa + overburden
    raise ValueError(f"Combinación de bases no reconocida: {from_basis} -> {to_basis}")
