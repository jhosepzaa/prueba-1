# Eficiencia (2026-09-24): guardar proyectos y repartir el barrido

Dos mejoras pedidas tras medir dónde se iba el tiempo. Ninguna cambia un solo resultado
de ingeniería; la segunda lo demuestra con un test de igualdad exacta.

## 1. Punto de partida: las mediciones

| Medición | Antes |
|---|---|
| Abrir la memoria de la aislada | 3,90 s, de los cuales ~3 s son repetir el barrido ya hecho |
| Abrir la memoria de la combinada | 0,74 s, repitiendo también el barrido |
| Abrir la memoria de la conectada | 0,01 s (ya tenía caché desde la Fase 4H) |
| Barrido de la conectada, 1500 ternas | 5,3–6,5 s, **truncado**: el resultado no es exhaustivo |
| Perfil del barrido (aislada) | 165 186 validaciones de `pydantic` = 19 % del tiempo |
| Perfil del barrido (conectada) | 470 247 validaciones = ~25 % |
| Bundle de la interfaz | 1,17 MB en un archivo, con `three.js` siempre dentro |
| Guardar un proyecto | No existía |
| Suite de tests | 4 min 02 s; **un solo test consume 54 s** (`test_automatic_range_scales_with_the_load`) |

## 2. Guardar y abrir proyectos

### Qué es un proyecto

La **petición** de una tipología: columnas, cargas, materiales, suelo, unidades y rangos
de búsqueda. Es exactamente lo que el motor necesita para reproducir un cálculo.

**No se guardan los resultados.** Al abrir un archivo se vuelve a calcular, de modo que
lo que se ve corresponde al motor de HOY y no a una versión anterior cuyos números
pudieran haber cambiado por una corrección —como la del signo del diagrama longitudinal
del 2026-09-22—.

### Validación al abrir

Un archivo es un dato externo, no una orden. Antes de cargarlo se valida contra el
contrato de la API: la interfaz manda la petición a `/api/units/rewrite` con sus propias
unidades, que no convierte nada pero **sí la valida entera** con el mismo `pydantic` que
valida un cálculo, y devuelve los campos ausentes con su valor por omisión.

Así no hay una segunda definición de «petición válida» viviendo en la interfaz. Se
rechazan con mensaje, sin tocar lo que hay en pantalla:

- un archivo que no es JSON;
- uno sin la marca de formato;
- uno de una versión de formato distinta (no se carga a medias);
- uno cuya petición el motor rechaza.

Un archivo de OTRA tipología se abre **en la suya**, cambiando de pestaña: abrir un
proyecto es abrir ese proyecto.

### Memoria del navegador

Además, cada pantalla recuerda lo último escrito (`localStorage`, una clave por
tipología, con número de formato). Vive solo en ese navegador, no sustituye al archivo y
si está bloqueado —modo privado, cuota llena— se descarta en silencio y la pantalla
arranca con el ejemplo, como antes.

Archivos: `ui/src/lib/project.ts`, `ProjectPanel` en `ui/src/components/SharedInputs.tsx`.

## 3. Barrido de la conectada repartido entre procesos

### Lo que había que demostrar

No que fuera más rápido: que da **exactamente lo mismo**. Un barrido repartido puede
cambiar sin querer qué candidatos se evalúan, cuántos y con qué identificadores, porque:

- dentro de cada planta el recorrido se detiene en la primera pareja de peralte aceptada;
- el tope `max_systems` se aplica candidato a candidato;
- los `CONN-xxx` se asignan por orden de aparición.

### Diseño

- La unidad de reparto es la **planta** (las cuatro dimensiones en planta), no el
  candidato suelto: así la parada por primera pareja aceptada ocurre dentro de un proceso.
- El padre **consume los resultados en el orden del barrido** y aplica el tope candidato a
  candidato, igual que el recorrido secuencial.
- Ventana deslizante de `procesos + 2` tareas, con varias plantas por tarea. La primera
  versión usaba `map` sobre todo el barrido y los procesos seguían calculando geometrías
  que nadie iba a leer: un 73 % de trabajo tirado que se comía la ganancia.
- Las plantas se generan **perezosamente**. Materializarlas costaba construir decenas de
  miles de geometrías que el barrido no llega a mirar; corregirlo aceleró también el
  camino secuencial y bajó la suite de 4:02 a 2:57.
- Los procesos se **reutilizan** entre barridos: arrancarlos cuesta 0,55 s en Windows. El
  contexto (3 KB) viaja con cada tarea en lugar de instalarse al arrancar, que es lo que
  permite reutilizarlos.
- Por debajo de 400 candidatos no se reparte: arrancar cuesta más de lo que ahorra.
- Si no hay recursos para crear procesos, o uno cae, se sigue por el camino secuencial.

`workers=1` fuerza el recorrido secuencial; `None` lo decide por tamaño.

### Resultados medidos

| Caso | Secuencial | Repartido | |
|---|---|---|---|
| Barrido con mayoría de rechazos (1500) | 4,75 s | 2,44 s | **1,9×** |
| Barrido con 841 aceptadas (1500) | 5,32 s | 3,44 s | **1,55×** |
| Endpoint completo `/api/design-connected` | 9,28 s | 6,41 s | **1,4×** |

Rendimiento puro del cálculo repartido: 1,32 ms por candidato frente a 4,30 ms
secuencial, **3,3×**. La diferencia entre ese 3,3× y el 1,4× del endpoint es trabajo que
ocurre en el padre y no se reparte (ley de Amdahl): generar las plantas, deserializar los
resultados y **construir la respuesta**.

### Por qué no es 8×

Con 12 núcleos y 8 procesos, el techo teórico nunca se alcanza porque:

1. cada resultado aceptado pesa 76 KB y cruzar el proceso cuesta 1,5 ms (0,58 serializar +
   0,89 deserializar), y la parte del padre es serial;
2. construir la respuesta del endpoint para 841 alternativas cuesta ~3 s, y ahí el perfil
   señala **191 660 construcciones de modelos `pydantic`** y recorridos repetidos de la
   traza (`open_tbd_entries`, `implemented_checks_status`), que se recalculan por
   alternativa cada vez que se consultan.

Eso es lo siguiente que conviene atacar, y beneficia a las tres tipologías.

## 4. Verificación

- `tests/test_barrido_paralelo_conectada.py`: los dos caminos dan el MISMO barrido campo
  por campo, con tope holgado y con tope que corta a mitad de planta; el caso de prueba
  mezcla aceptaciones y rechazos; con tope pequeño no se evalúa ni un candidato de más.
- Suite completa: **2053 pasan, 2 se saltan**, congelamiento incluido, sin tocar ningún
  baseline.
- Dos tests que inspeccionaban el CÓDIGO FUENTE de `generate_connected_alternatives`
  buscando el criterio de aceptación se apuntaron a `_evaluar_planta` y `_acumular`, que
  es donde vive ahora la decisión. El invariante que vigilan no cambia: el criterio sale
  de la máquina de estados (`.discards`) y no de una lista escrita a mano.

## 5. Lo que NO se hizo, y por qué

- **Subir el tope de 1500 ternas.** Ahora el barrido lo permitiría, pero explorar más
  geometrías puede cambiar cuál es la mejor alternativa: es una decisión del proyectista
  sobre el alcance de la búsqueda, no una optimización. Se propone, no se aplica.
- **Quitar validación de `pydantic` del bucle caliente.** Es el 19–25 % del barrido y
  buena parte del coste de la respuesta, pero exige distinguir dónde la validación protege
  de verdad (la entrada del usuario) y dónde no (objetos que el motor acaba de calcular).
  Es un trabajo aparte, con sus tests.
