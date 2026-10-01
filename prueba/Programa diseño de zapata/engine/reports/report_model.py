"""Modelo de datos del REPORTE DE CÁLCULO (sección 15 del encargo original).

Las 16 secciones exigidas, como estructura de datos pura e independiente del
formato de salida. Un renderizador (HTML hoy; DOCX o PDF nativo mañana) consume
este modelo sin necesidad de tocar el motor.

REGLA MANTENIDA: el reporte no calcula nada. Cada ecuación que muestra proviene
del `CalculationTrace`, que ya trae variables, unidades, hipótesis y fuente
normativa — los cuatro elementos que exige el encargo para cada ecuación.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from engine.reports.report_units import ReportUnits
from engine.results.calculation_trace import CalculationTraceEntry
from engine.results.status import CheckStatus
from engine.results.vocabulary import STATUS_VOCABULARY, VOCABULARY_NOTE  # noqa: F401
from engine.results.vocabulary import StatusLabel as VocabularyLabel
from engine.results.vocabulary import status_label as vocabulary_status_label


class ReportRow(BaseModel):
    """Fila genérica etiqueta / valor / unidad / referencia."""

    label: str
    value: str
    unit: str = ""
    reference: str = ""


class ReportTable(BaseModel):
    title: str = ""
    headers: list[str]
    rows: list[list[str]]
    note: str = ""


class LoadCombinationRow(BaseModel):
    name: str
    type: str
    P_kN: float
    Mx_kNm: float
    My_kNm: float
    Hx_kN: float
    Hy_kN: float
    seismic: bool


class GoverningRow(BaseModel):
    check: str
    combination: str
    status: CheckStatus


class DiscardSummary(BaseModel):
    reason: str
    count: int
    example_id: str
    example_geometry: str


class HypothesisItem(BaseModel):
    """Una hipótesis o supuesto aplicado, con su origen."""

    text: str
    source: str = Field(..., description='Check del que proviene, o "General"')
    is_normative_interpretation: bool = False


class LimitationItem(BaseModel):
    title: str
    kind: str
    code_reference: str
    impact: str
    can_cause_false_pass: bool


class FootingReport(BaseModel):
    """Reporte completo de una alternativa. Las 16 secciones del encargo."""

    # --- Encabezado ---
    generated_at: datetime
    engine_version: str
    code_name: str
    # Unidades en que se ESCRIBE la memoria (2026-09-23). Por omisión, las SI del
    # motor: así una memoria generada sin declarar unidades sale como salía antes.
    units: ReportUnits = ReportUnits()

    # 1. Datos del proyecto
    project_name: str
    alternative_id: str
    alternative_rank: int
    final_status: CheckStatus

    # 2. Datos de la columna
    column_rows: list[ReportRow]

    # 3. Datos del suelo
    soil_rows: list[ReportRow]

    # 3b. Materiales (no numerado en el encargo, pero imprescindible)
    material_rows: list[ReportRow]

    # 4. Combinaciones de carga
    service_combinations: list[LoadCombinationRow]
    factored_combinations: list[LoadCombinationRow]
    combinations_note: str

    # 5. Hipótesis utilizadas
    hypotheses: list[HypothesisItem]

    # 6. Geometría seleccionada
    geometry_rows: list[ReportRow]

    # 7 a 12. Memoria de cálculo, agrupada por tema.
    # Cada entrada trae ecuación, sustitución, unidades, hipótesis y artículo.
    trace_groups: list[tuple[str, list[CalculationTraceEntry]]]

    # 8b. Excentricidad (resumen numérico además del trace)
    eccentricity_rows: list[ReportRow]

    # 12b. Diseño del acero
    rebar_tables: list[ReportTable]
    short_direction_table: ReportTable | None

    # 13. Verificaciones normativas
    governing_combinations: list[GoverningRow]
    limitations: list[LimitationItem]

    # 14. Resultado final
    conclusion: str
    pass_conditions: list[str]

    # 15. Alternativas descartadas
    discarded: list[DiscardSummary]
    discard_note: str

    # 16. Tabla comparativa
    comparison: ReportTable

    # Búsqueda ejecutada (contexto del resultado)
    search_rows: list[ReportRow]
    summary_rows: list[ReportRow]


SECTION_TITLES: list[tuple[int, str]] = [
    (1, "Datos del proyecto"),
    (2, "Datos de la columna"),
    (3, "Datos del suelo"),
    (4, "Combinaciones de carga"),
    (5, "Hipótesis utilizadas"),
    (6, "Geometría seleccionada"),
    (7, "Cálculo de presiones de contacto"),
    (8, "Verificación de excentricidad"),
    (9, "Diseño por flexión"),
    (10, "Verificación de cortante"),
    (11, "Verificación de punzonamiento"),
    (12, "Diseño del acero"),
    (13, "Verificaciones normativas"),
    (14, "Resultado final"),
    (15, "Alternativas descartadas"),
    (16, "Tabla comparativa"),
]

# Qué entradas del trace corresponden a cada sección del reporte.
TRACE_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("7. Cálculo de presiones de contacto", ("self_weight", "contact_pressure")),
    ("8. Verificación de excentricidad y estabilidad", ("sliding", "overturning_x", "overturning_y")),
    ("9. Diseño por flexión", ("min_depth", "flexure_x", "flexure_y", "short_direction_distribution")),
    ("10. Verificación de cortante", ("shear_x", "shear_y")),
    ("11. Verificación de punzonamiento", ("punching",)),
    (
        "12. Diseño y desarrollo del acero",
        (
            "rebar_x", "rebar_y",
            "rebar_options_development_x", "rebar_options_development_y",
            "development_x", "development_y",
        ),
    ),
]

# Pendiente 8: el vocabulario es UNO para las tres tipologías y vive en
# `engine/results/vocabulary.py`. Aquí se reexporta para no romper los importadores.
# Antes la aislada rotulaba PASS como «ACEPTADA» y FAIL como «DESCARTADA»; esas dos
# palabras desaparecieron porque significaban cosas distintas según la tipología.
StatusLabel = VocabularyLabel


def status_label(status: CheckStatus) -> StatusLabel:
    """Rótulo del vocabulario único. La aislada no lleva pendientes por alternativa."""
    return vocabulary_status_label(status)
