import type { BoxOut, ConnectedSceneOut } from "../lib/api";

/**
 * Esquema del sistema conectado: planta y alzado a escala (Fase 4G).
 *
 * NO CALCULA NADA. Cada rectángulo es una caja que el motor ya situó
 * (`ConnectedSceneDTO`), en el sistema local del problema: X a lo largo de la viga
 * desde el lindero, Y transversal, Z vertical. Aquí solo se escala a píxeles.
 *
 * El estado viaja con la escena y se muestra junto al dibujo: un esquema limpio no
 * puede leerse como un diseño conforme.
 */

const PAD = 36;
const ANCHO = 640;

function rectPlanta(b: BoxOut, sx: (x: number) => number, sy: (y: number) => number, esc: number) {
  return {
    x: sx(b.center.x - b.size.x / 2),
    y: sy(b.center.y + b.size.y / 2),
    w: b.size.x * esc,
    h: b.size.y * esc,
  };
}

function rectAlzado(b: BoxOut, sx: (x: number) => number, sz: (z: number) => number, esc: number) {
  return {
    x: sx(b.center.x - b.size.x / 2),
    y: sz(b.center.z + b.size.z / 2),
    w: b.size.x * esc,
    h: b.size.z * esc,
  };
}

export default function ConnectedSystemDiagram({ scene }: { scene: ConnectedSceneOut }) {
  const cajas = [scene.exterior_footing, scene.interior_footing, scene.beam];
  const xMax = Math.max(...cajas.map((b) => b.center.x + b.size.x / 2));
  const yMax = Math.max(...cajas.map((b) => b.size.y / 2));
  const zMax = Math.max(scene.exterior_column.center.z + scene.exterior_column.size.z / 2,
                        scene.interior_column.center.z + scene.interior_column.size.z / 2);

  const esc = (ANCHO - 2 * PAD) / (xMax + 0.6);
  const sx = (x: number) => PAD + (x + 0.3) * esc;

  // Planta: Y hacia arriba en el dibujo.
  const altoPlanta = 2 * yMax * esc + 2 * PAD + 40;
  const sy = (y: number) => PAD + (yMax - y) * esc;

  // Alzado: Z hacia arriba.
  const altoAlzado = zMax * esc + 2 * PAD;
  const sz = (z: number) => PAD + (zMax - z) * esc;

  const pe = rectPlanta(scene.exterior_footing, sx, sy, esc);
  const pi = rectPlanta(scene.interior_footing, sx, sy, esc);
  const pv = rectPlanta(scene.beam, sx, sy, esc);
  const pce = rectPlanta(scene.exterior_column, sx, sy, esc);
  const pci = rectPlanta(scene.interior_column, sx, sy, esc);

  const ae = rectAlzado(scene.exterior_footing, sx, sz, esc);
  const ai = rectAlzado(scene.interior_footing, sx, sz, esc);
  const av = rectAlzado(scene.beam, sx, sz, esc);
  const ace = rectAlzado(scene.exterior_column, sx, sz, esc);
  const aci = rectAlzado(scene.interior_column, sx, sz, esc);

  const cotasPlanta = scene.dimensions.filter((d) => d.plane === "XY");

  return (
    <div>
      <div className="hint">
        Estado de esta alternativa: <span className={`badge ${scene.status}`}>{scene.status_label}</span>
        {scene.open_tbds.length > 0 && (
          <>
            {" "}· pendientes <code>{scene.open_tbds.join(", ")}</code>
          </>
        )}
      </div>

      <div className="eq-label">Planta</div>
      <svg width={ANCHO} height={altoPlanta} style={{ background: "#fff", maxWidth: "100%" }}
           role="img" aria-label="Planta del sistema conectado">
        {/* lindero */}
        <line x1={sx(scene.property_line_x_m)} y1={8} x2={sx(scene.property_line_x_m)} y2={altoPlanta - 8}
              stroke="#a03530" strokeDasharray="6 4" strokeWidth={1.5} />
        <text x={sx(scene.property_line_x_m) + 4} y={16} fontSize={10} fill="#a03530">lindero</text>

        <rect {...{ x: pe.x, y: pe.y, width: pe.w, height: pe.h }} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
        <rect {...{ x: pi.x, y: pi.y, width: pi.w, height: pi.h }} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
        <rect {...{ x: pv.x, y: pv.y, width: pv.w, height: pv.h }} fill="#dfe6ee" stroke="#4a5a6a" strokeWidth={1} />
        <rect {...{ x: pce.x, y: pce.y, width: pce.w, height: pce.h }} fill="#6b7785" />
        <rect {...{ x: pci.x, y: pci.y, width: pci.w, height: pci.h }} fill="#6b7785" />

        {/* ejes de columnas */}
        {[scene.exterior_column_axis_x_m, scene.interior_column_axis_x_m].map((x, i) => (
          <line key={i} x1={sx(x)} y1={PAD - 12} x2={sx(x)} y2={altoPlanta - PAD + 6}
                stroke="#888" strokeDasharray="2 3" strokeWidth={0.8} />
        ))}

        {cotasPlanta.map((d) => {
          const vertical = Math.abs(d.start.x - d.end.x) < 1e-9;
          const x1 = sx(d.start.x), x2 = sx(d.end.x), y1 = sy(d.start.y), y2 = sy(d.end.y);
          return (
            <g key={d.id}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#333" strokeWidth={0.8} />
              <text
                x={vertical ? x1 + 4 : (x1 + x2) / 2}
                y={vertical ? (y1 + y2) / 2 : y1 + 12}
                fontSize={10} textAnchor={vertical ? "start" : "middle"} fill="#333"
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="eq-label">Alzado</div>
      <svg width={ANCHO} height={altoAlzado} style={{ background: "#fff", maxWidth: "100%" }}
           role="img" aria-label="Alzado del sistema conectado">
        <line x1={PAD / 2} y1={sz(0)} x2={ANCHO - PAD / 2} y2={sz(0)} stroke="#999" strokeWidth={0.8} />
        <rect {...{ x: ae.x, y: ae.y, width: ae.w, height: ae.h }} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
        <rect {...{ x: ai.x, y: ai.y, width: ai.w, height: ai.h }} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
        <rect {...{ x: av.x, y: av.y, width: av.w, height: av.h }} fill="#dfe6ee" stroke="#4a5a6a" strokeWidth={1} />
        <rect {...{ x: ace.x, y: ace.y, width: ace.w, height: ace.h }} fill="#6b7785" />
        <rect {...{ x: aci.x, y: aci.y, width: aci.w, height: aci.h }} fill="#6b7785" />
      </svg>

      <div className="hint">{scene.scope_note}</div>
    </div>
  );
}
