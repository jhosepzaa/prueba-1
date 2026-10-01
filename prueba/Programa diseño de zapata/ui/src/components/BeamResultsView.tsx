import { useState } from "react";
import type { Formateador } from "../lib/units";
import type {
  BeamAxialFlexureOut,
  BeamDesignRequest,
  BeamDesignResponse,
  BeamMinSteelOut,
} from "../lib/api";
import { openBeamReport } from "../lib/api";
import TraceView, { type TraceGroup } from "./TraceView";

/**
 * Resultados de la viga de conexión.
 *
 * La regla de siempre: esta vista NO calcula. Cada número, cada ecuación y cada
 * referencia normativa llega resuelta desde el motor; aquí solo se ordenan.
 *
 * El diagrama de interacción se dibuja con los puntos (φMn, φPn) que envía la API,
 * y el punto de demanda encima. No se interpola nada en el navegador: la capacidad
 * a momento con ese mismo Pu ya viene resuelta en `phi_Mn_at_Pu_kNm`.
 */

interface Props {
  data: BeamDesignResponse;
  request: BeamDesignRequest;
  /** Unidades de presentación; el motor responde en SI. Ver `lib/units.ts`. */
  fmt: Formateador;
}

/** Orden de lectura de la memoria de la viga, distinto del de la zapata. */
const GRUPOS_VIGA: TraceGroup[] = [
  { title: "1. Geometría", ids: ["beam_dimension"] },
  {
    title: "2. Flexión y acero longitudinal",
    ids: [
      "beam_flexure_negativo",
      "beam_min_steel_negativo",
      "beam_flexure_positivo",
      "beam_min_steel_positivo",
    ],
  },
  {
    title: "3. Cortante y estribos",
    ids: [
      "beam_shear_concrete",
      "beam_shear_steel",
      "beam_shear_av_min",
      "beam_stirrup_spacing",
      "beam_confinement",
    ],
  },
  {
    title: "4. Fuerza axial e interacción P−M",
    ids: [
      "beam_axial_trigger",
      "beam_axial_flexure_negativo",
      "beam_axial_flexure_positivo",
    ],
  },
  { title: "5. Sistema resistente a fuerzas laterales", ids: ["beam_lateral_system"] },
];

function Badge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

/** El motor manda −1 cuando el cociente fue infinito: el punto cae fuera del diagrama. */
function formatoRatio(r: number): string {
  return r < 0 ? "fuera del diagrama" : r.toFixed(3);
}

function DiagramaInteraccion({ chk }: { chk: BeamAxialFlexureOut }) {
  const ancho = 620;
  const alto = 400;
  const mi = 64;
  const md = 22;
  const ms = 20;
  const mb = 42;
  const anchoUtil = ancho - mi - md;
  const altoUtil = alto - ms - mb;

  if (chk.diagram.length < 3) {
    return <p className="muted">Sin puntos suficientes para dibujar el diagrama.</p>;
  }

  const mDemanda = Math.abs(chk.Mu_kNm);
  const mMax = Math.max(...chk.diagram.map((p) => p.phi_Mn_kNm), mDemanda, 1) * 1.08;
  const pTodos = [...chk.diagram.map((p) => p.phi_Pn_kN), chk.Pu_kN];
  const pMax = Math.max(...pTodos, 1) * 1.05;
  const pMinBruto = Math.min(...pTodos, 0);
  const pMin = pMinBruto < 0 ? pMinBruto * 1.15 : 0;
  const rangoP = pMax - pMin || 1;

  const ex = (m: number) => mi + (m / mMax) * anchoUtil;
  const ey = (p: number) => ms + altoUtil * ((pMax - p) / rangoP);

  const frontera = chk.diagram
    .map((p) => `${ex(p.phi_Mn_kNm).toFixed(1)},${ey(p.phi_Pn_kN).toFixed(1)}`)
    .join(" ");
  const yCero = ey(0);
  const dx = ex(mDemanda);
  const dy = ey(chk.Pu_kN);

  return (
    <svg
      viewBox={`0 0 ${ancho} ${alto}`}
      className="interaccion"
      role="img"
      aria-label="Diagrama de interacción axial-flexión con el punto de demanda"
    >
      <polygon
        points={`${ex(0).toFixed(1)},${ey(pMax / 1.05).toFixed(1)} ${frontera} ${ex(0).toFixed(
          1
        )},${ey(pMin).toFixed(1)}`}
        fill="var(--accent, #1b4f6b)"
        fillOpacity={0.08}
      />
      <polyline points={frontera} fill="none" stroke="var(--accent, #1b4f6b)" strokeWidth={2} />
      <line x1={mi} y1={ms} x2={mi} y2={alto - mb} stroke="#999" strokeWidth={1} />
      <line x1={mi} y1={yCero} x2={ancho - md} y2={yCero} stroke="#999" strokeWidth={1} />
      <circle
        cx={dx}
        cy={dy}
        r={5.5}
        fill={chk.inside_diagram ? "#2c6e49" : "#a03530"}
        stroke="#fff"
        strokeWidth={1.5}
      />
      <text x={dx + 9} y={dy - 7} fontSize={11} fill="var(--ink, #333)">
        demanda ({mDemanda.toFixed(0)} kN·m, {chk.Pu_kN.toFixed(0)} kN)
      </text>
      <text x={mi} y={alto - 12} fontSize={11} fill="#666">
        0
      </text>
      <text x={ancho - md} y={alto - 12} fontSize={11} textAnchor="end" fill="#666">
        φMn = {mMax.toFixed(0)} kN·m
      </text>
      <text x={6} y={ms + 12} fontSize={11} fill="#666">
        φPn
      </text>
      <text x={6} y={yCero + 4} fontSize={11} fill="#666">
        0 kN
      </text>
    </svg>
  );
}

function BloqueInteraccion({
  titulo, chk, fmt,
}: {
  titulo: string;
  chk: BeamAxialFlexureOut | null;
  fmt: Formateador;
}) {
  if (!chk) return null;
  return (
    <div style={{ marginBottom: 18 }}>
      <h4>{titulo}</h4>
      <DiagramaInteraccion chk={chk} />
      <table className="mini">
        <tbody>
          <tr>
            <td>Fuerza axial de diseño P_u</td>
            <td className="num">{fmt.con(chk.Pu_kN, "force", 1)}</td>
          </tr>
          <tr>
            <td>Momento de diseño M_u</td>
            <td className="num">{fmt.con(Math.abs(chk.Mu_kNm), "moment", 1)}</td>
          </tr>
          <tr>
            <td>Tope de compresión φP_n,máx — ec. 10-2</td>
            <td className="num">{fmt.con(chk.phi_Pn_max_kN, "force", 1)}</td>
          </tr>
          <tr>
            <td>Tracción pura −f_y·A_st</td>
            <td className="num">{fmt.con(chk.P0_tension_kN, "force", 1)}</td>
          </tr>
          <tr>
            <td>Capacidad a momento con ese mismo P_u</td>
            <td className="num">
              {chk.phi_Mn_at_Pu_kNm !== null ? fmt.con(chk.phi_Mn_at_Pu_kNm, "moment", 1) : "—"}
            </td>
          </tr>
          <tr>
            <td>φ aplicado — §9.3.2</td>
            <td className="num">{chk.phi_at_Pu !== null ? chk.phi_at_Pu.toFixed(3) : "—"}</td>
          </tr>
          <tr>
            <td>
              <strong>Relación M_u / φM_n</strong>
            </td>
            <td className={`num ${chk.status_ok ? "ok" : "bad"}`}>
              <strong>{formatoRatio(chk.demand_ratio)}</strong>
            </td>
          </tr>
        </tbody>
      </table>
      <div className={`note ${chk.status_ok ? "pass" : "fail"}`}>{chk.message}</div>
    </div>
  );
}

function FilaMinimo({ titulo, m }: { titulo: string; m: BeamMinSteelOut }) {
  return (
    <tr>
      <td>{titulo}</td>
      <td className="num">{m.As_min_10_5_1_cm2.toFixed(2)}</td>
      <td className="num">{m.As_min_10_5_2_cm2.toFixed(2)}</td>
      <td className="num">
        <strong>{m.As_min_governing_cm2.toFixed(2)}</strong>
      </td>
      <td>{m.governed_by}</td>
      <td>{m.exempt_by_10_5_3 ? "sí" : "no"}</td>
    </tr>
  );
}

export default function BeamResultsView({ data, request, fmt }: Props) {
  const [pestana, setPestana] = useState<"resumen" | "interaccion" | "memoria">("resumen");
  const [errorInforme, setErrorInforme] = useState<string | null>(null);
  const s = data.shear;
  const lat = data.lateral_requirements;

  const abrirInforme = async () => {
    setErrorInforme(null);
    try {
      await openBeamReport(request);
    } catch (e) {
      setErrorInforme(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <>
      <div className="panel">
        <h2>
          Viga de conexión — {fmt.texto(data.b_m, "length", 2)} ×{" "}
          {fmt.con(data.h_m, "length", 2)} ·{" "}
          <Badge status={data.status} />
        </h2>
        <div className="panel-body">
          <div className="kpi-row">
            <div className={`kpi ${data.dimension_ok ? "good" : "bad"}`}>
              <div className="kpi-label">Dimensión mínima §21.12.3.2</div>
              <div className="kpi-value">{data.dimension_provided_mm.toFixed(0)} mm</div>
              <div className="kpi-note">exigido {data.dimension_required_mm.toFixed(0)} mm</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">As cara superior</div>
              <div className="kpi-value">{data.As_negative_cm2.toFixed(2)} cm²</div>
              <div className="kpi-note">Mu⁻ = {fmt.con(data.Mu_negative_kNm, "moment", 1)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">As cara inferior</div>
              <div className="kpi-value">{data.As_positive_cm2.toFixed(2)} cm²</div>
              <div className="kpi-note">Mu⁺ = {fmt.con(data.Mu_positive_kNm, "moment", 1)}</div>
            </div>
            <div className={`kpi ${s.status_ok ? "good" : "bad"}`}>
              <div className="kpi-label">Cortante</div>
              <div className="kpi-value">{fmt.con(s.Vu_kN, "force", 0)}</div>
              <div className="kpi-note">φVc = {fmt.con(s.phi_Vc_kN, "force", 0)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Estribos cerrados</div>
              <div className="kpi-value">
                {data.confinement_provided_cm !== null
                  ? `@ ${data.confinement_provided_cm.toFixed(0)} cm`
                  : "—"}
              </div>
              <div className="kpi-note">límite {data.confinement_limit_cm.toFixed(0)} cm</div>
            </div>
            {data.axial_required && (
              <div className="kpi">
                <div className="kpi-label">N — E.030 art. 65.1</div>
                <div className="kpi-value">{fmt.con(data.axial_N_kN, "force", 0)}</div>
                <div className="kpi-note">0,10 · ΣPu</div>
              </div>
            )}
          </div>

          <div className="tabs">
            <button
              className={pestana === "resumen" ? "tab active" : "tab"}
              onClick={() => setPestana("resumen")}
            >
              Verificaciones
            </button>
            <button
              className={pestana === "interaccion" ? "tab active" : "tab"}
              onClick={() => setPestana("interaccion")}
            >
              Interacción P−M
            </button>
            <button
              className={pestana === "memoria" ? "tab active" : "tab"}
              onClick={() => setPestana("memoria")}
            >
              Memoria de cálculo ({data.trace.length})
            </button>
          </div>

          {pestana === "resumen" && (
            <>
              <h3>Acero longitudinal y su mínimo — §10.5</h3>
              <table className="mini">
                <thead>
                  <tr>
                    <th>Cara</th>
                    <th>§10.5.1 (cm²)</th>
                    <th>§10.5.2 ec. 10-3 (cm²)</th>
                    <th>Gobierna (cm²)</th>
                    <th>Cuál</th>
                    <th>¿Exento por §10.5.3?</th>
                  </tr>
                </thead>
                <tbody>
                  <FilaMinimo titulo="Negativa (superior)" m={data.min_steel_negative} />
                  <FilaMinimo titulo="Positiva (inferior)" m={data.min_steel_positive} />
                </tbody>
              </table>
              <div className="note info">
                <strong>El mínimo de una viga no es el de la zapata que conecta</strong>
                §10.5.1 exime únicamente a <em>zapatas y losas macizas</em>. Una viga de
                conexión no está entre las excepciones, y confundir ambos criterios la deja
                bajo-armada.
              </div>

              <h3>Cortante y estribos — §11.3, §11.5 y §21.12.3.2</h3>
              <table className="mini">
                <tbody>
                  <tr>
                    <td>V_u</td>
                    <td className="num">{s.Vu_kN.toFixed(2)} kN</td>
                  </tr>
                  <tr>
                    <td>V_c — ec. 11-3</td>
                    <td className="num">{s.Vc_kN.toFixed(2)} kN</td>
                  </tr>
                  <tr>
                    <td>φV_c con φ = {s.phi.toFixed(2)}</td>
                    <td className="num">{s.phi_Vc_kN.toFixed(2)} kN</td>
                  </tr>
                  <tr>
                    <td>V_s requerido — ec. 11-15</td>
                    <td className="num">{s.Vs_required_kN.toFixed(2)} kN</td>
                  </tr>
                  <tr>
                    <td>V_s,máx — §11.5.7.9</td>
                    <td className={`num ${s.Vs_exceeds_limit ? "bad" : ""}`}>
                      {s.Vs_max_kN.toFixed(2)} kN
                    </td>
                  </tr>
                  <tr>
                    <td>¿Estribos por resistencia?</td>
                    <td>{s.stirrups_required ? "sí" : "no"}</td>
                  </tr>
                  <tr>
                    <td>¿Refuerzo mínimo de §11.5.6?</td>
                    <td>
                      {s.av_min_required ? "sí" : "no"}
                      {s.av_min_exemption ? ` — ${s.av_min_exemption}` : ""}
                    </td>
                  </tr>
                  <tr>
                    <td>Separación por resistencia</td>
                    <td className="num">
                      {s.spacing_cm !== null ? `${s.spacing_cm.toFixed(1)} cm` : "no exigida"}
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <strong>Separación adoptada — {data.confinement_governed_by}</strong>
                    </td>
                    <td className="num">
                      <strong>
                        {data.confinement_provided_cm !== null
                          ? `${data.confinement_provided_cm.toFixed(1)} cm`
                          : "—"}
                      </strong>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div className={`note ${s.status_ok ? "pass" : "fail"}`}>{s.message}</div>
              <div className="note info">
                <strong>Los estribos de §21.12.3.2 son cerrados y no negociables</strong>
                Rigen en toda la longitud de la viga aunque el cortante no los pida: son de
                confinamiento, no de cortante.
              </div>

              <h3>§21.12.3.3 — sistema resistente a fuerzas laterales</h3>
              {lat === null ? (
                <p className="muted">No evaluado.</p>
              ) : !lat.applies ? (
                <div className="note info">{lat.reason}</div>
              ) : (
                <>
                  <div className="note info">{lat.reason}</div>
                  <table className="mini">
                    <tbody>
                      <tr>
                        <td>Sección aplicable según §21.2</td>
                        <td>
                          <strong>{lat.section || "no resuelto"}</strong>
                          {lat.system_label ? ` — ${lat.system_label}` : ""}
                        </td>
                      </tr>
                      <tr>
                        <td>¿Anula la exención de §10.5.3?</td>
                        <td>{lat.disallows_10_5_3 ? "sí" : "no"}</td>
                      </tr>
                      <tr>
                        <td>M⁺ mínimo en la cara del nudo</td>
                        <td>
                          {lat.positive_moment_ratio_at_joint !== null
                            ? `${lat.positive_moment_ratio_at_joint.toFixed(3)} · M⁻`
                            : "—"}
                        </td>
                      </tr>
                      <tr>
                        <td>Cuantía máxima en tracción</td>
                        <td>{lat.max_tension_ratio ?? "—"}</td>
                      </tr>
                      <tr>
                        <td>Luz libre mínima</td>
                        <td>
                          {lat.min_clear_span_over_depth !== null
                            ? `${lat.min_clear_span_over_depth.toFixed(0)} · h`
                            : "—"}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  {lat.not_implemented.length > 0 && (
                    <div className="note warn">
                      <strong>
                        Requisitos de {lat.section} que este motor NO comprueba —{" "}
                        <span className="badge NO VERIFICADO">NO VERIFICADO</span>
                      </strong>
                      Mientras sigan sin implementarse, esta verificación no puede leerse como
                      conformidad.
                      <ul style={{ marginBottom: 0 }}>
                        {lat.not_implemented.map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}

              {data.messages.length > 0 && (
                <>
                  <h3>Observaciones del motor</h3>
                  <ul>
                    {data.messages.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {pestana === "interaccion" && (
            <>
              <div className={`note ${data.axial_required ? "info" : "pass"}`}>
                <strong>
                  E.030 art. 65.1 —{" "}
                  {data.axial_required ? "APLICA" : "no se dispara"}
                </strong>
                {data.axial_trigger_note}
              </div>
              {data.axial_required ? (
                <>
                  <div className="note info">
                    La verificación se hizo en <strong>los dos sentidos</strong> —tracción y
                    compresión—, porque el artículo dice «en tracción o compresión» y no fija
                    el signo. Se muestra el caso más desfavorable de cada momento. La
                    comprobación <em>no</em> es «φMn ≥ Mu» con el Mn de flexión pura: se busca
                    la capacidad a momento con ese mismo P<sub>u</sub> sobre el diagrama.
                  </div>
                  <BloqueInteraccion
                    fmt={fmt} titulo="Interacción P−M con el momento negativo"
                    chk={data.axial_flexure_negative}
                  />
                  <BloqueInteraccion
                    fmt={fmt} titulo="Interacción P−M con el momento positivo"
                    chk={data.axial_flexure_positive}
                  />
                </>
              ) : (
                <p className="muted">
                  Sin fuerza axial exigida, la viga se verifica a flexión y cortante; no se
                  construye diagrama de interacción.
                </p>
              )}
            </>
          )}

          {pestana === "memoria" && (
            <TraceView
              trace={data.trace}
              groups={GRUPOS_VIGA}
              othersTitle="6. Otras notas del motor"
            />
          )}

          <div style={{ marginTop: 16 }}>
            <button className="secondary" onClick={abrirInforme}>
              Abrir memoria de cálculo imprimible
            </button>
            {errorInforme && <div className="note fail">{errorInforme}</div>}
          </div>
        </div>
      </div>
    </>
  );
}
