"""CONVENCIÓN DE EJES — guardia contra una inversión accidental.

CONVENCIÓN ADOPTADA (E.050 art. 28.1)
=====================================
    ex = Mx / Q        ey = My / Q

`Mx` es el momento que desplaza la resultante A LO LARGO DEL EJE X, es decir el
que flexiona la zapata en la dirección de B. Mecánicamente es el momento
*alrededor del eje Y*; el rótulo sigue a la norma, no al eje de giro.

Es la misma convención que emplean E.050 y la bibliografía peruana: Aragón,
«Concreto Armado 2» 3.4.1 titula su sección de diseño *"Diseño por flexión Dir. X
(Momentos alrededor de Y)"*.

QUÉ PROTEGE ESTE ARCHIVO
========================
Que la convención sea coherente EN TODA LA CADENA, no solo en
`compute_eccentricity`. Una inversión de ejes es de las averías más silenciosas
que puede tener el motor: no lanza excepción, no rompe unidades, y en zapata
cuadrada con momentos iguales no se nota. Solo aparece cuando el proyecto es
asimétrico — y para entonces ya está en un plano.

Por eso los casos límite van deliberadamente asimétricos: B != L y Mx != My.
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.foundation.punching_moment_transfer import check_punching_with_moment_transfer
from engine.soil.contact_pressure import FullContactModel
from engine.soil.eccentricity import compute_eccentricity
from engine.soil.stability import check_stability

CODE = E060ConcreteCode()

# Geometría deliberadamente asimétrica: B != L y columna rectangular. Con estos
# valores, cruzar los ejes SIEMPRE cambia el resultado.
B_ASIM, L_ASIM = 4.0, 2.4
COLUMNA_ASIM = Column(shape="rectangular", bx_m=0.70, by_m=0.35)

P_REF = 1000.0
MX_REF, MY_REF = 300.0, 100.0  # Mx != My a propósito


def _soil() -> SoilProfile:
    return SoilProfile(
        qadm_kPa=400.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.20,
        source_notes="Caso de prueba de convención de ejes.",
    )


def _loads(Mx: float, My: float, *, Hx: float = 0.0, Hy: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=P_REF,
                Mx_kNm=Mx, My_kNm=My, Hx_kN=Hx, Hy_kN=Hy,
            )
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P_REF * 1.4,
                Mx_kNm=Mx * 1.4, My_kNm=My * 1.4, Hx_kN=Hx * 1.4, Hy_kN=Hy * 1.4,
            )
        ],
    )


def _candidato(Mx: float, My: float, B: float = B_ASIM, L: float = L_ASIM):
    return evaluate_candidate(
        B_m=B, L_m=L, h_m=0.70, column=COLUMNA_ASIM, soil=_soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=_loads(Mx, My), code=CODE, contact_model=FullContactModel(),
        depth_params=DepthSearchParameters(h_min_m=0.70, h_max_m=0.70, h_step_m=0.05),
    )


# =========================================================================
# La definición misma
# =========================================================================

def test_la_definicion_de_e050_art_28_1():
    """ex = Mx/Q y ey = My/Q. Si esto cambia, todo lo demás deja de tener sentido."""
    e = compute_eccentricity(P_kN=P_REF, Mx_kNm=MX_REF, My_kNm=MY_REF)
    assert e.ex_m == pytest.approx(MX_REF / P_REF)
    assert e.ey_m == pytest.approx(MY_REF / P_REF)


def test_la_excentricidad_es_lineal_en_el_momento_y_no_mezcla_ejes():
    """Duplicar Mx duplica ex y no toca ey. Detecta cualquier acoplamiento espurio."""
    base = compute_eccentricity(P_kN=P_REF, Mx_kNm=MX_REF, My_kNm=MY_REF)
    doble = compute_eccentricity(P_kN=P_REF, Mx_kNm=2 * MX_REF, My_kNm=MY_REF)
    assert doble.ex_m == pytest.approx(2 * base.ex_m)
    assert doble.ey_m == pytest.approx(base.ey_m)


# =========================================================================
# Casos A a E exigidos
# =========================================================================

def test_caso_A_mx_distinto_de_my_y_B_distinto_de_L():
    """El caso que de verdad detecta una inversión: todo asimétrico."""
    e = compute_eccentricity(P_kN=P_REF, Mx_kNm=MX_REF, My_kNm=MY_REF)
    r = FullContactModel().compute(B_ASIM, L_ASIM, P_REF, e.ex_m, e.ey_m)

    # ex debe dividirse entre B y ey entre L. Se comprueba reconstruyendo qmax.
    esperado = (P_REF / (B_ASIM * L_ASIM)) * (
        1 + abs(6 * e.ex_m / B_ASIM) + abs(6 * e.ey_m / L_ASIM)
    )
    assert r.qmax_kPa == pytest.approx(esperado)

    # Y con los ejes cruzados el resultado DEBE ser distinto: si coincidiera, el
    # caso sería degenerado y no probaría nada.
    cruzado = FullContactModel().compute(B_ASIM, L_ASIM, P_REF, e.ey_m, e.ex_m)
    assert cruzado.qmax_kPa != pytest.approx(r.qmax_kPa)


def test_caso_B_solo_my():
    """Mx = 0, My != 0: toda la excentricidad debe ir al eje Y."""
    e = compute_eccentricity(P_kN=P_REF, Mx_kNm=0.0, My_kNm=MY_REF)
    assert e.ex_m == pytest.approx(0.0)
    assert e.ey_m == pytest.approx(MY_REF / P_REF)

    cand = _candidato(Mx=0.0, My=MY_REF)
    assert cand.eccentricity_governing.ex_m == pytest.approx(0.0, abs=1e-12)
    assert abs(cand.eccentricity_governing.ey_m) > 1e-6


def test_caso_C_solo_mx():
    """Mx != 0, My = 0: toda la excentricidad debe ir al eje X."""
    e = compute_eccentricity(P_kN=P_REF, Mx_kNm=MX_REF, My_kNm=0.0)
    assert e.ex_m == pytest.approx(MX_REF / P_REF)
    assert e.ey_m == pytest.approx(0.0)

    cand = _candidato(Mx=MX_REF, My=0.0)
    assert abs(cand.eccentricity_governing.ex_m) > 1e-6
    assert cand.eccentricity_governing.ey_m == pytest.approx(0.0, abs=1e-12)


def test_caso_D_mx_igual_a_my_no_distingue_ejes():
    """Con Mx = My las dos excentricidades salen iguales. Se deja escrito para que
    quede constancia de que este caso NO sirve como prueba de convención: es
    justamente el que esconde una inversión."""
    e = compute_eccentricity(P_kN=P_REF, Mx_kNm=MX_REF, My_kNm=MX_REF)
    assert e.ex_m == pytest.approx(e.ey_m)


def test_caso_E_zapata_cuadrada_con_momentos_distintos_si_distingue():
    """B = L por sí solo NO esconde la inversión mientras Mx != My.

    La columna se toma CUADRADA a propósito: con una rectangular los voladizos de
    cada dirección son distintos y su efecto se mezcla con el de la excentricidad,
    de modo que el test dejaría de aislar lo que pretende medir. Con voladizos
    iguales, el único origen posible de una diferencia es el momento."""
    columna_cuadrada = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    cand = evaluate_candidate(
        B_m=3.0, L_m=3.0, h_m=0.70, column=columna_cuadrada, soil=_soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=_loads(MX_REF, MY_REF), code=CODE, contact_model=FullContactModel(),
        depth_params=DepthSearchParameters(h_min_m=0.70, h_max_m=0.70, h_step_m=0.05),
    )
    assert cand.flexure_x.cantilever_m == pytest.approx(cand.flexure_y.cantilever_m)
    # Mismo voladizo y Mx > My  =>  ex > ey  =>  más momento en la dirección X.
    assert cand.flexure_x.Mu_kNm > cand.flexure_y.Mu_kNm


# =========================================================================
# Coherencia a lo largo de toda la cadena
# =========================================================================

def test_la_flexion_asocia_mx_con_la_direccion_de_B():
    """Aumentar SOLO Mx aumenta el momento de la dirección X. Es la comprobación de que el
    rótulo llega correcto hasta el armado.

    LA DIRECCIÓN Y SE DEJA QUIETA **MIENTRAS HAY CONTACTO TOTAL** (2026-09-20)
    =========================================================================
    Hasta el contacto unilateral este test exigía además que Mu_y no se moviera *nunca*, y
    se cumplía porque el campo era separable: cada dirección se resolvía con su propia
    excentricidad, ignorando la otra. Esa independencia era un artefacto del modelo.

    Con el campo real hay acoplamiento en cuanto una esquina se levanta, y aquí ocurre: el
    núcleo es el ROMBO `|6·ex/B| + |6·ey/L| ≤ 1`, que vale 0,700 en el caso base y **1,150**
    al duplicar Mx. Levantada la esquina, la presión se redistribuye en las DOS direcciones
    y Mu_y cambia de verdad. No es un error de rótulo: es física que el modelo anterior no
    podía ver.

    Así que se comprueba lo que el test quiere comprobar —la convención de ejes— en el
    régimen donde la pregunta tiene sentido, y el acoplamiento se comprueba aparte."""
    base = _candidato(Mx=MX_REF, My=MY_REF)
    # 1,5·Mx mantiene el rombo en 0,925: contacto total, régimen separable.
    mas_mx_sin_despegue = _candidato(Mx=MX_REF * 1.5, My=MY_REF)

    assert mas_mx_sin_despegue.flexure_x.Mu_kNm > base.flexure_x.Mu_kNm
    assert mas_mx_sin_despegue.flexure_y.Mu_kNm == pytest.approx(base.flexure_y.Mu_kNm)


def test_al_levantarse_una_esquina_las_dos_direcciones_se_acoplan():
    """La contrapartida del test anterior, y la razón de que se dividiera en dos.

    Con la esquina levantada, aumentar Mx SÍ mueve Mu_y. Se exige que se mueva, no que se
    quede: si volviera a quedarse quieto, el campo habría dejado de resolver el contacto en
    2-D y estaríamos otra vez con dos problemas 1-D independientes."""
    from engine.foundation.unilateral_contact import solve_unilateral_contact

    base = _candidato(Mx=MX_REF, My=MY_REF)
    mas_mx = _candidato(Mx=MX_REF * 2, My=MY_REF)

    # Primero, que el régimen sea el que se afirma.
    Pu = P_REF * 1.4
    campo_base = solve_unilateral_contact(Pu, B_ASIM, L_ASIM, MX_REF * 1.4 / Pu, MY_REF * 1.4 / Pu)
    campo_mas = solve_unilateral_contact(Pu, B_ASIM, L_ASIM, MX_REF * 2 * 1.4 / Pu, MY_REF * 1.4 / Pu)
    assert campo_base.full_contact is True
    assert campo_mas.full_contact is False and campo_mas.uniaxial is False

    assert mas_mx.flexure_x.Mu_kNm > base.flexure_x.Mu_kNm
    assert mas_mx.flexure_y.Mu_kNm != pytest.approx(base.flexure_y.Mu_kNm)
    # Y el acoplamiento es pequeño: la dirección del momento sigue siendo la que gobierna.
    relativo = abs(mas_mx.flexure_y.Mu_kNm - base.flexure_y.Mu_kNm) / base.flexure_y.Mu_kNm
    assert relativo < 0.01


def test_el_cortante_asocia_my_con_la_direccion_de_L():
    base = _candidato(Mx=MX_REF, My=MY_REF)
    mas_my = _candidato(Mx=MX_REF, My=MY_REF * 2)

    assert mas_my.shear_y.Vu_kN > base.shear_y.Vu_kN
    assert mas_my.shear_x.Vu_kN == pytest.approx(base.shear_x.Vu_kN)


def test_el_punzonamiento_mide_b1_en_la_direccion_del_momento():
    """Ec. 13-1: b1 es la dimensión de la sección crítica MEDIDA EN LA DIRECCIÓN DEL
    MOMENTO. Para Mx, esa dirección es X."""
    bx, by, d = 0.70, 0.35, 0.50
    b_crit_x, b_crit_y = bx + d, by + d

    solo_mx = check_punching_with_moment_transfer(
        Vu_kN=500.0, Mux_kNm=MX_REF, Muy_kNm=0.0,
        bx_m=bx, by_m=by, d_m=d, Vc_kN=1500.0, phi=0.85,
    )
    assert solo_mx.axis_x is not None and solo_mx.axis_y is None
    assert solo_mx.axis_x.axis == "X"
    assert solo_mx.axis_x.b1_m == pytest.approx(b_crit_x)
    assert solo_mx.axis_x.b2_m == pytest.approx(b_crit_y)

    solo_my = check_punching_with_moment_transfer(
        Vu_kN=500.0, Mux_kNm=0.0, Muy_kNm=MX_REF,
        bx_m=bx, by_m=by, d_m=d, Vc_kN=1500.0, phi=0.85,
    )
    assert solo_my.axis_y is not None and solo_my.axis_x is None
    assert solo_my.axis_y.axis == "Y"
    assert solo_my.axis_y.b1_m == pytest.approx(b_crit_y)


def test_el_volcamiento_del_eje_X_lo_gobierna_mx():
    """El vuelco EN la dirección X lo produce el momento que desplaza la resultante
    a lo largo de X, es decir Mx, junto con Hx."""
    st = check_stability(
        _loads(Mx=MX_REF, My=MY_REF, Hx=50.0, Hy=20.0),
        _soil(), 200.0, B_ASIM, L_ASIM, 0.70,
    )
    assert st.overturning_x.applied_moment_kNm == pytest.approx(MX_REF)
    assert st.overturning_x.horizontal_force_kN == pytest.approx(50.0)
    assert st.overturning_y.applied_moment_kNm == pytest.approx(MY_REF)
    assert st.overturning_y.horizontal_force_kN == pytest.approx(20.0)


def test_intercambiar_momentos_y_dimensiones_a_la_vez_reproduce_el_mismo_problema():
    """Prueba de simetría global: una zapata girada 90° con los momentos también
    girados debe dar el resultado espejo. Detecta cualquier asimetría oculta que
    los tests por eje no vean."""
    directo = _candidato(Mx=MX_REF, My=MY_REF, B=B_ASIM, L=L_ASIM)
    girado = evaluate_candidate(
        B_m=L_ASIM, L_m=B_ASIM, h_m=0.70,
        column=Column(shape="rectangular", bx_m=0.35, by_m=0.70), soil=_soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=_loads(Mx=MY_REF, My=MX_REF), code=CODE,
        contact_model=FullContactModel(),
        depth_params=DepthSearchParameters(h_min_m=0.70, h_max_m=0.70, h_step_m=0.05),
    )
    assert girado.contact_pressure.qmax_kPa == pytest.approx(directo.contact_pressure.qmax_kPa)
    assert girado.flexure_y.Mu_kNm == pytest.approx(directo.flexure_x.Mu_kNm)
    assert girado.flexure_x.Mu_kNm == pytest.approx(directo.flexure_y.Mu_kNm)
    assert girado.punching.Vu_kN == pytest.approx(directo.punching.Vu_kN)


def test_la_convencion_queda_declarada_en_la_traza():
    """El informe no puede depender de que alguien conozca el código."""
    cand = _candidato(Mx=MX_REF, My=MY_REF)
    for entrada_id in ("contact_pressure", "punching"):
        entrada = cand.trace.by_id(entrada_id)
        assert entrada is not None
        texto = " ".join(entrada.hypotheses)
        assert "E.050 art. 28.1" in texto, f"Falta la convención en la traza «{entrada_id}»"
        assert "ex = Mx/P" in texto
