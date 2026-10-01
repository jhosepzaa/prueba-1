"""Cortante y refuerzo transversal en VIGAS — E.060 §11.5.

Era el bloqueo TBD-4 de la auditoría de Fase 0: sin §11.5 no se podía diseñar la
viga de conexión. Con el texto disponible, aquí está.

TEXTO NORMATIVO (verificado en el PDF de E.060)
===============================================
§11.5.2    "Los valores de fy y fyt usados en el diseño del refuerzo de cortante no
            deben exceder 420 MPa."

§11.5.5.1  "El espaciamiento del refuerzo de cortante colocado perpendicularmente al
            eje del elemento no debe exceder de d/2 en elementos de concreto no
            preesforzado [...] ni de 600 mm."

§11.5.5.3  "Donde Vs sobrepase 0,33·sqrt(f'c)·bw·d, las separaciones máximas dadas
            en 11.5.5.1 y 11.5.5.2 se deben reducir a la mitad."

§11.5.6.1  "Debe colocarse un área mínima de refuerzo para cortante, Av_min, en todo
            elemento de concreto armado sometido a flexión [...] donde Vu exceda de
            0,5·Vc, EXCEPTO EN: (a) Losas y zapatas. (b) Losas nervadas y aligerados
            [...]. (c) Vigas con un peralte h menor o igual que el mayor de los
            siguientes valores: 250 mm, 2,5 veces el espesor del ala y 0,5 veces el
            ancho del alma."

§11.5.6.2  "Av_min = 0,062·sqrt(f'c)·bw·s/fyt   (11-13)
            Pero no debe ser menor que 0,35·bw·s/fyt."

§11.5.7.2  "Vs = Av·fyt·d / s     (11-15)"

§11.5.7.9  "En ningún caso se debe considerar Vs mayor que 0,66·sqrt(f'c)·bw·d."

DÓNDE ENTRA φ
=============
La ecuación 11-1 exige φ·Vn >= Vu con Vn = Vc + Vs. El φ de cortante es 0,85 por
§9.3.2 — no §9.4, que es la resistencia mínima del concreto.

QUÉ NO CUBRE ESTE MÓDULO
========================
Estribos inclinados (§11.5.7.4) y barras dobladas (§11.5.7.5): solo se implementa
el refuerzo PERPENDICULAR al eje, que es lo que se usa en una viga de cimentación.
Torsión (§11.6) queda fuera; si la viga la tuviera, este cálculo estaría incompleto
y así debe declararse.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

# E.060 §11.5.2
MAX_FYT_SHEAR_MPA = 420.0
# E.060 §11.5.5.1
MAX_SPACING_ABS_M = 0.600
# E.060 §11.5.5.3: umbral a partir del cual las separaciones se reducen a la mitad.
VS_HALVING_COEFFICIENT = 0.33
# E.060 §11.5.6.2, ec. 11-13 y su cota inferior.
AV_MIN_COEFFICIENT = 0.062
AV_MIN_FLOOR_COEFFICIENT = 0.35
# E.060 §11.5.7.9
VS_MAX_COEFFICIENT = 0.66
# E.060 §11.5.6.1(c): peralte por debajo del cual no se exige Av_min.
MIN_DEPTH_FOR_AV_MIN_M = 0.250


class StirrupLayout(BaseModel):
    """Estribos adoptados en una zona de la viga."""

    Av_m2: float = Field(..., description="Área de las ramas del estribo que cruzan la fisura")
    n_legs: int
    bar_diameter_mm: float
    spacing_m: float
    spacing_limit_m: float
    spacing_limit_reference: str
    spacing_ok: bool


class BeamShearResult(BaseModel):
    Vu_kN: float
    bw_m: float
    d_m: float
    fc_MPa: float
    fyt_MPa: float
    phi: float

    Vc_kN: float
    phi_Vc_kN: float
    Vs_required_kN: float = Field(..., description="Vu/φ − Vc; cero si el concreto basta")
    Vs_max_kN: float = Field(..., description="Cota de §11.5.7.9")
    Vs_exceeds_limit: bool

    stirrups_required: bool = Field(..., description="Vu > φVc")
    av_min_required: bool = Field(..., description="Vu > 0,5·φVc y no aplica ninguna exención")
    av_min_exemption: str = Field(default="", description="Cuál exención de §11.5.6.1 aplica")

    Av_min_over_s_m: float = Field(..., description="(Av/s) mínimo por ec. 11-13 [m²/m]")
    Av_over_s_required_m: float = Field(..., description="(Av/s) que exige Vs [m²/m]")
    Av_over_s_governing_m: float

    layout: StirrupLayout | None = None
    status_ok: bool
    message: str
    equation_substituted: str
    code_reference: str


def concrete_shear_strength_kN(fc_MPa: float, bw_m: float, d_m: float) -> float:
    """Vc = 0,17·sqrt(f'c)·bw·d — E.060 §11.3.1.1, ec. 11-3.

    Es la misma expresión que ya usa el motor para el cortante de zapatas; se llama
    aquí para que el módulo de vigas sea autocontenido en su lectura."""
    return 0.17 * math.sqrt(fc_MPa) * (bw_m * 1000.0) * (d_m * 1000.0) / 1000.0


def max_stirrup_spacing_m(d_m: float, Vs_kN: float, fc_MPa: float, bw_m: float) -> tuple[float, str]:
    """Separación máxima por §11.5.5.1, reducida a la mitad si §11.5.5.3 aplica."""
    limite = min(d_m / 2.0, MAX_SPACING_ABS_M)
    referencia = "E.060 §11.5.5.1: s <= min(d/2, 600 mm)"

    umbral_kN = VS_HALVING_COEFFICIENT * math.sqrt(fc_MPa) * (bw_m * 1000.0) * (d_m * 1000.0) / 1000.0
    if Vs_kN > umbral_kN:
        limite /= 2.0
        referencia = (
            f"E.060 §11.5.5.3: Vs = {Vs_kN:.1f} kN supera 0,33·sqrt(f'c)·bw·d = "
            f"{umbral_kN:.1f} kN, de modo que la separación de §11.5.5.1 se REDUCE A LA MITAD"
        )
    return limite, referencia


def av_min_over_spacing_m(fc_MPa: float, bw_m: float, fyt_MPa: float) -> float:
    """(Av/s) mínimo — ec. 11-13 y su cota inferior de §11.5.6.2. Unidades: m²/m."""
    bw_mm = bw_m * 1000.0
    por_ecuacion = AV_MIN_COEFFICIENT * math.sqrt(fc_MPa) * bw_mm / fyt_MPa  # mm²/mm
    piso = AV_MIN_FLOOR_COEFFICIENT * bw_mm / fyt_MPa
    return max(por_ecuacion, piso) / 1000.0  # mm²/mm -> m²/m


def check_beam_shear(
    Vu_kN: float,
    bw_m: float,
    h_m: float,
    d_m: float,
    fc_MPa: float,
    fyt_MPa: float,
    phi: float = 0.85,
    stirrup_diameter_mm: float = 9.525,  # 3/8", el habitual en vigas de cimentación
    n_legs: int = 2,
    is_slab_or_footing: bool = False,
) -> BeamShearResult:
    """Verifica el cortante de una viga y dimensiona los estribos.

    `is_slab_or_footing` activa la exención de §11.5.6.1(a). Existe para que el
    módulo pueda usarse también sobre una zapata sin que su Av mínimo se exija por
    error — la exención es de la norma, no una comodidad."""
    if fyt_MPa > MAX_FYT_SHEAR_MPA + 1e-9:
        raise ValueError(
            f"E.060 §11.5.2 limita fyt del refuerzo de cortante a {MAX_FYT_SHEAR_MPA:.0f} MPa; "
            f"recibido {fyt_MPa:.0f} MPa."
        )

    Vc = concrete_shear_strength_kN(fc_MPa, bw_m, d_m)
    phi_Vc = phi * Vc
    Vs_req = max(Vu_kN / phi - Vc, 0.0)
    Vs_max = VS_MAX_COEFFICIENT * math.sqrt(fc_MPa) * (bw_m * 1000.0) * (d_m * 1000.0) / 1000.0
    excede = Vs_req > Vs_max

    requiere_estribos = Vu_kN > phi_Vc + 1e-9

    # §11.5.6.1: Av mínimo donde Vu > 0,5·Vc. La norma escribe "0,5 Vc" en el mismo
    # contexto en que compara con la resistencia de diseño, de modo que se toma
    # 0,5·φVc — la lectura conservadora, que exige estribos mínimos antes.
    supera_medio = Vu_kN > 0.5 * phi_Vc + 1e-9
    exencion = ""
    if is_slab_or_footing:
        exencion = "E.060 §11.5.6.1(a): losas y zapatas están exentas del refuerzo mínimo"
    elif h_m <= MIN_DEPTH_FOR_AV_MIN_M + 1e-9:
        exencion = (
            f"E.060 §11.5.6.1(c): viga con h = {h_m * 1000:.0f} mm <= 250 mm, exenta del "
            f"refuerzo mínimo"
        )
    av_min_exigido = supera_medio and not exencion

    av_min_s = av_min_over_spacing_m(fc_MPa, bw_m, fyt_MPa) if av_min_exigido else 0.0
    # De ec. 11-15: Av/s = Vs/(fyt·d)
    av_req_s = (Vs_req * 1000.0) / (fyt_MPa * d_m * 1000.0) / 1000.0 if Vs_req > 0 else 0.0
    av_gob_s = max(av_min_s, av_req_s)

    layout: StirrupLayout | None = None
    if av_gob_s > 0:
        area_rama_m2 = math.pi * (stirrup_diameter_mm / 1000.0) ** 2 / 4.0
        Av = n_legs * area_rama_m2
        s_por_area = Av / av_gob_s
        s_max, s_ref = max_stirrup_spacing_m(d_m, Vs_req, fc_MPa, bw_m)
        # Se redondea a la baja al centímetro: una separación de obra no se replantea
        # en milímetros, y redondear a la baja nunca reduce el área de estribos.
        s = math.floor(min(s_por_area, s_max) * 100.0) / 100.0
        layout = StirrupLayout(
            Av_m2=Av, n_legs=n_legs, bar_diameter_mm=stirrup_diameter_mm,
            spacing_m=s, spacing_limit_m=s_max, spacing_limit_reference=s_ref,
            spacing_ok=s <= s_max + 1e-9 and s > 0,
        )

    ok = not excede and (layout is None or layout.spacing_ok)
    if excede:
        mensaje = (
            f"SECCIÓN INSUFICIENTE: Vs requerido = {Vs_req:.1f} kN supera el máximo de "
            f"{Vs_max:.1f} kN que admite E.060 §11.5.7.9. Los estribos no pueden compensarlo: "
            f"hay que aumentar la sección o f'c."
        )
    elif not requiere_estribos and not av_min_exigido:
        mensaje = (
            f"El concreto basta: Vu = {Vu_kN:.1f} kN <= φVc = {phi_Vc:.1f} kN"
            + (f", y {exencion}." if exencion else ", y Vu no supera 0,5·φVc.")
        )
    elif not requiere_estribos:
        mensaje = (
            f"El concreto resiste el cortante (Vu = {Vu_kN:.1f} <= φVc = {phi_Vc:.1f} kN), pero "
            f"Vu supera 0,5·φVc: E.060 §11.5.6.1 exige refuerzo MÍNIMO de cortante."
        )
    else:
        mensaje = (
            f"Se requieren estribos: Vu = {Vu_kN:.1f} kN > φVc = {phi_Vc:.1f} kN, "
            f"Vs = {Vs_req:.1f} kN."
        )

    return BeamShearResult(
        Vu_kN=Vu_kN, bw_m=bw_m, d_m=d_m, fc_MPa=fc_MPa, fyt_MPa=fyt_MPa, phi=phi,
        Vc_kN=Vc, phi_Vc_kN=phi_Vc, Vs_required_kN=Vs_req, Vs_max_kN=Vs_max,
        Vs_exceeds_limit=excede,
        stirrups_required=requiere_estribos, av_min_required=av_min_exigido,
        av_min_exemption=exencion,
        Av_min_over_s_m=av_min_s, Av_over_s_required_m=av_req_s, Av_over_s_governing_m=av_gob_s,
        layout=layout, status_ok=ok, message=mensaje,
        equation_substituted=(
            f"Vc = 0,17·sqrt({fc_MPa:.1f})·{bw_m * 1000:.0f}·{d_m * 1000:.0f} = {Vc:.1f} kN | "
            f"φVc = {phi_Vc:.1f} kN | Vs = Vu/φ − Vc = {Vs_req:.1f} kN "
            f"(máx {Vs_max:.1f} kN por §11.5.7.9)"
            + (
                f" | Av/s = {av_gob_s * 1e6:.1f} mm²/m -> {n_legs}Ø{stirrup_diameter_mm:.1f} @ "
                f"{layout.spacing_m * 100:.0f} cm (límite {layout.spacing_limit_m * 100:.0f} cm)"
                if layout else ""
            )
        ),
        code_reference="E.060 §11.5 (ec. 11-13, 11-15), §11.3.1.1 ec. 11-3, φ por §9.3.2",
    )
