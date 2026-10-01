# Validación de extremo a extremo — Aragón CR2 §3.5, zapata combinada con columna en lindero

Fecha: 2026-09-22. Etapa A (primera validación de extremo a extremo del programa).

**Estado: DEFECTO REAL ENCONTRADO en el motor congelado y CORREGIDO** el 2026-09-22 con
aprobación expresa del proyectista. Se aplicaron dos cambios —el signo del salto de momento
en `beam_diagram._moment`, con una guarda que comprueba el cierre del diagrama, y la
envolvente de combinaciones en el diseño longitudinal— y se regeneró **un solo caso
congelado**, `K2` (`CLAUDE.md` §11: regeneración dirigida, nunca en bloque).

Las cuatro decisiones de ingeniería del apartado 8 **siguen abiertas**: el programa aplica
el criterio que allí se indica y lo declara en la memoria.

---

## 1. El caso

Enunciado del proyectista, que resultó ser el ejemplo resuelto de Aragón CR2 §3.5
(«Figura 74», `docs/normativa/aragon_cr2_extracto.txt`). Aragón es **benchmark, no
autoridad** (`CLAUDE.md` §1): las diferencias se documentan y el motor no se fuerza.

| Dato | Valor | Origen |
|---|---|---|
| Columnas | 50 × 50 cm, a 5,00 m entre ejes; C1 al ras del lindero | enunciado |
| C1 | CM: P 80 t, M +6 · CV: P 30 t, M +2,5 · CS: P −10 t, M +50 | enunciado; signos confirmados por las ecuaciones del libro |
| C2 | CM: P 160 t, M −2 · CV: P 60 t, M −0,5 · CS: P +10 t, M +70 | ídem |
| σadm | 1,5 kgf/cm² **bruta**, con **+30 %** en estados con sismo (E.060 §15.2.4) | proyectista |
| Df | 1,50 m | enunciado |
| f'c / fy | 210 / 4200 kgf/cm² | proyectista |
| γ relleno / concreto | 1,8 / 2,4 tonf/m³ (el segundo, E.020: grava 2300 + 100) | proyectista / E.020 |
| Sismo | a **nivel de servicio**; §15.2.5 (80 %) **no** se aplica: el artículo la justifica porque E.030 da el sismo a nivel de resistencia | enunciado / E.060 |
| Combinaciones | E.060 §9.2.1 (9-1) y §9.2.3 para sismo en servicio (9-4a), (9-4b), con ± explícito | E.060, confirmado en el flujo de contenido del PDF |
| Supuestos | sin Hs en la base, My = 0, columnas centradas en el ancho | declarados, no objetados |

Todos los datos se entregaron en las unidades del enunciado; la conversión la hizo la
capa única de unidades de la API.

---

## 2. Hallazgo principal — el diagrama longitudinal de la combinada no cierra

### 2.1 Síntoma

Para la geometría del libro (7,20 × 3,80 × 0,80 m) el motor daba el momento de la cara
**inferior** de 355,72 t·m en el eje de C2 y el de la cara **superior** de solo 56,08 t·m.
Una combinada con columnas y reacción del suelo trabaja con la tracción grande ARRIBA,
entre columnas.

### 2.2 Evidencia: el diagrama viola el equilibrio de momentos

Los puntos críticos del propio motor terminan en **M = 285,0 t·m en el extremo libre**
(x = 7,20). Debe valer cero. La cifra es exactamente `−2·(M₁ + M₂)` de la combinación
gobernante U3.

El control existente, `equilibrium_residual_kN`, es de **fuerza**, y un par mal signado
no produce residuo de fuerza. Por eso pasó.

### 2.3 Causa: un signo

`engine/analysis/beam_diagram.py`, función `_moment`:

```python
m -= load.M_kNm      # congelado
m += load.M_kNm      # corrección
```

El campo de presiones del **mismo módulo** usa `x_R = (Σ Pᵢxᵢ + Σ Mᵢ)/Σ Pᵢ`: M > 0 corre la
carga hacia +x (E.050 art. 28.1). Eso equivale a Pᵢ en `xᵢ + Mᵢ/Pᵢ`, cuya contribución al
momento flector —positivo, tracción abajo— es `−Pᵢ·(x − xᵢ) + Mᵢ`.

**Prueba por cierre.** Con `+=`,
`M(L) = P·(L − x_R) − Σ Pᵢ(L − xᵢ) + Σ Mᵢ = 0` idénticamente. Con `−=`, `M(L) = −2·Σ Mᵢ`.

### 2.4 Tres confirmaciones independientes

| Fuente | Resultado |
|---|---|
| Reconstrucción a mano, sin el motor | con el signo corregido cierra en 0,000 y da exactamente −159,83 y +161,35 t·m; con el congelado reproduce 56,08 / 355,72 y no cierra |
| **El libro** | sus polinomios de las tres combinaciones coinciden con el motor corregido **dentro del 1 %** en todos los puntos; el congelado se desvía 25–146 t·m e invierte el signo en U2 |
| **La constante del libro** | en `1,4CM + 1,7CV` el libro escribe `+14,77 = 2,12 + 12,65`: **suma** el par de columna, como la corrección |

### 2.5 Por qué no lo detectaron los tests

| Test | Qué comprobaba | Por qué no bastó |
|---|---|---|
| `test_las_fuerzas_y_los_momentos_cierran` | M(L) = 0 | sus cuatro casos tienen **momento de columna nulo** |
| `test_el_momento_aplicado_salta_el_diagrama_de_momentos` | el salto de M en el par | **fija el signo equivocado**: exige −500 para M = +500 |
| freeze `K2` | 29 números del diagrama | el baseline **congeló M(L) = −163,8 kN·m**, la violación misma |

Un freeze protege contra el cambio, no contra el error de origen. Hacía falta esta
validación contra una fuente independiente.

### 2.6 Alcance

- **Solo la zapata combinada.** La conectada tiene su propia estática, y tres tests
  prohíben expresamente que use `build_beam_diagram`.
- **Solo con momentos de columna.** Sin pares, el término no existe.
- **Afecta al acero, no a la geometría.** La flexión dimensiona el acero y no descarta: el
  conjunto de alternativas aceptadas es el mismo. El cortante sale del diagrama de V y
  **no** está afectado (un par no produce cortante).
- **Del lado inseguro en la cara superior.** Toda combinada diseñada con este programa con
  momentos de columna tiene el acero superior subestimado.

### 2.7 Impacto en el congelamiento

Solo `K2_columna_en_limite_de_propiedad`, el único caso combinado con pares: **29 claves
numéricas, 0 estados**. Su extremo libre pasa de −163,8 kN·m a 1,1·10⁻¹² kN·m.

---

## 3. Diseño resultante para el proyecto (con el diagrama CORREGIDO en memoria)

Búsqueda **exhaustiva**: 1218 geometrías evaluadas sin truncar. El primer barrido, con un
rango mayor, superaba el tope de 3000 y el propio motor lo advirtió; se acotó el rango. Hay
26 alternativas aceptadas, las 26 CONFORMES.

Recomendada: **L = 7,20 m, B = 4,20 m, h = 0,75 m** (d inf 0,667, d sup 0,692 m).

| Verificación | Resultado |
|---|---|
| Presión de contacto (S2, con sismo) | qmax = 18,76 t/m² ≤ 19,50 (1,5 × 1,3) |
| Cortante longitudinal (concreto solo, C-V) | Vu = 173,9 t ≤ φVc = 187,3 t (0,93) — gobierna h |
| Cortante transversal, punzonamiento C1 (3 lados) y C2 | PASS |
| Peralte mínimo §15.7, `L/B`, `Df/B` | PASS |

| Acero | Congelado (erróneo) | **Corregido** |
|---|---|---|
| Superior, entre columnas | 1/2" @ 0,125 (43 cm² provistos) | **5/8" @ 0,125** (67,7 cm²; requerido 62,7) |
| Inferior | 1" @ 0,125 (172 cm²) | **1/2" @ 0,100** (55,5 cm²; requerido 47,1) |
| Transversal bajo C1 / C2 | 3/4" @ 0,10 / 1" @ 0,10 | igual (no afectado) |

El congelado habría dejado la cara superior con el **69 % del acero requerido**.

**Recubrimiento superior.** Con 40, 50 o 75 mm el armado superior sale igual (5/8" @ 0,125;
As 61,8–65,2 cm²): la elección no cambia el plano.

---

## 4. Diferencias con el libro que NO son defectos

| Diferencia | Explicación |
|---|---|
| El libro adopta **B = 3,80 m**; con esa geometría el motor da FAIL por presión (20,43 > 19,50 t/m²) | El libro toma el peso propio como **solo concreto** (52,53 t) y omite el **relleno** sobre la zapata (≈ 34 t). Con presión **bruta** el relleno pesa sobre el suelo y tiene que entrar. Reconstruido a mano: 19,17 t/m² con la carga del libro, 20,41 t/m² sumando el relleno |
| El motor evalúa `0,9CM ± 1,25CS` (9-4b); el libro no | E.060 §9.2.3 la exige «como mínimo» también para sismo en servicio |
| 0,15 % de diferencia en la carga | el motor no descuenta el fuste de las columnas del relleno: hipótesis declarada («relleno sobre toda la huella»), conservadora |

Lo que **sí coincide**: longitud de centrado 7,203 m (libro 7,20), momento respecto del
centroide 170,50 t·m (libro 170,2), diagramas longitudinales dentro del 1 % y momentos
transversales exactos (58,39 / 116,78 frente a 58,38 / 116,78 t·m).

---

## 5. Hallazgo secundario — un criterio tomado de Aragón

La nota de las franjas transversales dice que su ancho, «ancho de columna + d/2 a cada
lado», es un criterio de modelación **«tomado de los apuntes de Aragón»**. `CLAUDE.md` §1
prohíbe tomar de Aragón «ningún factor, coeficiente ni criterio de cálculo». La traza lo
declara honestamente, pero la regla no admite la excepción. E.060 §15.4 no fija ancho de
franja para combinadas. **Decisión pendiente del proyectista.**

---

## 6. Pendiente de esta validación

Tras aprobar la corrección:
1. aplicar `m += load.M_kNm`, corregir el test que fijaba el signo y añadir el test de
   cierre **con** pares que faltaba;
2. regenerar `K2` de forma dirigida (29 claves, 0 estados);
3. reconstruir a mano el punzonamiento y el cortante, que el libro no trae;
4. recorrer el caso por la UI y generar la memoria de cálculo —generarla ahora imprimiría el
   acero superior erróneo—.
