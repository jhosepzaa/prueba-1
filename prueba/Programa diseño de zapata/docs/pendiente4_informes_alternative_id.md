# Pendiente 4 — Los informes no sustituyen en silencio una `alternative_id`

Fecha: 2026-09-14. Tipo: corrección de API sin decisión de ingeniería (CLAUDE.md §3). Sin
cambios en el motor ni en los baselines.

## Hallazgo

| Endpoint | Antes | Efecto |
|---|---|---|
| `/api/report-combined` | Buscaba el id solo entre las `top_n` mostradas; si no estaba, reportaba `top[0]` | Memoria de otra zapata, sin aviso. Un id válido fuera de `top_n` también se sustituía |
| `/api/report-connected` | `render_connected_report_html` sustituía un id no encontrado por la mejor clasificada | Mismo defecto; no estaba registrado |

## Corrección

- **Combinada:** el id se busca entre **todas** las aceptadas (`comparison`). Si no existe:
  422 con el id y el número de aceptadas. Sin id se reporta la primera del ordenamiento
  (= `top[0]`). El título de la memoria nombra la alternativa reportada.
- **Conectada:** si el id no está entre las aceptadas, 422 antes de generar el informe. Sin id,
  el informe sigue emitiéndose siempre (también sin aceptadas).

## Tests

`tests/test_report_alternative_id_pending4.py`:
- combinada: id inexistente → 422; id fuera de `top_n` → esa alternativa; sin id → la primera;
- conectada: id inexistente → 422; id existente → «Memoria de la alternativa <id>»; sin id → 200.
