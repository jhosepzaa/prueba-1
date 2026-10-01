/**
 * Forma y dimensiones de una columna en los paneles de entrada.
 *
 * El motor (`engine/domain/column.py`) rechaza una columna «cuadrada» con bx ≠ by, y
 * con razón: el rótulo tiene que decir la verdad. La forma no interviene en ningún
 * cálculo —solo se valida y se imprime en el informe—, así que la interfaz la hace
 * seguir a las dimensiones en vez de dejar que el usuario llegue a esa contradicción:
 *
 * - escribir bx o by nunca toca la otra dimensión;
 * - si quedan distintas, la columna pasa a «rectangular»;
 * - si quedan iguales, conserva la forma elegida (una rectangular de lados iguales es
 *   válida);
 * - elegir «cuadrada» en el selector iguala by a bx.
 */

export type FormaColumna = "cuadrada" | "rectangular";

interface ColumnaEditable {
  shape?: string;
  bx_m: number;
  by_m: number;
}

type Forma<C extends ColumnaEditable> = Pick<C, "shape" | "bx_m" | "by_m">;

/** Cambio de una dimensión, con la forma que le corresponde. */
export function conDimension<C extends ColumnaEditable>(
  c: C,
  cambio: { bx_m: number } | { by_m: number },
): Forma<C> {
  const bx_m = "bx_m" in cambio ? cambio.bx_m : c.bx_m;
  const by_m = "by_m" in cambio ? cambio.by_m : c.by_m;
  const shape: FormaColumna | string = Math.abs(bx_m - by_m) > 1e-9 ? "rectangular" : (c.shape ?? "cuadrada");
  // Las dos formas que produce esta función existen en todos los contratos de columna.
  return { shape, bx_m, by_m } as Forma<C>;
}

/** Cambio de forma desde el selector (cuyas opciones son «cuadrada» y «rectangular»). */
export function conForma<C extends ColumnaEditable>(c: C, shape: string): Forma<C> {
  return { shape, bx_m: c.bx_m, by_m: shape === "cuadrada" ? c.bx_m : c.by_m } as Forma<C>;
}

/** ¿Es una columna declarada «cuadrada» con lados distintos? */
function cuadradaContradictoria(c: unknown): c is ColumnaEditable {
  if (!c || typeof c !== "object") return false;
  const k = c as ColumnaEditable;
  return k.shape === "cuadrada" && typeof k.bx_m === "number" && typeof k.by_m === "number"
    && Math.abs(k.bx_m - k.by_m) > 1e-9;
}

/**
 * Corrige la forma de las columnas de una petición que llega de fuera de los paneles:
 * lo recordado por el navegador o un proyecto abierto desde archivo. Pudieron escribirse
 * antes de que la forma siguiera a las dimensiones, y una «cuadrada» de 0,80 × 0,35 el
 * motor la rechaza. Las dimensiones son lo que el usuario escribió; la forma era el valor
 * por omisión: se corrige la forma, nunca una dimensión.
 *
 * Devuelve la MISMA petición si no hay nada que corregir.
 */
export function normalizarColumnas<T>(peticion: T): T {
  if (!peticion || typeof peticion !== "object") return peticion;
  const p = peticion as Record<string, unknown>;
  const arreglar = (c: unknown) => (cuadradaContradictoria(c) ? { ...c, shape: "rectangular" } : c);
  const salida: Record<string, unknown> = { ...p };
  let cambio = false;
  // Aislada: column. Conectada: exterior e interior. Combinada: columns[].
  for (const clave of ["column", "exterior", "interior"]) {
    if (cuadradaContradictoria(p[clave])) {
      salida[clave] = arreglar(p[clave]);
      cambio = true;
    }
  }
  if (Array.isArray(p.columns) && p.columns.some(cuadradaContradictoria)) {
    salida.columns = p.columns.map(arreglar);
    cambio = true;
  }
  return cambio ? (salida as T) : peticion;
}
