# -*- coding: utf-8 -*-
"""E2: resolver la geometría de Wight 15-5 con el motor para leer la traza completa aunque
el barrido la rechace. Solo lectura: no modifica el motor."""
import sys

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[2]  # raíz del proyecto
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from api import mapping, schemas  # noqa: E402
from engine.units.unit_registry import length_to_m  # noqa: E402
from e2_combinada_wight_15_5 import peticion  # noqa: E402
from engine.codes.peru.e060_concrete import E060ConcreteCode  # noqa: E402
from engine.domain.column import Column  # noqa: E402
from engine.foundation.combined_solver import solve_combined_footing  # noqa: E402
from engine.optimization.combined_generator import ColumnSpec, build_layout  # noqa: E402
from engine.reinforcement.face_reinforcement import TopCoverDeclaration  # noqa: E402


def resolver(h_ft, P1u, P2u):
    req = schemas.CombinedDesignRequest(**peticion(h_ft, P1u, P2u))
    u = req.units
    specs = [
        ColumnSpec(label=c.label, column=Column(shape=c.shape, bx_m=length_to_m(c.bx_m, u.length),
                                                by_m=length_to_m(c.by_m, u.length)),
                   distance_from_first_m=length_to_m(c.distance_from_first_m, u.length),
                   transverse_offset_m=0.0,
                   loads=mapping.build_loads(c.combinations, u, c.load_cases, req.combination_definitions))
        for c in req.columns
    ]
    s = req.search
    layout = build_layout(specs, length_to_m(s.length_min_m, u.length), length_to_m(s.width_min_m, u.length),
                          length_to_m(s.first_column_edge_distance_m, u.length), "X")
    concrete, steel = mapping.build_materials(req.materials, u)
    return solve_combined_footing(
        layout, length_to_m(h_ft, u.length), soil=mapping.build_soil(req.soil, u), concrete=concrete,
        steel=steel, code=E060ConcreteCode(), contact_model=mapping.contact_model_for(req.soil),
        top_cover=TopCoverDeclaration(explicit_mm=76.0),
    )


if __name__ == "__main__":
    for etiqueta, h, P1, P2 in (("h = 36 in, ACI", 3.0, 480.0, 720.0), ("h = 40 in, ACI", 40 / 12, 480.0, 720.0)):
        r = resolver(h, P1, P2)
        print(f"== {etiqueta}: estado {r.overall_status.value}")
        for e in r.trace.entries:
            if any(k in e.id for k in ("punching", "shear", "flexure", "contact")):
                print(f"   [{e.id}] {e.status.value} → {e.result_value} {e.result_unit or ''}")
                print("      ", str(e.equation_substituted)[:600])
