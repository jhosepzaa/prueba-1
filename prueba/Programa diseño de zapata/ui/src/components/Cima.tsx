import type { ReactNode } from "react";
import type { Tipologia } from "../lib/api";
import type { Propiedades } from "../viewer3d/datos";

/**
 * Armazón con el formato del handoff «Cimentación 3D» (CIMA): cabecera con el selector
 * de tipología, panel de propiedades, dock de resultados y cajón de datos.
 *
 * Solo presenta. Toda la lógica —qué tipología, qué resultado, qué alternativa— vive en
 * `App.tsx`; los datos del panel llegan ya resueltos de `viewer3d/datos.ts`.
 */

// --- Glifos de planta del selector (30×18, como el diseño) ---------------------

const Glifo = ({ children }: { children: ReactNode }) => <span className="gl" aria-hidden="true">{children}</span>;

const GLIFOS: Record<Tipologia, ReactNode> = {
  aislada: (
    <Glifo>
      <i className="f" style={{ left: 9, width: 12 }} />
      <i className="c" style={{ left: 13 }} />
    </Glifo>
  ),
  combinada: (
    <Glifo>
      <i className="f" style={{ left: 1, width: 28 }} />
      <i className="c" style={{ left: 6 }} />
      <i className="c" style={{ left: 20 }} />
    </Glifo>
  ),
  conectada: (
    <Glifo>
      <i className="f" style={{ left: 0, width: 10 }} />
      <i className="f" style={{ left: 20, width: 10 }} />
      <i className="b" style={{ left: 10, width: 10 }} />
      <i className="c" style={{ left: 3 }} />
      <i className="c" style={{ left: 23 }} />
    </Glifo>
  ),
  viga: (
    <Glifo>
      <i className="b" style={{ left: 2, width: 26, height: 4, top: 7 }} />
      <i className="c" style={{ left: 2, top: 11 }} />
      <i className="c" style={{ left: 24, top: 11 }} />
    </Glifo>
  ),
};

const NOMBRES: Record<Tipologia, string> = {
  aislada: "Aislada",
  combinada: "Combinada",
  conectada: "Conectada",
  viga: "Viga",
};

// --- Cabecera -----------------------------------------------------------------

export function CimaHeader({
  proyecto,
  tipologia,
  onTipologia,
  unidades,
  datosAbiertos,
  onDatos,
  onGuardar,
  onAbrir,
  onCalcular,
  puedeCalcular,
  calculando,
  textoCalcular,
  conResultado,
}: {
  proyecto: string;
  tipologia: Tipologia;
  onTipologia: (t: Tipologia) => void;
  unidades: string;
  datosAbiertos: boolean;
  onDatos: () => void;
  onGuardar: () => void;
  onAbrir: (f: File) => void;
  onCalcular: () => void;
  puedeCalcular: boolean;
  calculando: boolean;
  textoCalcular: string;
  conResultado: Record<Tipologia, boolean>;
}) {
  return (
    <header className="cima-header">
      <div className="brand">
        <div className="mark" aria-hidden="true" />
        <b>CIMA</b>
        <div className="div" />
        <span className="sub" title={proyecto}>{proyecto || "Proyecto sin nombre"}</span>
      </div>

      <div className="typo">
        <span className="cap">Tipo de cimentación</span>
        <div className="seg big" role="tablist" aria-label="Tipo de cimentación">
          {(Object.keys(NOMBRES) as Tipologia[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tipologia === t}
              className={tipologia === t ? "on" : ""}
              onClick={() => onTipologia(t)}
            >
              {GLIFOS[t]}
              {NOMBRES[t]}
              {conResultado[t] && <span className="hecho" title="Con resultado" />}
            </button>
          ))}
        </div>
      </div>

      <div className="acciones">
        <span className="units">{unidades}</span>
        <button className={`cima-btn datos ${datosAbiertos ? "on" : ""}`} onClick={onDatos} aria-pressed={datosAbiertos}>
          Datos
        </button>
        <button className="cima-btn ghost solo-ancho" onClick={onGuardar} title="Guardar el proyecto en un archivo">Guardar</button>
        <label className="cima-btn ghost solo-ancho" title="Abrir un proyecto guardado">
          Abrir
          <input
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) onAbrir(f);
            }}
          />
        </label>
        <button
          className="cima-btn acento"
          onClick={onCalcular}
          disabled={!puedeCalcular || calculando}
          title={puedeCalcular ? undefined : "Faltan datos obligatorios: el cajón Datos indica cuáles"}
        >
          {calculando ? "Calculando…" : textoCalcular}
        </button>
      </div>
    </header>
  );
}

// --- Panel de propiedades --------------------------------------------------------

const CLASE_ESTADO: Record<string, string> = {
  PASS: "ok", INFO: "ok", CONFORME: "ok",
  WARNING: "warn", "ACEPTADA CON OBSERVACIONES": "warn",
  "NO VERIFICADO": "nv", "NO VERIFICADA": "nv",
  FAIL: "bad", RECHAZADA: "bad",
};

export function PanelPropiedades({ p, onEditar }: { p: Propiedades; onEditar: () => void }) {
  return (
    <aside className="props" aria-label="Propiedades">
      <div className="ph">
        <div className="k">{p.codigo}</div>
        <div className="t">{p.titulo}</div>
        <div className="d">{p.descripcion}</div>
        {(p.alternativa || p.estado) && (
          <div className="ph-estado">
            {p.alternativa && <span className="alt">{p.alternativa}</span>}
            {p.estado && <span className={`est ${CLASE_ESTADO[p.estado] ?? "nv"}`}>{p.estado}</span>}
          </div>
        )}
        {p.aviso && <div className="ph-aviso">{p.aviso}</div>}
      </div>

      {p.secciones.map((s) => (
        <section key={s.titulo} className={s.resumen ? "sum" : ""}>
          <h3>{s.titulo}</h3>
          {s.filas.map((f, i) => (
            <div className="row" key={f.lb + i}>
              <span className="sym">{f.sym}</span>
              <span className="lb" title={f.lb}>{f.lb}</span>
              <span className={`ro ${f.nota ? "ro-nota" : ""}`}>{f.valor}</span>
            </div>
          ))}
        </section>
      ))}

      <div className="props-pie">
        Los valores son del motor y de sus datos de entrada: aquí no se editan. Para cambiar un
        dato, <button className="enlace" onClick={onEditar}>ábralo en Datos</button> y vuelva a calcular.
      </div>
    </aside>
  );
}

// --- Dock de resultados ------------------------------------------------------------

export type EstadoDock = "cerrado" | "medio" | "completo";

export function DockResultados({
  estado,
  onEstado,
  resumen,
  children,
}: {
  estado: EstadoDock;
  onEstado: (e: EstadoDock) => void;
  resumen: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={`dock ${estado}`} aria-label="Resultados">
      <div className="dock-bar">
        <button
          className="dock-titulo"
          onClick={() => onEstado(estado === "cerrado" ? "medio" : "cerrado")}
          aria-expanded={estado !== "cerrado"}
        >
          <span className={`chev ${estado === "cerrado" ? "" : "abierto"}`} aria-hidden="true" />
          Resultados
        </button>
        <div className="dock-resumen">{resumen}</div>
        <div className="seg sm">
          <button className={estado === "medio" ? "on" : ""} onClick={() => onEstado("medio")}>Mitad</button>
          <button className={estado === "completo" ? "on" : ""} onClick={() => onEstado("completo")}>Completo</button>
          <button className={estado === "cerrado" ? "on" : ""} onClick={() => onEstado("cerrado")}>Ocultar</button>
        </div>
      </div>
      {estado !== "cerrado" && <div className="dock-cuerpo">{children}</div>}
    </section>
  );
}

// --- Cajón de datos ------------------------------------------------------------------

export function CajonDatos({ abierto, onCerrar, children }: { abierto: boolean; onCerrar: () => void; children: ReactNode }) {
  return (
    <aside className={`cajon ${abierto ? "abierto" : ""}`} aria-label="Datos del proyecto" aria-hidden={!abierto}>
      <div className="cajon-cab">
        <div>
          <div className="k">Entradas</div>
          <div className="t">Datos del proyecto</div>
        </div>
        <button className="cima-btn ghost" onClick={onCerrar} aria-label="Cerrar datos">Cerrar</button>
      </div>
      <div className="cajon-cuerpo">{children}</div>
    </aside>
  );
}
