# Fase 10C — Composición de las cargas corregidas en la zapata conectada

Fecha: 2026-09-15. Tipo: implementación. Estado: **cerrada; sin cambios de baseline** (D10C-1 y D10C-2 aprobadas e implementadas).

## Objetivo

En el modo de cargas por casos, la carga que recibe cada zapata de la conectada tras el reparto
debe conservar de qué casos está hecha, con sus factores, para que la estabilidad cuente solo la
carga muerta (E.020 art. 20.1). El modo directo no cambia: no se infiere composición.

## Modelo: superposición con el mismo reparto

Las tres estrategias (ARTICULADO + EQUILIBRIO, ARTICULADO + PAR_PURO con B\*, CUERPO_RIGIDO) son
afines en (P_ext, M_ext, P_int, M_int) más las cargas que genera el motor. Por combinación, con el
MISMO `distribute_couple` (no se reescribe ninguna ecuación de 4A–9c):

| Evaluación | Da |
|---|---|
| columnas en cero, factor CM de la combinación | peso de la viga (× f_CM) + peso de las zapatas |
| columnas en cero, factor CM nulo | solo peso de las zapatas (CUERPO_RIGIDO) |
| + 1 kN o 1 kN·m en cada entrada, menos la anterior | coeficientes de cada entrada |

Cada caso aporta `coeficientes · (P, M del eje)` con su tipo, nivel, factor y origen (`columna
exterior` / `columna interior`). El momento transversal y las H no pasan por el reparto: cada
zapata conserva los de su columna. Componentes del motor:

| Componente | Tipo | Factor | Cuándo |
|---|---|---|---|
| peso propio de la viga | CM | f_CM de la combinación (0 si no hay CM) | EXPLICITO |
| peso propio de las zapatas (reparto del cuerpo rígido) | CM | f_CM en factorizadas por casos; 1,0 en servicio (D10C-1) | CUERPO_RIGIDO |

La suma de componentes se contrasta con la carga corregida (tolerancia de equilibrio); si no
cerrara, el cálculo se detiene.

**Interpretación declarada:** la reacción redistribuida que produce un caso pertenece al tipo de
ese caso (superposición de un modelo lineal). Es la lectura que permite aplicar E.020 art. 20.1 a
las zapatas de la conectada.

## Implementación

- `engine/domain/loads.py`: `ComponentAction.origin` y `LoadComposition.redistributed` (aditivos).
- `engine/analysis/connected_statics.py`: `redistributed_compositions()`,
  `REDISTRIBUTED_COMPOSITION_NOTE`; `CoupleDistribution.exterior/interior_corrected_composition`;
  `correct_loads` adjunta la composición a las cargas corregidas y a la distribución.
- `engine/foundation/depth_solver.py`: una composición redistribuida NO habilita la reducción
  sísmica al 80 % (pendiente D10C-2); se deja nota.
- `engine/results/limitations.py`: `connected_footing_stability_composition` queda acotada al modo
  directo.
- `engine/reports/connected_report.py`: tabla «Composición de las cargas corregidas».
- `tests/freeze/snapshot.py`: las dos composiciones en `OPTIONAL_WHEN_NONE_FIELDS`.

## Resultados

- Modo directo: las 49 instantáneas congeladas son idénticas antes y después.
- Modo por casos (sonda sobre la geometría de Z1, Z2, Z3, Z5, Z8, Z12, Z14, Z15, S1 = CM + CV):
  - toda la carga en CM: volteo de la zapata de lindero NO VERIFICADO → **PASS**, mismo FS;
  - 60 % CM: la estabilizante baja (Z1: N 1126,9 → 738,4 kN, FS 1,547 → 1,013) → **FAIL**.
- Cargas corregidas, reparto, peso de la viga, ΔP, M_corte: idénticos al modo directo para la
  misma combinación.
- Búsqueda: mismo número de evaluadas, aceptadas y rechazos; sobrecosto ≈ 15 %.

## Tests

`tests/test_connected_composition_phase10c.py` (41): suma exacta de componentes en 8 geometrías;
superposición independiente (un caso a la vez por el pipeline público); peso de la viga con f_CM
y conservación (1,0 y 1,4 × 34,713 kN); combinación sin CM; peso de zapatas solo en rígido y con
aporte neto nulo; DESPRECIADO sin componente de viga; igualdad con el modo directo (servicio y
factorizada); estabilidad PASS/FAIL según la carga muerta y reconstrucción de N; modo directo sin
composición (no regresión); modos mezclados → error; guarda de linealidad; reducción sísmica no
aplicada; informe. `tests/test_load_cases_phase10b.py`: la equivalencia de la conectada admite
solo las diferencias de 10C. Mutaciones detectadas: tipo del peso de viga, momento omitido en el
aporte, composición descartada, reducción sísmica habilitada, factor de la viga.

## Decisiones cerradas

### D10C-1 — peso propio de las zapatas en el reparto rígido (APROBADA, opción A)

Fuentes: E.020 art. 2 (carga muerta incluye el peso propio); E.060 §9.2.1 (U = 1,4 CM + 1,7 CV);
E.060 §15.2.1 (cargas amplificadas y reacciones inducidas); E.020 art. 20.2 y D10-6 (relleno como
carga muerta, sin input CE para el relleno del motor).

- Concreto + relleno calculados por el motor = CM.
- Combinación FACTORIZADA por casos: `footing_weight_factor` = f_CM (0 sin CM; las dos columnas
  deben coincidir). El MISMO W factorizado entra en `_rigid_body_loads` y en P_corr = R − W, y se
  guarda en `W_ext_kN`/`W_int_kN`, que usa la estática de la viga rígida.
- Servicio y modo directo: 1,0 (el motor de zapata suma W sin factor a la presión de servicio).
- Trazado: `FOOTING_WEIGHT_CM_NOTE` en las hipótesis de la distribución; componente de
  composición «peso propio de las zapatas» con el factor aplicado.
- La superposición se evalúa alrededor de una carga de referencia no nula (op afín:
  c0 = op(x0) − J·x0), porque con f_CM = 0 el cuerpo rígido quedaría sin carga.

Resultados (U1 = 1,4 CM + 1,7 CV, reconstrucción a mano = motor a 1e-12):

| Caso | Antes (W × 1,0) | Ahora (W × 1,4) |
|---|---|---|
| Z3, h iguales | P_ext_corr 1476,535 | 1476,535 (el peso uniforme por área no redistribuye) |
| Z3, h_int = 0,60 | 1476,315 | **1476,227** |
| Z12, h_int = 0,90 | 1516,361 | **1519,126** |

Sin doble factorización: P_ext_corr + P_int_corr = Pu_ext + Pu_int (DESPRECIADO), exacto.

### D10C-2 — reducción sísmica 0,8 en la conectada (APROBADA, por zapata)

Fuentes: E.030 art. 29 y 62.2 (presiones para verificación por esfuerzos admisibles con 0,8·sismo);
E.060 §15.2.5; E.030 art. 64.2 (volteo sin reducción).

- Modo por casos, opción del suelo activada, CS a nivel de resistencia: `soil_actions` reduce las
  componentes CS de la carga CORREGIDA antes de q, e, núcleo y presión admisible de cada zapata.
  Por linealidad equivale a repartir 0,8·CS (comprobado a 1e-9).
- NO se aplica: estabilidad y FS de volteo/deslizamiento, puerta de despegue del sistema,
  diseño factorizado de zapatas y viga, modo directo, zapata combinada.

| Caso (S2 = CM + CV + CS) | Sin reducción | Con 0,8 |
|---|---|---|
| Z1 zapata interior q_max | 374,19 kPa | **346,27 kPa** |
| Z3 zapata interior q_max | 295,59 kPa | **283,38 kPa** |
| Z1 zapata exterior P usada para el suelo | 786,67 kN | **823,62 kN** (la acción se reduce, no el efecto) |
| Z3 con M_CS = 1600 kN·m | σ_min −4,2 kPa → despegue | sigue rechazado (despegue sin reducir) |

## Tests del cierre

`tests/test_connected_composition_phase10c.py` (54): cuerpo rígido a mano con f_CM (Z3 y Z12,
espesores iguales y distintos) y conservación; clasificación CM trazada; modo directo sin factor;
factorizada sin CM → W = 0 y factores CM distintos → error; estática de la viga rígida consistente;
presiones por zapata con reducción = reparto de 0,8·CS (Z1, Z3); estabilidad, diseño y reparto
idénticos con y sin la opción; despegue sin reducir; `soil_actions` sobre composición
redistribuida; modo directo sin reducción; zapata que recibe más carga. Mutaciones detectadas:
resta con W sin factor, factor fijo 1,0, puerta de reducción cerrada; el filtro de nivel CS lo
cubre `test_load_cases_phase10b.py`.

## Pendientes que quedan

- Reducción sísmica en la zapata combinada (fuera del alcance de D10C-2).
- D10-2b (volteo con sismo: E.030 64.2 frente a E.020 21).
