# Acta de FREEZE — 2026-09-20

Cierre formal de la etapa. Registra el estado congelado, la evidencia de cada comprobación
y lo que queda fuera de alcance de forma declarada.

Etapa anterior: `FORMULACION_VOLTEO` (2026-09-19, `freeze_formulacion_volteo.md`).

---

## 1. Qué se congela

Seis decisiones del proyectista, más las correcciones que aparecieron al implementarlas:

| # | Decisión | Documento |
|---|---|---|
| 1 | Contacto unilateral biaxial resuelto por equilibrio; **campo común** de punzonamiento, flexión y cortante | [`freeze_contacto_unilateral.md`](freeze_contacto_unilateral.md) §1 |
| 2 | `L/B ≤ 10` (E.050 art. 23.3), sin cambios | ídem §2 |
| 3 | `Df/B ≤ 5` (E.050 art. 23.1) → FAIL, en las tres tipologías | ídem §3 |
| 4 | TBD-C1: declaración del proyectista sobre §15.2.6 | ídem §4 |
| 5 | TBD-C4: `APOYA_EN_SUELO` rechazado por validación | ídem §5 |
| 6 | C-V: criterio de concreto solo, declarado como límite de alcance | ídem §6 |

Pasos intermedios del mismo día, conservados como historial y **marcados como superados**:
[`freeze_punzonamiento_campo_real.md`](freeze_punzonamiento_campo_real.md) y
[`freeze_zona_contacto_y_proporcion.md`](freeze_zona_contacto_y_proporcion.md).

---

## 2. Evidencia de cierre

| Comprobación | Resultado |
|---|---|
| `py -3 -m pytest -q` | **1966 passed, 2 skipped, 0 failed** |
| `py -3 -m pytest tests/freeze -q` | **220 passed, 2 skipped** |
| `npx tsc --noEmit -p .` | limpio (exit 0) |
| `npm run build` | correcto |
| diff de `baseline.json` contra el motor | 0 casos, 0 campos |
| diff de `baseline_connected.json` contra el motor | 0 casos, 0 campos |

### Hashes congelados

```text
baseline.json                   a05b59e4c2553bb602f46fa62f57f3aa69364c9ceb08cb1d8c08ddad91bc5253
baseline_connected.json         1e466340149e8166c5ec45c56bbcad31dee6de6edf411fc0a3a31aa8c28436af
reference_pre_5a_non_beam.json  1e3c1ebf2f8304cc546c195d5f6f56d1b5e3b567386318d26de9b95f604a8677
```

**`reference_pre_5a_non_beam.json` permanece INTACTA.** Su hash coincide con el registrado
desde la Fase 5A y su fecha de modificación sigue siendo **2026-09-15**. Las entradas nuevas
posteriores a 5A no la tocan: se enumeran en `ENTRADAS_NUEVAS_TRAS_5A`
(`zap_ext|zap_int/shape_ratio`, `zap_ext|zap_int/shallow_foundation`) y se filtran solo de
`traza.orden`, con un test que exige que cada una exista hoy y **no** existiera antes de 5A,
para que la lista no pueda convertirse en una puerta trasera.

---

## 3. El modelo retirado no deja referencias activas

`DesignPressureField2D`, `design_pressure_field_2d`, `integrate_contact_over_rectangle`,
`BIAXIAL_UPLIFT_PUNCHING_NOTE`, `punching_biaxial_uplift` y `punching_partial_contact`:

| Dónde | Resultado |
|---|---|
| `engine/` | ninguna |
| `api/` | ninguna |
| `ui/src/` | ninguna |
| `tests/` | solo como **guardia**: `test_la_limitacion_del_punzonamiento_se_retiro_al_resolverse` exige que `limitation_by_id` lance `KeyError` y que los ids no aparezcan en ninguna traza |
| `docs/` | solo en pasado o en documentos marcados como superados |

`docs/area_efectiva_e050_art28.md` §6 era el único documento **vivo** que describía el
modelo retirado en presente; se reescribió al modelo vigente conservando el historial del
camino recorrido.

---

## 4. C-V está descrito como alcance, no como implementación de Vc+Vs

`CONCRETE_ONLY_SHEAR_CRITERION` viaja en la traza de `shear_longitudinal` de los cuatro
casos combinados, y dice las seis cosas que la decisión 6 obliga a decir:

- se identifica como **criterio del programa**;
- **«NO ES UNA VERIFICACIÓN COMPLETA DEL MODELO DE CORTANTE DE E.060»**;
- nombra `Vn = Vc + Vs` como lo que la norma admite y el motor no hace;
- el aporte de estribos queda **FUERA DEL ALCANCE**;
- el criterio es **más estricto que la norma**: puede descartar geometrías que E.060
  admitiría con refuerzo, pero no puede aceptar ninguna que no cumpla;
- ampliarlo es una **decisión de ingeniería abierta**, no un pendiente de implementación.

Y no se presenta como prohibición normativa. `shear_reinforcement is None` en los cuatro
casos: el alcance declarado coincide con el código.

---

## 5. C1 es una declaración NO comprobada, y no basta por sí sola

La traza de la premisa dice literalmente **«EL MOTOR NO LO HA COMPROBADO»** y **«no
convierte el resultado en conforme»**, cita §15.2.6, y con la declaración queda en **INFO**
—no en PASS— con `open_tbd = None`.

Comprobado sobre las doce ternas congeladas que no esperan rechazo:

| Con la declaración | Ternas | Rótulo |
|---|---|---|
| Todo lo demás PASS/INFO, sin otro TBD | Z1, Z1b, Z5, Z6, Z13 | **CONFORME** |
| Otro TBD abierto (C11) o alguna verificación sin demostrar | Z2, Z3, Z8, Z15 | NO VERIFICADA |
| Alguna verificación en FAIL | Z11, Z12, Z14 | RECHAZADA |

La primera fila es lo que la decisión autoriza explícitamente —«las verificaciones restantes
deben estar PASS»—; las otras dos son lo que impide leerla de más. Auditadas Z1 y Z1b entrada
por entrada: **ninguna** entrada fuera de PASS/INFO y **ningún** `open_tbd`, de modo que
llegan a CONFORME porque todo lo demás pasa, no porque algo se saltara. En `Z1b` el FS de
volcamiento no declarado lo cubre el adoptado del programa (D10-2b), con la referencia
normativa en la traza.

Queda fijado en `test_el_rotulo_CONFORME_exige_la_declaracion_Y_todo_lo_demas`, que clava
las tres filas.

**Efecto secundario registrado:** `CLAUDE.md` §5 decía que CONFORME estaba «hoy vacío en
conectada por TBD-C1». Desde esta etapa deja de estarlo, y §5 se actualizó.

---

## 6. Mutaciones deliberadas

Once, todas detectadas: 8 / 2 / 10 / 24 / 16 / 17 / 11 / 13 / 11 / 12 / 10 tests caen.
Detalle en [`freeze_contacto_unilateral.md`](freeze_contacto_unilateral.md) §11.

---

## 7. Lo que queda FUERA DE ALCANCE, declarado

No son pendientes ambiguos: son límites escritos, con su motivo y lo que haría falta para
levantarlos.

| Límite | Qué haría falta |
|---|---|
| `Vn = Vc + Vs` en la combinada | Ramas y separación transversal, alcance de §11.12.3, sección crítica de §15.5.2 |
| Viga de conexión apoyada en el terreno | Modelo resistente de la viga sobre el terreno y transferencia de acciones viga–suelo–zapatas |
| Contacto unilateral en la CONECTADA (TBD-C12) | Ahí lo que despega es una zapata entera, no parte de una huella: es otro problema |
| TBD-C11 · destino de la rama del par | El motor no ve el pórtico y no puede comprobar que recoja la rama |
| Rigidez de §15.2.6 (TBD-C1) | Ninguna fuente da método ni umbral; la responde el proyectista |
