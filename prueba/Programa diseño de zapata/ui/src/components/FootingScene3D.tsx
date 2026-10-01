import { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, Html, Line, OrbitControls } from "@react-three/drei";
import type { BarOut, DimensionOut, FootingSceneOut } from "../lib/api";

/**
 * VISOR 3D — consume el FootingSceneDTO y NO recalcula nada.
 *
 * Cada barra que se dibuja tiene el diámetro, la longitud y la posición que el
 * motor resolvió: aquí no se deriva ninguna cantidad de ingeniería. Si un dato
 * no viene en el DTO, no se dibuja.
 *
 * SISTEMA DE COORDENADAS: el DTO usa Z hacia arriba; three.js usa Y hacia arriba.
 * Se resuelve rotando el grupo completo −90° sobre X, de modo que dentro del
 * grupo se pueden usar las coordenadas del DTO tal cual, sin transformarlas una
 * por una (lo que abriría la puerta a errores de conversión).
 */

const COLOR_X = "#c0392b"; // acero dirección X
const COLOR_Y = "#1e7a44"; // acero dirección Y
const COLOR_CONCRETE = "#b9c4d2";
const COLOR_COLUMN = "#6f8199";
const COLOR_COVER = "#8899aa";
const COLOR_DIM = "#33415c";

function Bar({ bar }: { bar: BarOut }) {
  const mid: [number, number, number] = [
    (bar.start.x + bar.end.x) / 2,
    (bar.start.y + bar.end.y) / 2,
    (bar.start.z + bar.end.z) / 2,
  ];
  // El cilindro de three.js nace alineado con su eje Y local. Las barras en
  // dirección Y ya coinciden; las de dirección X se giran 90° sobre Z.
  const rotation: [number, number, number] =
    bar.direction === "X" ? [0, 0, Math.PI / 2] : [0, 0, 0];
  const radius = bar.diameter_m / 2;

  return (
    <mesh position={mid} rotation={rotation}>
      <cylinderGeometry args={[radius, radius, bar.length_m, 10]} />
      <meshStandardMaterial
        color={bar.direction === "X" ? COLOR_X : COLOR_Y}
        roughness={0.5}
        metalness={0.35}
      />
    </mesh>
  );
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
      <Html position={mid} center distanceFactor={9} zIndexRange={[10, 0]}>
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

interface Visibility {
  concrete: boolean;
  column: boolean;
  barsX: boolean;
  barsY: boolean;
  cover: boolean;
  dimensions: boolean;
}

function SceneContent({ scene, vis }: { scene: FootingSceneOut; vis: Visibility }) {
  const barsX = useMemo(() => scene.bars.filter((b) => b.direction === "X"), [scene.bars]);
  const barsY = useMemo(() => scene.bars.filter((b) => b.direction === "Y"), [scene.bars]);

  return (
    // Rotación única: dentro de este grupo rigen las coordenadas del DTO (Z arriba).
    <group rotation={[-Math.PI / 2, 0, 0]}>
      {vis.concrete && (
        <mesh
          position={[scene.footing.center.x, scene.footing.center.y, scene.footing.center.z]}
        >
          <boxGeometry args={[scene.footing.size.x, scene.footing.size.y, scene.footing.size.z]} />
          <meshStandardMaterial
            color={COLOR_CONCRETE}
            transparent
            opacity={vis.barsX || vis.barsY ? 0.42 : 0.9}
            roughness={0.85}
          />
        </mesh>
      )}

      {vis.column && (
        <mesh position={[scene.column.center.x, scene.column.center.y, scene.column.center.z]}>
          <boxGeometry args={[scene.column.size.x, scene.column.size.y, scene.column.size.z]} />
          <meshStandardMaterial color={COLOR_COLUMN} roughness={0.75} />
        </mesh>
      )}

      {vis.cover && (
        <mesh
          position={[scene.cover_box.center.x, scene.cover_box.center.y, scene.cover_box.center.z]}
        >
          <boxGeometry
            args={[scene.cover_box.size.x, scene.cover_box.size.y, scene.cover_box.size.z]}
          />
          <meshBasicMaterial color={COLOR_COVER} wireframe transparent opacity={0.5} />
        </mesh>
      )}

      {vis.barsX && barsX.map((b) => <Bar key={`x-${b.index}`} bar={b} />)}
      {vis.barsY && barsY.map((b) => <Bar key={`y-${b.index}`} bar={b} />)}

      {vis.dimensions && scene.dimensions.map((d) => <Dimension key={d.id} dim={d} />)}
    </group>
  );
}

export default function FootingScene3D({ scene }: { scene: FootingSceneOut }) {
  const [vis, setVis] = useState<Visibility>({
    concrete: true, column: true, barsX: true, barsY: true, cover: true, dimensions: true,
  });

  // Encuadre isométrico inicial, escalado a la zapata concreta.
  const span = Math.max(scene.B_m, scene.L_m, scene.h_m);
  const camDistance = span * 2.1 + 1.6;
  const cameraPosition: [number, number, number] = [camDistance, camDistance * 0.72, camDistance];

  const toggle = (k: keyof Visibility) => setVis((v) => ({ ...v, [k]: !v[k] }));

  return (
    <div>
      {/* El estado real se muestra tal cual: el visor nunca lo presenta como PASS. */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 9, flexWrap: "wrap" }}>
        <strong className="mono">{scene.alternative_id}</strong>
        <span className={`badge ${scene.status}`}>{scene.status}</span>
        <span className="muted">
          B = {scene.B_m.toFixed(2)} m · L = {scene.L_m.toFixed(2)} m · h = {scene.h_m.toFixed(2)} m ·
          d = {scene.d_m.toFixed(3)} m · rec. = {(scene.cover_m * 1000).toFixed(0)} mm
        </span>
      </div>

      <div
        className="viewer-3d"
        style={{ height: 520 }}
      >
        <Canvas
          key={scene.alternative_id}
          camera={{ position: cameraPosition, fov: 42, near: 0.05, far: 400 }}
          dpr={[1, 2]}
        >
          <ambientLight intensity={0.72} />
          <directionalLight position={[8, 12, 6]} intensity={1.15} />
          <directionalLight position={[-6, 5, -8]} intensity={0.4} />

          <SceneContent scene={scene} vis={vis} />

          <Grid
            args={[24, 24]}
            cellSize={0.5}
            cellColor="#cbd4de"
            sectionSize={2}
            sectionColor="#a9b6c4"
            position={[0, -0.002, 0]}
            fadeDistance={38}
            infiniteGrid
          />

          <OrbitControls
            makeDefault
            enablePan
            enableZoom
            enableRotate
            target={[0, scene.h_m / 2, 0]}
            minDistance={0.8}
            maxDistance={span * 9 + 12}
          />
        </Canvas>
      </div>

      <div style={{ display: "flex", gap: 7, marginTop: 10, flexWrap: "wrap" }}>
        {([
          ["concrete", "Concreto"],
          ["column", "Columna"],
          ["barsX", "Acero X"],
          ["barsY", "Acero Y"],
          ["cover", "Recubrimiento"],
          ["dimensions", "Cotas"],
        ] as [keyof Visibility, string][]).map(([k, label]) => (
          <button
            key={k}
            className="tiny"
            onClick={() => toggle(k)}
            style={{
              background: vis[k] ? "var(--accent-soft)" : "#fff",
              borderColor: vis[k] ? "var(--accent)" : "var(--line-strong)",
              color: vis[k] ? "var(--accent)" : "var(--ink-soft)",
              fontWeight: vis[k] ? 600 : 400,
            }}
          >
            {vis[k] ? "◉" : "○"} {label}
          </button>
        ))}
      </div>

      <div className="legend">
        <span><span style={{ color: COLOR_X, fontWeight: 700 }}>■</span> acero dirección X</span>
        <span><span style={{ color: COLOR_Y, fontWeight: 700 }}>■</span> acero dirección Y</span>
        <span>Arrastrar: rotar · Rueda: zoom · Clic derecho o dos dedos: desplazar</span>
      </div>

      <div className="scroll-x" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Dirección</th><th>Capa</th><th>Armado</th>
              <th className="num">Ø (mm)</th><th className="num">s (cm)</th>
              <th className="num">N.º barras</th><th className="num">Long. barra (m)</th>
              <th className="num">d (m)</th>
            </tr>
          </thead>
          <tbody>
            {scene.layers.map((l) => (
              <tr key={l.direction}>
                <td>
                  <span style={{ color: l.direction === "X" ? COLOR_X : COLOR_Y, fontWeight: 700 }}>■</span>{" "}
                  {l.direction}
                </td>
                <td>{l.layer}</td>
                <td className="mono">{l.label}</td>
                <td className="num">{l.diameter_mm.toFixed(1)}</td>
                <td className="num">{l.spacing_cm.toFixed(1)}</td>
                <td className="num">{l.n_bars}</td>
                <td className="num">{l.bar_length_m.toFixed(3)}</td>
                <td className="num">{l.d_m.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="hint" style={{ marginTop: 8 }}>{scene.scope_note}</div>
    </div>
  );
}
