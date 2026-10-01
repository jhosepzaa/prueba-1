"""Servidor FastAPI — expone el motor sin contener ninguna ecuación de ingeniería.

Arranque:
    py -m uvicorn api.server:app --reload --port 8000

La UI consume estos endpoints. El motor se puede seguir usando sin la API
(los 306 tests lo hacen), que es el requisito de independencia de la sección 18.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, OrderedDict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import ValidationError

from api import mapping, schemas, unit_fields
from engine.codes.peru.rebar_catalog_peru import REBAR_CATALOG
from engine.optimization.alternative_generator import generate_alternatives
from engine.optimization.discard_explainer import explain_discarded
from engine.optimization.pareto import PARETO_OBJECTIVES
from engine.foundation.geometry_generator import pruning_note
from engine.optimization.search_boundary import describe_boundary
from engine.optimization.ranker import rank_alternatives
from engine.reports.html_renderer import render_report_html
from engine.reports.report_builder import build_report
from engine.reports.report_units import ReportUnits
from engine.results.status import CheckStatus
from engine.domain.search_parameters import GeometrySearchParameters
from engine.units.unit_registry import ROUNDING_NOTE, available_units, length_to_m
from engine.visualization.scene_dto import build_footing_scene
from engine.soil.stability import (
    FS_REFERENCE_NOTE,
    FS_REFERENCE_RETAINING_WALL_PSEUDOSTATIC,
    FS_REFERENCE_RETAINING_WALL_STATIC,
)

app = FastAPI(
    title="Diseño de cimentaciones — E.060 / E.050 / E.030",
    description=(
        "Motor de diseño, verificación y optimización de cimentaciones de concreto "
        "armado para el RNE peruano: zapata aislada, zapata combinada, cimentación "
        "conectada con viga y viga de conexión."
    ),
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_GEOMETRIES = 5000  # cota de seguridad para no colgar el servidor


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/typologies")
def typologies() -> dict:
    """Catálogo de tipologías: endpoints, criterio de aceptación, vocabulario, capacidades,
    pendientes abiertos y diferencias conocidas entre ellas. Punto de partida de la
    integración global; ver `engine/integration/typology_catalog.py`."""
    from engine.integration.typology_catalog import CATALOG

    return CATALOG.model_dump(mode="json")


@app.get("/api/reference")
def reference() -> dict:
    """Catálogos y notas que la UI muestra pero no calcula."""
    return {
        "rebar_catalog": [
            {"designation": b.designation, "diameter_mm": b.diameter_mm, "area_mm2": b.area_mm2}
            for b in REBAR_CATALOG
        ],
        "pareto_objectives": sorted(PARETO_OBJECTIVES),
        "units": available_units(),
        "limitations": [l.model_dump() for l in mapping.limitations_to_dto()],
        "pass_conditions": mapping.PASS_CONDITIONS,
        "fs_reference": {
            "static": FS_REFERENCE_RETAINING_WALL_STATIC,
            "pseudostatic": FS_REFERENCE_RETAINING_WALL_PSEUDOSTATIC,
            "note": FS_REFERENCE_NOTE,
        },
        "code_notes": {
            "cover": "E.060 §7.7.1 a): 75 mm para concreto colocado contra el suelo.",
            "phi_flexure": "E.060 §9.4: φ = 0.90 (flexión sin carga axial).",
            "phi_shear": "E.060 §9.4: φ = 0.85 (cortante y torsión).",
            "min_depth": "E.060 §15.7: 300 mm — interpretación adoptada sobre d, parametrizable.",
            "as_min": "E.060 §9.7 vía §10.6; §10.5.1 excluye zapatas del criterio Mcr.",
            "service_loads": "E.060 §15.2 y E.050 art. 17.1: geometría con cargas de SERVICIO.",
        },
        "rounding_note": ROUNDING_NOTE,
    }


# --- Cambio de unidades (2026-09-23) -------------------------------------------
# La interfaz no convierte por su cuenta: cuando el usuario cambia una unidad,
# manda la petición entera y la recibe reescrita. El mapa de magnitudes está en
# `api/unit_fields.py` y la aritmética en `engine/units/unit_registry.py`, que es
# donde ya vivía. Así la conversión sigue teniendo UNA sola implementación, cubierta
# por tests, y el valor físico del dato no cambia al cambiar de unidad.

_PETICIONES_CON_UNIDADES: dict[str, type] = {
    "aislada": schemas.DesignRequest,
    "combinada": schemas.CombinedDesignRequest,
    "conectada": schemas.ConnectedDesignRequest,
    "viga": schemas.BeamDesignRequest,
}


@app.post("/api/units/rewrite")
def rewrite_units_endpoint(payload: schemas.UnitsRewriteRequest) -> dict:
    """Devuelve la misma petición con sus números expresados en otras unidades."""
    modelo = _PETICIONES_CON_UNIDADES.get(payload.typology)
    if modelo is None:
        raise HTTPException(
            422,
            f'Tipología desconocida: "{payload.typology}". '
            f'Disponibles: {", ".join(sorted(_PETICIONES_CON_UNIDADES))}.',
        )
    try:
        peticion = modelo.model_validate(payload.request)
        reescrita = unit_fields.rewrite_units(peticion, payload.units)
    except ValidationError as exc:
        raise HTTPException(422, f"La petición no es válida: {exc.error_count()} errores.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"request": reescrita.model_dump(mode="json"), "rounding_note": ROUNDING_NOTE}


def _estimate_geometry_count(g: GeometrySearchParameters) -> int:
    nb = max(int((g.B_max_m - g.B_min_m) / g.B_step_m) + 1, 1)
    nl = max(int((g.L_max_m - g.L_min_m) / g.L_step_m) + 1, 1)
    return nb * nl


@app.post("/api/design", response_model=schemas.DesignResponse)
def design(request: schemas.DesignRequest) -> schemas.DesignResponse:
    if not request.combinations and not request.load_cases:
        raise HTTPException(422, "Debe definir al menos una combinación de carga o casos de carga.")

    try:
        code = mapping.build_code(request)
        placement = mapping.build_placement(request.column, request.units)
        column = placement.column
        concrete, steel = mapping.build_materials(request.materials, request.units)
        soil = mapping.build_soil(request.soil, request.units)
        loads = mapping.build_loads(
            request.combinations, request.units, request.load_cases, request.combination_definitions
        )
        geometry_params, depth_params, auto_range = mapping.build_search(
            request.search, request.units, loads, soil, column
        )
        weights = mapping.build_weights(request.weights)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(
            422,
            detail={
                "error": "Datos de entrada inválidos",
                "detail": first.get("msg", str(exc)),
                "field": ".".join(str(x) for x in first.get("loc", [])),
            },
        )
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)})

    estimated = _estimate_geometry_count(geometry_params)
    if estimated > MAX_GEOMETRIES:
        raise HTTPException(
            422,
            f"La malla de búsqueda genera ~{estimated} geometrías (máximo {MAX_GEOMETRIES}). "
            f"Aumente el incremento o reduzca el rango.",
        )

    input_warnings = [
        schemas.InputWarningOut(field=w.field, value=w.value, message=w.message)
        for source in (concrete, steel, soil, column)
        for w in source.plausibility_warnings()
    ]

    started = time.perf_counter()
    result = generate_alternatives(
        column=column, placement=placement, soil=soil, concrete=concrete, steel=steel,
        load_case_set=loads, code=code, contact_model=mapping.contact_model_for(request.soil),
        geometry_params=geometry_params, depth_params=depth_params,
    )
    ranking = rank_alternatives(result, weights, top_n=request.top_n)
    elapsed = time.perf_counter() - started

    pareto_ids = {a.id for a in ranking.pareto.front}
    score_by_id = {s.alternative.id: s for s in ranking.all_scored}

    top: list[schemas.AlternativeDetailOut] = []
    for scored in ranking.top:
        alt, c, m = scored.alternative, scored.alternative.candidate, scored.alternative.metrics
        cover_mm = (
            depth_params.cover_override_mm
            if depth_params.cover_override_mm is not None
            else code.cover_footing_mm()[0]
        )
        top.append(
            schemas.AlternativeDetailOut(
                id=alt.id, rank=scored.rank, score=scored.score, status=c.overall_status.value,
                B_m=c.B_m, L_m=c.L_m, h_m=c.h_m, d_m=c.d_m, cover_mm=cover_mm,
                concrete_volume_m3=m.concrete_volume_m3, steel_mass_kg=m.steel_mass_kg,
                footing_area_m2=m.footing_area_m2, excavation_volume_m3=m.excavation_volume_m3,
                constructive_complexity=m.constructive_complexity_index,
                score_breakdown={
                    k: {
                        "raw": b.raw_value, "normalized": b.normalized,
                        "weight": b.weight, "contribution": b.contribution,
                    }
                    for k, b in scored.breakdown.items()
                },
                self_weight_kN=c.self_weight.W_total_kN,
                qmax_kPa=c.contact_pressure.qmax_kPa, qmin_kPa=c.contact_pressure.qmin_kPa,
                qavg_kPa=c.contact_pressure.qavg_kPa, within_kern=c.contact_pressure.within_kern,
                ex_m=c.eccentricity_governing.ex_m, ey_m=c.eccentricity_governing.ey_m,
                Mu_x_kNm=c.flexure_x.Mu_kNm, Mu_y_kNm=c.flexure_y.Mu_kNm,
                As_req_x_cm2=c.flexure_x.As_required_m2 * mapping.M2_TO_CM2,
                As_req_y_cm2=c.flexure_y.As_required_m2 * mapping.M2_TO_CM2,
                As_min_x_cm2=c.flexure_x.As_min_m2 * mapping.M2_TO_CM2,
                As_min_y_cm2=c.flexure_y.As_min_m2 * mapping.M2_TO_CM2,
                shear_x_ratio=c.shear_x.ratio, shear_y_ratio=c.shear_y.ratio,
                punching_ratio=c.punching.ratio,
                punching_governing_equation=c.punching.governing_equation,
                punching_bo_m=c.punching.bo_m,
                punching_has_moment_transfer=c.punching.moment_transfer is not None,
                punching_amplification=(
                    c.punching.moment_transfer.amplification_factor if c.punching.moment_transfer else None
                ),
                rebar_x_label=f"{c.rebar_x.bar_designation} @ {c.rebar_x.spacing_m * 100:.1f} cm",
                rebar_y_label=f"{c.rebar_y.bar_designation} @ {c.rebar_y.spacing_m * 100:.1f} cm",
                rebar_options_x=[mapping.rebar_option_to_dto(o) for o in c.rebar_options_x],
                rebar_options_y=[mapping.rebar_option_to_dto(o) for o in c.rebar_options_y],
                short_direction=mapping.short_direction_to_dto(c),
                stability=mapping.stability_to_dto(c),
                scene=schemas.FootingSceneOut.model_validate(
                    build_footing_scene(
                        alternative_id=alt.id,
                        status=c.overall_status,
                        B_m=c.B_m, L_m=c.L_m, h_m=c.h_m, d_m=c.d_m,
                        cover_m=cover_mm / 1000.0,
                        column_bx_m=column.bx_m, column_by_m=column.by_m,
                        column_offset_x_m=placement.offset_x_m,
                        column_offset_y_m=placement.offset_y_m,
                        rebar_geometry=c.rebar_geometry,
                        designation_x=c.rebar_x.bar_designation,
                        designation_y=c.rebar_y.bar_designation,
                        label_x=f"{c.rebar_x.bar_designation} @ {c.rebar_x.spacing_m * 100:.1f} cm",
                        label_y=f"{c.rebar_y.bar_designation} @ {c.rebar_y.spacing_m * 100:.1f} cm",
                    ).model_dump()
                ),
                governing_combos=c.governing_combos.model_dump(),
                trace=mapping.trace_to_dto(c),
                discard_reasons=c.discard_reasons,
            )
        )

    table = [
        schemas.ComparisonRowOut(
            id=a.id,
            rank=score_by_id[a.id].rank if a.id in score_by_id else None,
            B_m=a.candidate.B_m, L_m=a.candidate.L_m, h_m=a.candidate.h_m, d_m=a.candidate.d_m,
            steel_x=f"{a.candidate.rebar_x.bar_designation} @ {a.candidate.rebar_x.spacing_m * 100:.1f} cm",
            steel_y=f"{a.candidate.rebar_y.bar_designation} @ {a.candidate.rebar_y.spacing_m * 100:.1f} cm",
            qmax_kPa=a.candidate.contact_pressure.qmax_kPa,
            concrete_volume_m3=a.metrics.concrete_volume_m3,
            steel_mass_kg=a.metrics.steel_mass_kg,
            max_dimension_m=a.metrics.max_plan_dimension_m,
            complexity=a.metrics.constructive_complexity_index,
            score=score_by_id[a.id].score if a.id in score_by_id else None,
            status=a.candidate.overall_status.value,
            in_pareto=a.id in pareto_ids,
        )
        for a in result.valid
    ]

    # Descartes agrupados por motivo, con un ejemplo explicado de cada grupo.
    grouped: dict[str, list] = {}
    for item in result.discarded:
        if item.representative is None:
            continue
        for reason in item.representative.discard_reasons:
            grouped.setdefault(reason, []).append(item)
    discarded = []
    for reason, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        sample = items[0]
        discarded.append(
            schemas.DiscardGroupOut(
                reason=reason, count=len(items), example_id=sample.id,
                example_B_m=sample.B_m, example_L_m=sample.L_m,
                example_explanation=explain_discarded(sample).to_text(),
            )
        )

    # ¿La alternativa recomendada quedó pegada al borde de lo que se exploró? El barrido
    # solo puede elegir entre lo que miró, y presentar como mejor la que está contra el
    # límite sin decirlo oculta que fuera puede haber algo mejor (2026-09-24).
    elegida = ranking.best()
    mejor = elegida.alternative.candidate if elegida else None
    _, aviso_borde = describe_boundary(
        [
            ("B", mejor.B_m if mejor else None,
             geometry_params.B_min_m, geometry_params.B_max_m, geometry_params.B_step_m),
            ("L", mejor.L_m if mejor else None,
             geometry_params.L_min_m, geometry_params.L_max_m, geometry_params.L_step_m),
            ("el peralte h", mejor.h_m if mejor else None,
             depth_params.h_min_m, depth_params.h_max_m, depth_params.h_step_m, False),
        ]
    )

    return schemas.DesignResponse(
        summary=schemas.DesignSummaryOut(
            project_name=request.project_name,
            n_evaluated=result.n_geometries_evaluated,
            n_valid=len(result.valid),
            n_discarded=len(result.discarded),
            pareto_size=ranking.pareto.front_size,
            elapsed_seconds=elapsed,
            code_name=code.code_name,
            min_depth_interpretation=code.min_depth_interpretation.value,
            status_histogram=dict(
                Counter(a.candidate.overall_status.value for a in result.valid)
            ),
            search_range_note=auto_range.note if auto_range else "",
            pruned_by_LB_ratio=result.pruned_by_LB_ratio,
            pruned_note=pruning_note(result.pruned_by_LB_ratio, geometry_params.max_LB_ratio),
            search_boundary_note=aviso_borde,
            effective_search_range={
                "B_min_m": geometry_params.B_min_m, "B_max_m": geometry_params.B_max_m,
                "L_min_m": geometry_params.L_min_m, "L_max_m": geometry_params.L_max_m,
                "h_min_m": depth_params.h_min_m, "h_max_m": depth_params.h_max_m,
            },
        ),
        top=top,
        table=table,
        discarded=discarded,
        limitations=mapping.limitations_to_dto(),
        input_warnings=input_warnings,
        pass_conditions=mapping.PASS_CONDITIONS,
    )


class ReportRequest(schemas.DesignRequest):
    """Igual que el diseño, más cuál alternativa reportar."""

    alternative_id: str | None = None


@app.post("/api/report", response_class=HTMLResponse)
def report(request: ReportRequest) -> HTMLResponse:
    """Memoria de cálculo en HTML autocontenido y listo para imprimir.

    No se genera PDF en el servidor: WeasyPrint requiere bibliotecas GTK/Pango
    ausentes en este entorno. El HTML lleva CSS @media print y el usuario obtiene
    el PDF con Ctrl+P → «Guardar como PDF», sin dependencias nativas.
    """
    if not request.combinations and not request.load_cases:
        raise HTTPException(422, "Debe definir al menos una combinación de carga o casos de carga.")

    try:
        code = mapping.build_code(request)
        placement = mapping.build_placement(request.column, request.units)
        column = placement.column
        concrete, steel = mapping.build_materials(request.materials, request.units)
        soil = mapping.build_soil(request.soil, request.units)
        loads = mapping.build_loads(
            request.combinations, request.units, request.load_cases, request.combination_definitions
        )
        geometry_params, depth_params, auto_range = mapping.build_search(
            request.search, request.units, loads, soil, column
        )
        weights = mapping.build_weights(request.weights)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)})

    started = time.perf_counter()
    result = generate_alternatives(
        column=column, placement=placement, soil=soil, concrete=concrete, steel=steel,
        load_case_set=loads, code=code, contact_model=mapping.contact_model_for(request.soil),
        geometry_params=geometry_params, depth_params=depth_params,
    )
    ranking = rank_alternatives(result, weights, top_n=max(request.top_n, 1))
    elapsed = time.perf_counter() - started

    if not ranking.top:
        raise HTTPException(
            422,
            detail={
                "error": "Sin alternativas válidas",
                "detail": "No hay ninguna alternativa que reportar: todas las geometrías fueron descartadas.",
            },
        )

    chosen = ranking.top[0]
    if request.alternative_id:
        match = next((s for s in ranking.all_scored if s.alternative.id == request.alternative_id), None)
        if match is None:
            raise HTTPException(404, f"La alternativa {request.alternative_id} no está entre las válidas.")
        chosen = match

    cover_mm = (
        depth_params.cover_override_mm
        if depth_params.cover_override_mm is not None
        else code.cover_footing_mm()[0]
    )
    built = build_report(
        alternative=chosen.alternative, alternative_set=result,
        project_name=request.project_name, column=column, concrete=concrete, steel=steel,
        soil=soil, load_case_set=loads, geometry_params=geometry_params,
        depth_params=depth_params, code_name=code.code_name,
        min_depth_interpretation=code.min_depth_interpretation.value,
        pass_conditions=mapping.PASS_CONDITIONS, cover_mm=cover_mm,
        elapsed_seconds=elapsed,
        units=ReportUnits.from_input(request.units),
    )
    built.alternative_rank = chosen.rank
    return HTMLResponse(content=render_report_html(built))


# --- Servir la UI compilada, si existe -------------------------------------------
_UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"
if _UI_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_UI_DIST / "assets"), name="assets")

    @app.get("/")
    def serve_index() -> FileResponse:
        return FileResponse(_UI_DIST / "index.html")


# =========================================================================
# Zapata combinada — Fase 2
# =========================================================================


def _face_out(cara, direccion: str) -> schemas.CombinedFaceOut:
    rb = cara.rebar
    return schemas.CombinedFaceOut(
        face=cara.face, Mu_kNm=cara.Mu_kNm, x_m=cara.x_m, d_m=cara.d_m, cover_m=cara.cover_m,
        As_design_cm2=cara.As_design_m2 * 1e4, min_governed_by=cara.min_governed_by,
        bar_designation=rb.bar_designation if rb else None,
        spacing_m=rb.spacing_m if rb else None,
        ld_required_m=rb.ld_required_m if rb else None,
        ld_available_m=rb.ld_available_m if rb else None,
        development_ok=rb.development_ok if rb else None,
        status=(rb.status if rb else cara.status).value,
    )


@app.post("/api/design-combined", response_model=schemas.CombinedDesignResponse)
def design_combined(request: schemas.CombinedDesignRequest) -> schemas.CombinedDesignResponse:
    """Diseño de zapata combinada (E.060 §15.10).

    El recubrimiento de la cara superior es obligatorio: la tabla de §7.7.1 no da un
    valor único para esa cara."""
    from engine.analysis.beam_diagram import length_to_center_resultant
    from engine.optimization.combined_generator import (
        ColumnSpec,
        CombinedSearchParameters,
        build_layout,
        generate_combined_alternatives,
        rank_combined_alternatives,
    )
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.column import Column
    from engine.reinforcement.face_reinforcement import TopCoverDeclaration
    from engine.results.vocabulary import status_label
    from engine.soil.eccentricity import AXIS_CONVENTION_NOTE

    try:
        if len(request.columns) < 2:
            raise ValueError(
                "Una zapata combinada soporta más de una columna (E.060 §15.10.1). "
                "Para una sola columna use /api/design."
            )

        units = request.units
        soil = mapping.build_soil(request.soil, units)
        concrete, steel = mapping.build_materials(request.materials, units)

        top_cover = TopCoverDeclaration(
            case=request.top_cover.case,
            explicit_mm=request.top_cover.explicit_mm,
        )
        # Se resuelve aquí para que el error sea claro y no aparezca dentro del barrido.
        top_cover.resolve_mm()

        specs = [
            ColumnSpec(
                label=c.label,
                column=Column(
                    shape=c.shape,
                    bx_m=length_to_m(c.bx_m, units.length),
                    by_m=length_to_m(c.by_m, units.length),
                ),
                distance_from_first_m=length_to_m(c.distance_from_first_m, units.length),
                transverse_offset_m=length_to_m(c.transverse_offset_m, units.length),
                loads=mapping.build_loads(c.combinations, units, c.load_cases, request.combination_definitions),
            )
            for c in request.columns
        ]

        s = request.search
        limites = mapping.build_site_limits(request.site_limits, units)
        # Rangos: los del proyectista, o los que estima el motor (2026-09-28).
        automatico = s.auto_ranges or any(
            v is None for v in (s.length_min_m, s.length_max_m, s.width_min_m, s.width_max_m)
        )
        nota_auto = ""
        borde_declarado = (
            None if s.first_column_edge_distance_m is None
            else length_to_m(s.first_column_edge_distance_m, units.length)
        )
        if not automatico:
            rangos = dict(
                length_min_m=length_to_m(s.length_min_m, units.length),
                length_max_m=length_to_m(s.length_max_m, units.length),
                length_step_m=length_to_m(s.length_step_m, units.length),
                width_min_m=length_to_m(s.width_min_m, units.length),
                width_max_m=length_to_m(s.width_max_m, units.length),
                width_step_m=length_to_m(s.width_step_m, units.length),
                h_min_m=length_to_m(s.h_min_m, units.length),
                h_max_m=length_to_m(s.h_max_m, units.length),
                h_step_m=length_to_m(s.h_step_m, units.length),
            )

        def _barrer(campos: dict):
            p = CombinedSearchParameters(
                **campos,
                first_column_edge_distance_m=borde_declarado,
                longitudinal_direction=s.longitudinal_direction,
                site_limits=limites,
            )
            return p, generate_combined_alternatives(
                specs, p, soil=soil, concrete=concrete, steel=steel,
                code=E060ConcreteCode(), contact_model=mapping.contact_model_for(request.soil),
                top_cover=top_cover,
            )

        if automatico:
            # Estimación y dos pasadas, en el motor (engine/optimization/auto_search.py).
            from engine.optimization.auto_search import auto_combined_search

            resultado, rangos, nota_auto = auto_combined_search(
                specs, soil, s.longitudinal_direction, limites,
                lambda campos: _barrer(campos)[1], rank_combined_alternatives,
            )
            # Los rangos de la pasada que se entrega: contra ellos se mide el aviso de borde.
            params = CombinedSearchParameters(
                **rangos, first_column_edge_distance_m=borde_declarado,
                longitudinal_direction=s.longitudinal_direction, site_limits=limites,
            )
        else:
            params, resultado = _barrer(rangos)
        if nota_auto:
            resultado.search_note = (nota_auto + " " + resultado.search_note).strip()

        # Ayuda de predimensionamiento: la longitud que centra la resultante.
        #
        # QUÉ COMBINACIÓN LA GOBIERNA (2026-09-24). Antes se tomaba `service[0]`, la
        # primera de la lista, fuera cual fuera. Ahora se elige explícitamente la primera
        # SIN sismo ni viento, y se dice cuál es:
        #
        # centrar es un criterio de estado PERMANENTE. El sismo se invierte —en el caso
        # de Aragón, S2 y S3 mueven la resultante en sentidos opuestos—, de modo que
        # centrar para uno descentra el otro y empeora el estado que sí es permanente.
        # Lo que la norma exige (ausencia de tracciones y presión admisible) se verifica
        # después para TODAS las combinaciones; esto solo dice por dónde empezar.
        #
        # La dispersión entre combinaciones se informa para que el proyectista vea cuánto
        # se mueve la resultante con el sismo.
        centrados = []
        # Con la posición automática no hay un extremo fijo desde el que medir: el propio
        # barrido ya centra la resultante en cada longitud. La ayuda no aplica.
        for indice, combo in (
            enumerate(specs[0].loads.service) if params.first_column_edge_distance_m is not None else ()
        ):
            candidato = length_to_center_resultant(
                column_positions_m=[sp.distance_from_first_m for sp in specs],
                column_loads_kN=[sp.loads.service[indice].P_kN for sp in specs],
                column_moments_kNm=[sp.loads.service[indice].Mx_kNm for sp in specs],
                start_offset_m=params.first_column_edge_distance_m,
            )
            centrados.append((combo, candidato))

        centrado = None
        if centrados:
            permanentes = [
                (c, v) for c, v in centrados
                if not c.includes_seismic_loads and not c.includes_wind_loads
            ]
            elegido, centrado = (permanentes or centrados)[0]
            centrado.note = f"[{elegido.name}] {centrado.note}"
            if not permanentes:
                centrado.note += (
                    " ATENCIÓN: ninguna combinación de servicio es puramente gravitatoria, "
                    "de modo que esta longitud centra un estado transitorio."
                )
            if len(centrados) > 1:
                largos = [v.length_m for _, v in centrados]
                centrado.note += (
                    f" Con las {len(centrados)} combinaciones de servicio declaradas, la "
                    f"longitud de centrado va de {min(largos):.2f} a {max(largos):.2f} m: "
                    f"centrar es un criterio de estado permanente y el sismo, que se "
                    f"invierte, no puede centrarse en los dos sentidos a la vez."
                )

        # Ordenamiento por el MISMO núcleo de puntuación que la zapata aislada,
        # no por volumen a secas: así las dos tipologías no divergen de criterio.
        ordenadas = rank_combined_alternatives(resultado.valid)
        mejores = [s.alternative for s in ordenadas][: request.top_n]

        # Tabla comparativa y frente de Pareto con el MISMO núcleo que las otras dos
        # tipologías. Opera sobre las alternativas que el barrido ya acepta.
        from engine.optimization.pareto import DEFAULT_OBJECTIVES, pareto_mask

        mascara = pareto_mask([s.alternative.metrics for s in ordenadas], DEFAULT_OBJECTIVES)
        comparacion = [
            schemas.CombinedComparisonRowOut(
                id=s.alternative.id, length_m=s.alternative.length_m,
                width_m=s.alternative.width_m, h_m=s.alternative.h_m,
                first_column_edge_distance_m=s.alternative.first_column_edge_distance_m,
                transverse_shift_m=s.alternative.transverse_shift_m,
                concrete_volume_m3=s.alternative.metrics.concrete_volume_m3,
                steel_mass_kg=s.alternative.metrics.steel_mass_kg,
                footing_area_m2=s.alternative.metrics.footing_area_m2,
                max_plan_dimension_m=s.alternative.metrics.max_plan_dimension_m,
                score=s.score,
                status=s.alternative.result.overall_status.value,
                status_label=status_label(s.alternative.result.overall_status),
                in_pareto=en_frente,
            )
            for s, en_frente in zip(ordenadas, mascara)
        ]
        def _stability_out(r) -> "schemas.CombinedStabilityOut | None":
            """Transporta lo que el motor ya calculó. No reinterpreta ningún estado."""
            from engine.foundation.combined_stability import D10_2B_ADOPTED_NOTE, ENVELOPE_NOTE

            if r.stability is None:
                return None
            filas = []
            for clave, res in (("sliding", r.stability.sliding),
                               ("overturning_x", r.stability.overturning_x),
                               ("overturning_y", r.stability.overturning_y)):
                filas.append(schemas.CombinedStabilityCheckOut(
                    check=clave, status=res.status.value,
                    FS_obtained=res.FS_obtained, FS_required=res.FS_required,
                    governing_combo=res.governing_combo, message=res.message,
                    code_reference=res.code_reference,
                    missing_parameters=list(res.missing_parameters),
                    envelope_reading=getattr(res, "envelope_reading", None),
                ))
            return schemas.CombinedStabilityOut(
                applicable=r.stability.applicable, status=r.stability.status.value,
                checks=filas, criterion_note=f"{D10_2B_ADOPTED_NOTE} {ENVELOPE_NOTE}",
            )

        salida = [
            schemas.CombinedAlternativeOut(
                id=a.id, length_m=a.length_m, width_m=a.width_m, h_m=a.h_m,
                first_column_edge_distance_m=a.first_column_edge_distance_m,
                transverse_shift_m=a.transverse_shift_m,
                concrete_volume_m3=a.concrete_volume_m3,
                longitudinal_direction=a.result.longitudinal_direction,
                M_positive_kNm=a.result.diagram.M_max_positive_kNm,
                M_negative_kNm=a.result.diagram.M_max_negative_kNm,
                has_top_steel=a.result.top_face is not None,
                bottom_face=_face_out(a.result.bottom_face, a.result.longitudinal_direction),
                top_face=(
                    _face_out(a.result.top_face, a.result.longitudinal_direction)
                    if a.result.top_face else None
                ),
                punching=[
                    schemas.CombinedPunchingOut(
                        column_label=col.label,
                        column_position=p.column_position,
                        critical_section_sides=p.critical_section_sides,
                        alpha_s=p.alpha_s, ratio=p.ratio, status=p.status.value,
                    )
                    for col, p in zip(specs, a.result.punching)
                ],
                stability=_stability_out(a.result),
                status=a.result.overall_status.value,
                status_label=status_label(a.result.overall_status),
            )
            for a in mejores
        ]

        # Pendiente 1: el esquema lo arma el motor a partir del layout que usó el cálculo.
        from engine.visualization.combined_scene import build_combined_scene

        escena = None
        if mejores:
            escena = schemas.CombinedSceneOut.model_validate(
                build_combined_scene(
                    build_layout(
                        specs, mejores[0].length_m, mejores[0].width_m,
                        mejores[0].first_column_edge_distance_m, params.longitudinal_direction,
                        transverse_shift_m=mejores[0].transverse_shift_m,
                    ),
                    mejores[0],
                ),
                from_attributes=True,
            )

        # ¿La geometría recomendada quedó contra el borde del rango explorado? Misma
        # comprobación que en la aislada y la conectada, con una sola implementación
        # (2026-09-24).
        elegida_c = mejores[0] if mejores else None
        _, aviso_borde = describe_boundary(
            [
                ("la longitud L", elegida_c.length_m if elegida_c else None,
                 params.length_min_m, params.length_max_m, params.length_step_m),
                ("el ancho B", elegida_c.width_m if elegida_c else None,
                 params.width_min_m, params.width_max_m, params.width_step_m),
                ("el peralte h", elegida_c.h_m if elegida_c else None,
                 params.h_min_m, params.h_max_m, params.h_step_m, False),
            ]
        )

        # Decisión 6: el desglose de lo aceptado se transporta tal como lo calcula el motor;
        # la API no lo reinterpreta.
        nv_ids = [a.id for a in resultado.not_verified]
        obs_ids = [a.id for a in resultado.accepted_with_findings]
        conformes_ids = [a.id for a in resultado.accepted_and_compliant]

        return schemas.CombinedDesignResponse(
            top=salida,
            evaluated_count=resultado.evaluated_count,
            discarded_count=resultado.discarded_count,
            truncated=resultado.truncated,
            search_note=resultado.search_note,
            search_boundary_note=aviso_borde,
            centering_length_m=centrado.length_m if centrado else None,
            centering_note=centrado.note if centrado else "",
            axis_convention_note=AXIS_CONVENTION_NOTE,
            comparison=comparacion,
            pareto_objectives=list(DEFAULT_OBJECTIVES),
            pareto_size=sum(mascara),
            discard_groups=[
                schemas.CombinedDiscardGroupOut(**g.model_dump())
                for g in resultado.discard_summary.groups
            ],
            discarded_by_status=resultado.discard_summary.discarded_by_status,
            unresolved_count=resultado.unresolved_count,
            unresolved_groups=[
                schemas.CombinedUnresolvedGroupOut(**u.model_dump())
                for u in resultado.discard_summary.unresolved
            ],
            accepted_count=len(resultado.valid),
            status_summary=resultado.status_summary(),
            not_verified=nv_ids,
            accepted_with_findings=obs_ids,
            accepted_and_compliant=conformes_ids,
            not_verified_count=len(nv_ids),
            accepted_with_findings_count=len(obs_ids),
            accepted_and_compliant_count=len(conformes_ids),
            can_claim_compliance=bool(conformes_ids),
            scene=escena,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"detail": str(exc)}) from exc


class CombinedReportRequest(schemas.CombinedDesignRequest):
    """Igual que el diseño combinado, más cuál alternativa reportar."""

    alternative_id: str | None = None


@app.post("/api/report-combined", response_class=HTMLResponse)
def report_combined(request: CombinedReportRequest) -> HTMLResponse:
    """Memoria de cálculo de zapata combinada, con los diagramas V(x) y M(x)."""
    from engine.reports.combined_report import render_combined_report_html

    base = schemas.CombinedDesignRequest(**request.model_dump(exclude={"alternative_id"}))
    respuesta = design_combined(base)
    if not respuesta.top:
        raise HTTPException(
            status_code=422,
            detail={"detail": "No hay ninguna alternativa viable que reportar."},
        )

    # La alternativa se busca entre TODAS las aceptadas (`comparison`), no solo en las
    # `top_n` que se muestran. Un id inexistente es un error explícito: sustituirlo en
    # silencio por la primera daría una memoria de otra zapata (CLAUDE.md §14).
    # Sin id se reporta la primera del ordenamiento, que es top[0].
    elegido = respuesta.comparison[0]
    if request.alternative_id:
        elegido = next(
            (a for a in respuesta.comparison if a.id == request.alternative_id), None
        )
        if elegido is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "detail": (
                        f"La alternativa {request.alternative_id!r} no está entre las "
                        f"{len(respuesta.comparison)} aceptadas de esta búsqueda. Repita el "
                        f"diseño y elija una de las alternativas devueltas."
                    )
                },
            )

    # Se recalcula la alternativa elegida para disponer del resultado completo: la
    # respuesta de la API es un resumen, y el informe necesita la traza entera.
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.column import Column
    from engine.foundation.combined_solver import solve_combined_footing
    from engine.optimization.combined_generator import ColumnSpec, build_layout
    from engine.reinforcement.face_reinforcement import TopCoverDeclaration

    units = request.units
    specs = [
        ColumnSpec(
            label=c.label,
            column=Column(
                shape=c.shape,
                bx_m=length_to_m(c.bx_m, units.length),
                by_m=length_to_m(c.by_m, units.length),
            ),
            distance_from_first_m=length_to_m(c.distance_from_first_m, units.length),
            transverse_offset_m=length_to_m(c.transverse_offset_m, units.length),
            loads=mapping.build_loads(c.combinations, units, c.load_cases, request.combination_definitions),
        )
        for c in request.columns
    ]
    # La posición con la que se CALCULÓ esa alternativa (con la posición automática
    # cambia de una planta a otra), no la de la petición.
    layout = build_layout(
        specs, elegido.length_m, elegido.width_m,
        elegido.first_column_edge_distance_m
        if elegido.first_column_edge_distance_m is not None
        else length_to_m(request.search.first_column_edge_distance_m or 0.0, units.length),
        request.search.longitudinal_direction,
        transverse_shift_m=elegido.transverse_shift_m,
    )
    resultado = solve_combined_footing(
        layout, elegido.h_m,
        soil=mapping.build_soil(request.soil, units),
        concrete=mapping.build_materials(request.materials, units)[0],
        steel=mapping.build_materials(request.materials, units)[1],
        code=E060ConcreteCode(), contact_model=mapping.contact_model_for(request.soil),
        top_cover=TopCoverDeclaration(
            case=request.top_cover.case, explicit_mm=request.top_cover.explicit_mm
        ),
    )
    return HTMLResponse(
        render_combined_report_html(
            resultado,
            f"{request.project_name} — alternativa {elegido.id}",
            units=ReportUnits.from_input(request.units),
        )
    )


# =========================================================================
# Viga de conexión — Fase 3
# =========================================================================


def _solve_beam(request: schemas.BeamDesignRequest):
    """Único punto donde se llama al motor de vigas. Los dos endpoints —diseño e
    informe— pasan por aquí, de modo que no puede haber divergencia entre lo que
    muestra la pantalla y lo que dice la memoria."""
    from engine.beam.beam_trace import build_beam_trace
    from engine.beam.connecting_beam import SeismicContext, design_connecting_beam

    units = request.units
    b = length_to_m(request.b_m, units.length)
    h = length_to_m(request.h_m, units.length)
    d = length_to_m(request.d_m, units.length)
    ln = length_to_m(request.clear_span_m, units.length)

    if d >= h:
        raise ValueError(
            f"El peralte efectivo d = {d:.3f} m no puede igualar ni superar el peralte "
            f"total h = {h:.3f} m: la diferencia es el recubrimiento hasta el centroide "
            f"del refuerzo."
        )

    concrete, steel = mapping.build_materials(request.materials, units)
    soil = mapping.build_soil(request.soil, units)

    seismic = SeismicContext(
        soil_profile=request.seismic.soil_profile,
        seismic_zone=request.seismic.seismic_zone,
        qadm_kPa=soil.qadm_kPa,
        part_of_lateral_force_system=request.seismic.part_of_lateral_force_system,
        lateral_system=request.seismic.lateral_system,
    )

    result = design_connecting_beam(
        b_m=b, h_m=h, d_m=d, clear_span_m=ln,
        Mu_negative_kNm=mapping.moment_to_kNm(request.Mu_negative_kNm, units.moment),
        Mu_positive_kNm=mapping.moment_to_kNm(request.Mu_positive_kNm, units.moment),
        Vu_kN=mapping.force_to_kN(request.Vu_kN, units.force),
        fc_MPa=concrete.fc_MPa, fy_MPa=steel.fy_MPa,
        longitudinal_db_mm=request.longitudinal_db_mm,
        sum_Pu_kN=mapping.force_to_kN(request.sum_Pu_kN, units.force),
        seismic=seismic,
        fyt_MPa=request.fyt_MPa,
        stirrup_diameter_mm=request.stirrup_diameter_mm,
        n_legs=request.n_legs,
    )
    return result, build_beam_trace(result)


@app.post("/api/design-beam", response_model=schemas.BeamDesignResponse)
def design_beam(request: schemas.BeamDesignRequest) -> schemas.BeamDesignResponse:
    """Diseño de una viga de conexión (E.060 §21.12.3, §10.5, §11.5 y E.030 art. 65.1).

    Los momentos y el cortante son DATOS DE ENTRADA: provienen del análisis de la
    estructura. Este motor no los deriva."""
    try:
        result, trace = _solve_beam(request)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)})
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)})
    return mapping.beam_result_to_dto(result, request.project_name, trace)


@app.post("/api/report-beam", response_class=HTMLResponse)
def report_beam(request: schemas.BeamDesignRequest) -> HTMLResponse:
    """Memoria de cálculo de la viga de conexión, con la traza completa."""
    from engine.reports.beam_report import render_beam_report_html

    try:
        result, trace = _solve_beam(request)
    except ValueError as exc:
        raise HTTPException(422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)})
    return HTMLResponse(render_beam_report_html(result, trace, request.project_name))


# =========================================================================
# Cimentación conectada — Fase 4E
# =========================================================================


def _build_connected_layout(request: schemas.ConnectedDesignRequest):
    """Traduce el DTO al layout del motor. No decide nada de ingeniería."""
    from engine.domain.column import Column
    from engine.domain.connected_layout import (
        AnalysisModel,
        BeamSelfWeightMode,
        BeamSupportMode,
        ConnectedElement,
        ConnectedFootingLayout,
        ConnectingBeamSpec,
        CoupleTransferMode,
        EdgeAnchor,
        StiffnessDeclaration,
    )

    units = request.units

    def columna(dto: schemas.ConnectedColumnInput) -> Column:
        return Column(
            shape=dto.shape,
            bx_m=length_to_m(dto.bx_m, units.length),
            by_m=length_to_m(dto.by_m, units.length),
        )

    # Los tres modos van SIN valor por defecto en el motor a propósito: ninguna norma
    # arbitra entre ellos. Si el DTO trae un valor inválido, el enum levanta el error
    # aquí y no en mitad del barrido.
    return ConnectedFootingLayout(
        analysis_model=AnalysisModel(request.analysis_model),
        couple_transfer_mode=CoupleTransferMode(request.couple_transfer_mode),
        exterior=ConnectedElement(
            label=request.exterior.label,
            column=columna(request.exterior),
            loads=mapping.build_loads(
                request.exterior.combinations, units, request.exterior.load_cases, request.combination_definitions
            ),
            anchor=EdgeAnchor(
                edge=request.anchor.edge,
                face_clearance_m=length_to_m(request.anchor.face_clearance_m, units.length),
            ),
            hook_type_x=request.exterior.hook_type_x,
            hook_type_y=request.exterior.hook_type_y,
        ),
        interior=ConnectedElement(
            label=request.interior.label,
            column=columna(request.interior),
            loads=mapping.build_loads(
                request.interior.combinations, units, request.interior.load_cases, request.combination_definitions
            ),
            hook_type_x=request.interior.hook_type_x,
            hook_type_y=request.interior.hook_type_y,
        ),
        beam=ConnectingBeamSpec(
            b_m=length_to_m(request.beam.b_m, units.length),
            h_m=length_to_m(request.beam.h_m, units.length),
            d_m=length_to_m(request.beam.d_m, units.length),
            support_mode=BeamSupportMode(request.beam.support_mode),
            # TBD-C1 (decisión 4): sin declarar equivale a NO_EVALUADA, que es lo que
            # había antes. El defecto no responde la pregunta, la deja sin responder.
            stiffness_declaration=(
                StiffnessDeclaration.NO_EVALUADA
                if request.beam.stiffness_declaration is None
                else StiffnessDeclaration(request.beam.stiffness_declaration)
            ),
            self_weight_mode=BeamSelfWeightMode(request.beam.self_weight_mode),
            # 2026-09-23: faltaba la conversión. `materials.concrete_unit_weight_kNm3`
            # sí pasaba por el registro; este no, de modo que un peso declarado en
            # tonf/m³ se leía como kN/m³ y el peso propio de la viga salía 9,8 veces
            # menor. Con las unidades por defecto (kN/m³) el factor es 1 y nada cambia.
            concrete_unit_weight_kNm3=mapping.unit_weight_to_kNm3(
                request.beam.concrete_unit_weight_kNm3, units.unit_weight
            ),
            soffit_above_base_m=(
                None if request.beam.soffit_above_base_m is None
                else length_to_m(request.beam.soffit_above_base_m, units.length)
            ),
            # TBD-C13: adimensional, no pasa por conversión de unidades.
            self_weight_dead_load_factor=request.beam.self_weight_dead_load_factor,
        ),
        axis_distance_m=length_to_m(request.axis_distance_m, units.length),
        longitudinal_axis=request.longitudinal_axis,
    )


# Fase 4H. `/api/report-connected` se pide normalmente justo después de
# `/api/design-connected` con la MISMA petición, y hasta aquí repetía el barrido entero.
# El motor es determinista y la petición lo determina por completo, de modo que el
# resultado se guarda en una caché pequeña indexada por la petición serializada.
# Es de solo lectura para los dos endpoints: ninguno modifica el conjunto que recibe.
_CONNECTED_CACHE_SIZE = 4
_connected_cache: "OrderedDict[str, object]" = OrderedDict()
_connected_cache_lock = threading.Lock()


def _run_connected_search(request: schemas.ConnectedDesignRequest):
    """Barrido de la conectada, servido desde caché si la misma petición ya se resolvió.

    La clave es la petición completa serializada: cualquier cambio de dato —una carga,
    un rango, un modo— es otra clave y otro cálculo. Solo se guardan resultados; un
    error de entrada no se guarda y se vuelve a lanzar en cada llamada."""
    clave = request.model_dump_json()
    with _connected_cache_lock:
        if clave in _connected_cache:
            _connected_cache.move_to_end(clave)
            return _connected_cache[clave]
    conjunto = _compute_connected_search(request)
    with _connected_cache_lock:
        _connected_cache[clave] = conjunto
        _connected_cache.move_to_end(clave)
        while len(_connected_cache) > _CONNECTED_CACHE_SIZE:
            _connected_cache.popitem(last=False)
    return conjunto


def _compute_connected_search(request: schemas.ConnectedDesignRequest):
    """Ejecuta el barrido y devuelve el conjunto sin recortar.

    Se separa del endpoint porque el informe necesita el conjunto ENTERO —incluidos los
    rechazos y la traza completa— mientras que la respuesta JSON sirve un resumen. Que
    los dos salgan de la misma llamada evita que informe y API acaben contando cosas
    distintas del mismo cálculo."""
    from engine.codes.peru.e060_concrete import E060ConcreteCode
    from engine.domain.search_parameters import DepthSearchParameters
    from engine.optimization.connected_generator import (
        ConnectedSearchParameters,
        generate_connected_alternatives,
    )

    units = request.units
    layout = _build_connected_layout(request)
    soil = mapping.build_soil(request.soil, units)
    concrete, steel = mapping.build_materials(request.materials, units)

    s = request.search
    L = units.length

    def m(valor: float) -> float:
        return length_to_m(valor, L)

    limites = mapping.build_site_limits(request.site_limits, units)
    rangos_manuales = (
        s.ext_long_min_m, s.ext_long_max_m, s.ext_transv_min_m, s.ext_transv_max_m,
        s.int_long_min_m, s.int_long_max_m, s.int_transv_min_m, s.int_transv_max_m,
    )
    nota_auto = ""
    # Una sola construcción del modelo de contacto para las dos ramas (CLAUDE.md §13:
    # se construye en `mapping.contact_model_for` y en ningún otro sitio).
    contacto = mapping.contact_model_for(request.soil)
    if s.auto_ranges or any(v is None for v in rangos_manuales):
        # Rangos estimados por el motor y búsqueda en dos pasadas (2026-09-28,
        # engine/optimization/auto_search.py). Se comparte el peralte entre las dos
        # zapatas —la malla independiente es n² parejas— y el tope se ajusta al tamaño de
        # cada malla para que ninguna pasada salga truncada. Se declara.
        from engine.optimization.auto_search import auto_connected_search
        from engine.optimization.connected_generator import rank_connected_alternatives

        def _barrer(campos: dict):
            n = 1
            for eje in ("ext_long", "ext_transv", "int_long", "int_transv", "h"):
                lo, hi, paso = campos[f"{eje}_min_m"], campos[f"{eje}_max_m"], campos[f"{eje}_step_m"]
                n *= int(round((hi - lo) / paso)) + 1
            p = ConnectedSearchParameters(
                **campos, max_systems=max(s.max_systems, n),
                same_depth_both_footings=True, site_limits=limites,
            )
            return generate_connected_alternatives(
                layout, p, soil=soil, concrete=concrete, steel=steel, code=E060ConcreteCode(),
                contact_model=contacto,
                depth_params=DepthSearchParameters(h_min_m=p.h_min_m, h_max_m=p.h_max_m, h_step_m=0.05),
            )

        conjunto, nota_auto = auto_connected_search(
            layout, soil, limites, _barrer, rank_connected_alternatives
        )
        nota_auto += " En la búsqueda automática las dos zapatas comparten peralte."
        conjunto.search_note = (nota_auto + " " + conjunto.search_note).strip()
        return conjunto
    else:
        params = ConnectedSearchParameters(
            ext_long_min_m=m(s.ext_long_min_m), ext_long_max_m=m(s.ext_long_max_m),
            ext_long_step_m=m(s.ext_long_step_m),
            ext_transv_min_m=m(s.ext_transv_min_m), ext_transv_max_m=m(s.ext_transv_max_m),
            ext_transv_step_m=m(s.ext_transv_step_m),
            int_long_min_m=m(s.int_long_min_m), int_long_max_m=m(s.int_long_max_m),
            int_long_step_m=m(s.int_long_step_m),
            int_transv_min_m=m(s.int_transv_min_m), int_transv_max_m=m(s.int_transv_max_m),
            int_transv_step_m=m(s.int_transv_step_m),
            h_min_m=m(s.h_min_m), h_max_m=m(s.h_max_m), h_step_m=m(s.h_step_m),
            max_systems=s.max_systems,
            same_depth_both_footings=s.same_depth_both_footings,
            site_limits=limites,
        )

    conjunto = generate_connected_alternatives(
        layout, params,
        soil=soil, concrete=concrete, steel=steel, code=E060ConcreteCode(),
        contact_model=contacto,
        depth_params=DepthSearchParameters(
            h_min_m=params.h_min_m, h_max_m=params.h_max_m, h_step_m=0.05
        ),
    )
    if nota_auto:
        conjunto.search_note = (nota_auto + " " + conjunto.search_note).strip()
    return conjunto


@app.post("/api/design-connected", response_model=schemas.ConnectedDesignResponse)
def design_connected(
    request: schemas.ConnectedDesignRequest,
) -> schemas.ConnectedDesignResponse:
    """Búsqueda de cimentación conectada (zapata de lindero + viga + zapata interior).

    LA RESPUESTA SE EMITE AUNQUE NADA ESTÉ VERIFICADO. Esta tipología no puede alcanzar
    PASS mientras TBD-C1 siga abierto, de modo que devolver 422 por eso dejaría el
    endpoint inservible. Lo que se devuelve es el estado real, con `can_claim_compliance`
    en false y los pendientes nombrados uno a uno.

    Todos los estados viajan como CAMPOS, no como `@property`: pydantic no serializa
    propiedades, y una `@property` olvidada es exactamente el modo en que un
    NO VERIFICADO llegaría al navegador convertido en «una alternativa más»."""
    from engine.optimization.connected_generator import rank_connected_alternatives
    from engine.reports.connected_report import (
        alternative_label,
        build_connected_status_summary,
    )

    try:
        conjunto = _run_connected_search(request)
    except ValidationError as exc:
        raise HTTPException(
            422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)}
        ) from exc

    from engine.optimization.pareto import DEFAULT_OBJECTIVES, pareto_mask
    from engine.visualization.connected_scene import build_connected_scene

    resumen = build_connected_status_summary(conjunto)
    ordenadas = rank_connected_alternatives(conjunto.accepted)

    # Frente de Pareto con el MISMO núcleo de dominancia que la zapata aislada.
    mascara = pareto_mask([s.alternative.metrics for s in ordenadas], DEFAULT_OBJECTIVES)
    en_frente = {s.alternative.id for s, m in zip(ordenadas, mascara) if m}

    def _fila(s) -> schemas.ConnectedAlternativeOut:
        a = s.alternative
        g = a.geometry
        return schemas.ConnectedAlternativeOut(
                id=a.id,
                exterior_B_m=g.exterior_B_m, exterior_L_m=g.exterior_L_m,
                exterior_h_m=g.exterior_h_m,
                interior_B_m=g.interior_B_m, interior_L_m=g.interior_L_m,
                interior_h_m=g.interior_h_m,
                concrete_volume_m3=a.metrics.concrete_volume_m3,
                steel_mass_kg=a.metrics.steel_mass_kg,
                system_length_m=a.result.system_length_m,
                beam_span_m=a.result.beam_span_m,
                delta_P_kN=a.result.statics[0].delta_P_kN if a.result.statics else 0.0,
                score=s.score,
                overall_status=a.overall_status.value,
                implemented_checks_status=a.implemented_checks_status.value,
                open_tbds=list(a.open_tbds),
                status_label=alternative_label(a),
                footing_area_m2=a.metrics.footing_area_m2,
                max_plan_dimension_m=a.metrics.max_plan_dimension_m,
                in_pareto=a.id in en_frente,
            )

    comparacion = [_fila(s) for s in ordenadas]
    aceptadas = comparacion[: request.top_n]

    # Mismo aviso de borde que las otras dos tipologías (2026-09-24). Aquí son cuatro
    # dimensiones en planta más el peralte, y el barrido además declara si se truncó.
    # Rangos EFECTIVOS del barrido, en SI (2026-09-28): la petición puede no traerlos
    # (búsqueda automática), traerlos en otra unidad, o quedar recortada por los linderos.
    # Y la dimensión «sobre la viga» es B con la viga en X y L con la viga en Y.
    mejor_conn = ordenadas[0].alternative.geometry if ordenadas else None
    r_conn = conjunto.search_ranges_m
    sobre_x = request.longitudinal_axis == "X"

    def _dim(g, zapata: str, a_lo_largo: bool):
        if g is None:
            return None
        B, Lz = (g.exterior_B_m, g.exterior_L_m) if zapata == "ext" else (g.interior_B_m, g.interior_L_m)
        return (B if sobre_x else Lz) if a_lo_largo else (Lz if sobre_x else B)

    def _r(eje: str):
        return r_conn.get(f"{eje}_min_m"), r_conn.get(f"{eje}_max_m"), r_conn.get(f"{eje}_step_m")

    _, aviso_borde_conn = describe_boundary(
        [
            ("el largo de la zapata de lindero", _dim(mejor_conn, "ext", True), *_r("ext_long")),
            ("el ancho de la zapata de lindero", _dim(mejor_conn, "ext", False), *_r("ext_transv")),
            ("el largo de la zapata interior", _dim(mejor_conn, "int", True), *_r("int_long")),
            ("el ancho de la zapata interior", _dim(mejor_conn, "int", False), *_r("int_transv")),
            ("el peralte de la zapata de lindero", mejor_conn.exterior_h_m if mejor_conn else None,
             *_r("h"), False),
            ("el peralte de la zapata interior", mejor_conn.interior_h_m if mejor_conn else None,
             *_r("h"), False),
        ]
    ) if r_conn else (None, "")

    escena = None
    if ordenadas:
        escena = schemas.ConnectedSceneOut.model_validate(
            build_connected_scene(_build_connected_layout(request), ordenadas[0].alternative),
            from_attributes=True,
        )

    # La traza que se sirve es la de la MEJOR por costo, con `scope` y `open_tbd`
    # intactos: es lo que permite a la UI separar un hueco normativo de un dato que
    # falta. Perder `open_tbd` aquí haría indistinguibles las dos cosas.
    traza = (
        [mapping.trace_entry_to_dto(e) for e in ordenadas[0].alternative.result.trace.entries]
        if ordenadas
        else []
    )

    return schemas.ConnectedDesignResponse(
        overall_status=resumen.overall_status.value,
        headline=resumen.headline,
        can_claim_compliance=resumen.can_claim_compliance,
        open_tbds=[
            schemas.OpenTbdOut(
                id=t.id, description=t.description,
                affected_alternatives=t.affected_alternatives,
            )
            for t in resumen.open_tbds
        ],
        accepted=aceptadas,
        not_verified=[a.id for a in conjunto.not_verified],
        accepted_and_compliant=[a.id for a in conjunto.accepted_and_compliant],
        rejected=[
            schemas.ConnectedRejectionOut(
                exterior_B_m=r.geometry.exterior_B_m,
                exterior_L_m=r.geometry.exterior_L_m,
                exterior_h_m=r.geometry.exterior_h_m,
                interior_B_m=r.geometry.interior_B_m,
                interior_L_m=r.geometry.interior_L_m,
                interior_h_m=r.geometry.interior_h_m,
                reason=r.reason.value,
                detail=r.detail[:400],
            )
            for r in conjunto.rejected[:50]
        ],
        evaluated_count=resumen.evaluated_count,
        accepted_count=resumen.accepted_count,
        not_verified_count=resumen.not_verified_count,
        accepted_and_compliant_count=resumen.accepted_and_compliant_count,
        accepted_with_findings_count=resumen.accepted_with_findings_count,
        rejected_count=resumen.rejected_count,
        rejections_by_reason=resumen.rejections_by_reason,
        truncated=resumen.truncated,
        search_note=resumen.search_note,
        search_boundary_note=aviso_borde_conn,
        trace=traza,
        comparison=comparacion,
        pareto_objectives=list(DEFAULT_OBJECTIVES),
        pareto_size=len(en_frente),
        scene=escena,
    )


class ConnectedReportRequest(schemas.ConnectedDesignRequest):
    """Igual que el diseño conectado, más cuál alternativa detallar."""

    alternative_id: str | None = None


@app.post("/api/report-connected", response_class=HTMLResponse)
def report_connected(request: ConnectedReportRequest) -> HTMLResponse:
    """Memoria de cálculo de cimentación conectada.

    Se emite SIEMPRE, incluso sin alternativas aceptadas: a diferencia de la combinada,
    aquí «no hay nada que reportar» no es cierto. Que el barrido entero se haya caído
    por despegue, o que todo esté NO VERIFICADO, es precisamente lo que el usuario
    necesita leer."""
    from engine.reports.connected_report import render_connected_report_html

    base = schemas.ConnectedDesignRequest(
        **request.model_dump(exclude={"alternative_id"})
    )
    try:
        conjunto = _run_connected_search(base)
    except ValidationError as exc:
        raise HTTPException(
            422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            422, detail={"error": "Datos de entrada inválidos", "detail": str(exc)}
        ) from exc

    # Un id pedido que no está entre las aceptadas es un error explícito, no una sustitución
    # silenciosa por la mejor clasificada (CLAUDE.md §14). Sin id, el informe detalla la mejor.
    if request.alternative_id and not any(
        a.id == request.alternative_id for a in conjunto.accepted
    ):
        raise HTTPException(
            422,
            detail={
                "error": "Alternativa inexistente",
                "detail": (
                    f"La alternativa {request.alternative_id!r} no está entre las "
                    f"{len(conjunto.accepted)} aceptadas de esta búsqueda. Repita el diseño "
                    f"y elija una de las alternativas devueltas."
                ),
            },
        )

    return HTMLResponse(
        render_connected_report_html(
            conjunto,
            titulo=f"Memoria de cálculo — {request.project_name}",
            selected_id=request.alternative_id,
            units=ReportUnits.from_input(request.units),
        )
    )
