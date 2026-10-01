# Decisión 6 — criterio de aceptación de la zapata combinada

Fecha: 2026-09-18. Estado: **cerrada e implementada**. Aprobada por el usuario.

Diferencia conocida que resuelve: `ACEPTACION_COMBINADA`
(`engine/integration/typology_catalog.py`).

---

## 1. Qué se decidió

La zapata combinada acepta con criterio **`NO_FAIL`**: sobrevive al barrido toda geometría
cuyo estado no sea FAIL. Es la máquina de estados del proyecto (`CheckStatus.discards`,
`CLAUDE.md` §5) y la regla que ya usaban la zapata aislada y la conectada.

Hasta esta decisión la combinada exigía **`PASS_OR_INFO`**: un WARNING o un NO VERIFICADO
contaban como descarte.

**Esto no es una decisión normativa.** No se apoya en ningún artículo ni lo necesita: es el
criterio de la búsqueda, es decir, qué alternativas se conservan y se muestran. Ninguna
ecuación, hipótesis física, referencia normativa ni estado de verificación cambió.

## 2. Por qué

La asimetría no era de presentación. Desde la corrección **D4**, la zapata combinada con
fuerzas horizontales declara su estabilidad **NO VERIFICADA** —deslizamiento y volcamiento
no están implementados para esta tipología— y esa entrada **no depende del peralte**:
aparece en todas las geometrías por igual.

Combinado con `PASS_OR_INFO` el efecto era que, en cuanto había sismo o viento, el barrido
combinado descartaba **todas** las geometrías y devolvía cero alternativas. La tipología
quedaba inutilizable, y el motivo real —«el motor no sabe verificar esto»— llegaba al
usuario disfrazado de «no se encontró ninguna solución».

Medición sobre el barrido de referencia (L 6,0–7,6 m × B 3,0–4,4 m × h 0,30–0,90 m,
q_adm = 147,1 kPa, 260 geometrías):

| | sin H | con Hx = 120 kN/columna |
|---|---|---|
| geometrías en FAIL | 255 | 255 |
| geometrías sin FAIL | 5 (PASS) | 5 (NO VERIFICADO) |
| alternativas que devolvía el barrido | las mismas 5 | **ninguna** |

Las mismas cinco geometrías, los mismos números: solo cambiaba si se mostraban o no.

## 3. Qué cambia y qué no

**Cambia** qué alternativas sobreviven al barrido, y solo eso:

- una geometría NO VERIFICADA o con observaciones se **conserva con su estado** en lugar de
  descartarse;
- entra por tanto en la tabla comparativa, en el frente de Pareto y en el informe;
- los motivos de descarte agrupados (Fase 2) pasan a registrar **solo FAIL**, que es lo
  único que descarta.

**No cambia** ninguna de estas cosas:

- las ecuaciones, las hipótesis y las referencias normativas del solver;
- el estado de ninguna verificación ni de ningún resultado: el solver es idéntico;
- el peralte elegido para cada planta (ver §5);
- ningún baseline congelado (ver §6).

### Aceptar no es aprobar

El conjunto separa explícitamente las tres cosas, igual que ya hacía la conectada
(`CombinedAlternativeSet`):

| Partición | Significado |
|---|---|
| `accepted` (alias de `valid`) | Ninguna verificación **implementada** la descarta. Nada más. |
| `accepted_and_compliant` | PASS o INFO: las únicas presentables como conformes. |
| `not_verified` | El motor no puede pronunciarse. Hoy, por la estabilidad no implementada (D4). |
| `accepted_with_findings` | Se pronuncia, y con reservas (WARNING). Hoy la combinada no produce ninguna. |

El campo del modelo sigue llamándose `valid` porque es contrato existente de la API, de los
informes y de los tests (`CLAUDE.md` §2: los cambios de contrato son aditivos). `accepted`
es su nombre honesto y es el que debe usarse al escribir código nuevo.

La combinada **no** lleva `open_tbds` por alternativa, a diferencia de la conectada: el
pendiente que la afecta se manifiesta como estado NO VERIFICADO de la propia alternativa,
de modo que el estado basta como criterio de conformidad.

## 4. Implementación

| Capa | Qué se hizo |
|---|---|
| `engine/optimization/combined_generator.py` | Criterio `if not r.overall_status.discards:`; particiones `accepted` / `not_verified` / `accepted_with_findings` / `accepted_and_compliant` y `status_summary()`; la nota de búsqueda pasa a advertir sobre lo **aceptado** que no es conforme, en vez de contar descartes no concluyentes. |
| `engine/integration/typology_catalog.py` | La combinada declara `NO_FAIL`. `KnownDifference` gana el campo `resolution` (aditivo): `ACEPTACION_COMBINADA` queda **resuelta, no borrada**. `VOCABULARIO_ACEPTADA` incorpora la combinada. |
| `engine/reports/combined_report.py` | Aviso destacado cuando la alternativa no es PASS ni INFO, con las verificaciones que impiden el pronunciamiento. Antes esa memoria era inalcanzable. |
| `api/schemas.py`, `api/server.py` | Campos **aditivos**: `accepted_count`, `status_summary`, `not_verified`, `accepted_with_findings`, `accepted_and_compliant`, sus tres recuentos y `can_claim_compliance`. Mismo desglose que la conectada. |
| `ui/` | Panel `EstadoAceptacion` con el desglose; avisa cuando ninguna aceptada puede presentarse como conforme. |

Defecto corregido de paso: el catálogo declaraba `explicacion_descartes: False` para la
combinada, que dejó de ser cierto con la Fase 2.

## 5. El riesgo que sí había, y por qué hoy no se materializa

`NO_FAIL` toma, para cada planta, el **primer peralte** que no está en FAIL. Si existiera
una verificación que diera WARNING o NO VERIFICADO en peraltes pequeños y PASS en peraltes
mayores, el criterio elegiría la alternativa superficial no demostrable y **ocultaría** la
profunda que sí cumple.

Hoy eso no puede ocurrir: la única entrada de la combinada capaz de degradar sin FAIL es
`stability_not_implemented`, que depende de la existencia de fuerza horizontal y **no** del
peralte. Verificado sobre las 260 geometrías del barrido de referencia: la lista de
alternativas aceptadas con H y sin H es idéntica, planta por planta y peralte por peralte.

Es una propiedad del estado actual del motor, no una garantía permanente. El test
`test_la_fuerza_horizontal_no_mueve_el_peralte_elegido` la fija, de modo que quien
introduzca una verificación con WARNING dependiente de h encuentre el problema.

## 6. Baselines

**Sin cambios.** Los casos congelados de la combinada (K1–K4) se resuelven con
`solve_combined_footing` sobre una geometría fija, no a través del barrido: el criterio de
aceptación no interviene. Comprobado: `tests/freeze` 225 pasan y 2 se omiten, con los
hashes de siempre.

## 7. Pendientes que esta decisión NO cierra

- **Pendiente 7 — estabilidad de la combinada.** Sigue sin implementarse. Esta decisión
  hace visible el NO VERIFICADO en lugar de esconderlo tras un barrido vacío; no lo
  resuelve. Es el siguiente paso natural.
- **Pendiente 8 — vocabulario común de estados.** `VOCABULARIO_ACEPTADA` sigue abierta y
  ahora alcanza a las tres tipologías: «aceptada» ya no significa lo mismo en la aislada
  que en la combinada o la conectada.
- **Esquema 2D de la combinada** (pendiente 1), única capacidad de presentación que le
  falta frente a las otras dos.

## 8. Tests

`tests/test_combined_acceptance_no_fail_d6.py` (17 tests) fija: la regla y su coherencia
con el catálogo, la equivalencia exacta sin fuerzas horizontales, el comportamiento nuevo
con ellas, que el FAIL sigue descartando, que las particiones son exactas y disjuntas, que
la memoria avisa y que la API transporta el desglose.

Mutaciones deliberadas detectadas: volver a `PASS_OR_INFO`, dar por conforme todo lo
aceptado, afirmar conformidad en la API, quitar el aviso de la memoria y callar la nota de
búsqueda.

Guardianes adaptados, conservando su propósito: `test_integration_typology_catalog.py`
(el catálogo no puede divergir del código), `test_combined_horizontal_forces_d4.py` (con H
nunca se llega a PASS) y `test_combined_discards_phase2.py` (una entrada NO VERIFICADA sin
texto se agrupa sin inventarle motivo).
