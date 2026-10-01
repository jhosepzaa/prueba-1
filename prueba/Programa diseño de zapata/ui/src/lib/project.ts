import { rewriteUnits, type Tipologia, type UnitsInput } from "./api";
import { normalizarColumnas } from "./columna";

/**
 * Guardar y abrir un proyecto.
 *
 * QUÉ ES UN PROYECTO. La petición completa de una tipología: columnas, cargas,
 * materiales, suelo, unidades y rangos de búsqueda. Es exactamente lo que el motor
 * necesita para reproducir un cálculo, de modo que el archivo no inventa ningún formato
 * propio: guarda la petición tal cual, con una cabecera que dice qué es.
 *
 * QUÉ NO GUARDA: los resultados. Se vuelven a calcular desde la petición, que es lo que
 * garantiza que lo que se ve corresponda al motor de HOY y no a una versión anterior
 * cuyos números podrían haber cambiado por una corrección.
 *
 * VALIDACIÓN AL ABRIR. Un archivo es un dato externo, no una orden: antes de cargarlo se
 * valida contra el contrato de la API —el mismo `pydantic` que valida un cálculo— y solo
 * se acepta lo que pasa. Un archivo de otra tipología, recortado o manipulado se rechaza
 * con un mensaje, en vez de dejar la pantalla en un estado imposible.
 */

export const FORMATO = "zapata-proyecto";
export const VERSION_FORMATO = 1;

const UNIDADES_SI: UnitsInput = {
  force: "kN", moment: "kN·m", pressure: "kPa",
  strength: "MPa", length: "m", unit_weight: "kN/m³",
};

const TIPOLOGIAS: Tipologia[] = ["aislada", "combinada", "conectada", "viga"];

const NOMBRE_TIPOLOGIA: Record<Tipologia, string> = {
  aislada: "zapata aislada",
  combinada: "zapata combinada",
  conectada: "cimentación conectada",
  viga: "viga de conexión",
};

export interface ArchivoProyecto<T = unknown> {
  formato: string;
  version: number;
  tipologia: Tipologia;
  guardado_en: string;
  peticion: T;
}

function nombreDeArchivo(nombre: string, tipologia: Tipologia): string {
  const limpio = (nombre || "proyecto")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\w\s.-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 60) || "proyecto";
  return `${limpio}-${tipologia}.zapata.json`;
}

/** Descarga el proyecto como archivo. El navegador decide dónde se guarda. */
export function guardarProyecto<T extends { project_name?: string }>(
  tipologia: Tipologia,
  peticion: T,
): void {
  const contenido: ArchivoProyecto<T> = {
    formato: FORMATO,
    version: VERSION_FORMATO,
    tipologia,
    guardado_en: new Date().toISOString(),
    peticion,
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(contenido, null, 2)], { type: "application/json" }),
  );
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreDeArchivo(peticion.project_name ?? "", tipologia);
  enlace.click();
  URL.revokeObjectURL(url);
}

/**
 * Lee un archivo de proyecto y devuelve la petición YA VALIDADA por el motor.
 *
 * La validación se hace pidiéndole al servidor que reescriba la petición a sus propias
 * unidades: la conversión no cambia nada, pero el contrato de la API sí la valida entera
 * y devuelve los campos que falten con su valor por omisión. Así no hay una segunda
 * definición de «petición válida» viviendo en la interfaz.
 */
export async function abrirProyecto(
  archivo: File,
): Promise<{ tipologia: Tipologia; peticion: Record<string, unknown> }> {
  let crudo: unknown;
  try {
    crudo = JSON.parse(await archivo.text());
  } catch {
    throw new Error("El archivo no es un JSON legible.");
  }

  const datos = crudo as Partial<ArchivoProyecto<Record<string, unknown>>>;
  if (datos?.formato !== FORMATO) {
    throw new Error(
      "El archivo no es un proyecto de este programa (falta la marca de formato).",
    );
  }
  if (datos.version !== VERSION_FORMATO) {
    throw new Error(
      `El archivo está en el formato ${datos.version}, y este programa lee el ` +
        `${VERSION_FORMATO}. No se abre: cargarlo a medias daría un proyecto distinto ` +
        "del que usted guardó.",
    );
  }
  const tipologia = datos.tipologia as Tipologia;
  if (!TIPOLOGIAS.includes(tipologia)) {
    throw new Error(`El archivo dice ser de la tipología «${datos.tipologia}», que no existe.`);
  }
  if (!datos.peticion || typeof datos.peticion !== "object") {
    throw new Error("El archivo no contiene ningún proyecto.");
  }

  // Proyectos guardados antes de que la forma de la columna siguiera a sus dimensiones.
  const peticion = normalizarColumnas(datos.peticion) as Record<string, unknown> & { units?: UnitsInput };
  const units = peticion.units ?? UNIDADES_SI;
  try {
    const validada = await rewriteUnits(
      tipologia,
      { ...peticion, units } as Record<string, unknown> & { units: UnitsInput },
      units,
    );
    return { tipologia, peticion: validada as Record<string, unknown> };
  } catch {
    throw new Error(
      `El archivo no es un proyecto válido de ${NOMBRE_TIPOLOGIA[tipologia]}: el motor lo ` +
        "rechazó. Si lo editó a mano, compruebe que no falte ningún dato.",
    );
  }
}

// --- Memoria del navegador -----------------------------------------------------
// Lo último escrito en cada tipología, para no volver a teclearlo al abrir el programa.
// Vive SOLO en este navegador y no sustituye a guardar el archivo: si el formato cambia
// o el almacenamiento está bloqueado, se descarta en silencio y la pantalla arranca con
// el ejemplo, que es lo que hacía antes.

const CLAVE = (tipologia: Tipologia) => `zapata:proyecto:${tipologia}:v${VERSION_FORMATO}`;

export function recordar<T>(tipologia: Tipologia, peticion: T): void {
  try {
    localStorage.setItem(CLAVE(tipologia), JSON.stringify(peticion));
  } catch {
    /* modo privado, cuota llena o almacenamiento bloqueado: no es un error del programa */
  }
}

export function recuperar<T>(tipologia: Tipologia): T | null {
  try {
    const guardado = localStorage.getItem(CLAVE(tipologia));
    return guardado ? normalizarColumnas(JSON.parse(guardado) as T) : null;
  } catch {
    return null;
  }
}

export function olvidar(tipologia: Tipologia): void {
  try {
    localStorage.removeItem(CLAVE(tipologia));
  } catch {
    /* ídem */
  }
}
