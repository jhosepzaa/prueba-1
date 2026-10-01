"""Motivos de descarte de la zapata combinada: diagnóstico por alternativa y agrupación — Fase 2.

POR QUÉ EXISTE
==============
La combinada descartaba geometrías sin conservarlas: solo un contador. Los `discard_reasons`
llevan números en el texto (qmax, cm exigidos...), una misma verificación puede producir
varios textos (sección, desarrollo y separación de una cara) y los descartes por WARNING o
NO VERIFICADO —aceptación PASS_OR_INFO— no producen texto alguno. Con eso el usuario no puede
saber por qué se descartó una planta ni qué verificación la tumbó.

QUÉ HACE Y QUÉ NO
=================
No recalcula ni cambia ningún criterio. Lee lo que el solver ya produjo:

  - `discard_records` (verificación, aspecto, elemento y texto de cada motivo), y
  - la TRAZA, para las entradas que degradan el estado sin dejar texto (WARNING, NO
    VERIFICADO, o un FAIL sin motivo escrito).

y lo normaliza en CAUSAS únicas por alternativa, con una clave determinista:

    (categoría, verificación, aspecto)          p. ej. (PUNZONAMIENTO, punching_C2, CAPACIDAD_...)

Los textos originales se conservan dentro de cada causa: son las categorías globales que la
API y los informes ya usan (CLAUDE.md §5) y no se reescriben.

La CAUSA PRINCIPAL de una alternativa es la primera de mayor severidad en el orden de la
traza. Es una regla de presentación, no de ingeniería: todas las causas se listan.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.results.status import CheckStatus

# Categorías estables por verificación. La clave es el id de traza (o su prefijo, para las
# verificaciones por columna). Un id que no esté aquí NO desaparece: cae en OTRA_VERIFICACION.
CATEGORY_BY_CHECK: dict[str, tuple[str, str]] = {
    "shape_ratio": ("PROPORCION", "Proporción de la zapata (E.050 art. 23.3)"),
    "shallow_foundation": ("ALCANCE", "Cimentación superficial, Df/B <= 5 (E.050 art. 23.1)"),
    "foundation_depth": ("PROFUNDIDAD_CIMENTACION", "Profundidad mínima de cimentación (E.050 art. 26.2)"),
    "min_depth": ("PERALTE_MINIMO", "Peralte mínimo de zapatas (E.060 §15.7)"),
    "sliding": ("ESTABILIDAD", "Estabilidad — deslizamiento (E.020 art. 22)"),
    "overturning_x": ("ESTABILIDAD", "Estabilidad — volcamiento (E.020 art. 21)"),
    "overturning_y": ("ESTABILIDAD", "Estabilidad — volcamiento (E.020 art. 21)"),
    "contact_pressure": ("PRESION_CONTACTO", "Presión de contacto sobre el suelo"),
    "flexure_bottom": ("FLEXION_LONGITUDINAL", "Flexión longitudinal"),
    "flexure_top": ("FLEXION_LONGITUDINAL", "Flexión longitudinal"),
    "shear_longitudinal": ("CORTANTE_LONGITUDINAL", "Cortante longitudinal (concreto solo, C-V)"),
    "shear_transversal": ("CORTANTE_TRANSVERSAL", "Cortante transversal (E.060 §11.12.1.1)"),
    "transverse_strip_": ("FRANJA_TRANSVERSAL", "Franja transversal bajo columna"),
    "punching_": ("PUNZONAMIENTO", "Punzonamiento"),
}
OTHER_CATEGORY = ("OTRA_VERIFICACION", "Otra verificación")

_SEVERITY = {
    CheckStatus.FAIL: 3,
    CheckStatus.NOT_VERIFIED: 2,
    CheckStatus.WARNING: 1,
    CheckStatus.INFO: 0,
    CheckStatus.PASS: 0,
}


def category_of(check_id: str) -> tuple[str, str]:
    """(código, etiqueta) de la verificación. Exacto primero, luego por prefijo."""
    if check_id in CATEGORY_BY_CHECK:
        return CATEGORY_BY_CHECK[check_id]
    for clave, valor in CATEGORY_BY_CHECK.items():
        if clave.endswith("_") and check_id.startswith(clave):
            return valor
    return OTHER_CATEGORY


class DiscardCause(BaseModel):
    """Una causa única de descarte de UNA alternativa."""

    category: str
    label: str
    check_id: str
    aspect: str
    element: str | None = None
    status: str = Field(..., description="Estado de la entrada de traza: FAIL, NO VERIFICADO, WARNING")
    code_reference: str = ""
    governing_combo: str | None = None
    texts: list[str] = Field(default_factory=list, description="Motivos originales, sin reescribir")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.category, self.check_id, self.aspect)


class DiscardDiagnosis(BaseModel):
    """Por qué se descartó UNA alternativa: todas sus causas y la principal."""

    status: str
    causes: list[DiscardCause]

    @property
    def primary(self) -> DiscardCause | None:
        return self.causes[0] if self.causes else None


def diagnose_combined_discard(result) -> DiscardDiagnosis:
    """Causas únicas y deterministas de un `CombinedFootingResult` no aceptado.

    Orden: severidad descendente y, a igual severidad, el orden de la traza (el del informe).
    Cada entrada de traza con estado distinto de PASS/INFO produce al menos una causa; los
    motivos escritos por el solver la detallan por aspecto."""
    entradas = {e.id: (i, e) for i, e in enumerate(result.trace.entries) if e.scope is None}
    causas: dict[tuple[str, str, str], DiscardCause] = {}
    orden: dict[tuple[str, str, str], tuple[int, int]] = {}

    def agregar(check_id: str, aspect: str, element: str | None, texto: str | None, sub: int):
        i, e = entradas.get(check_id, (len(entradas), None))
        estado = e.status if e is not None else CheckStatus.FAIL
        codigo, etiqueta = category_of(check_id)
        clave = (codigo, check_id, aspect)
        if clave not in causas:
            causas[clave] = DiscardCause(
                category=codigo, label=etiqueta, check_id=check_id, aspect=aspect, element=element,
                status=estado.value,
                code_reference=e.code_reference if e is not None else "",
                governing_combo=e.governing_combo if e is not None else None,
            )
            orden[clave] = (i, sub)
        if texto is not None and texto not in causas[clave].texts:
            causas[clave].texts.append(texto)

    registrados: set[str] = set()
    for n, r in enumerate(getattr(result, "discard_records", []) or []):
        agregar(r.check_id, r.aspect, r.element, r.text, n)
        registrados.add(r.check_id)

    # Entradas que degradan el estado sin motivo escrito (WARNING, NO VERIFICADO, o FAIL).
    for check_id, (i, e) in entradas.items():
        if _SEVERITY[e.status] == 0 or check_id in registrados:
            continue
        aspecto = {
            CheckStatus.FAIL: "no_cumple",
            CheckStatus.NOT_VERIFIED: "no_verificado",
            CheckStatus.WARNING: "advertencia",
        }[e.status]
        agregar(check_id, aspecto, None, None, 0)

    lista = sorted(
        causas.values(),
        key=lambda c: (-_SEVERITY[CheckStatus(c.status)], orden[c.key], c.aspect),
    )
    return DiscardDiagnosis(status=result.overall_status.value, causes=lista)


# =========================================================================
# Agrupación sobre un barrido
# =========================================================================


class DiscardExample(BaseModel):
    length_m: float
    width_m: float
    h_m: float
    texts: list[str] = Field(default_factory=list)


class CombinedDiscardGroup(BaseModel):
    """Un motivo normalizado y cuántas geometrías descartó."""

    category: str
    label: str
    aspect: str
    status: str
    count: int = Field(0, description="Geometrías descartadas con esta causa (una puede tener varias)")
    primary_count: int = Field(0, description="Geometrías cuya causa PRINCIPAL es esta")
    check_ids: list[str] = Field(default_factory=list)
    elements: list[str] = Field(default_factory=list)
    code_references: list[str] = Field(default_factory=list)
    has_written_reason: bool = Field(
        False,
        description=(
            "True si el solver escribió un motivo de descarte para esta causa. False: la entrada "
            "de traza degradó el estado sin texto (WARNING, NO VERIFICADO o un FAIL sin motivo)."
        ),
    )
    example: DiscardExample | None = None


class UnresolvedGroup(BaseModel):
    """Geometrías evaluadas que el solver no pudo resolver (ValueError)."""

    reason: str
    count: int = 0
    example: DiscardExample | None = None


def _clave_grupo(c: DiscardCause) -> tuple[str, str, str]:
    return (c.category, c.aspect, c.status)


class CombinedDiscardSummary(BaseModel):
    """Acumulador determinista de descartes de un barrido de la combinada."""

    groups: list[CombinedDiscardGroup] = Field(default_factory=list)
    unresolved: list[UnresolvedGroup] = Field(default_factory=list)
    discarded_by_status: dict[str, int] = Field(default_factory=dict)

    def add(self, result, length_m: float, width_m: float, h_m: float) -> DiscardDiagnosis:
        diag = diagnose_combined_discard(result)
        self.discarded_by_status[diag.status] = self.discarded_by_status.get(diag.status, 0) + 1
        vistos: set[tuple[str, str, str]] = set()
        por_clave = {(g.category, g.aspect, g.status): g for g in self.groups}
        for c in diag.causes:
            clave = _clave_grupo(c)
            g = por_clave.get(clave)
            if g is None:
                g = CombinedDiscardGroup(category=c.category, label=c.label, aspect=c.aspect, status=c.status)
                self.groups.append(g)
                por_clave[clave] = g
            if clave not in vistos:
                g.count += 1
                vistos.add(clave)
                if g.example is None:
                    g.example = DiscardExample(length_m=length_m, width_m=width_m, h_m=h_m, texts=list(c.texts))
            if c.texts:
                g.has_written_reason = True
            if c.check_id not in g.check_ids:
                g.check_ids.append(c.check_id)
            if c.element is not None and c.element not in g.elements:
                g.elements.append(c.element)
            if c.code_reference and c.code_reference not in g.code_references:
                g.code_references.append(c.code_reference)
        if diag.primary is not None:
            por_clave[_clave_grupo(diag.primary)].primary_count += 1
        return diag

    def add_unresolved(self, message: str, length_m: float, width_m: float, h_m: float) -> None:
        # El mensaje lleva números; la categoría es lo que precede a los dos puntos.
        motivo = message.split(":", 1)[0].strip() or "Geometría no resuelta"
        for g in self.unresolved:
            if g.reason == motivo:
                g.count += 1
                return
        self.unresolved.append(UnresolvedGroup(
            reason=motivo, count=1,
            example=DiscardExample(length_m=length_m, width_m=width_m, h_m=h_m, texts=[message]),
        ))

    def sorted(self) -> "CombinedDiscardSummary":
        """Orden determinista: más frecuentes primero; a igualdad, por categoría y aspecto."""
        grupos = [
            g.model_copy(update={
                "check_ids": sorted(g.check_ids), "elements": sorted(g.elements),
                "code_references": sorted(g.code_references),
            })
            for g in sorted(self.groups, key=lambda g: (-g.count, -g.primary_count, g.category, g.aspect, g.status))
        ]
        return CombinedDiscardSummary(
            groups=grupos,
            unresolved=sorted(self.unresolved, key=lambda u: (-u.count, u.reason)),
            discarded_by_status=dict(sorted(self.discarded_by_status.items())),
        )
