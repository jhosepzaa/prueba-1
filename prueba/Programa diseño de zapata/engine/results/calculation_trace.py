"""Trazabilidad de cálculo -- alimenta tanto la explicación de descartes (sección
12 del encargo original) como el futuro reporte de cálculo (sección 15), sin
duplicar lógica entre ambos (mejora #2 aceptada en la Fase 1).

Campos mínimos exigidos por el usuario (punto 6 de la corrección de Fase 2):
id, descripción, ecuación, ecuación con valores sustituidos, resultado, unidades,
hipótesis, combinación utilizada, código normativo, artículo/sección, estado.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.results.status import CheckStatus

# Centinela: distingue «no me importa el ámbito» de «quiero el ámbito None».
_UNSET = object()


class CalculationTraceEntry(BaseModel):
    id: str = Field(..., description='Identificador, p.ej. "flexure_x", "punching"')
    scope: str | None = Field(
        default=None,
        description=(
            'Componente al que pertenece la entrada cuando el resultado tiene varios: '
            '"zap_ext", "zap_int", "viga", "sistema". None en una tipología de un solo '
            'componente, que es el caso de la zapata aislada. La unicidad es del par '
            '(scope, id), no del id solo.'
        ),
    )
    description: str = Field(..., description="Qué se está verificando, en lenguaje llano")
    equation_symbolic: str = Field(..., description='Ecuación en forma simbólica, p.ej. "Vc = 0.17*sqrt(fc)*bw*d"')
    equation_substituted: str = Field(..., description="Misma ecuación con los valores numéricos sustituidos")
    result_value: float = Field(..., description="Resultado numérico de la ecuación")
    result_unit: str = Field(..., description='Unidad del resultado, p.ej. "kN", "MPa", "m"')
    hypotheses: list[str] = Field(
        default_factory=list,
        description="Supuestos aplicados en este cálculo (p.ej. incrementos opcionales activados, interpretaciones pendientes)",
    )
    governing_combo: str | None = Field(
        default=None, description="Nombre de la combinación de carga que gobierna este check específico"
    )
    code_name: str = Field(..., description='Código normativo de origen, p.ej. "E.060", "E.050", o "N/A (práctica estándar)"')
    code_reference: str = Field(..., description='Artículo/sección/ecuación exacta, p.ej. "§11.12.2.1, ec. 11-41"')
    status: CheckStatus = Field(..., description="PASS / FAIL / WARNING")
    open_tbd: str | None = Field(
        default=None,
        description=(
            'Identificador del pendiente abierto que impide verificar esta entrada, '
            'p.ej. "TBD-C1". Presente SOLO en entradas NO VERIFICADO cuya causa es que '
            'no existe criterio normativo que aplicar —no que una comprobación haya '
            'salido mal—. Es lo que permite distinguir «el programa comprobó todo lo '
            'que sabe comprobar y salió bien» de «el programa no puede pronunciarse», '
            'sin que ninguna de las dos se confunda con «cumple».'
        ),
    )


class CalculationTrace(BaseModel):
    """Contenedor ordenado de entradas de trazabilidad para una alternativa completa."""

    entries: list[CalculationTraceEntry] = Field(default_factory=list)

    def add(self, entry: CalculationTraceEntry) -> None:
        self.entries.append(entry)

    def by_id(
        self, entry_id: str, scope: str | None | object = _UNSET
    ) -> CalculationTraceEntry | None:
        """Busca una entrada por su identificador.

        DEFECTO QUE ESTA FIRMA CORRIGE. La versión anterior devolvía la PRIMERA
        coincidencia. Mientras los identificadores fueron únicos eso fue inofensivo,
        pero en cuanto un resultado tiene dos zapatas, `"punching"` aparece dos veces
        y devolver la primera mostraría el punzonamiento de una columna bajo el
        rótulo de la otra, sin que nada fallara.

        Ahora, omitir `scope` con varias coincidencias levanta un error en vez de
        elegir en silencio. El comportamiento con identificadores únicos —la zapata
        aislada y la combinada— no cambia."""
        if scope is not _UNSET:
            for e in self.entries:
                if e.id == entry_id and e.scope == scope:
                    return e
            return None

        coincidencias = [e for e in self.entries if e.id == entry_id]
        if len(coincidencias) > 1:
            ambitos = [e.scope for e in coincidencias]
            raise ValueError(
                f"El identificador «{entry_id}» aparece {len(coincidencias)} veces, en los "
                f"ámbitos {ambitos}. Indique cuál con by_id({entry_id!r}, scope=...): "
                f"devolver la primera mostraría el resultado de un componente bajo el "
                f"rótulo de otro."
            )
        return coincidencias[0] if coincidencias else None

    def by_scope(self, scope: str | None) -> list[CalculationTraceEntry]:
        """Todas las entradas de un componente, en orden."""
        return [e for e in self.entries if e.scope == scope]

    def scopes(self) -> list[str | None]:
        """Ámbitos presentes, en orden de primera aparición."""
        vistos: list[str | None] = []
        for e in self.entries:
            if e.scope not in vistos:
                vistos.append(e.scope)
        return vistos

    def overall_status(self) -> CheckStatus:
        if not self.entries:
            return CheckStatus.WARNING
        return CheckStatus.worst([e.status for e in self.entries])

    def failing_entries(self) -> list[CalculationTraceEntry]:
        return [e for e in self.entries if e.status is CheckStatus.FAIL]

    def warning_entries(self) -> list[CalculationTraceEntry]:
        return [e for e in self.entries if e.status is CheckStatus.WARNING]

    def open_tbd_entries(self) -> list[CalculationTraceEntry]:
        """Entradas bloqueadas por un pendiente abierto, en orden de traza."""
        return [e for e in self.entries if e.open_tbd]

    def open_tbds(self) -> list[str]:
        """Identificadores de los pendientes abiertos presentes, sin repetir."""
        vistos: list[str] = []
        for e in self.open_tbd_entries():
            if e.open_tbd not in vistos:
                vistos.append(e.open_tbd)
        return vistos

    def status_of_implemented_checks(self) -> CheckStatus:
        """Peor estado IGNORANDO las entradas de pendiente abierto.

        Responde a «de lo que este programa sabe comprobar, ¿algo sale mal?». No
        responde a «¿cumple?»: eso exige además que no quede ningún pendiente abierto,
        y por eso las dos preguntas viven en métodos distintos y con nombres que no se
        confunden."""
        implementadas = [e.status for e in self.entries if not e.open_tbd]
        if not implementadas:
            return CheckStatus.WARNING
        return CheckStatus.worst(implementadas)
