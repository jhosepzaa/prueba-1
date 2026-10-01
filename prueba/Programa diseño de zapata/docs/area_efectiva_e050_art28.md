# Método del área efectiva — E.050 art. 28

Fecha: 2026-09-19. Estado: **implementado, opcional y apagado por defecto.**
Decisión del usuario: «elige la opción que cumpla con la E.050 y que sea una opción
conservadora».

Motivación en [`tbd_conectada_c1_c4_c11_c12.md`](tbd_conectada_c1_c4_c11_c12.md) §C12 y en
[`auditoria_normativa_citas.md`](auditoria_normativa_citas.md) §5.

---

## 1. El hueco que cierra

Hasta aquí, una resultante fuera del núcleo central **descartaba la alternativa**. El motivo
era correcto —el campo lineal `q = P/A ± M·c/I` produciría tracciones, que E.060 §15.2.3 no
admite— pero la conclusión era incompleta: el motivo de descarte decía que haría falta «el
modelo EffectiveArea (E.050 Art.28), **no implementado en el MVP**».

No era un hueco normativo. E.050 art. 28.2-28.3 prescribe el método:

> «28.2. El ancho (B) o largo (L), se corrige por excentricidad reduciéndolo en dos veces la
> excentricidad para ubicar la carga en el centro de gravedad del "área efectiva = B'L'"»
>
> «28.3. El centro de gravedad del "área efectiva" coincide con la posición de la carga
> excéntrica y sigue el contorno más próximo de la base real con la mayor precisión posible.
> Su forma es rectangular, aún en el caso de cimentaciones circulares.»

La Figura 5 de la norma lo remite a NAVFAC DM 7: es el método del área efectiva de Meyerhof.
La fórmula ya estaba escrita en `engine/codes/peru/e050_soils.py`; lo que faltaba era
enchufarla.

## 2. Las dos decisiones, y por qué se resolvieron así

### 2.1 ¿Sustituye al núcleo central o lo extiende? · **Lo extiende**

El art. 28 **no releva de §15.2.3**. Los dos criterios conviven:

| | Qué rige | Por qué |
|---|---|---|
| Resultante **dentro** del núcleo | El **pico** de la distribución lineal, igual que antes | Es la presión de contacto real y el criterio más estricto de los dos |
| Resultante **fuera** del núcleo | E.050 art. 28: `q = Q/(B'·L')` | La lineal deja de ser válida |

La razón es aritmética y está comprobada en los tests. Con excentricidad en un solo eje,

```
q_área / pico_lineal = B² / ((B − 2e)·(B + 6e))
```

que es **menor que 1 en todo el núcleo** y vale exactamente **3/4 en su borde**, `e = B/6`.
Aplicar el art. 28 también dentro del núcleo haría el modelo **más permisivo que el actual
justo donde el actual es válido**, y elegir un modelo no puede convertir un FAIL en un PASS.

**Consecuencia comprobada:** activar la opción solo puede **añadir** geometrías que el núcleo
descartaba. Ninguna de las que ya pasaban cambia de resultado — hay un barrido de
excentricidades que lo verifica número a número.

### 2.2 ¿Contra qué `qadm` se compara? · **Contra el declarado, y sin poder afirmar cumplimiento**

Era el punto que quedó pendiente de su aprobación, y es donde está la conservación.

`qadm` lo declara el proyectista, y el Estudio de Mecánica de Suelos lo obtiene para la
zapata **real**, B×L. El art. 28 evalúa la capacidad sobre **B'×L'**, y la capacidad portante
de una zapata más estrecha no es la misma:

- en suelo **granular**, el término `0,5·γ·B'·Nγ` baja con `B'`: el `qadm` real del área
  efectiva sería **menor** que el declarado, y comparar contra el declarado sería
  **optimista**;
- en suelo **cohesivo** (φ = 0) la capacidad no depende de B, y si gobierna el **asentamiento**,
  un área menor asienta menos y el `qadm` sería **mayor**.

El motor no sabe cuál de los dos casos es el suyo, y `CLAUDE.md` §1 le prohíbe suponer
parámetros geotécnicos para averiguarlo. Se aplica entonces **la misma regla asimétrica que
el proyecto ya usa en la estabilidad con E.020 art. 20.1**, donde la fuerza estabilizante
también se calcula con una cota superior:

| | Estado | Por qué |
|---|---|---|
| `q > qadm` | **FAIL** | Válido a fortiori: con el `qadm` correcto del área efectiva incumpliría al menos tanto |
| `q ≤ qadm` | **NO VERIFICADO** | No puede afirmarse. La alternativa sobrevive al barrido —regla `NO_FAIL`— pero **nunca** llega a CONFORME |

El proyectista cierra la asimetría declarando que su `qadm` vale para las dimensiones
efectivas (`qadm_declared_for_effective_area`). Entonces, y solo entonces, el cumplimiento se
afirma. Es el mismo patrón de μ y de los factores de seguridad: el dato lo pone quien puede
ponerlo, y el motor nunca lo supone.

### 2.3 Lo que el modelo NO hace

- **No es la distribución real de contacto.** El pico de un bloque triangular con despegue es
  mayor que la presión uniforme del art. 28. El artículo plantea el área efectiva para la
  **capacidad portante**, y eso es lo que el modelo resuelve.
- **No afirma el punzonamiento con contacto parcial.** La flexión y el cortante ya usan
  el bloque triangular real (§6); el punzonamiento sigue obteniendo el alivio del suelo del
  campo lineal, y está medido que ahí el error va del lado inseguro. El motor lo declara y
  deja el resultado en NO VERIFICADO.
- **No cierra TBD-C12.** El `DESPEGUE` de la conectada es otra cosa: la presión bajo el
  CUERPO RÍGIDO formado por las dos zapatas y la viga, que no es un rectángulo y a la que el
  art. 28 no se aplica directamente. Lo que sí queda cerrado es el límite del núcleo central
  en la presión de contacto de cada zapata, en las tres tipologías.

## 3. Qué se implementó

| Pieza | Qué hace |
|---|---|
| `e050_soils.effective_area_from_eccentricity` | El núcleo del método: `B' = B − 2\|ex\|`, `L' = L − 2\|ey\|`. Única implementación. Con `strict=False` reporta un área no positiva en vez de reventar |
| `e050_soils.effective_area_meyerhof` | Envoltura por momentos (`e = M/Q`), la forma en que el art. 28.1 plantea el problema |
| `contact_pressure.EffectiveAreaModel` | El modelo de contacto. Se construye con la declaración del proyectista |
| `ContactPressureResult.B_eff_m` / `.L_eff_m` / `.qadm_declared_for_effective_area` | Diagnóstico congelado **solo cuando existe** (`OPTIONAL_WHEN_NONE_FIELDS`) |
| `.usable` / `.effective_area_governs` / `.compliance_can_be_affirmed` | Propiedades derivadas: no son campos, de modo que no añaden ni una clave al congelamiento |
| `mapping.contact_model_for` | **Único** sitio donde se elige el modelo. Los cinco endpoints pasan por él |
| `SoilInput.use_effective_area_e050_art28` y `.qadm_declared_for_effective_area` | Las dos declaraciones, apagadas por defecto |

`within_kern` **conserva su significado literal** —si la resultante cae en el núcleo— en los
dos modelos. Lo que cambió es que los solvers preguntan `usable`, que es la pregunta que
realmente hacían: «¿sirve este campo de presiones para juzgar el diseño?».

## 4. Impacto medido

- **Cero cambios en `numeros` y `estados`** de los dos baselines. El modelo por defecto no se
  tocó, y dentro del núcleo el nuevo devuelve lo mismo bit a bit.
- **50 claves de `referencias`** —24 de `baseline.json`, 26 de `baseline_connected.json`—,
  todas del mismo cambio: la prohibición de tracciones se citaba como «E.060 §15.2» y su
  sección exacta es **§15.2.3**. Es contrato blando y es una corrección de cita, la misma
  clase de cambio que el resto de la auditoría normativa.
- `reference_pre_5a_non_beam.json`: **sin tocar**. Sus dos claves de `contact_pressure` se
  añadieron a la dispensa de la auditoría de citas, que solo ampara contrato blando.
- **57 tests nuevos**: `tests/test_area_efectiva_e050_art28.py` y `tests/test_bloque_triangular_diseno.py`.
  **Mutación: 8 mutantes, 8 detectados** —aplicar el art. 28 dentro del núcleo, perder el
  factor 2, cruzar los ejes, afirmar cumplimiento sin declaración, dar por utilizable un área
  no positiva, no repartir sobre el área efectiva, y convertir el área efectiva en el modelo
  por defecto—.
- Suite completa: **1863 pasan, 2 se saltan, 0 fallan.** `tsc` limpio, build correcto.
- **Mutación del bloque triangular: 6 mutantes, 6 detectados.**

## 5. El motivo de descarte cambió de texto

El anterior decía «no implementado en el MVP», que ya no es cierto. El nuevo, que sigue
siendo una **categoría de texto global** (`CLAUDE.md` §5):

> «Excentricidad fuera del núcleo central: el modelo KernCheck (E.060 §15.2.3, solo
> compresiones) no es válido para esta combinación. El método del área efectiva de E.050
> art. 28 sí la resuelve: puede elegirse el modelo EffectiveArea.»

Y hay uno nuevo para el caso en que **ningún** modelo sirve —resultante fuera de la huella,
`B'` o `L'` no positivo—, que antes se confundía con el anterior.

## 6. El riesgo que apareció al implementarlo, y cómo quedó cerrado

**Al enchufar el modelo salió un problema que no estaba en el análisis previo.** Los
esfuerzos de diseño salen de `moment_at_critical_section`, que **recortaba a cero** las
presiones negativas del campo lineal:

```python
q_edge = max(q_edge, 0.0)
q_face = max(q_face, 0.0)
```

Esa distribución recortada **no equilibra la carga**: su resultante no vale Pu y no pasa
por el punto excéntrico. Y no era un problema del área efectiva: la excentricidad que
gobierna el DISEÑO se calcula con las cargas factorizadas y **sin peso propio**, y puede
salirse del núcleo aunque la de servicio no lo haga. **Cinco de los casos congelados de la
zapata aislada estaban en esa situación con el modelo por defecto.**

### Resuelto: bloque triangular real (opción B, aprobada)

`engine/foundation/flexure.py::NetPressureField` resuelve los dos regímenes por
equilibrio:

| | Campo | Comprobación |
|---|---|---|
| `e ≤ dim/6` | lineal clásico, `q'(0) = (Pu/dim)(1 + 6e/dim)` | resultante = Pu, brazo = dim/2 − e |
| `e > dim/6` | **triangular** sobre `a = 3·(dim/2 − e)`, con `q'(0) = 2Pu/a` | ídem |
| `e ≥ dim/2` | no existe: la resultante cae fuera de la huella | se declara imposible |

La flexión y el cortante unidireccional integran ese campo, truncándolo donde acaba el
contacto. Con contacto total se recupera `M = (c²/6)(2q_borde + q_cara)` término a término.

**Impacto medido**, 5 casos congelados, solo `numeros`, ningún estado ni descarte:

| Caso | Qué cambia |
|---|---|
| `13_descentrada_un_eje` | Mu 306,58 → **307,70**; Vu 275,13 → **276,25**. El diseño estaba **subestimado** |
| `15_descentrada_voladizo_largo_gobierna` | Mu 293,82 → **264,80** y el voladizo que gobierna pasa de 1,90 m a **0,80 m**: el largo cae en parte sobre la zona levantada |
| `16`, `17`, `18` | Ya descartados por presión de contacto. En el 18 el bloque comprimido mide 0,15 m y queda entero bajo la columna, de modo que Mu = 0: correcto, y antes valía 1146 kN·m de un campo que no existe |

El error iba **en las dos direcciones**, que es lo que se espera de una distribución que
no equilibraba: ni conservadora ni correcta.

### Cerrado el 2026-09-20: el punzonamiento integra el campo de contacto unilateral

El punzonamiento no integra un campo 1-D sino el alivio del suelo bajo el área crítica. Lo
obtenía de la **forma cerrada del campo lineal**,

```text
∫∫ q dA = q_avg · A_crit · (1 + 12·ex·a_x/B² + 12·ey·a_y/L²)
```

—la presión en el centroide del área encerrada, por su área—, que es exacta mientras la
distribución sea lineal, es decir **solo dentro del núcleo central**. Contrastado contra el
bloque triangular real, el alivio lineal salía **mayor** que el real y **Vu quedaba
subestimado**, hasta un **1,4 %**. Del lado inseguro: no bastaba con declararlo.

**Qué se implementó.** La demanda pasa a ser la integral del campo real sobre el área
crítica, sin ninguna simplificación adicional del alivio:

```text
Vu = Pu − ∫∫(A_crit) q⁺(x, y) dA
```

**El campo es el del CONTACTO UNILATERAL,** `engine/foundation/unilateral_contact.py`, y es
el **mismo** con que se calculan la flexión y el cortante unidireccional. No hay una segunda
representación del contacto de diseño:

```text
q⁺(x,y) = max(a + b·u + c·v, 0)          u = x/(B/2),  v = y/(L/2)

∫∫ q⁺ dA = Pu      ∫∫ x·q⁺ dA = Pu·ex      ∫∫ y·q⁺ dA = Pu·ey
```

El suelo no tracciona, y los tres coeficientes los fija el equilibrio. Con contacto total el
plano es el lineal clásico; con despegue en una sola dirección, el bloque triangular de
`NetPressureField`; con excentricidad biaxial y despegue se resuelve por Newton, cuyo
jacobiano resulta ser exactamente la matriz de Gram del polígono comprimido. Las integrales
son exactas: se recorta contra la zona comprimida y se evalúan los momentos del polígono en
forma cerrada.

**El camino hasta aquí, en un solo día.** Primero se integró el campo real en vez de la
forma cerrada; después se restringió la integral a la parte comprimida, `q > 0`; y
finalmente la decisión 1 del proyectista sustituyó la superposición de los dos campos 1-D
por el contacto unilateral completo. Los dos pasos intermedios están documentados con su
diff en [`freeze_punzonamiento_campo_real.md`](freeze_punzonamiento_campo_real.md) y
[`freeze_zona_contacto_y_proporcion.md`](freeze_zona_contacto_y_proporcion.md), los dos
marcados como superados.

**Por qué la superposición no bastaba, medido.** Es exacta con contacto total y con despegue
uniaxial, pero con excentricidad biaxial **no resuelve el contacto, solo lo describe**: su
parte positiva entregaba **1,61·Pu** en el régimen de `17_columna_de_esquina`, y daba allí un
alivio de 397,5 kN donde el exacto es 825,2.

**Un defecto que la integral destapó en la COMBINADA.** El alivio se calculaba con la carga
de la columna que se está verificando y su excentricidad respecto del centroide de la
zapata. Eso describe una zapata que no existe: bajo una zapata combinada el campo lo produce
la **resultante de todas las columnas**. En `K1` —dos columnas iguales y simétricas, sin
momento— el campo real es uniforme y el alivio vale exactamente 129,60 kN; el motor daba
174,14 kN, es decir un Vu subestimado. `punching_demand` separa ahora las dos cargas:
`P_u_column_kN`, la que punzona, y `field_P_u_kN`, la que produce el campo.

**El núcleo de un rectángulo es un ROMBO,** `|6·ex/B| + |6·ey/L| ≤ 1`, no el producto de los
dos sextos. Con cada excentricidad dentro de su sexto pero sumando más de uno ya hay tracción
en una esquina; lo destapó `14_descentrada_dos_ejes` (rombo 1,20, q_min = −23,58 kPa), que el
motor no estaba declarando.

**Ya no queda nada declarado por este concepto.** `punching_partial_contact` (2026-09-19) se
estrechó a `punching_biaxial_uplift` y finalmente **se retiró**: el campo equilibra por
construcción y no hay hueco que declarar. Una limitación se retira cuando se RESUELVE, no
cuando estorba. Lo único que queda es la imposibilidad geométrica —resultante fuera de la
huella—, que se declara con `ContactFieldImpossible`.

**Impacto en el congelamiento:** [`freeze_contacto_unilateral.md`](freeze_contacto_unilateral.md).
