# Auditoría normativa — ¿existe lo que el motor cita?

Fecha: 2026-09-19. Fuentes: solo las de `docs/normativa/fuentes/`, a través de los
extractos de `docs/normativa/texto/` (`CLAUDE.md` §8).

`CLAUDE.md` §1: «No inventar artículos, coeficientes, ecuaciones, factores ni criterios
normativos.» Esta auditoría lo comprueba de dos maneras distintas, porque son dos fallos
distintos.

---

## 1. Designaciones citadas — comprobación mecánica

Se recorrieron **todas** las referencias que el motor publica —el `code_reference` de cada
entrada de traza de las cuatro tipologías, más el registro de limitaciones—, se extrajo cada
designación (artículo, sección o ecuación) y se buscó en el texto de su norma.

| Norma | Designaciones distintas | No localizadas |
|---|---|---|
| E.020 | 5 | 0 |
| E.030 | 3 | 0 |
| E.050 | 3 | 0 |
| E.060 | 54 | 0 |
| **Total** | **65** | **0** |

**Ninguna designación inventada.** Queda como test permanente en
`tests/test_auditoria_citas_normativas.py`, que además exige que solo se citen las cuatro
normas admitidas y que el volumen auditado no se desplome. Mutación: se cambió
`E.050 art. 26.2` por `art. 99.7` y por `E.060 art. 26.2`; las dos se detectaron.

**Lo que este test NO comprueba** es que el artículo diga lo que el motor afirma. Eso es
lectura, no búsqueda, y va aparte: `docs/normativa/contraste_e060_motor.md` (A1–A8, B1–B11)
y los documentos de fase.

## 2. Citas literales — comprobación una por una

Se extrajeron todos los textos entrecomillados con «» del motor y se buscaron en las
fuentes, normalizando acentos, espacios y los artefactos de extracción del PDF (las
ligaduras «ﬁ» que el extractor parte en «fi »).

De 63 citas, 18 no aparecían en ninguna fuente. La mayoría son **uso tipográfico propio**
—«sobrevive al barrido», «un residuo de 1e-13 no es demanda»— o **citas de los apuntes de
Aragón**, que son benchmark y no norma, y están declaradas como tales. Quedaron **cuatro
defectos reales**, todos corregidos:

### 2.1 §21.12.3.2 transcrito con el tope de la edición anterior

`engine/beam/connecting_beam.py` transcribía el artículo diciendo «no necesita ser mayor a
**400 mm**». La E.060 designada por el proyecto (propuesta 2019) dice **450 mm**.

**El código siempre usó 450** (`MIN_DIMENSION_CAP_M = 0.450`, con la nota de que la edición
anterior decía 400), de modo que ningún resultado estuvo afectado. Lo que estaba mal era la
transcripción que un lector creería. Corregida, con la nota del cambio de edición.

> Queda un residuo deliberado: el campo `BeamDimensionalCheck.capped_at_400mm` conserva su
> nombre. Es un booleano congelado en el baseline y renombrarlo movería claves de contrato
> por un motivo cosmético (`CLAUDE.md` §2). El valor que compara es el correcto.

### 2.2 Una frase entre comillas que no está en la E.060

`engine/results/limitations.py` citaba, para el despegue:

    code_reference="E.060 §15.2 — «no se deberán considerar las tracciones»"

Esa frase **no aparece en la E.060 del proyecto**. El texto real es §15.2.**3**:

> «En el cálculo de las presiones de contacto entre las zapatas y el suelo solo se aceptará
> que ocurran compresiones sobre el suelo.»

Dice lo mismo, pero presentarlo como cita literal de un número de sección impreciso es
exactamente lo que la regla prohíbe. Sustituido por el texto literal y la sección exacta.

### 2.3 E.030 art. 65.1 parafraseado entre comillas

`engine/foundation/connected_solver.py` decía que el artículo mide la fuerza axial sobre
«la carga vertical amplificada de la zapata conectada». El texto real es «las cargas
verticales amplificadas **que soporta la zapata**». La lectura adoptada —usar la carga
corregida de la zapata de lindero— **no cambia**: lo que cambia es que ahora se distingue
qué es cita y qué es interpretación, que es justo lo que `CLAUDE.md` §8 pide separar.

### 2.4 §15.10.3 citado en singular

«consistente con las propiedades del suelo y la estructura» → el texto dice «debe ser
**consistentes** con las propiedades del suelo y la estructura y con los principios
establecidos de mecánica de suelos». Corregido a la forma literal completa.

## 3. Hallazgo de fondo: el artículo que faltaba citar en TBD-C1

Buscando criterio para la rigidez de la viga de conexión apareció **E.060 §15.2.6**, que el
motor no citaba en ninguna parte:

> «En terrenos de baja capacidad portante o cimentaciones sobre pilotes, deberá analizarse
> la necesidad de conectar las zapatas mediante vigas, **evaluándose en el diseño el
> comportamiento de éstas de acuerdo a su rigidez y la del conjunto suelo-cimentación**.»

La limitación decía «**Sin respaldo normativo**» y la entrada de traza, «Sin artículo». Las
dos eran inexactas, y en la dirección que más importa: **la pregunta SÍ es normativa**. La
norma manda evaluar la rigidez. Lo que no existe es método ni umbral con que hacerlo, y por
eso el motor no puede cerrarlo.

Corregido en los tres sitios —la nota de la premisa, la entrada de traza y el registro de
limitaciones—, **sin cambiar ningún estado**: la premisa sigue en NO VERIFICADO y sigue
impidiendo que una terna conectada llegue a CONFORME.

`tests/test_connected_contract_phase4c.py::test_la_premisa_no_se_atribuye_a_ningun_articulo`
se reescribió para vigilar las dos direcciones a la vez: que se cite §15.2.6 —callarlo
ocultaba que la norma lo pide— y que en la misma frase se diga que no prescribe criterio,
para que no se lea como si la verificación estuviera respaldada.

**Impacto en baselines:** 13 casos de la conectada, **13 claves, todas de `referencias`**
—contrato blando— y ninguna de `numeros` ni de `estados`. Es el caso para el que el
contrato blando existe: «cambiar una cita puede ser una CORRECCIÓN legítima».

## 4. La referencia pre-5A, otra vez sin regenerar

`reference_pre_5a_non_beam.json` tampoco se toca por esto. Se añadió una **segunda dispensa
enumerada y separada** de la de `FORMULACION_VOLTEO`, con dos claves —la cita de
`uniform_pressure_premise` y la de `rigid_body_premise`— y un test que exige que esta
dispensa sea **solo de contrato blando**: una cita puede corregirse, un número o un estado
no. Las dos dispensas se vigilan además con el test que comprueba que ninguna se ha quedado
obsoleta.

## 5. Qué se buscó y no se encontró

Para que conste qué se descartó por ausencia de fuente, no por olvido:

- **Criterio de rigidez de la viga de conexión (TBD-C1):** no existe. §15.2.6 exige la
  evaluación; ni él ni §21.12.3.2 ni §15.10.3 dan método. E.050 art. 26.3, para plateas,
  **delega expresamente** el asunto en el proyectista estructural: es la política de la
  norma, no un olvido suyo.
- **Viga de conexión apoyada en el terreno (TBD-C4):** nada en las cuatro fuentes.
- **Destino de la rama del par (TBD-C11):** nada, y no cabe esperarlo: es reparto entre
  cimentación y superestructura.
- **Contacto unilateral (TBD-C12):** **sí hay método.** E.060 §15.2.3 prohíbe las tracciones
  y E.050 art. 28.2–28.3 prescribe el área efectiva `B' = B − 2e`, `L' = L − 2e`. No es un
  hueco normativo sino de implementación. Detalle en
  `docs/tbd_conectada_c1_c4_c11_c12.md`.
