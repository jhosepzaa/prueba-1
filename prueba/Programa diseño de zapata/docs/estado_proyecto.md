# Estado del proyecto

Documento vivo. Se actualiza al cerrar cada fase. Las reglas estables están en `CLAUDE.md`.

Última actualización: 2026-09-25.

**ETAPA CONGELADA — FREEZE 2026-09-20.** Acta de cierre con la evidencia de cada
comprobación en [`freeze_2026_09_20_acta.md`](freeze_2026_09_20_acta.md).

> **DEFECTO POSTERIOR AL FREEZE, YA CORREGIDO (2026-09-22).** La validación de extremo a
> extremo con Aragón CR2 §3.5 destapó un error de signo en el diagrama longitudinal de la
> zapata **combinada** (`beam_diagram._moment`), que subestimaba el acero **superior**, del
> lado inseguro. Corregido con aprobación expresa, junto con la envolvente de combinaciones,
> y regenerado **solo el caso `K2`**. Detalle en
> [`validacion_aragon_3_5_combinada.md`](validacion_aragon_3_5_combinada.md).

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Auditoría de tipologías y arquitectura | cerrada |
| 1A / 1B / 1C | Correcciones normativas, columna descentrada, perímetro truncado | cerradas |
| 2 | Zapata combinada y refactor del optimizador | cerrada |
| 3 | Motor de la viga | cerrada |
| 4A–4H | Conectada: estática, integración, cuerpo rígido, búsqueda, API/informe/UI, freeze, presentación, deuda transversal | cerradas |
| 5A | D1 (rígido + par puro) y D3 (estática de la viga) | cerrada |
| 5B | D2 (causa del fallo por punzonamiento) | cerrada |
| 6 | Validación contra referencias externas | cerrada |
| Integración | Catálogo de tipologías, D4, paridad de la combinada | cerrada |
| 9a + 9c | Peso propio de viga por geometría física; B* para PAR_PURO + EXPLICITO | cerradas y congeladas (Z8 actualizado, Z15 agregado) |
| CC-0 | Transcripción de cargas y estabilidad (E.060 §9.2, E.020, E.030) | cerrada (`docs/normativa/transcripcion_cargas.md`) |
| 10A | Alineación con E.060 (A1–A8, B1–B11) | cerrada y congelada (2026-09-15) |
| 10B | Contrato de cargas por casos (C), estabilidad E.020, reducción sísmica 0,8 | cerrada y congelada (2026-09-15) |
| 10C | Composición de las cargas corregidas de la conectada; D10C-1 (peso de zapatas CM) y D10C-2 (0,8 sísmico por zapata) | cerrada, sin cambios de baseline (`docs/fase10c_composicion_cargas_conectada.md`) |
| 2 | Motivos de descarte de la combinada agrupados y trazables | cerrada, sin cambios de baseline (`docs/fase2_motivos_descarte_combinada.md`) |
| 9b | Vano libre físico `beam_span_m = f_i − L1` y métricas de viga sin doble conteo | cerrada y congelada (`docs/fase9b_vano_libre_y_metricas_viga.md`) |
| Pend. 4 | Informes combinada y conectada: `alternative_id` inexistente → 422, sin sustitución | cerrada (`docs/pendiente4_informes_alternative_id.md`) |
| C-V | Cortante longitudinal de la combinada: criterio explícito de concreto solo, estribos retirados | cerrada, sin cambios de baseline (`docs/auditoria_cv_cortante_longitudinal_combinada.md`) |
| Dec. 6 | Criterio de aceptación de la combinada: `PASS_OR_INFO` → `NO_FAIL` | cerrada, sin cambios de baseline (`docs/decision6_aceptacion_combinada.md`) |
| Pend. 1 | Esquema 2D de la zapata combinada (`CombinedSceneDTO`, campo `scene`) | cerrada, sin cambios de baseline |
| D10-2b | FS 1,50 al volteo (también sísmico) y al deslizamiento, como criterio adoptado del programa | cerrada y **congelada** (`docs/d10_2b_fs_volteo_sismico.md`, `docs/freeze_d10_2b_diff.md`) |
| Pend. 7 | Estabilidad de la zapata combinada: resultante de columnas y envolvente del momento volcador (opción B) | cerrada, sin cambios de baseline (`docs/pendiente7_estabilidad_combinada.md`) |
| Pend. 8 | Vocabulario único de estados: CONFORME / ACEPTADA CON OBSERVACIONES / NO VERIFICADA / RECHAZADA | cerrada, sin cambios de baseline (`docs/pendiente8_vocabulario_estados.md`) |
| Sismo comb. | Reducción sísmica al 80 % en las presiones de suelo de la combinada, con el operador ya existente | cerrada, sin cambios de baseline (`docs/reduccion_sismica_combinada.md`) |
| TBD-C13 | Factor de CM del peso propio de la viga en modo directo: dato declarado, y sin él NO VERIFICADO (decisión A′) | cerrada; **freeze dirigido de `n_descartes` en Z8 y Z15** (`docs/tbd_c13_factorizacion_peso_viga.md`) |
| Inc. 30 % | Auditoría de E.060 §15.2.4: la combinada no aplicaba el incremento. Corregido con el operador compartido | cerrada, sin cambios de baseline (`docs/auditoria_incremento_30pct.md`) |
| Pend. 3 | Vista 3D de la combinada y del sistema conectado, sobre los mismos DTO del esquema 2D | cerrada, sin cambios de baseline (`docs/pendiente3_vista_3d.md`) |
| Auditoría | Integridad transversal: `enforced_by` nominal, cortante sin explicación, invariante que faltaba | cerrada, 3 hallazgos corregidos, sin cambios de baseline (`docs/auditoria_integridad_final.md`) |
| `FORMULACION_VOLTEO` | Formulación común del momento volcador: término `P·offset` y envolvente en las tres tipologías, con un solo ayudante | cerrada y **congelada** (`docs/formulacion_volteo_analisis.md`, `docs/freeze_formulacion_volteo.md`) |
| Aud. paridad | Paridad entre tipologías: §15.7 no se verificaba en la combinada; limitaciones con texto obsoleto; 74 entradas de traza sin hipótesis | cerrada; **freeze dirigido de 4 casos combinados** (`docs/auditoria_paridad_tipologias.md`) |
| Aud. normativa | Toda designación citada existe en las fuentes (65/65); cuatro citas literales que no lo eran, corregidas; §15.2.6 incorporado a TBD-C1 | cerrada; **freeze dirigido de 13 `referencias`** (`docs/auditoria_normativa_citas.md`) |
| TBD conectada | Análisis de C1, C4, C11 y C12: naturaleza, impacto y opciones. **C12 no es un hueco normativo**: E.050 art. 28 prescribe el método | analizada, **ninguno cerrado** (`docs/tbd_conectada_c1_c4_c11_c12.md`) |
| Manual | Ampliado a las tres tipologías (secciones 12 y 13), alcance al día y tabla de limitaciones completa; PDF regenerado | cerrado (`docs/manual_usuario.html`) |
| Área efectiva | E.050 art. 28 implementado como modelo de contacto OPCIONAL: extiende al núcleo central sin sustituirlo, con la asimetría del `qadm` declarada | cerrada; **freeze dirigido de 50 `referencias`** (`docs/area_efectiva_e050_art28.md`) |
| Bloque triangular | Campo de presión de DISEÑO por equilibrio con despegue (opción B). Corrige Mu y Vu en 5 casos congelados; el error iba en las dos direcciones | cerrada y **congelada** (`docs/area_efectiva_e050_art28.md` §6) |
| Cortante transversal | H2: la combinada no verificaba el cortante unidireccional transversal que exige §11.12.1.1 | cerrada; **freeze dirigido de 4 casos combinados** (`docs/auditoria_paridad_tipologias.md` §H2) |
| Punzonamiento · campo real | `Vu = Pu − ∫∫(A_crit) q(x,y) dA` por cuadratura del mismo campo que usan flexión y cortante. Cierra el hueco del alivio lineal y destapa el campo ficticio con que la combinada lo calculaba. Queda declarado solo el despegue BIAXIAL | cerrada y **congelada**, 9 casos (`docs/freeze_punzonamiento_campo_real.md`) |
| Zona de contacto `q>0` | El alivio se integra solo sobre `A_crit ∩ {q > 0}`: el suelo no tracciona. Recorte del polígono contra la recta oblicua `q = 0`. Destapó que la bandera de despegue biaxial preguntaba por los dos ejes en vez de por el signo del campo —el núcleo de un rectángulo es un rombo— | cerrada y **congelada**, 2 casos sustantivos (`docs/freeze_zona_contacto_y_proporcion.md` §2 y §3) |
| H6 · Proporción 23.3 | `L/B ≤ 10` de E.050 art. 23.3 en las **tres** tipologías, con una sola implementación. Antes solo la combinada lo miraba y `max_LB_ratio` es un parámetro de búsqueda | cerrada y **congelada**, 22 casos con entrada AÑADIDA, todos PASS (`docs/freeze_zona_contacto_y_proporcion.md` §4) |
| Contacto unilateral | `q⁺ = max(a+b·u+c·v, 0)` resuelto por equilibrio (3 ecuaciones, Newton con jacobiano exacto = matriz de Gram). **Campo común** de punzonamiento, flexión y cortante; retira la superposición y cierra `punching_biaxial_uplift` | cerrada y **congelada**, 2 casos sustantivos (`docs/freeze_contacto_unilateral.md` §1) |
| H7 · `Df/B ≤ 5` | E.050 art. 23.1 en las **tres** tipologías, con B = lado MENOR. FAIL, no NO VERIFICADO: es condición de aplicabilidad del programa | cerrada y **congelada**, entrada AÑADIDA en 36 casos, todos PASS (`docs/freeze_contacto_unilateral.md` §3) |
| TBD-C1 | Declaración del proyectista sobre §15.2.6 (`beam.stiffness_declaration`). Levanta ESE bloqueo y ningún otro; no mueve ningún número | **cerrado por declaración** (`docs/freeze_contacto_unilateral.md` §4) |
| TBD-C4 | `APOYA_EN_SUELO` rechazado por validación, en el layout y en el solver. Retira el caso congelado `Z7` | **cerrado por rechazo** (`docs/freeze_contacto_unilateral.md` §5) |
| C-V | Cerrado con el criterio de concreto solo, declarado como límite de alcance: NO es una verificación completa del modelo de cortante de E.060 | **cerrada**, sin cambios de baseline (`docs/freeze_contacto_unilateral.md` §6) |
| Val. Aragón §3.5 | Primera validación de extremo a extremo: signo del salto de momento en el diagrama longitudinal (acero superior subestimado) y envolvente de combinaciones por efecto | cerrada; **freeze dirigido de `K2`** (`docs/validacion_aragon_3_5_combinada.md`) |
| Guía de uso | Cómo abrir el programa y usarlo entero, con lanzador de doble clic | cerrada (`docs/guia_de_uso.html`) |
| Unidades dinámicas | El proyectista elige unidades de entrada Y de presentación en las cuatro pantallas; conversión en el motor, redondeo declarado, traza en SI. Materiales, suelo y §15.2 añadidos a combinada y conectada. Corrige el peso unitario de la viga conectada, que no se convertía | cerrada, sin cambios de baseline (`docs/unidades_dinamicas.md`) |
| Proyectos | Guardar y abrir el proyecto en archivo, validado contra el contrato de la API, y memoria del navegador por tipología | cerrada, sin cambios de baseline (`docs/eficiencia_proyectos_y_barrido_paralelo.md` §2) |
| Barrido paralelo | El barrido de la conectada se reparte entre procesos conservando orden, tope e identificadores; 1,4–1,9× según el caso. Corrige de paso la materialización de plantas, que también lastraba el camino secuencial | cerrada, sin cambios de baseline (`docs/eficiencia_proyectos_y_barrido_paralelo.md` §3) |
| Calidad de propuestas | Cinco silencios del barrido: rango automático que ignoraba excentricidad y relleno, falta de aviso al quedar contra el borde, un solo peralte por planta, poda por L/B invisible y centrado de la combinada con la combinación equivocada | cerrada, sin cambios de baseline (`docs/calidad_de_las_propuestas.md`) |
| Documentación | AGENTS.md deja de duplicar CLAUDE.md y pasa a señalarlo; README, títulos de la aplicación y §13 del manual al día; contrato de unidades incorporado a CLAUDE.md | cerrada, sin cambios de baseline |
| Interfaz CIMA | Handoff «Cimentación 3D»: visor central con modos, corte, gizmo, transiciones y exportación; cajón de datos, panel de propiedades de solo lectura y dock de resultados. Sin tocar motor ni API; la armadura solo se dibuja donde el motor la posiciona | cerrada, sin cambios de baseline (`docs/interfaz_cima.md`) |
| Carga neta ascendente | La conectada rechaza como `CARGA_NETA_ASCENDENTE` —y no como ENTRADA_INVALIDA— la zapata que el suelo sostiene menos que su peso | cerrada, sin cambios de baseline (`docs/freeze_desarrollo_columna_descentrada.md` §1) |
| Desarrollo con columna descentrada | E.060 §15.6.2 a cada lado de la cara que gobierna; ganchos declarables en la conectada; casos de lindero congelados (conectada y aisladas 16–18) con gancho de 90° | cerrada y **congelada** con aprobación, 18 casos (`docs/freeze_desarrollo_columna_descentrada.md` §2-3) |
| Linderos y búsqueda automática | Límites del terreno en combinada (coloca la zapata) y conectada (recorta); rangos estimados por el motor en dos pasadas; aviso de borde de la conectada corregido | cerrada, sin cambios de baseline (`docs/linderos_y_busqueda_automatica.md`) |
| Práctica con ejercicios publicados | Wight 15-2 (aislada) y 15-5 (combinada) vía StructurePoint, y una conectada de Structville, pasados por el programa sin tocar el motor; mecánica coincidente, dos decisiones nuevas (H1, H2) | cerrada (`docs/practica/README.md`) |
| **FREEZE 2026-09-20** | Cierre formal de la etapa: suite, freeze, tsc, build, hashes, ausencia de referencias al modelo retirado, alcance de C-V y semántica de C1 | **acta en `docs/freeze_2026_09_20_acta.md`** |

Baselines vigentes (2026-09-28, freeze del desarrollo con columna descentrada):
`baseline.json` `f83e15382c66…`, `baseline_connected.json` `30647a1e92c3…` y `reference_pre_5a_non_beam.json` `1e3c1ebf2f83…`
(esta última **sin tocar desde 5A**, a propósito: ver §5 de
`docs/freeze_formulacion_volteo.md` y §4 de `docs/auditoria_normativa_citas.md`; lleva dos
dispensas enumeradas, cada una con su justificación y sus tests).

Tres freezes dirigidos el 2026-09-19, los tres verificados clave por clave contra la copia
previa y los tres con **cero claves ajenas**:

1. **`FORMULACION_VOLTEO`** (aprobado por el usuario, `docs/freeze_formulacion_volteo.md`):
   19 casos, 139 claves `numeros`, 44 `estados`, 13 `referencias`. Un solo cambio de conjunto
   en fallo (`18_borde_con_momento`, que ya era descartado por presión de contacto) y
   **ninguna aceptación distinta**.
2. **Peralte mínimo §15.7 en la combinada** (`docs/auditoria_paridad_tipologias.md`): 4 casos,
   20 claves, **todas añadidas** —la entrada nueva y `traza.orden`—. Ningún número ni estado
   anterior se movió.
3. **Citas normativas** (`docs/auditoria_normativa_citas.md`): 13 casos de la conectada, 13
   claves, **todas de `referencias`** (contrato blando). Cero `numeros`, cero `estados`.
4. **Área efectiva** (`docs/area_efectiva_e050_art28.md`): 50 claves, **todas de
   `referencias`** —«E.060 §15.2» → «§15.2.3»—. Cero `numeros`, cero `estados`: el modelo por
   defecto no se tocó y dentro del núcleo el nuevo devuelve lo mismo bit a bit.
5. **Bloque triangular** (opción B, `docs/area_efectiva_e050_art28.md` §6): 5 casos de la
   aislada, 149 claves `numeros`. Cero estados y cero descartes: los cinco ya estaban en NO
   VERIFICADO o en FAIL por otros motivos.
6. **Cortante transversal de la combinada** (H2): 4 casos, 3 `numeros` + 1 `estados` + 1
   `referencias` cada uno, **todas añadidas**. Los cuatro pasan la verificación nueva.
7. **Punzonamiento con contacto parcial**: 5 casos de la aislada, 3 `numeros` + 1 `estados`
   + 1 `referencias` cada uno, **todas añadidas**. Ninguna aceptación cambia.
8. **Integral del campo real en el punzonamiento**
   (`docs/freeze_punzonamiento_campo_real.md`): 9 casos —5 de la aislada y los 4 de la
   combinada—, 119 claves, **todas de `numeros`** salvo la entrada que se estrecha. Ningún
   `overall_status`, ningún descarte y ninguna aceptación. Cierra el punto 7: la declaración
   pasa de todo contacto parcial al despegue **biaxial**, que es lo único que queda sin
   resolver, y de paso corrige el campo ficticio con que la combinada calculaba el alivio.

Freezes dirigidos del 2026-09-18, ambos verificados clave por clave contra la copia previa:

1. **D10-2b** (aprobado por el usuario, `docs/freeze_d10_2b_diff.md`): 3 claves numéricas de
   `FS_required` en los casos 10 y 11 de la aislada, y 18 textos de referencia. Ningún estado.
2. **TBD-C13**: `n_descartes` de `Z8` (1 → 2) y `Z15` (2 → 3), por el motivo nuevo que escribe
   la entrada `beam_self_weight_mode` cuando falta el factor de CM. Nada más se movió:
   `baseline.json` y `reference_pre_5a_non_beam.json` quedaron idénticos.
Suite completa (2026-09-24): **2053 pasan, 2 se saltan, 0 fallan** (4:02 → 2:57). `npx tsc --noEmit` limpio y `npm run build` correcto.

## Pendientes

Solo lo que sigue ABIERTO. Lo cerrado está en la tabla de fases, con su documento.

### Requieren decisión del usuario

**Dos nuevas (2026-09-29), encontradas al contrastar ejercicios publicados**
(`docs/practica/README.md`); el motor no se modificó:

- **H1 — cuantía mínima con `fy = 4200 kg/cm²`.** La conversión exacta da 411,9 MPa < 420 y
  E.060 §9.7.2 literal asigna 0,0020 en vez de 0,0018 (+11 % de acero mínimo). ¿El umbral
  designa un grado de acero o un número?
- **H2 — punzonamiento en columnas de borde y esquina.** §11.12.7 solo se aplica con momento
  de la columna. La excentricidad del cortante respecto del centroide de la sección de 3 o 2
  lados no entra (ACI R8.4.4.2.3 sí la toma). En Wight 15-5 el original falla y el
  programa da PASS con 0,55. Posible lado inseguro; prioritaria.

Antes de esas dos no quedaba ninguna. Las seis que quedaban abiertas —contacto unilateral biaxial,
umbral de proporción, `Df/B`, TBD-C1, TBD-C4 y C-V— se decidieron el 2026-09-20 y están en
la tabla de fases con su documento.

Lo que sigue abierto son AMPLIACIONES de alcance, no decisiones que bloqueen nada:

| Id | Qué sería | Estado |
|---|---|---|
| `Vn = Vc + Vs` en la combinada | Admitir el aporte de estribos en el cortante longitudinal | **Decisión de ingeniería nueva**, no un pendiente. Exige resolver antes las ramas y la separación transversal, el alcance de §11.12.3 y la sección crítica de §15.5.2. Hoy el criterio de concreto solo es más estricto que la norma: solo pierde geometrías, no acepta ninguna mala |
| Viga de conexión apoyada en el terreno | Admitir `APOYA_EN_SUELO` | **Decisión de ingeniería nueva.** Exige definir el modelo resistente de la viga sobre el terreno y la transferencia de acciones entre viga, suelo y zapatas. Hoy se rechaza a la entrada (D5) |
| Contacto unilateral en la CONECTADA | Que el despegue de una zapata del sistema no rechace el candidato | TBD-C12 en su parte conectada. En aislada y combinada ya está resuelto por `unilateral_contact`; ahí lo que despega es parte de una huella, aquí una zapata entera, que es otro problema |

### TBD abiertos de la conectada

| TBD | Naturaleza | Por qué sigue abierto | Puede producir |
|---|---|---|---|
| C11 | Hipótesis sobre la superestructura | El motor no ve el pórtico y no puede comprobar que recoja la rama del par | zapata interior más aliviada |
| C12 | **NO es un hueco normativo.** E.060 §15.2.3 prohíbe las tracciones y E.050 art. 28.2–28.3 prescribe el área efectiva | Resuelto en aislada y combinada por `unilateral_contact`. En la CONECTADA falta implementarlo, no decidirlo | solo descartes de más |

**C1 y C4 se cerraron el 2026-09-20** (decisiones 4 y 5), el primero por declaración del
proyectista y el segundo por rechazo. El análisis que los dejó listos está en
`docs/tbd_conectada_c1_c4_c11_c12.md`.

Los dos que quedan están declarados, trazados con `open_tbd` y neutralizados: ninguna
alternativa conforme los arrastra (comprobado en `tests/test_auditoria_integridad_final.py`).

### Deuda menor anotada, sin decisión pendiente

- **H5** — la combinada no emite `self_weight` ni `column_placement` en la traza, ni recorre
  el registro de limitaciones. No falta ningún cálculo: el peso propio entra en la presión y
  la posición de las columnas la valida el layout. Es auditabilidad, no ingeniería
  (`docs/auditoria_paridad_tipologias.md` §H5).
- **`capped_at_400mm`** — nombre de campo heredado de la edición anterior de E.060. El valor
  que compara es el correcto (450 mm); renombrarlo movería claves de contrato congeladas por
  un motivo cosmético (`docs/auditoria_normativa_citas.md` §2.1).
- **`Vc_eq_11_33/34/35_kN`** — mismo caso: en la edición designada, las tres ecuaciones de
  §11.12.2.1 son **11-41, 11-42 y 11-43**, y así se citan en `governing_equation`, la traza
  y la memoria. Los nombres de campo están en 53 claves de los baselines congelados, de modo
  que renombrarlos exige regeneración dirigida por un motivo cosmético. Queda un comentario
  en `engine/foundation/punching_shear.py` para que nadie los lea como cita.

### Limitaciones declaradas que no son pendientes

Registradas en `LIMITATION_REGISTRY`, cada una con la verificación que la hace visible
(`enforced_by`, expandido a ids de traza reales desde la auditoría de integridad):

- relleno sobre la viga en el vano libre (`connected_beam_fill_over_span`): NO VERIFICADO
  cuando la geometría declarada lo deja;
- estabilidad de las zapatas de la conectada sin composición
  (`connected_footing_stability_composition`);
- factor de CM del peso de la viga en modo directo (`connected_beam_weight_factoring`),
  desde TBD-C13 A′;
- columnas circulares, fuera de alcance, rechazadas por validación de entrada.
