# Pendiente 7 — estabilidad de la zapata combinada (análisis)

Fecha: 2026-09-18. Estado: **análisis; no implementado**. Requiere una decisión (§4).

---

## 1. El problema

La zapata combinada **no verifica deslizamiento ni volcamiento**. La aislada sí, en
`engine/soil/stability.py`, y la conectada lo hereda en cada una de sus zapatas.

La corrección D4 tapó el agujero de forma conservadora: si alguna combinación declara
fuerza horizontal, el resultado queda NO VERIFICADO con una entrada que lo dice
(`stability_not_implemented`). Antes salía **PASS en silencio** con 4000 kN de fuerza
horizontal por columna.

La decisión 6 hizo visible ese NO VERIFICADO —la alternativa se conserva y se rotula en vez
de descartarse—, pero **no lo resolvió**: el motor sigue sin poder pronunciarse.

## 2. Lo que ya está cerrado y se reutiliza

Nada de esto hay que decidirlo otra vez:

| Pieza | Dónde está | Qué aporta |
|---|---|---|
| Fuerza estabilizante = solo carga muerta | `stabilizing_axial_kN` (E.020 art. 20.1) | Con composición, N exacta; sin ella, cota superior y NO VERIFICADO si cumple |
| FS por defecto | `_fs_overturning_required`, `_fs_sliding_required` | Volteo 1,5 (E.020 art. 21); volteo sísmico 1,2 (E.030 art. 64.2, ver D10-2b); deslizamiento 1,25 (E.020 art. 22.1) |
| μ | `SoilProfile.mu_friction_soil_concrete` (E.020 art. 22.2) | Es dato del proyectista. Sin μ → NO VERIFICADO, nunca un valor inventado |
| Cargas de servicio | E.050 art. 17.1 | El FS se calcula con cargas sin amplificar |
| Punto de giro | Documentado en `stability.py` | Arista inferior del lado hacia el que actúa la resultante; empuje pasivo no considerado |
| Brazo de H | `h` de la zapata | Supone H transmitida en la base de la columna |
| Sin reducción sísmica | E.030 art. 64.2 | El 0,8 nunca entra en estabilidad (`CLAUDE.md` §9) |
| **Reducción de varias columnas a una resultante** | `solve_combined_footing`, bloque de presión de contacto | Ya resuelto y probado (ver §3) |

La última fila es la que hace que este pendiente sea abordable: **la combinada ya sabe
reducir sus columnas a una resultante**, porque lo necesita para la presión de contacto.

## 3. El modelo

Emparejamiento de combinaciones: por **nombre**, entre todas las columnas. Ya es
obligatorio —`CombinedFootingLayout` rechaza un layout cuyas columnas no declaren las
mismas combinaciones— y es lo que hace `_combo_by_name`.

Para cada combinación de servicio, el solver ya calcula, con P y M de **todas** las
columnas, respecto del centroide de la zapata:

```text
P_col  = Σ P_i
Mx_tot = Σ (Mx_i + P_i · offset_x_i)
My_tot = Σ (My_i + P_i · offset_y_i)
```

El término `P_i · offset_i` es el momento que produce cada carga por estar descentrada. Es
exactamente lo que el volcamiento necesita y lo que distingue a la combinada de la aislada,
donde la columna se supone en el centroide.

Añadiendo lo que falta:

```text
Hx_tot = Σ Hx_i        Hy_tot = Σ Hy_i        H = √(Hx_tot² + Hy_tot²)
W      = peso propio (concreto + relleno), engine/foundation/self_weight.py
```

**Deslizamiento**

```text
N   = Σ N_i,estab + W                 (N_i,estab por E.020 art. 20.1)
F   = μ·N  (+ c·A solo si se declara c)
FS  = F / H  ≥  FS_req
```

**Volcamiento en la dirección X** (análogo en Y):

```text
M_estab = N · B/2                     brazo del centroide a la arista
M_volc  = |Mx_tot| + |Hx_tot| · h
FS      = M_estab / M_volc  ≥  FS_req
```

Reduce exactamente a la fórmula de la aislada cuando hay una sola columna centrada.

## 4. La decisión que hace falta

**Qué N entra en `Mx_tot`.** El momento estabilizador usa **solo carga muerta** (E.020 art.
20.1). Pero `Mx_tot` lleva `P_i · offset_i` con el **P total** de la combinación, porque así
lo calcula hoy la presión de contacto. Mezclar las dos cosas no es neutro: la excentricidad
de una carga viva puede **aumentar o reducir** `|Mx_tot|`, y si la reduce, usar el P total
**subestima** el momento volcador.

Tres formulaciones defendibles:

**A — Reutilizar la resultante tal cual.** `M_volc` con el P total; `M_estab` con carga
muerta. Es lo más simple y reutiliza literalmente lo que ya está probado.
*Riesgo:* una excentricidad favorable de carga viva puede enmascarar un volcamiento. No es
conservador en todos los casos.

**B — Envolvente de las dos lecturas.** `M_volc = max(|Mx_tot con P total|, |Mx_tot con
solo CM|)`. Conservador en ambos sentidos y sigue sin necesitar maquinaria nueva.
*Riesgo:* la envolvente es un **criterio del programa**, no una exigencia normativa, y hay
que declararlo como tal.

**C — Descomponer por componente.** Separar `Mx_tot` en su parte de carga muerta y el resto,
y situar cada aporte en el lado —estabilizador o volcador— que le corresponde por su signo.
Es la lectura más fiel de E.020 art. 20.1.
*Coste:* exige composición (solo existe en modo por casos) y maquinaria nueva; en modo
directo hay que caer a A o B con el resultado NO VERIFICADO que ya prescribe
`E020_DEAD_LOAD_ONLY_NOTE`.

**Recomendación: B**, declarada explícitamente como criterio del programa, con **C** como
mejora posterior cuando haya composición. B nunca es menos seguro que A, no inventa ningún
coeficiente y se reconstruye a mano con facilidad para los tests.

**Efecto secundario a declarar:** la aislada seguiría usando `abs(Mx)` sin el término
`P·offset` (no contempla columna descentrada en estabilidad). La combinada quedaría con una
formulación **más exacta** que la aislada. Es una divergencia real entre tipologías y
debería registrarse como `KnownDifference` en vez de quedar implícita. Alinear la aislada
es trabajo aparte y **tocaría baselines congelados**.

## 5. Invariantes para los tests

1. Con una sola columna centrada, la combinada y la aislada dan el mismo FS.
2. Sin fuerza horizontal ni momento, la verificación no aplica y no degrada el estado.
3. Sin μ declarado → NO VERIFICADO, nunca PASS y nunca un μ supuesto.
4. Sin composición (modo directo) y cumpliendo → NO VERIFICADO (E.020 art. 20.1).
5. Duplicar H divide el FS de deslizamiento por dos.
6. Reconstrucción a mano de un caso de dos columnas, sin llamar al código que se prueba.
7. La entrada `stability_not_implemented` desaparece; nada más de la traza cambia.

## 6. Impacto

**Resultados:** cambia lo que hoy es NO VERIFICADO con H > 0. Pasará a PASS, FAIL o seguirá
NO VERIFICADO según haya μ y composición. Sin fuerzas horizontales ni momentos, nada cambia.

**Baselines:** los casos congelados de la combinada (K1–K4) no declaran fuerza horizontal
—`_col_comb` en `tests/freeze/cases.py` solo fija P y Mx—, así que **no deberían moverse**.
Se comprobará con dry-run y diff por caso antes de tocar nada, según `CLAUDE.md` §11.

**Capas:** motor (nuevo módulo de estabilidad combinada + traza), API (campos aditivos),
UI, memoria de cálculo, catálogo de tipologías (retirar `ESTABILIDAD_COMBINADA` marcándola
resuelta) y tests.

## 7. Qué necesito del usuario

1. **Elegir A, B o C** para el momento volcador (recomendado: B).
2. Confirmar que la divergencia con la aislada se **registra** y no se corrige ahora
   (corregirla tocaría baselines congelados).
3. Tener presente que el FS de volteo sísmico depende de **D10-2b**, hoy abierto: el motor
   usaría 1,2 (E.030 art. 64.2) salvo FS declarado por el proyectista.

---

# Resolución aplicada (2026-09-18)

**Decisión del usuario: opción B, la envolvente.** Implementado en
`engine/foundation/combined_stability.py`.

## Qué quedó implementado

La declaración D4 (`stability_not_implemented`) queda **sustituida por la verificación
real**. Con fuerza horizontal, la combinada ahora comprueba deslizamiento y volcamiento en
los dos ejes; sin ella no se añade nada.

**Lo que se reutiliza sin volver a decidirlo**, de `engine/soil/stability.py`, que sigue
siendo la única fuente del criterio:

- fuerza estabilizante = solo carga muerta, E.020 art. 20.1 (`stabilizing_axial_kN`);
- FS adoptados en D10-2b: **1,50** al deslizamiento y al volteo, también con sismo, como
  criterio del programa y no como cita normativa;
- μ es dato del proyectista (E.020 art. 22.2): sin μ, **NO VERIFICADO**;
- cargas de servicio (E.050 art. 17.1), punto de giro en la arista, empuje pasivo no
  considerado, brazo de H igual a `h`, sin reducción sísmica del 80 %.

**Lo que este pendiente añade:** la resultante de varias columnas y la envolvente.

```text
P_total  = Σ P_i
Mx_total = Σ (Mx_i + P_i·offset_x_i)      My_total = Σ (My_i + P_i·offset_y_i)
Hx_tot   = Σ Hx_i                          Hy_tot   = Σ Hy_i

M_volc  = max(|M_total|, |M_estabilizante|) + |H|·h        ← ENVOLVENTE (opción B)
M_estab = N_estabilizante · dim/2
FS      = M_estab / M_volc
```

`M_estabilizante` se arma con **el mismo conjunto de componentes** que `stabilizing_axial_kN`
usa para N —los CM más los aportes no muertos que restan carga vertical—, de modo que N y su
momento son coherentes. Sin composición (modo directo) las dos lecturas coinciden y rige la
regla de siempre: si cumple, NO VERIFICADO.

La envolvente es un **criterio del programa**, declarado como tal en `ENVELOPE_NOTE`: E.020
art. 20.1 dice qué estabiliza, no cómo tratar la excentricidad de lo que no estabiliza.

**Guardas añadidas al alcance:** un eje sin momento ni fuerza horizontal propios se declara
no aplicable en lugar de emitir un FS infinito, igual que hace la zapata aislada.

## Divergencia registrada — RESUELTA el 2026-09-19

Cuando se cerró el pendiente 7, la zapata aislada **no se tocó** (decisión del usuario):
seguía tomando |M| de la combinación, sin el término `P·offset` y sin envolvente. Quedó
registrada en el catálogo como `FORMULACION_VOLTEO`.

**Ya no es así.** El análisis posterior mostró que la aislada era incoherente consigo
misma —su presión de contacto ya usaba `ex = (M + P·offset)/(P + W)`— y el usuario aprobó
alinearlas. Las tres tipologías comparten hoy la formulación y un solo ayudante,
`engine.soil.stability.axis_moments_kNm`; este módulo ya solo añade la suma de varias
columnas en una resultante. Ver `docs/formulacion_volteo_analisis.md` y
`docs/freeze_formulacion_volteo.md`.

## Tests

`tests/test_combined_stability_pendiente7.py` (22 tests): reconstrucción a mano de la
resultante y de los dos FS, el caso que justifica la envolvente —una carga viva excéntrica
favorable que reduciría |M_total|—, μ ausente, modo directo frente a modo por casos, el FS
adoptado sin atribuírselo a la norma, la sustitución de D4 en el solver y la comprobación
de que la aislada no cambió.

**Ocho mutaciones deliberadas detectadas:** quedarse solo con la lectura total, olvidar el
momento de la excentricidad, usar la carga total como estabilizante, inventar μ, volver a
1,20 y a 1,25, dar por bueno un cumplimiento sin composición, y verificar también sin
fuerza horizontal.

## Capas

Motor (`combined_stability.py` y `combined_solver.py`), API (`stability` aditivo en cada
alternativa), memoria de cálculo (sección 8 nueva) y UI (tabla de FS por alternativa).
