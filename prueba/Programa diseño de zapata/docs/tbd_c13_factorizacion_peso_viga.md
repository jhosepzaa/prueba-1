# TBD-C13 — Factorización del peso propio explícito de la viga en combinaciones factorizadas

Estado: **CERRADO (2026-09-18, decisión A′).** Modo por casos desde la Fase 10B; modo
directo con el factor declarado por el proyectista. Ver la sección final. Es independiente de 9a/9c: no depende
de cómo se calcula el peso de la viga, solo de qué factor recibe en las combinaciones
factorizadas.

## Qué ocurre hoy

Con `beam_self_weight_mode = EXPLICITO`, el reparto introduce el peso de la viga
(`beam_self_weight_kN`) con **el mismo valor en todas las combinaciones**, de servicio y
factorizadas. No se le aplica ningún factor de carga. Ya ocurría antes de 9a con el peso
sobre [L1, s_corte]. 9a cambió cuánto pesa la viga, no cómo se factoriza.

Ejemplo, caso congelado Z8 con HV-1:

| Combinación | P_ext | P_int | Peso de la viga |
|---|---|---|---|
| S1 (servicio) | 850 | 1100 | 33,2325 kN |
| U1 (factorizada) | 1190 | 1540 | 33,2325 kN (sin factor) |

## Por qué no se aplica ningún factor

El motor recibe cada combinación factorizada como `P` y `M` **ya combinadas por el
usuario**. No sabe qué parte es carga muerta, viva o de sismo, ni con qué factores se
formó la combinación. Por eso no puede inferir el factor que correspondería al peso
propio de la viga. Elegir uno sería inventar un criterio, y el proyecto no lo admite.

## Consecuencia

En las combinaciones factorizadas el peso de la viga entra sin amplificar. Eso **puede
subestimar**:

- las cargas corregidas de las dos zapatas (`P_ext_corrected_kN` y `P_int_corrected_kN`
  en las combinaciones factorizadas), y a través de ellas punzonamiento, cortante y
  flexión de ambas;
- los esfuerzos de diseño de la viga (Mu, Vu).

En las combinaciones de servicio el peso sin factor es el valor que corresponde: el
pendiente solo afecta a las factorizadas.

**Nota añadida en el análisis del contrato de cargas** (`docs/analisis_contrato_cargas.md`).
Según las ecuaciones de E.060 §9.2 recogidas en `docs/manual_usuario.html` —documentación
propia, pendiente de contraste con el texto primario—, el factor de la carga muerta
**cambia entre combinaciones** (1,4; 1,25; 0,9). En una combinación con 0,9 CM, dejar el
peso de la viga sin factor lo **sobrestima**, lo que es desfavorable para despegue,
volcamiento y tracciones. La consecuencia no es solo «puede subestimar»: el sentido del
error depende de la combinación. Por eso no hay un factor único que el motor pueda
aplicar.

**Este pendiente NO degrada todavía el estado de ninguna verificación.**

## Dónde queda documentado

| Lugar | Contenido | Campo |
|---|---|---|
| `engine/analysis/connected_statics.py` | constante `BEAM_SELF_WEIGHT_FACTORING_PENDING` y regla `factoring_pending_applies` | — |
| `CoupleDistribution.hypotheses` | el texto, solo en combinaciones FACTORIZADAS con peso de viga > 0 | prosa |
| Traza `sistema/beam_self_weight_mode` | el texto, solo con EXPLICITO y al menos una combinación factorizada | `hypotheses`, prosa |
| Este documento | descripción y opciones | — |

Solo cambia prosa. No hay marcador `open_tbd`, cambio de estado, motivo de descarte
(`discard_reasons`) ni entrada en `LIMITATION_REGISTRY`.

## Por qué todavía no está en el catálogo de limitaciones ni en el estado

El catálogo tiene un invariante (`test_toda_limitacion_que_puede_producir_falso_pass_esta_neutralizada`):
toda limitación capaz de producir un falso PASS debe nombrar la verificación que la
neutraliza. Este pendiente puede producir un falso PASS en las verificaciones
factorizadas. Registrarlo exige una de dos cosas:

- declararlo neutralizado por una entrada que degrade el estado, lo que **cambia
  resultados**; o
- declarar `can_cause_false_pass = False`, que sería **falso**.

Ninguna de las dos se hace sin decisión.

## Opciones para cerrarlo (requieren decisión)

| Opción | Qué implica | Qué cambiaría en el congelamiento |
|---|---|---|
| A. Factor declarado por el usuario, obligatorio con EXPLICITO y sin valor por defecto | Un dato nuevo, por ejemplo el factor del peso de la viga en combinaciones factorizadas | Números de las combinaciones factorizadas de todo caso EXPLICITO (hoy Z8 y Z15) |
| B. Composición de cargas por tipo (muerta, viva, sismo) con combinaciones generadas por el motor | Cambio de contrato de cargas mucho mayor | Todas las tipologías |
| C. Mantener sin factor y degradar a NO VERIFICADO con EXPLICITO y combinaciones factorizadas | Registro en `LIMITATION_REGISTRY` con `enforced_by` | Estados de todo caso EXPLICITO |
| D. Mantener sin factor y sin degradar | Situación actual; el invariante del catálogo impide registrarlo como limitación | Nada |

## Efecto de este cambio documental

- **Resultados:** ninguno. Solo se añaden textos a campos de prosa.
- **Instantáneas:** `hypotheses` está en `PROSE_FIELDS` de `tests/freeze/snapshot.py`,
  así que no se congela. Las 19 instantáneas conectadas (16 ternas, 3 de ellas negativas
  del motor, y 3 barridos) se compararon enteras antes y después de este cambio: idénticas.

## Cierre parcial (Fase 10B, 2026-09-14)

Con el **modo de cargas por casos**, el peso propio EXPLICITO de la viga (ΔW_e, W_V, ΔW_i) se
multiplica por el factor de los casos CM de cada combinación (E.020 art. 2: el peso propio es
carga muerta). Si la combinación no tiene CM, el factor es 0. Si las dos columnas declaran
factores de CM distintos en la misma combinación, es error de entrada.

- `BeamSelfWeightBreakdown.load_factor` registra el factor aplicado; `None` en modo directo.
- La hipótesis de TBD-C13 solo se emite cuando `load_factor is None`.
- **En el modo directo el TBD sigue abierto**, con la opción D de la tabla anterior.
- Es la opción B de la tabla, con combinaciones declaradas por el usuario en vez de generadas.

Ningún caso congelado usa el modo por casos: este cierre no altera los baselines.

---

# Modo directo — análisis y decisión pendiente (2026-09-18)

## 1. Por qué el modo por casos no lo resuelve todo

Desde la Fase 10B, en **modo por casos** el peso de la viga recibe el factor de los casos CM
de cada combinación, declarado por el usuario: el pendiente está cerrado ahí. En **modo
directo** el motor recibe `P` y `M` ya combinados y no puede inferir con qué factor de carga
muerta se formaron. No es una laguna que el motor pueda tapar calculando mejor: es
información que no está en la entrada.

Y el sentido del error no es único. Según E.060 §9.2 el factor de CM cambia entre
combinaciones (1,4; 1,25; 0,9): dejar el peso sin factor lo **subestima** frente a 1,4 y lo
**sobrestima** frente a 0,9, que es lo desfavorable para despegue y volcamiento. Por eso no
hay un valor por defecto defendible.

## 2. Lo que hace hoy el motor

`connected_solver` añade el texto del pendiente a `hypotheses` de la entrada
`sistema/beam_self_weight_mode`, **deliberadamente fuera de `motivos_pp`**, que es la lista
que decide el estado:

```python
status = CheckStatus.NOT_VERIFIED if motivos_pp else CheckStatus.INFO
```

De modo que el pendiente **no degrada nada**. Es la opción D de la tabla anterior.

## 3. Impacto real de cerrarlo, medido

La tabla de opciones original decía que degradar cambiaría «estados de todo caso
EXPLICITO». **Esa estimación quedó obsoleta.** Los dos casos congelados con peso EXPLICITO,
Z8 y Z15, tienen `fill_over_span = True`, así que su entrada `beam_self_weight_mode` **ya
está en NO VERIFICADO** por la limitación `connected_beam_fill_over_span`.

Consecuencia medida sobre los baselines vigentes:

| Qué | Cambia |
|---|---|
| `estados` de Z8 y Z15 | **No.** La entrada ya es NO VERIFICADO |
| `open_tbd` de la entrada | **No**, si se mantiene el criterio ya adoptado para esa entrada: «NO VERIFICADO sin `open_tbd`: no falta un criterio normativo, falta un dato». Es también lo que dice `CLAUDE.md` §6 de un dato de proyecto faltante |
| `numeros` | **No.** Ningún valor se mueve |
| `discard_reasons` | Es prosa (`PROSE_FIELDS`): no se congela |
| Aceptación y ranking | **No.** La conectada ya es NO VERIFICADA en bloque por TBD-C1 |

**Degradar cuesta cero cambios de baseline.** Lo único que cambia de comportamiento es un
sistema EXPLICITO en modo directo **sin** relleno sobre el vano: su entrada pasaría de INFO
a NO VERIFICADO. Hoy ese caso solo existe en
`tests/test_tbd_c13_beam_weight_factoring.py::test_el_pendiente_no_toca_estados_marcadores_ni_descartes`,
que es justamente el guardián puesto para que esta decisión no se tome en silencio.

## 4. Inconsistencia registrada

El pendiente **puede producir un falso PASS** en las verificaciones factorizadas y **no está
en `LIMITATION_REGISTRY`**. No se registró porque el invariante
`test_toda_limitacion_que_puede_producir_falso_pass_esta_neutralizada` exige que una
limitación así nombre la verificación que la neutraliza, y hoy no hay ninguna. El catálogo
de limitaciones es, por tanto, incompleto a sabiendas.

Existe el precedente exacto: `connected_beam_fill_over_span` es
`can_cause_false_pass=True` con `enforced_by="beam_self_weight_mode"`, y degrada esa misma
entrada.

## 5. Opciones para el modo directo

**A′ — Factor declarado por el proyectista, y sin él NO VERIFICADO (recomendada).**
Un dato de entrada opcional: el factor de carga muerta que aplicar al peso propio de la viga
en las combinaciones factorizadas del modo directo.

- Declarado → se aplica, queda trazado y la entrada no se degrada por C13.
- No declarado → la entrada queda **NO VERIFICADO**, y la limitación se registra con
  `enforced_by="beam_self_weight_mode"`.

Es exactamente la forma que el proyecto ya usa para **μ** (E.020 art. 22.2): dato del
proyectista, y sin él NO VERIFICADO, nunca un valor supuesto. No inventa ningún factor, da
una salida al usuario que no quiere migrar al modo por casos y cierra la inconsistencia del
catálogo.

**C — Degradar y nada más.** Igual que A′ pero sin la entrada nueva: la única salida sería
migrar al modo por casos. Más simple; deja al usuario de modo directo sin recurso.

**D — Dejarlo como está.** Cero trabajo y cero riesgo de regresión, pero el catálogo de
limitaciones sigue incompleto a sabiendas y un sistema EXPLICITO en modo directo sigue
pudiendo salir sin que nada advierta del pendiente en el estado.

**B — Generar las combinaciones en el motor.** Descartada: cambia el contrato de cargas de
las tres tipologías y el proyecto ya decidió que las combinaciones las declara el usuario.

## 6. Recomendación

**A′.** Coste bajo, impacto de baseline nulo y cierra la inconsistencia del catálogo. Si se
prefiere no añadir entradas, **C** es la variante honesta; **D** mantiene un hueco conocido.

## 7. Qué necesito del usuario

1. Elegir **A′**, **C** o **D**.
2. Con A′: confirmar que el factor es un **dato declarado sin valor por defecto** y que su
   ausencia deja NO VERIFICADO —no un 1,4 supuesto—.
3. Confirmar que la entrada sigue **sin `open_tbd`**, por coherencia con el criterio ya
   adoptado para `beam_self_weight_mode` y con `CLAUDE.md` §6.

---

# Resolución aplicada — decisión A′ (2026-09-18)

**Aprobada por el usuario.** El factor de carga muerta del peso propio de la viga en las
combinaciones FACTORIZADAS del modo directo es un **dato del proyectista**, sin valor por
defecto. Es la misma forma que el proyecto ya usa para **μ** (E.020 art. 22.2) y para los
FS: dato declarado, y sin él NO VERIFICADO, nunca un valor supuesto.

## Qué quedó implementado

| Pieza | Qué hace |
|---|---|
| `ConnectingBeamSpec.self_weight_dead_load_factor` | El dato. `default=None`, `ge=0`. Solo se admite con peso propio EXPLICITO, igual que z_b |
| `connected_statics.factored_beam_weight(..., direct_dead_load_factor)` | En modo directo aplica el factor a las combinaciones **FACTORIZADAS**; las de SERVICIO llevan el peso real (factor 1,0). En modo por casos no cambia: sigue mandando la composición |
| `connected_solver` | Sin el dato: `BEAM_SELF_WEIGHT_FACTORING_PENDING` y un **motivo**, que degrada `beam_self_weight_mode` a **NO VERIFICADO**. Con el dato: `BEAM_SELF_WEIGHT_FACTOR_DECLARED` con el valor aplicado |
| `LIMITATION_REGISTRY` | `connected_beam_weight_factoring`, `can_cause_false_pass=True`, `enforced_by="beam_self_weight_mode"` |
| API y UI | Campo aditivo `self_weight_dead_load_factor`, adimensional (no pasa por conversión de unidades), con su casilla en el panel de la conectada |

**Sin `open_tbd`.** Falta un dato del proyectista, no un criterio normativo que el motor no
tenga: `CLAUDE.md` §6 lo distingue expresamente, y la entrada `beam_self_weight_mode` ya
seguía ese criterio para sus otros dos motivos.

## Lo que cierra

El catálogo de limitaciones **ya no tiene el hueco conocido**. Antes, C13 podía producir un
falso PASS en las verificaciones factorizadas y no estaba registrado, porque el invariante
`test_toda_limitacion_que_puede_producir_falso_pass_esta_neutralizada` exige nombrar la
verificación que lo neutraliza y no había ninguna. Ahora la hay.

## Baselines

**Sin cambios.** Comprobado antes y después: `tests/freeze` 225 pasan y 2 se omiten, con los
hashes intactos. Dos razones:

1. Z8 y Z15, los dos casos congelados con peso EXPLICITO, tienen `fill_over_span = True`, de
   modo que su entrada `beam_self_weight_mode` **ya estaba** en NO VERIFICADO;
2. ninguno declara el factor, así que `load_factor` sigue en None y, por estar en
   `OPTIONAL_WHEN_NONE_FIELDS`, no añade ninguna clave.

## Tests

`tests/test_tbd_c13_beam_weight_factoring.py`, reescrito (16 tests): sin el dato no se
factoriza y la entrada se degrada sin `open_tbd`; con el dato se aplica solo a las
factorizadas y el servicio conserva el peso real; el factor escala el desglose sin mover la
geometría, con 0,9 incluido —E.060 §9.2 lo admite, y reducir el peso es lo desfavorable para
despegue y volcamiento—; no hay valor por defecto; el dato no se admite sin EXPLICITO ni con
valor negativo; la limitación está registrada y neutralizada.

**Seis mutaciones deliberadas, seis detectadas:** suponer 1,4 por defecto, no degradar la
entrada, aplicar el factor también al servicio, ignorar el factor declarado, declarar que la
limitación no puede producir falso PASS y admitir el dato sin peso EXPLICITO.
