# Fase 2 — Motivos de descarte de la zapata combinada

Fecha: 2026-09-15. Tipo: implementación de presentación y trazabilidad. Estado: **cerrada, sin
cambios de criterios ni de baselines**.

## Problema

- El barrido de la combinada solo contaba los descartes; no conservaba por qué.
- `discard_reasons` lleva números en el texto y una verificación puede dar varios textos.
- Los descartes por WARNING / NO VERIFICADO (aceptación PASS_OR_INFO) y algunos FAIL no
  escriben ningún motivo.
- Las geometrías que el solver no resuelve (ValueError) desaparecían sin contarse.

## Solución (sin tocar criterios)

- `combined_solver`: cada motivo se registra también en `discard_records` (verificación de
  traza, aspecto, elemento). El texto y el orden de `discard_reasons` NO cambian (§5).
- `engine/optimization/combined_discards.py`:
  - `diagnose_combined_discard`: causas únicas por (categoría, verificación, aspecto), con los
    textos originales, estado, referencia normativa y combinación gobernante. Incluye las
    entradas de traza degradadas sin texto. Orden: severidad y luego orden de traza; la causa
    principal es la primera.
  - `CombinedDiscardSummary`: grupos por (categoría, aspecto, estado) con `count`,
    `primary_count`, verificaciones, elementos, referencias, `has_written_reason` y ejemplo;
    grupos de geometrías no resueltas; descartes por estado. Orden determinista.
- `combined_generator`: `discard_summary` y `unresolved_count` (aditivos).
  Invariante: `evaluated_count = aceptadas + discarded_count + unresolved_count`.
- API `/api/design-combined`: `discard_groups`, `discarded_by_status`, `unresolved_count`,
  `unresolved_groups` (aditivos). UI: panel «Motivos de descarte».
- Congelamiento: `("CombinedFootingResult", "discard_records")` en `DIAGNOSTIC_FIELDS`.

## Hallazgo (resuelto en la auditoría C-V: ahora tiene motivo escrito `shear_longitudinal / concreto_solo`)

`shear_longitudinal` (cortante del concreto solo) puede quedar en FAIL aunque luego se
dimensionen estribos que sí cumplen; el solver no escribe motivo y la geometría se descarta.
Ahora aparece como grupo `CORTANTE_LONGITUDINAL / no_cumple` sin motivo escrito. En el barrido
de prueba afecta a 94 de 117 descartes (4 como causa principal). Requiere decisión.

## Tests

`tests/test_combined_discards_phase2.py` (14): registros alineados con los textos y con su
verificación (prefijos independientes); cobertura de todos los puntos de descarte; causas
únicas y entradas degradadas cubiertas; causa principal; aspecto de punzonamiento = causa
física; recuentos y grupos contra un barrido manual independiente; invariante de recuentos;
determinismo y orden; descartes NO VERIFICADOS sin texto inventado; no resueltas; API aditiva.
Mutaciones detectadas: verificación equivocada, registro omitido, entradas sin texto ignoradas,
orden de causas, conteo de no resueltas.

## Resultados

Suite sin `tests/freeze`: 1368 pasan; `tests/freeze`: 225 pasan, 2 omitidos. Instantánea completa
de los 49 casos idéntica; baselines sin cambios.
