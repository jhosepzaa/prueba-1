import { useEffect, useState } from "react";
import { conDimension, conForma } from "../lib/columna";
import type { DesignRequest, LoadCombinationInput, ReferenceData, UnitsInput } from "../lib/api";
import LoadCasesEditor, { SelectorModoCargas, casosIniciales, definicionesIniciales } from "./LoadCasesEditor";
import { MaterialsPanel, Num, ProjectPanel, SoilPanel, UnitsPanel } from "./SharedInputs";

/**
 * Panel de entrada. Solo recoge datos y declara EN QUÉ UNIDAD vienen: la
 * conversión a SI la hace el motor (engine/units/unit_registry.py), igual que
 * todas las verificaciones normativas. Aquí no se calcula nada.
 */

interface Props {
  value: DesignRequest;
  onChange: (next: DesignRequest) => void;
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

export default function InputPanel({
  value, onChange, onRun, running, reference, onUnitsChange, converting, proyecto, onListo,
}: Props) {
  useEffect(() => { onListo?.(true); }, [onListo]);
  const set = <K extends keyof DesignRequest>(key: K, v: DesignRequest[K]) =>
    onChange({ ...value, [key]: v });

  const setSoil = (patch: Partial<DesignRequest["soil"]>) =>
    onChange({ ...value, soil: { ...value.soil, ...patch } });
  const setSearch = (patch: Partial<DesignRequest["search"]>) =>
    onChange({ ...value, search: { ...value.search, ...patch } });
  const setCol = (patch: Partial<DesignRequest["column"]>) =>
    onChange({ ...value, column: { ...value.column, ...patch } });
  const setMat = (patch: Partial<DesignRequest["materials"]>) =>
    onChange({ ...value, materials: { ...value.materials, ...patch } });
  const setW = (patch: Partial<DesignRequest["weights"]>) =>
    onChange({ ...value, weights: { ...value.weights, ...patch } });

  const u = value.units;

  const updateCombo = (i: number, patch: Partial<LoadCombinationInput>) =>
    set("combinations", value.combinations.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const addCombo = (type: "SERVICIO" | "FACTORIZADA") => {
    const n = value.combinations.filter((c) => c.type === type).length + 1;
    set("combinations", [
      ...value.combinations,
      {
        name: `${type === "SERVICIO" ? "S" : "U"}${n}`,
        type, P_kN: 0, Mx_kNm: 0, My_kNm: 0, Hx_kN: 0, Hy_kN: 0,
        includes_seismic_loads: false, includes_wind_loads: false,
      },
    ]);
  };
  const removeCombo = (i: number) =>
    set("combinations", value.combinations.filter((_, j) => j !== i));

  // Fase 10B: modo de cargas por casos. Las combinaciones directas se guardan para poder volver.
  const porCasos = value.load_cases != null;
  const [guardadas, setGuardadas] = useState<LoadCombinationInput[]>(value.combinations);
  const cambiarModo = (aCasos: boolean) => {
    if (aCasos === porCasos) return;
    if (aCasos) {
      setGuardadas(value.combinations);
      onChange({ ...value, combinations: [], load_cases: casosIniciales(), combination_definitions: definicionesIniciales() });
    } else {
      onChange({ ...value, combinations: guardadas, load_cases: null, combination_definitions: null });
    }
  };

  const service = value.combinations.filter((c) => c.type === "SERVICIO");
  const factored = value.combinations.filter((c) => c.type === "FACTORIZADA");
  const hasHorizontal =
    value.combinations.some((c) => c.Hx_kN !== 0 || c.Hy_kN !== 0) ||
    (value.load_cases ?? []).some((c) => c.Hx_kN !== 0 || c.Hy_kN !== 0);
  // Fase 10B: los FS tienen valor normativo por defecto (E.020 arts. 21 y 22); μ no.
  const missingStability = hasHorizontal && value.soil.mu_friction_soil_concrete === null;

  const autoRange =
    value.search.B_min_m === null || value.search.B_max_m === null ||
    value.search.L_min_m === null || value.search.L_max_m === null ||
    value.search.h_min_m === null || value.search.h_max_m === null;

  const comboCards = (list: LoadCombinationInput[]) =>
    list.map((c) => {
      const i = value.combinations.indexOf(c);
      const numField = (key: keyof LoadCombinationInput, label: string, hint?: string) => (
        <div className="combo-field" key={key}>
          <label title={hint}>
            {label}
            {hint ? <span className="hint-mark" aria-hidden="true">?</span> : null}
          </label>
          <input
            type="number"
            step="any"
            value={c[key] as number}
            onChange={(e) =>
              updateCombo(i, { [key]: e.target.value === "" ? 0 : Number(e.target.value) } as Partial<LoadCombinationInput>)
            }
          />
        </div>
      );
      return (
        <div className="combo-card" key={i}>
          <div className="combo-card-head">
            <input
              type="text"
              value={c.name}
              onChange={(e) => updateCombo(i, { name: e.target.value })}
              aria-label="Nombre de la combinación"
            />
            <select
              value={c.includes_seismic_loads ? "sismo" : "gravedad"}
              onChange={(e) => updateCombo(i, { includes_seismic_loads: e.target.value === "sismo" })}
            >
              <option value="gravedad">Gravedad</option>
              <option value="sismo">Sismo</option>
            </select>
            <button className="tiny" onClick={() => removeCombo(i)} title="Eliminar combinación">×</button>
          </div>
          <div className="combo-fields">
            {numField("P_kN", `P (${u.force})`)}
            {numField(
              "Mx_kNm",
              `Mx (${u.moment})`,
              "Momento que desplaza la resultante a lo largo del eje X, es decir el que flexiona la zapata en la dirección de B. Convención E.050 art. 28.1: ex = Mx/Q."
            )}
            {numField(
              "My_kNm",
              `My (${u.moment})`,
              "Momento que desplaza la resultante a lo largo del eje Y, es decir el que flexiona la zapata en la dirección de L. Convención E.050 art. 28.1: ey = My/Q."
            )}
            {numField("Hx_kN", `Hx (${u.force})`)}
            {numField("Hy_kN", `Hy (${u.force})`)}
          </div>
        </div>
      );
    });

  return (
    <div>
      <UnitsPanel
        units={value.units}
        reference={reference}
        onChange={onUnitsChange}
        converting={converting}
      />

      <ProjectPanel
        nombre={value.project_name}
        onNombre={(v) => set("project_name", v)}
        onGuardar={proyecto.guardar}
        onAbrir={proyecto.abrir}
        aviso={proyecto.aviso}
      />

      <div className="panel">
        <h2>Columna</h2>
        <div className="panel-body">
          <div className="field">
            <label>Sección</label>
            <select
              value={value.column.shape}
              onChange={(e) => {
                const shape = e.target.value;
                setCol(conForma(value.column, shape));
              }}
            >
              <option value="cuadrada">Cuadrada</option>
              <option value="rectangular">Rectangular</option>
            </select>
          </div>
          <div className="grid2">
            <Num
              label={`bx (${u.length})`}
              value={value.column.bx_m}
              onChange={(v) => setCol(conDimension(value.column, { bx_m: v ?? 0 }))}
            />
            <Num
              label={`by (${u.length})`}
              value={value.column.by_m}
              onChange={(v) => setCol(conDimension(value.column, { by_m: v ?? 0 }))}
            />
          </div>

          <h4>Posición sobre la zapata</h4>
          <div className="grid2">
            <Num
              label={`Desplaz. X (${u.length})`}
              hint="0 = concéntrica. Positivo hacia el borde de mayor x"
              value={value.column.offset_x_m ?? 0}
              onChange={(v) => setCol({ offset_x_m: v ?? 0 })}
            />
            <Num
              label={`Desplaz. Y (${u.length})`}
              hint="0 = concéntrica. Positivo hacia el borde de mayor y"
              value={value.column.offset_y_m ?? 0}
              onChange={(v) => setCol({ offset_y_m: v ?? 0 })}
            />
          </div>
          <div className="note info">
            <strong>Alcance actual</strong>
            El desplazamiento se mide desde el centroide de la zapata, no desde un borde:
            durante la búsqueda B y L varían, y una coordenada absoluta describiría una
            posición distinta en cada alternativa.
            <br />
            La columna debe conservar una holgura al borde de al menos <code>d/2</code> para
            que la sección crítica de punzonamiento se cierre por los cuatro lados
            (E.060 §11.12.1.2). Por debajo de esa holgura el perímetro se trunca y la
            alternativa se descarta indicándolo: ese caso —columna de borde o de esquina—
            corresponde a una fase posterior.
          </div>
        </div>
      </div>

      <MaterialsPanel materials={value.materials} units={u} onChange={setMat} />

      <SoilPanel
        soil={value.soil}
        units={u}
        onChange={setSoil}
        missingStability={missingStability}
        prefijo="aislada-"
      />

      <div className="panel">
        <h2>Combinaciones de carga</h2>
        <div className="panel-body">
          <div className="note info">
            <strong>Servicio y factorizadas se mantienen separadas</strong>
            Las de <em>servicio</em> dimensionan la zapata contra el suelo (E.060 §15.2, E.050 art. 17.1);
            las <em>factorizadas</em> diseñan el concreto. El programa nunca las mezcla.
          </div>

          <div className="note info">
            <strong>Convención de momentos (E.050 art. 28.1)</strong>
            <strong className="conv-inline">Mx</strong> es el momento que desplaza la resultante a lo
            largo del eje <strong>X</strong> — el que flexiona la zapata en la dirección de <em>B</em> —
            y cumple <code>ex = Mx / P</code>. <strong className="conv-inline">My</strong> hace lo propio
            a lo largo de <strong>Y</strong>, en la dirección de <em>L</em>, con <code>ey = My / P</code>.
            <br />
            No se trata del «momento alrededor del eje X»: mecánicamente, Mx es el momento
            <em> alrededor del eje Y</em>. Es la misma convención que emplean la E.050 y la
            bibliografía peruana.
          </div>

          <SelectorModoCargas porCasos={porCasos} onChange={cambiarModo} />

          {porCasos ? (
            <LoadCasesEditor
              etiquetas={["Columna"]}
              casos={[value.load_cases ?? []]}
              definiciones={value.combination_definitions ?? []}
              onChange={(casos, defs) => onChange({ ...value, load_cases: casos[0], combination_definitions: defs })}
              unidadFuerza={u.force}
              unidadMomento={u.moment}
            />
          ) : (
            <>
              <h4>Servicio ({service.length})</h4>
              {comboCards(service)}
              <button className="tiny" onClick={() => addCombo("SERVICIO")}>+ combinación de servicio</button>

              <h4>Factorizadas ({factored.length})</h4>
              {comboCards(factored)}
              <button className="tiny" onClick={() => addCombo("FACTORIZADA")}>+ combinación factorizada</button>
            </>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Búsqueda de geometría</h2>
        <div className="panel-body">
          {autoRange && (
            <div className="auto-note">
              <strong>Rango automático activo.</strong> Los límites que deje en blanco los estima el
              motor a partir de A ≈ P/q<sub>adm</sub>. Es solo una heurística para acotar dónde buscar:
              cada geometría se verifica con los mismos criterios normativos.
            </div>
          )}

          <h4>Ancho B — límites opcionales</h4>
          <div className="optional-row">
            <Num label={`mín (${u.length})`} placeholder="auto" value={value.search.B_min_m}
              onChange={(v) => setSearch({ B_min_m: v })} step={0.1} />
            <Num label={`máx (${u.length})`} placeholder="auto" value={value.search.B_max_m}
              onChange={(v) => setSearch({ B_max_m: v })} step={0.1} />
            <Num label={`incremento (${u.length})`} value={value.search.B_step_m}
              onChange={(v) => setSearch({ B_step_m: v ?? 0.1 })} step={0.05} />
          </div>

          <h4>Largo L — límites opcionales</h4>
          <div className="optional-row">
            <Num label={`mín (${u.length})`} placeholder="auto" value={value.search.L_min_m}
              onChange={(v) => setSearch({ L_min_m: v })} step={0.1} />
            <Num label={`máx (${u.length})`} placeholder="auto" value={value.search.L_max_m}
              onChange={(v) => setSearch({ L_max_m: v })} step={0.1} />
            <Num label={`incremento (${u.length})`} value={value.search.L_step_m}
              onChange={(v) => setSearch({ L_step_m: v ?? 0.1 })} step={0.05} />
          </div>

          <h4>Peralte h — límites opcionales</h4>
          <div className="optional-row">
            <Num label={`mín (${u.length})`} placeholder="auto" value={value.search.h_min_m}
              onChange={(v) => setSearch({ h_min_m: v })} step={0.05} />
            <Num label={`máx (${u.length})`} placeholder="auto" value={value.search.h_max_m}
              onChange={(v) => setSearch({ h_max_m: v })} step={0.05} />
            <Num label={`incremento (${u.length})`} value={value.search.h_step_m}
              onChange={(v) => setSearch({ h_step_m: v ?? 0.05 })} step={0.05} />
          </div>

          <div style={{ marginTop: 10 }}>
            <button
              className="tiny"
              onClick={() =>
                setSearch({
                  B_min_m: null, B_max_m: null, L_min_m: null,
                  L_max_m: null, h_min_m: null, h_max_m: null,
                })
              }
            >
              Dejar todos los límites en automático
            </button>
          </div>

          <div className="grid2" style={{ marginTop: 12 }}>
            <Num label="Relación L/B máxima" value={value.search.max_LB_ratio}
              onChange={(v) => setSearch({ max_LB_ratio: v ?? 1 })} step={0.1} />
            <Num label="Recubrimiento (mm)" hint="por defecto 70 (§7.7)"
              value={value.search.cover_override_mm} onChange={(v) => setSearch({ cover_override_mm: v })} step={5} />
          </div>
          <div className="grid2">
            <div className="field">
              <label>Gancho dirección X</label>
              <select value={value.search.hook_type_x} onChange={(e) => setSearch({ hook_type_x: e.target.value })}>
                <option value="ninguno">Sin gancho</option>
                <option value="90">Gancho 90°</option>
                <option value="180">Gancho 180°</option>
              </select>
            </div>
            <div className="field">
              <label>Gancho dirección Y</label>
              <select value={value.search.hook_type_y} onChange={(e) => setSearch({ hook_type_y: e.target.value })}>
                <option value="ninguno">Sin gancho</option>
                <option value="90">Gancho 90°</option>
                <option value="180">Gancho 180°</option>
              </select>
            </div>
          </div>
          <div className="hint">Los ganchos nunca se asumen: solo se consideran si Ud. los declara aquí.</div>
        </div>
      </div>

      <div className="panel">
        <h2>Criterio de optimización</h2>
        <div className="panel-body">
          <div className="grid2">
            <Num label="Peso volumen concreto" value={value.weights.w_concrete_volume}
              onChange={(v) => setW({ w_concrete_volume: v ?? 0 })} step={0.05} />
            <Num label="Peso masa de acero" value={value.weights.w_steel_mass}
              onChange={(v) => setW({ w_steel_mass: v ?? 0 })} step={0.05} />
          </div>
          <div className="grid2">
            <Num label="Peso dimensión máx." value={value.weights.w_max_dimension}
              onChange={(v) => setW({ w_max_dimension: v ?? 0 })} step={0.05} />
            <Num label="Peso constructibilidad" value={value.weights.w_constructive_complexity}
              onChange={(v) => setW({ w_constructive_complexity: v ?? 0 })} step={0.05} />
          </div>
          <div className="hint">
            No incluye costo monetario: requiere una base de precios configurable que aún no existe.
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <label>Interpretación de E.060 §15.7 (peralte mínimo)</label>
            <select value={value.min_depth_interpretation}
              onChange={(e) => set("min_depth_interpretation", e.target.value)}>
              <option value="EFFECTIVE_DEPTH">d ≥ 300 mm (peralte efectivo)</option>
              <option value="TOTAL_DEPTH">h ≥ 300 mm (peralte total)</option>
            </select>
            <div className="hint">Interpretación adoptada y documentada, no una certeza normativa.</div>
          </div>
        </div>
      </div>

      <button className="primary" onClick={onRun} disabled={running}>
        {running ? <><span className="spinner" />Calculando…</> : "Generar alternativas"}
      </button>
    </div>
  );
}
