# Contacto unilateral, `Df/B ≤ 5` y cierre de C1, C4 y C-V

Fecha: 2026-09-20. Estado: **implementado, diff revisado caso a caso, regeneración dirigida
ejecutada.**

Seis decisiones del proyectista, tomadas juntas. `CLAUDE.md` §11: qué cambió, por qué, qué
casos afecta, qué invariantes se mantienen y por qué es intencional.

Documentos del mismo día que éste continúa:
[`freeze_punzonamiento_campo_real.md`](freeze_punzonamiento_campo_real.md) y
[`freeze_zona_contacto_y_proporcion.md`](freeze_zona_contacto_y_proporcion.md).

---

## Resumen

| # | Decisión | Qué se hizo |
|---|---|---|
| **1** | Contacto unilateral biaxial | Implementado por equilibrio; **campo común** de punzonamiento, flexión y cortante. Cierra `punching_biaxial_uplift` |
| **2** | `L/B` | Se mantiene el **10** del art. 23.3. Sin cambios de código |
| **3** | `Df/B` | **FAIL si Df/B > 5** (art. 23.1), en las tres tipologías |
| **4** | TBD-C1 | Declaración del proyectista sobre §15.2.6. Levanta ese bloqueo y **ningún otro** |
| **5** | TBD-C4 | `APOYA_EN_SUELO` **rechazado por validación** |
| **6** | C-V | Cerrado con el criterio de **concreto solo**, declarado como límite de alcance |

---

## 1. Decisión 1 — el contacto unilateral

### 1.1 El modelo

El suelo no tracciona: la distribución bajo una zapata rígida es un plano **truncado en
cero**, y sus tres coeficientes los fija el equilibrio con la resultante de diseño.

```text
q⁺(x,y) = max(a + b·u + c·v, 0)          u = x/(B/2),  v = y/(L/2)

∫∫ q⁺ dA = Pu        ∫∫ x·q⁺ dA = Pu·ex        ∫∫ y·q⁺ dA = Pu·ey
```

Sustituye a la superposición de los dos campos unidireccionales, que con excentricidad
biaxial **no resolvía el contacto sino que lo describía**: su parte positiva entregaba
1,61·Pu en el régimen de `17_columna_de_esquina`.

### 1.2 Por qué Newton es dócil aquí

Al derivar `F(a,b,c) = ∫_P (a + b·u + c·v) dA` respecto de cada coeficiente, el término de
frontera de Leibniz **se anula**: la frontera libre se mueve, pero el integrando vale cero
justo sobre ella. Queda

```text
J = [[ A,  Su,  Sv ],
     [ Su, Iuu, Iuv],
     [ Sv, Iuv, Ivv]]
```

—la matriz de Gram de `{1, u, v}` sobre el polígono comprimido, **simétrica y definida
positiva**—. No es una aproximación del jacobiano: es el jacobiano. Y como los momentos del
polígono se calculan en forma cerrada (fórmulas del cordón), residuo y jacobiano son
exactos.

Medido: **2 a 17 iteraciones**, residuos en precisión de máquina, incluso con la resultante
a 10 cm de la esquina (zona comprimida de 0,08 m²). La búsqueda de línea es lo que lo
sostiene ahí: el paso de Newton desde el plano lineal se pasa de largo y dejaría el
polígono vacío.

### 1.3 Dos regímenes no iteran, y eso es lo que hace revisable el diff

| Régimen | Condición | Solución |
|---|---|---|
| Contacto total | dentro del **rombo** `\|6·ex/B\| + \|6·ey/L\| ≤ 1` | plano lineal clásico |
| Despegue uniaxial | `ey = 0` (o `ex = 0`) fuera del sexto | bloque triangular de `NetPressureField` |
| Biaxial con despegue | lo demás | Newton |

En los dos primeros **se escribe la solución**. No es un atajo: es la misma solución
evaluada en forma cerrada. Está comprobado término a término —el plano lineal punto por
punto, y la marginal contra `NetPressureField` con `a = 3·(dim/2 − |e|)`— en
`tests/test_contacto_unilateral.py`.

Consecuencia: **solo se mueve el régimen biaxial**. Y `test_sin_despegue_biaxial_flexion_y_
cortante_no_cambian_ni_un_bit` lo exige con `==`, no con `approx`.

### 1.4 El campo es COMÚN

`punching_demand`, `moment_at_critical_section` y `shear_force_at_d_from_face` usan el mismo
campo. Las dos últimas reciben la excentricidad TRANSVERSAL (`e_transverse_m`,
`dim_transverse_m`, campos aditivos con defecto inerte) y, en el régimen biaxial, integran
el polígono sobre la franja del voladizo en vez de tratarlo como problema 1-D.

### 1.5 Impacto, verificado por reconstrucción independiente

Dos casos, exactamente los del régimen biaxial:

| Caso | ex / ey | Qué cambia |
|---|---|---|
| `17_columna_de_esquina` | +1,3500 / −1,3500 | alivio 365,49 → **825,20**; Vu 474,51 → **14,80**; Mu 7,78 → **13,125** |
| `14_descentrada_dos_ejes` | +0,4912 / −0,1676 | Mu_y 398,02 → **398,40**; Vu_x 301,02 → **301,34**; alivio 144,285 → **144,285** |

`14` es el caso que destapó el rombo: cada excentricidad dentro de su sexto —B/6 = 0,5667,
L/6 = 0,5000— pero `6·ex/B + 6·ey/L = 1,20`, con q_min = −23,58 kPa.

**Reconstrucción independiente**, Newton con cuadratura bruta y jacobiano numérico, escrito
sin llamar al código que se prueba:

| Caso | Alivio (a mano) | Alivio (motor) | Vu (a mano) | Vu (motor) |
|---|---|---|---|---|
| 17 | 825,2143 | 825,1958 | 14,7857 | 14,8042 |
| 14 | 144,2853 | 144,2852 | 1045,7147 | 1045,7148 |

### 1.6 Lo que se retira

`punching_biaxial_uplift` desaparece: el campo equilibra por construcción y no hay nada que
declarar. Con él se van `DesignPressureField2D`, `design_pressure_field_2d`,
`BIAXIAL_UPLIFT_PUNCHING_NOTE` y la limitación homónima. **No quedan dos representaciones
del contacto de diseño**, que es la condición que `CLAUDE.md` §13 impone.

La imposibilidad —resultante fuera de la huella— se declara con `ContactFieldImpossible`, y
el punzonamiento la trata devolviendo la carga entera sin alivio, el mismo criterio con que
`NetPressureField` trataba `e ≥ dim/2`.

---

## 2. Decisión 2 — `L/B ≤ 10`

Se mantiene el número del art. 23.3. Ningún cambio de código: H6 ya estaba implementado así.
La razón de no adoptar 5 queda escrita —el 5 es del art. 23.1 y es `Df/B`— para que no
vuelva a confundirse.

---

## 3. Decisión 3 — `Df/B ≤ 5` (H7)

Literal del artículo:

> «23.1. Son aquellas en las cuales la relación Profundidad / ancho (Dƒ/ B) es menor o igual
> a cinco (5), siendo Dƒ la profundidad de la cimentación y B el ancho o diámetro de la
> misma.»

Es una **definición**, no un requisito de resistencia, y el art. 23.2 enumera como
superficiales exactamente las tipologías que este motor resuelve.

**Qué es «B».** El lado MENOR. Tomar el mayor daría una relación más pequeña y dejaría pasar
geometrías que el artículo excluye; el lado menor es además la dimensión que gobierna los
mecanismos por los que la distinción existe.

**Por qué FAIL y no NO VERIFICADO**, decisión del proyectista: el programa diseña
cimentaciones superficiales, y admitir una entrada físicamente fuera del alcance del modelo
—aunque se rotule— deja abierta la puerta a que alguien la use. Es la misma lectura de
alcance que la proporción del 23.3, y así se declara en la hipótesis: no es que la norma lo
prohíba, es que el modelo deja de describir el problema.

Una sola implementación, `check_shallow_foundation`, en las tres tipologías.
`shallow_foundation` entra en `COMUNES_A_LAS_TRES`.

**Ningún caso congelado falla**: el máximo `Df/B` del congelamiento queda muy por debajo
de 5.

---

## 4. Decisión 4 — TBD-C1: la declaración del proyectista

E.060 §15.2.6 **exige** evaluar el comportamiento de las vigas de conexión «de acuerdo a su
rigidez y la del conjunto suelo-cimentación», y no da método ni umbral. El motor no puede
responderla sin inventar un criterio; lo que sí puede es **registrar quién la responde**.

`beam.stiffness_declaration`:

| Valor | Estado de la premisa | `open_tbd` |
|---|---|---|
| `NO_EVALUADA` (defecto) | NO VERIFICADO | `TBD-C1` |
| `DECLARADA_POR_PROYECTISTA` | INFO | ninguno |

**El defecto es la excepción deliberada** a la regla de «sin valor por defecto» de la
conectada: `NO_EVALUADA` es *no responder*, que es exactamente lo que había antes. Un
defecto que respondiera la pregunta sería el problema.

**Tres cosas que la decisión obliga a decir, y que los tests exigen:**

1. la traza dice «EL MOTOR NO LO HA COMPROBADO» y de quién es la afirmación;
2. la declaración **no cambia ni un número** —comprobado comparando las instantáneas
   completas—: registra una responsabilidad, no un criterio de diseño;
3. **no convierte el resultado en conforme.** Levanta ESE bloqueo. Cualquier otra
   verificación en NO VERIFICADO, y cualquier otro TBD abierto —C11 con `PAR_PURO`—, lo
   sigue impidiendo por su cuenta. Hay un test dedicado a eso.

---

## 5. Decisión 5 — TBD-C4: `APOYA_EN_SUELO` se rechaza

Un NO VERIFICADO dice «no puedo demostrar esto», y es correcto cuando el resto del resultado
sigue siendo el del problema planteado. Aquí no lo era: el motor resolvía una viga que salva
el vano sin apoyo —otro problema— y entregaba geometrías, esfuerzos y acero de ese otro
problema con una nota al pie. Ignorar el apoyo sobrestima ΔP, y como la carga corregida de
la zapata interior es `P_int − ΔP`, esa zapata queda **menos cargada de lo que estaría**.

Se rechaza en el validador del layout **y** a la entrada del solver, porque
`model_copy(update=…)` de pydantic v2 no ejecuta validadores: es la misma puerta trasera que
obligó a comprobar D1 en tres sitios, y hay un test que la recorre.

### 5.1 Consecuencia en el congelamiento: `Z7_viga_apoya_en_suelo` se retira

Ese caso congelaba que declarar `APOYA_EN_SUELO` emitiera el pendiente y no ascendiera de
estado. Desde la decisión **ya no se puede ni construir**: el layout lanza `ValueError` al
instanciarse.

**No es pérdida de cobertura, es endurecimiento.** Lo que Z7 protegía —que esa configuración
no produzca un diseño— lo protege ahora el rechazo mismo, y de forma más estricta: antes
producía un diseño con una advertencia; ahora no produce nada.

---

## 6. Decisión 6 — C-V: el alcance queda declarado

El criterio no cambia: **concreto solo**, `Vu ≤ φVc`, FAIL y descarte por encima. Lo que se
cierra es su **estatuto**: deja de ser un pendiente ambiguo y pasa a ser un límite de
alcance declarado.

La nota que viaja en la traza dice ahora tres cosas que antes no decía:

- **NO es una verificación completa del modelo de cortante de E.060.** La norma admite
  `Vn = Vc + Vs`; el aporte de estribos queda FUERA DEL ALCANCE;
- el criterio es **más estricto** que la norma, de modo que puede descartar geometrías que
  E.060 admitiría con refuerzo, pero **no puede aceptar** ninguna que no cumpla;
- ampliarlo es una **decisión de ingeniería nueva**, con tres preguntas normativas previas
  sin resolver, no un pendiente de implementación.

---

## 7. Diff de las dos baselines

**Ningún `overall_status` cambió. Ningún descarte cambió. Ninguna aceptación cambió.**

| Baseline | Casos | Campos | Qué |
|---|---|---|---|
| `baseline.json` | 24 de 30 | 171 | `shallow_foundation` aditivo en 24; contacto unilateral en 2 |
| `baseline_connected.json` | 13 de 16 | 113 | `shallow_foundation` aditivo en 12; `Z7` retirado |

### 7.1 Aditivo: `shallow_foundation`

Los 24 casos de `baseline.json` y los 12 de la conectada ganan la entrada, **todos PASS**,
con tres claves cada uno más la referencia. En la conectada son dos entradas por caso, una
por zapata.

### 7.2 Sustantivo: los dos casos del régimen biaxial

`17_columna_de_esquina` y `14_descentrada_dos_ejes`, detallados en §1.5. Los dos ya estaban
en NO VERIFICADO por la estabilidad en modo directo, de manera que `overall_status` no se
mueve en ninguno.

### 7.3 Caso retirado

`Z7_viga_apoya_en_suelo`, por la decisión 5 (§5.1).

---

## 8. Qué invariantes se mantienen

| Invariante | Cómo se comprueba |
|---|---|
| Las **tres** ecuaciones de equilibrio, en los tres regímenes | `test_el_campo_equilibra_las_tres_ecuaciones`, 9 casos |
| `q ≥ 0` en toda la huella | `test_la_presion_nunca_es_negativa` |
| Contacto total ⇒ plano lineal clásico, término a término | `test_con_contacto_total_es_el_plano_lineal_clasico` |
| Despegue uniaxial ⇒ bloque triangular de `NetPressureField` | `test_con_despegue_uniaxial_es_el_bloque_triangular` |
| Sin despegue biaxial, flexión y cortante **no cambian ni un bit** | `test_sin_despegue_biaxial_flexion_y_cortante_no_cambian_ni_un_bit`, con `==` |
| Los momentos del polígono, contra las fórmulas de libro | `test_los_momentos_del_poligono_reconstruidos_a_mano` |
| Aditividad de la integral al partir la huella | `test_la_suma_de_las_partes_es_el_todo` |
| La declaración de C1 no mueve ningún número | `test_la_declaracion_no_cambia_ni_un_numero` |
| La proporción y la profundidad se verifican en las tres tipologías | `COMUNES_A_LAS_TRES` |

---

## 9. Mutaciones deliberadas

Con `PYTHONDONTWRITEBYTECODE=1`, `py -3 -B` y `__pycache__` borrado. Resultados en §11.

| Mutación | Qué rompería si pasara |
|---|---|
| Jacobiano sin términos cruzados | Newton dejaría de converger o convergería a otro plano |
| Núcleo rectangular en vez de rombo | `14` volvería al régimen equivocado |
| No truncar el plano | se contaría tracción como alivio |
| `Iuv` mal escalado | los momentos del polígono dejarían de ser exactos |
| `Df/B` con umbral 10 | H7 dejaría pasar el doble |
| `Df/B` medido contra el lado mayor | H7 sería más permisivo de lo que dice el artículo |
| H7 traza pero no descarta | la decisión 3 quedaría a medias |
| `APOYA_EN_SUELO` deja de rechazarse | la decisión 5 quedaría anulada |
| C1 declarada por defecto | respondería la pregunta en silencio |
| Declarar C1 no levanta el TBD | la decisión 4 no serviría de nada |
| C-V sin el texto de alcance | se presentaría como verificación completa de E.060 |

---

## 10. Verificación posterior

```text
py -3 -m pytest -q                     1965 passed, 2 skipped
py -3 -m pytest tests/freeze -q         220 passed, 2 skipped
diff de ambas baselines contra el motor   0 casos, 0 campos
npx tsc --noEmit -p .                   limpio
npm run build                           correcto
```

`baseline.json` queda en `a05b59e4c255…` y `baseline_connected.json` en `1e466340149e…`.
`reference_pre_5a_non_beam.json` **no se tocó**: la entrada `shallow_foundation` se enumera
en `ENTRADAS_NUEVAS_TRAS_5A` junto a `shape_ratio`, con el test que exige que cada una
exista hoy y no existiera antes de 5A.

## 11. Mutaciones deliberadas

Sobre los cinco archivos de test afectados (119 tests), con `PYTHONDONTWRITEBYTECODE=1`,
`py -3 -B` y `__pycache__` borrado:

| Mutación | Tests que caen |
|---|---|
| Jacobiano sin términos cruzados | 8 |
| Núcleo rectangular en vez de rombo | 2 |
| No truncar el plano a su parte positiva | 10 |
| `Iuv` mal escalado | 24 |
| `Df/B` con umbral 10 | 16 |
| `Df/B` medido contra el lado mayor | 17 |
| H7 traza pero no descarta | 11 |
| `APOYA_EN_SUELO` deja de rechazarse | 13 |
| C1 declarada por defecto | 11 |
| Declarar C1 no levanta el TBD | 12 |
| C-V sin el texto de alcance | 10 |

Las once caen. La del núcleo rectangular cae en solo 2 y es correcto: distingue un régimen,
no un número, de modo que solo la ven los tests que preguntan por el régimen.
