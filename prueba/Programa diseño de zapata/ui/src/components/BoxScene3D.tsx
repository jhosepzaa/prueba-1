import { useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, Html, Line, OrbitControls } from "@react-three/drei";
import type { BoxOut, DimensionOut } from "../lib/api";

/**
 * VISOR 3D GENÉRICO de cajas — pendiente 3.
 *
 * Dibuja una lista de prismas y de cotas que el MOTOR ya situó. NO recalcula nada: si un
 * dato no viene en el DTO, no se dibuja. Es la misma regla de `FootingScene3D`, extraída
 * para que la combinada y la conectada no la reimplementen cada una por su lado.
 *
 * Lo que este visor NO hace, y por eso no lo usa la zapata aislada: no dibuja armado. La
 * aislada tiene `FootingSceneDTO` con la posición de cada barra y su propio visor; la
 * combinada y la conectada no resuelven posiciones de barra, y dibujar un armado inventado
 * sería exactamente lo que la regla prohíbe.
 *
 * SISTEMA DE COORDENADAS: los DTO usan Z hacia arriba; three.js usa Y hacia arriba. Se
 * resuelve rotando el grupo completo −90° sobre X, de modo que dentro del grupo rigen las
 * coordenadas del DTO tal cual, sin transformarlas una por una.
 */

const COLOR_DIM = "#33415c";

export interface SceneBox {
  key: string;
  box: BoxOut;
  color: string;
  /** Opacidad; por debajo de 1 el prisma se dibuja translúcido. */
  opacity?: number;
}

function Dimension({ dim }: { dim: DimensionOut }) {
  const a: [number, number, number] = [dim.start.x, dim.start.y, dim.start.z];
  const b: [number, number, number] = [dim.end.x, dim.end.y, dim.end.z];
  const mid: [number, number, number] = [
    (a[0] + b[0]) / 2,
    (a[1] + b[1]) / 2,
    (a[2] + b[2]) / 2,
  ];
  return (
    <group>
      <Line points={[a, b]} color={COLOR_DIM} lineWidth={1.6} />
      <Html position={mid} center distanceFactor={12} zIndexRange={[10, 0]}>
        <div
          style={{
            background: "rgba(255,255,255,0.94)",
            border: "1px solid #c3cad6",
            borderRadius: 3,
            padding: "1px 6px",
            fontSize: 11,
            fontWeight: 600,
            color: COLOR_DIM,
            whiteSpace: "nowrap",
            fontFamily: "Segoe UI, system-ui, sans-serif",
          }}
        >
          {dim.label}
        </div>
      </Html>
    </group>
  );
}

interface Props {
  /** Identificador de la alternativa, tal como lo entrega el motor. */
  alternativeId: string;
  /** `CheckStatus` crudo: el visor NUNCA lo presenta como PASS. */
  status: string;
  /** Rótulo del vocabulario único (pendiente 8). */
  statusLabel?: string;
  /** Línea de dimensiones, ya formateada por quien llama. */
  summary?: string;
  /** Aviso cuando la alternativa no puede presentarse como conforme. */
  statusNote?: string;
  boxes: SceneBox[];
  dimensions: DimensionOut[];
  /** Alcance del dibujo: qué no representa. Viene del motor. */
  scopeNote: string;
  /** Mayor dimensión del conjunto, para encuadrar la cámara. */
  span: number;
  /** Altura a la que apunta la cámara. */
  targetZ: number;
}

const CLASE_ESTADO: Record<string, string> = {
  PASS: "ok",
  INFO: "ok",
  WARNING: "warn",
  "NO VERIFICADO": "nv",
  FAIL: "bad",
};

export default function BoxScene3D({
  alternativeId,
  status,
  statusLabel,
  summary,
  statusNote,
  boxes,
  dimensions,
  scopeNote,
  span,
  targetZ,
}: Props) {
  const [verCotas, setVerCotas] = useState(true);
  const camDistance = span * 1.5 + 2.0;
  const cameraPosition: [number, number, number] = [camDistance, camDistance * 0.62, camDistance];

  return (
    <div>
      <div
        style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 9, flexWrap: "wrap" }}
      >
        <strong className="mono">{alternativeId}</strong>
        <span className={CLASE_ESTADO[status] ?? "info"}>{statusLabel ?? status}</span>
        <span className="muted">{status}</span>
        {summary && <span className="muted">{summary}</span>}
        <label style={{ marginLeft: "auto", fontSize: 12 }}>
          <input type="checkbox" checked={verCotas} onChange={() => setVerCotas((v) => !v)} /> cotas
        </label>
      </div>

      {statusNote && <div className="note nv">{statusNote}</div>}

      <div
        className="viewer-3d"
        style={{ height: 460 }}
      >
        <Canvas
          key={alternativeId}
          camera={{ position: cameraPosition, fov: 42, near: 0.05, far: 600 }}
          dpr={[1, 2]}
        >
          <ambientLight intensity={0.72} />
          <directionalLight position={[8, 12, 6]} intensity={1.15} />
          <directionalLight position={[-6, 5, -8]} intensity={0.4} />

          {/* Rotación única: dentro del grupo rigen las coordenadas del DTO (Z arriba). */}
          <group rotation={[-Math.PI / 2, 0, 0]}>
            {boxes.map((b) => (
              <mesh key={b.key} position={[b.box.center.x, b.box.center.y, b.box.center.z]}>
                <boxGeometry args={[b.box.size.x, b.box.size.y, b.box.size.z]} />
                <meshStandardMaterial
                  color={b.color}
                  roughness={0.8}
                  transparent={(b.opacity ?? 1) < 1}
                  opacity={b.opacity ?? 1}
                />
              </mesh>
            ))}
            {verCotas && dimensions.map((d) => <Dimension key={d.id} dim={d} />)}
          </group>

          <Grid
            args={[48, 48]}
            cellSize={0.5}
            cellColor="#cbd4de"
            sectionSize={2}
            sectionColor="#a9b6c4"
            position={[0, -0.002, 0]}
            fadeDistance={70}
            infiniteGrid
          />

          <OrbitControls
            makeDefault
            enablePan
            enableZoom
            enableRotate
            target={[0, targetZ, 0]}
            minDistance={0.8}
            maxDistance={span * 9 + 20}
          />
        </Canvas>
      </div>

      <div className="hint">{scopeNote}</div>
    </div>
  );
}
