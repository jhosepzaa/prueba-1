"""Validación de extremo a extremo — Aragón CR2 §3.5, zapata combinada (2026-09-22).

Primera validación del programa recorrido entero —API, conversión de unidades, barrido,
presiones, diagramas, envolvente, acero— contra una fuente independiente. Destapó dos
defectos reales de la combinada, los dos invisibles para el congelamiento:

1. **El signo del par de columna en el diagrama longitudinal.** El diagrama no cerraba el
   equilibrio de momentos y el acero SUPERIOR salía subestimado, del lado inseguro.
2. **La falta de envolvente.** Se diseñaban M⁺, M⁻ y V con el diagrama de una sola
   combinación, la de mayor |M|.

Ninguno de los dos aparecía en los casos congelados porque todos tienen **una sola
combinación factorizada** y solo uno lleva momentos de columna. Este archivo fija el primer
caso combinado con varias combinaciones y sismo.

Los valores esperados se reconstruyen a mano o se toman del libro, **nunca del motor**
(`CLAUDE.md` §12). Aragón es benchmark, no autoridad (§1): donde el libro difiere por su
método, se documenta y el test sigue a la física. Detalle en
`docs/validacion_aragon_3_5_combinada.md`.
"""

import pytest
from fastapi.testclient import TestClient

from api.server import app

T = 9.80665  # kN por tonf

cliente = TestClient(app)


def _columna(label, dist, cm, cv, cs):
    """(P [tonf], M [tonf·m]) por caso. P > 0 hacia abajo; M > 0 corre la carga a +X."""
    return {
        "label": label, "shape": "cuadrada", "bx_m": 0.50, "by_m": 0.50,
        "distance_from_first_m": dist,
        "load_cases": [
            {"name": "CM", "kind": "CM", "P_kN": cm[0], "Mx_kNm": cm[1]},
            {"name": "CV", "kind": "CV", "P_kN": cv[0], "Mx_kNm": cv[1]},
            {"name": "CS", "kind": "CS", "level": "SERVICIO", "P_kN": cs[0], "Mx_kNm": cs[1]},
        ],
    }


# E.060 §9.2.1 (9-1) y §9.2.3 para sismo a nivel de SERVICIO (9-4a), (9-4b).
COMBINACIONES = [
    {"name": "S1", "type": "SERVICIO", "factors": {"CM": 1, "CV": 1}},
    {"name": "S2", "type": "SERVICIO", "factors": {"CM": 1, "CV": 1, "CS": 1}},
    {"name": "S3", "type": "SERVICIO", "factors": {"CM": 1, "CV": 1, "CS": -1}},
    {"name": "U1", "type": "FACTORIZADA", "factors": {"CM": 1.4, "CV": 1.7}},
    {"name": "U2", "type": "FACTORIZADA", "factors": {"CM": 1.25, "CV": 1.25, "CS": 1.25}},
    {"name": "U3", "type": "FACTORIZADA", "factors": {"CM": 1.25, "CV": 1.25, "CS": -1.25}},
    {"name": "U4", "type": "FACTORIZADA", "factors": {"CM": 0.9, "CS": 1.25}},
    {"name": "U5", "type": "FACTORIZADA", "factors": {"CM": 0.9, "CS": -1.25}},
]


def _peticion(L_rango, B_rango, h_rango):
    return {
        "columns": [
            _columna("C1", 0.0, (80, 6), (30, 2.5), (-10, 50)),
            _columna("C2", 5.0, (160, -2), (60, -0.5), (10, 70)),
        ],
        "combination_definitions": COMBINACIONES,
        "materials": {"fc_MPa": 210, "fy_MPa": 4200, "concrete_unit_weight_kNm3": 2.4},
        "soil": {"qadm_kPa": 1.5, "pressure_basis": "BRUTA", "gamma_kNm3": 1.8, "Df_m": 1.50,
                 "allow_temporary_increase_30pct": True},
        "search": {
            "length_min_m": L_rango[0], "length_max_m": L_rango[1], "length_step_m": 0.20,
            "width_min_m": B_rango[0], "width_max_m": B_rango[1], "width_step_m": 0.20,
            "h_min_m": h_rango[0], "h_max_m": h_rango[1], "h_step_m": 0.05,
            "first_column_edge_distance_m": 0.25, "longitudinal_direction": "X",
        },
        "top_cover": {"case": "contacto_suelo_barras_grandes"},
        "units": {"force": "tonf", "moment": "tonf·m", "pressure": "kgf/cm²",
                  "strength": "kgf/cm²", "length": "m", "unit_weight": "tonf/m³"},
        "top_n": 30,
    }


@pytest.fixture(scope="module")
def resultado():
    r = cliente.post("/api/design-combined", json=_peticion((6.4, 8.0), (3.0, 5.0), (0.50, 1.20)))
    assert r.status_code == 200, r.text
    return r.json()


def _geometria(L, B, h):
    """La misma petición, una sola geometría, resuelta en el motor con sus conversiones."""
    from api import mapping, schemas
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.column import Column
    from engine.foundation.combined_solver import solve_combined_footing
    from engine.optimization.combined_generator import ColumnSpec, build_layout
    from engine.reinforcement.face_reinforcement import TopCoverDeclaration

    req = schemas.CombinedDesignRequest(**_peticion((L, L), (B, B), (h, h)))
    u = req.units
    specs = [
        ColumnSpec(
            label=c.label, column=Column(shape="cuadrada", bx_m=0.50, by_m=0.50),
            distance_from_first_m=c.distance_from_first_m, transverse_offset_m=0.0,
            loads=mapping.build_loads(c.combinations, u, c.load_cases, req.combination_definitions),
        )
        for c in req.columns
    ]
    concreto, acero = mapping.build_materials(req.materials, u)
    return solve_combined_footing(
        build_layout(specs, L, B, 0.25, "X"), h, soil=mapping.build_soil(req.soil, u),
        concrete=concreto, steel=acero, code=E060ConcreteCode(),
        contact_model=mapping.contact_model_for(req.soil),
        top_cover=TopCoverDeclaration(case="contacto_suelo_barras_grandes"),
    )


# =========================================================================
# 1. El barrido
# =========================================================================


def test_la_busqueda_es_exhaustiva_y_lo_dice(resultado):
    """Con un rango mayor el barrido supera el tope de 3000 y el motor lo advierte; este
    rango está elegido para que la búsqueda sea completa y pueda presentarse como tal."""
    assert resultado["truncated"] is False
    assert resultado["evaluated_count"] > 1000


def test_la_longitud_de_centrado_es_la_del_libro(resultado):
    """0,25(110) + 5,25(220) + 8,5 − 2,5 = X(330) ⇒ X = 3,6015 ⇒ L = 7,203 m. Libro: 7,20."""
    assert resultado["centering_length_m"] == pytest.approx(2 * 1188.5 / 330.0, rel=1e-9)


def test_la_geometria_recomendada_esta_aceptada(resultado):
    ids = {(a["length_m"], a["width_m"], a["h_m"]) for a in resultado["top"]}
    assert (7.2, 4.2, 0.75) in ids


# =========================================================================
# 2. La presión de contacto — el relleno que el libro omite
# =========================================================================


def test_la_geometria_del_libro_no_cumple_si_se_cuenta_el_relleno():
    """El libro adopta 7,20 × 3,80 × 0,80 y obtiene 19,18 t/m² ≤ 19,50 (1,5 × 1,3).

    Toma el peso propio como SOLO concreto (52,53 t) y omite el relleno sobre la zapata
    (≈ 34 t). Con presión admisible BRUTA —la declarada por el proyectista— el relleno
    pesa sobre el suelo. Reconstruido a mano:

        P = 330 + 52,53 + 7,2·3,8·0,70·1,8 = 416,99 t     M respecto del centroide = 170,5 t·m
        qmax = P/A·(1 + 6e/L) = 20,43 t/m² > 19,50

    El motor no descuenta el fuste de las columnas del relleno: hipótesis declarada
    («relleno sobre toda la huella»), conservadora en un 0,15 %."""
    r = _geometria(7.20, 3.80, 0.80)
    P = 330 + 7.2 * 3.8 * 0.80 * 2.4 + 7.2 * 3.8 * 0.70 * 1.8
    e = 170.5 / P
    qmax_mano = P / (7.2 * 3.8) * (1 + 6 * e / 7.2)
    entrada = r.trace.by_id("contact_pressure")
    assert entrada.status.value == "FAIL"
    assert qmax_mano > 19.5
    assert r.contact_pressure.qmax_kPa / T == pytest.approx(qmax_mano, rel=2e-3)


# =========================================================================
# 3. El diagrama longitudinal — el defecto del signo
# =========================================================================


@pytest.mark.parametrize("combo", ["U1", "U2", "U3", "U4", "U5"])
def test_el_diagrama_cierra_en_todas_las_combinaciones(combo):
    """M(L) = 0 en el extremo libre, en las cinco. Con el signo congelado del par valía
    −2·Σ Mᵢ: 285 t·m en U3."""
    from engine.analysis.beam_diagram import _moment
    from engine.foundation.combined_solver import _diagram_for
    from engine.optimization.combined_generator import build_layout

    from api import mapping, schemas
    from engine.domain.column import Column
    from engine.optimization.combined_generator import ColumnSpec

    req = schemas.CombinedDesignRequest(**_peticion((7.2, 7.2), (4.2, 4.2), (0.75, 0.75)))
    specs = [
        ColumnSpec(label=c.label, column=Column(shape="cuadrada", bx_m=0.5, by_m=0.5),
                   distance_from_first_m=c.distance_from_first_m, transverse_offset_m=0.0,
                   loads=mapping.build_loads(c.combinations, req.units, c.load_cases,
                                             req.combination_definitions))
        for c in req.columns
    ]
    d = _diagram_for(build_layout(specs, 7.2, 4.2, 0.25, "X"), combo, factored=True)
    assert _moment(7.2, d.w_start_kNm, d.w_end_kNm, 7.2, d.loads) == pytest.approx(0.0, abs=1e-6)


def test_el_momento_superior_es_el_reconstruido_a_mano():
    """U3 = 1,25(CM + CV − CS), sección de cortante nulo x = 2,000 m.

        P1 = 150, P2 = 262,5 t     M1 = −51,875, M2 = −90,625 t·m
        e = −0,5136 m   ⇒   q(0) = 81,81 t/m, q(L) = 32,77 t/m
        M(2,0) = 81,81·2²/2 − 6,812·2³/6 − 150·(2,0 − 0,25) − 51,875 = −159,83 t·m

    Con el signo congelado del par el motor daba 56,08: un 35 % del valor real, del lado
    inseguro en la cara superior."""
    r = _geometria(7.20, 4.20, 0.75)
    assert r.top_face.Mu_kNm / T == pytest.approx(159.83, abs=0.02)


# =========================================================================
# 4. La envolvente
# =========================================================================


def test_cada_efecto_lo_gobierna_su_propia_combinacion():
    """El momento superior lo gobierna U3 y el cortante U1.

    Con el diagrama de una sola combinación —la de mayor |M|, U3— el cortante salía
    173,92 t en vez de 176,43. Aquí sigue cumpliendo (176,43 ≤ 187,32), pero con otra
    geometría podía no hacerlo."""
    r = _geometria(7.20, 4.20, 0.75)
    por_id = {e.id: e for e in r.trace.entries}
    assert por_id["flexure_top"].governing_combo == "U3"
    assert por_id["shear_longitudinal"].governing_combo == "U1"

    # A mano: U1 es casi uniforme, 489 t sobre 7,20 m = 67,92 t/m. En la cara izquierda
    # de C2, x = 5,00: V = 67,92·5,00 − 163 = 176,6 t (la pendiente de q, e = 0,0017 m,
    # la baja a 176,43).
    assert r.shear_longitudinal.Vu_kN / T == pytest.approx(176.43, abs=0.05)
    assert r.shear_longitudinal.Vu_kN / T > 173.92  # lo que daba sin envolvente


# =========================================================================
# 5. Lo que el defecto no tocaba — franjas transversales
# =========================================================================


@pytest.mark.parametrize("columna,libro", [("C1", 58.38), ("C2", 116.78)])
def test_las_franjas_transversales_son_las_del_libro(columna, libro):
    """Libro: ωu = Pu/B, voladizo (3,80 − 0,50)/2 = 1,65 m, Mu = ωu·1,65²/2.
    C1: 163/3,8·1,65²/2 = 58,38 t·m. C2: 326/3,8·1,65²/2 = 116,78 t·m."""
    r = _geometria(7.20, 3.80, 0.80)
    franja = next(s for s in r.transverse_strips if s.column_label == columna)
    assert franja.Mu_kNm / T == pytest.approx(libro, abs=0.05)
