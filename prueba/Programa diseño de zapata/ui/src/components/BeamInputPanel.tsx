import { useEffect } from "react";
import type { BeamDesignRequest, LateralSystem, ReferenceData, UnitsInput } from "../lib/api";
import { ProjectPanel, UnitsPanel } from "./SharedInputs";

/**
 * Panel de entrada de la viga de conexión.
 *
 * Tres decisiones que conviene conocer al leer este archivo:
 *
 * 1. Los momentos y el cortante son DATOS DE ENTRADA. Provienen del análisis de la
 *    estructura; este programa no los deriva. La viga de conexión toma el par que
 *    genera la excentricidad de la zapata medianera, y ese reparto depende del
 *    modelo completo, no de la zapata aislada.
 *
 * 2. El perfil de suelo y la zona sísmica NO tienen valor por defecto. E.030 art.
 *    65.1 se dispara con (S3 o S4) Y (Zona 3 o 4), o con qadm < 0,10 MPa. Si el
 *    usuario no los declara, el motor dice que no pudo comprobar esa condición en
 *    vez de suponer que no aplica.
 *
 * 3. El sistema sismorresistente tampoco se supone. §21.12.3.3 remite a §21.4 o a
 *    §21.5 según el sistema, y §21.2 determina a cuál; sin sistema declarado el
 *    motor deja los requisitos adicionales sin resolver en lugar de elegir uno.
 *
 * Como en el resto de la interfaz, aquí NO hay ninguna ecuación de ingeniería.
 */

interface Props {
  value: BeamDesignRequest;
  onChange: (next: BeamDesignRequest) => void;
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

const PERFILES: { value: string; label: string }[] = [
  { value: "", label: "— Sin declarar —" },
  { value: "S0", label: "S0 — Roca dura" },
  { value: "S1", label: "S1 — Roca o suelos muy rígidos" },
  { value: "S2", label: "S2 — Suelos intermedios" },
  { value: "S3", label: "S3 — Suelos blandos" },
  { value: "S4", label: "S4 — Condiciones excepcionales" },
];

const SISTEMAS: { value: string; label: string }[] = [
  { value: "", label: "— Sin declarar —" },
  { value: "muros_estructurales", label: "Muros estructurales (R = 6) → §21.4" },
  { value: "dual_tipo_I", label: "Dual Tipo I (R = 7) → §21.4" },
  { value: "porticos", label: "Pórticos (R = 8) → §21.5" },
  { value: "dual_tipo_II", label: "Dual Tipo II (R = 7) → §21.5" },
];

/** Diámetros comerciales del catálogo peruano, en mm. */
const BARRAS: { value: number; label: string }[] = [
  { value: 12.7, label: '1/2" — 12,7 mm' },
  { value: 15.875, label: '5/8" — 15,88 mm' },
  { value: 19.05, label: '3/4" — 19,05 mm' },
  { value: 22.225, label: '7/8" — 22,23 mm' },
  { value: 25.4, label: '1" — 25,4 mm' },
  { value: 28.65, label: '1 1/8" — 28,65 mm' },
];

const ESTRIBOS: { value: number; label: string }[] = [
  { value: 7.938, label: '5/16" — 7,94 mm' },
  { value: 9.525, label: '3/8" — 9,53 mm' },
  { value: 12.7, label: '1/2" — 12,7 mm' },
];

export default function BeamInputPanel({
  value, onChange, onRun, running, reference, onUnitsChange, converting, proyecto, onListo,
}: Props) {
  const u = value.units;
  const set = (patch: Partial<BeamDesignRequest>) => onChange({ ...value, ...patch });
  const setSeismic = (patch: Partial<BeamDesignRequest["seismic"]>) =>
    onChange({ ...value, seismic: { ...value.seismic, ...patch } });

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
        {hint ? (
          <span className="hint-mark" aria-hidden="true">
            ?
          </span>
        ) : null}
      </label>
      <input
        type="number"
        step={step}
        value={v}
        onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    </div>
  );

  // El recubrimiento hasta el centroide del refuerzo es h − d; si d ≥ h no hay
  // sección que valga y el motor lo rechaza. Se avisa antes de enviar.
  const peralteInvalido = value.d_m >= value.h_m;
  useEffect(() => { onListo?.(!peralteInvalido); }, [peralteInvalido, onListo]);
  const sinContextoSismico =
    value.seismic.soil_profile === null || value.seismic.seismic_zone === null;
  const sistemaSinDeclarar =
    value.seismic.part_of_lateral_force_system && !value.seismic.lateral_system;

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

      <div className="panel">
        <h2>Geometría de la viga</h2>
        <div className="panel-body">
          <div className="combo-fields">
            {num(`b (${u.length})`, value.b_m, (n) => set({ b_m: n }))}
            {num(`h (${u.length})`, value.h_m, (n) => set({ h_m: n }))}
            {num(
              `d (${u.length})`,
              value.d_m,
              (n) => set({ d_m: n }),
              "Peralte efectivo: del borde comprimido al centroide del refuerzo en tracción. La diferencia h − d es el recubrimiento más medio diámetro.",
              0.01
            )}
          </div>
          <div className="combo-fields">
            {num(
              `Luz libre (${u.length})`,
              value.clear_span_m,
              (n) => set({ clear_span_m: n }),
              "Luz LIBRE entre caras de columna, no entre ejes. E.060 §21.12.3.2 mide sobre ella la dimensión mínima.",
              0.1
            )}
          </div>
          {peralteInvalido && (
            <div className="note fail">
              <strong>El peralte efectivo no puede alcanzar al total</strong>
              d = {value.d_m} debe ser menor que h = {value.h_m}: la diferencia es el
              recubrimiento hasta el centroide del refuerzo.
            </div>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Solicitaciones de diseño</h2>
        <div className="panel-body">
          <div className="note info">
            <strong>Estos valores no los calcula el programa</strong>
            M<sub>u</sub> y V<sub>u</sub> provienen del <em>análisis de la estructura</em>. La
            viga de conexión recibe el par que genera la excentricidad de la zapata medianera,
            y ese reparto depende del modelo completo. Aquí se verifica la sección frente a
            esas solicitaciones, no se derivan.
          </div>
          <div className="combo-fields">
            {num(
              `Mu⁻ (${u.moment})`,
              value.Mu_negative_kNm,
              (n) => set({ Mu_negative_kNm: n }),
              "Momento último NEGATIVO en magnitud: tracciona la cara superior.",
              1
            )}
            {num(
              `Mu⁺ (${u.moment})`,
              value.Mu_positive_kNm,
              (n) => set({ Mu_positive_kNm: n }),
              "Momento último POSITIVO en magnitud: tracciona la cara inferior.",
              1
            )}
            {num(`Vu (${u.force})`, value.Vu_kN, (n) => set({ Vu_kN: n }), undefined, 1)}
          </div>
          <div className="combo-fields">
            {num(
              `Σ Pu de la zapata (${u.force})`,
              value.sum_Pu_kN,
              (n) => set({ sum_Pu_kN: n }),
              "Carga vertical AMPLIFICADA de la zapata conectada. E.030 art. 65.1 mide sobre ella la fuerza axial mínima de 0,10·ΣPu.",
              1
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Materiales y refuerzo</h2>
        <div className="panel-body">
          <div className="combo-fields">
            {num(
              `f'c (${u.strength})`,
              value.materials.fc_MPa,
              (n) => onChange({ ...value, materials: { ...value.materials, fc_MPa: n } }),
              undefined,
              1
            )}
            {num(
              `fy (${u.strength})`,
              value.materials.fy_MPa,
              (n) => onChange({ ...value, materials: { ...value.materials, fy_MPa: n } }),
              undefined,
              10
            )}
          </div>
          <div className="combo-fields">
            <div className="combo-field">
              <label title="E.060 §21.12.3.2 acota la separación de estribos a 12 veces este diámetro.">
                Barra longitudinal
                <span className="hint-mark" aria-hidden="true">
                  ?
                </span>
              </label>
              <select
                value={value.longitudinal_db_mm}
                onChange={(e) => set({ longitudinal_db_mm: Number(e.target.value) })}
              >
                {BARRAS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="combo-field">
              <label>Estribo</label>
              <select
                value={value.stirrup_diameter_mm}
                onChange={(e) => set({ stirrup_diameter_mm: Number(e.target.value) })}
              >
                {ESTRIBOS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="combo-field">
              <label title="Número de ramas del estribo que cruzan la sección.">
                Ramas
                <span className="hint-mark" aria-hidden="true">
                  ?
                </span>
              </label>
              <input
                type="number"
                min={2}
                step={1}
                value={value.n_legs}
                onChange={(e) => set({ n_legs: Math.max(2, Number(e.target.value) || 2) })}
              />
            </div>
          </div>
          <div className="hint">
            Si no declara f<sub>yt</sub>, el motor toma mín(f<sub>y</sub>, 420 MPa) por E.060
            §11.5.2.
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Suelo y contexto sísmico</h2>
        <div className="panel-body">
          <div className="combo-fields">
            {num(
              `qadm (${u.pressure})`,
              value.soil.qadm_kPa,
              (n) => onChange({ ...value, soil: { ...value.soil, qadm_kPa: n } }),
              "E.030 art. 65.1 también se dispara con una presión admisible menor que 0,10 MPa (100 kPa).",
              5
            )}
            <div className="combo-field">
              <label>Perfil de suelo (E.030 art. 14)</label>
              <select
                value={value.seismic.soil_profile ?? ""}
                onChange={(e) => setSeismic({ soil_profile: e.target.value || null })}
              >
                {PERFILES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="combo-field">
              <label>Zona sísmica</label>
              <select
                value={value.seismic.seismic_zone ?? ""}
                onChange={(e) =>
                  setSeismic({ seismic_zone: e.target.value ? Number(e.target.value) : null })
                }
              >
                <option value="">— Sin declarar —</option>
                <option value="1">Zona 1</option>
                <option value="2">Zona 2</option>
                <option value="3">Zona 3</option>
                <option value="4">Zona 4</option>
              </select>
            </div>
          </div>

          {sinContextoSismico && (
            <div className="note warn">
              <strong>Sin perfil ni zona no puede comprobarse la condición completa</strong>
              E.030 art. 65.1 se dispara con (S3 o S4) <em>y</em> (Zona 3 o 4), o bien con
              q<sub>adm</sub> &lt; 0,10 MPa. Si los deja sin declarar, el motor solo evaluará
              el criterio de q<sub>adm</sub> y lo dirá expresamente: no dará por supuesto que
              el artículo no aplica.
            </div>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Sistema resistente a fuerzas laterales</h2>
        <div className="panel-body">
          <div className="checkbox">
            <input
              id="lfrs"
              type="checkbox"
              checked={value.seismic.part_of_lateral_force_system}
              onChange={(e) =>
                setSeismic({
                  part_of_lateral_force_system: e.target.checked,
                  lateral_system: e.target.checked ? value.seismic.lateral_system : null,
                })
              }
            />
            <label htmlFor="lfrs">
              La viga recibe <strong>flexión</strong> de columnas del sistema
              sismorresistente
            </label>
          </div>
          <div className="hint">
            E.060 §21.12.3.3 <em>no aplica siempre</em>: exige las dos condiciones a la vez —
            que las columnas conectadas formen parte del sistema sismorresistente y que le
            transmitan flexión. Una viga que solo ata zapatas para repartir el par no está
            alcanzada por ese artículo.
          </div>

          {value.seismic.part_of_lateral_force_system && (
            <>
              <div className="combo-field" style={{ marginTop: ".6rem" }}>
                <label>Sistema estructural del edificio</label>
                <select
                  value={value.seismic.lateral_system ?? ""}
                  onChange={(e) =>
                    setSeismic({
                      lateral_system: (e.target.value || null) as LateralSystem | null,
                    })
                  }
                >
                  {SISTEMAS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              {sistemaSinDeclarar && (
                <div className="note warn">
                  <strong>Sin sistema declarado no se resuelve a qué sección remite</strong>
                  §21.2 envía a §21.4 para muros estructurales y dual tipo I, y a §21.5 para
                  pórticos y dual tipo II. Los requisitos adicionales quedarán{" "}
                  <span className="badge NO VERIFICADO">NO VERIFICADO</span>.
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <button className="primary" onClick={onRun} disabled={running || peralteInvalido}>
        {running ? "Calculando…" : "Diseñar viga de conexión"}
      </button>
    </div>
  );
}
