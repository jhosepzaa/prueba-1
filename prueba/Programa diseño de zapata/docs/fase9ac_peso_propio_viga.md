# Fases 9a + 9c — Peso propio de la viga por geometría física y PAR_PURO con peso (B*)

Estado: **CERRADA y congelada (2026-09-13).** Freeze dirigido aprobado: Z8 actualizado y
Z15 agregado en `baseline_connected.json`; `baseline.json` intacto.

## 9a — Peso propio EXPLICITO por geometría física

### Defecto que corrige

El peso se tomaba sobre `[L1, s_corte]`. `s_corte` es la rótula del modelo articulado,
no un límite de la viga. En el caso de referencia (lindero [0,00; 2,00], interior
[5,15; 7,35], h = 0,90, Df = 1,50, viga 0,35 × 1,20):

| Tramo contado hasta 9a | kN |
|---|---|
| vano libre [2,00; 5,15] | 31,752 |
| sobre la huella interior [5,15; 6,00] — ya contada por `compute_self_weight` | 8,568 |
| dentro de la columna interior [6,00; 6,25] — no es viga | 2,520 |
| **total** | **42,840** |

El tramo de viga sobre la zapata de lindero, en cambio, no se contaba.

### Hipótesis de cota vertical — dato obligatorio

`ConnectingBeamSpec.soffit_above_base_m` (z_b) es la altura del fondo de la viga sobre
la base común de cimentación.

- Es obligatoria con `EXPLICITO` y no tiene valor por defecto.
- No se admite con los otros dos modos.
- `z_b < 0` se rechaza como `ENTRADA_INVALIDA`.

### Componentes y cuerpo al que pertenece cada una

| Componente | Tramo | Peso | Cuerpo |
|---|---|---|---|
| ΔW_e | [c_e, L1] | `Δw(h_ext)·(L1 − c_e)` | zapata exterior |
| W_V | [L1, f_i] | `b·h_v·γc·(f_i − L1)` (no depende de la cota) | viga |
| ΔW_i | [f_i, c_i] | `Δw(h_int)·(c_i − f_i)` | zapata interior |

La viga solo agrega sobre cada zapata lo que su concreto y su relleno no cuentan ya:

    Δw = b·[(γc_viga − γc_zapata)·t_f + (γc_viga − γs)·t_r + γc_viga·t_a]

- `t_f`: franja de la sección dentro de la zapata, [0, h_f].
- `t_r`: franja dentro del relleno, [h_f, max(Df, h_f)].
- `t_a`: franja por encima del terreno.

`beam_self_weight_kN = ΔW_e + W_V + ΔW_i`. El desglose se publica en
`CoupleDistribution.beam_self_weight_breakdown`.

Caso de referencia:

| | ΔW_e | W_V | ΔW_i | total |
|---|---|---|---|---|
| HV-1, z_b = 0 | 0,945 | 31,752 | 0,5355 | 33,2325 |
| HV-2, z_b = 0,30 | 1,890 | 31,752 | 1,071 | 34,713 |

### Uso en cada modelo

- **ARTICULADO + EQUILIBRIO.** ΔW_e y W_V entran en el cuerpo {zapata exterior + viga};
  ΔW_i va directo a `P_int_corr`.
- **CUERPO_RIGIDO.** Las tres componentes entran en la resultante global, cada una en su
  centroide. ΔW_i no forma parte del cuerpo con el que se calcula `M_cut`.
- **Diagramas de la viga.** ΔW_e se reparte sobre [c_e, L1] y W_V sobre [L1, f_i]. ΔW_i
  nunca carga la viga.

### Pendientes declarados (no implementados)

- **Relleno sobre la viga en el vano libre.** Aparece cuando `z_t < Df`. No se suma. La
  entrada `beam_self_weight_mode` queda **NO VERIFICADA**, sin `open_tbd`, porque la
  omisión subestima las cargas. Queda registrado en la limitación
  `connected_beam_fill_over_span`.
- **Viga sin contacto con una zapata** (`z_b > h_f`). El peso se contabiliza igual, pero
  el camino de carga no es el modelado: la misma entrada queda NO VERIFICADA.

## 9c — PAR_PURO_EN_ZAPATA + EXPLICITO: formulación B*

**Definición:** la rama transmitida al pórtico corresponde exclusivamente al par; las
cargas verticales gravitacionales de la viga se transmiten mediante sus reacciones.

Cuerpos libres, con s positivo hacia el interior y fuerzas positivas hacia arriba:

    Z (zapata)  −P_ext y −N_a en a, −ΔW_e en x_e, R_ext uniforme en L1/2, par C_Z
    V (viga)    +N_a y +F_p en a, −W_V en x_V, +V_I en s_corte, par −C_Z

    N_a  = W_V·(s_corte − x_V)/S
    R_ext = P_ext + N_a + ΔW_e
    C_Z  = −[e1·(P_ext + N_a) − (x_e − L1/2)·ΔW_e + M_fb]      (M_fb = −M_E050)
    ΔP = F_p = −C_Z/S
    V_I  = W_V − N_a − ΔP
    P_int_corr = P_int + V_I + ΔW_i

Consecuencias:

- `load_conservation_residual` sigue siendo 0 respecto de `expected_residual = −ΔP`. Al
  pórtico solo va la rama del par; el peso nunca falta.
- Con C_Z = 0, B* coincide con EQUILIBRIO (lo comprueba un test).
- Con DESPRECIADO, la aritmética es bit a bit la anterior; Aragón P1 queda intacto.
- Viga: V(s) = −M_par/S + N_a − W_izq(s) y M(s) = M_par·(1 − (s−a)/S) + N_a·(s−a) − M_izq(s).
  Los extremos se buscan por muestreo.

Hasta 9c el peso se perdía entero y la terna se rechazaba con «no cuadra en carga
vertical, −42,84 kN».

## Defecto destapado: ruido en la rótula tomado como demanda

En Z8, el momento en la rótula (cero por definición) cambió de −1,4e-13 a +3,8e-13 kN·m.
`M_max_positive` tomó ese residuo como Mu⁺. E.060 §10.5.3 eximió entonces el acero mínimo
positivo, que pasó de 9,24 cm² a cero.

**Corrección:** `design_extreme` anula los extremos de diseño que quedan por debajo de la
tolerancia de cierre de la misma estática (`statics_tolerance`, la de
`cut_moment_consistent`). No cambia ningún otro caso congelado.

## Congelamiento

- `snapshot.py` omite `beam_self_weight_breakdown` y `beam_node_reaction_kN` cuando valen
  `None`, igual que `open_tbd`. Así los otros 17 casos conectados no ganan claves.
- **Cambian solo Z8 y Z15 (nuevo).** Los otros casos conectados, los barridos y
  `baseline.json` son idénticos.
- Z8 declara HV-1:
  - 144 números cambian;
  - `implemented_checks_status` pasa de PASS a NO VERIFICADO, por el relleno sobre el vano;
  - `n_descartes` pasa de 0 a 1.
- Z15 = ARTICULADO + PAR_PURO + EXPLICITO, con HV-1.
- **Freeze dirigido (aprobado).** No se usó `FREEZE_REGEN=1`, que reescribe el archivo
  entero. Un script cargó el baseline, reemplazó solo Z8, agregó Z15 y lo escribió con la
  misma serialización (`dumps`; el round-trip del archivo previo era idéntico byte a byte).
  - Entradas: 18 → 19. Modificada: Z8. Agregada: Z15. Eliminadas: ninguna. Las otras 17
    son idénticas a la copia previa, clave por clave.
  - `baseline_connected.json`: `0f0e7c79af34…` → `203e9797ad58…`.
  - `baseline.json`: `0b2437648d89…`, sin cambios.
  - Suite completa tras el freeze: 1475 pasan, 2 omitidos, 0 fallos.

## Fuera del alcance de 9a/9c

La factorización del peso de la viga en combinaciones factorizadas es un pendiente
independiente, **TBD-C13**: `docs/tbd_c13_factorizacion_peso_viga.md`. 9a/9c no la
tratan ni la modifican.
