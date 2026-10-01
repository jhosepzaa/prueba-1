# Análisis — Contrato de cargas

Tipo de tarea: **análisis** (CLAUDE.md §17). No se modificó código, tests ni baselines.
Estado: **entregado, pendiente de decisiones** (§7 de este documento).

---

## 1. Problema

El contrato actual recibe **combinaciones ya formadas por el usuario**. El motor no sabe
qué parte de cada combinación es carga muerta, viva, de sismo o de viento, ni con qué
factores se formó. Eso bloquea o degrada varias cosas a la vez:

| # | Qué no se puede hacer bien hoy | Dónde | Efecto actual |
|---|---|---|---|
| 1 | Factorizar cargas **generadas por el motor** (peso de la viga) | conectada, TBD-C13 | Entra sin factor en las factorizadas |
| 2 | Factorizar el relleno sobre la viga, cuando se implemente | conectada, 9a | Bloqueado de antemano por la misma causa |
| 3 | Reducir al 80 % **solo la componente sísmica** para esfuerzos admisibles (E.030 art. 29 y 62.2; E.060 §15.2) | aislada | Limitación `seismic_reduction_80pct`: no se aplica, lado conservador |
| 4 | Estabilidad de la combinada (deslizamiento y volcamiento) con la regla de E.030 art. 64.2 | combinada | NO VERIFICADO con H > 0 (D4) |
| 5 | Fuerza axial mínima de la viga (E.030 art. 65.1, 10 % de las cargas verticales amplificadas) | conectada | Usa cargas corregidas que incluyen el peso de la viga sin factor (TBD-C13 también la alcanza) |
| 6 | Garantizar que las combinaciones de dos columnas son coherentes entre sí | combinada, conectada | Se exige que tengan los mismos **nombres**; que sus números sean coherentes no se puede comprobar |

La reducción del 80 % y la estabilidad dependen de separar la componente sísmica. El peso
de la viga y el relleno dependen de conocer el factor de la carga muerta **de cada
combinación**. Por eso conviene decidir primero el contrato común, antes que los pendientes
por separado.

## 2. Modelo actual (evidencia)

### Dominio (`engine/domain/loads.py`)

```text
LoadCombination: name, type ∈ {SERVICIO, FACTORIZADA},
                 P_kN, Mx_kNm, My_kNm, Hx_kN, Hy_kN, description,
                 includes_seismic_loads, includes_wind_loads
LoadCaseSet:     service[], factored[]   (≥ 1 de cada una; nombres únicos)
```

El docstring del módulo ya declara: «El motor NO deriva combinaciones factorizadas a partir
de CM/CV/CS (E.060 §9.2 se documenta como referencia, pero el MVP no la ejecuta)».

### Qué lee cada consumidor

| Consumidor | Servicio | Factorizadas | Banderas sismo / viento | H |
|---|---|---|---|---|
| Aislada, presión de contacto (`depth_solver`) | P + peso propio de la zapata, excentricidad | — | +30 % qadm (opcional, E.060 §15.2); reducción 80 % no aplicable | — |
| Aislada, flexión / cortante / punzonamiento | — | P, Mx, My (sin peso propio de la zapata) | — | — |
| Aislada, estabilidad (`soil/stability.py`) | P + peso propio, Mx/My, H | — | FS de volcamiento 1,2 solo si la combinación es sísmica (E.030 art. 64.2) | sí |
| Combinada (`combined_solver`) | diagramas por nombre de combinación | diagramas por nombre | — | H → NO VERIFICADO (D4) |
| Conectada (`connected_statics`) | reparto por pares de nombres | reparto por pares de nombres | — | — |
| Conectada, peso de viga EXPLICITO | mismo valor | **mismo valor, sin factor** (TBD-C13) | — | — |
| Conectada, E.030 art. 65.1 | — | máx. P factorizada corregida de lindero | — | — |
| Informes | tabla de combinaciones con H y bandera sísmica | ídem | sí | sí |

### API y UI

- `LoadCombinationInput` refleja el dominio uno a uno, con conversión de unidades en
  `api/mapping.build_loads`.
- Tres puntos de entrada lo usan (aislada, combinada, conectada), cada columna con su
  propia lista `combinations`.
- La UI tiene los mismos campos en `InputPanel`, `CombinedInputPanel` y
  `ConnectedInputPanel`.

### Dependencia de tests y baselines

- `LoadCombination(` aparece 119 veces en 39 archivos de tests.
- Todos los golden cases, los 30 casos de `baseline.json`, los 19 de
  `baseline_connected.json` y los benchmarks de la Fase 6 se construyen con combinaciones
  directas.
- **Un contrato que elimine la entrada directa invalida toda la base de regresión.**

## 3. Ecuaciones y texto normativo disponible

| Fuente | Contenido | Estado en el proyecto |
|---|---|---|
| E.060 §15.2 | Área de la zapata con cargas de servicio; +30 % qadm y reducción 80 % opcionales | Verificado contra fuente primaria (`referencias_e060_e050.md`) |
| E.050 art. 17.1 | FS con las cargas de servicio de las columnas del nivel más bajo | Verificado |
| E.030 art. 29 y 62.2 | Fuerzas sísmicas × 0,8 en verificaciones por esfuerzos admisibles | Verificado, transcrito |
| E.030 art. 64.2 | FS de volteo ≥ 1,2 con las fuerzas **sin** la reducción del art. 29 | Verificado, transcrito |
| E.030 art. 65.1 | Elementos de conexión: 10 % de las cargas verticales amplificadas | Verificado, transcrito |
| **E.060 §9.2, ec. 9-1** | U = 1,4 CM + 1,7 CV | Verificado (resumen del registro) |
| **E.060 §9.2, ec. 9-2 a 9-5** | 1,25(CM + CV ± CVi) · 0,9 CM ± 1,25 CVi · 1,25(CM + CV) ± CS · 0,9 CM ± CS | **Solo en `docs/manual_usuario.html`**: documentación propia, **no contrastada** con el texto primario en el registro |
| E.060 §9.2, resto (empuje de tierras, otras acciones) | — | **No transcrito** |
| **E.020 (Cargas)**: definición de carga muerta y viva, peso propio | — | **No está en el proyecto** |

Consecuencia directa, con la reserva de que las ecuaciones 9-2 a 9-5 están pendientes de
contraste: **el factor de la carga muerta cambia de una combinación a otra** (1,4; 1,25;
0,9). Por tanto:

- no existe un «factor de peso propio» único que el motor pueda aplicar;
- dejar el peso de la viga sin factor **no es siempre conservador**. En una combinación
  0,9 CM ± CS lo **sobrestima**, y eso es desfavorable para despegue, volcamiento y
  tracciones.

Este segundo punto amplía la consecuencia hoy escrita en
`docs/tbd_c13_factorizacion_peso_viga.md`; se añadió allí como nota.

## 4. Invariantes que cualquier contrato nuevo debe cumplir

| # | Invariante |
|---|---|
| I1 | **Linealidad:** cada combinación derivada vale P = Σₖ fₖ·Pₖ, y lo mismo para Mx, My, Hx, Hy, con fₖ el factor del caso k en esa combinación. |
| I2 | **Equivalencia con la entrada directa:** si el usuario introduce a mano las combinaciones que el contrato nuevo derivaría, todos los resultados deben coincidir bit a bit. Protege los baselines existentes. |
| I3 | **Servicio y factorizado separados:** la naturaleza de cada combinación es explícita; ninguna carga recibe un factor por estar en una lista. |
| I4 | **Cargas internas:** una carga generada por el motor recibe el factor del caso al que pertenece **en esa combinación**, o ninguno. Nunca un factor inferido. |
| I5 | **Coherencia entre columnas:** en combinada y conectada, la combinación j de todas las columnas usa los mismos factores. Hoy solo se comprueba el nombre. |
| I6 | **Componente sísmica aislable:** permite la reducción 0,8 de E.030 art. 29 donde la norma la admite y exige no aplicarla donde art. 64.2 lo prohíbe. |
| I7 | **Sin factores inventados:** el motor no incorpora factores de E.060 §9.2 ni categorías de E.020 hasta tener el texto primario transcrito. Mientras tanto, los factores los declara el usuario. |
| I8 | **Trazabilidad:** la traza muestra, por combinación, los casos, los factores y el resultado, y a qué caso se asignó cada carga interna. |

## 5. Alternativas

### A. Mantener combinaciones directas y declarar, en cada combinación, el factor de las cargas internas

Campo nuevo por combinación, por ejemplo `internal_dead_load_factor`. Obligatorio cuando el
motor genere una carga interna que deba factorizarse, sin valor por defecto.

- **Resuelve:** 1, 2 y 5 (TBD-C13 y relleno).
- **No resuelve:** 3, 4 y 6.
- **Riesgo:** el factor declarado puede no ser coherente con la combinación que el usuario
  formó. El motor no puede comprobarlo (incumple I5).
- **Coste:** bajo; cambio aditivo; baselines intactos.

### B. Casos por tipo y combinaciones definidas por factores, derivadas por el motor

- Cada columna recibe **casos de carga por tipo** (por ejemplo CM, CV, CS, CVi; la
  taxonomía exacta está pendiente de E.060 §9.2 y E.020).
- Cada combinación se declara como **conjunto de factores** por tipo, con su naturaleza
  (servicio o factorizada).
- El motor **deriva** los `LoadCombination` de hoy y conserva la composición.

Detalles:

- **Resuelve:** 1 a 6.
- **Coste:** alto si sustituye la entrada actual. Contradice I2 en la práctica, porque toda
  la regresión está escrita con combinaciones directas.

### C. Híbrido: B como capa opcional por encima del contrato actual (recomendada)

Dos modos de entrada que producen **los mismos `LoadCombination`**:

| Modo | Entrada | Composición conocida |
|---|---|---|
| `COMBINACIONES_DIRECTAS` (actual) | P, M, H por combinación | no |
| `CASOS_Y_COMBINACIONES` (nuevo) | casos por tipo + factores por combinación | sí |

Arquitectura:

```text
api (casos + definiciones de combinación)
  → engine/domain/load_cases.py   deriva LoadCombination (I1, I5) y adjunta la composición
  → solvers existentes            SIN CAMBIOS: consumen LoadCombination como hoy (I2)
  → cargas internas               usan la composición SOLO si existe (I4)
```

- `LoadCombination` gana un campo **opcional y aditivo**, `composition` (factor por tipo
  de caso), que vale `None` en modo directo.
- Con `composition = None` todo se comporta exactamente como hoy: baselines intactos.
- **Resuelve:** 1 a 6 en modo casos. En modo directo, cada limitación sigue declarada como
  hoy.
- **Coste:** medio y por fases (§8). La primera fase no cambia ningún resultado existente.

### D. Plantillas normativas de E.060 §9.2 generadas automáticamente

El motor genera las combinaciones con los factores de la norma, incluidos los signos del
sismo.

- **No es alternativa a C:** es una capa opcional encima de C, porque produciría las
  definiciones de combinación.
- **Bloqueada** hasta transcribir y verificar E.060 §9.2 completo contra el texto primario
  (I7).

### Comparación

| Criterio | A | B | C | D |
|---|---|---|---|---|
| Cierra TBD-C13 | sí, sin garantía de coherencia | sí | sí (modo casos) | sí, sobre C |
| Reducción 0,8 sísmica | no | sí | sí (modo casos) | sí |
| Estabilidad de la combinada con art. 64.2 | no | sí | sí | sí |
| Coherencia entre columnas (I5) | no | sí | sí (modo casos) | sí |
| Baselines existentes | intactos | todos afectados | intactos | intactos |
| Requiere texto normativo nuevo | no | taxonomía | taxonomía mínima | E.060 §9.2 completo |
| Coste | bajo | alto | medio, por fases | medio, después de C |

## 6. Recomendación

**Alternativa C**, con D como extensión posterior.

La razón no es que sea la más cómoda. C es la única que cumple a la vez:
- I2: no invalida la base de regresión;
- I4 e I5: la composición es conocida y coherente por construcción;
- I7: no incorpora factores normativos sin texto primario, porque los factores los declara
  el usuario.

A cierra TBD-C13 pero sin poder verificar la coherencia del factor declarado. Con
combinaciones 0,9 CM eso es un riesgo real, no teórico.

Qué **no** recomiendo:
- eliminar el modo directo;
- inferir la composición desde `includes_seismic_loads`;
- aplicar en modo directo cualquier factor a las cargas internas.

## 7. Decisiones que requieren aprobación

| Id | Decisión | Opciones | Afecta |
|---|---|---|---|
| **DL-1** | Arquitectura del contrato | A / B / **C (recomendada)** / D sobre C | todo lo siguiente |
| **DL-2** | Taxonomía de casos de carga | Mínima con lo verificado (CM, CV, CS, CVi) o completa. **Requiere transcribir E.060 §9.2 y E.020** en `docs/normativa` | dominio, API, UI |
| **DL-3** | Quién define los factores | Solo el usuario (compatible con I7 hoy) / plantillas normativas (D, requiere texto) | API, UI |
| **DL-4** | A qué caso pertenecen las cargas internas (peso de viga, relleno, peso propio de la zapata) | Por ejemplo, todas a CM. **Requiere la definición de carga muerta de E.020** | TBD-C13, relleno, 65.1 |
| **DL-5** | Peso de viga EXPLICITO en **modo directo** | Mantener el TBD-C13 documentado / NO VERIFICADO en combinaciones factorizadas / exigir el modo casos | estados de Z8 y Z15 si no se mantiene |
| **DL-6** | Signos del sismo y de las direcciones | Solo lo que el usuario declare (recomendado) / generación ± automática (D) | combinaciones derivadas |
| **DL-7** | Reducción 0,8 y +30 % qadm | Mantener opcionales y desactivadas por defecto; con composición conocida, la 0,8 pasaría a ser aplicable | aislada; baselines solo si se activan en casos congelados |

**Actualización 2026-09-13.** El usuario entregó E.020, E.030 (2026) y E.050
(`docs/normativa/fuentes/`). E.020 ya está disponible para DL-2 y DL-4: definiciones en el
art. 2, carga muerta en el cap. 2 y combinaciones para esfuerzos admisibles en el art. 19.
**E.060 sigue sin entregarse**: el archivo «e060 actualizada» contiene E.030 (2025).

**Actualización 2026-09-14.** E.060 entregada (propuesta 2019). Su §9.2 distingue el **nivel**
de la acción: viento a nivel de servicio (9-2, 9-3) o de resistencia (9-2a, 9-3b); sismo a
nivel de resistencia (9-4, 9-5) o de servicio (9-4a). DL-2 debe incluir ese nivel. Ver
`docs/normativa/contraste_e060_motor.md`.

Texto normativo necesario para cerrar DL-2 y DL-4 (estado original):
- **E.060 §9.2 completo**, ecuaciones 9-1 a 9-5 y cualquier disposición sobre empuje de
  tierras u otras acciones;
- **E.020**, definiciones de carga muerta, carga viva y peso propio.

## 8. Plan por fases si se aprueba C (orientativo, sin implementar)

| Fase | Contenido | Resultados existentes | Baselines |
|---|---|---|---|
| CC-0 | Transcribir E.060 §9.2 y E.020 en `docs/normativa`, verificado contra el texto primario | ninguno | ninguno |
| CC-1 | `engine/domain/load_cases.py`: casos, definiciones de combinación y derivación (I1, I5); campo opcional `composition`; tests de linealidad y de equivalencia bit a bit con la entrada directa (I2) | ninguno | ninguno; se **añaden** casos congelados de equivalencia, con aprobación |
| CC-2 | API y UI: segundo modo de entrada; informe con casos, factores y composición (I8) | ninguno | ninguno |
| CC-3 | Cargas internas con composición: peso de viga factorizado (cierra TBD-C13 en modo casos) y regla DL-5 para modo directo | casos EXPLICITO en modo casos | casos nuevos; Z8 y Z15 solo si DL-5 cambia el modo directo |
| CC-4 | Reducción 0,8 de la componente sísmica y art. 64.2 con composición | aislada en modo casos | casos nuevos |
| CC-5 | Estabilidad de la combinada sobre este contrato | combinada | por decidir en esa fase |
| CC-6 (D) | Plantillas de E.060 §9.2 | ninguno | ninguno |

## 9. Riesgos

- **Duplicación de caminos:** dos modos de entrada podrían divergir. Se mitiga con I2 como
  test obligatorio: derivar y entrar a mano deben dar lo mismo.
- **Sismo en condición última frente a servicio:** el manual del proyecto recomienda dividir
  el sismo entre 1,25 para servicio. Es una interpretación propia, no una cita. En modo casos
  la naturaleza del caso sísmico (nivel de resistencia o de servicio) debe declararse.
  Pertenece a DL-2.
- **Coherencia de nombres:** en modo casos las combinaciones de todas las columnas salen de
  la misma definición, lo que elimina el emparejamiento por nombre como única garantía.

## 10. Actualización tras la fase CC-0 (2026-09-14)

Transcripción verificada en `docs/normativa/transcripcion_cargas.md`. Efecto sobre el
análisis:

| Decisión | Antes | Ahora |
|---|---|---|
| DL-2 (taxonomía) | Pendiente de texto | **Texto disponible.** E.060 §9.2 define CM, CV, CVi, CS, CE, CL y CT, y **el nivel (servicio o resistencia) de CS y CVi cambia las ecuaciones** (9-2/9-2a, 9-3/9-3b, 9-4/9-4a, 9-5/9-4b). La taxonomía deja de ser una elección libre: queda por decidir cuánta de ella se implementa. |
| DL-4 (a qué caso pertenecen las cargas internas) | Pendiente de E.020 | **Peso propio de zapatas y viga = CM** (E.020 art. 2). **El relleno queda abierto**, porque las fuentes dan dos lecturas: CM para estabilidad (E.020 20.2) o CE con factor 1,7 (E.060 9.2.5). Requiere decisión. |
| Nuevo: **DL-8, estabilidad** | — | E.020 20.1: la estabilidad la dan **solo las cargas muertas**. El motor usa la P completa de servicio, que incluye CV. Solo se corrige conociendo la composición. |
| Nuevo: **DL-9, FS normativo** | — | E.020 art. 21 (volteo 1,5) y art. 22 (deslizamiento 1,25) frente a E.030 art. 64.2 (volteo 1,2 con sismo). Hay que decidir cómo se relacionan y si se adoptan como criterio. |
| Nuevo: **DL-10, sismo a nivel de servicio** | — | E.020 art. 19: 0,70 E; E.030 art. 29 y E.060 15.2.5: 0,8. |

**La recomendación C se refuerza.** Tres de los hallazgos nuevos (DL-8, H1 y el relleno)
solo tienen solución si el motor conoce la composición de las cargas. Con combinaciones
directas no hay forma de separar CM de CV para la estabilidad.

## 11. Decisión e implementación (Fase 10B, 2026-09-14)

**Se adoptó la alternativa C.** Implementación, tests y efecto en el congelamiento:
`docs/fase10_alineacion_e060_y_contrato_cargas.md`.

| Decisión | Resuelta como |
|---|---|
| DL-2 taxonomía | Los siete tipos de E.060 §9.2, con nivel para CVi y CS |
| DL-4 cargas internas | Peso propio de la viga = CM (× factor de CM). **Relleno: sin regla fija**; el usuario lo declara como CM o CE (D10-6) |
| DL-8 estabilidad | Solo carga muerta con composición; en modo directo un cumplimiento queda NO VERIFICADO |
| DL-9 FS | 1,5 / 1,25 (E.020) y 1,2 con sismo (E.030 art. 64.2) por defecto |
| DL-10 sismo | 0,8 (E.030 art. 29, E.060 §15.2.5) sobre CS a nivel de resistencia, solo para el suelo |
| Generación de combinaciones | No: los factores los declara el usuario (alternativa D descartada) |

Pendiente: las cargas corregidas de la conectada no conservan la composición (limitación
`connected_footing_stability_composition`).
