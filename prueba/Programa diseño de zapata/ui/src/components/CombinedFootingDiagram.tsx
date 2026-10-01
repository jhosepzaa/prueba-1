import type { BoxOut, CombinedSceneOut } from "../lib/api";

/**
 * Esquema de la zapata combinada: planta y alzado a escala (pendiente 1).
 *
 * NO CALCULA NADA. Cada rectángulo es una caja que el motor ya situó
 * (`CombinedSceneDTO`), en el sistema local de la zapata: X a lo largo de B, Y a lo largo
 * de L, Z vertical, origen en el centro de la base. Aquí solo se escala a píxeles.
 *
 * La dirección LONGITUDINAL —aquella en la que se separan las columnas— se dibuja siempre
 * horizontal, venga en X o en Y. Es la que el motor decide y la que traen las cotas; el
 * visor no la deduce, la recibe.
 *
 * El estado viaja con la escena y se muestra junto al dibujo: desde la decisión 6 una
 * alternativa dibujada puede estar NO VERIFICADA, y un esquema limpio no puede leerse
 * como un diseño conforme.
 */

const PAD = 40;
const ANCHO = 640;
const MARGEN_M = 1.2; // espacio para las cotas, en metros de dibujo

const CLASE_ESTADO: Record<string, string> = {
  PASS: "ok",
  INFO: "ok",
  WARNING: "warn",
  "NO VERIFICADO": "nv",
  FAIL: "bad",
};

type Eje = "x" | "y" | "z";

function rect(
  b: BoxOut,
  ejeH: Eje,
  ejeV: Eje,
  sh: (v: number) => number,
  sv: (v: number) => number,
  esc: number
) {
  return {
    x: sh(b.center[ejeH] - b.size[ejeH] / 2),
    y: sv(b.center[ejeV] + b.size[ejeV] / 2),
    width: b.size[ejeH] * esc,
    height: b.size[ejeV] * esc,
  };
}

export default function CombinedFootingDiagram({ scene }: { scene: CombinedSceneOut }) {
  const enX = scene.longitudinal_direction === "X";
  const ejeH: Eje = enX ? "x" : "y";
  const ejeT: Eje = enX ? "y" : "x";
  const largo = enX ? scene.B_m : scene.L_m;
  const ancho = enX ? scene.L_m : scene.B_m;

  const zMax = Math.max(
    ...scene.columns.map((c) => c.box.center.z + c.box.size.z / 2),
    scene.h_m
  );

  const esc = (ANCHO - 2 * PAD) / (largo + 2 * MARGEN_M);
  const sh = (v: number) => PAD + (v + largo / 2 + MARGEN_M) * esc;

  // Planta: el eje transversal crece hacia arriba en el dibujo.
  const altoPlanta = (ancho + 2 * MARGEN_M) * esc + 2 * PAD;
  const st = (v: number) => PAD + (ancho / 2 + MARGEN_M - v) * esc;

  // Alzado: Z hacia arriba, base en z = 0.
  const altoAlzado = zMax * esc + 2 * PAD;
  const sz = (z: number) => PAD + (zMax - z) * esc;

  const eje = (c: CombinedSceneOut["columns"][number]) => (enX ? c.x_m : c.y_m);
  const cotas = scene.dimensions.filter((d) => d.plane === "XY");

  return (
    <div>
      <div className="hint">
        Alternativa <strong>{scene.alternative_id}</strong> · estado{" "}
        <span className={CLASE_ESTADO[scene.status] ?? "info"}>{scene.status}</span> · dirección
        longitudinal <code>{scene.longitudinal_direction}</code>
      </div>
      {scene.status_note && <div className="note nv">{scene.status_note}</div>}

      <div className="eq-label">Planta</div>
      <svg
        width={ANCHO}
        height={altoPlanta}
        style={{ background: "#fff", maxWidth: "100%" }}
        role="img"
        aria-label="Planta de la zapata combinada"
      >
        <rect
          {...rect(scene.footing, ejeH, ejeT, sh, st, esc)}
          fill="#eef2f7"
          stroke="#1e4d8c"
          strokeWidth={1.5}
        />
        {scene.columns.map((c) => (
          <g key={c.label}>
            <line
              x1={sh(eje(c))}
              y1={st(ancho / 2 + MARGEN_M * 0.6)}
              x2={sh(eje(c))}
              y2={st(-ancho / 2 - MARGEN_M * 0.6)}
              stroke="#888"
              strokeDasharray="2 3"
              strokeWidth={0.8}
            />
            <rect {...rect(c.box, ejeH, ejeT, sh, st, esc)} fill="#6b7785" />
            <text x={sh(eje(c)) + 5} y={st(ancho / 2) - 5} fontSize={10} fill="#333">
              {c.label}
            </text>
          </g>
        ))}

        {cotas.map((d) => {
          const h1 = d.start[ejeH];
          const h2 = d.end[ejeH];
          const t1 = d.start[ejeT];
          const t2 = d.end[ejeT];
          const transversal = Math.abs(h1 - h2) < 1e-9;
          const x1 = sh(h1);
          const x2 = sh(h2);
          const y1 = st(t1);
          const y2 = st(t2);
          return (
            <g key={d.id}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#333" strokeWidth={0.8} />
              <text
                x={transversal ? x1 - 4 : (x1 + x2) / 2}
                y={transversal ? (y1 + y2) / 2 : y1 + 12}
                fontSize={10}
                textAnchor={transversal ? "end" : "middle"}
                fill="#333"
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="eq-label">Alzado</div>
      <svg
        width={ANCHO}
        height={altoAlzado}
        style={{ background: "#fff", maxWidth: "100%" }}
        role="img"
        aria-label="Alzado de la zapata combinada"
      >
        <line x1={PAD / 2} y1={sz(0)} x2={ANCHO - PAD / 2} y2={sz(0)} stroke="#999" strokeWidth={0.8} />
        <rect
          {...rect(scene.footing, ejeH, "z", sh, sz, esc)}
          fill="#eef2f7"
          stroke="#1e4d8c"
          strokeWidth={1.5}
        />
        {scene.columns.map((c) => (
          <rect key={c.label} {...rect(c.box, ejeH, "z", sh, sz, esc)} fill="#6b7785" />
        ))}
        <text x={sh(-largo / 2) + 4} y={sz(scene.h_m / 2)} fontSize={10} fill="#33406b">
          h = {scene.h_m.toFixed(2)} m
        </text>
      </svg>

      <div className="hint">{scene.scope_note}</div>
    </div>
  );
}
