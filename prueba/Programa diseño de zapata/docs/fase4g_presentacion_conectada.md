# Fase 4G — Paridad de presentación de la cimentación conectada

Sin cambios en el cálculo. Baselines idénticos (`baseline.json` `0b2437648d89…`,
`baseline_connected.json` `0f0e7c79af34…`).

## Qué se añadió

| Pieza | Archivo | Nota |
|---|---|---|
| Núcleo de Pareto sobre métricas | `engine/optimization/pareto.py` | `METRIC_OBJECTIVES`, `pareto_mask`. `pareto_front` y `PARETO_OBJECTIVES` conservan su contrato y su resultado. |
| Escena del sistema | `engine/visualization/connected_scene.py` | `ConnectedSceneDTO`: huellas, viga, columnas, lindero y cotas situadas por el motor en el sistema local del reparto (X = eje de la viga desde el lindero). |
| API | `api/schemas.py`, `api/server.py` | Campos **aditivos**: `comparison` (todas las aceptadas), `pareto_objectives`, `pareto_size`, `scene`; en cada alternativa `footing_area_m2`, `max_plan_dimension_m`, `in_pareto`. |
| Memoria HTML | `engine/reports/connected_report.py` | Columna «Pareto», calculada sobre todas las aceptadas. |
| UI | `ConnectedSystemDiagram.tsx`, `ConnectedResultsView.tsx`, `ConnectedInputPanel.tsx`, `lib/api.ts` | Planta y alzado a escala; tabla comparativa con filtro de Pareto; bloqueo de `CUERPO_RIGIDO + PAR_PURO_EN_ZAPATA` (D1). |

## Reglas que se mantienen

- Pertenecer al frente de Pareto es una comparación de **costo**: no cambia el estado.
  Todas las alternativas siguen NO VERIFICADAS mientras TBD-C1 siga abierto.
- La vista no recalcula geometría: escala cajas y cotas del DTO. Un test lo verifica
  sobre el fuente.
- La regla D1 en TypeScript es una copia de la del motor, contrastada contra
  `check_couple_mode_compatible` en las cuatro combinaciones. El servidor sigue siendo la
  autoridad (422).

## Fuera de alcance, declarado

- Vista 3D del sistema conectado: se entrega planta y alzado 2D. El armado no se dibuja.
- La cota vertical de la viga respecto de las zapatas no la calcula el motor; en el
  esquema es una convención de dibujo y así lo dice `scope_note`.

## Tests

`tests/test_connected_presentation_phase4g.py` (16). Se ajustó un test de contrato de 4E
que exigía el texto literal del `disabled` del botón, que ahora incluye la condición D1.
