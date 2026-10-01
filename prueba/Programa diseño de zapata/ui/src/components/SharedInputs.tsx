import type { MaterialsInput, ReferenceData, SoilInput, UnitsInput } from "../lib/api";

/**
 * Bloques de entrada COMUNES a las tres tipologías: unidades, materiales y suelo.
 *
 * POR QUÉ ESTÁN AQUÍ. Los DTOs de `MaterialsInput`, `SoilInput` y `UnitsInput` ya eran
 * los mismos para zapata aislada, combinada y conectada; solo la pantalla de la aislada
 * los exponía. Las otras dos calculaban con los valores del ejemplo (f'c 21 MPa, qadm
 * 150/250 kPa) sin que el usuario pudiera verlos ni cambiarlos. Duplicar el formulario
 * habría abierto la puerta a que una tipología acepte un campo que otra ignora en
 * silencio, que es justo lo que ya pasó con el vocabulario de estados.
 *
 * Aquí NO se calcula nada ni se convierte ningún valor: los desplegables de unidades
 * solo avisan del cambio, y quien reescribe los números es el motor a través de
 * `/api/units/rewrite`.
 */

export function Num({
  label, hint, value, onChange, step = 0.01, min, placeholder = "—",
}: {
  label: string; hint?: string; value: number | null;
  onChange: (v: number | null) => void; step?: number; min?: number; placeholder?: string;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <input
        type="number"
        step={step}
        min={min}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function UnitSelect({
  label, value, options, onChange,
}: {
  label: string; value: string;
  options: { value: string; label: string }[] | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {(options ?? [{ value, label: value }]).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

/** Desplegables de unidades. `onChange` entrega las unidades COMPLETAS ya cambiadas. */
export function UnitsPanel({
  units, reference, onChange, converting,
}: {
  units: UnitsInput;
  reference: ReferenceData | null;
  onChange: (next: UnitsInput) => void;
  converting?: boolean;
}) {
  const catalog = reference?.units;
  const set = (patch: Partial<UnitsInput>) => onChange({ ...units, ...patch });

  return (
    <div className="panel">
      <h2>Unidades</h2>
      <div className="panel-body">
        <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
          Elija las unidades en que quiere escribir y leer sus datos. Al cambiarlas, los
          valores ya escritos se convierten: el dato sigue siendo el mismo.
          {converting && <> <strong>Convirtiendo…</strong></>}
        </p>
        <div className="unit-bar">
          <UnitSelect label="Fuerza" value={units.force} options={catalog?.force}
            onChange={(v) => set({ force: v })} />
          <UnitSelect label="Momento" value={units.moment} options={catalog?.moment}
            onChange={(v) => set({ moment: v })} />
          <UnitSelect label="Presión del suelo" value={units.pressure} options={catalog?.pressure}
            onChange={(v) => set({ pressure: v })} />
          <UnitSelect label="Resistencia (f'c, fy)" value={units.strength} options={catalog?.strength}
            onChange={(v) => set({ strength: v })} />
          <UnitSelect label="Longitud" value={units.length} options={catalog?.length}
            onChange={(v) => set({ length: v })} />
          <UnitSelect label="Peso unitario" value={units.unit_weight} options={catalog?.unit_weight}
            onChange={(v) => set({ unit_weight: v })} />
        </div>
        {reference?.rounding_note && (
          <div className="hint" style={{ marginTop: 8 }}>{reference.rounding_note}</div>
        )}
      </div>
    </div>
  );
}

/**
 * Nombre del proyecto y el guardado en archivo.
 *
 * El archivo contiene la petición completa —lo que el motor necesita para reproducir el
 * cálculo—, no los resultados: al abrirlo se recalcula con el motor de hoy. Ver
 * `lib/project.ts`.
 */
export function ProjectPanel({
  nombre, onNombre, onGuardar, onAbrir, aviso,
}: {
  nombre: string;
  onNombre: (v: string) => void;
  onGuardar: () => void;
  onAbrir: (archivo: File) => void;
  aviso?: string | null;
}) {
  return (
    <div className="panel">
      <h2>Proyecto</h2>
      <div className="panel-body">
        <div className="field">
          <label>Nombre</label>
          <input type="text" value={nombre} onChange={(e) => onNombre(e.target.value)} />
        </div>
        <div className="grid2">
          <button type="button" onClick={onGuardar}>Guardar en archivo</button>
          <label className="boton-archivo">
            Abrir archivo…
            <input
              type="file"
              accept=".json,application/json"
              onChange={(e) => {
                const archivo = e.target.files?.[0];
                // Se limpia el input para poder volver a abrir el MISMO archivo después
                // de editarlo: sin esto el navegador no emite un segundo `change`.
                e.target.value = "";
                if (archivo) onAbrir(archivo);
              }}
            />
          </label>
        </div>
        <div className="hint">
          El archivo guarda los datos de entrada, no los resultados: al abrirlo se vuelve a
          calcular. Además, esta pantalla recuerda lo último que escribió en este navegador.
        </div>
        {aviso && <div className="note fail" style={{ marginTop: 10 }}>{aviso}</div>}
      </div>
    </div>
  );
}

export function MaterialsPanel({
  materials, units, onChange,
}: {
  materials: MaterialsInput; units: UnitsInput;
  onChange: (patch: Partial<MaterialsInput>) => void;
}) {
  return (
    <div className="panel">
      <h2>Materiales</h2>
      <div className="panel-body">
        <div className="grid2">
          <Num label={`f'c (${units.strength})`} hint="mín. 17 MPa (§9.4)" value={materials.fc_MPa}
            onChange={(v) => onChange({ fc_MPa: v ?? 0 })} step={1} />
          <Num label={`fy (${units.strength})`} hint="máx. 550 MPa (§9.5)" value={materials.fy_MPa}
            onChange={(v) => onChange({ fy_MPa: v ?? 0 })} step={10} />
        </div>
        <Num
          label={`Peso unitario del concreto (${units.unit_weight})`}
          hint="supuesto de proyecto, no normativo"
          value={materials.concrete_unit_weight_kNm3}
          onChange={(v) => onChange({ concrete_unit_weight_kNm3: v ?? 0 })}
          step={0.1}
        />
      </div>
    </div>
  );
}

/**
 * Suelo, estabilidad y las disposiciones potestativas de E.060 §15.2.
 *
 * `prefijo` distingue los `id` de las casillas cuando dos paneles conviven en la misma
 * página; sin él, pulsar una etiqueta activaría la casilla de la otra tipología.
 */
export function SoilPanel({
  soil, units, onChange, missingStability = false, prefijo = "",
}: {
  soil: SoilInput; units: UnitsInput;
  onChange: (patch: Partial<SoilInput>) => void;
  missingStability?: boolean;
  prefijo?: string;
}) {
  const id = (n: string) => `${prefijo}${n}`;

  return (
    <div className="panel">
      <h2>Suelo</h2>
      <div className="panel-body">
        <div className="grid2">
          <Num label={`q admisible (${units.pressure})`} value={soil.qadm_kPa}
            onChange={(v) => onChange({ qadm_kPa: v ?? 0 })} step={0.1} />
          <div className="field">
            <label>Base de la presión</label>
            <select
              value={soil.pressure_basis}
              onChange={(e) => onChange({ pressure_basis: e.target.value as "BRUTA" | "NETA" })}
            >
              <option value="BRUTA">Bruta</option>
              <option value="NETA">Neta</option>
            </select>
            <div className="hint">Declarar cuál entrega el EMS</div>
          </div>
        </div>
        <div className="grid2">
          <Num label={`γ del suelo (${units.unit_weight})`} value={soil.gamma_kNm3}
            onChange={(v) => onChange({ gamma_kNm3: v ?? 0 })} step={0.1} />
          <Num label={`Df (${units.length})`} value={soil.Df_m}
            onChange={(v) => onChange({ Df_m: v ?? 0 })} />
        </div>

        <div className="checkbox">
          <input id={id("roca")} type="checkbox" checked={soil.founded_on_rock}
            onChange={(e) => onChange({ founded_on_rock: e.target.checked })} />
          <label htmlFor={id("roca")}>Cimentación sobre roca (E.050 art. 26.2)</label>
        </div>

        <h4>Estabilidad (solo si hay fuerzas horizontales)</h4>
        <div className="grid3">
          <Num label="μ suelo-concreto" hint="sin default" value={soil.mu_friction_soil_concrete}
            onChange={(v) => onChange({ mu_friction_soil_concrete: v })} />
          <Num label="FS deslizam." hint="lo adopta Ud." value={soil.FS_sliding_required}
            onChange={(v) => onChange({ FS_sliding_required: v })} step={0.05} />
          <Num label="FS volcam." hint="lo adopta Ud." value={soil.FS_overturning_required}
            onChange={(v) => onChange({ FS_overturning_required: v })} step={0.05} />
        </div>
        <Num label={`Cohesión (${units.pressure})`} hint="opcional; sin valor no se suma"
          value={soil.cohesion_kPa} onChange={(v) => onChange({ cohesion_kPa: v })} step={0.1} />
        {missingStability && (
          <div className="note warn">
            <strong>Estabilidad quedará NO VERIFICADO</strong>
            Hay fuerzas horizontales pero falta μ. El programa no inventa parámetros
            geotécnicos: sin él no puede juzgar el deslizamiento.
          </div>
        )}

        <h4>Disposiciones opcionales de E.060 §15.2</h4>
        <div className="checkbox">
          <input id={id("inc30")} type="checkbox" checked={soil.allow_temporary_increase_30pct}
            onChange={(e) => onChange({ allow_temporary_increase_30pct: e.target.checked })} />
          <label htmlFor={id("inc30")}>Incrementar qadm 30 % en combinaciones con sismo/viento</label>
        </div>
        <div className="checkbox">
          <input id={id("red80")} type="checkbox" checked={soil.allow_seismic_reduction_80pct}
            onChange={(e) => onChange({ allow_seismic_reduction_80pct: e.target.checked })} />
          <label htmlFor={id("red80")}>
            Solicitar reducción sísmica al 80 % (E.030 art. 29; solo con el modo por casos)
          </label>
        </div>

        <h4>Excentricidad fuera del núcleo central</h4>
        <div className="note info">
          <strong>Qué hace el programa por defecto</strong>
          Si la resultante se sale del núcleo central, la distribución lineal produciría
          tracciones —que E.060 §15.2.3 no admite— y la alternativa se descarta. E.050
          art. 28 sí da un método para ese caso: el área efectiva B′ = B − 2|ex|, L′ = L − 2|ey|.
        </div>
        <div className="checkbox">
          <input id={id("areaEf")} type="checkbox" checked={soil.use_effective_area_e050_art28}
            onChange={(e) => onChange({ use_effective_area_e050_art28: e.target.checked })} />
          <label htmlFor={id("areaEf")}>
            Aplicar el área efectiva de E.050 art. 28 fuera del núcleo central
          </label>
        </div>
        {soil.use_effective_area_e050_art28 && (
          <>
            <div className="note warn">
              <strong>Dentro del núcleo no cambia nada</strong>
              Sigue rigiendo el pico de la distribución lineal, que es el criterio más
              estricto. Activar esta opción solo puede <em>añadir</em> geometrías que antes
              se descartaban; ninguna de las que ya pasaban cambia de resultado.
            </div>
            <div className="checkbox">
              <input id={id("qadmEf")} type="checkbox"
                checked={soil.qadm_declared_for_effective_area}
                onChange={(e) => onChange({ qadm_declared_for_effective_area: e.target.checked })} />
              <label htmlFor={id("qadmEf")}>
                Declaro que el qadm indicado vale para las dimensiones efectivas B′×L′
              </label>
            </div>
            {!soil.qadm_declared_for_effective_area && (
              <div className="note warn">
                <strong>Sin esa declaración el resultado será NO VERIFICADO</strong>
                El EMS obtiene el qadm para la zapata real B×L, y la capacidad portante de
                una zapata más estrecha no es la misma. Un <em>incumplimiento</em> sí se
                afirma; un cumplimiento, no.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
