# Diff de baselines por D10-2b

Fecha: 2026-09-18. Estado: **aprobado por el usuario y ejecutado.** Verificación en §7.

`CLAUDE.md` §4 y §11: «implementa X» no autoriza a tocar baselines. Este documento es el
diff por caso que se revisó ANTES de autorizar la regeneración dirigida, y la verificación
de lo que quedó después.

---

## 1. Qué cambió y por qué

Solo el **factor de seguridad exigido**, por la decisión D10-2b: el proyecto adopta 1,50 al
volteo —también con sismo— y 1,50 al deslizamiento. Antes el motor exigía el valor
normativo: 1,25 al deslizamiento (E.020 art. 22.1) y 1,20 al volteo sísmico (E.030 art.
64.2). El volteo sin sismo ya era 1,50 y no se mueve.

**No cambió ninguna otra magnitud**: ni presiones, ni momentos, ni acero, ni punzonamiento,
ni el FS obtenido. Tampoco cambió ningún **estado**: los tests de `estados` pasan enteros.

## 2. Contrato DURO (`numeros`) — 2 casos, 3 claves

| Caso | Clave | Antes | Después |
|---|---|---|---|
| `10_fuerzas_horizontales` | `stability.sliding.FS_required` | 1.25 | **1.5** |
| `11_sismica_con_horizontales` | `stability.sliding.FS_required` | 1.25 | **1.5** |
| `11_sismica_con_horizontales` | `stability.overturning_x.FS_required` | 1.2 | **1.5** |

Son los dos únicos casos congelados que declaran fuerza horizontal (`_loads(Hx=…)` en
`tests/freeze/cases.py`); el 11 es además el único declarado sísmico. Ningún otro caso los
toca, y eso es exactamente lo que se esperaba.

El `FS_obtained` no se mueve en ninguno: la exigencia sube, el valor calculado es el mismo.
Los estados tampoco, porque ambos casos ya estaban NO VERIFICADOS por falta de μ.

## 3. Contrato BLANDO (`referencias`) — 12 casos, solo texto

La referencia normativa de cada verificación de estabilidad tenía que cambiar: **no puede
seguir atribuyendo 1,50 a un artículo que dice 1,25 o 1,20.**

| Antes | Después |
|---|---|
| `… E.020 art. 21 (FS >= 1,50)` | `… FS 1,50: criterio del programa (D10-2b), coincide con E.020 art. 21` |
| `… E.030 art. 64.2 (FS >= 1,20 por volteo sísmico)` | `… FS 1,50: criterio del programa (D10-2b), más estricto que E.030 art. 64.2 (1,20 por volteo sísmico)` |
| `E.050 art. 17.1; E.020 art. 22.1 (FS) y art. 22.2 (μ del proyectista)` | `E.050 art. 17.1; E.020 art. 22.2 (μ del proyectista); FS 1,50: criterio del programa (D10-2b), más estricto que E.020 art. 22.1 (1,25)` |

**Casos afectados (12).** Aislada: `02`, `03`, `04`, `09`, `10`, `11`, `13`, `14`, `15`,
`18`, `S2`. Conectada: `Z1b_articulado_sin_FS_de_volcamiento`, el único cuyo FS no lo
declara el proyectista.

Los casos conectados que **sí** declaran FS (Z1, Z2, Z3, Z5–Z8, Z11–Z15) **no cambian**:
su referencia sigue diciendo «FS adoptado por el proyectista», y se comprobó que ese texto
no se tocara para no producir churn gratuito.

## 4. Invariantes que se mantienen

1. Ningún `estados` cambia: los 225 tests de estado pasan.
2. Ningún `FS_obtained` cambia: la exigencia sube, el cálculo es el mismo.
3. Ningún número fuera de `FS_required` cambia.
4. `Z1b` sigue distinguiéndose de `Z1`: uno cita el criterio del programa y el otro «FS
   adoptado por el proyectista». Era el propósito del caso y se conserva.
5. `reference_pre_5a_non_beam.json` **no se toca**: se comprobó que la redacción «FS
   adoptado por el proyectista» no cambiara, que era lo único que lo afectaba.

## 5. Lo que NO produjo cambios de baseline

- **Pendiente 7** (estabilidad de la combinada): los casos K1–K4 no declaran fuerza
  horizontal, así que `stability` es None y, declarado en `OPTIONAL_WHEN_NONE_FIELDS`, no
  añade ninguna clave.
- **Pendiente 8** (vocabulario): es rotulado; no entra en las instantáneas.
- **Decisión 6** y **pendiente 1**: verificados antes, sin cambios.

## 6. Qué haría falta para cerrarlo

Aprobación explícita y luego regeneración **dirigida**:

```bash
FREEZE_REGEN=1 py -3 -m pytest tests/freeze -q
```

Y verificación del antes/después: solo las 3 claves numéricas de §2 y los textos de §3.
Si apareciera cualquier otra diferencia, hay que detenerse (`CLAUDE.md` §11).

---

## 7. Regeneración ejecutada y verificada (2026-09-18)

`FREEZE_REGEN=1 py -3 -m pytest tests/freeze -q` → 227 pasan.

Comparación antes/después de los tres archivos, clave por clave, contra la copia previa:

| Archivo | `numeros` (duro) | `estados` (duro) | `referencias` (blando) | otros |
|---|---|---|---|---|
| `baseline.json` | **3** | 0 | 17 claves en 11 casos | 0 |
| `baseline_connected.json` | 0 | 0 | 1 (Z1b) | 0 |
| `reference_pre_5a_non_beam.json` | — | — | — | **archivo idéntico** |

Las 3 claves numéricas son exactamente las de §2. Las 17 claves de referencia son las de
§3: varios casos tienen a la vez `overturning_x` y `overturning_y`, por eso hay más claves
que casos. **Ninguna diferencia fuera de lo aprobado.**

Hashes nuevos: `baseline.json` `c816993bde09…`, `baseline_connected.json` `989ae11fe5ce…`.
`reference_pre_5a_non_beam.json` conserva `1e3c1ebf2f83…`.

La reducción sísmica de la combinada, implementada después, **no movió ningún baseline**:
K1–K4 están en modo directo y la reducción no puede aplicárseles.
