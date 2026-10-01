# Transcripción verificada: disposiciones de cargas y combinaciones

Fecha: 2026-09-14. Fase CC-0 del contrato de cargas (`docs/analisis_contrato_cargas.md`).
Solo contiene las disposiciones necesarias para el contrato de cargas y la estabilidad.

**Fuentes** (`docs/normativa/fuentes/`):
- E.060, `e.060-concreto-armado-sencico.pdf` (propuesta 2019);
- E.020, `Norma E.020 Cargas.pdf` (SENCICO, 2020);
- E.030, `E.030 Diseño sismorresistente (2026).pdf`.

**Verificación de símbolos.** La extracción de texto pierde los caracteres de la fuente
Symbol del PDF. Se identificaron por su código:
- U+F0B1 = Symbol 0xB1 = **±**;
- U+F061 = Symbol 0x61 = **α**.

La correspondencia se validó con otros símbolos de la misma fuente cuyo sentido es
inequívoco (0xA3 = ≤ en «0,10 ≤ SO₄ < 0,20»). No hubo lectura visual del PDF, porque en el
entorno no hay herramienta de renderizado. Queda disponible para quien quiera confirmarlo
con el PDF abierto.

---

## 1. E.060 §9.2 — Resistencia requerida (combinaciones factorizadas)

| Artículo | Condición | Ecuación | Nº |
|---|---|---|---|
| 9.2.1 | Cargas muertas (CM) y vivas (CV), como mínimo | U = 1,4 CM + 1,7 CV | (9-1) |
| 9.2.2 | Viento (CVi) **a nivel de servicio**, además de 9.2.1 | U = 1,25 (CM + CV ± CVi) | (9-2) |
| | | U = 0,9 CM ± 1,25 CVi | (9-3) |
| | Viento **a nivel de resistencia** | U = 1,25 (CM + CV) ± CVi | (9-2a) |
| | | U = 0,9 CM ± CVi | (9-3b) |
| 9.2.3 | Sismo (CS) **a nivel de resistencia**, además de 9.2.1 | U = 1,25 (CM + CV) ± CS | (9-4) |
| | | U = 0,9 CM ± CS | (9-5) |
| | Sismo **a nivel de servicio** | U = 1,25 (CM + CV ± CS) | (9-4a) |
| | | U = 0,9 CM ± 1,25 CS | (9-4b) |
| 9.2.4 | No es necesario considerar sismo y viento simultáneamente | — | — |
| 9.2.5 | Peso y empuje lateral de los suelos (CE), presión del agua del suelo, o presión y peso de otros materiales, además de 9.2.1 | U = 1,4 CM + 1,7 CV + 1,7 CE | (9-6) |
| | Si CM o CV reducen el efecto del empuje lateral | U = 0,9 CM + 1,7 CE | (9-7) |
| 9.2.6 | Peso y presión de líquidos (CL) de densidad definida y altura controlada | U = 1,4 CM + 1,7 CV + 1,4 CL | (9-8) |
| 9.2.7 | Impacto | se incluye en CV | — |
| 9.2.8 | Nieve o granizo | se considera CV | — |
| 9.2.9 | Asentamientos diferenciales, flujo plástico, retracción, temperatura (CT) | U = CM + 1,25 CV + CT | (9-9) |
| | | U = 1,4 CM + 1,4 CT | (9-10) |

La etiqueta (9-3b) figura así en la fuente, aunque su par es (9-2a).

**E.060 §15.2** (zapatas): 15.2.1 diseño con cargas amplificadas; 15.2.2 área con fuerzas
y momentos no amplificados (servicio); 15.2.3 solo compresiones en el suelo; 15.2.4
incremento de 30 % de la presión admisible con cargas temporales (sismo o viento); 15.2.5
acciones sísmicas reducibles al 80 % para esfuerzos en el suelo, «ya que las solicitaciones
sísmicas especificadas en la NTE E.030 … están especificadas al nivel de resistencia».

## 2. E.020 — Definiciones y alcance

| Artículo | Disposición |
|---|---|
| Art. 1 | Las cargas actúan en las combinaciones prescritas. **Las cargas mínimas de la norma están dadas en condiciones de servicio.** Se complementa con E.030 y con las normas de cada material. |
| Art. 2, *Carga* | Fuerza u otras acciones que resulten del peso de los materiales de construcción, ocupantes y sus pertenencias, efectos del medio ambiente, movimientos diferenciales y cambios dimensionales restringidos. |
| Art. 2, *Carga muerta* | Peso de los materiales, dispositivos de servicio, equipos, tabiques y otros elementos soportados por la edificación, **incluyendo su peso propio**, que sean permanentes o con variación pequeña en el tiempo. |
| Art. 2, *Carga viva* | Peso de todos los ocupantes, materiales, equipos, muebles y otros elementos movibles soportados por la edificación. |
| Art. 3 | Se considera el peso real de los materiales, con los pesos unitarios del Anexo 1 (se admiten menores si se justifica). |
| Art. 13.4 | Cuando la presión lateral del suelo se opone a la acción estructural de otras fuerzas, no se toma en cuenta en esa combinación, pero sí en el diseño. |

## 3. E.020 art. 19 — Combinaciones para diseño por esfuerzos admisibles

«Excepto en los casos indicados en las normas propias de los diversos materiales
estructurales»:

| Nº | Combinación |
|---|---|
| (1) | D |
| (2) | D + L |
| (3) | D + (W ó 0,70 E) |
| (4) | D + T |
| (5) | α [D + L + (W ó 0,70 E)] |
| (6) | α [D + L + T] |
| (7) | α [D + (W ó 0,70 E) + T] |
| (8) | α [D + L + (W ó 0,70 E) + T] |

Donde:
- D = carga muerta (cap. 2); L = carga viva (cap. 3); W = viento (art. 12); E = sismo según
  E.030; T = temperatura, contracción, deformaciones diferidas o asentamientos;
- **α** ≥ 0,75 para (5), (6) y (7), y ≥ 0,67 para (8). En estos casos no se permite aumentar
  los esfuerzos admisibles.

## 4. E.020 cap. 6 — Estabilidad

| Artículo | Disposición |
|---|---|
| 20.1 | La estabilidad requerida será suministrada **sólo por las cargas muertas** más la acción de los anclajes permanentes. |
| 20.2 | El peso de la tierra sobre las zapatas, calculado con el **peso unitario mínimo** de la tierra, **puede** considerarse parte de las cargas muertas. |
| 21 | Coeficiente de seguridad mínimo **1,5** contra el volteo, para la edificación o cualquiera de sus partes. |
| 22.1 | Coeficiente de seguridad mínimo **1,25** contra el deslizamiento. |
| 22.2 | Los coeficientes de fricción los establece el proyectista a partir de valores usuales de ingeniería. |

## 5. E.030 (2026), ya transcrito en `referencias_e060_e050.md`

- **Art. 29:** en verificaciones por esfuerzos admisibles, las fuerzas sísmicas se
  multiplican por 0,8.
- **Art. 62.2:** presiones del suelo con las fuerzas sísmicas multiplicadas por 0,8 según el
  art. 29.
- **Art. 64.2:** FS de volteo ≥ 1,2 con las fuerzas del análisis **sin** la reducción del
  art. 29.

---

## 6. Consecuencias para el proyecto (hallazgos; no decisiones)

| # | Hallazgo | Evidencia | Qué implica |
|---|---|---|---|
| H1 | **El nivel de la acción es un dato.** Sismo y viento tienen ecuaciones distintas según se entreguen a nivel de servicio o de resistencia | E.060 9.2.2, 9.2.3 | En el contrato de cargas (DL-2), cada caso CS o CVi declara su nivel |
| H2 | **Taxonomía verificada de casos:** CM, CV, CVi, CS, CE, CL, CT | E.060 9.2 | Cierra la parte normativa de DL-2 |
| H3 | **El peso propio es carga muerta** | E.020 art. 2 | El peso de zapatas y viga pertenece a CM (DL-4 para peso propio) |
| H4 | **El relleno tiene dos lecturas en las fuentes:** como carga muerta para estabilidad (E.020 20.2, con peso unitario mínimo) o como «peso de los suelos» CE con factor 1,7 (E.060 9.2.5) | E.020 20.2; E.060 9.2.5 | **Decisión del usuario** (DL-4 para el relleno). No se resuelve por suposición |
| H5 | **La estabilidad solo cuenta cargas muertas.** El motor calcula la fuerza estabilizante con la P **completa** de la combinación de servicio, que incluye carga viva, más el peso propio (`engine/soil/stability.py`) | E.020 20.1 | Puede **sobrestimar** la resistencia al volteo y al deslizamiento cuando hay carga viva: posible falso PASS en la estabilidad de la aislada. Corregirlo exige conocer la composición, es decir, el contrato de cargas |
| H6 | **Existe un FS normativo general:** volteo 1,5 y deslizamiento 1,25. El motor no tiene valor por defecto (NO VERIFICADO sin dato del usuario) y usa 1,2 solo en combinaciones sísmicas (E.030 64.2) | E.020 arts. 21 y 22 | **Decisión:** relación entre E.020 art. 21 (general) y E.030 art. 64.2 (sismo); si se adoptan como criterio. Afecta estados de aislada y a la estabilidad pendiente de la combinada |
| H7 | **Tres factores para el sismo a nivel de servicio:** E.020 art. 19 usa 0,70 E; E.030 art. 29 y E.060 15.2.5 usan 0,8 | E.020 19; E.030 29; E.060 15.2.5 | E.020 19 se declara subsidiaria («excepto en los casos indicados en las normas propias…»). **Decisión** sobre cuál rige para las presiones del suelo |
