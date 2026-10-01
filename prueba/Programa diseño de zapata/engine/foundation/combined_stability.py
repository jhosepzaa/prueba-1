"""Estabilidad de la ZAPATA COMBINADA: deslizamiento y volcamiento — pendiente 7.

POR QUÉ EXISTE Y QUÉ SUSTITUYE
==============================
Hasta aquí la combinada no verificaba estabilidad. La corrección D4 tapó el agujero
declarándolo: con fuerza horizontal el resultado quedaba NO VERIFICADO con la entrada
`stability_not_implemented`, y nunca PASS. Este módulo **la sustituye por la verificación
real**. Análisis previo en `docs/pendiente7_estabilidad_combinada.md`.

QUÉ SE REUTILIZA SIN CAMBIOS (no se vuelve a decidir nada de esto)
=================================================================
De `engine/soil/stability.py`, que es la única fuente del criterio:

  - fuerza estabilizante = SOLO CARGA MUERTA, E.020 art. 20.1 (`stabilizing_axial_kN`);
  - FS adoptados (D10-2b): 1,50 al volteo —con y sin sismo— y 1,50 al deslizamiento. Son
    CRITERIO DEL PROGRAMA, no cita normativa: ver `D10_2B_ADOPTED_NOTE`;
  - μ es dato del proyectista (E.020 art. 22.2). Sin μ → NO VERIFICADO, nunca un valor
    supuesto;
  - cargas de SERVICIO, E.050 art. 17.1;
  - punto de giro: arista inferior de la base; empuje pasivo NO considerado;
  - brazo de la fuerza horizontal: `h` de la zapata;
  - la reducción sísmica del 80 % nunca entra en estabilidad (E.030 art. 64.2).

LO QUE ESTE MÓDULO AÑADE: LA RESULTANTE DE VARIAS COLUMNAS
==========================================================
Las combinaciones se emparejan por NOMBRE entre columnas, que es lo que ya hace el solver
—y `CombinedFootingLayout` rechaza un layout cuyas columnas no declaren las mismas
combinaciones—. Para cada combinación de servicio, respecto del CENTROIDE de la zapata:

    P_total  = Σ P_i
    Mx_total = Σ (Mx_i + P_i·offset_x_i)        My_total = Σ (My_i + P_i·offset_y_i)
    Hx_tot   = Σ Hx_i                            Hy_tot   = Σ Hy_i

El término `P_i·offset_i` es el momento que produce cada carga por estar descentrada. Es
la misma reducción que el solver ya usa para la presión de contacto; aquí no se reinventa.

ENVOLVENTE DEL MOMENTO VOLCADOR (opción B, aprobada)
====================================================
El momento ESTABILIZADOR usa solo carga muerta (E.020 art. 20.1), pero `Mx_total` lleva el
P total. La excentricidad de una carga no muerta puede **reducir** `|Mx_total|`, y entonces
la lectura total SUBESTIMA el volcamiento. Se evalúan por eso las dos lecturas y se toma la
peor:

    M_volc = max(|M_total|, |M_estab|) + |H|·h

`M_estab` se arma con EXACTAMENTE el mismo conjunto de componentes que `stabilizing_axial_kN`
usa para N —los CM más los aportes no muertos que restan carga vertical—, de modo que N y
su momento son coherentes entre sí. Sin composición (modo directo) las dos lecturas
coinciden y rige la regla de siempre: si cumple, NO VERIFICADO.

La envolvente es un **criterio del programa**, no una exigencia normativa: E.020 art. 20.1
dice qué estabiliza, no cómo tratar la excentricidad de lo que no estabiliza.

ALCANCE
=======
La verificación se ejecuta cuando alguna combinación de servicio declara fuerza horizontal,
que es el mismo disparador de D4. Sin fuerza horizontal el momento de las columnas ya queda
acotado por la exigencia de resultante dentro del núcleo central de la presión de contacto
(e ≤ dim/6 da M_estab/M_volc = dim/(2e) ≥ 3), y no se añade ninguna entrada.

FORMULACIÓN COMÚN CON LA AISLADA (FORMULACION_VOLTEO, aprobada 2026-09-19)
=========================================================================
La divergencia `FORMULACION_VOLTEO` quedó RESUELTA: la zapata aislada y las zapatas de
la conectada usan la misma formulación —término `P·offset` y envolvente—, y el término
por columna lo calcula el MISMO ayudante, `engine.soil.stability.axis_moments_kNm`. Este
módulo ya solo añade lo que es propio de la combinada: la SUMA de varias columnas en una
resultante. Diagnóstico en `docs/formulacion_volteo_analisis.md`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.domain.combined_layout import CombinedFootingLayout, ColumnOnFooting
from engine.domain.loads import LoadCombination
from engine.domain.soil import SoilProfile
from engine.results.status import CheckStatus
from engine.soil.stability import (
    D10_2B_ADOPTED_NOTE,
    E020_DEAD_LOAD_ONLY_NOTE,
    E030_OVERTURNING_INTERPRETATION,
    E030_UNREDUCED_NOTE,
    ECCENTRICITY_TERM_NOTE,
    ENVELOPE_NOTE,
    OverturningResult,
    SlidingResult,
    _fs_overturning_required,
    _fs_sliding_required,
    axis_moments_kNm,
    denoise_moment_kNm,
    stabilizing_axial_kN,
)

__all__ = [
    "CombinedOverturningResult",
    "CombinedStabilityResult",
    "ENVELOPE_NOTE",
    "D10_2B_ADOPTED_NOTE",
    "check_combined_stability",
    "resultants",
]

RESULTANT_NOTE = (
    "Resultante de TODAS las columnas respecto del centroide de la zapata, emparejando las "
    "combinaciones por nombre: M = Σ (M_i + P_i·offset_i), H = Σ H_i. Es la misma reducción "
    "que usa la presión de contacto."
)

SCOPE_NOTE = (
    "Alcance: la estabilidad de la zapata combinada se verifica cuando alguna combinación de "
    "servicio declara fuerza horizontal. Sin ella, el momento de las columnas queda acotado "
    "por la exigencia de resultante dentro del núcleo central (e ≤ dim/6 ⇒ FS ≥ 3)."
)

NO_PASSIVE_NOTE = "Empuje pasivo del suelo NO considerado, del lado conservador."


# Desde FORMULACION_VOLTEO las dos lecturas de la envolvente viven en el modelo común
# `OverturningResult`, porque las tres tipologías las producen. El nombre se conserva
# para no romper los llamadores; no es un tipo distinto.
CombinedOverturningResult = OverturningResult


class CombinedStabilityResult(BaseModel):
    sliding: SlidingResult
    overturning_x: CombinedOverturningResult
    overturning_y: CombinedOverturningResult
    applicable: bool = Field(
        ..., description="False si ninguna combinación de servicio declara fuerza horizontal"
    )

    @property
    def status(self) -> CheckStatus:
        return CheckStatus.worst(
            [self.sliding.status, self.overturning_x.status, self.overturning_y.status]
        )


class _Resultant(BaseModel):
    """Reducción de todas las columnas al centroide, para UNA combinación."""

    name: str
    includes_seismic_loads: bool
    P_total_kN: float
    N_stabilizing_kN: float = Field(..., description="Sin el peso propio de la zapata")
    Mx_total_kNm: float
    My_total_kNm: float
    Mx_stabilizing_kNm: float
    My_stabilizing_kNm: float
    Hx_kN: float
    Hy_kN: float
    exact_dead_load: bool = Field(
        ..., description="False si alguna columna no declara composición (modo directo)"
    )

    @property
    def H_kN(self) -> float:
        return (self.Hx_kN**2 + self.Hy_kN**2) ** 0.5

    def as_combination(self) -> LoadCombination:
        """La resultante como combinación, solo para reutilizar los ayudantes que deciden
        el FS: lo único que miran es `includes_seismic_loads`."""
        return LoadCombination(
            name=self.name, type="SERVICIO", P_kN=self.P_total_kN,
            Mx_kNm=self.Mx_total_kNm, My_kNm=self.My_total_kNm,
            Hx_kN=self.Hx_kN, Hy_kN=self.Hy_kN,
            includes_seismic_loads=self.includes_seismic_loads,
        )


def _combo_by_name(col: ColumnOnFooting, name: str) -> LoadCombination | None:
    for c in col.loads.service:
        if c.name == name:
            return c
    return None


def resultants(layout: CombinedFootingLayout) -> list[_Resultant]:
    """Una resultante por combinación de servicio, en el orden en que las declara la
    primera columna. El layout ya garantiza que todas las columnas traen las mismas."""
    salida: list[_Resultant] = []
    for nombre in [c.name for c in layout.columns[0].loads.service]:
        P = N = mxt = myt = mxe = mye = hx = hy = 0.0
        escala_x = escala_y = 0.0
        exacta, sismica = True, False
        for col in layout.columns:
            c = _combo_by_name(col, nombre)
            if c is None:
                continue
            ox, oy = col.offset_x_m, col.offset_y_m
            P += c.P_kN
            hx += c.Hx_kN
            hy += c.Hy_kN
            sismica = sismica or c.includes_seismic_loads
            # El término P·offset y el conjunto estabilizante NO se recalculan aquí:
            # los da el ayudante común `axis_moments_kNm` (E.020 art. 20.1), el mismo
            # que usan la aislada y las zapatas de la conectada. Sin composición las dos
            # lecturas coinciden y el resultado no podrá afirmarse (`exacta = False`).
            n_col, exacta_col = stabilizing_axial_kN(c, 0.0)
            N += n_col
            exacta = exacta and exacta_col
            mxt_c, mxe_c = axis_moments_kNm(c, ox, "X")
            myt_c, mye_c = axis_moments_kNm(c, oy, "Y")
            mxt += mxt_c
            myt += myt_c
            mxe += mxe_c
            mye += mye_c
            # La cancelación también ocurre ENTRE columnas —dos cargas iguales a un lado
            # y otro del centroide—, no solo dentro de una. Se acumula la escala para
            # poder distinguir después un cero exacto de un residuo.
            escala_x += abs(mxt_c) + abs(mxe_c)
            escala_y += abs(myt_c) + abs(mye_c)
        salida.append(_Resultant(
            name=nombre, includes_seismic_loads=sismica, P_total_kN=P, N_stabilizing_kN=N,
            Mx_total_kNm=denoise_moment_kNm(mxt, escala_x),
            My_total_kNm=denoise_moment_kNm(myt, escala_y),
            Mx_stabilizing_kNm=denoise_moment_kNm(mxe, escala_x),
            My_stabilizing_kNm=denoise_moment_kNm(mye, escala_y),
            Hx_kN=hx, Hy_kN=hy, exact_dead_load=exacta,
        ))
    return salida


def _has_horizontal(r: _Resultant) -> bool:
    return abs(r.Hx_kN) > 1e-9 or abs(r.Hy_kN) > 1e-9


# =========================================================================
# Deslizamiento
# =========================================================================


def check_combined_sliding(
    res: list[_Resultant], soil: SoilProfile, self_weight_kN: float, area_m2: float
) -> SlidingResult:
    activos = [r for r in res if _has_horizontal(r)]
    if not activos:
        return SlidingResult(
            H_resultant_kN=0.0, Hx_kN=0.0, Hy_kN=0.0, N_total_kN=0.0,
            mu_used=None, friction_resistance_kN=None, cohesion_resistance_kN=None,
            total_resistance_kN=None, FS_obtained=None, FS_required=soil.FS_sliding_required,
            governing_combo=None, status=CheckStatus.PASS,
            message="No aplicable: ninguna combinación de servicio declara fuerzas horizontales.",
            equation_substituted="Hx = Hy = 0 en todas las combinaciones de servicio.",
            code_reference="E.050 art. 17.1 (cargas de servicio)",
        )

    fs_required, fs_source = _fs_sliding_required(soil.FS_sliding_required)
    falta = (
        ["mu_friction_soil_concrete (coeficiente de fricción suelo-concreto, E.020 art. 22.2)"]
        if soil.mu_friction_soil_concrete is None else []
    )

    def _N(r: _Resultant) -> float:
        return r.N_stabilizing_kN + self_weight_kN

    # Gobierna la de mayor H respecto de su N, que es la de menor FS.
    gob = max(activos, key=lambda r: (r.H_kN / _N(r)) if _N(r) > 0 else float("inf"))
    H, N = gob.H_kN, _N(gob)

    if falta:
        return SlidingResult(
            H_resultant_kN=H, Hx_kN=gob.Hx_kN, Hy_kN=gob.Hy_kN, N_total_kN=N,
            mu_used=None, friction_resistance_kN=None, cohesion_resistance_kN=None,
            total_resistance_kN=None, FS_obtained=None, FS_required=fs_required,
            governing_combo=gob.name, status=CheckStatus.NOT_VERIFIED,
            message=(
                f"DESLIZAMIENTO NO VERIFICADO: falta {falta[0]}. La resultante de la "
                f"combinación {gob.name} aplica H = {H:.1f} kN sobre N = {N:.1f} kN. "
                f"No se asume ningún valor."
            ),
            missing_parameters=falta,
            equation_substituted=f"H = {H:.2f} kN, N = {N:.2f} kN; falta {falta[0]}",
            code_reference=(
                "E.050 art. 17.1; E.020 art. 22.2 (μ del proyectista); FS 1,50: criterio del "
                "programa (D10-2b), más estricto que E.020 art. 22.1 (1,25)"
            ),
        )

    mu = soil.mu_friction_soil_concrete
    friccion = mu * N
    cohesion = soil.cohesion_kPa * area_m2 if soil.cohesion_kPa is not None else 0.0
    resistencia = friccion + cohesion
    fs = resistencia / H if H > 0 else float("inf")

    if fs >= fs_required and not gob.exact_dead_load:
        estado = CheckStatus.NOT_VERIFIED
        mensaje = (
            f"DESLIZAMIENTO NO VERIFICADO: FS = {fs:.2f} >= {fs_required:.2f} ({fs_source}) "
            f"con la carga total de la combinación {gob.name}. {E020_DEAD_LOAD_ONLY_NOTE}"
        )
    elif fs >= fs_required:
        estado = CheckStatus.PASS
        mensaje = (
            f"Deslizamiento cumple: FS = {fs:.2f} >= {fs_required:.2f} ({fs_source}), con solo "
            f"la carga muerta como estabilizante (E.020 art. 20.1), combinación {gob.name}."
        )
    else:
        estado = CheckStatus.FAIL
        mensaje = (
            f"DESLIZAMIENTO NO CUMPLE: FS = {fs:.2f} < {fs_required:.2f} requerido "
            f"(combinación {gob.name}). Resistencia {resistencia:.1f} kN frente a H = {H:.1f} kN. "
            f"Faltan {(H * fs_required - resistencia):.1f} kN de resistencia."
        )

    return SlidingResult(
        H_resultant_kN=H, Hx_kN=gob.Hx_kN, Hy_kN=gob.Hy_kN, N_total_kN=N,
        mu_used=mu, friction_resistance_kN=friccion,
        cohesion_resistance_kN=cohesion if soil.cohesion_kPa is not None else None,
        total_resistance_kN=resistencia, FS_obtained=fs, FS_required=fs_required,
        governing_combo=gob.name, status=estado, message=mensaje,
        equation_substituted=(
            f"H = sqrt({gob.Hx_kN:.1f}² + {gob.Hy_kN:.1f}²) = {H:.2f} kN (resultante de todas "
            f"las columnas) | "
            + (f"N = CM + no muertas desfavorables + peso propio = {N:.2f} kN (E.020 art. 20.1) | "
               if gob.exact_dead_load
               else f"N = {gob.P_total_kN:.1f} + {self_weight_kN:.1f} = {N:.2f} kN (cota superior) | ")
            + f"F_fricción = μ·N = {mu:.3f}·{N:.2f} = {friccion:.2f} kN"
            + (f" | F_cohesión = c·A = {soil.cohesion_kPa:.1f}·{area_m2:.3f} = {cohesion:.2f} kN"
               if soil.cohesion_kPa is not None else " | cohesión no proporcionada: no se considera")
            + f" | FS = {resistencia:.2f}/{H:.2f} = {fs:.3f} (requerido {fs_required:.2f})"
        ),
        code_reference=(
            "E.050 art. 17.1 (cargas de servicio); E.020 art. 20.1 (solo carga muerta); "
            + (
                "FS adoptado por el proyectista" if soil.FS_sliding_required is not None
                else "FS 1,50: criterio del programa (D10-2b), más estricto que E.020 art. 22.1 (1,25)"
            )
        ),
    )


# =========================================================================
# Volcamiento
# =========================================================================


def _check_overturning_axis(
    res: list[_Resultant], soil: SoilProfile, self_weight_kN: float,
    dimension_m: float, h_m: float, axis: str,
) -> CombinedOverturningResult:
    activos = [r for r in res if _has_horizontal(r)]
    if not activos:
        return CombinedOverturningResult(
            axis=axis, pivot_description="No aplicable",
            N_total_kN=0.0, stabilizing_moment_kNm=0.0, applied_moment_kNm=0.0,
            horizontal_force_kN=0.0, horizontal_lever_arm_m=0.0, overturning_moment_kNm=0.0,
            FS_obtained=None, FS_required=soil.FS_overturning_required, governing_combo=None,
            status=CheckStatus.PASS,
            message=(
                f"No aplicable en el eje {axis}: ninguna combinación de servicio declara "
                f"fuerza horizontal. {SCOPE_NOTE}"
            ),
            equation_substituted="H = 0 en todas las combinaciones de servicio.",
            code_reference="E.050 art. 17.1",
            applied_moment_total_kNm=0.0, applied_moment_dead_kNm=0.0, envelope_reading="TOTAL",
        )

    def _partes(r: _Resultant) -> tuple[float, float, float]:
        """(|M| total, |M| estabilizante, |H|) en este eje."""
        if axis == "X":
            return abs(r.Mx_total_kNm), abs(r.Mx_stabilizing_kNm), abs(r.Hx_kN)
        return abs(r.My_total_kNm), abs(r.My_stabilizing_kNm), abs(r.Hy_kN)

    def _valores(r: _Resultant):
        m_total, m_dead, h_force = _partes(r)
        # ENVOLVENTE (opción B): la peor de las dos lecturas.
        m_aplicado = max(m_total, m_dead)
        lectura = "TOTAL" if m_total >= m_dead else "ESTABILIZANTE"
        N = r.N_stabilizing_kN + self_weight_kN
        m_estab = N * dimension_m / 2.0
        m_volc = m_aplicado + h_force * h_m
        fs = m_estab / m_volc if m_volc > 0 else float("inf")
        return m_total, m_dead, m_aplicado, lectura, h_force, N, m_estab, m_volc, fs

    def _fs_req(r: _Resultant) -> float:
        return _fs_overturning_required(r.as_combination(), soil.FS_overturning_required)[0]

    # Un eje sin momento ni fuerza horizontal PROPIOS no tiene volcamiento que verificar:
    # su FS sería infinito. Se declara no aplicable, igual que en la zapata aislada, en
    # lugar de emitir un número sin significado.
    if all(max(_partes(r)[0], _partes(r)[1]) == 0.0 and _partes(r)[2] == 0.0 for r in activos):
        return CombinedOverturningResult(
            axis=axis, pivot_description="No aplicable",
            N_total_kN=0.0, stabilizing_moment_kNm=0.0, applied_moment_kNm=0.0,
            horizontal_force_kN=0.0, horizontal_lever_arm_m=0.0, overturning_moment_kNm=0.0,
            FS_obtained=None, FS_required=soil.FS_overturning_required, governing_combo=None,
            status=CheckStatus.PASS,
            message=(
                f"No aplicable en el eje {axis}: la resultante no produce momento ni fuerza "
                f"horizontal en esa dirección."
            ),
            equation_substituted=f"M_{axis.lower()} = 0 y H_{axis.lower()} = 0 en todas las combinaciones.",
            code_reference="E.050 art. 17.1",
            applied_moment_total_kNm=0.0, applied_moment_dead_kNm=0.0, envelope_reading="TOTAL",
        )

    gob = min(activos, key=lambda r: _valores(r)[8] / _fs_req(r))
    m_total, m_dead, m_aplicado, lectura, h_force, N, m_estab, m_volc, fs = _valores(gob)
    fs_required, fs_source = _fs_overturning_required(
        gob.as_combination(), soil.FS_overturning_required
    )

    pivote = (
        f"Arista inferior de la zapata perpendicular al eje {axis}, a {dimension_m / 2:.3f} m "
        f"del centroide. {NO_PASSIVE_NOTE}"
    )

    if fs >= fs_required and not gob.exact_dead_load:
        estado = CheckStatus.NOT_VERIFIED
        mensaje = (
            f"VOLCAMIENTO EJE {axis} NO VERIFICADO: FS = {fs:.2f} >= {fs_required:.2f} "
            f"({fs_source}) con la carga total de la combinación {gob.name}. "
            f"{E020_DEAD_LOAD_ONLY_NOTE}"
        )
    elif fs >= fs_required:
        estado = CheckStatus.PASS
        mensaje = (
            f"Volcamiento eje {axis} cumple: FS = {fs:.2f} >= {fs_required:.2f} ({fs_source}, "
            f"combinación {gob.name}), con solo la carga muerta como estabilizante "
            f"(E.020 art. 20.1) y la lectura {lectura} de la envolvente."
        )
    else:
        estado = CheckStatus.FAIL
        mensaje = (
            f"VOLCAMIENTO EJE {axis} NO CUMPLE: FS = {fs:.2f} < {fs_required:.2f} requerido "
            f"({fs_source}, combinación {gob.name}). M_estabilizador = {m_estab:.1f} kN·m frente "
            f"a M_volcador = {m_volc:.1f} kN·m (lectura {lectura} de la envolvente)."
        )

    return CombinedOverturningResult(
        axis=axis, pivot_description=pivote, N_total_kN=N,
        stabilizing_moment_kNm=m_estab, applied_moment_kNm=m_aplicado,
        horizontal_force_kN=h_force, horizontal_lever_arm_m=h_m,
        overturning_moment_kNm=m_volc, FS_obtained=fs, FS_required=fs_required,
        governing_combo=gob.name, status=estado, message=mensaje,
        equation_substituted=(
            f"Punto de giro: {pivote} | "
            f"M_estab = N·dim/2 = {N:.1f}·{dimension_m / 2:.3f} = {m_estab:.2f} kN·m "
            + ("(N: carga muerta y no muertas desfavorables, E.020 art. 20.1) | "
               if gob.exact_dead_load
               else f"(N = {gob.P_total_kN:.1f}+{self_weight_kN:.1f}, cota superior) | ")
            + f"envolvente |M|: total {m_total:.2f} / estabilizante {m_dead:.2f} "
            f"→ {m_aplicado:.2f} kN·m ({lectura}) | "
            f"M_volc = |M| + |H|·h = {m_aplicado:.2f} + {h_force:.2f}·{h_m:.3f} = {m_volc:.2f} kN·m | "
            f"FS = {fs:.3f} (requerido {fs_required:.2f}, {fs_source})"
        ),
        code_reference=(
            "E.050 art. 17.1 (cargas de servicio); E.020 art. 20.1 (solo carga muerta); "
            + (
                "FS adoptado por el proyectista" if soil.FS_overturning_required is not None
                else "FS 1,50: criterio del programa (D10-2b), más estricto que E.030 art. 64.2 "
                     "(1,20 por volteo sísmico)"
                if gob.includes_seismic_loads
                else "FS 1,50: criterio del programa (D10-2b), coincide con E.020 art. 21"
            )
        ),
        applied_moment_total_kNm=m_total, applied_moment_dead_kNm=m_dead,
        envelope_reading=lectura,
    )


def check_combined_stability(
    layout: CombinedFootingLayout, soil: SoilProfile, self_weight_kN: float,
    B_m: float, L_m: float, h_m: float,
) -> CombinedStabilityResult:
    res = resultants(layout)
    return CombinedStabilityResult(
        sliding=check_combined_sliding(res, soil, self_weight_kN, B_m * L_m),
        overturning_x=_check_overturning_axis(res, soil, self_weight_kN, B_m, h_m, "X"),
        overturning_y=_check_overturning_axis(res, soil, self_weight_kN, L_m, h_m, "Y"),
        applicable=any(_has_horizontal(r) for r in res),
    )


HYPOTHESES = [RESULTANT_NOTE, ECCENTRICITY_TERM_NOTE, ENVELOPE_NOTE, D10_2B_ADOPTED_NOTE, SCOPE_NOTE]
SEISMIC_HYPOTHESES = [E030_OVERTURNING_INTERPRETATION, E030_UNREDUCED_NOTE]
