"""Catálogo de tipologías — punto de partida de la integración global.

QUÉ ES
======
Una descripción ÚNICA, en datos, de lo que el programa ofrece para cada tipología: sus
endpoints, cómo decide qué alternativa acepta, qué vocabulario de estados usa, qué
capacidades de presentación tiene, qué pendientes normativos la afectan y en qué difiere
de las otras dos.

POR QUÉ EXISTE ANTES DE UNIR NADA
=================================
Las tres tipologías se construyeron en fases distintas y no son simétricas. Unificarlas
—una vista común, una comparación entre tipologías— sin haber escrito dónde difieren
llevaría a presentar como equivalentes resultados que se obtienen con criterios
distintos. Este catálogo hace explícitas esas diferencias. Los tests de
`tests/test_integration_typology_catalog.py` lo contrastan contra el código real, de modo
que no puede quedarse desactualizado en silencio.

NADA DE ESTE MÓDULO ES NORMATIVO NI CALCULA. Las referencias normativas que figuran son
las que el propio motor ya cita.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from engine.results.status import CheckStatus
from engine.results.vocabulary import STATUS_VOCABULARY, VOCABULARY_NOTE


class AcceptanceRule(str, Enum):
    """Cómo decide cada generador que una alternativa sobrevive al barrido."""

    NO_FAIL = "NO_FAIL"
    """Se acepta todo lo que no sea FAIL. Es la máquina de estados del proyecto: WARNING y
    NO VERIFICADO bloquean el PASS pero no descartan."""

    PASS_OR_INFO = "PASS_OR_INFO"
    """Solo se acepta PASS o INFO. WARNING y NO VERIFICADO se descartan."""


def accepts(rule: AcceptanceRule, status: CheckStatus) -> bool:
    if rule is AcceptanceRule.NO_FAIL:
        return status is not CheckStatus.FAIL
    return status in (CheckStatus.PASS, CheckStatus.INFO)


class TypologyEntry(BaseModel):
    id: str
    name: str
    design_endpoint: str
    report_endpoint: str
    normative_basis: list[str]
    acceptance_rule: AcceptanceRule
    acceptance_note: str
    status_vocabulary: list[str]
    vocabulary_note: str
    capabilities: dict[str, bool]
    open_tbds: list[str] = Field(default_factory=list)


class KnownDifference(BaseModel):
    """Diferencia entre tipologías que impide tratarlas como equivalentes y que necesita
    una decisión antes de integrarlas. Se lista para no ocultarla.

    Una diferencia RESUELTA no se borra: se marca con `resolution`. El historial de una
    decisión cerrada es parte del expediente (CLAUDE.md §16), y quien lea el catálogo
    necesita distinguir «esto está pendiente» de «esto se decidió y así quedó»."""

    id: str
    typologies: list[str]
    description: str
    consequence: str
    decision_needed: str
    resolution: str | None = Field(
        default=None,
        description=(
            "Si la diferencia ya se decidió: qué se decidió y qué quedó implementado. "
            "None significa que sigue abierta."
        ),
    )

    @property
    def is_open(self) -> bool:
        return self.resolution is None


class TypologyCatalog(BaseModel):
    typologies: list[TypologyEntry]
    known_differences: list[KnownDifference]


# Pendiente 8: vocabulario ÚNICO para las tres tipologías, en
# `engine/results/vocabulary.py`. Antes había tres: el de la aislada (donde «ACEPTADA» era
# PASS), el cerrado de la conectada (donde «ACEPTADA» era WARNING) y el CheckStatus crudo
# de la combinada. La palabra ambigua desapareció y «DESCARTADA/RECHAZADA» se unificó.
_VOCAB_UNICO = list(STATUS_VOCABULARY)


CATALOG = TypologyCatalog(
    typologies=[
        TypologyEntry(
            id="aislada",
            name="Zapata aislada",
            design_endpoint="/api/design",
            report_endpoint="/api/report",
            normative_basis=["E.060 Cap. 15", "E.060 §11.12", "E.050 art. 17.1", "E.050 art. 28.1"],
            acceptance_rule=AcceptanceRule.NO_FAIL,
            acceptance_note="`solve_depth` acepta el primer peralte cuyo estado no es FAIL.",
            status_vocabulary=_VOCAB_UNICO,
            vocabulary_note=VOCABULARY_NOTE,
            capabilities={
                "tabla_comparativa": True, "frente_pareto": True, "vista_3d": True,
                "esquema_2d": True, "memoria_html": True, "explicacion_descartes": True,
            },
        ),
        TypologyEntry(
            id="combinada",
            name="Zapata combinada",
            design_endpoint="/api/design-combined",
            report_endpoint="/api/report-combined",
            normative_basis=["E.060 §15.10", "E.060 §15.4.1", "E.050 art. 23.3", "E.060 §7.7.1"],
            acceptance_rule=AcceptanceRule.NO_FAIL,
            acceptance_note=(
                "`generate_combined_alternatives` acepta el primer peralte cuyo estado no es "
                "FAIL (decisión 6). Una alternativa NO VERIFICADA o con observaciones se "
                "conserva con su estado; `accepted_and_compliant` son las PASS o INFO."
            ),
            status_vocabulary=_VOCAB_UNICO,
            vocabulary_note=(
                VOCABULARY_NOTE
                + " La respuesta de la combinada entrega ADEMÁS el CheckStatus crudo en `status`, "
                "que es el que usan los criterios; el rótulo va en `status_label`."
            ),
            capabilities={
                "tabla_comparativa": True, "frente_pareto": True, "vista_3d": True,
                "esquema_2d": True, "memoria_html": True, "explicacion_descartes": True,
            },
        ),
        TypologyEntry(
            id="conectada",
            name="Cimentación conectada",
            design_endpoint="/api/design-connected",
            report_endpoint="/api/report-connected",
            normative_basis=["E.050 art. 23.2", "E.050 art. 28.1", "E.060 §21.12.3", "E.030 art. 65.1"],
            acceptance_rule=AcceptanceRule.NO_FAIL,
            acceptance_note=(
                "`generate_connected_alternatives` acepta todo lo que no es FAIL. Mientras "
                "TBD-C1 siga abierto ninguna alternativa alcanza PASS."
            ),
            status_vocabulary=_VOCAB_UNICO,
            vocabulary_note=VOCABULARY_NOTE,
            capabilities={
                "tabla_comparativa": True, "frente_pareto": True, "vista_3d": True,
                "esquema_2d": True, "memoria_html": True, "explicacion_descartes": True,
            },
            open_tbds=["TBD-C1", "TBD-C4", "TBD-C11"],
        ),
    ],
    known_differences=[
        KnownDifference(
            id="ACEPTACION_COMBINADA",
            typologies=["aislada", "combinada", "conectada"],
            description=(
                "La combinada acepta solo PASS o INFO; la aislada y la conectada aceptan todo "
                "lo que no es FAIL, como establece la máquina de estados del proyecto."
            ),
            consequence=(
                "Hasta la corrección D4 la diferencia era latente: la combinada no emitía "
                "WARNING ni NO VERIFICADO. Desde D4, una combinada con fuerzas horizontales "
                "queda NO VERIFICADA y el barrido la descartaba, mientras que la aislada y la "
                "conectada la mostrarían con su estado. Con sismo o viento eso dejaba la "
                "tipología entera sin alternativas, en TODOS los peraltes."
            ),
            decision_needed=(
                "Alinear la combinada con NO_FAIL (cambia qué alternativas devuelve el "
                "barrido combinado) o declarar la diferencia como deliberada."
            ),
            resolution=(
                "RESUELTA (decisión 6): la combinada se alineó con NO_FAIL. Las tres "
                "tipologías usan hoy el mismo criterio —solo el FAIL descarta— y la combinada "
                "separa `accepted_and_compliant` (PASS o INFO) de `not_verified` y "
                "`accepted_with_findings`. No cambió ninguna ecuación, hipótesis ni estado de "
                "verificación: cambió qué alternativas sobreviven al barrido. Ver "
                "docs/decision6_aceptacion_combinada.md."
            ),
        ),
        KnownDifference(
            id="ESTABILIDAD_COMBINADA",
            typologies=["combinada"],
            description=(
                "La combinada no verifica deslizamiento ni volcamiento. La aislada lo hace en "
                "`soil/stability.py` y la conectada lo hereda en cada zapata."
            ),
            consequence=(
                "Corregido de forma conservadora (D4): con fuerzas horizontales la combinada "
                "quedaba NO VERIFICADA y nunca PASS. Antes salía PASS en silencio. Sin fuerzas "
                "horizontales el momento queda acotado por la exigencia de resultante dentro "
                "del núcleo central."
            ),
            decision_needed=(
                "Implementar la estabilidad de la zapata combinada (resultante de varias "
                "columnas, μ y FS declarados por el proyectista) con tests independientes."
            ),
            resolution=(
                "RESUELTA (pendiente 7): `engine/foundation/combined_stability.py` verifica "
                "deslizamiento y volcamiento sobre la resultante de todas las columnas, con el "
                "criterio de `engine/soil/stability.py` —solo carga muerta estabiliza (E.020 art. "
                "20.1), μ del proyectista, FS adoptados en D10-2b— y la ENVOLVENTE del momento "
                "volcador (opción B). La declaración D4 queda sustituida por la verificación "
                "real. La formulación se extendió después a la aislada y a las zapatas de la "
                "conectada: ver FORMULACION_VOLTEO. "
                "Detalle en docs/pendiente7_estabilidad_combinada.md."
            ),
        ),
        KnownDifference(
            id="FORMULACION_VOLTEO",
            typologies=["aislada", "combinada"],
            description=(
                "El momento volcador se plantea distinto en cada tipología. La combinada usa la "
                "resultante de todas las columnas —incluye el término P_i·offset_i de cada carga "
                "descentrada— y la ENVOLVENTE de las lecturas con carga total y con solo la "
                "estabilizante. La aislada toma |M| de la combinación, sin término de "
                "excentricidad y sin envolvente."
            ),
            consequence=(
                "La combinada tiene hoy la formulación más exacta de las dos. En la aislada, una "
                "columna descentrada no aporta su momento de excentricidad al volcamiento, y una "
                "carga no muerta con excentricidad favorable puede reducir el momento volcador."
            ),
            decision_needed=(
                "Alinear la zapata aislada con la formulación de la combinada. Quedó fuera del "
                "alcance del pendiente 7 por decisión del usuario (2026-09-18) y TOCARÍA "
                "BASELINES CONGELADOS."
            ),
            resolution=(
                "RESUELTA (aprobada por el usuario el 2026-09-19). Las tres tipologías usan la "
                "misma formulación —término P·offset y envolvente— y un solo ayudante, "
                "`engine.soil.stability.axis_moments_kNm`. El motivo no fue uniformar por "
                "uniformar: la aislada era incoherente CONSIGO MISMA, porque su presión de "
                "contacto ya reducía la resultante con ex = (M + P·offset)/(P + W) mientras su "
                "volcamiento usaba |M|. El error iba en las dos direcciones: falso PASS en la "
                "zapata de lindero sin momento propio (caso 18 pasa a FAIL con FS 1,48) y falso "
                "conservadurismo en la zapata exterior de la conectada, que publicaba FS de 1,54 "
                "a 1,94 para una resultante centrada. Se regeneraron 19 casos congelados; ninguna "
                "aceptación cambió. Diagnóstico en docs/formulacion_volteo_analisis.md e impacto "
                "en docs/freeze_formulacion_volteo.md."
            ),
        ),
        KnownDifference(
            id="VOCABULARIO_ACEPTADA",
            typologies=["aislada", "combinada", "conectada"],
            description=(
                "«ACEPTADA» significa «sobrevive al barrido» en la conectada y, desde la "
                "decisión 6, también en la combinada: en ambas puede estar NO VERIFICADA. La "
                "aislada rotula con su propio vocabulario de informe."
            ),
            consequence=(
                "Una vista común que muestre el rótulo sin su tipología haría pasar una "
                "conectada o una combinada NO VERIFICADA por una aislada que cumple. Por eso "
                "la combinada entrega el estado crudo en cada alternativa y en cada fila de "
                "la tabla comparativa."
            ),
            resolution=(
                "RESUELTA (pendiente 8): vocabulario ÚNICO para las tres tipologías —CONFORME, "
                "ACEPTADA CON OBSERVACIONES, NO VERIFICADA, RECHAZADA— en "
                "`engine/results/vocabulary.py`. Desaparece «ACEPTADA» a secas, que era la "
                "palabra ambigua, y «DESCARTADA/RECHAZADA» se unifica. Es solo rotulado: la "
                "semántica interna no cambia y `accepted`, `not_verified` y "
                "`accepted_and_compliant` siguen significando lo mismo. Equivalencias con los "
                "rótulos anteriores en `LEGACY_EQUIVALENCE`. Detalle en "
                "docs/pendiente8_vocabulario_estados.md."
            ),
            decision_needed=(
                "Adoptar un vocabulario único para las tres —el cerrado de la conectada "
                "separa aceptación de conformidad— o mostrar siempre el estado crudo junto al "
                "rótulo."
            ),
        ),
        KnownDifference(
            id="PRESENTACION_COMBINADA",
            typologies=["combinada"],
            description=(
                "La combinada tiene tabla comparativa, frente de Pareto, explicación de "
                "descartes agrupada (Fase 2), esquema 2D (pendiente 1) y vista 3D "
                "(pendiente 3): la misma presentación que las otras dos tipologías."
            ),
            consequence=(
                "La paridad de presentación está COMPLETA. Desde la decisión 6 la tabla incluye "
                "además las alternativas NO VERIFICADAS, con su estado en cada fila, y tanto el "
                "esquema como la vista 3D llevan el estado junto al dibujo."
            ),
            decision_needed=(
                "Añadir el esquema 2D a la combinada; no depende de decisiones de ingeniería."
            ),
            resolution=(
                "RESUELTA. Parte 2D (pendiente 1): `CombinedSceneDTO` sitúa huella, peralte y "
                "columnas con la geometría que usó el cálculo, y la respuesta lo entrega en "
                "`scene`. Parte 3D (pendiente 3): `BoxScene3D` consume ESE MISMO DTO, de modo "
                "que no hay una segunda fuente de posiciones que pueda divergir; no dibuja "
                "armado, porque el motor no lo resuelve para esta tipología. La paridad de "
                "presentación entre las tres tipologías queda completa. Detalle en "
                "docs/pendiente3_vista_3d.md."
            ),
        ),
    ],
)
