# CLAUDE.md — Diseño de cimentaciones de concreto armado (RNE Perú)

Reglas permanentes del proyecto. **Precedencia:** lo que diga el prompt de la tarea >
este archivo > criterio propio. Un modo «autónomo» o «no te detengas» NO anula las
paradas obligatorias de §3 ni la política de baselines de §11.

Estado vivo del proyecto (fases, pendientes, prioridades): `docs/estado_proyecto.md`.
Actualizarlo al cerrar cada fase. Este archivo solo contiene reglas estables.

---

## 1. Propósito

Programa de ingeniería para diseñar, verificar y optimizar cimentaciones de concreto
armado de tres tipologías: **zapata aislada, zapata combinada y zapata conectada con
viga**. Debe ser trazable y técnicamente defendible; no es un calculador dimensional.

El resultado debe permitir:
1. ingresar geometría, materiales, suelo y acciones;
2. separar entradas, hipótesis, cálculo y verificaciones;
3. generar alternativas de diseño;
4. explicar por qué cada alternativa se acepta o se rechaza;
5. mostrar qué verificaciones se ejecutaron y cuáles no;
6. conservar una `CalculationTrace` auditable;
7. generar la memoria de cálculo;
8. exponer todo por API y UI;
9. proteger contra regresiones con benchmarks, tests y baselines.

Normativa principal: **RNE E.050** (suelos y cimentaciones), **E.060** (concreto armado)
y **E.030** (sismorresistente).

**No inventar artículos, coeficientes, ecuaciones, factores ni criterios normativos. No
inventar parámetros geotécnicos (μ, FS, k_s).** Si algo no es verificable: TBD / NO
VERIFICADO.

Los apuntes de Aragón son **benchmark, no autoridad normativa**: CR2-93-134
(`docs/normativa/aragon_cr2_extracto.txt`) y CR2-135-169, muros de sostenimiento
(`docs/benchmark/`). Una discrepancia con ellos se documenta; nunca se fuerza el motor para
coincidir, y **de ellos no se toma ningún factor, coeficiente ni criterio de cálculo** —ni
siquiera un factor de seguridad—: para eso están las fuentes de `docs/normativa/fuentes/`.

## 2. Arquitectura y principios

```text
engine/   dominio · análisis · verificaciones · optimización · traza · reportes
  ↓
api/      FastAPI + Pydantic: transforma contratos, no calcula
  ↓
ui/       React + TypeScript (+ three / @react-three para escenas): presenta, no calcula
```

- La ingeniería vive en el motor. La UI no reproduce ecuaciones ni recalcula en silencio
  valores que el motor ya entrega.
- La API no duplica lógica de cálculo; la presentación no modifica resultados.
- Cada fórmula debe poder testearse de forma independiente.
- Los resultados importantes deben poder reconstruirse desde las entradas y la traza.
- No introducir en el motor lógica específica de un caso de prueba.
- No cambiar contratos de API/DTO existentes sin necesidad. Los campos nuevos se añaden
  (cambio aditivo).

## 3. Decisiones de ingeniería: cuándo detenerse

**Detenerse y consultar** si una decisión nueva, no especificada en el prompt, puede
modificar cualquiera de estos elementos:

- ecuaciones o hipótesis físicas;
- la interpretación de una entrada o el contrato de cargas;
- un criterio normativo;
- el estado de una verificación o de una alternativa;
- un resultado numérico o un baseline congelado;
- el significado de una tipología o del vocabulario de estados.

En ese caso:
1. detener esa decisión;
2. explicar el problema con evidencia;
3. mostrar las alternativas técnicamente razonables;
4. indicar qué resultados y casos congelados se ven afectados;
5. pedir aprobación explícita.

No resolverla por intuición. «Más conservador» no equivale a «correcto».

**Se puede continuar sin consultar** en cambios mecánicos que no alteran la ingeniería:
- refactor sin cambio de comportamiento, tipado;
- adaptar DTOs o propagar un campo ya decidido por API, UI y reportes;
- tests y documentación.

**Ante la duda, tratarlo como decisión de ingeniería.**

Si durante una implementación aparece un defecto real, se corrige cuando la corrección es
segura y verificable. Si requiere una decisión, se documenta y se consulta. Nunca se
oculta.

## 4. Capas que pueden modificarse

Salvo indicación contraria, un cambio puede requerir modificaciones coordinadas en
`engine/`, `api/` (schemas y servidor), `ui/`, reportes, tests y `docs/`.

«Implementa X» **no** autoriza a modificar baselines (§11).

## 5. Estados

### Máquina de verificación (`engine/results/status.py`)

`CheckStatus`, de menor a mayor severidad: `PASS` = `INFO` < `WARNING` < `NOT_VERIFIED`
(valor `"NO VERIFICADO"`) < `FAIL`.

- Solo `FAIL` descarta (`CheckStatus.discards`).
- Un `WARNING` nunca se convierte en `PASS`.
- Un `NOT_VERIFIED` nunca se presenta como conforme.

### Vocabulario de alternativas — ÚNICO para las tres tipologías (pendiente 8)

Fuente única: `engine/results/vocabulary.py`. No duplicar el mapa en ningún otro sitio;
ya pasó tres veces (`report_model`, `connected_report`, `discard_explainer`).

| Término | Estado interno | Significado |
|---|---|---|
| CONFORME | PASS o INFO **sin pendiente abierto** | Único rótulo presentable como conforme (`accepted_and_compliant`). Estuvo vacío en la conectada mientras TBD-C1 siguió abierto; desde la decisión 4 (2026-09-20) una terna lo alcanza **si el proyectista declara §15.2.6 Y todo lo demás sale PASS o INFO**. La declaración sola no basta: `Z2_articulado_par_puro` la tiene y sigue NO VERIFICADA por TBD-C11. |
| ACEPTADA CON OBSERVACIONES | WARNING | El motor se pronuncia, y con reservas. |
| NO VERIFICADA | NO VERIFICADO, o PASS/INFO con pendiente abierto | Hay una condición que el motor no puede demostrar con lo implementado. |
| RECHAZADA | FAIL | No supera una condición implementada. En conectada lleva motivo estructurado `RejectionReason`: `GEOMETRIA_IMPOSIBLE`, `DESPEGUE`, `CARGA_NETA_ASCENDENTE` (el suelo devuelve bajo una zapata menos que su peso: la viga la sostiene; añadido 2026-09-28, antes caía en ENTRADA_INVALIDA), `ENTRADA_INVALIDA`, `NO_CUMPLE`. |

**«ACEPTADA» a secas y «DESCARTADA» ya no son rótulos.** La primera significaba PASS en la
aislada y WARNING en la conectada; la segunda era otro nombre de RECHAZADA. Equivalencias
con los informes anteriores en `LEGACY_EQUIVALENCE`.

El rótulo es presentación. **La semántica interna no cambia y es la que manda:** `accepted`
—sobrevive al barrido— no es `accepted_and_compliant` ni «verificada». La API entrega las
dos cosas por separado: `status` (CheckStatus crudo, el que usan los criterios) y
`status_label`.

Evitar:
- «válida» cuando solo sobrevivió al filtro;
- «cumple norma» cuando hay verificaciones no implementadas;
- «óptima» cuando es la mejor dentro de una búsqueda limitada o truncada.

### Regla de aceptación (única para las tres tipologías desde la decisión 6)

`NO_FAIL`: sobrevive al barrido todo lo que no sea FAIL. Aislada, combinada y conectada
usan la misma regla; la combinada usaba `PASS_OR_INFO` hasta la decisión 6
(`docs/decision6_aceptacion_combinada.md`). No cambiarla por tipología sin decisión
explícita: la diferencia `ACEPTACION_COMBINADA` del catálogo queda **resuelta, no borrada**
(campo `resolution` de `KnownDifference`).

**Aceptada no es conforme.** Combinada y conectada separan las particiones: `accepted`
—sobrevive—, `accepted_and_compliant` —PASS o INFO, lo único presentable como conforme—,
`not_verified` y `accepted_with_findings`. En la combinada el campo del modelo sigue
llamándose `valid` por contrato; `accepted` es su nombre honesto y el que se usa en código
nuevo.

Los `discard_reasons` de aislada y combinada son **categorías de texto globales**: la API,
los informes y los golden cases agrupan por texto exacto. No cambiar su redacción; el
detalle va en la traza.

## 6. TBD y datos faltantes

- Un TBD es una decisión o verificación pendiente. **No se cierra implícitamente con
  código.**
- En la traza se marca con `open_tbd="TBD-Cx"` (una **cadena**, no un booleano) solo
  cuando el hueco es del motor o de la norma.
- Un **dato de proyecto faltante** (por ejemplo, un FS requerido que el usuario no dio)
  **no** es un TBD. Queda NO VERIFICADO sin `open_tbd`.
- `overall_status` nunca llega a conforme mientras un TBD afecte la verificación.

TBD vigentes de la conectada:

| TBD | Tema | Estado |
|---|---|---|
| C1 | Rigidez de la viga / presión uniforme (premisa) | **cerrado por declaración (decisión 4, 2026-09-20).** E.060 §15.2.6 exige la evaluación y no da método: la responde el proyectista con `beam.stiffness_declaration`. Sin declarar → NO VERIFICADO, como antes. Declarar levanta ESE bloqueo y **ningún otro** |
| C4 | Viga apoyada en el suelo (`APOYA_EN_SUELO`) | **cerrado por rechazo (decisión 5, 2026-09-20).** El valor se rechaza por validación; no se deja en NO VERIFICADO, porque el motor resolvería otro problema y el error va del lado inseguro en la zapata interior. Admitirlo exige definir el modelo resistente: decisión nueva |
| C5 | Tratamiento del peso propio de la viga (modo obligatorio) | cerrado por declaración |
| C11 | Destino de la rama cercana del par (`CoupleTransferMode`) | PAR_PURO → NO VERIFICADO |
| C12 | Contacto unilateral / despegue | **resuelto en aislada y combinada** (decisión 1, 2026-09-20): `unilateral_contact` lo resuelve por equilibrio. En la CONECTADA el despegue del sistema sigue rechazando el candidato, que es otra cosa: ahí lo que despega es una zapata entera, no parte de una huella |
| C13 | Factorización del peso propio explícito en combinaciones factorizadas | **cerrado.** Modo por casos: × factor de CM de la composición. Modo directo: factor declarado por el proyectista (`beam.self_weight_dead_load_factor`); sin declararlo, NO VERIFICADO sin `open_tbd` |

C2 quedó resuelto (k_s se cancela en cuerpo rígido); C3, C6–C10 son históricos; ver
`docs/fase4_auditoria.html` antes de reutilizar su número. Los TBD nuevos toman el
siguiente número libre.

## 7. Trazabilidad

Cada entrada de traza conserva:
- ecuación simbólica y sustituida;
- entradas relevantes;
- resultado y unidad;
- estado e hipótesis;
- referencia normativa, cuando la hay;
- `open_tbd`, cuando corresponde.

En sistemas de varios componentes la clave es **(scope, id)**: `id` no es global.

**Ninguna entrada se queda sin hipótesis.** Una entrada muda se lee como «esto está
verificado, sin más», y casi nunca es cierto: toda verificación descansa en una lectura, en un
alcance que no cubre o en un dato que el motor no posee. `hypotheses` es prosa y el
congelamiento NO la protege; lo hace
`tests/test_auditoria_paridad_tipologias.py::test_ninguna_entrada_de_traza_se_queda_sin_hipotesis`.

No etiquetar un elemento como interior, exterior, de borde, etc. si su geometría real no
lo es.

## 8. Normativa

**Fuentes admitidas:** solo los documentos de `docs/normativa/fuentes/`, entregados por el
usuario (índice y advertencias en `docs/normativa/README.md`). Si la información necesaria
no está en ellos, **pedírsela al usuario antes de suponer nada**. El manual, los apuntes de
Aragón y los documentos de `docs/` son material propio, no fuente normativa.

Estado de las fuentes:
- Disponibles: E.020, E.030 (2026, vigente), E.050 y **E.060**
  (`e.060-concreto-armado-sencico.pdf`, portada «Propuesta de Norma E.060, 2019»,
  designada por el usuario).
- `e060 actualizada.pdf` **contiene E.030 (2025), no E.060**: no usarlo como E.060.
- El motor está alineado con esta E.060 desde la Fase 10A (A1–A8 y B1–B11 de
  `docs/normativa/contraste_e060_motor.md`). Cualquier diferencia nueva sigue el mismo proceso:
  decisión y diff por caso (§3, §11).
- Usar los extractos `docs/normativa/texto/*.txt` (modo `-raw`), no los de
  `texto/maquetado/`.

Cuando una decisión dependa de un artículo concreto:
1. buscar el texto en `docs/normativa/texto/` (extractos auxiliares) y confirmarlo en el PDF
   de `docs/normativa/fuentes/`;
2. identificar artículo y sección;
3. separar **requisito normativo / interpretación / hipótesis del modelo / decisión de
   implementación**.

No citar ni extrapolar desde memoria. Si el texto no está disponible y hace falta para
cerrar la decisión: dejarla pendiente y decir exactamente qué artículo falta.

No presentar una hipótesis de modelación como exigencia normativa. **Ni al revés:** decir
«sin respaldo normativo» de una pregunta que la norma sí plantea es el mismo error con el
signo cambiado (pasó con TBD-C1 y E.060 §15.2.6).

**Lo que va entre «» tiene que ser literal.** Una paráfrasis entrecomillada es una cita
inventada aunque diga lo mismo. `tests/test_auditoria_citas_normativas.py` comprueba
mecánicamente que toda designación citada EXISTE en la fuente —65 designaciones, las cuatro
normas—, pero no puede comprobar que diga lo que se afirma: eso se contrasta a mano
(`docs/normativa/contraste_e060_motor.md`, `docs/auditoria_normativa_citas.md`).

## 9. Cargas y servicio / factorizado

Hay **dos modos de entrada**, excluyentes por petición (Fase 10B, `docs/fase10_alineacion_e060_y_contrato_cargas.md`):

- **Directo:** combinaciones ya formadas (`LoadCombination`: P, Mx, My, Hx, Hy, de servicio o
  factorizada; `composition = None`). Solo declaran si incluyen sismo o viento. El motor
  **no conoce** qué parte es carga muerta o viva.
- **Por casos:** `LoadCase` sin factorizar (E.060 §9.2: CM, CV, CVi, CS, CE, CL, CT; nivel
  SERVICIO | RESISTENCIA obligatorio para CVi y CS) + `CombinationDefinition` con los factores
  **declarados por el usuario**. `engine/domain/load_cases.py` deriva `LoadCombination` con su
  `LoadComposition`. El motor **no genera** las combinaciones de §9.2.

Reglas:
- No aplicar factores a una carga ya combinada.
- Las cargas **generadas internamente** solo reciben factor si la composición lo permite o si
  el proyectista lo declara. Peso propio de la viga: × factor de CM de la combinación en modo
  por casos; en modo directo, × `beam.self_weight_dead_load_factor` si se declara —solo en las
  FACTORIZADAS; el servicio lleva el peso real— y sin factor si no, con la entrada
  `beam_self_weight_mode` en **NO VERIFICADO** (TBD-C13 cerrado con la decisión A′,
  `docs/tbd_c13_factorizacion_peso_viga.md`). El motor nunca supone un factor.
- Una combinación derivada debe dar P, M y H idénticos a la formada a mano (invariante I2).
- La reducción sísmica al 80 % (E.030 art. 29; E.060 §15.2.5) solo se aplica con composición, a
  la componente CS a nivel de resistencia y solo para el suelo; nunca en la estabilidad
  (E.030 art. 64.2). **Una sola implementación: `depth_solver.soil_actions`**, y el factor
  `SEISMIC_REDUCTION_FACTOR` está declarado en un único sitio. Hoy en las **tres tipologías**:
  aislada, presiones de suelo de cada zapata de la conectada (D10C-2) y presiones de suelo de
  la combinada (`docs/reduccion_sismica_combinada.md`). NO en el despegue del sistema
  conectado, ni en el diseño factorizado, ni en modo directo —ahí se traza que no se aplica—.
  En la combinada el término de excentricidad `P_i·offset_i` de la resultante lleva la carga
  ya reducida: por linealidad del reparto equivale a repartir 0,8·CS.
- El incremento del 30 % de la presión admisible (**E.060 §15.2.4**) es potestativo —«se
  podrá»—: lo habilita el usuario con `allow_temporary_increase_30pct` y por defecto está
  apagado. Se aplica en las **tres** tipologías, porque el artículo habla de la presión
  admisible DEL SUELO y no de una tipología. Una sola implementación:
  `depth_solver.effective_qadm`, con `TEMPORARY_INCREASE_FACTOR` declarado en un único sitio.
  Actúa sobre la RESISTENCIA admisible; la reducción del 80 % actúa sobre las ACCIONES: son
  independientes (`docs/auditoria_incremento_30pct.md`).
- Mantener separadas las lógicas de servicio y de factorizado.
- El peso propio de cada **zapata** (concreto más relleno sobre toda la huella) lo calcula
  `engine/foundation/self_weight.py` dentro de cada solver. No volver a sumarlo en otro
  sitio.

## 9 bis. Unidades (2026-09-24)

El motor calcula **siempre en SI**: kN, kN·m, kPa, MPa, m, kN/m³. La unidad que elige el
proyectista es una preferencia de **presentación y de entrada**; el valor físico del dato
no cambia al cambiar de unidad (21 MPa son 214,14 kgf/cm², no 210).

- **Una sola tabla de equivalencias:** `engine/units/unit_registry.py`. Nadie declara un
  factor en otro sitio, y menos en la interfaz.
- **Cambiar de unidad lo resuelve el motor.** La interfaz manda la petición entera a
  `POST /api/units/rewrite` y la recibe reescrita; el mapa de qué campo es de qué magnitud
  vive en `api/unit_fields.py` y está **auditado**: `tests/test_api_unit_fields.py` exige
  que todo campo numérico esté clasificado —con magnitud o con motivo de exención—, de
  modo que un campo nuevo sin clasificar rompe el test en vez de quedarse sin convertir.
- **Para PRESENTAR resultados** la interfaz sí multiplica, pero por el factor `to_si` que
  el motor le entrega en `/api/reference`. No es una segunda tabla: es la misma.
- **Redondeo declarado:** 6 cifras significativas (`DISPLAY_SIGNIFICANT_DIGITS`). Se
  muestra y se calcula ESE valor —lo que se ve es lo que se usa— con un error relativo
  ≤ 5·10⁻⁶. Los decimales solo se recortan en LONGITUD, para que 2,50 m no se escriba
  «250.00 cm»; en resistencia no, porque convertiría un f'c declarado de 211,5 en «212».
- **La TRAZA se emite siempre en SI**, y la memoria lo dice (`TRACE_IN_SI_NOTE`). No es
  una tabla de resultados: es el registro del cálculo con su sustitución numérica, y
  además esos valores son contrato congelado (§11).
- **No se convierte** lo que el usuario no elige: volumen (m³), área de acero (cm²), masa
  (kg), diámetros y recubrimientos (mm). Son unidades de obra.

Detalle en `docs/unidades_dinamicas.md`.

## 10. Convenciones que ya produjeron defectos reales

Leer `docs/convenciones_ejes.md` y `docs/fase5a_estatica_viga.md` antes de tocar estática.

- **Ejes:** X es la dirección de B e Y la de L (E.050 art. 28.1). La viga de la conectada
  corre sobre `longitudinal_axis`.
- **Coordenada `s` de la conectada:** origen en el lindero, positiva hacia el interior;
  fuerzas positivas hacia arriba.
- **Cuerpo libre:** momentos antihorarios positivos, `Σ(s_i − s_c)·F_up + ΣM_app = 0`.
- **Momento de columna:** `ex = Mx/Q` (E.050 28.1). En el cuerpo libre entra como
  `applied_moment_in_free_body(M) = −M`.
- **Esfuerzos en la viga:** porción izquierda, `M(s) = ΣF_up·(s − s_i) + M_E050` para s > a;
  positivo = tracción abajo.
- **Ruido numérico:** un extremo de diseño por debajo de la tolerancia de cierre de su
  propia estática vale cero (`design_extreme`, `statics_tolerance`). Un residuo de 1e-13
  no es demanda.

## 11. Baselines y regresión

Contratos congelados: `tests/freeze/baseline.json` (aislada, combinada, viga) y
`tests/freeze/baseline_connected.json` (conectada).

**Nunca modificar un baseline automáticamente.** Proceso obligatorio:

```text
implementación → tests → diff por caso → revisión → aprobación explícita
→ regeneración DIRIGIDA de los casos aprobados → freeze
```

- Nunca regenerar en bloque para que pase la suite. Si un cambio toca un caso no
  previsto, detenerse y explicar por qué.
- Todo cambio de baseline documenta: qué cambió, por qué, qué casos afecta, qué
  invariantes se mantienen y por qué es intencional.
- No ampliar tolerancias para hacer pasar un test o un benchmark.
- Regenerar solo con aprobación: `FREEZE_REGEN=1 py -3 -m pytest tests/freeze -q`.

Mecánica de las instantáneas (`tests/freeze/snapshot.py`):
- `numeros` y `estados` son contrato duro; `referencias` y `estados_blandos`
  (`overall_status` de la conectada) son blandos.
- La prosa (`PROSE_FIELDS`, que incluye `hypotheses`) no se congela.
- Un campo nuevo que solo exista en algunos casos se declara en
  `OPTIONAL_WHEN_NONE_FIELDS`; uno de diagnóstico, en `DIAGNOSTIC_FIELDS`. Así no altera
  todos los casos.
- La traza se indexa por (scope, id) y `open_tbd` se emite solo cuando existe.

Referencias históricas que no se alteran sin autorización:
- Aragón P1 y P2, y §3.5;
- benchmarks de la Fase 6 (`tests/validation/`);
- golden cases (`tests/golden_cases/`);
- `baseline.json`.

## 12. Validación

Combinar:
- tests unitarios y de integración;
- invariantes físicos (equilibrio, conservación);
- **reconstrucción independiente** escrita a mano, sin llamar al código que se prueba;
- benchmarks bibliográficos;
- freeze.

Un benchmark no puede ser la única evidencia de una ecuación cuando hay riesgo de
circularidad.

Para comprobar que un test sirve, usar mutación deliberada y revertirla. Ver §15 sobre el
bytecode obsoleto.

## 13. Reglas por tipología

### Aislada

Mantiene separación servicio/factorizado, presiones, excentricidades, punzonamiento,
cortante, flexión, acero mínimo, anclaje, estabilidad con H, traza y optimización.

Su criterio de aceptación no se cambia por analogía con las otras tipologías.

### Paridad entre tipologías

Una exigencia que la norma impone a «las zapatas» **sin distinguir tipología** se verifica en
las tres. Ya se perdió tres veces —estabilidad de la combinada (D4 → pendiente 7), incremento
del 30 % de §15.2.4 y formulación del volcamiento—, una cuarta en la auditoría del
2026-09-19 —la combinada no verificaba el peralte mínimo de **E.060 §15.7** y aceptaba como
CONFORME una zapata de 0,20 m de canto— y una quinta con **H6** el 2026-09-20: solo la
combinada miraba la proporción de **E.050 art. 23.3**, y en la aislada `max_LB_ratio` es un
parámetro de BÚSQUEDA que no protege de nada.

**E.050 art. 23.3 — proporción en planta (H6).** `L/B ≤ 10`, el número de la tabla de
formas del artículo. Una sola implementación,
`engine.codes.peru.e050_soils.check_shape_ratio`, para las tres tipologías. La tabla **no
prohíbe, clasifica**: por encima del límite el elemento es una cimentación continua, otra
tipología que el motor no modela, de modo que es FAIL por **alcance** y no por incumplir un
número.

**E.050 art. 23.1 — cimentación superficial (H7).** `Df/B ≤ 5`, con **B el lado MENOR**:
tomar el mayor daría una relación más pequeña y dejaría pasar geometrías que el artículo
excluye. Es una DEFINICIÓN, no un requisito de resistencia, y el art. 23.2 enumera como
superficiales justo las tipologías que este motor resuelve. Por encima el elemento es una
cimentación PROFUNDA, gobernada por mecanismos que el motor no modela: **FAIL**, por
decisión del proyectista (2026-09-20), y no NO VERIFICADO, porque admitir una entrada
físicamente fuera del alcance deja abierta la puerta a que alguien la use.
`engine.codes.peru.e050_soils.check_shallow_foundation`, una sola implementación.

**Los dos números son distintos artículos:** el 10 es del 23.3 (forma en planta) y el 5 es
del 23.1 (profundidad sobre ancho). Confundirlos es fácil porque van seguidos.
`docs/freeze_zona_contacto_y_proporcion.md` §4, `docs/freeze_contacto_unilateral.md`.

`tests/test_auditoria_paridad_tipologias.py` lo vigila: `COMUNES_A_LAS_TRES` enumera las
verificaciones que ninguna tipología puede dejar de hacer y comprueba que las tres las emitan.
Añadir una verificación a una tipología obliga a preguntarse si la norma la impone a las otras.
Diferencias abiertas y decisiones pendientes en `docs/auditoria_paridad_tipologias.md`.

### Punzonamiento (todas las tipologías)

La causa del fallo es explícita (`PunchingFailureCause`):
- `SECCION_CRITICA_DEGENERADA`;
- `CAPACIDAD_CORTANTE_DIRECTO`;
- `CAPACIDAD_TRANSFERENCIA_MOMENTO`.

`critical_section_fits = False` **no** significa «sección inservible»: las secciones de
borde y esquina con 3 o 2 lados son usables. El diagnóstico al usuario sigue la causa
física real.

### Combinada

- Tiene motor propio: geometría, presiones, verificaciones, búsqueda y Pareto.
- **Peralte mínimo de E.060 §15.7**, con el mismo `code.min_depth_rule` y la misma
  interpretación que la aislada, sobre el peralte de la cara INFERIOR, que es el que nombra el
  artículo. Añadido en la auditoría de paridad del 2026-09-19; antes no se verificaba.
- **Estabilidad implementada (pendiente 7)**, en `engine/foundation/combined_stability.py`:
  sustituye la declaración D4. Se verifica cuando alguna combinación de SERVICIO declara
  fuerza horizontal; sin ella no se añade nada, porque el momento de las columnas ya queda
  acotado por la exigencia de núcleo central. Reduce todas las columnas a una resultante
  —`M = Σ (M_i + P_i·offset_i)`, `H = Σ H_i`— y toma el momento volcador como **envolvente**
  de las lecturas con carga total y con solo la estabilizante (criterio del programa,
  opción B). Los FS, μ y la regla de carga muerta son los de `engine/soil/stability.py`.
  Sin μ: NO VERIFICADO. Detalle en `docs/pendiente7_estabilidad_combinada.md`.
- La formulación del volcamiento es **común a las tres tipologías** desde
  `FORMULACION_VOLTEO` (aprobada 2026-09-19): la diferencia del catálogo queda **resuelta,
  no borrada**. Este módulo ya solo añade la suma de varias columnas en una resultante; el
  término por columna lo da `engine.soil.stability.axis_moments_kNm`, única fuente.
- **Cortante unidireccional en las DOS direcciones.** El longitudinal, con `b_w` = ancho
  transversal; el **transversal** (H2, 2026-09-19), con la sección crítica a `d` de la cara de
  la columna y `b_w` = **longitud completa** de la zapata, que es lo que E.060 §11.12.1.1 llama
  «un plano a través del ancho total». `Vu` integra la presión neta factorizada de la
  RESULTANTE de todas las columnas, no la presión de franja —que es criterio de reparto del
  acero—. Con varias columnas gobierna el voladizo transversal mayor.
- **Cortante longitudinal (C-V): criterio de concreto solo. CERRADO** (decisión 6,
  2026-09-20). Vu > φVc → FAIL y descarte. Es un criterio del programa, **más estricto** que
  E.060 (que admite Vn = Vc + Vs): no presentarlo como prohibición normativa **ni como
  verificación completa del modelo de cortante de E.060**. El aporte de estribos queda
  declarado FUERA DEL ALCANCE; no hay refuerzo de cortante implementado
  (`shear_reinforcement` siempre None). Ampliarlo a Vn = Vc + Vs es una **decisión de
  ingeniería nueva**, no un pendiente de implementación: exige resolver antes las ramas y la
  separación transversal, el alcance de §11.12.3 y la sección crítica de §15.5.2
  (`docs/auditoria_cv_cortante_longitudinal_combinada.md`).

### Desarrollo del refuerzo con columna descentrada (2026-09-28)

E.060 §15.6.2: la tracción se desarrolla «a cada lado» de la sección crítica (la cara de la
columna, §15.6.3). En la cara cuyo momento GOBIERNA cada dirección, la barra dispone de
`min(voladizo − rec, columna + voladizo opuesto − rec)`
(`engine.reinforcement.rebar_geometry.development_length_available`, una sola
implementación). Con la columna centrada es idéntico a lo anterior. «Solo la cara que
gobierna» es hipótesis de modelación decidida por el proyectista, no texto de la norma; la
demanda sigue siendo la ld completa a fy. Detalle y diff por caso en
`docs/freeze_desarrollo_columna_descentrada.md`.

### Búsqueda automática y linderos (combinada y conectada, 2026-09-28)

Sin rangos —o con `auto_ranges`— el motor los estima (`engine/optimization/auto_search.py`)
y busca en dos pasadas: malla gruesa y malla fina alrededor de la mejor. Es HEURÍSTICA DE
BÚSQUEDA, declarada en `search_note`: cada geometría se verifica igual y el aviso de borde
sigue midiéndose contra los rangos efectivos. En la combinada, con
`first_column_edge_distance_m = None` la posición la elige el programa (centra la resultante
de la combinación permanente, la misma ayuda de predimensionamiento de antes) y se recorta
contra los linderos (`site_limits`); cada alternativa guarda su posición y la escena y la
memoria la usan. Sin linderos y con la posición declarada, nada cambia.

### Presión de contacto: dos modelos

`KernCheckModel` es el **modelo por defecto** y el único que usan los casos congelados. Exige
la resultante dentro del núcleo central (E.060 §15.2.3, solo compresiones) y descarta lo
demás.

`EffectiveAreaModel` es **opcional y lo elige el proyectista**
(`SoilInput.use_effective_area_e050_art28`). Aplica E.050 art. 28.2-28.3 —`B' = B − 2|ex|`,
`L' = L − 2|ey|`, `q = Q/(B'·L')`— y **EXTIENDE al del núcleo, no lo sustituye**: dentro del
núcleo sigue rigiendo el pico de la distribución lineal, que es el criterio más estricto.
Elegirlo solo puede AÑADIR geometrías; ninguna de las que ya pasaban cambia de resultado.

Asimetría declarada del `qadm`, que es conservadora: el que declara el proyectista
corresponde a B×L y el art. 28 evalúa sobre B'×L'. `q > qadm` → FAIL válido; `q ≤ qadm` →
**NO VERIFICADO**, salvo que se declare `qadm_declared_for_effective_area`. Es la misma
regla de E.020 art. 20.1 en la estabilidad.

El modelo se construye en UN solo sitio, `api.mapping.contact_model_for`; ningún endpoint lo
instancia por su cuenta. `within_kern` conserva su significado geométrico literal: los
solvers preguntan `usable`.

### Campo de presión de DISEÑO: contacto unilateral

`engine/foundation/unilateral_contact.py` es la **única fuente** del campo de presión de
diseño, y es **común a punzonamiento, flexión y cortante unidireccional**. El suelo no
tracciona: la distribución es un plano truncado en cero cuyos tres coeficientes se
determinan por EQUILIBRIO.

```text
q⁺(x,y) = max(a + b·u + c·v, 0)        u = x/(B/2),  v = y/(L/2)

∫∫ q⁺ dA = Pu      ∫∫ x·q⁺ dA = Pu·ex      ∫∫ y·q⁺ dA = Pu·ey
```

Tres regímenes, y en dos la solución **se escribe**, no se itera —son la misma solución
evaluada en forma cerrada, de modo que esas geometrías no se mueven ni un bit—:

| Régimen | Condición | Solución |
|---|---|---|
| Contacto total | resultante dentro del núcleo | plano lineal `q = q_avg·(1 + 12·ex·x/B² + 12·ey·y/L²)` |
| Despegue uniaxial | `ey = 0` (o `ex = 0`) fuera del sexto | bloque triangular de `NetPressureField`: `a = 3·(dim/2 − e)`, `q(0) = 2Pu/a` |
| Biaxial con despegue | lo demás | Newton, jacobiano exacto |
| Resultante fuera de la huella | `|ex| ≥ B/2` o `|ey| ≥ L/2` | `ContactFieldImpossible`: no existe campo |

- **El núcleo de un rectángulo es el ROMBO** `|6·ex/B| + |6·ey/L| ≤ 1`, no el producto de
  los dos sextos. Con cada excentricidad dentro de su sexto pero sumando más de uno ya hay
  tracción en una esquina. Confundirlos fue un defecto real (`14_descentrada_dos_ejes`).
- **El jacobiano de Newton es exacto**, no numérico: al derivar el término de frontera de
  Leibniz se anula —el integrando vale cero justo sobre la frontera libre— y queda la
  matriz de Gram de `{1, u, v}` sobre el polígono comprimido, simétrica y definida
  positiva. Los momentos del polígono salen de las fórmulas del cordón, de modo que
  residuo y jacobiano son exactos.
- **Las integrales son exactas**: se recorta el rectángulo contra la zona comprimida
  (Sutherland-Hodgman) y se evalúan los momentos del polígono en forma cerrada. No hay
  cuadratura de por medio.
- **La carga que PUNZONA y la que produce el CAMPO son distintas**: `P_u_column_kN` y
  `field_P_u_kN`. En la aislada coinciden; en la **combinada** el campo lo produce la
  RESULTANTE de todas las columnas.
- Flexión y cortante reciben la excentricidad TRANSVERSAL (`e_transverse_m`,
  `dim_transverse_m`). En los regímenes cerrados usan la marginal 1-D, que es la integral
  exacta del mismo campo; solo en el biaxial integran el polígono.
- La excentricidad que gobierna el diseño se calcula con las cargas FACTORIZADAS y **sin
  peso propio**, y puede salirse del núcleo aunque la de servicio no lo haga.

Historia: hasta 2026-09-19 el motor recortaba a cero el campo lineal, que no equilibra
(decisión B → bloque triangular). El 2026-09-20 el punzonamiento pasó a integrar el campo
real, luego solo su parte comprimida, y finalmente —decisión 1— al contacto unilateral
completo, que es el que equilibra en los tres regímenes y cerró `punching_biaxial_uplift`.
`docs/freeze_contacto_unilateral.md`.

### Estabilidad (aislada, zapatas de la conectada y combinada)

- Fuerza estabilizante: **solo carga muerta** (E.020 art. 20.1), que exige la composición.
  Con la P total (modo directo) un cumplimiento queda **NO VERIFICADO**; un FAIL sigue siendo
  FAIL.
- Conectada (Fase 10C): en modo por casos las cargas corregidas conservan su composición por
  superposición con el mismo reparto (`redistributed_compositions`); cada aporte mantiene el
  tipo del caso que lo origina. No se infiere composición en modo directo.
- Peso propio de las zapatas en el reparto de CUERPO_RIGIDO (D10C-1): concreto y relleno del
  motor son CM. En combinación FACTORIZADA por casos llevan f_CM en las cargas del cuerpo rígido
  y en la resta R − W (mismo factor: sin doble factorización); en servicio y en modo directo,
  1,0. No hay input CE para ese peso.
- **FS adoptados por el proyecto (D10-2b, 2026-09-18): 1,50 al volteo —también con sismo— y
  1,50 al deslizamiento.** Son CRITERIO DEL PROGRAMA, no exigencia textual de la norma, y en
  dos de los tres casos son más estrictos que ella. Valores normativos, que se conservan y se
  citan: volteo 1,50 (E.020 art. 21, coincide); volteo sísmico 1,20 (E.030 art. 64.2);
  deslizamiento 1,25 (E.020 art. 22.1). **No presentar 1,50 como valor normativo**: la traza y
  la referencia de cada verificación dicen cuál es el de la norma y que el adoptado es más
  estricto. Un FS declarado por el proyectista sustituye siempre al adoptado.
  `docs/d10_2b_fs_volteo_sismico.md`.
- μ es dato del proyectista (E.020 art. 22.2). Sin μ, NO VERIFICADO.
- **Momento volcador (FORMULACION_VOLTEO, 2026-09-19), único para las tres tipologías:**

  ```text
  M_volc = max(|M_total|, |M_estabilizante|) + |H|·h
  M_total = M + P·offset     M_estab = Σ_estab (M_k + P_k·offset)   (mismo conjunto que N)
  ```

  El término `P·offset` es **estática**, y es el mismo que la presión de contacto ya usaba
  en `ex = (M + P·offset)/(P + W)`: omitirlo hacía la aislada incoherente consigo misma. La
  **envolvente** es criterio del programa (opción B), no exigencia normativa.

  **CONVENCIÓN:** el término va al miembro VOLCADOR y el estabilizador se mantiene en
  `N·dim/2`. **No** equivale a acortar el brazo de la carga —un cociente no es invariante a
  ese cambio— y es la escritura más estricta. Es hipótesis de modelación declarada.

  Una sola implementación: `engine.soil.stability.axis_moments_kNm`. No reescribir
  `P * offset` a mano en ningún otro sitio. `denoise_moment_kNm` filtra el ruido de
  cancelación (CLAUDE.md §10) cuando `M = −P·offset`, que es el caso de la zapata exterior
  de la conectada. `docs/formulacion_volteo_analisis.md`,
  `docs/freeze_formulacion_volteo.md`.

### Conectada

Unidad de búsqueda: **el sistema completo** (zapata exterior + viga + zapata interior).
No optimizar las zapatas por separado.

Declaraciones obligatorias, sin valor por defecto:
- `AnalysisModel`: `ARTICULADO` | `CUERPO_RIGIDO`;
- `CoupleTransferMode`: `EQUILIBRIO_EN_CIMENTACION` | `PAR_PURO_EN_ZAPATA`;
- `BeamSupportMode`: solo `SIN_APOYO` en esta versión; `APOYA_EN_SUELO` se rechaza (D5);
- `BeamSelfWeightMode`: `EXPLICITO` | `EN_CARGAS_DE_COLUMNA` | `DESPRECIADO`.

`StiffnessDeclaration` (TBD-C1) SÍ tiene valor por defecto, y es la excepción deliberada:
`NO_EVALUADA` es *no responder*, que es exactamente lo que había antes. Un defecto que
respondiera la pregunta sería el problema; éste la deja abierta.

Decisiones cerradas (no reabrir sin decisión explícita):

- **D1:** `CUERPO_RIGIDO` solo admite `EQUILIBRIO_EN_CIMENTACION`. `PAR_PURO` se rechaza
  por validación, sin convertirlo en silencio.
- **Despegue:** candidato rechazado (`DESPEGUE`) y la búsqueda continúa. No hay contacto
  unilateral (TBD-C12).
- **Carga neta ascendente** (2026-09-28): si en una combinación FACTORIZADA la carga
  corregida de una zapata es ≤ 0, se rechaza como `CARGA_NETA_ASCENDENTE`. El diseño de una
  zapata que cuelga de la viga (tracción arriba) no está implementado.
- **Ganchos:** se declaran por zapata y dirección (`hook_type_x/_y`); nunca se suponen. Con
  E.060 §15.6.2 la zapata de lindero suele necesitarlo: hacia el lindero la barra solo
  tiene el ancho de la columna (`docs/freeze_desarrollo_columna_descentrada.md`).
- **Linderos** (2026-09-28): el del inicio es `EdgeAnchor`; el del fondo y los laterales
  (`site_limits`) RECORTAN el barrido, porque las zapatas se modelan centradas sobre su
  columna en la dirección transversal. Correrlas exigiría torsión en la viga y reparto
  biaxial en el cuerpo rígido: decisión nueva (`docs/linderos_y_busqueda_automatica.md`).
- **Brazo medido desde el lindero:** es convención del libro y no se adopta.
- **Sección de la viga:** es dato del usuario, no eje de optimización.
- **Búsqueda:**
  - `same_depth_both_footings = False` por defecto;
  - `max_systems` es configurable (por defecto 1500) y es un límite de búsqueda, no
    físico;
  - si la búsqueda se trunca, se dice, y el resultado no se presenta como exhaustivo.
- **Ranking:** `BEAM_COMPLEXITY_PENALTY = 0.0`. No se introducen penalizaciones
  arbitrarias para alterar el ranking.

**EQUILIBRIO_EN_CIMENTACION:** la cimentación cierra el equilibrio por sí sola; al pórtico
no va nada (F_p = 0).

**PAR_PURO_EN_ZAPATA — formulación B\* (9c).** La rama transmitida al pórtico corresponde
exclusivamente al par; las cargas gravitacionales de la viga se transmiten por sus
reacciones. **No** significa «fuerza vertical neta de la viga nula». Con peso EXPLICITO:

```text
N_a        = W_V·(s_cut − x_V)/S
R_ext      = P_ext + N_a + ΔW_e
C_Z        = −[e1·(P_ext + N_a) − (x_e − L1/2)·ΔW_e + M_fb]      M_fb = −M_E050
ΔP = F_p   = −C_Z/S
P_int_corr = P_int − ΔP + W_V·(x_V − a)/S + ΔW_i
```

Invariante de carga: `P_ext_corr + P_int_corr − P_ext − P_int − W_viga = −ΔP`. Es
`expected_residual_kN`, de modo que `load_conservation_residual_kN = 0`. Con peso
DESPRECIADO, B\* reproduce bit a bit el procedimiento de Aragón P1.

**Peso propio EXPLICITO de la viga (9a).**
- Se calcula por **geometría física**. **`s_cut` no es límite de peso**: es la rótula y
  la referencia de momentos.
- Tres componentes, cada una con su cuerpo:
  - ΔW_e sobre [c_e, L1] (zapata exterior);
  - W_V en el vano libre [L1, f_i] (viga);
  - ΔW_i sobre [f_i, c_i] (zapata interior).
- Sobre una zapata la viga solo agrega lo que su concreto y su relleno no cuentan ya.
- `beam_self_weight_kN = ΔW_e + W_V + ΔW_i`.
- `z_b` (fondo de la viga sobre la base común) es obligatoria solo con EXPLICITO:
  - `z_b < 0` → `ENTRADA_INVALIDA`;
  - `z_b > h` de una zapata → NO VERIFICADO.
- Relleno sobre la viga en el vano: no se contabiliza. Si existe geométricamente, NO
  VERIFICADO (limitación `connected_beam_fill_over_span`). No inventar una carga
  equivalente.
- Detalle en `docs/fase9ac_peso_propio_viga.md`; TBD-C13 en
  `docs/tbd_c13_factorizacion_peso_viga.md`.

**Vano libre y métricas de la viga (9b).** `beam_span_m = f_i − L1` en todos los modelos
(`ConnectedFootingResult.beam_axis`). Métrica de concreto de la viga = vano libre + lo que
sobresale de cada zapata; lo que queda dentro es zapata. Sin z_b declarada, la métrica usa
z_b = 0 como hipótesis trazada (nunca la estática). Acero de viga sobre c_i − c_e, sin anclajes
ni estribos. Detalle en `docs/fase9b_vano_libre_y_metricas_viga.md`.

## 14. Reportes y API

- Un reporte indica: alternativa solicitada y evaluada, estado, verificaciones ejecutadas y
  no ejecutadas, TBD y limitaciones.
- **Regla:** la API nunca sustituye en silencio una `alternative_id` inexistente por otra
  (por ejemplo `top[0]`); responde con un error explícito (422).
- La cumplen `/api/report-combined` (busca entre todas las aceptadas) y `/api/report-connected`
  desde el pendiente 4 (`docs/pendiente4_informes_alternative_id.md`).

## 15. Entorno y comandos (Windows)

- Python: `py -3`. Ejecutar desde la raíz del proyecto. Los scripts sueltos necesitan
  `PYTHONPATH` en la raíz o `sys.path.insert`.
- No hay repositorio git: antes de sobrescribir un archivo existente, leerlo. Para
  comparar, copiar antes al directorio temporal de la sesión.
- **Tests:** `py -3 -m pytest -q`; congelamiento: `py -3 -m pytest tests/freeze -q`.
- **UI:** `cd ui && npm run build`; tipos: `npx tsc --noEmit -p .`. El build necesita
  `NODE_OPTIONS=--max-old-space-size=4096` en esta máquina: sin él, node aborta por
  memoria durante `transforming`. No es un error del código.
- **Mutación y comparación de resultados:** usar `PYTHONDONTWRITEBYTECODE=1`, `py -3 -B`
  y borrar los `__pycache__`. Un bytecode obsoleto ya contaminó una mutación.
- Los heredocs de bash con comillas mezcladas fallan en este entorno. Para parches de
  varias líneas, escribir un script Python en el directorio temporal y ejecutarlo.

## 16. Documentación

Distinguir norma, modelo físico, implementación, hipótesis, limitaciones, decisiones y
TBD. No borrar el historial de una decisión cerrada: registrar la decisión final y su
justificación. Cada fase deja su documento en `docs/`.

## 17. Forma de trabajo por tipo de tarea

- **Análisis:** problema → modelo → ecuaciones → invariantes → alternativas → recomendación.
  No implementar hasta cerrar las decisiones.
- **Implementación:** objetivo → capas afectadas → implementación → tests → resultados →
  decisiones tomadas y pendientes. Sin tocar baselines.
- **Auditoría:** hallazgo → evidencia → impacto → severidad → recomendación. No convertir
  una recomendación en código.
- **Freeze:** diff → casos afectados → invariantes → tests → aprobación → baseline.

Cuando varios pendientes dependen de una decisión común, resolver primero el contrato
común. No empezar un pendiente que depende de una decisión arquitectónica abierta.

## 18. Regla final

El objetivo no es que los tests pasen. Es que **modelo físico → ecuaciones →
implementación → verificación → resultado → traza → reporte** sean coherentes y
auditables. Cuando un resultado no puede demostrarse, el sistema dice NO VERIFICADO; nunca
convierte la incertidumbre en PASS.
