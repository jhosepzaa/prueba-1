import type { CombinationDefinitionInput, LoadCaseInput } from "../lib/api";

/**
 * Fase 10B — modo de cargas por CASOS (contrato C del análisis del contrato de cargas).
 *
 * Aquí no se calcula nada: se recogen casos sin factorizar por columna (E.060 §9.2: CM, CV,
 * CVi, CS, CE, CL, CT; nivel de servicio o de resistencia para CVi y CS) y combinaciones
 * declaradas como factores sobre esos casos. El motor deriva las combinaciones y conserva
 * su composición, que es lo que le permite factorizar el peso propio de la viga, reducir
 * solo el sismo para el suelo y contar solo la carga muerta en la estabilidad.
 *
 * Los casos tienen la MISMA estructura (nombre, tipo, nivel) en todas las columnas: las
 * combinaciones los nombran y deben existir en cada una. Solo los valores cambian.
 *
 * Todo cambio se entrega en UNA sola llamada con todas las columnas y las definiciones:
 * varias llamadas seguidas partirían del mismo estado anterior y se pisarían entre sí.
 */

export const TIPOS_CASO: { value: string; label: string }[] = [
  { value: "CM", label: "CM — carga muerta" },
  { value: "CV", label: "CV — carga viva" },
  { value: "CVi", label: "CVi — viento" },
  { value: "CS", label: "CS — sismo" },
  { value: "CE", label: "CE — suelo (peso y empuje)" },
  { value: "CL", label: "CL — líquidos" },
  { value: "CT", label: "CT — asentamientos, temperatura" },
];

const CON_NIVEL = new Set(["CVi", "CS"]);

function casoVacio(name: string, kind: string): LoadCaseInput {
  return { name, kind, level: CON_NIVEL.has(kind) ? "RESISTENCIA" : null, P_kN: 0, Mx_kNm: 0, My_kNm: 0, Hx_kN: 0, Hy_kN: 0 };
}

export function casosIniciales(): LoadCaseInput[] {
  return [casoVacio("CM", "CM"), casoVacio("CV", "CV")];
}

/** Punto de partida editable: servicio CM + CV y la ec. 9-1 de E.060 §9.2.1. */
export function definicionesIniciales(): CombinationDefinitionInput[] {
  return [
    { name: "S1", type: "SERVICIO", factors: { CM: 1.0, CV: 1.0 }, description: "Servicio" },
    { name: "U1", type: "FACTORIZADA", factors: { CM: 1.4, CV: 1.7 }, description: "E.060 §9.2.1, ec. 9-1" },
  ];
}

/** Casos con la misma estructura que `plantilla` y valores en cero (para una columna nueva). */
export function casosConEstructura(plantilla: LoadCaseInput[]): LoadCaseInput[] {
  return plantilla.map((c) => ({ ...c, P_kN: 0, Mx_kNm: 0, My_kNm: 0, Hx_kN: 0, Hy_kN: 0 }));
}

export function SelectorModoCargas({ porCasos, onChange }: { porCasos: boolean; onChange: (porCasos: boolean) => void }) {
  return (
    <div className="combo-field">
      <label title="Con casos y combinaciones el programa conoce la composición de cada combinación: factoriza el peso propio de la viga, puede reducir solo el sismo para el suelo y cuenta solo la carga muerta en la estabilidad (E.020 art. 20.1).">
        Modo de cargas<span className="hint-mark" aria-hidden="true">?</span>
      </label>
      <select value={porCasos ? "casos" : "directo"} onChange={(e) => onChange(e.target.value === "casos")}>
        <option value="directo">Combinaciones ya formadas</option>
        <option value="casos">Casos y combinaciones (E.060 §9.2)</option>
      </select>
    </div>
  );
}

interface Props {
  etiquetas: string[];
  casos: LoadCaseInput[][];
  definiciones: CombinationDefinitionInput[];
  onChange: (casos: LoadCaseInput[][], definiciones: CombinationDefinitionInput[]) => void;
  unidadFuerza: string;
  unidadMomento: string;
}

export default function LoadCasesEditor({ etiquetas, casos, definiciones, onChange, unidadFuerza, unidadMomento }: Props) {
  const estructura = casos[0] ?? [];

  const conEstructura = (i: number, patch: Partial<LoadCaseInput>) =>
    casos.map((col) =>
      col.map((c, j) => {
        if (j !== i) return c;
        const s = { ...c, ...patch };
        if (patch.kind !== undefined) s.level = CON_NIVEL.has(patch.kind) ? s.level ?? "RESISTENCIA" : null;
        return s;
      })
    );

  const renombrar = (i: number, nuevo: string) => {
    const viejo = estructura[i]?.name;
    const defs = definiciones.map((d) => {
      if (viejo === undefined || !(viejo in d.factors)) return d;
      const factors = { ...d.factors };
      factors[nuevo] = factors[viejo];
      delete factors[viejo];
      return { ...d, factors };
    });
    onChange(conEstructura(i, { name: nuevo }), defs);
  };

  const agregarCaso = () =>
    onChange(casos.map((col) => [...col, casoVacio(`C${estructura.length + 1}`, "CM")]), definiciones);

  const quitarCaso = (i: number) => {
    const nombre = estructura[i]?.name ?? "";
    const defs = definiciones.map((d) => {
      const factors = { ...d.factors };
      delete factors[nombre];
      return { ...d, factors };
    });
    onChange(casos.map((col) => col.filter((_, j) => j !== i)), defs);
  };

  const valor = (ci: number, i: number, campo: keyof LoadCaseInput, v: number) =>
    onChange(casos.map((col, k) => (k !== ci ? col : col.map((c, j) => (j === i ? { ...c, [campo]: v } : c)))), definiciones);

  const editarDefinicion = (k: number, patch: Partial<CombinationDefinitionInput>) =>
    onChange(casos, definiciones.map((d, j) => (j === k ? { ...d, ...patch } : d)));

  const factor = (k: number, caso: string, texto: string) => {
    const factors = { ...definiciones[k].factors };
    if (texto === "") delete factors[caso];
    else factors[caso] = Number(texto);
    editarDefinicion(k, { factors });
  };

  const agregarDefinicion = (type: "SERVICIO" | "FACTORIZADA") => {
    const n = definiciones.filter((d) => d.type === type).length + 1;
    onChange(casos, [...definiciones, { name: `${type === "SERVICIO" ? "S" : "U"}${n}`, type, factors: {} }]);
  };

  const campoNum = (etiqueta: string, v: number, on: (n: number) => void) => (
    <div className="combo-field">
      <label>{etiqueta}</label>
      <input type="number" step="any" value={v} onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))} />
    </div>
  );

  return (
    <div>
      <div className="note info">
        <strong>Casos sin factorizar y combinaciones declaradas por usted</strong>
        Los factores de cada combinación los declara usted: el programa no genera las combinaciones
        de E.060 §9.2. Para viento y sismo indique si la acción viene a nivel de servicio o de
        resistencia, porque la norma da ecuaciones distintas para cada caso.
      </div>

      <h4>Casos de carga ({estructura.length})</h4>
      {estructura.map((caso, i) => (
        <div className="combo-card" key={i}>
          <div className="combo-card-head">
            <input value={caso.name} onChange={(e) => renombrar(i, e.target.value)} aria-label="Nombre del caso" />
            <select value={caso.kind} onChange={(e) => onChange(conEstructura(i, { kind: e.target.value }), definiciones)}>
              {TIPOS_CASO.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            {CON_NIVEL.has(caso.kind) && (
              <select value={caso.level ?? "RESISTENCIA"} onChange={(e) => onChange(conEstructura(i, { level: e.target.value }), definiciones)}>
                <option value="RESISTENCIA">Nivel de resistencia</option>
                <option value="SERVICIO">Nivel de servicio</option>
              </select>
            )}
            <button className="tiny" onClick={() => quitarCaso(i)} title="Quitar caso">×</button>
          </div>
          {casos.map((col, ci) => {
            const c = col[i];
            if (!c) return null;
            return (
              <div className="combo-fields" key={ci}>
                {casos.length > 1 && (
                  <div className="combo-field">
                    <label>Columna</label>
                    <input value={etiquetas[ci] ?? ""} readOnly />
                  </div>
                )}
                {campoNum(`P (${unidadFuerza})`, c.P_kN, (n) => valor(ci, i, "P_kN", n))}
                {campoNum(`Mx (${unidadMomento})`, c.Mx_kNm, (n) => valor(ci, i, "Mx_kNm", n))}
                {campoNum(`My (${unidadMomento})`, c.My_kNm, (n) => valor(ci, i, "My_kNm", n))}
                {campoNum(`Hx (${unidadFuerza})`, c.Hx_kN, (n) => valor(ci, i, "Hx_kN", n))}
                {campoNum(`Hy (${unidadFuerza})`, c.Hy_kN, (n) => valor(ci, i, "Hy_kN", n))}
              </div>
            );
          })}
        </div>
      ))}
      <button className="tiny" onClick={agregarCaso}>+ caso de carga</button>

      <h4>Combinaciones ({definiciones.length})</h4>
      {definiciones.map((d, k) => (
        <div className="combo-card" key={k}>
          <div className="combo-card-head">
            <input value={d.name} onChange={(e) => editarDefinicion(k, { name: e.target.value })} aria-label="Nombre de la combinación" />
            <select value={d.type} onChange={(e) => editarDefinicion(k, { type: e.target.value as "SERVICIO" | "FACTORIZADA" })}>
              <option value="SERVICIO">Servicio</option>
              <option value="FACTORIZADA">Factorizada</option>
            </select>
            <button className="tiny" onClick={() => onChange(casos, definiciones.filter((_, j) => j !== k))} title="Quitar combinación">×</button>
          </div>
          <div className="combo-fields">
            {estructura.map((caso) => (
              <div className="combo-field" key={caso.name}>
                <label title="Deje vacío si el caso no interviene. Use signo negativo para el sentido contrario.">Factor {caso.name}</label>
                <input type="number" step="any" value={d.factors[caso.name] ?? ""} placeholder="—" onChange={(e) => factor(k, caso.name, e.target.value)} />
              </div>
            ))}
          </div>
        </div>
      ))}
      <button className="tiny" onClick={() => agregarDefinicion("SERVICIO")}>+ combinación de servicio</button>{" "}
      <button className="tiny" onClick={() => agregarDefinicion("FACTORIZADA")}>+ combinación factorizada</button>
    </div>
  );
}
