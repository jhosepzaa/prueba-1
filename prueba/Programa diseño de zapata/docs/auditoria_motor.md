# Auditoría final del motor — estado por funcionalidad

Fecha de la auditoría: cierre de Fase 3 / inicio de Fase 4 de armado.
Suite: **183 tests, 183 pasan**. Casos golden: **8 de 8**.

Leyenda de "Validada":
- **Golden** — verificada contra cálculo manual documentado paso a paso
- **Unitario** — verificada con tests de propiedades/límites
- **Simetría** — cubierta además por el test de rotación de ejes
- **—** — no implementada, nada que validar

---

## A. Motor de cálculo

| Funcionalidad | Implementada | Validada | Pendiente | Impacto sobre el resultado |
|---|---|---|---|---|
| Sistema de unidades SI | Sí | Unitario | Entrada dual kgf/cm² | Ninguno: conversión en un único punto por ecuación |
| Validación de entradas | Sí | Unitario | — | f'c<17 MPa y fy>550 MPa se rechazan (§9.4, §9.5) |
| Combinaciones SERVICIO / FACTORIZADA | Sí | Unitario | — | Separación obligatoria; mezclarlas es imposible por construcción |
| Combinación gobernante por verificación | Sí | Unitario + E2E | — | Verificado con datos reales: S2 gobierna 190 descartes, S1 solo 36 |
| Peso propio + relleno | Sí | Golden | — | Recalculado en cada iteración de h |
| Presión de contacto (FullContact/KernCheck) | Sí | Golden + Simetría | Modelo EffectiveArea | Fuera del núcleo se descarta explícitamente, no se aproxima |
| Excentricidad uniaxial y biaxial | Sí | Golden + Simetría | — | Convención auditada en los 11 puntos del pipeline |
| Conversión presión BRUTA/NETA | Sí | Unitario | — | Módulo independiente; comparación siempre en la misma base |
| Generación de geometría B-L | Sí | Unitario | — | Sin ranking: separación dimensionamiento/optimización |
| Solver iterativo de h | Sí | Unitario | — | Poda temprana justificada; conserva historial completo |
| Flexión (§15.4, §10.2, φ=0.90) | Sí | Golden | — | Falla explícita si la sección es insuficiente; nunca NaN silencioso |
| As mínimo (§9.7 vía §10.6) | Sí | Golden + Unitario | — | Zapatas excluidas del criterio Mcr por §10.5.1 |
| Cortante unidireccional (ec. 11-3, φ=0.85) | Sí | Golden + Simetría | — | Sección crítica a d de la cara |
| Punzonamiento (ec. 11-33/34/35, φ=0.85) | Sí | Golden + Simetría | **§11.12.6** | Ver limitación L1 |
| Validación geométrica sección crítica | Sí | Unitario | — | d/2 fuera de la zapata → FAIL con razón propia |
| Distribución dirección corta (γs, ec. 15-1) | Sí | Unitario | — | Franjas exteriores elevadas al mínimo §9.7 (interacción no resuelta por la norma) |
| Peralte mínimo (§15.7) | Sí | Unitario | **Interpretación** | Ver limitación L6 |
| Recubrimiento (§7.7) | Sí | Unitario | — | 70 mm contra el suelo |
| Separaciones mín/máx (§7.6.6, §9.7.3) | Sí | Unitario | — | max(db,25mm) y min(3h,400mm) |
| Selección de acero + alternativas | Sí | Unitario | Clasificación de combinaciones | Ver Fase 4 de armado |
| Estados PASS / FAIL / WARNING | Sí | Unitario | — | WARNING no descarta; solo FAIL descarta |
| CalculationTrace | Sí | Unitario | — | 11 campos por entrada; alimenta descartes y futuro reporte |
| Explicación de descartes | Sí | Unitario | — | Tres estados rotulados correctamente |
| Registro formal de limitaciones | Sí | Unitario | — | Emite WARNING automático; impide falsos PASS |
| Scoring configurable | Sí | Unitario | Costo monetario | Normalización min-max; desglose auditable |
| Frente de Pareto | Sí | Unitario | — | 475 → 6 no dominadas en el caso E2E |
| Ranking Top-N de geometrías | Sí | Unitario | — | Determinista |
| **Soluciones de armado combinadas (X × Y)** | Sí | Unitario | — | Producto cartesiano de opciones por dirección; masa de acero real por solución |
| **Ranking de armados** | Sí | Unitario | — | Pesos independientes de los de geometría: elegir zapata y elegir armado son decisiones distintas |
| **Masa de acero por solución** | Sí | Unitario | Ganchos y traslapes | **Cota inferior**: excluye ganchos y traslapes por L4. Declarado en `steel_mass_excludes_hooks` |

## B. Limitaciones formalmente registradas

Todas viven en `engine/results/limitations.py` y se emiten automáticamente al
`CalculationTrace` cuando son relevantes.

| # | Limitación | Tipo | ¿Puede causar falso PASS? | Tratamiento en el motor | Impacto |
|---|---|---|---|---|---|
| **L1** | §11.12.6 transferencia de momento en punzonamiento | NO IMPLEMENTADO | **Sí** | Con Mu≠0 el punzonamiento es **WARNING, nunca PASS** | Punzonamiento verificado solo en su resultante; el esfuerzo real en el lado más cargado es mayor |
| **L2** | Reducción sísmica 80% (§15.2) | NO IMPLEMENTADO | No | Nota informativa; se procede sin la reducción | Resultado **más conservador** que el mínimo normativo |
| **L3** | Fuerzas horizontales: deslizamiento y volcamiento | NO IMPLEMENTADO | **Sí** | Con Hx/Hy≠0 emite **WARNING** nombrando las combinaciones | Una zapata puede cumplir todo lo demás y ser inestable. Verificación independiente requerida |
| **L4** | Longitud de desarrollo y anclaje (§15.6→Cap.12) | NO IMPLEMENTADO | **Sí** | **WARNING permanente** en toda alternativa | En voladizos cortos la longitud disponible puede ser < ld. El armado podría no ser ejecutable como se indica |
| **L5** | Columnas circulares | FUERA DE ALCANCE | No | Rechazo en validación de entrada | Imposible calcular una columna circular por error |
| **L6** | §15.7 peralte mínimo | INTERPRETACIÓN ADOPTADA | No | d ≥ 300 mm, parametrizado y rotulado | Es la lectura **más exigente**: puede rechazar zapatas que otra interpretación aceptaría, nunca al revés |

## C. Consecuencia deliberada sobre el estado global

**Ninguna alternativa puede alcanzar hoy el estado PASS.** El mejor estado
posible es **WARNING**, porque L4 (anclaje) es relevante en toda zapata y puede
gobernar.

Esto es intencional y responde al requisito explícito: el motor no puede declarar
"cumple normativamente" mientras existan verificaciones pendientes que podrían
gobernar. PASS vuelve a ser alcanzable en cuanto se implementen L3 y L4.

## D. Defectos encontrados y corregidos en esta auditoría

| Defecto | Gravedad | Corrección |
|---|---|---|
| Fuerzas horizontales producían **PASS silencioso**: Hx/Hy se aceptaban como entrada y no se usaban ni se mencionaban en ninguna parte | **Alta** — falso PASS real | Registro de limitaciones que emite WARNING nombrando las combinaciones afectadas |
| Alternativas con WARNING se rotulaban **"DESCARTADA"** en el explicador | Media — engañoso en sentido inverso | Tres estados: ACEPTADA / ACEPTADA CON OBSERVACIONES / DESCARTADA |

## E. Verificación de no-regresión

- 183 tests, 183 pasan
- 8 casos golden, 21 aserciones, todas pasan
- Caso end-to-end: 741 geometrías en 0.48 s, 475 válidas, Pareto de 6
- Las 3 limitaciones relevantes (L1, L3, L4) aparecen en el trace del ganador
- 0 checks en FAIL en el ganador, y aun así el estado global es WARNING
