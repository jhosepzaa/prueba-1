"""FASE 2 — Diagramas de cortante y momento a lo largo de la zapata.

Base normativa: E.060 §15.4.1, que define el momento en CUALQUIER sección por
estática sobre el área a un lado del plano. Es la regla general; §15.4.2, el de la
cara de columna, está acotado a la zapata AISLADA.

QUÉ SE VERIFICA
===============
1. DEGENERACIÓN. Con una sola columna centrada, el diagrama debe reproducir
   exactamente el voladizo que ya calcula el motor de zapata aislada.
2. EQUILIBRIO. La resultante de presiones debe igualar la de cargas y estar en el
   mismo punto; V y M deben cerrar en cero al final.
3. El momento negativo entre columnas, que es lo que obliga a armar la cara
   superior y no existe en una zapata aislada.
4. Los extremos de M se resuelven donde V=0, no muestreando.
5. Los momentos aplicados por las columnas desplazan la resultante.
"""

from __future__ import annotations

import pytest

from engine.analysis.beam_diagram import PointLoad, build_beam_diagram

TONF_TO_KN = 9.80665


def _carga(nombre: str, x: float, P: float, M: float = 0.0, b: float = 0.50) -> PointLoad:
    return PointLoad(label=nombre, position_m=x, P_kN=P, M_kNm=M, width_m=b)


# =========================================================================
# 1. Degeneración al caso de zapata aislada
# =========================================================================

def test_una_columna_centrada_reproduce_el_voladizo_con_carga_uniforme():
    """Con una sola columna centrada la presión es uniforme y el momento en la cara
    debe ser w·c²/2, que es la fórmula clásica del voladizo."""
    L, B, P, bc = 4.0, 2.0, 1000.0, 0.50
    d = build_beam_diagram(L, B, [_carga("C1", L / 2, P, b=bc)])

    assert d.w_start_kNm == pytest.approx(P / L)
    assert d.w_end_kNm == pytest.approx(P / L)

    c = (L - bc) / 2.0
    cara = next(p for p in d.critical_points if "cara izquierda" in p.description)
    assert cara.M_kNm == pytest.approx((P / L) * c**2 / 2.0)


def test_una_sola_columna_no_produce_momento_negativo():
    """No hay tramo entre columnas: no hay nada que armar arriba."""
    d = build_beam_diagram(4.0, 2.0, [_carga("C1", 2.0, 1000.0)])
    assert not d.has_negative_moment
    assert d.M_max_negative_kNm == pytest.approx(0.0, abs=1e-9)


def test_una_columna_descentrada_da_presion_trapecial():
    d = build_beam_diagram(4.0, 2.0, [_carga("C1", 1.2, 1000.0)])
    assert d.w_start_kNm > d.w_end_kNm, "Más presión del lado hacia el que está la carga"


# =========================================================================
# 2. Equilibrio — la comprobación que no puede fallar
# =========================================================================

@pytest.mark.parametrize(
    "cargas",
    [
        [("C1", 2.0, 1000.0)],
        [("C1", 1.0, 1000.0), ("C2", 7.0, 1000.0)],
        [("C1", 1.0, 800.0), ("C2", 5.5, 2000.0)],
        [("C1", 0.8, 500.0), ("C2", 3.5, 1200.0), ("C3", 6.9, 900.0)],
    ],
)
def test_las_fuerzas_y_los_momentos_cierran(cargas):
    L = 8.0
    loads = [_carga(n, x, P) for n, x, P in cargas]
    d = build_beam_diagram(L, 3.0, loads)

    assert d.equilibrium_residual_kN == pytest.approx(0.0, abs=1e-9)
    final = d.critical_points[-1]
    assert final.x_m == pytest.approx(L)
    assert final.V_kN == pytest.approx(0.0, abs=1e-9), "El cortante debe cerrar en el extremo"
    assert final.M_kNm == pytest.approx(0.0, abs=1e-8), "El momento debe cerrar en el extremo"


def test_la_resultante_de_presiones_coincide_con_la_de_cargas():
    """Si no coincidiera, la zapata estaría girando."""
    L = 7.0
    loads = [_carga("C1", 1.0, 800.0), _carga("C2", 5.5, 2000.0)]
    d = build_beam_diagram(L, 3.0, loads)

    P_total = sum(ld.P_kN for ld in loads)
    x_cargas = sum(ld.P_kN * ld.position_m for ld in loads) / P_total
    w0, w1 = d.w_start_kNm, d.w_end_kNm
    x_presiones = (w0 / 2.0 + (w1 - w0) / 3.0) * L**2 / P_total
    assert x_presiones == pytest.approx(x_cargas)


def test_una_resultante_fuera_del_nucleo_se_declara_en_las_hipotesis():
    """Con la resultante muy descentrada la distribución lineal da presión negativa.
    El suelo no resiste tracción (§15.2): hay que decirlo, no devolver el número."""
    d = build_beam_diagram(8.0, 3.0, [_carga("C1", 0.5, 1000.0)])
    assert d.w_end_kNm < 0
    assert any("no resiste tracción" in h for h in d.hypotheses)


# =========================================================================
# 3. Momento negativo — lo que obliga a armar la cara superior
# =========================================================================

def test_dos_columnas_con_voladizos_cortos_producen_momento_negativo():
    L = 8.0
    d = build_beam_diagram(L, 3.0, [_carga("C1", 1.0, 1000.0), _carga("C2", 7.0, 1000.0)])

    assert d.has_negative_moment
    assert d.x_M_max_negative_m == pytest.approx(4.0), "Simétrico: el extremo está en el centro"

    w = 2000.0 / L
    esperado = w * 4.0**2 / 2.0 - 1000.0 * (4.0 - 1.0)
    assert -d.M_max_negative_kNm == pytest.approx(esperado)


def test_los_voladizos_largos_pueden_anular_el_momento_negativo():
    """No siempre hay momento negativo: depende de la relación entre voladizo y luz.
    Con voladizos de 2 m y luz de 4 m se anula exactamente, y ese caso NO necesita
    acero superior por flexión."""
    d = build_beam_diagram(8.0, 3.0, [_carga("C1", 2.0, 1000.0), _carga("C2", 6.0, 1000.0)])
    assert d.M_max_negative_kNm == pytest.approx(0.0, abs=1e-9)


def test_con_cargas_desiguales_el_extremo_se_desplaza():
    """Y no al centro geométrico: hacia la columna menos cargada."""
    iguales = build_beam_diagram(8.0, 3.0, [_carga("C1", 1.0, 1000.0), _carga("C2", 7.0, 1000.0)])
    desiguales = build_beam_diagram(8.0, 3.0, [_carga("C1", 1.0, 600.0), _carga("C2", 7.0, 1400.0)])

    assert iguales.x_M_max_negative_m == pytest.approx(4.0)
    assert desiguales.x_M_max_negative_m > 4.0, "Se corre hacia la columna menos cargada"


def test_tres_columnas_producen_dos_tramos_con_momento_negativo():
    d = build_beam_diagram(12.0, 3.0, [
        _carga("C1", 1.0, 900.0), _carga("C2", 6.0, 1200.0), _carga("C3", 11.0, 900.0)
    ])
    ceros = [p for p in d.critical_points if "cortante nulo" in p.description]
    negativos = [p for p in ceros if p.M_kNm < 0]
    assert len(negativos) >= 2, "Un extremo negativo por cada tramo entre columnas"


# =========================================================================
# 4. Los extremos se resuelven, no se muestrean
# =========================================================================

def test_el_extremo_de_M_esta_exactamente_donde_V_es_nulo():
    d = build_beam_diagram(8.0, 3.0, [_carga("C1", 1.0, 600.0), _carga("C2", 7.0, 1400.0)])
    extremo = next(
        p for p in d.critical_points
        if "cortante nulo" in p.description and p.M_kNm == pytest.approx(-d.M_max_negative_kNm)
    )
    # Tolerancia RELATIVA a la carga total: un residuo absoluto fijo no dice nada
    # cuando las cargas son de miles de kN.
    P_total = sum(ld.P_kN for ld in d.loads)
    assert abs(extremo.V_kN) / P_total < 1e-9


def test_resolver_es_mas_exacto_que_muestrear():
    """Un muestreo grueso subestima el momento máximo, es decir queda del lado
    inseguro. Se comprueba que la solución exacta lo supera."""
    L = 8.0
    loads = [_carga("C1", 1.0, 600.0), _carga("C2", 7.0, 1400.0)]
    d = build_beam_diagram(L, 3.0, loads)

    from engine.analysis.beam_diagram import _moment

    w0, w1 = d.w_start_kNm, d.w_end_kNm
    muestreo = max(
        -_moment(L * i / 20.0, w0, w1, L, loads) for i in range(21)
    )
    assert d.M_max_negative_kNm >= muestreo


# =========================================================================
# 5. Momentos aplicados por las columnas
# =========================================================================

def test_un_momento_aplicado_desplaza_la_resultante_sin_aportar_carga():
    sin_m = build_beam_diagram(8.0, 3.0, [_carga("C1", 4.0, 1000.0)])
    con_m = build_beam_diagram(8.0, 3.0, [_carga("C1", 4.0, 1000.0, M=500.0)])

    assert sin_m.w_start_kNm == pytest.approx(sin_m.w_end_kNm), "Sin momento, presión uniforme"
    assert con_m.w_end_kNm > con_m.w_start_kNm, "El momento inclina la distribución"
    # La carga total no cambia: un par no aporta fuerza vertical.
    assert (con_m.w_start_kNm + con_m.w_end_kNm) == pytest.approx(
        sin_m.w_start_kNm + sin_m.w_end_kNm
    )


def test_el_momento_aplicado_salta_el_diagrama_de_momentos():
    """Un par no produce cortante pero SÍ un salto en M al pasar por su punto.

    EL SIGNO DEL SALTO ES +M (corregido el 2026-09-22)
    ==================================================
    Este test exigía −500 para M = +500, y así FIJABA el defecto en vez de detectarlo. El
    signo no es una convención libre: lo impone el campo de presiones de este mismo
    módulo, en el que M > 0 corre la carga hacia +x. Se comprueba por cierre, que no
    admite discusión: con una columna en x = 4, P = 1000 y M = +500, la resultante cae en
    x_R = 4,5 y el extremo libre vale

        M(8) = P·(L − x_R) − P·(L − 4) + salto = 3500 − 4000 + salto

    que es cero SOLO si el salto es +500. Con −500 queda en −1000."""
    d = build_beam_diagram(8.0, 3.0, [_carga("C1", 4.0, 1000.0, M=500.0)])
    from engine.analysis.beam_diagram import _moment

    w0, w1, L = d.w_start_kNm, d.w_end_kNm, 8.0
    antes = _moment(4.0 - 1e-7, w0, w1, L, d.loads)
    despues = _moment(4.0 + 1e-7, w0, w1, L, d.loads)
    assert despues - antes == pytest.approx(+500.0, abs=1e-3)
    # Y el extremo libre cierra, que es lo que decide el signo.
    assert d.critical_points[-1].M_kNm == pytest.approx(0.0, abs=1e-8)


# =========================================================================
# 6. Contraste con bibliografía — Aragón 3.5
# =========================================================================

def test_aragon_3_5_reproduce_la_posicion_de_la_resultante():
    """Aragón «Concreto Armado 2» §3.5: dos columnas 50x50, la primera en límite de
    propiedad. El libro sitúa la resultante en x = 3,60 m mediante
        0,25(110) + 5,25(220) + 8,5 − 2,5 = X(330)
    incluyendo los momentos aplicados, que es exactamente el modelo de este módulo."""
    T = TONF_TO_KN
    d = build_beam_diagram(7.20, 3.80, [
        _carga("C1", 0.25, 110.0 * T, M=8.5 * T),
        _carga("C2", 5.25, 220.0 * T, M=-2.5 * T),
    ])
    # Con L = 7,20 m el libro busca que la resultante caiga en el centroide, lo que
    # produce presión uniforme. Se comprueba que efectivamente sale casi uniforme.
    assert abs(d.w_end_kNm - d.w_start_kNm) / d.w_start_kNm < 0.01


def test_aragon_3_5_el_peso_propio_no_entra_en_los_diagramas():
    """El libro toma P = 363 t incluyendo un 10% de peso propio; para la presión sobre
    el SUELO es correcto. Para los diagramas de flexión no lo es: el peso propio está
    equilibrado por la reacción justo debajo. Este módulo usa las 330 t de columna."""
    T = TONF_TO_KN
    d = build_beam_diagram(7.20, 3.80, [
        _carga("C1", 0.25, 110.0 * T), _carga("C2", 5.25, 220.0 * T),
    ])
    q_modulo = d.w_start_kNm / 3.80 / T
    q_libro_con_pp = 363.0 / (7.20 * 3.80)
    assert q_libro_con_pp / q_modulo == pytest.approx(1.10, rel=0.02), (
        "La diferencia debe ser exactamente el 10% de peso propio que añade el libro"
    )


@pytest.mark.parametrize(
    "cargas",
    [
        # (nombre, x, P, M): con momentos, que es lo que el test de cierre de arriba no
        # probaba. Las cuatro columnas de aquel tienen M = 0.
        [("C1", 4.0, 1000.0, 500.0)],
        [("C1", 1.0, 1000.0, 200.0), ("C2", 7.0, 1000.0, -300.0)],
        [("C1", 1.0, 800.0, -150.0), ("C2", 5.5, 2000.0, 400.0)],
        [("C1", 0.8, 500.0, 90.0), ("C2", 3.5, 1200.0, -60.0), ("C3", 6.9, 900.0, 250.0)],
    ],
)
def test_el_momento_cierra_tambien_con_pares_de_columna(cargas):
    """El control de cierre CON pares aplicados (2026-09-22).

    `test_las_fuerzas_y_los_momentos_cierran` exige M(L) = 0, pero todos sus casos tienen
    momento de columna nulo, de modo que nunca vio el término del par. Por ese hueco pasó
    un signo invertido que dejaba el extremo libre en −2·Σ Mᵢ. Aquí se exige el cierre en
    presencia de pares de los dos signos."""
    L = 8.0
    d = build_beam_diagram(L, 3.0, [_carga(n, x, P, M=M) for n, x, P, M in cargas])
    final = d.critical_points[-1]
    assert final.x_m == pytest.approx(L)
    assert final.V_kN == pytest.approx(0.0, abs=1e-8)
    assert final.M_kNm == pytest.approx(0.0, abs=1e-8), "El momento debe cerrar en el extremo"


def test_un_diagrama_que_no_cierra_se_rechaza_en_vez_de_devolverse():
    """El control vive en el MOTOR, no solo en los tests: cualquier entrada lo dispara.

    Se reintroduce el signo congelado del par y se comprueba que `build_beam_diagram` se
    niega a devolver un diagrama que viola el equilibrio. Es la guardia que faltaba: el
    único control existente era de fuerza, y un par mal signado no produce residuo de
    fuerza."""
    import engine.analysis.beam_diagram as bd

    original = bd._moment

    def signo_congelado(x, w0, w1, L, loads):
        m = w0 * x * x / 2.0 + (w1 - w0) * x**3 / (6.0 * L)
        for ld in loads:
            if ld.position_m <= x + bd.TOL_M:
                m -= ld.P_kN * (x - ld.position_m)
                m -= ld.M_kNm
        return m

    bd._moment = signo_congelado
    try:
        with pytest.raises(ArithmeticError, match="no cierra"):
            build_beam_diagram(8.0, 3.0, [_carga("C1", 4.0, 1000.0, M=500.0)])
    finally:
        bd._moment = original


@pytest.mark.parametrize(
    "nombre,factores,polinomio",
    [
        # Polinomios del tramo B-C que da el libro, con X medido desde el eje de C1.
        ("1,4CM + 1,7CV", (1.4, 1.7, 0.0),
         lambda X: 33.96 * X**2 - 146.02 * X + 14.77),
        ("1,25(CM + CV + CS)", (1.25, 1.25, 1.25),
         lambda X: 1.14 * X**3 + 17.15 * X**2 - 116.6 * X + 74.116),
        ("1,25(CM + CV − CS)", (1.25, 1.25, -1.25),
         lambda X: -49.34 - 129.67 * X + 40.23 * X**2 - 1.16 * X**3),
    ],
)
def test_aragon_3_5_el_diagrama_reproduce_los_polinomios_del_libro(nombre, factores, polinomio):
    """Contraste con el benchmark, en las tres combinaciones que trae el libro.

    Es la evidencia que destapó el defecto del signo: con el signo congelado el diagrama
    se desviaba 25–146 t·m del libro y llegaba a invertir el signo del momento.

    LA TOLERANCIA, Y DE DÓNDE SALE
    ==============================
    No es redondeo —la primera suposición, 1,5 t·m, fue insuficiente—: es MÉTODO. El libro
    arma la presión factorizada como 1,25 × la de servicio (A.1.c: 19,22 / 8,74 t/m²), que
    ya llevaba su propia excentricidad con el peso propio; el motor la saca directamente de
    las cargas factorizadas. El trapecio del libro resulta un 1,50 % más inclinado
    (49,78 frente a 49,04 t/m de rango; coeficiente cúbico −1,152 frente a −1,135), y como
    ese término crece con x³ la diferencia aumenta hacia C2: máximo MEDIDO 1,71 t·m, en
    x = 5,0 de `1,25(CM + CV − CS)`. La tolerancia de 2,0 t·m cubre esa diferencia de
    método con margen, y el defecto que este test vigila produce desvíos de 25 t·m o más.

    Aragón es benchmark y no autoridad (`CLAUDE.md` §1): lo que decide el signo es el cierre
    del equilibrio, y el libro solo lo confirma."""
    T = TONF_TO_KN
    fcm, fcv, fcs = factores
    cargas = [
        _carga("C1", 0.25, (fcm * 80 + fcv * 30 + fcs * -10) * T,
               M=(fcm * 6 + fcv * 2.5 + fcs * 50) * T),
        _carga("C2", 5.25, (fcm * 160 + fcv * 60 + fcs * 10) * T,
               M=(fcm * -2 + fcv * -0.5 + fcs * 70) * T),
    ]
    d = build_beam_diagram(7.20, 3.80, cargas)
    from engine.analysis.beam_diagram import _moment

    for x in (0.5, 1.5, 2.5, 3.5, 4.5, 5.0):
        motor = _moment(x, d.w_start_kNm, d.w_end_kNm, 7.20, d.loads) / T
        assert motor == pytest.approx(polinomio(x - 0.25), abs=2.0), (nombre, x)


def test_aragon_3_5_la_constante_del_libro_suma_el_par():
    """El libro, en `1,4CM + 1,7CV`, escribe `+14,77` en el eje de C1.

    Es `2,12 + 12,65`: la presión integrada hasta 0,25 m MÁS el par factorizado de C1,
    `1,4·6 + 1,7·2,5 = 12,65 t·m`. El libro suma el par, como el motor corregido. Con el
    signo congelado saldría `2,12 − 12,65 = −10,53`."""
    T = TONF_TO_KN
    d = build_beam_diagram(7.20, 3.80, [
        _carga("C1", 0.25, 163.0 * T, M=12.65 * T),
        _carga("C2", 5.25, 326.0 * T, M=-3.65 * T),
    ])
    from engine.analysis.beam_diagram import _moment

    en_el_eje = _moment(0.25, d.w_start_kNm, d.w_end_kNm, 7.20, d.loads) / T
    assert en_el_eje == pytest.approx(14.77, abs=0.05)


# =========================================================================
# 7. Errores de entrada
# =========================================================================

def test_una_columna_fuera_de_la_zapata_es_un_error():
    with pytest.raises(ValueError, match="fuera de la zapata"):
        build_beam_diagram(6.0, 3.0, [_carga("C1", 7.5, 1000.0)])


def test_sin_columnas_es_un_error():
    with pytest.raises(ValueError, match="al menos una carga"):
        build_beam_diagram(6.0, 3.0, [])


def test_carga_total_no_positiva_es_un_error():
    with pytest.raises(ValueError, match="positiva"):
        build_beam_diagram(6.0, 3.0, [_carga("C1", 3.0, 0.0)])
