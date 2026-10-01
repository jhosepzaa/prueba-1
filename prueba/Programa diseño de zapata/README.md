# Diseño y optimización de cimentaciones de concreto armado — RNE Perú

Motor de cálculo, API e interfaz para diseñar, verificar y optimizar **zapatas
aisladas, zapatas combinadas y cimentaciones conectadas con viga**, además de la
**viga de conexión** por separado, según el Reglamento Nacional de Edificaciones del
Perú (E.050, E.060, E.030, E.020).

**2087 tests pasan y 2 se saltan.** El motor funciona de forma completamente
independiente de la API y de la interfaz.

No es un calculador dimensional: cada resultado lleva su ecuación, su sustitución
numérica, su hipótesis y su referencia normativa, y el programa dice explícitamente qué
verificó, qué no pudo verificar y por qué.

## Puesta en marcha

Dependencias (una sola vez):

```bash
py -3 -m pip install pydantic pytest fastapi "uvicorn[standard]" httpx2
```

```bash
cd ui && npm install
```

### Uso normal

Doble clic en `Abrir programa.bat`, o bien:

```bash
py -3 -m uvicorn api.server:app --port 8000
```

Abrir <http://localhost:8000> — FastAPI sirve la interfaz ya compilada. La
[guía de uso](docs/guia_de_uso.html) explica el programa entero, pantalla por pantalla.

### Modo desarrollo (recarga automática)

Terminal 1 — motor y API:

```bash
py -3 -m uvicorn api.server:app --reload --port 8000
```

Terminal 2 — interfaz, en <http://localhost:5173>:

```bash
cd ui && npm run dev
```

Para recompilar la interfaz hace falta ampliar la memoria de node en esta máquina:

```bash
cd ui && NODE_OPTIONS=--max-old-space-size=4096 npm run build
```

### Ejecutar las verificaciones

```bash
py -3 -m pytest -q
```

## Arquitectura

```
engine/          Motor de cálculo puro. Sin dependencias de UI ni de red.
  codes/         Disposiciones normativas intercambiables (peru/, futuro aci/)
  domain/        Modelos de entrada: columna, suelo, materiales, cargas
  units/         Registro único de unidades: entrada, presentación y conversión
  soil/          Presión de contacto, excentricidad, estabilidad
  foundation/    Peralte efectivo, flexión, cortante, punzonamiento, contacto unilateral
  analysis/      Estática de la viga de conexión y diagramas de la combinada
  reinforcement/ Acero: selección, alternativas, geometría, desarrollo
  optimization/  Generación de alternativas, scoring, Pareto, ranking, barrido paralelo
  reports/       Memoria de cálculo de cada tipología
  results/       Estados, CalculationTrace, vocabulario, registro de limitaciones
api/             FastAPI. Traduce DTOs ↔ motor. No contiene ingeniería.
ui/              React + TypeScript. Solo presenta; no calcula nada.
docs/            Guía de uso, manual, auditorías, fichas y fuentes normativas
tests/           92 archivos, 8 casos golden verificados a mano, 8 benchmarks
                 bibliográficos y los contratos congelados de tests/freeze/
```

**Regla arquitectónica verificada por test:** ninguna ecuación de ingeniería vive
en `api/` ni en `ui/`. Las fórmulas, sus sustituciones numéricas y sus referencias
normativas se calculan en `engine/` y viajan resueltas hasta la pantalla. La conversión
de unidades también: la interfaz declara en qué unidad viene o va un dato, y el motor
convierte.

## Alcance normativo

Implementado con cita verificada contra el PDF de cada norma
([auditoría de citas](docs/auditoria_normativa_citas.md): 65 designaciones, cuatro normas).

| Tema | Referencia |
|---|---|
| Cargas de servicio para geometría | E.060 §15.2 · E.050 art. 17.1 |
| Combinaciones de carga | E.060 §9.2 (las declara el usuario; el motor no las genera) |
| Sin tracciones suelo-zapata | E.060 §15.2.3 |
| Excentricidad y área efectiva | E.050 art. 28.1 · 28.2–28.3 (modelo opcional) |
| Factores φ (0,90 flexión / 0,85 cortante) | E.060 §9.4 |
| Flexión: sección crítica e hipótesis | E.060 §15.4 · §10.2 |
| As mínimo en zapatas | E.060 §9.7 vía §10.6 (§10.5.1 excluye zapatas) |
| Distribución en dirección corta | E.060 §15.4.4, ec. 15-1 |
| Cortante unidireccional | E.060 ec. 11-3 · §11.12.1.1 (ancho total) |
| Punzonamiento | E.060 §11.12.2.1, ec. 11-41 / 11-42 / 11-43 |
| Transferencia de momento | E.060 §11.12.7 (ec. 11-45, 11-46) y ec. 13-1 (γf) |
| Longitud de desarrollo y ganchos | E.060 §15.6 → Cap. 12 |
| Recubrimiento y separaciones | E.060 §7.7 · §7.6.6 · §9.7.3 |
| Peralte mínimo | E.060 §15.7 (interpretación adoptada, parametrizable) |
| Zapatas de varias columnas | E.060 §15.10.1 (§15.10.2 prohíbe el Método Directo) |
| Viga de conexión: rigidez | E.060 §15.2.6 (la evalúa el proyectista; TBD-C1) |
| Viga de conexión: dimensión y confinamiento | E.060 §21.12.3.2 · E.030 art. 65.1 |
| Proporción en planta y profundidad | E.050 art. 23.3 (L/B ≤ 10) · art. 23.1 (Df/B ≤ 5) |
| Profundidad mínima de cimentación | E.050 art. 26.2 (Df ≥ 0,80 m, salvo roca) |
| Estabilidad: volteo y deslizamiento | E.020 art. 20.1 · 21 · 22.1 · 22.2 · E.030 art. 64.2 |
| Incremento del 30 % de q admisible | E.060 §15.2.4 (potestativo, lo habilita el usuario) |
| Reducción sísmica al 80 % | E.030 art. 29 · E.060 §15.2.5 (solo con cargas por casos) |

Los factores de seguridad **adoptados por el programa** (1,50 al volteo, también con
sismo, y 1,50 al deslizamiento) son criterio del proyecto y no cita normativa: la traza
dice en cada verificación cuál es el valor de la norma y que el adoptado es más estricto
([decisión D10-2b](docs/d10_2b_fs_volteo_sismico.md)).

## Limitaciones declaradas

El motor lleva un registro formal ([limitations.py](engine/results/limitations.py)) con
**12 limitaciones**, que emite al `CalculationTrace` cuando corresponde.

**Cuatro de ellas pueden producir un PASS falso**, y las cuatro son de la cimentación
conectada. No están escondidas: cada una se declara, se traza y aparece en la memoria.

- Presión uniforme bajo la zapata de lindero: depende de que la viga sea lo bastante
  rígida, lo que E.060 §15.2.6 exige evaluar y no da método para ello (TBD-C1).
- Reacción del terreno bajo la viga de conexión: se ignora, lo que sobrestima la
  transferencia.
- Relleno sobre la viga en el vano libre: no se contabiliza.
- Factor de carga muerta del peso propio de la viga en modo directo, si no se declara
  (TBD-C13).

Otras limitaciones, sin ese riesgo: interpretación de §15.7 (configurable), columnas
circulares fuera de alcance (se rechazan en la entrada), `Jc` de §11.12.7 como derivación
geométrica estándar y no ecuación numerada, y la masa de acero con longitud recta, sin
ganchos ni traslapes.

## Documentación

- [Guía de uso](docs/guia_de_uso.html) — cómo abrir el programa y usarlo entero
- [Manual de usuario](docs/manual_usuario.html) — detalle campo por campo
- [Estado del proyecto](docs/estado_proyecto.md) — fases cerradas y pendientes abiertos
- [Convenciones de ejes](docs/convenciones_ejes.md)
- [Referencias normativas E.060 / E.050](docs/normativa/referencias_e060_e050.md)
- [Contraste de E.060 con el motor](docs/normativa/contraste_e060_motor.md)
- [Unidades dinámicas](docs/unidades_dinamicas.md)
- [Calidad de las propuestas](docs/calidad_de_las_propuestas.md)
- [Reglas del proyecto](CLAUDE.md)

## Fuera de alcance

Cimentaciones profundas, losas de cimentación, plateas, muros de sostenimiento,
interacción suelo-estructura avanzada, análisis no lineal y elementos finitos. En la
combinada, el aporte de estribos al cortante longitudinal queda declarado fuera de
alcance (criterio de concreto solo, más estricto que E.060).
