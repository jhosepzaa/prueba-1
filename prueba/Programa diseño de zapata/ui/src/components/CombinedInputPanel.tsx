import { useEffect } from "react";
import SiteLimitsPanel from "./SiteLimitsPanel";
import { conDimension, conForma } from "../lib/columna";
import type {
  CombinedColumnInput,
  CombinedDesignRequest,
  LoadCombinationInput,
  MaterialsInput,
  ReferenceData,
  SoilInput,
  UnitsInput,
} from "../lib/api";
import { MaterialsPanel, ProjectPanel, SoilPanel, UnitsPanel } from "./SharedInputs";
import LoadCasesEditor, {
  SelectorModoCargas,
  casosConEstructura,
  casosIniciales,
  definicionesIniciales,
} from "./LoadCasesEditor";

/**
 * Panel de entrada de zapata combinada.
 *
 * Dos decisiones de diseño que conviene conocer al leer este archivo:
 *
 * 1. Las columnas se sitúan por su DISTANCIA A LA PRIMERA, no por desplazamiento
 *    respecto del centro. Durante el barrido la longitud varía, y un
 *    desplazamiento constante dejaría de describir la misma estructura.
 *
 * 2. El recubrimiento superior NO tiene valor por defecto. La tabla de E.060
 *    §7.7.1 no da uno único para esa cara —depende de la exposición—, así que se
 *    pide explícitamente y el cálculo se rechaza si falta.
 */

interface Props {
  value: CombinedDesignRequest;
  onChange: (next: CombinedDesignRequest) => void;
  onRun: () => void;
  running: boolean;
  reference: ReferenceData | null;
  /** Cambio de unidades: lo resuelve el motor, no este panel. */
  onUnitsChange: (units: UnitsInput) => void;
  converting: boolean;
  /**
   * Avisa si los datos permiten calcular: el botón de la cabecera usa exactamente la
   * misma condición que el botón de este panel, sin repetirla en otro sitio.
   */
  onListo?: (listo: boolean) => void;
  /** Guardar el proyecto en archivo y abrirlo; lo resuelve `App` (ver `lib/project.ts`). */
  proyecto: {
    guardar: () => void;
    abrir: (archivo: File) => void;
    aviso: string | null;
  };
}

const TOP_COVER_CASES: { value: string; label: string }[] = [
  { value: "", label: "— Sin declarar —" },
  { value: "contacto_suelo_barras_pequenas", label: "Enterrada, barras ≤ 5/8\" — 40 mm (§7.7.1 b)" },
  { value: "contacto_suelo_barras_grandes", label: "Enterrada, barras ≥ 3/4\" — 50 mm (§7.7.1 b)" },
  { value: "no_expuesto", label: "Protegida, no expuesta — 20 mm (§7.7.1 c)" },
  { value: "vaciado_contra_suelo", label: "Vaciada contra el suelo — 75 mm (§7.7.1 a)" },
];

function nuevaColumna(indice: number): CombinedColumnInput {
  return {
    label: `C${indice + 1}`,
    shape: "cuadrada",
    bx_m: 0.5,
    by_m: 0.5,
    distance_from_first_m: indice === 0 ? 0 : 5,
    transverse_offset_m: 0,
    combinations: [
      {
        name: "S1", type: "SERVICIO", P_kN: 800, Mx_kNm: 0, My_kNm: 0,
        Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false,
      },
      {
        name: "U1", type: "FACTORIZADA", P_kN: 1160, Mx_kNm: 0, My_kNm: 0,
        Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false,
      },
    ],
  };
}

export default function CombinedInputPanel({
  value, onChange, onRun, running, reference, onUnitsChange, converting, proyecto, onListo,
}: Props) {
  const u = value.units;

  // Materiales y suelo son los MISMOS DTOs que en la aislada (`SharedInputs`). Hasta
  // 2026-09-23 esta pantalla no los exponía y la combinada calculaba siempre con los
  // valores del ejemplo, sin que el usuario pudiera verlos: un dato de proyecto que no
  // se puede introducir es un resultado que no es del proyecto.
  const setMateriales = (patch: Partial<MaterialsInput>) =>
    onChange({ ...value, materials: { ...value.materials, ...patch } });
  const setSuelo = (patch: Partial<SoilInput>) =>
    onChange({ ...value, soil: { ...value.soil, ...patch } });

  const hayHorizontales = value.columns.some(
    (c) =>
      c.combinations.some((k) => k.Hx_kN !== 0 || k.Hy_kN !== 0) ||
      (c.load_cases ?? []).some((k) => k.Hx_kN !== 0 || k.Hy_kN !== 0),
  );

  const setColumna = (i: number, patch: Partial<CombinedColumnInput>) => {
    const columns = value.columns.map((c, j) => (j === i ? { ...c, ...patch } : c));
    onChange({ ...value, columns });
  };

  const setCombo = (i: number, j: number, patch: Partial<LoadCombinationInput>) => {
    const columns = value.columns.map((c, ci) =>
      ci === i
        ? { ...c, combinations: c.combinations.map((k, kj) => (kj === j ? { ...k, ...patch } : k)) }
        : c
    );
    onChange({ ...value, columns });
  };

  // Fase 10B: modo de cargas por casos, común a todas las columnas.
  const porCasos = value.combination_definitions != null;
  const cambiarModo = (aCasos: boolean) => {
    if (aCasos === porCasos) return;
    onChange({
      ...value,
      combination_definitions: aCasos ? definicionesIniciales() : null,
      columns: value.columns.map((c) => ({
        ...c,
        combinations: aCasos ? [] : nuevaColumna(0).combinations,
        load_cases: aCasos ? casosIniciales() : null,
      })),
    });
  };

  const addColumna = () => {
    const nueva = nuevaColumna(value.columns.length);
    if (porCasos) {
      nueva.combinations = [];
      nueva.load_cases = casosConEstructura(value.columns[0]?.load_cases ?? casosIniciales());
    }
    onChange({ ...value, columns: [...value.columns, nueva] });
  };

  const removeColumna = (i: number) => {
    if (value.columns.length <= 2) return; // §15.10.1: más de una columna
    onChange({ ...value, columns: value.columns.filter((_, j) => j !== i) });
  };

  const setSearch = (patch: Partial<CombinedDesignRequest["search"]>) =>
    onChange({ ...value, search: { ...value.search, ...patch } });

  const num = (
    label: string,
    v: number,
    on: (n: number) => void,
    hint?: string,
    step = 0.05
  ) => (
    <div className="combo-field">
      <label title={hint}>
        {label}
        {hint ? <span className="hint-mark" aria-hidden="true">?</span> : null}
      </label>
      <input
        type="number"
        step={step}
        value={v}
        onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    </div>
  );

  const sinRecubrimiento = !value.top_cover.case && !value.top_cover.explicit_mm;
  useEffect(() => { onListo?.(!sinRecubrimiento); }, [sinRecubrimiento, onListo]);

  return (
    <div className="input-panel">
      <UnitsPanel
        units={value.units}
        reference={reference}
        onChange={onUnitsChange}
        converting={converting}
      />

      <ProjectPanel
        nombre={value.project_name}
        onNombre={(v) => onChange({ ...value, project_name: v })}
        onGuardar={proyecto.guardar}
        onAbrir={proyecto.abrir}
        aviso={proyecto.aviso}
      />

      <MaterialsPanel materials={value.materials} units={u} onChange={setMateriales} />

      <SoilPanel
        soil={value.soil}
        units={u}
        onChange={setSuelo}
        missingStability={hayHorizontales && value.soil.mu_friction_soil_concrete === null}
        prefijo="comb-"
      />

      <div className="panel">
        <h2>Columnas sobre la zapata</h2>
        <div className="panel-body">
          <div className="note info">
            <strong>Cómo se sitúan las columnas</strong>
            Cada columna se ubica por su <em>distancia a la primera</em>, que es lo que impone
            la estructura y no cambia. La distancia del extremo de la zapata a esa primera
            columna se declara abajo: para una columna en límite de propiedad vale la mitad de
            su ancho, porque la cara queda al ras del lindero.
          </div>

          {value.columns.map((c, i) => (
            <div className="combo-card" key={i}>
              <div className="combo-card-head">
                <input
                  className="combo-name"
                  value={c.label}
                  onChange={(e) => setColumna(i, { label: e.target.value })}
                />
                <select
                  value={c.shape}
                  onChange={(e) => setColumna(i, conForma(c, e.target.value))}
                >
                  <option value="cuadrada">Cuadrada</option>
                  <option value="rectangular">Rectangular</option>
                </select>
                {value.columns.length > 2 && (
                  <button className="tiny" onClick={() => removeColumna(i)} title="Quitar columna">
                    ×
                  </button>
                )}
              </div>

              <div className="combo-fields">
                {num(`bx (${u.length})`, c.bx_m, (n) => setColumna(i, conDimension(c, { bx_m: n })))}
                {num(`by (${u.length})`, c.by_m, (n) => setColumna(i, conDimension(c, { by_m: n })))}
                {num(
                  `Dist. a C1 (${u.length})`,
                  c.distance_from_first_m,
                  (n) => setColumna(i, { distance_from_first_m: n }),
                  "Distancia entre ejes desde la primera columna. La primera vale 0.",
                  0.1
                )}
              </div>

              {!porCasos && c.combinations.map((k, j) => (
                <div className="combo-fields" key={j}>
                  <div className="combo-field">
                    <label>{k.type === "SERVICIO" ? "Servicio" : "Factorizada"}</label>
                    <input value={k.name} onChange={(e) => setCombo(i, j, { name: e.target.value })} />
                  </div>
                  {num(`P (${u.force})`, k.P_kN, (n) => setCombo(i, j, { P_kN: n }), undefined, 1)}
                  {num(
                    `Mx (${u.moment})`,
                    k.Mx_kNm,
                    (n) => setCombo(i, j, { Mx_kNm: n }),
                    "Momento que desplaza la resultante a lo largo del eje X (E.050 art. 28.1: ex = Mx/Q).",
                    1
                  )}
                  {num(
                    `My (${u.moment})`,
                    k.My_kNm,
                    (n) => setCombo(i, j, { My_kNm: n }),
                    "Momento que desplaza la resultante a lo largo del eje Y (ey = My/Q).",
                    1
                  )}
                </div>
              ))}
            </div>
          ))}

          <button className="secondary" onClick={addColumna}>
            + Añadir columna
          </button>

          <SelectorModoCargas porCasos={porCasos} onChange={cambiarModo} />
          {porCasos && (
            <LoadCasesEditor
              etiquetas={value.columns.map((c) => c.label)}
              casos={value.columns.map((c) => c.load_cases ?? [])}
              definiciones={value.combination_definitions ?? []}
              onChange={(casos, defs) =>
                onChange({
                  ...value,
                  combination_definitions: defs,
                  columns: value.columns.map((c, i) => ({ ...c, load_cases: casos[i] })),
                })
              }
              unidadFuerza={u.force}
              unidadMomento={u.moment}
            />
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Recubrimiento de la cara superior</h2>
        <div className="panel-body">
          <div className="combo-field">
            <label>Condición de exposición (E.060 §7.7.1)</label>
            <select
              value={value.top_cover.case ?? ""}
              onChange={(e) =>
                onChange({
                  ...value,
                  top_cover: { case: e.target.value || null, explicit_mm: null },
                })
              }
            >
              {TOP_COVER_CASES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className={`note ${sinRecubrimiento ? "warn" : "info"}`}>
            <strong>
              {sinRecubrimiento ? "Falta declararlo" : "Por qué hay que declararlo"}
            </strong>
            La cara inferior se vacía contra el suelo y le corresponden 75 mm. La superior{" "}
            <em>no</em>, y la tabla de §7.7.1 no da un valor único para ella: depende de si
            queda enterrada bajo relleno o protegida. Es un dato de proyecto, así que el
            programa no lo elige — sin declararlo, el cálculo se rechaza.
          </div>
        </div>
      </div>

      <SiteLimitsPanel
        value={value.site_limits}
        onChange={(site_limits) => onChange({ ...value, site_limits })}
        unidad={u.length}
        campos={[
          { campo: "start_clearance_m", etiqueta: "Lindero tras la primera columna",
            ayuda: "De la cara de la primera columna al lindero, en la dirección en que se alinean las columnas." },
          { campo: "end_clearance_m", etiqueta: "Lindero tras la última columna",
            ayuda: "De la cara de la última columna al lindero del otro extremo." },
          { campo: "side_neg_clearance_m", etiqueta: "Lindero lateral (lado −)",
            ayuda: "De la cara lateral de las columnas al lindero del lado negativo del eje transversal." },
          { campo: "side_pos_clearance_m", etiqueta: "Lindero lateral (lado +)",
            ayuda: "De la cara lateral de las columnas al lindero del lado positivo del eje transversal." },
        ]}
        nota={
          <>
            El programa coloca la zapata para centrar la resultante de la combinación
            permanente y la recorta contra estos linderos: con la columna al lindero, la
            zapata queda al ras. Una planta que no cabe en el terreno no se evalúa.
          </>
        }
      />

      <div className="panel">
        <h2>Búsqueda de geometría</h2>
        <div className="panel-body">
          <div className="checkbox">
            <input
              id="comb-auto"
              type="checkbox"
              checked={!!value.search.auto_ranges}
              onChange={(e) =>
                setSearch(
                  e.target.checked
                    ? { auto_ranges: true, first_column_edge_distance_m: null }
                    : { auto_ranges: false }
                )
              }
            />
            <label htmlFor="comb-auto">El programa elige los rangos y la posición de la zapata (recomendado)</label>
          </div>
          {value.search.auto_ranges ? (
            <div className="auto-note">
              Largo, ancho y peralte se estiman con A ≈ ΣP / q<sub>disponible</sub>, con margen
              para la excentricidad y el sismo, y se recortan por los linderos. Es una heurística
              de búsqueda: cada geometría se verifica igual. Si la mejor alternativa queda contra
              un borde del rango, el resultado lo avisa y puede ajustarlo en modo manual.
            </div>
          ) : (
          <>
          <div className="combo-fields">
            {num(`L mín (${u.length})`, value.search.length_min_m ?? 0, (n) =>
              setSearch({ length_min_m: n })
            )}
            {num(`L máx (${u.length})`, value.search.length_max_m ?? 0, (n) =>
              setSearch({ length_max_m: n })
            )}
            {num(`Paso L (${u.length})`, value.search.length_step_m, (n) =>
              setSearch({ length_step_m: n })
            )}
          </div>
          <div className="combo-fields">
            {num(`B mín (${u.length})`, value.search.width_min_m ?? 0, (n) =>
              setSearch({ width_min_m: n })
            )}
            {num(`B máx (${u.length})`, value.search.width_max_m ?? 0, (n) =>
              setSearch({ width_max_m: n })
            )}
            {num(`Paso B (${u.length})`, value.search.width_step_m, (n) =>
              setSearch({ width_step_m: n })
            )}
          </div>
          <div className="combo-fields">
            {num(`h mín (${u.length})`, value.search.h_min_m, (n) => setSearch({ h_min_m: n }))}
            {num(`h máx (${u.length})`, value.search.h_max_m, (n) => setSearch({ h_max_m: n }))}
            {num(`Paso h (${u.length})`, value.search.h_step_m, (n) => setSearch({ h_step_m: n }))}
          </div>
          <div className="checkbox">
            <input
              id="comb-pos"
              type="checkbox"
              checked={value.search.first_column_edge_distance_m === null}
              onChange={(e) => setSearch({ first_column_edge_distance_m: e.target.checked ? null : 0.25 })}
            />
            <label htmlFor="comb-pos">Posición de la zapata elegida por el programa</label>
          </div>
          {value.search.first_column_edge_distance_m !== null && (
            <div className="combo-fields">
              {num(
                `Extremo a C1 (${u.length})`,
                value.search.first_column_edge_distance_m,
                (n) => setSearch({ first_column_edge_distance_m: n }),
                "Distancia del borde de la zapata al eje de la primera columna. Para columna en límite de propiedad: la mitad de su ancho.",
                0.05
              )}
            </div>
          )}
          </>
          )}
        </div>
      </div>

      <button className="primary" onClick={onRun} disabled={running || sinRecubrimiento}>
        {running ? "Calculando…" : "Calcular zapata combinada"}
      </button>
      {sinRecubrimiento && (
        <div className="hint">Declare el recubrimiento superior para poder calcular.</div>
      )}
    </div>
  );
}
