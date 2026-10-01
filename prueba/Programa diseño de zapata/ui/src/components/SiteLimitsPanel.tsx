import type { SiteLimitsInput } from "../lib/api";

/**
 * Linderos del terreno (2026-09-28), común a la combinada y a la conectada.
 *
 * Se declara la distancia libre de la CARA de la columna al lindero; vacío = sin límite por
 * ese lado. Solo recoge datos: dónde se coloca la zapata dentro de esos límites lo decide
 * el motor (`engine/domain/site_limits.py`).
 */

type Campo = keyof SiteLimitsInput;

export interface CampoLindero {
  campo: Campo;
  etiqueta: string;
  ayuda: string;
}

export default function SiteLimitsPanel({
  value,
  onChange,
  unidad,
  campos,
  nota,
}: {
  value: SiteLimitsInput | null | undefined;
  onChange: (v: SiteLimitsInput | null) => void;
  unidad: string;
  campos: CampoLindero[];
  nota: React.ReactNode;
}) {
  const actual: SiteLimitsInput = value ?? {};
  const poner = (campo: Campo, texto: string) => {
    const siguiente: SiteLimitsInput = { ...actual, [campo]: texto === "" ? null : Math.max(0, Number(texto)) };
    const vacio = Object.values(siguiente).every((v) => v === null || v === undefined);
    onChange(vacio ? null : siguiente);
  };

  return (
    <div className="panel">
      <h2>Límites del terreno</h2>
      <div className="panel-body">
        <div className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
          Distancia libre de la <strong>cara de la columna</strong> al lindero, en {unidad}. Deje
          el campo vacío si por ese lado no hay límite; 0 es una columna al ras del lindero.
        </div>
        <div className="grid2">
          {campos.map(({ campo, etiqueta, ayuda }) => (
            <div className="field" key={campo}>
              <label title={ayuda}>{etiqueta}</label>
              <input
                type="number"
                min={0}
                step={0.05}
                placeholder="sin límite"
                value={actual[campo] ?? ""}
                onChange={(e) => poner(campo, e.target.value)}
              />
            </div>
          ))}
        </div>
        <div className="auto-note">{nota}</div>
      </div>
    </div>
  );
}
