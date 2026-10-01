"""FASE 8 — Validación cruzada por caminos independientes.

Cada magnitud que el motor calcula en forma cerrada se recalcula aquí por un
camino distinto (integración numérica o bisección) y se comparan. Un test de un
solo camino solo confirma que el código hace lo que hace; esto confirma que lo
que hace coincide con la física.

No sustituye a la validación contra bibliografía peruana, que sigue pendiente de
que se aporten ejemplos resueltos (ver docs/validacion_bibliografica.md).
"""

import math

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.foundation.depth_solver import evaluate_candidate
from engine.foundation.flexure import design_flexure, moment_at_critical_section
from engine.foundation.punching_shear import punching_demand
from engine.foundation.shear_oneway import shear_force_at_d_from_face
from engine.soil.contact_pressure import FullContactModel
from engine.soil.eccentricity import compute_eccentricity
from tests.golden_cases.common import (
    CODE,
    COLUMN_40x40,
    CONCRETE_21,
    CONTACT_MODEL,
    DEPTH_PARAMS_DEFAULT,
    SOIL_150_BRUTA,
    STEEL_420,
)
from tests.validation.analytical_benchmarks import (
    biaxial_pressure,
    kern_limit_check,
    moment_by_integration,
    one_way_shear_capacity,
    punching_shear_by_integration,
    shear_by_integration,
    steel_area_by_bisection,
    total_reaction_by_integration,
)

code = E060ConcreteCode()

# Casos de prueba variados: concéntrico, uniaxial y biaxial.
MOMENT_CASES = [
    # (Pu, e, dim, cantilever)
    (560.0, 0.00, 2.00, 0.80),
    (630.0, 0.05, 2.40, 1.00),
    (800.0, 0.15, 3.00, 1.30),
    (450.0, 0.25, 3.20, 1.40),
    (1200.0, 0.10, 2.60, 1.10),
]


# ===== Momento: forma cerrada vs. integración numérica =================================

@pytest.mark.parametrize("Pu,e,dim,cant", MOMENT_CASES)
def test_moment_closed_form_matches_numerical_integration(Pu, e, dim, cant):
    engine_value = moment_at_critical_section(Pu, e, dim, cant, near_high_edge=True)
    analytical = moment_by_integration(Pu, e, dim, cant)
    assert engine_value == pytest.approx(analytical, rel=1e-3), (
        f"Pu={Pu} e={e} dim={dim} c={cant}: motor={engine_value:.4f} vs integración={analytical:.4f}"
    )


def test_uniform_pressure_moment_equals_the_classic_cantilever_formula():
    """Sin excentricidad, M debe ser exactamente w·c²/2."""
    Pu, dim, cant = 560.0, 2.0, 0.80
    w = Pu / dim
    assert moment_at_critical_section(Pu, 0.0, dim, cant, True) == pytest.approx(w * cant**2 / 2)


# ===== Cortante: forma cerrada vs. integración =========================================

@pytest.mark.parametrize("Pu,e,dim,cant", MOMENT_CASES)
def test_shear_closed_form_matches_numerical_integration(Pu, e, dim, cant):
    d = 0.35
    engine_value = shear_force_at_d_from_face(Pu, e, dim, cant, d, near_high_edge=True)
    analytical = shear_by_integration(Pu, e, dim, cant, d)
    assert engine_value == pytest.approx(analytical, rel=1e-3)


def test_shear_capacity_matches_an_independent_transcription_of_eq_11_3():
    for fc, bw, d in [(21.0, 2.0, 0.42), (28.0, 3.0, 0.55), (35.0, 1.6, 0.31)]:
        vc = code.one_way_shear_vc(fc, bw, d)
        phi_vc_engine = code.phi_factors().cortante * vc.value
        assert phi_vc_engine == pytest.approx(one_way_shear_capacity(fc, bw, d), rel=1e-9)


# ===== Equilibrio global del campo de presiones ========================================

@pytest.mark.parametrize(
    "P,B,L,ex,ey",
    [
        (500.0, 2.0, 2.0, 0.00, 0.00),
        (650.0, 2.4, 2.0, 0.12, 0.00),
        (700.0, 2.8, 2.8, 0.086, 0.115),
        (900.0, 3.0, 2.2, 0.20, 0.10),
    ],
)
def test_pressure_field_satisfies_global_equilibrium(P, B, L, ex, ey):
    """∫q dA = P, ∫q·x dA = P·ex, ∫q·y dA = P·ey."""
    force, mx, my = total_reaction_by_integration(P, B, L, ex, ey)
    assert force == pytest.approx(P, rel=1e-6)
    assert my == pytest.approx(P * ex, rel=1e-4, abs=1e-6)
    assert mx == pytest.approx(P * ey, rel=1e-4, abs=1e-6)


@pytest.mark.parametrize(
    "P,B,L,ex,ey",
    [
        (500.0, 2.0, 2.0, 0.00, 0.00),
        (650.0, 2.4, 2.0, 0.12, 0.00),
        (700.0, 2.8, 2.8, 0.086, 0.115),
    ],
)
def test_engine_corner_pressures_match_the_pressure_field(P, B, L, ex, ey):
    """qmax y qmin del motor deben coincidir con evaluar el campo en las esquinas."""
    result = FullContactModel().compute(B, L, P, ex, ey)
    corner_max = biaxial_pressure(P, B, L, ex, ey, B / 2, L / 2)
    corner_min = biaxial_pressure(P, B, L, ex, ey, -B / 2, -L / 2)
    assert result.qmax_kPa == pytest.approx(corner_max, rel=1e-9)
    assert result.qmin_kPa == pytest.approx(corner_min, rel=1e-9)


@pytest.mark.parametrize(
    "B,L,ex,ey",
    [(2.0, 2.0, 0.0, 0.0), (2.0, 2.0, 0.33, 0.0), (2.0, 2.0, 0.34, 0.0),
     (2.4, 3.0, 0.15, 0.25), (2.4, 3.0, 0.25, 0.35)],
)
def test_kern_criterion_matches_its_geometric_definition(B, L, ex, ey):
    result = FullContactModel().compute(B, L, 500.0, ex, ey)
    assert result.within_kern == kern_limit_check(B, L, ex, ey)


def test_kern_boundary_is_exactly_where_qmin_reaches_zero():
    """Dentro del núcleo qmin ≥ 0; fuera, negativo. Es la definición física."""
    for B, L, ex, ey in [(2.0, 2.0, 0.3, 0.0), (2.0, 2.0, 0.34, 0.0), (3.0, 2.0, 0.2, 0.2)]:
        r = FullContactModel().compute(B, L, 500.0, ex, ey)
        if r.within_kern:
            assert r.qmin_kPa >= -1e-9
        else:
            assert r.qmin_kPa < 0


# ===== Punzonamiento: resta de áreas vs. integración ===================================

@pytest.mark.parametrize(
    "Pu,B,L,bx,by,d",
    [
        (560.0, 2.0, 2.0, 0.40, 0.40, 0.42),
        (1700.0, 1.6, 1.6, 0.40, 0.40, 0.31),
        (6000.0, 6.0, 3.0, 1.20, 1.20, 0.70),
        (900.0, 2.6, 2.2, 0.30, 0.50, 0.38),
    ],
)
def test_punching_demand_matches_integration_of_the_outer_zone(Pu, B, L, bx, by, d):
    engine_value = punching_demand(Pu, B, L, bx, by, d)
    analytical = punching_shear_by_integration(Pu, B, L, bx, by, d)
    assert engine_value == pytest.approx(analytical, rel=2e-3)


def test_punching_demand_equals_load_minus_relieved_area_by_equilibrium():
    """Comprobación de equilibrio pura: Vu + reacción interior = Pu."""
    Pu, B, L, bx, by, d = 560.0, 2.0, 2.0, 0.40, 0.40, 0.42
    vu = punching_demand(Pu, B, L, bx, by, d)
    qu = Pu / (B * L)
    inner = qu * (bx + d) * (by + d)
    assert vu + inner == pytest.approx(Pu, rel=1e-9)


# ===== Acero: forma cerrada vs. bisección ==============================================

@pytest.mark.parametrize(
    "Mu,b,d,fc,fy",
    [
        (89.6, 2.00, 0.422, 21.0, 420.0),
        (191.25, 1.60, 0.311, 21.0, 420.0),
        (2880.0, 3.00, 0.722, 21.0, 420.0),
        (150.0, 2.40, 0.500, 28.0, 420.0),
        (320.0, 2.00, 0.450, 35.0, 520.0),
    ],
)
def test_steel_area_closed_form_matches_bisection(Mu, b, d, fc, fy):
    engine = design_flexure(
        Mu_kNm=Mu, b_m=b, h_m=d + 0.08, d_m=d, cantilever_m=1.0,
        fc_MPa=fc, fy_MPa=fy, bar_type="corrugada", code=code,
    )
    analytical = steel_area_by_bisection(Mu, b, d, fc, fy)
    assert not math.isnan(analytical), "El caso debe ser resoluble"
    assert engine.As_required_m2 == pytest.approx(analytical, rel=1e-4), (
        f"Mu={Mu}: motor={engine.As_required_m2 * 1e4:.4f} cm² vs "
        f"bisección={analytical * 1e4:.4f} cm²"
    )


def test_steel_solution_satisfies_section_equilibrium():
    """El As devuelto debe reproducir Mu al sustituirlo en φ·As·fy·(d−a/2)."""
    Mu, b, d, fc, fy = 191.25, 1.60, 0.311, 21.0, 420.0
    result = design_flexure(Mu, b, d + 0.08, d, 1.0, fc, fy, "corrugada", code)
    as_mm2 = result.As_required_m2 * 1e6
    a = as_mm2 * fy / (0.85 * fc * b * 1000.0)
    mn = as_mm2 * fy * (d * 1000.0 - a / 2.0) / 1e6  # kN·m
    assert 0.90 * mn == pytest.approx(Mu, rel=1e-4)


def test_insufficient_section_is_detected_by_both_paths():
    Mu, b, d, fc, fy = 845.0, 3.0, 0.122, 21.0, 420.0
    engine = design_flexure(Mu, b, d + 0.08, d, 1.0, fc, fy, "corrugada", code)
    analytical = steel_area_by_bisection(Mu, b, d, fc, fy)
    assert math.isnan(engine.As_required_m2)
    assert math.isnan(analytical)


# ===== Invariantes de monotonía (atrapan errores de signo y de despeje) =================

def test_required_steel_grows_with_moment():
    values = [
        design_flexure(mu, 2.0, 0.5, 0.42, 1.0, 21.0, 420.0, "corrugada", code).As_required_m2
        for mu in (50.0, 100.0, 200.0, 400.0)
    ]
    assert values == sorted(values)


def test_required_steel_shrinks_with_effective_depth():
    values = [
        design_flexure(200.0, 2.0, d + 0.08, d, 1.0, 21.0, 420.0, "corrugada", code).As_required_m2
        for d in (0.30, 0.40, 0.50, 0.60)
    ]
    assert values == sorted(values, reverse=True)


def test_pressure_grows_with_load_and_shrinks_with_area():
    model = FullContactModel()
    assert model.compute(2.0, 2.0, 800.0, 0, 0).qmax_kPa > model.compute(2.0, 2.0, 400.0, 0, 0).qmax_kPa
    assert model.compute(3.0, 3.0, 400.0, 0, 0).qmax_kPa < model.compute(2.0, 2.0, 400.0, 0, 0).qmax_kPa


def test_eccentricity_only_increases_the_maximum_pressure():
    model = FullContactModel()
    base = model.compute(2.4, 2.4, 600.0, 0.0, 0.0)
    for e in (0.05, 0.10, 0.20, 0.30):
        assert model.compute(2.4, 2.4, 600.0, e, 0.0).qmax_kPa > base.qmax_kPa


# ===== Coherencia del pipeline completo =================================================

def test_full_candidate_is_internally_consistent():
    """Recalcula las magnitudes clave del candidato por caminos independientes."""
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=450.0, Mx_kNm=40.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=630.0, Mx_kNm=56.0)],
    )
    c = evaluate_candidate(
        B_m=2.6, L_m=2.6, h_m=0.55, column=COLUMN_40x40, soil=SOIL_150_BRUTA,
        concrete=CONCRETE_21, steel=STEEL_420, load_case_set=loads, code=CODE,
        contact_model=CONTACT_MODEL, depth_params=DEPTH_PARAMS_DEFAULT,
    )

    # 1) Peso propio por geometría directa
    expected_w = (
        CONCRETE_21.unit_weight_kNm3 * 2.6 * 2.6 * 0.55
        + SOIL_150_BRUTA.gamma_kNm3 * 2.6 * 2.6 * max(SOIL_150_BRUTA.Df_m - 0.55, 0.0)
    )
    assert c.self_weight.W_total_kN == pytest.approx(expected_w)

    # 2) Presión máxima por evaluación del campo en la esquina
    p_total = 450.0 + c.self_weight.W_total_kN
    ecc = compute_eccentricity(p_total, 40.0, 0.0)
    corner = biaxial_pressure(p_total, 2.6, 2.6, ecc.ex_m, ecc.ey_m, 1.3, 1.3)
    assert c.contact_pressure.qmax_kPa == pytest.approx(corner, rel=1e-9)

    # 3) Momento de flexión por integración
    cant_y = (2.6 - COLUMN_40x40.by_m) / 2
    ey_factored = compute_eccentricity(630.0, 56.0, 0.0).ey_m
    assert c.flexure_y.Mu_kNm == pytest.approx(
        moment_by_integration(630.0, ey_factored, 2.6, cant_y), rel=1e-3
    )

    # 4) Punzonamiento por integración de la zona exterior
    assert c.punching.Vu_kN == pytest.approx(
        punching_shear_by_integration(630.0, 2.6, 2.6, 0.40, 0.40, c.d_m), rel=3e-3
    )

    # 5) Acero por bisección
    assert c.flexure_y.As_required_m2 == pytest.approx(
        steel_area_by_bisection(c.flexure_y.Mu_kNm, 2.6, c.d_m, 21.0, 420.0), rel=1e-4
    )
