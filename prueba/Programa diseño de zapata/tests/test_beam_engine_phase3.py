"""FASE 3 — Motor de vigas de concreto armado.

Era el bloqueo TBD-4 de la auditoría de Fase 0: sin §11.5 no se podía diseñar la
viga de conexión.

QUÉ SE VERIFICA
===============
1. El As mínimo de VIGAS (§10.5) es distinto del de zapatas y no debe confundirse:
   §10.5.1 excluye zapatas, una viga no está excluida. Es el riesgo R9.
2. Cortante con estribos: ec. 11-13, 11-15, los límites de §11.5.5 y §11.5.7.9.
3. Las exenciones de §11.5.6.1, incluida la de losas y zapatas.
4. §21.12.3.2: dimensión transversal mínima y estribos cerrados.
5. E.030 art. 65.1: fuerza axial y su condición de disparo.
6. Lo que NO se verifica queda declarado, no oculto.
"""

from __future__ import annotations

import math

import pytest

from engine.beam.beam_flexure import beam_minimum_steel, cracking_moment_kNm
from engine.beam.beam_shear import (
    av_min_over_spacing_m,
    check_beam_shear,
    concrete_shear_strength_kN,
    max_stirrup_spacing_m,
)
from engine.beam.connecting_beam import (
    SeismicContext,
    check_dimensions,
    confinement_spacing_limit,
    design_connecting_beam,
)
from engine.results.status import CheckStatus

TONF_TO_KN = 9.80665
KGF_CM2_TO_MPA = 0.0980665

FC = 210 * KGF_CM2_TO_MPA
FY = 4200 * KGF_CM2_TO_MPA


# =========================================================================
# 1. As mínimo de vigas — §10.5, y por qué no vale el de zapatas
# =========================================================================

def test_el_momento_de_agrietamiento_usa_la_seccion_bruta():
    """Mcr = fr·Ig/Yt con fr = 0,62·sqrt(f'c), sobre la sección BRUTA."""
    b, h, fc = 0.35, 1.20, 21.0
    Mcr, fr = cracking_moment_kNm(fc, b, h)
    assert fr == pytest.approx(0.62 * math.sqrt(fc))
    esperado = fr * (b * h**3 / 12.0) / (h / 2.0) * 1000.0
    assert Mcr == pytest.approx(esperado)


def test_las_dos_exigencias_de_10_5_son_simultaneas_no_alternativas():
    """§10.5.1 y §10.5.2 se piden a la vez: gobierna la mayor."""
    m = beam_minimum_steel(0.35, 1.20, 1.10, FC, FY, As_required_by_analysis_m2=0.0035)
    assert m.As_min_governing_m2 == pytest.approx(max(m.As_min_10_5_1_m2, m.As_min_10_5_2_m2))


def test_la_ecuacion_10_3_da_el_valor_de_la_norma():
    """As_min = (0,22·sqrt(f'c)/fy)·bw·d"""
    b, d = 0.35, 1.10
    m = beam_minimum_steel(b, 1.20, d, FC, FY, As_required_by_analysis_m2=0.0)
    assert m.As_min_10_5_2_m2 == pytest.approx(0.22 * math.sqrt(FC) / FY * b * d)


def test_el_minimo_de_viga_no_es_el_de_zapata():
    """RIESGO R9 de la auditoría de Fase 0. §10.5.1 excluye expresamente a zapatas y
    losas macizas; el motor las lleva a §9.7 vía §10.6. Una viga NO está excluida y
    le corresponde otro mínimo. Reutilizar la función de zapatas daría otro número."""
    from engine.codes.peru.e060_concrete import E060ConcreteCode

    b, h, d = 0.35, 1.20, 1.10
    rho_zapata, _ = E060ConcreteCode().rho_min_temperature(FY, "corrugada")
    As_como_zapata = rho_zapata * b * h
    As_como_viga = beam_minimum_steel(b, h, d, FC, FY, 0.0).As_min_governing_m2
    assert As_como_viga != pytest.approx(As_como_zapata), (
        "Si coincidieran, la distinción entre §9.7 y §10.5 se habría perdido."
    )


def test_la_exencion_de_10_5_3_no_alcanza_a_una_viga():
    """Fase 10A (A3). E.060 propuesta 2019, §10.5.3: la exención del tercio es «para
    losas macizas y losas nervadas que cumplan con 8.12». Una viga no puede acogerse:
    aunque 4/3 del As de análisis quede por debajo de los mínimos, rige el mayor de
    §10.5.1 y §10.5.2."""
    m = beam_minimum_steel(0.35, 1.20, 1.10, FC, FY, As_required_by_analysis_m2=0.0002)
    assert not m.exempt_by_10_5_3
    assert m.As_min_governing_m2 == pytest.approx(max(m.As_min_10_5_1_m2, m.As_min_10_5_2_m2))
    assert "§10.5.3" not in m.governed_by


def test_sin_exencion_cuando_el_analisis_ya_pide_mucho():
    m = beam_minimum_steel(0.35, 1.20, 1.10, FC, FY, As_required_by_analysis_m2=0.010)
    assert not m.exempt_by_10_5_3


# =========================================================================
# 2. Cortante con estribos — §11.5
# =========================================================================

def test_vc_es_la_ecuacion_11_3():
    assert concrete_shear_strength_kN(21.0, 0.35, 1.10) == pytest.approx(
        0.17 * math.sqrt(21.0) * 350.0 * 1100.0 / 1000.0
    )


def test_av_min_toma_el_mayor_entre_la_ec_11_13_y_su_piso():
    """§11.5.6.2: «Av_min = 0,062·sqrt(f'c)·bw·s/fyt, pero no debe ser menor que
    0,35·bw·s/fyt». Con f'c bajo gobierna el piso."""
    bw, fyt = 0.35, 420.0
    for fc in (17.0, 21.0, 45.0):
        obtenido = av_min_over_spacing_m(fc, bw, fyt)
        por_ec = 0.062 * math.sqrt(fc) * bw * 1000.0 / fyt / 1000.0
        piso = 0.35 * bw * 1000.0 / fyt / 1000.0
        assert obtenido == pytest.approx(max(por_ec, piso))
    # Con f'c = 17 MPa el piso manda; con 45, la ecuación.
    assert av_min_over_spacing_m(17.0, bw, fyt) == pytest.approx(0.35 * 350.0 / 420.0 / 1000.0)


def test_la_separacion_maxima_es_d_medios_o_600mm():
    limite, ref = max_stirrup_spacing_m(d_m=1.10, Vs_kN=0.0, fc_MPa=21.0, bw_m=0.35)
    assert limite == pytest.approx(min(1.10 / 2.0, 0.600))
    assert "§11.5.5.1" in ref


def test_un_vs_alto_reduce_la_separacion_a_la_mitad():
    """§11.5.5.3: donde Vs supera 0,33·sqrt(f'c)·bw·d."""
    fc, bw, d = 21.0, 0.35, 1.10
    umbral = 0.33 * math.sqrt(fc) * 350.0 * 1100.0 / 1000.0
    normal, _ = max_stirrup_spacing_m(d, umbral * 0.5, fc, bw)
    reducida, ref = max_stirrup_spacing_m(d, umbral * 1.5, fc, bw)
    assert reducida == pytest.approx(normal / 2.0)
    assert "§11.5.5.3" in ref


def test_vs_por_encima_del_maximo_es_seccion_insuficiente():
    """§11.5.7.9: «En ningún caso se debe considerar Vs mayor que 0,66·sqrt(f'c)·bw·d».
    Los estribos no pueden compensarlo: hay que cambiar la sección."""
    r = check_beam_shear(Vu_kN=6000.0, bw_m=0.25, h_m=0.50, d_m=0.42, fc_MPa=21.0, fyt_MPa=420.0)
    assert r.Vs_exceeds_limit
    assert not r.status_ok
    assert "§11.5.7.9" in r.message
    assert "aumentar la sección" in r.message


def test_la_ecuacion_11_15_relaciona_Av_s_con_Vs():
    """Vs = Av·fyt·d/s, de donde Av/s = Vs/(fyt·d)."""
    r = check_beam_shear(Vu_kN=900.0, bw_m=0.35, h_m=1.20, d_m=1.10, fc_MPa=21.0, fyt_MPa=420.0)
    assert r.stirrups_required
    assert r.Av_over_s_required_m == pytest.approx(
        r.Vs_required_kN * 1000.0 / (420.0 * 1100.0) / 1000.0
    )


def test_fyt_por_encima_de_420_se_rechaza():
    """§11.5.2 limita fy y fyt del refuerzo de cortante a 420 MPa."""
    with pytest.raises(ValueError, match="§11.5.2"):
        check_beam_shear(Vu_kN=100.0, bw_m=0.35, h_m=1.20, d_m=1.10, fc_MPa=21.0, fyt_MPa=500.0)


# =========================================================================
# 3. Exenciones de §11.5.6.1
# =========================================================================

def test_las_zapatas_estan_exentas_del_refuerzo_minimo():
    """§11.5.6.1(a). Es lo que permite que una zapata combinada no lleve estribos
    mínimos aunque Vu supere 0,5·Vc."""
    r = check_beam_shear(
        Vu_kN=400.0, bw_m=3.60, h_m=0.80, d_m=0.72, fc_MPa=21.0, fyt_MPa=420.0,
        is_slab_or_footing=True,
    )
    assert not r.av_min_required
    assert "§11.5.6.1(a)" in r.av_min_exemption


def test_una_viga_de_poco_peralte_esta_exenta():
    """§11.5.6.1(c): h <= 250 mm."""
    r = check_beam_shear(Vu_kN=40.0, bw_m=0.25, h_m=0.25, d_m=0.20, fc_MPa=21.0, fyt_MPa=420.0)
    assert not r.av_min_required
    assert "§11.5.6.1(c)" in r.av_min_exemption


def test_una_viga_normal_no_esta_exenta():
    r = check_beam_shear(Vu_kN=300.0, bw_m=0.35, h_m=1.20, d_m=1.10, fc_MPa=21.0, fyt_MPa=420.0)
    assert r.av_min_required
    assert r.av_min_exemption == ""


# =========================================================================
# 4. §21.12.3.2 — dimensión y confinamiento
# =========================================================================

def test_la_dimension_minima_es_la_luz_libre_entre_veinte():
    d = check_dimensions(b_m=0.35, h_m=1.20, clear_span_m=5.50)
    assert d.min_dimension_required_m == pytest.approx(5.50 / 20.0)
    assert d.min_dimension_provided_m == pytest.approx(0.35), "La MENOR de las dos dimensiones"
    assert d.ok


def test_el_tope_de_450mm_limita_el_requisito_no_la_viga():
    """Fase 10A (A2). §21.12.3.2 (propuesta 2019): «no necesita ser mayor a 450 mm».
    Acota lo EXIGIDO, no la dimensión posible. (El campo conserva su nombre histórico
    `capped_at_400mm` por contrato.)"""
    d = check_dimensions(b_m=0.45, h_m=1.50, clear_span_m=12.0)
    assert d.capped_at_400mm
    assert d.min_dimension_required_m == pytest.approx(0.450)
    assert d.ok, "0,45 m alcanza el requisito topado de 0,45 m"
    assert not check_dimensions(b_m=0.42, h_m=1.50, clear_span_m=12.0).ok, (
        "0,42 m cumplía con el tope anterior de 400 mm y ya no cumple"
    )


def test_una_viga_demasiado_esbelta_no_cumple():
    d = check_dimensions(b_m=0.20, h_m=0.60, clear_span_m=8.0)
    assert not d.ok


@pytest.mark.parametrize(
    "b, h, db, esperado",
    [
        (0.35, 1.20, 25.4, 0.300),   # gobierna el tope absoluto de 300 mm
        (0.25, 0.60, 12.7, 0.2032),  # gobierna 16·db
        (0.15, 0.40, 25.4, 0.150),   # gobierna la menor dimensión
    ],
)
def test_la_separacion_de_confinamiento_toma_el_menor_de_los_tres(b, h, db, esperado):
    c = confinement_spacing_limit(b, h, db)
    assert c.spacing_limit_m == pytest.approx(esperado, rel=1e-3)


def test_el_confinamiento_manda_sobre_la_separacion_de_cortante():
    """§21.12.3.2 es más restrictivo que §11.5.5.1 en una viga de cimentación
    típica: la separación final debe bajar."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=1240.0,
        seismic=SeismicContext(qadm_kPa=176.5),
    )
    assert r.shear.layout is not None
    assert r.confinement.spacing_provided_m <= r.confinement.spacing_limit_m + 1e-9
    assert r.confinement.spacing_provided_m < r.shear.layout.spacing_m
    assert any("§21.12.3.2" in m for m in r.messages)


def test_sin_estribos_por_cortante_el_confinamiento_los_exige_igual():
    """Son estribos CERRADOS de confinamiento, no de cortante: §21.12.3.2 no depende
    de que Vu supere φVc."""
    r = design_connecting_beam(
        b_m=0.40, h_m=1.20, d_m=1.10, clear_span_m=5.0,
        Mu_negative_kNm=200.0, Mu_positive_kNm=100.0, Vu_kN=10.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=1000.0,
        seismic=SeismicContext(qadm_kPa=200.0),
    )
    assert r.confinement.spacing_provided_m is not None
    assert any("§21.12.3.2 sí" in m for m in r.messages)


# =========================================================================
# 5. E.030 art. 65.1 — fuerza axial
# =========================================================================

def test_qadm_bajo_dispara_el_requisito_axial():
    ctx = SeismicContext(qadm_kPa=80.0)
    aplica, motivo = ctx.triggers_e030_65_1()
    assert aplica
    assert "0,10 MPa" in motivo


@pytest.mark.parametrize("perfil, zona, esperado", [
    ("S3", 4, True), ("S4", 3, True),
    ("S2", 4, False), ("S3", 2, False), ("S1", 1, False),
])
def test_la_combinacion_de_perfil_y_zona_decide(perfil, zona, esperado):
    """(S3 o S4) Y (Zona 3 o 4). Ambas condiciones, no una."""
    ctx = SeismicContext(soil_profile=perfil, seismic_zone=zona, qadm_kPa=200.0)
    assert ctx.triggers_e030_65_1()[0] is esperado


def test_sin_declarar_perfil_ni_zona_se_dice_que_no_pudo_comprobarse():
    """No es lo mismo «no aplica» que «no se pudo comprobar»."""
    aplica, motivo = SeismicContext(qadm_kPa=200.0).triggers_e030_65_1()
    assert not aplica
    assert "no puede comprobarse" in motivo


def test_la_fuerza_axial_es_el_diez_por_ciento_de_las_cargas_amplificadas():
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=2000.0,
        seismic=SeismicContext(soil_profile="S3", seismic_zone=4, qadm_kPa=200.0),
    )
    assert r.axial_required
    assert r.axial_N_kN == pytest.approx(0.10 * 2000.0)


def test_con_fuerza_axial_el_phi_deja_de_ser_el_de_flexion_pura():
    """§9.3.2: 0,90 en tracción con o sin flexión; 0,70 en compresión con o sin
    flexión para elementos sin refuerzo en espiral."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=2000.0,
        seismic=SeismicContext(soil_profile="S4", seismic_zone=3, qadm_kPa=200.0),
    )
    assert r.phi_axial == pytest.approx(0.70)
    assert any("0,90 en tracción" in m for m in r.messages)


def test_la_interaccion_axial_flexion_si_se_resuelve():
    """ACTUALIZADO: antes se declaraba NO VERIFICADA. Ahora se construye el diagrama
    de interacción y se comprueba el punto (Pu, Mu) contra él."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=2000.0,
        seismic=SeismicContext(soil_profile="S3", seismic_zone=4, qadm_kPa=200.0),
    )
    assert r.axial_required
    assert r.axial_flexure_negative is not None
    assert r.axial_flexure_positive is not None
    assert r.axial_flexure_negative.demand_ratio > 0
    assert any("Interacción P−M" in m for m in r.messages)


def test_la_interaccion_se_evalua_en_traccion_Y_en_compresion():
    """E.030 art. 65.1 dice «en tracción o compresión»: el signo de N no está
    definido, así que hay que comprobar los dos y quedarse con el peor."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=2000.0,
        seismic=SeismicContext(soil_profile="S4", seismic_zone=4, qadm_kPa=200.0),
    )
    # La tracción reduce la capacidad a momento, así que debe ser la que gobierne.
    assert r.axial_flexure_negative.Pu_kN < 0, (
        "Con la misma magnitud, la tracción es más desfavorable que la compresión"
    )


def test_sin_sistema_declarado_21_12_3_3_no_puede_resolverse():
    """§21.2 remite a §21.4 o §21.5 según el sistema. Sin saber cuál es, no puede
    determinarse qué requisitos corresponden — y eso no es lo mismo que decir que
    no aplican."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=643.0, Vu_kN=251.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=1240.0,
        seismic=SeismicContext(qadm_kPa=200.0, part_of_lateral_force_system=True),
    )
    assert r.status is CheckStatus.NOT_VERIFIED
    assert r.lateral_requirements.applies
    assert r.lateral_requirements.section == ""
    assert "no se ha declarado el sistema" in r.lateral_requirements.reason.lower()


# =========================================================================
# 6. Benchmark — Aragón §3.6, problema 1
# =========================================================================

def _aragon_3_6():
    """Viga de conexión 35 × 120 cm, d = 110 cm, luz entre ejes 6,00 m.
    El libro reporta: Mu(−) = 140,6 t·m → As = 37,7 cm²;
    Mu(+) = 65,6 t·m → As = 16,5 cm²; Vu = 25,6 t; Vc = 25,1 t."""
    return design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=6.0 - 0.50,
        Mu_negative_kNm=140.6 * TONF_TO_KN,
        Mu_positive_kNm=65.6 * TONF_TO_KN,
        Vu_kN=25.6 * TONF_TO_KN,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4,
        sum_Pu_kN=(1.4 * 60 + 1.7 * 25) * TONF_TO_KN,
        seismic=SeismicContext(qadm_kPa=1.8 * 98.0665),
    )


def test_aragon_3_6_reproduce_el_acero_negativo():
    assert _aragon_3_6().As_negative_m2 * 1e4 == pytest.approx(37.7, rel=0.03)


def test_aragon_3_6_reproduce_el_acero_positivo():
    assert _aragon_3_6().As_positive_m2 * 1e4 == pytest.approx(16.5, rel=0.03)


def test_aragon_3_6_reproduce_la_resistencia_al_cortante():
    """El libro: Vc = 0,85·0,53·sqrt(210)·35·110 = 25,1 t, con el φ ya dentro.
    La diferencia esperable es el redondeo del coeficiente: 0,53 en kgf/cm² frente a
    0,17 en MPa difieren un 1,4 %."""
    assert _aragon_3_6().shear.phi_Vc_kN / TONF_TO_KN == pytest.approx(25.1, rel=0.04)


def test_aragon_3_6_concluye_lo_mismo_que_el_libro_sobre_los_estribos():
    """El libro: «Colocamos refuerzo mínimo por cortante». El motor debe llegar a lo
    mismo: el concreto basta, pero Vu supera 0,5·φVc."""
    r = _aragon_3_6()
    assert not r.shear.stirrups_required, "El concreto resiste el cortante"
    assert r.shear.av_min_required, "Pero se exige refuerzo mínimo"


def test_aragon_3_6_la_seccion_cumple_la_dimension_minima():
    r = _aragon_3_6()
    assert r.dimensional.ok
    assert r.dimensional.min_dimension_provided_m == pytest.approx(0.35)
    assert r.dimensional.min_dimension_required_m == pytest.approx(5.50 / 20.0)

# =========================================================================
# 7. Interacción axial-flexión — §10.2, §10.3.6.2, §9.3.2
# =========================================================================

from engine.beam.axial_flexure import (  # noqa: E402
    SectionGeometry,
    beta1,
    build_interaction_diagram,
    check_axial_flexure,
    nominal_at_neutral_axis,
    phi_for,
)


def _seccion(As_inf=16.62e-4, As_sup=38.30e-4):
    return SectionGeometry(
        b_m=0.35, h_m=1.20, d_m=1.10, d_prime_m=0.10,
        As_bottom_m2=As_inf, As_top_m2=As_sup,
    )


def test_beta1_sigue_10_2_7_3():
    assert beta1(21.0) == pytest.approx(0.85)
    assert beta1(28.0) == pytest.approx(0.85)
    assert beta1(35.0) == pytest.approx(0.80)
    assert beta1(80.0) == pytest.approx(0.65), "Con piso en 0,65"


def test_el_tope_de_compresion_es_la_ecuacion_10_2():
    """§10.3.6.2: Pn_max = 0,80·[0,85·f'c·(Ag - Ast) + fy·Ast] para elementos con
    estribos."""
    s = _seccion()
    r = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=0.0)
    esperado = 0.80 * (0.85 * FC * (s.Ag_m2 - s.Ast_m2) + FY * s.Ast_m2) * 1000.0
    assert r.Pn_max_kN == pytest.approx(esperado)


def test_la_traccion_pura_la_da_el_acero_en_fluencia():
    s = _seccion()
    r = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=0.0)
    assert r.P0_tension_kN == pytest.approx(-FY * s.Ast_m2 * 1000.0)


def test_phi_sigue_9_3_2_en_traccion_y_en_compresion():
    """0,90 en tracción; 0,70 en compresión alta; sube linealmente al bajar Pn."""
    Ag, Pb = 0.42, 2000.0
    assert phi_for(-500.0, FC, Ag, Pb) == pytest.approx(0.90)
    assert phi_for(5000.0, FC, Ag, Pb) == pytest.approx(0.70)
    limite = min(0.1 * FC * Ag * 1000.0, Pb)
    intermedio = phi_for(limite / 2.0, FC, Ag, Pb)
    assert 0.70 < intermedio < 0.90


def test_el_diagrama_converge_al_refinarlo():
    """La frontera es convexa: interpolar linealmente SUBESTIMA la capacidad. Un
    muestreo grueso es conservador pero impreciso, y por eso la resolución por
    defecto se elevó de 40 a 200 puntos."""
    s = _seccion()
    valores = []
    for n in (40, 200, 800):
        d = build_interaction_diagram(s, FC, FY, n_points=n)
        for a, b in zip(d, d[1:]):
            if a.phi_Pn_kN <= 0 <= b.phi_Pn_kN and abs(b.phi_Pn_kN - a.phi_Pn_kN) > 1e-9:
                t = (0 - a.phi_Pn_kN) / (b.phi_Pn_kN - a.phi_Pn_kN)
                valores.append(a.phi_Mn_kNm + t * (b.phi_Mn_kNm - a.phi_Mn_kNm))
                break
    assert valores[0] < valores[1] < valores[2], "Debe crecer monótonamente al refinar"
    assert abs(valores[1] - valores[2]) / valores[2] < 0.02, "200 puntos ya converge al 2%"


def test_en_flexion_pura_coincide_con_el_calculo_simple_de_seccion():
    """Con P = 0 la interacción debe reproducir la flexión pura, salvo el efecto real
    del acero en compresión y del concreto que desplaza."""
    from engine.beam.beam_flexure import _as_for_moment

    Mu = 140.6 * TONF_TO_KN
    As = _as_for_moment(Mu, 0.35, 1.10, FC, FY, 0.90)
    s = SectionGeometry(b_m=0.35, h_m=1.20, d_m=1.10, d_prime_m=0.10,
                        As_bottom_m2=As, As_top_m2=As / 2.0)
    r = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=Mu)
    assert r.demand_ratio == pytest.approx(1.0, abs=0.06)


def test_el_signo_del_momento_decide_que_cara_resiste():
    """Con armado distinto arriba y abajo el diagrama NO es simétrico. Comparar un
    momento negativo contra la capacidad de flexión positiva daría un sinsentido."""
    s = _seccion(As_inf=16.62e-4, As_sup=38.30e-4)
    M = 140.6 * TONF_TO_KN
    positivo = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=M)
    negativo = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=-M)
    assert negativo.capacity_at_Pu.phi_Mn_kNm > positivo.capacity_at_Pu.phi_Mn_kNm, (
        "La cara superior tiene más acero: debe resistir más momento negativo"
    )
    assert negativo.status_ok and not positivo.status_ok


def test_la_traccion_reduce_la_capacidad_a_momento():
    """Es la razón por la que E.030 art. 65.1 obliga a verificar la interacción: la
    fuerza axial no es inocua."""
    s = _seccion()
    M = 140.6 * TONF_TO_KN
    sin_axial = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=-M)
    con_traccion = check_axial_flexure(s, FC, FY, Pu_kN=-800.0, Mu_kNm=-M)
    assert con_traccion.capacity_at_Pu.phi_Mn_kNm < sin_axial.capacity_at_Pu.phi_Mn_kNm


def test_una_compresion_moderada_sube_el_Mn_nominal_pero_baja_el_phi():
    """Dos efectos opuestos que NO deben confundirse.

    Por debajo del punto balanceado la compresión aumenta la capacidad NOMINAL a
    momento: cierra fisuras y desplaza el eje neutro. Pero §9.3.2 hace bajar φ desde
    0,90 hacia 0,70 conforme Pn crece, y el φMn de DISEÑO puede terminar siendo
    menor. El motor no debe suavizar esa pérdida: aplicar φ = 0,90 a una sección
    comprimida sobreestimaría la resistencia."""
    s = _seccion()
    M = 140.6 * TONF_TO_KN
    sin_axial = check_axial_flexure(s, FC, FY, Pu_kN=0.0, Mu_kNm=-M)
    con_compresion = check_axial_flexure(s, FC, FY, Pu_kN=600.0, Mu_kNm=-M)

    assert con_compresion.capacity_at_Pu.Mn_kNm > sin_axial.capacity_at_Pu.Mn_kNm, (
        "El Mn nominal debe crecer: es el efecto físico de la compresión"
    )
    assert con_compresion.capacity_at_Pu.phi < sin_axial.capacity_at_Pu.phi, (
        "Y φ debe bajar por §9.3.2 al crecer Pn"
    )
    assert con_compresion.capacity_at_Pu.phi_Mn_kNm < sin_axial.capacity_at_Pu.phi_Mn_kNm, (
        "En esta sección gana la caída de φ: el φMn de diseño baja"
    )


def test_una_compresion_por_encima_del_tope_se_rechaza():
    s = _seccion()
    r = check_axial_flexure(s, FC, FY, Pu_kN=99_000.0, Mu_kNm=-100.0)
    assert not r.axial_cap_ok
    assert not r.status_ok
    assert "10.3.6.2" in r.message


def test_una_traccion_por_encima_de_la_capacidad_del_acero_se_rechaza():
    s = _seccion()
    r = check_axial_flexure(s, FC, FY, Pu_kN=-99_000.0, Mu_kNm=-100.0)
    assert not r.axial_cap_ok
    assert "más área de refuerzo" in r.message


def test_el_equilibrio_de_la_seccion_cierra_en_cada_punto():
    """Comprobación independiente: al comprimir más, Pn debe crecer."""
    s = _seccion()
    for c in (0.10, 0.30, 0.60, 1.00):
        Pn, Mn, eps_t = nominal_at_neutral_axis(s, FC, FY, c)
        assert math.isfinite(Pn) and math.isfinite(Mn)
    Pn_bajo, _, _ = nominal_at_neutral_axis(s, FC, FY, 0.20)
    Pn_alto, _, _ = nominal_at_neutral_axis(s, FC, FY, 1.00)
    assert Pn_alto > Pn_bajo


# =========================================================================
# 8. §21.12.3.3 — mapeo determinado por §21.2
# =========================================================================

from engine.beam.connecting_beam import lateral_system_requirements  # noqa: E402


def test_21_12_3_3_no_aplica_a_una_viga_que_solo_ata_zapatas():
    """NO APLICA SIEMPRE: hace falta que las columnas conectadas formen parte del
    sistema sismorresistente Y le transmitan flexión."""
    r = lateral_system_requirements(part_of_lateral_force_system=False, system=None)
    assert not r.applies
    assert "NO aplica" in r.reason


@pytest.mark.parametrize("sistema, seccion", [
    ("muros_estructurales", "§21.4"),
    ("dual_tipo_I", "§21.5"),
    ("porticos", "§21.5"),
    ("dual_tipo_II", "§21.5"),
])
def test_21_2_determina_a_cual_de_los_dos_remite(sistema, seccion):
    """Fase 10A (A6). §21.2.4 (propuesta 2019): §21.4 para muros estructurales (R0=6);
    §21.2.5: §21.5 para pórticos (R0=8) y duales (R0=7), sin distinguir tipo I y II."""
    r = lateral_system_requirements(True, sistema)
    assert r.applies and r.section == seccion


def test_no_hay_exencion_de_10_5_3_que_anular():
    """Fase 10A (A3). En la fuente designada §21.4.4.1 y §21.5.2.1 no contienen «No se
    aplicará lo dispuesto en 10.5.3», y §10.5.3 solo exime a losas: el campo se
    conserva por contrato y vale siempre False."""
    for sistema in ("muros_estructurales", "porticos"):
        assert not lateral_system_requirements(True, sistema).disallows_10_5_3


def test_el_ratio_de_momento_positivo_difiere_entre_21_4_y_21_5():
    """§21.4.4.3 pide M+ >= 1/3 de M-; §21.5.2.2 pide la MITAD."""
    a = lateral_system_requirements(True, "muros_estructurales")
    b = lateral_system_requirements(True, "porticos")
    assert a.positive_moment_ratio_at_joint == pytest.approx(1 / 3)
    assert b.positive_moment_ratio_at_joint == pytest.approx(0.5)


def test_solo_21_5_impone_limites_geometricos():
    """Fase 10A (A5). §21.5.1.2 (luz libre >= 4h) y §21.5.1.3 (bw >= 0,3h y 250 mm) son
    propios de §21.5 (pórticos y duales)."""
    p = lateral_system_requirements(True, "porticos")
    m = lateral_system_requirements(True, "muros_estructurales")
    assert p.min_clear_span_over_depth == pytest.approx(4.0)
    assert p.min_width_over_depth == pytest.approx(0.30)
    assert m.min_clear_span_over_depth is None


def test_lo_que_no_se_comprueba_de_21_4_y_21_5_queda_declarado():
    for sistema in ("muros_estructurales", "porticos"):
        r = lateral_system_requirements(True, sistema)
        assert r.not_implemented
        assert all("NO IMPLEMENTADO" in x for x in r.not_implemented)


def test_el_minimo_de_la_viga_es_el_mismo_con_o_sin_21_4():
    """Fase 10A (A3). Como §10.5.3 ya no alcanza a vigas, activar §21.12.3.3 no cambia el
    acero mínimo: en los dos casos rige el mínimo completo de §10.5.1/§10.5.2."""
    comun = dict(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=50.0, Mu_positive_kNm=25.0, Vu_kN=100.0,
        fc_MPa=FC, fy_MPa=FY, longitudinal_db_mm=25.4, sum_Pu_kN=1000.0,
    )
    sin = design_connecting_beam(**comun, seismic=SeismicContext(qadm_kPa=200.0))
    con = design_connecting_beam(
        **comun,
        seismic=SeismicContext(qadm_kPa=200.0, part_of_lateral_force_system=True,
                               lateral_system="muros_estructurales"),
    )
    assert con.As_negative_m2 == pytest.approx(sin.As_negative_m2)
    assert not con.min_steel_negative.exempt_by_10_5_3
    assert not sin.min_steel_negative.exempt_by_10_5_3
