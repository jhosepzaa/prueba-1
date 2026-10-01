# Auditoría integral del motor

Ejecutada tras cerrar L1, L3 y L4, antes de abordar UI / 3D / reportes.

**Suite: 306 tests, 306 pasan. Casos golden: 8 de 8 (21 aserciones).**

---

## A. Defectos encontrados y corregidos

La auditoría no se limitó a re-verificar lo conocido: buscó inconsistencias
acumuladas. Encontró **tres**, dos de ellas falsos PASS reales.

### A1. Peralte efectivo `d` sobreestimado → capacidades infladas con PASS

**Severidad: alta (falso PASS).**

El motor calculaba `d = h − recubrimiento − db_asumido/2` con un diámetro
**asumido** (16 mm por defecto) y usaba ese único valor para flexión, cortante y
punzonamiento en **ambas direcciones**. Dos errores superpuestos:

1. La barra realmente seleccionada casi nunca es la asumida.
2. Una parrilla tiene **dos capas**: las barras de una dirección se apoyan sobre
   las de la otra, y la capa superior tiene menor `d`.

Medición real (B=L=2.6 m, h=0.50 m, barras 1/2"):

| Magnitud | Valor |
|---|---|
| `d` usado por el motor | 422.0 mm |
| `d` real capa inferior | 423.6 mm |
| `d` real capa superior | **410.9 mm** |
| Sobreestimación | **11.1 mm (≈2.7% de capacidad)** |
| Estado reportado | **PASS** |

**Corrección:** nuevo módulo `engine/foundation/effective_depth.py`. Resuelve `d`
por **punto fijo**: siembra con el diámetro asumido, hace un diseño preliminar,
recalcula `d` con los diámetros reales de la capa superior, e itera hasta
estabilizar (máx. 4 pasadas). Si no converge, adopta el mayor diámetro visto — el
`d` más pequeño, siempre conservador.

Se adopta el `d` de la **capa superior para ambas direcciones**: ligeramente
conservador para la inferior, garantiza que ninguna capacidad quede sobreestimada.
La geometría real por capa se sigue reportando.

Efecto colateral verificado: el diámetro sembrado ya **no influye** en el
resultado (test de invariancia con semillas de 9.5 mm y 34.9 mm).

### A2. Opciones de armado con longitud de desarrollo sin verificar

**Severidad: alta (falso PASS).**

`check_development_length` se ejecutaba **una sola vez**, sobre la barra elegida
por `select_rebar`. Pero `generate_rebar_alternatives` ofrece varios diámetros, y
las soluciones de armado los combinan libremente. Como `ld` crece linealmente con
`db`, una opción de 3/4" puede no desarrollarse donde una de 1/2" sí lo hace.

Medición real: **12 de 16 soluciones de armado** de una geometría usaban un
diámetro cuya `ld` nunca se verificó.

**Corrección:** nuevo módulo `engine/reinforcement/options_development.py`.
Verifica **cada opción con su propio diámetro y separación**, marca
`development_ok` y **excluye** las no desarrollables antes de que lleguen al
generador de armados. El trace registra cuáles se aceptaron y cuáles se
descartaron, con su `ld` requerida y disponible.

### A3. Detalle de §11.12.6 calculado pero ausente del trace

**Severidad: media (trazabilidad).**

La verificación de transferencia de momento computaba γf, γv, Jc y el esfuerzo
combinado, pero el `CalculationTrace` solo recibía la **conclusión**
("CUMPLE… ratio 0.377"), no el desarrollo. Una verificación no auditable.

**Corrección:** el trace de punzonamiento ahora incorpora el desarrollo completo:

```
§11.12.6: sección crítica 0.8110 x 0.8110 m, bo=3.2438 m, d=0.4109 m
| v_directo = Vu/(bo·d) = 568.71 kN/(3244·411) = 0.4266 MPa
| eje Y: b1=0.8110, b2=0.8110 -> γf = 1/(1+(2/3)·√1.0000) = 0.6000, γv = 0.4000
| Jc = 1.554902e-01 m⁴, c = 0.4055 m
| v = γv·Mu·c/Jc = 0.4000·56.00·0.4055/1.554902e-01 = 0.0584 MPa
```

---

## B. Auditoría del CalculationTrace

18 checks obligatorios verificados presentes en toda evaluación:

`self_weight` · `contact_pressure` · `min_depth` · `flexure_x/y` · `shear_x/y` ·
`punching` · `short_direction_distribution` · `rebar_x/y` ·
`rebar_options_development_x/y` · `development_x/y` · `sliding` ·
`overturning_x/y`

Verificado por test:
- Sin IDs duplicados.
- Los 11 campos exigidos presentes y no vacíos en cada entrada.
- Toda entrada normativa cita artículo (`§` o `art.`).
- Las entradas no normativas se declaran como tales (`code_name = "N/A"`).
- Los checks estructurales declaran su combinación gobernante.
- `min_depth` siempre arrastra la nota de interpretación adoptada.
- `development_*` siempre declara la política de ganchos.

## C. Auditoría de estados

Los **cinco** estados son alcanzables (ninguno es código muerto):

| Estado | Alcanzable mediante | Bloquea PASS | Descarta |
|---|---|---|---|
| PASS | Todo verificado y cumple | — | No |
| INFO | Reducción sísmica declarada pero no aplicable | **No** | No |
| WARNING | Reservado a limitaciones con falso PASS (hoy ninguna) | Sí | No |
| NO VERIFICADO | Fuerzas horizontales sin μ ni FS | Sí | No |
| FAIL | Presión de contacto excedida | Sí | **Sí** |

Invariantes verificadas:
- `overall_status == worst(entradas)` en todos los escenarios probados.
- Toda entrada FAIL produce al menos una razón de descarte.
- Ninguna razón de descarte sin una entrada FAIL que la respalde.
- Un PASS global implica que ninguna entrada bloquea PASS.
- Un WARNING solo puede provenir de una limitación registrada (nunca espurio).

## D. End-to-end

```
741 geometrías en 1.15 s → 475 válidas, 266 descartadas
Frente de Pareto: 6 no dominadas
Soluciones de armado sobre top-5: 60 (antes 80: 20 se filtraron por desarrollo)
Ganador: B=2.00 L=2.50 h=0.40 d=0.3158 m → PASS
```

**Razones de descarte:**

| Motivo | Geometrías |
|---|---|
| Presión de contacto (qmax > qadm) | 226 |
| Longitud de desarrollo (L4) | 118 |
| Sin opciones de armado desarrollables | 100 |
| Otros (núcleo central, punzonamiento, cortante) | 81 |

**Combinación gobernante por verificación** (independiente por check):

| Check | Gobierna |
|---|---|
| contact_pressure | S1 |
| flexure_x/y, shear_x/y, punching | U1 |
| sliding, overturning_x/y | S2 |

Las tres familias de combinaciones gobiernan checks distintos.

## E. Limitaciones restantes

| Limitación | Tipo | ¿Falso PASS? |
|---|---|---|
| Reducción sísmica 80% (§15.2) | NO IMPLEMENTADO | No — emite INFO, resultado más conservador |
| §15.7 interpretación `d ≥ 300 mm` | INTERPRETACIÓN ADOPTADA | No — lectura más exigente, parametrizada |
| Columnas circulares | FUERA DE ALCANCE | No — rechazo en validación de entrada |
| `Jc` en §11.12.6 | Derivación geométrica, no cita | Declarado en el trace |
| Masa de acero sin ganchos ni traslapes | Alcance declarado | Cota inferior, marcada |
| `d` conservador de capa superior en ambas direcciones | Decisión de ingeniería | No — conservador por construcción |

**Ninguna limitación restante puede producir un falso PASS** (verificado por test
sobre todo el registro).

## F. Condiciones para emitir PASS

1. Todas las verificaciones de resistencia cumplen: presión de contacto dentro
   del núcleo y ≤ qadm, flexión, cortante unidireccional, punzonamiento
   **incluyendo transferencia de momento**, peralte mínimo.
2. La longitud de desarrollo es suficiente para la barra seleccionada **y** existe
   al menos una opción de armado desarrollable en cada dirección.
3. Si hay fuerzas horizontales o momentos, el usuario declaró **μ, FS de
   deslizamiento y FS de volcamiento**; sin ellos → NO VERIFICADO.
4. Deslizamiento y volcamiento cumplen los FS declarados.
5. Ninguna limitación relevante con capacidad de falso PASS sigue pendiente.
