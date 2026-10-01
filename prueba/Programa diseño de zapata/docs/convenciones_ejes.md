# Convención de ejes y excentricidad biaxial

**Revisión: 20 de agosto de 2026 — migración a la convención de E.050 art. 28.1.**

Convención única del motor, declarada en `engine/soil/eccentricity.py`. Verificada
por dos pruebas ejecutables: `tests/test_axis_convention_vs_e050.py` (coherencia de
la convención a lo largo de toda la cadena) y `tests/test_axis_symmetry.py`
(simetría del pipeline).

---

## Convención vigente

**Fuente normativa: E.050 art. 28.1 — `ex = Mx/Q`, `ey = My/Q`.**

| Símbolo | Significado |
|---|---|
| **B** | dimensión de la zapata a lo largo del eje **X** |
| **L** | dimensión de la zapata a lo largo del eje **Y** |
| **bx** | dimensión de la columna a lo largo de X |
| **by** | dimensión de la columna a lo largo de Y |
| **Mx** | momento que desplaza la resultante a lo largo de **X** — flexiona en la dirección de *B* |
| **My** | momento que desplaza la resultante a lo largo de **Y** — flexiona en la dirección de *L* |

```
ex = Mx / P        (desplazamiento a lo largo de X, se compara contra B)
ey = My / P        (desplazamiento a lo largo de Y, se compara contra L)
```

> **`Mx` no es «el momento alrededor del eje X».** Es el momento que flexiona la
> zapata *en* la dirección X, que mecánicamente es el momento **alrededor del eje Y**.
> El rótulo sigue a la norma, no al eje de giro.

Es también la convención de la bibliografía peruana. Aragón, *«Concreto Armado 2»*
3.4.1, lo hace explícito al titular su sección de diseño:
**«Diseño por flexión Dir. X (Momentos alrededor de Y)»**.

---

## Informe de migración

### Motivo

El motor usaba el rótulo **opuesto** (`Mx` = momento alrededor del eje X, de modo que
`ex = My/P`). El encabezado de `eccentricity.py` justificaba esa elección afirmando que
«E.060 y E.050 usan Mx/My sin fijar una convención universal». **Esa afirmación era
falsa**: E.050 art. 28.1 sí la fija.

Consecuencia práctica: quien tomara un `Mx` calculado con la convención normativa y lo
escribiera en el campo `Mx` del programa lo aplicaba **al eje equivocado**. En zapata
cuadrada con momentos iguales pasa inadvertido; en zapata rectangular o con momentos
distintos, el resultado es incorrecto. El error llegó a cometerse al transcribir el
ejercicio de Aragón para validación.

### Diagnóstico previo: ¿etiqueta o física?

Antes de tocar nada se comprobó, con geometría deliberadamente asimétrica
(B ≠ L, Mx ≠ My), que la física estaba **internamente correcta y coherente**:

| Comprobación | Resultado |
|---|---|
| `ex` se compara contra `B` en la presión de contacto | ✔ coherente |
| El caso asimétrico distingue ejes (no es degenerado) | ✔ qmax cambia al cruzarlos |
| Punzonamiento: `Mux` toma b₁ en la dirección de su flexión | ✔ coherente |
| Estabilidad: cada eje usa su momento y su fuerza horizontal | ✔ coherente |

**Veredicto: caso A — etiqueta pura.** Ninguna aplicación física del momento estaba
invertida. No hizo falta detener la migración por la regla de seguridad.

### Puntos de ligadura modificados

El rótulo se ligaba a la física en **exactamente tres lugares**. Todo lo demás opera
sobre `ex`/`ey`, que no son ambiguos, y quedó intacto.

| # | Archivo | Antes | Después |
|---|---|---|---|
| 1 | `engine/soil/eccentricity.py` | `ex = My/P`, `ey = Mx/P` | `ex = Mx/P`, `ey = My/P` |
| 2 | `engine/foundation/punching_moment_transfer.py` | `Mux → b₁ a lo largo de Y` | `Mux → b₁ a lo largo de X` |
| 3 | `engine/soil/stability.py` | eje X ← `My` + `Hx` | eje X ← `Mx` + `Hx` |

La ligadura 2 corrigió además un rótulo interno confuso: el campo `axis_x` contenía una
entrada cuya propia etiqueta `axis` decía `"Y"`. Ahora `axis_x` contiene la
transferencia de la dirección X, con etiqueta `"X"`.

### Prueba de equivalencia física

Se ejecutó el motor **nuevo** con los momentos intercambiados y se comparó contra la
línea base **previa** de `tests/freeze/`: es el mismo problema físico descrito con otros
nombres, así que los resultados deben ser idénticos.

```
Diferencias fuera de los contenedores de moment_transfer : 0
v_max_MPa, Vu, φVc, q, Mu, As, estados                   : idénticos en los 14 casos
```

### Único cambio numérico real

En 7 de los 14 casos congelados, las dos entradas de `punching.moment_transfer`
**intercambian el campo que las contiene**:

```
axis_x.Mu_kNm: 112.0 -> 84.0
axis_y.Mu_kNm:  84.0 -> 112.0
```

Los valores son los mismos; cambia cuál está en `axis_x` y cuál en `axis_y`. Es
consecuencia directa —y deseada— de la ligadura 2: ahora `axis_x` describe de verdad la
dirección X. **`v_max_MPa`, el estado y el ratio de punzonamiento no cambian en ningún
caso.** La línea base se regeneró con este cambio revisado.

### Traducción para datos de la convención antigua

Quien tenga entradas escritas con la convención anterior del motor debe **intercambiar
`Mx` y `My`**. Las fuerzas horizontales `Hx`/`Hy` **no se tocan**: son fuerzas, no
momentos, y su rótulo siempre siguió al eje.

---

## Auditoría módulo por módulo

| Módulo | Variable | Significado físico | ¿Ligaba rótulo a eje? | Cambio |
|---|---|---|---|---|
| `soil/eccentricity.py` | `Mx`, `My` | momento por dirección de desplazamiento | **Sí — define la convención** | **Invertido** |
| `soil/contact_pressure.py` | `ex_m`, `ey_m` | excentricidades ya resueltas | No | Ninguno |
| `soil/stability.py` | `Mx`, `My`, `Hx`, `Hy` | volteo por eje | **Sí** | **Invertido (momentos)** |
| `foundation/flexure.py` | `e_m`, `dim_along_e_m` | excentricidad y dimensión de esa dirección | No | Ninguno |
| `foundation/shear_oneway.py` | `e_m`, `cantilever_m` | ídem | No | Ninguno |
| `foundation/punching_shear.py` | `Mux`, `Muy` | momentos transferidos | Delega en el módulo siguiente | Ninguno |
| `foundation/punching_moment_transfer.py` | `Mux`, `Muy` | b₁ en la dirección del momento (ec. 13-1) | **Sí** | **Invertido** |
| `foundation/depth_solver.py` | pasa `Mx`/`My` a los anteriores | orquestación | No — solo reenvía | Ninguno |
| `foundation/effective_depth.py` | usa `.ex_m`/`.ey_m` | iteración de d | No | Ninguno |
| `optimization/*` | métricas y puntuación | no ve momentos | No | Ninguno |
| `reports/*` | `Mx_kNm`, `My_kNm` | presentación | No | **Nota de convención añadida** |
| `domain/loads.py` | `Mx_kNm`, `My_kNm` | entrada del usuario | Solo rótulo | **Descripción reescrita** |
| `api/schemas.py` | `Mx_kNm`, `My_kNm` | contrato de la API | Solo rótulo | **Comentario de convención** |
| `ui/InputPanel.tsx` | campos `Mx`, `My` | entrada del usuario | Solo rótulo | **Ayuda por campo + nota visible** |

---

## Dónde queda declarada la convención para el usuario

| Superficie | Forma |
|---|---|
| Interfaz | Nota permanente en el panel de combinaciones + ayuda al pasar el cursor sobre cada campo |
| API | Comentario en `LoadCombinationInput` y descripción en `domain/loads.py` |
| Informe | Nota en la sección 4 «Combinaciones de carga» + `title` en las cabeceras de columna |
| `CalculationTrace` | `AXIS_CONVENTION_NOTE` en las hipótesis de `contact_pressure` y `punching` |
| Código | Encabezado de `engine/soil/eccentricity.py` |
