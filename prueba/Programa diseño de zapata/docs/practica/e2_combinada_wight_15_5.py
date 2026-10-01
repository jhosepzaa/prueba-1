# -*- coding: utf-8 -*-
"""E2 — Zapata combinada rectangular. Wight 7th ed., Example 15-5, resuelto por
StructurePoint (ACI 318-14).

Datos: columna exterior 16 in (a lo largo) × 24 in, al ras del lindero; interior 24 × 24 in;
entre ejes 20 ft (deducido: la zapata de 25 ft 4 in centra la resultante de servicio);
D = 200/300 k, L = 150/225 k; f'c 3000 psi, fy 60 ksi; qa = 5000 psf; γs 120 pcf.
Resultado publicado: 25 ft 4 in × 8 ft; qnu = 5,92 ksf; con h = 36 in (d = 32,5 in) el
punzonamiento de la columna exterior NO cumple (vu = 192 psi > φvc = 164 psi, con
Munb = 579 k·ft); con h = 40 in (d = 36,5 in) cumple (vu = 157 psi). Interior: vu = 80,2 psi.
Flexión: Mu⁻ = 2100 k·ft → As = 13,4 in² (17 #8 arriba).
"""
import json
import sys

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[2]  # raíz del proyecto
sys.path.insert(0, str(RAIZ))
from fastapi.testclient import TestClient  # noqa: E402

from api.server import app  # noqa: E402

LARGO, ANCHO = 25.0 + 4.0 / 12.0, 8.0


def peticion(h_ft: float, P1u: float, P2u: float) -> dict:
    col = lambda lab, bx, d, Ps, Pu: {
        "label": lab, "shape": "rectangular" if bx != 2.0 else "cuadrada", "bx_m": bx, "by_m": 2.0,
        "distance_from_first_m": d,
        "combinations": [{"name": "S1", "type": "SERVICIO", "P_kN": Ps},
                         {"name": "U1", "type": "FACTORIZADA", "P_kN": Pu}],
    }
    return {
        "project_name": "Wight 15-5",
        "columns": [col("EXT", 16 / 12, 0.0, 350.0, P1u), col("INT", 2.0, 20.0, 525.0, P2u)],
        "materials": {"fc_MPa": 3000.0, "fy_MPa": 60000.0},
        "soil": {"qadm_kPa": 5.0, "gamma_kNm3": 120.0, "Df_m": 5.0},
        "search": {"length_min_m": LARGO, "length_max_m": LARGO, "length_step_m": 0.1,
                   "width_min_m": ANCHO, "width_max_m": ANCHO, "width_step_m": 0.1,
                   "h_min_m": h_ft, "h_max_m": h_ft, "h_step_m": 0.05,
                   "first_column_edge_distance_m": 8 / 12, "longitudinal_direction": "X"},
        "top_cover": {"explicit_mm": 76.0},
        "units": {"force": "kip", "moment": "kip·ft", "pressure": "ksf", "strength": "psi",
                  "length": "ft", "unit_weight": "pcf"},
        "top_n": 1,
    }


def correr(etiqueta: str, h_ft: float, P1u: float, P2u: float, c: TestClient) -> None:
    r = c.post("/api/design-combined", json=peticion(h_ft, P1u, P2u))
    print(f"== {etiqueta}: HTTP {r.status_code}")
    j = r.json()
    if r.status_code != 200:
        print(json.dumps(j, ensure_ascii=False)[:1500]); return
    if not j["top"]:
        print("   sin aceptadas:", j.get("search_note", "")[:300])
        print("   descartes:", json.dumps(j.get("discard_summary"), ensure_ascii=False)[:1500])
        return
    a = j["top"][0]
    print("   ", a["id"], a.get("status"), "M+", round(a["M_positive_kNm"], 1), "M-", round(a["M_negative_kNm"], 1), "kN·m")
    for e in a.get("trace", []):
        if any(k in e["id"] for k in ("punching", "shear_long", "shear_trans", "flexure", "face", "contact")):
            print(f"   [{e['id']}] {e['status']} → {e.get('result_value')} {e.get('result_unit') or ''}")
            print("      ", str(e.get("equation_substituted"))[:520])


if __name__ == "__main__":
    c = TestClient(app)
    correr("h = 36 in, cargas ACI", 3.0, 480.0, 720.0, c)
    correr("h = 40 in, cargas ACI", 40 / 12, 480.0, 720.0, c)
    correr("h = 40 in, cargas E.060", 40 / 12, 1.4 * 200 + 1.7 * 150, 1.4 * 300 + 1.7 * 225, c)
