# Diff de baselines por `FORMULACION_VOLTEO`

Fecha: 2026-09-19. Estado: **aprobado por el usuario y ejecutado.** Verificación en §8.

`CLAUDE.md` §4 y §11: «implementa X» no autoriza a tocar baselines. Este documento es el
diff por caso que se revisó antes de la regeneración dirigida y la verificación de lo que
quedó después. El análisis que motivó la decisión está en
[`formulacion_volteo_analisis.md`](formulacion_volteo_analisis.md).

---

## 1. Qué cambió

El momento volcador de la zapata **aislada** —y con ella el de las zapatas de la
**conectada**, que reutilizan su motor— pasó a ser

```
M_volc = max(|M_total|, |M_estabilizante|) + |H|·h
M_total         = M + P·offset
M_estabilizante = Σ_estab (M_k + P_k·offset)        (mismo conjunto que N, E.020 art. 20.1)
```

que es la formulación que la **combinada** ya usaba desde el pendiente 7. Las tres
tipologías comparten ahora un solo ayudante, `engine.soil.stability.axis_moments_kNm`.

No cambió ninguna otra magnitud: ni presiones, ni acero, ni punzonamiento, ni cortante, ni
la geometría elegida por ningún barrido.

## 2. Dos cosas distintas, aprobadas juntas

| | Qué es | Respaldo |
|---|---|---|
| Término `P·offset` | **Estática.** El brazo real de la carga de columna es `dim/2 − offset` | Ninguna norma lo prescribe ni hace falta: es equilibrio. Lo que sí hay es una incoherencia interna que se cierra — la presión de contacto ya usaba `ex = (M + P·offset)/(P + W)` |
| Envolvente de las dos lecturas | **Criterio del programa** (opción B, pendiente 7) | E.020 art. 20.1 dice qué estabiliza, no cómo tratar la excentricidad de lo demás. No se presenta como exigencia normativa |

### A qué miembro va el término — convención adoptada

Se descubrió al escribir la reconstrucción a mano y **no es una identidad algebraica**:

```
adoptada:        FS = N·(dim/2) / (|M + P·offset| + |H|·h)
brazo acortado:  FS = (N·dim/2 − P·offset) / (|M| + |H|·h)
```

Un cociente no es invariante al pasar un término de un miembro al otro. Con los datos de
`test_el_momento_volcador_es_el_de_la_arista_reconstruido_a_mano`, las dos escrituras dan
**2,612** y **7,119**. Se adopta la primera porque:

1. es la **más estricta** siempre que la otra dé FS > 1, que es el caso normal;
2. es la única coherente con la presión de contacto, que reduce la misma resultante;
3. con `H = 0` da `FS = dim/(2·e)`, de donde sale la relación «resultante en el núcleo
   central ⇒ FS ≥ 3» que el alcance de la combinada invoca.

Es una **hipótesis de modelación declarada**, no una exigencia normativa: ninguna fuente
del proyecto prescribe cómo plantear el volcamiento de una zapata. Queda escrita en el
docstring de `engine/soil/stability.py` y comprobada con números en
`tests/test_formulacion_volteo.py`.

## 3. `baseline.json` (aislada) — 6 casos

46 claves `numeros`, 8 `estados`, 3 `referencias`, 1 `trazas_en_fallo`, 1 `n_descartes`.

| Caso | offset | FS antes | FS ahora | Estado |
|---|---|---|---|---|
| `13_descentrada_un_eje` | +0,55 | 13,27 | **3,41** | NO VERIFICADO (sin cambio) |
| `14_descentrada_dos_ejes` | (+0,40, +0,30) | 15,77 / 23,85 | **4,53 / 11,72** | NO VERIFICADO (sin cambio) |
| `15_descentrada_voladizo_largo_gobierna` | +0,55 | 15,48 | **3,02** | NO VERIFICADO (sin cambio) |
| `16_columna_de_borde` | +1,35 | «no aplicable» | **1,63** | PASS → **NO VERIFICADO** |
| `17_columna_de_esquina` | (+1,30, +1,30) | «no aplicable» | **1,71 / 1,71** | PASS → **NO VERIFICADO** |
| `18_borde_con_momento` | +1,45 | 12,21 | **1,48** | NO VERIFICADO → **FAIL** |

**Los casos 16 y 17 son la evidencia del hueco inseguro**: el volcamiento se declaraba «no
aplicable» —`M = H = 0`— para una columna a 1,35 m del centro de una zapata de 3,4 m,
mientras la presión de contacto veía la resultante fuera del núcleo.

**El 18 es el único que cambia de conjunto en fallo**: `overturning_x` pasa a FAIL y
`n_descartes` de 1 a 2. **No cambia su aceptación**: ya era descartado por
`contact_pressure` (`within_kern = False`), igual que el 16 y el 17.

Las 3 referencias que cambian son las de los casos 16 y 17, que pasan de
`E.050 art. 17.1` —la cita de la rama «no aplicable»— a la cita completa con E.020
art. 20.1 y el criterio D10-2b.

## 4. `baseline_connected.json` — 13 casos

93 claves `numeros`, 36 `estados`, 10 `referencias`. Ninguna en `trazas_en_fallo`.

Todas en la **zapata exterior**, que es la de lindero. Su carga corregida trae
`M = −P·offset`: la viga de conexión absorbe la excentricidad y la resultante queda
centrada. Antes el motor leía `|M| = |P·offset|` como demanda.

| Caso | FS antes | Ahora |
|---|---|---|
| `Z1_articulado_equilibrio` | 1,547 | **no aplicable** |
| `Z1b_articulado_sin_FS_de_volcamiento` | 1,547 | **no aplicable** |
| `Z2_articulado_par_puro` | 1,577 | **no aplicable** |
| `Z5_eje_longitudinal_Y` | 1,547 (eje Y) | **no aplicable** |
| `Z6_holgura_al_lindero_no_nula` | 1,941 | **no aplicable** |
| `Z7_viga_apoya_en_suelo` | 1,547 | **no aplicable** |
| `Z8_peso_propio_de_viga_explicito` | 1,543 | **no aplicable** |
| `Z11_aragon_p1_articulado` | 1,730 | **no aplicable** |
| `Z13_articulado_con_momento_de_columna` | 1,560 | **no aplicable** |
| `Z15_par_puro_con_peso_propio_de_viga_explicito` | 1,573 | **no aplicable** |
| `Z3_cuerpo_rigido_equilibrio` | 1,547 | **19 797** |
| `Z12_aragon_p2_cuerpo_rigido` | 1,785 | **90,5** |
| `Z14_cuerpo_rigido_con_momento_de_columna` | 1,575 | **157,7** |

Los tres últimos son de **CUERPO_RIGIDO**, cuyo reparto deja una excentricidad residual
pequeña pero real (0,06 a 15 kN·m): la verificación se ejecuta y da un FS enorme. Los
ARTICULADO y PAR_PURO recentran exactamente y quedan sin demanda.

**Esto RELAJA**, y hay que decirlo con esas palabras: diez entradas pasan de NO VERIFICADO
a PASS «no aplicable», y con ellas `exterior.overall_status` en ocho casos e
`implemented_checks_status` en seis. Es correcto bajo el modelo declarado —no hay momento
neto que verificar—, pero antes había un número conservador donde el modelo dice que no hay
demanda. El `overall_status` del sistema **no se mueve**: sigue NO VERIFICADO por TBD-C1.

## 5. `reference_pre_5a_non_beam.json` — NO se regenera

Esta referencia vale como prueba precisamente por ser **anterior a 5A**. Regenerarla la
convertiría en una foto del presente y dejaría de demostrar nada sobre D3: la afirmación
«D3 no movió las zapatas» se comprobaría contra un archivo escrito después de D3.

Se **enumeran** en su lugar las 12 claves que este cambio mueve —todas del volcamiento X de
la zapata exterior— en `EXCLUIDAS_FORMULACION_VOLTEO`
(`tests/test_connected_beam_statics_phase5a.py`), y dos tests acotan la dispensa:

- `test_la_dispensa_esta_acotada_al_volcamiento_de_la_zapata_exterior`: ninguna clave toca
  el reparto, la viga, la presión de contacto ni la zapata interior;
- `test_la_dispensa_no_se_ha_quedado_obsoleta`: cada clave dispensada sigue haciendo falta
  en al menos un caso; una lista de excepciones que nadie poda deja de ser una lista.

## 6. Qué NO cambió

- **Ninguna aceptación.** Los casos 16, 17 y 18 ya eran descartados por `contact_pressure`;
  las 13 ternas conectadas ya eran NO VERIFICADAS por TBD-C1.
- **Ningún barrido.** `barrido` no cambia en `S1` ni `S2`: sus columnas son concéntricas.
- **La combinada.** Sus casos congelados K1–K4 no declaran fuerza horizontal, de modo que
  `CombinedFootingResult.stability` es `None` y no aporta claves. El refactor que le quitó
  el cálculo del término duplicado se verificó: 0 claves distintas.
- **La viga de conexión**, el punzonamiento, la flexión y el desarrollo: 0 claves.

## 7. Ruido numérico (CLAUDE.md §10)

`M + P·offset` es una diferencia de magnitudes grandes. Cuando la columna descentrada está
equilibrada el resultado exacto es cero, pero en coma flotante queda un residuo de ~1e-13
kN·m que producía un FS de 1e16 y hacía que dos casos idénticos se leyeran distinto según
de qué lado cayera el último bit.

Se añadió `denoise_moment_kNm` con tolerancia **relativa** a la escala de los términos que
se cancelan (`MOMENT_NOISE_REL_TOL = 1e-9`): siete órdenes por encima del ruido de la doble
precisión y muchos por debajo de cualquier momento con significado de ingeniería. No puede
silenciar una demanda real, y hay un test que lo comprueba en los dos bordes del umbral.

## 8. Verificación posterior

- `py -3 -m pytest -q`: **1758 pasan, 2 se saltan**, 0 fallan.
- Diff del baseline regenerado contra la copia previa, clave por clave: exactamente los 6 +
  13 casos y las 139 claves `numeros` / 44 `estados` / 13 `referencias` de §3 y §4. Cero
  claves ajenas.
- `reference_pre_5a_non_beam.json`: **0 claves distintas** (no se tocó).
- **Mutación deliberada, 8 mutantes, 8 detectados** sin usar el congelamiento: quitar
  `P·offset` de cada lectura, quitar la envolvente, ignorar el desplazamiento, cruzar los
  ejes, quitar el filtro de ruido, exigir fuerza horizontal para aplicar el eje, y que la
  combinada dejara de usar el conjunto estabilizante.
- `npx tsc --noEmit -p .` limpio y `npm run build` correcto.
