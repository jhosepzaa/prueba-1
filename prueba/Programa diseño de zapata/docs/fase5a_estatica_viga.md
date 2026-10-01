# Fase 5A — D1 y D3: coherencia de modelo y estática de la viga de conexión

Registro escrito **antes** de modificar el motor. Fija qué se calculaba, qué debe
calcularse, sobre qué cuerpo libre, y qué resultados cambian y por qué.

Referencia conservada antes de editar:

| Archivo | sha256 (24) |
|---|---|
| `tests/freeze/baseline.json` | `0b2437648d89ef5a1789c28c` |
| `tests/freeze/baseline_connected.json` | `a52f813b1e64806598c31fbd` |

---

## Convenciones (las del propio motor, no se cambian)

- Coordenada `s`: origen en el borde de lindero, positiva hacia el interior.
- Fuerzas positivas hacia **arriba**.
- `FreeBody` (reparto): `Σ (s_i − s_c)·F_up + Σ M_app = 0`, momentos antihorarios +.
- Viga (`connecting_beam_statics`): porción **izquierda** de la sección,
  `V(s) = Σ F_up`, `M(s) = Σ F_up·(s − s_i)`, positivo = tracción abajo.
- E.050 art. 28.1: `ex = Mx/Q`; un momento positivo desplaza la resultante hacia +x.
- Conversión existente: `applied_moment_in_free_body(M) = −M`.

### Derivación del término de momento de columna en la viga

Equilibrio de la porción izquierda respecto de `s`, en la convención `FreeBody`:

    Σ (s_i − s)·F_up  +  M_app_fb  +  M_int_fb  =  0

Con `M_viga(s) = −Σ (s_i − s)·F_up` y `M_app_fb = −M_E050`:

    M_viga(s) = Σ F_up·(s − s_i)  +  M_E050        para s > a

Comprobación independiente: con esta expresión la rótula del modelo articulado cierra
(`M(s_cut) = 0`) en Z13, donde hoy da −420 kN·m.

---

## D1 — `CUERPO_RIGIDO × PAR_PURO_EN_ZAPATA`

**Decisión aprobada: (a1).** `CoupleTransferMode` sigue obligatorio. En
`CUERPO_RIGIDO` solo `EQUILIBRIO_EN_CIMENTACION` es aplicable; `PAR_PURO_EN_ZAPATA` se
rechaza por validación.

**Por qué (derivación, nivel B).** `PAR_PURO_EN_ZAPATA` se define por `R_ext = P_ext`
y por que la carga no se conserva en la cimentación. `CUERPO_RIGIDO` es un sistema
estáticamente determinado —campo lineal fijado por ΣF y ΣM globales— que conserva la
carga. Imponer `R_ext = P_ext` es una ecuación de más: las dos hipótesis se excluyen.

**Dónde se rechaza.** En el validador de `ConnectedFootingLayout` y, porque
`model_copy(update=…)` de pydantic v2 no ejecuta validadores, también a la entrada de
`distribute_couple` y de `solve_connecting_beam`. Una sola función de comprobación,
llamada desde los tres puntos.

**Resultado.** Ningún número del dominio válido cambia. La combinación pasa a error.
Desaparece el mecanismo M3.

---

## D3 — Estática de la viga de conexión

### Cuerpo libre

Porción a la izquierda de la sección `s`. Regiones:

| Región | Tramo | Carga sobre la viga |
|---|---|---|
| 1 | `0 ≤ s ≤ L1` | reacción del terreno bajo la zapata exterior, menos su peso propio |
| — | `s = a` | carga `P_ext` hacia abajo y momento de columna `M_E050` |
| 2 | `L1 < s ≤ s_cut` | ninguna (salvo peso propio de viga `EXPLICITO`, repartido) |

La comparación cruzada se evalúa en `s_cut` (eje de la columna interior), que es la
sección donde el reparto calcula `M_cut_kNm` sobre el **mismo** cuerpo:
{huella exterior + cargas a la izquierda del eje}.

### Ecuaciones actuales

**Articulado, `EQUILIBRIO_EN_CIMENTACION`:**

    w = R_ext / L1                         (R_ext neto; presión uniforme por H2)
    V(s) = w·min(s, L1) − P_ext·H(s − a) − W_viga·…
    M(s) = w·x·(s − x/2) − P_ext·(s − a)·H(s − a) − …,     x = min(s, L1)
                                           ← falta M_E050          [M2]

**Cuerpo rígido, `EQUILIBRIO_EN_CIMENTACION`:** las MISMAS ecuaciones, con

    w = R_ext / L1                         ← R_ext BRUTO (incluye W_ext)   [M1]
                                           ← presión uniforme, no trapecial [M1]
                                           ← falta M_E050                   [M2]

**Cuerpo rígido, `PAR_PURO_EN_ZAPATA`:** cuerpo libre de par puro con rótula
articulada, `V = −M_par/S`, `M(s) = M_par·(1 − (s − a)/S)`.     [M3]

**Comprobación cruzada:** `cut_moment_consistent` se calcula y ningún código la lee.

### Ecuaciones corregidas

**Articulado, `EQUILIBRIO_EN_CIMENTACION`** — se añade solo M2:

    M(s) = w·x·(s − x/2) − P_ext·(s − a)·H(s − a) + M_E050·H(s − a) − (viga)

`w = R_ext/L1` se mantiene: en el modelo articulado `R_ext` ya es neto y la presión es
uniforme por hipótesis. Tramo de diseño sin cambios: `[L1, s_cut]`.

**Cuerpo rígido** — campo real y carga neta:

    p(s) = p₀ + p₁·(s − x_c)        de _rigid_pressure(footprints, P_total, M_origen)
    q(s) = B_ext·p(s) − W_ext/L1    carga neta por metro sobre la huella exterior

    Q(x)  = ∫₀ˣ q dt  = B_ext·[p₀·x + p₁·((x − x_c)² − x_c²)/2] − (W_ext/L1)·x
    Qₛ(x) = ∫₀ˣ t·q dt = B_ext·[p₀·x²/2 + p₁·(x³/3 − x_c·x²/2)] − (W_ext/L1)·x²/2

    V(s) = Q(x) − P_ext·H(s − a) − (viga)
    M(s) = s·Q(x) − Qₛ(x) − P_ext·(s − a)·H(s − a) + M_E050·H(s − a) − (viga)
                                                                    x = min(s, L1)

`P_total` y `M_origen` se ensamblan desde el reparto con las mismas cargas que usa
`_distribute_rigid_body`. La integración usa primitivas distintas de las de
`_integrate_footprint`: es lo que hace que la comparación con `M_cut_kNm` sea una
comprobación **independiente** y no una tautología.

**Tramo de diseño en rígido: `[L1, s_fin]`**, con `s_fin` = inicio de la huella
interior. Consecuencia directa de M1: entre `s_fin` y `s_cut` el cuerpo está sobre la
zapata interior, cuya presión real no pertenece a la viga. Seguir hasta `s_cut` con
carga nula no sería «el campo de presión real». En el modelo articulado el tramo no
cambia: la rótula en `s_cut` es la hipótesis del modelo.

**Comprobación cruzada integrada.** La entrada de traza `beam_statics_<combo>` pasa de
`INFO` fijo a `INFO` si `cut_moment_consistent`, `FAIL` con motivo de descarte si no.
Sigue el precedente del cierre del reparto (`El equilibrio de la combinación … no
cierra`). No se añade ninguna entrada nueva: los casos consistentes no cambian de traza.

### Resultados que cambian y por qué

Solo cambian valores de VIGA (`beam.*`, `beam_statics.*`, entrada
`beam_statics_<combo>` de la traza). El reparto y las dos zapatas no dependen de la
estática de la viga y no deben moverse.

| Caso | Mecanismo | Vu antes → real | Mu⁻ antes → real | Mu⁺ antes → real |
|---|---|---|---|---|
| Z3 rígido | M1 | 325,49 → 169,97 | 567,01 → 722,45 | 816,30 → 0 |
| Z4 rígido + par puro | M3 (D1) | — | — | pasa a **rechazo** |
| Z12 Aragón P2 | M1, M2 | 272,30 → 86,00 | 665,07 → 775,96 | 587,49 → 0 |
| Z13 articulado + M_col | M2 | 90,00 → 90,00 | 802,50 → 382,50 | 0 → 0 |
| Z14 rígido + M_col | M1, M2 | 249,55 → 94,03 | 642,95 → 388,00 | 417,62 → 0 |

«Real» es la reconstrucción independiente de la Fase 5A, validada contra el
`M_cut_kNm` del reparto a la última cifra impresa.

Casos donde la viga ya era correcta y **no deben cambiar**: Z1, Z1b, Z2, Z5, Z6, Z7,
Z8, Z11 (todos con `cut_moment_consistent = True`), las negativas Z9 y Z10, y los
micro-barridos ZB1–ZB3.

### Fuera de alcance, observado y no corregido

- El peso propio de viga `EXPLICITO` se reparte sobre `[L1, s_cut]`, que incluye la
  mitad de la zapata interior ya contada en su propio peso. Ningún caso rígido
  congelado usa `EXPLICITO`. Queda anotado.
- En el reparto, un motivo de descarte añadido a `motivos` sin una entrada `FAIL` no
  descarta la alternativa (el estado global sale de la traza). Precedente preexistente.

---

## Resultado de la implementación

Escrito después de implementar. Los valores «después» coinciden con la reconstrucción
independiente de arriba en todas las cifras impresas.

| Caso | Vu antes → después | Mu⁻ antes → después | Mu⁺ antes → después | contraste |
|---|---|---|---|---|
| Z3 | 325,49 → 169,97 | 567,01 → 722,45 | 816,30 → 0 | False → True |
| Z12 | 272,30 → 86,00 | 665,07 → 775,96 | 587,49 → 0 | False → True |
| Z13 | 90,00 → 90,00 | 802,50 → 382,50 | 0 → 0 | False → True |
| Z14 | 249,55 → 94,03 | 642,95 → 388,00 | 417,62 → 0 | False → True |
| Z4 | — | — | — | aceptado → rechazo `ENTRADA_INVALIDA` |

Baseline: solo cambian Z3, Z4, Z12, Z13 y Z14 (`sha256 0f0e7c79af34c11d1cfb4d80`).
`baseline.json` intacta. Los micro-barridos no cambian.

### Dos precisiones surgidas al implementar

1. **Entrada `viga/beam_stirrup_spacing` en Z12 y Z14.** Con el cortante corregido el
   motor de vigas de la Fase 3 deja de exigir estribos por cálculo y esa entrada
   desaparece; `traza.orden` cambia por eso. La lista de invariantes fijada antes de
   implementar incluía `traza.orden` completo: se contrasta ahora con la afirmación
   física exacta —el orden de las entradas que NO son de viga es idéntico—, sin tocar
   el archivo de referencia.
2. **Tramo de diseño en rígido.** Con `[L1, s_corte]`, Z14 habría mostrado un Mu⁺ de
   11,6 kN·m que es el momento del reparto trasladado al eje interior, dentro de la
   zapata interior. Con el vano libre `[L1, s_fin]` es 0, que es lo que da el cuerpo
   libre.
