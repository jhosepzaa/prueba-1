# TBD abiertos de la zapata conectada — análisis, impacto y opciones

Fecha: 2026-09-19. **No se cierra ninguno aquí.** `CLAUDE.md` §6: un TBD no se cierra
implícitamente con código. Lo que sigue es lo que hace falta para decidir: qué dice cada
fuente del proyecto, qué supone hoy el motor, en qué dirección puede equivocarse y qué
opciones hay.

Método: se releyó el texto de las cuatro fuentes buscando un criterio aplicable a cada
pendiente, no una justificación de lo ya implementado.

**Resultado que cambia la prioridad:** de los cuatro, **solo C1 y C4 son huecos
normativos**. C11 es una hipótesis sobre la superestructura, y **C12 no es un hueco
normativo en absoluto**: la norma prescribe el método y lo que falta es implementarlo.

| TBD | Naturaleza | ¿Bloqueado por la norma? | Puede producir |
|---|---|---|---|
| C1 | Hueco de criterio: la norma EXIGE evaluar la rigidez y no dice cómo | **Sí** | falso PASS |
| C4 | Modelo no implementado, sin criterio normativo que lo cubra | **Sí** | falso PASS de la zapata interior |
| C11 | Hipótesis sobre la superestructura, fuera del alcance del motor | No, pero no es comprobable aquí | falso alivio de la zapata interior |
| C12 | **Implementación.** E.050 art. 28 prescribe el método | **No** | descartes de más, nunca falso PASS |

---

## TBD-C1 — Rigidez de la viga y premisa de presión uniforme

### Qué supone el motor

Tres cosas encadenadas, y conviene no confundirlas:

1. la viga impide el **giro** de la zapata de lindero;
2. en consecuencia, la resultante del suelo pasa por el **centroide** de esa zapata;
3. en consecuencia, y por ser la zapata rígida, la presión es **uniforme**.

El motor calcula (2): entrega a la zapata el par que anula la excentricidad. (3) se sigue
de (2) más la hipótesis de zapata rígida, que es la misma de cualquier zapata aislada.
**Quien no tiene respaldo es (1).**

En el modelo `CUERPO_RIGIDO` la hipótesis no desaparece: cambia de forma —el conjunto gira
como un solo cuerpo— y sigue sin criterio.

### Qué dicen las fuentes

**E.060 §15.2.6 es el artículo que más cerca queda, y hasta esta auditoría no se citaba:**

> «En terrenos de baja capacidad portante o cimentaciones sobre pilotes, deberá analizarse
> la necesidad de conectar las zapatas mediante vigas, **evaluándose en el diseño el
> comportamiento de éstas de acuerdo a su rigidez y la del conjunto suelo-cimentación**.»

Es decir: **la pregunta es normativa**. La norma manda evaluar la rigidez. Lo que no da es
método ni umbral. La limitación del registro decía «Sin respaldo normativo», que era
inexacto y ya está corregido: lo que falta es el criterio, no la exigencia.

El resto:

- **§21.12.3.2** fija la dimensión transversal mínima de la viga (≥ luz libre/20, tope
  **450 mm** en la E.060 designada) y la separación de estribos. Es dimensional y el motor
  lo verifica con su propio PASS/FAIL. **No es una comprobación de rigidez**: cumplirlo no
  dice nada sobre si la viga impide el giro.
- **§15.10.3** exige que la distribución de presiones sea consistente con las propiedades
  del suelo y la estructura, pero está escrito para zapatas **combinadas y losas** —«zapatas
  que soporten más de una columna»—; la conectada son dos zapatas de una columna cada una.
- **E.050 art. 26.3**, sobre plateas, deja el espesor y los peraltes «determinados por el
  proyectista estructural, para garantizar la rigidez de la cimentación». Otra tipología,
  pero muestra cómo trata la norma este asunto: **delega, no tasa**.
- **h ≈ L/7** de los apuntes de Aragón es predimensionamiento profesional, nivel C. No puede
  producir PASS ni FAIL (`CLAUDE.md` §1).

### Impacto

Si la viga no fuera bastante rígida, la presión bajo la zapata de lindero dejaría de ser
uniforme, su `qmax` real superaría al calculado y el resultado dejaría de ser conservador.
**Puede producir un falso PASS**, y por eso la entrada mantiene todo el sistema fuera de
CONFORME. Hoy **ninguna** alternativa conectada alcanza CONFORME, y eso es correcto.

### Opciones

- **A. Dejarlo abierto** (lo actual). Honesto y conservador en la presentación, pero el
  programa nunca podrá pronunciarse sobre esta tipología.
- **B. Pedir el dato al proyectista.** Que declare, bajo su responsabilidad, que la viga
  satisface §15.2.6 —igual que hoy declara μ o el FS—. Pasaría de «el motor no puede
  demostrarlo» a «el proyectista lo afirma», con el mismo tratamiento que cualquier otro
  dato declarado: sin `open_tbd`, y el estado dejaría de estar atascado. **Es la opción que
  mejor encaja con lo que la norma hace** (delegar en el PR) y con el patrón que el
  programa ya usa. Requiere decidir el vocabulario: una alternativa así, ¿es CONFORME o
  ACEPTADA CON OBSERVACIONES?
- **C. Implementar viga sobre lecho elástico** (k_s del suelo) y resolver la interacción.
  Cierra la pregunta de verdad, pero exige `k_s`, que `CLAUDE.md` §1 prohíbe suponer, y es
  un motor nuevo.
- **D. Adoptar un umbral propio** (p. ej. una rigidez relativa viga/suelo). **Descartada:**
  sería fabricar un criterio normativo, que es exactamente lo que el proyecto prohíbe.

**Recomendación: B**, que no inventa nada y devuelve la decisión a quien la norma se la da.
Requiere su aprobación porque cambia el estado alcanzable de una tipología entera.

---

## TBD-C4 — Viga apoyada en el terreno (`APOYA_EN_SUELO`)

### Qué pasa hoy

`BeamSupportMode` es declaración obligatoria sin valor por defecto. Con `SIN_APOYO` el
reparto es el que el motor sabe resolver. Con **`APOYA_EN_SUELO` el motor NO modela la
reacción del terreno bajo la viga** y lo declara: la entrada queda NO VERIFICADO.

### Qué dicen las fuentes

Nada. §15.2.6 habla de conectar zapatas mediante vigas y de evaluar su comportamiento;
§21.12.3 las trata como acoples horizontales, a flexión y cortante. **Ninguna fuente del
proyecto dice si una viga de conexión puede considerarse apoyada en el terreno ni con qué
modelo repartir esa reacción.** No hay artículo que citar.

### Impacto — y en qué dirección

Ignorar la reacción del suelo **sobrestima ΔP**. Como la carga corregida de la zapata
interior es `P_int − ΔP`, la deja **menos cargada de lo que estaría en realidad**:

- zapata exterior: del lado seguro;
- zapata interior: **NO**. Puede ser un falso PASS.

Es una asimetría que hay que tener presente al decidir: el error no es conservador.

### Opciones

- **A. Dejarlo abierto** (lo actual), con NO VERIFICADO declarado y su limitación en el
  registro.
- **B. Rechazar el modo** `APOYA_EN_SUELO` por validación, como se hizo con
  `CUERPO_RIGIDO + PAR_PURO` (D1). Más honesto que devolver un resultado cuya zapata
  interior puede estar mal, pero le quita al usuario una opción que hoy al menos se traza.
- **C. Modelarla** como carga distribuida sobre la viga, con la presión del terreno bajo su
  huella. Exige decidir la distribución de esa presión —uniforme, lineal, sobre lecho
  elástico— y eso es la misma pregunta de C1 aplicada a la viga.

**Recomendación: A o B.** Entre las dos, B si se prefiere que el programa no entregue nunca
un resultado con un falso PASS posible en una zapata; A si se prefiere que el usuario pueda
verlo declarado. **No decido esto**: cambia qué entradas admite el programa.

---

## TBD-C11 — Destino de la rama cercana del par (`PAR_PURO_EN_ZAPATA`)

### Qué es

Cuando la viga reparte el par, una de sus dos ramas queda cerca de la zapata de lindero. El
modo lo declara el usuario:

- **`EQUILIBRIO_EN_CIMENTACION`**: la toma la propia zapata de lindero. El equilibrio
  vertical **cierra sobre la cimentación sola** y la suma de las cargas corregidas iguala la
  de las aplicadas. Es la lectura más exigente para esa zapata.
- **`PAR_PURO_EN_ZAPATA`**: la viga aplica a la zapata un **par puro** y la rama cercana se
  supone absorbida por la columna y el pórtico. Es el procedimiento de los apuntes
  CR2-93-134 §3.6.

Con `CUERPO_RIGIDO` la pregunta no se plantea —el conjunto es un cuerpo y cierra por
construcción— y `PAR_PURO` se rechaza por validación (D1).

### Qué dicen las fuentes

Nada, y **no es razonable esperar que digan algo**: es una pregunta sobre el reparto de
esfuerzos entre cimentación y superestructura, no sobre la cimentación. E.060 §15.2.1 pide
diseñar las zapatas «para resistir las cargas amplificadas y las reacciones inducidas», sin
arbitrar de dónde vienen.

### Impacto

Con `PAR_PURO_EN_ZAPATA`, la carga vertical **no se conserva dentro de la cimentación**:
faltan exactamente las toneladas de la rama del par, y la zapata interior queda **más
aliviada** que si la cimentación tuviera que equilibrarse sola. Que el pórtico recoja esa
rama es una hipótesis sobre la superestructura que este motor no comprueba y no puede
comprobar: no ve el pórtico.

El invariante de carga está declarado y verificado —`expected_residual_kN`, de modo que
`load_conservation_residual_kN = 0`—, así que el motor **sabe** cuánto falta y lo dice.

### Opciones

- **A. Dejarlo abierto** (lo actual). Es coherente: el motor no puede verificar una
  hipótesis sobre un elemento que no modela.
- **B. Exigir que el proyectista declare** que el pórtico toma esa rama, igual que en la
  opción B de C1. Convierte un hueco del motor en un dato del proyecto, sin `open_tbd`.
- **C. Retirar el modo.** Perdería el benchmark de Aragón P1, que se reproduce bit a bit
  con él. No parece buena idea.

**Recomendación: A**, o **B** si se adopta esa misma política para C1. No es un hueco que el
motor pueda cerrar por sí mismo bajo ninguna lectura.

---

## TBD-C12 — Contacto unilateral (despegue) · **NO es un hueco normativo**

### Qué pasa hoy

El campo lineal `σ = P/A ± M·y/I` supone que **toda la huella trabaja**. Cuando una parte se
levanta, la hipótesis deja de valer y las resultantes bajo cada zapata quedarían mal, no
solo la presión de un extremo. El motor detecta el despegue, **rechaza el candidato**
(`RejectionReason.DESPEGUE`) y la búsqueda continúa.

En la aislada y la combinada el mismo hueco aparece como `within_kern = False` → FAIL, con
el motivo que ya nombra la salida: «requeriría el modelo EffectiveArea (E.050 Art.28), no
implementado en el MVP».

### Qué dicen las fuentes — aquí está lo importante

**E.060 §15.2.3**, literal:

> «En el cálculo de las presiones de contacto entre las zapatas y el suelo solo se aceptará
> que ocurran compresiones sobre el suelo.»

**E.050 art. 28.2 y 28.3** dan el MÉTODO:

> «28.2. El ancho (B) o largo (L), se corrige por excentricidad reduciéndolo en dos veces la
> excentricidad para ubicar la carga en el centro de gravedad del "área efectiva = B'L'".»
>
> «28.3. El centro de gravedad del "área efectiva" coincide con la posición de la carga
> excéntrica y sigue el contorno más próximo de la base real […]. Su forma es rectangular,
> aún en el caso de cimentaciones circulares.»

La Figura 5 de E.050 lo remite a NAVFAC DM 7: es el método del área efectiva de Meyerhof.

**Conclusión: la norma prohíbe las tracciones Y prescribe cómo resolver la excentricidad
alta.** No falta criterio. Falta implementarlo.

### Qué hay ya construido

- `engine/codes/peru/e050_soils.py::effective_area_meyerhof` — **implementado**: `B' = B −
  2·e₂`, `L' = L − 2·e₁`, con su referencia a Art. 28.2-28.3.
- `engine/soil/contact_pressure.py::EffectiveAreaModel` — **esqueleto** que hoy lanza
  `NotImplementedError`. La arquitectura de modelos de contacto se construyó justamente para
  poder enchufarlo sin tocar el resto del motor.

### Impacto de NO tenerlo

Solo **descartes de más**: geometrías que la norma admite y que el programa rechaza. Nunca
un falso PASS —el rechazo es la posición conservadora—. Pero:

- `docs/formulacion_volteo_analisis.md` mostró tres casos congelados (16, 17, 18) que ya
  eran descartados por `contact_pressure`. Con el área efectiva podrían ser evaluables.
- En la conectada, `DESPEGUE` retira candidatos del barrido y el resultado no puede
  presentarse como exhaustivo.

### La decisión que hace falta (y es de implementación, no normativa)

Tres puntos, todos acotados:

1. **Qué significa `qmax` bajo el modelo de área efectiva.** Meyerhof da presión uniforme
   `q = Q/(B'·L')` sobre el área reducida, no una distribución lineal con un máximo en el
   borde. Comparar ese `q` contra `q_adm` es lo que el método supone.
2. **Con qué `q_adm` se compara.** El art. 28 pertenece al capítulo de capacidad de carga:
   `q_adm` debería corresponder a las dimensiones efectivas. Si el usuario declara un
   `q_adm` obtenido para `B × L`, usarlo con `B' × L'` es una aproximación que hay que
   declarar.
3. **Qué hace el diseño estructural.** La flexión y el punzonamiento se calculan hoy con el
   campo lineal. Con área efectiva hay que decidir de qué presión salen los momentos.

El punto 2 es el único con enjundia y **sí requiere su aprobación**, porque fija una
hipótesis. Los otros dos se siguen del método.

**Recomendación: es el pendiente de mayor valor que NO está bloqueado por la norma.** Cerrar
C12 por esta vía cierra a la vez la limitación del núcleo central en las tres tipologías.

### Qué se hizo el mismo día (2026-09-19)

`EffectiveAreaModel` quedó **implementado** como modelo opcional:
`docs/area_efectiva_e050_art28.md`. Con eso queda cerrada **la limitación del núcleo central
en la presión de contacto de cada zapata**, en las tres tipologías.

**TBD-C12 NO queda cerrado.** El `DESPEGUE` de la conectada es otra cosa: la presión bajo el
CUERPO RÍGIDO formado por las dos zapatas y la viga, que no es un rectángulo y a la que el
art. 28 no se aplica directamente. Sigue abierto, y ahora con una nota adicional: el método
del área efectiva es rectangular por definición («Su forma es rectangular, aún en el caso de
cimentaciones circulares», art. 28.3), de modo que extenderlo al cuerpo rígido exigiría una
decisión de modelación propia.

---

## Resumen para decidir

| | Requiere decisión suya | Qué desbloquea |
|---|---|---|
| **C12 / área efectiva** | Sí, pero solo sobre el `q_adm` a usar (punto 2) | Geometrías hoy descartadas en las tres tipologías; cierra `DESPEGUE` y el límite del núcleo central |
| **C1 opción B** | Sí: cambia el estado alcanzable de la conectada | Que una terna conectada pueda llegar a CONFORME |
| **C4** | Sí: A (dejar) o B (rechazar el modo) | Quita un posible falso PASS de la zapata interior |
| **C11** | Sí, si se adopta la política de C1 | Coherencia de vocabulario |

Ninguno se cierra en esta sesión. Lo que sí se corrigió es que **C1 ya cita §15.2.6** —el
artículo que exige la evaluación— en vez de decir «sin respaldo normativo», y que la
limitación de C12 cita el texto literal de §15.2.3 en lugar de una frase que no está en la
E.060 del proyecto.
