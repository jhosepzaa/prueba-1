"""Interacción axial-flexión (P−M) — Fase 3.

Cuando E.030 art. 65.1 dispara la fuerza axial, la viga de conexión deja de ser un
elemento a flexión pura y hay que verificar la SECCIÓN COMPLETA bajo la combinación
(Pu, Mu). Este módulo construye el diagrama de interacción por compatibilidad de
deformaciones y comprueba si el punto de demanda cae dentro.

BASE NORMATIVA
==============
§10.2.3   "La deformación unitaria máxima utilizable en la fibra extrema en
           compresión del concreto se supondrá igual a 0,003."

§10.2.7   Bloque rectangular equivalente de 0,85·f'c sobre una profundidad
           a = β1·c, con β1 = 0,85 para f'c entre 17 y 28 MPa.

§10.3.6.2 ec. (10-2), elementos no preesforzados CON ESTRIBOS:
              Pn_max = 0,80·[0,85·f'c·(Ag − Ast) + fy·Ast]
           Es un tope a la resistencia de diseño en compresión: contempla la
           excentricidad accidental que ninguna columna deja de tener.

§9.3.2     φ = 0,90 flexión sin carga axial
           φ = 0,90 carga axial de TRACCIÓN con o sin flexión
           φ = 0,70 carga axial de COMPRESIÓN con o sin flexión (otros elementos)
           "Para elementos en flexocompresión puede incrementarse LINEALMENTE hasta
            0,90 en la medida que Pn disminuye desde 0,1·f'c·Ag ó Pb, el que sea
            menor, hasta cero."

QUÉ SE MODELA Y QUÉ NO
======================
Sección RECTANGULAR con dos capas de refuerzo —superior e inferior—, que es lo que
tiene una viga de conexión. No se modelan secciones T, refuerzo repartido en el
alma ni confinamiento por espiral.

Se supone comportamiento elastoplástico perfecto del acero, con Es = 200 000 MPa
(§8.5.5). El acero dentro del bloque de compresión descuenta el concreto que
desplaza: omitirlo sobreestimaría la resistencia.

CONVENCIÓN DE SIGNOS
====================
Compresión POSITIVA en la carga axial. Momento positivo = tracción en la cara
inferior. El diagrama se construye respecto del centroide geométrico de la sección
bruta.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

# §10.2.3
EPS_CU = 0.003
# §8.5.5: módulo de elasticidad del acero de refuerzo.
ES_MPA = 200_000.0
# §10.3.6.2, ec. 10-2: tope para elementos con estribos.
PN_MAX_TIED_FACTOR = 0.80
# §9.3.2
PHI_TENSION = 0.90
PHI_COMPRESSION_TIED = 0.70
PHI_FLEXURE = 0.90

AxialSense = Literal["compresión", "tracción", "flexión pura"]


def beta1(fc_MPa: float) -> float:
    """§10.2.7.3: β1 = 0,85 para f'c <= 28 MPa; disminuye 0,05 por cada 7 MPa por
    encima, con piso en 0,65."""
    if fc_MPa <= 28.0:
        return 0.85
    return max(0.85 - 0.05 * (fc_MPa - 28.0) / 7.0, 0.65)


class SectionGeometry(BaseModel):
    """Sección rectangular con refuerzo en dos capas."""

    b_m: float = Field(..., gt=0)
    h_m: float = Field(..., gt=0)
    d_m: float = Field(..., gt=0, description="Recubrimiento efectivo hasta la capa INFERIOR")
    d_prime_m: float = Field(..., gt=0, description="Desde la fibra superior hasta la capa SUPERIOR")
    As_bottom_m2: float = Field(..., ge=0)
    As_top_m2: float = Field(..., ge=0)

    @property
    def Ag_m2(self) -> float:
        return self.b_m * self.h_m

    @property
    def Ast_m2(self) -> float:
        return self.As_bottom_m2 + self.As_top_m2


class InteractionPoint(BaseModel):
    """Un punto del diagrama, con y sin factor de reducción."""

    c_m: float = Field(..., description="Profundidad del eje neutro")
    Pn_kN: float
    Mn_kNm: float
    phi: float
    phi_Pn_kN: float
    phi_Mn_kNm: float
    eps_t: float = Field(..., description="Deformación del acero en tracción más alejado")
    sense: AxialSense


class AxialFlexureCheck(BaseModel):
    section: SectionGeometry
    fc_MPa: float
    fy_MPa: float

    Pu_kN: float
    Mu_kNm: float

    Pn_max_kN: float = Field(..., description="Tope de §10.3.6.2, ec. 10-2, sin φ")
    phi_Pn_max_kN: float
    P0_tension_kN: float = Field(..., description="Tracción pura: −fy·Ast")

    capacity_at_Pu: InteractionPoint | None = Field(
        default=None, description="Punto del diagrama con el mismo Pu que la demanda"
    )
    demand_ratio: float = Field(..., description="Mu / φMn a ese mismo Pu; <= 1 cumple")
    inside_diagram: bool
    axial_cap_ok: bool

    status_ok: bool
    message: str
    equation_substituted: str
    code_reference: str = "E.060 §10.2, §10.3.6.2 ec. 10-2, §9.3.2"
    diagram: list[InteractionPoint] = Field(default_factory=list)


def _steel_stress_MPa(eps: float, fy_MPa: float) -> float:
    """Elastoplástico perfecto: fs = Es·ε acotado a ±fy."""
    return max(min(ES_MPA * eps, fy_MPa), -fy_MPa)


def phi_for(Pn_kN: float, fc_MPa: float, Ag_m2: float, Pb_kN: float) -> float:
    """§9.3.2. En tracción vale 0,90; en compresión parte de 0,70 y sube
    linealmente hasta 0,90 cuando Pn baja desde min(0,1·f'c·Ag, Pb) hasta cero."""
    if Pn_kN <= 0.0:
        return PHI_TENSION
    limite = min(0.1 * fc_MPa * Ag_m2 * 1000.0, Pb_kN)
    if limite <= 0.0 or Pn_kN >= limite:
        return PHI_COMPRESSION_TIED
    fraccion = Pn_kN / limite
    return PHI_COMPRESSION_TIED + (PHI_TENSION - PHI_COMPRESSION_TIED) * (1.0 - fraccion)


def nominal_at_neutral_axis(
    section: SectionGeometry, fc_MPa: float, fy_MPa: float, c_m: float
) -> tuple[float, float, float]:
    """(Pn, Mn, ε_t) para una profundidad de eje neutro dada.

    Compresión positiva. Momentos respecto del centroide geométrico."""
    s = section
    b1 = beta1(fc_MPa)
    a_m = min(b1 * c_m, s.h_m)

    # Concreto: 0,85·f'c sobre el bloque. f'c en MPa = MN/m² -> kN.
    Cc_kN = 0.85 * fc_MPa * a_m * s.b_m * 1000.0

    # Deformaciones por triángulos semejantes desde la fibra comprimida (arriba).
    eps_top = EPS_CU * (c_m - s.d_prime_m) / c_m if c_m > 0 else -1.0
    eps_bot = EPS_CU * (c_m - s.d_m) / c_m if c_m > 0 else -1.0

    fs_top = _steel_stress_MPa(eps_top, fy_MPa)
    fs_bot = _steel_stress_MPa(eps_bot, fy_MPa)

    # El acero dentro del bloque desplaza concreto ya contabilizado en Cc.
    if s.d_prime_m <= a_m:
        fs_top -= 0.85 * fc_MPa
    if s.d_m <= a_m:
        fs_bot -= 0.85 * fc_MPa

    F_top_kN = s.As_top_m2 * fs_top * 1000.0
    F_bot_kN = s.As_bottom_m2 * fs_bot * 1000.0

    Pn_kN = Cc_kN + F_top_kN + F_bot_kN
    y_c = s.h_m / 2.0
    Mn_kNm = (
        Cc_kN * (y_c - a_m / 2.0)
        + F_top_kN * (y_c - s.d_prime_m)
        + F_bot_kN * (y_c - s.d_m)
    )
    # ε_t: el acero en tracción más alejado de la fibra comprimida (el de abajo).
    eps_t = -eps_bot  # positivo cuando está traccionado
    return Pn_kN, Mn_kNm, eps_t


def _balanced_point(section: SectionGeometry, fc_MPa: float, fy_MPa: float) -> tuple[float, float]:
    """§10.3.2: falla balanceada, con el acero en tracción alcanzando fy justo cuando
    el concreto llega a 0,003."""
    eps_y = fy_MPa / ES_MPA
    c_b = EPS_CU * section.d_m / (EPS_CU + eps_y)
    Pb, Mb, _ = nominal_at_neutral_axis(section, fc_MPa, fy_MPa, c_b)
    return Pb, Mb


def build_interaction_diagram(
    section: SectionGeometry, fc_MPa: float, fy_MPa: float, n_points: int = 200
) -> list[InteractionPoint]:
    """Diagrama de interacción reducido por φ, de tracción pura a compresión pura.

    RESOLUCIÓN
    ==========
    La frontera del diagrama es convexa, de modo que interpolar linealmente entre
    puntos SUBESTIMA la capacidad: el resultado queda del lado seguro, pero un
    muestreo grueso lo hace innecesariamente conservador. Con 40 puntos el error
    frente a la flexión pura llegaba al 6%; con 200 baja al 0,3%, que es del orden
    del efecto real del acero en compresión. Verificado en los tests de
    convergencia."""
    Pb, _ = _balanced_point(section, fc_MPa, fy_MPa)
    Ag = section.Ag_m2
    Pn_max = PN_MAX_TIED_FACTOR * (
        0.85 * fc_MPa * (Ag - section.Ast_m2) + fy_MPa * section.Ast_m2
    ) * 1000.0

    puntos: list[InteractionPoint] = []

    # Tracción pura: todo el acero en fluencia, sin concreto.
    P_trac = -fy_MPa * section.Ast_m2 * 1000.0
    M_trac = (
        -fy_MPa * section.As_top_m2 * 1000.0 * (section.h_m / 2.0 - section.d_prime_m)
        - fy_MPa * section.As_bottom_m2 * 1000.0 * (section.h_m / 2.0 - section.d_m)
    )
    puntos.append(
        InteractionPoint(
            c_m=0.0, Pn_kN=P_trac, Mn_kNm=M_trac, phi=PHI_TENSION,
            phi_Pn_kN=PHI_TENSION * P_trac, phi_Mn_kNm=PHI_TENSION * M_trac,
            eps_t=999.0, sense="tracción",
        )
    )

    c_max = 2.0 * section.h_m
    for i in range(1, n_points + 1):
        c = c_max * i / n_points
        Pn, Mn, eps_t = nominal_at_neutral_axis(section, fc_MPa, fy_MPa, c)
        phi = phi_for(Pn, fc_MPa, Ag, Pb)
        phi_Pn = min(phi * Pn, PHI_COMPRESSION_TIED * Pn_max) if Pn > 0 else phi * Pn
        sentido: AxialSense = (
            "compresión" if Pn > 1e-6 else "tracción" if Pn < -1e-6 else "flexión pura"
        )
        puntos.append(
            InteractionPoint(
                c_m=c, Pn_kN=Pn, Mn_kNm=Mn, phi=phi,
                phi_Pn_kN=phi_Pn, phi_Mn_kNm=phi * Mn, eps_t=eps_t, sense=sentido,
            )
        )
    return sorted(puntos, key=lambda p: p.phi_Pn_kN)


def check_axial_flexure(
    section: SectionGeometry,
    fc_MPa: float,
    fy_MPa: float,
    Pu_kN: float,
    Mu_kNm: float,
) -> AxialFlexureCheck:
    """Verifica el punto (Pu, Mu) contra el diagrama de interacción reducido por φ.

    La comprobación NO es «φMn >= Mu» con el Mn de flexión pura: eso ignoraría la
    carga axial, que es justamente lo que E.030 art. 65.1 obliga a considerar. Se
    busca la capacidad a momento CON EL MISMO Pu y se compara contra ella.

    EL SIGNO DEL MOMENTO IMPORTA
    ============================
    Con armado distinto arriba y abajo —que es el caso normal en una viga de
    conexión— el diagrama NO es simétrico. Un momento NEGATIVO tracciona la cara
    superior, y su capacidad la da el acero de arriba. Compararlo contra la
    capacidad de flexión positiva daría un resultado sin sentido: es exactamente el
    error que esta comprobación evita volteando la sección."""
    seccion_original = section
    if Mu_kNm < 0:
        # Momento negativo: se voltea la sección para que la cara traccionada quede
        # abajo en el modelo. El resultado se reporta con la sección tal como entró.
        section = SectionGeometry(
            b_m=section.b_m, h_m=section.h_m,
            d_m=section.h_m - section.d_prime_m,
            d_prime_m=section.h_m - section.d_m,
            As_bottom_m2=section.As_top_m2,
            As_top_m2=section.As_bottom_m2,
        )
    Ag = section.Ag_m2
    Pb, _ = _balanced_point(section, fc_MPa, fy_MPa)
    Pn_max = PN_MAX_TIED_FACTOR * (
        0.85 * fc_MPa * (Ag - section.Ast_m2) + fy_MPa * section.Ast_m2
    ) * 1000.0
    phi_Pn_max = PHI_COMPRESSION_TIED * Pn_max
    P_trac = -fy_MPa * section.Ast_m2 * 1000.0

    diagrama = build_interaction_diagram(section, fc_MPa, fy_MPa)

    # §10.3.6.2: la compresión de diseño no puede superar el tope de la ec. 10-2.
    cap_ok = Pu_kN <= phi_Pn_max + 1e-6
    # Y en tracción no puede superar la que da el acero en fluencia.
    if Pu_kN < 0:
        cap_ok = Pu_kN >= PHI_TENSION * P_trac - 1e-6

    # Capacidad a momento con el mismo Pu: se interpola sobre el diagrama.
    punto: InteractionPoint | None = None
    phi_Mn_en_Pu = 0.0
    for a, b in zip(diagrama, diagrama[1:]):
        lo, hi = a.phi_Pn_kN, b.phi_Pn_kN
        if lo <= Pu_kN <= hi and abs(hi - lo) > 1e-9:
            t = (Pu_kN - lo) / (hi - lo)
            phi_Mn_en_Pu = a.phi_Mn_kNm + t * (b.phi_Mn_kNm - a.phi_Mn_kNm)
            punto = InteractionPoint(
                c_m=a.c_m + t * (b.c_m - a.c_m),
                Pn_kN=a.Pn_kN + t * (b.Pn_kN - a.Pn_kN),
                Mn_kNm=a.Mn_kNm + t * (b.Mn_kNm - a.Mn_kNm),
                phi=a.phi + t * (b.phi - a.phi),
                phi_Pn_kN=Pu_kN,
                phi_Mn_kNm=phi_Mn_en_Pu,
                eps_t=a.eps_t + t * (b.eps_t - a.eps_t),
                sense=a.sense,
            )
            break

    if punto is None:
        # Pu queda fuera del rango del diagrama: no hay capacidad que ofrecer.
        ratio = float("inf")
        dentro = False
    else:
        ratio = abs(Mu_kNm) / phi_Mn_en_Pu if phi_Mn_en_Pu > 1e-9 else float("inf")
        dentro = ratio <= 1.0 + 1e-9

    ok = dentro and cap_ok
    if not cap_ok and Pu_kN > 0:
        mensaje = (
            f"CARGA AXIAL POR ENCIMA DEL TOPE: Pu = {Pu_kN:.1f} kN supera "
            f"φPn_max = {phi_Pn_max:.1f} kN de E.060 §10.3.6.2, ec. 10-2. Ningún armado "
            f"longitudinal lo corrige: hay que aumentar la sección o f'c."
        )
    elif not cap_ok:
        mensaje = (
            f"TRACCIÓN POR ENCIMA DE LA CAPACIDAD DEL ACERO: Pu = {Pu_kN:.1f} kN supera "
            f"φ·fy·Ast = {PHI_TENSION * P_trac:.1f} kN. Hace falta más área de refuerzo."
        )
    elif punto is None:
        mensaje = (
            f"Pu = {Pu_kN:.1f} kN cae fuera del diagrama de interacción de la sección: no hay "
            f"capacidad a momento que oponerle."
        )
    elif dentro:
        mensaje = (
            f"La sección resiste la combinación ({'cara superior traccionada' if Mu_kNm < 0 else 'cara inferior traccionada'}): "
            f"Mu = {abs(Mu_kNm):.1f} kN·m frente a "
            f"φMn = {phi_Mn_en_Pu:.1f} kN·m con Pu = {Pu_kN:.1f} kN (ratio {ratio:.3f}). "
            f"φ = {punto.phi:.3f} por §9.3.2, en {punto.sense}."
        )
    else:
        mensaje = (
            f"LA SECCIÓN NO RESISTE la combinación: Mu = {abs(Mu_kNm):.1f} kN·m supera "
            f"φMn = {phi_Mn_en_Pu:.1f} kN·m con Pu = {Pu_kN:.1f} kN (ratio {ratio:.3f}). "
            f"La carga axial reduce la capacidad a momento respecto de la flexión pura."
        )

    return AxialFlexureCheck(
        section=seccion_original, fc_MPa=fc_MPa, fy_MPa=fy_MPa, Pu_kN=Pu_kN, Mu_kNm=Mu_kNm,
        Pn_max_kN=Pn_max, phi_Pn_max_kN=phi_Pn_max, P0_tension_kN=P_trac,
        capacity_at_Pu=punto, demand_ratio=ratio, inside_diagram=dentro,
        axial_cap_ok=cap_ok, status_ok=ok, message=mensaje,
        equation_substituted=(
            f"β1 = {beta1(fc_MPa):.3f} | Pn_max (ec. 10-2) = 0,80·[0,85·{fc_MPa:.1f}·"
            f"({Ag:.4f}−{section.Ast_m2:.5f}) + {fy_MPa:.0f}·{section.Ast_m2:.5f}] = "
            f"{Pn_max:.1f} kN -> φPn_max = {phi_Pn_max:.1f} kN | "
            f"punto de demanda (Pu={Pu_kN:.1f} kN, Mu={abs(Mu_kNm):.1f} kN·m) frente a "
            f"φMn = {phi_Mn_en_Pu:.1f} kN·m"
            + (f" con φ = {punto.phi:.3f}" if punto else "")
        ),
        diagram=diagrama,
    )
