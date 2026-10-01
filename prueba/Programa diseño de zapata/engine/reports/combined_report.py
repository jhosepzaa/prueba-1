"""Memoria de cálculo de zapata combinada — Fase 2.

Reutiliza el estilo y la estructura del informe de zapata aislada, pero con las
secciones que la combinada necesita y la aislada no tiene: los diagramas de
cortante y momento, y el armado de las dos caras.

El diagrama se dibuja como SVG en línea a partir de los puntos que ya calculó
`analysis/beam_diagram.py`. El informe NO recalcula nada: es la misma regla que
rige el modelo 3D — visualiza datos calculados, nunca los produce.
"""

from __future__ import annotations

from html import escape

from engine.foundation.combined_solver import CombinedFootingResult
from engine.foundation.combined_stability import D10_2B_ADOPTED_NOTE, ENVELOPE_NOTE
from engine.reports.report_units import ReportUnits
from engine.results.status import CheckStatus

_ESTADO_CLASE = {
    CheckStatus.PASS: "ok",
    CheckStatus.INFO: "info",
    CheckStatus.WARNING: "warn",
    CheckStatus.NOT_VERIFIED: "nv",
    CheckStatus.FAIL: "bad",
}


def _e(texto: object) -> str:
    return escape(str(texto))


def _diagram_svg(result: CombinedFootingResult, ancho_px: int = 720, alto_px: int = 300) -> str:
    """Diagramas V(x) y M(x) en SVG, dibujados sobre los puntos ya calculados."""
    puntos = sorted(result.diagram.critical_points, key=lambda p: p.x_m)
    if len(puntos) < 2:
        return "<p>Sin puntos suficientes para dibujar el diagrama.</p>"

    L = result.diagram.length_m
    margen = 46
    ancho_util = ancho_px - 2 * margen
    alto_banda = (alto_px - 3 * margen) / 2

    def escala_x(x: float) -> float:
        return margen + (x / L) * ancho_util

    def banda(valores: list[float], base_y: float) -> tuple:
        vmax = max(max(valores), 0.0)
        vmin = min(min(valores), 0.0)
        rango = (vmax - vmin) or 1.0
        cero = base_y + alto_banda * (vmax / rango)

        def escala_y(v: float) -> float:
            return base_y + alto_banda * ((vmax - v) / rango)

        return cero, escala_y

    y_v = margen
    y_m = margen * 2 + alto_banda

    cero_v, esc_v = banda([p.V_kN for p in puntos], y_v)
    cero_m, esc_m = banda([p.M_kNm for p in puntos], y_m)

    def poligono(getter, esc_y, cero_y) -> str:
        pts = " ".join(f"{escala_x(p.x_m):.1f},{esc_y(getter(p)):.1f}" for p in puntos)
        return (
            f'<polygon points="{escala_x(0):.1f},{cero_y:.1f} {pts} '
            f'{escala_x(L):.1f},{cero_y:.1f}" />'
        )

    etiquetas = []
    for p in puntos:
        if "cortante nulo" in p.description or "cara" in p.description:
            etiquetas.append(
                f'<line x1="{escala_x(p.x_m):.1f}" y1="{y_v}" '
                f'x2="{escala_x(p.x_m):.1f}" y2="{y_m + alto_banda:.1f}" class="guia" />'
            )

    extremo_neg = ""
    if result.diagram.has_negative_moment:
        x = escala_x(result.diagram.x_M_max_negative_m)
        y = esc_m(-result.diagram.M_max_negative_kNm)
        extremo_neg = (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="hito" />'
            f'<text x="{x:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="hito-txt">'
            f'M⁻ = {result.diagram.M_max_negative_kNm:.0f} kN·m</text>'
        )

    return f"""<svg viewBox="0 0 {ancho_px} {alto_px}" class="diagrama" role="img"
     aria-label="Diagramas de cortante y momento a lo largo de la zapata">
  <style>
    .diagrama polygon {{ fill: rgba(20,92,51,0.18); stroke: #145c33; stroke-width: 1.4; }}
    .diagrama .m polygon {{ fill: rgba(27,79,107,0.18); stroke: #1b4f6b; }}
    .diagrama .eje {{ stroke: #333; stroke-width: 1; }}
    .diagrama .guia {{ stroke: #bbb; stroke-width: 0.7; stroke-dasharray: 3 3; }}
    .diagrama text {{ font: 11px sans-serif; fill: #444; }}
    .diagrama .titulo {{ font-weight: 600; fill: #222; }}
    .diagrama .hito {{ fill: #a03530; }}
    .diagrama .hito-txt {{ font-size: 10px; fill: #a03530; font-weight: 600; }}
  </style>
  {''.join(etiquetas)}
  <text x="{margen}" y="{y_v - 10}" class="titulo">Cortante V(x) — máx {result.diagram.V_max_abs_kN:.0f} kN</text>
  <g>{poligono(lambda p: p.V_kN, esc_v, cero_v)}</g>
  <line x1="{margen}" y1="{cero_v:.1f}" x2="{ancho_px - margen}" y2="{cero_v:.1f}" class="eje" />

  <text x="{margen}" y="{y_m - 10}" class="titulo">Momento M(x) — positivo abajo, negativo arriba</text>
  <g class="m">{poligono(lambda p: p.M_kNm, esc_m, cero_m)}</g>
  <line x1="{margen}" y1="{cero_m:.1f}" x2="{ancho_px - margen}" y2="{cero_m:.1f}" class="eje" />
  {extremo_neg}

  <text x="{margen}" y="{alto_px - 8}">0</text>
  <text x="{ancho_px - margen}" y="{alto_px - 8}" text-anchor="end">{L:.2f} m</text>
</svg>"""


def _fila_cara(titulo: str, cara, u: ReportUnits) -> str:
    if cara is None:
        return (
            f"<tr><td>{_e(titulo)}</td><td colspan='6'><i>El diagrama no produce momento "
            f"negativo: la cara superior no trabaja a tracción por flexión. El refuerzo por "
            f"cambios volumétricos de §9.7 sigue siendo exigible.</i></td></tr>"
        )
    rb = cara.rebar
    return (
        f"<tr><td>{_e(titulo)}</td>"
        f"<td class='num'>{u.fmt(cara.Mu_kNm, 'moment', 1)}</td>"
        f"<td class='num'>{u.fmt(cara.d_m, 'length', 3)}</td>"
        f"<td class='num'>{cara.cover_m * 1000:.0f}</td>"
        f"<td class='num'>{cara.As_design_m2 * 1e4:.2f}</td>"
        f"<td>{_e(rb.bar_designation) if rb else '—'}"
        f"{f' @ {_cm(rb.spacing_m)} cm' if rb else ''}</td>"
        f"<td class='{_ESTADO_CLASE.get(cara.status, 'info')}'>{_e(cara.status.value)}</td></tr>"
    )


def _cm(metros: float) -> str:
    """Separación en cm SIN perder el medio centímetro: 0,125 m es «12.5», no «12».

    Con `:.0f` una separación de 12,5 cm se imprimía «12 cm» (redondeo al par), que no es
    la que dimensiona el acero. En un plano, la cifra tiene que ser la del cálculo."""
    cm = metros * 100.0
    return f"{cm:.0f}" if abs(cm - round(cm)) < 1e-6 else f"{cm:.1f}"


def _combo_de(result: CombinedFootingResult, check_id: str) -> str:
    """La combinación que gobierna un efecto, tal como la registró el solver en la traza."""
    e = result.trace.by_id(check_id)
    return (e.governing_combo or "—") if e is not None else "—"


def render_combined_report_html(
    result: CombinedFootingResult, titulo: str, units: ReportUnits | None = None
) -> str:
    """Memoria de cálculo autocontenida de una zapata combinada.

    `CLAUDE.md` §14: indica el estado —con el rótulo del vocabulario único—, qué
    verificaciones no son conformes, los TBD abiertos y los criterios del programa que
    delimitan el alcance. Presenta; no calcula ni reinterpreta ningún estado."""
    from engine.foundation.combined_solver import (
        CONCRETE_ONLY_SHEAR_CRITERION,
        ENVELOPE_DESIGN_NOTE,
    )
    from engine.results.vocabulary import status_label

    # Unidades de PRESENTACIÓN (2026-09-23). Por omisión, las SI del motor, que es como
    # se emitía esta memoria hasta esa fecha. La traza sigue en SI: ver `report_units`.
    u = units or ReportUnits()

    tbd_abiertos = sorted({e.open_tbd for e in result.trace.entries if e.open_tbd})
    rotulo = status_label(result.overall_status, tuple(tbd_abiertos))
    no_conformes = [
        e for e in result.trace.entries if e.status not in (CheckStatus.PASS, CheckStatus.INFO)
    ]
    transversal = result.trace.by_id("shear_transversal")
    filas_punz = "".join(
        f"<tr><td>{_e(p.column_position)}</td>"
        f"<td class='num'>{p.critical_section_sides}</td>"
        f"<td class='num'>{p.alpha_s:.0f}</td>"
        f"<td class='num'>{u.fmt(p.bo_m, 'length', 3)}</td>"
        f"<td class='num'>{p.ratio:.3f}</td>"
        f"<td class='{_ESTADO_CLASE.get(p.status, 'info')}'>{_e(p.status.value)}</td></tr>"
        for p in result.punching
    )
    filas_franja = "".join(
        f"<tr><td>{_e(f.column_label)}</td>"
        f"<td class='num'>{u.fmt(f.strip_width_m, 'length', 3)}</td>"
        f"<td class='num'>{u.fmt(f.cantilever_m, 'length', 3)}</td>"
        f"<td class='num'>{u.fmt(f.Mu_kNm, 'moment', 1)}</td>"
        f"<td class='num'>{f.As_design_m2 * 1e4:.2f}</td>"
        f"<td>{_e(f.rebar.bar_designation) if f.rebar else '—'}"
        f"{f' @ {_cm(f.rebar.spacing_m)} cm' if f.rebar else ''}</td></tr>"
        for f in result.transverse_strips
    )
    filas_traza = "".join(
        f"<tr><td>{_e(e.id)}</td><td>{_e(e.description)}</td>"
        f"<td class='eq'>{_e(e.equation_substituted)}</td>"
        f"<td>{_e(e.code_name)} {_e(e.code_reference)}</td>"
        f"<td class='{_ESTADO_CLASE.get(e.status, 'info')}'>{_e(e.status.value)}</td></tr>"
        for e in result.trace.entries
    )
    motivos = (
        "<ul>" + "".join(f"<li>{_e(m)}</li>" for m in result.discard_reasons) + "</ul>"
        if result.discard_reasons
        else "<p>Ninguna verificación resultó en descarte.</p>"
    )

    # Pendiente 7: estabilidad. Solo existe cuando alguna combinación declara fuerza
    # horizontal; si no, la sección lo dice en vez de callarlo.
    if result.stability is None:
        bloque_estabilidad = (
            "<p>No aplicable: ninguna combinación de servicio declara fuerzas horizontales. "
            "El momento de las columnas queda acotado por la exigencia de resultante dentro "
            "del núcleo central de la presión de contacto.</p>"
        )
    else:
        filas_est = "".join(
            f"<tr><td>{_e(etiqueta)}</td>"
            f"<td class='num'>{'—' if res.FS_obtained is None else f'{res.FS_obtained:.2f}'}</td>"
            f"<td class='num'>{'—' if res.FS_required is None else f'{res.FS_required:.2f}'}</td>"
            f"<td>{_e(res.governing_combo or '—')}</td>"
            f"<td class='{_ESTADO_CLASE.get(res.status, 'info')}'>{_e(res.status.value)}</td></tr>"
            for etiqueta, res in (
                ("Deslizamiento", result.stability.sliding),
                ("Volcamiento eje X", result.stability.overturning_x),
                ("Volcamiento eje Y", result.stability.overturning_y),
            )
        )
        bloque_estabilidad = (
            "<table><thead><tr><th>Verificación</th><th>FS obtenido</th><th>FS requerido</th>"
            "<th>Combinación</th><th>Estado</th></tr></thead>"
            f"<tbody>{filas_est}</tbody></table>"
            f"<div class='nota'><b>Criterio.</b> {_e(D10_2B_ADOPTED_NOTE)} {_e(ENVELOPE_NOTE)}</div>"
            + "".join(f"<p>{_e(r.message)}</p>" for r in (
                result.stability.sliding, result.stability.overturning_x,
                result.stability.overturning_y))
        )

    # Decisión 6: el barrido de la combinada acepta con criterio NO_FAIL, de modo que una
    # alternativa NO VERIFICADA o con observaciones puede llegar hasta aquí. El aviso no
    # cambia ningún resultado: impide que el lector tome «aceptada» por «conforme».
    aviso_estado = ""
    if result.overall_status not in (CheckStatus.PASS, CheckStatus.INFO):
        degradadas = ", ".join(
            _e(e.id) for e in result.trace.entries
            if e.status not in (CheckStatus.PASS, CheckStatus.INFO)
        )
        aviso_estado = (
            f'<div class="nota"><b>Esta alternativa NO puede declararse conforme.</b> '
            f'Su estado es <span class="{_ESTADO_CLASE.get(result.overall_status, "info")}">'
            f'{_e(result.overall_status.value)}</span>. El barrido la conserva porque ninguna '
            f'verificación implementada la descarta (criterio NO_FAIL), no porque cumpla. '
            f'Verificación(es) que impiden el pronunciamiento: <b>{degradadas}</b>. '
            f'Véase el detalle en la traza.</div>'
        )

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>{_e(titulo)}</title>
<style>
 body {{ font: 14px/1.5 Georgia, serif; color: #1a1d21; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
 h1 {{ font-size: 26px; border-bottom: 2px solid #1a1d21; padding-bottom: .4rem; }}
 h2 {{ font-size: 19px; margin-top: 2rem; border-top: 1px solid #ccc; padding-top: 1rem; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; margin: .8rem 0; }}
 th {{ background: #eef1f4; text-align: left; padding: 6px 8px; font-size: 11px;
       text-transform: uppercase; letter-spacing: .05em; }}
 td {{ padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 td.eq {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; }}
 .ok {{ color: #2c6e49; font-weight: 600; }} .bad {{ color: #a03530; font-weight: 600; }}
 .warn {{ color: #8a5a0c; font-weight: 600; }} .nv {{ color: #6b5b8a; font-weight: 600; }}
 .info {{ color: #666; }}
 .nota {{ background: #f4f6f8; border-left: 3px solid #1b4f6b; padding: .7rem 1rem; margin: 1rem 0; font-size: 13px; }}
 svg.diagrama {{ width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; background: #fff; }}
</style></head><body>

<h1>{_e(titulo)}</h1>
<p><b>Zapata combinada</b> — {u.fmt(result.B_m, 'length')} × {u.fmt(result.L_m, 'length')} ×
{u.con(result.h_m, 'length')} ·
dirección longitudinal <b>{_e(result.longitudinal_direction)}</b> ·
estado <span class="{_ESTADO_CLASE.get(result.overall_status, 'info')}">{_e(result.overall_status.value)}</span>
· <b>{_e(rotulo)}</b></p>

{aviso_estado}

<div class="nota">
<b>Convención de momentos (E.050 art. 28.1).</b> <code>Mx</code> desplaza la resultante a lo
largo del eje X y flexiona la zapata en la dirección de <i>B</i>; <code>My</code> hace lo propio
en <i>L</i>. No es «momento alrededor del eje X».
</div>

<div class="nota"><b>Unidades.</b> {_e(u.note())}</div>

<h2>1. Base normativa del análisis</h2>
<p>E.060 <b>§15.10.1</b> exige diseñar las zapatas que soportan más de una columna «de acuerdo
con los requisitos de diseño apropiados de esta Norma». El momento en cada sección se obtiene
con el método de <b>§15.4.1</b> —un plano vertical y los momentos sobre el área a un lado—, que
el artículo enuncia para «una zapata corrida, zapata aislada o cabezal de pilote»: la zapata
combinada no figura en esa lista, de modo que aplicarlo aquí es una <b>lectura del programa por
analogía</b> bajo §15.10.1, no una prescripción literal. §15.4.2, que fija la sección crítica en
la cara de la columna, está escrito «para una zapata aislada».
<b>§15.10.2</b> prohíbe el Método Directo del Capítulo 13; no se emplea.</p>
<p>E.050 <b>art. 23.3</b> limita la zapata combinada a L ≤ 10·B: la proporción de esta zapata es
<b>{result.shape_ratio:.2f}</b> ({'admisible' if result.shape_ok else 'FUERA DE RANGO'}).</p>

<h2>2. Diagramas de cortante y momento</h2>
{_diagram_svg(result)}
<p>Reacción del suelo de {result.diagram.w_start_kNm:.1f} a {result.diagram.w_end_kNm:.1f} kN/m.
El diagrama dibujado es el de la combinación de mayor |M|, <b>{_e(result.diagram_combo)}</b>.
Los extremos de M se resuelven donde V = 0, no por muestreo.</p>
<p class="nota"><b>Envolvente.</b> El diseño NO sale solo de ese diagrama: cada efecto toma su
propia combinación más desfavorable — M positivo (cara inferior): <b>{_e(_combo_de(result, "flexure_bottom"))}</b>;
M negativo (cara superior): <b>{_e(_combo_de(result, "flexure_top"))}</b>;
cortante longitudinal: <b>{_e(_combo_de(result, "shear_longitudinal"))}</b>.
{_e(ENVELOPE_DESIGN_NOTE)}</p>

<h2>3. Flexión longitudinal — armado de las dos caras</h2>
<table>
<thead><tr><th>Cara</th><th>Mu ({_e(u.label('moment'))})</th><th>d ({_e(u.label('length'))})</th><th>Recubr. (mm)</th>
<th>As (cm²)</th><th>Armado</th><th>Estado</th></tr></thead>
<tbody>
{_fila_cara('Inferior (M positivo)', result.bottom_face, u)}
{_fila_cara('Superior (M negativo)', result.top_face, u)}
</tbody></table>
<p class="nota">El acero mínimo repartido en dos caras sigue <b>E.060 §10.5.4</b>: la cara en
tracción por flexión no puede bajar de ρ = 0,0012. El recubrimiento de la cara superior se
declara según <b>§7.7.1</b> — no se supone, porque la tabla no da un valor único para esa cara.</p>

<h2>4. Franjas transversales</h2>
<table>
<thead><tr><th>Columna</th><th>Ancho franja ({_e(u.label('length'))})</th>
<th>Voladizo ({_e(u.label('length'))})</th>
<th>Mu ({_e(u.label('moment'))})</th><th>As (cm²)</th><th>Armado</th></tr></thead>
<tbody>{filas_franja}</tbody></table>
<p class="nota"><b>Criterio de modelación, no norma.</b> El ancho de franja «columna + d/2 a cada
lado» procede de los apuntes de Aragón. E.060 §15.4 no fija ancho de franja para zapatas de
varias columnas, y §15.4.4 solo cubre el reparto en la dirección corta de una zapata aislada.</p>

<h2>5. Punzonamiento por columna</h2>
<table>
<thead><tr><th>Clasificación</th><th>Lados</th><th>α<sub>s</sub></th><th>b<sub>o</sub> ({_e(u.label('length'))})</th>
<th>Vu/φVc</th><th>Estado</th></tr></thead>
<tbody>{filas_punz}</tbody></table>
<p class="nota">La clasificación de la columna —interior, de borde o de esquina— la decide el
número de lados de la sección crítica recortados contra el borde. <b>E.060 §11.12.2.1(b) da los
valores de α<sub>s</sub> pero no define qué hace de borde a una columna:</b> esta clasificación
es una interpretación declarada del motor.</p>

<h2>6. Cortante unidireccional</h2>
<table>
<thead><tr><th>Dirección</th><th>Sección crítica</th><th>V<sub>u</sub> ({_e(u.label('force'))})</th>
<th>φV<sub>c</sub> ({_e(u.label('force'))})</th><th>Combinación</th><th>Estado</th></tr></thead>
<tbody>
<tr><td>Longitudinal</td><td>en la cara de la columna</td>
<td class="num">{u.fmt(result.shear_longitudinal.Vu_kN, 'force', 1)}</td>
<td class="num">{u.fmt(result.shear_longitudinal.phi_Vc_kN, 'force', 1)}</td>
<td>{_e(_combo_de(result, "shear_longitudinal"))}</td>
<td class="{_ESTADO_CLASE.get(result.shear_longitudinal.status, 'info')}">{_e(result.shear_longitudinal.status.value)}</td></tr>
{(f'<tr><td>Transversal</td><td>a d de la cara, b<sub>w</sub> = longitud total</td>'
  f'<td colspan="3" class="eq">{_e(transversal.equation_substituted)}</td>'
  f'<td class="{_ESTADO_CLASE.get(transversal.status, "info")}">{_e(transversal.status.value)}</td></tr>')
 if transversal is not None else ''}
</tbody></table>
<p>El longitudinal se toma del diagrama, no de una fórmula de voladizo: en una zapata de varias
columnas el cortante no es monótono. E.060 §11.5.6.1(a) exime a losas y zapatas del refuerzo
mínimo de cortante.</p>
<div class="nota"><b>Alcance.</b> {_e(CONCRETE_ONLY_SHEAR_CRITERION)}</div>

<h2>7. Presión de contacto</h2>
<p>q<sub>máx</sub> = {u.con(result.contact_pressure.qmax_kPa, 'pressure', 1)},
q<sub>mín</sub> = {u.con(result.contact_pressure.qmin_kPa, 'pressure', 1)},
dentro del núcleo central: <b>{result.contact_pressure.within_kern}</b>.
Combinación gobernante: <b>{_e(result.contact_combo)}</b>.</p>

<h2>8. Estabilidad: deslizamiento y volcamiento</h2>
{bloque_estabilidad}

<h2>9. Motivos de descarte</h2>
{motivos}

<h2>10. Verificaciones no conformes, pendientes y criterios del programa</h2>
<p><b>Verificaciones fuera de PASS o INFO:</b>
{('<ul>' + ''.join(f'<li><b>{_e(e.id)}</b> — {_e(e.status.value)}: {_e(e.description)}</li>' for e in no_conformes) + '</ul>')
 if no_conformes else 'ninguna.'}</p>
<p><b>TBD abiertos:</b> {_e(', '.join(tbd_abiertos)) if tbd_abiertos else 'ninguno.'}</p>
<p><b>Criterios del programa que delimitan el alcance</b> — no son exigencias literales de la
norma; se aplican y se declaran:</p>
<ul>
<li><b>Cortante longitudinal por concreto solo (C-V).</b> El aporte de estribos (Vn = Vc + Vs)
queda fuera del alcance; el criterio es más estricto que E.060.</li>
<li><b>Sección crítica del cortante longitudinal en la cara de la columna.</b> E.060 §11.1.3.1
«permite» tomarla a d de la cara bajo las condiciones de §11.1.3; el programa usa la cara, que es
más conservadora. La dirección transversal sí se evalúa a d.</li>
<li><b>Momento de diseño longitudinal: máximo del diagrama, incluidos los ejes de columna.</b>
E.060 no fija la sección crítica de flexión de la zapata combinada (§15.4.2 es para la aislada);
tomar el máximo en toda la longitud es la lectura más conservadora.</li>
<li><b>Ancho de las franjas transversales</b> «columna + d/2 a cada lado», tomado de la
bibliografía (apartado 4).</li>
</ul>

<h2>11. Traza de cálculo</h2>
<table>
<thead><tr><th>Id</th><th>Verificación</th><th>Sustitución</th><th>Referencia</th><th>Estado</th></tr></thead>
<tbody>{filas_traza}</tbody></table>

</body></html>"""
