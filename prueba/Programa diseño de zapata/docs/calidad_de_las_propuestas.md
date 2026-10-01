# Calidad de las propuestas: cinco silencios del barrido (2026-09-24)

Auditoría del motor centrada en **qué propuestas llega a ver**, no en qué verifica. Ninguno
de los hallazgos podía hacer que el motor ACEPTARA un diseño malo: todos hacían que dejara
de encontrar, o de mostrar, diseños buenos. Los cinco están resueltos; cada uno con la
medición que lo motivó.

---

## 1. El rango automático subestimaba el área necesaria

**Lo que hacía.** Cuando el proyectista no declara límites, el motor estimaba
`A ≈ P/q_adm`. Eso ignoraba dos cosas:

- con base **BRUTA**, el relleno y el concreto sobre la huella consumen capacidad antes de
  que la columna aporte nada;
- la **excentricidad**: el modelo de contacto por defecto exige la resultante dentro del
  núcleo central (E.060 §15.2.3), lo que pide un lado del orden de 6·e.

**Medición.** Columna de P = 600 kN y M = 900 kN·m (e = 1,50 m), q_adm 150 kPa bruta,
Df 1,50 m:

| | Rango explorado | Mejor propuesta |
|---|---|---|
| Antes | 1,10 – 4,40 m | 18,39 m³ |
| Después | 1,30 – 9,90 m | **13,16 m³** |
| Referencia manual amplia | 1,00 – 8,00 m, paso 0,2 | 12,56 m³ |

**Lo implementado.** `engine/foundation/auto_search_range.py`:

- la presión disponible se obtiene con `convert_pressure`, **la misma función que usa el
  verificador** para pasar de base bruta a neta: aquí no hay ninguna fórmula nueva;
- si el relleno se come toda la capacidad, se abre un rango amplio y se dice por qué, en
  lugar de dividir por un número sin sentido;
- el rango alcanza `6·e·1,10` cuando hay excentricidad de servicio;
- como el rango se ensancha, la heurística **también propone el incremento** (escala 0,05 →
  0,50 m, máximo 45 puntos por eje): con paso fino la malla llegaba a 7396 geometrías y el
  servidor rechazaba la petición por tamaño. El incremento propuesto solo se usa en los
  ejes cuyos límites son automáticos; si el proyectista declara los límites, manda su paso.

Sigue siendo una **heurística de búsqueda**: acota dónde mirar y no decide nada. Un rango
mal elegido solo puede impedir encontrar la mejor, nunca aceptar una mala.

## 2. Nadie avisaba cuando el óptimo caía en el borde del rango

En el caso de arriba, la mejor alternativa tenía B = L = 4,40 m, que era **exactamente el
máximo explorado**, y solo 5 de 892 geometrías resultaban válidas. Dos señales claras de
que la búsqueda se quedó contra la pared, y ninguna se comunicaba.

`engine/optimization/search_boundary.py`, **una sola implementación para las tres
tipologías**, comprueba si la geometría recomendada coincide con alguno de los límites de
su malla —tolerancia de medio incremento, porque el barrido solo produce valores de la
malla— y lo dice. También informa del límite INFERIOR: si la recomendada es la más pequeña
que se miró, puede haber algo más económico por debajo.

No cambia ningún número: ni descarta, ni acepta, ni altera un resultado.

## 3. Para cada planta solo existía el primer peralte que no falla

**El problema.** El barrido probaba peraltes crecientes y se detenía en el primero que no
daba FAIL. Un peralte mayor gasta más concreto pero puede necesitar menos acero: ninguno
domina al otro, son puntos distintos del compromiso. Al no generarlos, el «frente de
Pareto» que veía el proyectista **no era el frente**.

**Medición** (planta 3,60 × 3,60 m, P = 900 kN, M = 180 kN·m):

| | Frente de Pareto |
|---|---|
| Antes | 2 puntos: (6,48 m³, 230,6 kg) y (6,84 m³, 215,5 kg) |
| Después | 3 puntos: los dos anteriores más **(7,13 m³, 202,6 kg)** — misma planta, 5 cm más de peralte, 10 % más de concreto y 12 % menos de acero |

**Lo implementado.** Segunda pasada en `alternative_generator.generate_alternatives`:

- **solo sobre las alternativas del frente**. Refinarlas todas triplicaba el tiempo del
  barrido y llenaba la tabla de variantes de plantas ya dominadas: 2280 alternativas en vez
  de 894, con el mismo ganador. Sobre el frente cuesta 1,8 s de un barrido de 35 s;
- se prueban hasta `EXTRA_DEPTH_STEPS = 3` peraltes por encima del mínimo, y solo se
  conservan los que **bajan el acero** respecto de todos los ya guardados para esa planta.
  Como el concreto crece siempre con el peralte, esa es exactamente la condición de no
  dominancia sobre (concreto, acero);
- **parada demostrable, no por ahorro a ciegas**: `As_min = ρ_min·b·h` (E.060 §9.7) CRECE
  con el peralte. Si en las dos direcciones el acero ya lo gobierna el mínimo, un canto
  mayor solo puede pedir más acero y más concreto: está dominado con seguridad y no se
  evalúa.

**Limitación declarada.** La variante de peralte de una planta *dominada* podría, en
teoría, pertenecer al frente real, y ahí no se busca. Es estrategia de búsqueda, como el
rango automático, y se declara en lugar de disimularse.

**Corrección de una afirmación previa.** En la auditoría se citó como ejemplo la planta
4,20 × 4,20 m (8,82 m³/315,8 kg frente a 9,70 m³/278,9 kg). Comprobado después: esa
variante está **dominada por otras 14 alternativas** —era mejor solo dentro de su propia
planta, no en el conjunto—. El fenómeno es real y el frente sí crece, pero con el ejemplo
correcto, que es el de la tabla de arriba.

**Contrato.** Una planta puede aportar ahora varias alternativas, de modo que
`n_evaluated` (plantas) y `n_valid` (alternativas) ya no coinciden. El recuento de plantas
se lleva explícito en `AlternativeSet.geometries_evaluated`.

## 4. La poda por relación L/B era invisible

Las geometrías con `L/B > max_LB_ratio` **no se generan**, así que tampoco aparecían entre
las descartadas: no quedaba ni rastro de que existieran. En una malla de 1 a 6 m con paso
0,5 m, el valor por omisión (2,0) deja fuera **40 de 121** geometrías.

Ahora se cuentan (`pruned_by_LB_ratio`) y se explican: cuántas son, que no figuran entre
las descartadas porque no llegaron a generarse, y que el límite es criterio del programa
—E.050 art. 23.3 admite hasta L/B = 10 antes de considerar el elemento una cimentación
continua—.

**El valor por omisión NO se cambia.** Subirlo amplía el espacio de búsqueda y puede
cambiar cuál es la mejor alternativa: es una decisión del proyectista, no una optimización.

## 5. La longitud de centrado de la combinada usaba la primera combinación

`length_to_center_resultant` se llamaba con `service[0]`, la primera de la lista, fuera
cual fuera. Con gravedad y sismo declarados, la longitud sugerida podía corresponder a un
estado que no gobierna.

**La decisión tomada, y por qué.** Se elige la primera combinación de servicio **sin sismo
ni viento**, y se dice cuál es. Centrar la resultante es un criterio de estado
**permanente**: el sismo se invierte —en el caso de Aragón CR2 §3.5, S2 y S3 mueven la
resultante en sentidos opuestos— de modo que centrar para uno descentra el otro y empeora
el estado que sí es permanente. Tomar «la más exigente» daba 8,23 m frente a los 7,20 m del
libro, y habría sido centrar un estado transitorio.

Además se informa de **la dispersión**: entre qué valores se mueve la longitud de centrado
con todas las combinaciones declaradas. Si ninguna es puramente gravitatoria, se avisa de
que la longitud mostrada centra un estado transitorio.

Sigue siendo predimensionamiento: ni E.060 ni E.050 obligan a centrar la resultante, y lo
que sí exigen se verifica después para todas las combinaciones.

---

## Verificación

- `tests/test_aviso_borde_rango.py` (10), `tests/test_peraltes_no_dominados.py` (7),
  `tests/test_rango_automatico_excentricidad.py` (8),
  `tests/test_poda_visible_y_centrado.py` (8).
- Suite completa **en verde, congelamiento incluido y sin tocar ningún baseline**: los
  casos congelados fijan `solve_depth` con B, L y peraltes explícitos, no el generador ni
  la heurística.
- Un test tuvo que reenfocarse: comprobaba que el rango AUTOMÁTICO disparaba el aviso de
  borde, y tras corregir la heurística ya no lo dispara —porque el rango dejó de quedarse
  corto—. Ahora usa un rango estrecho declarado a mano, que es la situación que seguirá
  dándose.
- `tests/test_api_units_and_ranges.py` verificaba la nota del rango buscando el texto
  «P/qadm»; ahora exige «P/q_disponible» y la mención a la presión disponible.

## Lo que queda abierto, y es decisión del proyectista

- **`max_LB_ratio = 2,0` por omisión.** Ahora se ve lo que poda; subirlo es decisión suya.
- **Refinar los peraltes de plantas dominadas** (limitación declarada en §3).
- **El voladizo de la combinada** (`first_column_edge_distance_m`) sigue siendo dato fijo:
  el motor calcula la longitud que centra la resultante, pero no propone esa geometría por
  sí mismo.
- Las **cuatro limitaciones declaradas de la conectada** que pueden producir un PASS falso
  (rigidez de la viga, reacción del terreno bajo la viga, relleno sobre la viga en el vano
  libre y factor de carga muerta en modo directo).
