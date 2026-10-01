"""FASE 1C — Perímetro crítico truncado: columnas de borde y de esquina.

QUÉ SE VERIFICA
===============
1. DEGENERACIÓN. La derivación general debe reproducir EXACTAMENTE las tres
   expresiones clásicas (interior, borde, esquina), no aproximarlas.
2. CONTINUIDAD. Con la sección cerrada, todo debe seguir dando lo de antes.
3. La clasificación geométrica y su alpha_s.
4. El centroide desplazado y c_low != c_high.
5. Jc del perímetro no simétrico.
6. La frontera en holgura = d/2, que es discontinua por razones físicas.
7. El caso sin categoría normativa (3 o 4 lados recortados) se rechaza.
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.critical_section import build_critical_section
from engine.foundation.depth_solver import evaluate_candidate
from engine.foundation.punching_moment_transfer import check_punching_with_moment_transfer
from engine.foundation.punching_shear import check_punching_shear
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel

CODE = E060ConcreteCode()
BX = BY = 0.50
D = 0.60
B_ANCHA = L_ANCHA = 4.0


def _seccion(**kw):
    return build_critical_section(B_ANCHA, L_ANCHA, BX, BY, D, **kw)


# Desplazamiento que deja una cara de la columna EXACTAMENTE sobre el borde.
OFF_BORDE_X = -(B_ANCHA / 2.0 - BX / 2.0)
OFF_BORDE_Y = -(L_ANCHA / 2.0 - BY / 2.0)


# =========================================================================
# 1. Degeneración exacta en las tres expresiones clásicas
# =========================================================================

def test_interior_reproduce_el_perimetro_cerrado():
    s = _seccion()
    b1, b2 = BX + D, BY + D
    assert s.position == "interior"
    assert len(s.faces) == 4
    assert s.bo_m == pytest.approx(2.0 * (b1 + b2))
    assert s.enclosed_area_m2 == pytest.approx(b1 * b2)


def test_interior_reproduce_el_Jc_clasico_de_columna_interior():
    """Jc = d·b1³/6 + b1·d³/6 + d·b2·b1²/2. Es la comprobación de que la derivación
    general no se desvía en el caso que ya estaba validado."""
    s = _seccion()
    b1, b2 = BX + D, BY + D
    clasico = D * b1**3 / 6.0 + b1 * D**3 / 6.0 + D * b2 * b1**2 / 2.0
    assert s.axis_x.Jc_m4 == pytest.approx(clasico, rel=1e-12)
    assert s.axis_y.Jc_m4 == pytest.approx(clasico, rel=1e-12)


def test_interior_tiene_el_centroide_en_el_centro_de_la_columna():
    s = _seccion()
    assert s.axis_x.is_symmetric and s.axis_y.is_symmetric
    assert s.axis_x.c_low_m == pytest.approx((BX + D) / 2.0)
    assert s.axis_x.c_high_m == pytest.approx((BX + D) / 2.0)


def test_borde_reproduce_el_perimetro_clasico_de_tres_lados():
    """bo = 2·b1 + b2 con b1 = bx + d/2 (una sola extensión) y b2 = by + d."""
    s = _seccion(offset_x_m=OFF_BORDE_X)
    b1, b2 = BX + D / 2.0, BY + D
    assert s.position == "borde"
    assert len(s.faces) == 3
    assert s.bo_m == pytest.approx(2.0 * b1 + b2)
    assert s.axis_x.b1_m == pytest.approx(b1)


def test_borde_reproduce_la_distancia_clasica_al_centroide():
    """c a la cara lejana = b1²/(2b1+b2). Es la expresión estándar del centroide de
    una sección de tres lados; la derivación general debe darla exactamente."""
    s = _seccion(offset_x_m=OFF_BORDE_X)
    b1, b2 = BX + D / 2.0, BY + D
    assert s.axis_x.c_high_m == pytest.approx(b1**2 / (2.0 * b1 + b2))
    # Y la suma de las dos distancias es b1: el centroide está DENTRO de la sección.
    assert s.axis_x.c_low_m + s.axis_x.c_high_m == pytest.approx(b1)


def test_esquina_reproduce_el_perimetro_clasico_de_dos_lados():
    s = _seccion(offset_x_m=OFF_BORDE_X, offset_y_m=OFF_BORDE_Y)
    b1, b2 = BX + D / 2.0, BY + D / 2.0
    assert s.position == "esquina"
    assert len(s.faces) == 2
    assert s.bo_m == pytest.approx(b1 + b2)


# =========================================================================
# 2. El centroide se desplaza y las dos distancias dejan de ser iguales
# =========================================================================

def test_en_borde_el_centroide_se_desplaza_hacia_el_lado_cerrado():
    s = _seccion(offset_x_m=OFF_BORDE_X)
    assert not s.axis_x.is_symmetric
    # El lado abierto está en x_lo; el centroide debe quedar más lejos de él.
    assert s.axis_x.c_low_m > s.axis_x.c_high_m
    # El eje perpendicular sigue cerrado y simétrico: solo se truncó uno.
    assert s.axis_y.is_symmetric


def test_el_esfuerzo_maximo_usa_la_distancia_mayor_no_b1_medios():
    """En una sección truncada, tomar c = b1/2 subestimaría el esfuerzo. La fibra
    más alejada del centroide pertenece a las caras PARALELAS, que llegan hasta el
    borde: ese material existe aunque allí no haya cara perpendicular."""
    s = _seccion(offset_x_m=OFF_BORDE_X)
    b1 = s.axis_x.b1_m
    assert s.axis_x.c_max_m > b1 / 2.0
    assert s.axis_x.c_max_m == pytest.approx(s.axis_x.c_low_m)


def test_el_Jc_truncado_es_menor_que_el_cerrado():
    """Menos caras resistentes -> menor propiedad de sección. Si saliera mayor, el
    traslado de Steiner estaría mal aplicado."""
    cerrada = _seccion()
    borde = _seccion(offset_x_m=OFF_BORDE_X)
    esquina = _seccion(offset_x_m=OFF_BORDE_X, offset_y_m=OFF_BORDE_Y)
    assert esquina.axis_x.Jc_m4 < borde.axis_x.Jc_m4 < cerrada.axis_x.Jc_m4


def test_el_Jc_se_calcula_sobre_las_caras_resistentes():
    """Reconstrucción independiente de Jc sumando cara por cara, para no depender de
    la misma implementación que se está verificando."""
    s = _seccion(offset_x_m=OFF_BORDE_X)
    xbar = s.axis_x.centroid_m
    esperado = 0.0
    for f in s.faces:
        if f.axis == "y":  # cara paralela al eje X: se extiende de x_lo a x_hi
            Lp = s.x_hi_m - s.x_lo_m
            e = (s.x_lo_m + s.x_hi_m) / 2.0 - xbar
            esperado += D * Lp**3 / 12.0 + Lp * D**3 / 12.0 + Lp * D * e**2
        else:  # cara perpendicular al eje X
            esperado += f.length_m * D * (f.position_m - xbar) ** 2
    assert s.axis_x.Jc_m4 == pytest.approx(esperado, rel=1e-12)


# =========================================================================
# 3. alpha_s por clasificación geométrica
# =========================================================================

@pytest.mark.parametrize(
    "kw, posicion, alpha",
    [
        ({}, "interior", 40.0),
        ({"offset_x_m": OFF_BORDE_X}, "borde", 30.0),
        ({"offset_x_m": OFF_BORDE_X, "offset_y_m": OFF_BORDE_Y}, "esquina", 20.0),
    ],
)
def test_alpha_s_sigue_a_la_clasificacion_geometrica(kw, posicion, alpha):
    r = check_punching_shear(
        P_u_column_kN=800.0, B_m=B_ANCHA, L_m=L_ANCHA, bx_m=BX, by_m=BY, d_m=D,
        fc_MPa=21.0, code=CODE,
        offset_x_m=kw.get("offset_x_m", 0.0), offset_y_m=kw.get("offset_y_m", 0.0),
    )
    assert r.column_position == posicion
    assert r.alpha_s == alpha


def test_la_interpretacion_de_alpha_s_queda_declarada():
    """E.060 da los valores pero no define qué hace de borde a una columna. La
    interpretación tiene que verse en el resultado, no vivir solo en el código."""
    r = check_punching_shear(
        800.0, B_ANCHA, L_ANCHA, BX, BY, D, 21.0, CODE, offset_x_m=OFF_BORDE_X
    )
    assert "NO define" in r.completeness_note
    assert "INTERPRETACIÓN" in r.completeness_note


def test_truncar_reduce_la_resistencia_por_los_dos_caminos():
    """bo baja y alpha_s baja de 40 a 30. Ambos efectos reducen φVc, y ésa es la
    razón por la que ignorar el truncamiento producía un falso PASS (riesgo R1)."""
    interior = check_punching_shear(800.0, B_ANCHA, L_ANCHA, BX, BY, D, 21.0, CODE)
    borde = check_punching_shear(
        800.0, B_ANCHA, L_ANCHA, BX, BY, D, 21.0, CODE, offset_x_m=OFF_BORDE_X
    )
    assert borde.bo_m < interior.bo_m
    assert borde.alpha_s < interior.alpha_s
    assert borde.phi_Vc_kN < interior.phi_Vc_kN


def test_alpha_s_decide_de_verdad_cuando_gobierna_la_ec_11_34():
    """En las zapatas habituales gobierna la ec. 11-43, que NO depende de alpha_s: el
    efecto del truncamiento llega entonces solo por bo. Este caso —columna ancha con
    peralte pequeño, bo/d grande— hace gobernar la ec. 11-42, donde alpha_s sí entra.
    Sin él, la implementación de alpha_s quedaría inerte y sin verificar."""
    Bw = Lw = 8.0
    bx = by = 2.0
    dd = 0.25
    al = (Bw - bx) / 2.0

    resultados = {}
    for etiqueta, kw in (
        ("interior", {}),
        ("borde", {"offset_x_m": al}),
        ("esquina", {"offset_x_m": al, "offset_y_m": -al}),
    ):
        r = check_punching_shear(3000.0, Bw, Lw, bx, by, dd, 21.0, CODE, **kw)
        assert r.governing_equation == "11-42", (
            f"El caso «{etiqueta}» debía hacer gobernar la ec. 11-42 para que alpha_s "
            f"tenga efecto; gobernó {r.governing_equation}."
        )
        resultados[etiqueta] = r

    assert resultados["interior"].alpha_s == 40.0
    assert resultados["borde"].alpha_s == 30.0
    assert resultados["esquina"].alpha_s == 20.0
    # Y la resistencia debe caer monótonamente con la clasificación.
    assert (
        resultados["esquina"].phi_Vc_kN
        < resultados["borde"].phi_Vc_kN
        < resultados["interior"].phi_Vc_kN
    )


def test_el_perimetro_cerrado_sobre_una_columna_de_borde_sobreestima_la_resistencia():
    """RIESGO R1 de la auditoría de Fase 0, cuantificado.

    Es la razón por la que la Fase 1B rechazaba estas geometrías en vez de calcularlas
    con el modelo cerrado: habría producido un falso PASS en el modo de falla más
    frágil de una zapata."""
    Bw = Lw = 3.20
    al = (Bw - BX) / 2.0
    cerrado = check_punching_shear(900.0, Bw, Lw, BX, BY, D, 21.0, CODE)
    borde = check_punching_shear(900.0, Bw, Lw, BX, BY, D, 21.0, CODE, offset_x_m=al)
    esquina = check_punching_shear(
        900.0, Bw, Lw, BX, BY, D, 21.0, CODE, offset_x_m=al, offset_y_m=-al
    )
    assert cerrado.phi_Vc_kN / borde.phi_Vc_kN > 1.5, "El sobrecálculo en borde supera el 50%"
    assert cerrado.phi_Vc_kN / esquina.phi_Vc_kN > 2.5, "En esquina supera el 150%"


# =========================================================================
# 4. Frontera en holgura = d/2
# =========================================================================

def test_holgura_exactamente_d_medios_todavia_cierra():
    """La norma dice «no necesita estar más cerca de d/2»: d/2 exacto es admisible."""
    off = -(B_ANCHA / 2.0 - BX / 2.0 - D / 2.0)
    assert _seccion(offset_x_m=off).position == "interior"


def test_un_milimetro_mas_alla_ya_trunca():
    off = -(B_ANCHA / 2.0 - BX / 2.0 - D / 2.0) - 0.001
    assert _seccion(offset_x_m=off).position == "borde"


def test_la_discontinuidad_en_la_frontera_es_la_longitud_del_lado_que_deja_de_contar():
    """No es un salto arbitrario: bo pierde exactamente la cara que desaparece."""
    off_justo = -(B_ANCHA / 2.0 - BX / 2.0 - D / 2.0)
    cerrada = _seccion(offset_x_m=off_justo)
    truncada = _seccion(offset_x_m=off_justo - 1e-6)
    perdido = cerrada.bo_m - truncada.bo_m
    assert perdido == pytest.approx(BY + D, abs=1e-5)


# =========================================================================
# 5. Transferencia de momento sobre sección truncada
# =========================================================================

def test_la_transferencia_de_momento_usa_el_Jc_truncado():
    s = _seccion(offset_x_m=OFF_BORDE_X)
    r = check_punching_with_moment_transfer(
        Vu_kN=600.0, Mux_kNm=200.0, Muy_kNm=0.0,
        bx_m=BX, by_m=BY, d_m=D, Vc_kN=1500.0, phi=0.85, section=s,
    )
    assert r.axis_x is not None
    assert r.axis_x.Jc_m4 == pytest.approx(s.axis_x.Jc_m4)
    assert r.axis_x.c_m == pytest.approx(s.axis_x.c_max_m)
    assert r.bo_m == pytest.approx(s.bo_m)


def test_sin_seccion_la_transferencia_conserva_el_comportamiento_anterior():
    """Retrocompatibilidad: omitir `section` supone la sección cerrada de columna
    interior, que es lo que hacía antes de la Fase 1C."""
    sin = check_punching_with_moment_transfer(
        Vu_kN=600.0, Mux_kNm=200.0, Muy_kNm=0.0,
        bx_m=BX, by_m=BY, d_m=D, Vc_kN=1500.0, phi=0.85,
    )
    con = check_punching_with_moment_transfer(
        Vu_kN=600.0, Mux_kNm=200.0, Muy_kNm=0.0,
        bx_m=BX, by_m=BY, d_m=D, Vc_kN=1500.0, phi=0.85, section=_seccion(),
    )
    assert con.v_max_MPa == pytest.approx(sin.v_max_MPa, rel=1e-12)


def test_el_momento_amplifica_mas_sobre_una_seccion_truncada():
    """Jc menor y c mayor: el mismo momento produce más esfuerzo. Es la razón de que
    una columna de borde con momento sea el caso más exigente."""
    comun = dict(Vu_kN=600.0, Mux_kNm=200.0, Muy_kNm=0.0, bx_m=BX, by_m=BY,
                 d_m=D, Vc_kN=1500.0, phi=0.85)
    interior = check_punching_with_moment_transfer(**comun, section=_seccion())
    borde = check_punching_with_moment_transfer(
        **comun, section=_seccion(offset_x_m=OFF_BORDE_X)
    )
    assert borde.axis_x.shear_stress_MPa > interior.axis_x.shear_stress_MPa


# =========================================================================
# 6. Geometría sin categoría normativa
# =========================================================================

def test_tres_o_cuatro_lados_recortados_no_tienen_alpha_s_y_se_rechazan():
    """E.060 §11.12.2.1(b) solo clasifica 0, 1 o 2 lados recortados. Para 3 o 4 no
    hay valor prescrito y el motor no inventa uno."""
    r = check_punching_shear(560.0, 1.0, 1.0, 0.40, 0.40, 0.70, 21.0, CODE)
    assert r.column_position == "degenerada"
    assert r.status is CheckStatus.FAIL
    assert r.alpha_s == 0.0
    assert r.phi_Vc_kN == 0.0
    assert "no prescribe alpha_s" in r.completeness_note


# =========================================================================
# 7. Integración con el solver
# =========================================================================

def _cand(offset_x: float, offset_y: float = 0.0, Mx: float = 0.0):
    columna = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
    return evaluate_candidate(
        B_m=3.20, L_m=3.20, h_m=0.70, column=columna,
        soil=SoilProfile(
            qadm_kPa=400.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
            Df_m=1.20, source_notes="prueba",
        ),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                     P_kN=700.0, Mx_kNm=Mx)],
            factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                      P_kN=980.0, Mx_kNm=Mx * 1.4)],
        ),
        code=CODE, contact_model=FullContactModel(),
        depth_params=DepthSearchParameters(h_min_m=0.70, h_max_m=0.70, h_step_m=0.05),
        placement=ColumnPlacement(column=columna, offset_x_m=offset_x, offset_y_m=offset_y),
    )


def test_el_solver_resuelve_una_columna_de_borde():
    cand = _cand(offset_x=1.15)
    assert cand.punching.column_position == "borde"
    assert cand.punching.critical_section_sides == 3
    assert cand.punching.alpha_s == 30.0
    assert cand.punching.phi_Vc_kN > 0.0


def test_el_solver_resuelve_una_columna_de_esquina():
    cand = _cand(offset_x=1.15, offset_y=1.15)
    assert cand.punching.column_position == "esquina"
    assert cand.punching.critical_section_sides == 2
    assert cand.punching.alpha_s == 20.0


def test_una_columna_de_borde_con_momento_se_verifica_por_11_12_6():
    """El caso más exigente: sección truncada Y momento no balanceado."""
    cand = _cand(offset_x=1.15, Mx=150.0)
    assert cand.punching.unbalanced_moment_present
    assert cand.punching.moment_transfer is not None
    assert "§11.12.7" in cand.punching.completeness_note


def test_la_columna_de_borde_queda_declarada_en_la_traza():
    entrada = _cand(offset_x=1.15).trace.by_id("punching")
    texto = " ".join(entrada.hypotheses) + entrada.equation_substituted
    assert "borde" in texto or "TRUNCADA" in texto
