"""Sistema interno de unidades.

Convención adoptada para todo el motor (no normativa, decisión de arquitectura):

- Longitud:            metros (m)
- Fuerza:               kilonewtons (kN)
- Momento:              kilonewton-metro (kN·m)
- Presión sobre suelo:  kilopascales (kPa = kN/m^2)
- Esfuerzos de material (f'c, fy): megapascales (MPa = N/mm^2)
- Peso unitario:        kN/m^3

Las ecuaciones normativas de E.060 (cortante, punzonamiento, flexión) están
calibradas en MPa-mm-N. Para no mezclar convenciones dentro de los modelos de
dominio, esas ecuaciones reciben metros/kN y hacen la conversión a mm/N
internamente, en un único punto por ecuación (ver engine/codes/peru/e060_concrete.py).
Esto evita el error de conversión disperso que pide evitar la sección 17 del
encargo original.
"""

from __future__ import annotations

M_TO_MM = 1000.0
MM_TO_M = 1.0 / M_TO_MM

KN_TO_N = 1000.0
N_TO_KN = 1.0 / KN_TO_N

# kgf/cm^2 <-> MPa, kgf <-> kN: conversiones de uso frecuente en la práctica
# peruana (sistema técnico métrico), para la futura entrada dual de unidades.
KGF_CM2_TO_MPA = 0.0980665
MPA_TO_KGF_CM2 = 1.0 / KGF_CM2_TO_MPA
KGF_TO_KN = 0.00980665
KN_TO_KGF = 1.0 / KGF_TO_KN


def m_to_mm(value_m: float) -> float:
    return value_m * M_TO_MM


def mm_to_m(value_mm: float) -> float:
    return value_mm * MM_TO_M


def kn_to_n(value_kn: float) -> float:
    return value_kn * KN_TO_N


def n_to_kn(value_n: float) -> float:
    return value_n * N_TO_KN
