# -*- coding: utf-8 -*-
"""E3 — Zapata conectada (strap footing). Structville, «Design of strap footing», EC2.

Datos: C1 y C2 de 300 × 300 mm, 4 m entre ejes; C1 con su eje a 0,30 m del lindero (lo
implica «3.3·R1 = 450·4» con la zapata de 2,0 m a lo largo de la viga); cargas de servicio
450 y 600 kN, últimas 617 y 822 kN; capacidad 150 kPa; zapata exterior 2,0 (a lo largo) ×
1,85 m, interior 1,85 × 1,85 m; viga 300 × 600 mm.
Resultado publicado: R1 = 545,45 kN y R2 = 504,55 kN (servicio), 747,87 y 691,23 kN
(últimas); momento negativo de la viga 416,474 kN·m.

Se compara la ESTÁTICA (el reparto del par y la viga), que no depende de la norma. El
diseño de los elementos se hace con E.060, y ahí EC2 y E.060 no son comparables.
"""
import sys

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[2]  # raíz del proyecto
sys.path.insert(0, str(RAIZ))
from api import mapping, schemas  # noqa: E402
from api.server import _build_connected_layout  # noqa: E402
from engine.codes.peru.e060_concrete import E060ConcreteCode  # noqa: E402
from engine.domain.search_parameters import DepthSearchParameters  # noqa: E402
from engine.foundation.connected_solver import solve_connected_footing  # noqa: E402
from engine.optimization.connected_generator import ConnectedFootingGeometry  # noqa: E402

combos = lambda Ps, Pu: [{"name": "S1", "type": "SERVICIO", "P_kN": Ps},
                         {"name": "U1", "type": "FACTORIZADA", "P_kN": Pu}]
PET = {
    "project_name": "Structville strap",
    "analysis_model": "ARTICULADO", "couple_transfer_mode": "EQUILIBRIO_EN_CIMENTACION",
    "exterior": {"label": "C1", "shape": "cuadrada", "bx_m": 0.30, "by_m": 0.30,
                 "hook_type_x": "90", "combinations": combos(450.0, 617.0)},
    "interior": {"label": "C2", "shape": "cuadrada", "bx_m": 0.30, "by_m": 0.30,
                 "combinations": combos(600.0, 822.0)},
    "anchor": {"edge": "X_MIN", "face_clearance_m": 0.15},
    "beam": {"b_m": 0.30, "h_m": 0.60, "d_m": 0.54, "support_mode": "SIN_APOYO",
             "self_weight_mode": "DESPRECIADO"},
    "axis_distance_m": 4.0, "longitudinal_axis": "X",
    "materials": {"fc_MPa": 25.0, "fy_MPa": 420.0},
    "soil": {"qadm_kPa": 150.0, "pressure_basis": "NETA", "gamma_kNm3": 18.0, "Df_m": 1.0},
    "search": {"auto_ranges": True},
}

if __name__ == "__main__":
    req = schemas.ConnectedDesignRequest(**PET)
    layout = _build_connected_layout(req)
    u = req.units
    concrete, steel = mapping.build_materials(req.materials, u)
    r = solve_connected_footing(
        layout,
        ConnectedFootingGeometry(exterior_B_m=2.0, exterior_L_m=1.85, exterior_h_m=0.40,
                                 interior_B_m=1.85, interior_L_m=1.85, interior_h_m=0.40),
        soil=mapping.build_soil(req.soil, u), concrete=concrete, steel=steel,
        code=E060ConcreteCode(), contact_model=mapping.contact_model_for(req.soil),
        depth_params=DepthSearchParameters(h_min_m=0.4, h_max_m=0.4, h_step_m=0.05),
    )
    print("estado", r.overall_status.value)
    for d in r.statics:
        print(f"[{d.combo_name}] R_ext = {d.R_ext_kN:.2f} kN · ΔP = {d.delta_P_kN:.2f} kN · "
              f"P_ext_corr = {d.P_ext_corrected_kN:.2f} · P_int_corr = {d.P_int_corrected_kN:.2f}")
    for b in r.beam_statics:
        print(f"[viga {b.combo_name}] M⁻max = {b.M_max_negative_kNm:.2f} kN·m · M⁺max = {b.M_max_positive_kNm:.2f} · V = {b.V_design_kN:.2f} kN")
    for e in r.trace.entries:
        if e.id.startswith(("couple_", "beam_statics")) or "contact" in e.id:
            print(f"   [{e.scope}/{e.id}] {str(e.equation_substituted)[:420]}")
