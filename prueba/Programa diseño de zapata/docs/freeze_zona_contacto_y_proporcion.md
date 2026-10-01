# Diff de baseline: zona de contacto `q > 0` y proporción de E.050 art. 23.3

> **⚠ SUPERADO EL MISMO DÍA.** Lo que sigue describe un paso INTERMEDIO del 2026-09-20 y
> se conserva como historial (`CLAUDE.md` §16), no como descripción del motor actual. La
> superposición de los dos campos 1-D y la declaración `punching_biaxial_uplift` que este
> documento describe **ya no existen**: la decisión 1 del proyectista las sustituyó por el
> contacto unilateral resuelto por equilibrio, que equilibra en los tres regímenes y cerró
> la declaración. Estado vigente en
> [`freeze_contacto_unilateral.md`](freeze_contacto_unilateral.md).

---

Fecha: 2026-09-20. Estado: **implementado, diff revisado caso a caso.**

Dos decisiones del usuario, tomadas el mismo día, más una corrección que apareció al
implementar la primera. `CLAUDE.md` §11: qué cambió, por qué, qué casos afecta, qué
invariantes se mantienen y por qué es intencional.

Continúa a [`freeze_punzonamiento_campo_real.md`](freeze_punzonamiento_campo_real.md), del
mismo día.

---

## 1. Las tres cosas que cambiaron

| | Qué | Origen |
|---|---|---|
| **A** | El alivio del punzonamiento se integra solo sobre la zona comprimida, `q(x,y) > 0` | decisión del usuario |
| **A′** | La bandera de despegue biaxial preguntaba lo que no era | defecto destapado al implementar A |
| **B** | La proporción del art. 23.3 se verifica en las **tres** tipologías (H6) | decisión del usuario |

---

## 2. A — la zona de contacto es `q > 0`

El suelo no tracciona: contar una presión negativa como alivio sería restar una fuerza que
no existe. El alivio pasa a ser

```text
Vu = Pu − ∫∫(A_crit ∩ {q > 0}) q(x, y) dA
```

**Cómo se integra.** La frontera del contacto, `q = 0`, es una recta **oblicua**: no está
alineada con los ejes y la cuadratura de dos puntos deja de ser exacta sobre ella. Se
recorta cada subrectángulo contra el semiplano `q ≥ 0` (Sutherland-Hodgman) y se integra el
polígono resultante —triángulo, cuadrilátero o pentágono— con `∫∫ q dA = Área · q(centroide)`,
que es **exacta** para un campo afín. Cada subrectángulo lo es por construcción.

**Dónde cambia algo.** Solo con despegue biaxial. Con contacto total y con despegue
uniaxial el campo ya es no negativo en toda la huella —en el segundo caso
`q = q'_x(s_x)/L`, porque el término uniforme de la otra dirección se cancela con
`Pu/(B·L)`—, y las dos integrales coinciden **bit a bit**. Está comprobado así, no
«aproximadamente», en `test_sin_despegue_biaxial_la_zona_comprimida_es_toda_la_huella`.

### 2.1 Lo que esta decisión NO resuelve, medido

Truncar es correcto para el alivio, pero **no resuelve el contacto unilateral**: la
superposición nunca lo resolvió, solo lo describió. Sobre la huella completa el campo
truncado entrega mucho más que Pu.

En el régimen de `17_columna_de_esquina` (3,20 × 3,20 m, Pu = 840 kN, ex = +1,350,
ey = −1,350):

| | `∫∫` sobre la planta | Relación con Pu |
|---|---|---|
| Campo con signo | 840,00 | 1,000 |
| Campo truncado a `q > 0` | 1 350,16 | **1,607** |

Un 61 % de reacción de más. No es una distribución de presiones admisible.

**La solución exacta, para poner número al error.** Hay que hallar el plano
`q = a + b·x + c·y` cuya parte positiva cumpla a la vez `∫q⁺ = Pu`, `∫x·q⁺ = Pu·ex` y
`∫y·q⁺ = Pu·ey`. Son tres ecuaciones con tres incógnitas y se resuelven por Newton. Para el
caso 17 la solución es `q = −11 088,7 + 5 040,3·x − 5 040,3·y`, cuya zona comprimida es un
**triángulo de 0,5 m² en la esquina** —casi todo él dentro de `A_crit`—:

| | Alivio | Vu |
|---|---|---|
| **Exacto** (contacto unilateral) | 836,51 | **3,50** |
| Superposición con signo (antes) | 395,31 | 444,69 |
| Superposición truncada (ahora) | 397,51 | 442,49 |

El truncado mueve el resultado un 0,5 % hacia una respuesta que está a un factor de 127. Es
la razón por la que **`punching_biaxial_uplift` sigue en NO VERIFICADO**: esta integral hace
lo correcto con el campo que hay, y el campo que hay no es el verdadero. El número queda
fijado en `test_el_campo_truncado_deja_de_equilibrar_y_por_eso_sigue_declarandose`; si
alguien resuelve el contacto de verdad, ese test debe caer.

En este caso el error va del lado **conservador** —Vu muy sobrestimado—, pero eso no se
puede afirmar en general y no se afirma.

---

## 3. A′ — la bandera preguntaba lo que no era

`biaxial_uplift` devolvía `not field_x.full_contact and not field_y.full_contact`. Es una
condición **más estrecha** que la que hace falta, porque el núcleo central de un rectángulo
es un **rombo**:

```text
|6·ex/B| + |6·ey/L| <= 1
```

y no el producto de los dos núcleos unidireccionales. Con `ex` y `ey` cada uno dentro de su
propio sexto pero sumando más de uno, la esquina está traccionada aunque los dos campos 1-D
declaren contacto total.

Lo destapó `14_descentrada_dos_ejes`:

| | valor | su límite |
|---|---|---|
| ex | +0,4912 | B/6 = 0,5667 ✔ |
| ey | −0,1676 | L/6 = 0,5000 ✔ |
| rombo | **1,20** | 1,00 ✘ |
| q mínimo en la huella | **−23,58 kPa** | |

El motor integraba como alivio una presión negativa y **no declaraba nada**. Ahora la
bandera pregunta por el signo en las cuatro esquinas —`q` es afín a trozos y no creciente
en `s` en cada dirección, de modo que su mínimo se alcanza siempre en una esquina—, lo que
sigue valiendo también cuando alguno de los dos campos ya despegó y la fórmula del rombo no
aplica. El cero exacto no cuenta: el borde descargado del bloque triangular y la resultante
justo sobre el núcleo valen cero por construcción.

**Verificado que el despegue UNIAXIAL sigue sin declararse**, que es lo correcto: ahí el
bloque triangular resuelve el contacto de forma exacta y `q ≥ 0` en toda la huella.

---

## 4. B — H6: la proporción del art. 23.3, en las tres tipologías

### 4.1 El número es 10, no 5

El texto literal del artículo:

> 23.3. Las zapatas y plateas deberán tener una forma regular: cuadrada, rectangular,
> continua o circular como las mostradas a continuación.

y su tabla de formas:

| Zapata | Dimensiones |
|---|---|
| Cuadrada | L = B |
| Rectangular | **L ≤ 10 B** |
| Continua | L > 10 B |
| Combinada | **L ≤ 10 B** |

El «cinco (5)» que aparece unas líneas antes pertenece al art. **23.1** y es otra relación
—`Df/B`, profundidad sobre ancho, la que define una cimentación como superficial—, que no
dice nada sobre la forma en planta. Es justamente el pendiente **H7**, distinto de H6.

Adoptar `L/B ≤ 5` sería un **criterio del programa** más estricto que la norma, no una
lectura del 23.3, y tendría que declararse como tal —igual que los FS de D10-2b—. El motor
usa hoy el 10 del artículo; cambiarlo es decisión abierta (§7).

### 4.2 Qué se implementó

Una sola implementación, `engine.codes.peru.e050_soils.check_shape_ratio`, usada por las
tres tipologías. La combinada delega en ella y `engine/domain/combined_layout.py` pierde su
constante propia: **duplicarla fue lo que permitió que la aislada no mirara el artículo**.

`L/B > 10` → entrada `shape_ratio` en **FAIL** y descarte de la alternativa, igual que en la
combinada. La hipótesis declara la lectura: la tabla **no prohíbe, clasifica**, y por encima
del límite el elemento deja de ser una zapata para ser una cimentación continua, que es otra
tipología que este motor no modela. Es un límite de **alcance**, no una exigencia numérica
de la norma.

`shape_ratio` entra en `COMUNES_A_LAS_TRES` de
`tests/test_auditoria_paridad_tipologias.py`, que a partir de ahora impide que vuelva a
perderse.

---

## 5. Diff de las dos baselines

**Ningún `overall_status` cambió. Ningún descarte cambió. Ninguna aceptación cambió,
en ninguna de las dos.**

| Baseline | Casos | Campos |
|---|---|---|
| `baseline.json` | 24 de 30 | 112 |
| `baseline_connected.json` | 13 de 13 | 117, **todos aditivos** |

### 5.1 Lo aditivo: la entrada `shape_ratio` (22 casos)

Los 18 casos de la aislada y los 2 de barrido ganan la entrada, **todos PASS** —el máximo
L/B del congelamiento es 3,75—, con tres claves cada uno: `traza.orden`,
`traza[shape_ratio].result_value` y su `status`, más la referencia. Los 4 casos combinados
solo cambian el texto de la referencia:

```text
E.050 art. 23.3 (tabla de formas: combinada con L <= 10 B)
  ->  E.050 art. 23.3 (tabla de formas: L <= 10 B)
```

porque la regla ya no es «de la combinada». Es `referencias`, contrato blando.

### 5.2 Lo sustantivo: dos casos

| Caso | Qué cambia | Por qué |
|---|---|---|
| `17_columna_de_esquina` | alivio 364,917 → **365,491**; Vu 475,083 → **474,509** | A: deja de contar la esquina traccionada |
| `14_descentrada_dos_ejes` | gana `punching_biaxial_uplift` en NO VERIFICADO; **ningún número se mueve** | A′: su `A_crit` cae entera en la zona comprimida, de modo que el alivio no cambia; lo que cambia es que ahora se declara |

Los dos casos ya estaban en NO VERIFICADO por la estabilidad en modo directo, de manera que
`overall_status` no se mueve en ninguno.

### 5.3 `baseline_connected.json` — 13 casos, puramente aditivo

Las dos zapatas de cada terna pasan por `evaluate_candidate`, de modo que heredan H6 sin
código nuevo. El diff son **nueve claves por caso y ninguna más**: `traza.orden` y, por cada
zapata, `result_value`, `result_unit_len`, `status` y la referencia de
`zap_ext/shape_ratio` y `zap_int/shape_ratio`. Todas PASS.

El script de regeneración comprobó exactamente eso antes de escribir —lista blanca de nueve
claves, y además que ninguna de ellas existiera ya en la versión anterior, porque una clave
preexistente que cambiara no sería una adición— y se habría detenido sin escribir ante una
sola clave ajena. La decisión A no llega aquí: ninguna terna congelada alcanza un régimen
con tracción bajo las cargas de diseño.

---

## 6. Mutaciones deliberadas

Sobre `tests/test_punzonamiento_campo_real.py` y `tests/test_proporcion_e050_art23_3.py`
(92 tests), con `PYTHONDONTWRITEBYTECODE=1`, `py -3 -B` y `__pycache__` borrado:

| Mutación | Tests que caen |
|---|---|
| No recortar: integrar el rectángulo entero | 1 |
| La bandera vuelve a preguntar por los dos ejes | 3 |
| Recortar bien pero evaluar en el centroide del RECTÁNGULO | 5 |
| Umbral de forma a 5 sin decirlo | 2 |
| La aislada traza pero no descarta | 1 |

---

## 7. Lo que queda abierto

| | Qué falta decidir |
|---|---|
| **Contacto unilateral biaxial** | Resolver el plano por Newton (§2.1) cerraría `punching_biaxial_uplift`. Es un modelo físico nuevo: afectaría también a flexión y cortante, que hoy usan el mismo campo |
| **Umbral de forma** | Mantener el 10 del art. 23.3, o adoptar 5 como criterio del programa declarado (§4.1) |

## 8. Verificación posterior

```text
py -3 -m pytest -q                     1957 passed, 2 skipped
py -3 -m pytest tests/freeze -q         225 passed, 2 skipped
diff de ambas baselines contra el motor   0 casos, 0 campos
npx tsc --noEmit -p .                   limpio
npm run build                           correcto
```

`baseline.json` queda en `f240ae09bf09…` y `baseline_connected.json` en `d02f737e8e45…`.
`reference_pre_5a_non_beam.json` **no se tocó**: la entrada nueva se enumera en
`ENTRADAS_NUEVAS_TRAS_5A` y se filtra solo de `traza.orden`, con un test que exige que cada
una exista hoy y no existiera antes de 5A, para que la lista no se convierta en una puerta
trasera.
