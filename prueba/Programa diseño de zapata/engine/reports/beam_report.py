"""Memoria de cálculo de la viga de conexión — Fase 3.

Misma regla que los otros dos informes: NO recalcula nada. Recibe el resultado del
motor y la traza ya construida, y les da forma. Si el informe necesitara un número
que el motor no produjo, el que tiene que cambiar es el motor.

El diagrama de interacción se dibuja a partir de los puntos que ya calculó
`beam/axial_flexure.py`, con el punto de demanda (Pu, Mu) marcado encima: es la única
manera de que se vea si cae dentro o fuera de la frontera.
"""

from __future__ import annotations

from html import escape

from engine.beam.connecting_beam import ConnectingBeamResult
from engine.results.calculation_trace import CalculationTrace
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


def _interaction_svg(check, ancho_px: int = 660, alto_px: int = 420) -> str:
    """Diagrama de interacción φPn−φMn con el punto de demanda marcado."""
    puntos = check.diagram
    if len(puntos) < 3:
        return "<p>Sin puntos suficientes para dibujar el diagrama.</p>"

    margen_i, margen_d, margen_s, margen_inf = 62, 24, 24, 46
    ancho_util = ancho_px - margen_i - margen_d
    alto_util = alto_px - margen_s - margen_inf

    m_vals = [p.phi_Mn_kNm for p in puntos] + [abs(check.Mu_kNm)]
    p_vals = [p.phi_Pn_kN for p in puntos] + [check.Pu_kN]
    m_max = max(max(m_vals), 1.0) * 1.08
    p_max = max(max(p_vals), 1.0) * 1.05
    p_min = min(min(p_vals), 0.0) * 1.15 if min(p_vals) < 0 else 0.0
    rango_p = (p_max - p_min) or 1.0

    def ex(m: float) -> float:
        return margen_i + (m / m_max) * ancho_util

    def ey(p: float) -> float:
        return margen_s + alto_util * ((p_max - p) / rango_p)

    frontera = " ".join(f"{ex(p.phi_Mn_kNm):.1f},{ey(p.phi_Pn_kN):.1f}" for p in puntos)
    y_cero = ey(0.0)
    dx, dy = ex(abs(check.Mu_kNm)), ey(check.Pu_kN)
    clase_punto = "dentro" if check.inside_diagram else "fuera"

    return f"""<svg viewBox="0 0 {ancho_px} {alto_px}" class="interaccion" role="img"
     aria-label="Diagrama de interaccion axial-flexion con el punto de demanda">
  <style>
   .eje {{ stroke: #999; stroke-width: 1; }}
   .frontera {{ fill: none; stroke: #1b4f6b; stroke-width: 2; }}
   .relleno {{ fill: #1b4f6b; fill-opacity: .08; stroke: none; }}
   .dentro {{ fill: #2c6e49; stroke: #fff; stroke-width: 1.5; }}
   .fuera {{ fill: #a03530; stroke: #fff; stroke-width: 1.5; }}
   .rot {{ font: 11px Georgia, serif; fill: #555; }}
   .val {{ font: 11px ui-monospace, Consolas, monospace; fill: #333; }}
  </style>
  <polygon class="relleno" points="{ex(0):.1f},{ey(p_max / 1.05):.1f} {frontera} {ex(0):.1f},{ey(p_min):.1f}" />
  <polyline class="frontera" points="{frontera}" />
  <line class="eje" x1="{margen_i}" y1="{margen_s}" x2="{margen_i}" y2="{alto_px - margen_inf}" />
  <line class="eje" x1="{margen_i}" y1="{y_cero:.1f}" x2="{ancho_px - margen_d}" y2="{y_cero:.1f}" />
  <circle class="{clase_punto}" cx="{dx:.1f}" cy="{dy:.1f}" r="5.5" />
  <text class="val" x="{dx + 9:.1f}" y="{dy - 7:.1f}">demanda ({abs(check.Mu_kNm):.0f} kN·m, {check.Pu_kN:.0f} kN)</text>
  <text class="rot" x="{margen_i}" y="{alto_px - 14}">0</text>
  <text class="rot" x="{ancho_px - margen_d}" y="{alto_px - 14}" text-anchor="end">φMn = {m_max:.0f} kN·m</text>
  <text class="rot" x="6" y="{margen_s + 12}">φPn</text>
  <text class="val" x="6" y="{y_cero + 4:.1f}">0 kN</text>
</svg>"""


def _bloque_interaccion(titulo: str, check) -> str:
    if check is None:
        return ""
    clase = "ok" if check.status_ok else "bad"
    ratio = "∞" if check.demand_ratio != check.demand_ratio or check.demand_ratio > 1e6 else f"{check.demand_ratio:.3f}"
    phi_Mn = check.capacity_at_Pu.phi_Mn_kNm if check.capacity_at_Pu else None
    phi = check.capacity_at_Pu.phi if check.capacity_at_Pu else None
    return f"""
<h3>{_e(titulo)}</h3>
{_interaction_svg(check)}
<table>
<tbody>
<tr><td>Fuerza axial de diseño P<sub>u</sub></td><td class="num">{check.Pu_kN:.1f} kN</td></tr>
<tr><td>Momento de diseño M<sub>u</sub></td><td class="num">{abs(check.Mu_kNm):.1f} kN·m</td></tr>
<tr><td>Tope de compresión φP<sub>n,máx</sub> — ec. 10-2</td><td class="num">{check.phi_Pn_max_kN:.1f} kN</td></tr>
<tr><td>Tracción pura −f<sub>y</sub>·A<sub>st</sub></td><td class="num">{check.P0_tension_kN:.1f} kN</td></tr>
<tr><td>Capacidad a momento con ese mismo P<sub>u</sub></td>
    <td class="num">{f'{phi_Mn:.1f} kN·m' if phi_Mn is not None else '—'}</td></tr>
<tr><td>φ aplicado — §9.3.2</td><td class="num">{f'{phi:.3f}' if phi is not None else '—'}</td></tr>
<tr><td>Relación M<sub>u</sub>/φM<sub>n</sub></td><td class="num {clase}">{ratio}</td></tr>
</tbody></table>
<p class="{clase}">{_e(check.message)}</p>
"""


def _tabla_minimo(titulo: str, m) -> str:
    return (
        f"<tr><td>{_e(titulo)}</td>"
        f"<td class='num'>{m.As_min_10_5_1_m2 * 1e4:.2f}</td>"
        f"<td class='num'>{m.As_min_10_5_2_m2 * 1e4:.2f}</td>"
        f"<td class='num'>{m.As_min_governing_m2 * 1e4:.2f}</td>"
        f"<td>{_e(m.governed_by)}</td>"
        f"<td>{'sí' if m.exempt_by_10_5_3 else 'no'}</td></tr>"
    )


def render_beam_report_html(
    result: ConnectingBeamResult, trace: CalculationTrace, titulo: str
) -> str:
    """Memoria de cálculo autocontenida de una viga de conexión."""
    s = result.shear
    lat = result.lateral_requirements

    filas_traza = "".join(
        f"<tr><td>{_e(e.id)}</td><td>{_e(e.description)}</td>"
        f"<td class='eq'>{_e(e.equation_substituted)}</td>"
        f"<td class='num'>{e.result_value:.3f} {_e(e.result_unit)}</td>"
        f"<td>{_e(e.code_name)} {_e(e.code_reference)}</td>"
        f"<td class='{_ESTADO_CLASE.get(e.status, 'info')}'>{_e(e.status.value)}</td></tr>"
        for e in trace.entries
    )
    hipotesis = "".join(
        f"<li><b>{_e(e.id)}</b> — {_e(h)}</li>"
        for e in trace.entries
        for h in e.hypotheses
    )
    mensajes = (
        "<ul>" + "".join(f"<li>{_e(m)}</li>" for m in result.messages) + "</ul>"
        if result.messages
        else "<p>El motor no emitió observaciones.</p>"
    )

    if lat is None or not lat.applies:
        bloque_lateral = (
            f"<p>{_e(lat.reason) if lat else '§21.12.3.3 no evaluado.'}</p>"
        )
    else:
        pendientes = "".join(f"<li>{_e(x)}</li>" for x in lat.not_implemented)
        bloque_lateral = f"""
<p>{_e(lat.reason)}</p>
<table><tbody>
<tr><td>Sección aplicable según §21.2</td><td><b>{_e(lat.section)}</b> — {_e(lat.system_label)}</td></tr>
<tr><td>¿Anula la exención de §10.5.3?</td><td>{'sí' if lat.disallows_10_5_3 else 'no'}</td></tr>
<tr><td>M<sup>+</sup> mínimo en la cara del nudo</td>
    <td>{f'{lat.positive_moment_ratio_at_joint:.3f} · M⁻' if lat.positive_moment_ratio_at_joint else '—'}</td></tr>
<tr><td>Cuantía máxima en tracción</td><td>{lat.max_tension_ratio if lat.max_tension_ratio else '—'}</td></tr>
<tr><td>Luz libre mínima</td>
    <td>{f'{lat.min_clear_span_over_depth:.0f} · h' if lat.min_clear_span_over_depth else '—'}</td></tr>
</tbody></table>
<div class="nota nv"><b>Requisitos de {_e(lat.section)} que este motor NO comprueba.</b>
Mientras sigan sin implementarse, el estado de esta verificación es
<b>NO VERIFICADO</b> y no puede leerse como conformidad.
<ul>{pendientes}</ul></div>
"""

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>{_e(titulo)}</title>
<style>
 body {{ font: 14px/1.5 Georgia, serif; color: #1a1d21; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
 h1 {{ font-size: 26px; border-bottom: 2px solid #1a1d21; padding-bottom: .4rem; }}
 h2 {{ font-size: 19px; margin-top: 2rem; border-top: 1px solid #ccc; padding-top: 1rem; }}
 h3 {{ font-size: 15px; margin-top: 1.4rem; color: #1b4f6b; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; margin: .8rem 0; }}
 th {{ background: #eef1f4; text-align: left; padding: 6px 8px; font-size: 11px;
       text-transform: uppercase; letter-spacing: .05em; }}
 td {{ padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 td.eq {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; }}
 .ok {{ color: #2c6e49; font-weight: 600; }} .bad {{ color: #a03530; font-weight: 600; }}
 .warn {{ color: #8a5a0c; font-weight: 600; }} .nv {{ color: #6b5b8a; font-weight: 600; }}
 .info {{ color: #666; }}
 .nota {{ background: #f4f6f8; border-left: 3px solid #1b4f6b; padding: .7rem 1rem;
          margin: 1rem 0; font-size: 13px; }}
 .nota.nv {{ border-left-color: #6b5b8a; background: #f6f4f9; }}
 svg.interaccion {{ width: 100%; max-width: 660px; height: auto; border: 1px solid #ddd;
                    border-radius: 4px; background: #fff; display: block; margin: .8rem 0; }}
 @media print {{ body {{ margin: 0; max-width: none; }} h2 {{ page-break-after: avoid; }} }}
</style></head><body>

<h1>{_e(titulo)}</h1>
<p><b>Viga de conexión</b> — {result.b_m:.2f} × {result.h_m:.2f} m, d = {result.d_m:.3f} m ·
luz libre {result.clear_span_m:.2f} m ·
estado <span class="{_ESTADO_CLASE.get(result.status, 'info')}">{_e(result.status.value)}</span></p>

<div class="nota"><b>Alcance.</b> Los momentos M<sub>u</sub> y el cortante V<sub>u</sub> son
DATOS DE ENTRADA procedentes del análisis de la estructura: este motor no los deriva. Lo que
verifica es la sección frente a esas solicitaciones.</div>

<h2>1. Dimensión transversal — §21.12.3.2</h2>
<p>Mínimo exigido <b>{result.dimensional.min_dimension_required_m * 1000:.0f} mm</b>,
proporcionado <b>{result.dimensional.min_dimension_provided_m * 1000:.0f} mm</b> —
<span class="{'ok' if result.dimensional.ok else 'bad'}">{'CUMPLE' if result.dimensional.ok else 'NO CUMPLE'}</span>.</p>
<p class="eq"><code>{_e(result.dimensional.equation_substituted)}</code></p>

<h2>2. Flexión y acero longitudinal</h2>
<table>
<thead><tr><th>Cara</th><th>M<sub>u</sub> (kN·m)</th><th>A<sub>s</sub> de diseño (cm²)</th></tr></thead>
<tbody>
<tr><td>Negativa (superior)</td><td class="num">{result.Mu_negative_kNm:.2f}</td>
    <td class="num">{result.As_negative_m2 * 1e4:.2f}</td></tr>
<tr><td>Positiva (inferior)</td><td class="num">{result.Mu_positive_kNm:.2f}</td>
    <td class="num">{result.As_positive_m2 * 1e4:.2f}</td></tr>
</tbody></table>

<h3>Acero mínimo — §10.5</h3>
<table>
<thead><tr><th>Cara</th><th>§10.5.1 (cm²)</th><th>§10.5.2 ec. 10-3 (cm²)</th>
<th>Gobierna (cm²)</th><th>Cuál</th><th>¿Exento por §10.5.3?</th></tr></thead>
<tbody>
{_tabla_minimo('Negativa', result.min_steel_negative)}
{_tabla_minimo('Positiva', result.min_steel_positive)}
</tbody></table>
<div class="nota">Una viga <b>no</b> está entre las excepciones de §10.5.1, que solo exime a
<i>zapatas y losas macizas</i>. El mínimo de una viga de conexión no es el de la zapata que
conecta, y confundirlos deja la viga bajo-armada.</div>

<h2>3. Cortante — §11.3 y §11.5</h2>
<table><tbody>
<tr><td>V<sub>u</sub></td><td class="num">{s.Vu_kN:.2f} kN</td></tr>
<tr><td>V<sub>c</sub> — ec. 11-3</td><td class="num">{s.Vc_kN:.2f} kN</td></tr>
<tr><td>φV<sub>c</sub> con φ = {s.phi:.2f}</td><td class="num">{s.phi_Vc_kN:.2f} kN</td></tr>
<tr><td>V<sub>s</sub> requerido — ec. 11-15</td><td class="num">{s.Vs_required_kN:.2f} kN</td></tr>
<tr><td>V<sub>s,máx</sub> — §11.5.7.9</td>
    <td class="num {'bad' if s.Vs_exceeds_limit else ''}">{s.Vs_max_kN:.2f} kN</td></tr>
<tr><td>¿Estribos por resistencia?</td><td>{'sí' if s.stirrups_required else 'no'}</td></tr>
<tr><td>¿Refuerzo mínimo de §11.5.6?</td>
    <td>{'sí' if s.av_min_required else 'no'}{f' — {_e(s.av_min_exemption)}' if s.av_min_exemption else ''}</td></tr>
</tbody></table>
<p class="eq"><code>{_e(s.equation_substituted)}</code></p>
<p class="{'ok' if s.status_ok else 'bad'}">{_e(s.message)}</p>

<h2>4. Estribos y confinamiento — §21.12.3.2</h2>
<table><tbody>
<tr><td>Separación por resistencia — §11.5.5</td>
    <td class="num">{f'{s.layout.spacing_m * 100:.1f} cm' if s.layout else 'no exigida'}</td></tr>
<tr><td>Límite de confinamiento</td><td class="num">{result.confinement.spacing_limit_m * 100:.1f} cm</td></tr>
<tr><td>Gobierna</td><td>{_e(result.confinement.governed_by)}</td></tr>
<tr><td><b>Separación adoptada</b></td>
    <td class="num"><b>{f'{result.confinement.spacing_provided_m * 100:.1f} cm' if result.confinement.spacing_provided_m is not None else '—'}</b></td></tr>
</tbody></table>
<div class="nota">§21.12.3.2 exige estribos <b>cerrados</b> en toda la longitud de la viga, y
rige aunque el cortante no los pida: son estribos de confinamiento, no de cortante.</div>

<h2>5. Fuerza axial — E.030 art. 65.1</h2>
<p>{'<b>APLICA</b>' if result.axial_required else 'No se dispara'} —
N = {result.axial_N_kN:.2f} kN.</p>
<p class="nota">{_e(result.axial_trigger_note)}</p>
{_bloque_interaccion('Interacción P−M con el momento negativo', result.axial_flexure_negative)}
{_bloque_interaccion('Interacción P−M con el momento positivo', result.axial_flexure_positive)}
{'<div class="nota">La verificación se hizo en <b>los dos sentidos</b> —tracción y compresión—, porque el artículo dice «en tracción o compresión» y no fija el signo. Se reporta el caso más desfavorable de los dos.</div>' if result.axial_required else ''}

<h2>6. Sistema resistente a fuerzas laterales — §21.12.3.3</h2>
{bloque_lateral}

<h2>7. Observaciones del motor</h2>
{mensajes}

<h2>8. Hipótesis declaradas</h2>
<ul>{hipotesis if hipotesis else '<li>Sin hipótesis adicionales.</li>'}</ul>

<h2>9. Traza de cálculo</h2>
<table>
<thead><tr><th>Id</th><th>Verificación</th><th>Sustitución</th><th>Resultado</th>
<th>Referencia</th><th>Estado</th></tr></thead>
<tbody>{filas_traza}</tbody></table>

</body></html>"""
