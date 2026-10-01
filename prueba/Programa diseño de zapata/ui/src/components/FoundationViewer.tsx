import { useEffect, useRef, useState } from "react";
import type { ModeloVisor } from "../viewer3d/model";
import {
  EscenaCima,
  type Banderas,
  type EjeSeccion,
  type EstadoPasos,
  type Modo,
  type Vista,
} from "../viewer3d/stage";

/**
 * Visor 3D del handoff CIMA: escena three.js + superposiciones.
 *
 * La escena (`viewer3d/stage.ts`) es imperativa; este componente la crea una vez, le
 * pasa cada modelo nuevo y dibuja en React todo lo que va encima: modos, corte, cotas,
 * gizmo, vistas, pasos de transición, leyenda y exportación.
 */

const MODOS: { id: Modo; texto: string; tecla: string }[] = [
  { id: "modelo", texto: "Modelo", tecla: "1" },
  { id: "transparente", texto: "Transparente", tecla: "2" },
  { id: "armadura", texto: "Armadura", tecla: "3" },
  { id: "seccion", texto: "Sección", tecla: "4" },
];

const BANDERAS: { id: keyof Banderas; texto: string; tecla?: string }[] = [
  { id: "dims", texto: "Cotas", tecla: "D" },
  { id: "soil", texto: "Suelo", tecla: "S" },
  { id: "axes", texto: "Ejes" },
  { id: "loads", texto: "Cargas" },
];

const VISTAS: { id: Vista; texto: string }[] = [
  { id: "iso", texto: "Isométrica" },
  { id: "planta", texto: "Planta" },
  { id: "frontal", texto: "Frontal" },
  { id: "lateral", texto: "Lateral" },
];

export default function FoundationViewer({
  modelo,
  nombreArchivo,
}: {
  modelo: ModeloVisor;
  nombreArchivo: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const capaRef = useRef<HTMLDivElement>(null);
  const gizmoRef = useRef<HTMLCanvasElement>(null);
  const escenaRef = useRef<EscenaCima | null>(null);

  const [modo, setModo] = useState<Modo>("transparente");
  const [eje, setEje] = useState<EjeSeccion>("long");
  const [banderas, setBanderas] = useState<Banderas>({ dims: true, soil: true, axes: true, loads: true });
  const [pasos, setPasos] = useState<EstadoPasos | null>(null);
  const [reposo, setReposo] = useState(false);
  const [exportando, setExportando] = useState(false);

  // Crear la escena una sola vez.
  useEffect(() => {
    if (!hostRef.current || !capaRef.current || !gizmoRef.current) return;
    const escena = new EscenaCima(hostRef.current, capaRef.current, gizmoRef.current);
    escena.onPasos = setPasos;
    escenaRef.current = escena;
    return () => {
      escena.dispose();
      escenaRef.current = null;
    };
  }, []);

  // Cada modelo nuevo: la escena recorre la transición.
  useEffect(() => {
    escenaRef.current?.setModelo(modelo);
  }, [modelo]);

  useEffect(() => { if (escenaRef.current) escenaRef.current.setModo(modo); }, [modo]);
  useEffect(() => { if (escenaRef.current) escenaRef.current.eje = eje; }, [eje]);
  useEffect(() => { if (escenaRef.current) escenaRef.current.banderas = banderas; }, [banderas]);

  // La barra de pasos se atenúa 3,5 s después de terminar, como en el diseño.
  useEffect(() => {
    setReposo(false);
    if (!pasos?.terminado) return;
    const t = setTimeout(() => setReposo(true), 3500);
    return () => clearTimeout(t);
  }, [pasos?.terminado, pasos?.hasta]);

  // Atajos: 1–4 modos, D cotas, S suelo, R restablecer. Nunca con el foco en un campo.
  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el?.closest("input, select, textarea, [contenteditable]")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const m = MODOS.find((x) => x.tecla === e.key);
      if (m) setModo(m.id);
      else if (e.key === "d" || e.key === "D") setBanderas((b) => ({ ...b, dims: !b.dims }));
      else if (e.key === "s" || e.key === "S") setBanderas((b) => ({ ...b, soil: !b.soil }));
      else if (e.key === "r" || e.key === "R") escenaRef.current?.setVista("reset");
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, []);

  const exportar = async (formato: "obj" | "glb") => {
    const escena = escenaRef.current;
    if (!escena) return;
    setExportando(true);
    try {
      if (formato === "obj") await escena.exportarOBJ(nombreArchivo);
      else await escena.exportarGLB(nombreArchivo);
    } finally {
      setExportando(false);
    }
  };

  const sinArmado = (modo === "armadura" || modo === "transparente" || modo === "seccion")
    && modelo.barras.length === 0 && modelo.notaArmado;

  return (
    <div className="cima-view">
      <div className="cima-stage" ref={hostRef} />
      <div className="cima-labels" ref={capaRef} />

      {/* Arriba-izquierda: modos, eje de corte y capas */}
      <div className="ov tl">
        <div className="seg" role="group" aria-label="Modo de visualización">
          {MODOS.map((m) => (
            <button
              key={m.id}
              className={modo === m.id ? "on" : ""}
              title={`Tecla ${m.tecla}`}
              onClick={() => setModo(m.id)}
            >
              {m.texto}
            </button>
          ))}
        </div>
        {modo === "seccion" && (
          <div className="seg sm" role="group" aria-label="Eje del corte">
            <button className={eje === "long" ? "on" : ""} onClick={() => setEje("long")}>Longitudinal A–A</button>
            <button className={eje === "trans" ? "on" : ""} onClick={() => setEje("trans")}>Transversal</button>
          </div>
        )}
        <div className="toggles">
          {BANDERAS.map((b) => (
            <button
              key={b.id}
              className={`tg ${banderas[b.id] ? "on" : ""}`}
              title={b.tecla ? `Tecla ${b.tecla}` : undefined}
              aria-pressed={banderas[b.id]}
              onClick={() => setBanderas((x) => ({ ...x, [b.id]: !x[b.id] }))}
            >
              <i />
              {b.texto}
            </button>
          ))}
        </div>
        {modelo.esquema && (
          <div className="cima-badge">
            <b>Esquema · sin calcular</b>
            {modelo.tipo === "viga"
              ? "La sección y la luz son datos suyos; el armado lo diseña el motor al pulsar Diseñar viga."
              : "La planta de la zapata la decide el motor: pulse Calcular para ver la geometría diseñada. Solo se acota lo que ya es dato."}
          </div>
        )}
        {!modelo.esquema && sinArmado && (
          <div className="cima-badge suave">
            <b>Armadura no dibujada</b>
            {modelo.notaArmado}
          </div>
        )}
      </div>

      {/* Arriba-derecha: gizmo y vistas */}
      <div className="ov tr">
        <canvas ref={gizmoRef} className="cima-gizmo" title="Clic en un eje para alinear la vista" />
        <div className="vbtns">
          {VISTAS.map((v) => (
            <button key={v.id} onClick={() => escenaRef.current?.setVista(v.id)}>{v.texto}</button>
          ))}
          <hr />
          <button title="Tecla R" onClick={() => escenaRef.current?.setVista("reset")}>Restablecer</button>
        </div>
      </div>

      {/* Abajo-centro: pasos de la transición */}
      <div className="ov bc">
        <div className={`steps ${reposo ? "idle" : ""}`}>
          {!pasos ? (
            <span className="hint">
              Seleccione una tipología para transformar el modelo · arrastrar para orbitar, rueda para zoom
            </span>
          ) : (
            <>
              <span className="ep">{pasos.desde}</span>
              <i className="ar" />
              {pasos.etiquetas.map((l, i) => (
                <span key={l + i} style={{ display: "contents" }}>
                  <span className={`st ${i < pasos.activo ? "done" : i === pasos.activo && !pasos.terminado ? "on" : pasos.terminado ? "done" : ""}`}>
                    <b style={{ width: `${i === pasos.activo && !pasos.terminado ? pasos.progreso * 100 : 0}%` }} />
                    {l}
                  </span>
                  <i className="ar" />
                </span>
              ))}
              <span className={`ep ${pasos.terminado ? "on" : ""}`}>{pasos.hasta}</span>
            </>
          )}
        </div>
      </div>

      {/* Abajo-izquierda: leyenda de materiales */}
      <div className="ov bl">
        <span><i style={{ background: "#d6d3cc" }} />Concreto</span>
        <span><i style={{ background: "#a9b5c1" }} />Viga</span>
        <span><i style={{ background: "#c4683f" }} />Acero principal</span>
        <span><i style={{ background: "#cdbd9f" }} />Suelo</span>
      </div>

      {/* Abajo-derecha: exportación */}
      <div className="ov br">
        <button className="cima-btn" disabled={exportando} onClick={() => exportar("obj")}>Exportar OBJ + MTL</button>
        <button className="cima-btn" disabled={exportando} onClick={() => exportar("glb")}>Exportar GLB</button>
      </div>
    </div>
  );
}
