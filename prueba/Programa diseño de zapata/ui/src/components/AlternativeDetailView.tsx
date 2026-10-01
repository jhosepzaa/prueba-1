import { useState } from "react";
import type { Formateador } from "../lib/units";
import type { AlternativeDetail, RebarOption } from "../lib/api";
import TraceView from "./TraceView";
import FootingDiagram from "./FootingDiagram";
import FootingScene3D from "./FootingScene3D";

/**
 * Ficha completa de una alternativa: resumen, armado, estabilidad y memoria.
 *
 * UNIDADES. Los números llegan del motor en SI y `fmt` decide en qué unidad se
 * escriben (`lib/units.ts`). Quedan en su unidad de obra los volúmenes (m³), las áreas
 * de acero (cm²) y la traza, que es el registro del propio cálculo.
 */

function Stat({ k, v, u }: { k: string; v: string | number; u?: string }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">
        {v}
        {u && <span className="u"> {u}</span>}
      </div>
    </div>
  );
}

function RatioCell({ value }: { value: number }) {
  const cls = value > 1 ? "FAIL" : value > 0.9 ? "WARNING" : "PASS";
  return (
    <span className={`badge ${cls}`}>
      {Number.isFinite(value) ? value.toFixed(3) : "—"}
    </span>
  );
}

function RebarTable({ title, options, chosen }: { title: string; options: RebarOption[]; chosen: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h4>{title} — seleccionado: <span className="mono">{chosen}</span></h4>
      {options.length === 0 ? (
        <p className="muted">Sin opciones desarrollables en esta dirección.</p>
      ) : (
        <div className="scroll-x">
          <table>
            <thead>
              <tr>
                <th>Opción</th>
                <th className="num">n barras</th>
                <th className="num">As req. (cm²)</th>
                <th className="num">As mín. (cm²)</th>
                <th className="num">As prov. (cm²)</th>
                <th className="num">Uso</th>
                <th>Gobierna</th>
                <th className="num">ld req. (mm)</th>
                <th className="num">ld disp. (mm)</th>
              </tr>
            </thead>
            <tbody>
              {options.map((o) => (
                <tr key={o.label}>
                  <td className="mono">{o.label}</td>
                  <td className="num">{o.n_bars}</td>
                  <td className="num">{o.As_required_cm2.toFixed(2)}</td>
                  <td className="num">{o.As_min_cm2.toFixed(2)}</td>
                  <td className="num">{o.As_provided_cm2.toFixed(2)}</td>
                  <td className="num">{(o.utilization * 100).toFixed(0)} %</td>
                  <td className="muted">{o.governed_by}</td>
                  <td className="num">{o.ld_required_mm?.toFixed(0) ?? "—"}</td>
                  <td className="num">{o.ld_available_mm?.toFixed(0) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="hint">
        Solo se ofrecen opciones cuya longitud de desarrollo cabe en el voladizo disponible
        (E.060 §15.6 → Cap. 12). Las que no se desarrollan quedan excluidas.
      </div>
    </div>
  );
}

export default function AlternativeDetailView({
  alt, fmt,
}: {
  alt: AlternativeDetail;
  fmt: Formateador;
}) {
  const [tab, setTab] = useState<"resumen" | "modelo3d" | "armado" | "estabilidad" | "memoria">("resumen");

  return (
    <div>
      <div className="panel">
        <h2>
          {alt.id} — Alternativa #{alt.rank} <span className={`badge ${alt.status}`}>{alt.status}</span>
        </h2>
        <div className="panel-body">
          <div className="stats">
            <Stat k="B" v={fmt.texto(alt.B_m, "length", 2)} u={fmt.unidad("length")} />
            <Stat k="L" v={fmt.texto(alt.L_m, "length", 2)} u={fmt.unidad("length")} />
            <Stat k="h" v={fmt.texto(alt.h_m, "length", 2)} u={fmt.unidad("length")} />
            <Stat k="d" v={fmt.texto(alt.d_m, "length", 3)} u={fmt.unidad("length")} />
            <Stat k="Concreto" v={alt.concrete_volume_m3.toFixed(2)} u="m³" />
            <Stat k="Acero" v={alt.steel_mass_kg.toFixed(0)} u="kg" />
            <Stat k="Score" v={alt.score.toFixed(4)} />
          </div>
        </div>
      </div>

      <div className="tabs">
        {(["resumen", "modelo3d", "armado", "estabilidad", "memoria"] as const).map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "resumen" && "Resumen técnico"}
            {t === "modelo3d" && "Modelo 3D"}
            {t === "armado" && "Armado"}
            {t === "estabilidad" && "Estabilidad"}
            {t === "memoria" && `Memoria de cálculo (${alt.trace.length})`}
          </button>
        ))}
      </div>

      {tab === "resumen" && (
        <>
          <div className="panel">
            <h2>Esquema</h2>
            <div className="panel-body">
              <FootingDiagram alt={alt} />
            </div>
          </div>

          <div className="panel">
            <h2>Presión de contacto (cargas de servicio)</h2>
            <div className="panel-body">
              <div className="stats">
                <Stat k="q máx" v={fmt.texto(alt.qmax_kPa, "pressure", 1)} u={fmt.unidad("pressure")} />
                <Stat k="q mín" v={fmt.texto(alt.qmin_kPa, "pressure", 1)} u={fmt.unidad("pressure")} />
                <Stat k="q prom" v={fmt.texto(alt.qavg_kPa, "pressure", 1)} u={fmt.unidad("pressure")} />
                <Stat k="ex" v={fmt.texto(alt.ex_m, "length", 4)} u={fmt.unidad("length")} />
                <Stat k="ey" v={fmt.texto(alt.ey_m, "length", 4)} u={fmt.unidad("length")} />
                <Stat k="Peso propio" v={fmt.texto(alt.self_weight_kN, "force", 1)} u={fmt.unidad("force")} />
              </div>
              <div className={`note ${alt.within_kern ? "pass" : "fail"}`} style={{ marginTop: 12 }}>
                <strong>{alt.within_kern ? "Resultante dentro del núcleo central" : "Resultante fuera del núcleo central"}</strong>
                {alt.within_kern
                  ? "La distribución lineal es válida y no hay tracciones en el suelo (E.060 §15.2)."
                  : "El modelo de contacto completo no es aplicable: requeriría el método de área efectiva (E.050 art. 28)."}
              </div>
              <div className="muted">Combinación gobernante: <strong>{alt.governing_combos.contact_pressure}</strong></div>
            </div>
          </div>

          <div className="panel">
            <h2>Verificaciones estructurales (cargas factorizadas)</h2>
            <div className="panel-body">
              <table>
                <thead>
                  <tr>
                    <th>Verificación</th><th className="num">Demanda</th>
                    <th className="num">Vu/φVc</th><th>Gobierna</th><th>Referencia</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Flexión X</td>
                    <td className="num">{fmt.con(alt.Mu_x_kNm, "moment", 1)}</td>
                    <td className="num">—</td>
                    <td>{alt.governing_combos.flexure_x}</td>
                    <td className="muted">§15.4.2, §10.2</td>
                  </tr>
                  <tr>
                    <td>Flexión Y</td>
                    <td className="num">{fmt.con(alt.Mu_y_kNm, "moment", 1)}</td>
                    <td className="num">—</td>
                    <td>{alt.governing_combos.flexure_y}</td>
                    <td className="muted">§15.4.2, §10.2</td>
                  </tr>
                  <tr>
                    <td>Cortante unidireccional X</td>
                    <td className="num">—</td>
                    <td className="num"><RatioCell value={alt.shear_x_ratio} /></td>
                    <td>{alt.governing_combos.shear_x}</td>
                    <td className="muted">ec. 11-3</td>
                  </tr>
                  <tr>
                    <td>Cortante unidireccional Y</td>
                    <td className="num">—</td>
                    <td className="num"><RatioCell value={alt.shear_y_ratio} /></td>
                    <td>{alt.governing_combos.shear_y}</td>
                    <td className="muted">ec. 11-3</td>
                  </tr>
                  <tr>
                    <td>
                      Punzonamiento
                      {alt.punching_has_moment_transfer && (
                        <div className="tiny-label">con transferencia de momento §11.12.7</div>
                      )}
                    </td>
                    <td className="num">b<sub>o</sub> = {fmt.con(alt.punching_bo_m, "length", 3)}</td>
                    <td className="num"><RatioCell value={alt.punching_ratio} /></td>
                    <td>{alt.governing_combos.punching}</td>
                    <td className="muted">ec. {alt.punching_governing_equation}</td>
                  </tr>
                </tbody>
              </table>
              {alt.punching_amplification != null && (
                <div className="note info" style={{ marginTop: 11 }}>
                  <strong>Transferencia de momento incluida</strong>
                  El esfuerzo cortante máximo alrededor del perímetro crítico resulta{" "}
                  {((alt.punching_amplification - 1) * 100).toFixed(1)} % mayor que el del cortante
                  directo, por la fracción γv·Mu transferida por excentricidad (E.060 §11.12.7).
                </div>
              )}
            </div>
          </div>

          <div className="panel">
            <h2>Cómo se calculó la puntuación</h2>
            <div className="panel-body">
              <table>
                <thead>
                  <tr>
                    <th>Métrica</th><th className="num">Valor</th><th className="num">Normalizado</th>
                    <th className="num">Peso</th><th className="num">Aporte</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(alt.score_breakdown).map(([k, b]) => (
                    <tr key={k}>
                      <td>{k.replace(/_/g, " ")}</td>
                      <td className="num">{b.raw.toFixed(3)}</td>
                      <td className="num">{b.normalized.toFixed(4)}</td>
                      <td className="num">{b.weight.toFixed(2)}</td>
                      <td className="num">{b.contribution.toFixed(4)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td colSpan={4}><strong>Score total</strong></td>
                    <td className="num"><strong>{alt.score.toFixed(4)}</strong></td>
                  </tr>
                </tbody>
              </table>
              <div className="hint">
                Normalización mín-máx dentro del conjunto evaluado: el score es relativo a las
                alternativas generadas, no una medida absoluta. Menor es mejor.
              </div>
            </div>
          </div>
        </>
      )}

      {tab === "modelo3d" && (
        <div className="panel">
          <h2>Modelo 3D interactivo</h2>
          <div className="panel-body">
            <FootingScene3D scene={alt.scene} />
          </div>
        </div>
      )}

      {tab === "armado" && (
        <div className="panel">
          <h2>Diseño del refuerzo</h2>
          <div className="panel-body">
            <div className="stats" style={{ marginBottom: 16 }}>
              <Stat k="As req. X" v={alt.As_req_x_cm2.toFixed(2)} u="cm²" />
              <Stat k="As mín. X" v={alt.As_min_x_cm2.toFixed(2)} u="cm²" />
              <Stat k="As req. Y" v={alt.As_req_y_cm2.toFixed(2)} u="cm²" />
              <Stat k="As mín. Y" v={alt.As_min_y_cm2.toFixed(2)} u="cm²" />
              <Stat k="Recubrimiento" v={alt.cover_mm.toFixed(0)} u="mm" />
            </div>

            <RebarTable title="Dirección X" options={alt.rebar_options_x} chosen={alt.rebar_x_label} />
            <RebarTable title="Dirección Y" options={alt.rebar_options_y} chosen={alt.rebar_y_label} />

            {alt.short_direction && (
              <div>
                <h4>Distribución en la dirección corta — E.060 §15.4.4 (ec. 15-1)</h4>
                <p className="muted">
                  β = {alt.short_direction.beta.toFixed(4)} → γs = {alt.short_direction.gamma_s.toFixed(4)}
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Franja</th><th className="num">Ancho ({fmt.unidad("length")})</th>
                      <th className="num">As asignado (cm²)</th><th className="num">As mín. (cm²)</th><th>Nota</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alt.short_direction.bands.map((b) => (
                      <tr key={b.name}>
                        <td>{b.name}</td>
                        <td className="num">{fmt.texto(b.width_m, "length", 2)}</td>
                        <td className="num">{b.As_required_cm2.toFixed(2)}</td>
                        <td className="num">{b.As_min_cm2.toFixed(2)}</td>
                        <td className="muted">{b.topped_up ? "elevado al mínimo §9.7" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="hint">{alt.short_direction.note}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "estabilidad" && (
        <div className="panel">
          <h2>Deslizamiento y volcamiento</h2>
          <div className="panel-body">
            {!alt.stability ? (
              <p className="muted">Sin información de estabilidad.</p>
            ) : (
              <>
                {alt.stability.missing_parameters.length > 0 && (
                  <div className="note warn">
                    <strong>Parámetros faltantes</strong>
                    {alt.stability.missing_parameters.join(" · ")}
                    <div style={{ marginTop: 5 }}>
                      El programa no inventa parámetros geotécnicos: sin ellos la verificación
                      queda NO VERIFICADO.
                    </div>
                  </div>
                )}
                <table>
                  <thead>
                    <tr>
                      <th>Verificación</th><th>Estado</th>
                      <th className="num">FS obtenido</th><th className="num">FS requerido</th><th>Gobierna</th>
                      <th>Lectura de la envolvente</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Deslizamiento</td>
                      <td><span className={`badge ${alt.stability.sliding_status}`}>{alt.stability.sliding_status}</span></td>
                      <td className="num">{alt.stability.sliding_FS?.toFixed(2) ?? "—"}</td>
                      <td className="num">{alt.stability.sliding_FS_required?.toFixed(2) ?? "—"}</td>
                      <td>{alt.stability.sliding_governing_combo ?? "—"}</td>
                      <td>—</td>
                    </tr>
                    <tr>
                      <td>Volcamiento eje X</td>
                      <td><span className={`badge ${alt.stability.overturning_x_status}`}>{alt.stability.overturning_x_status}</span></td>
                      <td className="num">{alt.stability.overturning_x_FS?.toFixed(2) ?? "—"}</td>
                      <td className="num">{alt.stability.overturning_x_FS_required?.toFixed(2) ?? "—"}</td>
                      <td>{alt.stability.overturning_x_governing_combo ?? "—"}</td>
                      <td>{alt.stability.overturning_x_envelope_reading ?? "—"}</td>
                    </tr>
                    <tr>
                      <td>Volcamiento eje Y</td>
                      <td><span className={`badge ${alt.stability.overturning_y_status}`}>{alt.stability.overturning_y_status}</span></td>
                      <td className="num">{alt.stability.overturning_y_FS?.toFixed(2) ?? "—"}</td>
                      <td className="num">{alt.stability.overturning_y_FS_required?.toFixed(2) ?? "—"}</td>
                      <td>{alt.stability.overturning_y_governing_combo ?? "—"}</td>
                      <td>{alt.stability.overturning_y_envelope_reading ?? "—"}</td>
                    </tr>
                  </tbody>
                </table>

                <h4>Modelo de volcamiento adoptado</h4>
                <div className="pre">{alt.stability.pivot_description}</div>
                {alt.stability.criterion_note && (
                  <div className="pre" style={{ marginTop: 7 }}>{alt.stability.criterion_note}</div>
                )}

                <h4>Mensajes del motor</h4>
                <div className="pre">{alt.stability.sliding_message}</div>
                <div className="pre" style={{ marginTop: 7 }}>{alt.stability.overturning_message_x}</div>
                <div className="pre" style={{ marginTop: 7 }}>{alt.stability.overturning_message_y}</div>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "memoria" && (
        <div className="panel">
          <h2>Memoria de cálculo</h2>
          <div className="panel-body">
            <TraceView trace={alt.trace} />
          </div>
        </div>
      )}
    </div>
  );
}
