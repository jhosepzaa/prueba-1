# Fase 10 — Alineación con E.060 (10A) y contrato de cargas por casos (10B)

Fecha: 2026-09-14. Tipo: **implementación** (CLAUDE.md §17). Estado: **cerrada y congelada**
(freeze dirigido aprobado y ejecutado el 2026-09-15).

Freeze: `baseline.json` `0b2437648d89…` → `2f7eee69b46c…` (26 casos);
`baseline_connected.json` `203e9797ad58…` → `8db2a0b36b69…` (13 casos);
`reference_pre_5a_non_beam.json` `052a7b015500…` → `f204225ef0f2…` (Z3 158, Z12 187, Z13 141 y
Z14 157 claves existentes; metadatos y `traza.orden` intactos). Sin cambio verificado: V1, V2,
V3, V6, Z4, Z9, Z10, ZB1, ZB2, ZB3. Tras el freeze: 1275 pasan sin `tests/freeze`; 225 pasan y
2 omitidos en `tests/freeze`.

Fuentes (CLAUDE.md §8): `docs/normativa/fuentes/e.060-concreto-armado-sencico.pdf` (propuesta
E.060 2019, designada por el usuario), `Norma E.020 Cargas.pdf`, `E.030 Diseño
sismorresistente (2026).pdf`. Transcripciones: `docs/normativa/contraste_e060_motor.md` y
`docs/normativa/transcripcion_cargas.md`.

---

## 10A — Alineación del motor con E.060

### Diferencias de valor (A1–A8)

| # | Norma | Antes | Ahora | Archivos |
|---|---|---|---|---|
| A1 | §7.7.1 a) recubrimiento contra el suelo | 70 mm | **75 mm** (`COVER_FOOTING_ON_SOIL_MM`); también «vaciado contra suelo» de la cara superior | `codes/peru/e060_concrete.py`, `reinforcement/face_reinforcement.py`, `domain/search_parameters.py` |
| A2 | §21.12.3.2 tope de la menor dimensión | 400 mm | **450 mm** (`MIN_DIMENSION_CAP_M`) | `beam/connecting_beam.py`, `beam/beam_trace.py` |
| A3 | §10.5.3 exención de 4/3 del acero requerido | aplicada a vigas | **solo losas**: la viga nunca queda exenta. Se eliminó la frase «No se aplicará 10.5.3», que no está en §21.4.4.1 ni §21.5.2.1 (B11) | `beam/beam_flexure.py`, `beam/connecting_beam.py` |
| A4 | §12.5.1 longitud mínima del gancho | `min(8db, 150 mm)` | **`max(8db, 150 mm)`** | `codes/peru/e060_development.py` |
| A5 | §21.5.1.3 ancho de la viga sísmica | bw ≥ 0,25h | **bw ≥ 0,3h** | `beam/connecting_beam.py` |
| A6 | §21.2.4 / §21.2.5 | dual tipo I → §21.4 | **dual → §21.5**, sin distinguir tipo I y II. Se conserva el valor de entrada `dual_tipo_I` por compatibilidad de API | `beam/connecting_beam.py` |
| A7 | §12.1.3 límite de √f'c | 8,3 MPa | **7,3 MPa** (`SQRT_FC_MAX_MPA`). Solo afecta a f'c > 53,3 MPa. **Posible errata de la fuente**: adoptado tal cual, pendiente de confirmación | `codes/peru/e060_development.py` |
| A8 | §3.5.1, §3.5.4.2, §9.7.2 | ρ = 0,0025 para barras lisas | **barras lisas rechazadas**: `ENTRADA_INVALIDA` en el material y `ValueError` en `rho_min_temperature` | `domain/materials.py`, `codes/peru/e060_concrete.py` |

`disallows_10_5_3` se conserva en el DTO (cambio aditivo, CLAUDE.md §2) y vale siempre `False`.

### Diferencias de cita (B1–B11)

Se reemplazaron 87 citas en el motor, la API, la UI y los tests. El contenido no cambia:

| Contenido | Antes | Ahora |
|---|---|---|
| Vc de punzonamiento | ec. 11-33 / 11-34 / 11-35 | **ec. 11-41 / 11-42 / 11-43** (§11.12.2.1) |
| Transferencia de momento | §11.12.6.1 / .2, ec. 11-39 / 11-40 | **§11.12.7.1 (11-45) / §11.12.7.2 (11-46)** |
| Es | §8.5.2 | **§8.5.5** |
| Separación mínima | §7.6.6 | **§7.6.1** |
| Límite de √f'c | §12.1.2 | **§12.1.3** |
| ψt·ψe ≤ 1,7 | §12.2.5 | **§12.2.4** (nota de la Tabla 12.2) |
| Sección de cortante de la zapata | §15.5.3.2 | **§15.5.2** |
| Requisitos de §21.5.1 | .2 / .3 / .4 | **.1 / .2 / .3** |
| Recubrimiento | «§7.7(a)» | **§7.7.1 a)** |
| Sección crítica de flexión | «§15.4(a)» | **§15.4.2** |

Los nombres de campo del snapshot y del DTO (`Vc_eq_11_33_kN`…) **no** se renombraron: son
contrato congelado. Solo cambia el texto de la referencia.

### Referencias recalculadas (autorizadas por la tarea, no baselines)

- Golden 06 y 08 (`tests/golden_cases/`) y benchmarks G06/G08 (`tests/validation/benchmarks.py`):
  recalculados a mano con d = h − 75 mm − db. Golden 06: d = 0,30595 m, ratio de punzonamiento
  1,233. Golden 08: d = 0,69165 m, ratio 1,243. Se conservan las causas de fallo.
- Tests de la viga (fase 3), de desarrollo, de E.060 y de auditoría ajustados a los nuevos valores.

---

## 10B — Contrato de cargas por casos (alternativa C)

Decisión de contrato: `docs/analisis_contrato_cargas.md`, alternativa C (híbrida).

### Modelo

```text
modo directo (sin cambios):  LoadCombination(P, Mx, My, Hx, Hy)          composition = None
modo por casos (nuevo):      LoadCase(nombre, tipo, nivel, P, Mx, My, Hx, Hy)  por columna
                           + CombinationDefinition(nombre, tipo, {caso: factor})
                           → derive_combination → LoadCombination + LoadComposition
```

- `engine/domain/load_cases.py`: tipos de E.060 §9.2 (CM, CV, CVi, CS, CE, CL, CT). El nivel
  (SERVICIO | RESISTENCIA) es obligatorio para CVi y CS y prohibido en los demás.
- El motor **no genera** las combinaciones de §9.2: el usuario declara los factores (I7).
- `LoadComposition` guarda cada componente factorizada y `dead_load_factor` (el factor único de
  los casos CM en esa combinación; dos factores distintos de CM son error).
- Una combinación derivada es idéntica, en P, M y H, a la que el usuario formaría a mano. Los
  consumidores que no leen la composición no ven diferencia (I2, probado en aislada, combinada
  y conectada).

### Qué usa la composición

| Consumidor | Modo directo | Modo por casos | Base |
|---|---|---|---|
| Peso propio EXPLICITO de la viga (conectada) | sin factor (TBD-C13 abierto) | **× factor de CM** de la combinación; sin CM, 0. Se exige el mismo factor en las dos columnas | E.020 art. 2 (el peso propio es carga muerta) |
| Presión en el suelo (aislada), reducción sísmica activada por el usuario | no se aplica | **CS a nivel de resistencia × 0,8**; CS a nivel de servicio sin reducir | E.030 art. 29; E.060 §15.2.5 |
| Estabilidad (aislada): fuerza estabilizante | P total (cota superior) | **peso propio + CM + componentes negativas no muertas** | E.020 art. 20.1 |

### Estabilidad (engine/soil/stability.py)

- FS requerido, si el usuario no lo declara:
  - volteo con sismo: **1,2** (E.030 art. 64.2, sin la reducción de art. 29);
  - volteo sin sismo: **1,5** (E.020 art. 21);
  - deslizamiento: **1,25** (E.020 art. 22.1).
- μ sigue siendo dato obligatorio (E.020 art. 22.2: lo fija el proyectista).
- **Regla de estado:** con la fuerza estabilizante exacta (modo por casos), el resultado es
  PASS o FAIL. Si se usó la P total (modo directo o cargas corregidas de la conectada), el
  cumplimiento queda **NO VERIFICADO**: la P total incluye carga viva y es una cota superior.
  Un FAIL sigue siendo FAIL, porque con menos fuerza estabilizante fallaría igual.
- Nueva limitación `connected_footing_stability_composition`: las cargas corregidas de la
  conectada no conservan la composición. Su estabilidad no puede demostrarse todavía, ni
  siquiera en modo por casos. `can_cause_false_pass=False`.

### API y UI (cambio aditivo)

- `DesignRequest`: `load_cases`, `combination_definitions`; `combinations` pasa a lista vacía
  por defecto.
- `CombinedColumnInput` / `ConnectedColumnInput`: `load_cases`. `CombinedDesignRequest` /
  `ConnectedDesignRequest`: `combination_definitions`.
- Enviar los dos modos a la vez, o casos sin definiciones, devuelve 422.
- UI: selector «Modo de cargas» y editor `LoadCasesEditor.tsx` en los tres paneles. Punto de
  partida editable: S1 = CM + CV; U1 = 1,4 CM + 1,7 CV (E.060 §9.2.1, ec. 9-1).

### Tests nuevos

- `tests/test_load_cases_phase10b.py` (17): validación, linealidad, equivalencia I2 (aislada,
  combinada y conectada DESPRECIADO), factor de CM en el peso de la viga (U1 = 1,4 × 34,713 kN),
  combinación sin CM, reducción sísmica con fórmula a mano, modo directo sin reducción, y API
  (aislada por casos, dos modos → 422, casos sin definiciones → 422, combinada y conectada).
- `tests/test_tbd_c13_beam_weight_factoring.py` (4).
- Mutaciones deliberadas y revertidas, las tres detectadas: estabilizante solo muerta, escala
  por el factor de CM y factor 0,8.

---

## Resultado de la suite

`py -3 -m pytest -q --ignore=tests/freeze`: **1265 pasan, 4 fallan**. Los 4 son
`test_D3_no_mueve_zapatas_ni_reparto[Z3, Z12, Z13, Z14]`, que comparan contra la referencia
congelada `tests/freeze/reference_pre_5a_non_beam.json`. Primer fallo:
`exterior.d_m 0.80615 → 0.80115` (A1).

Los tests de `tests/freeze/` fallan contra los baselines vigentes, como se espera de un cambio
normativo intencional.

---

## Revisión del freeze (pendiente de aprobación)

Método: se compararon el baseline vigente, una instantánea tomada al terminar 10A
(`snap_post10a`) y el motor actual. Así, cada campo se atribuye a 10A o a 10B.

### `baseline.json` (aislada, combinada, viga): 26 de 30 casos cambian

| Casos | 10A | 10B |
|---|---|---|
| 01–18, S1, S2 (aislada) | d = h − 75 − db (−5 mm) y lo que depende de d: punzonamiento, cortante, As, anclaje, geometría del refuerzo. 5 referencias por caso (B1, B4, B10) | FS_required `None → 1,5 / 1,25` en 02, 03, 04, 09, 10, 11, 13, 14, 15, 18, S2 |
| 11_sismica_con_horizontales | igual | `overturning_x`: **PASS → NO VERIFICADO** (modo directo) |
| S1_barrido_axial | `n_descartes [1,1,0] → [2,1,0]`: en h = 0,30 m (d 0,21095 → 0,20595) se suma «Punzonamiento no cumple.» al peralte mínimo. h aceptado sigue en 0,40 m | — |
| K1–K4 (combinada) | d (−5 mm) y derivados; 2–3 referencias | — |
| V4 (viga, §21.4) | `disallows_10_5_3 True → False`; `As_required_by_analysis` ahora informado | — |
| V5 (viga, §21.5) | **status NO VERIFICADO → FAIL**: b/h = 0,35/1,20 = 0,292 < 0,30 (A5) | — |

No cambian: V1, V2, V3 y V6.

### `baseline_connected.json`: 13 de 19 casos cambian

| Casos | 10A | 10B |
|---|---|---|
| Z1, Z1b, Z2, Z3, Z5, Z6, Z7, Z8, Z11–Z15 | d de las dos zapatas (−5 mm) y derivados; 10 referencias (B1, B4, B10). **Nada de la viga ni del reparto cambia** | `overturning` de la zapata: **PASS → NO VERIFICADO** (cargas corregidas sin composición). Arrastra `exterior/interior.overall_status` e `implemented_checks_status` a NO VERIFICADO donde eran PASS |
| Z1b | igual | FS_required `None → 1,5` (E.020 art. 21). Propósito adaptado: ver «Z1b» en Decisiones |

No cambian: Z4, Z9, Z10, ZB1, ZB2 y ZB3 (rechazados antes de verificar las zapatas o sin campos afectados).

### `reference_pre_5a_non_beam.json` (Z3, Z12, Z13, Z14)

Es la lista positiva de claves que D3 no debía mover. Cambian 141–187 claves por caso, todas
por las mismas dos causas: d (A1) y citas en 10A, y estabilidad en 10B. La lista de claves no
cambia. Propuesta: actualizar **solo los valores** de esas claves y registrar la causa en
`_descripcion`.

### Invariantes que se mantienen

- Estática, reparto, B*, conservación de carga y diagramas de la viga: sin cambios en los 13
  casos conectados.
- Ningún cambio convierte NO VERIFICADO en PASS. Los cambios de estado van hacia más severo
  (PASS → NO VERIFICADO, NO VERIFICADO → FAIL).
- El orden de la traza no cambia. Los textos globales de descarte no cambian; solo S1 suma uno ya existente.

### Regeneración propuesta (tras aprobación explícita)

1. `baseline.json`: los 26 casos listados.
2. `baseline_connected.json`: los 13 casos listados.
3. `reference_pre_5a_non_beam.json`: solo los valores de las claves existentes.

---

## Decisiones (estado al 2026-09-14)

Aprobadas por el usuario según esta revisión: D10-1, D10-3 a D10-7. D10-2 se verificó contra
el texto de las fuentes (`docs/normativa/texto/`, modo `-raw`).

| # | Decisión | Evidencia normativa | Estado |
|---|---|---|---|
| D10-1 | √f'c ≤ 7,3 MPa (A7), tal cual la fuente | E.060 §12.1.3 (posible errata, declarada en el contraste) | **aprobada** |
| D10-2a | FS por defecto: deslizamiento 1,25; volteo sin sismo 1,5 | E.020 art. 22.1 y art. 21: «La edificación o cualquiera de sus partes» con coeficiente mínimo 1,25 / 1,5. Capítulo 6 general, sin exclusiones | **cerrada** |
| D10-2b | Volteo con sismo: 1,2 | E.030 art. 64.2: FS ≥ 1,2 con fuerzas del análisis sin la reducción del art. 29 | **abierta**: ver ambigüedad abajo. No bloquea el freeze |
| D10-3 | Con la P total (modo directo o cargas corregidas), un cumplimiento de estabilidad es NO VERIFICADO | E.020 art. 20.1: estabilidad «sólo por las cargas muertas» | **aprobada** |
| D10-4 | Reducción sísmica 0,8 (no 0,70) | E.030 art. 29; E.060 §15.2.5; E.020 art. 19 se declara subsidiaria («Excepto en los casos indicados en las normas propias…») | **aprobada** |
| D10-5 | Peso propio de la viga × factor de CM, en modo por casos | E.020 art. 2 (el peso propio es carga muerta) | **aprobada** |
| D10-6 | Relleno: el usuario lo declara como CM o CE | E.020 art. 20.2 («puede ser considerado»); E.060 §9.2.5 | **aprobada** |
| D10-7 | Estabilidad de las zapatas de la conectada no demostrable (limitación) | E.020 art. 20.1 | **aprobada** |

### Ambigüedad de D10-2b

Para una combinación **con sismo** aplican literalmente dos textos y ninguna fuente dice cuál
prevalece:

- E.020 art. 21 exige 1,5 contra el volteo a «la edificación o cualquiera de sus partes», sin
  distinguir el tipo de carga;
- E.030 art. 64.2 exige 1,2 al volteo producido por el sismo.

Son posibles dos lecturas: (i) E.030 64.2 sustituye a E.020 21 en las combinaciones sísmicas
(norma específica), que es lo que hace el motor; (ii) ambas aplican y rige 1,5. E.020 declara
su subsidiariedad en el art. 19 (combinaciones) y en el art. 25.1 (flechas), y el art. 24 remite
expresamente a E.030 para los desplazamientos sísmicos; el art. 21 no contiene ninguna remisión.

Por qué no bloquea el freeze: el valor 1,2 para el sismo **ya estaba en el motor antes de la
Fase 10** y congelado. Único caso afectado: `11_sismica_con_horizontales`, con FS_required =
1,2 (sin cambio en este freeze) y FS obtenido = 7,92. Con la lectura (ii) cambiaría a 1,5 ese
número; el estado seguiría en NO VERIFICADO (modo directo).

### Z1b

El caso conserva nombre y entradas (sin FS de volteo declarado). Cambió lo que fija:

- **Antes (4D):** FS no declarado → NO VERIFICADO sin `open_tbd`.
- **Ahora (10B):** FS no declarado → rige E.020 art. 21 (1,5), y la traza cita esa fuente en vez
  de «adoptado por el proyectista», que es lo que cita Z1. La falta del dato sigue sin ser un
  pendiente del motor: ninguna verificación de estabilidad lleva `open_tbd` y TBD-C1 es el mismo
  en los dos casos.
- `tests/freeze/test_freeze_connected.py::test_el_dato_que_falta_no_se_marca_como_pendiente_del_motor`
  lo afirma. Mutación: si el valor por defecto se atribuye al proyectista, el test falla.
- Solo cambiaron textos de `tests/freeze/cases.py` (mecanismo y docstring) y ese test. Ningún
  número ni estado.

### Test D2 de la conectada (adaptado por D10-3 / D10-7)

`test_el_estado_de_las_verificaciones_implementadas_es_contrato_duro` afirmaba
`implemented_checks_status == PASS` en Z1 y Z3. Con D10-3 el volteo de las zapatas conectadas
queda NO VERIFICADO, que no es un TBD y por eso entra en ese estado. El test conserva su
propósito (el estado de lo implementado no depende de pendientes y vive en el contrato duro) y
ahora afirma: `implemented_checks_status` = peor estado de las entradas sin `open_tbd`, y las
únicas peores que PASS/INFO son las de volteo, en NO VERIFICADO. Mutación: si el volteo vuelve
a PASS con la carga total, el test falla.

## Pendientes que deja la fase

- Propagar la composición a las cargas corregidas de la conectada, para demostrar su
  estabilidad.
- Reducción sísmica 0,8 en la combinada y en las zapatas de la conectada.
- Estabilidad de la combinada (pendiente 7), ahora con base normativa E.020.
