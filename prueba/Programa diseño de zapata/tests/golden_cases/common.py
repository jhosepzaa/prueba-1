"""Insumos comunes a los casos golden -- ver docs/normativa/referencias_e060_e050.md
para las citas de cada disposición usada por el motor."""

from __future__ import annotations

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.soil.contact_pressure import KernCheckModel

CODE = E060ConcreteCode()
CONTACT_MODEL = KernCheckModel()

COLUMN_40x40 = Column(shape="cuadrada", bx_m=0.40, by_m=0.40)
CONCRETE_21 = MaterialConcrete(fc_MPa=21.0, unit_weight_kNm3=24.0)
STEEL_420 = MaterialSteel(fy_MPa=420.0, bar_type="corrugada")
SOIL_150_BRUTA = SoilProfile(
    qadm_kPa=150.0,
    pressure_basis=PressureBasis.BRUTA,
    gamma_kNm3=18.0,
    Df_m=1.20,
    source_notes="Dato de entrada del caso golden -- no proviene de un EMS real.",
)
DEPTH_PARAMS_DEFAULT = DepthSearchParameters(h_min_m=0.30, h_max_m=0.80, h_step_m=0.05)
