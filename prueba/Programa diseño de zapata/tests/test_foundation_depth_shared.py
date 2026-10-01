"""E.050 art. 26.2 como restricción COMÚN a las tres tipologías — TBD-C10.

EL RIESGO QUE ESTOS TESTS CUBREN
================================
`Df >= 0,80 m` es un requisito sobre un DATO DE ENTRADA, no sobre una geometría
calculada. Ninguna combinación de B, L o h lo corrige. Eso lo vuelve tentador de
comprobar «al paso», con un `if` suelto en cada solver — y entonces cada tipología
acaba teniendo su propia versión, con su propio mensaje y su propio umbral.

Estos tests fijan que la comprobación vive en UN solo sitio,
`engine/soil/foundation_depth.py`, y que las tres tipologías llegan a ella. La
excepción de cimentación sobre roca la declara el usuario: si el motor la dedujera
de cualquier otro dato estaría relajando un requisito numérico explícito de la
norma por su cuenta.
"""

from __future__ import annotations

import inspect

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.depth_solver import evaluate_candidate
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel, KernCheckModel
from engine.soil.foundation_depth import (
    MIN_FOUNDATION_DEPTH_M,
    check_foundation_depth,
)

CODE = E060ConcreteCode()
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)


def _soil(Df_m: float, rock: bool = False) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=300.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
        Df_m=Df_m, founded_on_rock=rock, source_notes="prueba",
    )


def _loads(P: float = 700.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4)],
    )


def _aislada(Df_m: float, rock: bool = False):
    return evaluate_candidate(
        B_m=2.20, L_m=2.20, h_m=0.60, column=COL, soil=_soil(Df_m, rock),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=_loads(), code=CODE, contact_model=KernCheckModel(),
        depth_params=DepthSearchParameters(h_min_m=0.40, h_max_m=1.00, h_step_m=0.05),
    )


def _combinada(Df_m: float, rock: bool = False):
    def col(label, x, P, L):
        return ColumnOnFooting(
            label=label,
            placement=ColumnPlacement(column=COL, offset_x_m=x - L / 2.0),
            loads=_loads(P),
        )

    return solve_combined_footing(
        CombinedFootingLayout(B_m=8.0, L_m=3.60,
                              columns=[col("C1", 1.0, 900.0, 8.0), col("C2", 7.0, 900.0, 8.0)]),
        0.80,
        soil=_soil(Df_m, rock),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(),
        top_cover=TopCoverDeclaration(case="contacto_suelo_barras_pequenas"),
    )


# =========================================================================
# 1. El valor y la excepción vienen de la norma, no del motor
# =========================================================================

def test_el_minimo_es_el_valor_literal_del_articulo():
    """«no siendo menor de 0,80 metros». No es una heurística redondeada."""
    assert MIN_FOUNDATION_DEPTH_M == 0.80


def test_exactamente_080_cumple():
    """El artículo dice «no menor de», de modo que 0,80 m es admisible."""
    assert check_foundation_depth(0.80, founded_on_rock=False).status is CheckStatus.PASS


def test_por_debajo_de_080_es_FAIL_no_advertencia():
    """Es una exigencia numérica explícita, no una interpretación: no admite
    degradarse a WARNING."""
    r = check_foundation_depth(0.79, founded_on_rock=False)
    assert r.status is CheckStatus.FAIL
    assert "E.050 art. 26.2" in r.code_reference


def test_la_roca_es_la_unica_excepcion_y_la_declara_el_usuario():
    r = check_foundation_depth(0.40, founded_on_rock=True)
    assert r.status is CheckStatus.INFO, "No es un PASS: el mínimo deja de aplicar"
    assert r.Df_min_required_m is None


def test_el_valor_por_defecto_no_supone_roca():
    """Suponer roca relajaría el requisito por cuenta del motor."""
    assert _soil(1.20).founded_on_rock is False


# =========================================================================
# 2. Las tipologías llegan al MISMO módulo
# =========================================================================

def test_la_zapata_aislada_lo_verifica_y_lo_publica_en_la_traza():
    r = _aislada(0.50)
    entrada = r.trace.by_id("foundation_depth")
    assert entrada is not None, "Debe figurar en la memoria de cálculo"
    assert entrada.status is CheckStatus.FAIL
    assert entrada.code_name == "E.050"
    assert "26.2" in entrada.code_reference
    assert r.overall_status is CheckStatus.FAIL


def test_la_zapata_combinada_lo_verifica_y_lo_publica_en_la_traza():
    r = _combinada(0.50)
    entrada = r.trace.by_id("foundation_depth")
    assert entrada is not None
    assert entrada.status is CheckStatus.FAIL
    assert "26.2" in entrada.code_reference


@pytest.mark.parametrize("constructor", [_aislada, _combinada])
def test_con_Df_suficiente_deja_de_descartar(constructor):
    r = constructor(1.20)
    assert r.trace.by_id("foundation_depth").status is CheckStatus.PASS
    assert not any("26.2" in m for m in r.discard_reasons)


@pytest.mark.parametrize("constructor", [_aislada, _combinada])
def test_la_roca_declarada_levanta_el_descarte_en_ambas_tipologias(constructor):
    profundo = constructor(0.50, rock=True)
    assert profundo.trace.by_id("foundation_depth").status is CheckStatus.INFO
    assert not any("26.2" in m for m in profundo.discard_reasons)


@pytest.mark.parametrize("constructor", [_aislada, _combinada])
def test_el_motivo_de_descarte_es_el_mismo_texto_en_las_dos_tipologias(constructor):
    """Prueba de que no hay dos redacciones distintas del mismo requisito: el motivo
    de descarte lo produce el módulo compartido, no cada solver."""
    esperado = check_foundation_depth(0.50, founded_on_rock=False).message
    assert esperado in constructor(0.50).discard_reasons


@pytest.mark.parametrize("constructor", [_aislada, _combinada])
def test_la_sustitucion_numerica_tambien_sale_del_modulo_compartido(constructor):
    esperado = check_foundation_depth(0.50, founded_on_rock=False).equation_substituted
    assert constructor(0.50).trace.by_id("foundation_depth").equation_substituted == esperado


# =========================================================================
# 3. No hay una segunda implementación
# =========================================================================

@pytest.mark.parametrize("modulo_nombre", [
    "engine.foundation.depth_solver",
    "engine.foundation.combined_solver",
])
def test_ningun_solver_reimplementa_el_umbral(modulo_nombre):
    """El literal 0,80 no puede aparecer suelto en un solver: si el día de mañana el
    valor cambia, tiene que cambiar en un solo sitio."""
    import importlib

    fuente = inspect.getsource(importlib.import_module(modulo_nombre))
    assert "check_foundation_depth" in fuente, "El solver debe llamar al módulo compartido"
    for prohibido in ("0.80 m", "0.8 m", "MIN_FOUNDATION_DEPTH_M = "):
        assert prohibido not in fuente, (
            f"«{prohibido}» aparece en {modulo_nombre}: el mínimo de E.050 art. 26.2 "
            f"vive en engine/soil/foundation_depth.py y en ningún otro sitio."
        )
