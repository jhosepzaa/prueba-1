# Desarrollo del refuerzo con columna descentrada y carga neta ascendente (2026-09-28)

Dos defectos del motor encontrados al resolver el problema 2 de Aragón (CR2-93-134 §3.6)
como cimentación conectada. **Estado: cerrado y congelado** (aprobación explícita del
proyectista, 2026-09-28; regeneración verificada caso por caso: cambiaron exactamente los 18
casos aprobados y ninguno más). Hashes: `baseline.json` `f83e15382c66…`,
`baseline_connected.json` `30647a1e92c3…`.

## 1. Carga neta ascendente en la conectada — `CARGA_NETA_ASCENDENTE`

**Hallazgo.** En cuerpo rígido, si el suelo devuelve bajo una zapata menos que su propio
peso, la carga corregida R − W sale negativa: columna y viga tienen que sostenerla. El
diseño de la zapata (`evaluate_candidate`) solo está planteado para carga neta hacia abajo
y abortaba con «La carga vertical total debe ser positiva», que el barrido clasificaba
como `ENTRADA_INVALIDA`, es decir, «un dato mal declarado», con los datos correctos.

**Corrección.** `solve_connected_footing` lo detecta después del despegue, en las
combinaciones FACTORIZADAS, en las dos zapatas y en los dos modelos. El candidato se sigue
RECHAZANDO, pero con motivo propio (`RejectionReason.CARGA_NETA_ASCENDENTE`, valor
**añadido** al vocabulario de búsqueda) y un detalle que nombra la combinación, la zapata y
la carga, y explica la física. **No** se implementa el diseño de la zapata que cuelga de la
viga: sería un modelo nuevo, con la tracción arriba.

**Impacto.** Ningún baseline cambia. El único `ENTRADA_INVALIDA` congelado (Z4) es un error
real de declaración y lo sigue siendo. Suite completa: 2101 pasan con este cambio solo.
Tests: `tests/test_carga_neta_ascendente_conectada.py`.

## 2. Desarrollo del refuerzo con la columna descentrada — E.060 §15.6.2

**Hallazgo.** `build_rebar_geometry` tomaba el voladizo como `(B − bx)/2`: la columna
CENTRADA, aunque `depth_solver` ya conocía su posición. Con la columna al lindero, la barra
que cruza la cara del voladizo solo tiene, hacia el lindero, el ancho de la columna para
anclarse, y el motor no lo miraba: **del lado inseguro**.

**Norma** (`docs/normativa/texto/e.060-concreto-armado-sencico.txt`):

- §15.6.2: «La tracción o compresión calculadas en el refuerzo en cada sección debe
  desarrollarse a cada lado de dicha sección»
- §15.6.3: secciones críticas en los planos de §15.4.2, la cara de la columna.

**Regla implementada** (`rebar_geometry.development_length_available`):

```text
disponible = min( voladizo_libre − rec ,  columna + voladizo_opuesto − rec )
```

evaluada en la cara cuyo momento **gobierna** la dirección, la que `depth_solver` ya
identifica. Con la columna concéntrica el segundo término siempre es mayor y el resultado
es idéntico al anterior, bit a bit.

**Decisiones del proyectista (2026-09-28):**

1. Solo la cara que gobierna. Exigir la ld completa a fy en la cara de voladizo corto (casi
   sin tracción) la hacía gobernar por un artificio: Z6, holgura de 0,15 m al lindero,
   0,075 m disponibles. Es hipótesis de modelación declarada, no texto de la norma. Si
   ninguna combinación dio momento, se verifican todas las caras con voladizo.
2. Ganchos declarables en la conectada, por zapata y por dirección
   (`ConnectedElement.hook_type_x/_y`, `ConnectedColumnInput.hook_type_x/_y`). Campo
   **aditivo**; por defecto «ninguno»: el programa nunca los supone.
3. Los casos congelados de la conectada declaran gancho de 90° en la zapata de lindero, en
   la dirección de la viga. Sin él, una barra recta no se ancla en los 0,425 m que deja una
   columna de 0,50 m (una Ø1/2" pide unos 0,56 m) y el caso dejaría de proteger su
   estática para congelar un FAIL de anclaje.

Sin cambios: la demanda sigue siendo la ld completa a fy, sin reducirla por la tensión
calculada ni por §12.2.5 (refuerzo en exceso, potestativo y con excepción sísmica).

Campo nuevo `BarLayerGeometry.through_column_length_m`: solo existe cuando gobierna el tramo
a través de la columna; va en `OPTIONAL_WHEN_NONE_FIELDS` y no añade claves a los casos
concéntricos.

## 3. Diff por caso (a regenerar solo con aprobación)

Concéntricas y combinadas: **sin cambios**. Micro-barridos ZB1–ZB3: **sin cambios** (con el
gancho de lindero conservan 8/8/0 aceptadas).

| Caso | Disponible X/Y (m) | Estado | Nota |
|---|---|---|---|
| 13_descentrada_un_eje | X 1,275 → 0,825 | sin cambio | se descartan 2 opciones de armado |
| 14_descentrada_dos_ejes | X 1,375 → 1,025; Y 1,275 → **1,325** | sin cambio | en Y la regla real da MÁS que la concéntrica |
| 15_descentrada_voladizo_largo_gobierna | X 1,275 → 0,725 | sin cambio | 2 opciones descartadas |
| 16_columna_de_borde | X 1,275 → 0,425 | sin cambio | gancho 90° en X: ldg = 0,279 m; se descarta la opción de barra mayor |
| 17_columna_de_esquina | X y Y 1,275 → 0,425 | sin cambio | gancho 90° en X e Y |
| 18_borde_con_momento | X 1,375 → 0,425 | sin cambio | gancho 90° en X: ldg = 0,350 m |
| Z1, Z1b, Z2, Z3, Z8, Z13, Z14, Z15 | X 0,675 → 0,425 | sin cambio | gancho 90°: ldg = 0,350 m |
| Z5_eje_longitudinal_Y | Y 0,675 → 0,425 | sin cambio | gancho en Y |
| Z6_holgura_al_lindero_no_nula | X 0,675 → 0,575 | sin cambio | ya no gobierna la cara de 0,15 m |
| Z11_aragon_p1_articulado | X 0,375 → 0,425 | **desarrollo X FAIL → PASS** | fallaba recta ANTES del cambio; el gancho lo resuelve. Sigue en FAIL global por punzonamiento |
| Z12_aragon_p2_cuerpo_rigido | X 0,825 → 0,575 | sin cambio | ldg = 0,279 m |

Invariantes que se mantienen: estática, presiones, cortante, punzonamiento y flexión no se
mueven en ningún caso; solo cambian la geometría de desarrollo, la ld con gancho y la lista
de opciones de armado desarrollables.

Aisladas 16–18: el proyectista decidió (2026-09-28) declararles gancho de 90° en las barras
que corren hacia el borde, igual que a las zapatas de lindero de la conectada. Sin él, la
regla corregida las dejaba en FAIL de anclaje.

`test_D3_no_mueve_zapatas_ni_reparto` compara contra la referencia previa a la Fase 5A,
que no se regenera: el cambio entra como dispensa acotada
(`EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA`, 16 claves, todas del desarrollo del acero de la
zapata exterior; `test_la_dispensa_de_desarrollo_esta_acotada` lo vigila y
`test_la_dispensa_no_se_ha_quedado_obsoleta` exige que cada una siga haciendo falta).
Suite completa tras el freeze: 2124 pasan, 2 se saltan. Tests nuevos:
`tests/test_desarrollo_columna_descentrada.py` (reconstrucción a mano y mutación
comprobada).

## 4. Efecto en el problema 2 de Aragón entregado el 2026-09-28

Con la regla corregida y barra recta, ninguna terna del rango refinado pasa: con la columna
de 0,80 m al lindero, hacia él la barra solo tiene 0,725 m. Con gancho de 90° en la zapata
de lindero se recupera exactamente el resultado anterior (451 aceptadas, CONN-076). El
archivo `proyectos/Aragon-CR2-problema-2-conectada.zapata.json` declara ahora ese gancho y
la búsqueda automática, que recomienda CONN-021 (31,6 m³, frente a 40,4 m³), y la memoria
se regeneró.
