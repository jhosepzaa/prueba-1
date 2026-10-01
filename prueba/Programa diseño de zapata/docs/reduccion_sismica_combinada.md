# Reducción sísmica al 80 % en la zapata combinada

Fecha: 2026-09-18. Estado: **cerrada e implementada.** Aprobada por el usuario.

Cierra el último hueco del contrato de cargas: la reducción existía en la zapata aislada
(Fase 10B) y en las presiones de suelo de cada zapata de la conectada (D10C-2), pero no en
la combinada.

---

## 1. El criterio, que no cambia

**E.030 art. 29:** «Cuando se realicen verificaciones por esfuerzos admisibles, las fuerzas
sísmicas obtenidas con esta Norma Técnica se multiplican por 0,8». **E.060 §15.2.5** lo
justifica porque E.030 da las fuerzas a nivel de resistencia.

Ninguno de los dos artículos se reinterpreta aquí. La implementación es **la misma**:
`engine/foundation/depth_solver.soil_actions`, que sigue siendo la única del proyecto.

## 2. Alcance, idéntico al de la conectada (D10C-2)

| Se aplica | No se aplica |
|---|---|
| Presiones de suelo de la combinada | **Estabilidad** — E.030 art. 64.2 lo prohíbe expresamente |
| Solo con composición (modo por casos) | **Modo directo** — sin composición no se sabe qué parte es sísmica |
| Solo a la componente **CS a nivel de RESISTENCIA** | Un CS declarado a nivel de SERVICIO no se vuelve a reducir |
| | **Diseño factorizado** — diagrama, flexión, punzonamiento y cortante |

En modo directo, con la reducción activada y una combinación sísmica, el motor lo **dice**
en la traza en vez de callarlo: «NO aplicada … requiere conocer la componente sísmica».

## 3. Implementación

**Sin duplicar lógica**, que era el requisito explícito:

- `combined_solver` llama a `soil_actions(combo, soil, hip_col)` por columna y combinación
  de servicio, exactamente como hace `depth_solver._evaluate_contact_pressure`;
- el factor `SEISMIC_REDUCTION_FACTOR = 0.8` sigue declarado **en un solo sitio**, y hay un
  test que lo comprueba recorriendo `engine/`;
- el aviso de «no aplicable en modo directo» se extrajo a
  `seismic_reduction_unavailable()` y `seismic_reduction_unavailable_note()`, para que la
  redacción viva también en un solo sitio en vez de copiarse.

Las hipótesis de la combinada llevan la **etiqueta de la columna** de la que salen —`[C1]`,
`[C2]`—, porque la reducción se evalúa columna por columna.

### El término de excentricidad

La resultante de la combinada es `M = Σ (M_i + P_i·offset_i)`. El término `P_i·offset_i`
usa la carga **ya reducida**: por linealidad del reparto, reducir la componente CS de cada
columna equivale a repartir 0,8·CS. Es el mismo argumento de D10C-2.

Esto no era evidente: una **mutación deliberada** que dejaba ese término sin reducir pasó
todos los tests a la primera, porque el escenario original tenía columnas iguales y
simétricas y `Σ P_i·offset_i` se cancelaba. Se añadió
`test_con_columnas_desiguales_tambien_se_reduce_el_momento_de_la_excentricidad`, y la
mutación pasa a detectarse.

## 4. Tests

`tests/test_combined_seismic_reduction.py` (13 tests):

1. apagada, nada cambia; sin componente sísmica, tampoco;
2. modo directo: no se aplica y queda dicho, con la columna identificada;
3. con composición baja la presión, y el texto trae el ΔP con su número;
4. **invariante de linealidad**: reducir al 80 % da exactamente lo mismo que declarar
   0,8·CS y no reducir — reconstrucción que no pasa por el operador;
5. el mismo invariante con columnas desiguales, que ejerce la excentricidad;
6. CS a nivel de servicio: sin doble reducción;
7. estabilidad y diseño factorizado: idénticos con y sin reducción;
8. una sola implementación: el solver no contiene el factor ni filtra por `kind == "CS"`.

**Seis mutaciones deliberadas, seis detectadas:** no aplicarla, olvidar el término de
excentricidad, aplicarla en modo directo, reducir el CS de servicio, cambiar el factor a
0,7 y meterla en la estabilidad.

## 5. Baselines

**Sin cambios.** Los casos congelados de la combinada (K1–K4) se construyen con
`LoadCombination` escritas a mano (`composition = None`), de modo que están en modo directo
y la reducción no puede aplicárseles. Comprobado: `tests/freeze` 225 pasan y 2 se omiten,
con los hashes intactos.

## 6. Hallazgo abierto, no implementado

**La combinada no aplica el incremento del 30 % de E.060 §15.2** (`allow_temporary_increase_30pct`):
usa `soil.qadm_kPa` sin pasar por `_effective_qadm`, que es donde la aislada lo aplica. Un
usuario que active esa opción la verá surtir efecto en la aislada y no en la combinada.

No se tocó: está fuera del encargo, que era la reducción del 80 %, y es una decisión propia
—qué verificaciones de la combinada admiten el incremento temporal—. Queda registrado en
`docs/estado_proyecto.md`.
