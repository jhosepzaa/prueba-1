import type { ConnectedSceneOut } from "../lib/api";
import BoxScene3D, { type SceneBox } from "./BoxScene3D";

/**
 * Vista 3D del sistema conectado — pendiente 3.
 *
 * Consume el MISMO `ConnectedSceneDTO` que la planta y el alzado: las dos zapatas, la viga
 * y los arranques de columna ya vienen situados por el motor, en el sistema local del
 * problema (X a lo largo de la viga desde el lindero). Aquí solo se eligen colores.
 *
 * No se dibuja armado, y la cota vertical de la viga respecto de las zapatas sigue siendo
 * una convención de dibujo: lo dice `scope_note`, que viaja con la escena.
 */

const COLOR_CONCRETE = "#b9c4d2";
const COLOR_BEAM = "#9aa8bb";
const COLOR_COLUMN = "#6f8199";

export default function ConnectedScene3D({ scene }: { scene: ConnectedSceneOut }) {
  const boxes: SceneBox[] = [
    { key: "zap-ext", box: scene.exterior_footing, color: COLOR_CONCRETE, opacity: 0.92 },
    { key: "zap-int", box: scene.interior_footing, color: COLOR_CONCRETE, opacity: 0.92 },
    { key: "viga", box: scene.beam, color: COLOR_BEAM, opacity: 0.95 },
    { key: "col-ext", box: scene.exterior_column, color: COLOR_COLUMN },
    { key: "col-int", box: scene.interior_column, color: COLOR_COLUMN },
  ];

  const alturas = [
    scene.exterior_footing.center.z + scene.exterior_footing.size.z / 2,
    scene.interior_footing.center.z + scene.interior_footing.size.z / 2,
  ];

  return (
    <BoxScene3D
      alternativeId={scene.alternative_id}
      status={scene.status}
      statusLabel={scene.status_label}
      summary={`sistema de ${scene.system_length_m.toFixed(2)} m · vano libre ${(scene.free_span_end_x_m - scene.free_span_start_x_m).toFixed(2)} m · eje ${scene.longitudinal_axis}${scene.open_tbds.length ? ` · pendientes ${scene.open_tbds.join(", ")}` : ""}`}
      boxes={boxes}
      dimensions={scene.dimensions}
      scopeNote={scene.scope_note}
      span={scene.system_length_m}
      targetZ={Math.max(...alturas) / 2}
    />
  );
}
