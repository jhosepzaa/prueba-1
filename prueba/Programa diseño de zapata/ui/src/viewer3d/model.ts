/**
 * Modelo del visor 3D (CIMA) — la geometría que se dibuja, ya en el mundo de three.js.
 *
 * DE DÓNDE SALE CADA NÚMERO
 * =========================
 * El diseño de referencia (handoff «Cimentación 3D») genera la geometría y la armadura
 * a partir de parámetros propios. Este programa NO puede hacer eso: la geometría la
 * decide el motor y el visor solo la muestra (`engine/visualization/scene_dto.py`:
 * «la visualización muestra datos calculados, NUNCA los recalcula»). Por eso este
 * módulo es un ADAPTADOR, no un generador:
 *
 *   - Zapatas, columnas y viga: las cajas del `*SceneDTO` del motor.
 *   - Barras: las de `FootingSceneDTO.bars`, con la posición que resolvió el motor.
 *     Solo existen en la zapata aislada; en combinada y conectada el motor declara que
 *     no resuelve el armado, y el visor no se lo inventa.
 *   - Cotas: las del motor (`dimensions`), rotuladas en la unidad del usuario.
 *   - Df y cargas: datos de ENTRADA del usuario, no resultados.
 *
 * Lo único de presentación pura, y se dice: la columna se prolonga por encima del
 * terreno (el motor dibuja un tramo corto), la caja de suelo y el margen de encuadre.
 *
 * SISTEMA DE COORDENADAS
 * ======================
 * Mundo three.js: Y hacia arriba, NTN en y = 0, metros. Las escenas del motor usan
 * X a lo largo de B, Y a lo largo de L y Z vertical con origen en la base de la
 * zapata. La conversión es
 *
 *     x_mundo = x      y_mundo = z − Df      z_mundo = −y
 *
 * que es la misma convención del handoff: el eje Y de ingeniería apunta a −Z de three,
 * y así lo rotula el gizmo.
 */

import type {
  BoxOut,
  CombinedSceneOut,
  ConnectedSceneOut,
  DimensionOut,
  FootingSceneOut,
  Vec3,
} from "../lib/api";

export type Tipo = "iso" | "comb" | "conn" | "viga";

/** Una caja del modelo. `o` es presencia/opacidad (0–1): lo que permite interpolar. */
export interface Caja {
  cx: number;
  cy: number;
  cz: number;
  sx: number;
  sy: number;
  sz: number;
  o: number;
}

export interface Barra {
  /** Extremos en el mundo. */
  a: [number, number, number];
  b: [number, number, number];
  diametro: number;
  nombre: string;
  /** Retardo de aparición, s. Solo animación. */
  retardo: number;
  estribo: boolean;
}

export interface Cota {
  id: string;
  texto: string;
  a: [number, number, number];
  b: [number, number, number];
}

export interface Carga {
  x: number;
  z: number;
  /** Valor en kN, solo para escalar la flecha. */
  kN: number;
  texto: string;
}

export interface ModeloVisor {
  tipo: Tipo;
  /** Sin resultado del motor: el modelo es un esquema dibujado con los datos de entrada. */
  esquema: boolean;
  id: string | null;
  /** Rótulo del vocabulario único, tal como lo da el motor. */
  estado: string | null;
  foot1: Caja;
  foot2: Caja;
  col1: Caja;
  col2: Caja;
  beam: Caja;
  Df: number;
  recubrimiento: number | null;
  barras: Barra[];
  cotas: Cota[];
  cargas: Carga[];
  /** Rótulos de elemento: «C1 0.40×0.40». */
  etiquetas: { texto: string; clase: "tag" | "tag vc"; p: [number, number, number] }[];
  /** Por qué el armado no aparece, cuando no aparece. */
  notaArmado: string | null;
  notaAlcance: string | null;
}

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

export const caja = (cx: number, cy: number, cz: number, sx: number, sy: number, sz: number, o = 1): Caja =>
  ({ cx, cy, cz, sx, sy, sz, o });

const OCULTA = (x = 0, y = 0, z = 0): Caja => caja(x, y, z, 0, 0, 0, 0);

/** Cuánto se prolonga la columna por encima del terreno. Presentación, no estructura. */
const COLUMNA_SOBRE_NTN = 1.0;

/** Conversión escena del motor → mundo. `girar` lleva el eje Y del motor al X del mundo. */
function punto(v: Vec3, Df: number, girar = false): [number, number, number] {
  return girar ? [v.y, v.z - Df, v.x] : [v.x, v.z - Df, -v.y];
}

function desdeMotor(b: BoxOut, Df: number, girar = false): Caja {
  const [cx, cy, cz] = punto(b.center, Df, girar);
  return girar
    ? caja(cx, cy, cz, b.size.y, b.size.z, b.size.x)
    : caja(cx, cy, cz, b.size.x, b.size.z, b.size.y);
}

/** La columna desde la cara superior de su zapata hasta un poco por encima del NTN. */
function columnaHastaArriba(c: Caja): Caja {
  const base = c.cy - c.sy / 2;
  const tope = Math.max(c.cy + c.sy / 2, COLUMNA_SOBRE_NTN);
  return caja(c.cx, (base + tope) / 2, c.cz, c.sx, tope - base, c.sz, c.o);
}

/** Nombre corto de cada cota del motor, para rotularla como en el diseño. */
// Solo se abrevian las cotas cuyo símbolo significa lo mismo en el motor y en el panel.
// Las de la conectada (L1, B1, S, vano…) conservan el rótulo del motor —«zapata de
// lindero = …», «entre ejes = …»—: su id no es el B/L por eje que usa el resultado.
const NOMBRE_COTA: Record<string, string> = {
  B: "B", L: "L", h: "h", col_bx: "bx", col_by: "by",
};

/**
 * Rótulo de una cota en la unidad del usuario. El motor escribe sus rótulos en metros;
 * aquí se conserva su TEXTO y solo se sustituye el número, que se mide en la escena.
 *   «B = 2.50 m»            → «B = <valor>»
 *   «0.25 m al eje de C1»   → «<valor> al eje de C1»
 */
function textoCota(d: DimensionOut, valor: string, nombres: Record<string, string>): string {
  const nombre = nombres[d.id] ?? NOMBRE_COTA[d.id];
  if (nombre) return `${nombre} = ${valor}`;
  if (d.label.includes("=")) return `${d.label.split("=")[0].trim()} = ${valor}`;
  const m = /^\s*[\d.,]+\s*m\s*(.*)$/.exec(d.label);
  if (m) return m[1] ? `${valor} ${m[1]}` : valor;
  return d.label;
}

/** Formatea una longitud del motor (SI) en la unidad del usuario. */
export type FormatoLongitud = (m: number) => string;

function cotasDesdeMotor(
  dims: DimensionOut[],
  Df: number,
  topeZapata: number,
  fmtL: FormatoLongitud,
  girar = false,
  nombres: Record<string, string> = {},
): Cota[] {
  return dims.map((d) => {
    let a = punto(d.start, Df, girar);
    let b = punto(d.end, Df, girar);
    // Las cotas en planta del motor están a nivel de la base; el diseño las dibuja sobre
    // la cara superior. Se sube la LÍNEA —su posición en planta y su longitud no cambian.
    if (d.plane === "XY") {
      a = [a[0], topeZapata, a[2]];
      b = [b[0], topeZapata, b[2]];
    }
    const largo = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    return { id: d.id, texto: textoCota(d, fmtL(largo), nombres), a, b };
  });
}

// ---------------------------------------------------------------------------
// Desde el motor
// ---------------------------------------------------------------------------

export interface DatosEntrada {
  /** Profundidad de cimentación, m (dato del usuario convertido a SI). */
  Df: number;
  /** Cargas de servicio por columna, en el orden C1, C2. */
  cargas: { kN: number; texto: string }[];
}

/** Zapata aislada: geometría y ARMADURA resueltas por el motor. */
export function desdeAislada(
  s: FootingSceneOut,
  entrada: DatosEntrada,
  fmtL: FormatoLongitud,
  estado: string,
): ModeloVisor {
  const Df = Math.max(entrada.Df, s.h_m);
  const foot1 = desdeMotor(s.footing, Df);
  const col1 = columnaHastaArriba(desdeMotor(s.column, Df));
  const tope = foot1.cy + foot1.sy / 2;

  const barras: Barra[] = s.bars.map((bar, i) => ({
    a: punto(bar.start, Df),
    b: punto(bar.end, Df),
    diametro: bar.diameter_m,
    // Nombres del prototipo: Z1_inf_L_3 / Z1_inf_B_2, útiles al exportar.
    nombre: `Z1_${bar.layer === "inferior" ? "inf" : "sup"}_${bar.direction === "X" ? "B" : "L"}_${bar.index + 1}`,
    // Escalonado de aparición: primero una capa, luego la otra, como en el diseño.
    retardo: (bar.direction === "X" ? 0 : 0.08) + (i / Math.max(1, s.bars.length)) * 0.45,
    estribo: false,
  }));

  return {
    tipo: "iso",
    esquema: false,
    id: s.alternative_id,
    estado,
    foot1,
    foot2: OCULTA(foot1.cx + foot1.sx, foot1.cy, foot1.cz),
    col1,
    col2: caja(col1.cx + foot1.sx, col1.cy + 1.6, col1.cz, col1.sx, col1.sy, col1.sz, 0),
    beam: OCULTA(col1.cx, foot1.cy - foot1.sy / 2, 0),
    Df,
    recubrimiento: s.cover_m,
    barras,
    cotas: cotasDesdeMotor(s.dimensions, Df, tope, fmtL),
    cargas: cargasSobre([col1], entrada),
    etiquetas: [etiquetaColumna("C1", col1, fmtL)],
    notaArmado: null,
    notaAlcance: s.scope_note,
  };
}

/** Zapata combinada: geometría del motor; el motor no resuelve la posición del armado. */
export function desdeCombinada(
  s: CombinedSceneOut,
  entrada: DatosEntrada,
  fmtL: FormatoLongitud,
): ModeloVisor {
  // El visor dibuja siempre las columnas a lo largo de X, como el diseño. Si el motor
  // las separó en Y, se gira el modelo entero: la geometría no cambia, solo la vista.
  const girar = s.longitudinal_direction === "Y";
  const Df = Math.max(entrada.Df, s.h_m);
  const foot1 = desdeMotor(s.footing, Df, girar);
  const cols = [...s.columns]
    .map((c) => ({ label: c.label, caja: columnaHastaArriba(desdeMotor(c.box, Df, girar)) }))
    .sort((p, q) => p.caja.cx - q.caja.cx);
  const col1 = cols[0]?.caja ?? OCULTA();
  const col2 = cols[cols.length - 1]?.caja ?? OCULTA();
  const tope = foot1.cy + foot1.sy / 2;

  return {
    tipo: "comb",
    esquema: false,
    id: s.alternative_id,
    estado: s.status_label,
    foot1,
    foot2: caja(col2.cx, foot1.cy, foot1.cz, 0, foot1.sy, foot1.sz, 0),
    col1,
    col2,
    beam: OCULTA(col1.cx, foot1.cy - foot1.sy / 2, 0),
    Df,
    recubrimiento: null,
    barras: [],
    // La escena de la combinada nombra B y L por EJE (X, Y); el resultado y el panel,
    // por significado (largo entre columnas, ancho). Se rotulan por significado para que
    // el visor no llame «B» a lo que el panel llama «L».
    cotas: cotasDesdeMotor(s.dimensions, Df, tope, fmtL, girar, {
      B: s.longitudinal_direction === "X" ? "Largo" : "Ancho",
      L: s.longitudinal_direction === "X" ? "Ancho" : "Largo",
    }),
    cargas: cargasSobre(cols.map((c) => c.caja), entrada),
    etiquetas: cols.map((c) => etiquetaColumna(c.label, c.caja, fmtL)),
    notaArmado:
      "El motor diseña el acero de la combinada —caras superior e inferior y franjas " +
      "transversales— pero no resuelve la posición de cada barra. El visor no la inventa: " +
      "el armado de diseño está en Resultados.",
    notaAlcance: s.scope_note,
  };
}

/** Sistema conectado: dos zapatas, viga y columnas, en el sistema local de la viga. */
export function desdeConectada(
  s: ConnectedSceneOut,
  entrada: DatosEntrada,
  fmtL: FormatoLongitud,
): ModeloVisor {
  const Df = Math.max(entrada.Df, s.exterior_footing.size.z, s.interior_footing.size.z);
  const foot1 = desdeMotor(s.exterior_footing, Df);
  const foot2 = desdeMotor(s.interior_footing, Df);
  const col1 = columnaHastaArriba(desdeMotor(s.exterior_column, Df));
  const col2 = columnaHastaArriba(desdeMotor(s.interior_column, Df));
  const beam = desdeMotor(s.beam, Df);
  const tope = Math.max(foot1.cy + foot1.sy / 2, foot2.cy + foot2.sy / 2);

  const etiquetas: ModeloVisor["etiquetas"] = [
    etiquetaColumna("C1", col1, fmtL),
    etiquetaColumna("C2", col2, fmtL),
  ];
  if (beam.sx > 0.05) {
    etiquetas.push({
      texto: `VC-1  ${fmtL(beam.sz)}×${fmtL(beam.sy)}`,
      clase: "tag vc",
      p: [(s.free_span_start_x_m + s.free_span_end_x_m) / 2, beam.cy + beam.sy / 2 + 0.16, 0],
    });
  }

  return {
    tipo: "conn",
    esquema: false,
    id: s.alternative_id,
    estado: s.status_label,
    foot1,
    foot2,
    col1,
    col2,
    beam,
    Df,
    recubrimiento: null,
    barras: [],
    cotas: cotasDesdeMotor(s.dimensions, Df, tope, fmtL),
    cargas: cargasSobre([col1, col2], entrada),
    etiquetas,
    notaArmado:
      "El motor no resuelve la posición de las barras del sistema conectado. El visor no " +
      "las inventa: el diseño de cada zapata y de la viga está en Resultados.",
    notaAlcance: s.scope_note,
  };
}

/** Viga de conexión aislada: una caja con las medidas del resultado. Sin armado dibujado. */
export function desdeViga(
  b: { b_m: number; h_m: number; clear_span_m: number },
  fmtL: FormatoLongitud,
): ModeloVisor {
  const Df = b.h_m + 0.2;
  const beam = caja(b.clear_span_m / 2, -Df + b.h_m / 2, 0, b.clear_span_m, b.h_m, b.b_m);
  return {
    tipo: "viga",
    esquema: false,
    id: "VC-1",
    estado: null,
    foot1: OCULTA(0, -Df, 0),
    foot2: OCULTA(b.clear_span_m, -Df, 0),
    col1: OCULTA(0, 0.5, 0),
    col2: OCULTA(b.clear_span_m, 0.5, 0),
    beam,
    Df,
    recubrimiento: null,
    barras: [],
    cotas: [
      {
        id: "Lv", texto: `Lv = ${fmtL(b.clear_span_m)}`,
        a: [0, -Df + b.h_m, b.b_m / 2 + 0.4], b: [b.clear_span_m, -Df + b.h_m, b.b_m / 2 + 0.4],
      },
      {
        id: "h", texto: `h = ${fmtL(b.h_m)}`,
        a: [-0.35, -Df, b.b_m / 2], b: [-0.35, -Df + b.h_m, b.b_m / 2],
      },
    ],
    cargas: [],
    etiquetas: [{
      texto: `VC-1  ${fmtL(b.b_m)}×${fmtL(b.h_m)}`, clase: "tag vc",
      p: [b.clear_span_m / 2, -Df + b.h_m + 0.18, 0],
    }],
    notaArmado:
      "El motor calcula el área de acero de la viga pero no la disposición de las barras. " +
      "El armado de diseño está en Resultados.",
    notaAlcance: "Viga dibujada con la sección y la luz libre del resultado.",
  };
}

// ---------------------------------------------------------------------------
// Esquema: sin resultado todavía
// ---------------------------------------------------------------------------

export interface DatosEsquema {
  Df: number;
  columnas: { b: number; t: number; x: number }[];
  vigaB?: number;
  vigaH?: number;
}

/**
 * Lo que se dibuja ANTES de calcular. Solo lleva datos de entrada: secciones de columna,
 * su separación y Df. La planta de la zapata todavía no existe —la decide el motor—, así
 * que se dibuja con una proporción nominal y SIN rotular sus medidas. El visor pone
 * encima un distintivo «Esquema · sin calcular».
 */
export function esquema(tipo: Tipo, d: DatosEsquema, cargas: DatosEntrada["cargas"], fmtL: FormatoLongitud): ModeloVisor {
  const Df = Math.max(d.Df, 0.8);
  const h = 0.5;
  const fy = -Df + h / 2;
  const c1 = d.columnas[0] ?? { b: 0.4, t: 0.4, x: 0 };
  const c2 = d.columnas[1] ?? { b: c1.b, t: c1.t, x: 3.5 };
  const lado = Math.max(1.6, 4 * Math.max(c1.b, c1.t));
  const col = (c: { b: number; t: number; x: number }, o = 1) =>
    columnaHastaArriba(caja(c.x, -Df + h + 0.3, 0, c.b, 0.6, c.t, o));

  const col1 = col(c1);
  let foot1 = caja(c1.x, fy, 0, lado, h, lado);
  let foot2 = caja(c2.x, fy, 0, 0, h, lado, 0);
  let col2 = { ...col(c2), cy: col(c2).cy + 1.6, o: 0 };
  let beam = OCULTA(c1.x, -Df, 0);

  if (tipo === "comb") {
    const x0 = c1.x - lado / 2, x1 = c2.x + lado / 2;
    foot1 = caja((x0 + x1) / 2, fy, 0, x1 - x0, h, lado);
    col2 = col(c2);
  }
  if (tipo === "conn") {
    col2 = col(c2);
    foot2 = caja(c2.x, fy, 0, lado, h, lado);
    const bh = d.vigaH ?? 0.6, bb = d.vigaB ?? 0.3;
    beam = caja((c1.x + c2.x) / 2, -Df + bh / 2, 0, c2.x - c1.x, bh, bb);
  }

  const cols = tipo === "iso" ? [col1] : [col1, col2];
  return {
    tipo,
    esquema: true,
    id: null,
    estado: null,
    foot1,
    foot2,
    col1,
    col2,
    beam,
    Df,
    recubrimiento: null,
    barras: [],
    // Solo se rotula lo que es DATO: Df. La planta no se acota porque aún no existe.
    cotas: [{
      id: "Df", texto: `Df = ${fmtL(Df)}`,
      a: [foot1.cx - foot1.sx / 2 - 0.9, 0, foot1.sz / 2],
      b: [foot1.cx - foot1.sx / 2 - 0.9, -Df, foot1.sz / 2],
    }],
    cargas: cargasSobre(cols, { Df, cargas }),
    etiquetas: cols.map((c, i) => etiquetaColumna(`C${i + 1}`, c, fmtL)),
    notaArmado: null,
    notaAlcance: null,
  };
}

// ---------------------------------------------------------------------------
// Piezas comunes
// ---------------------------------------------------------------------------

function etiquetaColumna(nombre: string, c: Caja, fmtL: FormatoLongitud) {
  return {
    texto: `${nombre}  ${fmtL(c.sx)}×${fmtL(c.sz)}`,
    clase: "tag" as const,
    p: [c.cx, c.cy + c.sy / 2 + 0.14, c.cz] as [number, number, number],
  };
}

function cargasSobre(cols: Caja[], entrada: DatosEntrada): Carga[] {
  return cols
    .map((c, i) => {
      const q = entrada.cargas[i];
      return q ? { x: c.cx, z: c.cz, kN: q.kN, texto: q.texto } : null;
    })
    .filter((q): q is Carga => q !== null);
}

/** Cota de Df: dato de entrada del usuario, no del motor. Se añade a los modelos calculados. */
export function conCotaDf(m: ModeloVisor, fmtL: FormatoLongitud): ModeloVisor {
  if (m.tipo === "viga" || m.cotas.some((c) => c.id === "Df")) return m;
  const x = m.foot1.cx - m.foot1.sx / 2 - 0.9;
  const z = m.foot1.cz + m.foot1.sz / 2;
  return {
    ...m,
    cotas: [...m.cotas, { id: "Df", texto: `Df = ${fmtL(m.Df)}`, a: [x, 0, z], b: [x, -m.Df, z] }],
  };
}

// ---------------------------------------------------------------------------
// Transiciones entre tipologías (handoff: «Rutas de transición»)
// ---------------------------------------------------------------------------

export type Clave = Pick<ModeloVisor, "foot1" | "foot2" | "col1" | "col2" | "beam">;
const ELEMENTOS = ["foot1", "foot2", "col1", "col2", "beam"] as const;

export function interpolar(A: Clave, B: Clave, t: number): Clave {
  const R = {} as Clave;
  for (const k of ELEMENTOS) {
    const a = A[k], b = B[k];
    R[k] = {
      cx: a.cx + (b.cx - a.cx) * t, cy: a.cy + (b.cy - a.cy) * t, cz: a.cz + (b.cz - a.cz) * t,
      sx: a.sx + (b.sx - a.sx) * t, sy: a.sy + (b.sy - a.sy) * t, sz: a.sz + (b.sz - a.sz) * t,
      o: a.o + (b.o - a.o) * t,
    };
  }
  return R;
}

export const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export interface Ruta {
  claves: Clave[];
  etiquetas: string[];
}

const NOMBRE_TIPO: Record<Tipo, string> = {
  iso: "Aislada", comb: "Combinada", conn: "Conectada", viga: "Viga",
};
export const nombreTipo = (t: Tipo) => NOMBRE_TIPO[t];

/**
 * Los pasos intermedios del handoff, construidos entre los DOS modelos reales —el que
 * se ve y el que llega— y no desde un juego de parámetros común, porque en este programa
 * cada tipología tiene su propio cálculo. Cada fotograma clave toma de un extremo lo que
 * todavía no ha cambiado y del otro lo que ya cambió.
 */
export function ruta(A: ModeloVisor, B: ModeloVisor): Ruta {
  const orden: Tipo[] = ["iso", "comb", "conn"];
  const ia = orden.indexOf(A.tipo), ib = orden.indexOf(B.tipo);

  // Misma tipología, o viga: un único paso de geometría.
  if (A.tipo === B.tipo || ia < 0 || ib < 0) {
    return { claves: [A, B], etiquetas: [A.tipo === B.tipo ? "Actualizar geometría" : "Cambiar modelo"] };
  }
  if (ia > ib) {
    // Las inversas son la ida recorrida al revés, con sus rótulos propios.
    const ida = rutaAdelante(B, A);
    return { claves: [...ida.claves].reverse(), etiquetas: [...ida.inversas].reverse() };
  }
  const ida = rutaAdelante(A, B);
  return { claves: ida.claves, etiquetas: ida.etiquetas };
}

function rutaAdelante(A: ModeloVisor, B: ModeloVisor) {
  // col2 de llegada, visible; zapata 2 de llegada, plegada sobre su columna.
  const col2Viva = { ...B.col2, o: 1 };
  const foot2Plegada = { ...B.foot2, sx: 0, o: 0 };

  if (A.tipo === "iso" && B.tipo === "comb") {
    const pre: Clave = { ...A, col2: col2Viva, foot2: foot2Plegada, beam: A.beam };
    return {
      claves: [A, pre, B],
      etiquetas: ["Agregar columna C2", "Unificar zapata"],
      inversas: ["Retirar columna C2", "Reducir zapata"],
    };
  }
  if (A.tipo === "comb" && B.tipo === "conn") {
    const split: Clave = {
      foot1: B.foot1, col1: A.col1, col2: A.col2,
      foot2: { ...B.foot2, cx: A.col2.cx, o: 1 },
      beam: { ...B.beam, sx: 0, cx: B.col1.cx, o: 0 },
    };
    const conn0: Clave = { ...B, beam: { ...B.beam, sx: 0, cx: B.col1.cx + B.col1.sx / 2, o: 1 } };
    return {
      claves: [A, split, conn0, B],
      etiquetas: ["Separar cimentaciones", "Zapatas independientes", "Viga de conexión"],
      inversas: ["Unificar zapata", "Acercar zapatas", "Retirar viga"],
    };
  }
  // iso → conn: la columna C2 aparece, se le da zapata, se aleja y se une con la viga.
  const pre: Clave = { ...A, col2: { ...col2Viva, cx: A.col1.cx + (B.col2.cx - B.col1.cx) * 0.6 } };
  const split: Clave = {
    ...pre,
    foot2: { ...B.foot2, cx: pre.col2.cx, o: 1 },
  };
  const conn0: Clave = { ...B, beam: { ...B.beam, sx: 0, cx: B.col1.cx + B.col1.sx / 2, o: 1 } };
  return {
    claves: [A, pre, split, conn0, B],
    etiquetas: ["Agregar columna C2", "Zapata para C2", "Zapatas independientes", "Viga de conexión"],
    inversas: ["Retirar columna C2", "Retirar zapata Z-2", "Acercar zapatas", "Retirar viga"],
  };
}
