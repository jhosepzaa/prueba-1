# Auditoría C-V — Cortante longitudinal en la zapata combinada

Fecha: 2026-09-17. Tipo: auditoría (CLAUDE.md §17), con resolución aplicada el mismo día (ver al final). Baselines sin cambios.

## Hallazgo

`shear_longitudinal` (Vu ≤ φVc con Vc = 0,17·√f'c·bw·d) queda en FAIL cuando el concreto solo no
basta. A continuación el solver dimensiona estribos (`shear_reinforcement`), pero la entrada del
concreto conserva su FAIL, y con la aceptación PASS_OR_INFO la geometría se descarta aunque los
estribos «cumplan». El comentario del solver declara la intención contraria («Antes de la Fase 3
esto se descartaba sin más; ahora se dimensiona»).

## Evidencia normativa (E.060, propuesta 2019)

| Artículo | Contenido | Consecuencia |
|---|---|---|
| §15.5.1 | Cortante de zapatas según §11.12, comportamiento §11.12.1.1 y §11.12.1.2 | — |
| §11.12.1.1 | Comportamiento como viga: diseñar según §11.1 a §11.5 | Vn = Vc + Vs es admisible |
| §11.1.1, ec. 11-1 y 11-2 | φVn ≥ Vu, Vn = Vc + Vs | «Vu > φVc» no es por sí solo inviabilidad |
| §11.5.6.1(a) | Zapatas exentas del Av mínimo | exime del mínimo, no del Vs requerido |
| §11.5.7.9 (en el motor) | Vs ≤ 0,66·√f'c·bw·d | límite real de la sección con estribos |
| §11.12.3 | Refuerzo de cortante en losas y zapatas con d ≥ 150 mm y d ≥ 16·db del estribo | condición de uso |
| §11.12.3.1–3.4 | Vc ≤ 0,17·√f'c·bo·d, **Vn ≤ 0,5·√f'c·bo·d**, líneas periféricas alrededor de la columna | redactado para acción en dos direcciones; su alcance sobre la acción de viga es interpretable |
| §15.5.2 y §11.1.3.1 | Sección crítica medida desde las secciones de §15.4.2; se permite diseñar con Vu a d de la cara | el motor no usa esta sección |

Conclusión normativa: la norma **no** exige descartar cuando Vu > φVc; admite estribos. La
sección solo es definitivamente inviable si Vs excede su máximo (o Vn el tope que se adopte) o si
no se cumplen las condiciones de §11.12.3.

## Evidencia en el motor

1. **Secuenciación:** la entrada del concreto solo sigue en FAIL tras dimensionar estribos → filtro
   de concreto solo de hecho.
2. **Estribos no creíbles para una zapata ancha:** `check_beam_shear` se llama con bw = ancho total
   (3,0–4,4 m) y 2 ramas fijas; la separación entre ramas es el ancho completo. No se diseña el
   número de ramas ni su separación transversal. Un PASS de `shear_reinforcement` no demuestra un
   armado constructible.
3. **§11.12.3 incompleto:** no se verifica d ≥ 16·db ni el tope Vn ≤ 0,5·√f'c·b·d; el caso d < 150 mm
   escribe un motivo pero deja la entrada en PASS.
4. **Sección crítica:** Vu = máx |V| de todo el diagrama, con las columnas como cargas puntuales en
   su eje: no se toma a d de la cara (§15.5.2 / §11.1.3.1). Conservador, pero distinto de la norma.

## Impacto medido (barridos de la Fase 2, sin tocar el motor)

| Barrido | Descartes | Con `shear_longitudinal` FAIL | …como ÚNICA causa | Plantas cuya h aceptada cambiaría si contaran los estribos |
|---|---|---|---|---|
| q = 147,1 kPa, h 0,40–0,90 / 0,10 | 117 | 94 | **0** | 0 |
| q = 147,1 kPa, h 0,30–0,90 / 0,05 | 255 | 214 | **1** | 1 (L×B 7,2×4,2: h 0,70 → 0,65; «2 ramas» sobre 4,2 m) |

Los 94/117 no se deben a C-V: todas esas geometrías fallan además otra verificación. Hoy C-V casi
no cambia el resultado del optimizador; el caso que sí cambia lo haría con un armado de estribos no
constructible.

## Veredicto

- C-V **no** es un filtro definitivo respaldado por la norma: es un criterio de concreto solo, más
  estricto que E.060.
- Relajarlo **no** es una corrección segura: el diseño de estribos existente no es un diseño válido
  para una zapata ancha, y quedan interpretaciones abiertas (§11.12.3 en acción de viga, sección
  crítica).
- Se deja intacto. Requiere decisión (ver estado del proyecto).

---

## Resolución aplicada (2026-09-17)

Decisión del usuario: que el comportamiento del motor coincida con el criterio declarado, **sin**
implementar Vc + Vs y sin tocar la sección crítica, §11.12.3 ni otros criterios.

### 1. Criterio actual del programa: concreto solo

- `shear_longitudinal`: Vu = máx |V| del diagrama; φVc = 0,85·0,17·√f'c·b·d (E.060 §11.3.1.1);
  **Vu > φVc → FAIL** y la geometría se descarta (aceptación PASS_OR_INFO).
- Motivo escrito explícito (categoría «Cortante longitudinal:»), registrado como
  `shear_longitudinal / concreto_solo`.
- Hipótesis `CONCRETE_ONLY_SHEAR_CRITERION` en la traza.
- Se retiró el dimensionamiento de estribos que seguía al FAIL: no intervenía en ninguna decisión
  y sugería que el motor contaba con Vs. `CombinedFootingResult.shear_reinforcement` se conserva
  por contrato y vale siempre `None`.

### 2. Diferencia respecto de E.060

El criterio es **más estricto que la norma**. E.060 §11.12.1.1 remite el comportamiento como viga
a §11.1–11.5 (Vn = Vc + Vs) y §11.12.3 admite refuerzo de cortante en zapatas. El programa **no**
afirma que la norma prohíba continuar con estribos: afirma que no los implementa.

### 3. Posibilidad futura: Vn = Vc + Vs

Requiere, antes de aceptar una geometría con refuerzo:
- diseño del refuerzo a lo ancho: número de ramas y separación transversal;
- límite Vs ≤ 0,66·√f'c·b·d (§11.5.7.9) y, si se adopta, Vn ≤ 0,5·√f'c·b·d (§11.12.3.2);
- condiciones d ≥ 150 mm y d ≥ 16·db (§11.12.3);
- que la entrada del concreto deje de descartar solo cuando el refuerzo esté verificado.

### 4. Pendientes normativos de la auditoría (abiertos)

- Alcance de §11.12.3 (y de su tope 0,5·√f'c·b·d) sobre el comportamiento como viga.
- Sección crítica: hoy máx |V| del diagrama con columnas puntuales; §15.5.2 y §11.1.3.1 permiten
  tomar Vu a d de la cara (hoy conservador).
- Implementación de Vc + Vs (punto 3).

### Verificación

- Huella de C-V en tres barridos (A, B, C: 534 geometrías): estados, aceptación, Vu, φVc y resto de
  la traza **idénticos** antes y después.
- Instantánea completa de los 49 casos congelados idéntica; baselines sin cambios.
- `tests/test_combined_shear_concrete_only_cv.py`: estribos fuera de la aceptación, recuentos y
  aceptadas iguales a los previos, φVc a mano, sin falsos PASS (caso 7,2 × 4,2 × 0,65 sigue FAIL).
  Mutaciones detectadas: rescate del FAIL por un Vs ficticio y motivo explícito omitido.
