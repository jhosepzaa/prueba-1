"""Renderizado del reporte a HTML autocontenido y listo para imprimir.

Por qué HTML y no PDF nativo: WeasyPrint requiere bibliotecas GTK/Pango que no
están disponibles en este entorno Windows. El HTML autocontenido resuelve el
mismo problema sin dependencias nativas — el usuario obtiene el PDF con
Ctrl+P → «Guardar como PDF», y el HTML es además archivable por sí mismo.

El CSS incluye reglas @media print: saltos de página por sección, sin elementos
interactivos y colores que sobreviven a la impresión en blanco y negro.

Este módulo no calcula nada: formatea el `FootingReport`.
"""

from __future__ import annotations

from html import escape

from engine.reports.report_model import FootingReport, ReportRow, ReportTable, status_label
from engine.results.status import CheckStatus

CSS = """
@page { size: A4; margin: 18mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 10.5pt; line-height: 1.45; color: #14171f; margin: 0;
  padding: 22px 26px 60px; max-width: 1000px; margin: 0 auto; background: #fff;
}
h1 { font-size: 17pt; margin: 0 0 3px; letter-spacing: -0.2px; }
h2 {
  font-size: 12pt; margin: 26px 0 9px; padding-bottom: 4px;
  border-bottom: 1.6px solid #14171f; page-break-after: avoid;
}
h3 { font-size: 10.8pt; margin: 15px 0 6px; color: #1e4d8c; page-break-after: avoid; }
h4 { font-size: 10pt; margin: 11px 0 5px; color: #5a6172; page-break-after: avoid; }
p { margin: 0 0 8px; }

.masthead { border-bottom: 2.5px solid #14171f; padding-bottom: 11px; margin-bottom: 6px; }
.masthead .sub { color: #5a6172; font-size: 9.5pt; }
.meta { display: flex; gap: 22px; flex-wrap: wrap; font-size: 9pt; color: #5a6172; margin-top: 7px; }

table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin-bottom: 10px; page-break-inside: avoid; }
th {
  text-align: left; background: #f2f4f7; border-bottom: 1.4px solid #98a2b3;
  padding: 5px 7px; font-size: 8.6pt; text-transform: uppercase; letter-spacing: 0.3px; color: #475065;
}
td { padding: 4px 7px; border-bottom: 1px solid #e3e7ee; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kv td:first-child { width: 34%; color: #5a6172; }
.kv td:nth-child(2) { font-weight: 600; }
.ref { color: #7a8395; font-size: 8.8pt; }

.eq { border: 1px solid #dfe3ea; border-left: 3px solid #98a2b3; border-radius: 3px;
      margin-bottom: 9px; page-break-inside: avoid; }
.eq.PASS { border-left-color: #1f7a44; }
.eq.INFO { border-left-color: #4a5a8a; }
.eq.WARNING { border-left-color: #9a6a00; }
.eq.NOVER { border-left-color: #7a5aa8; }
.eq.FAIL { border-left-color: #a32a2a; }
.eq-head { background: #fafbfc; padding: 6px 9px; border-bottom: 1px solid #e3e7ee;
           display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
.eq-title { font-weight: 600; font-size: 10pt; }
.eq-body { padding: 8px 9px; }
.lbl { font-size: 8.2pt; text-transform: uppercase; letter-spacing: 0.4px; color: #7a8395;
       font-weight: 700; margin-bottom: 2px; margin-top: 7px; }
.lbl:first-child { margin-top: 0; }
.formula {
  font-family: "Consolas", "SFMono-Regular", monospace; font-size: 8.8pt;
  background: #f6f8fa; border: 1px solid #e3e7ee; border-radius: 2px;
  padding: 5px 7px; white-space: pre-wrap; word-break: break-word; line-height: 1.55;
}
.hyp { font-size: 9pt; color: #475065; padding-left: 12px; position: relative; margin-bottom: 2px; }
.hyp::before { content: "–"; position: absolute; left: 2px; }
.cite { font-size: 8.8pt; color: #1e4d8c; font-weight: 600; }

.badge { display: inline-block; padding: 1px 6px; border-radius: 2px;
         font-size: 8.2pt; font-weight: 700; border: 1px solid; }
.badge.PASS { background: #e8f5ee; color: #1f7a44; border-color: #a8d5bd; }
.badge.INFO { background: #eceffa; color: #4a5a8a; border-color: #c2cbe8; }
.badge.WARNING { background: #fdf3e0; color: #9a6a00; border-color: #e8d5a8; }
.badge.NOVER { background: #f2ecfa; color: #7a5aa8; border-color: #d5c5ea; }
.badge.FAIL { background: #fbeaea; color: #a32a2a; border-color: #eec5c5; }

.note { border: 1px solid; border-radius: 3px; padding: 8px 11px; font-size: 9.5pt; margin-bottom: 11px; }
.note.info { background: #eceffa; border-color: #ccd4ee; color: #33406b; }
.note.warn { background: #fdf3e0; border-color: #e8d5a8; color: #6b4b00; }
.note.pass { background: #e8f5ee; border-color: #bfe0cd; color: #145c33; }
.note.fail { background: #fbeaea; border-color: #eec5c5; color: #7d1f1f; }
.note strong { display: block; margin-bottom: 3px; }

.conclusion { border: 2px solid #14171f; border-radius: 4px; padding: 13px 15px; margin: 14px 0; }
.conclusion .verdict { font-size: 13pt; font-weight: 700; margin-bottom: 6px; }

ol, ul { margin: 0 0 9px; padding-left: 20px; }
li { margin-bottom: 3px; }
.section { page-break-before: always; }
.section:first-of-type { page-break-before: avoid; }
.toc { columns: 2; font-size: 9.5pt; }
.footer { margin-top: 30px; padding-top: 9px; border-top: 1px solid #dfe3ea;
          font-size: 8.6pt; color: #7a8395; }

@media print {
  body { padding: 0; max-width: none; }
  .no-print { display: none !important; }
  .eq-body { padding: 6px 8px; }
  a { text-decoration: none; color: inherit; }
}
"""

_BADGE_CLASS = {
    CheckStatus.PASS: "PASS",
    CheckStatus.INFO: "INFO",
    CheckStatus.WARNING: "WARNING",
    CheckStatus.NOT_VERIFIED: "NOVER",
    CheckStatus.FAIL: "FAIL",
}


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def _badge(status: CheckStatus) -> str:
    return f'<span class="badge {_BADGE_CLASS[status]}">{_e(status.value)}</span>'


def _kv_table(rows: list[ReportRow]) -> str:
    body = "".join(
        f"<tr><td>{_e(r.label)}</td><td>{_e(r.value)}"
        + (f" <span class='ref'>{_e(r.unit)}</span>" if r.unit else "")
        + "</td><td class='ref'>"
        + _e(r.reference)
        + "</td></tr>"
        for r in rows
    )
    return f"<table class='kv'><tbody>{body}</tbody></table>"


def _table(t: ReportTable) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in t.headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>" for row in t.rows
    )
    title = f"<h4>{_e(t.title)}</h4>" if t.title else ""
    note = f"<p class='ref'>{_e(t.note)}</p>" if t.note else ""
    empty = "<tr><td colspan='99' class='ref'>Sin registros.</td></tr>"
    return f"{title}<table><thead><tr>{head}</tr></thead><tbody>{body or empty}</tbody></table>{note}"


def _trace_entry(entry) -> str:
    hyps = "".join(f"<div class='hyp'>{_e(h)}</div>" for h in entry.hypotheses)
    combo = (
        f" &middot; gobierna <strong>{_e(entry.governing_combo)}</strong>"
        if entry.governing_combo
        else ""
    )
    value = (
        f"{entry.result_value:.6g}"
        if isinstance(entry.result_value, float) and entry.result_value == entry.result_value
        else "—"
    )
    return f"""
<div class="eq {_BADGE_CLASS[entry.status]}">
  <div class="eq-head">
    <span class="eq-title">{_e(entry.description)}</span>
    {_badge(entry.status)}
  </div>
  <div class="eq-body">
    <div class="lbl">Ecuación</div>
    <div class="formula">{_e(entry.equation_symbolic)}</div>
    <div class="lbl">Sustitución numérica (variables y unidades)</div>
    <div class="formula">{_e(entry.equation_substituted)}</div>
    <div class="lbl">Resultado</div>
    <div>{_e(value)} <span class="ref">{_e(entry.result_unit)}</span></div>
    {f'<div class="lbl">Supuestos</div>{hyps}' if hyps else ''}
    <div class="lbl">Fuente normativa</div>
    <div class="cite">{_e(entry.code_name)} — {_e(entry.code_reference)}{combo}</div>
  </div>
</div>"""


def render_report_html(report: FootingReport) -> str:
    label = status_label(report.final_status)

    # Unidades de PRESENTACIÓN (2026-09-23). La traza sigue en SI; ver `report_units`.
    u = report.units

    combos_rows = "".join(
        f"<tr><td><strong>{_e(c.name)}</strong></td><td>{_e(c.type)}</td>"
        f"<td class='num'>{u.fmt(c.P_kN, 'force', 1)}</td>"
        f"<td class='num'>{u.fmt(c.Mx_kNm, 'moment', 1)}</td>"
        f"<td class='num'>{u.fmt(c.My_kNm, 'moment', 1)}</td>"
        f"<td class='num'>{u.fmt(c.Hx_kN, 'force', 1)}</td>"
        f"<td class='num'>{u.fmt(c.Hy_kN, 'force', 1)}</td>"
        f"<td>{'Sí' if c.seismic else '—'}</td></tr>"
        for c in report.service_combinations + report.factored_combinations
    )

    hyp_rows = "".join(
        f"<li>{_e(h.text)} <span class='ref'>({_e(h.source)}"
        + (" · interpretación adoptada" if h.is_normative_interpretation else "")
        + ")</span></li>"
        for h in report.hypotheses
    ) or "<li class='ref'>Sin supuestos adicionales registrados.</li>"

    rebar_html = "".join(_table(t) for t in report.rebar_tables)
    short_html = _table(report.short_direction_table) if report.short_direction_table else ""

    # Bloques que se intercalan DENTRO de la secuencia de secciones para que el
    # documento se lea 1 → 16 sin saltos: el resumen numérico de excentricidad va
    # justo tras su memoria, y el detalle del armado tras la suya.
    ANNEX_AFTER: dict[str, str] = {
        "8. Verificación de excentricidad y estabilidad": (
            "<h3>8b. Resumen numérico de excentricidad y presiones</h3>"
            + _kv_table(report.eccentricity_rows)
        ),
        "12. Diseño y desarrollo del acero": (
            "<h3>12b. Detalle del armado adoptado</h3>" + rebar_html + short_html
        ),
    }

    trace_html = "".join(
        f"<div class='section'><h2>{_e(title)}</h2>"
        + "".join(_trace_entry(e) for e in entries)
        + ANNEX_AFTER.get(title, "")
        + "</div>"
        for title, entries in report.trace_groups
    )

    gov_rows = "".join(
        f"<tr><td>{_e(g.check)}</td><td><strong>{_e(g.combination)}</strong></td>"
        f"<td>{_badge(g.status)}</td></tr>"
        for g in report.governing_combinations
    )

    lim_rows = "".join(
        f"<tr><td>{_e(l.title)}</td><td>{_e(l.kind)}</td><td class='ref'>{_e(l.code_reference)}</td>"
        f"<td class='ref'>{_e(l.impact)}</td>"
        f"<td>{'SÍ' if l.can_cause_false_pass else 'No'}</td></tr>"
        for l in report.limitations
    )

    disc_rows = "".join(
        f"<tr><td>{_e(d.reason)}</td><td class='num'>{d.count}</td>"
        f"<td>{_e(d.example_id)}</td><td class='ref'>{_e(d.example_geometry)}</td></tr>"
        for d in report.discarded
    ) or "<tr><td colspan='4' class='ref'>No se descartó ninguna geometría.</td></tr>"

    conclusion_class = {
        CheckStatus.PASS: "pass", CheckStatus.INFO: "pass",
        CheckStatus.WARNING: "warn", CheckStatus.NOT_VERIFIED: "warn", CheckStatus.FAIL: "fail",
    }[report.final_status]

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Memoria de cálculo — {_e(report.project_name)} — {_e(report.alternative_id)}</title>
<style>{CSS}</style>
</head>
<body>

<div class="masthead">
  <h1>Memoria de cálculo — Zapata aislada</h1>
  <div class="sub">Norma Técnica E.060 (Concreto Armado) y E.050 (Suelos y Cimentaciones) —
  Reglamento Nacional de Edificaciones del Perú</div>
  <div class="meta">
    <span><strong>Proyecto:</strong> {_e(report.project_name)}</span>
    <span><strong>Alternativa:</strong> {_e(report.alternative_id)}</span>
    <span><strong>Emitido:</strong> {report.generated_at:%d/%m/%Y %H:%M}</span>
    <span><strong>Motor:</strong> v{_e(report.engine_version)}</span>
  </div>
</div>

<div class="no-print" style="margin:14px 0;padding:9px 12px;background:#eceffa;
     border:1px solid #ccd4ee;border-radius:4px;font-size:9.5pt;color:#33406b;">
  <strong>Para obtener el PDF:</strong> use Ctrl+P (o Cmd+P) y elija «Guardar como PDF».
  Este bloque no aparece en la impresión.
</div>

<h2>Contenido</h2>
<div class="toc">
  <ol>
    <li>Datos del proyecto</li><li>Datos de la columna</li><li>Datos del suelo</li>
    <li>Combinaciones de carga</li><li>Hipótesis utilizadas</li><li>Geometría seleccionada</li>
    <li>Cálculo de presiones de contacto</li><li>Verificación de excentricidad y estabilidad</li>
    <li>Diseño por flexión</li><li>Verificación de cortante</li>
    <li>Verificación de punzonamiento</li><li>Diseño del acero</li>
    <li>Verificaciones normativas</li><li>Resultado final</li>
    <li>Alternativas descartadas</li><li>Tabla comparativa</li>
  </ol>
</div>

<div class="section">
<h2>1. Datos del proyecto</h2>
{_kv_table([ReportRow(label="Proyecto", value=report.project_name),
            ReportRow(label="Alternativa analizada", value=report.alternative_id),
            ReportRow(label="Norma aplicada", value=report.code_name),
            ReportRow(label="Estado del resultado", value=f"{report.final_status.value} — {label}")])}
<h3>Parámetros de búsqueda ejecutados</h3>
{_kv_table(report.search_rows)}
<h3>Resumen de la corrida</h3>
{_kv_table(report.summary_rows)}
</div>

<div class="section">
<h2>2. Datos de la columna</h2>
{_kv_table(report.column_rows)}
<h3>Materiales</h3>
{_kv_table(report.material_rows)}
</div>

<div class="section">
<h2>3. Datos del suelo</h2>
{_kv_table(report.soil_rows)}
<div class="note info">
  <strong>Sobre los parámetros no declarados</strong>
  El motor no asume ningún parámetro geotécnico que el usuario no haya
  proporcionado. Las verificaciones que dependen de un dato ausente se reportan
  como NO VERIFICADO, nunca como conformes.
</div>
</div>

<div class="section">
<h2>4. Combinaciones de carga</h2>
<div class="note info">{_e(report.combinations_note)}</div>
<div class="note info"><b>Unidades.</b> {_e(u.note())}</div>
<div class="note info"><b>Convención de momentos (E.050 art.&nbsp;28.1).</b>
<code>Mx</code> es el momento que desplaza la resultante a lo largo del eje <b>X</b>,
el que flexiona la zapata en la dirección de <i>B</i>: <code>ex = Mx / P</code>.
<code>My</code> hace lo propio a lo largo de <b>Y</b>, en la dirección de <i>L</i>:
<code>ey = My / P</code>. No es «momento alrededor del eje X»: mecánicamente
<code>Mx</code> es el momento <i>alrededor del eje Y</i>.</div>
<table>
<thead><tr><th>Nombre</th><th>Tipo</th><th class="num">P ({_e(u.label('force'))})</th>
<th class="num" title="Momento que desplaza la resultante a lo largo de X (E.050 art. 28.1: ex = Mx/P)">Mx ({_e(u.label('moment'))})</th>
<th class="num" title="Momento que desplaza la resultante a lo largo de Y (E.050 art. 28.1: ey = My/P)">My ({_e(u.label('moment'))})</th>
<th class="num">Hx ({_e(u.label('force'))})</th><th class="num">Hy ({_e(u.label('force'))})</th>
<th>Sismo</th></tr></thead>
<tbody>{combos_rows}</tbody>
</table>
</div>

<div class="section">
<h2>5. Hipótesis utilizadas</h2>
<p>Supuestos que el motor registró durante el cálculo, con la verificación que los originó.</p>
<ul>{hyp_rows}</ul>
</div>

<div class="section">
<h2>6. Geometría seleccionada</h2>
{_kv_table(report.geometry_rows)}
</div>

{trace_html}

<div class="section">
<h2>13. Verificaciones normativas</h2>
<h3>Combinación gobernante por verificación</h3>
<p class="ref">Cada verificación selecciona su combinación gobernante de forma independiente.</p>
<table>
<thead><tr><th>Verificación</th><th>Combinación gobernante</th><th>Estado</th></tr></thead>
<tbody>{gov_rows}</tbody>
</table>

<h3>Limitaciones declaradas del motor</h3>
<table>
<thead><tr><th>Limitación</th><th>Estado</th><th>Referencia</th><th>Impacto</th>
<th>¿Puede producir falso PASS?</th></tr></thead>
<tbody>{lim_rows}</tbody>
</table>
</div>

<div class="section">
<h2>14. Resultado final</h2>
<div class="conclusion">
  <div class="verdict">{_e(label)} &nbsp; {_badge(report.final_status)}</div>
  <p>{_e(report.conclusion)}</p>
</div>
<div class="note {conclusion_class}">
  <strong>Condiciones bajo las cuales este programa emite un resultado conforme</strong>
  <ol>{''.join(f'<li>{_e(c)}</li>' for c in report.pass_conditions)}</ol>
</div>
</div>

<div class="section">
<h2>15. Alternativas descartadas</h2>
<p>{_e(report.discard_note)}</p>
<table>
<thead><tr><th>Motivo del descarte</th><th class="num">Geometrías</th><th>Ejemplo</th><th>Geometría del ejemplo</th></tr></thead>
<tbody>{disc_rows}</tbody>
</table>
</div>

<div class="section">
<h2>16. Tabla comparativa</h2>
{_table(report.comparison)}
</div>

<div class="footer">
  Documento generado automáticamente por el motor de diseño de zapatas aisladas
  v{_e(report.engine_version)} el {report.generated_at:%d/%m/%Y a las %H:%M}.
  Las ecuaciones, sus sustituciones numéricas y sus referencias normativas provienen
  íntegramente del registro de cálculo del motor. Este documento no sustituye la
  revisión de un ingeniero civil colegiado.
</div>

</body>
</html>"""
