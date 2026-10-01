# Fase 6 — Validación del motor contra referencias externas

Generado por `tests/validation/render_report.py` el 2026-09-14. Cada valor del motor se calculó al generar este documento; no hay cifras escritas a mano.

**36 de 36 comparaciones** dentro de su criterio (tolerancia contra la referencia, o valor documentado en el caso de una diferencia explicada).

Las referencias proceden de fuentes ya incorporadas al proyecto; la tolerancia es la que ya aceptaba el test de origen. En las tablas de benchmarks el criterio es la tolerancia absoluta y la diferencia relativa solo orienta; en la sección bibliográfica el criterio es la tolerancia relativa del arnés, con los ajustes que el propio arnés justifica en los supuestos del autor.

Alcance: estos benchmarks validan el reparto de la conectada (P1, P2), la estática de la viga en el modelo articulado con par puro (P1), la presión de la combinada (§3.5) y las verificaciones de la zapata aislada (golden cases y §3.4.1). **No hay referencia externa numérica para la viga en cuerpo rígido**: sus diagramas en los apuntes (figuras 81 y 87–90) son imágenes. Esa parte se valida por derivación independiente en `tests/test_connected_beam_statics_phase5a.py`.

## Aragón, problema 1 — conectada, articulado con par puro

Fuente: Apuntes CR2-93-134 §3.6, problema de aplicación 1. Test de origen: `tests/test_connected_statics_phase4a.py`.

| Id | Magnitud | Referencia | Motor | Diferencia | Dif. rel. | Tolerancia | Estado |
|---|---|---|---|---|---|---|---|
| P1-Mpar-grav | Momento del par (gravedad) | -32.75 | -32.7500 | +0.0000 | 0.000 % | ± 0.02 t·m | reproduce |
| P1-dP-grav | Transferencia ΔP (gravedad) | 5.45 | 5.4583 | +0.0083 | 0.153 % | ± 0.02 t | reproduce |
| P1-Mpar-sismo+ | Momento del par (sismo +) | 57.25 | 57.2500 | -0.0000 | 0.000 % | ± 0.02 t·m | reproduce |
| P1-dP-sismo+ | Transferencia ΔP (sismo +) | 9.54 | 9.5417 | +0.0017 | 0.017 % | ± 0.02 t | reproduce |
| P1-Mpar-sismo- | Momento del par (sismo −) | -122.75 | -122.7500 | -0.0000 | 0.000 % | ± 0.02 t·m | reproduce |
| P1-dP-sismo- | Transferencia ΔP (sismo −) | 20.45 | 20.4583 | +0.0083 | 0.041 % | ± 0.02 t | reproduce |
| P1-Vu-viga | Vu de la viga (1,25·V) | 25.6 | 25.5729 | -0.0271 | 0.106 % | ± 0.1 t | reproduce |
| P1-Mu-eje | Mu⁻ de la viga en el eje (1,25·M) | 153.4 | 153.4375 | +0.0375 | 0.024 % | ± 0.2 t·m | reproduce |
| P1-Mu-cara | Mu⁻ de la viga a la cara de la columna | 140.6 | 147.0443 | +6.4443 | 4.583 % | ± 0.2 t·m | diferencia documentada |

- **P1-Mu-cara** — El motor da 147,0 t·m. El libro mide el brazo desde el lindero: 153,4·(1 − 0,50/6,00) = 140,6. Es otra convención de cuerpo libre, no un error; se decidió no adoptarla (decisión cerrada en 4D).

## Aragón, problema 2 — conectada, cuerpo rígido

Fuente: Apuntes CR2-93-134 §3.6, problema de aplicación 2. Test de origen: `tests/test_connected_rigid_body_phase4c.py`.

| Id | Magnitud | Referencia | Motor | Diferencia | Dif. rel. | Tolerancia | Estado |
|---|---|---|---|---|---|---|---|
| P2-A | Área de apoyo (geometría final) | 32.46 | 32.4600 | +0.0000 | 0.000 % | ± 0.005 m² | reproduce |
| P2-I | Inercia de la sección compuesta | 320.36 | 320.3585 | -0.0015 | 0.000 % | ± 0.05 m⁴ | reproduce |
| P2-smin-CMCV | σ mín, CM+CV | 8.14 | 8.0705 | -0.0695 | 0.854 % | ± 0.1 t/m² | reproduce |
| P2-smax-CMCV | σ máx, CM+CV | 11.63 | 11.7119 | +0.0819 | 0.705 % | ± 0.15 t/m² | reproduce |
| P2-smin-CS+ | σ mín, CM+CV+CS | 5.01 | 5.0695 | +0.0595 | 1.187 % | ± 0.1 t/m² | reproduce |
| P2-smax-CS+ | σ máx, CM+CV+CS | 14.96 | 14.8661 | -0.0939 | 0.628 % | ± 0.15 t/m² | reproduce |
| P2-smin-CS- | σ mín, CM+CV−CS | 1.32 | 1.2749 | -0.0451 | 3.419 % | ± 0.1 t/m² | reproduce |
| P2-smax-CS- | σ máx, CM+CV−CS | 18.25 | 18.3544 | +0.1044 | 0.572 % | ± 0.15 t/m² | reproduce |
| P2-smax-predim | σ máx del predimensionamiento (se rechaza) | 18.91 | 18.9431 | +0.0331 | 0.175 % | ± 0.1 t/m² | reproduce |

## Aragón §3.5 — zapata combinada

Fuente: Apuntes CR2-93-134 §3.5, zapata combinada (referencia ajustada por el peso propio declarado). Test de origen: `tests/test_combined_footing_phase2.py`.

| Id | Magnitud | Referencia | Motor | Diferencia | Dif. rel. | Tolerancia | Estado |
|---|---|---|---|---|---|---|---|
| K35-qmax | q máx de servicio | 1.53041 | 1.5319 | +0.0015 | 0.100 % | ± 0.0153041 kg/cm² | reproduce |

## Golden cases — zapata aislada, cálculo a mano

Fuente: Golden case: cálculo a mano en el docstring (caso 03). Test de origen: `tests/golden_cases/test_case_03_biaxial_moment.py`.

| Id | Magnitud | Referencia | Motor | Diferencia | Dif. rel. | Tolerancia | Estado |
|---|---|---|---|---|---|---|---|
| G03-W | Peso propio total | 197.568 | 197.5680 | -0.0000 | 0.000 % | ± 0.000197568 kN | reproduce |
| G03-qmax | q máx (flexión biaxial) | 127.241 | 127.2408 | -0.0002 | 0.000 % | ± 0.0127241 kPa | reproduce |
| G03-qmin | q mín (flexión biaxial) | 50.71 | 50.7102 | +0.0002 | 0.000 % | ± 0.005071 kPa | reproduce |
| G06-bo | Perímetro crítico bo | 2.8238 | 2.8238 | +0.0000 | 0.000 % | ± 0.00028238 m | reproduce |
| G06-Vu | Vu de punzonamiento | 1369.1 | 1369.0542 | -0.0458 | 0.003 % | ± 1.3691 kN | reproduce |
| G06-phiVc | φVc de punzonamiento | 1110.5 | 1110.5213 | +0.0213 | 0.002 % | ± 1.1105 kN | reproduce |
| G08-Vu | Vu de cortante unidireccional | 1708.35 | 1708.3500 | +0.0000 | 0.000 % | ± 1.70835 kN | reproduce |
| G08-phiVc | φVc de cortante unidireccional | 1374 | 1373.9949 | -0.0051 | 0.000 % | ± 1.374 kN | reproduce |
| G08-qmax | q máx | 248.62 | 248.6222 | +0.0022 | 0.001 % | ± 0.24862 kPa | reproduce |

## Bibliografía — ARAGON-3.4.1

Fuente: Aragón Brousset, John P. «Concreto Armado 2», sección 3.4.1 «Problema de aplicación», diseño de zapata aislada.. Arnés: `tests/validation/reference_cases.py`.

| Caso | Magnitud | Libro | Motor | Dif. rel. | Tolerancia | Estado |
|---|---|---|---|---|---|---|
| ARAGON-3.4.1 | d (m) | 0.5 | 0.5061 | 1.23 % | 5 % | reproduce |
| ARAGON-3.4.1 | Mu X (kN·m) | 1071 | 994.3451 | 7.14 % | 9 % | reproduce |
| ARAGON-3.4.1 | Mu Y (kN·m) | 928.2 | 871.3590 | 6.12 % | 9 % | reproduce |
| ARAGON-3.4.1 | As X (cm²) | 60 | 55.0695 | 8.22 % | 10 % | reproduce |
| ARAGON-3.4.1 | As Y (cm²) | 51.7 | 48.0177 | 7.12 % | 9 % | reproduce |
| ARAGON-3.4.1 | Vu cortante (kN) | 872.8 | 887.3109 | 1.66 % | 5 % | reproduce |
| ARAGON-3.4.1 | Vu punzonamiento (kN) | 2373 | 2185.5240 | 7.91 % | 9 % | reproduce |
| ARAGON-3.4.1 | φVc punzonamiento (kN) | 2433 | 2464.1555 | 1.28 % | 5 % | reproduce |

Supuestos del autor declarados:
- CONVENCIÓN: coincide con la del motor desde la migración de ejes. El Mx del libro (que el propio libro define como momento ALREDEDOR DE Y en el título de su sección de diseño) es el Mx del motor. No se traduce nada.
- El libro adopta d = 50 cm plano para h = 60 cm. El motor calcula el d REAL de cada capa a partir del recubrimiento y del diámetro seleccionado, que es menor.
- El libro estima el peso propio como 10% de (CM+CV) y NO incluye el peso del relleno de suelo sobre la zapata. El motor sí lo incluye.
- En el cortante unidireccional el libro calcula Vc con h = 60 cm en vez de d = 50 cm: escribe Vc = 0,53·√210·340·50 pero reporta 156,7 ton, que corresponde a usar 60. Con d el valor correcto es 130,6 ton. MANDA LA NORMA.
- En punzonamiento el libro toma Vu = Pu completo (242 ton) sin descontar la reacción del suelo dentro del perímetro crítico. El motor sí la descuenta, de modo que su Vu es menor. El libro es conservador en este punto.
- El libro NO aplica §11.12.6 (transferencia de momento en punzonamiento). El motor sí. MANDA LA NORMA.
- Las fuerzas sísmicas del enunciado están en condición ÚLTIMA; para las combinaciones de servicio el libro las divide entre 1,25.
