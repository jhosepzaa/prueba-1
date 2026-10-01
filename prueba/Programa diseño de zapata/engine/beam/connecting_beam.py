"""Viga de conexión entre zapatas — Fase 3.

Una viga de cimentación tiene exigencias que una viga corriente no: dimensión
transversal mínima, estribos cerrados con separación acotada, y —cuando se dispara
la condición sísmica— una fuerza axial que la convierte en elemento de
flexo-tracción o flexo-compresión.

TEXTO NORMATIVO
===============
E.060 §21.12.3.1
  "Las vigas diseñadas para actuar como acoples horizontales entre las zapatas o
   cabezales de pilotes deben tener refuerzo longitudinal CONTINUO, el cual debe
   desarrollarse dentro o más allá de la columna, o anclarse dentro de la zapata o
   del cabezal del pilote en todas las discontinuidades."

E.060 §21.12.3.2
  "[...] deben diseñarse de tal manera que la MENOR DIMENSIÓN TRANSVERSAL sea igual
   o mayor que el espacio libre entre columnas conectadas DIVIDIDO POR 20, pero no
   necesita ser mayor a 450 mm. Se deben proporcionar ESTRIBOS CERRADOS con un
   espaciamiento que no exceda al menor de: la menor dimensión de la sección
   transversal, 300 mm ni de 16 db."

  El tope es 450 mm en la E.060 designada por el proyecto (propuesta 2019); la
  edición anterior decía 400 mm. Esta transcripción llegó a decir 400 y se corrigió
  en la auditoría de citas del 2026-09-19. El código SIEMPRE usó 450
  (`MIN_DIMENSION_CAP_M`), de modo que ningún resultado estuvo afectado: lo que
  estaba mal era la transcripción que el lector creería.

E.060 §21.12.3.3
  "Las vigas de cimentación que estén sometidas a flexión por las columnas que son
   parte del sistema resistente a fuerzas laterales deben adecuarse a lo indicado
   en 21.4 ó 21.5 de acuerdo al sistema resistente a fuerzas laterales empleado."

E.030 art. 65.1
  "Para zapatas aisladas con o sin pilotes en suelos tipo S3 y S4, para las Zonas 3
   y 4, y en general para suelos con una presión admisible menor que 0,10 MPa, se
   provee elementos de conexión en ambas direcciones, los que se diseñan EN TRACCIÓN
   O COMPRESIÓN, para una fuerza horizontal mínima equivalente al 10% DE LAS CARGAS
   VERTICALES AMPLIFICADAS que soporta la zapata, adicionalmente a las solicitaciones
   por flexión que pudieran existir."

LO QUE ESTO IMPLICA
===================
Cuando la condición de E.030 art. 65.1 se dispara, la viga DEJA DE SER un elemento
a flexión pura. Hay que diseñarla a flexo-tracción o flexo-compresión, y el factor
φ deja de ser 0,90: por §9.3.2 vale 0,90 en tracción con o sin flexión, pero 0,70
en compresión con o sin flexión para elementos sin refuerzo en espiral.

CONDICIÓN DE DISPARO — LA DECLARA EL USUARIO
============================================
Se activa con (S3 o S4) Y (Zona 3 o 4), o bien con qadm < 0,10 MPa. Los tres datos
provienen del Estudio de Mecánica de Suelos: **el motor no los deduce**. El perfil
de suelo y la zona sísmica se declaran; qadm ya es dato de entrada.

LO QUE SIGUE SIN CUBRIRSE
=========================
§21.12.3.3 remite a §21.4 o §21.5 cuando la viga recibe flexión de columnas del
sistema sismorresistente. Ese detallado NO está implementado: si el usuario declara
esa condición, el resultado se reporta como NO VERIFICADO en ese aspecto en vez de
darse por completo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.beam.beam_flexure import BeamMinimumSteel, beam_minimum_steel
from engine.beam.axial_flexure import AxialFlexureCheck, SectionGeometry, check_axial_flexure
from engine.beam.beam_shear import BeamShearResult, check_beam_shear
from engine.results.status import CheckStatus

# E.060 §21.12.3.2
MIN_DIMENSION_SPAN_DIVISOR = 20.0
MIN_DIMENSION_CAP_M = 0.450
STIRRUP_SPACING_ABS_M = 0.300
STIRRUP_SPACING_DB_FACTOR = 16.0

# E.030 art. 65.1
E030_AXIAL_FRACTION = 0.10
E030_QADM_TRIGGER_KPA = 100.0  # 0,10 MPa

SoilProfileType = Literal["S0", "S1", "S2", "S3", "S4"]

E030_TRIGGER_NOTE = (
    "E.030 art. 65.1 exige diseñar los elementos de conexión EN TRACCIÓN O COMPRESIÓN para una "
    "fuerza mínima del 10% de las cargas verticales amplificadas, adicionalmente a la flexión. "
    "La condición se dispara con (S3 o S4) Y (Zona 3 o 4), o con qadm < 0,10 MPa. Los tres datos "
    "provienen del EMS y los declara el usuario: el motor no los deduce."
)


# =========================================================================
# §21.12.3.3 — cuándo aplica y a qué remite
# =========================================================================
#
# AUDITORÍA. §21.12.3.3 dice: "Las vigas de cimentación que estén sometidas a
# flexión por las columnas que son parte del sistema resistente a fuerzas laterales
# deben adecuarse a lo indicado en 21.4 ó 21.5 de acuerdo al sistema resistente a
# fuerzas laterales empleado."
#
# NO APLICA SIEMPRE. Se necesitan DOS condiciones a la vez:
#   1. que las columnas conectadas formen parte del sistema sismorresistente, y
#   2. que transmitan FLEXIÓN a la viga.
# Una viga que solo ata zapatas para repartir el par —el caso de la zapata
# conectada clásica— no cumple la primera y §21.12.3.3 no la alcanza.
#
# A CUÁL DE LOS DOS REMITE. §21.2 de la E.060 designada (propuesta 2019):
#   21.2.4 "Las disposiciones contenidas en 21.4, son aplicables a las vigas y columnas
#          de los edificios cuyo sistema resistente a fuerzas laterales [...] sea de
#          muros estructurales (R0 = 6)."
#   21.2.5 "Las disposiciones contenidas en 21.5, 21.6 y 21.7 son aplicables a [...] los
#          edificios cuyo sistema [...] sea: a) Pórticos (R0 = 8)  b) Duales (R0 = 7)."
#
# La fuente NO distingue dual tipo I y tipo II (la edición anterior sí, y mandaba el
# tipo I a 21.4). Fase 10A, A6: todo dual remite a §21.5. Los valores `dual_tipo_I` y
# `dual_tipo_II` se conservan por contrato de API y ambos resuelven a §21.5.

LateralSystem = Literal["muros_estructurales", "dual_tipo_I", "porticos", "dual_tipo_II"]

LATERAL_SYSTEM_TO_SECTION: dict[str, str] = {
    "muros_estructurales": "§21.4",
    "dual_tipo_I": "§21.5",
    "porticos": "§21.5",
    "dual_tipo_II": "§21.5",
}

LATERAL_SYSTEM_LABEL: dict[str, str] = {
    "muros_estructurales": "Muros estructurales (R0 = 6)",
    "dual_tipo_I": "Dual (R0 = 7); la E.060 designada no distingue tipo I y II",
    "porticos": "Pórticos (R0 = 8)",
    "dual_tipo_II": "Dual (R0 = 7); la E.060 designada no distingue tipo I y II",
}


class LateralSystemRequirements(BaseModel):
    """Requisitos adicionales que §21.12.3.3 activa, ya resueltos a la sección que
    corresponde según §21.2."""

    applies: bool
    section: str = Field(default="", description='"§21.4" o "§21.5"')
    system_label: str = ""
    reason: str

    # Requisitos que este motor SÍ comprueba.
    disallows_10_5_3: bool = Field(
        default=False,
        description=(
            "Conservado por contrato; siempre False. En la E.060 designada (propuesta 2019) "
            "§10.5.3 solo exime a losas, de modo que ninguna viga puede acogerse a él y no hay "
            "nada que anular (Fase 10A)."
        ),
    )
    min_two_bars_each_face: bool = Field(default=False)
    positive_moment_ratio_at_joint: float | None = Field(
        default=None,
        description="§21.4.4.3: M+ >= 1/3 M−; §21.5.2.2: M+ >= 1/2 M−",
    )
    max_tension_ratio: float | None = Field(
        default=None, description="§21.5.2.1: la cuantía en tracción no excederá 0,025"
    )
    max_Pu_over_fcAg: float | None = Field(
        default=None, description="§21.5.1.1: Pu <= 0,1·f'c·Ag"
    )
    min_clear_span_over_depth: float | None = Field(
        default=None, description="§21.5.1.2: luz libre >= 4·peralte"
    )
    min_width_over_depth: float | None = Field(
        default=None, description="§21.5.1.3: bw >= 0,3·h y >= 250 mm"
    )

    # Requisitos que este motor NO comprueba y quedan declarados.
    not_implemented: list[str] = Field(default_factory=list)


def lateral_system_requirements(
    part_of_lateral_force_system: bool, system: str | None
) -> LateralSystemRequirements:
    """Resuelve §21.12.3.3 para el sistema declarado."""
    if not part_of_lateral_force_system:
        return LateralSystemRequirements(
            applies=False,
            reason=(
                "§21.12.3.3 NO aplica: no se ha declarado que la viga reciba flexión de columnas "
                "del sistema resistente a fuerzas laterales. Una viga que solo ata zapatas para "
                "repartir el par no está alcanzada por ese artículo."
            ),
        )
    if system is None:
        return LateralSystemRequirements(
            applies=True,
            reason=(
                "§21.12.3.3 aplica, pero NO se ha declarado el sistema resistente a fuerzas "
                "laterales. §21.2 remite a §21.4 para muros estructurales y a §21.5 para "
                "pórticos y duales: sin saber cuál es, no puede determinarse "
                "qué requisitos adicionales corresponden."
            ),
            not_implemented=["Sistema sismorresistente no declarado: §21.4 o §21.5 sin resolver."],
        )

    seccion = LATERAL_SYSTEM_TO_SECTION[system]
    etiqueta = LATERAL_SYSTEM_LABEL[system]
    base = dict(
        applies=True,
        section=seccion,
        system_label=etiqueta,
        reason=(
            f"§21.12.3.3 aplica y §21.2 remite a {seccion} para el sistema «{etiqueta}»: la viga "
            f"recibe flexión de columnas del sistema resistente a fuerzas laterales."
        ),
        min_two_bars_each_face=True,
    )

    if seccion == "§21.4":
        return LateralSystemRequirements(
            **base,
            positive_moment_ratio_at_joint=1.0 / 3.0,
            not_implemented=[
                "§21.4.3: la fuerza cortante de diseño debe ser el menor entre el cortante por "
                "capacidad (momentos nominales en los extremos) y el de las combinaciones con "
                "el sismo amplificado 2,5 veces. NO IMPLEMENTADO.",
                "§21.4.4.2: prohibición de empalmes traslapados a menos de 2h de la cara del "
                "nudo. NO IMPLEMENTADO.",
                "§21.4.4.4: estribos de confinamiento en 2h desde la cara de apoyo, con "
                "diámetro mínimo según la barra longitudinal y s <= min(d/4 pero no menor de "
                "100 mm, 8·db, 24·db_estribo, 300 mm). NO IMPLEMENTADO.",
            ],
        )

    return LateralSystemRequirements(
        **base,
        positive_moment_ratio_at_joint=0.5,
        max_tension_ratio=0.025,
        max_Pu_over_fcAg=0.1,
        min_clear_span_over_depth=4.0,
        min_width_over_depth=0.30,
        not_implemented=[
            "§21.5.3: requisitos de refuerzo transversal y cortante por capacidad. "
            "NO IMPLEMENTADO.",
        ],
    )


class SeismicContext(BaseModel):
    """Datos del EMS que deciden si aplica E.030 art. 65.1."""

    soil_profile: SoilProfileType | None = Field(
        default=None, description="Perfil de suelo de E.030 art. 14 (S0 a S4)"
    )
    seismic_zone: int | None = Field(
        default=None, ge=1, le=4, description="Zona sísmica de E.030"
    )
    qadm_kPa: float | None = None
    part_of_lateral_force_system: bool = Field(
        default=False,
        description=(
            "True si la viga recibe flexión de columnas del sistema sismorresistente. "
            "Activa §21.12.3.3. NO aplica siempre: una viga que solo ata zapatas para "
            "repartir el par no está alcanzada por ese artículo."
        ),
    )
    lateral_system: LateralSystem | None = Field(
        default=None,
        description=(
            "Sistema resistente a fuerzas laterales del edificio. §21.2 remite a §21.4 para "
            "muros estructurales y a §21.5 para pórticos y duales (sin distinción de tipo)."
        ),
    )

    def triggers_e030_65_1(self) -> tuple[bool, str]:
        """¿Aplica el requisito de fuerza axial? Devuelve (aplica, motivo)."""
        if self.qadm_kPa is not None and self.qadm_kPa < E030_QADM_TRIGGER_KPA:
            return True, (
                f"qadm = {self.qadm_kPa:.1f} kPa < 100 kPa (0,10 MPa): E.030 art. 65.1 aplica "
                f"«en general para suelos con una presión admisible menor que 0,10 MPa»."
            )
        if self.soil_profile in ("S3", "S4") and self.seismic_zone in (3, 4):
            return True, (
                f"Perfil {self.soil_profile} en Zona {self.seismic_zone}: E.030 art. 65.1 aplica "
                f"a zapatas aisladas en suelos S3/S4 de las Zonas 3 y 4."
            )
        if self.soil_profile is None or self.seismic_zone is None:
            return False, (
                "No se han declarado el perfil de suelo ni la zona sísmica, de modo que no puede "
                "comprobarse la condición de (S3 o S4) Y (Zona 3 o 4) de E.030 art. 65.1. Solo se "
                "evaluó el criterio de qadm."
            )
        return False, (
            f"Perfil {self.soil_profile} en Zona {self.seismic_zone} y qadm >= 0,10 MPa: no se "
            f"dispara E.030 art. 65.1."
        )


class DimensionalCheck(BaseModel):
    """§21.12.3.2 — dimensión transversal mínima."""

    clear_span_m: float
    min_dimension_required_m: float
    min_dimension_provided_m: float
    capped_at_400mm: bool
    ok: bool
    equation_substituted: str
    code_reference: str = "E.060 §21.12.3.2"


class ConfinementCheck(BaseModel):
    """§21.12.3.2 — estribos cerrados y su separación máxima."""

    spacing_limit_m: float
    governed_by: str
    spacing_provided_m: float | None = None
    ok: bool | None = None
    code_reference: str = "E.060 §21.12.3.2"


class ConnectingBeamResult(BaseModel):
    b_m: float
    h_m: float
    d_m: float
    clear_span_m: float

    dimensional: DimensionalCheck
    confinement: ConfinementCheck
    shear: BeamShearResult

    Mu_negative_kNm: float
    Mu_positive_kNm: float
    As_negative_m2: float
    As_positive_m2: float
    min_steel_negative: BeamMinimumSteel
    min_steel_positive: BeamMinimumSteel

    axial_required: bool
    axial_N_kN: float = Field(default=0.0, description="Fuerza axial de E.030 art. 65.1")
    axial_trigger_note: str = ""
    phi_axial: float | None = Field(
        default=None, description="φ de §9.3.2 para el caso axial que corresponda"
    )

    axial_flexure_negative: "AxialFlexureCheck | None" = Field(
        default=None, description="Interacción P−M con el momento negativo"
    )
    axial_flexure_positive: "AxialFlexureCheck | None" = Field(
        default=None, description="Interacción P−M con el momento positivo"
    )
    lateral_requirements: "LateralSystemRequirements | None" = None

    lateral_system_note: str = ""
    status: CheckStatus
    messages: list[str]


def check_dimensions(b_m: float, h_m: float, clear_span_m: float) -> DimensionalCheck:
    """§21.12.3.2: la MENOR dimensión transversal debe ser >= luz libre / 20, con
    tope en 450 mm (E.060 propuesta 2019; la edición anterior decía 400 mm).

    «No necesita ser mayor a 450 mm» es un tope al REQUISITO, no a la dimensión: una
    viga puede ser más ancha; lo que no puede es exigírsele más de 450 mm."""
    requerido_sin_tope = clear_span_m / MIN_DIMENSION_SPAN_DIVISOR
    requerido = min(requerido_sin_tope, MIN_DIMENSION_CAP_M)
    menor = min(b_m, h_m)
    return DimensionalCheck(
        clear_span_m=clear_span_m,
        min_dimension_required_m=requerido,
        min_dimension_provided_m=menor,
        capped_at_400mm=requerido_sin_tope > MIN_DIMENSION_CAP_M,
        ok=menor >= requerido - 1e-9,
        equation_substituted=(
            f"luz libre / 20 = {clear_span_m:.3f}/20 = {requerido_sin_tope * 1000:.0f} mm"
            + (f", topado en {MIN_DIMENSION_CAP_M * 1000:.0f} mm" if requerido_sin_tope > MIN_DIMENSION_CAP_M else "")
            + f" -> exigido {requerido * 1000:.0f} mm; menor dimensión de la sección = "
            f"{menor * 1000:.0f} mm"
        ),
    )


def confinement_spacing_limit(
    b_m: float, h_m: float, longitudinal_db_mm: float
) -> ConfinementCheck:
    """§21.12.3.2: estribos cerrados a s <= min(menor dimensión, 300 mm, 16·db)."""
    menor = min(b_m, h_m)
    por_db = STIRRUP_SPACING_DB_FACTOR * longitudinal_db_mm / 1000.0
    candidatos = {
        "menor dimensión de la sección": menor,
        "300 mm": STIRRUP_SPACING_ABS_M,
        f"16·db = 16·{longitudinal_db_mm:.1f} mm": por_db,
    }
    gobierna = min(candidatos, key=lambda k: candidatos[k])
    return ConfinementCheck(spacing_limit_m=candidatos[gobierna], governed_by=gobierna)


def design_connecting_beam(
    b_m: float,
    h_m: float,
    d_m: float,
    clear_span_m: float,
    Mu_negative_kNm: float,
    Mu_positive_kNm: float,
    Vu_kN: float,
    fc_MPa: float,
    fy_MPa: float,
    longitudinal_db_mm: float,
    sum_Pu_kN: float,
    seismic: SeismicContext,
    fyt_MPa: float | None = None,
    stirrup_diameter_mm: float = 9.525,
    n_legs: int = 2,
) -> ConnectingBeamResult:
    """Diseña una viga de conexión entre zapatas.

    `sum_Pu_kN` es la carga vertical amplificada que soporta la zapata conectada:
    E.030 art. 65.1 mide sobre ella la fuerza axial mínima."""
    from engine.beam.beam_flexure import _as_for_moment

    interaccion_neg = interaccion_pos = None

    fyt = fyt_MPa if fyt_MPa is not None else min(fy_MPa, 420.0)
    mensajes: list[str] = []
    estados: list[CheckStatus] = []

    # --- §21.12.3.2: dimensión transversal ---
    dim = check_dimensions(b_m, h_m, clear_span_m)
    estados.append(CheckStatus.PASS if dim.ok else CheckStatus.FAIL)
    if not dim.ok:
        mensajes.append(
            f"E.060 §21.12.3.2: la menor dimensión transversal "
            f"({dim.min_dimension_provided_m * 1000:.0f} mm) no alcanza el mínimo de "
            f"{dim.min_dimension_required_m * 1000:.0f} mm."
        )

    # --- Flexión en ambas caras ---
    lateral = lateral_system_requirements(
        seismic.part_of_lateral_force_system, seismic.lateral_system
    )

    phi_flexion = 0.90  # §9.3.2, flexión sin carga axial
    As_neg = _as_for_moment(Mu_negative_kNm, b_m, d_m, fc_MPa, fy_MPa, phi_flexion)
    As_pos = _as_for_moment(Mu_positive_kNm, b_m, d_m, fc_MPa, fy_MPa, phi_flexion)
    # §10.5.3 no alcanza a vigas (propuesta 2019): el mínimo completo de §10.5.1/§10.5.2
    # rige con o sin sistema sismorresistente.
    min_neg = beam_minimum_steel(b_m, h_m, d_m, fc_MPa, fy_MPa, As_neg, phi_flexion)
    min_pos = beam_minimum_steel(b_m, h_m, d_m, fc_MPa, fy_MPa, As_pos, phi_flexion)
    As_neg_dis = max(As_neg, min_neg.As_min_governing_m2)
    As_pos_dis = max(As_pos, min_pos.As_min_governing_m2)
    estados.append(CheckStatus.PASS)

    # --- Cortante y estribos ---
    shear = check_beam_shear(
        Vu_kN=Vu_kN, bw_m=b_m, h_m=h_m, d_m=d_m, fc_MPa=fc_MPa, fyt_MPa=fyt,
        stirrup_diameter_mm=stirrup_diameter_mm, n_legs=n_legs,
    )
    estados.append(CheckStatus.PASS if shear.status_ok else CheckStatus.FAIL)
    if not shear.status_ok:
        mensajes.append(shear.message)

    # --- §21.12.3.2: confinamiento. Manda sobre la separación de §11.5 ---
    conf = confinement_spacing_limit(b_m, h_m, longitudinal_db_mm)
    if shear.layout is not None:
        s_final = min(shear.layout.spacing_m, conf.spacing_limit_m)
        s_final = max(round(s_final * 100.0) / 100.0, 0.05)
        conf.spacing_provided_m = s_final
        conf.ok = s_final <= conf.spacing_limit_m + 1e-9
        if shear.layout.spacing_m > conf.spacing_limit_m:
            mensajes.append(
                f"La separación de estribos baja de {shear.layout.spacing_m * 100:.0f} a "
                f"{s_final * 100:.0f} cm: E.060 §21.12.3.2 exige estribos CERRADOS a "
                f"s <= {conf.spacing_limit_m * 100:.0f} cm (gobierna «{conf.governed_by}»), "
                f"más restrictivo que §11.5.5.1."
            )
        estados.append(CheckStatus.PASS if conf.ok else CheckStatus.FAIL)
    else:
        # Sin estribos por resistencia, §21.12.3.2 los exige igualmente: son estribos
        # cerrados de confinamiento, no de cortante.
        conf.spacing_provided_m = conf.spacing_limit_m
        conf.ok = True
        mensajes.append(
            f"El cortante no exige estribos, pero E.060 §21.12.3.2 sí: estribos CERRADOS a "
            f"s <= {conf.spacing_limit_m * 100:.0f} cm (gobierna «{conf.governed_by}»)."
        )
        estados.append(CheckStatus.PASS)

    # --- E.030 art. 65.1: fuerza axial ---
    aplica, motivo = seismic.triggers_e030_65_1()
    N = E030_AXIAL_FRACTION * sum_Pu_kN if aplica else 0.0
    phi_axial = None
    if aplica:
        # §9.3.2: 0,90 en tracción con o sin flexión; 0,70 en compresión con o sin
        # flexión para elementos sin refuerzo en espiral. La viga se verifica en AMBOS
        # sentidos, de modo que se reporta el más desfavorable.
        phi_axial = 0.70
        mensajes.append(
            f"E.030 art. 65.1: la viga debe diseñarse EN TRACCIÓN O COMPRESIÓN para "
            f"N = 0,10·SumaPu = {N:.1f} kN, adicionalmente a la flexión. {motivo} "
            f"El factor phi de §9.3.2 vale 0,90 en tracción con o sin flexión y 0,70 en "
            f"compresión con o sin flexión (elementos sin refuerzo en espiral)."
        )
        # INTERACCIÓN P−M. La viga debe verificarse en AMBOS sentidos: E.030 art. 65.1
        # dice «en tracción o compresión», de modo que el signo de N no está definido y
        # hay que comprobar los dos. Se toma el más desfavorable.
        seccion = SectionGeometry(
            b_m=b_m, h_m=h_m, d_m=d_m, d_prime_m=h_m - d_m,
            As_bottom_m2=As_pos_dis, As_top_m2=As_neg_dis,
        )
        peor_neg = peor_pos = None
        for sentido, N_signed in (("compresión", N), ("tracción", -N)):
            cn = check_axial_flexure(seccion, fc_MPa, fy_MPa, N_signed, -Mu_negative_kNm)
            cp = check_axial_flexure(seccion, fc_MPa, fy_MPa, N_signed, Mu_positive_kNm)
            if peor_neg is None or cn.demand_ratio > peor_neg.demand_ratio:
                peor_neg = cn
            if peor_pos is None or cp.demand_ratio > peor_pos.demand_ratio:
                peor_pos = cp
        interaccion_neg, interaccion_pos = peor_neg, peor_pos

        for etiqueta, chk in (("negativo", peor_neg), ("positivo", peor_pos)):
            mensajes.append(f"Interacción P−M con el momento {etiqueta}: {chk.message}")
            estados.append(CheckStatus.PASS if chk.status_ok else CheckStatus.FAIL)

    # --- §21.12.3.3 ---
    nota_sistema = lateral.reason
    if lateral.applies:
        mensajes.append(lateral.reason)
        if lateral.positive_moment_ratio_at_joint is not None and Mu_negative_kNm > 0:
            exigido = lateral.positive_moment_ratio_at_joint * As_neg_dis
            if As_pos_dis < exigido - 1e-12:
                mensajes.append(
                    f"{lateral.section}: la resistencia a momento POSITIVO en la cara del nudo "
                    f"debe ser al menos {lateral.positive_moment_ratio_at_joint:.2f} veces la "
                    f"negativa. As(+) = {As_pos_dis * 1e4:.2f} cm² frente a los "
                    f"{exigido * 1e4:.2f} cm² exigidos."
                )
                estados.append(CheckStatus.FAIL)
        if lateral.min_clear_span_over_depth is not None:
            if clear_span_m < lateral.min_clear_span_over_depth * h_m - 1e-9:
                mensajes.append(
                    f"{lateral.section} (§21.5.1.2): la luz libre ({clear_span_m:.2f} m) debe ser "
                    f"al menos 4 veces el peralte ({4 * h_m:.2f} m)."
                )
                estados.append(CheckStatus.FAIL)
        if lateral.min_width_over_depth is not None:
            if b_m < max(lateral.min_width_over_depth * h_m, 0.250) - 1e-9:
                mensajes.append(
                    f"{lateral.section} (§21.5.1.3): el ancho ({b_m * 1000:.0f} mm) debe ser al "
                    f"menos 0,3·h ({lateral.min_width_over_depth * h_m * 1000:.0f} mm) y 250 mm."
                )
                estados.append(CheckStatus.FAIL)
        for pendiente in lateral.not_implemented:
            mensajes.append(pendiente)
        if lateral.not_implemented:
            estados.append(CheckStatus.NOT_VERIFIED)

    return ConnectingBeamResult(
        b_m=b_m, h_m=h_m, d_m=d_m, clear_span_m=clear_span_m,
        dimensional=dim, confinement=conf, shear=shear,
        Mu_negative_kNm=Mu_negative_kNm, Mu_positive_kNm=Mu_positive_kNm,
        As_negative_m2=As_neg_dis, As_positive_m2=As_pos_dis,
        min_steel_negative=min_neg, min_steel_positive=min_pos,
        axial_required=aplica, axial_N_kN=N, axial_trigger_note=motivo, phi_axial=phi_axial,
        axial_flexure_negative=interaccion_neg, axial_flexure_positive=interaccion_pos,
        lateral_requirements=lateral, lateral_system_note=nota_sistema,
        status=CheckStatus.worst(estados), messages=mensajes,
    )


ConnectingBeamResult.model_rebuild()
