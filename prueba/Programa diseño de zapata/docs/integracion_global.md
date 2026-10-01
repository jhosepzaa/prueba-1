# Integración global de las tres tipologías — inicio

Suite: 1402 passed, 2 skipped. Baselines idénticos.

## Qué se hizo

1. **Catálogo de tipologías** (`engine/integration/typology_catalog.py`, `GET /api/typologies`).
   Describe en datos, para aislada, combinada y conectada: endpoints, base normativa ya
   citada por el motor, criterio de aceptación, vocabulario de estados, capacidades de
   presentación, pendientes abiertos y diferencias conocidas. Los tests
   (`tests/test_integration_typology_catalog.py`, 15) lo contrastan contra el código: rutas
   existentes, predicado de aceptación real de cada generador, vocabularios del informe,
   pendientes del informe conectado y campos de los DTO.

2. **Defecto D4 corregido — la combinada ignoraba las fuerzas horizontales.**
   Con 4000 kN por columna salía PASS sin entrada de estabilidad. Ahora, si alguna
   combinación trae `Hx` o `Hy`, `solve_combined_footing` añade `stability_not_implemented`
   en NO VERIFICADO: nunca PASS. Sin fuerzas horizontales no cambia nada (K1–K4 congelados
   idénticos). Ningún número se modifica. El barrido combinado informa en `search_note`
   cuántos descartes fueron por WARNING/NO VERIFICADO y no por FAIL.
   Tests: `tests/test_combined_horizontal_forces_d4.py` (9).

## Decisiones necesarias antes de unificar vistas o comparar tipologías

| Id | Diferencia | Decisión |
|---|---|---|
| ACEPTACION_COMBINADA | La combinada acepta solo PASS/INFO; aislada y conectada aceptan todo lo que no es FAIL. Hoy afecta a combinadas con fuerzas horizontales. | Alinear con NO_FAIL (cambia qué alternativas devuelve el barrido combinado) o declararla deliberada. |
| ESTABILIDAD_COMBINADA | La combinada no verifica deslizamiento ni volcamiento; se declara NO VERIFICADO si hay H. | Implementar la estabilidad con la resultante de varias columnas y tests independientes. |
| VOCABULARIO_ACEPTADA | «ACEPTADA» = PASS/INFO en la aislada; = «sobrevive al barrido» en la conectada. | Vocabulario único (el cerrado de la conectada) o mostrar siempre el estado crudo. |
| PRESENTACION_COMBINADA | La combinada no tiene tabla comparativa, Pareto, esquema ni explicación de descartes. | Incorporarlos después de ACEPTACION_COMBINADA. |

## Siguiente paso previsto

Una comparación entre tipologías para el mismo par de columnas (combinada frente a
conectada) solo es válida tras resolver ACEPTACION_COMBINADA y VOCABULARIO_ACEPTADA: con
criterios distintos, los recuentos y los rótulos no son comparables.
