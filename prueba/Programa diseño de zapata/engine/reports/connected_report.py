"""Memoria de cálculo de zapata conectada — Fase 4E.

EL INFORME SE EMITE AUNQUE NADA ESTÉ VERIFICADO
===============================================
Esta tipología no puede alcanzar PASS mientras TBD-C1 siga abierto: la premisa de
rigidez que sostiene el modelo no tiene criterio normativo que verificar. Negarse a
emitir el informe por eso dejaría la herramienta inservible; emitirlo como si fuera un
diseño conforme sería peor. El informe se emite, y lo primero que dice —antes de
cualquier tabla de alternativas— es en qué estado está y qué pendiente lo causa.

EL VOCABULARIO ES CERRADO Y NO SE MEZCLA
========================================
Cuatro palabras, cuatro significados que no se solapan:

* **RECHAZADA** — el sistema no se pudo plantear, o alguna verificación salió FAIL.
* **ACEPTADA** — ninguna verificación implementada la descarta. Nada más que eso.
* **NO VERIFICADA** — aceptada, pero con un pendiente abierto que impide pronunciarse.
* **CONFORME** — aceptada, sin pendientes abiertos y sin observaciones. Hoy, ninguna.

La palabra «válida» no aparece en este módulo, y hay un test que lo comprueba sobre el
HTML producido. «Válida» se lee como «correcta», y presentar como correcta una
alternativa que depende de una funcionalidad no implementada es exactamente lo que el
encargo prohíbe.

NO CALCULA NADA
===============
Misma regla que los otros dos informes: cada número que muestra sale del resultado del
motor o de su `CalculationTrace`. Aquí solo se decide qué se enseña y en qué orden.
"""

from __future__ import annotations

from html import escape

from pydantic import BaseModel, Field

from engine.optimization.connected_generator import (
    ConnectedAlternative,
    ConnectedAlternativeSet,
)
from engine.reports.report_units import ReportUnits
from engine.results.status import CheckStatus
from engine.results.vocabulary import ESTADO_CONFORME as V_CONFORME
from engine.results.vocabulary import ESTADO_CON_OBSERVACIONES as V_CON_OBSERVACIONES
from engine.results.vocabulary import ESTADO_NO_VERIFICADA as V_NO_VERIFICADA
from engine.results.vocabulary import ESTADO_RECHAZADA as V_RECHAZADA
from engine.results.vocabulary import status_label as vocabulary_status_label

# Vocabulario de estado PROPIO de esta tipología.
#
# ACTUALIZADO en el pendiente 8: ahora SÍ se comparte el rótulo, porque el vocabulario es
# uno solo y la palabra ambigua desapareció. Antes no se reutilizaba
# `report_model.status_label` a propósito: allí PASS se rotulaba
# «ACEPTADA», y aquí «aceptada» significaba otra cosa —sobrevivir al barrido—. Compartir
# la función haría que la misma palabra significase dos cosas distintas en dos informes
# del mismo programa, que es el modo en que un vocabulario cerrado se deshace.
def _tabla_composicion(alternativa: ConnectedAlternative) -> str:
    """Fase 10C. Qué casos, con qué factor y desde qué origen, forman cada carga corregida.
    Vacío en el modo directo: allí no hay composición y no se infiere."""
    bloques = []
    for d in alternativa.result.statics:
        ce, ci = d.exterior_corrected_composition, d.interior_corrected_composition
        if ce is None or ci is None:
            continue
        filas = "".join(
            f"<tr><td>{_e(a.origin or '')}</td><td>{_e(a.case_name)}</td><td>{_e(a.kind)}</td>"
            f"<td>{_e(a.level or '—')}</td><td class='num'>{a.factor:g}</td>"
            f"<td class='num'>{a.P_kN:+.2f}</td><td class='num'>{b.P_kN:+.2f}</td></tr>"
            for a, b in zip(ce.components, ci.components)
        )
        bloques.append(
            f"<h4>Combinación {_e(d.combo_name)} ({_e(d.combo_type)})</h4>"
            "<table><thead><tr><th>Origen</th><th>Caso</th><th>Tipo</th><th>Nivel</th>"
            "<th>Factor</th><th>P zapata exterior [kN]</th><th>P zapata interior [kN]</th>"
            f"</tr></thead><tbody>{filas}"
            f"<tr><td colspan='5'><b>Carga corregida</b></td>"
            f"<td class='num'><b>{d.P_ext_corrected_kN:+.2f}</b></td>"
            f"<td class='num'><b>{d.P_int_corrected_kN:+.2f}</b></td></tr></tbody></table>"
        )
    if not bloques:
        return ""
    return (
        "<h3>Composición de las cargas corregidas</h3>"
        "<p class='aviso'>Obtenida por superposición con el mismo reparto (Fase 10C). La "
        "estabilidad cuenta solo la carga muerta (E.020 art. 20.1).</p>" + "".join(bloques)
    )


# Pendiente 8: los rótulos son los del vocabulario ÚNICO. El que cambia es
# ESTADO_ACEPTADA: aquí significaba «sobrevive con reservas» (WARNING), que es justamente
# lo que en la aislada se llamaba «ACEPTADA CON OBSERVACIONES». Ahora se llaman igual.
ESTADO_RECHAZADA = V_RECHAZADA
ESTADO_ACEPTADA = V_CON_OBSERVACIONES
ESTADO_NO_VERIFICADA = V_NO_VERIFICADA
ESTADO_CONFORME = V_CONFORME

_ESTADO_CLASE = {
    CheckStatus.PASS: "ok",
    CheckStatus.INFO: "info",
    CheckStatus.WARNING: "warn",
    CheckStatus.NOT_VERIFIED: "nv",
    CheckStatus.FAIL: "bad",
}

# Qué significa cada pendiente, en una línea, para que el informe no obligue a buscarlo
# en otro documento. El texto describe el hueco; no lo resuelve ni lo minimiza.
TBD_DESCRIPTIONS: dict[str, str] = {
    "TBD-C1": (
        "La premisa de rigidez del conjunto (presión uniforme bajo la zapata de lindero, "
        "o giro como cuerpo rígido) no tiene criterio normativo de verificación en E.060 "
        "ni en E.050. El motor la aplica como hipótesis declarada y no puede comprobarla."
    ),
    "TBD-C4": (
        "Se declaró que la viga de conexión apoya sobre el terreno, y esa reacción no está "
        "modelada. La carga que llega a la zapata interior puede quedar sobrestimada."
    ),
    "TBD-C11": (
        "Con PAR_PURO_EN_ZAPATA, la rama cercana del par no se cierra dentro de la "
        "cimentación. Que la recoja el pórtico es una hipótesis sobre la superestructura "
        "que este motor no comprueba."
    ),
}


def _e(texto: object) -> str:
    return escape(str(texto))


# =========================================================================
# Modelo de datos del bloque de estado
# =========================================================================


class OpenTbdItem(BaseModel):
    """Un pendiente abierto, con lo necesario para entenderlo sin salir del informe."""

    id: str
    description: str
    affected_alternatives: int = Field(
        ..., description="Cuántas alternativas aceptadas bloquea este pendiente"
    )


class ConnectedStatusSummary(BaseModel):
    """Lo que el informe dice ANTES de enseñar ninguna alternativa.

    Existe como modelo y no solo como HTML porque la API sirve exactamente estos mismos
    campos: si el resumen viviera únicamente dentro de la plantilla, el informe y el
    JSON podrían acabar contando cosas distintas."""

    overall_status: CheckStatus = Field(
        ...,
        description=(
            "Estado del conjunto: el MEJOR que alcanza alguna alternativa aceptada, o "
            "FAIL si no hay ninguna. Es lo que gobierna el titular del informe."
        ),
    )
    open_tbds: list[OpenTbdItem] = Field(default_factory=list)

    evaluated_count: int = 0
    accepted_count: int = 0
    not_verified_count: int = 0
    accepted_and_compliant_count: int = 0
    accepted_with_findings_count: int = 0
    rejected_count: int = 0
    rejections_by_reason: dict[str, int] = Field(default_factory=dict)

    truncated: bool = False
    search_note: str = ""

    @property
    def can_claim_compliance(self) -> bool:
        """¿Puede este informe afirmar que algo cumple?

        Solo si existe al menos una alternativa aceptada, sin pendientes abiertos y sin
        observaciones. Mientras TBD-C1 siga abierto es False por construcción, y el
        titular del informe se redacta a partir de aquí —no al revés—."""
        return self.accepted_and_compliant_count > 0

    @property
    def headline(self) -> str:
        """El titular. Nunca afirma «cumple» si `can_claim_compliance` es False."""
        if self.accepted_count == 0:
            # El motivo importa: «no superó las verificaciones» y «no se pudo ni
            # plantear» piden acciones distintas del usuario, y decir lo primero cuando
            # ocurrió lo segundo lo manda a revisar un diseño que nunca llegó a existir.
            motivo = ""
            if self.rejections_by_reason:
                dominante = max(self.rejections_by_reason.items(), key=lambda kv: kv[1])[0]
                motivo = {
                    "DESPEGUE": (
                        " El motivo dominante es DESPEGUE: la excentricidad levanta parte "
                        "del apoyo y el modelo deja de describir el problema. Reduzca la "
                        "excentricidad o aumente el área de apoyo."
                    ),
                    "GEOMETRIA_IMPOSIBLE": (
                        " El motivo dominante es GEOMETRIA_IMPOSIBLE: con esos rangos las "
                        "huellas se solapan o la columna no cabe en su zapata."
                    ),
                    "CARGA_NETA_ASCENDENTE": (
                        " El motivo dominante es CARGA_NETA_ASCENDENTE: bajo alguna zapata "
                        "el suelo devuelve menos que su propio peso y la viga tendría que "
                        "sostenerla; ese diseño no está implementado. Reduzca la zapata "
                        "de la columna menos cargada o aumente la otra."
                    ),
                    "ENTRADA_INVALIDA": (
                        " El motivo dominante es ENTRADA_INVALIDA: el sistema no llega a "
                        "plantearse con los datos declarados."
                    ),
                    "NO_CUMPLE": (
                        " El motivo dominante es NO_CUMPLE: los sistemas se resolvieron "
                        "enteros y alguna verificación resultó FAIL."
                    ),
                }.get(dominante, f" Motivo dominante: {dominante}.")
            return (
                "Ninguna alternativa fue aceptada: los "
                f"{self.rejected_count} sistemas evaluados resultaron RECHAZADOS.{motivo}"
            )
        if not self.can_claim_compliance:
            pendientes = ", ".join(t.id for t in self.open_tbds) or "un pendiente abierto"
            return (
                f"{self.accepted_count} alternativa(s) ACEPTADA(s), todas ellas "
                f"NO VERIFICADAS. Este informe NO declara que ninguna cumpla: quedan "
                f"pendientes sin criterio normativo que aplicar ({pendientes}). El "
                f"resultado es un predimensionamiento trazable, no una verificación "
                f"normativa completa."
            )
        return (
            f"{self.accepted_and_compliant_count} alternativa(s) CONFORME(s) de "
            f"{self.accepted_count} aceptada(s)."
        )


def build_connected_status_summary(
    alternatives: ConnectedAlternativeSet,
) -> ConnectedStatusSummary:
    """Resume un barrido sin tocar ni un número del motor."""
    pendientes = [
        OpenTbdItem(
            id=tbd,
            description=TBD_DESCRIPTIONS.get(
                tbd, "Pendiente abierto sin descripción registrada en el informe."
            ),
            affected_alternatives=sum(1 for a in alternatives.accepted if tbd in a.open_tbds),
        )
        for tbd in alternatives.open_tbds()
    ]

    # El estado del CONJUNTO es el mejor que alguien alcanza: si una sola alternativa
    # llegara a PASS, el informe podría proponerla. Tomar el peor diría que no hay nada
    # utilizable cuando sí lo hay.
    if alternatives.accepted:
        estado = min(
            (a.overall_status for a in alternatives.accepted),
            key=lambda s: s.severity,
        )
    else:
        estado = CheckStatus.FAIL

    return ConnectedStatusSummary(
        overall_status=estado,
        open_tbds=pendientes,
        evaluated_count=alternatives.evaluated_count,
        accepted_count=len(alternatives.accepted),
        not_verified_count=len(alternatives.not_verified),
        accepted_and_compliant_count=len(alternatives.accepted_and_compliant),
        accepted_with_findings_count=len(alternatives.accepted_with_findings),
        rejected_count=len(alternatives.rejected),
        rejections_by_reason=alternatives.rejections_by_reason(),
        truncated=alternatives.truncated,
        search_note=alternatives.search_note,
    )


def alternative_label(alternative: ConnectedAlternative) -> str:
    """Rótulo de UNA alternativa, con el vocabulario cerrado.

    «Aceptada» no asciende a «conforme» por haberse implementado otra verificación: para
    ser conforme no puede quedar ningún pendiente abierto."""
    return vocabulary_status_label(alternative.overall_status, alternative.open_tbds)


# =========================================================================
# Renderizado
# =========================================================================


def _bloque_estado(resumen: ConnectedStatusSummary) -> str:
    """El bloque que va ANTES de la tabla de alternativas. No es negociable su posición:
    quien lea solo la tabla tiene que haber pasado por aquí."""
    clase = _ESTADO_CLASE.get(resumen.overall_status, "info")

    if resumen.open_tbds:
        filas = "".join(
            f"<tr><td><code>{_e(t.id)}</code></td><td>{_e(t.description)}</td>"
            f"<td class='num'>{t.affected_alternatives}</td></tr>"
            for t in resumen.open_tbds
        )
        pendientes = f"""
<table>
<thead><tr><th>Pendiente</th><th>Por qué impide verificar</th>
<th>Alternativas afectadas</th></tr></thead>
<tbody>{filas}</tbody></table>
<p class="aviso">Estos pendientes <b>no son verificaciones que hayan salido mal</b>: son
verificaciones que no existen. No se cierran aportando más datos de entrada — requieren
una decisión de modelación o una disposición normativa de la que hoy no se dispone.</p>"""
    else:
        pendientes = "<p>No hay pendientes abiertos que afecten a estas alternativas.</p>"

    truncado = (
        f'<p class="aviso"><b>Búsqueda truncada.</b> {_e(resumen.search_note)}</p>'
        if resumen.truncated
        else ""
    )

    return f"""
<div class="estado {clase}-caja">
<h2 class="sin-linea">Estado del análisis</h2>
<p class="titular {clase}">{_e(resumen.headline)}</p>
<p>Estado del conjunto:
<span class="{clase}"><b>{_e(resumen.overall_status.value)}</b></span></p>
</div>

<h2>Pendientes abiertos</h2>
{pendientes}
{truncado}
"""


def _bloque_recuento(resumen: ConnectedStatusSummary) -> str:
    """Los cuatro conceptos, separados y con su definición al lado. Un recuento de
    «alternativas encontradas» a secas es lo que permite confundirlos."""
    motivos = (
        "".join(
            f"<tr><td class='sangria'>· {_e(motivo)}</td>"
            f"<td class='num'>{n}</td>"
            f"<td class='def'>Motivo de rechazo</td></tr>"
            for motivo, n in sorted(resumen.rejections_by_reason.items())
        )
        or ""
    )
    conforme_clase = "ok" if resumen.can_claim_compliance else "nv"
    return f"""
<h2>Recuento por categoría</h2>
<table>
<thead><tr><th>Categoría</th><th>N.º</th><th>Qué significa exactamente</th></tr></thead>
<tbody>
<tr><td>Sistemas evaluados</td><td class="num">{resumen.evaluated_count}</td>
    <td class="def">Ternas (zapata de lindero + viga + zapata interior) que el barrido
    llegó a plantear.</td></tr>
<tr><td><b>{ESTADO_RECHAZADA}S</b></td><td class="num">{resumen.rejected_count}</td>
    <td class="def">No se pudieron plantear, o alguna verificación resultó FAIL.</td></tr>
{motivos}
<tr><td><b>{ESTADO_ACEPTADA}S</b></td><td class="num">{resumen.accepted_count}</td>
    <td class="def">Ninguna verificación <i>implementada</i> las descarta.
    <b>Aceptada no significa conforme.</b></td></tr>
<tr><td class="sangria">· de ellas, {ESTADO_NO_VERIFICADA}S</td>
    <td class="num">{resumen.not_verified_count}</td>
    <td class="def">Hay un pendiente abierto y el motor no puede pronunciarse.</td></tr>
<tr><td class="sangria">· de ellas, con observaciones</td>
    <td class="num">{resumen.accepted_with_findings_count}</td>
    <td class="def">Algo de lo comprobado salió con reserva (WARNING).</td></tr>
<tr><td><b>{ESTADO_CONFORME}S</b></td>
    <td class="num {conforme_clase}">{resumen.accepted_and_compliant_count}</td>
    <td class="def">Aceptadas, sin pendientes abiertos y sin observaciones. Son las
    únicas que este informe podría presentar como cumpliendo.</td></tr>
</tbody></table>
"""


def _tabla_alternativas(
    alternativas: ConnectedAlternativeSet, limite: int = 20, u: ReportUnits | None = None
) -> str:
    u = u or ReportUnits()
    if not alternativas.accepted:
        return "<p>No hay alternativas aceptadas que listar.</p>"

    from engine.optimization.connected_generator import rank_connected_alternatives
    from engine.optimization.pareto import DEFAULT_OBJECTIVES, pareto_mask

    todas = rank_connected_alternatives(alternativas.accepted)
    # Fase 4G. El frente se calcula sobre TODAS las aceptadas, no sobre las que caben en
    # la tabla: recortar antes cambiaría quién domina a quién.
    mascara = pareto_mask([s.alternative.metrics for s in todas], DEFAULT_OBJECTIVES)
    en_frente = {s.alternative.id for s, m in zip(todas, mascara) if m}
    ordenadas = todas[:limite]
    filas = ""
    for puesto, s in enumerate(ordenadas, 1):
        a = s.alternative
        g = a.geometry
        clase = _ESTADO_CLASE.get(a.overall_status, "info")
        filas += (
            f"<tr><td class='num'>{puesto}</td><td>{_e(a.id)}</td>"
            f"<td>{u.fmt(g.exterior_B_m, 'length')} × {u.fmt(g.exterior_L_m, 'length')} × "
            f"{u.fmt(g.exterior_h_m, 'length')}</td>"
            f"<td>{u.fmt(g.interior_B_m, 'length')} × {u.fmt(g.interior_L_m, 'length')} × "
            f"{u.fmt(g.interior_h_m, 'length')}</td>"
            f"<td class='num'>{a.metrics.concrete_volume_m3:.2f}</td>"
            f"<td class='num'>{a.metrics.steel_mass_kg:.0f}</td>"
            f"<td class='num'>{s.score:.4f}</td>"
            f"<td>{'◆' if a.id in en_frente else ''}</td>"
            f"<td class='{clase}'>{_e(alternative_label(a))}</td>"
            f"<td><code>{_e(', '.join(a.open_tbds) or '—')}</code></td></tr>"
        )

    nota = (
        "El orden es por <b>costo</b>, no por conformidad: la primera de la lista está "
        "tan NO VERIFICADA como el resto. Ordenar no aprueba."
        if not alternativas.accepted_and_compliant
        else "El orden es por costo. Consúltese la columna de estado."
    )
    return f"""
<table>
<thead><tr><th>#</th><th>Id</th><th>Zapata de lindero ({_e(u.label('length'))})</th>
<th>Zapata interior ({_e(u.label('length'))})</th>
<th>Concreto (m³)</th><th>Acero (kg)</th><th>Puntuación</th><th>Pareto</th><th>Estado</th>
<th>Pendientes</th></tr></thead>
<tbody>{filas}</tbody></table>
<p class="nota">{nota} Se muestran {len(ordenadas)} de {len(alternativas.accepted)}
alternativas aceptadas. ◆ = frente de Pareto sobre {", ".join(DEFAULT_OBJECTIVES)}
({len(en_frente)} alternativa(s)); es una comparación de costo y no cambia el estado.</p>
"""


def _tabla_rechazos(
    alternativas: ConnectedAlternativeSet, u: ReportUnits, limite: int = 15
) -> str:
    if not alternativas.rejected:
        return "<p>Ningún sistema fue rechazado.</p>"
    filas = "".join(
        f"<tr><td>{u.fmt(r.geometry.exterior_B_m, 'length')} × "
        f"{u.fmt(r.geometry.exterior_L_m, 'length')} × "
        f"{u.fmt(r.geometry.exterior_h_m, 'length')}</td>"
        f"<td>{u.fmt(r.geometry.interior_B_m, 'length')} × "
        f"{u.fmt(r.geometry.interior_L_m, 'length')} × "
        f"{u.fmt(r.geometry.interior_h_m, 'length')}</td>"
        f"<td><code>{_e(r.reason.value)}</code></td>"
        f"<td class='def'>{_e(r.detail[:220])}</td></tr>"
        for r in alternativas.rejected[:limite]
    )
    return f"""
<table>
<thead><tr><th>Zapata de lindero ({_e(u.label('length'))})</th>
<th>Zapata interior ({_e(u.label('length'))})</th>
<th>Motivo</th><th>Detalle</th></tr></thead>
<tbody>{filas}</tbody></table>
<p class="nota">Se muestran {min(limite, len(alternativas.rejected))} de
{len(alternativas.rejected)} rechazos.</p>
"""


def _tabla_traza(alternativa: ConnectedAlternative) -> str:
    filas = ""
    for e in alternativa.result.trace.entries:
        clase = _ESTADO_CLASE.get(e.status, "info")
        pendiente = (
            f"<code>{_e(e.open_tbd)}</code>" if e.open_tbd else "—"
        )
        filas += (
            f"<tr><td>{_e(e.scope or '—')}</td><td>{_e(e.id)}</td>"
            f"<td>{_e(e.description)}</td>"
            f"<td class='eq'>{_e(e.equation_substituted)}</td>"
            f"<td>{_e(e.code_name)} {_e(e.code_reference)}</td>"
            f"<td class='{clase}'>{_e(e.status.value)}</td>"
            f"<td>{pendiente}</td></tr>"
        )
    return f"""
<table>
<thead><tr><th>Ámbito</th><th>Id</th><th>Verificación</th><th>Sustitución</th>
<th>Referencia</th><th>Estado</th><th>Pendiente</th></tr></thead>
<tbody>{filas}</tbody></table>
<p class="nota">La columna <b>Pendiente</b> distingue una verificación que salió mal de
una que no existe. Una entrada NO VERIFICADO <i>con</i> pendiente señala un hueco
normativo; <i>sin</i> pendiente, señala un dato que el proyectista no declaró y que sí
puede aportar.</p>
"""


def render_connected_report_html(
    alternatives: ConnectedAlternativeSet,
    titulo: str = "Memoria de cálculo — Cimentación conectada",
    *,
    selected_id: str | None = None,
    detail_limit: int = 20,
    units: ReportUnits | None = None,
) -> str:
    """Memoria autocontenida de un barrido de zapata conectada.

    Se emite SIEMPRE, incluso si todas las alternativas están NO VERIFICADAS o si no hay
    ninguna aceptada: un informe que se niega a existir no informa de nada."""
    # Unidades de PRESENTACIÓN (2026-09-23); por omisión las SI del motor. La traza y
    # las métricas de volumen se mantienen en SI: ver `report_units`.
    u = units or ReportUnits()
    resumen = build_connected_status_summary(alternatives)

    detalle = ""
    if alternatives.accepted:
        from engine.optimization.connected_generator import rank_connected_alternatives

        elegida = None
        if selected_id:
            elegida = next(
                (a for a in alternatives.accepted if a.id == selected_id), None
            )
        if elegida is None:
            elegida = rank_connected_alternatives(alternatives.accepted)[0].alternative

        d = elegida.result.statics[0]
        from engine.optimization.connected_metrics import beam_volume_breakdown

        vv = beam_volume_breakdown(elegida.result)
        hipotesis_metrica = "".join(f"<li>{_e(h)}</li>" for h in vv.hypotheses)
        composicion = _tabla_composicion(elegida)
        detalle = f"""
<h2>Memoria de la alternativa {_e(elegida.id)}</h2>
<p>Estado <span class="{_ESTADO_CLASE.get(elegida.overall_status, 'info')}">
<b>{_e(alternative_label(elegida))}</b></span> ·
verificaciones implementadas:
<b>{_e(elegida.implemented_checks_status.value)}</b> ·
pendientes abiertos: <code>{_e(', '.join(elegida.open_tbds) or '—')}</code></p>
<p class="aviso">Las dos etiquetas anteriores responden a preguntas distintas.
«Verificaciones implementadas» dice si algo de lo que el motor <i>sabe</i> comprobar
salió mal. El estado dice si el motor puede pronunciarse. Que la primera sea PASS
<b>no autoriza</b> a informar que el diseño cumple.</p>

<table>
<tbody>
<tr><td>Modelo de análisis declarado</td>
    <td><b>{_e(d.analysis_model)}</b></td></tr>
<tr><td>Reparto del par declarado</td>
    <td><b>{_e(d.couple_transfer_mode)}</b></td></tr>
<tr><td>Longitud del sistema</td>
    <td class="num">{u.con(elegida.result.system_length_m, 'length', 3)}</td></tr>
<tr><td>Vano libre de la viga (f<sub>i</sub> − L1)</td>
    <td class="num">{u.con(elegida.result.beam_span_m, 'length', 3)}</td></tr>
<tr><td>Concreto atribuido a la viga (métrica): vano libre + lo que sobresale de cada zapata</td>
    <td class="num">{vv.span_m3:.3f} + {vv.exterior_above_m3:.3f} + {vv.interior_above_m3:.3f} = {vv.total_m3:.3f} m³</td></tr>
<tr><td>Viga dentro de las zapatas (contada como zapata, no se suma)</td>
    <td class="num">{vv.exterior_inside_m3:.3f} + {vv.interior_inside_m3:.3f} m³</td></tr>
<tr><td>Longitud de acero longitudinal de la viga (métrica, c<sub>i</sub> − c<sub>e</sub>)</td>
    <td class="num">{vv.steel_length_m:.3f} m</td></tr>
<tr><td>Transferencia a la zapata interior (ΔP, 1.ª combinación)</td>
    <td class="num">{u.con(d.delta_P_kN, 'force', 1)}</td></tr>
</tbody></table>
<p class="aviso">Hipótesis de las métricas (no intervienen en la estática, las cargas ni el diseño):</p>
<ul>{hipotesis_metrica}</ul>
{composicion}

<h3>Traza de cálculo</h3>
{_tabla_traza(elegida)}
"""

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)}</title>
<style>
 body {{ font: 14px/1.5 Georgia, serif; color: #1a1d21; max-width: 980px;
        margin: 2rem auto; padding: 0 1rem; background: #fff; }}
 h1 {{ font-size: 26px; border-bottom: 2px solid #1a1d21; padding-bottom: .4rem; }}
 h2 {{ font-size: 19px; margin-top: 2rem; border-top: 1px solid #ccc; padding-top: 1rem; }}
 h2.sin-linea {{ border-top: none; margin-top: 0; padding-top: 0; }}
 h3 {{ font-size: 16px; margin-top: 1.4rem; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; margin: .8rem 0; }}
 th {{ background: #eef1f4; text-align: left; padding: 6px 8px; font-size: 11px;
       text-transform: uppercase; letter-spacing: .05em; }}
 td {{ padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 td.eq {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; }}
 td.def {{ color: #444; font-size: 11.5px; }}
 td.sangria {{ padding-left: 1.8rem; color: #444; }}
 .ok {{ color: #2c6e49; font-weight: 600; }} .bad {{ color: #a03530; font-weight: 600; }}
 .warn {{ color: #8a5a0c; font-weight: 600; }} .nv {{ color: #6b5b8a; font-weight: 600; }}
 .info {{ color: #666; }}
 .estado {{ border: 2px solid #6b5b8a; border-radius: 6px; padding: 1rem 1.2rem;
            margin: 1.2rem 0; background: #f7f5fb; }}
 .estado.ok-caja {{ border-color: #2c6e49; background: #f2f8f4; }}
 .estado.bad-caja {{ border-color: #a03530; background: #fbf4f3; }}
 .titular {{ font-size: 15px; margin: .5rem 0; }}
 .nota {{ background: #f4f6f8; border-left: 3px solid #1b4f6b; padding: .7rem 1rem;
          margin: 1rem 0; font-size: 12.5px; }}
 .aviso {{ background: #fbf7ef; border-left: 3px solid #8a5a0c; padding: .7rem 1rem;
           margin: 1rem 0; font-size: 12.5px; }}
 code {{ font-family: ui-monospace, Consolas, monospace; font-size: 11.5px; }}
</style></head><body>

<h1>{_e(titulo)}</h1>
<p><b>Cimentación conectada</b> — zapata de lindero, viga de conexión y zapata interior.</p>
<div class="nota"><b>Unidades.</b> {_e(u.note())}</div>

{_bloque_estado(resumen)}

{_bloque_recuento(resumen)}

<h2>Alternativas aceptadas</h2>
{_tabla_alternativas(alternatives, detail_limit, u)}

<h2>Sistemas rechazados</h2>
{_tabla_rechazos(alternatives, u)}

{detalle}

<h2>Alcance de este documento</h2>
<p class="aviso">Este informe recoge el resultado de las verificaciones que el motor
tiene implementadas. <b>No es un certificado de conformidad normativa</b> mientras
figure algún pendiente abierto en el apartado correspondiente. La responsabilidad de
adoptar las hipótesis de modelación declaradas —modelo de análisis y reparto del par—
es del proyectista: ninguna norma arbitra entre ellas.</p>

</body></html>"""
