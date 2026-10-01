# Diff de baseline por la integración del campo real en el punzonamiento

> **⚠ SUPERADO EL MISMO DÍA.** Lo que sigue describe un paso INTERMEDIO del 2026-09-20 y
> se conserva como historial (`CLAUDE.md` §16), no como descripción del motor actual. La
> superposición de los dos campos 1-D y la declaración `punching_biaxial_uplift` que este
> documento describe **ya no existen**: la decisión 1 del proyectista las sustituyó por el
> contacto unilateral resuelto por equilibrio, que equilibra en los tres regímenes y cerró
> la declaración. Estado vigente en
> [`freeze_contacto_unilateral.md`](freeze_contacto_unilateral.md).

---

Fecha: 2026-09-20. Estado: **implementado, diff revisado caso a caso y regeneración
dirigida ejecutada.**

`CLAUDE.md` §11: una regeneración se documenta diciendo qué cambió, por qué, qué casos
afecta, qué invariantes se mantienen y por qué es intencional. Eso es este documento. El
análisis y la justificación del modelo están en
[`area_efectiva_e050_art28.md`](area_efectiva_e050_art28.md) §6.

---

## 1. Qué cambió

El alivio del suelo bajo la sección crítica de punzonamiento pasa a obtenerse por
**integración del campo real de presión de diseño**:

```text
Vu = Pu − ∫∫(A_crit) q(x, y) dA
```

en lugar de la forma cerrada del campo LINEAL,

```text
∫∫ q dA = q_avg · A_crit · (1 + 12·ex·a_x/B² + 12·ey·a_y/L²)
```

que es exacta **solo dentro del núcleo central**. Fuera de él el campo lineal no existe:
parte de la huella no apoya. La flexión y el cortante unidireccional ya usaban el bloque
triangular real desde la decisión B (2026-09-19); el punzonamiento no.

`q(x, y)` lo da `engine/foundation/flexure.py::DesignPressureField2D`, construido con los
**mismos** `NetPressureField` que usan flexión y cortante. No hay una segunda
representación del contacto de diseño.

Junto con eso, `punching_demand` separa dos cargas que hasta ahora eran una sola:
`P_u_column_kN`, la que punzona, y `field_P_u_kN`, la que produce el campo bajo la zapata.
En la aislada coinciden; en la combinada no.

## 2. Por qué no bastaba con declararlo

Porque el error estaba **medido, y en los casos medidos iba del lado inseguro**: el alivio
lineal salía MAYOR que el real y Vu quedaba SUBESTIMADO, hasta un 1,4 %. Una limitación
declarada sirve cuando el motor no puede pronunciarse; no cuando puede pronunciarse mal.

El signo del error **no es constante**, y no tenía por qué serlo: una distribución que no
equilibra la carga se equivoca en las dos direcciones, igual que pasó con la flexión en la
decisión B. Con la columna centrada el alivio lineal sobra (§3.1); con la columna junto al
borde hacia el que se desplaza la resultante, falta (§3.2). Lo que importa no es de qué
lado caía sino que el campo del que salía **no existe** fuera del núcleo.

## 3. `baseline.json` (aislada) — 9 casos, 119 campos

**Ningún `overall_status` cambió. Ningún descarte cambió. Ninguna aceptación cambió.**
`baseline_connected.json` no se tocó: la conectada reutiliza el motor de la aislada para
sus zapatas, pero ninguno de sus casos congelados alcanza un régimen afectado.

### 3.1 Casos con despegue UNIAXIAL de diseño (13, 15) — el error medido, corregido

| Caso | Campo | Antes | Después | Lectura |
|---|---|---|---|---|
| `13_descentrada_un_eje` | `punching.soil_relief_kN` | 179,92 | 179,78 | alivio real menor |
| | `punching.Vu_kN` | 1080,08 | **1080,22** | Vu **sube**: estaba subestimado |
| `15_descentrada_voladizo_largo_gobierna` | `punching.soil_relief_kN` | 196,43 | 196,19 | ídem |
| | `punching.Vu_kN` | 1063,57 | **1063,81** | ídem |

Movimiento pequeño (≈ 0,01 %) y en la dirección correcta: la demanda **aumenta**. Arrastra
`ratio`, `moment_transfer.*` y el `result_value` de la traza, que son el mismo número
propagado.

### 3.2 Casos con la columna en el borde o la esquina (16, 17, 18)

| Caso | `soil_relief_kN` | `Vu_kN` | Excentricidad de diseño |
|---|---|---|---|
| `16_columna_de_borde` | 241,80 → **334,81** | 738,20 → **645,19** | ex = +1,350 (B/6 = 0,533) |
| `17_columna_de_esquina` | 248,26 → **364,92** | 591,74 → **475,08** | ex = +1,350, ey = −1,350 |
| `18_borde_con_momento` | 251,50 → **324,66** | 658,50 → **585,34** | ex = +1,650 (B/6 = 0,567) |

Aquí el alivio **sube** y Vu baja, que es lo contrario de 13 y 15. No es una incoherencia:
la excentricidad de diseño incluye el descentrado de la columna (`ex = (M + P·offset)/P`,
`engine/soil/eccentricity.py`), de modo que la resultante se desplaza **hacia la columna**.
El bloque triangular concentra toda la carga sobre una franja corta junto a ese borde
—en el caso 16, `a = 3·(1,60 − 1,35) = 0,75 m`—, y la sección crítica de la columna cae
justo encima. El suelo alivia ahí más, no menos.

**Comprobado por reconstrucción independiente**, malla de 1200×1200 sobre el campo,
escrita sin llamar a `integrate_over_rectangle`:

| Caso | Alivio (malla) | Alivio (motor) | `∫∫` sobre la planta | Pu |
|---|---|---|---|---|
| 16 | 334,8078 | 334,8078 | 979,993 | 980,00 |
| 17 | 364,9174 | 364,9174 | 839,988 | 840,00 |
| 18 | 324,6561 | 324,6567 | 909,712 | 910,00 |

Los tres son **FAIL por presión de contacto** desde antes y lo siguen siendo: el cambio no
mueve ninguna decisión.

### 3.3 Combinada (K1–K4) — un defecto preexistente que la integral destapó

El campo se construía con la carga de **una sola columna** y su excentricidad respecto del
centroide de la zapata. Eso describe una zapata que no existe.

| Caso | Columna | `qu_avg_kPa` | `soil_relief_kN` | `Vu_kN` |
|---|---|---|---|---|
| `K1_dos_columnas_simetricas` | C1 y C2 | 43,75 → **87,50** | 174,14 → **129,60** | 1085,86 → **1130,40** |
| `K2_columna_en_limite_de_propiedad` | C1 | 55,26 → **165,79** | 196,45 → **173,04** | 1315,55 → **1338,96** |
| | C2 | 110,53 → **165,79** | 266,15 → **245,68** | 2757,85 → **2778,32** |
| `K3_tres_columnas_desiguales` | C1 | 25,52 → **102,08** | 126,32 → **151,68** | 853,68 → **828,32** |
| | C2 | 47,40 → **102,08** | 76,08 → **163,87** | 1743,92 → **1656,13** |
| | C3 | 29,17 → **102,08** | 144,36 → **176,07** | 975,64 → **943,93** |
| `K4_voladizos_largos_sin_momento_negativo` | C1 y C2 | 43,75 → **87,50** | 113,40 → **129,60** | 1146,60 → **1130,40** |

`K1` tiene respuesta **exacta a mano**: dos columnas iguales y simétricas sin momento dan
un campo uniforme, `qu = ΣPu/(B·L) = 87,50 kPa`, y sobre el área crítica de 1,4811 m² el
alivio vale **129,5953 kN** y `Vu = 1260,0000 − 129,5953 = 1130,4047 kN`. El motor da
exactamente eso. El valor anterior, 174,14, correspondía a una zapata con una sola columna
descentrada, que no es el caso que se está resolviendo.

`qu_avg_kPa` ya no es «la carga de esta columna repartida en la huella» sino la presión
media real bajo la zapata, la misma para todas sus columnas. Es un campo de diagnóstico.

## 4. Qué invariantes se mantienen

| Invariante | Cómo se comprueba |
|---|---|
| `∫∫ q dA = Pu` en todos los regímenes, incluido el despegue biaxial | `test_el_campo_equilibra_la_carga`, 8 regímenes |
| Las marginales del campo 2-D son los campos 1-D de flexión y cortante | `test_la_marginal_en_x/y_es_el_campo_unidireccional` |
| Con contacto total se reduce término a término al campo lineal biaxial | `test_con_contacto_total_se_reduce_al_campo_lineal_biaxial` |
| Ninguna geometría **sin despegue** cambia de resultado | `test_dentro_del_nucleo_reproduce_la_forma_cerrada_anterior`, y los 21 casos congelados que no se movieron |
| La cuadratura es exacta, no aproximada | contraste contra malla fina; `test_partir_en_el_quiebre_es_lo_que_hace_exacta_la_cuadratura` |

## 5. Mutaciones deliberadas

Sobre `tests/test_punzonamiento_campo_real.py` (54 tests), con
`PYTHONDONTWRITEBYTECODE=1`, `py -3 -B` y `__pycache__` borrado:

| Mutación | Tests que caen |
|---|---|
| No partir en el quiebre del contacto | 10 |
| Superposición en forma de producto | 5 |
| Recortar a cero la presión negativa del despegue biaxial | 10 |
| Ignorar `field_P_u_kN` | 2 |
| Integrar el rectángulo ideal en vez del recortado | 1 |

La del producto cae en 5 y no en más: **es la señal correcta**. Esa forma conserva el
equilibrio y las marginales, de modo que solo la tercera propiedad —la reducción al campo
lineal— la descarta, que es exactamente el argumento del docstring.

## 6. La declaración que sobrevive

`punching_partial_contact` → **`punching_biaxial_uplift`**. No es un renombrado: es un
estrechamiento. Cubría todo contacto parcial de diseño, uniaxial incluido, que ahora está
resuelto. Lo que queda declarado es solo el despegue en **los dos ejes**, donde la zona
comprimida deja de ser un rectángulo.

| Caso | Antes | Después |
|---|---|---|
| 13, 15, 16, 18 | `punching_partial_contact` NO VERIFICADO | **sin entrada** |
| 17 | `punching_partial_contact` NO VERIFICADO | `punching_biaxial_uplift` NO VERIFICADO |

Los cuatro que pierden la entrada no ganan ninguna aceptación: 13 y 15 ya estaban en NO
VERIFICADO por la estabilidad en modo directo; 16 y 18 son FAIL.

La presión negativa de la esquina doblemente levantada **no se recorta a cero**: recortarla
rompería el equilibrio, que es la única propiedad que hace utilizable el campo. Cómo
resolver bien ese régimen —un problema de contacto unilateral en 2-D— sigue siendo decisión
abierta.

## 7. Cómo se regeneró

Regeneración **dirigida**, no en bloque. El script de sesión reconstruyó las 30
instantáneas, comprobó que los casos movidos fueran **exactamente** los 9 revisados —se
detenía sin escribir si aparecía uno más o faltaba uno— y reescribió solo esos. Los otros
21 quedan byte a byte.

## 8. Verificación posterior

```text
py -3 -m pytest -q                          1917 passed, 2 skipped
py -3 -m pytest tests/freeze -q              225 passed, 2 skipped
diff de baseline contra el motor             0 casos, 0 campos
npx tsc --noEmit -p .                        limpio
npm run build                                correcto
```

`baseline.json` queda en `46389bd1b046…`. `baseline_connected.json` y
`reference_pre_5a_non_beam.json` no se tocaron.
