# Práctica con ejercicios publicados (2026-09-29)

Tres ejercicios resueltos, buscados en la web, se pasaron por el programa **sin modificar el
motor**. Objetivo: contrastar la mecánica con referencias independientes y aprender dónde
el programa coincide, dónde difiere por la norma y dónde difiere por una decisión propia.

Los ejercicios en español (Scribd, Studocu, SlideShare) estaban detrás de un muro o no
traían números. Se usaron memorias abiertas y completas, dos de ellas **validadas por
StructurePoint** contra el libro de Wight:

| # | Tipología | Fuente | Norma del original |
|---|---|---|---|
| E1 | Aislada cuadrada | Wight, *Reinforced Concrete Mechanics and Design* 7.ª ed., ej. 15-2, resuelto por [StructurePoint](https://structurepoint.org/publication/pdf/Reinforced-Concrete-Square-Spread-Footing-Analysis-Design-ACI318-14.pdf) | ACI 318-14 |
| E2 | Combinada con columna de lindero | Wight, ej. 15-5, resuelto por [StructurePoint](https://structurepoint.org/pdfs/Reinforced-Concrete-Column-Combined-Footing-Analysis-Design.pdf) | ACI 318-14 |
| E3 | Conectada (*strap footing*) | [Structville, «Design of strap footing»](https://structville.com/2021/04/design-of-strap-footing-cantilever-footing.html) | EC2 |

**Cómo compararlos con justicia.** El programa admite combinaciones ya factorizadas (modo
directo), así que las cargas últimas del original entran tal cual y la mecánica se compara
sin mezclar factores de carga. Lo que sí difiere por norma se dice en cada caso: φ de
cortante (E.060 0,85; ACI 0,75), acero mínimo y coeficientes de Vc.

Scripts, ejecutables desde la raíz con `py -3 docs/practica/<archivo>.py`:
`e1_aislada_wight_15_2.py`, `e2_combinada_wight_15_5.py` (barrido), `e2_traza.py` (traza de
la geometría aunque se rechace), `e3_conectada_structville.py`.

---

## E1 — Aislada (Wight 15-2): la mecánica coincide

Datos: columna 18 in; D = 400 k, L = 270 k; f'c 3000 psi; fy 60 ksi; qa 6000 psf;
11 ft 2 in × 32 in. Cargas ACI, Pu = 912 k.

| Magnitud | Original | Programa |
|---|---|---|
| d promedio | 28 in | 0,714 m = 28,1 in |
| Punzonamiento Vu | 805 k | 3576 kN = 804 k |
| vu | 156 psi | 155 psi |
| vc (sin φ) | 219 psi | 218 psi |
| Cortante unidireccional Vu | 204 k | 905 kN = 203 k |
| Mu en la cara | 954 k·ft | 1293 kN·m = 954 k·ft |
| As por flexión | 7,76 in² | 49,86 cm² = 7,73 in² |

Diferencias **normativas**, no de cálculo: φvc = 0,85·vc en E.060 (185 psi) frente a
0,75·vc en ACI (164 psi); y el acero mínimo, que se trata en el hallazgo H1.

## E2 — Combinada (Wight 15-5): coinciden los números, difieren dos criterios

Datos: columna exterior 16 × 24 in al ras del lindero, interior 24 × 24 in; 20 ft entre
ejes (deducido: la zapata de 25 ft 4 in centra la resultante de servicio); D = 200/300 k,
L = 150/225 k; qa 5000 psf; 25 ft 4 in × 8 ft.

| Magnitud | Original | Programa |
|---|---|---|
| Punzonamiento interior Vu | 589 k | 2614 kN = 588 k |
| vu interior | 80,2 psi | 79 psi |
| Punzonamiento exterior Vu (h = 36 in) | 405,1 k | 1799 kN = 404 k |
| As negativo (h = 40 in) | 13,4 in² | 86,4 cm² = 13,39 in² |
| As positivo por flexión | 3,3 in² | 20,35 cm² = 3,15 in² |
| **Punzonamiento exterior, h = 36 in** | **vu = 192 psi > φvc: NO cumple** | **PASS, aprovechamiento 0,55** (hallazgo H2) |
| **Cortante longitudinal** | no se detalla | **FAIL**: Vu = 2009 kN > φVc = 1495 kN (hallazgo H3) |

## E3 — Conectada (Structville): la estática coincide exactamente

Datos: columnas 300 × 300 mm a 4 m; C1 con su eje a 0,30 m del lindero; 450/600 kN de
servicio, 617/822 kN últimas; zapata exterior 2,0 m (a lo largo de la viga) × 1,85 m.

| Magnitud | Original | Programa (ARTICULADO, equilibrio en la cimentación) |
|---|---|---|
| R1 servicio / última | 545,45 / 747,87 kN | 545,45 / 747,88 kN |
| R2 servicio / última | 504,55 / 691,23 kN | 504,55 / 691,12 kN |
| Momento negativo de la viga | 416,47 kN·m | 301,0 kN·m en el borde de la zapata (sección de diseño de la viga) |

- **R2 = 691,23 es una errata del original:** 617 + 822 − 747,87 = 691,13.
- **El 416,47 kN·m es incoherente con el propio ejemplo:** reconstruido a mano, sale de
  poner la columna al ras del lindero (s = 0,15 m), mientras que sus reacciones la ponen a
  0,30 m. Con la geometría coherente, el máximo dentro de la zapata es 324 kN·m.
- **No es un defecto del programa:** dentro de la zapata exterior el momento lo toma la
  losa de la zapata, cuya flexión en X se diseña con Mu = 449 kN·m (≥ 324); la viga se
  diseña en su vano libre (Fase 9b, documentado).
- El diseño con E.060 de esta geometría falla en la zapata exterior (cortante, punzonamiento
  y anclaje por 10 mm aun con gancho): los 400 mm de espesor venían del EC2.

**Lección:** una memoria publicada puede traer incoherencias internas. Aquí la reconstrucción
independiente las sacó a la luz; el programa no las copia porque calcula con una sola
geometría.

---

## Hallazgos que requieren decisión (no se modificó el motor)

### H1 — `fy = 4200 kg/cm²` activa la cuantía mínima de 0,0020, no la de 0,0018 · impacto alto

E.060 §9.7.2, literal: barras con «fy < 420 MPa» → 0,0020; «fy ≥ 420 MPa» → 0,0018. El motor
lo aplica al pie de la letra (`e060_concrete.py`, líneas 154-155). Pero la conversión exacta
del programa (CLAUDE.md §9 bis) hace que **4200 kg/cm² = 411,9 MPa < 420**. El acero peruano
de uso corriente, escrito como se escribe en el Perú, recibe la cuantía del acero de grado
inferior. Medido en E1: 49,80 cm² con 420 MPa frente a **55,33 cm² con 4200 kg/cm²** (+11 %).
Lo mismo pasa con 60 ksi (413,7 MPa).

Va del lado seguro, pero cambia cómo se interpreta la entrada: ¿el umbral de §9.7.2 designa
un **grado** de acero (el de 4200 kg/cm² y el de 420 MPa son el mismo) o un número? Opciones:
(a) dejarlo literal y avisar en la traza; (b) declarar el grado del acero como dato;
(c) una tolerancia de conversión con justificación escrita. **Decisión del proyectista.**

### H2 — Punzonamiento en columnas de borde y esquina: falta la excentricidad del cortante · posible lado inseguro

En E2 la columna exterior tiene una sección crítica de 3 lados cuyo centroide no coincide
con el eje de la columna. El original (ACI R8.4.4.2.3, Wight) toma el momento de la reacción
respecto de ese centroide (Munb = 579 k·ft) y con h = 36 in **falla** (vu = 192 psi, más
que el φvc de E.060, 186 psi). El motor solo aplica §11.12.7 cuando hay momento **de la
columna** (`punching_shear.py`, `has_moment`) y da PASS con 0,55.

E.060 §11.12.7.1 dice que el momento no balanceado se transfiere «alrededor del centroide de
la sección crítica», pero no dice si la carga axial excéntrica respecto de ese centroide
genera por sí sola un momento no balanceado. Es un punto de **interpretación**, no una lectura
literal. Afecta a toda columna de borde o esquina: aislada de lindero, combinada y zapata
exterior de la conectada. Recomiendo tratarlo como decisión prioritaria (CLAUDE.md §3), con
diff por caso sobre los congelados 16–18, K y Z.

### H3 — Cortante longitudinal de la combinada con máx |V| en vez de a d de la cara · conocido

Ya documentado en `docs/auditoria_cv_cortante_longitudinal_combinada.md` como desviación
conservadora. El ejercicio mide su efecto: a d de la cara de la columna interior el cortante
es 307,5 k = 1368 kN, que pasa (φVc = 1495 kN); con máx |V| (451,6 k = 2009 kN) la combinada
de libro se **rechaza**. Reconstrucción a mano: w = 1200/25,33 = 47,37 k/ft;
V(19,67 ft) = 451,6 k; V(16,63 ft) = 307,5 k. Si se reabre C-V, este es un caso de prueba.

---

## Lo que se aprendió

1. En E1 y E2, lo que no depende de la norma (Vu, vu, Mu, As, d) coincide con las referencias
   validadas en menos del 1 %. En E3, la estática de la viga coincide exactamente.
2. Las diferencias restantes se clasifican en tres clases, y conviene no confundirlas:
   - **normativas** (φ, acero mínimo);
   - **decisiones del programa**, documentadas (H3, sección de diseño de la viga);
   - **puntos abiertos** (H1, H2).
3. Comparar con ACI exige cuidado con φ: con cargas iguales, E.060 admite un 13 % más de
   cortante (0,85 / 0,75).
4. Una memoria publicada no es un oráculo. Structville trae una errata y una incoherencia de
   geometría; StructurePoint omite la separación entre ejes, que hay que deducir.
