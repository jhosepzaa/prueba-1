import type { AlternativeDetail } from "../lib/api";

/**
 * Esquema 2D acotado (planta y corte). Es un dibujo a escala de las dimensiones
 * que el motor ya resolvió — no calcula nada. El modelo 3D interactivo es materia
 * de la Fase 6; esto solo da lectura inmediata de la geometría.
 */

export default function FootingDiagram({ alt }: { alt: AlternativeDetail }) {
  const { B_m, L_m, h_m, d_m, cover_mm } = alt;

  // --- planta ---
  const planW = 300;
  const scale = planW / Math.max(B_m, L_m);
  const bw = B_m * scale;
  const bl = L_m * scale;
  const colRatio = 0.16;
  const cw = Math.max(bw * colRatio, 22);
  const ch = Math.max(bl * colRatio, 22);
  const padding = 46;
  const planH = bl + padding * 2;

  // --- corte ---
  const sectScale = planW / B_m;
  const sh = h_m * sectScale;
  const sectH = sh + padding * 1.6;

  const cover = cover_mm / 1000;
  const inset = cover * sectScale;

  return (
    <div style={{ display: "flex", gap: 26, flexWrap: "wrap" }}>
      {/* PLANTA */}
      <div>
        <div className="eq-label">Planta</div>
        <svg width={bw + padding * 2} height={planH} style={{ background: "#fff" }}>
          {/* zapata */}
          <rect x={padding} y={padding} width={bw} height={bl} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
          {/* recubrimiento */}
          <rect
            x={padding + cover * scale} y={padding + cover * scale}
            width={bw - 2 * cover * scale} height={bl - 2 * cover * scale}
            fill="none" stroke="#a9b6c8" strokeWidth={0.8} strokeDasharray="3 3"
          />
          {/* columna */}
          <rect
            x={padding + bw / 2 - cw / 2} y={padding + bl / 2 - ch / 2}
            width={cw} height={ch} fill="#c8d6e8" stroke="#14171f" strokeWidth={1.2}
          />
          {/* barras esquemáticas dirección X (corren a lo largo de B) */}
          {Array.from({ length: 7 }).map((_, i) => {
            const y = padding + cover * scale + ((bl - 2 * cover * scale) * (i + 0.5)) / 7;
            return (
              <line key={`x${i}`} x1={padding + cover * scale} y1={y} x2={padding + bw - cover * scale} y2={y}
                stroke="#a32a2a" strokeWidth={0.7} opacity={0.55} />
            );
          })}
          {/* barras dirección Y */}
          {Array.from({ length: 7 }).map((_, i) => {
            const x = padding + cover * scale + ((bw - 2 * cover * scale) * (i + 0.5)) / 7;
            return (
              <line key={`y${i}`} x1={x} y1={padding + cover * scale} x2={x} y2={padding + bl - cover * scale}
                stroke="#1f7a44" strokeWidth={0.7} opacity={0.55} />
            );
          })}

          {/* cota B */}
          <line x1={padding} y1={padding + bl + 16} x2={padding + bw} y2={padding + bl + 16} stroke="#5a6172" strokeWidth={0.9} />
          <line x1={padding} y1={padding + bl + 11} x2={padding} y2={padding + bl + 21} stroke="#5a6172" />
          <line x1={padding + bw} y1={padding + bl + 11} x2={padding + bw} y2={padding + bl + 21} stroke="#5a6172" />
          <text x={padding + bw / 2} y={padding + bl + 33} textAnchor="middle" fontSize="11.5" fill="#14171f">
            B = {B_m.toFixed(2)} m
          </text>

          {/* cota L */}
          <line x1={padding - 16} y1={padding} x2={padding - 16} y2={padding + bl} stroke="#5a6172" strokeWidth={0.9} />
          <line x1={padding - 21} y1={padding} x2={padding - 11} y2={padding} stroke="#5a6172" />
          <line x1={padding - 21} y1={padding + bl} x2={padding - 11} y2={padding + bl} stroke="#5a6172" />
          <text x={padding - 25} y={padding + bl / 2} textAnchor="middle" fontSize="11.5" fill="#14171f"
            transform={`rotate(-90 ${padding - 25} ${padding + bl / 2})`}>
            L = {L_m.toFixed(2)} m
          </text>

          <text x={padding + bw / 2} y={padding + bl / 2 + 3.5} textAnchor="middle" fontSize="9.5" fill="#14171f">
            columna
          </text>
        </svg>
        <div className="legend">
          <span><span style={{ color: "#a32a2a" }}>—</span> acero dir. X</span>
          <span><span style={{ color: "#1f7a44" }}>—</span> acero dir. Y</span>
          <span style={{ color: "#8a90a0" }}>--- recubrimiento {cover_mm.toFixed(0)} mm</span>
        </div>
      </div>

      {/* CORTE */}
      <div>
        <div className="eq-label">Corte</div>
        <svg width={bw + padding * 2} height={sectH} style={{ background: "#fff" }}>
          <rect x={padding} y={padding * 0.5} width={bw} height={sh} fill="#eef2f7" stroke="#1e4d8c" strokeWidth={1.5} />
          {/* columna arrancando */}
          <rect x={padding + bw / 2 - cw / 2} y={padding * 0.5 - 20} width={cw} height={20}
            fill="#c8d6e8" stroke="#14171f" strokeWidth={1.2} />
          {/* parrilla inferior */}
          <line x1={padding + inset} y1={padding * 0.5 + sh - inset} x2={padding + bw - inset} y2={padding * 0.5 + sh - inset}
            stroke="#a32a2a" strokeWidth={2} />
          {Array.from({ length: 9 }).map((_, i) => {
            const x = padding + inset + ((bw - 2 * inset) * i) / 8;
            return <circle key={i} cx={x} cy={padding * 0.5 + sh - inset - 3.2} r={2} fill="#1f7a44" />;
          })}

          {/* cota h */}
          <line x1={padding + bw + 15} y1={padding * 0.5} x2={padding + bw + 15} y2={padding * 0.5 + sh} stroke="#5a6172" strokeWidth={0.9} />
          <line x1={padding + bw + 10} y1={padding * 0.5} x2={padding + bw + 20} y2={padding * 0.5} stroke="#5a6172" />
          <line x1={padding + bw + 10} y1={padding * 0.5 + sh} x2={padding + bw + 20} y2={padding * 0.5 + sh} stroke="#5a6172" />
          <text x={padding + bw + 25} y={padding * 0.5 + sh / 2} fontSize="11.5" fill="#14171f">
            h = {h_m.toFixed(2)} m
          </text>

          <text x={padding + 5} y={padding * 0.5 + sh + 20} fontSize="11" fill="#5a6172">
            d = {d_m.toFixed(3)} m (capa superior, criterio conservador)
          </text>
        </svg>
      </div>
    </div>
  );
}
