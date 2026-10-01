# -*- coding: utf-8 -*-
"""E1 — Zapata aislada cuadrada. Wight, Reinforced Concrete Mechanics and Design 7th ed.,
Example 15-2, resuelto por StructurePoint (ACI 318-14).

Datos del original: columna 18 in cuadrada; D = 400 k, L = 270 k; f'c zapata 3000 psi;
fy 60 ksi; qa = 6000 psf (bruta); relleno 6 in (120 pcf) y losa de sótano 6 in + 100 psf.
Resultado publicado: 11 ft 2 in cuadrada × 32 in, d = 28 in; Pu = 912 k; qnu = 7310 psf;
punzonamiento Vu = 805 k, vu = 156 psi ≤ φvc = 164 psi; cortante Vu = 204 k ≤ φVc = 308 k;
Mu = 954 k·ft; As = 7,76 in².
"""
import json
import sys

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[2]  # raíz del proyecto
sys.path.insert(0, str(RAIZ))
from fastapi.testclient import TestClient  # noqa: E402

from api.server import app  # noqa: E402

B = 11.0 + 2.0 / 12.0          # ft
H = 32.0 / 12.0                # ft
DF = (32 + 6 + 6) / 12.0       # zapata + relleno + losa, ft


def peticion(Pu_kip: float, nombre: str) -> dict:
    return {
        "project_name": f"Wight 15-2 — {nombre}",
        "column": {"shape": "cuadrada", "bx_m": 1.5, "by_m": 1.5},
        "materials": {"fc_MPa": 3000.0, "fy_MPa": 60000.0},
        "soil": {"qadm_kPa": 6.0, "gamma_kNm3": 120.0, "Df_m": DF},
        "search": {"B_min_m": B, "B_max_m": B, "B_step_m": 0.1,
                   "L_min_m": B, "L_max_m": B, "L_step_m": 0.1,
                   "h_min_m": H, "h_max_m": H, "h_step_m": 0.05},
        "combinations": [
            {"name": "S1", "type": "SERVICIO", "P_kN": 670.0},
            {"name": "U1", "type": "FACTORIZADA", "P_kN": Pu_kip},
        ],
        "units": {"force": "kip", "moment": "kip·ft", "pressure": "ksf", "strength": "psi",
                  "length": "ft", "unit_weight": "pcf"},
        "top_n": 1,
    }


def mostrar(j: dict) -> None:
    if not j.get("top"):
        print("   sin alternativa:", json.dumps(j.get("summary"), ensure_ascii=False)[:600])
        print("   descartes:", json.dumps(j.get("discards") or j.get("discard_summary"), ensure_ascii=False)[:1200])
        return
    a = j["top"][0]
    print("   alternativa", a.get("id"), "estado", a.get("status"), "B", a.get("B_m"), "h", a.get("h_m"))
    for e in a.get("trace", []):
        if any(k in e["id"] for k in ("punching", "shear_x", "flexure_x", "rebar_x", "contact_pressure", "development_x", "min_depth")):
            print(f"   [{e['id']}] {e['status']} → {e.get('result_value')} {e.get('result_unit') or ''}")
            print("      ", str(e.get("equation_substituted"))[:420])


if __name__ == "__main__":
    c = TestClient(app)
    for Pu, nombre in ((912.0, "cargas factorizadas ACI (1,2D+1,6L)"),
                       (1.4 * 400 + 1.7 * 270, "cargas factorizadas E.060 (1,4CM+1,7CV)")):
        r = c.post("/api/design", json=peticion(Pu, nombre))
        print(f"== {nombre}: Pu = {Pu:.0f} kip · HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:800]); continue
        mostrar(r.json())
