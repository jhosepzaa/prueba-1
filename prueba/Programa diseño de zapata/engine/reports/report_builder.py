"""Construcción del reporte a partir de resultados YA calculados.

No hay una sola ecuación en este módulo: solo lee el `FootingCandidate`, sus
entradas y el conjunto de alternativas, y los organiza en las 16 secciones.
"""

from __future__ import annotations

from datetime import datetime

from engine.domain.column import Column
from engine.domain.loads import LoadCaseSet
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters, GeometrySearchParameters
from engine.domain.soil import SoilProfile
from engine.optimization.alternative_generator import Alternative, AlternativeSet
from engine.reports.report_units import ReportUnits
from engine.reports.report_model import (
    TRACE_GROUPS,
    DiscardSummary,
    FootingReport,
    GoverningRow,
    HypothesisItem,
    LimitationItem,
    LoadCombinationRow,
    ReportRow,
    ReportTable,
    status_label,
)
from engine.results.limitations import LIMITATION_REGISTRY
from engine.results.status import CheckStatus

ENGINE_VERSION = "0.7.0"

CHECK_LABELS = {
    "contact_pressure": "Presión de contacto",
    "flexure_x": "Flexión dirección X",
    "flexure_y": "Flexión dirección Y",
    "shear_x": "Cortante unidireccional X",
    "shear_y": "Cortante unidireccional Y",
    "punching": "Punzonamiento",
    "development_x": "Longitud de desarrollo X",
    "development_y": "Longitud de desarrollo Y",
    "sliding": "Deslizamiento",
    "overturning_x": "Volcamiento eje X",
    "overturning_y": "Volcamiento eje Y",
    "min_depth": "Peralte mínimo",
}


def _f(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _combination_rows(load_case_set: LoadCaseSet, factored: bool) -> list[LoadCombinationRow]:
    source = load_case_set.factored if factored else load_case_set.service
    return [
        LoadCombinationRow(
            name=c.name, type=c.type.value, P_kN=c.P_kN, Mx_kNm=c.Mx_kNm, My_kNm=c.My_kNm,
            Hx_kN=c.Hx_kN, Hy_kN=c.Hy_kN, seismic=c.includes_seismic_loads,
        )
        for c in source
    ]


def _collect_hypotheses(alternative: Alternative) -> list[HypothesisItem]:
    """Reúne las hipótesis que el motor registró en cada verificación."""
    items: list[HypothesisItem] = []
    seen: set[str] = set()
    for entry in alternative.candidate.trace.entries:
        for text in entry.hypotheses:
            key = text.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(
                HypothesisItem(
                    text=key,
                    source=CHECK_LABELS.get(entry.id, entry.description),
                    is_normative_interpretation=(
                        "interpretación" in key.lower() or "no una certeza" in key.lower()
                    ),
                )
            )
    return items


def _rebar_tables(alternative: Alternative) -> list[ReportTable]:
    c = alternative.candidate
    tables: list[ReportTable] = []
    for direction, options, chosen in (
        ("X", c.rebar_options_x, c.rebar_x),
        ("Y", c.rebar_options_y, c.rebar_y),
    ):
        rows = [
            [
                o.label, str(o.n_bars),
                _f(o.As_required_m2 * 1e4), _f(o.As_min_m2 * 1e4), _f(o.As_provided_m2 * 1e4),
                f"{o.utilization * 100:.0f} %", o.governed_by,
                _f(o.ld_required_m * 1000, 0) if o.ld_required_m else "—",
                _f(o.ld_available_m * 1000, 0) if o.ld_available_m else "—",
            ]
            for o in options
        ]
        tables.append(
            ReportTable(
                title=(
                    f"Dirección {direction} — armado adoptado: "
                    f"{chosen.bar_designation} @ {chosen.spacing_m * 100:.1f} cm"
                ),
                headers=[
                    "Opción", "N.º barras", "As req. (cm²)", "As mín. (cm²)", "As prov. (cm²)",
                    "Utilización", "Gobierna", "ld req. (mm)", "ld disp. (mm)",
                ],
                rows=rows,
                note=(
                    "Solo se listan opciones cuya longitud de desarrollo cabe en el voladizo "
                    "disponible (E.060 §15.6 → Cap. 12)."
                ),
            )
        )
    return tables


def _short_direction_table(alternative: Alternative) -> ReportTable | None:
    sd = alternative.candidate.short_direction
    if sd is None:
        return None
    return ReportTable(
        title=f"Distribución en dirección corta — β = {sd.beta:.4f}, γs = {sd.gamma_s:.4f}",
        headers=["Franja", "Ancho (m)", "As asignado (cm²)", "As mínimo (cm²)", "Observación"],
        rows=[
            [
                b.name, _f(b.width_m), _f(b.As_required_m2 * 1e4), _f(b.As_min_m2 * 1e4),
                "Elevado al mínimo §9.7" if b.topped_up else "—",
            ]
            for b in sd.bands
        ],
        note=f"{sd.note} Referencia: {sd.code_reference}.",
    )


def _comparison_table(alternative_set: AlternativeSet, limit: int = 20) -> ReportTable:
    rows = [
        [
            a.id, _f(a.candidate.B_m), _f(a.candidate.L_m), _f(a.candidate.h_m),
            f"{a.candidate.rebar_x.bar_designation} @ {a.candidate.rebar_x.spacing_m * 100:.1f}",
            f"{a.candidate.rebar_y.bar_designation} @ {a.candidate.rebar_y.spacing_m * 100:.1f}",
            _f(a.candidate.contact_pressure.qmax_kPa, 1),
            _f(a.metrics.concrete_volume_m3, 3),
            _f(a.metrics.steel_mass_kg, 1),
            a.candidate.overall_status.value,
        ]
        for a in alternative_set.valid[:limit]
    ]
    note = (
        f"Se muestran {min(limit, len(alternative_set.valid))} de "
        f"{len(alternative_set.valid)} alternativas válidas."
    )
    return ReportTable(
        title="Alternativas válidas",
        headers=["ID", "B (m)", "L (m)", "h (m)", "Acero X", "Acero Y",
                 "q máx (kPa)", "V. concreto (m³)", "Acero (kg)", "Estado"],
        rows=rows,
        note=note,
    )


def _discards(alternative_set: AlternativeSet) -> list[DiscardSummary]:
    grouped: dict[str, list] = {}
    for item in alternative_set.discarded:
        if item.representative is None:
            continue
        for reason in item.representative.discard_reasons:
            grouped.setdefault(reason, []).append(item)
    return [
        DiscardSummary(
            reason=reason, count=len(items), example_id=items[0].id,
            example_geometry=f"B = {items[0].B_m:.2f} m, L = {items[0].L_m:.2f} m",
        )
        for reason, items in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    ]


def _conclusion(alternative: Alternative) -> str:
    c = alternative.candidate
    label = status_label(c.overall_status)
    base = (
        f"La alternativa {alternative.id} (B = {c.B_m:.2f} m, L = {c.L_m:.2f} m, "
        f"h = {c.h_m:.2f} m, d = {c.d_m:.3f} m) resulta {label}."
    )
    if c.overall_status is CheckStatus.FAIL:
        return base + " Motivos: " + " ".join(c.discard_reasons)
    if c.overall_status is CheckStatus.NOT_VERIFIED:
        pending = [e.description for e in c.trace.entries if e.status is CheckStatus.NOT_VERIFIED]
        return (
            base
            + " Existen verificaciones aplicables que NO pudieron ejecutarse por falta de datos: "
            + "; ".join(pending)
            + ". El resultado no puede considerarse conforme mientras esas verificaciones "
            "permanezcan sin realizar."
        )
    if c.overall_status is CheckStatus.WARNING:
        warnings = [e.description for e in c.trace.warning_entries()]
        return base + " Requiere revisión del ingeniero por: " + "; ".join(warnings) + "."
    return (
        base
        + " Todas las verificaciones aplicables se ejecutaron completas y cumplen los "
        "requisitos de las normas E.060 y E.050 implementados por el motor, dentro de las "
        "limitaciones declaradas en la sección 13."
    )


def build_report(
    alternative: Alternative,
    alternative_set: AlternativeSet,
    project_name: str,
    column: Column,
    concrete: MaterialConcrete,
    steel: MaterialSteel,
    soil: SoilProfile,
    load_case_set: LoadCaseSet,
    geometry_params: GeometrySearchParameters,
    depth_params: DepthSearchParameters,
    code_name: str,
    min_depth_interpretation: str,
    pass_conditions: list[str],
    cover_mm: float,
    elapsed_seconds: float,
    generated_at: datetime | None = None,
    units: ReportUnits | None = None,
) -> FootingReport:
    # `units` solo decide en qué unidad se ESCRIBE cada número (2026-09-23). Por
    # omisión son las SI del motor, que es como se emitía la memoria hasta esa fecha.
    u = units or ReportUnits()
    c = alternative.candidate
    trace_by_id = {e.id: e for e in c.trace.entries}

    groups = []
    for title, ids in TRACE_GROUPS:
        entries = [trace_by_id[i] for i in ids if i in trace_by_id]
        if entries:
            groups.append((title, entries))
    # Entradas que no encajan en ningún grupo (p. ej. limitaciones emitidas)
    placed = {i for _, ids in TRACE_GROUPS for i in ids}
    extra = [e for e in c.trace.entries if e.id not in placed]
    if extra:
        groups.append(("13b. Limitaciones y notas del motor", extra))

    return FootingReport(
        generated_at=generated_at or datetime.now(),
        engine_version=ENGINE_VERSION,
        units=u,
        code_name=code_name,
        project_name=project_name,
        alternative_id=alternative.id,
        alternative_rank=0,
        final_status=c.overall_status,
        column_rows=[
            ReportRow(label="Sección", value=column.shape),
            ReportRow(label="Dimensión bx", value=u.fmt(column.bx_m, "length"), unit=u.label("length")),
            ReportRow(label="Dimensión by", value=u.fmt(column.by_m, "length"), unit=u.label("length")),
        ],
        soil_rows=[
            ReportRow(label="Presión admisible", value=u.fmt(soil.qadm_kPa, "pressure"),
                      unit=u.label("pressure"), reference=f"Base {soil.pressure_basis.value}"),
            ReportRow(label="Peso unitario del suelo", value=u.fmt(soil.gamma_kNm3, "unit_weight"),
                      unit=u.label("unit_weight")),
            ReportRow(label="Profundidad de cimentación Df", value=u.fmt(soil.Df_m, "length"),
                      unit=u.label("length")),
            ReportRow(
                label="Coef. fricción suelo-concreto μ",
                value=_f(soil.mu_friction_soil_concrete, 3) if soil.mu_friction_soil_concrete is not None else "no declarado",
            ),
            ReportRow(
                label="FS deslizamiento adoptado",
                value=_f(soil.FS_sliding_required) if soil.FS_sliding_required is not None else "no declarado",
                reference="E.050 no lo prescribe para zapatas aisladas",
            ),
            ReportRow(
                label="FS volcamiento adoptado",
                value=_f(soil.FS_overturning_required) if soil.FS_overturning_required is not None else "no declarado",
                reference="E.050 no lo prescribe para zapatas aisladas",
            ),
            ReportRow(
                label="Cohesión",
                value=u.fmt(soil.cohesion_kPa, "pressure") if soil.cohesion_kPa is not None else "no declarada",
                unit=u.label("pressure"),
            ),
            ReportRow(label="Origen de los datos", value=soil.source_notes or "no indicado"),
        ],
        material_rows=[
            ReportRow(label="f'c", value=u.fmt(concrete.fc_MPa, "strength", 1), unit=u.label("strength"),
                      reference="E.060 §9.4: mínimo 17 MPa"),
            ReportRow(label="fy", value=u.fmt(steel.fy_MPa, "strength", 1), unit=u.label("strength"),
                      reference="E.060 §9.5: máximo 550 MPa"),
            ReportRow(label="Tipo de barra", value=steel.bar_type),
            ReportRow(label="Peso unitario del concreto", value=u.fmt(concrete.unit_weight_kNm3, "unit_weight"),
                      unit=u.label("unit_weight")),
            ReportRow(label="Recubrimiento", value=_f(cover_mm, 0), unit="mm", reference="E.060 §7.7.1 a)"),
        ],
        service_combinations=_combination_rows(load_case_set, factored=False),
        factored_combinations=_combination_rows(load_case_set, factored=True),
        combinations_note=(
            "Las combinaciones de SERVICIO dimensionan la zapata frente al suelo (E.060 §15.2 y "
            "E.050 art. 17.1); las FACTORIZADAS diseñan el elemento de concreto. El motor las "
            "mantiene separadas y nunca las mezcla."
        ),
        hypotheses=_collect_hypotheses(alternative),
        geometry_rows=[
            ReportRow(label="Ancho B (eje X)", value=u.fmt(c.B_m, "length"), unit=u.label("length")),
            ReportRow(label="Largo L (eje Y)", value=u.fmt(c.L_m, "length"), unit=u.label("length")),
            ReportRow(label="Peralte total h", value=u.fmt(c.h_m, "length"), unit=u.label("length")),
            ReportRow(label="Peralte efectivo d", value=u.fmt(c.d_m, "length", 4), unit=u.label("length"),
                      reference="Capa superior de la parrilla (criterio conservador)"),
            ReportRow(label="Área en planta", value=_f(alternative.metrics.footing_area_m2, 3), unit="m²"),
            ReportRow(label="Volumen de concreto", value=_f(alternative.metrics.concrete_volume_m3, 3), unit="m³"),
            ReportRow(label="Masa de acero", value=_f(alternative.metrics.steel_mass_kg, 1), unit="kg",
                      reference="Longitud recta; sin ganchos ni traslapes"),
            ReportRow(label="Volumen de excavación", value=_f(alternative.metrics.excavation_volume_m3, 3), unit="m³"),
        ],
        trace_groups=groups,
        eccentricity_rows=[
            ReportRow(label="Excentricidad ex", value=u.fmt(c.eccentricity_governing.ex_m, "length", 4),
                      unit=u.label("length")),
            ReportRow(label="Excentricidad ey", value=u.fmt(c.eccentricity_governing.ey_m, "length", 4),
                      unit=u.label("length")),
            ReportRow(label="q máximo", value=u.fmt(c.contact_pressure.qmax_kPa, "pressure"),
                      unit=u.label("pressure")),
            ReportRow(label="q mínimo", value=u.fmt(c.contact_pressure.qmin_kPa, "pressure"),
                      unit=u.label("pressure")),
            ReportRow(label="q promedio", value=u.fmt(c.contact_pressure.qavg_kPa, "pressure"),
                      unit=u.label("pressure")),
            ReportRow(
                label="Resultante dentro del núcleo central",
                value="Sí" if c.contact_pressure.within_kern else "No",
                reference="E.060 §15.2: no se consideran tracciones",
            ),
            ReportRow(label="Modelo de contacto", value=c.contact_pressure.model_name),
        ],
        rebar_tables=_rebar_tables(alternative),
        short_direction_table=_short_direction_table(alternative),
        governing_combinations=[
            GoverningRow(
                check=CHECK_LABELS.get(e.id, e.description),
                combination=e.governing_combo,
                status=e.status,
            )
            for e in c.trace.entries
            if e.governing_combo
        ],
        limitations=[
            LimitationItem(
                title=l.title, kind=l.kind.value, code_reference=l.code_reference,
                impact=l.impact, can_cause_false_pass=l.can_cause_false_pass,
            )
            for l in LIMITATION_REGISTRY
        ],
        conclusion=_conclusion(alternative),
        pass_conditions=pass_conditions,
        discarded=_discards(alternative_set),
        discard_note=(
            f"De {alternative_set.n_geometries_evaluated} geometrías evaluadas, "
            f"{len(alternative_set.valid)} resultaron válidas y "
            f"{len(alternative_set.discarded)} fueron descartadas por los motivos siguientes."
        ),
        comparison=_comparison_table(alternative_set),
        search_rows=[
            ReportRow(label="Rango de B", value=f"{_f(geometry_params.B_min_m)} – {_f(geometry_params.B_max_m)}",
                      unit="m", reference=f"incremento {_f(geometry_params.B_step_m)} m"),
            ReportRow(label="Rango de L", value=f"{_f(geometry_params.L_min_m)} – {_f(geometry_params.L_max_m)}",
                      unit="m", reference=f"incremento {_f(geometry_params.L_step_m)} m"),
            ReportRow(label="Rango de h", value=f"{_f(depth_params.h_min_m)} – {_f(depth_params.h_max_m)}",
                      unit="m", reference=f"incremento {_f(depth_params.h_step_m)} m"),
            ReportRow(label="Relación L/B máxima", value=_f(geometry_params.max_LB_ratio)),
            ReportRow(label="Gancho declarado en X", value=depth_params.hook_type_x),
            ReportRow(label="Gancho declarado en Y", value=depth_params.hook_type_y),
            ReportRow(label="Interpretación de E.060 §15.7", value=min_depth_interpretation,
                      reference="Interpretación adoptada, no certeza normativa"),
        ],
        summary_rows=[
            ReportRow(label="Geometrías evaluadas", value=str(alternative_set.n_geometries_evaluated)),
            ReportRow(label="Alternativas válidas", value=str(len(alternative_set.valid))),
            ReportRow(label="Alternativas descartadas", value=str(len(alternative_set.discarded))),
            ReportRow(label="Tiempo de cálculo", value=_f(elapsed_seconds, 2), unit="s"),
        ],
    )
