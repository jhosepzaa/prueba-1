"""Bloque triangular real para los esfuerzos de diseño — decisión B (2026-09-19).

QUÉ ESTABA MAL
==============
Los esfuerzos de diseño —flexión y cortante unidireccional— salen de la presión NETA
FACTORIZADA que produce la reacción del suelo ante las cargas amplificadas de columna.
Hasta aquí el motor usaba siempre el campo lineal `q' = (Pu/dim)·(1 ± 6e/dim)` y
**recortaba a cero** las presiones negativas:

    q_edge = max(q_edge, 0.0)
    q_face = max(q_face, 0.0)

Esa recortada **no equilibra la carga**: su resultante no vale Pu y no pasa por el punto
excéntrico. Con la resultante fuera del núcleo central, Mu y Vu quedaban mal calculados.

POR QUÉ OCURRÍA TAMBIÉN CON EL MODELO POR DEFECTO
=================================================
No es un problema del área efectiva. La excentricidad que gobierna el DISEÑO se calcula
con las cargas **factorizadas** y **sin peso propio**, y puede salirse del núcleo aunque
la de servicio —que lleva el peso propio en el denominador— no lo haga. Cinco de los
casos congelados de la zapata aislada estaban en esa situación.

LO IMPLEMENTADO
===============
`NetPressureField` resuelve los dos regímenes por equilibrio, no por prescripción:

  - contacto total (`e ≤ dim/6`): el campo lineal clásico;
  - contacto parcial (`e > dim/6`): bloque **triangular** sobre la longitud comprimida
    `a = 3·(dim/2 − e)`, con `q'(0) = 2·Pu/a` y cero más allá de `a`.

E.060 §15.2.3 es lo que obliga a que no haya tracciones; las dos expresiones salen de
imponer que la resultante valga Pu y pase por el punto excéntrico.

Detalle en `docs/area_efectiva_e050_art28.md` §6.
"""

import pytest

from engine.foundation.flexure import (
    moment_at_critical_section,
    net_pressure_field,
)
from engine.foundation.shear_oneway import shear_force_at_d_from_face


def _integra(campo, s1: float, s2: float, s_face: float, n: int = 200_000):
    """Integración numérica bruta del campo, para contrastar contra la cerrada.

    Se escribe a mano y no llama a `force_and_moment`: es la reconstrucción
    independiente que exige `CLAUDE.md` §12."""
    h = (s2 - s1) / n
    fuerza = momento = 0.0
    for i in range(n):
        s = s1 + (i + 0.5) * h
        q = campo.q_at(s)
        fuerza += q * h
        momento += q * abs(s - s_face) * h
    return fuerza, momento


# =========================================================================
# 1. El campo equilibra la carga — el invariante que lo decide todo
# =========================================================================


@pytest.mark.parametrize("e", [0.0, 0.10, 0.30, 0.50, 0.5001, 0.60, 1.00, 1.40, 1.4999])
def test_la_resultante_vale_Pu_y_pasa_por_el_punto_excentrico(e):
    """El único invariante que hace falta para saber si el campo es el correcto.

    Con `dim = 3,00` el núcleo acaba en 0,50 y la huella en 1,50, de modo que el barrido
    cruza los dos regímenes y llega al límite físico. La recortada anterior NO cumplía
    esto: es exactamente lo que estaba mal."""
    dim, Pu = 3.00, 600.0
    campo = net_pressure_field(Pu, e, dim)
    fuerza, momento = campo.force_and_moment(0.0, dim, 0.0)

    assert fuerza == pytest.approx(Pu, rel=1e-12), "La resultante debe valer Pu"
    # Momentos en s = 0 (borde de mayor presión): el brazo es dim/2 − e.
    assert momento / fuerza == pytest.approx(dim / 2.0 - e, abs=1e-12)


def test_fuera_de_la_huella_no_hay_campo_posible():
    """Con `e ≥ dim/2` la resultante cae fuera de la zapata: no existe distribución que
    la equilibre. El campo se declara imposible y no se inventa ninguno."""
    campo = net_pressure_field(600.0, 1.60, 3.00)
    assert campo.equilibrium_possible is False
    assert campo.contact_length_m == 0.0
    assert campo.force_and_moment(0.0, 3.00, 0.0) == (0.0, 0.0)


# =========================================================================
# 2. Los dos regímenes
# =========================================================================


def test_dentro_del_nucleo_es_el_campo_lineal_de_siempre():
    dim, Pu, e = 3.00, 600.0, 0.30
    campo = net_pressure_field(Pu, e, dim)
    assert campo.full_contact is True
    assert campo.contact_length_m == pytest.approx(dim)
    assert campo.q_at(0.0) == pytest.approx((Pu / dim) * (1 + 6 * e / dim), rel=1e-12)
    assert campo.q_at(dim) == pytest.approx((Pu / dim) * (1 - 6 * e / dim), rel=1e-12)


def test_fuera_del_nucleo_es_un_triangulo_sobre_la_longitud_comprimida():
    dim, Pu, e = 3.00, 600.0, 0.90
    campo = net_pressure_field(Pu, e, dim)
    a = 3.0 * (dim / 2.0 - e)
    assert campo.full_contact is False
    assert campo.contact_length_m == pytest.approx(a, rel=1e-12)
    assert campo.q_at(0.0) == pytest.approx(2.0 * Pu / a, rel=1e-12)
    assert campo.q_at(a) == pytest.approx(0.0, abs=1e-9)
    assert campo.q_at(a + 0.01) == 0.0
    assert campo.q_at(dim) == 0.0


def test_la_transicion_en_el_borde_del_nucleo_es_continua():
    """En `e = dim/6` las dos expresiones tienen que dar lo mismo: `a = dim` y
    `q'(0) = 2Pu/dim`, que es también `(Pu/dim)(1 + 6·(dim/6)/dim) = 2Pu/dim`."""
    dim, Pu = 3.00, 600.0
    dentro = net_pressure_field(Pu, dim / 6.0 - 1e-9, dim)
    fuera = net_pressure_field(Pu, dim / 6.0 + 1e-9, dim)
    assert dentro.q_at(0.0) == pytest.approx(fuera.q_at(0.0), rel=1e-7)
    assert dentro.contact_length_m == pytest.approx(fuera.contact_length_m, rel=1e-7)
    assert dentro.q_at(dim) == pytest.approx(0.0, abs=1e-6)


def test_el_borde_del_contacto_se_evalua_con_comparacion_estricta():
    """Defecto real durante la implementación: con `s >= a` la presión se anulaba también
    en el borde opuesto del contacto TOTAL, donde `a = dim`, y la resultante salía la
    mitad. Lo detectó la comprobación de equilibrio."""
    campo = net_pressure_field(600.0, 0.0, 3.00)
    assert campo.q_at(3.00) == pytest.approx(200.0, rel=1e-12)
    assert campo.q_at(3.00 + 1e-9) == 0.0


# =========================================================================
# 3. La integración cerrada coincide con la numérica
# =========================================================================


@pytest.mark.parametrize("e", [0.20, 0.50, 0.70, 1.20])
@pytest.mark.parametrize("c", [0.40, 1.10])
def test_la_formula_cerrada_reproduce_la_integracion_numerica(e, c):
    dim, Pu = 3.00, 600.0
    campo = net_pressure_field(Pu, e, dim)
    # Voladizo del lado de MAYOR presión: s de 0 a c, cara en s = c.
    f_cerrada, m_cerrada = campo.force_and_moment(0.0, c, c)
    f_num, m_num = _integra(campo, 0.0, c, c)
    assert f_cerrada == pytest.approx(f_num, rel=1e-5)
    assert m_cerrada == pytest.approx(m_num, rel=1e-5)
    # Y del lado opuesto.
    f_cerrada, m_cerrada = campo.force_and_moment(dim - c, dim, dim - c)
    f_num, m_num = _integra(campo, dim - c, dim, dim - c)
    assert f_cerrada == pytest.approx(f_num, rel=1e-5)
    assert m_cerrada == pytest.approx(m_num, abs=1e-6, rel=1e-5)


def test_el_centroide_del_trapecio_sale_bien_en_los_dos_limites():
    """`x̄ = ℓ·(q1 + 2q2)/(3(q1 + q2))`: con carga uniforme da ℓ/2 y con triángulo ℓ/3."""
    uniforme = net_pressure_field(600.0, 0.0, 3.00)
    f, m = uniforme.force_and_moment(0.0, 3.00, 0.0)
    assert m / f == pytest.approx(1.50, rel=1e-12)

    # Triángulo completo: e = dim/6 deja q'(dim) = 0 y el centroide a dim/3.
    triangulo = net_pressure_field(600.0, 3.00 / 6.0, 3.00)
    f, m = triangulo.force_and_moment(0.0, 3.00, 0.0)
    assert m / f == pytest.approx(1.00, rel=1e-9)


# =========================================================================
# 4. Con contacto total, los momentos son los de siempre
# =========================================================================


@pytest.mark.parametrize("e", [0.0, 0.15, 0.35, 0.50])
@pytest.mark.parametrize("near_high_edge", [True, False])
def test_con_contacto_total_se_recupera_la_formula_clasica(e, near_high_edge):
    """`M = (c²/6)·(2·q_borde + q_cara)`, escrita aquí a mano. Es la garantía de que la
    decisión B no movió nada donde el campo lineal ya era válido."""
    dim, Pu, c = 3.00, 600.0, 0.90
    campo = net_pressure_field(Pu, e, dim)
    assert campo.full_contact

    q_avg = Pu / dim
    q_alto = q_avg * (1 + 6 * e / dim)
    q_bajo = q_avg * (1 - 6 * e / dim)
    if near_high_edge:
        q_borde, q_cara = q_alto, q_alto - (q_alto - q_bajo) * (c / dim)
    else:
        q_borde, q_cara = q_bajo, q_bajo + (q_alto - q_bajo) * (c / dim)
    clasica = (c**2 / 6.0) * (2.0 * q_borde + q_cara)

    assert moment_at_critical_section(Pu, e, dim, c, near_high_edge) == pytest.approx(
        clasica, rel=1e-12
    )


# =========================================================================
# 5. Con despegue, la corrección y su dirección
# =========================================================================


def test_con_despegue_el_voladizo_cargado_recibe_MAS_que_antes():
    """Del lado comprimido la carga se concentra: Mu y Vu SUBEN. Es la mitad insegura del
    defecto que la decisión B corrige.

    Reconstrucción a mano con `dim = 3,00`, `Pu = 600`, `e = 0,90`:
        a = 3·(1,50 − 0,90) = 1,80 m ;  q'(0) = 2·600/1,80 = 666,667 kN/m
        voladizo c = 0,60 del lado comprimido, cara en s = 0,60:
            q'(0,60) = 666,667·(1 − 0,60/1,80) = 444,444 kN/m
            M = (0,60²/6)·(2·666,667 + 444,444) = 106,667 kN·m
    La fórmula recortada anterior daba (0,60²/6)·(2·1000 + 880) = 172,800 kN·m con
    q' lineal, que ni siquiera equilibra la carga."""
    dim, Pu, e, c = 3.00, 600.0, 0.90, 0.60
    assert moment_at_critical_section(Pu, e, dim, c, near_high_edge=True) == pytest.approx(
        106.6667, rel=1e-5
    )


def test_con_despegue_el_voladizo_levantado_no_recibe_nada():
    """Y la otra mitad: sobre la zona levantada no hay presión, y antes el recorte a cero
    del campo lineal le repartía carga que no existe."""
    dim, Pu, e = 3.00, 600.0, 1.20
    a = 3.0 * (dim / 2.0 - e)  # 0,90 m
    # Un voladizo de 0,60 m en el extremo opuesto empieza en s = 2,40 > a: nada.
    assert moment_at_critical_section(Pu, e, dim, 0.60, near_high_edge=False) == 0.0
    assert shear_force_at_d_from_face(Pu, e, dim, 0.60, 0.10, near_high_edge=False) == 0.0
    assert a < dim - 0.60


def test_el_cortante_usa_el_mismo_campo_que_la_flexion():
    """Una sola fuente para las dos: si divergieran, el diseño sería incoherente consigo
    mismo. Vu se reconstruye aquí como la resultante sobre el tramo exterior."""
    dim, Pu, e, c, d = 3.00, 600.0, 0.80, 1.00, 0.35
    campo = net_pressure_field(Pu, e, dim)
    esperado, _ = campo.force_and_moment(0.0, c - d, c - d)
    assert shear_force_at_d_from_face(Pu, e, dim, c, d, near_high_edge=True) == pytest.approx(
        esperado, rel=1e-12
    )


def test_si_la_seccion_critica_cae_dentro_de_la_columna_el_cortante_es_cero():
    assert shear_force_at_d_from_face(600.0, 0.80, 3.00, 0.30, 0.50, near_high_edge=True) == 0.0


# =========================================================================
# 6. De punta a punta, en los casos congelados
# =========================================================================


def test_los_casos_congelados_con_despegue_de_diseno_estan_identificados():
    """Cinco casos de la zapata aislada tienen la excentricidad de DISEÑO fuera del
    núcleo. Son exactamente los que la decisión B mueve, y conviene que estén nombrados:
    si mañana aparece otro, el diff del congelamiento no debería sorprender a nadie."""
    from engine.soil.eccentricity import compute_total_eccentricity
    from tests.freeze.cases import CASES, SWEEP_CASES

    con_despegue = []
    for caso in list(CASES) + list(SWEEP_CASES):
        ox = caso.placement.offset_x_m if caso.placement else 0.0
        oy = caso.placement.offset_y_m if caso.placement else 0.0
        for combo in caso.load_case_set.factored:
            e = compute_total_eccentricity(combo.P_kN, 0.0, combo.Mx_kNm, combo.My_kNm, ox, oy)
            if abs(e.ex_m) > caso.B_m / 6.0 + 1e-12 or abs(e.ey_m) > caso.L_m / 6.0 + 1e-12:
                con_despegue.append(caso.name)
                break

    assert sorted(con_despegue) == [
        "13_descentrada_un_eje",
        "15_descentrada_voladizo_largo_gobierna",
        "16_columna_de_borde",
        "17_columna_de_esquina",
        "18_borde_con_momento",
    ], con_despegue


def test_la_correccion_sube_la_demanda_del_caso_13():
    """Caso 13, el más representativo: la excentricidad de diseño se pasa poco del núcleo
    y el efecto es pequeño pero del lado inseguro. Antes Mu = 306,58 y Vu = 275,13."""
    from tests.freeze.test_freeze_isolated import _evaluate
    from tests.freeze.cases import CASES

    r = _evaluate(next(c for c in CASES if c.name == "13_descentrada_un_eje"))
    assert r.flexure_x.Mu_kNm > 306.582825
    assert r.shear_x.Vu_kN > 275.128327
