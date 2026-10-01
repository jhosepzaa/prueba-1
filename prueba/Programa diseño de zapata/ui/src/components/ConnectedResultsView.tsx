import { useState } from "react";
import type { Formateador } from "../lib/units";
import type {
  ConnectedDesignRequest,
  ConnectedDesignResponse,
  ConnectedStatusLabel,
} from "../lib/api";
import { openConnectedReport } from "../lib/api";
import ConnectedScene3D from "./ConnectedScene3D";
import ConnectedSystemDiagram from "./ConnectedSystemDiagram";

/**
 * Resultados de cimentación conectada.
 *
 * EL VOCABULARIO ES ÚNICO PARA LAS TRES TIPOLOGÍAS Y LLEGA DEL SERVIDOR (pendiente 8).
 * Cuatro rótulos —CONFORME, ACEPTADA CON OBSERVACIONES, NO VERIFICADA, RECHAZADA— con
 * cuatro significados que no se solapan. Esta vista NO los
 * deriva: los recibe en `status_label`, porque un rótulo calculado en el cliente acaba
 * divergiendo del que calcula el servidor, y el que divergiría es justo el que dice si
 * algo cumple.
 *
 * La palabra «válida» no aparece aquí. Se lee como «correcta», y mientras TBD-C1 siga
 * abierto ninguna alternativa de esta tipología puede declararse correcta: lo máximo
 * que el motor alcanza es NO VERIFICADA.
 */

interface Props {
  data: ConnectedDesignResponse;
  request: ConnectedDesignRequest;
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

const CLASE_ROTULO: Record<ConnectedStatusLabel, string> = {
  CONFORME: "ok",
  "ACEPTADA CON OBSERVACIONES": "warn",
  "NO VERIFICADA": "nv",
  RECHAZADA: "bad",
};

/** Qué significa cada rótulo, para que el usuario no tenga que deducirlo. */
const GLOSARIO: { rotulo: ConnectedStatusLabel; texto: string }[] = [
  {
    rotulo: "RECHAZADA",
    texto:
      "El sistema no se pudo plantear, o alguna verificación resultó FAIL. No es candidata.",
  },
  {
    rotulo: "ACEPTADA CON OBSERVACIONES",
    texto:
      "Ninguna verificación implementada la descarta, pero alguna salió con reserva. Aceptada no es conforme.",
  },
  {
    rotulo: "NO VERIFICADA",
    texto:
      "Aceptada, pero con un pendiente abierto que impide pronunciarse. No existe criterio normativo que aplicar.",
  },
  {
    rotulo: "CONFORME",
    texto:
      "Aceptada, sin pendientes abiertos y sin observaciones. La única que puede presentarse como cumpliendo.",
  },
];

export default function ConnectedResultsView({ data, request, fmt }: Props) {
  const [verTraza, setVerTraza] = useState(false);
  const [verRechazos, setVerRechazos] = useState(false);
  const [soloPareto, setSoloPareto] = useState(false);

  const comparacion = data.comparison ?? [];
  const filasComparacion = soloPareto ? comparacion.filter((a) => a.in_pareto) : comparacion;

  const claseEstado = CLASE_ESTADO[data.overall_status] ?? "nv";
  const traceConPendiente = data.trace.filter((e) => e.open_tbd);

  return (
    <div className="results">
      {/* ------------------------------------------------------------------
          ESTADO Y PENDIENTES — van ANTES de la tabla de alternativas.
          Quien lea solo la tabla tiene que haber pasado por aquí.
         ------------------------------------------------------------------ */}
      <div className={`note ${claseEstado === "ok" ? "info" : claseEstado}`}>
        <strong>
          Estado del análisis:{" "}
          <span className={`badge ${data.overall_status}`}>{data.overall_status}</span>
        </strong>
        {data.headline}
      </div>

      <div className="panel">
        <h2>Pendientes abiertos</h2>
        <div className="panel-body">
          {data.open_tbds.length === 0 ? (
            <p>No hay pendientes abiertos que afecten a estas alternativas.</p>
          ) : (
            <>
              <table className="mini">
                <thead>
                  <tr>
                    <th>Pendiente</th>
                    <th>Por qué impide verificar</th>
                    <th className="num">Alternativas afectadas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.open_tbds.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <code>{t.id}</code>
                      </td>
                      <td>{t.description}</td>
                      <td className="num">{t.affected_alternatives}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="note warn">
                <strong>No son verificaciones que hayan salido mal</strong>
                Son verificaciones que <em>no existen</em>. No se cierran aportando más
                datos de entrada: requieren una decisión de modelación o una disposición
                normativa de la que hoy no se dispone.
              </div>
            </>
          )}

          {!data.can_claim_compliance && (
            <div className="note nv">
              <strong>Este resultado no se puede presentar como conforme</strong>
              Ninguna alternativa alcanza el rótulo <strong>CONFORME</strong>. Lo que el
              programa entrega es un predimensionamiento trazable con sus hipótesis
              declaradas, no una verificación normativa completa.
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------
          RECUENTO — las cuatro categorías separadas, con su definición.
         ------------------------------------------------------------------ */}
      <div className="panel">
        <h2>Recuento por categoría</h2>
        <div className="panel-body">
          <table className="mini">
            <thead>
              <tr>
                <th>Categoría</th>
                <th className="num">N.º</th>
                <th>Qué significa exactamente</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Sistemas evaluados</td>
                <td className="num">{data.evaluated_count}</td>
                <td>Ternas (lindero + viga + interior) que el barrido llegó a plantear.</td>
              </tr>
              <tr>
                <td>
                  <span className="badge FAIL">RECHAZADAS</span>
                </td>
                <td className="num">{data.rejected_count}</td>
                <td>No se pudieron plantear, o alguna verificación resultó FAIL.</td>
              </tr>
              {Object.entries(data.rejections_by_reason).map(([motivo, n]) => (
                <tr key={motivo}>
                  <td className="sangria">
                    · <code>{motivo}</code>
                  </td>
                  <td className="num">{n}</td>
                  <td>Motivo de rechazo.</td>
                </tr>
              ))}
              <tr>
                <td>
                  <strong>ACEPTADAS</strong>
                </td>
                <td className="num">{data.accepted_count}</td>
                <td>
                  Ninguna verificación <em>implementada</em> las descarta.{" "}
                  <strong>Aceptada no significa conforme.</strong>
                </td>
              </tr>
              <tr>
                <td className="sangria">
                  · de ellas,{" "}
                  <span className="badge NO-VERIFICADO">NO VERIFICADAS</span>
                </td>
                <td className="num">{data.not_verified_count}</td>
                <td>Hay un pendiente abierto y el motor no puede pronunciarse.</td>
              </tr>
              <tr>
                <td className="sangria">· de ellas, con observaciones</td>
                <td className="num">{data.accepted_with_findings_count}</td>
                <td>Algo de lo comprobado salió con reserva (WARNING).</td>
              </tr>
              <tr>
                <td>
                  <strong>CONFORMES</strong>
                </td>
                <td className={`num ${data.can_claim_compliance ? "ok" : "nv"}`}>
                  {data.accepted_and_compliant_count}
                </td>
                <td>
                  Aceptadas, sin pendientes abiertos y sin observaciones. Las únicas que
                  podrían presentarse como cumpliendo.
                </td>
              </tr>
            </tbody>
          </table>

          {data.truncated && (
            <div className="note warn">
              <strong>Búsqueda truncada</strong>
              {data.search_note}
            </div>
          )}

          {data.search_boundary_note && (
            <div className="note warn">
              <strong>La mejor alternativa está en el borde del rango explorado</strong>
              {data.search_boundary_note}
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------
          ESQUEMA DEL SISTEMA — Fase 4G. Posiciones del motor; aquí solo se escala.
         ------------------------------------------------------------------ */}
      {data.scene && (
        <div className="panel">
          <h2>Esquema de la mejor alternativa por costo ({data.scene.alternative_id})</h2>
          <div className="panel-body">
            <ConnectedSystemDiagram scene={data.scene} />
            <div className="eq-label" style={{ marginTop: 14 }}>
              Vista 3D
            </div>
            <ConnectedScene3D scene={data.scene} />
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------
          ALTERNATIVAS ACEPTADAS
         ------------------------------------------------------------------ */}
      <div className="panel">
        <h2>Alternativas aceptadas</h2>
        <div className="panel-body">
          {data.accepted.length === 0 ? (
            <p>No hay alternativas aceptadas que listar.</p>
          ) : (
            <>
              <table className="mini">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Id</th>
                    <th>Zapata de lindero ({fmt.unidad("length")})</th>
                    <th>Zapata interior ({fmt.unidad("length")})</th>
                    <th className="num">Concreto (m³)</th>
                    <th className="num">Acero (kg)</th>
                    <th className="num">ΔP ({fmt.unidad("force")})</th>
                    <th>Estado</th>
                    <th>Verificado</th>
                    <th>Pendientes</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.accepted.map((a, i) => (
                    <tr key={a.id}>
                      <td className="num">{i + 1}</td>
                      <td>{a.id}</td>
                      <td>
                        {fmt.texto(a.exterior_B_m, "length", 2)} ×{" "}
                        {fmt.texto(a.exterior_L_m, "length", 2)} ×{" "}
                        {fmt.texto(a.exterior_h_m, "length", 2)}
                      </td>
                      <td>
                        {fmt.texto(a.interior_B_m, "length", 2)} ×{" "}
                        {fmt.texto(a.interior_L_m, "length", 2)} ×{" "}
                        {fmt.texto(a.interior_h_m, "length", 2)}
                      </td>
                      <td className="num">{a.concrete_volume_m3.toFixed(2)}</td>
                      <td className="num">{a.steel_mass_kg.toFixed(0)}</td>
                      <td className="num">{fmt.texto(a.delta_P_kN, "force", 1)}</td>
                      <td>
                        <span className={`badge ${a.overall_status}`}>
                          {a.status_label}
                        </span>
                      </td>
                      <td className={CLASE_ROTULO[a.status_label] === "ok" ? "ok" : ""}>
                        {a.implemented_checks_status}
                      </td>
                      <td>
                        <code>{a.open_tbds.join(", ") || "—"}</code>
                      </td>
                      <td>
                        <button
                          className="tiny"
                          onClick={() => openConnectedReport(request, a.id)}
                          title="Abrir la memoria de cálculo de esta alternativa"
                        >
                          Memoria
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="note info">
                <strong>Cómo leer las dos columnas de estado</strong>
                <em>Estado</em> dice si el motor puede pronunciarse. <em>Verificado</em>{" "}
                dice si algo de lo que el motor <em>sabe</em> comprobar salió mal. Que la
                segunda diga PASS <strong>no autoriza</strong> a dar el diseño por
                conforme: el orden de la tabla es por costo, y ordenar no aprueba.
              </div>
            </>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------
          TABLA COMPARATIVA — Fase 4G. Todas las aceptadas, con el frente de Pareto.
         ------------------------------------------------------------------ */}
      {comparacion.length > 0 && (
        <div className="panel">
          <h2>Tabla comparativa</h2>
          <div className="panel-body">
            <label className="hint">
              <input
                type="checkbox"
                checked={soloPareto}
                onChange={(e) => setSoloPareto(e.target.checked)}
              />{" "}
              Mostrar solo el frente de Pareto ({data.pareto_size ?? 0} de {comparacion.length})
            </label>
            <table className="mini">
              <thead>
                <tr>
                  <th>Id</th>
                  <th className="num">Concreto (m³)</th>
                  <th className="num">Acero (kg)</th>
                  <th className="num">Área (m²)</th>
                  <th className="num">Longitud sistema ({fmt.unidad("length")})</th>
                  <th className="num">Puntuación</th>
                  <th>Pareto</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {filasComparacion.map((a) => (
                  <tr key={a.id}>
                    <td>{a.id}</td>
                    <td className="num">{a.concrete_volume_m3.toFixed(2)}</td>
                    <td className="num">{a.steel_mass_kg.toFixed(0)}</td>
                    <td className="num">{(a.footing_area_m2 ?? 0).toFixed(2)}</td>
                    <td className="num">{fmt.texto(a.system_length_m, "length", 2)}</td>
                    <td className="num">{a.score.toFixed(4)}</td>
                    <td>{a.in_pareto ? "◆" : ""}</td>
                    <td>
                      <span className={`badge ${a.overall_status}`}>{a.status_label}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="note info">
              <strong>Qué es el frente de Pareto</strong>
              Las alternativas que no pueden mejorar en un objetivo sin empeorar en otro
              ({(data.pareto_objectives ?? []).join(", ")}). Es una comparación de
              <em> costo</em>: pertenecer al frente no cambia el estado de la alternativa.
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------
          GLOSARIO — el vocabulario, escrito.
         ------------------------------------------------------------------ */}
      <div className="panel">
        <h2>Qué significa cada rótulo</h2>
        <div className="panel-body">
          <table className="mini">
            <tbody>
              {GLOSARIO.map((g) => (
                <tr key={g.rotulo}>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <span className={`badge ${CLASE_ROTULO[g.rotulo] === "bad" ? "FAIL" : ""}`}>
                      {g.rotulo}
                    </span>
                  </td>
                  <td>{g.texto}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ------------------------------------------------------------------
          RECHAZOS Y TRAZA
         ------------------------------------------------------------------ */}
      <div className="panel">
        <h2>Sistemas rechazados</h2>
        <div className="panel-body">
          {data.rejected.length === 0 ? (
            <p>Ningún sistema fue rechazado.</p>
          ) : (
            <>
              <button className="secondary" onClick={() => setVerRechazos(!verRechazos)}>
                {verRechazos ? "Ocultar" : `Ver los ${data.rejected.length} primeros rechazos`}
              </button>
              {verRechazos && (
                <table className="mini">
                  <thead>
                    <tr>
                      <th>Zapata de lindero (m)</th>
                      <th>Zapata interior (m)</th>
                      <th>Motivo</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rejected.map((r, i) => (
                      <tr key={i}>
                        <td>
                          {fmt.texto(r.exterior_B_m, "length", 2)} ×{" "}
                          {fmt.texto(r.exterior_L_m, "length", 2)} ×{" "}
                          {fmt.texto(r.exterior_h_m, "length", 2)}
                        </td>
                        <td>
                          {fmt.texto(r.interior_B_m, "length", 2)} ×{" "}
                          {fmt.texto(r.interior_L_m, "length", 2)} ×{" "}
                          {fmt.texto(r.interior_h_m, "length", 2)}
                        </td>
                        <td>
                          <code>{r.reason}</code>
                        </td>
                        <td>{r.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>

      {data.trace.length > 0 && (
        <div className="panel">
          <h2>Memoria de cálculo de la mejor alternativa por costo</h2>
          <div className="panel-body">
            {traceConPendiente.length > 0 && (
              <div className="note nv">
                <strong>
                  {traceConPendiente.length} entrada(s) bloqueada(s) por un pendiente
                </strong>
                {traceConPendiente.map((e) => (
                  <div key={`${e.scope}-${e.id}`}>
                    <code>{e.open_tbd}</code> — {e.description} ({e.scope})
                  </div>
                ))}
                Una entrada NO VERIFICADO <em>con</em> pendiente señala un hueco
                normativo; <em>sin</em> pendiente, señala un dato que usted aún puede
                declarar.
              </div>
            )}
            <button className="secondary" onClick={() => setVerTraza(!verTraza)}>
              {verTraza ? "Ocultar traza" : "Ver traza completa"}
            </button>
            {/*
              Tabla propia en vez de <TraceView>: aquel componente indexa por `id`, y en
              un sistema de tres componentes los ids se repiten —`punching` existe en las
              DOS zapatas—. Reutilizarlo mostraría el punzonamiento de una bajo el rótulo
              de la otra. Aquí la clave es el par (ámbito, id), que es la unicidad real.
            */}
            {verTraza && (
              <table className="mini">
                <thead>
                  <tr>
                    <th>Ámbito</th>
                    <th>Verificación</th>
                    <th>Sustitución</th>
                    <th>Referencia</th>
                    <th>Estado</th>
                    <th>Pendiente</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trace.map((e) => (
                    <tr key={`${e.scope ?? ""}-${e.id}`}>
                      <td>
                        <code>{e.scope ?? "—"}</code>
                      </td>
                      <td>{e.description}</td>
                      <td className="eq-mono">{e.equation_substituted}</td>
                      <td>
                        {e.code_name} {e.code_reference}
                      </td>
                      <td>
                        <span className={`badge ${e.status}`}>{e.status}</span>
                      </td>
                      <td>
                        <code>{e.open_tbd ?? "—"}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button
              className="primary"
              onClick={() => openConnectedReport(request)}
              style={{ marginTop: "0.8rem" }}
            >
              Abrir memoria completa
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
