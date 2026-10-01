"""Campo de presión de DISEÑO: contacto unilateral resuelto por equilibrio (2026-09-20).

QUÉ MODELO ES, Y QUÉ SUSTITUYE
==============================
El suelo no tracciona. La distribución bajo una zapata rígida es un plano **truncado en
cero**, `q⁺ = max(a + b·u + c·v, 0)`, y los tres coeficientes se determinan por equilibrio:

    ∫∫ q⁺ dA = Pu        ∫∫ x·q⁺ dA = Pu·ex        ∫∫ y·q⁺ dA = Pu·ey

`engine/foundation/unilateral_contact.py` lo resuelve, y es el **campo común** de
punzonamiento, flexión y cortante unidireccional. No hay una segunda representación del
contacto de diseño.

Sustituye a dos aproximaciones sucesivas, insuficientes las dos en el mismo régimen:

1. la forma cerrada del campo LINEAL para el alivio del punzonamiento, que fuera del
   núcleo describe una distribución que no existe;
2. la SUPERPOSICIÓN de los dos campos unidireccionales, exacta con contacto total y con
   despegue en una sola dirección, pero que con excentricidad biaxial no resolvía el
   contacto: su parte positiva entregaba 1,61·Pu en el régimen de `17_columna_de_esquina`
   y daba un alivio de 397,5 kN donde el exacto es 825,2.

QUÉ COMPRUEBA ESTE ARCHIVO
==========================
1. El campo: equilibrio en las tres ecuaciones, existencia y los tres regímenes.
2. Que los dos regímenes cerrados **son** la solución, no una aproximación de ella.
3. Las integrales: exactas contra malla fina, sobre polígonos recortados.
4. Punzonamiento, flexión y cortante sobre el mismo campo.

Las reconstrucciones se escriben a mano, sin llamar al código que se prueba (CLAUDE.md
§12).
"""

import pytest

from engine.foundation.critical_section import build_critical_section
from engine.foundation.flexure import moment_at_critical_section, net_pressure_field
from engine.foundation.punching_shear import punching_demand
from engine.foundation.shear_oneway import shear_force_at_d_from_face
from engine.foundation.unilateral_contact import (
    ContactFieldImpossible,
    clip_half_plane,
    momentos_poligono,
    solve_unilateral_contact,
)

B, L = 3.00, 2.40
PU = 840.0

# Los tres regímenes. B/6 = 0,500 y L/6 = 0,400, pero OJO: el núcleo de un rectángulo es
# el ROMBO |6·ex/B| + |6·ey/L| <= 1, no el producto de los dos sextos.
REGIMENES = [
    (0.00, 0.00, "concéntrica", "total"),
    (0.30, 0.00, "dentro del rombo, un eje", "total"),
    (0.25, 0.20, "justo sobre el rombo", "total"),
    (0.70, 0.00, "despegue uniaxial en X", "uniaxial"),
    (0.00, -0.55, "despegue uniaxial en Y", "uniaxial"),
    (-1.20, 0.00, "despegue uniaxial severo", "uniaxial"),
    (0.30, 0.20, "biaxial: cada eje en su sexto, el rombo no", "biaxial"),
    (0.90, 0.60, "biaxial franco", "biaxial"),
    (-1.10, -0.75, "biaxial, signos negativos", "biaxial"),
]


def _campo(ex: float, ey: float):
    return solve_unilateral_contact(PU, B, L, ex, ey)


def _regimen(campo) -> str:
    if campo.full_contact:
        return "total"
    return "uniaxial" if campo.uniaxial else "biaxial"


def _malla(campo, x_lo, x_hi, y_lo, y_hi, n=400):
    """Punto medio sobre malla fina. Deliberadamente tonta: no sabe dónde acaba el
    contacto ni recorta polígonos, de modo que converge a la integral verdadera sin
    compartir una línea con el código que se prueba."""
    dx, dy = (x_hi - x_lo) / n, (y_hi - y_lo) / n
    F = Mx = My = 0.0
    for i in range(n):
        x = x_lo + (i + 0.5) * dx
        for j in range(n):
            y = y_lo + (j + 0.5) * dy
            q = max(campo.plane_at(x, y), 0.0)
            F += q
            Mx += x * q
            My += y * q
    k = dx * dy
    return F * k, Mx * k, My * k


# =========================================================================
# 1. El campo cumple las tres ecuaciones de equilibrio
# =========================================================================


@pytest.mark.parametrize("ex,ey,etq,_reg", REGIMENES)
def test_el_campo_equilibra_las_tres_ecuaciones(ex, ey, etq, _reg):
    """`∫q⁺ = Pu`, `∫x·q⁺ = Pu·ex`, `∫y·q⁺ = Pu·ey`, en TODOS los regímenes.

    Es la definición del campo, no una propiedad deseable: si alguna no se cumple, lo que
    hay debajo no es una distribución en equilibrio con la carga."""
    rF, rMx, rMy = _campo(ex, ey).equilibrium_residual()
    assert abs(rF) <= 1e-9 * PU, etq
    assert abs(rMx) <= 1e-9 * PU * B, etq
    assert abs(rMy) <= 1e-9 * PU * L, etq


@pytest.mark.parametrize("ex,ey,etq,reg", REGIMENES)
def test_cada_caso_cae_en_el_regimen_que_le_toca(ex, ey, etq, reg):
    """El régimen no es una etiqueta suelta: decide si se itera o se escribe la solución.

    En particular, `(0.30, 0.20)` es **biaxial** aunque cada excentricidad esté dentro de
    su propio sexto —B/6 = 0,500 y L/6 = 0,400—, porque el núcleo es el rombo y
    `6·0,30/3,00 + 6·0,20/2,40 = 1,10 > 1`."""
    campo = _campo(ex, ey)
    assert _regimen(campo) == reg, etq
    assert (campo.iterations == 0) is (reg != "biaxial")


@pytest.mark.parametrize("ex,ey,etq,_reg", REGIMENES)
def test_la_presion_nunca_es_negativa(ex, ey, etq, _reg):
    campo = _campo(ex, ey)
    for i in range(11):
        for j in range(11):
            assert campo.q_at(-B / 2 + i * B / 10, -L / 2 + j * L / 10) >= 0.0, etq


def test_sin_campo_posible_se_declara_imposible():
    """Una distribución no negativa tiene su resultante DENTRO de la huella. Fuera de ella
    no hay nada que resolver, y decirlo es mejor que devolver un número."""
    with pytest.raises(ContactFieldImpossible):
        solve_unilateral_contact(PU, B, L, B / 2 + 0.01, 0.0)
    with pytest.raises(ContactFieldImpossible):
        solve_unilateral_contact(PU, B, L, 0.0, L / 2)
    with pytest.raises(ContactFieldImpossible):
        solve_unilateral_contact(0.0, B, L, 0.0, 0.0)
    # Y justo por dentro sí existe, con una zona comprimida diminuta.
    campo = solve_unilateral_contact(PU, B, L, B / 2 - 0.05, L / 2 - 0.05)
    assert campo.contact_area_m2 > 0.0
    assert abs(campo.equilibrium_residual()[0]) <= 1e-9 * PU


def test_newton_converge_tambien_muy_cerca_de_la_esquina():
    """El caso que rompe un Newton sin búsqueda de línea: la zona comprimida es un
    triángulo minúsculo y el primer paso, partiendo del plano lineal, se pasa de largo."""
    campo = solve_unilateral_contact(1000.0, 3.00, 3.00, 1.40, 1.40)
    assert campo.contact_area_m2 == pytest.approx(0.08, abs=1e-3)
    for r, escala in zip(campo.equilibrium_residual(), (1000.0, 3000.0, 3000.0)):
        assert abs(r) <= 1e-9 * escala


# =========================================================================
# 2. Los regímenes cerrados SON la solución
# =========================================================================


@pytest.mark.parametrize("ex,ey", [(0.0, 0.0), (0.30, 0.0), (0.0, 0.25), (0.25, 0.20)])
def test_con_contacto_total_es_el_plano_lineal_clasico(ex, ey):
    """`q = q_avg·(1 + 12·ex·x/B² + 12·ey·y/L²)`, término a término.

    Continuidad con lo que el motor ya calculaba: ninguna geometría con la resultante
    dentro del núcleo puede cambiar de resultado por este cambio de modelo."""
    campo = _campo(ex, ey)
    q_avg = PU / (B * L)
    for x in (-1.4, -0.7, 0.0, 0.55, 1.45):
        for y in (-1.1, -0.3, 0.0, 0.8, 1.15):
            esperado = q_avg * (1.0 + 12.0 * ex * x / B**2 + 12.0 * ey * y / L**2)
            assert campo.q_at(x, y) == pytest.approx(esperado, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("ex", [0.70, -0.85, 1.20, 0.55])
def test_con_despegue_uniaxial_es_el_bloque_triangular(ex):
    """La marginal del campo reproduce `NetPressureField`, el bloque triangular de la
    decisión B (2026-09-19).

    Con `ey = 0` el campo no depende de `y`, de modo que su marginal es `q(x, 0)·L`. Que
    coincida significa que el contacto unilateral **no aporta nada nuevo** en este
    régimen: ya estaba resuelto, y por eso aquí no se itera."""
    campo = _campo(ex, 0.0)
    unidireccional = net_pressure_field(PU, ex, B)
    for k in range(41):
        s = k * B / 40.0
        x = (B / 2 - s) if ex >= 0 else (s - B / 2)
        assert campo.q_at(x, 0.0) * L == pytest.approx(
            unidireccional.q_at(s), rel=1e-10, abs=1e-9
        )
    assert campo.contact_area_m2 == pytest.approx(3.0 * (B / 2 - abs(ex)) * L, rel=1e-10)


def test_el_regimen_biaxial_NO_coincide_con_la_superposicion():
    """Lo que motivó el cambio, con número.

    La superposición de los dos campos 1-D —lo que el motor usaba— se reconstruye aquí a
    mano. En el régimen de `17_columna_de_esquina` su parte positiva entrega 1,61·Pu: no
    es una distribución admisible. El campo unilateral entrega Pu por construcción."""
    lado, pu = 3.20, 840.0
    ex, ey = 1.35, -1.35
    fx = net_pressure_field(pu, ex, lado)
    fy = net_pressure_field(pu, ey, lado)

    def superpuesto(x, y):
        s_x = lado / 2 - x           # ex > 0
        s_y = y + lado / 2           # ey < 0
        return fx.q_at(s_x) / lado + fy.q_at(s_y) / lado - pu / (lado * lado)

    n = 400
    h = lado / n
    total = sum(
        max(superpuesto(-lado / 2 + (i + 0.5) * h, -lado / 2 + (j + 0.5) * h), 0.0)
        for i in range(n)
        for j in range(n)
    ) * h * h
    assert total / pu == pytest.approx(1.607, abs=5e-3)

    unilateral = solve_unilateral_contact(pu, lado, lado, ex, ey)
    assert abs(unilateral.equilibrium_residual()[0]) <= 1e-9 * pu
    # Su zona comprimida es un triángulo de medio metro cuadrado en la esquina.
    assert unilateral.contact_area_m2 == pytest.approx(0.500, abs=1e-3)


# =========================================================================
# 3. Las integrales
# =========================================================================


@pytest.mark.parametrize("ex,ey,etq,_reg", REGIMENES)
def test_las_resultantes_coinciden_con_una_integracion_bruta(ex, ey, etq, _reg):
    """Momentos del polígono contra malla de 400×400. La tolerancia es la del error de la
    malla, no la del método: los momentos del polígono son exactos."""
    campo = _campo(ex, ey)
    for rect in ((-B / 2, B / 2, -L / 2, L / 2), (-0.9, 0.62, -0.7, 0.51)):
        exacto = campo.resultants_over_rectangle(*rect)
        bruto = _malla(campo, *rect, n=400)
        escala = max(abs(bruto[0]), 1e-9)
        for k in range(3):
            assert abs(exacto[k] - bruto[k]) <= 3e-4 * escala * (1.0 if k == 0 else B), etq


def test_los_momentos_del_poligono_reconstruidos_a_mano():
    """Un triángulo rectángulo con respuesta analítica: (0,0), (2,0), (0,3).

    `A = b·h/2`, `Su = A·b/3`, `Sv = A·h/3`, `Iuu = b³·h/12`, `Ivv = h³·b/12`,
    `Iuv = b²·h²/24`. Son las fórmulas de libro, escritas aquí para no depender de la
    implementación que se prueba."""
    b, h = 2.0, 3.0
    m = momentos_poligono([(0.0, 0.0), (b, 0.0), (0.0, h)])
    assert m.A == pytest.approx(b * h / 2)
    assert m.Su == pytest.approx(b * h / 2 * b / 3)
    assert m.Sv == pytest.approx(b * h / 2 * h / 3)
    assert m.Iuu == pytest.approx(b**3 * h / 12)
    assert m.Ivv == pytest.approx(h**3 * b / 12)
    assert m.Iuv == pytest.approx(b**2 * h**2 / 24)


def test_los_momentos_no_dependen_de_la_orientacion_del_contorno():
    directo = momentos_poligono([(0.0, 0.0), (2.0, 0.0), (0.0, 3.0)])
    inverso = momentos_poligono([(0.0, 3.0), (2.0, 0.0), (0.0, 0.0)])
    for campo in ("A", "Su", "Sv", "Iuu", "Iuv", "Ivv"):
        assert getattr(directo, campo) == pytest.approx(getattr(inverso, campo))


def test_el_recorte_deja_un_convexo_y_respeta_el_semiplano():
    cuadrado = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    # Semiplano u + v >= 0: corta el cuadrado por su diagonal.
    recortado = clip_half_plane(cuadrado, 0.0, 1.0, 1.0)
    assert len(recortado) == 3
    assert momentos_poligono(recortado).A == pytest.approx(2.0)  # la mitad de 4
    # Un semiplano que no alcanza nada deja el polígono vacío.
    assert momentos_poligono(clip_half_plane(cuadrado, -5.0, 1.0, 1.0)).degenerado
    # Y uno que lo contiene entero no quita nada.
    assert momentos_poligono(clip_half_plane(cuadrado, 5.0, 1.0, 1.0)).A == pytest.approx(4.0)


def test_un_rectangulo_degenerado_no_aporta_nada():
    campo = _campo(0.30, 0.20)
    assert campo.resultants_over_rectangle(0.4, 0.4, -0.3, 0.3) == (0.0, 0.0, 0.0)
    assert campo.force_over_rectangle(0.4, 0.2, -0.3, 0.3) == 0.0


def test_la_suma_de_las_partes_es_el_todo():
    """Aditividad de la integral: partir la huella en cuatro y sumar da lo mismo.

    Delata un recorte mal hecho, porque la frontera del contacto atraviesa varias partes."""
    campo = _campo(0.90, 0.60)
    entero = campo.resultants_over_rectangle(-B / 2, B / 2, -L / 2, L / 2)
    partes = [
        campo.resultants_over_rectangle(x0, x1, y0, y1)
        for x0, x1 in ((-B / 2, 0.37), (0.37, B / 2))
        for y0, y1 in ((-L / 2, -0.11), (-0.11, L / 2))
    ]
    for k in range(3):
        assert sum(p[k] for p in partes) == pytest.approx(entero[k], rel=1e-12, abs=1e-12)


# =========================================================================
# 4. Punzonamiento, flexión y cortante sobre el MISMO campo
# =========================================================================

BX = BY = 0.50
D = 0.60


def _seccion(offset_x=0.0, offset_y=0.0):
    return build_critical_section(B, L, BX, BY, D, offset_x, offset_y)


def test_concentrica_sin_momento_el_alivio_es_qu_por_el_area():
    area = (BX + D) * (BY + D)
    vu = punching_demand(PU, B, L, BX, BY, D, section=_seccion())
    assert vu == pytest.approx(PU - PU / (B * L) * area, rel=1e-12)


@pytest.mark.parametrize(
    "ex,ey,ox,oy",
    [(0.30, 0.00, 0.0, 0.0), (0.20, 0.15, 0.0, 0.0), (0.15, 0.10, 0.60, -0.40)],
)
def test_dentro_del_rombo_reproduce_la_forma_cerrada_anterior(ex, ey, ox, oy):
    """Ninguna geometría con contacto total cambia de resultado.

    La forma cerrada se escribe aquí a mano —es la que el motor ya no tiene— y es la que
    fijó los casos congelados que no se mueven."""
    seccion = _seccion(ox, oy)
    cx = (seccion.x_hi_m + seccion.x_lo_m) / 2.0
    cy = (seccion.y_hi_m + seccion.y_lo_m) / 2.0
    area = (seccion.x_hi_m - seccion.x_lo_m) * (seccion.y_hi_m - seccion.y_lo_m)
    cerrada = PU / (B * L) * (1.0 + 12.0 * ex * cx / B**2 + 12.0 * ey * cy / L**2) * area

    vu = punching_demand(
        PU, B, L, BX, BY, D, offset_x_m=ox, offset_y_m=oy,
        ex_m=ex, ey_m=ey, section=seccion,
    )
    assert vu == pytest.approx(PU - cerrada, rel=1e-12)


def test_el_punzonamiento_integra_el_campo_unilateral():
    ex, ey = 0.90, 0.60
    campo = _campo(ex, ey)
    seccion = _seccion()
    esperado = campo.force_over_rectangle(
        seccion.x_lo_m, seccion.x_hi_m, seccion.y_lo_m, seccion.y_hi_m
    )
    vu = punching_demand(PU, B, L, BX, BY, D, ex_m=ex, ey_m=ey, section=seccion)
    assert vu == pytest.approx(PU - esperado, rel=1e-12)


def test_la_carga_que_punzona_y_la_que_produce_el_campo_son_distintas():
    """Separación `P_u_column_kN` / `field_P_u_kN`, que la combinada necesita: bajo una
    zapata combinada el campo lo produce la RESULTANTE de todas las columnas."""
    P_col, P_total = 500.0, 1200.0
    area = (BX + D) * (BY + D)
    vu = punching_demand(P_col, B, L, BX, BY, D, section=_seccion(), field_P_u_kN=P_total)
    assert vu == pytest.approx(P_col - P_total / (B * L) * area, rel=1e-12)


def test_sin_campo_posible_el_punzonamiento_no_revienta():
    """La resultante fuera de la huella: se devuelve la carga entera, sin alivio, que es
    el mismo criterio con que `NetPressureField` trata `e >= dim/2`."""
    vu = punching_demand(PU, B, L, BX, BY, D, ex_m=B / 2 + 0.1, section=_seccion())
    assert vu == pytest.approx(PU)


def test_la_flexion_y_el_cortante_usan_el_mismo_campo_con_despegue_biaxial():
    """El campo es COMÚN. Con despegue biaxial la presión deja de ser uniforme a lo ancho
    de la franja, y el voladizo ya no se puede integrar como un problema 1-D."""
    ex, ey = 0.90, 0.60
    cant, d = 1.25, 0.60
    campo = _campo(ex, ey)

    # A mano: la franja del voladizo del lado de mayor presión va de x = B/2 − cant a B/2.
    x_lo, x_hi = B / 2 - cant, B / 2
    F, Mx, _ = campo.resultants_over_rectangle(x_lo, x_hi, -L / 2, L / 2)
    Mu_esperado = abs(x_lo * F - Mx)

    Mu = moment_at_critical_section(
        PU, ex, B, cant, near_high_edge=True, e_transverse_m=ey, dim_transverse_m=L
    )
    assert Mu == pytest.approx(Mu_esperado, rel=1e-12)

    x_corte = B / 2 - (cant - d)
    Vu_esperado = campo.force_over_rectangle(x_corte, B / 2, -L / 2, L / 2)
    Vu = shear_force_at_d_from_face(
        PU, ex, B, cant, d, near_high_edge=True, e_transverse_m=ey, dim_transverse_m=L
    )
    assert Vu == pytest.approx(Vu_esperado, rel=1e-12)


@pytest.mark.parametrize("ex,ey", [(0.30, 0.00), (0.20, 0.15), (0.70, 0.00)])
def test_sin_despegue_biaxial_flexion_y_cortante_no_cambian_ni_un_bit(ex, ey):
    """La ruta 1-D y la 2-D tienen que dar **el mismo número**, no uno parecido.

    En contacto total y en despegue uniaxial la marginal del campo común es exactamente
    `NetPressureField`, de modo que declarar la excentricidad transversal no puede mover
    nada. Es lo que permite que el cambio de modelo solo toque el régimen biaxial, y lo
    que hace revisable el diff del congelamiento."""
    cant, d = 1.10, 0.55
    for lado in (True, False):
        sin = moment_at_critical_section(PU, ex, B, cant, near_high_edge=lado)
        con = moment_at_critical_section(
            PU, ex, B, cant, near_high_edge=lado, e_transverse_m=ey, dim_transverse_m=L
        )
        assert con == sin
        sin_v = shear_force_at_d_from_face(PU, ex, B, cant, d, near_high_edge=lado)
        con_v = shear_force_at_d_from_face(
            PU, ex, B, cant, d, near_high_edge=lado, e_transverse_m=ey, dim_transverse_m=L
        )
        assert con_v == sin_v
