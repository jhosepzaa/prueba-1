# Reverificación normativa: E.060 entregada frente al motor

Fecha: 2026-09-14. Tipo: **auditoría** (CLAUDE.md §17). **No se modificó código, tests ni
baselines.** Sustituye al contraste preliminar del mismo día.

Fuente: `fuentes/e.060-concreto-armado-sencico.pdf`, portada «PROPUESTA DE NORMA E.060
CONCRETO ARMADO 2019», designada por el usuario como la E.060 del proyecto. Extracto:
`texto/e.060-concreto-armado-sencico.txt` (modo `-raw`).

## Método

1. Se listaron las **95 citas `§x.y` distintas** del motor (`engine/**/*.py`). Dos no son de
   E.060: §3.5 y §3.6 citan los apuntes de Aragón. Quedan **93 secciones de E.060**.
2. Para cada una se puso lado a lado el texto de la norma (desde su encabezado hasta el
   siguiente) y todos los usos en el motor: valor, fórmula o afirmación.
3. Se comprobó el **contenido**: coeficientes, límites, alcance y numeración de ecuaciones.
4. Símbolos perdidos en la extracción (±, ≥, ≤, α) se identificaron por su código en la
   fuente Symbol del PDF (0xB1 = ±, 0xA3 = ≤, 0x61 = α). Se validó con usos inequívocos del
   mismo documento, por ejemplo «0,10 ≤ SO₄ < 0,20».

## Resumen

| Resultado | Temas |
|---|---|
| **A. Diferencia de valor o de alcance: cambia resultados** | 8 |
| **B. Diferencia de numeración o de cita: mismo contenido** | 11 |
| **C. Coincide** | el resto de las 93 secciones |

---

## A. Diferencias que cambian resultados (requieren decisión, una por una)

| # | Artículo en la fuente | Fuente | Motor hoy | Dónde | Alcance |
|---|---|---|---|---|---|
| A1 | §7.7.1 a) | Concreto colocado contra el suelo y expuesto permanentemente: **75 mm** | 70 mm (`COVER_FOOTING_ON_SOIL_MM`); también la opción «vaciado contra suelo» de la cara superior | `codes/peru/e060_concrete.py`, `reinforcement/face_reinforcement.py` | d de **todas** las zapatas; golden cases, benchmarks y los dos baselines |
| A2 | §21.12.3.2 | Menor dimensión ≥ luz libre/20, «no necesita ser mayor a **450 mm**» | Tope de 400 mm | `beam/connecting_beam.py`, `beam_trace.py` | Viga de conexión con luz libre/20 > 400 mm |
| A3 | §10.5.3 | La exención por colocar un tercio más del acero requerido es solo para **losas macizas y losas nervadas** que cumplan 8.12 | Se aplica a la **viga de conexión** (`EXCESS_FACTOR = 4/3`). Además cita que §21.4.4.1 y §21.5.2.1 dicen «No se aplicará lo dispuesto en 10.5.3»: esa frase **no está** en la fuente | `beam/beam_flexure.py`, `beam/connecting_beam.py` | Acero mínimo de la viga (conectada y viga) |
| A4 | §12.5.1 | Longitud de gancho «no debe ser menor que **8 db ni 150 mm**»: rigen **ambos** mínimos | `min(8·db, 150 mm)`: rige el menor | `codes/peru/e060_development.py` | Anclaje con gancho declarado. Del lado **no conservador** |
| A5 | §21.5.1.3 | bw ≥ **0,3·h** y ≥ 250 mm | bw ≥ **0,25·h** y ≥ 250 mm, citado como §21.5.1.4 | `beam/connecting_beam.py` | Viga con §21.12.3.3 activo y sistema de pórticos o dual |
| A6 | §21.2.4 / §21.2.5 | §21.4 aplica a **muros estructurales**; §21.5 a **pórticos y duales**. **No distingue dual tipo I y tipo II** | «dual_tipo_I» → §21.4; «dual_tipo_II» → §21.5 | `beam/connecting_beam.py` | Qué requisitos sísmicos se aplican a una viga con sistema dual |
| A7 | §12.1.3 | √f'c ≤ **7,3 MPa** en el capítulo 12 | 8,3 MPa, citando §12.1.2 | `codes/peru/e060_development.py` | Solo f'c > 53,3 MPa. **Posible errata de la fuente**: confirmar con el usuario, no suponer |
| A8 | §9.7.2 y §3.5.1 | Refuerzo por retracción y temperatura «será de acero corrugado»; solo da 0,0020 y 0,0018. §3.5.1: el refuerzo debe ser corrugado salvo 3.5.4 | Devuelve ρ = 0,0025 para **barras lisas**, citando §9.7 | `codes/peru/e060_concrete.py` | La opción de barras lisas no tiene respaldo en esta fuente |

## B. Diferencias de numeración o de cita (sin cambio numérico)

| # | Contenido (coincide) | Fuente | Motor cita |
|---|---|---|---|
| B1 | Vc de punzonamiento: 0,17(1 + 2/β)·√f'c·bo·d; 0,083(αs·d/bo + 2)·√f'c·bo·d; 0,33·√f'c·bo·d; αs 40/30/20 | §11.12.2.1, ec. **(11-41), (11-42), (11-43)** | ec. 11-33, 11-34, 11-35 |
| B2 | Transferencia de momento: γv = 1 − γf; vn = Vc/(bo·d) | **§11.12.7.1 (11-45), §11.12.7.2 (11-46)**. Su §11.12.6 es «Aberturas y bordes libres en losas» | §11.12.6, §11.12.6.1, §11.12.6.2; ec. 11-39, 11-40 |
| B3 | Es = 200 000 MPa | **§8.5.5** (§8.5.2 es Ec) | §8.5.2 |
| B4 | Separación libre mínima ≥ db y ≥ 25 mm | **§7.6.1** (§7.6.6 es paquetes de barras) | §7.6.6 |
| B5 | Límite de √f'c en el capítulo 12 (valor en A7) | **§12.1.3** (§12.1.2: las longitudes de desarrollo no llevan φ) | §12.1.2 |
| B6 | ψt·ψe ≤ 1,7 | Nota de la **Tabla 12.2, §12.2.4** (§12.2.5 es refuerzo en exceso) | §12.2.5 |
| B7 | Sección crítica de cortante de la zapata medida desde las secciones de 15.4.2 | **§15.5.2** (§15.5.3.2 trata de pilotes) | §15.5.3.2 |
| B8 | Pu ≤ 0,1·f'c·Ag / luz libre ≥ 4·h / ancho de la viga | **§21.5.1.1 / §21.5.1.2 / §21.5.1.3** | §21.5.1.2 / §21.5.1.3 / §21.5.1.4 |
| B9 | Recubrimiento contra el suelo (valor en A1) | **§7.7.1 a)** | «§7.7(a)» |
| B10 | Sección crítica de momento en la cara de la columna | **§15.4.2**, tabla | «§15.4(a)» |
| B11 | Refuerzo continuo en vigas sísmicas | §21.4.4.1 y §21.5.2.1 **no contienen** «No se aplicará 10.5.3» | Cita esa frase como texto de la norma |

## C. Coincidencias comprobadas

| Tema | Secciones |
|---|---|
| Materiales | §9.4 f'c ≥ 17 MPa; §9.5 fy ≤ 550 MPa |
| Factores φ | §9.3.2: flexión 0,90; cortante 0,85; tracción 0,90; compresión 0,70 / 0,75 en espiral |
| Flexión | §10.2.3 εcu = 0,003; §10.2.7 bloque 0,85·f'c; §10.2.7.3 β1 (0,85 → 0,65 lineal entre 28 y 56 MPa); §10.3.2; §10.3.6.2 Pn,máx = 0,80·Po (10-2) |
| Acero mínimo | §9.7.2 0,0018 / 0,0020; §9.7.3 y §10.5.4 separación ≤ 3h y 400 mm, cara traccionada ≥ 0,0012; §10.5.1 fr = 0,62√f'c y 1,2·Mcr, exclusión de zapatas y losas macizas; §10.5.2 0,22√f'c/fy·bw·d (10-3); §10.6 |
| Cortante | §11.1; §11.1.3.1; §11.3.1.1 Vc = 0,17√f'c·bw·d (11-3); §11.5.2 fyt ≤ 420; §11.5.5.1 d/2 y 600 mm; §11.5.5.3 0,33; §11.5.6.1 exenciones a) losas y zapatas, c) h ≤ 250 mm; §11.5.6.2 0,062 / 0,35 (11-13); §11.5.7.2 (11-15); §11.5.7.9 0,66 |
| Punzonamiento | §11.12.1.1; §11.12.1.2 perímetro mínimo a d/2; coeficientes de B1; §11.12.3 d ≥ 150 mm; γf de la ec. (13-1) |
| Anclaje | §12.2.1 ≥ 300 mm; Tabla 12.1 divisores 2,6 y 2,1; §12.2.3 (12-1) con 1,1 y (cb + Ktr)/db ≤ 2,5; Tabla 12.2 ψt 1,3, ψe, ψs 0,8 / 1,0, λ; §12.5.2 0,24; Tabla 12.4 ψc 0,7 y ψr 0,8 |
| Zapatas | §15.2.1 cargas amplificadas; §15.2.2 área con cargas de servicio; §15.2.3 solo compresiones; §15.2.4 +30 %; §15.2.5 80 % sísmico; §15.3; §15.4.1; §15.4.2; §15.4.4 (15-1); §15.5.1; §15.6; §15.7 300 / 400 mm; §15.10.1 a §15.10.3 |
| Sísmico | §21.4.3; §21.4.4.2 a §21.4.4.4; §21.4.4.3 M⁺ ≥ M⁻/3; §21.5.2.1 cuantía ≤ 0,025; §21.5.2.2 M⁺ ≥ M⁻/2; §21.5.3; §21.12.3.1; §21.12.3.2 estribos; §21.12.3.3 |

## D. Disposiciones de la fuente que el motor no usa y conviene conocer

| Artículo | Contenido | Relación con el motor |
|---|---|---|
| §9.2 completo | Variantes por nivel de la acción (9-2a, 9-3b, 9-4a, 9-4b), CE (9-6, 9-7), CL (9-8), CT (9-9, 9-10); §9.2.4: sismo y viento no simultáneos | Contrato de cargas. Ver `transcripcion_cargas.md` |
| §11.12.3.1 / §11.12.3.2 | Con refuerzo de cortante en losas y zapatas: Vc ≤ 0,17√f'c·bo·d y Vn ≤ 0,5√f'c·bo·d | Revisar si aplica a los estribos de la combinada |
| §15.2.6 | En terrenos de baja capacidad portante debe analizarse conectar las zapatas con vigas | Informativo para la conectada |

## Recomendación

- **Orden de las decisiones A:**
  1. A4 (gancho): del lado no conservador y de alcance acotado.
  2. A1 (recubrimiento): mueve toda la base de regresión; exige diff por caso.
  3. A3 y A2 (viga).
  4. A5 y A6 (vigas sísmicas).
  5. A8 (barras lisas).
  6. A7, tras confirmar si «7,3» es errata.
- **Correcciones de cita B:** son cambios mecánicos (§3 permite hacerlos sin consultar). Tocan
  `code_reference`, que en el congelamiento es un contrato **blando**: se revisan una por una.
  No cambian números ni estados.

## Aplicación (Fase 10A, 2026-09-14)

Todas las diferencias A1–A8 y B1–B11 se aplicaron al motor, la API, la UI y los tests. Detalle,
archivos y efecto en el congelamiento: `docs/fase10_alineacion_e060_y_contrato_cargas.md`.

- A7 se adoptó con el valor de la fuente (7,3 MPa) y queda pendiente de confirmar si es errata.
- A6 conserva el valor de entrada `dual_tipo_I` por compatibilidad de API; ahora lleva a §21.5.
- Los nombres de campo congelados (`Vc_eq_11_33_kN`…) no se renombraron; solo cambia la cita.
