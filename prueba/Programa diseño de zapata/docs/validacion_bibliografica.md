# Fase 8 — Validación

## Estado honesto: qué está validado y qué no

| Tipo de validación | Estado | Cobertura |
|---|---|---|
| **Analítica independiente** (integración numérica, bisección, equilibrio) | ✔ **Completada** | 42 tests |
| **Casos golden verificados a mano** | ✔ Completada | 8 casos, 21 aserciones |
| **Auditorías y regresiones de defectos** | ✔ Completadas | 13 + 19 tests |
| **Contra ejemplos resueltos de bibliografía peruana** | ✘ **PENDIENTE** | 0 casos |

## Por qué la validación bibliográfica está pendiente

**No dispongo de los textos** (Ottazzi, Blanco Blasco, Harmsen, Morales Morales u
otros). Una búsqueda en línea devolvió únicamente:

- subidas de estudiantes en Scribd / Studocu / SlideShare, de pago y sin
  posibilidad de verificar su corrección;
- un artículo abierto ([UNIENSEÑA](https://uniensena.com/diseno-de-zapata-aislada-portico-plano/))
  que resultó ser un recorrido metodológico con capturas de pantalla, **sin
  valores numéricos transcritos** que pudieran contrastarse.

Cargar un caso con números inventados y atribuirlos a un autor sería fabricar
bibliografía. El registro `tests/validation/reference_cases.py` queda **vacío a
propósito**, y `test_registry_state_is_explicit` emite un *skip* con el motivo,
de modo que la suite nunca aparente una validación que no se hizo.

## Validación analítica realizada

Cada magnitud que el motor resuelve en forma cerrada se recalcula por un camino
que **no comparte nada** con la implementación validada:

| Magnitud del motor | Camino independiente |
|---|---|
| Momento en la cara de columna (fórmula trapezoidal) | Integración numérica del campo de presiones, 20 000 pasos |
| Cortante a distancia *d* | Integración numérica de la zona exterior |
| Vu de punzonamiento (Pu − qu·A_crit) | Integración celda a celda fuera del perímetro crítico (600×600) |
| As requerido (solución cuadrática) | Bisección sobre φ·As·fy·(d − a/2) = Mu, 200 iteraciones |
| φVc cortante | Transcripción independiente de la ec. 11-3 |
| q máx / q mín | Evaluación directa del campo lineal en las esquinas |
| Condición de núcleo central | Definición geométrica y contraste con el signo de q mín |

### Resultados — Caso A: zapata 2.00 × 2.00, columna 0.40 × 0.40, Pu = 560 kN, sin momento

| Magnitud | Motor | Analítico | Unidad | Diferencia |
|---|---|---|---|---|
| Momento en cara de columna | 89.60000 | 89.60000 | kN·m | 0.0000 % |
| Cortante a *d* de la cara | 106.40000 | 106.40000 | kN | 0.0000 % |
| Vu punzonamiento | 465.86400 | 465.86400 | kN | 0.0000 % |
| φVc cortante | 556.23304 | 556.23304 | kN | 0.0000 % |
| Presión máxima | 140.00000 | 140.00000 | kPa | 0.0000 % |
| As requerido por flexión | 5.66167 | 5.66167 | cm² | 0.0000 % |

### Resultados — Caso B: zapata 2.80 × 2.20, momento biaxial, Pu = 800 kN, ex = 0.15 m, ey = 0.10 m

| Magnitud | Motor | Analítico | Unidad | Diferencia |
|---|---|---|---|---|
| Momento dirección X | 252.94461 | 252.94461 | kN·m | 0.0000 % |
| Momento dirección Y | 176.48385 | 176.48385 | kN·m | 0.0000 % |
| Cortante dirección X | 264.71392 | 264.71392 | kN | 0.0000 % |
| Vu punzonamiento | 706.16883 | 706.16889 | kN | 0.0000 % |
| Presión máxima | 207.03323 | 207.03323 | kPa | 0.0000 % |
| Presión mínima | 52.70703 | 52.70703 | kPa | 0.0000 % |
| As requerido por flexión | 19.13893 | 19.13893 | cm² | 0.0000 % |

### Equilibrio global del campo de presiones

Integrando sobre toda la base debe cumplirse ∫q dA = P, ∫q·x dA = P·ex y
∫q·y dA = P·ey.

| Caso | Fuerza integrada | Aplicada | Momento Y integrado | P·ex | Momento X integrado | P·ey |
|---|---|---|---|---|---|---|
| P=500, 2.0×2.0, e=0 | 500.0000 | 500.0000 | −0.0000 | 0.0000 | 0.0000 | 0.0000 |
| P=700, 2.8×2.8, ex=0.086 ey=0.115 | 700.0000 | 700.0000 | 60.1996 | 60.2000 | 80.4995 | 80.5000 |
| P=900, 3.0×2.2, ex=0.20 ey=0.10 | 900.0000 | 900.0000 | 179.9989 | 180.0000 | 89.9994 | 90.0000 |

Los residuos (≤ 0.0012 kN·m) son error de discretización de la malla, no del motor.

## Qué NO demuestra esta validación

La coincidencia analítica prueba que **las ecuaciones están correctamente
implementadas y despejadas**. No prueba que sean **las ecuaciones correctas según
E.060** — eso depende de la extracción normativa, que se validó por separado
citando el texto del PDF artículo por artículo
(ver [referencias_e060_e050.md](normativa/referencias_e060_e050.md)).

Tampoco sustituye el contraste con un ejemplo resuelto por un ingeniero, que es
lo único que verifica el **criterio de diseño completo** de punta a punta.

## Cómo completar la validación bibliográfica

El arnés ya está construido. Para cada ejemplo del libro hace falta transcribir:

**Entrada**
- P y M de servicio; P y M factorizados (o los factores empleados)
- f'c, fy, dimensiones de columna
- qadm y si es bruta o neta
- peso unitario del suelo, Df, recubrimiento adoptado

**Resultados publicados** (los que estén; el resto se deja vacío)
- B, L, h, d
- q máx, q mín
- Mu de diseño y As requerido en cada dirección
- Vu y φVc de cortante y de punzonamiento
- armado final (Ø y separación)

**Supuestos del autor** — imprescindibles para interpretar cualquier desajuste:
si usó ACI en vez de E.060, si redondeó dimensiones, si estimó *d*, si incluyó el
peso del relleno, si aplicó el incremento del 30 % de §15.2, o qué lectura dio a
§15.7.

Con esos datos, añadir un `BibliographicCase` a `REFERENCE_CASES` basta: la suite
lo ejecuta y compara automáticamente cada magnitud, tolerando la desviación que se
declare.
