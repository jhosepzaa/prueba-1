"""Explicación de descartes (sección 12 del encargo original).

"Cuando una alternativa no cumpla, el programa debe explicar exactamente por qué
[...] Esto debe permitir al ingeniero entender el comportamiento del algoritmo."

Este módulo NO recalcula nada: lee el CalculationTrace que el motor ya produjo
durante la evaluación. Esa es la razón por la que el trace se diseñó como
ciudadano de primera clase desde la Fase 2 -- la explicación de descartes y el
futuro reporte de cálculo se alimentan de la misma fuente, sin duplicar lógica.

La salida es un modelo estructurado (consumible por la futura UI) más un
renderizador de texto para consola/reporte.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.optimization.alternative_generator import Alternative, DiscardedAlternative
from engine.results.footing_candidate import FootingCandidate
from engine.results.status import CheckStatus
from engine.results.vocabulary import status_label as vocabulary_status_label

# Etiquetas legibles por check. El motor identifica los checks por id; aquí se
# traducen al lenguaje del ingeniero.
CHECK_LABELS: dict[str, str] = {
    "self_weight": "Peso propio",
    "contact_pressure": "Presión de contacto sobre el suelo",
    "min_depth": "Peralte mínimo",
    "foundation_depth": "Profundidad de cimentación",
    "column_placement": "Posición de la columna",
    "sliding": "Deslizamiento",
    "overturning_x": "Volcamiento dirección X",
    "overturning_y": "Volcamiento dirección Y",
    "flexure_x": "Flexión dirección X",
    "flexure_y": "Flexión dirección Y",
    "shear_x": "Cortante unidireccional X",
    "shear_y": "Cortante unidireccional Y",
    "punching": "Punzonamiento",
    "rebar_x": "Armado dirección X",
    "rebar_y": "Armado dirección Y",
}

_SYMBOL = {
    CheckStatus.PASS: "OK",
    CheckStatus.FAIL: "NO",
    CheckStatus.WARNING: "!!",
    CheckStatus.NOT_VERIFIED: "??",
    CheckStatus.INFO: "--",
}


class CheckOutcome(BaseModel):
    check_id: str
    label: str
    status: CheckStatus
    detail: str
    governing_combo: str | None
    code_reference: str


class Explanation(BaseModel):
    alternative_id: str
    B_m: float
    L_m: float
    h_m: float | None
    verdict: CheckStatus
    failed: list[CheckOutcome]
    warnings: list[CheckOutcome]
    not_verified: list[CheckOutcome]
    passed: list[CheckOutcome]
    informative: list[CheckOutcome]
    search_note: str = ""

    # Los cinco cubos cubren los cinco estados. La partición debe ser EXHAUSTIVA:
    # una verificación que no cayera en ninguno desaparecería de la explicación sin
    # dejar rastro, y la que más importa que no desaparezca es precisamente
    # NO VERIFICADO. Ver test_explanation_covers_every_trace_entry.

    def to_text(self) -> str:
        geom = f"B={self.B_m:.2f} m  L={self.L_m:.2f} m"
        if self.h_m is not None:
            geom += f"  h={self.h_m:.2f} m"
        # Cuatro desenlaces, no dos: una alternativa con WARNING no es ni RECHAZADA ni
        # CONFORME. El rótulo sale del vocabulario único (pendiente 8), que es el mismo
        # de las tres tipologías: rotularlo aquí por separado fue lo que produjo que
        # «ACEPTADA» significara PASS en un sitio y WARNING en otro.
        header = vocabulary_status_label(self.verdict)
        lines = [f"{self.alternative_id} -- {header}", f"  {geom}", ""]

        if self.search_note:
            lines.append(f"  {self.search_note}")
            lines.append("")

        for group, title in (
            (self.failed, "NO CUMPLE"),
            (self.not_verified, "NO VERIFICADO"),
            (self.warnings, "REVISAR"),
            (self.passed, "CUMPLE"),
            (self.informative, "INFORMATIVO"),
        ):
            if not group:
                continue
            lines.append(f"  {title}:")
            for outcome in group:
                combo = f" [gobierna {outcome.governing_combo}]" if outcome.governing_combo else ""
                lines.append(f"    [{_SYMBOL[outcome.status]}] {outcome.label}{combo}")
                lines.append(f"         {outcome.detail}")
                lines.append(f"         ({outcome.code_reference})")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _format_reference(code_name: str, code_reference: str) -> str:
    """Evita duplicar el nombre del código cuando la referencia ya lo incluye
    (p. ej. code_name='E.060' + reference='E.060 §11.3.1.1')."""
    if code_reference.startswith(code_name):
        return code_reference
    return f"{code_name} {code_reference}"


def _outcomes(candidate: FootingCandidate) -> list[CheckOutcome]:
    return [
        CheckOutcome(
            check_id=entry.id,
            label=CHECK_LABELS.get(entry.id, entry.id),
            status=entry.status,
            detail=entry.equation_substituted,
            governing_combo=entry.governing_combo,
            code_reference=_format_reference(entry.code_name, entry.code_reference),
        )
        for entry in candidate.trace.entries
    ]


def explain_candidate(candidate: FootingCandidate, alternative_id: str, search_note: str = "") -> Explanation:
    outcomes = _outcomes(candidate)
    return Explanation(
        alternative_id=alternative_id,
        B_m=candidate.B_m,
        L_m=candidate.L_m,
        h_m=candidate.h_m,
        verdict=candidate.overall_status,
        failed=[o for o in outcomes if o.status is CheckStatus.FAIL],
        warnings=[o for o in outcomes if o.status is CheckStatus.WARNING],
        not_verified=[o for o in outcomes if o.status is CheckStatus.NOT_VERIFIED],
        passed=[o for o in outcomes if o.status is CheckStatus.PASS],
        informative=[o for o in outcomes if o.status is CheckStatus.INFO],
        search_note=search_note,
    )


def explain_discarded(discarded: DiscardedAlternative) -> Explanation:
    if discarded.representative is None:
        return Explanation(
            alternative_id=discarded.id,
            B_m=discarded.B_m,
            L_m=discarded.L_m,
            h_m=None,
            verdict=CheckStatus.FAIL,
            failed=[],
            warnings=[],
            not_verified=[],
            passed=[],
            informative=[],
            search_note="No se evaluó ningún peralte (rango de h vacío).",
        )

    if discarded.pruned_early and discarded.prune_reason:
        note = discarded.prune_reason
    else:
        lo, hi = discarded.h_range_tried_m
        note = (
            f"Se probaron {discarded.n_depths_tried} peraltes entre h={lo:.2f} m y h={hi:.2f} m; "
            f"ninguno cumple. Se detalla el intento con h={discarded.representative.h_m:.2f} m "
            f"(el más favorable estructuralmente)."
        )
    return explain_candidate(discarded.representative, discarded.id, search_note=note)


def explain_alternative(alternative: Alternative) -> Explanation:
    return explain_candidate(alternative.candidate, alternative.id)
