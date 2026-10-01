"""L4 — Verificación de longitud de desarrollo del refuerzo de la zapata.

E.060 §15.6: "El desarrollo del refuerzo en las zapatas debe hacerse de acuerdo
con el Capítulo 12. La tracción o compresión calculadas en el refuerzo en cada
sección debe desarrollarse a cada lado de dicha sección [...] Las secciones
críticas para el desarrollo del refuerzo deben suponerse en los mismos planos
definidos en 15.4.2 para el momento máximo amplificado" -> la CARA DE LA COLUMNA.

CRITERIO:      ld_requerida  <=  ld_disponible
DISPONIBLE:    voladizo − recubrimiento lateral
               = (dimensión_zapata − dimensión_columna)/2 − recubrimiento

Si no cumple y no hay gancho declarado -> FAIL, informando ld requerida,
disponible y el déficit exacto.

GANCHOS: nunca se asumen. Solo se consideran si el usuario los declara
explícitamente en la geometría de la barra (`hook_type`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.codes.peru.e060_development import (
    DevelopmentLengthResult,
    HookDevelopmentResult,
    development_length_eq_12_1,
    development_length_table_12_1,
    hook_development_length,
    psi_s_bar_size,
    psi_t_top_bar,
    simplified_conditions_met,
)
from engine.reinforcement.rebar_geometry import BarLayerGeometry
from engine.results.status import CheckStatus


class DevelopmentCheckResult(BaseModel):
    direction: str
    layer: str

    ld_required_m: float
    ld_available_m: float
    deficit_m: float = Field(..., description="ld_requerida − ld_disponible, positivo si falta")
    utilization: float = Field(..., description="ld_requerida / ld_disponible")

    uses_hook: bool
    hook_type: str
    hook_result: HookDevelopmentResult | None = None
    straight_result: DevelopmentLengthResult

    # Parámetros que entraron al cálculo (auditabilidad)
    bar_diameter_mm: float
    fy_MPa: float
    fc_MPa: float
    cover_m: float
    spacing_m: float
    clear_spacing_m: float
    cb_m: float
    is_top_bar: bool
    has_confinement_stirrups: bool

    status: CheckStatus
    message: str
    equation_substituted: str
    code_reference: str


def check_development_length(
    layer: BarLayerGeometry,
    fy_MPa: float,
    fc_MPa: float,
    *,
    epoxy_coated: bool = False,
    lightweight_concrete: bool = False,
    has_confinement_stirrups: bool = False,
    hook_side_cover_ok: bool = False,
    hook_confined_by_stirrups: bool = False,
) -> DevelopmentCheckResult:
    db = layer.bar_diameter_m

    # --- Factores de la Tabla 12.2 ---
    # Barra superior = 300 mm o más de concreto fresco DEBAJO. En una zapata, la
    # parrilla inferior tiene solo el recubrimiento debajo -> nunca es "superior".
    concrete_below = layer.depth_to_bar_center_from_bottom_m
    psi_t = psi_t_top_bar(concrete_below)
    is_top_bar = psi_t > 1.0

    if epoxy_coated:
        psi_e = 1.5 if (layer.bottom_cover_m < 3 * db or layer.clear_spacing_m < 6 * db) else 1.2
    else:
        psi_e = 1.0
    psi_s = psi_s_bar_size(db)
    lam = 1.3 if lightweight_concrete else 1.0

    # --- cb (§12.2.3): la MENOR entre distancia al concreto más cercano y media separación ---
    cover_to_bar_center = layer.bottom_cover_m + db / 2.0
    cb = min(cover_to_bar_center, layer.spacing_m / 2.0)

    # --- Método: Tabla 12.1 si se cumplen sus condiciones; si no, ec. 12-1 ---
    if simplified_conditions_met(layer.clear_spacing_m, layer.bottom_cover_m, db, has_confinement_stirrups):
        straight = development_length_table_12_1(db, fy_MPa, fc_MPa, psi_t, psi_e, lam)
    else:
        straight = development_length_eq_12_1(
            db, fy_MPa, fc_MPa, cb, psi_t, psi_e, psi_s, Ktr=0.0, lambda_concrete=lam
        )

    available = layer.available_development_length_m

    hook_result: HookDevelopmentResult | None = None
    if layer.has_hook:
        hook_result = hook_development_length(
            db, fy_MPa, fc_MPa, layer.hook_type,
            psi_e=1.2 if epoxy_coated else 1.0,
            lambda_concrete=lam,
            side_cover_ok_for_0_7=hook_side_cover_ok,
            confined_by_stirrups=hook_confined_by_stirrups,
        )
        ld_required = hook_result.ldg_m
        governing_desc = f"gancho de {layer.hook_type}° declarado por el usuario"
    else:
        ld_required = straight.ld_m
        governing_desc = "barra recta sin gancho (no se asume ningún gancho)"

    deficit = ld_required - available
    utilization = ld_required / available if available > 0 else float("inf")

    if deficit <= 1e-9:
        status = CheckStatus.PASS
        message = (
            f"Desarrollo suficiente: ld requerida {ld_required * 1000:.0f} mm <= "
            f"disponible {available * 1000:.0f} mm ({governing_desc}). "
            f"Holgura {-deficit * 1000:.0f} mm."
        )
    else:
        status = CheckStatus.FAIL
        remedy = (
            "Alternativas: usar un diámetro menor, aumentar la dimensión de la zapata, "
            "o declarar explícitamente un gancho estándar (§12.5)."
            if not layer.has_hook
            else "Ni siquiera con el gancho declarado se alcanza la longitud necesaria."
        )
        message = (
            f"DESARROLLO INSUFICIENTE en dirección {layer.direction}: se requieren "
            f"{ld_required * 1000:.0f} mm y solo hay {available * 1000:.0f} mm disponibles "
            + (
                "desde la cara de columna hasta el extremo de la barra. "
                if layer.through_column_length_m is None
                else "hacia el lado de la columna: con la columna descentrada, la barra que "
                "cruza la cara del voladizo solo tiene el ancho de la columna y el voladizo "
                "opuesto para anclarse (E.060 §15.6.2, a cada lado de la sección crítica). "
            )
            + f"FALTAN {deficit * 1000:.0f} mm ({governing_desc}). {remedy}"
        )

    return DevelopmentCheckResult(
        direction=layer.direction,
        layer=layer.layer,
        ld_required_m=ld_required,
        ld_available_m=available,
        deficit_m=deficit,
        utilization=utilization,
        uses_hook=layer.has_hook,
        hook_type=layer.hook_type,
        hook_result=hook_result,
        straight_result=straight,
        bar_diameter_mm=db * 1000.0,
        fy_MPa=fy_MPa,
        fc_MPa=fc_MPa,
        cover_m=layer.bottom_cover_m,
        spacing_m=layer.spacing_m,
        clear_spacing_m=layer.clear_spacing_m,
        cb_m=cb,
        is_top_bar=is_top_bar,
        has_confinement_stirrups=has_confinement_stirrups,
        status=status,
        message=message,
        equation_substituted=(
            f"[{straight.method}] {straight.equation_substituted}"
            + (f" || GANCHO: {hook_result.equation_substituted}" if hook_result else "")
            + (
                f" || disponible = voladizo {layer.cantilever_m * 1000:.0f} − recubrimiento "
                f"{layer.side_cover_m * 1000:.0f} = {available * 1000:.0f} mm"
                if layer.through_column_length_m is None
                else f" || disponible = min(hacia el borde libre: voladizo "
                f"{layer.cantilever_m * 1000:.0f} − recubrimiento {layer.side_cover_m * 1000:.0f}; "
                f"hacia el otro lado, a través de la columna: "
                f"{layer.through_column_length_m * 1000:.0f}) = {available * 1000:.0f} mm "
                f"(§15.6.2: a cada lado de la sección crítica; gobierna el tramo a través de la columna)"
            )
            + f" || requerida {ld_required * 1000:.0f} mm, déficit {deficit * 1000:+.0f} mm"
        ),
        code_reference=(
            f"E.060 §15.6 (sección crítica en cara de columna) → Cap. 12; {straight.code_reference}"
            + ("; gancho §12.5" if hook_result else "")
        ),
    )
