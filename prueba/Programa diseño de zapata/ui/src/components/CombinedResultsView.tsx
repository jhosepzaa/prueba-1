import type { Formateador } from "../lib/units";
import type {
  CombinedDesignRequest,
  CombinedDesignResponse,
  CombinedFaceOut,
  CombinedStabilityOut,
} from "../lib/api";
import { openCombinedReport } from "../lib/api";
import CombinedFootingDiagram from "./CombinedFootingDiagram";
import CombinedScene3D from "./CombinedScene3D";

interface Props {
  data: CombinedDesignResponse;
  request: CombinedDesignRequest;
  /** Unidades de presentación; el motor responde en SI. Ver `lib/units.ts`. */
  fmt: Formateador;
}

const CLASE_ESTADO: Record<string, string> = {
  PASS: "ok",
  INFO: "ok",
  WARNING: "warn",
  "NO VERIFICADO": "nv",
  FAIL: "bad",
};

function Cara({
  titulo, cara, fmt,
}: {
  titulo: string;
  cara: CombinedFaceOut | null;
  fmt: Formateador;
}) {
  if (!cara) {
    return (
      <tr>
        <td>{titulo}</td>
        <td colSpan={5}>
          <em>
            El diagrama no produce momento negativo: esta cara no trabaja a tracción por
            flexión. El refuerzo por cambios volumétricos de §9.7 sigue siendo exigible.
          </em>
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td>{titulo}</td>
      <td className="num">{fmt.texto(cara.Mu_kNm, "moment", 1)}</td>
      <td className="num">{fmt.texto(cara.d_m, "length", 3)}</td>
      <td className="num">{(cara.cover_m * 1000).toFixed(0)}</td>
      <td className="num">{cara.As_design_cm2.toFixed(2)}</td>
      <td>
        {cara.bar_designation ?? "—"}
        {cara.spacing_m ? ` @ ${(cara.spacing_m * 100).toFixed(0)} cm` : ""}
        {cara.development_ok === false ? " ⚠ desarrollo insuficiente" : ""}
      </td>
    </tr>
  );
}

/**
 * Fase 2 — motivos de descarte agrupados. Solo presenta lo que entrega el motor: la
 * categoría, la verificación de traza que la produjo y un ejemplo con el texto original.
 */
function MotivosDescarte({ data, fmt }: { data: CombinedDesignResponse; fmt: Formateador }) {
  const grupos = data.discard_groups ?? [];
  const noResueltas = data.unresolved_groups ?? [];
  if (!grupos.length && !noResueltas.length) return null;
  const porEstado = Object.entries(data.discarded_by_status ?? {})
    .map(([estado, n]) => `${n} ${estado}`)
    .join(" · ");
  return (
    <div className="panel">
      <h2>Motivos de descarte ({data.discarded_count} geometrías)</h2>
      <div className="panel-body">
        {porEstado && <div className="hint">Por estado: {porEstado}</div>}
        <table className="mini">
          <thead>
            <tr>
              <th>Motivo</th>
              <th>Aspecto</th>
              <th>Estado</th>
              <th className="num">Geometrías</th>
              <th className="num">Principal</th>
              <th>Verificación (traza)</th>
              <th>Ejemplo</th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((g) => (
              <tr key={`${g.category}|${g.aspect}|${g.status}`}>
                <td title={g.code_references.join(" · ")}>
                  {g.label}
                  {g.elements.length ? ` (${g.elements.join(", ")})` : ""}
                </td>
                <td>{g.aspect}</td>
                <td className={CLASE_ESTADO[g.status] ?? "info"}>{g.status}</td>
                <td className="num">{g.count}</td>
                <td className="num">{g.primary_count}</td>
                <td>
                  {g.check_ids.join(", ")}
                  {g.has_written_reason ? "" : " — sin motivo escrito"}
                </td>
                <td>
                  {g.example
                    ? `${fmt.texto(g.example.length_m, "length", 2)} × ${fmt.texto(g.example.width_m, "length", 2)} × ${fmt.con(g.example.h_m, "length", 2)}`
                    : "—"}
                  {g.example?.texts.length ? `: ${g.example.texts[0]}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {noResueltas.length > 0 && (
          <div className="hint">
            No resueltas ({data.unresolved_count ?? 0}):{" "}
            {noResueltas.map((u) => `${u.reason} (${u.count})`).join(" · ")}
          </div>
        )}
        <div className="hint">
          Una geometría puede tener varias causas; «Principal» cuenta la primera de mayor
          severidad según el orden de la traza. Los criterios de aceptación no cambian.
        </div>
      </div>
    </div>
  );
}

/**
 * Decisión 6 — la combinada acepta con criterio NO_FAIL, igual que la aislada y la
 * conectada. Aceptada significa «ninguna verificación implementada la descarta», no
 * «cumple». Este panel muestra el desglose que entrega el motor; no lo recalcula.
 */
function EstadoAceptacion({ data }: { data: CombinedDesignResponse }) {
  const porEstado = Object.entries(data.status_summary ?? {});
  if (!porEstado.length) return null;
  const conformes = data.accepted_and_compliant_count ?? 0;
  const noVerificadas = data.not_verified_count ?? 0;
  const conObservaciones = data.accepted_with_findings_count ?? 0;
  const puedeAfirmar = data.can_claim_compliance ?? conformes > 0;
  return (
    <div className={`note ${puedeAfirmar ? "info" : "nv"}`}>
      <strong>
        {data.accepted_count ?? 0} alternativa(s) aceptada(s) —{" "}
        {conformes} en PASS o INFO
        {noVerificadas ? `, ${noVerificadas} NO VERIFICADA(S)` : ""}
        {conObservaciones ? `, ${conObservaciones} con observaciones` : ""}
      </strong>
      {puedeAfirmar
        ? "Aceptada significa que ninguna verificación implementada la descarta. El estado de cada alternativa está en su ficha y en la tabla comparativa."
        : "Ninguna alternativa aceptada puede presentarse como conforme: el motor no puede pronunciarse sobre ellas. Se conservan con su estado en lugar de descartarlas en silencio; revise la traza en la memoria de cálculo."}
      <div className="hint">
        {porEstado.map(([estado, n], i) => (
          <span key={estado}>
            {i > 0 && " · "}
            <span className={CLASE_ESTADO[estado] ?? "info"}>
              {n} {estado}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Pendiente 7 — estabilidad de la zapata combinada. Muestra los tres FS que entrega el
 * motor; no recalcula ninguno. El criterio (FS adoptados en D10-2b y envolvente del
 * momento volcador) viaja con la respuesta.
 */
function Estabilidad({ estabilidad }: { estabilidad: CombinedStabilityOut | null | undefined }) {
  if (!estabilidad) {
    return (
      <div className="hint">
        Estabilidad: no aplicable — ninguna combinación de servicio declara fuerzas
        horizontales.
      </div>
    );
  }
  const ETIQUETA: Record<string, string> = {
    sliding: "Deslizamiento",
    overturning_x: "Volcamiento eje X",
    overturning_y: "Volcamiento eje Y",
  };
  return (
    <>
      <table className="mini">
        <thead>
          <tr>
            <th>Estabilidad</th>
            <th className="num">FS obtenido</th>
            <th className="num">FS requerido</th>
            <th>Combinación</th>
            <th>Lectura</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {estabilidad.checks.map((c) => (
            <tr key={c.check}>
              <td>{ETIQUETA[c.check] ?? c.check}</td>
              <td className="num">{c.FS_obtained === null ? "—" : c.FS_obtained.toFixed(2)}</td>
              <td className="num">{c.FS_required === null ? "—" : c.FS_required.toFixed(2)}</td>
              <td>{c.governing_combo ?? "—"}</td>
              <td>{c.envelope_reading ?? "—"}</td>
              <td className={CLASE_ESTADO[c.status] ?? "info"}>{c.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {estabilidad.checks
        .filter((c) => c.missing_parameters.length > 0)
        .map((c) => (
          <div className="hint" key={`falta-${c.check}`}>
            {ETIQUETA[c.check]}: falta {c.missing_parameters.join(", ")}.
          </div>
        ))}
      <div className="hint">{estabilidad.criterion_note}</div>
    </>
  );
}

export default function CombinedResultsView({ data, request, fmt }: Props) {
  const comparacion = data.comparison ?? [];

  if (!data.top.length) {
    // Desde la decisión 6 la combinada acepta con criterio NO_FAIL, de modo que llegar
    // aquí significa que TODAS las geometrías evaluadas dieron FAIL. Los motivos
    // agrupados dicen cuál verificación las tumbó; ampliar el rango sí viene al caso.
    return (
      <>
        <div className="note fail">
          <strong>Ninguna alternativa aceptada</strong>
          Se evaluaron {data.evaluated_count} geometrías y se descartaron {data.discarded_count}.
          {data.search_note ? ` ${data.search_note}` : " Amplíe el rango de búsqueda."}
        </div>
        <MotivosDescarte data={data} fmt={fmt} />
      </>
    );
  }

  return (
    <>
      {data.search_boundary_note && (
        <div className="note warn">
          <strong>La mejor alternativa está en el borde del rango explorado</strong>
          {data.search_boundary_note}
        </div>
      )}

      {data.search_note && (
        <div className="note warn">
          <strong>{data.truncated ? "Búsqueda truncada" : "Nota de búsqueda"}</strong>
          {data.search_note}
        </div>
      )}

      <EstadoAceptacion data={data} />

      <div className="note info">
        <strong>Convención de momentos (E.050 art. 28.1)</strong>
        {data.axis_convention_note}
      </div>

      {data.centering_length_m !== null && (
        <div className="note info">
          <strong>
            Predimensionamiento: L = {fmt.con(data.centering_length_m, "length", 2)} centraría la
            resultante
          </strong>
          {data.centering_note}
        </div>
      )}

      <div className="panel">
        <h2>
          Alternativas ({data.top.length} de {data.evaluated_count} evaluadas)
        </h2>
        <div className="panel-body">
          {data.top.map((a) => (
            <div className="combo-card" key={a.id}>
              <div className="combo-card-head">
                <strong>{a.id}</strong>
                <span>
                  {fmt.texto(a.length_m, "length", 2)} × {fmt.texto(a.width_m, "length", 2)} ×{" "}
                  {fmt.con(a.h_m, "length", 2)} — {a.concrete_volume_m3.toFixed(2)} m³
                </span>
                <span className={CLASE_ESTADO[a.status] ?? "info"}>{a.status}</span>
                <button className="tiny" onClick={() => openCombinedReport(request, a.id)}>
                  Memoria
                </button>
              </div>

              <table className="mini">
                <thead>
                  <tr>
                    <th>Cara</th>
                    <th className="num">Mu ({fmt.unidad("moment")})</th>
                    <th className="num">d ({fmt.unidad("length")})</th>
                    <th className="num">Recubr. (mm)</th>
                    <th className="num">As (cm²)</th>
                    <th>Armado</th>
                  </tr>
                </thead>
                <tbody>
                  <Cara titulo="Inferior (M+)" cara={a.bottom_face} fmt={fmt} />
                  <Cara titulo="Superior (M−)" cara={a.top_face} fmt={fmt} />
                </tbody>
              </table>

              <table className="mini">
                <thead>
                  <tr>
                    <th>Columna</th>
                    <th>Clasificación</th>
                    <th className="num">Lados</th>
                    <th className="num">α<sub>s</sub></th>
                    <th className="num">Vu/φVc</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {a.punching.map((p) => (
                    <tr key={p.column_label}>
                      <td>{p.column_label}</td>
                      <td>{p.column_position}</td>
                      <td className="num">{p.critical_section_sides}</td>
                      <td className="num">{p.alpha_s.toFixed(0)}</td>
                      <td className="num">{p.ratio.toFixed(3)}</td>
                      <td className={CLASE_ESTADO[p.status] ?? "info"}>{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <Estabilidad estabilidad={a.stability} />

              <div className="hint">
                M⁺ = {fmt.con(a.M_positive_kNm, "moment", 0)} · M⁻ ={" "}
                {fmt.con(a.M_negative_kNm, "moment", 0)} ·
                dirección longitudinal {a.longitudinal_direction}
                {a.has_top_steel ? " · requiere acero de cara superior" : " · sin acero superior"}
              </div>
            </div>
          ))}
        </div>
      </div>

      {data.scene && (
        <div className="panel">
          <h2>Esquema de la alternativa {data.scene.alternative_id}</h2>
          <div className="panel-body">
            <CombinedFootingDiagram scene={data.scene} />
          </div>
        </div>
      )}

      {data.scene && (
        <div className="panel">
          <h2>Vista 3D de la alternativa {data.scene.alternative_id}</h2>
          <div className="panel-body">
            <CombinedScene3D scene={data.scene} />
          </div>
        </div>
      )}

      {comparacion.length > 0 && (
        <div className="panel">
          <h2>Tabla comparativa</h2>
          <div className="panel-body">
            <table className="mini">
              <thead>
                <tr>
                  <th>Id</th>
                  <th className="num">L × B × h ({fmt.unidad("length")})</th>
                  <th className="num">Concreto (m³)</th>
                  <th className="num">Acero (kg)</th>
                  <th className="num">Puntuación</th>
                  <th>Pareto</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {comparacion.map((a) => (
                  <tr key={a.id}>
                    <td>{a.id}</td>
                    <td className="num">
                      {fmt.texto(a.length_m, "length", 2)} × {fmt.texto(a.width_m, "length", 2)} ×{" "}
                      {fmt.texto(a.h_m, "length", 2)}
                    </td>
                    <td className="num">{a.concrete_volume_m3.toFixed(2)}</td>
                    <td className="num">{a.steel_mass_kg.toFixed(0)}</td>
                    <td className="num">{a.score.toFixed(4)}</td>
                    <td>{a.in_pareto ? "◆" : ""}</td>
                    <td className={CLASE_ESTADO[a.status] ?? "info"}>{a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="hint">
              ◆ = frente de Pareto sobre {(data.pareto_objectives ?? []).join(", ")} (
              {data.pareto_size ?? 0} de {comparacion.length}). Es una comparación de costo:
              no cambia el estado de la alternativa.
            </div>
          </div>
        </div>
      )}

      <MotivosDescarte data={data} fmt={fmt} />

      <div className="note info">
        <strong>Qué es norma y qué es criterio en estos resultados</strong>
        El momento en cada sección sale de <b>E.060 §15.4.1</b> y el mínimo repartido en dos
        caras de <b>§10.5.4</b>. En cambio, el ancho de la franja transversal es un{" "}
        <em>criterio de modelación</em> —§15.4 no lo fija para zapatas de varias columnas— y la
        clasificación de columna que decide α<sub>s</sub> es una{" "}
        <em>interpretación declarada</em>: §11.12.2.1(b) da los valores pero no define qué hace
        de borde a una columna. La memoria de cálculo lo detalla.
      </div>
    </>
  );
}
