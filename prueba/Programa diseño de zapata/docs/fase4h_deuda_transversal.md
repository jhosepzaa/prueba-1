# Fase 4H — Deuda transversal

Sin cambios numéricos. Baselines idénticos. Suite: 1378 passed, 2 skipped.

## Corregido

| Defecto | Dónde | Corrección |
|---|---|---|
| `TraceView` indexaba la traza por `id`; con ids repetidos entre ámbitos mostraba una zapata bajo el rótulo de otra. | `ui/src/components/TraceView.tsx` | Índice `Map<id, TraceEntry[]>` y clave React `traceKey(e)` = `scope/id`, igual que `trace_key` del motor. El título muestra el ámbito cuando existe. |
| `/api/report-connected` repetía el barrido completo recién hecho por `/api/design-connected`. | `api/server.py` | Caché LRU de 4 entradas indexada por la petición serializada, con cerrojo. Solo guarda resultados; los errores se relanzan en cada llamada. |
| La hipótesis de α_s del punzonamiento decía siempre «columna interior». | `engine/foundation/depth_solver.py` | `_alpha_s_note` según `column_position`: interior, borde, esquina o degenerada. Es texto de traza. |

Tests: `tests/test_transversal_debt_phase4h.py` (9).

## Observado, sin corregir (requiere decisión o no es alcanzable)

- **Peso propio de viga `EXPLICITO`** (registrado en 5A): se reparte sobre `[L1, s_corte]`,
  que incluye media zapata interior ya contada en el peso de esa zapata. Corregirlo
  cambia números: requiere decisión de modelación. Ningún caso congelado lo usa en rígido.
- **`/api/report-combined`** también recalcula el diseño que acaba de servir
  `/api/design-combined`. Mismo patrón que la conectada; no se tocó para no cambiar el
  flujo de la combinada sin necesidad. Aplicar la misma caché es directo si se decide.
- **Cierre del reparto en la traza del sistema conectado** (`not d.closes` →
  motivo sin FAIL): la rama es inalcanzable, porque `distribute_couple` ya lanza
  `ValueError` si el equilibrio no cierra. No hay defecto observable.
