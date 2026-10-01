"""E.060 Capítulo 12 — LONGITUD DE DESARROLLO (L4).

Todas las ecuaciones y factores verificados contra el texto del PDF.

§12.1.1  "La tracción o compresión calculada en el refuerzo en cada sección [...]
          debe ser desarrollada hacia cada lado de dicha sección mediante una
          longitud embebida en el concreto (longitud de anclaje), gancho,
          dispositivo mecánico o una combinación de ellos."

§12.1.3  "Los valores de sqrt(f'c) usados en este capítulo no deben exceder de 7,3 MPa."
          -> equivale a f'c <= 53,29 MPa. Texto de la E.060 designada (propuesta 2019).
          La edición anterior y el resto del mismo documento (§11.1.2, §11.6.2) usan 8,3 MPa:
          posible errata de la fuente. Se aplica el texto tal como está (Fase 10A, A7) y queda
          declarado.

§12.2.1  ld debe determinarse de 12.2.2 ó 12.2.3, "pero no debe ser menor que 300 mm".

§12.2.2  TABLA 12.1 — método simplificado. Aplicable cuando:
            (separación libre >= db  Y  recubrimiento libre >= db  Y  estribos >= mínimo de 11.5.6)
          Ó  (separación libre >= 2db  Y  recubrimiento libre >= db)

            barras 3/4" y menores :  ld = fy·ψt·ψe / (2.6·λ·sqrt(f'c)) · db
            barras mayores de 3/4":  ld = fy·ψt·ψe / (2.1·λ·sqrt(f'c)) · db

§12.2.3  ECUACIÓN 12-1 — método general (siempre aplicable):

            ld = [ fy·ψt·ψe·ψs / (1.1·λ·sqrt(f'c)·((cb+Ktr)/db)) ] · db

          con (cb+Ktr)/db <= 2.5   y   Ktr = Atr·fyt/(10·s·n)   (ec. 12-2)
          "Se permite usar Ktr = 0, como una simplificación de diseño".

          cb = la MENOR entre:
            (a) distancia del centro de la barra a la superficie más cercana del concreto
            (b) la mitad de la separación centro a centro de las barras

§12.2.4  TABLA 12.2 — factores de modificación:
            ψt : barras superiores* 1,3 ; otras 1,0
            ψe : epóxico con rec.<3db o sep.libre<6db 1,5 ; otro epóxico 1,2 ; sin tratamiento 1,0
            ψs : barras 3/4" y menores 0,8 ; mayores de 3/4" 1,0
            λ  : concreto liviano 1,3 ; peso normal 1,0
          (*) "Se consideran barras superiores aquellas que tienen 300 mm o más de
              concreto fresco por debajo de ellas."

§12.2.4  Nota de la Tabla 12.2: "El producto ψt·ψe no necesita considerarse mayor que 1,7"
          NOTA DE EXTRACCIÓN: el PDF pierde los subíndices y el texto se lee
          "El producto: t s no necesita considerarse mayor que 1,7". Se adopta
          ψt·ψe porque ψt·ψs <= 1,3·1,0 = 1,3 nunca alcanzaría 1,7 y la cláusula
          sería vacía, mientras que ψt·ψe = 1,3·1,5 = 1,95 sí supera el tope.
          Marcado como interpretación de lectura, no como certeza.

REFUERZO EN EXCESO (§12.2, cláusula "Refuerzo en exceso"):
          "Se permite reducir ld cuando el refuerzo [...] excede el requerido por
          análisis, mediante el factor (As requerido)/(As proporcionado), excepto
          [...] cuando se trate de elementos con responsabilidad sísmica."
          NO se aplica por defecto: requiere activación explícita del usuario.

§12.5    GANCHO ESTÁNDAR EN TRACCIÓN:
            ldg = 0,24·ψe·λ·fy/sqrt(f'c)·db
          §12.5.1: "no debe ser menor que 8 db ni 150 mm" -> rigen AMBOS mínimos, es decir
          ldg >= max(8db, 150 mm). (La lectura anterior tomaba el menor: Fase 10A, A4.)
          Factores de reducción de §12.5.3:
            (a) 0,7 — barras 1 3/8" y menores con recubrimiento lateral >= 65 mm
                (y para ganchos de 90°, recubrimiento en la extensión >= 50 mm)
            (b) 0,8 — ganchos de 90° confinados por estribos a <= 3db
            (c) 0,8 — ganchos de 180° confinados por estribos a <= 3db
          Los ganchos NUNCA se asumen: solo se aplican si el usuario los declara.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

CODE_NAME = "E.060"

MIN_LD_M = 0.300  # §12.2.1
SQRT_FC_MAX_MPA = 7.3  # §12.1.3 (propuesta 2019; posible errata, declarada)
PSI_T_PSI_E_CAP = 1.7  # §12.2.4, nota de la Tabla 12.2
BAR_SIZE_THRESHOLD_M = 0.01905  # 3/4" = 19.05 mm -- frontera de Tabla 12.1 y de ψs

HookType = Literal["ninguno", "90", "180"]


class DevelopmentLengthResult(BaseModel):
    ld_m: float = Field(..., description="Longitud de desarrollo requerida (ya con el mínimo de 300 mm)")
    ld_before_minimum_m: float
    method: Literal["Tabla 12.1", "ec. 12-1"]
    governed_by_minimum: bool

    # Factores aplicados
    psi_t: float
    psi_e: float
    psi_s: float
    lambda_concrete: float
    psi_t_psi_e_capped: bool

    # Parámetros del método general
    cb_m: float | None = None
    Ktr: float | None = None
    cb_plus_ktr_over_db: float | None = None
    cb_ktr_capped: bool = False

    sqrt_fc_used_MPa: float
    sqrt_fc_capped: bool

    equation_symbolic: str
    equation_substituted: str
    code_reference: str


class HookDevelopmentResult(BaseModel):
    ldg_m: float
    ldg_before_minimum_m: float
    minimum_m: float
    governed_by_minimum: bool
    reduction_factor: float
    hook_type: HookType
    equation_symbolic: str
    equation_substituted: str
    code_reference: str


def _sqrt_fc(fc_MPa: float) -> tuple[float, bool]:
    """§12.1.3: sqrt(f'c) no debe exceder 7,3 MPa (texto de la fuente designada)."""
    raw = math.sqrt(fc_MPa)
    if raw > SQRT_FC_MAX_MPA:
        return SQRT_FC_MAX_MPA, True
    return raw, False


def psi_t_top_bar(concrete_below_bar_m: float) -> float:
    """§12.2.4 Tabla 12.2 y su nota: barra superior = 300 mm o más de concreto
    fresco por DEBAJO de ella.

    En una zapata, la parrilla inferior tiene solo el recubrimiento (70 mm) por
    debajo, muy por debajo del umbral -> ψt = 1,0 para ambas capas.
    """
    return 1.3 if concrete_below_bar_m >= 0.300 else 1.0


def psi_s_bar_size(db_m: float) -> float:
    """§12.2.4: 0,8 para barras de 3/4" y menores; 1,0 para mayores."""
    return 0.8 if db_m <= BAR_SIZE_THRESHOLD_M + 1e-9 else 1.0


def simplified_conditions_met(
    clear_spacing_m: float, clear_cover_m: float, db_m: float, has_min_stirrups: bool
) -> bool:
    """Condiciones de la Tabla 12.1 (§12.2.2)."""
    cond_a = clear_spacing_m >= db_m - 1e-12 and clear_cover_m >= db_m - 1e-12 and has_min_stirrups
    cond_b = clear_spacing_m >= 2.0 * db_m - 1e-12 and clear_cover_m >= db_m - 1e-12
    return cond_a or cond_b


def development_length_table_12_1(
    db_m: float, fy_MPa: float, fc_MPa: float, psi_t: float, psi_e: float, lambda_concrete: float = 1.0
) -> DevelopmentLengthResult:
    sqrt_fc, capped_fc = _sqrt_fc(fc_MPa)

    product = psi_t * psi_e
    capped_te = product > PSI_T_PSI_E_CAP
    if capped_te:
        product = PSI_T_PSI_E_CAP

    is_small_bar = db_m <= BAR_SIZE_THRESHOLD_M + 1e-9
    coefficient = 2.6 if is_small_bar else 2.1
    size_label = '3/4" y menores' if is_small_bar else 'mayores de 3/4"'

    ld_raw = (fy_MPa * product / (coefficient * lambda_concrete * sqrt_fc)) * db_m
    ld = max(ld_raw, MIN_LD_M)

    return DevelopmentLengthResult(
        ld_m=ld,
        ld_before_minimum_m=ld_raw,
        method="Tabla 12.1",
        governed_by_minimum=ld_raw < MIN_LD_M,
        psi_t=psi_t,
        psi_e=psi_e,
        psi_s=1.0,  # la Tabla 12.1 no usa ψs (está embebido en los coeficientes 2.6/2.1)
        lambda_concrete=lambda_concrete,
        psi_t_psi_e_capped=capped_te,
        sqrt_fc_used_MPa=sqrt_fc,
        sqrt_fc_capped=capped_fc,
        equation_symbolic=f"ld = fy·ψt·ψe / ({coefficient}·λ·sqrt(f'c)) · db   [barras {size_label}]",
        equation_substituted=(
            f"ld = {fy_MPa:.0f}·{product:.3f} / ({coefficient}·{lambda_concrete:.1f}·{sqrt_fc:.4f}) "
            f"· {db_m * 1000:.1f} mm = {ld_raw * 1000:.1f} mm"
            + (f" -> gobierna el mínimo de 300 mm" if ld_raw < MIN_LD_M else "")
        ),
        code_reference="E.060 §12.2.2, Tabla 12.1; mínimo §12.2.1; factores Tabla 12.2",
    )


def development_length_eq_12_1(
    db_m: float,
    fy_MPa: float,
    fc_MPa: float,
    cb_m: float,
    psi_t: float,
    psi_e: float,
    psi_s: float,
    Ktr: float = 0.0,
    lambda_concrete: float = 1.0,
) -> DevelopmentLengthResult:
    """Ecuación 12-1 (§12.2.3), método general."""
    sqrt_fc, capped_fc = _sqrt_fc(fc_MPa)

    product_te = psi_t * psi_e
    capped_te = product_te > PSI_T_PSI_E_CAP
    if capped_te:
        product_te = PSI_T_PSI_E_CAP

    ratio_raw = (cb_m + Ktr * db_m) / db_m if db_m > 0 else 0.0
    capped_ratio = ratio_raw > 2.5
    ratio = min(ratio_raw, 2.5)

    ld_raw = (fy_MPa * product_te * psi_s / (1.1 * lambda_concrete * sqrt_fc * ratio)) * db_m
    ld = max(ld_raw, MIN_LD_M)

    return DevelopmentLengthResult(
        ld_m=ld,
        ld_before_minimum_m=ld_raw,
        method="ec. 12-1",
        governed_by_minimum=ld_raw < MIN_LD_M,
        psi_t=psi_t,
        psi_e=psi_e,
        psi_s=psi_s,
        lambda_concrete=lambda_concrete,
        psi_t_psi_e_capped=capped_te,
        cb_m=cb_m,
        Ktr=Ktr,
        cb_plus_ktr_over_db=ratio,
        cb_ktr_capped=capped_ratio,
        sqrt_fc_used_MPa=sqrt_fc,
        sqrt_fc_capped=capped_fc,
        equation_symbolic="ld = [ fy·ψt·ψe·ψs / (1.1·λ·sqrt(f'c)·((cb+Ktr)/db)) ] · db",
        equation_substituted=(
            f"cb={cb_m * 1000:.1f} mm, Ktr={Ktr:.2f}, (cb+Ktr)/db={ratio_raw:.3f}"
            + (" -> limitado a 2.5" if capped_ratio else "")
            + f" | ld = [{fy_MPa:.0f}·{product_te:.3f}·{psi_s:.1f} / "
            f"(1.1·{lambda_concrete:.1f}·{sqrt_fc:.4f}·{ratio:.3f})]·{db_m * 1000:.1f} mm "
            f"= {ld_raw * 1000:.1f} mm"
            + (" -> gobierna el mínimo de 300 mm" if ld_raw < MIN_LD_M else "")
        ),
        code_reference="E.060 §12.2.3, ec. 12-1 y 12-2; mínimo §12.2.1; factores Tabla 12.2",
    )


def hook_development_length(
    db_m: float,
    fy_MPa: float,
    fc_MPa: float,
    hook_type: HookType,
    psi_e: float = 1.0,
    lambda_concrete: float = 1.0,
    side_cover_ok_for_0_7: bool = False,
    confined_by_stirrups: bool = False,
) -> HookDevelopmentResult:
    """§12.5.2: ldg = 0,24·ψe·λ·fy/sqrt(f'c)·db; §12.5.1: no menor que 8db ni 150 mm.

    Los factores de reducción de §12.5.3 solo se aplican si el usuario declara
    expresamente que se cumplen las condiciones. NUNCA se asumen.
    """
    if hook_type == "ninguno":
        raise ValueError("hook_development_length requiere un gancho de 90 o 180 grados.")

    sqrt_fc, _ = _sqrt_fc(fc_MPa)
    ldg_raw = 0.24 * psi_e * lambda_concrete * fy_MPa / sqrt_fc * db_m

    factor = 1.0
    applied: list[str] = []
    if side_cover_ok_for_0_7 and db_m <= 0.0349 + 1e-9:  # 1 3/8"
        factor *= 0.7
        applied.append("§12.5.3(a) recubrimiento lateral >= 65 mm: x0.7")
    if confined_by_stirrups and db_m <= 0.0349 + 1e-9:
        factor *= 0.8
        applied.append(f"§12.5.3({'b' if hook_type == '90' else 'c'}) confinado por estribos: x0.8")

    ldg_reduced = ldg_raw * factor
    minimum = max(8.0 * db_m, 0.150)  # §12.5.1: 8db y 150 mm, ambos
    ldg = max(ldg_reduced, minimum)

    return HookDevelopmentResult(
        ldg_m=ldg,
        ldg_before_minimum_m=ldg_reduced,
        minimum_m=minimum,
        governed_by_minimum=ldg_reduced < minimum,
        reduction_factor=factor,
        hook_type=hook_type,
        equation_symbolic="ldg = 0.24·ψe·λ·fy/sqrt(f'c)·db ; >= max(8db, 150 mm)",
        equation_substituted=(
            f"ldg = 0.24·{psi_e:.1f}·{lambda_concrete:.1f}·{fy_MPa:.0f}/{sqrt_fc:.4f}·{db_m * 1000:.1f} "
            f"= {ldg_raw * 1000:.1f} mm"
            + (f" x{factor:.2f} [{'; '.join(applied)}] = {ldg_reduced * 1000:.1f} mm" if applied else "")
            + f" | mínimo max(8db,150)={minimum * 1000:.1f} mm -> ldg = {ldg * 1000:.1f} mm"
        ),
        code_reference="E.060 §12.5.2 y §12.5.3",
    )
