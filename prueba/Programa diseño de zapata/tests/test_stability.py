"""L3 — Estabilidad: deslizamiento y volcamiento."""

import pytest

from engine.domain.load_cases import CombinationDefinition, LoadCase, LoadCaseKind, derive_load_case_set
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.results.status import CheckStatus
from engine.soil.stability import (
    FS_REFERENCE_RETAINING_WALL_PSEUDOSTATIC,
    FS_REFERENCE_RETAINING_WALL_STATIC,
    check_sliding,
    check_stability,
)

B, L, H_FOOTING = 2.5, 2.5, 0.60
SELF_WEIGHT = 150.0


def _soil(mu=None, fs_slide=None, fs_over=None, cohesion=None) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=150.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.20,
        mu_friction_soil_concrete=mu, FS_sliding_required=fs_slide,
        FS_overturning_required=fs_over, cohesion_kPa=cohesion,
    )


def _loads(**kwargs) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=500.0, **kwargs)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=700.0)],
    )


def _por_casos(**kwargs) -> LoadCaseSet:
    """Modo por casos (Fase 10B): CM = 400 kN, CV = 100 kN; M y H van en el caso CV para
    que la combinación de servicio S1 = CM + CV reproduzca P = 500 kN."""
    casos = [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=400.0),
        LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=100.0, **kwargs),
    ]
    return derive_load_case_set(casos, [
        CombinationDefinition(name="S1", type=LoadCombinationType.SERVICIO, factors={"CM": 1.0, "CV": 1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA, factors={"CM": 1.4, "CV": 1.7}),
    ])


# --- CASO: Hx = Hy = 0 ---------------------------------------------------------------

def test_no_horizontal_forces_sliding_not_applicable():
    r = check_sliding(_loads(), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.status is CheckStatus.PASS
    assert r.H_resultant_kN == 0.0
    assert "No aplicable" in r.message


def test_no_loads_at_all_gives_pass_on_every_stability_check():
    s = check_stability(_loads(), _soil(mu=0.5, fs_slide=1.5, fs_over=1.5), SELF_WEIGHT, B, L, H_FOOTING)
    assert s.sliding.status is CheckStatus.PASS
    assert s.overturning_x.status is CheckStatus.PASS
    assert s.overturning_y.status is CheckStatus.PASS
    assert s.status is CheckStatus.PASS
    assert s.applicable is False


# --- CASO: parámetro de fricción faltante -> NO VERIFICADO ----------------------------

def test_missing_friction_coefficient_gives_not_verified():
    r = check_sliding(_loads(Hx_kN=100.0), _soil(fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.status is CheckStatus.NOT_VERIFIED
    assert any("mu_friction" in p for p in r.missing_parameters)
    assert r.mu_used is None
    assert r.FS_obtained is None


def test_sin_fs_declarado_rige_el_criterio_adoptado_d10_2b():
    """ACTUALIZADO en D10-2b. E.020 art. 22.1 pide 1,25 al deslizamiento; el proyecto adopta
    1,50, que es MÁS ESTRICTO. El valor normativo se conserva en `E020_FS_SLIDING` y la
    referencia dice de dónde sale cada cosa: 1,50 no se presenta como cita de la norma.

    Lo que no cambia: ya no falta ningún dato; en modo directo sigue NO VERIFICADO, pero por
    E.020 art. 20.1 (no se conoce la carga muerta), no por falta de FS."""
    from engine.soil.stability import E020_FS_SLIDING, PROGRAM_FS_SLIDING

    assert E020_FS_SLIDING == 1.25, "El valor de la norma se conserva, no se sobrescribe"
    assert PROGRAM_FS_SLIDING == 1.50
    r = check_sliding(_loads(Hx_kN=100.0), _soil(mu=0.5), SELF_WEIGHT, B * L)
    assert r.FS_required == pytest.approx(1.50)
    assert "criterio del programa" in r.code_reference
    assert "E.020 art. 22.1 (1,25)" in r.code_reference
    assert r.missing_parameters == []
    assert r.status is CheckStatus.NOT_VERIFIED
    assert "E.020 art. 20.1" in r.message


def test_no_geotechnical_parameter_is_ever_invented():
    r = check_sliding(_loads(Hx_kN=100.0), _soil(), SELF_WEIGHT, B * L)
    assert r.mu_used is None
    assert r.friction_resistance_kN is None
    assert r.total_resistance_kN is None
    # y se informa el criterio normativo real disponible
    assert "muros de contención" in r.message.lower() or "MUROS DE CONTENCIÓN" in r.message


def test_los_valores_de_muros_siguen_siendo_solo_referencia():
    """E.050 art. 39.13.6 es de muros de contención. El FS por defecto que aplica ahora el
    motor sale de E.020 art. 22.1, y así lo cita (coincide en 1,25, pero la fuente es otra)."""
    assert FS_REFERENCE_RETAINING_WALL_STATIC == 1.50
    assert FS_REFERENCE_RETAINING_WALL_PSEUDOSTATIC == 1.25
    r = check_sliding(_por_casos(Hx_kN=100.0), _soil(mu=0.5), SELF_WEIGHT, B * L)
    assert "E.020 art. 22.1" in r.code_reference
    assert "39.13.6" not in r.code_reference


# --- CASO: deslizamiento PASS / FAIL ---------------------------------------------------

def test_sliding_pass():
    """Modo por casos. E.020 art. 20.1: solo la carga muerta estabiliza.
    N = CM + peso propio = 400 + 150 = 550 ; F = 0.5*550 = 275 ; H = 100 ; FS = 2.75 >= 1.5"""
    r = check_sliding(_por_casos(Hx_kN=100.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.N_total_kN == pytest.approx(550.0)
    assert r.friction_resistance_kN == pytest.approx(275.0)
    assert r.FS_obtained == pytest.approx(2.75)
    assert r.status is CheckStatus.PASS


def test_con_combinaciones_directas_un_cumplimiento_no_puede_afirmarse():
    """Modo directo: N = P + peso propio = 650 es cota superior de la estabilizante.
    FS = 3.25 >= 1.5, pero E.020 art. 20.1 no admite contar la carga viva: NO VERIFICADO."""
    r = check_sliding(_loads(Hx_kN=100.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.N_total_kN == pytest.approx(650.0)
    assert r.FS_obtained == pytest.approx(3.25)
    assert r.status is CheckStatus.NOT_VERIFIED


def test_las_cargas_no_muertas_que_restan_si_se_cuentan():
    """E.020 art. 20.1: lo no muerto no estabiliza, pero si RESTA carga vertical sí
    desestabiliza. Un sismo con P negativo reduce N."""
    casos = [
        LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=400.0),
        LoadCase(name="CS", kind=LoadCaseKind.CS, level="RESISTENCIA", P_kN=50.0, Hx_kN=80.0),
    ]
    lcs = derive_load_case_set(casos, [
        CombinationDefinition(name="S-", type=LoadCombinationType.SERVICIO, factors={"CM": 1.0, "CS": -1.0}),
        CombinationDefinition(name="U1", type=LoadCombinationType.FACTORIZADA, factors={"CM": 1.4}),
    ])
    r = check_sliding(lcs, _soil(mu=0.5, fs_slide=1.25), SELF_WEIGHT, B * L)
    assert r.N_total_kN == pytest.approx(400.0 - 50.0 + 150.0)


def test_sliding_fail_reports_the_missing_resistance():
    # H = 400 ; F = 325 ; FS = 0.8125 < 1.5
    r = check_sliding(_loads(Hx_kN=400.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.FS_obtained == pytest.approx(0.8125)
    assert r.status is CheckStatus.FAIL
    assert "NO CUMPLE" in r.message
    assert "Faltan" in r.message


def test_resultant_combines_both_components():
    r = check_sliding(_loads(Hx_kN=30.0, Hy_kN=40.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.H_resultant_kN == pytest.approx(50.0)  # 3-4-5


def test_cohesion_is_only_added_when_provided():
    sin_c = check_sliding(_loads(Hx_kN=100.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    con_c = check_sliding(
        _loads(Hx_kN=100.0), _soil(mu=0.5, fs_slide=1.5, cohesion=10.0), SELF_WEIGHT, B * L
    )
    assert sin_c.cohesion_resistance_kN is None
    assert con_c.cohesion_resistance_kN == pytest.approx(10.0 * B * L)
    assert con_c.FS_obtained > sin_c.FS_obtained


# --- CASO: combinación horizontal gobernante -------------------------------------------

def test_governing_horizontal_combination_is_the_worst_ratio():
    loads = LoadCaseSet(
        service=[
            LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=800.0, Hx_kN=100.0),
            LoadCombination(name="S2", type=LoadCombinationType.SERVICIO, P_kN=300.0, Hx_kN=150.0),
        ],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=700.0)],
    )
    r = check_sliding(loads, _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    # S2 tiene menos peso y más H -> peor relación
    assert r.governing_combo == "S2"


# --- CASO: volcamiento PASS / FAIL ------------------------------------------------------

def test_overturning_pass():
    """Modo por casos. M_estab = (CM 400 + 150)*2.5/2 = 687.5 ; M_volc = 100 + 50*0.60 = 130 ;
    FS = 5.288 >= 1.5"""
    s = check_stability(
        _por_casos(Mx_kNm=100.0, Hx_kN=50.0), _soil(mu=0.5, fs_slide=1.5, fs_over=1.5),
        SELF_WEIGHT, B, L, H_FOOTING,
    )
    ox = s.overturning_x
    assert ox.stabilizing_moment_kNm == pytest.approx(687.5)
    assert ox.overturning_moment_kNm == pytest.approx(130.0)
    assert ox.FS_obtained == pytest.approx(687.5 / 130.0)
    assert ox.status is CheckStatus.PASS


def test_overturning_fail():
    s = check_stability(
        _loads(Mx_kNm=700.0, Hx_kN=100.0), _soil(mu=0.5, fs_slide=1.5, fs_over=1.5),
        SELF_WEIGHT, B, L, H_FOOTING,
    )
    ox = s.overturning_x
    assert ox.overturning_moment_kNm == pytest.approx(760.0)
    assert ox.FS_obtained == pytest.approx(812.5 / 760.0)
    assert ox.FS_obtained < 1.5
    assert ox.status is CheckStatus.FAIL
    assert "NO CUMPLE" in ox.message


def test_sin_fs_de_volteo_declarado_rige_e020_art_21():
    """Fase 10B. E.020 art. 21: 1,5 contra el volteo. Sin sismo y sin FS declarado ya hay
    criterio; con combinaciones directas el cumplimiento no puede afirmarse."""
    directo = check_stability(_loads(Mx_kNm=100.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B, L, H_FOOTING)
    assert directo.overturning_x.FS_required == pytest.approx(1.5)
    assert directo.overturning_x.missing_parameters == []
    assert directo.overturning_x.status is CheckStatus.NOT_VERIFIED
    assert "E.020 art. 21" in directo.overturning_x.code_reference
    casos = check_stability(_por_casos(Mx_kNm=100.0), _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B, L, H_FOOTING)
    assert casos.overturning_x.status is CheckStatus.PASS


# --- Documentación del modelo de volcamiento ---------------------------------------------

def test_overturning_documents_pivot_moments_and_lever_arm():
    s = check_stability(
        _loads(Mx_kNm=100.0, Hx_kN=50.0), _soil(mu=0.5, fs_slide=1.5, fs_over=1.5),
        SELF_WEIGHT, B, L, H_FOOTING,
    )
    ox = s.overturning_x
    assert "Arista inferior" in ox.pivot_description
    assert "Empuje pasivo no considerado" in ox.pivot_description
    assert ox.horizontal_lever_arm_m == pytest.approx(H_FOOTING)
    assert ox.applied_moment_kNm == pytest.approx(100.0)
    assert ox.horizontal_force_kN == pytest.approx(50.0)
    assert ox.N_total_kN == pytest.approx(650.0)


def test_each_axis_uses_its_own_moment_and_horizontal_force():
    """My y Hx gobiernan el vuelco alrededor del eje X; Mx y Hy el del eje Y."""
    s = check_stability(
        _loads(My_kNm=200.0, Mx_kNm=50.0, Hx_kN=10.0, Hy_kN=80.0),
        _soil(mu=0.5, fs_slide=1.5, fs_over=1.5), SELF_WEIGHT, B, L, H_FOOTING,
    )
    assert s.overturning_x.applied_moment_kNm == pytest.approx(50.0)
    assert s.overturning_x.horizontal_force_kN == pytest.approx(10.0)
    assert s.overturning_y.applied_moment_kNm == pytest.approx(200.0)
    assert s.overturning_y.horizontal_force_kN == pytest.approx(80.0)


def test_service_loads_are_used_not_factored():
    """E.050 art. 17.1: el FS de cimentaciones usa cargas de SERVICIO."""
    loads = LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=500.0, Hx_kN=100.0)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=9999.0, Hx_kN=9999.0)],
    )
    r = check_sliding(loads, _soil(mu=0.5, fs_slide=1.5), SELF_WEIGHT, B * L)
    assert r.H_resultant_kN == pytest.approx(100.0)  # no 9999
    assert r.N_total_kN == pytest.approx(650.0)
