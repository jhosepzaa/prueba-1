# Pendiente 8 — vocabulario común de estados entre tipologías (análisis)

Fecha: 2026-09-18. Estado: **análisis; no implementado**. Requiere decisión del usuario:
`CLAUDE.md` §3 lista expresamente «el significado del vocabulario de estados» entre las
paradas obligatorias.

---

## 1. El problema

La máquina de verificación es **una sola** para las tres tipologías: `CheckStatus`, con
PASS = INFO < WARNING < NO VERIFICADO < FAIL. Lo que difiere es el **rótulo** con que cada
tipología presenta ese estado al usuario.

| `CheckStatus` | Aislada (`report_model.status_label`) | Conectada (`connected_report.alternative_label`) | Combinada |
|---|---|---|---|
| PASS / INFO | **ACEPTADA** | **CONFORME** (si no hay TBD abierto) | estado crudo |
| WARNING | ACEPTADA CON OBSERVACIONES | **ACEPTADA** | estado crudo |
| NO VERIFICADO | NO VERIFICADA | NO VERIFICADA | estado crudo |
| FAIL | DESCARTADA | RECHAZADA | estado crudo |

El choque está en negrita: **«ACEPTADA» significa cosas distintas**. En la aislada es
PASS/INFO —lo mejor que hay—; en la conectada es WARNING —aceptada con reservas—. Es la
diferencia `VOCABULARIO_ACEPTADA` del catálogo, que desde la decisión 6 alcanza también a
la combinada, cuyo conjunto aceptado puede contener alternativas NO VERIFICADAS.

**Consecuencia:** una vista común que muestre el rótulo sin decir de qué tipología es haría
pasar una conectada con observaciones por una aislada que cumple. Y «DESCARTADA» frente a
«RECHAZADA» son dos palabras para lo mismo.

Nada de esto afecta al cálculo: los estados internos son correctos y coherentes. Es un
problema de presentación, pero de los que inducen a error al lector.

## 2. Las dos salidas que plantea el catálogo

**Opción 1 — vocabulario único para las tres.** Un solo mapa estado → rótulo, con la
distinción de conformidad que ya tiene la conectada:

| Estado | Rótulo propuesto |
|---|---|
| PASS / INFO sin pendiente abierto | CONFORME |
| PASS / INFO con pendiente abierto | NO VERIFICADA |
| WARNING | ACEPTADA CON OBSERVACIONES |
| NO VERIFICADO | NO VERIFICADA |
| FAIL | RECHAZADA |

Desaparece «ACEPTADA» a secas, que es justamente la palabra ambigua, y desaparece el par
DESCARTADA / RECHAZADA.

*A favor:* resuelve el problema de raíz y hace posible una vista común.
*En contra:* cambia rótulos que el usuario ya ve en la aislada («ACEPTADA» → «CONFORME»,
«DESCARTADA» → «RECHAZADA»). Toca `report_model.StatusLabel`, la memoria de la aislada, la
UI y los tests que fijan el vocabulario. **Hay que comprobar si toca golden cases.**

**Opción 2 — mostrar siempre el estado crudo junto al rótulo.** Cada rótulo viaja
acompañado de su `CheckStatus` («ACEPTADA · PASS», «ACEPTADA · WARNING»). Los rótulos
actuales no se tocan.

*A favor:* no cambia nada existente y es imposible de malinterpretar si se lee entero.
*En contra:* no resuelve la ambigüedad, la hace tolerable. Dos tipologías siguen usando la
misma palabra para cosas distintas, y quien lea solo el rótulo sigue equivocándose.

## 3. Recomendación

**Opción 1**, por dos razones:

1. La combinada ya entrega el estado crudo y aun así el catálogo mantiene la diferencia
   abierta: el estado crudo solo no basta, porque el rótulo es lo que la gente lee.
2. El vocabulario de la conectada ya distingue **aceptada** de **conforme**, que es
   exactamente la distinción que la decisión 6 acaba de hacer necesaria en la combinada.
   Extenderla a la aislada la hace consistente en lugar de excepcional.

Con una condición: el cambio es de **presentación**. No debe tocar ningún `CheckStatus`, ni
ninguna regla de aceptación, ni ningún número. Si al aplicarlo se moviera un baseline o un
golden case, es señal de que algo se salió del ámbito y hay que parar.

## 4. Qué haría falta

1. Decidir entre opción 1 y opción 2.
2. Si es la 1: un único `status_label(status, open_tbds)` en el motor, del que dependan las
   tres tipologías; retirar `VOCABULARIO_ACEPTADA` del catálogo marcándola resuelta;
   actualizar memorias, UI y los tests que fijan cada vocabulario.
3. En ambos casos, dejar en el catálogo la tabla de equivalencias, para que un lector de un
   informe antiguo sepa traducir.

## 5. Impacto

**Resultados y baselines:** ninguno esperado. Es rotulado. Se comprobará con dry-run y diff
antes de tocar nada (`CLAUDE.md` §11).

**Riesgo real:** que un test de informe o un golden case fije el texto «ACEPTADA» y el
cambio lo mueva. Eso no sería un cambio de resultado, pero sí un cambio de contrato de
presentación que hay que revisar caso por caso.

---

# Resolución aplicada (2026-09-18)

**Decisión del usuario: vocabulario único.** (El mensaje lo numeró como «opción 2», pero
enumeró los cuatro rótulos y pidió eliminar la ambigüedad de «ACEPTADA» y unificar
«DESCARTADA/RECHAZADA», que es el contenido de la **opción 1** de este documento. Se
implementó lo descrito, no el número.)

## Qué quedó implementado

Fuente única: `engine/results/vocabulary.py`.

| Estado interno | Rótulo |
|---|---|
| PASS o INFO, sin pendiente abierto | **CONFORME** |
| PASS o INFO, con pendiente abierto | **NO VERIFICADA** |
| WARNING | **ACEPTADA CON OBSERVACIONES** |
| NO VERIFICADO | **NO VERIFICADA** |
| FAIL | **RECHAZADA** |

Desaparece «ACEPTADA» a secas, que era la palabra ambigua, y «DESCARTADA/RECHAZADA» se
unifica en RECHAZADA.

**Los tres productores de rótulo delegan** en esa fuente: `report_model.status_label`
(aislada), `connected_report.alternative_label` (conectada) y `discard_explainer`, que era
una tercera copia del mapa que nadie había advertido.

## Lo que NO cambió

La semántica interna, como pedía el encargo. `accepted` ≠ `not_verified` ≠
`accepted_and_compliant`: siguen siendo las mismas particiones, con los mismos criterios y
los mismos recuentos. La regla de aceptación sigue siendo `NO_FAIL` y el `CheckStatus`
sigue siendo lo que deciden los criterios.

Por eso la API entrega **las dos cosas por separado**: `status` es el `CheckStatus` crudo
—el que usan los criterios— y `status_label` es el rótulo. La UI no deriva ninguno.

`LEGACY_EQUIVALENCE` conserva la traducción con los rótulos anteriores, para que quien lea
un informe antiguo sepa interpretarlo (`CLAUDE.md` §16).

## Tests

`tests/test_status_vocabulary_pendiente8.py` (28 tests): el mapa exacto, que los tres
productores coinciden, que la palabra ambigua ya no existe, que un pendiente abierto
degrada CONFORME y nunca mejora un rótulo, que las particiones y los criterios no cambiaron,
y que el vocabulario no decide nada —el módulo no importa `AcceptanceRule` ni `discards`—.
