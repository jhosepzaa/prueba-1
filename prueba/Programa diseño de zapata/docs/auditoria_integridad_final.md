# Auditoría de integridad — invariantes transversales

Fecha: 2026-09-18. Estado: **tres hallazgos, los tres corregidos.** Sin cambios de baseline.

No audita ingeniería: audita el **andamiaje que hace auditable la ingeniería**. Son las
comprobaciones que, si fallan, dejan al usuario leyendo un resultado que el programa no puede
respaldar. Quedan fijadas en `tests/test_auditoria_integridad_final.py` (20 tests), que
recorre las trazas de **todos** los casos congelados de las tres tipologías.

---

## Hallazgo 1 — neutralizaciones nominales

**Evidencia.** `EngineLimitation.enforced_by` nombra la verificación que hace visible una
limitación capaz de producir un falso PASS. El invariante que ya existía
(`test_toda_limitacion_que_puede_producir_falso_pass_esta_neutralizada`) solo exigía que el
campo **no estuviera vacío**. Nadie comprobaba que el nombre correspondiera a una entrada de
traza real, y **tres no correspondían**:

| Limitación | Decía | Ids reales |
|---|---|---|
| `development_length` | `development` | `development_x`, `development_y` |
| `horizontal_forces`, `connected_footing_stability_composition` | `stability` | `sliding`, `overturning_x`, `overturning_y` |
| `connected_uplift_partial_contact` | `rigid_pressure` | `rigid_pressure_S1`, `rigid_pressure_U1`, … (una por combinación) |

**Severidad: media.** No cambia ningún número, pero la neutralización era **nominal**: el
catálogo afirmaba estar cubierto por verificaciones que, con ese nombre, no existían. Si
alguna de esas entradas se hubiera renombrado o retirado, nada lo habría delatado.

**Corrección.** `ENFORCED_BY_CHECKS` en `engine/results/limitations.py` expande cada grupo a
los ids de traza reales, con la convención de prefijo terminado en `_` que ya usa
`combined_discards.CATEGORY_BY_CHECK`. El contrato de la API no cambia: `enforced_by` sigue
siendo una cadena. Tres tests nuevos lo protegen: que cada patrón case con una entrada real,
que la tabla no tenga patrones muertos y que ningún `enforced_by` declarado se quede fuera de
la tabla.

## Hallazgo 2 — una verificación que degrada sin explicar por qué

**Evidencia.** `shear_x` y `shear_y` de la zapata aislada se emitían con
`hypotheses=[]` **codificado a mano**. Un FAIL de cortante llegaba a la traza sin ninguna
hipótesis: el usuario veía el ratio y la referencia, pero no de qué voladizo ni de qué lado
salía la demanda, que es lo que hace falta para reconstruirlo.

**Severidad: media.** No cambia ningún número. Rompe el objetivo del proyecto: un resultado
que no puede reconstruirse desde la traza.

**Corrección.** La entrada declara ahora la sección crítica a `d` de la cara, el voladizo de
diseño, el lado y la combinación gobernante —datos que el motor ya tenía en `demand_x` /
`demand_y`—, y que la resistencia es la del concreto solo. `hypotheses` es prosa
(`PROSE_FIELDS`): no entra en las instantáneas.

## Hallazgo 3 — el invariante que faltaba

Ninguna prueba exigía que **toda** entrada degradada explicara su estado. Ahora sí:
`test_una_entrada_degradada_explica_por_que` recorre las tres tipologías y falla si un
WARNING, un NO VERIFICADO o un FAIL llega sin hipótesis. Fue lo que destapó el hallazgo 2.

---

## Lo que la auditoría confirma que SÍ se cumple

Verificado sobre todos los casos congelados de las tres tipologías:

1. **`open_tbd` solo aparece en entradas NO VERIFICADAS**, siempre como cadena con forma
   `TBD-Cx` (`CLAUDE.md` §6).
2. **Toda entrada de traza está completa**: descripción, ecuación simbólica, sustitución,
   unidad, norma y referencia.
3. **La clave (scope, id) es única** en cada traza (`CLAUDE.md` §7).
4. **Ningún resultado conforme arrastra un pendiente abierto**, y el estado global es siempre
   el peor de sus entradas.
5. **Las tres tipologías comparten regla de aceptación (`NO_FAIL`) y vocabulario.**
6. **Toda diferencia del catálogo está documentada**: abierta con su decisión pendiente,
   cerrada con su resolución.
7. **La combinada verifica todo su alcance declarado** y, sin fuerza horizontal, no emite
   estabilidad —que es lo que mantiene K1–K4 intactos—.
8. **Las dos disposiciones de E.060 §15.2** —reducción del 80 % e incremento del 30 %— tienen
   **una sola implementación**, comprobado recorriendo `engine/`.
9. **El motor no inventa ningún parámetro geotécnico**: μ, cohesión y los dos FS tienen
   `default=None`, y un suelo sin ellos se construye igual —faltar un dato no es un error de
   entrada, es un NO VERIFICADO más adelante—.

## Mutaciones

Seis deliberadas, seis detectadas: volver a nombrar una verificación inexistente, dejar sin
neutralizar una limitación con falso PASS, devolver el cortante a `hypotheses=[]`, quitarle
la referencia normativa a una entrada, romper el vocabulario común y emitir estabilidad en la
combinada sin fuerza horizontal.

## Baselines

**Sin cambios.** Las dos correcciones tocan prosa (`hypotheses`) y una tabla interna que no
entra en las instantáneas.
