/**
 * Qué se muestra en el visor y en el panel de propiedades, tipología por tipología.
 *
 * Todo sale de dos fuentes, y se distinguen a propósito:
 *   - RESULTADOS del motor (SI): geometría, armado, volúmenes, estado.
 *   - ENTRADAS del usuario (en SU unidad): secciones de columna, materiales, Df, cargas.
 *
 * Nada se calcula aquí. Donde el motor no entrega un dato —la posición de las barras de
 * la combinada, el refuerzo de la columna— el panel lo dice en vez de rellenarlo.
 */

import type {
  BeamDesignRequest,
  BeamDesignResponse,
  CombinedDesignRequest,
  CombinedDesignResponse,
  CombinedFaceOut,
  ConnectedDesignRequest,
  ConnectedDesignResponse,
  DesignRequest,
  DesignResponse,
  LoadCombinationInput,
} from "../lib/api";
import type { Formateador } from "../lib/units";
import {
  conCotaDf,
  desdeAislada,
  desdeCombinada,
  desdeConectada,
  desdeViga,
  esquema,
  type DatosEntrada,
  type ModeloVisor,
} from "./model";

// ---------------------------------------------------------------------------
// Cargas: SOLO en modo directo
// ---------------------------------------------------------------------------

/**
 * La carga de servicio que se rotula sobre cada columna: la mayor P de las combinaciones
 * de servicio escritas por el usuario, con el nombre de la combinación.
 *
 * En modo POR CASOS no se muestra ninguna: la P de cada combinación sale de sumar casos
 * por sus factores, y esa suma la hace el motor (`derive_load_case_set`), no la pantalla.
 */
function cargaMaxima(combos: LoadCombinationInput[] | undefined, porCasos: boolean, fmt: Formateador, nombre: string) {
  if (porCasos || !combos) return null;
  const servicio = combos.filter((c) => c.type === "SERVICIO");
  if (!servicio.length) return null;
  const peor = servicio.reduce((a, b) => (b.P_kN > a.P_kN ? b : a));
  return {
    kN: fmt.si(peor.P_kN, "force") ?? peor.P_kN,
    texto: `${nombre} = ${fmtNum(peor.P_kN)} ${fmt.unidad("force")} · ${peor.name}`,
  };
}

const fmtNum = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));
const lon = (fmt: Formateador) => (m: number) => fmt.con(m, "length", 2);

// ---------------------------------------------------------------------------
// Modelos del visor
// ---------------------------------------------------------------------------

export function modeloAislada(
  req: DesignRequest, res: DesignResponse | null, sel: number, fmt: Formateador,
): ModeloVisor {
  const Df = fmt.si(req.soil.Df_m, "length") ?? req.soil.Df_m;
  const carga = cargaMaxima(req.combinations, req.load_cases != null, fmt, "P1");
  const entrada: DatosEntrada = { Df, cargas: carga ? [carga] : [] };
  const alt = res?.top[sel] ?? res?.top[0];
  if (alt?.scene) {
    return conCotaDf(desdeAislada(alt.scene, entrada, lon(fmt), alt.status), lon(fmt));
  }
  return esquema("iso", {
    Df,
    columnas: [{ b: fmt.si(req.column.bx_m, "length") ?? 0.4, t: fmt.si(req.column.by_m, "length") ?? 0.4, x: 0 }],
  }, entrada.cargas, lon(fmt));
}

export function modeloCombinada(
  req: CombinedDesignRequest, res: CombinedDesignResponse | null, fmt: Formateador,
): ModeloVisor {
  const Df = fmt.si(req.soil.Df_m, "length") ?? req.soil.Df_m;
  const porCasos = req.combination_definitions != null;
  const cargas = req.columns.slice(0, 2)
    .map((c, i) => cargaMaxima(c.combinations, porCasos, fmt, `P${i + 1}`))
    .filter((q): q is NonNullable<typeof q> => q !== null);
  const entrada: DatosEntrada = { Df, cargas };
  if (res?.scene) return conCotaDf(desdeCombinada(res.scene, entrada, lon(fmt)), lon(fmt));
  return esquema("comb", {
    Df,
    columnas: req.columns.slice(0, 2).map((c) => ({
      b: fmt.si(c.bx_m, "length") ?? 0.4,
      t: fmt.si(c.by_m, "length") ?? 0.4,
      x: fmt.si(c.distance_from_first_m, "length") ?? 0,
    })),
  }, cargas, lon(fmt));
}

export function modeloConectada(
  req: ConnectedDesignRequest, res: ConnectedDesignResponse | null, fmt: Formateador,
): ModeloVisor {
  const Df = fmt.si(req.soil.Df_m, "length") ?? req.soil.Df_m;
  const porCasos = req.combination_definitions != null;
  const cargas = [req.exterior, req.interior]
    .map((c, i) => cargaMaxima(c.combinations, porCasos, fmt, `P${i + 1}`))
    .filter((q): q is NonNullable<typeof q> => q !== null);
  const entrada: DatosEntrada = { Df, cargas };
  if (res?.scene) return conCotaDf(desdeConectada(res.scene, entrada, lon(fmt)), lon(fmt));
  return esquema("conn", {
    Df,
    columnas: [
      { b: fmt.si(req.exterior.bx_m, "length") ?? 0.4, t: fmt.si(req.exterior.by_m, "length") ?? 0.4, x: 0 },
      {
        b: fmt.si(req.interior.bx_m, "length") ?? 0.4,
        t: fmt.si(req.interior.by_m, "length") ?? 0.4,
        x: fmt.si(req.axis_distance_m, "length") ?? 5,
      },
    ],
    vigaB: fmt.si(req.beam.b_m, "length") ?? undefined,
    vigaH: fmt.si(req.beam.h_m, "length") ?? undefined,
  }, cargas, lon(fmt));
}

export function modeloViga(
  req: BeamDesignRequest, res: BeamDesignResponse | null, fmt: Formateador,
): ModeloVisor {
  // Con resultado, la sección y la luz vienen del motor en SI; sin él, de la entrada.
  const b = res
    ? { b_m: res.b_m, h_m: res.h_m, clear_span_m: res.clear_span_m }
    : {
      b_m: fmt.si(req.b_m, "length") ?? 0.3,
      h_m: fmt.si(req.h_m, "length") ?? 0.6,
      clear_span_m: fmt.si(req.clear_span_m, "length") ?? 4,
    };
  const m = desdeViga(b, lon(fmt));
  return res ? m : { ...m, esquema: true };
}

// ---------------------------------------------------------------------------
// Panel de propiedades
// ---------------------------------------------------------------------------

export interface Fila {
  sym: string;
  lb: string;
  valor: string;
  /** Texto secundario (fuera de alcance, pendiente…), en gris. */
  nota?: boolean;
}
export interface Seccion {
  titulo: string;
  filas: Fila[];
  resumen?: boolean;
}
export interface Propiedades {
  codigo: string;
  titulo: string;
  descripcion: string;
  alternativa: string | null;
  estado: string | null;
  secciones: Seccion[];
  aviso: string | null;
}

/** Valor de ENTRADA del usuario, escrito en su propia unidad. Sin convertir. */
const entradaCon = (v: number | null | undefined, unidad: string, dec = 2) =>
  v === null || v === undefined ? "—" : `${v.toFixed(dec)} ${unidad}`;

function materiales(m: { fc_MPa: number; fy_MPa: number }, fmt: Formateador): Seccion {
  return {
    titulo: "Material",
    filas: [
      { sym: "f'c", lb: "Concreto", valor: entradaCon(m.fc_MPa, fmt.unidad("strength"), 1) },
      { sym: "fy", lb: "Acero", valor: entradaCon(m.fy_MPa, fmt.unidad("strength"), 0) },
    ],
  };
}

const PENDIENTE = "pendiente de cálculo";
/** Valor numérico aún sin calcular: la raya basta, el aviso de cabecera lo explica. */
const SIN_CALCULO = "—";

export function propiedadesAislada(req: DesignRequest, res: DesignResponse | null, sel: number, fmt: Formateador): Propiedades {
  const alt = res?.top[sel] ?? res?.top[0] ?? null;
  const L = (v: number | undefined, dec = 2) => (alt && v !== undefined ? fmt.con(v, "length", dec) : SIN_CALCULO);
  const u = req.units;
  const capas = alt?.scene?.layers ?? [];
  return {
    codigo: "Z-1",
    titulo: "Zapata aislada",
    descripcion: "Una columna transmite su carga a una zapata propia.",
    alternativa: alt?.id ?? null,
    estado: alt?.status ?? null,
    aviso: alt ? null : "Sin alternativa calculada: la geometría la decide el motor.",
    secciones: [
      {
        titulo: "Geometría · Zapata",
        filas: [
          { sym: "B", lb: "Ancho (eje X)", valor: L(alt?.B_m) },
          { sym: "L", lb: "Largo (eje Y)", valor: L(alt?.L_m) },
          { sym: "h", lb: "Peralte total", valor: L(alt?.h_m) },
          { sym: "d", lb: "Peralte efectivo", valor: L(alt?.d_m, 3) },
          { sym: "Df", lb: "Profundidad de desplante", valor: entradaCon(req.soil.Df_m, u.length) },
          { sym: "eₓ", lb: "Excentricidad X", valor: entradaCon(req.column.offset_x_m ?? 0, u.length) },
          { sym: "eᵧ", lb: "Excentricidad Y", valor: entradaCon(req.column.offset_y_m ?? 0, u.length) },
        ],
      },
      {
        titulo: "Columna C1",
        filas: [
          { sym: "bx", lb: "Ancho", valor: entradaCon(req.column.bx_m, u.length) },
          { sym: "by", lb: "Fondo", valor: entradaCon(req.column.by_m, u.length) },
          { sym: "", lb: "Refuerzo", valor: "fuera del alcance", nota: true },
        ],
      },
      materiales(req.materials, fmt),
      {
        titulo: "Armadura de zapata",
        filas: alt
          ? [
            { sym: "X", lb: "Dirección X", valor: alt.rebar_x_label },
            { sym: "Y", lb: "Dirección Y", valor: alt.rebar_y_label },
            { sym: "r", lb: "Recubrimiento", valor: `${alt.cover_mm.toFixed(0)} mm` },
            ...capas.map((c) => ({
              sym: "n", lb: `Barras ${c.direction} · ${c.layer}`, valor: `${c.n_bars}`,
            })),
          ]
          : [{ sym: "", lb: "Armado", valor: PENDIENTE, nota: true }],
      },
      {
        titulo: "Presión de contacto",
        filas: alt
          ? [
            { sym: "q⁺", lb: "Máxima", valor: fmt.con(alt.qmax_kPa, "pressure", 1) },
            { sym: "q⁻", lb: "Mínima", valor: fmt.con(alt.qmin_kPa, "pressure", 1) },
            { sym: "qa", lb: "Admisible (dato)", valor: entradaCon(req.soil.qadm_kPa, u.pressure, 1) },
          ]
          : [{ sym: "qa", lb: "Admisible (dato)", valor: entradaCon(req.soil.qadm_kPa, u.pressure, 1) }],
      },
      {
        titulo: "Resumen",
        resumen: true,
        filas: alt
          ? [
            { sym: "A", lb: "Área de apoyo", valor: `${alt.footing_area_m2.toFixed(2)} m²` },
            { sym: "V", lb: "Concreto", valor: `${alt.concrete_volume_m3.toFixed(2)} m³` },
            { sym: "W", lb: "Acero", valor: `${alt.steel_mass_kg.toFixed(0)} kg` },
          ]
          : [{ sym: "", lb: "Resultados", valor: PENDIENTE, nota: true }],
      },
    ],
  };
}

export function propiedadesCombinada(req: CombinedDesignRequest, res: CombinedDesignResponse | null, fmt: Formateador): Propiedades {
  const alt = res?.top[0] ?? null;
  const fila = res?.comparison?.find((c) => c.id === alt?.id) ?? null;
  const u = req.units;
  const cara = (c: CombinedFaceOut | null) =>
    c?.bar_designation && c.spacing_m ? `${c.bar_designation} @ ${fmt.texto(c.spacing_m, "length", 3)} ${fmt.unidad("length")}` : "—";
  return {
    codigo: "Z-1",
    titulo: "Zapata combinada",
    descripcion: "Dos o más columnas comparten una única base de cimentación.",
    alternativa: alt?.id ?? null,
    estado: res?.scene?.status_label ?? alt?.status ?? null,
    aviso: alt
      ? "Se muestra la alternativa recomendada: el motor solo prepara el modelo 3D de esa."
      : "Sin alternativa calculada: la geometría la decide el motor.",
    secciones: [
      {
        titulo: "Geometría · Zapata combinada",
        filas: [
          { sym: "L", lb: "Largo (entre columnas)", valor: alt ? fmt.con(alt.length_m, "length", 2) : SIN_CALCULO },
          { sym: "B", lb: "Ancho", valor: alt ? fmt.con(alt.width_m, "length", 2) : SIN_CALCULO },
          { sym: "h", lb: "Peralte total", valor: alt ? fmt.con(alt.h_m, "length", 2) : SIN_CALCULO },
          { sym: "Df", lb: "Profundidad de desplante", valor: entradaCon(req.soil.Df_m, u.length) },
        ],
      },
      {
        titulo: `Columnas ${req.columns.map((c) => c.label).join(" · ")}`,
        filas: [
          ...req.columns.map((c) => ({
            sym: c.label, lb: `${entradaCon(c.bx_m, u.length)} × ${entradaCon(c.by_m, u.length)}`,
            valor: `a ${entradaCon(c.distance_from_first_m, u.length)}`,
          })),
          { sym: "", lb: "Refuerzo de columna", valor: "fuera del alcance", nota: true },
        ],
      },
      materiales(req.materials, fmt),
      {
        titulo: "Armadura de diseño",
        filas: alt
          ? [
            { sym: "inf", lb: "Cara inferior (M+)", valor: cara(alt.bottom_face) },
            { sym: "sup", lb: "Cara superior (M−)", valor: alt.top_face ? cara(alt.top_face) : "no requerida" },
            { sym: "", lb: "Posición de barras", valor: "no resuelta por el motor", nota: true },
          ]
          : [{ sym: "", lb: "Armado", valor: PENDIENTE, nota: true }],
      },
      {
        titulo: "Resumen",
        resumen: true,
        filas: alt
          ? [
            ...(fila ? [{ sym: "A", lb: "Área de apoyo", valor: `${fila.footing_area_m2.toFixed(2)} m²` }] : []),
            { sym: "V", lb: "Concreto", valor: `${alt.concrete_volume_m3.toFixed(2)} m³` },
            ...(fila ? [{ sym: "W", lb: "Acero", valor: `${fila.steel_mass_kg.toFixed(0)} kg` }] : []),
          ]
          : [{ sym: "", lb: "Resultados", valor: PENDIENTE, nota: true }],
      },
    ],
  };
}

export function propiedadesConectada(req: ConnectedDesignRequest, res: ConnectedDesignResponse | null, fmt: Formateador): Propiedades {
  const alt = (res?.comparison ?? res?.accepted ?? []).find((a) => a.id === res?.scene?.alternative_id)
    ?? res?.accepted[0] ?? null;
  const u = req.units;
  const L = (v: number | undefined) => (alt && v !== undefined ? fmt.con(v, "length", 2) : SIN_CALCULO);
  // B y L siguen a los ejes (E.050 art. 28.1: X es la dirección de B); cuál de las dos
  // corre a lo largo de la viga («longitudinal») lo decide `longitudinal_axis`, como en el motor.
  const porX = req.longitudinal_axis === "X";
  const rotB = porX ? "Eje X · longitudinal" : "Eje X · transversal";
  const rotL = porX ? "Eje Y · transversal" : "Eje Y · longitudinal";
  return {
    codigo: "Z-1 · Z-2 · VC-1",
    titulo: "Zapata conectada",
    descripcion: "Dos zapatas independientes unidas por una viga de conexión.",
    alternativa: alt?.id ?? null,
    estado: alt?.status_label ?? null,
    aviso: alt
      ? "Se muestra la terna recomendada: el motor solo prepara el modelo 3D de esa."
      : "Sin alternativa calculada: la geometría la decide el motor.",
    secciones: [
      {
        titulo: "Zapata de lindero · Z-1",
        filas: [
          { sym: "B", lb: rotB, valor: L(alt?.exterior_B_m) },
          { sym: "L", lb: rotL, valor: L(alt?.exterior_L_m) },
          { sym: "h", lb: "Peralte", valor: L(alt?.exterior_h_m) },
        ],
      },
      {
        titulo: "Zapata interior · Z-2",
        filas: [
          { sym: "B", lb: rotB, valor: L(alt?.interior_B_m) },
          { sym: "L", lb: rotL, valor: L(alt?.interior_L_m) },
          { sym: "h", lb: "Peralte", valor: L(alt?.interior_h_m) },
          { sym: "Df", lb: "Profundidad de desplante", valor: entradaCon(req.soil.Df_m, u.length) },
        ],
      },
      {
        titulo: "Viga de conexión VC-1",
        filas: [
          { sym: "b", lb: "Ancho", valor: entradaCon(req.beam.b_m, u.length) },
          { sym: "h", lb: "Peralte", valor: entradaCon(req.beam.h_m, u.length) },
          { sym: "Lv", lb: "Vano libre", valor: L(alt?.beam_span_m) },
          { sym: "s", lb: "Separación entre ejes", valor: entradaCon(req.axis_distance_m, u.length) },
          { sym: "", lb: "Refuerzo", valor: "ver Resultados", nota: true },
        ],
      },
      materiales(req.materials, fmt),
      {
        titulo: "Resumen",
        resumen: true,
        filas: alt
          ? [
            ...(alt.footing_area_m2 != null ? [{ sym: "A", lb: "Área de apoyo", valor: `${alt.footing_area_m2.toFixed(2)} m²` }] : []),
            { sym: "V", lb: "Concreto", valor: `${alt.concrete_volume_m3.toFixed(2)} m³` },
            { sym: "W", lb: "Acero", valor: `${alt.steel_mass_kg.toFixed(0)} kg` },
            { sym: "ΔP", lb: "Transferencia a Z-2", valor: fmt.con(alt.delta_P_kN, "force", 1) },
          ]
          : [{ sym: "", lb: "Resultados", valor: PENDIENTE, nota: true }],
      },
    ],
  };
}

export function propiedadesViga(req: BeamDesignRequest, res: BeamDesignResponse | null, fmt: Formateador): Propiedades {
  const u = req.units;
  return {
    codigo: "VC-1",
    titulo: "Viga de conexión",
    descripcion: "Diseño directo con solicitaciones conocidas.",
    alternativa: null,
    estado: res?.status ?? null,
    aviso: res ? null : "Sin diseño todavía: pulse Diseñar.",
    secciones: [
      {
        titulo: "Sección",
        filas: [
          { sym: "b", lb: "Ancho", valor: res ? fmt.con(res.b_m, "length", 2) : entradaCon(req.b_m, u.length) },
          { sym: "h", lb: "Peralte", valor: res ? fmt.con(res.h_m, "length", 2) : entradaCon(req.h_m, u.length) },
          { sym: "d", lb: "Peralte efectivo", valor: res ? fmt.con(res.d_m, "length", 3) : entradaCon(req.d_m, u.length) },
          { sym: "Lv", lb: "Luz libre", valor: res ? fmt.con(res.clear_span_m, "length", 2) : entradaCon(req.clear_span_m, u.length) },
        ],
      },
      materiales(req.materials, fmt),
      {
        titulo: "Armadura de diseño",
        filas: res
          ? [
            { sym: "As⁻", lb: "Cara superior", valor: `${res.As_negative_cm2.toFixed(2)} cm²` },
            { sym: "As⁺", lb: "Cara inferior", valor: `${res.As_positive_cm2.toFixed(2)} cm²` },
            {
              sym: "s", lb: "Estribos cerrados",
              valor: res.confinement_provided_cm != null ? `@ ${res.confinement_provided_cm.toFixed(0)} cm` : "—",
            },
          ]
          : [{ sym: "", lb: "Armado", valor: PENDIENTE, nota: true }],
      },
      {
        titulo: "Resumen",
        resumen: true,
        filas: res
          ? [
            { sym: "Mu⁻", lb: "Momento negativo", valor: fmt.con(res.Mu_negative_kNm, "moment", 1) },
            { sym: "Mu⁺", lb: "Momento positivo", valor: fmt.con(res.Mu_positive_kNm, "moment", 1) },
          ]
          : [{ sym: "", lb: "Resultados", valor: PENDIENTE, nota: true }],
      },
    ],
  };
}
