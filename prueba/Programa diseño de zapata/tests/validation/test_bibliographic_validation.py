"""Ejecuta los casos bibliográficos que estén registrados.

Mientras el registro esté vacío, la suite lo declara explícitamente en vez de
pasar en silencio: un conjunto de tests vacío que "pasa" daría una falsa
sensación de validación cumplida.
"""

from __future__ import annotations

import pytest

from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from tests.golden_cases.common import CODE, CONTACT_MODEL
from tests.validation.reference_cases import REFERENCE_CASES, BibliographicCase


def run_case(case: BibliographicCase) -> dict[str, tuple[float | None, float]]:
    """Ejecuta el motor con las entradas del libro y devuelve
    {magnitud: (valor_del_libro, valor_del_motor)} para las que el libro reporta."""
    i = case.inputs
    loads = LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=i.P_service_kN,
                Mx_kNm=i.Mx_service_kNm, My_kNm=i.My_service_kNm,
            )
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=i.P_factored_kN,
                Mx_kNm=i.Mx_factored_kNm, My_kNm=i.My_factored_kNm,
            )
        ]
        + [
            LoadCombination(
                name=f"U{n + 2}", type=LoadCombinationType.FACTORIZADA,
                P_kN=P, Mx_kNm=Mx, My_kNm=My,
            )
            for n, (P, Mx, My) in enumerate(i.extra_factored)
        ],
    )
    loads.service.extend(
        LoadCombination(
            name=f"S{n + 2}", type=LoadCombinationType.SERVICIO, P_kN=P, Mx_kNm=Mx, My_kNm=My,
        )
        for n, (P, Mx, My) in enumerate(i.extra_service)
    )
    expected = case.expected
    if expected.B_m is None or expected.L_m is None or expected.h_m is None:
        pytest.skip(f"{case.id}: el libro no reporta B, L y h; no puede fijarse la geometría.")

    candidate = evaluate_candidate(
        B_m=expected.B_m, L_m=expected.L_m, h_m=expected.h_m,
        column=Column(
            shape="cuadrada" if i.column_bx_m == i.column_by_m else "rectangular",
            bx_m=i.column_bx_m, by_m=i.column_by_m,
        ),
        soil=SoilProfile(
            qadm_kPa=i.qadm_kPa, pressure_basis=PressureBasis(i.pressure_basis),
            gamma_kNm3=i.gamma_soil_kNm3, Df_m=i.Df_m,
        ),
        concrete=MaterialConcrete(fc_MPa=i.fc_MPa),
        steel=MaterialSteel(fy_MPa=i.fy_MPa),
        load_case_set=loads, code=CODE, contact_model=CONTACT_MODEL,
        depth_params=DepthSearchParameters(
            h_min_m=expected.h_m, h_max_m=expected.h_m, h_step_m=0.05,
            cover_override_mm=i.cover_mm,
        ),
    )

    comparisons: dict[str, tuple[float | None, float]] = {
        "d (m)": (expected.d_m, candidate.d_m),
        "q max (kPa)": (expected.qmax_kPa, candidate.contact_pressure.qmax_kPa),
        "q min (kPa)": (expected.qmin_kPa, candidate.contact_pressure.qmin_kPa),
        "Mu X (kN·m)": (expected.Mu_x_kNm, candidate.flexure_x.Mu_kNm),
        "Mu Y (kN·m)": (expected.Mu_y_kNm, candidate.flexure_y.Mu_kNm),
        "As X (cm²)": (expected.As_x_cm2, candidate.flexure_x.As_design_m2 * 1e4),
        "As Y (cm²)": (expected.As_y_cm2, candidate.flexure_y.As_design_m2 * 1e4),
        "Vu cortante (kN)": (expected.Vu_oneway_kN, candidate.shear_x.Vu_kN),
        "φVc cortante (kN)": (expected.phiVc_oneway_kN, candidate.shear_x.phi_Vc_kN),
        "Vu punzonamiento (kN)": (expected.Vu_punching_kN, candidate.punching.Vu_kN),
        "φVc punzonamiento (kN)": (expected.phiVc_punching_kN, candidate.punching.phi_Vc_kN),
    }
    return {k: v for k, v in comparisons.items() if v[0] is not None}


def test_registry_state_is_explicit():
    """Declara sin ambigüedad si hay o no validación bibliográfica cargada."""
    if not REFERENCE_CASES:
        pytest.skip(
            "VALIDACIÓN BIBLIOGRÁFICA PENDIENTE: no hay ejemplos resueltos cargados. "
            "No se han inventado datos de libros. Ver docs/validacion_bibliografica.md "
            "para el formato en que deben aportarse."
        )
    assert all(c.source.strip() for c in REFERENCE_CASES), "Todo caso debe citar su fuente"


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c.id)
def test_engine_matches_the_published_example(case: BibliographicCase):
    comparisons = run_case(case)
    assert comparisons, f"{case.id}: el libro no reporta ninguna magnitud comparable."

    failures: list[str] = []
    for name, (book, engine) in comparisons.items():
        tol = case.tolerance_overrides.get(name, case.tolerance)
        if book == 0:
            ok = abs(engine) < 1e-6
        else:
            ok = abs(engine - book) / abs(book) <= tol
        if not ok:
            diff = (engine - book) / book * 100 if book else float("inf")
            failures.append(f"  {name}: libro={book:.4g} motor={engine:.4g} ({diff:+.1f} %)")

    assert not failures, (
        f"\n{case.id} — {case.source}\n"
        + "\n".join(failures)
        + f"\nTolerancia: {case.tolerance * 100:.0f} %\n"
        + ("Supuestos declarados del autor:\n  " + "\n  ".join(case.author_assumptions)
           if case.author_assumptions else "")
    )
