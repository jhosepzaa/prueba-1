import type { CombinedSceneOut } from "../lib/api";
import BoxScene3D, { type SceneBox } from "./BoxScene3D";

/**
 * Vista 3D de la zapata combinada — pendiente 3.
 *
 * Consume el MISMO `CombinedSceneDTO` que el esquema 2D: la huella, el peralte y la caja de
 * cada columna ya vienen situadas por el motor. Aquí solo se eligen colores y se delega en
 * el visor genérico. No se dibuja armado: el motor no resuelve posiciones de barra para
 * esta tipología, y dibujarlas inventadas sería exactamente lo que la regla prohíbe.
 */

const COLOR_CONCRETE = "#b9c4d2";
const COLOR_COLUMN = "#6f8199";

export default function CombinedScene3D({ scene }: { scene: CombinedSceneOut }) {
  const boxes: SceneBox[] = [
    { key: "zapata", box: scene.footing, color: COLOR_CONCRETE, opacity: 0.92 },
    ...scene.columns.map((c) => ({
      key: `col-${c.label}`,
      box: c.box,
      color: COLOR_COLUMN,
    })),
  ];

  return (
    <BoxScene3D
      alternativeId={scene.alternative_id}
      status={scene.status}
      statusLabel={scene.status_label}
      statusNote={scene.status_note}
      summary={`B = ${scene.B_m.toFixed(2)} m · L = ${scene.L_m.toFixed(2)} m · h = ${scene.h_m.toFixed(2)} m · dirección longitudinal ${scene.longitudinal_direction}`}
      boxes={boxes}
      dimensions={scene.dimensions}
      scopeNote={scene.scope_note}
      span={Math.max(scene.B_m, scene.L_m)}
      targetZ={scene.h_m / 2}
    />
  );
}
