"""Arnés para validar contra EJEMPLOS RESUELTOS DE BIBLIOGRAFÍA.

ESTADO: un caso cargado — ARAGÓN 3.4.1 (zapata aislada).

No se cargan casos de textos que no estén a la vista (Ottazzi, Blanco Blasco,
Harmsen, Morales Morales u otros): inventar valores de un ejemplo de libro sería
fabricar bibliografía, que es justamente lo que este proyecto no hace en ninguna
otra parte.

CÓMO AGREGAR UN CASO
====================
Basta con añadir un `BibliographicCase` a REFERENCE_CASES con los datos del libro.
`test_bibliographic_validation.py` lo ejecutará automáticamente y comparará cada
magnitud reportada, tolerando la diferencia que se declare en `tolerance`.

Datos mínimos que hace falta transcribir del ejemplo:

    ENTRADA
      - P y M de servicio, P y M factorizados (o los factores usados)
      - f'c, fy
      - dimensiones de columna
      - qadm y si es bruta o neta
      - peso unitario del suelo, Df
      - recubrimiento adoptado por el autor

    RESULTADOS DEL LIBRO (los que estén disponibles; el resto se deja en None)
      - B, L, h, d
      - qmax, qmin
      - Mu de diseño, As requerido en cada dirección
      - Vu y φVc de cortante unidireccional
      - Vu y φVc de punzonamiento
      - armado final (Ø y separación)

DISCREPANCIAS ESPERABLES Y LEGÍTIMAS
====================================
Un desajuste no implica error del motor. Antes de concluir nada hay que verificar
si el autor:
  - usó ACI 318 en vez de E.060 (coeficientes de punzonamiento y φ pueden diferir);
  - redondeó dimensiones a múltiplos comerciales;
  - adoptó `d` estimado en vez del real de la capa superior;
  - incluyó o excluyó el peso del relleno sobre la zapata;
  - aplicó el incremento del 30 % de §15.2 o la reducción sísmica del 80 %;
  - usó otra interpretación de §15.7.

Por eso cada caso lleva `author_assumptions`: sirve para documentar esas
diferencias y decidir si la comparación es válida.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BibliographicInputs(BaseModel):
    P_service_kN: float
    Mx_service_kNm: float = 0.0
    My_service_kNm: float = 0.0
    P_factored_kN: float
    Mx_factored_kNm: float = 0.0
    My_factored_kNm: float = 0.0

    fc_MPa: float
    fy_MPa: float
    column_bx_m: float
    column_by_m: float

    qadm_kPa: float
    pressure_basis: str = "BRUTA"
    gamma_soil_kNm3: float
    Df_m: float
    cover_mm: float = 70.0

    # Un libro suele resolver cada verificación con una combinación distinta
    # (p. ej. flexión con 1,25(CM+CV)+CS y punzonamiento con 1,4CM+1,7CV). El motor
    # también elige la gobernante por check de forma independiente, así que hay que
    # entregarle TODAS las combinaciones o la comparación no es del mismo problema.
    extra_service: list[tuple[float, float, float]] = Field(
        default_factory=list,
        description="Combinaciones de servicio adicionales: (P_kN, Mx_kNm, My_kNm)",
    )
    extra_factored: list[tuple[float, float, float]] = Field(
        default_factory=list,
        description="Combinaciones factorizadas adicionales: (P_kN, Mx_kNm, My_kNm)",
    )


class BibliographicResults(BaseModel):
    """Valores que el libro reporta. Los no disponibles quedan en None."""

    B_m: float | None = None
    L_m: float | None = None
    h_m: float | None = None
    d_m: float | None = None
    qmax_kPa: float | None = None
    qmin_kPa: float | None = None
    Mu_x_kNm: float | None = None
    Mu_y_kNm: float | None = None
    As_x_cm2: float | None = None
    As_y_cm2: float | None = None
    Vu_oneway_kN: float | None = None
    phiVc_oneway_kN: float | None = None
    Vu_punching_kN: float | None = None
    phiVc_punching_kN: float | None = None
    rebar_x: str | None = None
    rebar_y: str | None = None


class BibliographicCase(BaseModel):
    """Un ejemplo resuelto, con su fuente citada de forma verificable."""

    id: str
    source: str = Field(..., description="Autor, título, edición, página y número de ejemplo")
    author_assumptions: list[str] = Field(
        default_factory=list,
        description="Diferencias declaradas respecto del motor (norma usada, redondeos, etc.)",
    )
    inputs: BibliographicInputs
    expected: BibliographicResults
    tolerance: float = Field(
        default=0.05,
        description="Tolerancia relativa admitida. 0.05 = 5 %, razonable ante redondeos del autor.",
    )
    tolerance_overrides: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Tolerancia por magnitud, para no aflojar TODA la comparación por culpa de "
            "una diferencia metodológica acotada. Cada override debe justificarse en "
            "`author_assumptions`: una tolerancia holgada sin explicación es una "
            "discrepancia escondida."
        ),
    )
    notes: str = ""


# ============================================================================
# REGISTRO DE CASOS
# ============================================================================

TONF_TO_KN = 9.80665
KGF_CM2_TO_KPA = 98.0665
KGF_CM2_TO_MPA = 0.0980665

REFERENCE_CASES: list[BibliographicCase] = []

# ----------------------------------------------------------------------------
# ARAGÓN 3.4.1 — Zapata aislada con momento uniaxial de gravedad y sismo biaxial
# ----------------------------------------------------------------------------
# CONVENCIÓN DE MOMENTOS — LEER ANTES DE TOCAR ESTOS VALORES
# =========================================================
# El libro rotula "Mcmx = 8 ton-m" y luego titula la sección de diseño:
#
#     "A.- Diseño por flexión Dir. X (Momentos alrededor de Y)"
#
# Es decir, el "Mx" del libro es el momento que produce flexión EN la dirección X,
# que es el momento ALREDEDOR del eje Y. Es también la convención de E.050 art.
# 28.1 (ex = Mx/Q).
#
# Tras la migración de convención, el motor usa EXACTAMENTE esa misma convención
# (ex = Mx/P). Por lo tanto **ya no hace falta traducir nada**: el Mx del libro se
# carga como Mx del motor. Antes de la migración estos valores iban intercambiados.
#
# Verificación independiente del mapeo: Mu = 92,71 ton·m a la cara de la columna
# reproduce exactamente con c = 0,45 m y el momento actuando en la dirección X.
REFERENCE_CASES.append(
    BibliographicCase(
        id="ARAGON-3.4.1",
        source=(
            "Aragón Brousset, John P. «Concreto Armado 2», sección 3.4.1 "
            "«Problema de aplicación», diseño de zapata aislada."
        ),
        author_assumptions=[
            "CONVENCIÓN: coincide con la del motor desde la migración de ejes. El Mx del "
            "libro (que el propio libro define como momento ALREDEDOR DE Y en el título de "
            "su sección de diseño) es el Mx del motor. No se traduce nada.",
            "El libro adopta d = 50 cm plano para h = 60 cm. El motor calcula el d REAL de "
            "cada capa a partir del recubrimiento y del diámetro seleccionado, que es menor.",
            "El libro estima el peso propio como 10% de (CM+CV) y NO incluye el peso del "
            "relleno de suelo sobre la zapata. El motor sí lo incluye.",
            "En el cortante unidireccional el libro calcula Vc con h = 60 cm en vez de "
            "d = 50 cm: escribe Vc = 0,53·√210·340·50 pero reporta 156,7 ton, que "
            "corresponde a usar 60. Con d el valor correcto es 130,6 ton. MANDA LA NORMA.",
            "En punzonamiento el libro toma Vu = Pu completo (242 ton) sin descontar la "
            "reacción del suelo dentro del perímetro crítico. El motor sí la descuenta, "
            "de modo que su Vu es menor. El libro es conservador en este punto.",
            "El libro NO aplica §11.12.6 (transferencia de momento en punzonamiento). "
            "El motor sí. MANDA LA NORMA.",
            "Las fuerzas sísmicas del enunciado están en condición ÚLTIMA; para las "
            "combinaciones de servicio el libro las divide entre 1,25.",
        ],
        inputs=BibliographicInputs(
            # Cargas de COLUMNA (sin peso propio: el motor lo calcula).
            # Servicio gobernante en X: CM+CV+CS/1,25 -> P = 160 + 12, M = 13 + 52 = 65 ton·m
            P_service_kN=172.0 * TONF_TO_KN,
            My_service_kNm=0.0,
            Mx_service_kNm=65.0 * TONF_TO_KN,  # Mx del libro = Mx del motor
            # Factorizada gobernante en flexión X: 1,25(CM+CV)+CS
            P_factored_kN=215.0 * TONF_TO_KN,
            My_factored_kNm=50.0 * TONF_TO_KN,  # My del libro = My del motor
            Mx_factored_kNm=81.25 * TONF_TO_KN,  # Mx del libro = Mx del motor
            # El libro resuelve cada verificación con su propia combinación. Sin todas
            # ellas el motor no está resolviendo el mismo problema: el punzonamiento lo
            # gobierna 1,4CM+1,7CV, y la flexión 1,25(CM+CV)±CS.
            extra_factored=[
                # 1,4CM + 1,7CV  -> P = 242 t. Gobierna el punzonamiento (lo dice el libro).
                (242.0 * TONF_TO_KN, 19.7 * TONF_TO_KN, 0.0),
                # 1,25(CM+CV) - CS en X
                (185.0 * TONF_TO_KN, -48.75 * TONF_TO_KN, 0.0),
                # 1,25(CM+CV) ± CS en Y
                (210.0 * TONF_TO_KN, 0.0, 50.0 * TONF_TO_KN),
                (190.0 * TONF_TO_KN, 0.0, -50.0 * TONF_TO_KN),
            ],
            extra_service=[
                # CM+CV sin sismo
                (160.0 * TONF_TO_KN, 13.0 * TONF_TO_KN, 0.0),
                # CM+CV-CS/1,25 en X
                (148.0 * TONF_TO_KN, -39.0 * TONF_TO_KN, 0.0),
            ],
            fc_MPa=210.0 * KGF_CM2_TO_MPA,
            fy_MPa=4200.0 * KGF_CM2_TO_MPA,
            column_bx_m=0.45,
            column_by_m=0.45,
            qadm_kPa=2.2 * KGF_CM2_TO_KPA,
            pressure_basis="BRUTA",
            gamma_soil_kNm3=18.0,
            Df_m=1.00,
            cover_mm=70.0,
        ),
        expected=BibliographicResults(
            B_m=3.40, L_m=3.40, h_m=0.60,
            d_m=0.50,
            # Todas las magnitudes que el libro reporta se comparan. Ninguna se
            # omite: las que difieren por metodología llevan tolerancia propia y
            # justificada, no se esconden dejándolas en None.
            Mu_x_kNm=109.19 * TONF_TO_KN,   # dirección X del libro
            Mu_y_kNm=94.65 * TONF_TO_KN,    # dirección Y del libro
            As_x_cm2=60.0,
            As_y_cm2=51.7,
            Vu_oneway_kN=89.0 * TONF_TO_KN,
            Vu_punching_kN=242.0 * TONF_TO_KN,
            phiVc_punching_kN=248.1 * TONF_TO_KN,
        ),
        tolerance=0.05,
        tolerance_overrides={
            # Mu y As: el libro construye el diagrama de presiones incluyendo su peso
            # propio y toma momentos de la presión TOTAL. El peso propio de la zapata
            # está equilibrado por una reacción igual y opuesta justo debajo, así que
            # no produce flexión neta; el motor lo excluye. Diferencia medida: -7,1% en
            # Mu_X, -6,1% en Mu_Y, -8,2% en As_X. El motor es el correcto; el libro,
            # conservador.
            "Mu X (kN·m)": 0.09,
            "Mu Y (kN·m)": 0.09,
            "As X (cm²)": 0.10,
            "As Y (cm²)": 0.09,
            # Punzonamiento: el libro toma Vu = Pu completo sin descontar la reacción
            # del suelo encerrada por el perímetro crítico. Diferencia medida: -7,9%,
            # que se reproduce exactamente como 242·(1 - A_crit/(B·L)).
            "Vu punzonamiento (kN)": 0.09,
        },
        notes=(
            "Valores que reporta el libro y NO se comparan aquí por diferencia de "
            "metodología ya documentada en author_assumptions: "
            "Mu_X = 109,19 ton·m -> As = 60 cm² (13 Ø1\" @ 0,275); "
            "Mu_Y = 94,65 ton·m -> As = 51,7 cm² (11 Ø1\" @ 0,325); "
            "Vu cortante X = 89 ton, Y = 76,8 ton; "
            "punzonamiento Vu = 242 ton frente a φVc = 248,1 ton (margen 2,5%). "
            "Incluyendo §11.12.6, que el libro omite, el margen baja a 0,15%."
        ),
    )
)


# Ejemplo de cómo se vería un caso ya cargado (comentado: NO son datos reales,
# solo muestran la forma de la estructura):
#
# REFERENCE_CASES.append(
#     BibliographicCase(
#         id="OTTAZZI-EJ-12-3",
#         source="Ottazzi Pasino, G. «Apuntes del curso Concreto Armado I», PUCP, ejemplo 12.3, p. 4xx",
#         author_assumptions=[
#             "El autor usa d estimado = h - 10 cm, no el real de la capa superior.",
#             "No incluye el peso del relleno sobre la zapata.",
#         ],
#         inputs=BibliographicInputs(
#             P_service_kN=..., P_factored_kN=..., fc_MPa=..., fy_MPa=...,
#             column_bx_m=..., column_by_m=..., qadm_kPa=..., gamma_soil_kNm3=..., Df_m=...,
#         ),
#         expected=BibliographicResults(B_m=..., h_m=..., As_x_cm2=...),
#         tolerance=0.05,
#     )
# )
