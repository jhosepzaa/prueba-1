"""Interfaces normativas intercambiables.

El motor de dimensionamiento (engine/foundation, engine/soil) llama únicamente a
estas interfaces, nunca a un módulo `peru.*` en forma directa ni a un `if pais ==
"peru"` disperso. Esto es lo que permite agregar `/codes/aci/` en el futuro sin
tocar el resto del motor (sección 16 y 18 del encargo original).

Cada método debe devolver, además del valor numérico, los metadatos necesarios
para construir un CalculationTraceEntry (fórmula simbólica, referencia normativa)
-- se hace mediante los NamedTuple `*Result` definidos aquí, que las
implementaciones concretas (engine/codes/peru/*) rellenan con su propia cita.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple


class PhiFactors(NamedTuple):
    flexion: float
    cortante: float
    code_reference: str


class EquationResult(NamedTuple):
    """Resultado de una única ecuación normativa, listo para volcarse a un
    CalculationTraceEntry."""

    value: float
    unit: str
    equation_symbolic: str
    equation_substituted: str
    code_reference: str


class PunchingVcResult(NamedTuple):
    """Resultado del cálculo de Vc por punzonamiento, con las TRES ecuaciones
    evaluadas por separado además de la gobernante. Se exponen todas porque el
    ingeniero necesita ver cuál controla y por qué margen (auditoría solicitada)."""

    vc_kN: float  # el mínimo de las tres = valor de diseño
    vc_a_kN: float  # ec. 11-41, término de beta (forma de la columna)
    vc_b_kN: float  # ec. 11-42, término de alpha_s (posición de la columna)
    vc_c_kN: float  # ec. 11-43, techo constante
    governing_equation: str
    beta_col: float
    alpha_s: float
    equation_symbolic: str
    equation_substituted: str
    code_reference: str


class IConcreteCode(ABC):
    code_name: str

    @abstractmethod
    def phi_factors(self) -> PhiFactors: ...

    @abstractmethod
    def fc_min_MPa(self) -> tuple[float, str]:
        """Devuelve (valor_minimo, referencia_normativa)."""

    @abstractmethod
    def cover_footing_mm(self) -> tuple[float, str]:
        """Recubrimiento mínimo por defecto para zapatas apoyadas en suelo."""

    @abstractmethod
    def one_way_shear_vc(self, fc_MPa: float, bw_m: float, d_m: float) -> EquationResult:
        """Vc para cortante unidireccional (viga ancha) sin aporte de Nu significativo."""

    @abstractmethod
    def punching_shear_vc(
        self, fc_MPa: float, bo_m: float, d_m: float, beta_col: float, alpha_s: float
    ) -> PunchingVcResult:
        """Vc para punzonamiento: las tres ecuaciones evaluadas y la gobernante."""

    @abstractmethod
    def rho_min_temperature(self, fy_MPa: float, bar_type: str) -> tuple[float, str]:
        """Cuantía mínima de retracción/temperatura aplicable como As_min en zapatas."""

    @abstractmethod
    def min_depth_rule(self, h_total_m: float, d_m: float, on_soil: bool) -> EquationResult:
        """Regla de peralte mínimo. `value` es la magnitud gobernante ya resuelta
        según la interpretación configurada, para que quien llama solo tenga que
        compararla contra `min_depth_threshold_m()`.
        Ver docs/normativa/peralte_minimo_zapatas.md."""

    @abstractmethod
    def min_depth_threshold_m(self) -> float:
        """Umbral de peralte mínimo para zapatas apoyadas sobre suelo."""

    @abstractmethod
    def short_direction_steel_fraction(self, beta: float) -> EquationResult:
        """Fracción del acero en franja central, dirección corta (ec. 15-1)."""
