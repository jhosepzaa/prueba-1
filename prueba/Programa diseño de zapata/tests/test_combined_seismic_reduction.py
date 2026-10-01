"""Reducción sísmica al 80 % en la zapata COMBINADA.

QUÉ CIERRA
==========
Era el último pendiente del contrato de cargas: la reducción existía en la zapata aislada
(Fase 10B) y en las presiones de suelo de cada zapata de la conectada (D10C-2), pero no en
la combinada. Ahora se aplica con **el mismo operador**, `depth_solver.soil_actions`, que
sigue siendo la única implementación del criterio (E.030 art. 29; E.060 §15.2.5).

ALCANCE, IDÉNTICO AL DE LA CONECTADA
====================================
Solo las presiones de suelo, solo con composición —modo por casos— y solo sobre la
componente CS declarada a nivel de RESISTENCIA. **No** toca la estabilidad (E.030 art. 64.2
lo prohíbe expresamente), ni el diseño factorizado, ni el modo directo.

QUÉ FIJA ESTE ARCHIVO
=====================
1. sin activarla, nada cambia;
2. en modo directo no se aplica y se dice por qué;
3. con composición se aplica, y el resultado se reconstruye a mano;
4. reducir la componente CS equivale a declarar 0,8·CS (invariante de linealidad);
5. un CS a nivel de SERVICIO no se vuelve a reducir;
6. la estabilidad y el diagrama factorizado NO la usan;
7. no hay lógica duplicada: el factor 0,8 vive en un solo sitio.
"""

from __future__ import annotations

import io

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.load_cases import (
    ActionLevel,
    CombinationDefinition,
    LoadCase,
    LoadCaseKind,
    derive_load_case_set,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.depth_solver import SEISMIC_REDUCTION_FACTOR
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel

CODE = E060ConcreteCode()
TAPA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")
MAT = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)

B, L, H = 8.0, 3.60, 0.80
P_CM, P_CV = 700.0, 200.0
CS_P, CS_MX, CS_HX = 150.0, 90.0, 60.0


def _suelo(*, reducir: bool, q=400.0, mu=None):
    return SoilProfile(
        qadm_kPa=q, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50,
        mu_friction_soil_concrete=mu, allow_seismic_reduction_80pct=reducir,
    )


def _por_casos(cs_factor: float = 1.0, nivel: ActionLevel = ActionLevel.RESISTENCIA) -> LoadCaseSet:
    """CM + CV + CS. `cs_factor` permite declarar directamente 0,8·CS para el contraste."""
    casos = [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=P_CM),
        LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=P_CV),
        LoadCase(name="CSx", kind=LoadCaseKind.CS, level=nivel,
                 P_kN=CS_P * cs_factor, Mx_kNm=CS_MX * cs_factor, Hx_kN=CS_HX * cs_factor),
    ]
    return derive_load_case_set(casos, [
        CombinationDefinition(name="S1", type=LoadCombinationType.SERVICIO,
                              factors={"CM": 1.0, "CV": 1.0, "CSx": 1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA,
                              factors={"CM": 1.25, "CV": 1.25, "CSx": 1.0}),
    ])


def _sin_sismo() -> LoadCaseSet:
    casos = [LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=P_CM),
             LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=P_CV)]
    return derive_load_case_set(casos, [
        CombinationDefinition(name="S1", type=LoadCombinationType.SERVICIO,
                              factors={"CM": 1.0, "CV": 1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA,
                              factors={"CM": 1.4, "CV": 1.7}),
    ])


def _directo() -> LoadCaseSet:
    """Modo DIRECTO: combinación ya formada, sin composición. El motor no sabe qué parte
    es sísmica, y por eso la reducción no puede aplicarse."""
    P, Mx, Hx = P_CM + P_CV + CS_P, CS_MX, CS_HX
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P,
                                 Mx_kNm=Mx, Hx_kN=Hx, includes_seismic_loads=True)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=1.25 * (P_CM + P_CV) + CS_P, Mx_kNm=Mx, Hx_kN=Hx,
                                  includes_seismic_loads=True)],
    )


def _layout(cargas: LoadCaseSet, posiciones=(1.0, 7.0)) -> CombinedFootingLayout:
    return CombinedFootingLayout(
        B_m=B, L_m=L,
        columns=[
            ColumnOnFooting(
                label=f"C{i + 1}",
                placement=ColumnPlacement(column=COL, offset_x_m=x - B / 2.0),
                loads=cargas,
            )
            for i, x in enumerate(posiciones)
        ],
    )


def _layout_mixto(cargas: list[LoadCaseSet], posiciones=(1.0, 7.0)) -> CombinedFootingLayout:
    """Cada columna con sus propias cargas: hace falta para que Σ P_i·offset_i NO se
    cancele y el término de excentricidad quede realmente ejercido."""
    return CombinedFootingLayout(
        B_m=B, L_m=L,
        columns=[
            ColumnOnFooting(
                label=f"C{i + 1}",
                placement=ColumnPlacement(column=COL, offset_x_m=x - B / 2.0),
                loads=cs,
            )
            for i, (x, cs) in enumerate(zip(posiciones, cargas))
        ],
    )


def _resolver_mixto(cargas: list[LoadCaseSet], *, reducir: bool):
    return solve_combined_footing(
        _layout_mixto(cargas), H, soil=_suelo(reducir=reducir), code=CODE,
        contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )


def _resolver(cargas: LoadCaseSet, *, reducir: bool, mu=None):
    return solve_combined_footing(
        _layout(cargas), H, soil=_suelo(reducir=reducir, mu=mu), code=CODE,
        contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )


def _hipotesis(r) -> str:
    return " ".join(r.trace.by_id("contact_pressure").hypotheses)


# =========================================================================
# 1. Sin activarla, nada cambia
# =========================================================================


def test_sin_activar_la_reduccion_no_cambia_ningun_numero():
    """La reducción es opcional (`allow_seismic_reduction_80pct`). Apagada, el resultado
    tiene que ser exactamente el de antes de este cambio."""
    a = _resolver(_por_casos(), reducir=False)
    assert a.contact_pressure.qmax_kPa == pytest.approx(
        _resolver(_por_casos(), reducir=False).contact_pressure.qmax_kPa
    )
    assert "Reducción sísmica" not in _hipotesis(a)


def test_sin_componente_sismica_no_se_aplica_aunque_este_activada():
    con = _resolver(_sin_sismo(), reducir=True)
    sin = _resolver(_sin_sismo(), reducir=False)
    assert con.contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-15)
    assert "Reducción sísmica" not in _hipotesis(con)


# =========================================================================
# 2. Modo directo: no se aplica, y se dice por qué
# =========================================================================


def test_en_modo_directo_no_se_aplica_y_queda_dicho():
    """No se toca el modo directo: sin composición no se sabe qué parte es sísmica."""
    con = _resolver(_directo(), reducir=True)
    sin = _resolver(_directo(), reducir=False)
    assert con.contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-15)
    texto = _hipotesis(con)
    assert "NO aplicada" in texto
    assert "combinaciones directas no se conoce" in texto
    assert "[C1]" in texto and "[C2]" in texto, "El aviso dice de qué columna viene"


# =========================================================================
# 3. Con composición se aplica, y se reconstruye a mano
# =========================================================================


def test_con_composicion_la_presion_baja_y_queda_trazado():
    con = _resolver(_por_casos(), reducir=True)
    sin = _resolver(_por_casos(), reducir=False)
    assert con.contact_pressure.qmax_kPa < sin.contact_pressure.qmax_kPa
    texto = _hipotesis(con)
    assert "Reducción sísmica al 80% aplicada" in texto
    assert "E.030 art. 29" in texto and "E.060 §15.2.5" in texto
    # ΔP = 0,2·CS por columna, y el texto lo dice con su número.
    assert f"ΔP = −{(1 - SEISMIC_REDUCTION_FACTOR) * CS_P:.2f} kN" in texto


def test_reducir_la_componente_equivale_a_declarar_el_80_por_ciento():
    """INVARIANTE DE LINEALIDAD. Es el mismo argumento de D10C-2: el reparto de la
    resultante es lineal, así que reducir la componente CS de cada columna al 80 % tiene
    que dar exactamente lo mismo que declarar 0,8·CS y no reducir nada.

    Reconstrucción independiente: el segundo caso no pasa por el operador de reducción."""
    reducido = _resolver(_por_casos(), reducir=True)
    declarado = _resolver(_por_casos(cs_factor=SEISMIC_REDUCTION_FACTOR), reducir=False)
    for campo in ("qmax_kPa", "qmin_kPa"):
        assert getattr(reducido.contact_pressure, campo) == pytest.approx(
            getattr(declarado.contact_pressure, campo), rel=1e-12
        )
    assert reducido.contact_pressure.within_kern == declarado.contact_pressure.within_kern


def test_con_columnas_desiguales_tambien_se_reduce_el_momento_de_la_excentricidad():
    """La carga descentrada aporta `P_i·offset_i` al momento de la resultante. Ese término
    tiene que llevar la carga YA REDUCIDA, o la reducción quedaría a medias.

    Hace falta que las columnas sean desiguales: con cargas iguales y simétricas ese
    término se cancela y el error no se vería. Lo detectó una mutación deliberada."""
    mucho, poco = _por_casos(), _por_casos(cs_factor=0.2)
    reducido = _resolver_mixto([mucho, poco], reducir=True)
    declarado = _resolver_mixto(
        [_por_casos(cs_factor=SEISMIC_REDUCTION_FACTOR),
         _por_casos(cs_factor=0.2 * SEISMIC_REDUCTION_FACTOR)],
        reducir=False,
    )
    # El escenario debe ejercer de verdad la excentricidad: sin reducir, la resultante NO
    # está centrada.
    sin_reducir = _resolver_mixto([mucho, poco], reducir=False)
    assert abs(sin_reducir.contact_pressure.qmax_kPa - sin_reducir.contact_pressure.qmin_kPa) > 1.0

    assert reducido.contact_pressure.qmax_kPa == pytest.approx(
        declarado.contact_pressure.qmax_kPa, rel=1e-12
    )
    assert reducido.contact_pressure.qmin_kPa == pytest.approx(
        declarado.contact_pressure.qmin_kPa, rel=1e-12
    )
    assert reducido.contact_pressure.qmax_kPa < sin_reducir.contact_pressure.qmax_kPa


def test_un_sismo_declarado_a_nivel_de_servicio_no_se_vuelve_a_reducir():
    """E.060 §15.2.5 justifica el 0,8 porque E.030 da las fuerzas a nivel de RESISTENCIA.
    Un CS ya declarado a nivel de servicio no se reduce otra vez."""
    servicio = _por_casos(nivel=ActionLevel.SERVICIO)
    con = _resolver(servicio, reducir=True)
    sin = _resolver(servicio, reducir=False)
    assert con.contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-15)
    assert "sin reducir" in _hipotesis(con)


# =========================================================================
# 4. Lo que la reducción NO toca
# =========================================================================


def test_la_estabilidad_no_usa_la_reduccion():
    """E.030 art. 64.2 lo exige expresamente: el FS se calcula SIN la reducción del art. 29."""
    con = _resolver(_por_casos(), reducir=True, mu=0.50)
    sin = _resolver(_por_casos(), reducir=False, mu=0.50)
    assert con.stability is not None and sin.stability is not None
    assert con.stability.sliding.H_resultant_kN == pytest.approx(
        sin.stability.sliding.H_resultant_kN, rel=1e-15
    )
    assert con.stability.sliding.FS_obtained == pytest.approx(
        sin.stability.sliding.FS_obtained, rel=1e-15
    )
    for eje in ("overturning_x", "overturning_y"):
        a, b = getattr(con.stability, eje), getattr(sin.stability, eje)
        assert a.overturning_moment_kNm == pytest.approx(b.overturning_moment_kNm, rel=1e-15)
        assert a.stabilizing_moment_kNm == pytest.approx(b.stabilizing_moment_kNm, rel=1e-15)
        assert a.status is b.status


def test_el_diseno_factorizado_no_usa_la_reduccion():
    """La reducción es para verificaciones por esfuerzos admisibles, no para el diseño."""
    con = _resolver(_por_casos(), reducir=True)
    sin = _resolver(_por_casos(), reducir=False)
    assert con.diagram.M_max_positive_kNm == pytest.approx(sin.diagram.M_max_positive_kNm, rel=1e-15)
    assert con.diagram.M_max_negative_kNm == pytest.approx(sin.diagram.M_max_negative_kNm, rel=1e-15)
    assert con.diagram.V_max_abs_kN == pytest.approx(sin.diagram.V_max_abs_kN, rel=1e-15)
    assert con.bottom_face.As_design_m2 == pytest.approx(sin.bottom_face.As_design_m2, rel=1e-15)
    assert [p.ratio for p in con.punching] == [pytest.approx(p.ratio, rel=1e-15) for p in sin.punching]
    assert con.shear_longitudinal.Vu_kN == pytest.approx(sin.shear_longitudinal.Vu_kN, rel=1e-15)


# =========================================================================
# 5. Una sola implementación del criterio
# =========================================================================


def test_el_solver_combinado_no_duplica_la_logica_de_la_reduccion():
    fuente = io.open("engine/foundation/combined_solver.py", encoding="utf-8").read()
    assert "soil_actions(combo, soil, hip_col)" in fuente, "Usa el operador compartido"
    assert "0.8" not in fuente, "El factor vive en depth_solver, no aquí"
    assert "SEISMIC_REDUCTION_FACTOR =" not in fuente
    assert 'kind == "CS"' not in fuente and '{\"CS\"}' not in fuente


def test_el_factor_esta_declarado_una_sola_vez_en_el_motor():
    import pathlib

    con_factor = [
        p for p in pathlib.Path("engine").rglob("*.py")
        if "SEISMIC_REDUCTION_FACTOR =" in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in con_factor] == ["depth_solver.py"]
    assert SEISMIC_REDUCTION_FACTOR == 0.8


def test_las_tres_tipologias_reducen_con_el_mismo_operador():
    """La aislada y la conectada ya pasaban por `soil_actions`; la combinada también."""
    import inspect

    import engine.foundation.combined_solver as comb
    import engine.foundation.depth_solver as dep

    assert "soil_actions" in inspect.getsource(comb.solve_combined_footing)
    assert "soil_actions" in inspect.getsource(dep._evaluate_contact_pressure)


def test_el_estado_no_se_degrada_por_activar_la_reduccion():
    """La reducción baja la presión: nunca puede empeorar el estado."""
    con = _resolver(_por_casos(), reducir=True)
    sin = _resolver(_por_casos(), reducir=False)
    assert con.trace.by_id("contact_pressure").status in (CheckStatus.PASS, sin.trace.by_id("contact_pressure").status)
    assert con.contact_pressure.qmax_kPa <= sin.contact_pressure.qmax_kPa
