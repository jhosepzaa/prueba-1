# Referencias normativas del proyecto

**Revisión: 20 de agosto de 2026.** Sustituye a la ficha de Fase 2.

## Estado de las fuentes primarias

| Norma | Archivo | Estado | Alcance verificable hoy |
|---|---|---|---|
| **E.050** Suelos y Cimentaciones | `Norma E.050 Suelos y cimentaciones (1).pdf` — SENCICO, 1.ª ed. digital, diciembre 2020 | ✅ **Primaria disponible** | Completo |
| **E.030** Diseño Sismorresistente | `E.030 Diseño sismorresistente (2026).pdf` — RM 183-2026-VIVIENDA, El Peruano, 3 mayo 2026 | ✅ **Primaria disponible, vigente** | Completo |
| **E.030** (versión anterior) | `e060 actualizada.pdf` — firmada 30.10.2025 | ⚠️ **Archivo mal rotulado**: contiene E.030 (2025), no E.060 | Solo para contraste de versiones |
| **E.060** Concreto Armado | `Norma E.060 Concreto armado.pdf` — 44 pp. | ✅ **Primaria disponible** | Completo |

> **Nota sobre el archivo mal rotulado.** `e060 actualizada.pdf` sigue conteniendo
> E.030 (versión de octubre de 2025), no E.060. La E.060 llegó en un archivo aparte.
> Las tres normas están ahora disponibles como fuente primaria.

## Jerarquía de fuentes

1. **Autoridad normativa**: E.050, E.060, E.030. Nada las sustituye.
2. **Benchmarks de validación**: apuntes de *Concreto Armado 2*, John P. Aragón Brousset.
   Sirven para contrastar resultados numéricos, **nunca como autoridad normativa**.
   Las discrepancias con la norma se documentan, no se ocultan.
3. **Derivaciones y criterios**: ver la clasificación de tres niveles más abajo.

---

## Clasificación de tres niveles

Toda regla del motor pertenece a exactamente una categoría:

| Nivel | Definición | Puede dar PASS/FAIL |
|---|---|---|
| **A — Requisito normativo** | Respaldado directamente por una sección citable | Sí |
| **B — Derivación de ingeniería** | La norma da el principio; la expresión para una geometría concreta se deriva matemáticamente | Sí, con la derivación declarada |
| **C — Criterio / heurística** | Práctica profesional o de predimensionamiento | **No.** Solo INFO |

---

## E.060 Concreto Armado

**Verificado contra fuente primaria el 20/08/2026.**

| # | Tema | Artículo/Ec. | Contenido | Nivel | Estado |
|---|---|---|---|---|---|
| 1 | Cargas para área de zapata | §15.2 | Fuerzas/momentos no amplificados (servicio) | A | Implementado |
| 2 | No tracciones suelo-zapata | §15.2 | «no se deberán considerar las tracciones» | A | Implementado |
| 3 | Incremento 30% qadm | §15.2 | Opcional | A | Implementado — **default OFF** |
| 4 | Reducción sísmica 80% | §15.2 | Opcional, solo esfuerzos en el suelo | A | Implementado — **default OFF**. Ver E.030 art. 29 y 62.2, que ahora aportan fuente primaria concordante |
| 5 | Combinaciones factorizadas | §9.2, ec. 9-1 a 9-5 | U=1,4CM+1,7CV; sismo y viento | A | El usuario entrega P, Mx, My ya combinados |
| 6 | Factores φ | **§9.3.2** | Flexión sin carga axial 0,90; cortante y torsión 0,85 | A | Implementado. ✅ Cita corregida en Fase 1A (§9.4 → §9.3.2) |
| 7 | f'c mínimo | §9.4 | 17 MPa | A | Implementado |
| 8 | Hipótesis de flexión | §10.2 | εcu=0,003; bloque 0,85f'c; β1=0,85 para f'c 17–28 MPa | A | Implementado |
| 9 | Sección crítica de momento | §15.4(a) | Cara de columna | A | Implementado |
| 10 | Reparto dirección corta | §15.4, ec. 15-1 | γs = 2/(β+1) | A | Implementado |
| 11 | Cortante unidireccional | §15.5 → §11.3.1.1, ec. 11-3 | Sección a d de la cara; Vc = 0,17√f'c·bw·d | A | Implementado |
| 12 | Punzonamiento | §11.12.1.2, §11.12.2.1 | Sección crítica **de perímetro bo mínimo**, no más cerca de d/2 de bordes o esquinas; Vc = mín(11-33, 11-34, 11-35) | A | ✅ **Implementado completo en Fase 1C**: perímetro de 4, 3 o 2 lados según truncamiento contra el borde |
| 13 | As_min en zapatas | §10.5.1 (excluye zapatas y losas macizas) + §10.5.4 + §9.7 | ρmin 0,0018 / 0,0020 / 0,0025 | A | Implementado — ver `as_min_zapatas.md` |
| 14 | Peralte mínimo | §15.7 | h ≥ 300 mm sobre el refuerzo inferior | A + interpretación | Implementado — ver `peralte_minimo_zapatas.md` |
| 15 | Recubrimiento | §7.7.1 | Tabla completa transcrita abajo | A | Implementado solo el caso (a) de 70 mm |
| 16 | Separación libre mínima | §7.6.6 | máx(db, 25 mm) | A | Implementado |
| 17 | Separación máxima | §9.7.3 | mín(3h, 400 mm) | A | Implementado |
| 18 | Interacción §15.4.4 con §9.7 | — | E.060 no la resuelve | B | Decisión conservadora documentada abajo |
| 19 | **Transferencia de momento** | §11.12.6, ec. 11-39/11-40 | γv·Mu por excentricidad del cortante | A | ✅ **IMPLEMENTADO** en `punching_moment_transfer.py`. *La ficha anterior lo declaraba NO IMPLEMENTADO: era información desactualizada.* |
| 20 | γf | ec. 13-1 | γf = 1/(1 + (2/3)√(b1/b2)) | A | Implementado |
| 21 | Desarrollo en tracción | §12.2, Tabla 12.1, ec. 12-1 | ψt, ψe, ψs, λ | A | Implementado |
| 22 | Ganchos | §12.5 | ldg = 0,24ψeλfy/√f'c·db | A | Implementado |

### Secciones de E.060 extraídas el 20/08/2026

Transcripciones literales de la fuente primaria. Todas son **nivel A**.

#### §7.7.1 — Recubrimiento, concreto construido en sitio no preesforzado

| Condición | Recubrimiento |
|---|---|
| (a) Concreto colocado contra el suelo y expuesto permanentemente a él | **70 mm** |
| (b) En contacto permanente con el suelo o la intemperie — barras 3/4" y mayores | **50 mm** |
| (b) En contacto permanente con el suelo o la intemperie — barras 5/8" y menores, mallas | **40 mm** |
| (c) No expuesto a la intemperie ni en contacto con el suelo — losas, muros, viguetas, barras ≤ 1 3/8" | **20 mm** |
| (c) No expuesto — **vigas y columnas: armadura principal, estribos y espirales** | **40 mm** |

> **Consecuencia.** El recubrimiento de la cara superior de una zapata combinada y el de la
> viga de conexión **dependen de la condición de exposición**, que es un dato de proyecto,
> no una constante. Debe ser **entrada declarada por el usuario**, no un valor elegido por
> el programa.

#### §9.3.2 — Factores de reducción de resistencia φ

| Solicitación | φ |
|---|---|
| Flexión sin carga axial | 0,90 |
| **Carga axial de tracción con o sin flexión** | **0,90** |
| Carga axial de compresión con o sin flexión — refuerzo en espiral (10.9.3) | 0,75 |
| **Carga axial de compresión con o sin flexión — otros elementos** | **0,70** |
| Cortante y torsión | 0,85 |
| Aplastamiento en el concreto | 0,70 |

> «Para elementos en flexocompresión puede incrementarse linealmente hasta 0,90 en la medida
> que Pn disminuye desde 0,1 f'c Ag ó Pb, el que sea menor, hasta cero.»

**Corrección al código.** `e060_concrete.py::phi_factors` devuelve
`code_reference="E.060 §9.4"`. La sección correcta es **§9.3.2**; §9.4 es
«Resistencia mínima del concreto estructural» (f'c ≥ 17 MPa), que sí está bien citada
en `fc_min_MPa`.

#### §10.5 — Refuerzo mínimo en elementos sometidos a flexión

- **§10.5.1** — «En cualquier sección de un elemento estructural — **excepto en zapatas y
  losas macizas** — sometido a flexión… Mn ≥ 1,2 Mcr», con `Mcr = fr·Ig/Yt` y
  `fr = 0,62√f'c`.
- **§10.5.2** — ec. (10-3): `As_min = (0,22√f'c / fy)·bw·d` para secciones rectangulares y
  secciones T con el ala en compresión.
- **§10.5.3** — No es necesario satisfacer 10.5.1 ni 10.5.2 si el área proporcionada es al
  menos **un tercio superior** a la requerida por análisis.
- **§10.5.4** — «Para losas estructurales y zapatas de espesor uniforme, el acero mínimo en
  la dirección de la luz debe ser el requerido por 9.7. **Cuando el acero mínimo se
  distribuya en las dos caras de la losa, deberá cumplirse que la cuantía de refuerzo en la
  cara en tracción por flexión no sea menor de 0,0012.** El espaciamiento máximo del
  refuerzo no debe exceder tres veces el espesor ni de 400 mm.»

> **Consecuencia.** §10.5.4 es el anclaje normativo del **acero de cara superior de la zapata
> combinada**: contempla explícitamente el mínimo repartido en dos caras, con ρ ≥ 0,0012 en
> la cara traccionada. La regla de vigas (§10.5.1 y §10.5.2) es distinta y **no aplica a
> zapatas**, que quedan excluidas por el propio §10.5.1.

#### §11.5 — Resistencia proporcionada por el refuerzo de cortante

- **§11.5.2** — fy y fyt del refuerzo de cortante **no deben exceder 420 MPa**.
- **§11.5.5.1** — El espaciamiento del refuerzo perpendicular al eje **no debe exceder d/2**
  en concreto no preesforzado, **ni 600 mm**.
- **§11.5.5.3** — Donde `Vs > 0,33√f'c·bw·d`, las separaciones máximas **se reducen a la
  mitad**.
- **§11.5.6.1** — Av_min se exige donde `Vu > 0,5·Vc`, **excepto en: (a) losas y zapatas**;
  (b) losas nervadas y aligerados según 8.11; (c) vigas con h ≤ máx(250 mm, 2,5·espesor del
  ala, 0,5·ancho del alma).
- **§11.5.6.2** — ec. (11-13): `Av_min = 0,062√f'c·bw·s/fyt`, **pero no menor que
  `0,35·bw·s/fyt`**.
- **§11.5.7.2** — ec. (11-15): `Vs = Av·fyt·d/s`.
- **§11.5.7.9** — «En ningún caso se debe considerar Vs mayor que `0,66√f'c·bw·d`».

> **Consecuencia — corrige la auditoría de Fase 0.** §11.5.6.1(a) **exime a losas y zapatas
> del refuerzo mínimo de cortante**. Una zapata combinada no necesita Av_min aunque
> `Vu > 0,5·Vc`; solo necesita Vs si `Vu > φVc`. La preocupación registrada en la Rev. 1
> sobre estribos en zapatas combinadas queda acotada.

#### §11.12.1.2 — Ubicación de la sección crítica de punzonamiento

> «La superficie crítica equivalente que deberá investigarse estará localizada de modo que
> **su perímetro, bo, sea mínimo**, pero no necesita estar más cerca de d/2 desde: (a) los
> bordes o las esquinas de las columnas, cargas concentradas, o áreas de reacción, o (b) los
> cambios en el espesor de la losa…»
>
> «Para columnas cuadradas o rectangulares… se permite utilizar secciones críticas
> equivalentes con cuatro lados rectos.»

> **Consecuencia.** El **perímetro truncado de una columna de borde es exigencia normativa**,
> no una derivación: la norma obliga a tomar la sección de bo mínimo. La licencia de «cuatro
> lados rectos» se refiere a la *forma* de los lados, no a que la sección deba cerrarse por
> los cuatro. Esto eleva el perímetro truncado de nivel B a **nivel A**.

#### §11.12.2.1(b) — Valores de αs

> «donde αs es **40 para columnas interiores, 30 para columnas de borde, y 20 para columnas
> en esquina**.»

> **Límite de la norma.** E.060 da los valores pero **no define qué convierte a una columna en
> interior, de borde o de esquina**. La clasificación sigue siendo una **interpretación a
> declarar**. Recomendación mantenida: clasificar por el truncamiento geométrico de la sección
> crítica, coherente con que αs aparece en la misma ecuación que bo.

#### §11.12.3 — Refuerzo de cortante en losas y zapatas

Se permite refuerzo de cortante (barras, alambres y estribos) en losas y zapatas con
**d ≥ 150 mm** y no menor de 16 veces el diámetro de la barra de refuerzo por cortante.
Vc no debe tomarse mayor que `0,17√f'c·bo·d` y Vs se calcula según §11.5.
**§11.12.3.2** — Vn no debe considerarse mayor que `0,5√f'c·bo·d`.

#### §15.4 — Momentos flectores en zapatas

- **§15.4.1** — «El momento flector en **cualquier sección** de una zapata debe determinarse
  pasando un plano vertical a través de la zapata, y calculando el momento de las fuerzas que
  actúan sobre el área total de la zapata que quede a un lado de dicho plano vertical.»
- **§15.4.2** — «**Para una zapata aislada** el momento máximo amplificado Mu debe calcularse
  en la forma indicada en 15.4.1, en las secciones críticas…»: (a) cara de columna, pedestal o
  muro de concreto; (b) punto medio entre eje y borde para muros de albañilería; (c) punto
  medio entre cara de columna y borde de la plancha para columna con plancha de apoyo.
- **§15.4.3** — Zapatas armadas en una dirección y cuadradas armadas en dos: refuerzo
  distribuido uniformemente en el ancho total.
- **§15.4.4** — Zapatas **rectangulares** armadas en dos direcciones: dirección larga uniforme;
  dirección corta con γs·As en una franja centrada de ancho igual al lado corto, resto
  repartido fuera. Ec. (15-1): `γs = 2/(β+1)`.

> **Consecuencia doble.**
> 1. **§15.4.1 es general y sirve para la zapata combinada**: define el momento en cualquier
>    sección por estática sobre el área a un lado del plano. Los diagramas V(x) y M(x) pasan de
>    ser derivación (nivel B) a **aplicación directa de §15.4.1 (nivel A)**. §15.4.2 está
>    explícitamente acotado a la *zapata aislada*.
> 2. **§15.4 no fija ningún ancho de franja transversal para zapatas de varias columnas.**
>    El criterio de «b + d/2 a cada lado» de los apuntes de Aragón queda confirmado como
>    **nivel C**, no normativo.

#### §15.10 — Zapatas combinadas y losas de cimentación

- **§15.10.1** — «Las zapatas que soporten **más de una columna**, pedestal o muro (zapatas
  combinadas y losas de cimentación) deben diseñarse para resistir las cargas amplificadas y
  las reacciones inducidas, de acuerdo con los requisitos de diseño apropiados de esta Norma.»
- **§15.10.2** — «**El Método Directo de Diseño del Capítulo 13 no debe utilizarse** para el
  diseño de zapatas combinadas y losas de cimentación.»
- **§15.10.3** — «La distribución de la presión del terreno bajo zapatas combinadas y losas de
  cimentación debe ser consistente con las propiedades del suelo y la estructura y con los
  principios establecidos de mecánica de suelos.»

> **Consecuencia.** E.060 reconoce la zapata combinada y **no prescribe un método**: exige
> aplicar los requisitos generales y prohíbe uno concreto. El enfoque de estática con V(x) y
> M(x) es admisible bajo §15.10.1 y §15.4.1. La hipótesis de distribución lineal de presiones
> debe declararse conforme a §15.10.3.

#### §15.7 — Peralte mínimo (cláusula adicional no implementada)

> «La altura de las zapatas, medida sobre el refuerzo inferior no debe ser menor de 300 mm
> para zapatas apoyadas sobre el suelo, ni menor de 400 mm en el caso de zapatas apoyadas
> sobre pilotes. **El peralte de la zapata deberá ser compatible con los requerimientos de
> anclaje de las armaduras de las columnas, pedestales y muros que se apoyen en la zapata.**»

La segunda frase **no está implementada**: el motor no verifica el anclaje de las barras de
la columna dentro de la zapata.

#### §21.12.3 — Vigas en la cimentación

- **§21.12.3.1** — Las vigas que actúan como acoples horizontales entre zapatas o cabezales
  deben tener **refuerzo longitudinal continuo**, desarrollado dentro o más allá de la
  columna, o anclado dentro de la zapata en todas las discontinuidades.
- **§21.12.3.2** — «…deben diseñarse de tal manera que **la menor dimensión transversal sea
  igual o mayor que el espacio libre entre columnas conectadas dividido por 20, pero no
  necesita ser mayor a 400 mm**. Se deben proporcionar **estribos cerrados con un
  espaciamiento que no exceda al menor de: la menor dimensión de la sección transversal,
  300 mm ni de 16 db**.»
- **§21.12.3.3** — Las vigas de cimentación sometidas a flexión por columnas que forman parte
  del sistema resistente a fuerzas laterales deben cumplir §21.4 o §21.5 según el sistema.
- **§21.12.1.1** (alcance) — «Las cimentaciones resistentes a las fuerzas sísmicas o que
  transfieran las fuerzas sísmicas entre la estructura y el terreno deben cumplir con lo
  indicado en 21.12.»

> **Consecuencia — resuelve TBD-7.** Existe un requisito dimensional normativo para la viga de
> conexión: `b_min ≥ L_libre / 20`, con tope en 400 mm, más estribos cerrados con separación
> máxima. **No sustituye** a `h ≈ L/7` de los apuntes, que sigue siendo nivel C: la norma fija
> una dimensión mínima, no verifica la premisa de presión uniforme por rigidez del conjunto.

---

### Corrección respecto a la ficha anterior

La entrada 19 declaraba §11.12.6 como **NO IMPLEMENTADO** y enumeraba tres piezas
faltantes (γf por ec. 13-1, la propiedad Jc y el esfuerzo combinado). **Las tres
existen** desde que se añadió `engine/foundation/punching_moment_transfer.py`. La
ficha quedó desactualizada y podía inducir a error sobre el alcance real del motor.

### Hallazgo vigente: interacción no resuelta entre §15.4.4 y §9.7

Cuando el acero de la dirección corta está gobernado por la cuantía mínima de §9.7,
repartirlo según §15.4.4 deja las franjas exteriores por debajo de esa misma cuantía:

```
(1 − γs) = (B − L)/(B + L)
As_exterior = (B−L)/(B+L) · ρmin · B · h
As_min exigido en ancho (B−L) = ρmin · (B−L) · h
cociente = B/(B+L) < 1        → quedan cortas
```

E.060 no resuelve explícitamente esta interacción. **Decisión adoptada (nivel B,
conservadora):** elevar cada franja a su propio mínimo de §9.7. Registrado en el
campo `topped_up` y en el `CalculationTrace`.

---

## E.050 Suelos y Cimentaciones

**Verificado contra fuente primaria el 20/08/2026.**

| # | Tema | Artículo | Contenido verificado | Nivel | Estado |
|---|---|---|---|---|---|
| 1 | Cargas para FS | 17.1 | «las Cargas de Servicio que se utilizan para el diseño estructural de las columnas del nivel más bajo» | A | Implementado |
| 2 | Capacidad última qd | 20 | Remite a Bowles (1996) | A | Fuera de alcance: qadm es dato de entrada |
| 3 | **Factor de seguridad por corte** | **21.1 / 21.2** | **Estáticas: 3,0. Sismo o viento (la más desfavorable): 2,5** | A | Contexto; qadm entra ya afectado |
| 4 | Presión admisible | 22 | Factores a considerar; 22.2.2 asentamiento admisible | A | qadm es dato |
| 5 | Cimentación superficial | 23.1 | D/B ≤ 5 | A | Implementado como validador |
| 6 | **Tipologías reconocidas** | **23.2** | **«Son cimentaciones superficiales las zapatas aisladas, conectadas y combinadas»** | A | 🆕 Respaldo normativo explícito de las tres tipologías del proyecto |
| 7 | **Forma y proporción** | **23.3** | Cuadrada L=B · Rectangular L ≤ 10B · **Combinada L ≤ 10B** · Continua L > 10B | A | 🆕 **No implementado.** `max_LB_ratio` usa 2,0 por defecto, que es heurística propia, no la frontera normativa |
| 8 | **Peralte de la cimentación** | **23.3, nota** | «El peralte de la cimentación (h) debe ser determinado por el ingeniero que efectúa el diseño estructural» | A | 🆕 E.050 delega h explícitamente en E.060 |
| 9 | Suelos no permitidos | 24 | Turba, orgánico, relleno no controlado | A | Fuera de alcance |
| 10 | **Profundidad mínima** | **26.2** | **«no siendo menor de 0,80 metros»** salvo cimentación sobre roca | A | ✅ **Implementado** en `engine/soil/foundation_depth.py`. Aplicado en zapata aislada (`depth_solver`), combinada (`combined_solver`) y conectada (ámbito de sistema). La excepción de roca la declara el usuario (`founded_on_rock`); el motor nunca la deduce |
| 11 | Presión admisible | 27 | Remite al Capítulo III | A | — |
| 12 | **Cargas excéntricas** | **28.1** | **ex = Mx/Q, ey = My/Q** | A | ✅ **Implementado.** El motor adopta esta convención en todo el flujo. Corroborada de forma independiente por Aragón 3.4.1, que titula «Diseño por flexión Dir. X (Momentos alrededor de Y)» |
| 13 | Área efectiva | 28.2 / 28.3 | B' = B − 2e, L' = L − 2e; el CG del área efectiva coincide con la carga | A | Stub `EffectiveAreaModel`, fuera del MVP |
| 14 | Cargas inclinadas | 29 | Modifican la superficie de falla | A | Fuera de alcance |
| 15 | Taludes | 30.3 | FS talud 1,5 estático / 1,25 pseudo-dinámico | A | Fuera de alcance |
| 16 | **FS de muros de contención** | **39.13.6** | **«El diseño del muro de contención debe cumplir…» 1,50 estático / 1,25 pseudo-dinámico** | A | ✅ **Confirmado: aplica solo a muros de contención.** Valida la nota `FS_REFERENCE_NOTE` de `stability.py`, que ya advertía de esto |

---

## E.030 Diseño Sismorresistente

**Fuente primaria incorporada el 20/08/2026.** Versión vigente: RM 183-2026-VIVIENDA.

| # | Tema | Artículo | Contenido verificado | Nivel | Estado |
|---|---|---|---|---|---|
| 1 | **Reducción de fuerzas sísmicas** | **29** | «Cuando se realicen verificaciones por esfuerzos admisibles, las fuerzas sísmicas obtenidas con esta Norma Técnica se multiplican por 0,8» | A | 🆕 Fuente primaria del factor 0,8, hasta ahora atribuido solo a E.060 §15.2 |
| 2 | Cimentación, hipótesis de apoyo | 62.1 | Concordantes con el suelo y el tipo de cimentación | A | Contexto |
| 3 | **Presiones para esfuerzos admisibles** | **62.2** | Se calculan con las fuerzas del análisis sísmico multiplicadas por 0,8, según art. 29 | A | 🆕 Concordante con la opción ya implementada |
| 4 | Presión admisible y sismo | 63.1 | El EMS debe considerar los efectos de los sismos | A | Contexto: qadm es dato |
| 5 | Licuación | 63.2 | Investigación geotécnica específica | A | Fuera de alcance |
| 6 | **Momento de volteo** | **64.2** | **«El factor de seguridad calculado con las fuerzas que se obtienen en el análisis estructural, sin considerar la reducción establecida en el artículo 29, debe ser mayor o igual que 1,2»** | A | 🆕 **No implementado.** `FS_overturning_required` no tiene valor por defecto y el motor reporta NO VERIFICADO. **Ésta es la referencia que faltaba** |
| 7 | **Elementos de conexión** | **65.1** | Ver transcripción abajo | A | 🆕 **No implementado.** Resuelve TBD-6 |
| 8 | Zapatas sobre pilotes | 65.2 | Vigas de conexión considerando giros y deformaciones; pilotes con resistencia en tracción ≥ 15% de la carga vertical | A | Fuera de alcance (no hay pilotes en el motor) |
| 9 | Perfiles de suelo S0–S4 | 14 | Clasificación por Vs, SPT o Su en los 30 m superiores | A | Dato del EMS, entrada del usuario |

### Transcripción literal de E.030 art. 65.1

> «Para zapatas aisladas con o sin pilotes en suelos tipo S3 y S4, para las Zonas 3
> y 4, y en general para suelos con una presión admisible menor que 0,10 MPa, se
> provee elementos de conexión en ambas direcciones, los que se diseñan en tracción
> o compresión, para una fuerza horizontal mínima equivalente al 10% de las cargas
> verticales amplificadas que soporta la zapata, adicionalmente a las solicitaciones
> por flexión que pudieran existir.»

**Consecuencia de diseño.** La viga de conexión **no es un elemento a flexión pura**:
cuando se cumple la condición de disparo, debe diseñarse a **flexo-tracción o
flexo-compresión** con N ≥ 0,10 · ΣPu. Esto amplía el alcance de la Fase 3 respecto a
lo previsto en la auditoría de Fase 0.

**Condición de disparo.** Se activa por *(S3 o S4)* **y** *(Zona 3 o 4)*, o bien por
qadm < 0,10 MPa. Los tres datos provienen del EMS y deben ser **entradas declaradas
por el usuario**: el programa no puede derivarlos.

**Nota de versiones.** El requisito es sustantivamente idéntico en la versión de 2025
(`e060 actualizada.pdf`, art. 65), que lo numera 65.1/65.2 de otro modo y dice «baja
capacidad portante» donde la de 2026 dice «baja presión admisible». Se cita la de 2026
por ser la vigente.

---

## Nivel C — Criterios y heurísticas

**Ninguno de estos puede producir PASS ni FAIL.** Se registran como INFO.

| Criterio | Origen | Uso | Estado |
|---|---|---|---|
| Rango automático de búsqueda A ≈ P/qadm, 0,60√A a 2,20√A | Heurística propia | Acotar el barrido | Implementado con leyenda «no criterio de diseño» |
| `max_LB_ratio = 2,0` | Heurística propia | Acotar el barrido | Implementado. **No confundir con E.050 23.3 (L ≤ 10B)**, que es de nivel A y tiene otro propósito |
| Índice de complejidad constructiva | Heurística propia | Ordenar alternativas | Implementado y declarado |
| Separaciones «habituales en obra» | Práctica constructiva | Heurística de constructibilidad | Implementado y declarado |
| h ≈ L/7 de la viga de conexión | Apuntes Aragón | Predimensionamiento | No implementado |
| L/B = 2 a 2,5 de la zapata excéntrica | Apuntes Aragón | Predimensionamiento | No implementado |
| Umbral de 6 m conectada vs. combinada | Apuntes Aragón | Orientación de tipología | No implementado |
| Ancho de franja transversal b + d/2 por lado | Apuntes Aragón | Modelación de combinada | No implementado. **Pendiente de contrastar con §15.4 completo** |

---

## Nivel B — Derivaciones declaradas

| Derivación | Principio normativo que la respalda | Módulo |
|---|---|---|
| Distribución lineal q = P/A(1 ± 6e/B ± 6e/L) | Mecánica de materiales | `contact_pressure.py` |
| Condición de núcleo central | Derivada de la prohibición de tracciones, E.060 §15.2 | `contact_pressure.py` |
| Jc de la sección crítica de 4 lados | §11.12.6.2 exige variación lineal; no da Jc | `punching_moment_transfer.py` |
| Superposición biaxial del esfuerzo de punzonamiento | Extensión del principio lineal de §11.12.6.2 | `punching_moment_transfer.py` |
| Momento de carga trapezoidal en voladizo | Resistencia de materiales | `flexure.py` |
| Elevación de franjas al mínimo de §9.7 | Interacción no resuelta por E.060 | `short_direction.py` |
| Conversión bruta ↔ neta | Práctica geotécnica (Terzaghi/Peck) | `pressure_basis.py` |

---

## Matriz de trazabilidad: norma → módulo → test

| Norma y sección | Cálculo | Módulo | Test |
|---|---|---|---|
| E.060 §9.4 | Factores φ, f'c mínimo | `codes/peru/e060_concrete.py` | `test_e060_concrete.py` |
| E.060 §10.2 | Bloque 0,85f'c, flexión | `foundation/flexure.py` | `test_flexure.py` |
| E.060 §9.7, §10.5.1, §10.6 | As mínimo en zapatas | `codes/peru/e060_concrete.py` | `test_e060_concrete.py` |
| E.060 §11.3.1.1 ec. 11-3 | Cortante unidireccional Vc | `codes/peru/e060_concrete.py` | `test_shear_oneway.py` |
| E.060 §11.12.1.1 | Sección crítica a d de la cara | `foundation/shear_oneway.py` | `test_shear_oneway.py` |
| E.060 §11.12.1.2 | Perímetro crítico a d/2 | `foundation/punching_shear.py` | `test_punching_shear.py` |
| E.060 §11.12.2.1 ec. 11-33/34/35 | Vc de punzonamiento | `codes/peru/e060_concrete.py` | `test_punching_shear.py` |
| E.060 §11.12.6, ec. 11-39/11-40, 13-1 | Transferencia de momento | `foundation/punching_moment_transfer.py` | `test_punching_moment_transfer.py` |
| E.060 §12.2, Tabla 12.1, ec. 12-1 | Longitud de desarrollo | `codes/peru/e060_development.py` | `test_development_length.py` |
| E.060 §12.5 | Ganchos | `codes/peru/e060_development.py` | `test_development_length.py` |
| E.060 §15.2 | Cargas de servicio, sin tracciones | `soil/contact_pressure.py` | `test_contact_pressure.py` |
| E.060 §15.4 ec. 15-1 | Reparto dirección corta | `reinforcement/short_direction.py` | `test_short_direction.py` |
| E.060 §15.7 | Peralte mínimo | `codes/peru/e060_concrete.py` | `test_e060_concrete.py` |
| E.060 §7.6.6, §9.7.3 | Separaciones | `reinforcement/rebar_selector.py` | `test_rebar_selector.py` |
| E.060 §7.7(a) | Recubrimiento 70 mm | `codes/peru/e060_concrete.py` | `test_e060_concrete.py` |
| E.050 art. 17.1 | Cargas de servicio para FS | `domain/loads.py` | `test_domain_models.py` |
| E.050 art. 23.1 | D/B ≤ 5 | `units/validators.py` | `test_units.py` |
| E.050 art. 28 | Excentricidad, área efectiva | `soil/eccentricity.py` | `test_eccentricity.py`, `test_axis_symmetry.py` |
| E.050 art. 39.13.6 | FS de muros (**no de zapatas**) | `soil/stability.py` | `test_stability.py` |
| **E.050 art. 23.3** | **L ≤ 10B en combinada** | — | **sin test** |
| **E.050 art. 26.2** | **Df ≥ 0,80 m** | `soil/foundation_depth.py` | `test_normative_corrections_phase1a.py` · `test_foundation_depth_shared.py` |
| **E.030 art. 29 / 62.2** | **Reducción 0,8** | `soil/contact_pressure.py` (opción) | `test_contact_pressure.py` — *falta la referencia a E.030* |
| **E.030 art. 64.2** | **FS de volteo ≥ 1,2** | — | **sin test** |
| **E.030 art. 65.1** | **Elementos de conexión, N ≥ 0,10·ΣPu** | — | **sin test** |

---

## Discrepancias detectadas entre implementación y norma

| # | Discrepancia | Gravedad | Acción |
|---|---|---|---|
| D1 | Df ≥ 0,80 m (E.050 26.2) no se verificaba | Media | ✅ **Corregido en Fase 1A** — `engine/soil/foundation_depth.py` |
| D2 | FS de volteo sin referencia, existiendo E.030 64.2 | Media | ✅ **Corregido en Fase 1A** — se aplica 1,20 **solo a combinaciones sísmicas**; sin sismo sigue NO VERIFICADO |
| D3 | Reducción 0,8 atribuida solo a E.060 §15.2 | Baja | Pendiente — E.030 art. 29 y 62.2 son fuente concordante |
| D4 | **§11.12.6 documentado como no implementado.** Corregido en esta revisión | Baja — documental | ✅ Hecho |
| D5 | **`max_LB_ratio = 2,0` puede confundirse con norma.** Es heurística; E.050 23.3 fija L ≤ 10B | Baja | Documentar la distinción en la interfaz |
| D6 | Los rótulos Mx/My estaban INVERTIDOS respecto de E.050 art. 28.1 | **Alta** | ✅ **Corregido** — el motor adopta `ex = Mx/P`. Migración de etiqueta pura, verificada contra el congelamiento: cero cambios físicos. Informe en `docs/convenciones_ejes.md` |

## Discrepancias entre los apuntes de Aragón y la norma

| # | Discrepancia | Autoridad |
|---|---|---|
| A1 | El ejemplo 3.4.1 omite §11.12.6. Incluirlo baja el margen de 2,5% a 0,15% (ratio 0,9985) | **La norma.** El motor aplica §11.12.6 |
| A2 | El ejemplo 3.4.1 usa h = 60 cm en lugar de d = 50 cm al calcular Vc (156,7 vs. 130,6 tonf) | **La norma.** Vc se calcula con d |
| A3 | Los apuntes no mencionan E.030 art. 65.1 en el diseño de la viga de conexión | **La norma.** El requisito de N ≥ 0,10·ΣPu es exigible cuando se dispara |

---

## Información que sigue faltando

| Prioridad | Documento | Bloquea |
|---|---|---|
| 1 | **Criterio de verificación de la premisa de presión uniforme** en la zapata excéntrica. §21.12.3.2 fija una dimensión mínima, no una comprobación de rigidez del conjunto | Que la zapata conectada pueda dar PASS en lugar de NO VERIFICADO en ese aspecto |

Resuelto el 20/08/2026: las ecuaciones de E.050 art. 28.1 (**ex = Mx/Q, ey = My/Q**), que
no se extraían del PDF por ser objeto gráfico, fueron aportadas por el usuario. La
consecuencia está registrada como discrepancia D6.

Ninguno de los dos bloquea la implementación: el primero es una confirmación documental de
una convención ya coherente, y el segundo se gestiona declarando la hipótesis.
