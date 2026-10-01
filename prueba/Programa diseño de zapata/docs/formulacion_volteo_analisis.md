# `FORMULACION_VOLTEO` — análisis

Fecha: 2026-09-18. Estado: **CERRADO. Aprobado por el usuario el 2026-09-19 e
implementado.** Lo que sigue se conserva tal como se escribió, porque es el expediente de
la decisión (CLAUDE.md §16); el resultado y el diff están en
[`freeze_formulacion_volteo.md`](freeze_formulacion_volteo.md).

Tres correcciones al análisis, encontradas al implementarlo:

1. **A qué miembro va el término.** El §9 daba por hecho que «pasar `P·offset` al otro
   miembro» era una identidad. No lo es: un cociente no es invariante a ese cambio, y las
   dos escrituras dan números distintos —2,612 frente a 7,119 en el caso de prueba—. Se
   adopta llevarlo al miembro VOLCADOR, que es la más estricta y la coherente con la
   presión de contacto. Queda declarada como hipótesis de modelación, no como norma.
2. **El recuento de claves era corto.** Medido tras implementar: 19 casos regenerados —6
   de la aislada y 13 de la conectada—, 139 claves `numeros`, 44 `estados`, 13
   `referencias`. El §11 decía 23 casos y 30 `estados`; el script previo no enumeraba
   todos los campos del modelo.
3. **`reference_pre_5a_non_beam.json` NO se regeneró.** Se acotaron sus 12 claves con una
   dispensa enumerada y dos tests que la vigilan: regenerarla habría destruido lo único
   que esa referencia demuestra, que es ser anterior a 5A.

Y un efecto que el análisis no previó: con el término incorporado, la zapata exterior de
los modelos ARTICULADO y PAR_PURO queda **sin demanda** de volcamiento —no con un FS
mayor—, de modo que la verificación se declara no aplicable y varios estados NO VERIFICADO
pasan a PASS. Tres tests que usaban ese caso como ejemplo canónico de «NO VERIFICADO sin
pendiente» se trasladaron a casos de CUERPO_RIGIDO, donde el reparto deja una
excentricidad residual real.

Diferencia conocida del catálogo (`engine/integration/typology_catalog.py`), hoy marcada
como RESUELTA.

---

## 1. Las dos formulaciones

Ambas comparten el mismo convenio, ya adoptado y documentado en `engine/soil/stability.py`:
el punto de giro es la arista inferior de la base, el momento estabilizador es el de la
carga vertical **estabilizante** actuando en el centroide, y el momento aplicado es una
acción volcadora.

```text
M_estab = N_estabilizante · dim/2          (E.020 art. 20.1: solo carga muerta)
FS      = M_estab / M_volcador
```

Lo que difiere es **M_volcador**:

| Tipología | M_volcador |
|---|---|
| Aislada y zapatas de la conectada | `\|M\| + \|H\|·h` |
| Combinada | `max(\|M_total\|, \|M_estabilizante\|) + \|H\|·h`, con `M_total = Σ(M_i + P_i·offset_i)` |

## 2. Diagnóstico: la aislada es incoherente **consigo misma**

El problema no es que las dos tipologías difieran. Es que **la aislada usa dos
excentricidades distintas para la misma resultante**:

| Verificación | Qué excentricidad usa | Dónde |
|---|---|---|
| Presión de contacto | `ex = (M + P·offset) / (P + W)` | `compute_total_eccentricity`, Fase 1B |
| Volcamiento | `M` a secas, **sin** `P·offset` | `_check_overturning_axis` |

`_check_overturning_axis` **ni siquiera recibe el `placement`**: estructuralmente no puede
incluir el término. Es una omisión de la Fase 1B, que añadió la columna descentrada a la
presión de contacto y no a la estabilidad.

### 2.1 Por qué `P_i·offset_i` pertenece al lado volcador

Tomando momentos respecto de la arista de giro, a `dim/2` del centroide, una carga vertical
`P` situada a `offset` del centroide tiene brazo estabilizador `dim/2 − offset`:

```text
M_estab_real = W·(dim/2) + P·(dim/2 − offset) = (P + W)·dim/2 − P·offset
```

Pasar `P·offset` al otro miembro da exactamente `M_volc = |M + P·offset|` con
`M_estab = N·dim/2`. **No es una hipótesis nueva: es el mismo convenio ya adoptado, escrito
sin omitir un término.** Con `offset = 0` se reduce a `|M|`, que es el caso que la aislada
sí resuelve bien.

### 2.2 El error va en las DOS direcciones

**a) Inseguro — aislada con columna de borde y sin momento aplicado.**
Casos congelados `16_columna_de_borde` y `17_columna_de_esquina`: `M = 0`, `H = 0`,
`offset = ±1,35 m`. El volcamiento se declara **«no aplicable», FS = ∞**, mientras la
presión de contacto ve la resultante **fuera del núcleo** y falla.

| Caso | offset | FS actual | FS con `P·offset` |
|---|---|---|---|
| `16_columna_de_borde` | +1,350 | ∞ (no aplicable) | **1,63** |
| `17_columna_de_esquina` | ±1,350 | ∞ (no aplicable) | **1,71** |
| `18_borde_con_momento` | +1,450 | 12,21 | **1,48 → FAIL** |
| `13_descentrada_un_eje` | +0,450 | 13,27 | **3,41** |
| `15_descentrada_voladizo_largo` | +0,550 | 15,48 | **3,02** |

**b) Falsamente conservador — zapata exterior de la conectada.**
Es el hallazgo más claro. En las 13 ternas congeladas la redistribución **centra la
resultante**: la presión sale uniforme, `ex = 0,00000`. Pero el volcamiento cuenta como
acción el momento `M` de la carga corregida, que es exactamente `−P·offset`:

```text
Z1: P_ext_corr = 971,43 kN   offset = −0,750 m   P·offset = −728,57 kN·m
    M de la combinación corregida = +728,57 kN·m
    M + P·offset = 0,00        ← lo que ve la presión de contacto (ex = 0)
    |M| = 728,57               ← lo que usa el volcamiento hoy
    FS = 1126,95 / 728,57 = 1,547   frente a FS = ∞ (sin acción volcadora)
```

Las 13 ternas dan FS entre **1,54 y 1,94**, es decir **rozando el mínimo de 1,50 por un
momento que la propia presión de contacto dice que no existe**. Las zapatas interiores, con
`offset = 0`, dan lo mismo con las dos formulaciones —control limpio de que el término es lo
único que difiere—.

## 3. Ejemplo numérico donde cambia la ACEPTACIÓN

Dentro del núcleo central, con carga viva y fuerza horizontal:

```text
B = L = 1,60 m   h = 0,80 m   Df = 1,20 m   CM = 300 kN   CV = 700 kN
offset = 0,264 m   H = 200 kN   M = 0        W = 67,6 kN

e = (0 + 1000·0,264)/(1000 + 67,6) = 0,2473 m  ≤  B/6 = 0,2667 m   → DENTRO del núcleo:
                                                  la presión de contacto PASA
N_estab = CM + W = 367,6 kN        M_estab = 367,6 · 0,80 = 294,1 kN·m

FS ACTUAL    = 294,1 / (0 + 200·0,80)            = 1,84  → PASA
FS PROPUESTA = 294,1 / (1000·0,264 + 200·0,80)   = 0,69  → FALLA
```

Factor 2,7 entre las dos, y a un lado y otro del 1,50 exigido. **La omisión sí puede
producir un falso PASS**; el núcleo central no la cubre siempre, porque `N_estabilizante`
(solo carga muerta) es menor que `P + W` y porque `H·h` no entra en el núcleo.

## 4. Signos y envolvente

`M_total` es **con signo**: `Σ(M_i + P_i·offset_i)`. El valor absoluto se toma al final, lo
que equivale a elegir la arista de giro más desfavorable —el convenio ya adoptado—.

La **envolvente** resuelve un segundo problema: `M_estab` usa la carga **estabilizante**
(solo muerta, E.020 art. 20.1) mientras el término `P·offset` usaría el `P` **total**.
Mezclar los dos no es neutro: la excentricidad de una carga no muerta puede **reducir**
`|M_total|` y enmascarar el volcamiento. Por eso la combinada toma

```text
M_volc = max(|M_total|, |M_estabilizante|) + |H|·h
```

y declara la envolvente como criterio del programa —no como exigencia normativa—. Si la
aislada adopta el término `P·offset`, debe adoptar también la envolvente: son la misma
decisión, ya aprobada para la combinada (opción B del pendiente 7).

## 5. Coherencia con la distribución de presiones

Con la formulación propuesta, las dos verificaciones usan **la misma resultante**:

```text
presión:      ex = M_total / (P + W),   exige |ex| ≤ dim/6 (núcleo, E.060 §15.2.3)
volcamiento:  M_volc = |M_total| + |H|·h
```

y la relación entre ambas queda explícita: dentro del núcleo y sin fuerza horizontal,

```text
FS = N·(dim/2) / |M_total| = (N/(P+W)) · dim/(2|ex|) ≥ 3·N/(P+W)
```

es decir, **FS ≥ 3 cuando toda la carga es muerta**. Es exactamente el argumento que la
combinada ya usa para no emitir estabilidad sin fuerza horizontal. Con la formulación
actual esa relación no se sostiene, porque las dos verificaciones no hablan de la misma
excentricidad.

## 6. Respaldo normativo

| Elemento | Respaldo |
|---|---|
| Punto de giro en la arista, empuje pasivo no considerado | **Hipótesis de modelación declarada**, no normativa (ya documentada en `stability.py`) |
| Solo la carga muerta estabiliza | **E.020 art. 20.1**, literal |
| FS exigido | **Criterio del programa D10-2b** (1,50), con los valores normativos citados aparte |
| Momento de la carga descentrada, `P·offset` | **Estática**, no normativa. Es la misma derivación que `compute_total_eccentricity` ya documenta para la presión de contacto |
| Envolvente de las dos lecturas | **Criterio del programa** (opción B, pendiente 7). E.020 art. 20.1 dice qué estabiliza, no cómo tratar la excentricidad de lo que no estabiliza |

**Ninguna norma del proyecto prescribe cómo plantear el volcamiento de una zapata.** E.020
arts. 20–22 fijan qué estabiliza y qué FS; E.030 art. 64 habla de «toda estructura y su
cimentación» sin detallar el nivel. La formulación es, en las tres tipologías, una
**hipótesis de modelación declarada**. Lo que el análisis sostiene no es que la norma exija
`P·offset`, sino que **omitirlo hace incoherente el modelo consigo mismo**.

## 7. ¿Está justificada la diferencia entre tipologías?

**No.** El `offset` es un hecho geométrico del layout, no una propiedad de la tipología. La
aislada admite columna descentrada desde la Fase 1B —cuatro casos congelados la ejercen— y
la zapata exterior de la conectada es de lindero por definición. `|M|` es el caso
particular de `|M + P·offset|` con `offset = 0`, y ahí las dos coinciden exactamente
(comprobado en las zapatas interiores de la conectada).

## 8. Impacto medido sobre los casos congelados

Recuento exacto, clave por clave, comparando el valor congelado con el que daría la
formulación propuesta:

| Archivo | Casos | Claves `numeros` | Claves `estados` |
|---|---|---|---|
| `baseline.json` (aislada) | **6** | **38** | **8** |
| `baseline_connected.json` | **13** | **82** | **20** |
| `reference_pre_5a_non_beam.json` | **4** | **19** | **2** |
| **Total** | **23 casos** | **139** | **30** |

Casos afectados:

- **Aislada (6):** `13_descentrada_un_eje`, `14_descentrada_dos_ejes`,
  `15_descentrada_voladizo_largo_gobierna`, `16_columna_de_borde`, `17_columna_de_esquina`,
  `18_borde_con_momento`. Los casos con columna centrada **no se mueven**.
- **Conectada (13):** todas las ternas no rechazadas, en la entrada `zap_ext/overturning_*`.
  Las zapatas interiores **no se mueven**.
- **Referencia pre-5A (4):** `Z3`, `Z12`, `Z13`, `Z14`.

### Lo que NO cambia

**Ninguna aceptación.** Comprobado caso por caso:

- Aislada: `16`, `17` y `18` ya son **FAIL** globalmente por presión de contacto —resultante
  fuera del núcleo—; `13`, `14` y `15` ya son **NO VERIFICADO** por modo directo.
  `overall_status` no se mueve en ninguno.
- Conectada: las 13 ternas ya son **NO VERIFICADO** por TBD-C1.

### El punto que hay que mirar con cuidado

En la conectada la corrección **relaja** una verificación: `zap_ext/overturning_x` pasa de
**NO VERIFICADO con FS 1,55** a **PASS «no aplicable»**. Es correcto bajo el modelo
declarado —resultante centrada y `H = 0`: no hay acción volcadora—, y el estado global sigue
siendo NO VERIFICADO por TBD-C1. Pero conviene decidirlo con los ojos abiertos: hoy hay un
número conservador donde el modelo dice que no hay demanda.

### Gobernanza

`reference_pre_5a_non_beam.json` es la referencia que protege
`test_D3_no_mueve_zapatas_ni_reparto`, cuyo propósito es afirmar que la Fase 5A no movió las
zapatas. Tocarla exige, además de la aprobación, **decidir si esas claves se excluyen de la
lista positiva o si la referencia se regenera** dejando constancia de que el cambio es
posterior a 5A y ajeno a ella.

## 9. Formulación que considero defendible

Unificar en la formulación de la combinada, aplicada a las tres tipologías:

```text
M_total          = Σ (M_i + P_i · offset_i)          con signo
M_estabilizante  = Σ sobre los componentes que E.020 art. 20.1 admite como estabilizantes
M_volc           = max(|M_total|, |M_estabilizante|) + |H|·h
M_estab          = N_estabilizante · dim/2
FS               = M_estab / M_volc
```

Para una sola columna se reduce a `|M + P·offset|`, y con la columna centrada, a `|M|`: los
casos congelados con columna centrada quedan **bit a bit** iguales.

Implicaciones de implementación, si se aprueba:

1. `_check_overturning_axis` necesita el `placement` (hoy no lo recibe).
2. La entrada pasa a ser **aplicable** cuando `M_total ≠ 0` aunque `M = 0` y `H = 0`: es lo
   que destapa los casos 16 y 17.
3. Conviene extraer la formulación a **una sola función** compartida por las tres
   tipologías, en línea con lo hecho con `soil_actions` y `effective_qadm`.

## 10. Decisión que requiere aprobación

**Sí, la requiere.** Cambia una hipótesis de modelación, el estado de verificaciones y
139 + 30 claves congeladas en 23 casos (§3 y §11).

Lo que hay que aprobar, en tres puntos separables:

1. **Incorporar `P·offset` al momento volcador** en aislada y conectada. Es lo que corrige
   la incoherencia con la presión de contacto y elimina el falso PASS del §3.
2. **Adoptar también la envolvente** (opción B), para no reintroducir por otra vía el
   problema que la combinada ya resolvió.
3. **Autorizar el freeze dirigido** de los 23 casos, incluido
   `reference_pre_5a_non_beam.json`, decidiendo cómo se trata la lista positiva de
   `test_D3_no_mueve_zapatas_ni_reparto`.

Se puede aprobar 1 sin 2, pero no lo recomiendo: dejaría la aislada con el término y sin la
protección contra la excentricidad favorable de la carga no muerta, que es precisamente el
caso que motivó la opción B.
