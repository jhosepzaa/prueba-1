"""Función de puntuación configurable (sección 10 del encargo original).

DECISIÓN ACORDADA (punto 8 de la corrección del usuario): el MVP NO usa costo
monetario, porque no existe una base de precios configurable. Los criterios son
métricas físicas medibles:

    Score = w_volumen  * volumen_concreto_normalizado
          + w_acero    * masa_acero_normalizada
          + w_dimension* dimensión_máxima_normalizada
          + w_complejidad * complejidad_constructiva_normalizada

Menor score = mejor. Todos los pesos son configurables.

NORMALIZACIÓN MIN-MAX DENTRO DEL POOL VÁLIDO
--------------------------------------------
Cada métrica se lleva a [0, 1] usando el mínimo y el máximo observados entre las
alternativas válidas. Esto es lo que hace que los pesos sean COMPARABLES entre sí:
sin normalizar, sumar "2.0 m3 de concreto" con "180 kg de acero" daría un peso
implícito arbitrario a la métrica de mayor magnitud numérica.

Consecuencia que el ingeniero debe conocer: el score es RELATIVO al conjunto
evaluado. Cambiar el rango de búsqueda cambia los scores (aunque rara vez el
orden). Por eso el ranking siempre se acompaña de las métricas crudas.

Cuando todas las alternativas tienen el mismo valor en una métrica, esa métrica
se normaliza a 0 para todas (no aporta a la discriminación) en vez de producir
una división por cero.

NO ES UNA FUNCIÓN NORMATIVA. Es un criterio de decisión de proyecto; ninguna
norma prescribe cómo ponderar economía contra constructibilidad.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from engine.optimization.alternative_generator import Alternative


class ScoreWeights(BaseModel):
    """Pesos configurables. No necesitan sumar 1: se normalizan internamente para
    que el score quede en [0, 1] y sea legible."""

    w_concrete_volume: float = Field(default=0.35, ge=0.0)
    w_steel_mass: float = Field(default=0.30, ge=0.0)
    w_max_dimension: float = Field(default=0.20, ge=0.0)
    w_constructive_complexity: float = Field(default=0.15, ge=0.0)

    # Reservado para cuando exista una base de precios configurable (punto 8).
    # Mientras sea None, el costo monetario NO participa en el score.
    w_monetary_cost: float | None = Field(
        default=None,
        description="No disponible en el MVP: requiere base de precios configurable.",
    )

    @model_validator(mode="after")
    def _at_least_one_positive(self) -> "ScoreWeights":
        if self.total() <= 0:
            raise ValueError("Al menos un peso debe ser mayor que cero.")
        if self.w_monetary_cost is not None:
            raise ValueError(
                "w_monetary_cost no puede usarse todavía: no existe una base de precios "
                "configurable en el motor. Déjelo en None hasta implementar el módulo de costos."
            )
        return self

    def total(self) -> float:
        return (
            self.w_concrete_volume
            + self.w_steel_mass
            + self.w_max_dimension
            + self.w_constructive_complexity
        )


class MetricBreakdown(BaseModel):
    """Aporte de cada métrica al score final, para que el ingeniero pueda ver por
    qué una alternativa quedó donde quedó."""

    raw_value: float
    normalized: float
    weight: float
    contribution: float


class ScoredAlternative(BaseModel):
    alternative: Alternative
    score: float
    breakdown: dict[str, MetricBreakdown]
    rank: int = 0


def _normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


# Métricas participantes: nombre -> (extractor, atributo de peso)
_METRICS: dict[str, tuple] = {
    "volumen_concreto": (lambda m: m.concrete_volume_m3, "w_concrete_volume"),
    "masa_acero": (lambda m: m.steel_mass_kg, "w_steel_mass"),
    "dimension_maxima": (lambda m: m.max_plan_dimension_m, "w_max_dimension"),
    "complejidad_constructiva": (
        lambda m: m.constructive_complexity_index,
        "w_constructive_complexity",
    ),
}


def score_metric_sets(
    metric_sets: list, weights: ScoreWeights | None = None
) -> list[tuple[float, dict[str, MetricBreakdown]]]:
    """Puntúa a partir de las MÉTRICAS solamente, sin saber qué tipo de zapata las
    produjo.

    Es el núcleo de la puntuación, extraído para que lo compartan la zapata aislada
    y la combinada. Cualquier objeto con los campos de `AlternativeMetrics` sirve:
    el optimizador nunca necesitó conocer la tipología, y duplicar esta aritmética
    para cada una habría sido la vía directa a que divergieran.

    Devuelve (puntuación, desglose) en el mismo orden de entrada. Menor es mejor:
    todas las métricas participantes son costos."""
    if not metric_sets:
        return []
    weights = weights or ScoreWeights()
    weight_total = weights.total()

    normalized_by_metric: dict[str, list[float]] = {}
    raw_by_metric: dict[str, list[float]] = {}
    for name, (extractor, _) in _METRICS.items():
        raw = [extractor(m) for m in metric_sets]
        raw_by_metric[name] = raw
        normalized_by_metric[name] = _normalize(raw)

    salida: list[tuple[float, dict[str, MetricBreakdown]]] = []
    for i in range(len(metric_sets)):
        breakdown: dict[str, MetricBreakdown] = {}
        score = 0.0
        for name, (_, weight_attr) in _METRICS.items():
            w = getattr(weights, weight_attr) / weight_total
            normalized = normalized_by_metric[name][i]
            contribution = w * normalized
            score += contribution
            breakdown[name] = MetricBreakdown(
                raw_value=raw_by_metric[name][i],
                normalized=normalized,
                weight=w,
                contribution=contribution,
            )
        salida.append((score, breakdown))
    return salida


def score_alternatives(
    alternatives: list[Alternative], weights: ScoreWeights | None = None
) -> list[ScoredAlternative]:
    """Puntúa (sin ordenar) el conjunto de alternativas válidas de zapata aislada."""
    puntuadas = score_metric_sets([a.metrics for a in alternatives], weights)
    return [
        ScoredAlternative(alternative=a, score=score, breakdown=breakdown)
        for a, (score, breakdown) in zip(alternatives, puntuadas)
    ]
