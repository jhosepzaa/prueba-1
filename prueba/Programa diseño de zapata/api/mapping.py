"""Traducción entre los DTOs de la API y los modelos del motor.

Todo el conocimiento de ingeniería vive en `engine/`. Este módulo solo mueve
datos: convierte unidades de presentación (cm², cm, mm) y aplana estructuras.
No decide nada de ingeniería.
"""

from __future__ import annotations

import math

from api import schemas
from engine.codes.peru.e060_concrete import E060ConcreteCode, MinDepthInterpretation
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters, GeometrySearchParameters
from engine.domain.site_limits import SiteLimits
from engine.domain.soil import SoilProfile
from engine.foundation.auto_search_range import AutoRange, estimate_search_range
from engine.soil.contact_pressure import (
    ContactPressureModel,
    EffectiveAreaModel,
    KernCheckModel,
)
from engine.soil.stability import (
    D10_2B_ADOPTED_NOTE,
    ECCENTRICITY_TERM_NOTE,
    ENVELOPE_NOTE,
)
from engine.optimization.scoring import ScoreWeights
from engine.units.unit_registry import (
    force_to_kN,
    length_to_m,
    moment_to_kNm,
    pressure_to_kPa,
    strength_to_MPa,
    unit_weight_to_kNm3,
)
from engine.reinforcement.rebar_alternatives import RebarAlternative
from engine.results.footing_candidate import FootingCandidate
from engine.results.limitations import LIMITATION_REGISTRY

M2_TO_CM2 = 1e4


# ---------------- entrada: DTO -> motor ----------------


def build_code(request: schemas.DesignRequest) -> E060ConcreteCode:
    return E060ConcreteCode(
        min_depth_interpretation=MinDepthInterpretation(request.min_depth_interpretation)
    )


def build_column(dto: schemas.ColumnInput, units: schemas.UnitsInput) -> Column:
    return Column(
        shape=dto.shape,
        bx_m=length_to_m(dto.bx_m, units.length),
        by_m=length_to_m(dto.by_m, units.length),
    )


def build_placement(dto: schemas.ColumnInput, units: schemas.UnitsInput) -> ColumnPlacement:
    """Columna más su posición sobre la zapata. Con desplazamientos nulos describe
    el caso concéntrico y el motor sigue el mismo camino que antes de la Fase 1B."""
    return ColumnPlacement(
        column=build_column(dto, units),
        offset_x_m=length_to_m(dto.offset_x_m, units.length),
        offset_y_m=length_to_m(dto.offset_y_m, units.length),
    )


def build_materials(
    dto: schemas.MaterialsInput, units: schemas.UnitsInput
) -> tuple[MaterialConcrete, MaterialSteel]:
    return (
        MaterialConcrete(
            fc_MPa=strength_to_MPa(dto.fc_MPa, units.strength),
            unit_weight_kNm3=unit_weight_to_kNm3(dto.concrete_unit_weight_kNm3, units.unit_weight),
        ),
        MaterialSteel(fy_MPa=strength_to_MPa(dto.fy_MPa, units.strength), bar_type=dto.bar_type),
    )


def build_soil(dto: schemas.SoilInput, units: schemas.UnitsInput) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=pressure_to_kPa(dto.qadm_kPa, units.pressure),
        pressure_basis=dto.pressure_basis,
        gamma_kNm3=unit_weight_to_kNm3(dto.gamma_kNm3, units.unit_weight),
        Df_m=length_to_m(dto.Df_m, units.length),
        mu_friction_soil_concrete=dto.mu_friction_soil_concrete,
        cohesion_kPa=(
            pressure_to_kPa(dto.cohesion_kPa, units.pressure)
            if dto.cohesion_kPa is not None
            else None
        ),
        FS_sliding_required=dto.FS_sliding_required,
        FS_overturning_required=dto.FS_overturning_required,
        allow_temporary_increase_30pct=dto.allow_temporary_increase_30pct,
        allow_seismic_reduction_80pct=dto.allow_seismic_reduction_80pct,
        founded_on_rock=dto.founded_on_rock,
        source_notes=dto.source_notes,
    )


def build_loads(
    combinations: list[schemas.LoadCombinationInput],
    units: schemas.UnitsInput,
    load_cases: "list[schemas.LoadCaseInput] | None" = None,
    definitions: "list[schemas.CombinationDefinitionInput] | None" = None,
) -> LoadCaseSet:
    """Modo directo (combinaciones) o modo por casos (Fase 10B). Nunca los dos a la vez."""
    if load_cases is not None or definitions is not None:
        if combinations:
            raise ValueError(
                "Use un solo modo de cargas: combinaciones directas O casos con definiciones "
                "de combinación, no ambos."
            )
        if not load_cases or not definitions:
            raise ValueError(
                "El modo de cargas por casos necesita casos (load_cases) en cada columna y "
                "definiciones de combinación (combination_definitions)."
            )
        from engine.domain.load_cases import (
            CombinationDefinition, LoadCase, LoadCaseKind, ActionLevel, derive_load_case_set,
        )
        casos = [
            LoadCase(
                name=c.name, kind=LoadCaseKind(c.kind),
                level=ActionLevel(c.level) if c.level is not None else None,
                P_kN=force_to_kN(c.P_kN, units.force),
                Mx_kNm=moment_to_kNm(c.Mx_kNm, units.moment),
                My_kNm=moment_to_kNm(c.My_kNm, units.moment),
                Hx_kN=force_to_kN(c.Hx_kN, units.force),
                Hy_kN=force_to_kN(c.Hy_kN, units.force),
                description=c.description,
            )
            for c in load_cases
        ]
        defs = [
            CombinationDefinition(
                name=d.name, type=LoadCombinationType(d.type), factors=d.factors,
                description=d.description,
            )
            for d in definitions
        ]
        return derive_load_case_set(casos, defs)
    service, factored = [], []
    for c in combinations:
        combo = LoadCombination(
            name=c.name, type=LoadCombinationType(c.type),
            P_kN=force_to_kN(c.P_kN, units.force),
            Mx_kNm=moment_to_kNm(c.Mx_kNm, units.moment),
            My_kNm=moment_to_kNm(c.My_kNm, units.moment),
            Hx_kN=force_to_kN(c.Hx_kN, units.force),
            Hy_kN=force_to_kN(c.Hy_kN, units.force),
            includes_seismic_loads=c.includes_seismic_loads,
            includes_wind_loads=c.includes_wind_loads,
            description=c.description,
        )
        (service if combo.type is LoadCombinationType.SERVICIO else factored).append(combo)
    return LoadCaseSet(service=service, factored=factored)


def build_search(
    dto: schemas.SearchInput,
    units: schemas.UnitsInput,
    load_case_set: LoadCaseSet,
    soil: SoilProfile,
    column: Column,
) -> tuple[GeometrySearchParameters, DepthSearchParameters, AutoRange | None]:
    """Los limites omitidos se completan con el rango que estima el motor."""
    b_step = length_to_m(dto.B_step_m, units.length)
    l_step = length_to_m(dto.L_step_m, units.length)
    h_step = length_to_m(dto.h_step_m, units.length)

    needs_auto = any(
        v is None
        for v in (dto.B_min_m, dto.B_max_m, dto.L_min_m, dto.L_max_m, dto.h_min_m, dto.h_max_m)
    )
    auto = (
        estimate_search_range(load_case_set, soil, column.bx_m, column.by_m, b_step, l_step, h_step)
        if needs_auto
        else None
    )

    def pick(value: float | None, fallback: float) -> float:
        return fallback if value is None else length_to_m(value, units.length)

    # Cuando los límites los pone la heurística, el INCREMENTO también es suyo: con el
    # rango ampliado por la excentricidad, mantener el paso fino generaba una malla que
    # el servidor rechaza por tamaño. Si el usuario declaró los límites, manda su paso.
    if auto is not None and auto.B_step_m:
        if dto.B_min_m is None or dto.B_max_m is None:
            b_step = auto.B_step_m
        if dto.L_min_m is None or dto.L_max_m is None:
            l_step = auto.L_step_m or auto.B_step_m

    return (
        GeometrySearchParameters(
            B_min_m=pick(dto.B_min_m, auto.B_min_m if auto else 1.0),
            B_max_m=pick(dto.B_max_m, auto.B_max_m if auto else 4.0),
            B_step_m=b_step,
            L_min_m=pick(dto.L_min_m, auto.L_min_m if auto else 1.0),
            L_max_m=pick(dto.L_max_m, auto.L_max_m if auto else 4.0),
            L_step_m=l_step,
            max_LB_ratio=dto.max_LB_ratio,
        ),
        DepthSearchParameters(
            h_min_m=pick(dto.h_min_m, auto.h_min_m if auto else 0.40),
            h_max_m=pick(dto.h_max_m, auto.h_max_m if auto else 1.00),
            h_step_m=h_step,
            cover_override_mm=dto.cover_override_mm,
            hook_type_x=dto.hook_type_x, hook_type_y=dto.hook_type_y,
        ),
        auto,
    )


def build_weights(dto: schemas.WeightsInput) -> ScoreWeights:
    return ScoreWeights(
        w_concrete_volume=dto.w_concrete_volume,
        w_steel_mass=dto.w_steel_mass,
        w_max_dimension=dto.w_max_dimension,
        w_constructive_complexity=dto.w_constructive_complexity,
    )


# ---------------- salida: motor -> DTO ----------------


def trace_entry_to_dto(entry) -> schemas.TraceEntryOut:
    """Única traducción de una entrada de traza, para las TRES tipologías.

    Estaba duplicada entre la zapata y la viga, y la copia de la viga se quedaba atrás
    cada vez que se añadía un campo. `open_tbd` es justamente uno de esos campos: si se
    perdiera al cruzar la API, la UI no podría distinguir un hueco normativo de un dato
    que falta, que es la distinción que la Fase 4D dejó cerrada."""
    return schemas.TraceEntryOut(
        id=entry.id, scope=entry.scope, description=entry.description,
        equation_symbolic=entry.equation_symbolic,
        equation_substituted=entry.equation_substituted,
        result_value=entry.result_value, result_unit=entry.result_unit,
        hypotheses=entry.hypotheses, governing_combo=entry.governing_combo,
        code_name=entry.code_name, code_reference=entry.code_reference,
        status=entry.status.value, open_tbd=entry.open_tbd,
    )


def trace_to_dto(candidate: FootingCandidate) -> list[schemas.TraceEntryOut]:
    return [trace_entry_to_dto(e) for e in candidate.trace.entries]


def rebar_option_to_dto(option: RebarAlternative) -> schemas.RebarOptionOut:
    return schemas.RebarOptionOut(
        label=option.label,
        bar_designation=option.bar_designation,
        diameter_mm=option.diameter_mm,
        spacing_cm=option.spacing_m * 100.0,
        n_bars=option.n_bars,
        As_provided_cm2=option.As_provided_m2 * M2_TO_CM2,
        As_required_cm2=option.As_required_m2 * M2_TO_CM2,
        As_min_cm2=option.As_min_m2 * M2_TO_CM2,
        utilization=option.utilization,
        governed_by=option.governed_by,
        ld_required_mm=option.ld_required_m * 1000.0 if option.ld_required_m is not None else None,
        ld_available_mm=option.ld_available_m * 1000.0 if option.ld_available_m is not None else None,
        development_ok=option.development_ok,
    )


def short_direction_to_dto(candidate: FootingCandidate) -> schemas.ShortDirectionOut | None:
    sd = candidate.short_direction
    if sd is None:
        return None
    return schemas.ShortDirectionOut(
        is_square=sd.is_square, beta=sd.beta, gamma_s=sd.gamma_s,
        bands=[
            schemas.BandOut(
                name=b.name, width_m=b.width_m,
                As_required_cm2=b.As_required_m2 * M2_TO_CM2,
                As_min_cm2=b.As_min_m2 * M2_TO_CM2,
                topped_up=b.topped_up,
            )
            for b in sd.bands
        ],
        note=sd.note, code_reference=sd.code_reference,
    )


def stability_to_dto(candidate: FootingCandidate) -> schemas.StabilityOut | None:
    st = candidate.stability
    if st is None:
        return None
    missing = list(
        dict.fromkeys(
            st.sliding.missing_parameters
            + st.overturning_x.missing_parameters
            + st.overturning_y.missing_parameters
        )
    )
    return schemas.StabilityOut(
        sliding_status=st.sliding.status.value,
        sliding_FS=st.sliding.FS_obtained,
        sliding_FS_required=st.sliding.FS_required,
        sliding_message=st.sliding.message,
        sliding_governing_combo=st.sliding.governing_combo,
        overturning_x_status=st.overturning_x.status.value,
        overturning_x_FS=st.overturning_x.FS_obtained,
        overturning_y_status=st.overturning_y.status.value,
        overturning_y_FS=st.overturning_y.FS_obtained,
        overturning_message_x=st.overturning_x.message,
        overturning_message_y=st.overturning_y.message,
        pivot_description=st.overturning_x.pivot_description,
        missing_parameters=missing,
        # FORMULACION_VOLTEO: paridad con la combinada. Se transporta lo que el motor ya
        # calculó; la API no reinterpreta ningún estado ni recompone ninguna nota.
        overturning_x_FS_required=st.overturning_x.FS_required,
        overturning_y_FS_required=st.overturning_y.FS_required,
        overturning_x_governing_combo=st.overturning_x.governing_combo,
        overturning_y_governing_combo=st.overturning_y.governing_combo,
        overturning_x_envelope_reading=st.overturning_x.envelope_reading,
        overturning_y_envelope_reading=st.overturning_y.envelope_reading,
        criterion_note=" ".join(
            (D10_2B_ADOPTED_NOTE, ECCENTRICITY_TERM_NOTE, ENVELOPE_NOTE)
        ),
    )


def contact_model_for(soil: "schemas.SoilInput") -> ContactPressureModel:
    """Modelo de presión de contacto que pide el proyectista.

    Un solo sitio para las cinco llamadas del servidor: si la elección se construyera en
    cada endpoint, una tipología podría quedarse con el modelo por defecto sin que nadie
    lo notara —que es exactamente el defecto de paridad que la auditoría del 2026-09-19
    encontró con §15.7—."""
    if not soil.use_effective_area_e050_art28:
        return KernCheckModel()
    return EffectiveAreaModel(
        qadm_declared_for_effective_area=soil.qadm_declared_for_effective_area
    )


def limitations_to_dto() -> list[schemas.LimitationOut]:
    return [
        schemas.LimitationOut(
            id=l.id, title=l.title, kind=l.kind.value,
            code_reference=l.code_reference, description=l.description,
            impact=l.impact, can_cause_false_pass=l.can_cause_false_pass,
            enforced_by=l.enforced_by,
        )
        for l in LIMITATION_REGISTRY
    ]


PASS_CONDITIONS = [
    "Todas las verificaciones de resistencia cumplen: presión de contacto dentro del núcleo "
    "y ≤ qadm, flexión, cortante unidireccional, punzonamiento (incluyendo transferencia de "
    "momento §11.12.7) y peralte mínimo §15.7.",
    "La longitud de desarrollo (§15.6 → Cap. 12) es suficiente para la barra seleccionada y "
    "existe al menos una opción de armado desarrollable en cada dirección.",
    "Si hay fuerzas horizontales o momentos, el usuario declaró μ, FS de deslizamiento y FS "
    "de volcamiento. Sin ellos el resultado es NO VERIFICADO, nunca PASS.",
    "Deslizamiento y volcamiento cumplen los factores de seguridad declarados.",
    "Ninguna limitación relevante con capacidad de producir un falso PASS sigue pendiente.",
]


# =========================================================================
# Viga de conexión — Fase 3
# =========================================================================


def beam_trace_to_dto(trace) -> list[schemas.TraceEntryOut]:
    """Misma forma que la traza de la zapata: la UI no distingue tipologías."""
    return [trace_entry_to_dto(e) for e in trace.entries]


def _beam_min_steel_to_dto(m) -> schemas.BeamMinSteelOut:
    return schemas.BeamMinSteelOut(
        As_min_10_5_1_cm2=m.As_min_10_5_1_m2 * M2_TO_CM2,
        As_min_10_5_2_cm2=m.As_min_10_5_2_m2 * M2_TO_CM2,
        As_min_governing_cm2=m.As_min_governing_m2 * M2_TO_CM2,
        governed_by=m.governed_by,
        Mcr_kNm=m.Mcr_kNm, fr_MPa=m.fr_MPa,
        exempt_by_10_5_3=m.exempt_by_10_5_3,
        equation_substituted=m.equation_substituted,
    )


def _beam_shear_to_dto(s) -> schemas.BeamShearOut:
    lay = s.layout
    return schemas.BeamShearOut(
        Vu_kN=s.Vu_kN, phi=s.phi, Vc_kN=s.Vc_kN, phi_Vc_kN=s.phi_Vc_kN,
        Vs_required_kN=s.Vs_required_kN, Vs_max_kN=s.Vs_max_kN,
        Vs_exceeds_limit=s.Vs_exceeds_limit,
        stirrups_required=s.stirrups_required,
        av_min_required=s.av_min_required, av_min_exemption=s.av_min_exemption,
        Av_over_s_governing_cm2_m=s.Av_over_s_governing_m * 1e4,
        stirrup_label=(
            f"{lay.n_legs} ramas Ø{lay.bar_diameter_mm:.2f} mm @ {lay.spacing_m * 100:.1f} cm"
            if lay else None
        ),
        spacing_cm=lay.spacing_m * 100.0 if lay else None,
        spacing_limit_cm=lay.spacing_limit_m * 100.0 if lay else None,
        spacing_limit_reference=lay.spacing_limit_reference if lay else None,
        status_ok=s.status_ok, message=s.message, code_reference=s.code_reference,
    )


def _beam_axial_flexure_to_dto(c) -> schemas.BeamAxialFlexureOut | None:
    if c is None:
        return None
    punto = c.capacity_at_Pu
    return schemas.BeamAxialFlexureOut(
        Pu_kN=c.Pu_kN, Mu_kNm=c.Mu_kNm,
        Pn_max_kN=c.Pn_max_kN, phi_Pn_max_kN=c.phi_Pn_max_kN,
        P0_tension_kN=c.P0_tension_kN,
        phi_Mn_at_Pu_kNm=punto.phi_Mn_kNm if punto else None,
        phi_at_Pu=punto.phi if punto else None,
        demand_ratio=c.demand_ratio if math.isfinite(c.demand_ratio) else -1.0,
        inside_diagram=c.inside_diagram, axial_cap_ok=c.axial_cap_ok,
        status_ok=c.status_ok, message=c.message,
        equation_substituted=c.equation_substituted,
        code_reference=c.code_reference,
        diagram=[
            schemas.BeamInteractionPointOut(
                Pn_kN=p.Pn_kN, Mn_kNm=p.Mn_kNm, phi=p.phi,
                phi_Pn_kN=p.phi_Pn_kN, phi_Mn_kNm=p.phi_Mn_kNm,
            )
            for p in c.diagram
        ],
    )


def _beam_lateral_to_dto(l) -> schemas.BeamLateralRequirementsOut | None:
    if l is None:
        return None
    return schemas.BeamLateralRequirementsOut(
        applies=l.applies, section=l.section, system_label=l.system_label,
        reason=l.reason, disallows_10_5_3=l.disallows_10_5_3,
        positive_moment_ratio_at_joint=l.positive_moment_ratio_at_joint,
        max_tension_ratio=l.max_tension_ratio,
        min_clear_span_over_depth=l.min_clear_span_over_depth,
        min_width_over_depth=l.min_width_over_depth,
        not_implemented=list(l.not_implemented),
    )


def beam_result_to_dto(result, project_name: str, trace) -> schemas.BeamDesignResponse:
    """Traduce el resultado del motor de vigas al DTO. NO recalcula nada."""
    return schemas.BeamDesignResponse(
        project_name=project_name,
        b_m=result.b_m, h_m=result.h_m, d_m=result.d_m, clear_span_m=result.clear_span_m,
        status=result.status.value, messages=list(result.messages),
        dimension_required_mm=result.dimensional.min_dimension_required_m * 1000.0,
        dimension_provided_mm=result.dimensional.min_dimension_provided_m * 1000.0,
        dimension_ok=result.dimensional.ok,
        dimension_equation=result.dimensional.equation_substituted,
        Mu_negative_kNm=result.Mu_negative_kNm, Mu_positive_kNm=result.Mu_positive_kNm,
        As_negative_cm2=result.As_negative_m2 * M2_TO_CM2,
        As_positive_cm2=result.As_positive_m2 * M2_TO_CM2,
        min_steel_negative=_beam_min_steel_to_dto(result.min_steel_negative),
        min_steel_positive=_beam_min_steel_to_dto(result.min_steel_positive),
        shear=_beam_shear_to_dto(result.shear),
        confinement_limit_cm=result.confinement.spacing_limit_m * 100.0,
        confinement_provided_cm=(
            result.confinement.spacing_provided_m * 100.0
            if result.confinement.spacing_provided_m is not None else None
        ),
        confinement_governed_by=result.confinement.governed_by,
        confinement_ok=result.confinement.ok,
        axial_required=result.axial_required, axial_N_kN=result.axial_N_kN,
        axial_trigger_note=result.axial_trigger_note,
        axial_flexure_negative=_beam_axial_flexure_to_dto(result.axial_flexure_negative),
        axial_flexure_positive=_beam_axial_flexure_to_dto(result.axial_flexure_positive),
        lateral_requirements=_beam_lateral_to_dto(result.lateral_requirements),
        trace=beam_trace_to_dto(trace),
    )


def build_site_limits(dto: "schemas.SiteLimitsInput | None", units) -> SiteLimits | None:
    """Linderos del terreno en SI. None si no se declaró ninguno: el comportamiento de
    siempre, sin límites."""
    if dto is None:
        return None

    def m(v: float | None) -> float | None:
        return None if v is None else length_to_m(v, units.length)

    limites = SiteLimits(
        start_clearance_m=m(dto.start_clearance_m),
        end_clearance_m=m(dto.end_clearance_m),
        side_neg_clearance_m=m(dto.side_neg_clearance_m),
        side_pos_clearance_m=m(dto.side_pos_clearance_m),
    )
    if all(v is None for v in limites.model_dump().values()):
        return None
    return limites
