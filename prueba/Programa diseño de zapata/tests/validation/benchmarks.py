"""Fase 6 — registro de benchmarks de validación del MOTOR contra referencias externas.

REGLAS DEL REGISTRO
===================
1. Cada valor de referencia procede de una fuente ya incorporada al proyecto y ya
   afirmada por algún test: los apuntes CR2-93-134 (Aragón) o los cálculos a mano de los
   golden cases. Aquí no se introduce ningún valor nuevo; se cita el test de origen.
2. El valor calculado sale del MOTOR, no de un ayudante de test que reproduzca el método
   del libro. Donde el test de origen usaba un ayudante propio, este registro no lo copia.
3. La tolerancia es la que el test de origen ya aceptaba.
4. Las diferencias explicadas y no adoptadas se registran como tales
   (`documented_difference`), con su explicación, en lugar de ajustarse al libro.

Unidades de presentación: las del propio benchmark (t, t·m, t/m² para Aragón; kN, kPa,
m² para los golden cases).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

TONF = 9.80665


@dataclass(frozen=True)
class Benchmark:
    id: str
    source: str
    origin_test: str
    quantity: str
    unit: str
    reference: float
    tolerance_abs: float
    compute: Callable[[], float]
    documented_difference: str = ""
    # Solo para diferencias documentadas: el valor que el motor da y que se decidió
    # mantener, con la tolerancia del test de origen. La diferencia NO se absorbe
    # ensanchando la tolerancia contra el libro.
    expected_engine_value: float | None = None
    expected_engine_tolerance: float = 0.0

    def engine_value(self) -> float:
        return self.compute()


# ---------------------------------------------------------------------------
# Aragón, problema de aplicación 1 — zapata conectada, modelo ARTICULADO + PAR_PURO
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _p1_reparto(Ms: float):
    from engine.domain.connected_layout import CoupleTransferMode
    from tests.test_connected_statics_phase4a import _reparto_aragon_p1_modo

    return _reparto_aragon_p1_modo(CoupleTransferMode.PAR_PURO_EN_ZAPATA, Ms)


@lru_cache(maxsize=None)
def _p1_viga_diseno():
    """Misma construcción que `test_aragon_p1_la_viga_en_modo_PAR_PURO_reproduce_el_cortante_del_libro`."""
    from engine.analysis.connected_statics import distribute_couple
    from engine.analysis.connecting_beam_statics import solve_connecting_beam
    from engine.domain.column import Column
    from engine.domain.connected_layout import (
        AnalysisModel, ConnectedElement, ConnectedFootingLayout, CoupleTransferMode, EdgeAnchor,
    )
    from tests.test_connected_statics_phase4a import (
        ARAGON_P1 as d, SIGNO_MOMENTO_LIBRO, TONF_TO_KN, _SUELO, _huellas, _loads, _viga,
    )

    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    M = SIGNO_MOMENTO_LIBRO * (d["M_ext"] - d["Ms_ext"]) * TONF_TO_KN
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        couple_transfer_mode=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
        exterior=ConnectedElement(label="Z1", column=col,
                                  loads=_loads(d["P_ext"] * TONF_TO_KN, d["P_ext"] * TONF_TO_KN,
                                               Mx_serv=M, Mx_fact=M),
                                  anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=0.0)),
        interior=ConnectedElement(label="Z2", column=col,
                                  loads=_loads(d["P_int"] * TONF_TO_KN, d["P_int"] * TONF_TO_KN)),
        beam=_viga(), axis_distance_m=d["S"], longitudinal_axis="X",
    )
    r = distribute_couple(lay, _huellas(lay, d["L1"], L_transv=d["B1"]),
                          lay.exterior.loads.service[0], lay.interior.loads.service[0], _SUELO)
    return solve_connecting_beam(lay, r)


@lru_cache(maxsize=None)
def _p1_viga_cara():
    """Misma construcción que `test_aragon_p1_el_momento_a_la_cara_no_se_reproduce_y_esta_documentado`."""
    from engine.analysis.connecting_beam_statics import solve_connecting_beam
    from engine.domain.column import Column
    from engine.domain.connected_layout import (
        AnalysisModel, ConnectedElement, ConnectedFootingLayout, CoupleTransferMode, EdgeAnchor,
    )
    from tests.test_connected_statics_phase4a import ARAGON_P1 as d, _loads, _viga

    r = _p1_reparto(-d["Ms_ext"])
    col = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    lay = ConnectedFootingLayout(
        analysis_model=AnalysisModel.ARTICULADO,
        couple_transfer_mode=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
        exterior=ConnectedElement(label="Z1", column=col, loads=_loads(1.0, 1.0),
                                  anchor=EdgeAnchor(edge="X_MIN")),
        interior=ConnectedElement(label="Z2", column=col, loads=_loads(1.0, 1.0)),
        beam=_viga(), axis_distance_m=d["S"], longitudinal_axis="X",
    )
    return solve_connecting_beam(lay, r)


_P1 = "Apuntes CR2-93-134 §3.6, problema de aplicación 1"
_P1_TEST = "tests/test_connected_statics_phase4a.py"

ARAGON_P1_BENCHMARKS = [
    Benchmark("P1-Mpar-grav", _P1, _P1_TEST, "Momento del par (gravedad)", "t·m", -32.75, 0.02,
              lambda: _p1_reparto(0.0).M_couple_kNm / TONF),
    Benchmark("P1-dP-grav", _P1, _P1_TEST, "Transferencia ΔP (gravedad)", "t", 5.45, 0.02,
              lambda: abs(_p1_reparto(0.0).delta_P_kN) / TONF),
    Benchmark("P1-Mpar-sismo+", _P1, _P1_TEST, "Momento del par (sismo +)", "t·m", 57.25, 0.02,
              lambda: _p1_reparto(90.0).M_couple_kNm / TONF),
    Benchmark("P1-dP-sismo+", _P1, _P1_TEST, "Transferencia ΔP (sismo +)", "t", 9.54, 0.02,
              lambda: abs(_p1_reparto(90.0).delta_P_kN) / TONF),
    Benchmark("P1-Mpar-sismo-", _P1, _P1_TEST, "Momento del par (sismo −)", "t·m", -122.75, 0.02,
              lambda: _p1_reparto(-90.0).M_couple_kNm / TONF),
    Benchmark("P1-dP-sismo-", _P1, _P1_TEST, "Transferencia ΔP (sismo −)", "t", 20.45, 0.02,
              lambda: abs(_p1_reparto(-90.0).delta_P_kN) / TONF),
    Benchmark("P1-Vu-viga", _P1, _P1_TEST, "Vu de la viga (1,25·V)", "t", 25.6, 0.1,
              lambda: 1.25 * _p1_viga_diseno().V_design_kN / TONF),
    Benchmark("P1-Mu-eje", _P1, _P1_TEST, "Mu⁻ de la viga en el eje (1,25·M)", "t·m", 153.4, 0.2,
              lambda: 1.25 * _p1_viga_diseno().M_max_negative_kNm / TONF),
    Benchmark("P1-Mu-cara", _P1, _P1_TEST, "Mu⁻ de la viga a la cara de la columna", "t·m",
              140.6, 0.2,
              lambda: 1.25 * abs(_p1_viga_cara().M_at_exterior_column_face_kNm) / TONF,
              documented_difference=(
                  "El motor da 147,0 t·m. El libro mide el brazo desde el lindero: "
                  "153,4·(1 − 0,50/6,00) = 140,6. Es otra convención de cuerpo libre, no un "
                  "error; se decidió no adoptarla (decisión cerrada en 4D)."
              ),
              expected_engine_value=147.0, expected_engine_tolerance=0.3),
]


# ---------------------------------------------------------------------------
# Aragón, problema de aplicación 2 — zapata conectada, modelo CUERPO_RIGIDO
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _p2(geo: str, P_ext=95.0, M_ext=6.0, P_int=180.0, M_int=-6.5):
    import tests.test_connected_rigid_body_phase4c as m

    return m._resolver(getattr(m, geo), P_ext, M_ext, P_int, M_int)


_P2 = "Apuntes CR2-93-134 §3.6, problema de aplicación 2"
_P2_TEST = "tests/test_connected_rigid_body_phase4c.py"

ARAGON_P2_BENCHMARKS = [
    Benchmark("P2-A", _P2, _P2_TEST, "Área de apoyo (geometría final)", "m²", 32.46, 0.005,
              lambda: _p2("FINAL")[1].total_area_m2),
    Benchmark("P2-I", _P2, _P2_TEST, "Inercia de la sección compuesta", "m⁴", 320.36, 0.05,
              lambda: _p2("FINAL")[1].inertia_m4),
    Benchmark("P2-smin-CMCV", _P2, _P2_TEST, "σ mín, CM+CV", "t/m²", 8.14, 0.10,
              lambda: _p2("FINAL")[2].sigma_min_kPa / TONF),
    Benchmark("P2-smax-CMCV", _P2, _P2_TEST, "σ máx, CM+CV", "t/m²", 11.63, 0.15,
              lambda: _p2("FINAL")[2].sigma_max_kPa / TONF),
    Benchmark("P2-smin-CS+", _P2, _P2_TEST, "σ mín, CM+CV+CS", "t/m²", 5.01, 0.10,
              lambda: _p2("FINAL", 75.0, 146.0, 200.0, 143.5)[2].sigma_min_kPa / TONF),
    Benchmark("P2-smax-CS+", _P2, _P2_TEST, "σ máx, CM+CV+CS", "t/m²", 14.96, 0.15,
              lambda: _p2("FINAL", 75.0, 146.0, 200.0, 143.5)[2].sigma_max_kPa / TONF),
    Benchmark("P2-smin-CS-", _P2, _P2_TEST, "σ mín, CM+CV−CS", "t/m²", 1.32, 0.10,
              lambda: _p2("FINAL", 115.0, -134.0, 160.0, -156.5)[2].sigma_min_kPa / TONF),
    Benchmark("P2-smax-CS-", _P2, _P2_TEST, "σ máx, CM+CV−CS", "t/m²", 18.25, 0.15,
              lambda: _p2("FINAL", 115.0, -134.0, 160.0, -156.5)[2].sigma_max_kPa / TONF),
    Benchmark("P2-smax-predim", _P2, _P2_TEST, "σ máx del predimensionamiento (se rechaza)",
              "t/m²", 18.91, 0.10, lambda: _p2("PREDIM")[2].sigma_max_kPa / TONF),
]


# ---------------------------------------------------------------------------
# Golden cases — zapata aislada, cálculo a mano en el docstring de cada caso
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _golden(modulo: str):
    import importlib

    return importlib.import_module(f"tests.golden_cases.{modulo}")._candidate()


_G = "Golden case: cálculo a mano en el docstring"

GOLDEN_BENCHMARKS = [
    Benchmark("G03-W", _G + " (caso 03)", "tests/golden_cases/test_case_03_biaxial_moment.py",
              "Peso propio total", "kN", 197.568, 197.568e-6,
              lambda: _golden("test_case_03_biaxial_moment").self_weight.W_total_kN),
    Benchmark("G03-qmax", _G + " (caso 03)", "tests/golden_cases/test_case_03_biaxial_moment.py",
              "q máx (flexión biaxial)", "kPa", 127.241, 127.241e-4,
              lambda: _golden("test_case_03_biaxial_moment").contact_pressure.qmax_kPa),
    Benchmark("G03-qmin", _G + " (caso 03)", "tests/golden_cases/test_case_03_biaxial_moment.py",
              "q mín (flexión biaxial)", "kPa", 50.710, 50.710e-4,
              lambda: _golden("test_case_03_biaxial_moment").contact_pressure.qmin_kPa),
    Benchmark("G06-bo", _G + " (caso 06)", "tests/golden_cases/test_case_06_punching_fail.py",
              "Perímetro crítico bo", "m", 2.8238, 2.8238e-4,
              lambda: _golden("test_case_06_punching_fail").punching.bo_m),
    Benchmark("G06-Vu", _G + " (caso 06)", "tests/golden_cases/test_case_06_punching_fail.py",
              "Vu de punzonamiento", "kN", 1369.1, 1369.1e-3,
              lambda: _golden("test_case_06_punching_fail").punching.Vu_kN),
    Benchmark("G06-phiVc", _G + " (caso 06)", "tests/golden_cases/test_case_06_punching_fail.py",
              "φVc de punzonamiento", "kN", 1110.5, 1110.5e-3,
              lambda: _golden("test_case_06_punching_fail").punching.phi_Vc_kN),
    Benchmark("G08-Vu", _G + " (caso 08)", "tests/golden_cases/test_case_08_oneway_shear_fail.py",
              "Vu de cortante unidireccional", "kN", 1708.35, 1708.35e-3,
              lambda: _golden("test_case_08_oneway_shear_fail").shear_x.Vu_kN),
    Benchmark("G08-phiVc", _G + " (caso 08)", "tests/golden_cases/test_case_08_oneway_shear_fail.py",
              "φVc de cortante unidireccional", "kN", 1374.0, 1374.0e-3,
              lambda: _golden("test_case_08_oneway_shear_fail").shear_x.phi_Vc_kN),
    Benchmark("G08-qmax", _G + " (caso 08)", "tests/golden_cases/test_case_08_oneway_shear_fail.py",
              "q máx", "kPa", 248.62, 248.62e-3,
              lambda: _golden("test_case_08_oneway_shear_fail").contact_pressure.qmax_kPa),
]

# ---------------------------------------------------------------------------
# Aragón §3.5 — zapata combinada
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _aragon_3_5():
    import tests.test_combined_footing_phase2 as m

    return m._resolver(m._aragon_3_5(), h=0.80, qadm=1.5 * 98.0665)


def _q_3_5_referencia() -> float:
    """Referencia DERIVADA del libro, igual que en el test de origen: la presión del libro
    (363 t sobre 7,20 × 3,80 m) corregida por la diferencia DECLARADA de peso propio —el
    libro estima 33 t y no incluye relleno—. No es un número del libro sin más."""
    q_libro = 363.0 / (7.20 * 3.80) / 10.0
    pp_motor = (7.20 * 3.80 * 0.80 * 24.0 + (1.50 - 0.80) * 7.20 * 3.80 * 18.0) / TONF
    return q_libro * (330.0 + pp_motor) / (330.0 + 33.0)


_Q35 = _q_3_5_referencia()

COMBINED_BENCHMARKS = [
    Benchmark("K35-qmax", "Apuntes CR2-93-134 §3.5, zapata combinada (referencia ajustada por "
              "el peso propio declarado)", "tests/test_combined_footing_phase2.py",
              "q máx de servicio", "kg/cm²", _Q35, 0.01 * _Q35,
              lambda: _aragon_3_5().contact_pressure.qmax_kPa / 98.0665),
]

ALL_BENCHMARKS: list[Benchmark] = (
    ARAGON_P1_BENCHMARKS + ARAGON_P2_BENCHMARKS + COMBINED_BENCHMARKS + GOLDEN_BENCHMARKS
)
