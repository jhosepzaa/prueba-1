import { useCallback, useEffect, useMemo, useState } from "react";
import InputPanel from "./components/InputPanel";
import BeamInputPanel from "./components/BeamInputPanel";
import BeamResultsView from "./components/BeamResultsView";
import CombinedInputPanel from "./components/CombinedInputPanel";
import CombinedResultsView from "./components/CombinedResultsView";
import ConnectedInputPanel from "./components/ConnectedInputPanel";
import ConnectedResultsView from "./components/ConnectedResultsView";
import ResultsView from "./components/ResultsView";
import { CajonDatos, CimaHeader, DockResultados, PanelPropiedades, type EstadoDock } from "./components/Cima";
import FoundationViewer from "./components/FoundationViewer";
import {
  modeloAislada,
  modeloCombinada,
  modeloConectada,
  modeloViga,
  propiedadesAislada,
  propiedadesCombinada,
  propiedadesConectada,
  propiedadesViga,
} from "./viewer3d/datos";
import {
  fetchReference,
  runBeamDesign,
  runCombinedDesign,
  runConnectedDesign,
  runDesign,
  rewriteUnits,
  type BeamDesignRequest,
  type BeamDesignResponse,
  type CombinedDesignRequest,
  type CombinedDesignResponse,
  type ConnectedDesignRequest,
  type ConnectedDesignResponse,
  type DesignRequest,
  type DesignResponse,
  type ReferenceData,
  type Tipologia,
  type UnitsInput,
} from "./lib/api";
import { crearFormateador } from "./lib/units";
import { abrirProyecto, guardarProyecto, recordar, recuperar } from "./lib/project";
import { normalizarColumnas } from "./lib/columna";

/** Cómo se llama cada tipología en la pantalla. Un solo sitio. */
const NOMBRE_TIPOLOGIA: Record<Tipologia, string> = {
  aislada: "Zapata aislada",
  combinada: "Zapata combinada",
  conectada: "Cimentación conectada",
  viga: "Viga de conexión",
};

function comboPorDefecto(nombre: string, tipo: "SERVICIO" | "FACTORIZADA", P: number, M: number) {
  return {
    name: nombre, type: tipo, P_kN: P, Mx_kNm: M, My_kNm: 0,
    Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false,
  };
}

const DEFAULT_COMBINED: CombinedDesignRequest = {
  project_name: "Zapata combinada sin nombre",
  columns: [
    {
      label: "C1", shape: "cuadrada", bx_m: 0.5, by_m: 0.5,
      distance_from_first_m: 0, transverse_offset_m: 0,
      combinations: [
        comboPorDefecto("S1", "SERVICIO", 1078, 83),
        comboPorDefecto("U1", "FACTORIZADA", 1563, 120),
      ],
    },
    {
      label: "C2", shape: "cuadrada", bx_m: 0.5, by_m: 0.5,
      distance_from_first_m: 5, transverse_offset_m: 0,
      combinations: [
        comboPorDefecto("S1", "SERVICIO", 2157, -24.5),
        comboPorDefecto("U1", "FACTORIZADA", 3128, -35.5),
      ],
    },
  ],
  materials: { fc_MPa: 21, fy_MPa: 420, bar_type: "corrugada", concrete_unit_weight_kNm3: 24 },
  soil: {
    qadm_kPa: 150, pressure_basis: "BRUTA", gamma_kNm3: 18, Df_m: 1.5,
    mu_friction_soil_concrete: null, cohesion_kPa: null,
    FS_sliding_required: null, FS_overturning_required: null,
    use_effective_area_e050_art28: false, qadm_declared_for_effective_area: false,
    allow_temporary_increase_30pct: false, allow_seismic_reduction_80pct: false,
    founded_on_rock: false,
    source_notes: "",
  },
  search: {
    length_min_m: 6.8, length_max_m: 7.8, length_step_m: 0.2,
    width_min_m: 3.6, width_max_m: 4.4, width_step_m: 0.2,
    h_min_m: 0.65, h_max_m: 0.95, h_step_m: 0.05,
    // null (2026-09-28): la posición la decide el programa, centrando la resultante y
    // respetando los linderos. Los rangos de arriba solo se usan en modo manual.
    first_column_edge_distance_m: null,
    longitudinal_direction: "X",
    auto_ranges: true,
  },
  // Sin declarar a propósito: la tabla de §7.7.1 no da un valor único para la cara
  // superior, así que el usuario debe elegir antes de poder calcular.
  top_cover: { case: null, explicit_mm: null },
  units: {
    force: "kN", moment: "kN·m", pressure: "kPa",
    strength: "MPa", length: "m", unit_weight: "kN/m³",
  },
  top_n: 5,
};

/**
 * Cimentacion conectada por defecto.
 *
 * Las CUATRO declaraciones de modelacion quedan VACIAS a proposito: el modelo de
 * analisis (TBD-C1), el reparto del par (TBD-C11) y los dos modos de la viga (TBD-C4 y
 * TBD-C5) no los elige el programa, porque ninguna norma arbitra entre las opciones.
 * El panel deshabilita el boton de calcular hasta que el proyectista las declare.
 * Rellenarlas con un valor por defecto seria decidir por el sin decirselo.
 */
const DEFAULT_CONNECTED: ConnectedDesignRequest = {
  project_name: "Cimentacion conectada sin nombre",
  analysis_model: "",
  couple_transfer_mode: "",
  exterior: {
    label: "Z1", shape: "cuadrada", bx_m: 0.5, by_m: 0.5,
    combinations: [
      comboPorDefecto("S1", "SERVICIO", 850, 0),
      comboPorDefecto("U1", "FACTORIZADA", 1190, 0),
    ],
  },
  interior: {
    label: "Z2", shape: "cuadrada", bx_m: 0.5, by_m: 0.5,
    combinations: [
      comboPorDefecto("S1", "SERVICIO", 1100, 0),
      comboPorDefecto("U1", "FACTORIZADA", 1540, 0),
    ],
  },
  anchor: { edge: "X_MIN", face_clearance_m: 0 },
  beam: { b_m: 0.35, h_m: 1.2, d_m: 1.1, support_mode: "", self_weight_mode: "",
    stiffness_declaration: null,
          concrete_unit_weight_kNm3: 24 },
  axis_distance_m: 6,
  longitudinal_axis: "X",
  materials: { fc_MPa: 21, fy_MPa: 420, bar_type: "corrugada", concrete_unit_weight_kNm3: 24 },
  soil: {
    qadm_kPa: 250, pressure_basis: "BRUTA", gamma_kNm3: 18, Df_m: 1.5,
    mu_friction_soil_concrete: null, cohesion_kPa: null,
    FS_sliding_required: null, FS_overturning_required: null,
    use_effective_area_e050_art28: false, qadm_declared_for_effective_area: false,
    allow_temporary_increase_30pct: false, allow_seismic_reduction_80pct: false,
    founded_on_rock: false,
    source_notes: "",
  },
  search: {
    ext_long_min_m: 2.0, ext_long_max_m: 2.8, ext_long_step_m: 0.4,
    ext_transv_min_m: 2.4, ext_transv_max_m: 2.8, ext_transv_step_m: 0.4,
    int_long_min_m: 2.2, int_long_max_m: 2.6, int_long_step_m: 0.4,
    int_transv_min_m: 2.2, int_transv_max_m: 2.6, int_transv_step_m: 0.4,
    h_min_m: 0.6, h_max_m: 1.0, h_step_m: 0.2,
    // Editable, y a la vista en el panel: no es un limite del producto.
    max_systems: 1500,
    // Falso por defecto: igualar peraltes es practica constructiva, no supuesto
    // del programa, y puede dejar fuera el optimo.
    same_depth_both_footings: false,
    // 2026-09-28: el programa estima los rangos; los de arriba son el modo manual.
    auto_ranges: true,
  },
  units: {
    force: "kN", moment: "kN·m", pressure: "kPa",
    strength: "MPa", length: "m", unit_weight: "kN/m³",
  },
  top_n: 5,
};

/**
 * Viga de conexion por defecto. Los momentos y el cortante corresponden al problema 1
 * de Aragon §3.6, que se mantiene como benchmark permanente del motor.
 *
 * El perfil de suelo y la zona sismica se dejan SIN DECLARAR a proposito: E.030 art.
 * 65.1 se dispara con (S3 o S4) Y (Zona 3 o 4), y suponerlos ocultaria al usuario que
 * esa condicion no se comprobo.
 */
const DEFAULT_BEAM: BeamDesignRequest = {
  project_name: "Viga de conexion VC-1",
  b_m: 0.35,
  h_m: 1.2,
  d_m: 1.1,
  clear_span_m: 5.5,
  Mu_negative_kNm: 1379,
  Mu_positive_kNm: 300,
  Vu_kN: 220,
  sum_Pu_kN: 1240,
  longitudinal_db_mm: 25.4,
  stirrup_diameter_mm: 9.525,
  n_legs: 2,
  fyt_MPa: null,
  materials: { fc_MPa: 21, fy_MPa: 420, bar_type: "corrugada", concrete_unit_weight_kNm3: 24 },
  soil: {
    qadm_kPa: 150, pressure_basis: "BRUTA", gamma_kNm3: 18, Df_m: 1.5,
    mu_friction_soil_concrete: null, cohesion_kPa: null,
    FS_sliding_required: null, FS_overturning_required: null,
    use_effective_area_e050_art28: false, qadm_declared_for_effective_area: false,
    allow_temporary_increase_30pct: false, allow_seismic_reduction_80pct: false,
    founded_on_rock: false,
    source_notes: "",
  },
  seismic: {
    soil_profile: null,
    seismic_zone: null,
    part_of_lateral_force_system: false,
    lateral_system: null,
  },
  units: {
    force: "kN", moment: "kN·m", pressure: "kPa",
    strength: "MPa", length: "m", unit_weight: "kN/m³",
  },
};

const DEFAULT_REQUEST: DesignRequest = {
  project_name: "Zapata aislada — ejemplo",
  column: { shape: "cuadrada", bx_m: 0.4, by_m: 0.4 },
  materials: { fc_MPa: 21, fy_MPa: 420, bar_type: "corrugada", concrete_unit_weight_kNm3: 24 },
  soil: {
    qadm_kPa: 150,
    pressure_basis: "BRUTA",
    gamma_kNm3: 18,
    Df_m: 1.2,
    mu_friction_soil_concrete: null,
    cohesion_kPa: null,
    FS_sliding_required: null,
    FS_overturning_required: null,
    use_effective_area_e050_art28: false, qadm_declared_for_effective_area: false,
    allow_temporary_increase_30pct: false,
    allow_seismic_reduction_80pct: false,
    founded_on_rock: false,
    source_notes: "",
  },
  search: {
    // null = automatico. Por defecto se dejan libres B, L y h.
    B_min_m: null, B_max_m: null, B_step_m: 0.1,
    L_min_m: null, L_max_m: null, L_step_m: 0.1,
    max_LB_ratio: 2.0,
    h_min_m: null, h_max_m: null, h_step_m: 0.05,
    cover_override_mm: null,
    hook_type_x: "ninguno", hook_type_y: "ninguno",
  },
  units: {
    force: "kN", moment: "kN·m", pressure: "kPa",
    strength: "MPa", length: "m", unit_weight: "kN/m³",
  },
  weights: {
    w_concrete_volume: 0.35, w_steel_mass: 0.3,
    w_max_dimension: 0.2, w_constructive_complexity: 0.15,
  },
  combinations: [
    { name: "S1", type: "SERVICIO", P_kN: 450, Mx_kNm: 40, My_kNm: 25, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false },
    { name: "S2", type: "SERVICIO", P_kN: 380, Mx_kNm: 75, My_kNm: 20, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: true, includes_wind_loads: false },
    { name: "U1", type: "FACTORIZADA", P_kN: 630, Mx_kNm: 56, My_kNm: 35, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: false, includes_wind_loads: false },
    { name: "U2", type: "FACTORIZADA", P_kN: 520, Mx_kNm: 110, My_kNm: 28, Hx_kN: 0, Hy_kN: 0, includes_seismic_loads: true, includes_wind_loads: false },
  ],
  top_n: 5,
  min_depth_interpretation: "EFFECTIVE_DEPTH",
};

export default function App() {
  const [request, setRequest] = useState<DesignRequest>(() => recuperar<DesignRequest>("aislada") ?? DEFAULT_REQUEST);
  const [result, setResult] = useState<DesignResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [reference, setReference] = useState<ReferenceData | null>(null);

  // Tipología activa. La aislada y la combinada tienen modelos de entrada distintos
  // —una columna frente a N— así que cada una lleva su propio estado en vez de
  // forzarlas a compartir uno.
  const [tipologia, setTipologia] = useState<
    "aislada" | "combinada" | "conectada" | "viga"
  >("aislada");
  const [combRequest, setCombRequest] = useState<CombinedDesignRequest>(() => recuperar<CombinedDesignRequest>("combinada") ?? DEFAULT_COMBINED);
  const [combResult, setCombResult] = useState<CombinedDesignResponse | null>(null);
  const [connRequest, setConnRequest] = useState<ConnectedDesignRequest>(() => recuperar<ConnectedDesignRequest>("conectada") ?? DEFAULT_CONNECTED);
  const [connResult, setConnResult] = useState<ConnectedDesignResponse | null>(null);
  const [beamRequest, setBeamRequest] = useState<BeamDesignRequest>(() => recuperar<BeamDesignRequest>("viga") ?? DEFAULT_BEAM);
  const [beamResult, setBeamResult] = useState<BeamDesignResponse | null>(null);

  // Cambio de unidades (2026-09-23). La interfaz NO convierte: manda la peticion al
  // motor y la recibe reescrita, de modo que el valor fisico del dato no cambia. Si la
  // conversion falla, la peticion se queda como estaba —incluidas las unidades—: cambiar
  // el rotulo sin convertir el numero seria cambiar el dato en silencio.
  const [convirtiendo, setConvirtiendo] = useState(false);

  // --- Guardar y abrir proyectos (2026-09-24) -------------------------------
  // Un proyecto es la PETICIÓN de una tipología: lo que el motor necesita para
  // reproducir el cálculo. No se guardan los resultados, que se recalculan al abrirlo;
  // así lo que se ve corresponde siempre al motor de hoy. Ver `lib/project.ts`.
  const [avisoProyecto, setAvisoProyecto] = useState<string | null>(null);
  // --- Armazón CIMA ---
  const [datosAbiertos, setDatosAbiertos] = useState(true);
  const [dock, setDock] = useState<EstadoDock>("cerrado");
  const [selAislada, setSelAislada] = useState(0);
  // Cada panel dice si sus datos permiten calcular; el botón de la cabecera lo respeta.
  const [listo, setListo] = useState<Record<Tipologia, boolean>>({
    aislada: true, combinada: false, conectada: false, viga: true,
  });
  const listoPara = useCallback(
    (t: Tipologia) => (v: boolean) => setListo((l) => (l[t] === v ? l : { ...l, [t]: v })),
    [],
  );
  const listoAislada = useMemo(() => listoPara("aislada"), [listoPara]);
  const listoCombinada = useMemo(() => listoPara("combinada"), [listoPara]);
  const listoConectada = useMemo(() => listoPara("conectada"), [listoPara]);
  const listoViga = useMemo(() => listoPara("viga"), [listoPara]);

  const peticionDe: Record<Tipologia, { units: UnitsInput; project_name: string }> = {
    aislada: request,
    combinada: combRequest,
    conectada: connRequest,
    viga: beamRequest,
  };
  const aplicarPeticion: Record<Tipologia, (p: never) => void> = {
    aislada: setRequest as (p: never) => void,
    combinada: setCombRequest as (p: never) => void,
    conectada: setConnRequest as (p: never) => void,
    viga: setBeamRequest as (p: never) => void,
  };

  const proyectoDe = (tipo: Tipologia) => ({
    guardar: () => {
      setAvisoProyecto(null);
      guardarProyecto(tipo, peticionDe[tipo]);
    },
    abrir: async (archivo: File) => {
      setAvisoProyecto(null);
      try {
        const { tipologia: leida, peticion } = await abrirProyecto(archivo);
        aplicarPeticion[leida](peticion as never);
        // El archivo manda: si es de otra tipología, se abre en la suya en vez de
        // rechazarlo. Abrir un proyecto es abrir ESE proyecto.
        if (leida !== tipologia) setTipologia(leida);
      } catch (e) {
        setAvisoProyecto(e instanceof Error ? e.message : String(e));
      }
    },
    aviso: avisoProyecto,
  });

  const cambiarUnidades = async <T extends { units: UnitsInput }>(
    tipo: Tipologia,
    actual: T,
    aplicar: (siguiente: T) => void,
    nuevas: UnitsInput,
  ) => {
    setConvirtiendo(true);
    setError(null);
    try {
      aplicar(await rewriteUnits(tipo, actual, nuevas));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConvirtiendo(false);
    }
  };

  const runCombinada = async () => {
    setRunning(true);
    setError(null);
    try {
      setCombResult(await runCombinedDesign(normalizarColumnas(combRequest)));
    } catch (e) {
      setCombResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const runConectada = async () => {
    setRunning(true);
    setError(null);
    try {
      // La respuesta se muestra SIEMPRE, aunque no haya ninguna alternativa aceptada
      // o todas esten NO VERIFICADAS: ese es justamente el estado que el usuario
      // necesita leer, y tratarlo como error lo ocultaria.
      setConnResult(await runConnectedDesign(normalizarColumnas(connRequest)));
    } catch (e) {
      setConnResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const runViga = async () => {
    setRunning(true);
    setError(null);
    try {
      setBeamResult(await runBeamDesign(beamRequest));
    } catch (e) {
      setBeamResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  // Un formateador por tipología: cada una lleva sus propias unidades, igual que su
  // propia petición. Solo decide en qué unidad se ESCRIBE un resultado que el motor
  // entrega en SI; no recalcula nada.
  const fmtAislada = useMemo(() => crearFormateador(request.units, reference), [request.units, reference]);
  const fmtCombinada = useMemo(() => crearFormateador(combRequest.units, reference), [combRequest.units, reference]);
  const fmtConectada = useMemo(() => crearFormateador(connRequest.units, reference), [connRequest.units, reference]);
  const fmtViga = useMemo(() => crearFormateador(beamRequest.units, reference), [beamRequest.units, reference]);

  useEffect(() => {
    fetchReference()
      .then(setReference)
      .catch(() => setReference(null));
  }, []);

  // Lo último escrito en cada tipología se recupera en el ESTADO INICIAL de cada petición
  // (más arriba), no en un efecto: un efecto de montaje corre dos veces en modo estricto y
  // el segundo leía lo que `recordar` ya había pisado con el ejemplo. Si no hay nada
  // guardado —o el navegador no lo permite— se queda el ejemplo, como antes.

  useEffect(() => { recordar("aislada", request); }, [request]);
  useEffect(() => { recordar("combinada", combRequest); }, [combRequest]);
  useEffect(() => { recordar("conectada", connRequest); }, [connRequest]);
  useEffect(() => { recordar("viga", beamRequest); }, [beamRequest]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await runDesign(normalizarColumnas(request)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setRunning(false);
    }
  };

  const resultadoDe: Record<Tipologia, unknown> = {
    aislada: result, combinada: combResult, conectada: connResult, viga: beamResult,
  };
  const unidadesActivas = peticionDe[tipologia].units;
  const proyectoActivo = proyectoDe(tipologia);

  // La pestaña del navegador dice qué tipología está abierta.
  useEffect(() => { document.title = `CIMA · ${NOMBRE_TIPOLOGIA[tipologia]}`; }, [tipologia]);

  // Cada resultado nuevo abre el dock a media altura; en la aislada, además, se vuelve a
  // la alternativa recomendada.
  // Donde el cajón flota sobre el visor (≤ 1500 px, ver styles.css) se cierra para que
  // el modelo recién calculado quede a la vista.
  const alLlegarResultado = useCallback(() => {
    setDock("medio");
    if (window.matchMedia("(max-width: 1500px) and (min-width: 901px)").matches) setDatosAbiertos(false);
  }, []);
  useEffect(() => { if (result) { setSelAislada(0); alLlegarResultado(); } }, [result, alLlegarResultado]);
  useEffect(() => { if (combResult) alLlegarResultado(); }, [combResult, alLlegarResultado]);
  useEffect(() => { if (connResult) alLlegarResultado(); }, [connResult, alLlegarResultado]);
  useEffect(() => { if (beamResult) alLlegarResultado(); }, [beamResult, alLlegarResultado]);

  // Modelo del visor y panel de propiedades de la tipología activa. Solo adaptan datos
  // del motor y entradas del usuario: `viewer3d/datos.ts`.
  const modelo = useMemo(() => {
    switch (tipologia) {
      case "aislada": return modeloAislada(request, result, selAislada, fmtAislada);
      case "combinada": return modeloCombinada(combRequest, combResult, fmtCombinada);
      case "conectada": return modeloConectada(connRequest, connResult, fmtConectada);
      default: return modeloViga(beamRequest, beamResult, fmtViga);
    }
  }, [tipologia, request, result, selAislada, fmtAislada, combRequest, combResult, fmtCombinada,
    connRequest, connResult, fmtConectada, beamRequest, beamResult, fmtViga]);

  const propiedades = useMemo(() => {
    switch (tipologia) {
      case "aislada": return propiedadesAislada(request, result, selAislada, fmtAislada);
      case "combinada": return propiedadesCombinada(combRequest, combResult, fmtCombinada);
      case "conectada": return propiedadesConectada(connRequest, connResult, fmtConectada);
      default: return propiedadesViga(beamRequest, beamResult, fmtViga);
    }
  }, [tipologia, request, result, selAislada, fmtAislada, combRequest, combResult, fmtCombinada,
    connRequest, connResult, fmtConectada, beamRequest, beamResult, fmtViga]);

  const calcular: Record<Tipologia, () => void> = {
    aislada: run, combinada: runCombinada, conectada: runConectada, viga: runViga,
  };
  const TEXTO_CALCULAR: Record<Tipologia, string> = {
    aislada: "Generar alternativas",
    combinada: "Calcular",
    conectada: "Calcular",
    viga: "Diseñar viga",
  };

  const resumenDock = (() => {
    if (running) return <span>Calculando…</span>;
    if (tipologia === "aislada" && result) {
      return (
        <span>
          <b>{result.summary.n_evaluated}</b> geometrías · <b>{result.summary.n_valid}</b> alternativas ·
          mejor <b>{result.top[0]?.id ?? "—"}</b>
        </span>
      );
    }
    if (tipologia === "combinada" && combResult) {
      return (
        <span>
          <b>{combResult.evaluated_count}</b> evaluadas · <b>{combResult.accepted_count ?? combResult.top.length}</b> aceptadas ·
          mejor <b>{combResult.top[0]?.id ?? "—"}</b>
        </span>
      );
    }
    if (tipologia === "conectada" && connResult) {
      return (
        <span>
          <b>{connResult.evaluated_count}</b> ternas · <b>{connResult.accepted_count}</b> aceptadas
          {connResult.truncated ? " · búsqueda truncada" : ""}
        </span>
      );
    }
    if (tipologia === "viga" && beamResult) return <span>Estado <b>{beamResult.status}</b></span>;
    if (error) return <span className="apagado">El último cálculo no se completó</span>;
    return <span className="apagado">Sin resultados · complete los datos y pulse {TEXTO_CALCULAR[tipologia]}</span>;
  })();

  // Nombre de archivo para exportar el modelo: el del proyecto, sin acentos ni símbolos.
  const nombreArchivo =
    (peticionDe[tipologia].project_name || "cimentacion")
      .normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^\w.-]+/g, "_").slice(0, 60)
    + "_" + tipologia;

  return (
    <div className={`cima ${datosAbiertos ? "con-datos" : ""}`}>
      <CimaHeader
        proyecto={peticionDe[tipologia].project_name}
        tipologia={tipologia}
        onTipologia={setTipologia}
        unidades={`${unidadesActivas.force} · ${unidadesActivas.length} · ${unidadesActivas.pressure} · ${unidadesActivas.strength}`}
        datosAbiertos={datosAbiertos}
        onDatos={() => setDatosAbiertos((v) => !v)}
        onGuardar={proyectoActivo.guardar}
        onAbrir={proyectoActivo.abrir}
        onCalcular={calcular[tipologia]}
        puedeCalcular={listo[tipologia]}
        calculando={running || convirtiendo}
        textoCalcular={TEXTO_CALCULAR[tipologia]}
        conResultado={{
          aislada: resultadoDe.aislada != null, combinada: resultadoDe.combinada != null,
          conectada: resultadoDe.conectada != null, viga: resultadoDe.viga != null,
        }}
      />

      <CajonDatos abierto={datosAbiertos} onCerrar={() => setDatosAbiertos(false)}>

          {tipologia === "aislada" && (
            <InputPanel
              value={request}
              onChange={setRequest}
              onRun={run}
              running={running}
              reference={reference}
              onUnitsChange={(u) => cambiarUnidades("aislada", request, setRequest, u)}
              converting={convirtiendo}
              proyecto={proyectoDe("aislada")}
              onListo={listoAislada}
            />
          )}
          {tipologia === "combinada" && (
            <CombinedInputPanel
              value={combRequest}
              onChange={setCombRequest}
              onRun={runCombinada}
              running={running}
              reference={reference}
              onUnitsChange={(u) => cambiarUnidades("combinada", combRequest, setCombRequest, u)}
              converting={convirtiendo}
              proyecto={proyectoDe("combinada")}
              onListo={listoCombinada}
            />
          )}
          {tipologia === "conectada" && (
            <ConnectedInputPanel
              value={connRequest}
              onChange={setConnRequest}
              onRun={runConectada}
              running={running}
              reference={reference}
              onUnitsChange={(u) => cambiarUnidades("conectada", connRequest, setConnRequest, u)}
              converting={convirtiendo}
              proyecto={proyectoDe("conectada")}
              onListo={listoConectada}
            />
          )}
          {tipologia === "viga" && (
            <BeamInputPanel
              value={beamRequest}
              onChange={setBeamRequest}
              onRun={runViga}
              running={running}
              reference={reference}
              onUnitsChange={(u) => cambiarUnidades("viga", beamRequest, setBeamRequest, u)}
              converting={convirtiendo}
              proyecto={proyectoDe("viga")}
              onListo={listoViga}
            />
          )}
      </CajonDatos>

      <main className="cima-centro">
        <FoundationViewer modelo={modelo} nombreArchivo={nombreArchivo} />

        <DockResultados estado={dock} onEstado={setDock} resumen={resumenDock}>
          {error && (
            <div className="note fail">
              <strong>No se pudo completar el cálculo</strong>
              {error}
            </div>
          )}

          {tipologia === "viga" && !beamResult && !error && (
            <div className="panel">
              <h2>Viga de conexión entre zapatas</h2>
              <div className="panel-body">
                <p>
                  Complete la sección, la luz libre y las solicitaciones, y pulse{" "}
                  <strong>Diseñar viga</strong>. El motor verifica la dimensión
                  mínima de E.060 §21.12.3.2, el acero longitudinal y su mínimo de §10.5, el
                  cortante y los estribos de §11.5, el confinamiento cerrado de §21.12.3.2 y,
                  cuando corresponde, la fuerza axial de E.030 art. 65.1 con su interacción
                  axial-flexión completa.
                </p>

                <h4>Lo que este motor NO hace</h4>
                <ul style={{ marginTop: 0 }}>
                  <li>
                    <strong>No deriva M<sub>u</sub> ni V<sub>u</sub></strong>. El reparto del par
                    de la zapata medianera depende del modelo completo de la estructura; aquí
                    son datos de entrada.
                  </li>
                  <li>
                    <strong>No supone el perfil de suelo ni la zona sísmica.</strong> Si no los
                    declara, el motor dirá que solo pudo evaluar el criterio de q<sub>adm</sub>,
                    en vez de dar por supuesto que el artículo no aplica.
                  </li>
                  <li>
                    <strong>No supone el sistema sismorresistente.</strong> §21.12.3.3 remite a
                    §21.4 o a §21.5 según cuál sea; sin declararlo, los requisitos adicionales
                    quedan <span className="badge NO VERIFICADO">NO VERIFICADO</span>.
                  </li>
                </ul>

                <div className="note info">
                  <strong>Sobre la interacción axial-flexión</strong>
                  Cuando E.030 art. 65.1 se dispara, la comprobación no es «φMn ≥ Mu» con el
                  M<sub>n</sub> de flexión pura: se busca la capacidad a momento con esa misma
                  P<sub>u</sub> sobre el diagrama de interacción, y en los dos sentidos, porque
                  el artículo dice «en tracción o compresión» y no fija el signo.
                </div>
              </div>
            </div>
          )}

          {tipologia === "conectada" && !connResult && !error && (
            <div className="panel">
              <h2>Cimentación conectada</h2>
              <div className="panel-body">
                <p>
                  Una zapata en límite de propiedad no puede centrarse bajo su columna, y
                  esa excentricidad genera un par. La cimentación conectada lo resuelve
                  uniendo la zapata de lindero con una zapata interior mediante una{" "}
                  <strong>viga de conexión</strong> que transporta el par. Declare las dos
                  columnas, la viga y los rangos de búsqueda, y pulse{" "}
                  <strong>Calcular</strong>.
                </p>

                <h4>Lo que tiene que declarar usted</h4>
                <ul style={{ marginTop: 0 }}>
                  <li>
                    <strong>Modelo de análisis</strong> — articulado o cuerpo rígido.
                    Ninguna norma dice cuál corresponde.
                  </li>
                  <li>
                    <strong>Reparto del par</strong> — dónde va la rama cercana del par que
                    reparte la viga.
                  </li>
                  <li>
                    <strong>Apoyo y peso propio de la viga</strong> — en esta versión solo se
                    admite la viga sin apoyo en el terreno: el apoyo en el suelo se rechaza,
                    porque su modelo resistente no está definido.
                  </li>
                </ul>

                <div className="note nv">
                  <strong>La rigidez de la viga la responde usted</strong>
                  E.060 §15.2.6 exige evaluar la premisa de presión uniforme y no da método. Se
                  responde con la declaración de rigidez de la viga (<code>TBD-C1</code>): sin
                  declararla, la terna queda <strong>NO VERIFICADA</strong>. Declararla levanta
                  ese bloqueo y ningún otro; para ser CONFORME, todo lo demás debe salir PASS o INFO.
                </div>

                <h4>Lo que este motor NO hace</h4>
                <ul style={{ marginTop: 0 }}>
                  <li>
                    No admite el <strong>despegue de una zapata entera</strong>. Si alguna
                    combinación la levanta, ese sistema se rechaza por{" "}
                    <code>DESPEGUE</code> y la búsqueda continúa con los demás.
                  </li>
                  <li>
                    No optimiza la <strong>sección de la viga</strong>: es dato suyo, no
                    un eje de la búsqueda.
                  </li>
                </ul>
              </div>
            </div>
          )}

          {(tipologia === "aislada" || tipologia === "combinada") &&
            (tipologia === "aislada" ? !result : !combResult) &&
            !error && (
            <div className="panel">
              <h2>Cómo usar este programa</h2>
              <div className="panel-body">
                <p>
                  Complete los datos en el cajón <strong>Datos</strong> y pulse{" "}
                  <strong>
                    {TEXTO_CALCULAR[tipologia]}
                  </strong>. El motor recorrerá la malla de geometrías B–L, resolverá para cada una
                  el peralte mínimo viable y le mostrará las mejores soluciones junto con las
                  razones exactas por las que descartó las demás.
                </p>

                <h4>Lo que verá en los resultados</h4>
                <ul style={{ marginTop: 0 }}>
                  <li><strong>Mejores alternativas</strong> — Top-5 con esquema acotado, armado y memoria de cálculo.</li>
                  <li><strong>Tabla comparativa</strong> — todas las aceptadas, ordenables, con el frente de Pareto marcado.</li>
                  <li><strong>Descartes</strong> — cada motivo, cuántas geometrías afectó y un ejemplo detallado.</li>
                  <li><strong>Alcance</strong> — las limitaciones declaradas y cuándo el programa puede emitir PASS.</li>
                </ul>

                <h4>Unidades y rangos</h4>
                <ul style={{ marginTop: 0 }}>
                  <li>
                    Puede introducir cargas en <strong>toneladas fuerza, kilogramos fuerza,
                    libras o kips</strong>, y la presión del suelo en <strong>kg/cm² o t/m²</strong>.
                    El motor convierte a SI internamente.
                  </li>
                  <li>
                    Los límites de <strong>B, L y h son opcionales</strong>: si los deja en blanco,
                    el motor estima el rango a partir de A ≈ P/q<sub>adm</sub>.
                  </li>
                </ul>

                <h4>Criterios que conviene tener presentes</h4>
                <ul style={{ marginTop: 0 }}>
                  <li>
                    Las combinaciones de <strong>servicio</strong> dimensionan contra el suelo; las
                    <strong> factorizadas</strong> diseñan el concreto. El programa nunca las mezcla.
                  </li>
                  <li>
                    Si declara fuerzas horizontales debe aportar μ y los factores de seguridad: sin
                    ellos, deslizamiento y volcamiento quedan <span className="badge NO VERIFICADO">NO VERIFICADO</span>.
                  </li>
                  <li>
                    Los <strong>ganchos nunca se asumen</strong>. Si el refuerzo no se desarrolla con
                    barra recta, la alternativa se descarta salvo que Ud. declare el gancho.
                  </li>
                </ul>

                <div className="note info">
                  <strong>Sobre la interpretación de E.060 §15.7</strong>
                  La frase «altura medida sobre el refuerzo inferior» se interpreta por defecto como
                  el peralte efectivo d ≥ 300 mm. Es una lectura razonada y documentada, no una
                  certeza normativa: puede cambiarla en el panel de criterios.
                </div>
              </div>
            </div>
          )}

          {tipologia === "aislada" && result && (
            <ResultsView
              data={result} request={request} fmt={fmtAislada}
              seleccion={selAislada} onSeleccion={setSelAislada}
            />
          )}
          {tipologia === "combinada" && combResult && (
            <CombinedResultsView data={combResult} request={combRequest} fmt={fmtCombinada} />
          )}
          {tipologia === "conectada" && connResult && (
            <ConnectedResultsView data={connResult} request={connRequest} fmt={fmtConectada} />
          )}
          {tipologia === "viga" && beamResult && (
            <BeamResultsView data={beamResult} request={beamRequest} fmt={fmtViga} />
          )}
        </DockResultados>
      </main>

      <PanelPropiedades p={propiedades} onEditar={() => setDatosAbiertos(true)} />
    </div>
  );
}
