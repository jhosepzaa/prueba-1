# Estado tras la sesión autónoma: 4G, 4H, integración global y Fase 6

Suite: **1433 passed, 2 skipped**. Build de la UI correcto.
Baselines congelados **idénticos** a los aprobados en 5B:
`baseline.json` `0b2437648d89…`, `baseline_connected.json` `0f0e7c79af34…`.
Ningún número del motor cambió.

## Implementado

| Bloque | Resultado | Documento |
|---|---|---|
| 4G | Pareto con núcleo común (`pareto_mask`), escena del sistema conectado (planta/alzado), tabla comparativa, marca de Pareto en la memoria, bloqueo de D1 en el formulario | `docs/fase4g_presentacion_conectada.md` |
| 4H | `TraceView` por (ámbito, id); caché del barrido conectado para el informe; nota de α_s según la clasificación real | `docs/fase4h_deuda_transversal.md` |
| Integración | Catálogo de tipologías (`GET /api/typologies`) contrastado contra el código; **D4 corregido**; tabla comparativa y Pareto en la combinada | `docs/integracion_global.md` |
| Fase 6 | Registro de benchmarks del motor contra Aragón P1, P2, §3.5 y golden cases; informe generado desde el motor, con el arnés bibliográfico de §3.4.1 | `docs/fase6_validacion.md` |

## Defecto encontrado y corregido

**D4 — la zapata combinada ignoraba las fuerzas horizontales.** Con 4000 kN por columna
salía PASS sin verificar estabilidad. Ahora queda NO VERIFICADO si hay `Hx` o `Hy`. Sin
fuerzas horizontales nada cambia. La vista combinada muestra siempre la nota de búsqueda
y ya no titula «Ninguna alternativa cumple» cuando el motivo es un NO VERIFICADO.

## Incidencia de la sesión

Al crear `tests/validation/` sobrescribí `tests/validation/__init__.py`, que ya existía.
No hay control de versiones para comprobar su contenido. Todos los `__init__.py` de
paquetes de tests del proyecto tienen 0 bytes y nada importa desde ese paquete; los tests
preexistentes de la carpeta pasan. Conviene confirmarlo si hay copia de respaldo.

## Decisiones pendientes (no se tomaron)

1. **ACEPTACION_COMBINADA** — la combinada acepta solo PASS/INFO; aislada y conectada,
   todo lo que no es FAIL. Hoy afecta a combinadas con fuerzas horizontales.
2. **ESTABILIDAD_COMBINADA** — implementar deslizamiento y volcamiento de la combinada.
3. **VOCABULARIO_ACEPTADA** — «ACEPTADA» no significa lo mismo en aislada y conectada.
4. **Peso propio de viga `EXPLICITO`** — se reparte sobre un tramo que incluye media
   zapata interior (registrado en 5A).
5. **Caché en `/api/report-combined`** — mismo patrón que la conectada, no aplicado.

## Siguiente trabajo sin decisiones de ingeniería

- Esquema 2D y explicación de descartes agrupada para la combinada.
- Vista 3D del sistema conectado (hoy planta y alzado).
