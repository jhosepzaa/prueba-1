"""Casos representativos de zapata AISLADA cuyo resultado numérico queda congelado.

Estos casos definen el contrato de no regresión de la Fase 1A: mientras el motor
se generaliza para columna descentrada, zapata combinada y zapata conectada, el
resultado de una zapata aislada **no debe cambiar**.

Criterio de selección: cada caso ejerce un mecanismo distinto del motor, de modo
que un desplazamiento numérico en cualquier parte de la cadena de cálculo rompa
al menos un caso. La cobertura buscada es de mecanismos, no de geometrías.

CONVENCIÓN DE MOMENTOS: estos casos se escribieron con la convención antigua del
motor (Mx = momento alrededor del eje X). Al migrar a la convención de E.050 art.
28.1 (Mx = momento que desplaza la resultante a lo largo de X) los momentos se
INTERCAMBIARON, de forma que cada caso sigue describiendo EXACTAMENTE el mismo
problema físico y su línea base numérica sigue siendo válida. Ver el informe de
migración en docs/convenciones_ejes.md.

Las entradas de los casos 01 a 08 son deliberadamente las mismas de
`tests/golden_cases/`, para que ambos conjuntos hablen de las mismas zapatas: los
golden verifican valores calculados a mano, el congelamiento verifica que nada se
mueva. Los casos 09 a 12 cubren mecanismos que los golden no ejercen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile

COLUMN_40x40 = Column(shape="cuadrada", bx_m=0.40, by_m=0.40)
COLUMN_50x30 = Column(shape="rectangular", bx_m=0.50, by_m=0.30)
COLUMN_50x50 = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
CONCRETE_21 = MaterialConcrete(fc_MPa=21.0, unit_weight_kNm3=24.0)
STEEL_420 = MaterialSteel(fy_MPa=420.0, bar_type="corrugada")

_SOURCE = "Dato de entrada del caso de congelamiento -- no proviene de un EMS real."


def _soil(qadm_kPa: float, Df_m: float = 1.20, **kwargs: Any) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=qadm_kPa,
        pressure_basis=PressureBasis.BRUTA,
        gamma_kNm3=18.0,
        Df_m=Df_m,
        source_notes=_SOURCE,
        **kwargs,
    )


SOIL_150 = _soil(150.0)
SOIL_300 = _soil(300.0)
SOIL_500 = _soil(500.0)

DEPTH_PARAMS = DepthSearchParameters(h_min_m=0.30, h_max_m=0.80, h_step_m=0.05)


def _loads(
    P_serv: float,
    P_fact: float,
    Mx_serv: float = 0.0,
    My_serv: float = 0.0,
    Mx_fact: float = 0.0,
    My_fact: float = 0.0,
    Hx: float = 0.0,
    Hy: float = 0.0,
    seismic: bool = False,
) -> LoadCaseSet:
    return LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=P_serv,
                Mx_kNm=Mx_serv, My_kNm=My_serv, Hx_kN=Hx, Hy_kN=Hy,
                includes_seismic_loads=seismic,
            )
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P_fact,
                Mx_kNm=Mx_fact, My_kNm=My_fact, Hx_kN=Hx * 1.4, Hy_kN=Hy * 1.4,
                includes_seismic_loads=seismic,
            )
        ],
    )


@dataclass(frozen=True)
class FreezeCase:
    """Un caso congelado. `mechanism` documenta QUÉ protege, para que al romperse
    se sepa de inmediato qué parte del motor se movió."""

    name: str
    mechanism: str
    B_m: float
    L_m: float
    h_m: float
    column: Column
    soil: SoilProfile
    load_case_set: LoadCaseSet
    concrete: MaterialConcrete = field(default_factory=lambda: CONCRETE_21)
    steel: MaterialSteel = field(default_factory=lambda: STEEL_420)
    depth_params: DepthSearchParameters = field(default_factory=lambda: DEPTH_PARAMS)
    placement: ColumnPlacement | None = None
    extra: dict[str, Any] = field(default_factory=dict)


CASES: list[FreezeCase] = [
    FreezeCase(
        name="01_cuadrada_centrada",
        mechanism="Carga axial pura. As gobernado por cuantía mínima §9.7. Todo PASS.",
        B_m=2.0, L_m=2.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(P_serv=400.0, P_fact=560.0),
    ),
    FreezeCase(
        name="02_momento_uniaxial",
        mechanism="Excentricidad en un eje. Presión trapezoidal, voladizos desiguales en demanda.",
        B_m=2.4, L_m=2.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(P_serv=350.0, P_fact=560.0, My_serv=60.0, My_fact=90.0),
    ),
    FreezeCase(
        name="03_momento_biaxial",
        mechanism="Excentricidad biaxial. Suma de términos en núcleo central y en punzonamiento §11.12.6.",
        B_m=2.8, L_m=2.8, h_m=0.60,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(
            P_serv=500.0, P_fact=700.0,
            My_serv=80.0, Mx_serv=60.0, My_fact=112.0, Mx_fact=84.0,
        ),
    ),
    FreezeCase(
        name="04_limite_nucleo_central",
        mechanism="Excentricidad cercana al borde del kern. Protege KERN_TOLERANCE.",
        B_m=1.5, L_m=1.5, h_m=0.40,
        column=COLUMN_40x40, soil=SOIL_300,
        load_case_set=_loads(
            P_serv=1000.0, P_fact=1400.0,
            Mx_serv=1000.0 * 1.5 / 6.0, Mx_fact=1000.0 * 1.5 / 6.0 * 1.4,
        ),
    ),
    FreezeCase(
        name="05_falla_capacidad_portante",
        mechanism="qmax > qadm. Protege la rama de descarte por presión de contacto.",
        B_m=1.0, L_m=1.0, h_m=0.50,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(P_serv=400.0, P_fact=560.0),
    ),
    FreezeCase(
        name="06_falla_punzonamiento",
        mechanism="Punzonamiento gobernante. Protege bo, A_crit y las ec. 11-33/34/35.",
        B_m=1.6, L_m=1.6, h_m=0.40,
        column=COLUMN_40x40, soil=SOIL_500,
        load_case_set=_loads(P_serv=1150.0, P_fact=1700.0),
    ),
    FreezeCase(
        name="07_falla_flexion",
        mechanism="Peralte insuficiente para el momento. Protege el resolvedor de sección.",
        B_m=3.0, L_m=3.0, h_m=0.20,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(P_serv=2200.0, P_fact=3000.0),
    ),
    FreezeCase(
        name="08_falla_cortante_unidireccional",
        mechanism="Voladizo largo con h grande. Protege la sección crítica a d de la cara.",
        B_m=6.0, L_m=3.0, h_m=0.80,
        column=COLUMN_40x40, soil=SOIL_300,
        load_case_set=_loads(P_serv=4000.0, P_fact=6000.0),
    ),
    # --- Mecanismos que los casos golden no ejercen ---
    FreezeCase(
        name="09_rectangular_reparto_direccion_corta",
        mechanism=(
            "Zapata claramente rectangular con columna rectangular: ejerce γs de la ec. 15-1, "
            "el reparto en franjas de §15.4.4 y la elevación de franjas al mínimo de §9.7."
        ),
        B_m=3.60, L_m=2.00, h_m=0.55,
        column=COLUMN_50x30, soil=SOIL_150,
        load_case_set=_loads(P_serv=800.0, P_fact=1120.0, My_serv=40.0, My_fact=56.0),
    ),
    FreezeCase(
        name="10_fuerzas_horizontales",
        mechanism=(
            "Hx y Hy presentes: congela el estado de deslizamiento y volcamiento, y el "
            "registro de limitaciones asociado."
        ),
        B_m=2.60, L_m=2.60, h_m=0.60,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(
            P_serv=600.0, P_fact=840.0, My_serv=50.0, My_fact=70.0, Hx=45.0, Hy=30.0,
        ),
    ),
    FreezeCase(
        name="11_sismica_con_horizontales",
        mechanism=(
            "Combinación declarada sísmica con fuerzas horizontales: congela el trato de "
            "las hipótesis opcionales (incremento 30% y reducción 80%, ambas OFF por defecto)."
        ),
        B_m=2.80, L_m=2.80, h_m=0.65,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(
            P_serv=700.0, P_fact=980.0, Mx_serv=120.0, Mx_fact=168.0,
            Hx=60.0, seismic=True,
        ),
    ),
    FreezeCase(
        name="12_columna_rectangular_beta_alto",
        mechanism=(
            "β = bx/by alto: ejerce la ec. 11-33, que solo gobierna cuando la columna es "
            "marcadamente alargada."
        ),
        B_m=2.40, L_m=2.40, h_m=0.45,
        column=Column(shape="rectangular", bx_m=0.90, by_m=0.25),
        soil=SOIL_300,
        load_case_set=_loads(P_serv=900.0, P_fact=1260.0),
    ),
]


# --- Fase 1B: columna descentrada, perímetro cerrado ---
# Se congelan igual que los concéntricos: en cuanto la Fase 1C abra el perímetro
# truncado, estos casos deben seguir dando exactamente lo mismo, porque su holgura
# sigue siendo >= d/2 y les corresponde el modelo cerrado.
CASES += [
    FreezeCase(
        name="13_descentrada_un_eje",
        mechanism=(
            "Desplazamiento solo en X con holgura holgada: excentricidad geométrica sumada "
            "a la de carga, voladizos asimétricos, perímetro aún cerrado."
        ),
        B_m=3.20, L_m=3.20, h_m=0.65,
        column=COLUMN_50x50, soil=SOIL_300,
        load_case_set=_loads(P_serv=900.0, P_fact=1260.0, Mx_serv=140.0, Mx_fact=196.0),
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=0.45),
    ),
    FreezeCase(
        name="14_descentrada_dos_ejes",
        mechanism=(
            "Desplazamiento biaxial con momento biaxial: ejerce la suma de términos en el "
            "núcleo central, en §11.12.6 y en la descarga del suelo del punzonamiento."
        ),
        B_m=3.40, L_m=3.00, h_m=0.70,
        column=COLUMN_50x30, soil=SOIL_300,
        load_case_set=_loads(
            P_serv=850.0, P_fact=1190.0,
            Mx_serv=120.0, My_serv=70.0, Mx_fact=168.0, My_fact=98.0,
        ),
        placement=ColumnPlacement(column=COLUMN_50x30, offset_x_m=0.35, offset_y_m=-0.25),
    ),
    FreezeCase(
        name="15_descentrada_voladizo_largo_gobierna",
        mechanism=(
            "RIESGO R3: el voladizo largo cae del lado de MENOR presión y aun así gobierna. "
            "Congela la evaluación de ambos lados; con la lógica anterior Mu salía 11% menor."
        ),
        B_m=3.20, L_m=3.20, h_m=0.65,
        column=COLUMN_50x50, soil=SOIL_300,
        load_case_set=_loads(P_serv=900.0, P_fact=1260.0, Mx_serv=120.0, Mx_fact=168.0),
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=0.55),
    ),
]


# --- Fase 1C: perímetro crítico truncado ---
# Una zapata de 3,20 m con columna de 0,50 m: la cara de la columna queda sobre el
# borde con offset = ±1,35 m. Con h = 0,70 m, d/2 ronda 0,30 m, muy por encima de
# la holgura nula: la sección se trunca de verdad.
_OFF_BORDE = 1.35

CASES += [
    FreezeCase(
        name="16_columna_de_borde",
        mechanism=(
            "Cara de columna sobre el borde: sección crítica de 3 lados, alpha_s = 30, "
            "centroide desplazado y c_low != c_high."
        ),
        B_m=3.20, L_m=3.20, h_m=0.70,
        column=COLUMN_50x50, soil=SOIL_500,
        load_case_set=_loads(P_serv=700.0, P_fact=980.0),
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=_OFF_BORDE),
        # 2026-09-28, decisión del proyectista: gancho de 90° en las barras que corren
        # hacia el borde, como en las zapatas de lindero de la conectada. Con E.060
        # §15.6.2 una barra recta no se ancla en el ancho de una columna de 0,50 m.
        depth_params=DEPTH_PARAMS.model_copy(update={"hook_type_x": "90"}),
    ),
    FreezeCase(
        name="17_columna_de_esquina",
        mechanism=(
            "Dos caras sobre dos bordes: sección crítica de 2 lados, alpha_s = 20. "
            "Es el caso de menor resistencia al punzonamiento."
        ),
        B_m=3.20, L_m=3.20, h_m=0.70,
        column=COLUMN_50x50, soil=SOIL_500,
        load_case_set=_loads(P_serv=600.0, P_fact=840.0),
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=_OFF_BORDE, offset_y_m=-_OFF_BORDE),
        # 2026-09-28, decisión del proyectista: gancho de 90° en las barras que corren
        # hacia el borde, como en las zapatas de lindero de la conectada. Con E.060
        # §15.6.2 una barra recta no se ancla en el ancho de una columna de 0,50 m.
        depth_params=DEPTH_PARAMS.model_copy(update={"hook_type_x": "90", "hook_type_y": "90"}),
    ),
    FreezeCase(
        name="18_borde_con_momento",
        mechanism=(
            "El caso más exigente: sección truncada Y momento no balanceado. Ejerce "
            "§11.12.6 con Jc no simétrico y c = c_max, no b1/2."
        ),
        B_m=3.40, L_m=3.20, h_m=0.75,
        column=COLUMN_50x50, soil=SOIL_500,
        load_case_set=_loads(P_serv=650.0, P_fact=910.0, Mx_serv=130.0, Mx_fact=182.0),
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=1.45),
        # 2026-09-28, decisión del proyectista: gancho de 90° en las barras que corren
        # hacia el borde, como en las zapatas de lindero de la conectada. Con E.060
        # §15.6.2 una barra recta no se ancla en el ancho de una columna de 0,50 m.
        depth_params=DEPTH_PARAMS.model_copy(update={"hook_type_x": "90"}),
    ),
]


# Casos que se congelan a través del barrido completo `solve_depth`, no de una
# geometría fija: protegen la SELECCIÓN de h, que es una decisión del motor y no
# un cálculo aislado.
SWEEP_CASES: list[FreezeCase] = [
    FreezeCase(
        name="S1_barrido_axial",
        mechanism="solve_depth con carga axial: congela qué h resulta elegido y los h descartados.",
        B_m=2.20, L_m=2.20, h_m=0.0,  # h lo decide el solver
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(P_serv=500.0, P_fact=700.0),
    ),
    FreezeCase(
        name="S2_barrido_con_momento",
        mechanism="solve_depth con momento biaxial: congela la interacción entre h, d y §11.12.6.",
        B_m=3.00, L_m=2.60, h_m=0.0,
        column=COLUMN_40x40, soil=SOIL_150,
        load_case_set=_loads(
            P_serv=750.0, P_fact=1050.0,
            My_serv=90.0, Mx_serv=55.0, My_fact=126.0, Mx_fact=77.0,
        ),
    ),
]


# =========================================================================
# Fase 2: zapatas COMBINADAS
# =========================================================================
# Se congelan igual que las aisladas y por la misma razón: las fases siguientes
# —motor de vigas y zapata conectada— no deben moverles ni un número.

from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout  # noqa: E402
from engine.reinforcement.face_reinforcement import TopCoverDeclaration  # noqa: E402

TAPA_ENTERRADA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")


@dataclass(frozen=True)
class CombinedFreezeCase:
    name: str
    mechanism: str
    layout: CombinedFootingLayout
    h_m: float
    soil: SoilProfile
    top_cover: TopCoverDeclaration = field(default_factory=lambda: TAPA_ENTERRADA)
    concrete: MaterialConcrete = field(default_factory=lambda: CONCRETE_21)
    steel: MaterialSteel = field(default_factory=lambda: STEEL_420)


def _col_comb(label: str, x_desde_extremo: float, L_total: float, P: float, M: float = 0.0):
    return ColumnOnFooting(
        label=label,
        placement=ColumnPlacement(column=COLUMN_50x50, offset_x_m=x_desde_extremo - L_total / 2.0),
        loads=LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P, Mx_kNm=M)],
            factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                      P_kN=P * 1.4, Mx_kNm=M * 1.4)],
        ),
    )


COMBINED_CASES: list[CombinedFreezeCase] = [
    CombinedFreezeCase(
        name="K1_dos_columnas_simetricas",
        mechanism=(
            "Voladizos cortos: aparece momento negativo y con él el acero de CARA SUPERIOR, "
            "que es el concepto nuevo de la Fase 2."
        ),
        layout=CombinedFootingLayout(
            B_m=8.0, L_m=3.60,
            columns=[_col_comb("C1", 1.0, 8.0, 900.0), _col_comb("C2", 7.0, 8.0, 900.0)],
        ),
        h_m=0.80, soil=_soil(400.0, Df_m=1.50),
    ),
    CombinedFreezeCase(
        name="K2_columna_en_limite_de_propiedad",
        mechanism=(
            "Caso canónico: una columna al ras del borde. Ejerce la integración con la Fase 1C "
            "—sección crítica de 3 lados— dentro del solver de combinada."
        ),
        layout=CombinedFootingLayout(
            B_m=7.20, L_m=3.80,
            columns=[_col_comb("C1", 0.25, 7.20, 1080.0, 83.0),
                     _col_comb("C2", 5.25, 7.20, 2160.0, -24.5)],
        ),
        h_m=0.80, soil=_soil(300.0, Df_m=1.50),
    ),
    CombinedFreezeCase(
        name="K3_tres_columnas_desiguales",
        mechanism=(
            "Tres columnas con cargas distintas: dos tramos con momento negativo y el extremo "
            "de M desplazado del centro geométrico."
        ),
        layout=CombinedFootingLayout(
            B_m=12.0, L_m=3.20,
            columns=[_col_comb("C1", 1.0, 12.0, 700.0), _col_comb("C2", 6.0, 12.0, 1300.0),
                     _col_comb("C3", 11.0, 12.0, 800.0)],
        ),
        h_m=0.85, soil=_soil(400.0, Df_m=1.50),
    ),
    CombinedFreezeCase(
        name="K4_voladizos_largos_sin_momento_negativo",
        mechanism=(
            "Voladizos que anulan el momento negativo: la cara superior NO se diseña por "
            "flexión. Congela que esa rama siga sin producir acero."
        ),
        layout=CombinedFootingLayout(
            B_m=8.0, L_m=3.60,
            columns=[_col_comb("C1", 2.0, 8.0, 900.0), _col_comb("C2", 6.0, 8.0, 900.0)],
        ),
        h_m=0.80, soil=_soil(400.0, Df_m=1.50),
    ),
]


# =========================================================================
# Viga de conexión — Fase 3
# =========================================================================
#
# Cada caso ejerce una rama distinta del motor de vigas, de modo que un
# desplazamiento numérico en cualquier parte de la cadena rompa al menos uno. Lo
# que se busca cubrir:
#
#   V1  Sin fuerza axial: flexión y cortante puros. La rama base.
#   V2  E.030 art. 65.1 disparado por qadm: aparece la interacción P−M en los dos
#       sentidos.
#   V3  Disparado por perfil S3 en Zona 4, que es la OTRA condición del artículo.
#   V4  §21.12.3.3 con §21.4 (muros): anula la exención de §10.5.3.
#   V5  §21.12.3.3 con §21.5 (pórticos): otro ratio M+/M− y límites geométricos.
#   V6  Vu por encima de lo que admite la sección: congela que el FAIL siga siendo
#       FAIL y no se degrade a otra cosa.


@dataclass
class BeamFreezeCase:
    name: str
    mechanism: str
    b_m: float
    h_m: float
    d_m: float
    clear_span_m: float
    Mu_negative_kNm: float
    Mu_positive_kNm: float
    Vu_kN: float
    sum_Pu_kN: float
    fc_MPa: float = 21.0
    fy_MPa: float = 420.0
    longitudinal_db_mm: float = 25.4
    qadm_kPa: float | None = 200.0
    soil_profile: str | None = None
    seismic_zone: int | None = None
    part_of_lateral_force_system: bool = False
    lateral_system: str | None = None


BEAM_CASES: list[BeamFreezeCase] = [
    BeamFreezeCase(
        name="V1_flexion_y_cortante_sin_axial",
        mechanism=(
            "Rama base: qadm holgada y sin perfil declarado, de modo que E.030 art. 65.1 no "
            "se dispara y no hay diagrama de interacción."
        ),
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=300.0, Vu_kN=220.0, sum_Pu_kN=1240.0,
        qadm_kPa=200.0,
    ),
    BeamFreezeCase(
        name="V2_axial_disparado_por_qadm",
        mechanism=(
            "qadm = 80 kPa < 0,10 MPa dispara el artículo por su primera condición. Congela "
            "la interacción P−M evaluada en tracción Y en compresión."
        ),
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=1379.0, Mu_positive_kNm=300.0, Vu_kN=220.0, sum_Pu_kN=1240.0,
        qadm_kPa=80.0,
    ),
    BeamFreezeCase(
        name="V3_axial_disparado_por_perfil_y_zona",
        mechanism=(
            "S3 en Zona 4 con qadm holgada: la OTRA condición de disparo del artículo. Si "
            "alguien la rompiera, V2 seguiría pasando y este caso no."
        ),
        b_m=0.40, h_m=1.00, d_m=0.92, clear_span_m=6.00,
        Mu_negative_kNm=600.0, Mu_positive_kNm=250.0, Vu_kN=300.0, sum_Pu_kN=2000.0,
        qadm_kPa=250.0, soil_profile="S3", seismic_zone=4,
    ),
    BeamFreezeCase(
        name="V4_21_12_3_3_con_21_4_muros",
        mechanism=(
            "§21.2 remite a §21.4 para muros estructurales. §21.4.4.1 anula la exención de "
            "§10.5.3 y el acero mínimo sube; el ratio M+/M− en el nudo es 1/3."
        ),
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=500.0, Mu_positive_kNm=120.0, Vu_kN=250.0, sum_Pu_kN=1500.0,
        qadm_kPa=200.0, part_of_lateral_force_system=True,
        lateral_system="muros_estructurales",
    ),
    BeamFreezeCase(
        name="V5_21_12_3_3_con_21_5_porticos",
        mechanism=(
            "§21.2 remite a §21.5 para pórticos. Cambia el ratio a 1/2 y aparecen los "
            "límites geométricos de §21.5.1.3 y §21.5.1.4."
        ),
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=500.0, Mu_positive_kNm=120.0, Vu_kN=250.0, sum_Pu_kN=1500.0,
        qadm_kPa=200.0, part_of_lateral_force_system=True, lateral_system="porticos",
    ),
    BeamFreezeCase(
        name="V6_cortante_por_encima_de_la_seccion",
        mechanism=(
            "Vu que lleva Vs por encima de la cota de §11.5.7.9: ningún estribo lo corrige. "
            "Congela que el FAIL se mantenga y no se degrade a WARNING."
        ),
        b_m=0.30, h_m=0.60, d_m=0.52, clear_span_m=5.00,
        Mu_negative_kNm=200.0, Mu_positive_kNm=80.0, Vu_kN=900.0, sum_Pu_kN=1000.0,
        qadm_kPa=200.0,
    ),
]


# =========================================================================
# Fase 4F: cimentación CONECTADA
# =========================================================================
# La última tipología sin contrato de no regresión, y la más frágil: tres solvers
# acoplados, dos modelos de análisis, dos modos de reparto del par y una convención de
# momentos que ya produjo un defecto de signo detectado solo por auditoría manual.
#
# DOS FORMAS DE CASO, POR DECISIÓN EXPLÍCITA
# ==========================================
# `ConnectedFreezeCase`  — una TERNA fija resuelta por `solve_connected_footing`.
#                          Congela física: números, estados y traza. Es la mayoría.
#
# `ConnectedSweepCase`   — un MICRO-BARRIDO. Congela SOLO cuántas ternas se evaluaron,
#                          cuántas se aceptaron y por qué se rechazaron las demás. No
#                          congela orden ni ranking: esa es estrategia de búsqueda y
#                          puede mejorarse legítimamente sin que la ingeniería cambie.

from engine.domain.connected_layout import (  # noqa: E402
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectedElement,
    ConnectedFootingLayout,
    ConnectingBeamSpec,
    CoupleTransferMode,
    EdgeAnchor,
)
from engine.foundation.connected_solver import ConnectedFootingGeometry  # noqa: E402
from engine.optimization.connected_generator import (  # noqa: E402
    ConnectedSearchParameters,
)

# Factor del libro de Aragón: sus cargas están en toneladas fuerza.
TONF_TO_KN = 9.80665

CONNECTED_DEPTH_PARAMS = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)


def _soil_conn(qadm_kPa: float, Df_m: float = 1.50, **kwargs: Any) -> SoilProfile:
    """Suelo de los casos conectados. `FS_overturning_required` se declara por defecto.

    El caso `Z1b` lo deja sin declarar para fijar qué hace el motor cuando el proyectista
    no aporta el FS. Hasta la Fase 10B quedaba NO VERIFICADO por falta del dato; desde 10B
    rige el valor normativo (E.020 art. 21, o E.030 art. 64.2 con sismo) y la traza cita
    esa fuente en lugar de «declarado por el proyectista»."""
    base: dict[str, Any] = dict(FS_overturning_required=1.5)
    base.update(kwargs)
    return _soil(qadm_kPa, Df_m=Df_m, **base)


def _conn_loads(P_serv: float, P_fact: float, Mx_serv: float = 0.0, Mx_fact: float = 0.0):
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                 P_kN=P_serv, Mx_kNm=Mx_serv)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=P_fact, Mx_kNm=Mx_fact)],
    )


def _conn_layout(
    *,
    modelo: AnalysisModel,
    modo: CoupleTransferMode,
    P_ext: float,
    P_int: float,
    M_ext: float = 0.0,
    S: float = 6.0,
    clearance: float = 0.0,
    eje: str = "X",
    apoyo: BeamSupportMode = BeamSupportMode.SIN_APOYO,
    peso: BeamSelfWeightMode = BeamSelfWeightMode.DESPRECIADO,
    factor_u: float = 1.4,
    z_b: float | None = None,
) -> ConnectedFootingLayout:
    """Layout de un caso congelado. Los cuatro modos se declaran SIEMPRE y explícitos:
    el motor no admite valor por defecto, y un caso congelado tampoco debería."""
    borde = "X_MIN" if eje == "X" else "Y_MIN"
    return ConnectedFootingLayout(
        analysis_model=modelo,
        couple_transfer_mode=modo,
        exterior=ConnectedElement(
            label="Z1", column=COLUMN_50x50,
            loads=_conn_loads(P_ext, P_ext * factor_u, M_ext, M_ext * factor_u),
            anchor=EdgeAnchor(edge=borde, face_clearance_m=clearance),
            # 2026-09-28, decisión del proyectista: la zapata de lindero lleva gancho de
            # 90° en las barras que corren hacia el lindero. Con la regla corregida de
            # E.060 §15.6.2 una barra recta no se ancla en el ancho de una columna de
            # 0,50 m, y el caso dejaría de proteger su estática para congelar un FAIL
            # de anclaje. La interior sigue con barra recta.
            **({"hook_type_x": "90"} if eje == "X" else {"hook_type_y": "90"}),
        ),
        interior=ConnectedElement(
            label="Z2", column=COLUMN_50x50,
            loads=_conn_loads(P_int, P_int * factor_u),
        ),
        beam=ConnectingBeamSpec(
            b_m=0.35, h_m=1.20, d_m=1.10,
            support_mode=apoyo, self_weight_mode=peso, soffit_above_base_m=z_b,
        ),
        axis_distance_m=S, longitudinal_axis=eje,
    )


@dataclass(frozen=True)
class ConnectedFreezeCase:
    """Una terna fija de cimentación conectada.

    `benchmark` marca los casos que reproducen un problema de los apuntes CR2-93-134.
    Están aquí para que el congelamiento cubra TODO lo que el motor produce sobre esa
    geometría, no solo los pocos valores que el test de benchmark afirma. Los asserts
    numéricos del libro NO se repiten aquí: viven en `test_connected_statics_phase4a.py`
    y `test_aragon_p2_rigid_body.py`, y duplicarlos haría que un mismo fallo se
    reportara dos veces sin añadir información."""

    name: str
    mechanism: str
    geometry: ConnectedFootingGeometry
    soil: SoilProfile
    layout: ConnectedFootingLayout | None = None
    layout_factory: Callable[[], ConnectedFootingLayout] | None = None
    """Construcción DIFERIDA del layout. Existe para los casos cuyo layout el motor
    rechaza por validación (Fase 5A, Z4): construirlo al importar este módulo haría
    fallar la carga de TODOS los casos, y lo que se quiere congelar es precisamente
    el rechazo. El driver llama a `build_layout()` dentro del mismo `try` que captura
    las demás negativas del motor."""
    concrete: MaterialConcrete = field(default_factory=lambda: CONCRETE_21)
    steel: MaterialSteel = field(default_factory=lambda: STEEL_420)
    depth_params: DepthSearchParameters = field(
        default_factory=lambda: CONNECTED_DEPTH_PARAMS
    )
    expects_rejection: bool = False
    benchmark: str | None = None

    def __post_init__(self) -> None:
        if (self.layout is None) == (self.layout_factory is None):
            raise ValueError(
                f"El caso {self.name} debe declarar exactamente uno de `layout` o "
                f"`layout_factory`."
            )

    def build_layout(self) -> ConnectedFootingLayout:
        return self.layout if self.layout is not None else self.layout_factory()


@dataclass(frozen=True)
class ConnectedSweepCase:
    """Un micro-barrido. Ver el contrato estrecho en `snapshot_connected_sweep`."""

    name: str
    mechanism: str
    layout: ConnectedFootingLayout
    params: ConnectedSearchParameters
    soil: SoilProfile
    concrete: MaterialConcrete = field(default_factory=lambda: CONCRETE_21)
    steel: MaterialSteel = field(default_factory=lambda: STEEL_420)
    depth_params: DepthSearchParameters = field(
        default_factory=lambda: CONNECTED_DEPTH_PARAMS
    )


# Geometría de referencia de la matriz: la misma en los cuatro cruces de
# modelo × modo, para que lo único que cambie entre ellos sea la declaración.
GEO_REF = ConnectedFootingGeometry(
    exterior_B_m=2.00, exterior_L_m=2.40, exterior_h_m=0.90,
    interior_B_m=2.20, interior_L_m=2.20, interior_h_m=0.90,
)
SOIL_CONN_250 = _soil_conn(250.0)

CONNECTED_CASES: list[ConnectedFreezeCase] = [
    # --- Matriz modelo × modo de reparto del par -------------------------
    ConnectedFreezeCase(
        name="Z1_articulado_equilibrio",
        mechanism=(
            "Cruce de referencia. Cuerpo libre de la zapata de lindero con el par "
            "cerrado dentro de la cimentación. Congela el reparto articulado completo, "
            "la carga corregida de las dos zapatas y el diseño de la viga."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z1b_articulado_sin_FS_de_volcamiento",
        mechanism=(
            "El MISMO caso que Z1 sin declarar FS_overturning_required. Fija qué hace el "
            "motor cuando el FS requerido no está disponible: desde la Fase 10B aplica el "
            "valor de E.020 art. 21 (1,5) y lo cita como fuente, distinta de «declarado por "
            "el proyectista» en Z1. La falta del dato NO es un pendiente del motor: ninguna "
            "verificación de estabilidad lleva `open_tbd`, y TBD-C1 sigue igual en ambos."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
        ),
        geometry=GEO_REF,
        soil=_soil(250.0, Df_m=1.50),
    ),
    ConnectedFreezeCase(
        name="Z2_articulado_par_puro",
        mechanism=(
            "TBD-C11 activo. La rama cercana del par no se cierra en la cimentación: "
            "aparece un segundo pendiente abierto y la zapata interior queda más "
            "aliviada. Congela que `open_tbds` sean DOS y en qué orden."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
            P_ext=850.0, P_int=1100.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z3_cuerpo_rigido_equilibrio",
        mechanism=(
            "Campo de presión de la sección compuesta: área, centroide e inercia de las "
            "dos huellas como una sola sección. Es el modelo cuya premisa TBD-C1 no "
            "tiene criterio que verificar, y el que más superficie numérica tiene."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z4_cuerpo_rigido_par_puro",
        mechanism=(
            "Fase 5A, defecto D1: CUERPO_RIGIDO con PAR_PURO_EN_ZAPATA es una combinación "
            "INCOMPATIBLE y se rechaza por validación. El par puro exige R_ext = P_ext y "
            "que la carga no se conserve en la cimentación; el cuerpo rígido determina "
            "R_ext por equilibrio global y conserva la carga. Hasta 4F este caso se "
            "aceptaba y combinaba el campo rígido de las zapatas con una viga de par "
            "puro articulado. Congela que la combinación siga rechazándose, y que se "
            "rechace como ENTRADA_INVALIDA —un error de declaración— y no como otra cosa."
        ),
        # Diferido: el layout no se puede construir, y ese es el resultado a congelar.
        layout_factory=lambda: _conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
            P_ext=850.0, P_int=1100.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
        expects_rejection=True,
    ),

    # --- Variantes geométricas -------------------------------------------
    ConnectedFreezeCase(
        name="Z5_eje_longitudinal_Y",
        mechanism=(
            "El mismo sistema girado 90 grados. Congela que el eje longitudinal se "
            "propague a las dos huellas, al vano de la viga y a la longitud del "
            "sistema: tomar siempre la dimensión en X fue un defecto real de 4D. "
            "LAS DOS ZAPATAS SON RECTANGULARES A PROPÓSITO: con la interior cuadrada, "
            "intercambiar B y L no cambia nada y el caso no detectaría el defecto que "
            "existe para protegerse. Comprobado por mutación."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, eje="Y",
        ),
        geometry=ConnectedFootingGeometry(
            exterior_B_m=2.40, exterior_L_m=2.00, exterior_h_m=0.90,
            interior_B_m=2.60, interior_L_m=2.20, interior_h_m=0.90,
        ),
        soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z6_holgura_al_lindero_no_nula",
        mechanism=(
            "`face_clearance_m` = 0,15 m. Lo invariante durante el barrido es la holgura "
            "de la CARA al borde, no el desplazamiento respecto del centro: este caso "
            "congela que la condición de lindero sobreviva con holgura, no solo al ras."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, clearance=0.15,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    # `Z7_viga_apoya_en_suelo` se RETIRÓ el 2026-09-20 (decisión 5 sobre TBD-C4).
    #
    # Congelaba que declarar `APOYA_EN_SUELO` emitiera el pendiente y no ascendiera de
    # estado. Desde esa decisión el valor se rechaza por VALIDACIÓN, de modo que el caso
    # ya no se puede ni construir: el layout lanza `ValueError` al instanciarse.
    #
    # No es una pérdida de cobertura. Lo que Z7 protegía —que esa configuración no
    # produzca un diseño— lo protege ahora, y de forma más estricta, el rechazo en sí:
    # `tests/test_decisiones_conectada_2026_09_20.py` comprueba que se rechaza en el
    # layout y también en el solver, que es la puerta trasera de `model_copy`.
    ConnectedFreezeCase(
        name="Z8_peso_propio_de_viga_explicito",
        mechanism=(
            "TBD-C5 en su única variante que entra en el equilibrio. Congela que el peso "
            "de la viga aparezca UNA vez y no dos: el doble conteo fue un defecto real "
            "que la auditoría de Fase 4 persiguió. Desde la Fase 9a, por geometría física "
            "con la cota HV-1 (fondo de la viga en la base común, z_b = 0): ΔW_e, W_V y "
            "ΔW_i, y el relleno sobre el vano declarado como pendiente."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
            peso=BeamSelfWeightMode.EXPLICITO, z_b=0.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z15_par_puro_con_peso_propio_de_viga_explicito",
        mechanism=(
            "Fase 9c, formulación B*: con PAR_PURO_EN_ZAPATA la rama que va al pórtico es "
            "EXCLUSIVAMENTE la del par, y el peso de la viga llega a las zapatas por sus "
            "reacciones —N_a en el nudo exterior, el resto en la rótula—. Hasta 9c el peso "
            "se perdía entero y la terna se rechazaba por «no cuadra en carga vertical». "
            "Misma cota que Z8 (HV-1)."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
            P_ext=850.0, P_int=1100.0,
            peso=BeamSelfWeightMode.EXPLICITO, z_b=0.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),

    # --- Convención de momentos E.050 art. 28.1 --------------------------
    #
    # Los ocho casos anteriores llevan momento de columna NULO, de modo que ninguno
    # ejerce la conversión de convención. Y esa conversión es justamente donde vivió el
    # defecto más grave de toda la Fase 4 (D4): el mismo Mx AUMENTABA la reacción de la
    # zapata de lindero en el modelo articulado y la DISMINUÍA en el de cuerpo rígido.
    # Se comprobó invirtiendo el signo a mano: sin estos dos casos, solo el benchmark de
    # Aragón lo detectaba, y por accidente.
    ConnectedFreezeCase(
        name="Z13_articulado_con_momento_de_columna",
        mechanism=(
            "E.050 art. 28.1: un Mx positivo desplaza la resultante hacia +x. La "
            "conversión a la convención del cuerpo libre es la que produjo el defecto D4. "
            "Congela el reparto articulado CON momento, no solo con carga axial."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, M_ext=300.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),
    ConnectedFreezeCase(
        name="Z14_cuerpo_rigido_con_momento_de_columna",
        mechanism=(
            "El MISMO momento en el otro modelo. La resolución de D4 fue que los dos "
            "modelos deben mover la reacción de lindero en la misma dirección física: un "
            "momento hacia el interior descarga el borde. Congela las dos mitades de esa "
            "resolución, que es lo que impide que una corrección de signo se reintroduzca "
            "en un solo camino."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, M_ext=300.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
    ),

    # --- Negativas del motor ---------------------------------------------
    ConnectedFreezeCase(
        name="Z9_despegue_rechaza_la_terna",
        mechanism=(
            "Momento grande en cuerpo rígido: el campo lineal da presión negativa y el "
            "motor SE NIEGA a resolver (TBD-C12, contacto unilateral no implementado). "
            "Congela la negativa y su motivo: que esta terna dejara de rechazarse sería "
            "un cambio de criterio, no una mejora."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, M_ext=9000.0,
        ),
        geometry=GEO_REF, soil=SOIL_CONN_250,
        expects_rejection=True,
    ),
    ConnectedFreezeCase(
        name="Z10_geometria_imposible_huellas_solapadas",
        mechanism=(
            "Ejes a 2,20 m con zapatas de 3,20 m: las huellas se solapan. El área y la "
            "inercia saldrían POR EXCESO y la presión por defecto —no conservador—, así "
            "que se corta en la geometría. Congela que se siga cortando ahí."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, S=2.20,
        ),
        geometry=ConnectedFootingGeometry(
            exterior_B_m=3.20, exterior_L_m=2.40, exterior_h_m=0.80,
            interior_B_m=3.20, interior_L_m=2.40, interior_h_m=0.80,
        ),
        soil=SOIL_CONN_250,
        expects_rejection=True,
    ),

    # --- Benchmarks de los apuntes CR2-93-134 ----------------------------
    #
    # Se resuelven con el juego COMPLETO de verificaciones de E.060 y E.050, que el
    # libro no aplica: ambos acaban en FAIL por punzonamiento y eso es lo esperado.
    # El libro resuelve la estática y las presiones, no el diseño íntegro. Sus valores
    # están afirmados en los tests de benchmark; aquí solo se congela la salida entera.
    ConnectedFreezeCase(
        name="Z11_aragon_p1_articulado",
        mechanism=(
            "Apuntes CR2-93-134 §3.6 problema 1, geometría y cargas del libro, con el "
            "modo PAR_PURO_EN_ZAPATA que reproduce su procedimiento. Df se eleva a 0,80 m "
            "por E.050 art. 26.2: el libro no aplica ese mínimo y calcula el peso propio "
            "sin relleno, de modo que su presión queda justo en el límite y aquí lo pasa."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
            P_ext=85.0 * TONF_TO_KN, P_int=170.0 * TONF_TO_KN,
            M_ext=5.5 * TONF_TO_KN, S=6.00,
        ),
        geometry=ConnectedFootingGeometry(
            exterior_B_m=1.40, exterior_L_m=3.70, exterior_h_m=0.60,
            interior_B_m=3.20, interior_L_m=3.20, interior_h_m=0.60,
        ),
        soil=_soil_conn(18.0 * TONF_TO_KN, Df_m=0.80),
        benchmark="CR2-93-134 §3.6 problema 1 (asserts en test_connected_statics_phase4a.py)",
    ),
    ConnectedFreezeCase(
        name="Z12_aragon_p2_cuerpo_rigido",
        mechanism=(
            "Apuntes CR2-93-134 §3.6 problema 2, geometría final del libro y el modelo "
            "de cuerpo rígido que el propio enunciado declara. Congela el campo de "
            "presión de la sección compuesta sobre una geometría real, no inventada."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=95.0 * TONF_TO_KN, P_int=180.0 * TONF_TO_KN,
            M_ext=6.0 * TONF_TO_KN, S=6.50, clearance=0.15,
        ),
        geometry=ConnectedFootingGeometry(
            exterior_B_m=2.30, exterior_L_m=4.50, exterior_h_m=0.60,
            interior_B_m=6.70, interior_L_m=3.30, interior_h_m=0.60,
        ),
        soil=_soil_conn(17.5 * TONF_TO_KN, Df_m=0.80),
        benchmark="CR2-93-134 §3.6 problema 2 (asserts en test_aragon_p2_rigid_body.py)",
    ),
]


def _micro_params(**kw: Any) -> ConnectedSearchParameters:
    """Rango deliberadamente minúsculo. El presupuesto del congelamiento entero es de
    5 s: un barrido amplio lo consumiría solo, y no añadiría cobertura —lo que se
    congela son tres recuentos, no el óptimo—."""
    base = dict(
        ext_long_min_m=2.0, ext_long_max_m=2.4, ext_long_step_m=0.4,
        ext_transv_min_m=2.4, ext_transv_max_m=2.8, ext_transv_step_m=0.4,
        int_long_min_m=2.2, int_long_max_m=2.6, int_long_step_m=0.4,
        int_transv_min_m=2.2, int_transv_max_m=2.2, int_transv_step_m=0.4,
        h_min_m=0.60, h_max_m=1.00, h_step_m=0.20,
        same_depth_both_footings=True,
        max_systems=200,
    )
    base.update(kw)
    return ConnectedSearchParameters(**base)


CONNECTED_SWEEP_CASES: list[ConnectedSweepCase] = [
    ConnectedSweepCase(
        name="ZB1_micro_barrido_peralte_compartido",
        mechanism=(
            "Espacio de búsqueda con las dos zapatas al mismo peralte. Congela cuántas "
            "ternas hay, cuántas sobreviven y por qué caen las demás: los tres números "
            "que describen el espacio y la física que lo filtra."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
        ),
        params=_micro_params(),
        soil=SOIL_CONN_250,
    ),
    ConnectedSweepCase(
        name="ZB2_micro_barrido_peraltes_independientes",
        mechanism=(
            "El MISMO rango con peraltes independientes. El espacio crece de n a n² "
            "parejas: congela que `same_depth_both_footings` siga siendo una restricción "
            "real del usuario y no un adorno sin efecto."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.ARTICULADO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0,
        ),
        params=_micro_params(same_depth_both_footings=False),
        soil=SOIL_CONN_250,
    ),
    ConnectedSweepCase(
        name="ZB3_micro_barrido_con_despegue",
        mechanism=(
            "Momento que levanta el apoyo en todo el rango. Congela la decisión de 4D: "
            "el despegue RECHAZA el candidato y la búsqueda continúa hasta agotar el "
            "espacio. Si volviera a propagarse como excepción, `evaluated_count` caería."
        ),
        layout=_conn_layout(
            modelo=AnalysisModel.CUERPO_RIGIDO,
            modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            P_ext=850.0, P_int=1100.0, M_ext=9000.0,
        ),
        params=_micro_params(),
        soil=SOIL_CONN_250,
    ),
]
