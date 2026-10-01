import { useState } from "react";
import type { TraceEntry } from "../lib/api";

/**
 * MEMORIA DE CÁLCULO. La pieza académica de la interfaz: cada verificación
 * muestra su ecuación simbólica, la misma ecuación con los valores sustituidos,
 * el resultado, las hipótesis y el artículo normativo exacto.
 *
 * La UI no calcula ni compone ninguna fórmula: todos estos textos llegan
 * resueltos desde el motor.
 */

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

function EquationBlock({ entry, defaultOpen }: { entry: TraceEntry; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`eq ${entry.status}`}>
      <div className="eq-head" onClick={() => setOpen(!open)}>
        <div>
          <div className="eq-title">
            {open ? "▾" : "▸"} {entry.scope ? `[${entry.scope}] ` : ""}{entry.description}
          </div>
          <div className="eq-meta">
            {entry.code_name} · {entry.code_reference}
            {entry.governing_combo && ` · gobierna ${entry.governing_combo}`}
          </div>
        </div>
        <StatusBadge status={entry.status} />
      </div>

      {open && (
        <div className="eq-body">
          <div className="eq-line">
            <div className="eq-label">Ecuación</div>
            <div className="formula">{entry.equation_symbolic}</div>
          </div>

          <div className="eq-line">
            <div className="eq-label">Sustitución numérica</div>
            <div className="formula subst">{entry.equation_substituted}</div>
          </div>

          <div className="eq-line">
            <div className="eq-label">Resultado</div>
            <div>
              <strong className="mono">
                {Number.isFinite(entry.result_value) ? entry.result_value.toPrecision(6) : "—"}
              </strong>{" "}
              <span className="muted">{entry.result_unit}</span>
            </div>
          </div>

          {entry.hypotheses.length > 0 && (
            <div className="eq-line">
              <div className="eq-label">Hipótesis y observaciones</div>
              {entry.hypotheses.map((h, i) => (
                <div className="hyp" key={i}>{h}</div>
              ))}
            </div>
          )}

          <div className="eq-line">
            <div className="eq-label">Fuente normativa</div>
            <span className="cite">{entry.code_name} — {entry.code_reference}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** Clave única de una entrada: el par (ámbito, id). Igual que `trace_key` del motor. */
export function traceKey(e: TraceEntry): string {
  return e.scope ? `${e.scope}/${e.id}` : e.id;
}

export interface TraceGroup {
  title: string;
  ids: string[];
}

/** Agrupacion por defecto: la de la zapata aislada. */
const GROUPS: TraceGroup[] = [
  { title: "1. Cargas y geometría", ids: ["self_weight"] },
  { title: "2. Interacción con el suelo", ids: ["contact_pressure", "sliding", "overturning_x", "overturning_y"] },
  { title: "3. Dimensionamiento", ids: ["min_depth"] },
  { title: "4. Diseño por flexión", ids: ["flexure_x", "flexure_y", "short_direction_distribution"] },
  { title: "5. Verificación por cortante", ids: ["shear_x", "shear_y", "punching"] },
  {
    title: "6. Detallado del refuerzo",
    ids: ["rebar_x", "rebar_y", "rebar_options_development_x", "rebar_options_development_y", "development_x", "development_y"],
  },
];

/**
 * `groups` y `othersTitle` permiten que otras tipologias reutilicen esta vista con
 * su propio orden de secciones. Omitirlos deja el comportamiento de la zapata
 * aislada intacto.
 */
export default function TraceView({
  trace,
  groups = GROUPS,
  othersTitle,
}: {
  trace: TraceEntry[];
  groups?: TraceGroup[];
  othersTitle?: string;
}) {
  const [onlyIssues, setOnlyIssues] = useState(false);
  const shown = onlyIssues ? trace.filter((e) => e.status !== "PASS") : trace;
  // Fase 4H. Un id puede repetirse entre ámbitos (`punching` existe en las dos zapatas de
  // un sistema conectado): la unicidad es del par (scope, id). Antes el Map guardaba solo
  // la última entrada de cada id y la vista mostraba una zapata bajo el rótulo de otra.
  const byId = new Map<string, TraceEntry[]>();
  for (const e of shown) {
    byId.set(e.id, [...(byId.get(e.id) ?? []), e]);
  }
  const grouped = groups
    .map((g) => ({
      ...g,
      entries: g.ids.flatMap((id) => byId.get(id) ?? []),
    }))
    .filter((g) => g.entries.length > 0);

  const placed = new Set(groups.flatMap((g) => g.ids));
  const others = shown.filter((e) => !placed.has(e.id));
  const tituloOtros = othersTitle ?? `${groups.length + 1}. Limitaciones y notas del motor`;

  return (
    <div>
      <div className="note info">
        <strong>Memoria de cálculo</strong>
        Cada verificación muestra su ecuación, la sustitución con los valores de este
        caso, el resultado y el artículo del que proviene. Haga clic en cualquier bloque
        para plegarlo o desplegarlo.
      </div>

      <div className="checkbox">
        <input id="onlyIssues" type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />
        <label htmlFor="onlyIssues">Mostrar solo lo que no está en PASS ({trace.filter((e) => e.status !== "PASS").length})</label>
      </div>

      {grouped.map((g) => (
        <div key={g.title} style={{ marginBottom: 18 }}>
          <h3>{g.title}</h3>
          {g.entries.map((e) => (
            <EquationBlock key={traceKey(e)} entry={e} defaultOpen={e.status !== "PASS"} />
          ))}
        </div>
      ))}

      {others.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <h3>{tituloOtros}</h3>
          {others.map((e) => (
            <EquationBlock key={traceKey(e)} entry={e} defaultOpen />
          ))}
        </div>
      )}

      {shown.length === 0 && <p className="muted">Sin entradas que mostrar con el filtro activo.</p>}
    </div>
  );
}
