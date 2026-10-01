# Auditoría de paridad entre tipologías

Fecha: 2026-09-19. Alcance: zapata aislada, combinada y conectada.
Método: se enumeraron **empíricamente** las verificaciones que cada motor emite en la traza
—recorriendo sus casos congelados— y se contrastó cada diferencia contra el texto de las
fuentes del proyecto. Una diferencia solo es admisible si la norma la justifica o si está
decidida y documentada; si no, es un olvido.

Resultado: **7 hallazgos**. Cuatro quedaron corregidos —H1, H2, H3 y H4—, uno es deuda
menor anotada y dos requieren decisión del usuario.

---

## Tabla de verificaciones por tipología

Solo lo que NO es propio de una tipología. El punzonamiento, la flexión y el cortante
existen en las tres con ids distintos, porque las secciones críticas lo son.

| Verificación | Aislada | Combinada | Conectada |
|---|---|---|---|
| `contact_pressure` | sí | sí | sí |
| `foundation_depth` (E.050 art. 26.2) | sí | sí | sí |
| `min_depth` (E.060 §15.7) | sí | **no → corregido (H1)** | sí |
| `sliding` / `overturning_x` / `overturning_y` | sí | sí, solo con fuerza horizontal | sí |
| `development_x` / `development_y` | sí | dentro de la entrada de flexión | sí |
| `shape_ratio` (E.050 art. 23.3) | sí (H6, 2026-09-20) | sí | sí (H6, 2026-09-20) |
| `self_weight`, `column_placement` | sí | no (H5) | sí |
| Cortante unidireccional transversal | sí (`shear_y`) | **no → corregido (H2)** | sí |
| Df/B ≤ 5 (E.050 art. 23.1) | sí (H7, 2026-09-20) | sí (H7, 2026-09-20) | sí (H7, 2026-09-20) |

---

## H1 — La combinada no verificaba el peralte mínimo de §15.7 · CORREGIDO

**Severidad: alta.** Producía CONFORME sobre un diseño que incumple una exigencia
prescriptiva de la norma.

E.060 §15.7, literal:

> «La altura de las zapatas, medida sobre el refuerzo inferior no debe ser menor de 300 mm
> para zapatas apoyadas sobre el suelo, ni menor de 400 mm en el caso de zapatas apoyadas
> sobre pilotes.»

No distingue tipología. §15.10.1 manda diseñar las zapatas que soportan más de una columna
«de acuerdo con los requisitos de diseño apropiados de esta Norma».

**Evidencia.** Una zapata combinada de 8,00 × 3,60 m con dos columnas de 120 kN y
`h = 0,20 m` salía **PASS, sin un solo motivo de descarte**. La aislada equivalente la
habría descartado.

**Corrección.** Se llama al mismo `E060ConcreteCode.min_depth_rule` con la misma
interpretación documentada (`docs/normativa/peralte_minimo_zapatas.md`), sobre `d_bottom`,
que es el peralte sobre el refuerzo INFERIOR que el artículo nombra. No hubo criterio nuevo
que decidir: la implementación ya existía y no se la llamaba.

**Impacto en baselines:** 4 casos de la combinada, 20 claves, **todas añadidas** (la
entrada nueva y `traza.orden`). Ningún número ni estado anterior se movió; los cuatro casos
tienen canto de sobra (d = 0,717 m) y siguen en PASS.

**Tests:** `tests/test_auditoria_paridad_tipologias.py`, 8 tests, entre ellos el guardián
genérico `test_las_tres_tipologias_verifican_lo_que_la_norma_no_distingue`. Mutación: 4
mutantes, 4 detectados.

## H2 — La combinada no verificaba cortante unidireccional TRANSVERSAL · CORREGIDO

**Severidad: media.** Era una verificación que la norma exige y que no se ejecutaba.

E.060 §15.5.1 remite al §11.12, y §11.12.1.1 describe el comportamiento **como viga ancha**:

> «Cada sección crítica que debe investigarse se extiende en un plano a través del ancho
> total del elemento.»

La aislada lo comprueba en las dos direcciones (`shear_x`, `shear_y`) y la conectada lo
hereda. La combinada comprobaba **solo la longitudinal**; sus franjas transversales
diseñan flexión y nada más.

**Criterio aprobado por el usuario (2026-09-19):**

1. sección crítica a **d de la cara de la columna** (§15.5.2, que remite a §15.4.2);
2. ancho resistente igual al **ancho total de la zapata** en ese plano, es decir su
   longitud completa — no el ancho de la franja transversal, que es un criterio de reparto
   del acero y no una sección resistente;
3. **Vu integrando la presión de contacto** sobre el área que queda fuera de la sección
   crítica;
4. `Vu ≤ φVc`.

**Qué presión.** La neta factorizada de la **resultante de todas las columnas**, reducida
al centroide con el término `P_i·offset_i` de cada carga descentrada: la misma reducción
que usa la presión de contacto. No la presión de franja `P_col/(ancho_franja·dim)`, que es
un criterio de reparto tomado de los apuntes y no describe el campo bajo el plano crítico.
El campo lo resuelve `NetPressureField`, de modo que el contacto parcial también queda bien
tratado.

**Qué plano.** Con varias columnas gobierna el que deja más área fuera, es decir el de la
columna con el voladizo transversal mayor. Se evalúan los dos lados de cada columna y todas
las combinaciones factorizadas.

**Verificación.** K1, reconstruido a mano sin llamar al motor: `q' = 2520/3,60 = 700,0
kN/m`, voladizo `1,800 − 0,250 = 1,550 m`, `d = 0,717 m` ⇒
`Vu = 700,0 × 0,833 = 583,100 kN`. El motor da 583,100.

**Impacto en baselines:** 4 casos de la combinada, 3 claves `numeros` + 1 `estados` + 1
`referencias` cada uno, **todas añadidas**. Los cuatro **pasan** la verificación nueva:
ninguna aceptación cambia.

**Tests:** 6 en `tests/test_auditoria_paridad_tipologias.py`. **Mutación: 5 mutantes, 5
detectados** —ancho resistente equivocado, ignorar la excentricidad transversal, no tomar
el peor Vu, fallar sin descartar, y perder la categoría del descarte—.

## H3 — `seismic_reduction_80pct` negaba lo que el motor hace · CORREGIDO

El registro decía «NO se aplica […] ni en la combinada» después de que la combinada
empezara a aplicarla (`docs/reduccion_sismica_combinada.md`). Texto corregido: se nombran
las tres tipologías y la única implementación, `depth_solver.soil_actions`. Se explica
además por qué el rótulo NO IMPLEMENTADO se conserva: lo que se declara como limitación es
el RESTO —modo directo, estabilidad, despegue, diseño factorizado—, donde la reducción
permitida no puede aplicarse.

Guardado con `test_el_registro_no_niega_una_reduccion_que_el_motor_si_aplica`, que lo
comprueba contra el solver y no contra una copia del texto.

## H4 — `horizontal_forces` presentaba los FS de la norma como los del motor · CORREGIDO

**Severidad: media**, y es exactamente lo que `CLAUDE.md` §8 prohíbe.

El registro decía: «FS por defecto de E.020 art. 21 (volteo 1,5), art. 22.1 (deslizamiento
1,25) y E.030 art. 64.2 (volteo sísmico 1,2)». Desde **D10-2b** el programa exige **1,50 en
los tres**, que en dos de ellos es MÁS ESTRICTO que la norma. Un lector del informe se
llevaba dos ideas falsas a la vez: que el motor exige 1,25 y 1,20, y que esos son «los FS
por defecto» en lugar de un criterio adoptado.

Texto corregido: separa el valor adoptado del valor de la fuente, dice cuál es más estricto
y añade el término `P·offset` y la envolvente de `FORMULACION_VOLTEO`. Guardado con
`test_el_registro_no_presenta_los_FS_de_la_norma_como_los_del_motor`, que compara los
números contra las constantes del motor.

## H5 — La combinada no emite `self_weight`, `column_placement` ni las limitaciones del registro

**Severidad: baja.** No falta ningún cálculo: el peso propio entra en la presión de
contacto y la posición de las columnas la valida `CombinedFootingLayout`. Lo que falta es
que aparezcan en la traza, de modo que un lector de la memoria de la combinada no puede
auditar esos dos números como sí puede en la aislada.

`collect_applicable_limitations` solo lo llama la aislada. En la combinada la única
limitación que hoy sería aplicable —la reducción sísmica no disponible— sí llega, por otra
vía: como hipótesis de la entrada de presión de contacto.

**No se corrige en esta sesión** porque añadiría entradas a la traza de los cuatro casos
congelados por una mejora de presentación, y hay hallazgos con más valor por delante. Queda
anotado como deuda menor.

## H6 — `shape_ratio` (E.050 art. 23.3) solo se comprobaba en la combinada · **CERRADA**

La tabla del art. 23.3 se refiere a **«las zapatas y plateas»**, no a las combinadas:

| Zapata | Dimensiones |
|---|---|
| Cuadrada | L = B |
| Rectangular | L ≤ 10 B |
| Continua | L > 10 B |

La combinada la trata como límite de alcance: por encima de 10 el elemento «es una
cimentación continua, no una zapata combinada», y descarta. La aislada no la mira, y su
`max_LB_ratio` es un parámetro de BÚSQUEDA con `gt=1.0`: un usuario puede pedir 15 y obtener
el diseño de un cimiento corrido presentado como zapata aislada.

**Por qué no se extrapola por cuenta propia.** El artículo CLASIFICA, no prohíbe: las cuatro
formas de la tabla son admisibles, y «continua» es una de ellas. Convertir esa clasificación
en un FAIL de la aislada es adoptar la misma lectura que ya se adoptó para la combinada,
pero es una lectura, y cambiaría qué alternativas acepta la aislada. `CLAUDE.md` §3 manda
tratarlo como decisión de ingeniería.

**Opciones:**

- **A.** Extender el mismo FAIL a la aislada y a las zapatas de la conectada. Coherente con
  lo ya decidido; añade una entrada de traza a ~22 casos congelados (todos PASS).
- **B.** Emitirlo como INFO o WARNING en lugar de FAIL, porque el artículo clasifica.
  Informa sin descartar, pero rompe la paridad con la combinada, que sí descarta.
- **C.** Dejarlo como está y registrar la asimetría en el catálogo de diferencias.

### Resuelta el 2026-09-20: opción A

Decisión del usuario: la proporción se verifica en **todas** las zapatas del programa y
pasarse **descarta** la alternativa. Descartado el WARNING de la opción B: si el programa
verifica el criterio, lo verifica.

**El umbral es el 10 del artículo.** La propuesta llegó con `L/B ≤ 5`, y el 5 no es de este
artículo: pertenece al **23.1** y es `Df/B`, profundidad sobre ancho —el criterio que define
una cimentación como superficial, que es el pendiente **H7**, distinto de éste—. La tabla
del 23.3 dice `L ≤ 10 B` para la rectangular y para la combinada. Adoptar 5 sería un
criterio del programa más estricto que la norma y habría que declararlo como tal, igual que
los FS de D10-2b; queda como decisión abierta.

**Implementación.** Una sola, `engine.codes.peru.e050_soils.check_shape_ratio`, usada por
las tres tipologías; `engine/domain/combined_layout.py` pierde su constante propia, porque
duplicarla fue lo que permitió que la aislada no mirara el artículo. `shape_ratio` entra en
`COMUNES_A_LAS_TRES`, que impide que vuelva a perderse. Diff y congelamiento en
`docs/freeze_zona_contacto_y_proporcion.md` §4; tests en
`tests/test_proporcion_e050_art23_3.py`.

Recomendación: **A**, por coherencia, y revisar de paso si la combinada debería ser INFO.

## H7 — Nadie comprobaba el art. 23.1 (Df/B ≤ 5) · **CERRADA**

E.050 art. 23.1 define cimentación superficial como aquella con `Df/B ≤ 5`. Todo el
Capítulo IV —y con él el modelo de presión admisible que usa el motor— se aplica a
cimentaciones superficiales. Ninguna tipología comprueba la relación.

Con `Df = 3,0 m` y `B = 0,50 m` el motor diseñaría tan tranquilo una zapata que la propia
E.050 ya no clasifica como superficial, y cuya capacidad portante no se obtiene con las
expresiones del capítulo.

**Por qué no se decide aquí.** Hay que elegir qué significa pasarse: ¿FAIL, porque el modelo
deja de aplicar? ¿NO VERIFICADO, porque el motor no puede pronunciarse fuera del alcance de
su capítulo? La segunda parece más honesta —no es que el diseño sea malo, es que el programa
no sabe juzgarlo—, pero fija el significado de un estado y eso es decisión del usuario.

---

### Resuelta el 2026-09-20: FAIL

Decisión del usuario: **FAIL si `Df/B > 5`**, en las tres tipologías. El programa diseña
cimentaciones superficiales, y permitir superar ese límite marcándolo solo como NO
VERIFICADO deja abierta una entrada físicamente fuera del alcance del modelo. Se documenta
como **condición de aplicabilidad del programa**, con referencia al art. 23.1.

**Qué es «B»:** el lado MENOR. El artículo dice «el ancho o diámetro de la misma», y tomar
el lado mayor daría una relación más pequeña y dejaría pasar geometrías que el artículo
excluye.

**Lo que la hipótesis declara:** no es que la norma lo prohíba —el art. 23.1 DEFINE, no
prohíbe—, es que por encima de esa relación el elemento es una cimentación profunda,
gobernada por mecanismos que este motor no modela. Es la misma lectura de alcance que la
del 23.3 en H6.

Implementación única en `engine.codes.peru.e050_soils.check_shallow_foundation`;
`shallow_foundation` entra en `COMUNES_A_LAS_TRES`. Ningún caso congelado falla. Diff y
congelamiento en `docs/freeze_contacto_unilateral.md` §3.

## Lo que la auditoría comprobó y encontró bien

- **Regla de aceptación:** `NO_FAIL` en las tres (decisión 6), en el catálogo y en los tres
  generadores.
- **Reducción sísmica al 80 % e incremento del 30 %:** una sola implementación cada uno
  (`soil_actions`, `effective_qadm`), usada por las tres.
- **Punzonamiento:** las tres reducen la excentricidad igual, con `self_weight = 0` en el
  numerador, y pasan `ex`/`ey` al chequeo.
- **Presión de contacto:** el mismo modelo y el mismo trato de `within_kern` en las tres; el
  incumplimiento del núcleo central es FAIL en todas.
- **Acero mínimo:** las tres pasan por `rho_min_temperature` y por el reparto en dos caras.
- **Trazas:** ninguna entrada sin referencia normativa, sin unidad ni sin ecuación
  sustituida; ningún `open_tbd` colocado sobre un estado que no sea NO VERIFICADO.
- **Hipótesis:** 74 entradas no declaraban ninguna. Corregido (ver abajo).

## Auditoría de trazas — hipótesis ausentes · CORREGIDO

Una entrada sin hipótesis se lee como «esto está verificado, sin más», y casi nunca es
cierto. Se encontraron 74 entradas en cinco verificaciones:

| Verificación | Entradas | Qué faltaba declarar |
|---|---|---|
| `foundation_depth` | 35 | Que el art. 26.2 pone la estratigrafía, los cambios de volumen y las condiciones de uso en manos del profesional responsable, y que el motor solo comprueba el mínimo numérico |
| `beam_dimension` | 13 | Que `ln` se mide entre caras y que la sección de la viga es dato, no variable de diseño |
| `beam_shear_av_min` | 13 | Que clasificar la viga de conexión como VIGA —y no como losa o zapata— es una decisión declarada, de la que depende que no le alcance la exención de §11.5.6.1(a) |
| `beam_stirrup_spacing` | 9 | Que es la separación por RESISTENCIA y que el confinamiento de §21.12.3.2 puede reducirla después |
| `shape_ratio` | 4 | La lectura adoptada del art. 23.3: clasifica, no prohíbe; se usa como límite de alcance |
| `beam_shear_steel` | 2 | Que no se redistribuye cortante entre secciones |

El alcance del art. 26.2 se declara ahora en **una sola fuente**
(`foundation_depth.SCOPE_NOTES`) y las tres tipologías la usan: antes cada solver armaba su
propia lista y las tres omitían lo mismo.

`hypotheses` es prosa y no está congelada, de modo que el congelamiento no protege esto.
Lo protege `test_ninguna_entrada_de_traza_se_queda_sin_hipotesis`, que recorre las cuatro
tipologías y exige que ninguna entrada se quede muda.
