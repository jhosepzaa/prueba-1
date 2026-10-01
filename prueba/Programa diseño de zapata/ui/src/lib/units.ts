import type { ReferenceData, UnitsInput } from "./api";

/**
 * PRESENTACIÓN de resultados en las unidades que eligió el usuario.
 *
 * El motor calcula y responde SIEMPRE en SI (kN, kN·m, kPa, MPa, m, kN/m³). Esto solo
 * decide en qué unidad se ESCRIBE ese mismo número en pantalla.
 *
 * DE DÓNDE SALEN LOS FACTORES. De `/api/reference`, que los toma de
 * `engine/units/unit_registry.py`. La interfaz no declara ninguna equivalencia por su
 * cuenta: si mañana cambia un factor, cambia en el motor y aquí se refleja solo. Lo
 * único que vive aquí son los NOMBRES de las unidades SI, para poder rotular mientras
 * el catálogo aún no ha llegado del servidor.
 *
 * Las ENTRADAS no se convierten aquí: eso lo hace el motor en `/api/units/rewrite`.
 */

export type Magnitud = "force" | "moment" | "pressure" | "strength" | "length" | "unit_weight";

/** Nombres —no factores— de la unidad SI de cada magnitud. Ver comentario de arriba. */
const UNIDAD_SI: Record<Magnitud, string> = {
  force: "kN",
  moment: "kN·m",
  pressure: "kPa",
  strength: "MPa",
  length: "m",
  unit_weight: "kN/m³",
};

/** Decimales por omisión de cada magnitud, pensados para la unidad SI. */
const DECIMALES: Record<Magnitud, number> = {
  force: 1,
  moment: 1,
  pressure: 1,
  strength: 1,
  length: 3,
  unit_weight: 1,
};

export interface Formateador {
  /** Rótulo de la unidad elegida para esa magnitud, p. ej. "tonf·m (t·m)" → "tonf·m". */
  unidad(m: Magnitud): string;
  /** El valor SI expresado en la unidad elegida. Sin redondear. */
  valor(si: number | null | undefined, m: Magnitud): number | null;
  /**
   * Lo inverso: un dato que el usuario escribió en su unidad, llevado a SI. Solo para
   * DIBUJAR (Df, cargas y secciones en el visor 3D); el cálculo lo convierte el motor.
   */
  si(valorUsuario: number | null | undefined, m: Magnitud): number | null;
  /** El número ya escrito, sin la unidad. */
  texto(si: number | null | undefined, m: Magnitud, decimales?: number): string;
  /** El número con su unidad detrás. */
  con(si: number | null | undefined, m: Magnitud, decimales?: number): string;
  /** true mientras se usan los factores de reserva (catálogo no cargado). */
  enSI: boolean;
}

/**
 * Los rótulos del catálogo llevan la aclaración entre paréntesis —"tonf (t)"— que es
 * útil en un desplegable y estorba dentro de una tabla.
 */
function rotuloCorto(unidad: string): string {
  return unidad;
}

export function crearFormateador(
  units: UnitsInput | undefined,
  reference: ReferenceData | null,
): Formateador {
  const catalogo = reference?.units;

  const factor = (m: Magnitud): number | null => {
    const elegida = units?.[m];
    if (!elegida) return null;
    const opcion = catalogo?.[m]?.find((o) => o.value === elegida);
    return opcion && typeof opcion.to_si === "number" && opcion.to_si > 0 ? opcion.to_si : null;
  };

  const unidad = (m: Magnitud): string => {
    const f = factor(m);
    return f === null ? UNIDAD_SI[m] : rotuloCorto(units![m]);
  };

  const valor = (si: number | null | undefined, m: Magnitud): number | null => {
    if (si === null || si === undefined || !Number.isFinite(si)) return null;
    const f = factor(m);
    return f === null ? si : si / f;
  };

  /**
   * Decimales de la unidad elegida. Solo se ajustan en LONGITUD: los que pide quien
   * llama están pensados para metros, y en cm o mm sobran cifras —2,50 m escritos
   * «250.00 cm» fingen precisión de centésima de milímetro—, así que se descuenta un
   * decimal por orden de magnitud sin perder precisión absoluta.
   *
   * En las demás magnitudes no se toca: recortar un decimal en kgf/cm² convertiría un
   * f'c declarado de 211,5 en «212», y el dato del proyectista se escribe como lo
   * escribió él. Misma regla que `engine/reports/report_units.py`.
   */
  const decimalesDe = (m: Magnitud, pedidos: number): number => {
    if (m !== "length") return pedidos;
    const f = factor(m);
    if (f === null || f >= 1) return pedidos;
    return Math.max(0, pedidos + Math.round(Math.log10(f)));
  };

  const texto = (si: number | null | undefined, m: Magnitud, decimales?: number): string => {
    const v = valor(si, m);
    if (v === null) return "—";
    return v.toFixed(decimalesDe(m, decimales ?? DECIMALES[m]));
  };

  const si = (v: number | null | undefined, m: Magnitud): number | null => {
    if (v === null || v === undefined || !Number.isFinite(v)) return null;
    const f = factor(m);
    return f === null ? v : v * f;
  };

  return {
    unidad,
    valor,
    si,
    texto,
    con: (si, m, decimales) => `${texto(si, m, decimales)} ${unidad(m)}`,
    enSI: (["force", "moment", "pressure", "strength", "length", "unit_weight"] as Magnitud[])
      .every((m) => factor(m) === null),
  };
}
