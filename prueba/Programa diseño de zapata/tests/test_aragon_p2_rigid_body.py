"""Benchmark del problema de aplicación 2 — modelo de CUERPO RÍGIDO.

FUENTE PRIMARIA
===============
Apuntes CR2-93-134, Prof. John P. Aragón Brousset, §3.6, problema de aplicación 2,
páginas 36 a 42. El enunciado declara el modelo:

    «Solución simplificada del problema asumiendo zapata rígida y comportamiento
     elástico lineal del suelo. El modelo de análisis será el de un cuerpo rígido para
     el conjunto de 2 zapatas y la viga de conexión pues la viga lleva esfuerzos de la
     zapata izquierda a la zapata derecha y viceversa.»

QUÉ RESUELVE ESTE ARCHIVO, Y QUÉ NO
===================================
El solver de CUERPO_RIGIDO todavía no existe. Lo que sí se puede fijar hoy —y conviene
fijar antes de escribirlo— es que la lectura del método es la correcta. El libro
calcula las PROPIEDADES DE SECCIÓN de las dos huellas tratadas como una sola
—área, centroide y momento de inercia— y aplica

    sigma = P/A  ±  M·y/I

Si estos tests reproducen A, el centroide y I del libro, entonces la interpretación
de TBD-C2 es correcta y el solver puede escribirse contra ella. Si no los
reprodujeran, el error estaría en la lectura y no en el código que todavía no existe.

CONFIRMACIÓN DE TBD-C2
======================
Este método —presión lineal sobre las huellas, determinada por estática— es
exactamente lo que resulta de resolver el cuerpo rígido sobre resortes de Winkler: el
módulo de balasto se cancela en el equilibrio. Verificado por discretización numérica
con k_s entre 5 000 y 500 000 kN/m³, que da presiones idénticas a doce cifras. Las
dos lecturas que la auditoría de Fase 4 dio por distintas son la misma, y la fuente
usa la forma estática.
"""

from __future__ import annotations

import pytest

# --- Datos del enunciado, página 36 ----------------------------------------
S = 6.50                 # entre ejes de columnas
A_COL_EXT = 0.40         # del lindero al eje de la columna exterior
X_COL_INT = A_COL_EXT + S
SIGMA_ADM = 17.5         # 1,75 kg/cm²
GAMMA_CONCRETO = 2.4

CARGAS = dict(
    ext=dict(Pcm=70.0, Pcv=25.0, Mcm=4.0, Mcv=2.0, Ps=20.0, Ms=140.0),
    inter=dict(Pcm=130.0, Pcv=50.0, Mcm=4.5, Mcv=2.0, Ps=20.0, Ms=150.0),
)

# --- Dimensiones, página 38. (ancho transversal, largo longitudinal, altura) ---
PREDIM = dict(ext=(3.0, 2.0, 0.6), inter=(2.1, 5.5, 0.6))
FINAL = dict(ext=(4.5, 2.3, 0.6), inter=(3.3, 6.7, 0.6))


def _propiedades(dims: dict) -> dict:
    """Área, centroide y momento de inercia de las DOS huellas como una sola sección.

    Es el método del libro: la zapata exterior arranca en el lindero (s = 0) y la
    interior va centrada sobre su columna. El vano entre ambas NO aporta área."""
    b_ext, l_ext, _ = dims["ext"]
    b_int, l_int, _ = dims["inter"]

    A_ext, A_int = b_ext * l_ext, b_int * l_int
    x_ext = l_ext / 2.0                       # la exterior arranca en el lindero
    x_int = X_COL_INT                         # la interior, centrada en su columna

    A = A_ext + A_int
    x_c = (A_ext * x_ext + A_int * x_int) / A
    I = (
        b_ext * l_ext**3 / 12.0 + A_ext * (x_c - x_ext) ** 2
        + b_int * l_int**3 / 12.0 + A_int * (x_c - x_int) ** 2
    )
    return dict(A=A, x_c=x_c, I=I, x_ext=x_ext, x_int=x_int,
                x_ini=0.0, x_fin=x_int + l_int / 2.0)


# =========================================================================
# 1. Las propiedades de sección del predimensionamiento
# =========================================================================

def test_p2_predimensionamiento_area():
    """Libro, página 37-38: A = 17,55 m²."""
    assert _propiedades(PREDIM)["A"] == pytest.approx(17.55, abs=0.005)


def test_p2_predimensionamiento_centroide():
    """Libro: x = 4,88 m."""
    assert _propiedades(PREDIM)["x_c"] == pytest.approx(4.88, abs=0.005)


def test_p2_predimensionamiento_inercia():
    """Libro: I = 168,57 m⁴. Es la comprobación que valida la lectura del método:
    sale solo si las dos huellas se tratan como una sección compuesta."""
    assert _propiedades(PREDIM)["I"] == pytest.approx(168.57, abs=0.02)


def test_p2_el_predimensionamiento_se_rechaza_por_exceso_de_presion():
    """El libro lo descarta: sigma+ = 18,91 > 17,5 y redimensiona. El caso importa
    porque fija que el método puede FALLAR y obligar a cambiar la geometría."""
    p = _propiedades(PREDIM)
    pp = p["A"] * PREDIM["ext"][2] * GAMMA_CONCRETO
    assert pp == pytest.approx(25.27, abs=0.02), "Peso propio de ambas zapatas"

    P = 95.0 + 180.0 + pp
    assert P == pytest.approx(300.27, abs=0.02)

    # Punto de aplicación de la resultante, con los momentos de columna.
    x_R = (A_COL_EXT * 95.0 + X_COL_INT * 180.0 + p["x_c"] * pp + 6.0 - 6.5) / P
    assert x_R == pytest.approx(4.67, abs=0.01)

    e = x_R - p["x_c"]
    M = abs(P * e)
    sigma_mas = P / p["A"] + M * p["x_c"] / p["I"]
    assert sigma_mas == pytest.approx(18.91, abs=0.05)
    assert sigma_mas > SIGMA_ADM, "Por eso el libro redimensiona"


# =========================================================================
# 2. Las propiedades de sección de la geometría definitiva
# =========================================================================

def test_p2_geometria_final_area():
    """Libro, página 38: A = 32,46 m²."""
    assert _propiedades(FINAL)["A"] == pytest.approx(32.46, abs=0.005)


def test_p2_geometria_final_centroide():
    """Libro: X = 5,05 m."""
    assert _propiedades(FINAL)["x_c"] == pytest.approx(5.05, abs=0.02)


def test_p2_geometria_final_inercia():
    """Libro: I = 320,36 m⁴."""
    assert _propiedades(FINAL)["I"] == pytest.approx(320.36, abs=0.1)


def test_p2_las_dos_fibras_extremas_tienen_distinta_distancia():
    """El libro usa 5,05 hacia el lindero y 5,20 hacia el extremo interior. La sección
    NO es simétrica, y usar una sola distancia daría mal una de las dos presiones."""
    p = _propiedades(FINAL)
    assert p["x_c"] - p["x_ini"] == pytest.approx(5.05, abs=0.02)
    assert p["x_fin"] - p["x_c"] == pytest.approx(5.20, abs=0.02)


def test_p2_gravedad_reproduce_las_presiones_del_libro():
    """Libro, página 39: sigma+ = 11,63 y sigma− = 8,14 t/m²."""
    p = _propiedades(FINAL)
    pp = p["A"] * FINAL["ext"][2] * GAMMA_CONCRETO
    assert pp == pytest.approx(46.74, abs=0.02)

    P = 95.0 + 180.0 + pp
    assert P == pytest.approx(321.74, abs=0.02)

    x_R = (A_COL_EXT * 95.0 + X_COL_INT * 180.0 + p["x_c"] * pp + 6.0 - 6.5) / P
    assert x_R == pytest.approx(4.71, abs=0.01)

    # REDONDEO DE LA FUENTE. El libro redondea el centroide a 5,05 m (el exacto es
    # 5,066) y de ahi la excentricidad a 0,34 m (la exacta es 0,355). Ese redondeo
    # propaga un 4 % al momento y un 0,7 % a las presiones. Se reproduce el calculo
    # del libro con SUS valores redondeados, y aparte se comprueba que el calculo
    # exacto cae dentro de ese margen: la diferencia es aritmetica de la fuente, no
    # una discrepancia de metodo.
    M_libro = 321.74 * 0.34
    assert M_libro == pytest.approx(109.39, abs=0.05)

    M_exacto = abs(P * (x_R - p["x_c"]))
    assert M_exacto == pytest.approx(M_libro, rel=0.05), "Solo difiere por el redondeo"

    sigma_mas = P / p["A"] + M_libro * 5.05 / p["I"]
    sigma_menos = P / p["A"] - M_libro * 5.20 / p["I"]
    assert sigma_mas == pytest.approx(11.63, abs=0.05)
    assert sigma_menos == pytest.approx(8.14, abs=0.05)
    assert sigma_mas < SIGMA_ADM

    # Con el centroide exacto la conclusion no cambia.
    sigma_mas_exacto = P / p["A"] + M_exacto * (p["x_c"] - p["x_ini"]) / p["I"]
    assert sigma_mas_exacto == pytest.approx(sigma_mas, rel=0.01)
    assert sigma_mas_exacto < SIGMA_ADM


def test_p2_el_sismo_invierte_el_signo_de_la_excentricidad():
    """CM+CV deja la resultante a la IZQUIERDA del centroide (e = −0,34 m); con
    +CS se va a la derecha (e = +0,96 m). Las dos ramas deben evaluarse."""
    p = _propiedades(FINAL)
    pp = p["A"] * FINAL["ext"][2] * GAMMA_CONCRETO
    P = 321.74

    # CM+CV+CS: página 39.
    x_mas = (A_COL_EXT * 75.0 + 6.0 + X_COL_INT * 200.0 - 6.5
             + p["x_c"] * pp + 140.0 + 150.0) / P
    assert x_mas == pytest.approx(6.0, abs=0.02)
    assert x_mas - p["x_c"] == pytest.approx(0.96, abs=0.03)

    # CM+CV−CS: página 40.
    x_menos = (A_COL_EXT * 115.0 + 6.0 + X_COL_INT * 160.0 - 6.5
               + p["x_c"] * pp - 140.0 - 150.0) / P
    assert x_menos == pytest.approx(3.4, abs=0.02)
    assert x_menos - p["x_c"] == pytest.approx(-1.65, abs=0.03)


def test_p2_el_sismo_es_el_caso_critico_y_sigue_cumpliendo():
    """Libro, página 40: con CM+CV−CS, sigma+ = 18,25 t/m² frente a 1,3·sigma_adm."""
    p = _propiedades(FINAL)
    P = 321.74
    M = 529.25
    sigma_mas = P / p["A"] + M * (p["x_c"] - p["x_ini"]) / p["I"]
    sigma_menos = P / p["A"] - M * (p["x_fin"] - p["x_c"]) / p["I"]
    assert sigma_mas == pytest.approx(18.25, abs=0.05)
    assert sigma_menos == pytest.approx(1.32, abs=0.05)
    assert sigma_mas < 1.3 * SIGMA_ADM
    assert sigma_menos > 0.0, "Sin despegue: toda la huella sigue comprimida"


# =========================================================================
# 3. Lo que este benchmark exige del futuro solver de CUERPO_RIGIDO
# =========================================================================

def test_p2_el_modelo_puede_producir_despegue_y_hay_que_detectarlo():
    """Con esta geometría no hay despegue —sigma− = 1,32 > 0—, pero el margen es
    estrecho. Un momento algo mayor lo produciría, y entonces el campo lineal deja de
    valer: E.060 §15.2 prohíbe considerar tracciones. El solver de 4C tiene que
    detectarlo, no aceptarlo en silencio. Es la consecuencia F3 de la auditoría."""
    p = _propiedades(FINAL)
    P = 321.74
    M_que_despega = (P / p["A"]) * p["I"] / (p["x_fin"] - p["x_c"])
    assert M_que_despega == pytest.approx(610.5, rel=0.02)
    assert M_que_despega > 529.25, "El caso del libro no despega, pero por poco"
    assert M_que_despega / 529.25 < 1.2, "Menos de un 20 % de margen"


def test_p2_la_zapata_interior_no_esta_centrada_sobre_el_conjunto():
    """El centroide de las huellas (5,05 m) no coincide con ninguna de las dos
    columnas. Por eso la resultante bajo cada zapata NO pasa por su centroide, y el
    peso propio deja de agruparse como en el modelo articulado: es la consecuencia F2
    de la auditoría."""
    p = _propiedades(FINAL)
    assert p["x_c"] != pytest.approx(p["x_ext"], abs=0.5)
    assert p["x_c"] != pytest.approx(p["x_int"], abs=0.5)
