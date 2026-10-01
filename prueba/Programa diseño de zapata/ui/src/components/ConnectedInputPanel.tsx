import { useEffect } from "react";
import SiteLimitsPanel from "./SiteLimitsPanel";
import { conDimension, conForma } from "../lib/columna";
import type {
  ConnectedDesignRequest,
  ConnectedColumnInput,
  LoadCombinationInput,
  MaterialsInput,
  ReferenceData,
  SoilInput,
  UnitsInput,
} from "../lib/api";
import { coupleModeCompatible } from "../lib/api";
import { MaterialsPanel, ProjectPanel, SoilPanel, UnitsPanel } from "./SharedInputs";
import LoadCasesEditor, { SelectorModoCargas, casosIniciales, definicionesIniciales } from "./LoadCasesEditor";

/**
 * Panel de entrada de cimentación conectada.
 *
 * Tres decisiones que conviene conocer al leer este archivo:
 *
 * 1. TRES DECLARACIONES OBLIGATORIAS SIN VALOR POR DEFECTO. El modelo de análisis
 *    (TBD-C1), el reparto del par (TBD-C11) y el apoyo de la viga (TBD-C4) no los
 *    elige el programa: ninguna norma arbitra entre las opciones. El selector arranca
 *    vacío y el botón de calcular está deshabilitado hasta que el proyectista los
 *    declare. Poner un valor por defecto sería decidir por él sin decírselo.
 *
 * 2. LA ZAPATA DE LINDERO SE SITÚA POR SU BORDE, no por desplazamiento respecto del
 *    centro. Durante el barrido la longitud varía, y un desplazamiento constante
 *    dejaría de describir la misma condición de borde.
 *
 * 3. `max_systems` Y `same_depth_both_footings` SON EDITABLES Y VISIBLES. El tope no
 *    es un límite del producto sino un parámetro, y compartir peralte es una práctica
 *    constructiva que el programa no impone: por eso arranca desactivada.
 */

interface Props {
  value: ConnectedDesignRequest;
  onChange: (next: ConnectedDesignRequest) => void;
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

const MODELOS_ANALISIS = [
  { value: "", label: "— Sin declarar —" },
  { value: "ARTICULADO", label: "Articulado (viga biarticulada)" },
  { value: "CUERPO_RIGIDO", label: "Cuerpo rígido (conjunto gira como uno)" },
];

const MODOS_PAR = [
  { value: "", label: "— Sin declarar —" },
  { value: "EQUILIBRIO_EN_CIMENTACION", label: "El par se cierra en la cimentación" },
  { value: "PAR_PURO_EN_ZAPATA", label: "Par puro en la zapata (lo recoge el pórtico)" },
];

const MODOS_APOYO_VIGA = [
  { value: "", label: "— Sin declarar —" },
  { value: "SIN_APOYO", label: "Sin apoyo — salva el vano" },
  // APOYA_EN_SUELO se retiró el 2026-09-20 (decisión 5 sobre TBD-C4). El motor lo rechaza:
  // no modela la reacción del terreno bajo la viga, e ignorarla sobrestima ΔP y deja la
  // zapata interior menos cargada de lo que estaría. Ofrecer la opción para que el motor
  // la rechace sería ofrecer un callejón sin salida.
];

const DECLARACIONES_RIGIDEZ = [
  { value: "", label: "— Sin declarar (queda NO VERIFICADO) —" },
  {
    value: "DECLARADA_POR_PROYECTISTA",
    label: "Declaro que el modelo satisface E.060 §15.2.6",
  },
];

const MODOS_PESO_VIGA = [
  { value: "", label: "— Sin declarar —" },
  { value: "DESPRECIADO", label: "Despreciado" },
  { value: "EXPLICITO", label: "Explícito — entra en el equilibrio" },
  { value: "EN_CARGAS_DE_COLUMNA", label: "Ya incluido en las cargas de columna" },
];

export default function ConnectedInputPanel({
  value, onChange, onRun, running, reference, onUnitsChange, converting, proyecto, onListo,
}: Props) {
  const u = value.units;

  // Los mismos DTOs que la aislada y la combinada (`SharedInputs`). Antes del
  // 2026-09-23 esta pantalla no los exponía: la conectada calculaba siempre con el
  // qadm del ejemplo (250 kPa) y el usuario no tenía forma de verlo ni de cambiarlo.
  const setMateriales = (patch: Partial<MaterialsInput>) =>
    onChange({ ...value, materials: { ...value.materials, ...patch } });
  const setSuelo = (patch: Partial<SoilInput>) =>
    onChange({ ...value, soil: { ...value.soil, ...patch } });

  const hayHorizontales = [value.exterior, value.interior].some(
    (c) =>
      c.combinations.some((k) => k.Hx_kN !== 0 || k.Hy_kN !== 0) ||
      (c.load_cases ?? []).some((k) => k.Hx_kN !== 0 || k.Hy_kN !== 0),
  );

  const setColumna = (cual: "exterior" | "interior", patch: Partial<ConnectedColumnInput>) =>
    onChange({ ...value, [cual]: { ...value[cual], ...patch } });

  const setCombo = (
    cual: "exterior" | "interior",
    j: number,
    patch: Partial<LoadCombinationInput>
  ) =>
    onChange({
      ...value,
      [cual]: {
        ...value[cual],
        combinations: value[cual].combinations.map((k, kj) =>
          kj === j ? { ...k, ...patch } : k
        ),
      },
    });

  // Fase 10B: modo de cargas por casos, común a las dos columnas.
  const porCasos = value.combination_definitions != null;
  const combinacionesEjemplo = (P: number): LoadCombinationInput[] => [
    { name: "S1", type: "SERVICIO", P_kN: P, Mx_kNm: 0, My_kNm: 0, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false },
    { name: "U1", type: "FACTORIZADA", P_kN: 1.4 * P, Mx_kNm: 0, My_kNm: 0, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false },
  ];
  const cambiarModo = (aCasos: boolean) => {
    if (aCasos === porCasos) return;
    onChange({
      ...value,
      combination_definitions: aCasos ? definicionesIniciales() : null,
      exterior: { ...value.exterior, combinations: aCasos ? [] : combinacionesEjemplo(850), load_cases: aCasos ? casosIniciales() : null },
      interior: { ...value.interior, combinations: aCasos ? [] : combinacionesEjemplo(1100), load_cases: aCasos ? casosIniciales() : null },
    });
  };

  const setSearch = (patch: Partial<ConnectedDesignRequest["search"]>) =>
    onChange({ ...value, search: { ...value.search, ...patch } });

  const setBeam = (patch: Partial<ConnectedDesignRequest["beam"]>) =>
    onChange({ ...value, beam: { ...value.beam, ...patch } });

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

  // Fase 9a: con peso EXPLICITO la cota vertical de la viga es una declaración más, sin
  // valor por defecto.
  const pesoExplicito = value.beam.self_weight_mode === "EXPLICITO";
  const faltaCotaViga =
    pesoExplicito &&
    (value.beam.soffit_above_base_m === undefined || value.beam.soffit_above_base_m === null);

  const faltanDeclaraciones =
    !value.analysis_model ||
    !value.couple_transfer_mode ||
    !value.beam.support_mode ||
    !value.beam.self_weight_mode ||
    faltaCotaViga;

  // Fase 5A, D1: CUERPO_RIGIDO + PAR_PURO_EN_ZAPATA es incompatible y el motor lo rechaza.
  const combinacionIncompatible =
    !!value.analysis_model &&
    !!value.couple_transfer_mode &&
    !coupleModeCompatible(value.analysis_model, value.couple_transfer_mode);

  const listo = !(faltanDeclaraciones || combinacionIncompatible);
  useEffect(() => { onListo?.(listo); }, [listo, onListo]);

  const tarjetaColumna = (cual: "exterior" | "interior", titulo: string, nota: string) => {
    const c = value[cual];
    return (
      <div className="combo-card">
        <div className="combo-card-head">
          <input
            className="combo-name"
            value={c.label}
            onChange={(e) => setColumna(cual, { label: e.target.value })}
          />
          <select
            value={c.shape ?? "cuadrada"}
            onChange={(e) => setColumna(cual, conForma(c, e.target.value))}
          >
            <option value="cuadrada">Cuadrada</option>
            <option value="rectangular">Rectangular</option>
          </select>
          <span className="hint">{titulo}</span>
        </div>
        <div className="hint">{nota}</div>
        <div className="combo-fields">
          {num(`bx (${u.length})`, c.bx_m, (n) => setColumna(cual, conDimension(c, { bx_m: n })))}
          {num(`by (${u.length})`, c.by_m, (n) => setColumna(cual, conDimension(c, { by_m: n })))}
        </div>
        <div className="combo-fields">
          {(["x", "y"] as const).map((eje) => {
            const clave = eje === "x" ? "hook_type_x" : "hook_type_y";
            return (
              <div className="combo-field" key={eje}>
                <label title="Gancho estándar en ambos extremos de las barras de esa dirección. Nunca se asume: solo cuenta si lo declara.">
                  Gancho {eje.toUpperCase()}<span className="hint-mark" aria-hidden="true">?</span>
                </label>
                <select
                  value={c[clave] ?? "ninguno"}
                  onChange={(e) => setColumna(cual, { [clave]: e.target.value as "ninguno" | "90" | "180" })}
                >
                  <option value="ninguno">Sin gancho</option>
                  <option value="90">90°</option>
                  <option value="180">180°</option>
                </select>
              </div>
            );
          })}
        </div>
        {!porCasos && c.combinations.map((k, j) => (
          <div className="combo-fields" key={j}>
            <div className="combo-field">
              <label>{k.type === "SERVICIO" ? "Servicio" : "Factorizada"}</label>
              <input
                value={k.name}
                onChange={(e) => setCombo(cual, j, { name: e.target.value })}
              />
            </div>
            {num(`P (${u.force})`, k.P_kN, (n) => setCombo(cual, j, { P_kN: n }), undefined, 1)}
            {num(
              `Mx (${u.moment})`,
              k.Mx_kNm,
              (n) => setCombo(cual, j, { Mx_kNm: n }),
              "Momento que desplaza la resultante a lo largo del eje X (E.050 art. 28.1: ex = Mx/Q).",
              1
            )}
          </div>
        ))}
      </div>
    );
  };

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
        prefijo="conn-"
      />

      <div className="panel">
        <h2>Declaraciones obligatorias</h2>
        <div className="panel-body">
          <div className={`note ${faltanDeclaraciones ? "warn" : "info"}`}>
            <strong>
              {faltanDeclaraciones
                ? "Faltan declaraciones sin las que no se puede calcular"
                : "Por qué las elige usted y no el programa"}
            </strong>
            Ninguna norma arbitra entre estas opciones. Cambian el reparto de cargas y,
            con él, el resultado. El programa no elige por usted ni adopta un valor por
            defecto: se declaran, quedan registradas en la memoria de cálculo y son
            hipótesis de proyecto.
          </div>

          <div className="combo-field">
            <label title="Ninguna norma dice qué modelo corresponde. La premisa de rigidez que lo sostiene (TBD-C1) la exige E.060 §15.2.6 sin dar método: se responde con la declaración de rigidez de la viga.">
              Modelo de análisis<span className="hint-mark" aria-hidden="true">?</span>
            </label>
            <select
              value={value.analysis_model}
              onChange={(e) => onChange({ ...value, analysis_model: e.target.value })}
            >
              {MODELOS_ANALISIS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="combo-field">
            <label title="TBD-C11: dónde va la rama cercana del par que reparte la viga.">
              Reparto del par<span className="hint-mark" aria-hidden="true">?</span>
            </label>
            <select
              value={value.couple_transfer_mode}
              onChange={(e) => onChange({ ...value, couple_transfer_mode: e.target.value })}
            >
              {MODOS_PAR.map((o) => (
                <option
                  key={o.value}
                  value={o.value}
                  disabled={!!o.value && !coupleModeCompatible(value.analysis_model, o.value)}
                >
                  {o.label}
                  {o.value && !coupleModeCompatible(value.analysis_model, o.value)
                    ? " — incompatible con cuerpo rígido"
                    : ""}
                </option>
              ))}
            </select>
          </div>
          {combinacionIncompatible && (
            <div className="note fail">
              <strong>Combinación incompatible</strong>
              El par puro exige que la reacción de la zapata de lindero iguale la carga de su
              columna y que la carga no se conserve en la cimentación; el cuerpo rígido fija
              esa reacción por equilibrio global y conserva la carga. En CUERPO_RIGIDO solo
              es aplicable «El par se cierra en la cimentación».
            </div>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Columnas</h2>
        <div className="panel-body">
          {tarjetaColumna(
            "exterior",
            "Zapata de lindero",
            "Su cara queda al ras del límite de propiedad. La excentricidad que eso genera es lo que la viga reparte."
          )}
          {tarjetaColumna(
            "interior",
            "Zapata interior",
            "Concéntrica sobre su zapata. Recibe —o cede— la transferencia ΔP que llega por la viga."
          )}
          <SelectorModoCargas porCasos={porCasos} onChange={cambiarModo} />
          {porCasos && (
            <LoadCasesEditor
              etiquetas={[value.exterior.label, value.interior.label]}
              casos={[value.exterior.load_cases ?? [], value.interior.load_cases ?? []]}
              definiciones={value.combination_definitions ?? []}
              onChange={(casos, defs) =>
                onChange({
                  ...value,
                  combination_definitions: defs,
                  exterior: { ...value.exterior, load_cases: casos[0] },
                  interior: { ...value.interior, load_cases: casos[1] },
                })
              }
              unidadFuerza={u.force}
              unidadMomento={u.moment}
            />
          )}
          <div className="combo-fields">
            {num(
              `Distancia entre ejes (${u.length})`,
              value.axis_distance_m,
              (n) => onChange({ ...value, axis_distance_m: n }),
              "Separación entre los ejes de las dos columnas. La impone la estructura, no el barrido.",
              0.1
            )}
            {num(
              `Holgura al lindero (${u.length})`,
              value.anchor.face_clearance_m,
              (n) => onChange({ ...value, anchor: { ...value.anchor, face_clearance_m: n } }),
              "Distancia de la CARA de la columna al borde de la zapata. Cero = al ras del lindero.",
              0.05
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Viga de conexión</h2>
        <div className="panel-body">
          <div className="combo-fields">
            {num(`b (${u.length})`, value.beam.b_m, (n) => setBeam({ b_m: n }))}
            {num(`h (${u.length})`, value.beam.h_m, (n) => setBeam({ h_m: n }))}
            {num(
              `d (${u.length})`,
              value.beam.d_m,
              (n) => setBeam({ d_m: n }),
              "Peralte efectivo. Debe ser menor que h: la diferencia es el recubrimiento hasta el centroide del refuerzo.",
            )}
          </div>

          <div className="combo-field">
            <label title="TBD-C4: el motor solo resuelve la viga que salva el vano sin apoyo.">
              Apoyo de la viga<span className="hint-mark" aria-hidden="true">?</span>
            </label>
            <select
              value={value.beam.support_mode}
              onChange={(e) => setBeam({ support_mode: e.target.value })}
            >
              {MODOS_APOYO_VIGA.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="combo-field">
            <label title="TBD-C1: E.060 §15.2.6 exige evaluar la rigidez de la viga y del conjunto suelo-cimentación, pero no prescribe método ni umbral. El programa no puede responderla; usted sí, bajo su responsabilidad. Declararla NO convierte el resultado en conforme: solo levanta este bloqueo.">
              Rigidez de la viga (§15.2.6)<span className="hint-mark" aria-hidden="true">?</span>
            </label>
            <select
              value={value.beam.stiffness_declaration ?? ""}
              onChange={(e) =>
                setBeam({ stiffness_declaration: e.target.value || null })
              }
            >
              {DECLARACIONES_RIGIDEZ.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="combo-field">
            <label title="TBD-C5: dónde se contabiliza el peso propio de la viga.">
              Peso propio de la viga<span className="hint-mark" aria-hidden="true">?</span>
            </label>
            <select
              value={value.beam.self_weight_mode}
              onChange={(e) =>
                // z_b solo existe con EXPLICITO: al cambiar de modo se descarta.
                setBeam({
                  self_weight_mode: e.target.value,
                  soffit_above_base_m:
                    e.target.value === "EXPLICITO" ? value.beam.soffit_above_base_m ?? null : null,
                })
              }
            >
              {MODOS_PESO_VIGA.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {pesoExplicito && (
            <div className="combo-field">
              <label title="Fase 9a: altura del fondo de la viga sobre la base de cimentación. Sin valor por defecto: el peso que la viga agrega sobre cada zapata depende de ella.">
                Fondo de la viga sobre la base, z_b (m)
                <span className="hint-mark" aria-hidden="true">?</span>
              </label>
              <input
                type="number"
                step={0.05}
                min={0}
                value={value.beam.soffit_above_base_m ?? ""}
                onChange={(e) =>
                  setBeam({
                    soffit_above_base_m: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              {faltaCotaViga && (
                <div className="hint">
                  Obligatoria con peso propio explícito. 0 = fondo de la viga en la base de
                  las zapatas. El relleno sobre la viga en el vano no se incluye todavía.
                </div>
              )}
            </div>
          )}

          {value.beam.self_weight_mode === "EXPLICITO" && (
            <div className="combo-field">
              <label title="TBD-C13: factor de carga muerta del peso propio de la viga en las combinaciones factorizadas del modo directo. El motor no puede inferirlo de una combinacion ya formada.">
                Factor de CM del peso de la viga, f_CM
                <span className="hint-mark" aria-hidden="true">?</span>
              </label>
              <input
                type="number"
                step={0.05}
                min={0}
                value={value.beam.self_weight_dead_load_factor ?? ""}
                onChange={(e) =>
                  setBeam({
                    self_weight_dead_load_factor:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              <div className="hint">
                Solo para combinaciones <strong>factorizadas escritas a mano</strong>. Sin
                declararlo, el peso de la viga entra sin amplificar y la verificación del peso
                propio queda <strong>NO VERIFICADA</strong>. En el modo de cargas por casos no
                hace falta: el factor sale de la composición.
              </div>
            </div>
          )}

          <div className="hint">
            La sección de la viga es dato suyo, no eje de optimización: el
            predimensionamiento h ≈ L/7 es criterio de práctica y no tiene respaldo
            normativo, de modo que el programa no lo usa para elegir por usted.
          </div>
        </div>
      </div>

      <SiteLimitsPanel
        value={value.site_limits}
        onChange={(site_limits) => onChange({ ...value, site_limits })}
        unidad={u.length}
        campos={[
          { campo: "end_clearance_m", etiqueta: "Lindero tras la columna interior",
            ayuda: "De la cara de la columna interior al lindero del fondo, en la dirección de la viga." },
          { campo: "side_neg_clearance_m", etiqueta: "Lindero lateral (lado −)",
            ayuda: "De la cara lateral de las columnas al lindero del lado negativo, perpendicular a la viga." },
          { campo: "side_pos_clearance_m", etiqueta: "Lindero lateral (lado +)",
            ayuda: "De la cara lateral de las columnas al lindero del lado positivo, perpendicular a la viga." },
        ]}
        nota={
          <>
            El lindero de la zapata exterior es la <strong>holgura al lindero</strong> de la zapata
            de lindero, en «Columnas». El del fondo limita el largo de la zapata interior y los laterales, el ancho
            de las dos: el modelo de la conectada las supone <strong>centradas sobre su columna
            en la dirección transversal</strong>, así que no las corre hacia dentro del terreno.
          </>
        }
      />

      <div className="panel">
        <h2>Búsqueda de geometría</h2>
        <div className="panel-body">
          <div className="checkbox">
            <input
              id="conn-auto"
              type="checkbox"
              checked={!!value.search.auto_ranges}
              onChange={(e) => setSearch({ auto_ranges: e.target.checked })}
            />
            <label htmlFor="conn-auto">El programa elige los rangos de las dos zapatas (recomendado)</label>
          </div>
          {value.search.auto_ranges ? (
            <div className="auto-note">
              Los tamaños de las dos zapatas y el peralte se estiman con A ≈ P / q<sub>disponible</sub>
              de cada columna, con margen para el par y el sismo, y se recortan por los linderos.
              En este modo las dos zapatas comparten peralte y el tope de ternas se ajusta al
              tamaño de la malla, para que la búsqueda no quede truncada. Heurística de búsqueda:
              cada terna se verifica igual.
            </div>
          ) : (
          <>
          <div className="hint">
            Zapata de lindero — longitudinal es la dirección de la viga.
          </div>
          <div className="combo-fields">
            {num(`Long. mín (${u.length})`, value.search.ext_long_min_m, (n) => setSearch({ ext_long_min_m: n }))}
            {num(`Long. máx (${u.length})`, value.search.ext_long_max_m, (n) => setSearch({ ext_long_max_m: n }))}
            {num(`Paso (${u.length})`, value.search.ext_long_step_m, (n) => setSearch({ ext_long_step_m: n }))}
          </div>
          <div className="combo-fields">
            {num(`Transv. mín (${u.length})`, value.search.ext_transv_min_m, (n) => setSearch({ ext_transv_min_m: n }))}
            {num(`Transv. máx (${u.length})`, value.search.ext_transv_max_m, (n) => setSearch({ ext_transv_max_m: n }))}
            {num(`Paso (${u.length})`, value.search.ext_transv_step_m, (n) => setSearch({ ext_transv_step_m: n }))}
          </div>

          <div className="hint">Zapata interior.</div>
          <div className="combo-fields">
            {num(`Long. mín (${u.length})`, value.search.int_long_min_m, (n) => setSearch({ int_long_min_m: n }))}
            {num(`Long. máx (${u.length})`, value.search.int_long_max_m, (n) => setSearch({ int_long_max_m: n }))}
            {num(`Paso (${u.length})`, value.search.int_long_step_m, (n) => setSearch({ int_long_step_m: n }))}
          </div>
          <div className="combo-fields">
            {num(`Transv. mín (${u.length})`, value.search.int_transv_min_m, (n) => setSearch({ int_transv_min_m: n }))}
            {num(`Transv. máx (${u.length})`, value.search.int_transv_max_m, (n) => setSearch({ int_transv_max_m: n }))}
            {num(`Paso (${u.length})`, value.search.int_transv_step_m, (n) => setSearch({ int_transv_step_m: n }))}
          </div>

          <div className="hint">Peralte, común a las dos zapatas.</div>
          <div className="combo-fields">
            {num(`h mín (${u.length})`, value.search.h_min_m, (n) => setSearch({ h_min_m: n }))}
            {num(`h máx (${u.length})`, value.search.h_max_m, (n) => setSearch({ h_max_m: n }))}
            {num(`Paso h (${u.length})`, value.search.h_step_m, (n) => setSearch({ h_step_m: n }))}
          </div>
          </>
          )}
        </div>
      </div>

      {!value.search.auto_ranges && (
      <div className="panel">
        <h2>Alcance del barrido</h2>
        <div className="panel-body">
          <div className="combo-fields">
            {num(
              "Tope de sistemas",
              value.search.max_systems,
              (n) => setSearch({ max_systems: Math.max(1, Math.round(n)) }),
              "Cuántas ternas como máximo se evalúan. No es un límite del producto: súbalo si necesita explorar más.",
              100
            )}
          </div>
          <div className="hint">
            Valor actual: <strong>{value.search.max_systems}</strong> ternas. Si el rango
            solicitado lo supera, el resultado se marcará como truncado y verá la
            advertencia — el recorte nunca ocurre en silencio.
          </div>

          <div className="combo-field">
            <label>
              <input
                type="checkbox"
                checked={value.search.same_depth_both_footings}
                onChange={(e) => setSearch({ same_depth_both_footings: e.target.checked })}
              />{" "}
              Mismo peralte en las dos zapatas
            </label>
          </div>
          <div className="hint">
            {value.search.same_depth_both_footings ? (
              <>
                <strong>Activada.</strong> El espacio de búsqueda se reduce de n² a n
                parejas de peralte. Es una restricción suya y <em>puede dejar fuera el
                óptimo</em>.
              </>
            ) : (
              <>
                <strong>Desactivada</strong> (valor por defecto). Cada zapata busca su
                propio peralte. Igualarlos es una práctica constructiva habitual, pero el
                programa no la impone.
              </>
            )}
          </div>
        </div>
      </div>
      )}

      <button
        className="primary"
        onClick={onRun}
        disabled={running || faltanDeclaraciones || combinacionIncompatible}
      >
        {running ? "Calculando…" : "Calcular cimentación conectada"}
      </button>
      {faltanDeclaraciones && (
        <div className="hint">
          Declare el modelo de análisis, el reparto del par y los dos modos de la viga
          para poder calcular.
        </div>
      )}
    </div>
  );
}
