import { useMemo, useState } from "react";
import { openReport, type ComparisonRow, type DesignRequest, type DesignResponse } from "../lib/api";
import type { Formateador } from "../lib/units";
import AlternativeDetailView from "./AlternativeDetailView";

/**
 * Vista de resultados: resumen, Top-N, tabla comparativa, descartes y limitaciones.
 *
 * UNIDADES. El motor responde siempre en SI; `fmt` solo decide en qué unidad se
 * ESCRIBE cada número (`lib/units.ts`). Los volúmenes (m³) y la masa de acero (kg) se
 * mantienen en su unidad de obra: no son magnitudes que el usuario pueda elegir, y
 * medir el concreto en cm³ no ayudaría a nadie.
 */

type SortKey = keyof Pick<
  ComparisonRow,
  "score" | "concrete_volume_m3" | "steel_mass_kg" | "max_dimension_m" | "complexity" | "qmax_kPa" | "h_m"
>;

const SORT_LABELS: Record<SortKey, string> = {
  score: "Puntuación",
  concrete_volume_m3: "Volumen de concreto",
  steel_mass_kg: "Masa de acero",
  max_dimension_m: "Dimensión máxima",
  complexity: "Complejidad constructiva",
  qmax_kPa: "Presión máxima",
  h_m: "Peralte",
};

/**
 * Indicador del resumen. `tono` colorea la franja superior según lo que mide: verde lo
 * que sobrevive, rojo lo que se descartó, acento el frente de Pareto. El color es
 * SEMÁNTICA —distingue de un vistazo qué mira cada número—, no adorno.
 */
function Stat({
  k, v, u, tono,
}: {
  k: string;
  v: string | number;
  u?: string;
  tono?: "ok" | "mal" | "acento" | "neutro";
}) {
  return (
    <div className={`stat ${tono ? `t-${tono}` : ""}`}>
      <div className="k">{k}</div>
      <div className="v">{v}{u && <span className="u"> {u}</span>}</div>
    </div>
  );
}

export default function ResultsView({
  data, request, fmt, seleccion, onSeleccion,
}: {
  data: DesignResponse;
  request: DesignRequest;
  fmt: Formateador;
  /** Alternativa elegida, cuando la controla quien monta la vista (el visor 3D la sigue). */
  seleccion?: number;
  onSeleccion?: (i: number) => void;
}) {
  const [tab, setTab] = useState<"mejores" | "tabla" | "descartes" | "alcance">("mejores");
  const [seleccionLocal, setSeleccionLocal] = useState(0);
  const selected = Math.min(seleccion ?? seleccionLocal, Math.max(0, data.top.length - 1));
  const setSelected = (i: number) => { setSeleccionLocal(i); onSeleccion?.(i); };
  const [sortBy, setSortBy] = useState<SortKey>("score");
  const [onlyPareto, setOnlyPareto] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const showReport = async (alternativeId: string) => {
    setReportBusy(true);
    setReportError(null);
    try {
      await openReport(request, alternativeId);
    } catch (e) {
      setReportError(e instanceof Error ? e.message : String(e));
    } finally {
      setReportBusy(false);
    }
  };

  const rows = useMemo(() => {
    const filtered = onlyPareto ? data.table.filter((r) => r.in_pareto) : data.table;
    return [...filtered].sort((a, b) => {
      const av = a[sortBy] ?? Number.POSITIVE_INFINITY;
      const bv = b[sortBy] ?? Number.POSITIVE_INFINITY;
      return (av as number) - (bv as number);
    });
  }, [data.table, sortBy, onlyPareto]);

  const s = data.summary;
  const noResults = data.top.length === 0;

  return (
    <div>
      <div className="panel">
        <h2>Resultado de la búsqueda — {s.project_name}</h2>
        <div className="panel-body">
          <div className="stats">
            <Stat k="Geometrías" v={s.n_evaluated} tono="neutro" />
            <Stat k="Alternativas" v={s.n_valid} tono="ok" />
            <Stat k="Descartadas" v={s.n_discarded} tono="mal" />
            <Stat k="Frente Pareto" v={s.pareto_size} tono="acento" />
            <Stat k="Tiempo" v={s.elapsed_seconds.toFixed(2)} u="s" tono="neutro" />
          </div>
          <div className="legend">
            <span>Norma: <strong>{s.code_name}</strong></span>
            <span>§15.7: <strong>{s.min_depth_interpretation === "EFFECTIVE_DEPTH" ? "d ≥ 300 mm" : "h ≥ 300 mm"}</strong></span>
            {Object.entries(s.status_histogram).map(([k, v]) => (
              <span key={k}><span className={`badge ${k}`}>{k}</span> {v}</span>
            ))}
          </div>

          {s.pruned_note && (
            <div className="note info" style={{ marginTop: 12 }}>
              <strong>Geometrías que no se miraron (relación L/B)</strong>
              {s.pruned_note}
            </div>
          )}

          {s.search_boundary_note && (
            <div className="note warn" style={{ marginTop: 12 }}>
              <strong>La mejor alternativa está en el borde del rango explorado</strong>
              {s.search_boundary_note}
            </div>
          )}

          {s.search_range_note && (
            <div className="note info" style={{ marginTop: 12 }}>
              <strong>Rango de búsqueda estimado automáticamente</strong>
              {s.search_range_note}
              <div style={{ marginTop: 5 }}>
                Explorado: B y L de {fmt.texto(s.effective_search_range.B_min_m, "length", 2)} a{" "}
                {fmt.con(s.effective_search_range.B_max_m, "length", 2)} · h de{" "}
                {fmt.texto(s.effective_search_range.h_min_m, "length", 2)} a{" "}
                {fmt.con(s.effective_search_range.h_max_m, "length", 2)}
              </div>
            </div>
          )}

          {data.input_warnings.length > 0 && (
            <div className="note warn" style={{ marginTop: 12 }}>
              <strong>Valores de entrada fuera de rango habitual</strong>
              {data.input_warnings.map((w, i) => <div key={i}>{w.message}</div>)}
            </div>
          )}

          {noResults && (
            <div className="note fail" style={{ marginTop: 12 }}>
              <strong>Ninguna geometría resultó válida</strong>
              Revise la pestaña «Descartes» para ver exactamente qué verificación falló y en cuántas
              geometrías. Suele deberse a un rango de búsqueda insuficiente para la capacidad portante.
            </div>
          )}
        </div>
      </div>

      <div className="tabs">
        {(["mejores", "tabla", "descartes", "alcance"] as const).map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "mejores" && `Mejores alternativas (${data.top.length})`}
            {t === "tabla" && `Tabla comparativa (${data.table.length})`}
            {t === "descartes" && `Descartes (${data.discarded.length} motivos)`}
            {t === "alcance" && "Alcance y limitaciones"}
          </button>
        ))}
      </div>

      {tab === "mejores" && !noResults && (
        <>
          <div className="panel">
            <h2>Seleccione una alternativa</h2>
            <div className="panel-body">
              <div className="scroll-x">
                <table>
                  <thead>
                    <tr>
                      <th>#</th><th>ID</th>
                      <th className="num">B ({fmt.unidad("length")})</th>
                      <th className="num">L ({fmt.unidad("length")})</th>
                      <th className="num">h ({fmt.unidad("length")})</th>
                      <th>Acero X</th><th>Acero Y</th>
                      <th className="num">Concreto</th><th className="num">Acero</th>
                      <th className="num">Score</th><th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top.map((a, i) => (
                      <tr key={a.id} className={i === selected ? "selected" : ""}
                        style={{ cursor: "pointer" }} onClick={() => setSelected(i)}>
                        <td><strong>{a.rank}</strong></td>
                        <td className="mono">{a.id}</td>
                        <td className="num">{fmt.texto(a.B_m, "length", 2)}</td>
                        <td className="num">{fmt.texto(a.L_m, "length", 2)}</td>
                        <td className="num">{fmt.texto(a.h_m, "length", 2)}</td>
                        <td className="mono">{a.rebar_x_label}</td>
                        <td className="mono">{a.rebar_y_label}</td>
                        <td className="num">{a.concrete_volume_m3.toFixed(2)} m³</td>
                        <td className="num">{a.steel_mass_kg.toFixed(0)} kg</td>
                        <td className="num">{a.score.toFixed(4)}</td>
                        <td><span className={`badge ${a.status}`}>{a.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          {reportError && (
            <div className="note fail">
              <strong>No se pudo abrir la memoria de cálculo</strong>
              {reportError}
            </div>
          )}
          <div className="panel">
            <h2>Memoria de cálculo</h2>
            <div className="panel-body">
              <p className="muted" style={{ marginTop: 0 }}>
                Documento con las 16 secciones normativas: datos de entrada, hipótesis, cada
                ecuación con su sustitución numérica y su artículo, verificaciones, alternativas
                descartadas y tabla comparativa. Se abre en una pestaña nueva; para obtener el PDF
                use Ctrl+P y elija «Guardar como PDF».
              </p>
              <button
                className="primary"
                style={{ width: "auto" }}
                disabled={reportBusy}
                onClick={() => showReport(data.top[selected].id)}
              >
                {reportBusy ? <><span className="spinner" />Generando…</> : `Generar memoria de ${data.top[selected].id}`}
              </button>
            </div>
          </div>

          <AlternativeDetailView alt={data.top[selected]} fmt={fmt} />
        </>
      )}

      {tab === "tabla" && (
        <div className="panel">
          <h2>Todas las alternativas válidas</h2>
          <div className="panel-body">
            <div style={{ display: "flex", gap: 14, alignItems: "flex-end", marginBottom: 12, flexWrap: "wrap" }}>
              <div className="field" style={{ marginBottom: 0, minWidth: 230 }}>
                <label>Ordenar por</label>
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortKey)}>
                  {Object.entries(SORT_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div className="checkbox" style={{ marginBottom: 6 }}>
                <input id="pareto" type="checkbox" checked={onlyPareto} onChange={(e) => setOnlyPareto(e.target.checked)} />
                <label htmlFor="pareto">Solo el frente de Pareto ({data.summary.pareto_size})</label>
              </div>
            </div>

            <div className="note info">
              <strong>Frente de Pareto</strong>
              Las alternativas marcadas con ◆ no pueden mejorarse en un objetivo sin empeorar otro.
              Es el compromiso real, antes de aplicar cualquier ponderación subjetiva.
            </div>

            <div className="scroll-x scroll-y">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th className="num">B ({fmt.unidad("length")})</th>
                    <th className="num">L ({fmt.unidad("length")})</th>
                    <th className="num">h ({fmt.unidad("length")})</th>
                    <th className="num">d ({fmt.unidad("length")})</th>
                    <th>Acero X</th><th>Acero Y</th>
                    <th className="num">q máx ({fmt.unidad("pressure")})</th>
                    <th className="num">Concreto (m³)</th><th className="num">Acero (kg)</th>
                    <th className="num">Compl.</th><th className="num">Score</th><th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">
                        {r.in_pareto && <span className="pareto-dot">◆ </span>}{r.id}
                      </td>
                      <td className="num">{fmt.texto(r.B_m, "length", 2)}</td>
                      <td className="num">{fmt.texto(r.L_m, "length", 2)}</td>
                      <td className="num">{fmt.texto(r.h_m, "length", 2)}</td>
                      <td className="num">{fmt.texto(r.d_m, "length", 3)}</td>
                      <td className="mono">{r.steel_x}</td>
                      <td className="mono">{r.steel_y}</td>
                      <td className="num">{fmt.texto(r.qmax_kPa, "pressure", 1)}</td>
                      <td className="num">{r.concrete_volume_m3.toFixed(2)}</td>
                      <td className="num">{r.steel_mass_kg.toFixed(0)}</td>
                      <td className="num">{r.complexity.toFixed(2)}</td>
                      <td className="num">{r.score?.toFixed(4) ?? "—"}</td>
                      <td><span className={`badge ${r.status}`}>{r.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {tab === "descartes" && (
        <div className="panel">
          <h2>Por qué se descartaron las alternativas</h2>
          <div className="panel-body">
            <div className="note info">
              <strong>Transparencia del algoritmo</strong>
              Cada motivo indica cuántas geometrías descartó y muestra un ejemplo con el detalle
              completo de qué cumplió y qué no.
            </div>
            {data.discarded.length === 0 ? (
              <p className="muted">No se descartó ninguna geometría.</p>
            ) : (
              data.discarded.map((g) => (
                <details key={g.reason} className="eq FAIL" style={{ marginBottom: 10 }}>
                  <summary className="eq-head" style={{ listStyle: "none" }}>
                    <div>
                      <div className="eq-title">{g.reason}</div>
                      <div className="eq-meta">
                        {g.count} geometría{g.count === 1 ? "" : "s"} · ejemplo {g.example_id}{" "}
                        (B={g.example_B_m.toFixed(2)} m, L={g.example_L_m.toFixed(2)} m)
                      </div>
                    </div>
                    <span className="badge FAIL">{g.count}</span>
                  </summary>
                  <div className="eq-body">
                    <div className="pre">{g.example_explanation}</div>
                  </div>
                </details>
              ))
            )}
          </div>
        </div>
      )}

      {tab === "alcance" && (
        <>
          <div className="panel">
            <h2>Cuándo el programa puede emitir PASS</h2>
            <div className="panel-body">
              <ol style={{ margin: 0, paddingLeft: 20 }}>
                {data.pass_conditions.map((c, i) => (
                  <li key={i} style={{ marginBottom: 7 }}>{c}</li>
                ))}
              </ol>
            </div>
          </div>

          <div className="panel">
            <h2>Limitaciones declaradas del motor</h2>
            <div className="panel-body">
              <div className="note info">
                <strong>Ninguna limitación oculta</strong>
                Toda limitación relevante que pudiera hacer pasar por válido un diseño inseguro
                degrada el estado del resultado. Las que solo lo vuelven más conservador se
                marcan como informativas.
              </div>
              <div className="scroll-x">
                <table>
                  <thead>
                    <tr>
                      <th>Limitación</th><th>Estado</th><th>Referencia</th>
                      <th>Impacto</th><th>¿Falso PASS?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.limitations.map((l) => (
                      <tr key={l.id}>
                        <td>
                          <strong>{l.title}</strong>
                          <div className="tiny-label">{l.description}</div>
                        </td>
                        <td><span className={`badge ${l.kind === "IMPLEMENTADO" ? "PASS" : "INFO"}`}>{l.kind}</span></td>
                        <td className="muted">{l.code_reference}</td>
                        <td className="muted">{l.impact}</td>
                        <td>
                          <span className={`badge ${l.can_cause_false_pass ? "FAIL" : "PASS"}`}>
                            {l.can_cause_false_pass ? "SÍ" : "No"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
