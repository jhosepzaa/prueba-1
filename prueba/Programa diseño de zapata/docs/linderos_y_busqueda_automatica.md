# Linderos del terreno y búsqueda automática — combinada y conectada (2026-09-28)

Pedido del usuario: declarar los límites del terreno para que se tenga en cuenta la
posición de la zapata, y que el programa asuma la «Búsqueda de geometría» sin que haga
falta escribirla. **Sin cambios de baseline**: con los campos nuevos vacíos, el
comportamiento es el de siempre (medido: el diff del congelamiento es el mismo que el de
`docs/freeze_desarrollo_columna_descentrada.md`, ni un caso más).

## 1. Linderos (`SiteLimits`, `engine/domain/site_limits.py`)

El proyectista declara la distancia libre de la **cara** de la columna al lindero, por cada
lado. `None` = sin límite; 0 = columna al ras. Es geometría de la propiedad, no un criterio
de diseño.

| Campo | Combinada | Conectada |
|---|---|---|
| `start_clearance_m` | cara de la primera columna → lindero inicial | (lo da la holgura al lindero de `EdgeAnchor`) |
| `end_clearance_m` | cara de la última columna → lindero final | cara de la columna interior → lindero del fondo |
| `side_neg/pos_clearance_m` | caras laterales → linderos laterales | ídem |

### Combinada: la zapata se COLOCA dentro del terreno

Para cada longitud, el generador prueba una posición: la que centra la resultante de la
combinación permanente (el mismo criterio de predimensionamiento que la ayuda de centrado
de la API), recortada para cubrir todas las columnas y no salir de los linderos. Con la
columna al lindero, la zapata queda al ras. Lateralmente, sin linderos laterales no se
corre nada (idéntico a antes); con ellos, el eje de la zapata se corre lo mínimo necesario.
Una planta que no cabe no se evalúa, y la nota lo cuenta. Cada alternativa guarda
`first_column_edge_distance_m` y `transverse_shift_m`, y la escena y la memoria reconstruyen
el layout con ellos.

Es **heurística de búsqueda**: centrar no es exigencia normativa (E.060 §15.2 pide ausencia
de tracciones y presión admisible, y eso se verifica para todas las combinaciones).

### Conectada: los linderos RECORTAN el barrido

El cuerpo libre de la conectada es plano, a lo largo de la viga, y las dos zapatas se
modelan centradas sobre su columna en la dirección transversal; la interior, también a lo
largo de la viga. Por eso un lindero lateral limita el ancho a `columna + 2·holgura menor`
y el del fondo, el largo de la interior a `columna + 2·holgura`. **No se corren**: hacerlo
exigiría torsión en la viga y reparto biaxial en el cuerpo rígido, que no están
implementados. Es una decisión de modelo nueva, no un pendiente de implementación.

## 2. Búsqueda automática (`engine/optimization/auto_search.py`)

Se activa con `auto_ranges` o dejando vacío algún rango. Hermana de la heurística de la
aislada (`engine/foundation/auto_search_range.py`):

- **Estimación:** A ≈ P_servicio_máx / q_disponible (qadm en base neta con la misma
  conversión que el verificador), con margen generoso para la excentricidad, el par y el
  sismo, recortada por los linderos y por Df (la zapata no puede asomar del terreno).
- **Dos pasadas:** malla gruesa (peralte cada 0,20 m) y, alrededor de la mejor, malla fina
  un paso grueso a cada lado (peralte cada 0,05 m). Así la mejor sale del borde de la
  malla gruesa si había quedado en él.
- **Conectada:** en modo automático las dos zapatas comparten peralte (la malla
  independiente es n² parejas) y el tope se ajusta al tamaño de cada malla para que
  ninguna pasada salga truncada. Se declara en la nota.
- Todo se dice en `search_note`, y el aviso de borde se mide contra los rangos EFECTIVOS.

**Medido** con el problema 2 de Aragón (sismo a nivel de servicio, gancho de 90° en la
zapata de lindero): la búsqueda automática, sin dar un solo rango, evalúa 5 098 ternas en
22 s, acepta 215 y recomienda exterior 2,00 × 6,50 m, interior 6,50 × 2,50 m, h = 1,05 m,
31,6 m³ de concreto. El mejor rango refinado a mano daba 40,4 m³. Con una sola pasada
fueron 46 660 ternas en 55 s y la mejor quedaba contra el borde.

## 3. Defecto corregido de paso: el aviso de borde de la conectada

Comparaba la geometría del motor (SI) con los rangos de la petición (en la unidad del
usuario) y rotulaba siempre como «largo» la dimensión L, aunque con la viga en X el largo es
B. Ahora usa `ConnectedAlternativeSet.search_ranges_m` (SI, ya recortados) y la dimensión
que corre de verdad sobre la viga. En el caso de Aragón el aviso no salía y debía salir.

## 4. Contrato (todo aditivo)

- `SiteLimitsInput`; `site_limits` en `CombinedDesignRequest` y `ConnectedDesignRequest`.
- Rangos de `CombinedSearchInput` y `ConnectedSearchInput` opcionales; `auto_ranges`.
- `CombinedSearchInput.first_column_edge_distance_m` admite `null` (posición automática);
  su valor por defecto sigue siendo 0,25.
- `first_column_edge_distance_m`/`transverse_shift_m` en las alternativas de la combinada.
- Campos de longitud clasificados en `api/unit_fields.py`.

La interfaz trae la búsqueda automática activada por defecto y un panel «Límites del
terreno» en las dos tipologías; el modo manual sigue disponible.

Tests: `tests/test_linderos_y_busqueda_automatica.py` (posiciones reconstruidas a mano; los
rangos automáticos cubren la solución conocida de Aragón P2).
