# Fase 9b — Vano libre físico de la viga y geometría de las métricas de viga

Fecha: 2026-09-15. Estado: **cerrada y congelada** (freeze dirigido: solo `beam_span_m`).

## Decisiones aprobadas

- `beam_span_m = max(f_i − L1, 0)` en todos los modelos. Antes valía `s_corte − s_inicio` del
  tramo de diseño: `s_corte − L1` (EQUILIBRIO, CUERPO_RIGIDO) o `s_corte − a` = distancia entre
  ejes (PAR_PURO). `s_corte` es la rótula, no un borde de la viga (Fase 9a).
- Volumen de viga (métrica) = vano libre + lo que sobresale de cada zapata. Lo que queda dentro
  de una zapata ya está en su prisma B·L·h.
- Si `z_b` no está declarada, la métrica adopta `z_b = 0` y lo traza como hipótesis
  (`BEAM_METRIC_SOFFIT_HYPOTHESIS`). Da el volumen de viga mínimo compatible con la geometría.
- Acero longitudinal de la viga: `(As⁻ + As⁺)·(c_i − c_e)`, sin anclajes ni estribos.

## Modelo

```text
ℓ_e = L1 − c_e      ℓ_v = f_i − L1      ℓ_i = c_i − f_i
t_j = max(0, min(z_b + h, h_j) − max(z_b, 0))
V_vano = b·h·ℓ_v    V_dentro,j = b·t_j·ℓ_j (zapata)    V_sobre,j = b·(h − t_j)·ℓ_j (viga)
V_viga = V_vano + V_sobre,e + V_sobre,i
invariante: V_viga + V_dentro,e + V_dentro,i = b·h·(c_i − c_e)
```

## Implementación

- `engine/analysis/connected_statics.py`: `BeamAxisGeometry` y `beam_axis_geometry()` (c_e, L1,
  f_i, c_i, z_b declarada). El peso propio de 9a la usa: refactor sin cambio numérico.
- `engine/foundation/connected_solver.py`: `ConnectedFootingResult.beam_axis`; `beam_span_m`
  lee `beam_axis.clear_span_m`.
- `engine/optimization/connected_metrics.py`: `BeamVolumeBreakdown`, `beam_volume_breakdown()`,
  hipótesis de z_b y de acero; `_beam_concrete_m3` y `_beam_steel_kg` reescritas.
- `engine/reports/connected_report.py`: desglose de la métrica e hipótesis en la memoria.
- `tests/freeze/snapshot.py`: `("ConnectedFootingResult", "beam_axis")` en `DIAGNOSTIC_FIELDS`
  (la geometría no se congela; `beam_span_m` sí). Las métricas nuevas no se congelan.

No cambian estados, estática, cargas, peso propio, diseño ni traza: la instantánea completa de
los 49 casos antes y después difiere solo en `beam_span_m` de 13 casos conectados. En los
barridos congelados no cambian el orden, la mejor alternativa ni las otras métricas.

## Valores (m)

| Casos | beam_span_m | Concreto viga (m³) antes → ahora |
|---|---|---|
| Z1, Z1b, Z3, Z5, Z7, Z8, Z13, Z14 | 4,25 → 3,15 | 1,785 → 1,570 |
| Z2, Z15 (PAR_PURO) | 6,00 → 3,15 | 2,520 → 1,570 |
| Z6 | 4,40 → 3,30 | 1,848 → 1,617 |
| Z11 (PAR_PURO) | 6,00 → 3,25 | 2,520 → 1,838 |
| Z12 | 4,60 → 1,25 | 1,932 → 1,523 |

## Tests

- `tests/test_beam_span_metrics_phase9b.py` (25): cálculo a mano en Z1, Z2, Z3, Z6, Z11, Z12 y
  Z15; independencia del modelo; invariante sin doble conteo y métricas aditivas en los 13
  casos; z_b no declarada (hipótesis) y declarada (0 y 0,30); misma geometría que el peso propio;
  informe.
- `tests/test_connected_search_phase4d.py`: el test de volumen dejó de ser tautológico.
- `tests/test_punching_failure_cause_phase5b.py`: el guardián de `DIAGNOSTIC_FIELDS` lista la
  ampliación de 9b.
- Mutaciones detectadas: fórmula antigua del vano, volumen sin lo que sobresale y acero sobre
  el vano libre.

## Freeze

| Archivo | Cambio | SHA-256 |
|---|---|---|
| `baseline.json` | ninguno | `2f7eee69b46c…` |
| `baseline_connected.json` | `numeros.beam_span_m` en los 13 casos | `96a4a63de28d…` |
| `reference_pre_5a_non_beam.json` | `beam_span_m` en Z3, Z12, Z13 y Z14 | `1e3c1ebf2f83…` |
