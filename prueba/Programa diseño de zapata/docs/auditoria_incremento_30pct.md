# Auditoría — incremento del 30 % de la presión admisible (E.060 §15.2.4)

Fecha: 2026-09-18. Estado: **hallazgo corregido**, sin cambios de baseline.

---

## 1. Qué dice la fuente

`docs/normativa/fuentes/e.060-concreto-armado-sencico.pdf`, **§15.2.4**, literal:

> Se podrá considerar un incremento del 30% en el valor de la presión admisible del suelo
> para los estados de cargas en los que intervengan cargas temporales, tales como sismo o
> viento.

Dos cosas del texto gobiernan la implementación:

1. **«Se podrá»** — es potestativo, no una exigencia. Por eso
   `allow_temporary_increase_30pct` es una declaración del proyectista y está **apagada por
   defecto**: el motor no lo aplica por su cuenta.
2. **«la presión admisible del suelo»** — el artículo habla del SUELO y del estado de
   cargas. No distingue tipología de cimentación.

El artículo vecino §15.2.5 es el de la reducción sísmica al 80 %, ya cerrado para las tres
tipologías (`docs/reduccion_sismica_combinada.md`).

## 2. Hallazgo

**La zapata combinada no aplicaba el incremento.** Juzgaba la presión contra `soil.qadm_kPa`
sin pasar por `_effective_qadm`, que es donde la aislada lo aplica y de donde la conectada lo
hereda a través de `evaluate_candidate`.

| Tipología | Antes | Ahora |
|---|---|---|
| Aislada | Lo aplica (`_effective_qadm`) | igual |
| Conectada | Lo hereda por `evaluate_candidate` | igual |
| **Combinada** | **No lo aplicaba** | Lo aplica, con el mismo operador |

**Evidencia:** habilitando la opción, una combinada con qmax = 94,3 kPa sobre un suelo de
q_adm = 80 kPa fallaba por presión de contacto, cuando el criterio declarado admitía
1,30 × 80 = 104 kPa. La aislada, con la misma opción y el mismo suelo, sí lo admitía.

**Severidad: media.** No produce un falso PASS —la combinada era más estricta de lo que el
criterio declarado permite—, pero sí un **falso FAIL**: descartaba geometrías que el propio
criterio del proyecto acepta, y de forma incoherente con las otras dos tipologías. Un usuario
que habilitara la opción la vería surtir efecto en una tipología y no en otra, sin que nada
lo explicara.

## 3. Corrección

No es una decisión de ingeniería nueva: el criterio ya estaba adoptado, implementado y
declarado; lo que faltaba era aplicarlo donde el artículo también alcanza. Se reutiliza el
operador en vez de duplicarlo.

- `_effective_qadm` → **`effective_qadm`**, público, con el texto del artículo en su
  docstring y el factor extraído a `TEMPORARY_INCREASE_FACTOR = 1.30`.
- `combined_solver` lo llama por combinación de servicio. Como el artículo habla del **estado
  de cargas**, basta con que **alguna columna** declare sismo o viento en esa combinación
  para que el estado sea temporal.
- El motivo de descarte por presión cita ahora el **q_adm realmente usado**, no el declarado:
  si dijera el otro, el número no cuadraría con el criterio aplicado.
- La traza cita **§15.2.4**, no «§15.2», que es el capítulo entero.

## 4. Efecto

**Ninguno con la opción apagada**, que es el valor por defecto y el de todos los casos
congelados. Habilitada, la combinada deja de descartar geometrías que el criterio admite.

**Baselines: sin cambios.** `tests/freeze` 225 pasan y 2 se omiten, con los hashes intactos.

## 5. Tests

`tests/test_temporary_increase_30pct.py` (10 tests): el operador reconstruido a mano para las
cuatro combinaciones de sismo/viento; apagado por defecto; sin carga temporal no se aplica; la
combinada lo aplica igual que la aislada —el caso que documenta el hallazgo—; basta con que
lo declare cualquiera de las dos columnas; el motivo cita el q_adm usado; la traza cita el
artículo exacto; y no toca la estabilidad ni el diseño factorizado.

**Siete mutaciones deliberadas, siete detectadas.** Una de ellas —ignorar el sismo declarado
en la segunda columna— pasó desapercibida en el primer intento porque el escenario lo
declaraba en la primera; el test se reforzó para cubrir las dos posiciones.

## 6. Lo que esta auditoría NO cambia

- El incremento sigue siendo **potestativo**: no se activa solo.
- No se aplica a la estabilidad ni al diseño factorizado: es presión **admisible** del suelo,
  y el diseño por resistencia va por §15.2.1.
- No se combina con ningún otro criterio: la reducción del 80 % de §15.2.5 actúa sobre las
  **acciones**, y este incremento sobre la **resistencia admisible**. Son independientes y el
  motor los aplica por separado.
