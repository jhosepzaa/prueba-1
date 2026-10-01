"""Implementación E.060 (Perú) de IConcreteCode.

Cada ecuación cita artículo y número de ecuación tal como se verificó en
`Norma E.060 Concreto armado.pdf` (ver docs/normativa/referencias_e060_e050.md).
Ningún coeficiente de este archivo proviene de memoria general de ACI: todos
fueron confirmados contra el texto del PDF adjuntado por el usuario.
"""

from __future__ import annotations

import math
from enum import Enum

from engine.codes.base import EquationResult, IConcreteCode, PhiFactors, PunchingVcResult
from engine.units.si_units import m_to_mm, n_to_kn

CODE_NAME = "E.060"

# E.060 §15.7 -- ver docs/normativa/peralte_minimo_zapatas.md para el razonamiento
# completo de la interpretación adoptada.
MIN_DEPTH_ON_SOIL_M = 0.300
MIN_DEPTH_ON_PILES_M = 0.400

COVER_FOOTING_ON_SOIL_MM = 75.0  # E.060 §7.7.1 a) (propuesta 2019: 75 mm; antes 70 mm)
FC_MIN_MPA = 17.0  # E.060 §9.4


class MinDepthInterpretation(str, Enum):
    """Cuál magnitud geométrica se compara contra el límite de §15.7.

    EFFECTIVE_DEPTH es la interpretación adoptada por defecto (ver
    docs/normativa/peralte_minimo_zapatas.md): "altura medida sobre el refuerzo
    inferior" = peralte efectivo d. Se mantiene configurable porque es una
    interpretación de ingeniería razonada, no una certeza normativa.
    """

    EFFECTIVE_DEPTH = "EFFECTIVE_DEPTH"
    TOTAL_DEPTH = "TOTAL_DEPTH"


class E060ConcreteCode(IConcreteCode):
    code_name = CODE_NAME

    def __init__(
        self, min_depth_interpretation: MinDepthInterpretation = MinDepthInterpretation.EFFECTIVE_DEPTH
    ) -> None:
        self.min_depth_interpretation = min_depth_interpretation

    def phi_factors(self) -> PhiFactors:
        # E.060 §9.3.2: flexión sin carga axial = 0.90; cortante y torsión = 0.85.
        # La sección es §9.3 "Resistencia de diseño"; §9.4 es "Resistencia mínima del
        # concreto estructural" (f'c >= 17 MPa) y se cita aparte en fc_min_MPa.
        return PhiFactors(flexion=0.90, cortante=0.85, code_reference="E.060 §9.3.2")

    def fc_min_MPa(self) -> tuple[float, str]:
        return FC_MIN_MPA, "E.060 §9.4"

    def cover_footing_mm(self) -> tuple[float, str]:
        return COVER_FOOTING_ON_SOIL_MM, "E.060 §7.7.1 a)"

    def one_way_shear_vc(self, fc_MPa: float, bw_m: float, d_m: float) -> EquationResult:
        """Vc = 0.17 * sqrt(f'c) * bw * d  (ec. 11-3, elementos sin Nu significativo).

        E.060 §15.5 remite el cortante en zapatas ("comportamiento como viga") a
        §11.1-11.5; §11.3.1.1 da la ec. 11-3. Unidades de la ecuación: MPa, mm, N
        -- se convierte aquí en el único punto de conversión de esta ecuación.
        """
        bw_mm = m_to_mm(bw_m)
        d_mm = m_to_mm(d_m)
        vc_N = 0.17 * math.sqrt(fc_MPa) * bw_mm * d_mm
        vc_kN = n_to_kn(vc_N)
        return EquationResult(
            value=vc_kN,
            unit="kN",
            equation_symbolic="Vc = 0.17 * sqrt(f'c) * bw * d",
            equation_substituted=(
                f"Vc = 0.17 * sqrt({fc_MPa:.1f} MPa) * {bw_mm:.0f} mm * {d_mm:.0f} mm "
                f"= {vc_N:.0f} N = {vc_kN:.2f} kN"
            ),
            code_reference="E.060 §11.3.1.1, ec. 11-3 (aplicable a zapatas vía §15.5.1-15.5.2)",
        )

    def punching_shear_vc(
        self, fc_MPa: float, bo_m: float, d_m: float, beta_col: float, alpha_s: float
    ) -> PunchingVcResult:
        """Vc = min de las ecuaciones 11-41, 11-42, 11-43 (E.060 §11.12.2.1).

        Las tres ecuaciones representan tres modos de agotamiento distintos:
          (a) ec. 11-41 -- 0.17*(1+2/beta)*sqrt(f'c)*bo*d
              Penaliza columnas ALARGADAS: con beta grande, la fisura de
              punzonamiento no se reparte uniformemente en el perímetro.
              Solo puede gobernar si beta > 2.
          (b) ec. 11-42 -- 0.083*(alpha_s*d/bo + 2)*sqrt(f'c)*bo*d
              Penaliza perímetros LARGOS respecto de d (bo/d grande), donde el
              comportamiento se acerca al de viga ancha. Gobierna cuando
              alpha_s*d/bo < 2, es decir bo/d > alpha_s/2 (=20 si alpha_s=40).
          (c) ec. 11-43 -- 0.33*sqrt(f'c)*bo*d
              Techo constante; gobierna en el caso compacto habitual de zapatas.

        beta_col: relación lado largo / lado corto de la SECCIÓN DE LA COLUMNA
                  (E.060 §11.12.2.1(a): "beta es la relación del lado largo al
                  lado corto de la sección de la columna").
        alpha_s:  40 columna interior, 30 de borde, 20 de esquina (§11.12.2.1(b)).

        Unidades de las ecuaciones: MPa, mm, N. La conversión desde m/kN ocurre
        aquí, en un único punto.
        """
        bo_mm = m_to_mm(bo_m)
        d_mm = m_to_mm(d_m)
        sqrt_fc = math.sqrt(fc_MPa)

        vc_a_N = 0.17 * (1.0 + 2.0 / beta_col) * sqrt_fc * bo_mm * d_mm
        vc_b_N = 0.083 * (alpha_s * d_mm / bo_mm + 2.0) * sqrt_fc * bo_mm * d_mm
        vc_c_N = 0.33 * sqrt_fc * bo_mm * d_mm

        vc_N = min(vc_a_N, vc_b_N, vc_c_N)
        if vc_N == vc_a_N:
            governing = "11-41"
        elif vc_N == vc_b_N:
            governing = "11-42"
        else:
            governing = "11-43"

        return PunchingVcResult(
            vc_kN=n_to_kn(vc_N),
            vc_a_kN=n_to_kn(vc_a_N),
            vc_b_kN=n_to_kn(vc_b_N),
            vc_c_kN=n_to_kn(vc_c_N),
            governing_equation=governing,
            beta_col=beta_col,
            alpha_s=alpha_s,
            equation_symbolic=(
                "Vc = min[ 0.17*(1+2/beta)*sqrt(f'c)*bo*d ;  "
                "0.083*(alpha_s*d/bo+2)*sqrt(f'c)*bo*d ;  0.33*sqrt(f'c)*bo*d ]"
            ),
            equation_substituted=(
                f"(a) ec.11-41 = 0.17*(1+2/{beta_col:.2f})*sqrt({fc_MPa:.1f})*{bo_mm:.0f}*{d_mm:.0f} = {n_to_kn(vc_a_N):.2f} kN | "
                f"(b) ec.11-42 = 0.083*({alpha_s:.0f}*{d_mm:.0f}/{bo_mm:.0f}+2)*sqrt({fc_MPa:.1f})*{bo_mm:.0f}*{d_mm:.0f} = {n_to_kn(vc_b_N):.2f} kN | "
                f"(c) ec.11-43 = 0.33*sqrt({fc_MPa:.1f})*{bo_mm:.0f}*{d_mm:.0f} = {n_to_kn(vc_c_N):.2f} kN | "
                f"GOBIERNA {governing}: Vc = {n_to_kn(vc_N):.2f} kN"
            ),
            code_reference=f"E.060 §11.12.2.1, ec. {governing} (gobernante de las tres)",
        )

    def rho_min_temperature(self, fy_MPa: float, bar_type: str) -> tuple[float, str]:
        """Ver docs/normativa/as_min_zapatas.md para el razonamiento completo
        (E.060 §10.5.1 excluye zapatas del As_min por Mcr; §10.6 remite a §9.7)."""
        if bar_type == "lisa":
            raise ValueError(
                "E.060 §9.7.2 solo da cuantías para acero corrugado, y §3.5.4.2 no admite barras "
                "lisas como refuerzo de zapatas."
            )
        if fy_MPa >= 420.0:
            return 0.0018, "E.060 §9.7 (barras corrugadas, fy>=420 MPa), vía §10.6 y exclusión de §10.5.1 para zapatas"
        return 0.0020, "E.060 §9.7 (barras corrugadas, fy<420 MPa), vía §10.6 y exclusión de §10.5.1 para zapatas"

    def min_depth_rule(self, h_total_m: float, d_m: float, on_soil: bool) -> EquationResult:
        """Aplica §15.7 según la interpretación configurada. El valor devuelto es
        la magnitud gobernante (la que debe compararse contra el umbral), de modo
        que quien llama nunca tiene que saber cuál interpretación está activa.
        Ver docs/normativa/peralte_minimo_zapatas.md."""
        if not on_soil:
            raise NotImplementedError(
                "Zapatas apoyadas sobre pilotes (E.060 §15.7, límite 400 mm) están "
                "fuera del alcance del MVP."
            )
        threshold = MIN_DEPTH_ON_SOIL_M
        if self.min_depth_interpretation is MinDepthInterpretation.EFFECTIVE_DEPTH:
            governing_value = d_m
            symbolic = "d >= 0.300 m"
            interp_note = "interpretación EFFECTIVE_DEPTH: 'altura medida sobre el refuerzo inferior' = peralte efectivo d"
        else:
            governing_value = h_total_m
            symbolic = "h_total >= 0.300 m"
            interp_note = "interpretación TOTAL_DEPTH: la disposición se aplica al peralte total h"
        return EquationResult(
            value=governing_value,
            unit="m",
            equation_symbolic=symbolic,
            equation_substituted=(
                f"h_total={h_total_m:.3f} m, d={d_m:.3f} m, umbral={threshold:.3f} m ; "
                f"magnitud gobernante={governing_value:.3f} m -- {interp_note}"
            ),
            code_reference=f"E.060 §15.7 ({self.min_depth_interpretation.value}, interpretación documentada)",
        )

    def min_depth_threshold_m(self) -> float:
        return MIN_DEPTH_ON_SOIL_M

    def short_direction_steel_fraction(self, beta: float) -> EquationResult:
        """gamma_s = 2 / (beta + 1)  (ec. 15-1), beta = lado largo / lado corto."""
        gamma_s = 2.0 / (beta + 1.0)
        return EquationResult(
            value=gamma_s,
            unit="adimensional",
            equation_symbolic="gamma_s = 2 / (beta + 1)",
            equation_substituted=f"gamma_s = 2 / ({beta:.3f} + 1) = {gamma_s:.4f}",
            code_reference="E.060 §15.4, ec. 15-1",
        )
