# D10-2b — factores de seguridad al volteo y al deslizamiento

Fecha del análisis: 2026-09-18. **Cerrado el 2026-09-18 por decisión del usuario.**

---

## 1. Resumen de la decisión

| Verificación | Valor en la fuente | **Valor adoptado por el programa** | Relación |
|---|---|---|---|
| Volteo, sin sismo | 1,50 — E.020 art. 21 | **1,50** | coincide |
| Volteo, con acción sísmica | 1,20 — E.030 art. 64.2 | **1,50** | **más estricto** |
| Deslizamiento | 1,25 — E.020 art. 22.1 | **1,50** | **más estricto** |

**1,50 es un criterio de diseño adoptado por el proyecto, no una exigencia textual de la
norma.** En dos de los tres casos la norma pide menos. El motor lo dice con esas palabras
en la traza, en la referencia normativa de cada verificación y en la memoria de cálculo.

Un FS declarado por el proyectista sustituye siempre al adoptado.

## 2. La pregunta original

Dos artículos de dos normas vigentes daban un factor distinto, y ninguno de los dos textos
decía cuál manda cuando ambos podrían aplicarse.

**E.020, artículo 21 — VOLTEO** (texto íntegro):

> La edificación o cualquiera de sus partes, será diseñada para proveer un coeficiente de
> seguridad mínimo de 1,5 contra la falla por volteo.

No distingue el tipo de carga que produce el volteo.

**E.030 (2026), artículo 64.2:**

> El factor de seguridad calculado con las fuerzas que se obtienen en el análisis
> estructural, sin considerar la reducción establecida en el artículo 29 de la presente
> Norma Técnica, debe ser mayor o igual que 1,2.

Es específico del momento de volteo que produce el sismo (art. 64.1).

**E.020, artículo 22.1:** coeficiente de seguridad mínimo de **1,25** contra el
deslizamiento. **Art. 22.2:** los coeficientes de fricción los establece el proyectista.

## 3. Cómo se cerró

El usuario aportó `docs/benchmark/Apuntes CR2-135-169.pdf` (Aragón, muros de sostenimiento),
que pide FS ≥ 1,5 al deslizamiento y ≥ 1,5 al volteo, y **decidió adoptar 1,50 en los tres
casos** como criterio del programa.

Lo que esos apuntes **no** son, y así se registró antes de decidir:

1. **No son fuente normativa.** `CLAUDE.md` §1: los apuntes de Aragón son benchmark. De
   ellos no se toma ningún factor ni criterio de cálculo.
2. **No tratan el caso en disputa.** Los valores 1,5 / 1,5 se aplican a empuje de suelo
   **estático** (Rankine). En todo el capítulo no hay una sola combinación sísmica.
3. **Adoptarlos cambia también el deslizamiento**, donde E.020 art. 22.1 sí da un número
   distinto (1,25).

Por eso el valor adoptado **no se apoya** en los apuntes ni se presenta como normativo: es
una decisión de proyecto, más conservadora que la norma, y así queda registrada. El aporte
de los apuntes fue motivar la decisión, no fundamentarla normativamente.

## 4. Implementación

En `engine/soil/stability.py`:

- se **conservan** los valores normativos, que siguen siendo citables y comprobables:
  `E020_FS_OVERTURNING = 1.50`, `E020_FS_SLIDING = 1.25`,
  `E030_FS_OVERTURNING_SEISMIC = 1.20`;
- se añaden los **adoptados**, con nombre que no admite confusión:
  `PROGRAM_FS_OVERTURNING`, `PROGRAM_FS_OVERTURNING_SEISMIC`, `PROGRAM_FS_SLIDING`, todos
  1,50, y la nota `D10_2B_ADOPTED_NOTE`;
- `_fs_overturning_required` y `_fs_sliding_required` devuelven el adoptado y **la
  procedencia**, que viaja a la traza. Por ejemplo, con sismo:

  > FS 1,50: criterio del programa (D10-2b), **más estricto que E.030 art. 64.2, que exige
  > 1,20**

Alcance: la zapata aislada, las zapatas de la conectada y —desde el pendiente 7— la zapata
combinada, porque todas resuelven el FS por la misma función.

## 5. Efecto en los resultados

Solo cambia **el FS exigido**, no ninguna otra magnitud. Casos afectados: los que declaran
fuerza horizontal o combinación sísmica. Ver la sección de baselines en
`docs/estado_proyecto.md`.

## 6. Lo que sigue siendo cierto

- La reducción sísmica del 80 % **nunca** entra en la estabilidad (E.030 art. 64.2 lo exige
  expresamente y `CLAUDE.md` §9 lo recoge).
- μ sigue siendo dato del proyectista (E.020 art. 22.2). Sin μ: **NO VERIFICADO**, nunca un
  valor supuesto.
- La estabilidad la suministra **solo la carga muerta** (E.020 art. 20.1).
