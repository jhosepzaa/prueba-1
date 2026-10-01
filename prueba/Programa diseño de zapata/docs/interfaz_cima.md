# Interfaz CIMA — integración del handoff «Cimentación 3D»

Fecha: 2026-09-27. Alcance: solo `ui/` y documentación. **El motor no se modificó**; la API
tampoco. Sin cambios de baseline.

Origen: handoff de diseño `design_handoff_cimentacion_3d/` (README, `Cimentacion 3D.html`,
`three-d-stage.js`), entregado por el usuario.

## 1. Qué se adoptó del diseño

| Elemento | Implementación |
|---|---|
| Tokens (colores, bordes, acento oklch, acero), IBM Plex Sans/Mono | `ui/src/styles.css` (`:root`), fuentes locales `@fontsource/ibm-plex-*` importadas en `main.tsx` |
| Cabecera de 56 px: marca, subtítulo, «Tipo de cimentación» con glifos de planta 30×18, unidades | `components/Cima.tsx` → `CimaHeader` |
| Visor: modos Modelo/Transparente/Armadura/Sección (1–4), corte A–A / transversal, capas Cotas (D), Suelo (S), Ejes, Cargas, gizmo de 96 px, vistas y Restablecer (R), barra de pasos, leyenda, exportación OBJ+MTL y GLB | `components/FoundationViewer.tsx` + `viewer3d/stage.ts` |
| Materiales, luces, amortiguación de órbita, transiciones de 0,9 s por tramo con `easeInOutCubic`, barras que crecen escalonadas | `viewer3d/stage.ts`, `viewer3d/model.ts` |
| Rutas de transformación entre tipologías («Agregar columna C2», «Unificar zapata», «Viga de conexión»…) | `viewer3d/model.ts` → `ruta()` |
| Panel de propiedades de 316 px con filas `30px 1fr auto` | `Cima.tsx` → `PanelPropiedades`, datos en `viewer3d/datos.ts` |

Lo que el diseño no tenía y la aplicación sí —formularios, tablas, traza, memoria— se viste
con el mismo lenguaje: el cajón **Datos** (izquierda) aloja los paneles de entrada y el dock
**Resultados** (abajo, Mitad/Completo/Ocultar) aloja las vistas de resultados sin cambios de
contenido.

## 2. Desviaciones deliberadas del diseño

El diseño es un modelo paramétrico libre; el programa no. Cada desviación responde a CLAUDE.md §2
(«la UI presenta, no calcula»):

1. **Propiedades de solo lectura.** En el diseño se editan B, L, h… y el modelo cambia. Aquí la
   geometría la decide el optimizador; editarla en el panel sería presentar una geometría que el
   motor no verificó. Los datos se cambian en el cajón y se recalcula.
2. **Antes de calcular, esquema.** El visor muestra un esquema rotulado «Esquema · sin calcular»
   que solo acota lo que ya es dato (Df, sección de columnas, sección y luz de la viga).
3. **Armadura solo donde el motor la posiciona.** La aislada dibuja las barras que resuelve
   `FootingSceneDTO`. `CombinedSceneDTO` y `ConnectedSceneDTO` no traen posiciones de barras: el
   visor lo dice («Armadura no dibujada») y no inventa una parrilla.
4. **Sin armado de columna ni estribos.** Fuera del alcance del motor; la leyenda no los incluye.
5. **Cargas solo en modo directo:** la mayor P de servicio de cada columna, rotulada con su
   combinación. En modo por casos no hay una única P que mostrar sin elegirla.
6. **Sin telemetría:** el `postMessage` de exportación del prototipo no se portó.

Adaptaciones de presentación (no cambian ningún valor): la columna se prolonga hasta NTN + 1,0 m
para leerse sobre el terreno; las cotas en planta del motor se elevan a la cara superior; la
combinada se gira cuando su dirección longitudinal es Y; `preserveDrawingBuffer` permite capturar
el lienzo.

## 3. Coherencia de rótulos con el motor

- **Cotas en la unidad del usuario.** Se conserva el texto del rótulo del motor y se sustituye
  solo el número, medido en la escena (`model.ts` → `textoCota`). Antes se duplicaba el valor
  («0.25 m al eje de C1 = 0.25 m»).
- **Combinada.** La escena del motor nombra B y L por eje (X, Y); el resultado y el panel, por
  significado (largo entre columnas, ancho). El visor rotula esas dos cotas «Largo» y «Ancho»
  para no llamar «B» a lo que el panel llama «L».
- **Conectada.** Las cotas conservan los rótulos del motor («zapata de lindero», «entre ejes»,
  «vano libre»…). En el panel, B y L siguen a los ejes (E.050 art. 28.1) y se indica cuál es la
  longitudinal según `longitudinal_axis`; antes se rotulaba B como «longitudinal» siempre.
- Recubrimiento en mm (§9 bis: unidad de obra).

## 4. Textos corregidos de paso

- Bienvenida de la conectada: decía que la tipología «no puede alcanzar PASS hoy» porque TBD-C1
  «no tiene criterio normativo». Desde la decisión 4 eso es falso (CLAUDE.md §6 y §8). Ahora
  explica la declaración de rigidez de §15.2.6. También el apoyo en el suelo (rechazado, TBD-C4)
  y la sección de la viga (dato, no eje de búsqueda).
- Tooltip «Modelo de análisis» del panel de la conectada, por la misma razón.
- «todas las válidas» → «todas las aceptadas» (§5, vocabulario).

**Pendiente fuera de alcance:** `engine/reports/connected_report.py` → `TBD_DESCRIPTIONS`
conserva los textos antiguos de TBD-C1 y TBD-C4, y los muestra la pestaña de pendientes de la
conectada. Es texto del motor: exige propuesta y aprobación (§3).

## 5. Pantallas estrechas

- ≤ 1500 px: el cajón de datos flota sobre el visor y se cierra al llegar un resultado;
  Guardar/Abrir salen de la cabecera (siguen en el cajón).
- ≤ 1400 px: se ocultan el rótulo «Tipo de cimentación» y las unidades de la cabecera.
- ≤ 900 px: una columna (cabecera, datos, visor, propiedades).

## 6. Verificación

- `npx tsc --noEmit` limpio; `npm run build` correcto.
- `py -3 -m pytest -q`: 2087 pasan, 2 se saltan.
- En el navegador, a 1024×768 y 1440×900: esquema y cálculo de las cuatro tipologías, modos
  Transparente/Armadura/Sección, transiciones Aislada → Combinada → Conectada → Viga, cierre
  automático del cajón, dock y consola sin errores.

Archivos: `ui/src/App.tsx`, `ui/src/main.tsx`, `ui/src/styles.css`, `ui/index.html`,
`ui/src/components/{Cima,FoundationViewer}.tsx`, `ui/src/viewer3d/{model,stage,datos}.ts`,
`ui/src/lib/units.ts` (`si`), `onListo` en los cuatro paneles de entrada, selección controlada en
`ResultsView.tsx`. Eliminado `ui/src/components/Shell.tsx` (armazón anterior, sin uso).
